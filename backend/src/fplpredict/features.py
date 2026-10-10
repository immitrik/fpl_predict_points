"""As-of features: everything is computed from matches strictly before the row's fixture.

Player and team histories are exponentially weighted moving averages over matches. Future
(unplayed) rows carry NaN stats; an EWM over a NaN row keeps its previous value, so shifting
by `h` rows gives, for the h-th upcoming match, the state after the last *played* match.
The same shift on past rows reproduces "what we knew h matches ahead", which is how the
ML models learn to be less certain about distant fixtures.
"""
import numpy as np
import pandas as pd

from .scoring import DC_THRESHOLD

TEAM_HALFLIFE = 6
TEAM_PRIOR_MATCHES = 5
TEAM_MAX_N = 17

# prefix -> (halflife in matches, stats)
EWM_SETS = {
    "ew": (5, ["minutes", "played", "p60", "goals_scored", "expected_goals", "assists",
               "expected_assists", "bonus", "saves", "yellow_cards", "red_cards", "own_goals",
               "penalties_saved", "penalties_missed", "dc_ind", "total_points"]),
    "fw": (2, ["minutes", "played", "p60", "total_points", "goals_scored", "expected_goals",
               "assists", "expected_assists", "bonus", "sel_rank"]),
    "sw": (15, ["minutes", "played", "goals_scored", "expected_goals", "assists",
                "expected_assists", "bonus", "saves", "yellow_cards", "dc_ind", "total_points"]),
}


def prepare(frame: pd.DataFrame) -> pd.DataFrame:
    """Sort chronologically and add per-match indicators (NaN for unplayed rows)."""
    f = frame.sort_values(["kickoff_time", "fixture", "code"]).reset_index(drop=True)
    mins = f["minutes"]
    f["played"] = (mins > 0).astype(float).where(mins.notna())
    f["p60"] = (mins >= 60).astype(float).where(mins.notna())
    # ownership percentile among all players in the same gameweek ("wisdom of the crowd")
    # (played rows and not-yet-played rows are ranked separately: their `selected` scales differ)
    f["sel_rank"] = f.groupby(["season", "round", f["minutes"].isna()])["selected"].rank(pct=True)
    thr = f["position"].map(DC_THRESHOLD).astype(float)
    f["dc_ind"] = (f["defensive_contribution"] >= thr).astype(float).where(
        f["defensive_contribution"].notna())
    return f


