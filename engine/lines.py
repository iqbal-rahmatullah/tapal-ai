import numpy as np
import pandas as pd

from engine import stats as S

# TARGETS v2 bagian 5 and 6.
CANDIDATES = (24, 48, 72, 96, 120, 144, 168)
COMPARATORS = (120, 144, 168)
PLACEBO = (120, 144)
WIDTH = 8


def comparators(line: int, tariff_lines: tuple[int, ...]) -> tuple[int, ...]:
    if line in PLACEBO:
        return tuple(c for c in COMPARATORS if c != line)
    return tuple(c for c in (line + 24, line + 48, line + 72) if c not in tariff_lines)


def log_ratio(hours: np.ndarray, line: int) -> float:
    above = np.count_nonzero((hours >= line) & (hours < line + WIDTH))
    below = np.count_nonzero((hours >= line - WIDTH) & (hours < line))
    return float(np.log((above + 0.5) / (below + 0.5)))


def asymmetry(hours: np.ndarray, line: int, tariff_lines: tuple[int, ...]) -> float:
    return log_ratio(hours, line) - float(np.mean([log_ratio(hours, c) for c in comparators(line, tariff_lines)]))


def _resample(rs: np.ndarray, rng: np.random.Generator, reps: int):
    hospitals = np.unique(rs)
    rows = {h: np.flatnonzero(rs == h) for h in hospitals}
    for _ in range(reps):
        yield np.concatenate([rows[h] for h in rng.choice(hospitals, len(hospitals))])


def asymmetry_table(hours: np.ndarray, rs: np.ndarray, rng: np.random.Generator, lines=CANDIDATES,
                    tariff_lines: tuple[int, ...] = (96,), reps: int = S.B_BOOT) -> pd.DataFrame:
    boot = np.array([[asymmetry(hours[pick], line, tariff_lines) for line in lines] for pick in _resample(rs, rng, reps)])
    lo, hi = np.percentile(boot, [2.5, 97.5], axis=0)
    return pd.DataFrame({"garis": lines, "S": [asymmetry(hours, line, tariff_lines) for line in lines], "bawah": lo, "atas": hi,
                         "p_satu_sisi": (boot <= 0).mean(axis=0), "garis_tarif": [line in tariff_lines for line in lines],
                         "plasebo": [line in PLACEBO for line in lines], "n_klaim": len(hours)})


def stacking_difference(hours: np.ndarray, rs: np.ndarray, flagged: set, rng: np.random.Generator, line: int = 96,
                        tariff_lines: tuple[int, ...] = (96,), reps: int = S.B_BOOT) -> dict | None:
    # T4: S(L) on flagged RS minus S(L) on the rest, each side resampled by RS.
    inside = np.isin(rs, list(flagged))
    if not inside.any() or inside.all():
        return None
    point = asymmetry(hours[inside], line, tariff_lines) - asymmetry(hours[~inside], line, tariff_lines)
    a, b = list(_resample(rs[inside], rng, reps)), list(_resample(rs[~inside], rng, reps))
    hi_, lo_ = hours[inside], hours[~inside]
    diffs = np.array([asymmetry(hi_[x], line, tariff_lines) - asymmetry(lo_[y], line, tariff_lines) for x, y in zip(a, b)])
    return {"selisih": round(point, 3), "rentang95": [round(float(v), 3) for v in np.percentile(diffs, [2.5, 97.5])],
            "rs_ditandai": int(len(set(rs[inside])))}
