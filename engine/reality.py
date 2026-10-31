# Data Sampel never leaves this laptop: only aggregates are written and the model is not saved (pakta integritas).
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from engine import ai1 as A
from engine import stats as S
from engine.contracts import MAJOR_SURGERY_GROUPS, TARGET_DIAGNOSES_BROAD, TARGET_DIAGNOSIS_CODES, TRIGGER_CODES
from engine.synth.calibration import dotted

BASE = Path.home() / "Downloads/2025"
REGULER = BASE / "Data Sampel Reguler Edisi 2025" / "data"
DM = BASE / "Data Sampel Kontekstual DM Edisi 2025" / "data"
OUT = Path(__file__).resolve().parents[2] / "tapal-percobaan" / "ai1-kenyataan"
REPS = 300
# Clinical sanity check of the data-driven list (user decision, 31 Okt 2026): catheters and a lab test are not operations.
NON_OPERATIVE = frozenset({"38.91", "38.95", "90.06"})


def load(data_dir: Path) -> pd.DataFrame:
    cols = ["FKL02", "FKL03", "FKL04", "FKL06", "FKL07", "FKL09", "FKL10", "FKL13", "FKL14", "FKL17A", "FKL19", "FKL30",
            "FKL31", "PSTV01"]
    f = pd.read_stata(next(data_dir.glob("*fkrtl.dta")), columns=cols)
    ri = f[f.FKL10 == "RITL"].copy()
    peserta = pd.read_stata(next(data_dir.glob("*kepesertaan.dta")), columns=["PSTV01", "PSTV03", "PSTV05"]).drop_duplicates("PSTV01")
    ri = ri.merge(peserta, on="PSTV01", how="left").reset_index(drop=True)
    dx2 = pd.read_stata(next(data_dir.glob("*diagnosissekunder.dta")), columns=["FKL02", "FKL24A"])
    secondary = dx2.groupby("FKL02").FKL24A.agg(lambda s: [str(x) for x in s])
    ri["codes"] = ri.FKL30.fillna("").astype(str).str.split(";").map(
        lambda xs: frozenset(dotted(x.split(" - ")[0]) for x in xs if x.strip()))
    ri["dx"] = [[str(p)] + secondary.get(k, []) for p, k in zip(ri.FKL17A, ri.FKL02)]
    ri["umur_hari"] = (ri.FKL03 - ri.PSTV03).dt.days
    ri["grup"] = ri.FKL19.astype(str).str[:6]
    return ri


def evidence(ri: pd.DataFrame) -> pd.DataFrame:
    # Data Sampel has no ICU days, admission route, or bill items.
    return pd.DataFrame({
        "umur": ri.umur_hari / 365.25, "jenis_kelamin": ri.PSTV05.astype(str).str.upper().str[0],
        "kelas_rawat": pd.to_numeric(ri.FKL13.astype(str).str[-1], errors="coerce"), "cara_masuk": "tidak_ada",
        "tgl_masuk": ri.FKL03, "tgl_pulang": ri.FKL04, "icu_los": np.nan, "discharge_status": ri.FKL14.astype(str),
        "kelas_rs": ri.FKL09.astype(str), "kepemilikan": ri.FKL07.astype(str), "regional": ri.FKL31.astype(str),
        "prosedur_bukti": ri.codes.map(lambda c: sorted(c - TRIGGER_CODES)), "dx": ri.dx,
    })


def surgery_codes(ri: pd.DataFrame) -> list[str]:
    # T22 "tanpa kode operasi besar"; 96.72 claims are left out because only 96.72 moves a surgical claim to J-1-02.
    base = ri[~ri.codes.map(lambda c: "96.72" in c)]
    e = base.assign(code=base.codes.map(lambda c: sorted(c - TRIGGER_CODES))).explode("code").dropna(subset=["code"])
    g = e.groupby("code").grup.agg(n="size", share=lambda s: s.isin(MAJOR_SURGERY_GROUPS).mean())
    return sorted(set(g[(g.n >= 10) & (g.share >= 0.5)].index) - NON_OPERATIVE)


def population(ri: pd.DataFrame, dx_codes, surgery: list[str]) -> np.ndarray:
    no_surgery = ~ri.grup.isin(MAJOR_SURGERY_GROUPS) & ~ri.codes.map(lambda c: bool(c & set(surgery)))
    return ((ri.umur_hari > 28) & ri.FKL17A.astype(str).isin(dx_codes) & no_surgery).to_numpy()


def cluster_ci(y: np.ndarray, p: np.ndarray, groups: np.ndarray, rng: np.random.Generator) -> list[float]:
    ids = np.unique(groups)
    rows = {g: np.flatnonzero(groups == g) for g in ids}
    vals = []
    for _ in range(REPS):
        pick = np.concatenate([rows[g] for g in rng.choice(ids, len(ids))])
        if 0 < y[pick].sum() < len(pick):
            vals.append(roc_auc_score(y[pick], p[pick]))
    return [round(float(np.percentile(vals, 2.5)), 3), round(float(np.percentile(vals, 97.5)), 3)]


