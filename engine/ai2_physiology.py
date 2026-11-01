import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold

SEED = 0
N_FOLD = 5
CARRY_HOURS = 12
SEEN_HOURS = 6
VITALS = ["spo2", "fio2", "peep", "rr_set", "rr_total"]


def features(hourly: pd.DataFrame, stay: str) -> pd.DataFrame:
    # Synthetic sheets carry no heart rate, so the model reads only breathing values and ventilator settings.
    g = hourly.groupby(stay, sort=False)
    out = pd.DataFrame(index=hourly.index)
    for v in VITALS:
        out[v] = g[v].ffill(limit=CARRY_HOURS)
        out[f"{v}_tercatat_{SEEN_HOURS}j"] = g[v].transform(lambda s: s.notna().astype(float).rolling(SEEN_HOURS, min_periods=1).max())
    out["rr_spontan"] = out.rr_total - out.rr_set
    out["sf_rasio"] = out.spo2 / out.fio2.where(out.fio2 > 0)
    return out.astype(np.float32)


def new_model() -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=31, l2_regularization=1.0,
                                          early_stopping=False, random_state=SEED)


def calibration_bins(y: np.ndarray, p: np.ndarray, bins: int = 10) -> list[dict]:
    edges = np.quantile(p, np.linspace(0, 1, bins + 1))
    which = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, bins - 1)
    return [{"p_rata": round(float(p[which == b].mean()), 4), "teramati": round(float(y[which == b].mean()), 4), "n": int((which == b).sum())}
            for b in range(bins) if (which == b).any()]


def labelled_eicu(eicu: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    e = eicu.sort_values(["rawatan_id", "jam"]).reset_index(drop=True)
    X = features(e, "rawatan_id")
    known = e.alat.notna().to_numpy()
    return X[known], (e.alat[known] == "ventilator_invasif").to_numpy().astype(int), e.rs_id[known].to_numpy()


def train(eicu: pd.DataFrame, mimic: pd.DataFrame) -> tuple[CalibratedClassifierCV, dict]:
    X, y, rs = labelled_eicu(eicu)
    folds = list(GroupKFold(n_splits=N_FOLD, shuffle=True, random_state=SEED).split(X, y, rs))
    oof = np.zeros(len(y))
    for tr, te in folds:
        oof[te] = new_model().fit(X.iloc[tr], y[tr]).predict_proba(X.iloc[te])[:, 1]
    model = CalibratedClassifierCV(new_model(), method="isotonic", cv=folds).fit(X, y)
    m = mimic.sort_values(["rawatan_id", "jam"]).reset_index(drop=True)
    pm = model.predict_proba(features(m, "rawatan_id"))[:, 1]
    ym = m.ventilasi_invasif.to_numpy().astype(int)
    stays = m.assign(p=pm, y=ym).groupby("rawatan_id").agg(jam_benar=("y", "sum"), jam_perkiraan=("p", lambda p: int((p >= 0.5).sum())))
    vent = stays[stays.jam_benar > 0]
    report = {
        "eicu": {"jam_berlabel": int(len(y)), "rs": int(len(np.unique(rs))), "porsi_jam_berventilasi": round(float(y.mean()), 3),
                 "auc_rs_disisihkan": round(float(roc_auc_score(y, oof)), 3), "kalibrasi_rs_disisihkan": calibration_bins(y, oof)},
        "mimic_validasi_luar": {"jam": int(len(ym)), "rawatan": int(m.rawatan_id.nunique()), "auc": round(float(roc_auc_score(ym, pm)), 3),
                                "kalibrasi": calibration_bins(ym, pm),
                                "galat_jam_median_rawatan_berventilasi": round(float((vent.jam_perkiraan - vent.jam_benar).abs().median()), 1),
                                "rawatan_berventilasi": int(len(vent))},
    }
    return model, report


def hourly_ventilation(model: CalibratedClassifierCV, vitals: pd.DataFrame) -> pd.DataFrame:
    v = vitals.sort_values(["nomor_sep", "waktu"]).reset_index(drop=True)
    v["p_ventilasi"] = model.predict_proba(features(v, "nomor_sep"))[:, 1]
    return v[["nomor_sep", "waktu", "p_ventilasi"]]



def ventilated_hours(hourly: pd.DataFrame) -> pd.Series:
    return hourly.groupby("nomor_sep").p_ventilasi.agg(lambda p: float((p >= 0.5).sum()))
