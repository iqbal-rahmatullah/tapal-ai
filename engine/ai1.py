import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from engine import MODEL_VERSION
from engine import stats as S
from engine.contracts import (CARDIAC_GROUPS_NOT_MOVING, LINE_GROUPS, MAJOR_SURGERY_CODES, MAJOR_SURGERY_GROUPS,
                              NEONATAL_PREFIX, TARGET_DIAGNOSIS_CODES, TRIGGER_CODES, TarifRs, split_codes)
from engine.synth import grouper as G

N_FOLD, GARIS, JENDELA = 5, 96, (72, 120)  # TARGETS v2 bagian 5
SEED = 0
COSTS = [f"tarif_rs_{k}" for k in TarifRs.model_fields]
# Fitur terlarang AI 1 (TARGETS v2 bagian 6); features are built only from ALLOWED.
FORBIDDEN = frozenset({"ventilator_hour", "ventilator_use_ind", "ventilator_start_dttm", "ventilator_stop_dttm", "cbg",
                       "tarif_ina_cbg", "kode_rs", "nomor_sep", "bulan"})
ALLOWED = ["umur", "jenis_kelamin", "kelas_rawat", "cara_masuk", "tgl_masuk", "tgl_pulang", "diagnosa", "icu_los",
           "discharge_status", *COSTS]
HOSPITAL = ["kelas_rs", "kepemilikan", "regional"]
CATEGORICAL = ["jenis_kelamin", "cara_masuk", "discharge_status", "kelas_rs", "kepemilikan", "regional", "dx_primer"]
MODELS_DIR = Path(__file__).resolve().parents[1] / "models"


def evidence(claims: pd.DataFrame, hospitals: pd.DataFrame) -> pd.DataFrame:
    ev = claims[ALLOWED].join(hospitals.set_index("kode_rs")[HOSPITAL], on=claims.kode_rs)
    ev["prosedur_bukti"] = claims.procedure.map(lambda s: sorted(set(split_codes(s)) - TRIGGER_CODES))
    ev["dx"] = claims.diagnosa.map(split_codes)
    return ev.drop(columns="diagnosa")


@dataclass
class Vocab:
    procedures: list
    secondary: list
    categories: dict
    with_costs: bool = True
    # Off in the main AI 1 (user decision, 31 Okt 2026): discharge status is an outcome, not evidence of ventilation, and easy to game.
    with_status: bool = False


def fit_vocab(ev: pd.DataFrame, with_costs: bool = True, min_count: int = 30, with_status: bool = False) -> Vocab:
    px = ev.prosedur_bukti.explode().value_counts()
    dx2 = ev.dx.map(lambda d: [c[:3] for c in d[1:]]).explode().value_counts()
    # HistGradientBoosting takes at most 255 categories per feature, one of them kept for missing values.
    cats = {c: sorted(_categorical(ev, c).value_counts().index[:254].tolist()) for c in CATEGORICAL}
    return Vocab(sorted(px[px >= min_count].index), sorted(dx2[dx2 >= min_count].index), cats, with_costs, with_status)


def _categorical(ev: pd.DataFrame, col: str) -> pd.Series:
    if col == "dx_primer":
        return ev.dx.map(lambda d: d[0][:3])
    return ev[col].astype(str)


def _multi_hot(sets: pd.Series, vocab: list, prefix: str) -> pd.DataFrame:
    e = sets.explode()
    e = e[e.isin(vocab)]
    m = pd.crosstab(e.index, e).reindex(index=sets.index, columns=vocab, fill_value=0).clip(upper=1)
    m.columns = [f"{prefix}{c}" for c in vocab]
    return m.astype(np.int8)