def oof(X: pd.DataFrame, y: np.ndarray, groups: np.ndarray, pop: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    p = A.cross_fit(X, y, groups, pop, pop)
    return p, A.calibrate(p, y, groups, pop)


def summary(y: np.ndarray, p: np.ndarray, q: np.ndarray, groups: np.ndarray, rng: np.random.Generator) -> dict:
    return {"n": int(len(y)), "prevalensi": round(float(y.mean()), 4), "auc": round(float(roc_auc_score(y, p)), 3),
            "auc_rentang95_per_kabkota": cluster_ci(y, p, groups, rng), "kalibrasi_total": round(float(y.sum() / q.sum()), 3),
            "kalibrasi_total_sebelum_isotonik": round(float(y.sum() / p.sum()), 3),
            "average_precision": round(float(average_precision_score(y, p)), 3), "presisi_pada_k": precision_k(y, p)}


def precision_k(y: np.ndarray, p: np.ndarray) -> dict:
    return {f"k{k}": round(S.precision_at_k(p, y, k), 3) for k in (S.TOP_K, S.AUDIT_K)}


def simple_summary(y: np.ndarray, p: np.ndarray) -> dict:
    return {"auc": round(float(roc_auc_score(y, p)), 3), "average_precision": round(float(average_precision_score(y, p)), 3),
            "presisi_pada_k": precision_k(y, p)}


def main() -> None:
    rng = np.random.default_rng(A.SEED)
    ri = load(REGULER)
    ev = evidence(ri)
    y = ri.codes.map(lambda c: bool(c & TRIGGER_CODES)).to_numpy().astype(int)
    groups = ri.FKL06.astype(str).to_numpy()
    surgery = surgery_codes(ri)
    pop = population(ri, TARGET_DIAGNOSIS_CODES, surgery)
    vocab = A.fit_vocab(ev[pop], with_costs=False)
    X = A.features(ev, vocab)
    p, q = oof(X, y, groups, pop)
    t22 = summary(y[pop], p[pop], q[pop], groups[pop], rng)
    t22["lolos"] = bool(t22["auc"] >= 0.80 and 0.9 <= t22["kalibrasi_total"] <= 1.1)
    vocab_s = A.fit_vocab(ev[pop], with_costs=False, with_status=True)
    X_s = A.features(ev, vocab_s)
    p_s, q_s = oof(X_s, y, groups, pop)
    p_simple = A.cross_fit_simple(X_s, y, groups, pop, pop)[pop]
    p_simple_ns = A.cross_fit_simple(X, y, groups, pop, pop)[pop]
    leaks = A.leakage_scan(X[pop], y[pop], groups[pop])
    pop_a = population(ri, TARGET_DIAGNOSES_BROAD, surgery)
    vocab_a = A.fit_vocab(ev[pop_a], with_costs=False)
    p_a, q_a = oof(A.features(ev, vocab_a), y, groups, pop_a)
    pop_all = (ri.umur_hari > 28).to_numpy()
    vocab_all = A.fit_vocab(ev[pop_all], with_costs=False)
    p_all, q_all = oof(A.features(ev, vocab_all), y, groups, pop_all)

    dm = load(DM)
    ev_dm = evidence(dm)
    y_dm = dm.codes.map(lambda c: bool(c & TRIGGER_CODES)).to_numpy().astype(int)
    pop_dm = population(dm, TARGET_DIAGNOSIS_CODES, surgery)
    X_dm, g_dm = A.features(ev_dm, vocab)[pop_dm], dm.FKL06.astype(str).to_numpy()[pop_dm]
    p_dm = A.final_model(X[pop], y[pop], groups[pop]).predict_proba(X_dm)[:, 1]
    t23 = summary(y_dm[pop_dm], p_dm, p_dm, g_dm, rng)
    p_dm_s = A.final_model(X_s[pop], y[pop], groups[pop]).predict_proba(A.features(ev_dm, vocab_s)[pop_dm])[:, 1]
    t23["penurunan_auc"] = round(t22["auc"] - t23["auc"], 3)
    t23["lolos"] = bool(t23["penurunan_auc"] <= 0.05)

    out = {
        "sumber": "Data Sampel Reguler dan DM Edisi 2025, dihitung lokal; hanya agregat, model tidak disimpan",
        "definisi": {"diagnosis_sasaran": sorted(TARGET_DIAGNOSIS_CODES), "umur_minimal_hari": 29,
                     "kode_operasi_besar_dari_data": surgery, "dikeluarkan_periksa_akal_sehat": sorted(NON_OPERATIVE),
                     "validasi_silang": f"GroupKFold {A.N_FOLD} lipatan per kab/kota (FKL06)",
                     "label": "kode pemicu tercatat (96.04, 96.70-96.72)", "fitur": X.shape[1]},
        "t22": t22,
        "t22_dengan_status_pulang": summary(y[pop], p_s[pop], q_s[pop], groups[pop], rng),
        "t22_model_sederhana": simple_summary(y[pop], p_simple),
        "t22_model_sederhana_tanpa_status_pulang": simple_summary(y[pop], p_simple_ns),
        "t22_pindai_kebocoran": leaks,
        "t22_daftar_a_19_kode": summary(y[pop_a], p_a[pop_a], q_a[pop_a], groups[pop_a], rng),
        "t22_semua_rawat_inap_bukan_bayi": summary(y[pop_all], p_all[pop_all], q_all[pop_all], groups[pop_all], rng),
        "t23_dm": t23,
        "t23_dm_dengan_status_pulang": summary(y_dm[pop_dm], p_dm_s, p_dm_s, g_dm, rng),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "hasil.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
