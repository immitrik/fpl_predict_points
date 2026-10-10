"""Baseline expected-points model.

Predicts each scoring *event* (minutes, goals, assists, clean sheet, ...) from shrunk
recent per-90 rates adjusted for the fixture, then converts events to points using the
official scoring rules. Event-level prediction keeps it valid across rule changes.
"""
import numpy as np
import pandas as pd

from .scoring import expected_floor, GC_PER_POINT, SAVES_PER_POINT

PRIOR_MATCHES = 4        # weight of the position-average prior, in 90-minute matches
MAX_N = 15               # cap on how many past matches count as evidence
NEW_PLAYER = {"minutes": 20.0, "played": 0.3, "p60": 0.15}

# (stat, ewm columns blended, fixture factor, scoring key)
RATE_STATS = ["goals", "assists", "bonus", "saves", "yellow_cards", "red_cards",
              "own_goals", "penalties_saved", "penalties_missed"]


def position_priors(f: pd.DataFrame) -> pd.DataFrame:
    """Per-90 event rates and defensive-contribution frequency by position (from played rows)."""
    p = f[f["minutes"].notna()].copy()
    p["goals"] = 0.5 * p["goals_scored"] + 0.5 * p["expected_goals"]
    p["assists_b"] = 0.5 * p["assists"] + 0.5 * p["expected_assists"]
    g = p.groupby("position")
    mins = g["minutes"].sum()
    out = pd.DataFrame({
        "goals": g["goals"].sum() / mins * 90,
        "assists": g["assists_b"].sum() / mins * 90,
        **{c: g[c].sum() / mins * 90 for c in RATE_STATS[2:]},
    })
    out["dc"] = p[p["dc_ind"].notna()].groupby("position")["dc_ind"].mean()
    return out


def _blend(f: pd.DataFrame, stat: str) -> pd.Series:
    if stat == "goals":
        return 0.5 * f["ew_goals_scored"] + 0.5 * f["ew_expected_goals"]
    if stat == "assists":
        return 0.5 * f["ew_assists"] + 0.5 * f["ew_expected_assists"]
    return f[f"ew_{stat}"]


def expected_events(f: pd.DataFrame, priors: pd.DataFrame,
                    avail: pd.Series | None = None) -> pd.DataFrame:
    """Expected event counts from shrunk EWM rates (see features.FeatureBuilder)."""
    out = f.copy()
    pos = out["position"]
    avail = np.ones(len(out)) if avail is None else avail.to_numpy()
    fresh = out["n"] == 0
    n = np.minimum(out["n"], MAX_N)

    m_ew = out["ew_minutes"].fillna(NEW_PLAYER["minutes"]).where(~fresh, NEW_PLAYER["minutes"])
    p_play = out["ew_played"].fillna(NEW_PLAYER["played"]).where(~fresh, NEW_PLAYER["played"])
    p60 = out["ew_p60"].fillna(NEW_PLAYER["p60"]).where(~fresh, NEW_PLAYER["p60"])
    out["avail"], out["p_play"], out["p60"] = avail, p_play, p60
    out["m_play"] = (m_ew / p_play.clip(lower=0.05)).clip(1, 90)
    out["xmin"] = m_ew * avail
    scale = out["xmin"] / 90

    f_att = (out["exp_gf"] / out["att_s"]).clip(0.5, 2)
    f_def = (out["exp_ga"] / out["def_s"]).clip(0.5, 2)
    factor = {"goals": f_att, "assists": f_att, "bonus": f_att ** 0.5, "saves": f_def}

    for stat in RATE_STATS:
        prior = pos.map(priors[stat])
        s_ew = _blend(out, stat).fillna(0.0)
        rate90 = 90 * (n * s_ew + PRIOR_MATCHES * prior) / (n * m_ew + PRIOR_MATCHES * 90)
        out[f"x_{stat}"] = rate90 * scale * factor.get(stat, 1.0)
    out.loc[pos != "GKP", "x_saves"] = 0.0

    out["p_cs_team"] = np.exp(-out["exp_ga"])  # Poisson: P(no goals conceded)
    n_dc = np.minimum(out["n_dc"], MAX_N)
    p_dc = (n_dc * out["ew_dc_ind"].fillna(0.0) + PRIOR_MATCHES * pos.map(priors["dc"])) / (n_dc + PRIOR_MATCHES)
    out["x_dc"] = p_dc * avail
    return out


def events_to_points(out: pd.DataFrame, sc: dict) -> pd.DataFrame:
    """Convert expected events to expected points with the official scoring rules."""
    out = out.copy()
    pos, avail, p_play = out["position"], out["avail"], out["p_play"]
    out["x_cs"] = out["p_cs_team"] * out["p60"] * avail
    # goals conceded while on the pitch: Poisson with rate implied by P(clean sheet)
    gc_mu = -np.log(out["p_cs_team"].clip(1e-6, 1)) * out["m_play"] / 90
    out["x_gc_pts_units"] = p_play * avail * expected_floor(gc_mu.to_numpy(), GC_PER_POINT)
    sv_mu = (out["x_saves"] / (p_play * avail).clip(lower=0.05)).to_numpy()
    out["x_save_units"] = p_play * avail * expected_floor(sv_mu, SAVES_PER_POINT)

    def by_pos(key: str) -> pd.Series:
        return pos.map(sc[key]).astype(float)

    out["xpts"] = (
        avail * (p_play * sc["short_play"] + out["p60"] * (sc["long_play"] - sc["short_play"]))
        + out["x_goals"] * by_pos("goals_scored")
        + out["x_assists"] * sc["assists"]
        + out["x_cs"] * by_pos("clean_sheets")
        + out["x_gc_pts_units"] * by_pos("goals_conceded")
        + out["x_save_units"] * sc["saves"]
        + out["x_penalties_saved"] * sc["penalties_saved"]
        + out["x_penalties_missed"] * sc["penalties_missed"]
        + out["x_yellow_cards"] * sc["yellow_cards"]
        + out["x_red_cards"] * sc["red_cards"]
        + out["x_own_goals"] * sc["own_goals"]
        + out["x_bonus"] * sc["bonus"]
        + out["x_dc"] * by_pos("defensive_contribution")
    )
    out["xpts_naive"] = out["ew_total_points"].fillna(0.0) * avail
    return out


def expected_points(f: pd.DataFrame, sc: dict, priors: pd.DataFrame,
                    avail: pd.Series | None = None) -> pd.DataFrame:
    return events_to_points(expected_events(f, priors, avail), sc)
