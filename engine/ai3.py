from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

CAPACITY = 60
PI_MIN = 0.005
MONTHS = 12
N_REPEAT = 500
N_MODELS = 30
WEIGHT_CAP = 20.0
EXPLORE = 1.0
AI2_FLAGS = ["kata_kunci", "asersi", "klaim_vs_lembar", "teks_vs_lembar", "kloning_kuat", "tulis_serentak"]
FEATURES = ["ragu_fiktif", "ragu_panjang", "ada_panjang", *AI2_FLAGS, "log_dipertaruhkan", "rs_laju_temuan", "rs_audit"]
EXPLORE_REASON = "eksplorasi: model belum yakin"
VALUE_REASON = "nilai harapan tinggi"


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def doubt(f: pd.DataFrame) -> np.ndarray:
    return np.maximum(1 - f.p_fiktif.to_numpy(), (1 - f.p_panjang).fillna(0).to_numpy())


def static_probability(f: pd.DataFrame) -> np.ndarray:
    # Month 1 and the T16 comparator: AI 1 doubt, raised to one half when an AI 2 quick layer fires; no audit outcome is used.
    return np.where(f[AI2_FLAGS].any(axis=1).to_numpy(), np.maximum(doubt(f), 0.5), doubt(f))


def rs_history(rs: pd.Series, audited: pd.DataFrame) -> pd.DataFrame:
    # Only audits from earlier months enter, so no claim sees an outcome from its own month or later.
    g = audited.groupby("kode_rs").temuan.agg(["sum", "size"]).reindex(rs.to_numpy()).fillna(0).astype(float)
    rate = (g["sum"].to_numpy() + 0.5) / (g["size"].to_numpy() + 1.0)
    return pd.DataFrame({"rs_laju_temuan": _logit(rate), "rs_audit": np.log1p(g["size"].to_numpy())}, index=rs.index)


def design(f: pd.DataFrame, history: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({"ragu_fiktif": _logit(1 - f.p_fiktif.to_numpy()), "ragu_panjang": _logit((1 - f.p_panjang).fillna(0.5).to_numpy()),
                         "ada_panjang": f.p_panjang.notna().to_numpy(float), **{c: f[c].to_numpy(float) for c in AI2_FLAGS},
                         "log_dipertaruhkan": np.log1p(f.dipertaruhkan.to_numpy() / 1e6),
                         "rs_laju_temuan": history.rs_laju_temuan.to_numpy(), "rs_audit": history.rs_audit.to_numpy()}, index=f.index)[FEATURES]


@dataclass
class OutcomeModel:
    scaler: StandardScaler
    models: list

    @classmethod
    def fit(cls, X: pd.DataFrame, y: np.ndarray, pi: np.ndarray, rng: np.random.Generator, cap: float | None = WEIGHT_CAP) -> "OutcomeModel | None":
        if len(set(y)) < 2:
            return None
        # Exact 1/pi is kept for the total; for training it is capped so one exploration claim (1/0.005 = 200) cannot steer the model.
        w = 1 / pi if cap is None else np.minimum(1 / pi, cap)
        scaler = StandardScaler().fit(X)
        Z = scaler.transform(X)
        models = []
        for _ in range(N_MODELS):
            idx = rng.integers(0, len(y), len(y))
            if len(set(y[idx])) < 2:
                idx = np.arange(len(y))
            models.append(LogisticRegression(C=1.0, max_iter=2000).fit(Z[idx], y[idx], sample_weight=w[idx]))
        return cls(scaler, models)

    def predict(self, X: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        Z = self.scaler.transform(X)
        P = np.column_stack([m.predict_proba(Z)[:, 1] for m in self.models])
        return P.mean(axis=1), P.std(axis=1)


def inclusion(score: np.ndarray, capacity: int = CAPACITY, pi_min: float = PI_MIN) -> np.ndarray:
    # Every claim keeps the floor; the rest of the capacity follows the score, capped at 1, so the pi add up to the capacity.
    s = np.maximum(np.asarray(score, float), 0.0)
    if capacity >= len(s):
        return np.ones(len(s))
    if pi_min * len(s) >= capacity or s.sum() == 0:
        return np.full(len(s), capacity / len(s))
    lo, hi = 0.0, 1.0
    while np.minimum(1, pi_min + hi * s).sum() < capacity:
        hi *= 2
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if np.minimum(1, pi_min + mid * s).sum() < capacity else (lo, mid)
    return np.minimum(1, pi_min + hi * s)


def systematic(pi: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    # The list is shuffled first, so no pattern in its order can line up with the sampling step (user note, 1 Nov 2026).
    order = rng.permutation(len(pi))
    cum = np.cumsum(pi[order])
    points = rng.uniform() + np.arange(int(round(cum[-1])))
    return np.sort(order[np.minimum(np.searchsorted(cum, points, side="right"), len(pi) - 1)])


def reasons(value: np.ndarray, bonus: np.ndarray, pi: np.ndarray, picked: np.ndarray) -> list[str]:
    return [EXPLORE_REASON if bonus[i] > value[i] or pi[i] <= 2 * PI_MIN else VALUE_REASON for i in picked]


def estimate(predicted: np.ndarray, picked: np.ndarray, found: np.ndarray, pi: np.ndarray, spread: np.ndarray | None = None) -> dict:
    # predicted must come from the model trained before this month's outcomes, or the correction reuses its own data (user, 1 Nov 2026).
    e = found - predicted[picked]
    p = pi[picked]
    ppi = predicted.sum() + (e / p).sum()
    ht = (found / p).sum()
    out = {"ppi": float(ppi), "var_ppi": float(((1 - p) * (e / p) ** 2).sum()), "ht": float(ht), "var_ht": float(((1 - p) * (found / p) ** 2).sum())}
    if spread is not None:
        # Anticipated variance (Isaki-Fuller) from the model's spread for every claim, so a month without a rare low-pi find keeps its width.
        out["var_ppi_model"] = float(((1 - pi) / pi * spread).sum())
    return out


def official_variance(var_design: float, var_model: float) -> float:
    # Frozen 1 Nov 2026, decided after seeing T18 fail in DEV with the design variance alone: the larger of design and anticipated variance.
    return max(var_design, var_model)


def interval(total: float, var: float) -> tuple[float, float]:
    half = 1.959964 * np.sqrt(max(var, 0.0))
    return total - half, total + half