class FeatureBuilder:
    """Computes EWM states once; `at(h)` returns features as known h matches before each row."""

    def __init__(self, frame: pd.DataFrame, odds: pd.DataFrame | None = None) -> None:
        self.odds = odds
        self.base = prepare(frame)
        fc = self.base.sort_values(["code", "kickoff_time", "fixture"])
        self.codes = fc["code"]
        self.player_state = {
            prefix: fc.groupby("code")[cols].ewm(halflife=hl).mean().reset_index(level=0, drop=True)
            for prefix, (hl, cols) in EWM_SETS.items()
        }
        self.sel_own = fc["sel_rank"]
        self.count_n = fc["minutes"].notna().groupby(self.codes).cumsum()
        self.count_dc = fc["dc_ind"].notna().groupby(self.codes).cumsum()
        self._init_teams()

    # -- teams ---------------------------------------------------------------------------
    def _init_teams(self) -> None:
        f = self.base
        tm = f.groupby(["season", "fixture", "team"], as_index=False).agg(
            opponent=("opponent", "first"), was_home=("was_home", "first"),
            kickoff_time=("kickoff_time", "first"), gf=("team_score", "first"),
            ga=("opp_score", "first"), xgf=("expected_goals", lambda s: s.sum(min_count=1)),
        )
        opp_xg = tm[["season", "fixture", "team", "xgf"]].rename(
            columns={"team": "opponent", "xgf": "xga"})
        tm = tm.merge(opp_xg, on=["season", "fixture", "opponent"], how="left")
        tm = self._attach_odds(tm)
        tm["att_raw"] = 0.5 * tm["gf"] + 0.5 * tm["xgf"]
        tm["def_raw"] = 0.5 * tm["ga"] + 0.5 * tm["xga"]
        tm = tm.sort_values(["team", "kickoff_time", "fixture"]).reset_index(drop=True)
        # schedule density: days since the team's previous (scheduled) match
        rest = tm.groupby("team")["kickoff_time"].diff().dt.total_seconds() / 86400
        tm["rest"] = rest.fillna(7.0).clip(upper=14.0)

        played = tm[tm["att_raw"].notna()]
        self.lg = {
            "all": float(played["att_raw"].mean()),
            "home": float(played.loc[played["was_home"], "att_raw"].mean()),
            "away": float(played.loc[~played["was_home"], "att_raw"].mean()),
        }
        self.lg["mk"] = float(tm["odds_gf"].mean()) if tm["odds_gf"].notna().any() else self.lg["all"]
        self.tm = tm
        self.team_ew = tm.groupby("team")[["att_raw", "def_raw", "odds_gf", "odds_ga"]].ewm(
            halflife=TEAM_HALFLIFE).mean().reset_index(level=0, drop=True)
        self.team_n = tm["att_raw"].notna().groupby(tm["team"]).cumsum()
        self.team_mk_n = tm["odds_gf"].notna().groupby(tm["team"]).cumsum()

    def _attach_odds(self, tm: pd.DataFrame) -> pd.DataFrame:
        """Market-implied goals for/against of each team-match (NaN where odds are unknown)."""
        tm = tm.copy()
        tm["odds_gf"] = np.nan
        tm["odds_ga"] = np.nan
        if self.odds is None:
            return tm
        home = np.where(tm["was_home"], tm["team"], tm["opponent"])
        away = np.where(tm["was_home"], tm["opponent"], tm["team"])
        key = pd.DataFrame({"season": tm["season"], "home": home, "away": away})
        o = key.merge(self.odds[["season", "home", "away", "lam_h", "lam_a"]], how="left",
                      on=["season", "home", "away"])
        tm["odds_gf"] = np.where(tm["was_home"], o["lam_h"], o["lam_a"])
        tm["odds_ga"] = np.where(tm["was_home"], o["lam_a"], o["lam_h"])
        return tm

    def _team_at(self, h: int) -> pd.DataFrame:
        tm, lg = self.tm, self.lg["all"]
        ew = self.team_ew.groupby(tm["team"]).shift(h)
        n = np.minimum(self.team_n.groupby(tm["team"]).shift(h).fillna(0), TEAM_MAX_N)
        out = tm[["season", "fixture", "team", "rest", "odds_gf", "odds_ga"]].copy()
        for raw, name in (("att_raw", "att_s"), ("def_raw", "def_s")):
            out[name] = (n * ew[raw].fillna(lg) + TEAM_PRIOR_MATCHES * lg) / (n + TEAM_PRIOR_MATCHES)
        # market-based ratings: smoothed odds-implied goals for / against
        mk = self.lg["mk"]
        nm = np.minimum(self.team_mk_n.groupby(tm["team"]).shift(h).fillna(0), TEAM_MAX_N)
        for raw, name in (("odds_gf", "mk_att"), ("odds_ga", "mk_def")):
            out[name] = (nm * ew[raw].fillna(mk) + TEAM_PRIOR_MATCHES * mk) / (nm + TEAM_PRIOR_MATCHES)
        return out

    # -- full feature frame -----------------------------------------------------------------
    def at(self, h: int = 1) -> pd.DataFrame:
        f = self.base
        tf = self._team_at(h)
        f = f.merge(tf, on=["season", "fixture", "team"], how="left")
        opp = tf.drop(columns=["odds_gf", "odds_ga"]).rename(columns={
            "team": "opponent", "att_s": "opp_att_s", "def_s": "opp_def_s",
            "mk_att": "opp_mk_att", "mk_def": "opp_mk_def", "rest": "opp_rest"})
        f = f.merge(opp, on=["season", "fixture", "opponent"], how="left")
        lg = self.lg
        lg_for = np.where(f["was_home"], lg["home"], lg["away"])
        lg_against = np.where(f["was_home"], lg["away"], lg["home"])
        f["exp_gf"] = lg_for * (f["att_s"] / lg["all"]) * (f["opp_def_s"] / lg["all"])
        f["exp_ga"] = lg_against * (f["opp_att_s"] / lg["all"]) * (f["def_s"] / lg["all"])

        parts = [f]
        for prefix, st in self.player_state.items():
            sh = st.groupby(self.codes).shift(h).add_prefix(f"{prefix}_")
            parts.append(sh.reindex(f.index))
        f = pd.concat(parts, axis=1)
        f["n"] = self.count_n.groupby(self.codes).shift(h).fillna(0).reindex(f.index)
        f["n_dc"] = self.count_dc.groupby(self.codes).shift(h).fillna(0).reindex(f.index)
        # ownership as known when forecasting: at h=1 the match's own deadline value; further ahead
        # we only know the value h-1 matches earlier (for upcoming rows: today's ownership)
        f["sel_rank"] = self.sel_own.groupby(self.codes).shift(h - 1).reindex(f.index)
        f["h"] = h
        return f