def features(ev: pd.DataFrame, vocab: Vocab) -> pd.DataFrame:
    days = (pd.to_datetime(ev.tgl_pulang).dt.normalize() - pd.to_datetime(ev.tgl_masuk).dt.normalize()).dt.days
    secondary = ev.dx.map(lambda d: sorted({c[:3] for c in d[1:]}))
    parts = [pd.DataFrame({
        "umur": ev.umur.astype(float), "kelas_rawat": ev.kelas_rawat.astype(float), "lama_rawat": days.astype(float),
        "icu_los": ev.icu_los.astype(float), "n_dx_sekunder": secondary.map(len).astype(float),
        "n_prosedur": ev.prosedur_bukti.map(len).astype(float),
    }, index=ev.index)]
    parts.append(_multi_hot(ev.prosedur_bukti, vocab.procedures, "px_"))
    parts.append(_multi_hot(secondary, vocab.secondary, "dx2_"))
    cats = pd.DataFrame({c: pd.Categorical(_categorical(ev, c), categories=vocab.categories[c]) for c in CATEGORICAL
                         if c != "discharge_status" or vocab.with_status}, index=ev.index)
    parts.append(cats)
    if not vocab.with_costs:
        return pd.concat(parts, axis=1)
    return _with_derived(pd.concat([*parts, ev[COSTS].astype(float)], axis=1))


def _with_derived(X: pd.DataFrame) -> pd.DataFrame:
    return X.assign(biaya_total=X[COSTS].sum(axis=1), intensif_per_hari=X.tarif_rs_rawat_intensif / X.icu_los.clip(lower=1),
                    obat_per_hari=X.tarif_rs_obat / X.lama_rawat.clip(lower=1))


def codes(claims: pd.DataFrame) -> pd.Series:
    return claims.procedure.map(lambda s: set(split_codes(s)))


def has_trigger(claims: pd.DataFrame) -> np.ndarray:
    return codes(claims).map(lambda c: bool(c & TRIGGER_CODES)).to_numpy()


def in_line(claims: pd.DataFrame) -> np.ndarray:
    # Ventilation-line population (TARGETS v2 bagian 6).
    return ((claims.cbg.str[:6].isin(LINE_GROUPS).to_numpy() | has_trigger(claims))
            & ~claims.cbg.str.startswith(NEONATAL_PREFIX).to_numpy())


def eligible_fictitious(claims: pd.DataFrame) -> np.ndarray:
    group = claims.cbg.str[:6]
    surgery = codes(claims).map(lambda c: bool(c & set(MAJOR_SURGERY_CODES))).to_numpy()
    return ((claims.icu_indikator == 1) & claims.diagnosa.str[:3].isin(TARGET_DIAGNOSIS_CODES)
            & ~group.isin(MAJOR_SURGERY_GROUPS) & ~claims.cbg.str.startswith(NEONATAL_PREFIX)).to_numpy() & ~surgery


def eligible_prolonged(claims: pd.DataFrame) -> np.ndarray:
    vent = codes(claims).map(lambda c: bool(c & {"96.71", "96.72"})).to_numpy()
    return vent & ~claims.cbg.str[:6].isin(CARDIAC_GROUPS_NOT_MOVING).to_numpy() & ~claims.cbg.str.startswith(NEONATAL_PREFIX).to_numpy()


def prolonged_window(claims: pd.DataFrame) -> np.ndarray:
    hours = claims.ventilator_hour.to_numpy()
    return eligible_prolonged(claims) & (hours >= JENDELA[0]) & (hours < JENDELA[1])


def new_model(seed: int = SEED) -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=31, l2_regularization=1.0,
                                          early_stopping=False, categorical_features="from_dtype", random_state=seed)


def cross_fit(X: pd.DataFrame, y: np.ndarray, groups: np.ndarray, fit_mask: np.ndarray, predict_mask: np.ndarray,
              seed: int = SEED) -> np.ndarray:
    # Every hospital is scored by a model trained without any of its own claims.
    p = np.full(len(X), np.nan)
    for tr, te in GroupKFold(n_splits=N_FOLD, shuffle=True, random_state=seed).split(X, y, groups):
        tr, te = tr[fit_mask[tr]], te[predict_mask[te]]
        if len(te):
            p[te] = new_model(seed).fit(X.iloc[tr], y[tr]).predict_proba(X.iloc[te])[:, 1]
    return p


