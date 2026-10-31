import numpy as np
import pandas as pd
from scipy import stats

from engine.contracts import VENTILATION_CODES, split_codes

# TARGETS v2 bagian 5.
BH_Q = 0.05
MIN_KLAIM = 30
TOP_K = 50
B_BOOT = 1000
AUDIT_K = 60 * 12  # KAPASITAS_AUDIT over 12 months


def robust_flags(value: pd.Series, n_layak: pd.Series) -> pd.DataFrame:
    layak = n_layak.reindex(value.index).fillna(0) >= MIN_KLAIM
    med = value[layak].median()
    mad = 1.4826 * np.median(np.abs(value[layak] - med))
    z = (value - med) / (mad if mad > 0 else 1.0)
    p = pd.Series(np.nan, index=value.index)
    p[layak] = stats.norm.sf(z[layak])
    p_bh = pd.Series(np.nan, index=value.index)
    if layak.any():
        p_bh[layak] = stats.false_discovery_control(p[layak].to_numpy(), method="bh")
    return pd.DataFrame({"z_robust": z, "p_satu_sisi": p, "p_bh": p_bh, "ditandai": layak & (p_bh <= BH_Q)})


def exact_z(pmfs, observed: int) -> float:
    # One-sided mid-p of the exact sum (user decision, 31 Okt 2026): the normal approximation flagged honest RS for two surprise claims.
    dist = np.ones(1)
    for pmf in pmfs:
        dist = np.convolve(dist, pmf)
    mid = dist[observed + 1:].sum() + 0.5 * dist[observed]
    return float(stats.norm.isf(np.clip(mid, 1e-300, 1 - 1e-16)))


def per_rs_test(rs: pd.Series, y: np.ndarray, p: np.ndarray, population: np.ndarray, n_layak: pd.Series) -> pd.DataFrame:
    d = pd.DataFrame({"rs": rs.to_numpy(), "y": y, "p": p})[population]
    rows = {k: (len(g), int(g.y.sum()), float(g.p.sum()), exact_z(((1 - x, x) for x in g.p), int(g.y.sum())))
            for k, g in d.groupby("rs")}
    t = pd.DataFrame.from_dict(rows, orient="index", columns=["n_uji", "O", "E", "z"]).reindex(n_layak.index, fill_value=0)
    t["n_layak"] = n_layak
    return t.join(robust_flags(t.z, n_layak))


def counterfactual_rupiah(d: pd.DataFrame, rng: np.random.Generator, reps: int = B_BOOT) -> pd.DataFrame:
    # Excess claims (O - E) times the mean delta of the least-supported coded claims, weighted 1 - p as in v1.
    def estimate(y, p, delta):
        w = (1 - p) * y
        mean_delta = np.average(delta, weights=w) if w.sum() > 0 else 0.0
        return max(y.sum() - p.sum(), 0.0) * mean_delta

    y, p, delta = d.y.to_numpy(), d.p.to_numpy(), d.delta.to_numpy()
    point = estimate(y, p, delta)
    idx = rng.integers(0, len(d), (reps, len(d)))
    boot = np.array([estimate(y[i], p[i], delta[i]) for i in idx])
    return pd.Series({"rupiah": point, "rupiah_bawah": np.percentile(boot, 2.5), "rupiah_atas": np.percentile(boot, 97.5)})


def point_score_rules(claims: pd.DataFrame) -> pd.DataFrame:
    # Rules, not AI 1, so they may read the columns AI 1 is forbidden (TARGETS v2 bagian 6).
    procs = claims.procedure.map(lambda s: set(split_codes(s)))
    vent = procs.map(lambda p: bool(p & VENTILATION_CODES)).to_numpy()
    hours = claims.ventilator_hour.to_numpy()
    return pd.DataFrame({
        "tanpa_intubasi": vent & ~procs.map(lambda p: "96.04" in p).to_numpy(),
        "sewa_alat_nol": vent & (claims.tarif_rs_sewa_alat.to_numpy() == 0),
        "jam_96_100": (hours >= 96) & (hours <= 100),
        "icu_lebih_pendek": vent & (claims.icu_los.to_numpy() * 24 < hours),
        "intubasi_saja_j120": (claims.cbg.str[:6] == "J-1-20").to_numpy() & ~vent,
    }, index=claims.index)


def precision_at_k(score: np.ndarray, positive: np.ndarray, k: int) -> float:
    # Expected precision over every random tie-break at the cut (user decision, 31 Okt 2026), for stable numbers on coarse scores.
    k = min(k, len(score))
    cut = np.sort(score)[::-1][k - 1]
    above, tie = score > cut, score == cut
    return float((positive[above].sum() + (k - above.sum()) * positive[tie].mean()) / k)


def paired_precision_test(score_a: np.ndarray, score_b: np.ndarray, positive: np.ndarray, rs: np.ndarray, k: int,
                          rng: np.random.Generator, reps: int = B_BOOT) -> dict:
    hospitals = np.unique(rs)
    rows = {h: np.flatnonzero(rs == h) for h in hospitals}
    diffs = []
    for _ in range(reps):
        pick = np.concatenate([rows[h] for h in rng.choice(hospitals, len(hospitals))])
        diffs.append(precision_at_k(score_a[pick], positive[pick], k) - precision_at_k(score_b[pick], positive[pick], k))
    diffs = np.array(diffs)
    return {"selisih": float(precision_at_k(score_a, positive, k) - precision_at_k(score_b, positive, k)),
            "rentang95": [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))],
            "p_satu_sisi": float((diffs <= 0).mean())}
