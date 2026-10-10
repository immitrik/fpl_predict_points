"""Gradient-boosting (or random-forest) models for each scoring event.

Predicting events rather than points keeps the models independent of the scoring rules, which
are applied afterwards (baseline.events_to_points). Models are trained on stacked feature
frames for horizons h = 1..MAX_H so that predictions for distant fixtures are appropriately
less certain.
"""
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier, LGBMRegressor
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor

from .features import EWM_SETS

MAX_H = 6
POS_CODE = {"GKP": 0, "DEF": 1, "MID": 2, "FWD": 3}
COUNT_STATS = ["goals_scored", "assists", "bonus", "yellow_cards"]
MIN_DC_ROWS = 5000

MARKET_FEATURES = ["odds_gf", "odds_ga", "mk_att", "mk_def", "opp_mk_att", "opp_mk_def", "rest", "opp_rest"]
PLAYER_FEATURES = (
    [f"{p}_{c}" for p, (_, cols) in EWM_SETS.items() for c in cols]
    + ["n", "n_dc", "h", "was_home", "pos", "value", "sel_rank", "exp_gf", "exp_ga",
       "att_s", "def_s", "opp_att_s", "opp_def_s"] + MARKET_FEATURES
)
TEAM_FEATURES = ["exp_gf", "exp_ga", "att_s", "def_s", "opp_att_s", "opp_def_s", "was_home", "h"] + MARKET_FEATURES


def design(f: pd.DataFrame, cols: list[str], fill: float | None = None) -> pd.DataFrame:
    x = f.assign(pos=f["position"].map(POS_CODE), was_home=f["was_home"].astype(int))[cols]
    x = x.astype("float32")
    return x if fill is None else x.fillna(fill)


class Learner:
    """Thin wrapper so LightGBM and random forest share one interface."""

    def __init__(self, algo: str, kind: str, objective: str | None = None) -> None:
        self.algo, self.kind = algo, kind
        if algo == "lgbm":
            params = dict(n_estimators=300, learning_rate=0.04, num_leaves=31,
                          min_child_samples=200, subsample=0.8, subsample_freq=1,
                          colsample_bytree=0.7, reg_lambda=5.0, n_jobs=-1, verbose=-1)
            if kind == "clf":
                self.model = LGBMClassifier(**params)
            else:
                self.model = LGBMRegressor(objective=objective or "regression", **params)
        elif algo == "rf":
            params = dict(n_estimators=100, min_samples_leaf=100, max_features=0.4,
                          max_samples=0.3, n_jobs=-1, random_state=0)
            self.model = (RandomForestClassifier if kind == "clf" else RandomForestRegressor)(**params)
        else:
            raise ValueError(algo)

    def fit(self, x: pd.DataFrame, y: pd.Series) -> "Learner":
        self.const = None
        if y.nunique() < 2:  # e.g. goalkeepers never score: nothing to learn, predict the constant
            self.const = float(y.iloc[0]) if len(y) else 0.0
            return self
        self.model.fit(x.fillna(-1) if self.algo == "rf" else x, y)
        return self

    def predict(self, x: pd.DataFrame) -> np.ndarray:
        if self.const is not None:
            return np.full(len(x), self.const)
        x = x.fillna(-1) if self.algo == "rf" else x
        if self.kind == "clf":
            return self.model.predict_proba(x)[:, 1]
        return self.model.predict(x)


class EventModels:
    def __init__(self, algo: str = "lgbm") -> None:
        self.algo = algo
        self.m: dict[str, Learner] = {}

    def fit(self, train: pd.DataFrame) -> "EventModels":
        """`train`: stacked feature frames (column `h`) of played rows."""
        a = self.algo
        x_all = design(train, PLAYER_FEATURES)
        self.m["play"] = Learner(a, "clf").fit(x_all, train["played"])
        self.m["p60"] = Learner(a, "clf").fit(x_all, train["p60"])

        pl = train["minutes"] > 0
        x_pl = x_all[pl.to_numpy()]
        tp = train[pl]
        self.m["minutes"] = Learner(a, "reg").fit(x_pl, tp["minutes"])
        for stat in COUNT_STATS:
            self.m[stat] = Learner(a, "reg", "poisson").fit(x_pl, tp[stat])
        gk = (tp["position"] == "GKP").to_numpy()
        if gk.any():
            self.m["saves"] = Learner(a, "reg", "poisson").fit(x_pl[gk], tp.loc[gk, "saves"])

        dc = tp["dc_ind"].notna().to_numpy()
        if dc.sum() >= MIN_DC_ROWS and tp.loc[dc, "dc_ind"].nunique() > 1:
            self.m["dc"] = Learner(a, "clf").fit(x_pl[dc], tp.loc[dc, "dc_ind"])

        teams = train.drop_duplicates(["season", "fixture", "team", "h"])
        self.m["cs"] = Learner(a, "clf").fit(design(teams, TEAM_FEATURES), (teams["opp_score"] == 0).astype(int))
        return self

    def apply(self, ev: pd.DataFrame) -> pd.DataFrame:
        """Override the event expectations of `ev` (baseline.expected_events output)."""
        out = ev.copy()
        av = out["avail"].to_numpy()
        x = design(out, PLAYER_FEATURES)
        p_play = np.clip(self.m["play"].predict(x), 0, 1)
        p60 = np.minimum(np.clip(self.m["p60"].predict(x), 0, 1), p_play)
        out["p_play"], out["p60"] = p_play, p60
        out["m_play"] = np.clip(self.m["minutes"].predict(x), 1, 90)
        out["xmin"] = p_play * out["m_play"] * av
        for stat, col in zip(COUNT_STATS, ["x_goals", "x_assists", "x_bonus", "x_yellow_cards"]):
            out[col] = p_play * av * np.clip(self.m[stat].predict(x), 0, None)
        gk = (out["position"] == "GKP").to_numpy()
        sv = np.zeros(len(out))
        if gk.any() and "saves" in self.m:
            sv[gk] = p_play[gk] * av[gk] * np.clip(self.m["saves"].predict(x[gk]), 0, None)
        out["x_saves"] = sv
        if "dc" in self.m:
            pdc = self.m["dc"].predict(x)
            out["x_dc"] = np.where(out["position"] == "GKP", 0.0, p_play * av * pdc)
        out["p_cs_team"] = np.clip(self.m["cs"].predict(design(out, TEAM_FEATURES)), 0.005, 0.95)
        return out


class PositionModels:
    """One EventModels per position: each learns its own relationships (keepers vs strikers...)."""

    def __init__(self, algo: str = "lgbm") -> None:
        self.algo = algo
        self.by_pos: dict[str, EventModels] = {}

    def fit(self, train: pd.DataFrame) -> "PositionModels":
        for pos in POS_CODE:
            self.by_pos[pos] = EventModels(self.algo).fit(train[train["position"] == pos])
        return self

    def apply(self, ev: pd.DataFrame) -> pd.DataFrame:
        parts = [self.by_pos[pos].apply(ev[ev["position"] == pos]) for pos in POS_CODE
                 if (ev["position"] == pos).any()]
        return pd.concat(parts).loc[ev.index]


def make_models(spec: str):
    """`lgbm` / `rf` = one global model; `lgbm-pos` / `rf-pos` = one model per position."""
    algo, _, suffix = spec.partition("-")
    return PositionModels(algo) if suffix == "pos" else EventModels(algo)