def cross_fit_simple(X: pd.DataFrame, y: np.ndarray, groups: np.ndarray, fit_mask: np.ndarray, predict_mask: np.ndarray,
                     seed: int = SEED) -> np.ndarray:
    # Comparator of TARGETS v2 bagian 8: logistic regression on age, length of stay, primary diagnosis, and discharge status when X has it.
    cats = ["dx_primer"] + (["discharge_status"] if "discharge_status" in X.columns else [])
    d = pd.DataFrame({"umur": X.umur.fillna(X.umur.median()), "lama_rawat": X.lama_rawat.fillna(0), **{c: X[c].astype(str) for c in cats}})
    model = make_pipeline(ColumnTransformer([("num", StandardScaler(), ["umur", "lama_rawat"]),
                                             ("cat", OneHotEncoder(handle_unknown="ignore"), cats)]),
                          LogisticRegression(max_iter=2000))
    p = np.full(len(X), np.nan)
    for tr, te in GroupKFold(n_splits=N_FOLD, shuffle=True, random_state=seed).split(d, y, groups):
        tr, te = tr[fit_mask[tr]], te[predict_mask[te]]
        if len(te):
            p[te] = model.fit(d.iloc[tr], y[tr]).predict_proba(d.iloc[te])[:, 1]
    return p


def calibrate(p: np.ndarray, y: np.ndarray, groups: np.ndarray, fit_mask: np.ndarray, seed: int = SEED) -> np.ndarray:
    # Boosting is overconfident near 0 and 1, which flagged 17 RS in DEV's fraud-free twin; maps fitted on other RS fix it.
    out = p.copy()
    ok = ~np.isnan(p)
    for tr, te in GroupKFold(n_splits=N_FOLD, shuffle=True, random_state=seed + 1).split(p, y, groups):
        tr, te = tr[ok[tr] & fit_mask[tr]], te[ok[te]]
        out[te] = IsotonicRegression(y_min=1e-4, y_max=1 - 1e-4, out_of_bounds="clip").fit(p[tr], y[tr]).predict(p[te])
    return out


def final_model(X: pd.DataFrame, y: np.ndarray, groups: np.ndarray, seed: int = SEED) -> CalibratedClassifierCV:
    folds = list(GroupKFold(n_splits=N_FOLD, shuffle=True, random_state=seed).split(X, y, groups))
    return CalibratedClassifierCV(new_model(seed), method="isotonic", cv=folds).fit(X, y)


@dataclass
class ModeRun:
    p: np.ndarray
    p_raw: np.ndarray
    table: pd.DataFrame
    table_round1: pd.DataFrame


def run_mode(X: pd.DataFrame, y: np.ndarray, rs: pd.Series, model_pop: np.ndarray, test_pop: np.ndarray,
             n_layak: pd.Series, seed: int = SEED, fit: Callable = cross_fit) -> ModeRun:
    groups = rs.to_numpy()
    p1 = fit(X, y, groups, model_pop, model_pop | test_pop, seed)
    t1 = S.per_rs_test(rs, y, calibrate(p1, y, groups, model_pop, seed), test_pop, n_layak)
    # Second fit without the hospitals flagged in round one, so their claims stop shaping the expectation.
    clean = ~rs.isin(t1.index[t1.ditandai]).to_numpy()
    p2 = fit(X, y, groups, model_pop & clean, model_pop | test_pop, seed)
    q2 = calibrate(p2, y, groups, model_pop & clean, seed)
    t2 = S.per_rs_test(rs, y, q2, test_pop, n_layak)
    t2["ditandai_putaran1"] = t1.ditandai
    return ModeRun(q2, p2, t2, t1)


def tariff_deltas(claims: pd.DataFrame, hospitals: pd.DataFrame, mode: str, rows: np.ndarray,
                  cfg: G.GrouperConfig = G.DEFAULT) -> np.ndarray:
    # The synthetic grouper stands in for the official one.
    hosp = hospitals.set_index("kode_rs")
    out = np.zeros(len(claims))
    line = cfg.long_vent_min_hours or GARIS
    for i in np.flatnonzero(rows):
        r = claims.iloc[i]
        c = set(split_codes(r.procedure))
        dx = split_codes(r.diagnosa)
        if mode == "fiktif":
            c, hours = c - TRIGGER_CODES, 0
        else:
            c, hours = ((c - {"96.72"}) | {"96.71"}) if "96.72" in c else c, min(int(r.ventilator_hour), line - 1)
        h = hosp.loc[r.kode_rs]
        g = G.group(dx[0][:3], c, [d[:3] for d in dx[1:]], hours, cfg)
        out[i] = r.tarif_ina_cbg - G.tariff(h.regional, h.kelas_rs, h.kepemilikan, g, int(r.kelas_rawat))
    return np.maximum(out, 0)


REASON_FEATURES = ["icu_los", "lama_rawat", "discharge_status", "n_prosedur", "n_dx_sekunder", "dx_primer", "umur"]
DISCHARGE = {"1": "pulang atas persetujuan dokter", "2": "dirujuk", "3": "pulang atas permintaan sendiri", "4": "meninggal",
             "5": "lain-lain"}
CODE_NAMES = {
    "99.60": "resusitasi jantung paru", "38.93": "kateter vena sentral", "96.07": "pemasangan selang lambung",
    "99.04": "transfusi sel darah merah", "57.94": "kateter urin", "89.65": "analisa gas darah", "96.6": "nutrisi enteral",
    "31.1": "trakeostomi", "31.29": "trakeostomi", "39.95": "hemodialisis", "93.90": "NIV/CPAP", "34.04": "selang dada (WSD)",
    "93.96": "terapi oksigen", "87.44": "foto toraks", "89.54": "pemantauan EKG", "96.05": "intubasi saluran napas lain",
    "J96": "gagal napas", "R57": "syok", "A41": "sepsis", "I46": "henti jantung", "N17": "gagal ginjal akut",
    "G93": "gangguan otak lain", "J80": "ARDS", "E87": "gangguan elektrolit", "D64": "anemia", "J18": "pneumonia",
}


def _rupiah(x: float) -> str:
    return "Rp" + f"{x:,.0f}".replace(",", ".")


def _describe(feature: str, value, ref) -> str:
    if feature.startswith("px_"):
        code = feature[3:]
        return f"{'Ada' if value else 'Tidak ada'} kode {code}" + (f" ({CODE_NAMES[code]})" if code in CODE_NAMES else "")
    if feature.startswith("dx2_"):
        code = feature[4:]
        return f"{'Ada' if value else 'Tidak ada'} diagnosis sekunder {code}" + (f" ({CODE_NAMES[code]})" if code in CODE_NAMES else "")
    if feature == "discharge_status":
        return f"Status pulang: {DISCHARGE.get(str(value), value)} (klaim berventilasi umumnya: {DISCHARGE.get(str(ref), ref)})"
    if feature in ("icu_los", "lama_rawat"):
        name = "Lama ICU" if feature == "icu_los" else "Lama rawat"
        return f"{name} {value:.0f} hari (klaim berventilasi umumnya {ref:.0f} hari)"
    if feature in ("n_prosedur", "n_dx_sekunder"):
        name = "kode prosedur lain" if feature == "n_prosedur" else "diagnosis sekunder"
        return f"{value:.0f} {name} (klaim berventilasi umumnya {ref:.0f})"
    if feature == "dx_primer":
        return f"Diagnosis utama {value}"
    if feature == "umur":
        return f"Umur {value:.0f} tahun"
    label = feature.replace("tarif_rs_", "").replace("_", " ")
    return f"Tagihan {label} {_rupiah(value)} (klaim berventilasi umumnya {_rupiah(ref)})"


@dataclass
class Bundle:
    version: str
    vocab: Vocab
    models: dict
    reference: dict
    percentiles: dict
    thresholds: dict
    summary: dict = field(default_factory=dict)

    def predict(self, X: pd.DataFrame, mode: str) -> np.ndarray:
        return self.models[mode].predict_proba(X)[:, 1]

    def reasons(self, X: pd.DataFrame, mode: str, top: int = 3) -> list[list[dict]]:
        # Occlusion: each feature is swapped for its typical supported value, and the change in p gives direction and size.
        cands = [c for c in REASON_FEATURES if c in X.columns] + [c for c in X.columns if c.startswith(("px_", "dx2_", "tarif_rs_"))]
        out = []
        for i in range(len(X)):
            row = X.iloc[[i]]
            base = self.predict(row, mode)[0]
            batch = pd.concat([row] * len(cands), ignore_index=True)
            for j, c in enumerate(cands):
                batch.loc[j, c] = self.reference[c]
            if self.vocab.with_costs:
                batch = _with_derived(batch)
            delta = base - self.predict(batch, mode)
            order = np.argsort(delta)
            picked = [k for k in order[:top] if delta[k] < -0.01] + [k for k in order[::-1][:top] if delta[k] > 0.01]
            out.append([{"fitur": cands[k], "teks": _describe(cands[k], row.iloc[0][cands[k]], self.reference[cands[k]]),
                         "arah": "menaikkan" if delta[k] > 0 else "menurunkan", "besar": round(float(delta[k]), 3)}
                        for k in picked])
        return out

    def percentile(self, p: float, dx3: str) -> float:
        q = self.percentiles.get(dx3, self.percentiles["_semua"])
        return float(np.searchsorted(q, p, side="right") / len(q))

    def status(self, p_fiktif: float | None, p_panjang: float | None, ai2_bersih: bool | None) -> str:
        # Forged claim evidence passes AI 1, so the fast lane also needs AI 2's quick layers clean (user decision, 31 Okt 2026).
        if p_fiktif is None or ai2_bersih is not True:
            return "periksa_manual"
        suspicious = p_fiktif <= self.thresholds["fiktif"] or (p_panjang is not None and p_panjang <= self.thresholds["panjang"])
        return "periksa_manual" if suspicious else "lolos_cepat"


def single_feature_auc(X: pd.DataFrame, y: np.ndarray, groups: np.ndarray, seed: int = SEED) -> pd.Series:
    # Categories are target-encoded out of fold, so a category cannot score by remembering its own rows.
    folds = list(GroupKFold(n_splits=N_FOLD, shuffle=True, random_state=seed).split(X, y, groups))
    out = {}
    for col in X.columns:
        x = X[col]
        if isinstance(x.dtype, pd.CategoricalDtype):
            codes, score = x.cat.codes.to_numpy(), np.empty(len(x))
            for tr, te in folds:
                rate = pd.Series(y[tr]).groupby(codes[tr]).mean()
                score[te] = pd.Series(codes[te]).map(rate).fillna(y[tr].mean()).to_numpy()
        elif x.notna().any():
            score = x.astype(float).fillna(x.median()).to_numpy()
        else:
            continue
        auc = roc_auc_score(y, score)
        out[col] = max(auc, 1 - auc)
    return pd.Series(out).sort_values(ascending=False)


def leakage_scan(X: pd.DataFrame, y: np.ndarray, groups: np.ndarray, floor: float = 0.70) -> list[dict]:
    # TARGETS v2 bagian 8 asks for one-feature AUC on every column with threshold 0.80; counts under 10 stay hidden.
    cell = lambda n: int(n) if n >= 10 else "<10"
    rows = []
    for col, auc in single_feature_auc(X, y, groups).items():
        if auc < floor:
            break
        row = {"fitur": col, "auc": round(float(auc), 3), "di_atas_0_80": bool(auc > 0.80)}
        if col.startswith(("px_", "dx2_")):
            has = X[col].to_numpy() == 1
            row |= {"ada_pada_klaim_berlabel": cell((has & (y == 1)).sum()), "ada_pada_klaim_tanpa_label": cell((has & (y == 0)).sum())}
        rows.append(row)
    return rows


def reference_values(X: pd.DataFrame, supported: np.ndarray) -> dict:
    ref = {}
    for c in X.columns:
        col = X.loc[supported, c]
        if isinstance(col.dtype, pd.CategoricalDtype):
            ref[c] = col.mode().iloc[0]
        elif c.startswith(("px_", "dx2_")):
            ref[c] = int(col.mean() >= 0.5)
        else:
            ref[c] = float(col.median())
    return ref


def save_bundle(bundle: Bundle, path: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    meta = {"versi_model": bundle.version, "sha256": digest, "berkas": path.name,
            "dibuat": datetime.now(timezone.utc).isoformat(timespec="seconds"), "ambang": bundle.thresholds,
            "fitur": int(bundle.models["fiktif"].n_features_in_), "ringkasan": bundle.summary}
    path.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=1, default=str))
    return meta


def load_bundle(path: Path = MODELS_DIR / f"ai1-{MODEL_VERSION}.joblib") -> Bundle:
    meta = json.loads(path.with_suffix(".json").read_text())
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != meta["sha256"]:
        raise ValueError(f"model file {path.name} does not match its recorded fingerprint")
    bundle = joblib.load(path)
    if bundle.version != MODEL_VERSION:
        raise ValueError(f"model version {bundle.version} differs from engine version {MODEL_VERSION}")
    return bundle
