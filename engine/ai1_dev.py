import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from joblib import Memory
from matplotlib.figure import Figure
from scipy.stats import false_discovery_control, norm
from sklearn.metrics import roc_auc_score

from engine import MODEL_VERSION
from engine import ai1 as A
from engine import stats as S
from engine.data import ROOT, canonical_dev, key_dir, load_world, out_dir, world_dir
from engine.data import label as world_label

OUT = out_dir("ai1-dev")
FAKE = ("fiktif", "rme_meragukan")
# DEV only: the key also hashes the AI 1 source and library versions, so any change to data, code, or config starts afresh.
CACHE = Memory(ROOT / ".cache" / "ai1-dev", verbose=0)
CODE = hashlib.sha256(Path(A.__file__).read_bytes() + f"{sklearn.__version__} {np.__version__} {pd.__version__}".encode()).hexdigest()


@CACHE.cache
def cached(name: str, code: str, *args):
    return getattr(A, name)(*args)


def cross_fit(*args) -> np.ndarray:
    return cached("cross_fit", CODE, *args)


def cross_fit_simple(*args) -> np.ndarray:
    return cached("cross_fit_simple", CODE, *args)


def honest_hospitals(kh: pd.DataFrame) -> pd.Series:
    return (kh.modus == "") & (kh.modus_tersembunyi == "") & (kh.garis_kedua == "")


def detect(c: pd.DataFrame, h: pd.DataFrame, with_costs: bool, fit=cross_fit, status: bool = False) -> tuple:
    ev = A.evidence(c, h)
    vocab = A.fit_vocab(ev, with_costs, with_status=status)
    X = A.features(ev, vocab)
    elig_f, win = A.eligible_fictitious(c), A.prolonged_window(c)
    n_layak_f = pd.Series(elig_f, index=c.index).groupby(c.kode_rs).sum()
    n_layak_p = pd.Series(A.eligible_prolonged(c), index=c.index).groupby(c.kode_rs).sum()
    mf = A.run_mode(X, A.has_trigger(c).astype(int), c.kode_rs, np.ones(len(c), bool), elig_f, n_layak_f, fit=fit)
    mp = A.run_mode(X, (c.ventilator_hour >= A.GARIS).to_numpy().astype(int), c.kode_rs, win, win, n_layak_p, fit=fit)
    return vocab, X, mf, mp


def calibration_bins(y: np.ndarray, p: np.ndarray) -> list[dict]:
    edges = np.array([0, 1e-3, 1e-2, 0.05, 0.2, 0.5, 0.8, 0.95, 0.99, 0.999, 1])
    idx = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, len(edges) - 2)
    return [{"p_rata": float(f"{p[idx == b].mean():.3g}"), "teramati": float(f"{y[idx == b].mean():.3g}"), "n": int((idx == b).sum())}
            for b in range(len(edges) - 1) if (idx == b).sum() >= 30]


def share(g: pd.DataFrame) -> str:
    return f"{int(g.ditandai.sum())}/{len(g)}"


def recall_table(table: pd.DataFrame, kh: pd.DataFrame, mode: str) -> dict:
    r = kh.set_index("kode_rs").join(table[["n_layak", "ditandai"]])
    perp = r[r.modus == mode]
    judged = perp[(perp.intensitas_terwujud >= 0.10) & (perp.n_layak >= S.MIN_KLAIM)]
    biasa = judged[judged.tingkat == "biasa"]
    return {"pelaku": len(perp), "dinilai": len(judged), "t1_biasa": share(biasa),
            "recall_biasa": round(float(biasa.ditandai.mean()), 3) if len(biasa) else None,
            "per_tingkat": {t: share(g) for t, g in judged.groupby("tingkat")},
            "biasa_per_kelas": {k: share(g) for k, g in biasa.groupby("kelas_rs")},
            "semua_pelaku_ditandai": int(perp.ditandai.sum())}


def false_alarms(flags: pd.Series, kh: pd.DataFrame, assessable: pd.Series) -> dict:
    h = kh[honest_hospitals(kh)].set_index("kode_rs").join(flags.rename("ditandai")).join(assessable.rename("dinilai"))
    t2 = h[h.jebakan != "sakit_tersembunyi"]
    return {"rs_jujur": len(h), "rs_jujur_dinilai": int(h.dinilai.sum()),
            "t2_ditandai": int(t2.ditandai.sum()), "t2_porsi": round(float(t2.ditandai.mean()), 3),
            "t2_porsi_di_antara_dinilai": round(float(t2[t2.dinilai].ditandai.mean()), 3) if t2.dinilai.any() else None,
            "per_jebakan": {j or "bukan jebakan": share(g) for j, g in h.groupby("jebakan")}}


def honest_shares(hit, kh: pd.DataFrame, size: pd.Series) -> dict:
    d = kh.assign(kena=kh.kode_rs.isin(hit), ukuran=kh.kode_rs.map(size),
                  dokumentasi=pd.qcut(kh.efek_kode, 3, labels=["rendah", "sedang", "tinggi"]))[honest_hospitals(kh)]
    return {col: {str(g): f"{int(x.sum())}/{len(x)}" for g, x in d.groupby(col, observed=True).kena}
            for col in ("kelas_rs", "regional", "ukuran", "dokumentasi")}


def embedded_share(k: pd.DataFrame, flagged, mode: str) -> float:
    m = k[k.modus == mode]
    return round(float(m.selisih_rupiah[m.kode_rs.isin(flagged)].sum() / m.selisih_rupiah.sum()), 3)


def rupiah_errors(c: pd.DataFrame, h: pd.DataFrame, k: pd.DataFrame, kh: pd.DataFrame, run: A.ModeRun, y: np.ndarray,
                  pop: np.ndarray, mode: str, rng: np.random.Generator) -> dict:
    flagged = run.table.index[run.table.ditandai]
    delta = A.tariff_deltas(c, h, mode, pop & y.astype(bool) & c.kode_rs.isin(flagged).to_numpy())
    d = pd.DataFrame({"rs": c.kode_rs, "y": y.astype(float), "p": run.p, "delta": delta})[pop]
    est = {rs: S.counterfactual_rupiah(g, rng) for rs, g in d[d.rs.isin(flagged)].groupby("rs")}
    truth = k[k.modus == mode].groupby("kode_rs").selisih_rupiah.sum()
    perp = set(kh.kode_rs[kh.modus == mode])
    rows = []
    for rs, e in est.items():
        true = float(truth.get(rs, 0.0))
        rows.append({"rs": rs, "pelaku": rs in perp, "perkiraan": round(e.rupiah), "bawah": round(e.rupiah_bawah),
                     "atas": round(e.rupiah_atas), "sebenarnya": round(true),
                     "galat_relatif": round(abs(e.rupiah - true) / true, 3) if true > 0 else None})
    errs = [r["galat_relatif"] for r in rows if r["pelaku"] and r["galat_relatif"] is not None]
    covered = [r["bawah"] <= r["sebenarnya"] <= r["atas"] for r in rows if r["pelaku"]]
    return {"median_galat_relatif": round(float(np.median(errs)), 3) if errs else None, "n_rs": len(errs),
            "rentang_memuat_nilai_sebenarnya": f"{sum(covered)}/{len(covered)}", "rs": rows}


def ranking_metrics(score_ai: np.ndarray, score_rule: np.ndarray, positive: np.ndarray, rupiah: np.ndarray, rs: np.ndarray,
                    modus: np.ndarray, kh: pd.DataFrame, size: pd.Series, rng: np.random.Generator, other: str = "skor_poin") -> dict:
    out = {"n_kandidat": int(len(positive)), "n_positif": int(positive.sum()), "n_rs": int(len(np.unique(rs))),
           "fraud_rate": round(float(positive.mean()), 4)}
    for name, k in (("top_k", S.TOP_K), ("kapasitas", S.AUDIT_K)):
        k = min(k, len(positive))
        ceiling = min(k, int(positive.sum())) / k
        ai, rule = S.precision_at_k(score_ai, positive, k), S.precision_at_k(score_rule, positive, k)
        top = np.zeros(len(score_ai), bool)
        top[np.lexsort((rng.random(len(score_ai)), -score_ai))[:k]] = True
        out[name] = {"k": k, "k_per_n": round(k / len(positive), 4), "presisi_maksimum": round(ceiling, 3),
                     "catatan": f"hanya {int(positive.sum())} klaim positif untuk k = {k}; perbandingan tidak bermakna"
                     if positive.sum() < k else "",
                     "presisi_ai": round(ai, 3), f"presisi_{other}": round(rule, 3),
                     "rasio": round(ai / rule, 2) if rule > 0 else None,
                     "lift_ai": round(ai / positive.mean(), 1) if positive.mean() > 0 else None,
                     "rupiah_recall_ai": round(float(rupiah[top].sum() / rupiah.sum()), 3) if rupiah.sum() > 0 else None,
                     "recall_per_modus": {m: round(float(top[modus == m].mean()), 3) for m in sorted(set(modus) - {""})},
                     "rs_jujur_diaudit_per_kelompok": honest_shares(set(rs[top]), kh, size),
                     "uji_berpasangan": S.paired_precision_test(score_ai, score_rule, positive, rs, k, rng)}
    return out


def placebo_details(run: A.ModeRun, c0: pd.DataFrame, truth: pd.Series, kh: pd.DataFrame) -> dict:
    habits = ["kelas_rs", "modus", "tingkat", "gaya_sewa", "efek_kode", "p_kode_intubasi", "porsi_bulat24", "pengali_biaya",
              "efek_ventilasi"]
    r, t = kh.set_index("kode_rs"), run.table
    assessed = t[t.n_layak >= S.MIN_KLAIM]
    weak = A.eligible_fictitious(c0) & A.has_trigger(c0) & (run.p < 0.5)
    vent_codes = A.codes(c0).map(lambda cs: bool(cs & {"96.70", "96.71", "96.72"})).to_numpy()
    rows = []
    for name, x in t[t.ditandai].iterrows():
        own = weak & (c0.kode_rs == name).to_numpy()
        rows.append({"rs": name, **{k: (round(float(r.at[name, k]), 3) if isinstance(r.at[name, k], float) else r.at[name, k]) for k in habits},
                     "n_layak": int(x.n_layak), "persentil_n_layak": round(float(assessed.n_layak.rank(pct=True).get(name, np.nan)), 2),
                     "O": int(x.O), "E": round(float(x.E), 1), "z": round(float(x.z), 2), "z_robust": round(float(x.z_robust), 2),
                     "p_bh": float(f"{x.p_bh:.3g}"), "klaim_berkode_p_di_bawah_0_5": int(own.sum()),
                     "di_antaranya_96_04_saja": int((own & ~vent_codes).sum()), "di_antaranya_benar_diventilasi": int(truth[own].sum())})
    return {"korelasi_spearman_z_robust_dan_n_layak": round(float(assessed.z_robust.corr(assessed.n_layak, method="spearman")), 2),
            "rs_ditandai": rows}


def flagged_hospitals(run: A.ModeRun, cand: np.ndarray, rs: pd.Series, X: pd.DataFrame, bundle: A.Bundle, model: str,
                      rupiah: list[dict]) -> list[dict]:
    money = {r["rs"]: r for r in rupiah}
    out = []
    for name, t in run.table[run.table.ditandai].iterrows():
        idx = np.flatnonzero(cand & (rs == name).to_numpy())
        idx = idx[np.argsort(run.p_raw[idx])][:20]
        first = [next((a["fitur"] for a in r if a["arah"] == "menurunkan"), "-") for r in bundle.reasons(X.iloc[idx], model)]
        m = money.get(name, {})
        out.append({"rs": name, "n_uji": int(t.n_uji), "O": int(t.O), "E": round(float(t.E), 1), "z_robust": round(float(t.z_robust), 2),
                    "p_bh": float(f"{t.p_bh:.3g}"), "rupiah": m.get("perkiraan"), "rupiah_rentang95": [m.get("bawah"), m.get("atas")],
                    "alasan_utama_di_20_klaim_terlemah": pd.Series(first).value_counts().head(3).to_dict()})
    return out


def rule_flags(c: pd.DataFrame, rules: pd.DataFrame, pop: np.ndarray, n_layak: pd.Series) -> pd.DataFrame:
    # Same exact test, robust z, and BH as AI 1, with the pooled rate of all RS as each rule's expectation.
    out = {}
    for col in rules.columns:
        y = rules[col].to_numpy().astype(int)
        out[col] = S.per_rs_test(c.kode_rs, y, np.full(len(c), y[pop].mean()), pop, n_layak).ditandai
    score = rules.sum(axis=1).to_numpy()[pop]
    pmf = np.bincount(score, minlength=len(rules.columns) + 1) / len(score)
    per_rs = pd.Series(score).groupby(c.kode_rs.to_numpy()[pop])
    z = pd.Series({k: S.exact_z([pmf] * len(g), int(g.sum())) for k, g in per_rs})
    out["skor_poin"] = S.robust_flags(z.reindex(n_layak.index).fillna(0), n_layak, per_rs.sum() > per_rs.size() * score.mean()).ditandai
    return pd.DataFrame(out)


def raw_z_flags(t: pd.DataFrame) -> pd.Series:
    ok = t.n_layak >= S.MIN_KLAIM
    p = pd.Series(1.0, index=t.index)
    p[ok] = false_discovery_control(norm.sf(t.z[ok]), method="bh")
    return ok & (p <= S.BH_Q)


def prolonged_diagnosis(kh: pd.DataFrame, tables: dict) -> list[dict]:
    r = kh.set_index("kode_rs")
    rows = []
    for rs in r.index[r.modus == "diperpanjang"]:
        row = {"rs": rs, "kelas": r.at[rs, "kelas_rs"], "tingkat": r.at[rs, "tingkat"],
               "intensitas_terwujud": float(r.at[rs, "intensitas_terwujud"]), "klaim_dimanipulasi": int(r.at[rs, "klaim_dimanipulasi_modus"])}
        for name, t in tables.items():
            row[f"{name}_n_jendela"] = int(t.at[rs, "n_uji"])
            row[f"{name}_O_minus_E"] = round(float(t.at[rs, "O"] - t.at[rs, "E"]), 2)
            row[f"{name}_ditandai"] = bool(t.at[rs, "ditandai"])
        rows.append(row)
    return sorted(rows, key=lambda x: -x["klaim_dimanipulasi"])


def calibration_plot(series: dict[str, list[dict]], path: Path) -> None:
    fig = Figure(figsize=(5.5, 5))
    ax = fig.subplots()
    ax.plot([1e-4, 1 - 1e-4], [1e-4, 1 - 1e-4], color="#C9C7C3", lw=1, ls="--", label="kalibrasi sempurna")
    for (label, bins), color in zip(series.items(), ("#898781", "#2A78D6")):
        ax.plot([b["p_rata"] for b in bins], [b["teramati"] for b in bins], marker="o", ms=6, color=color, lw=2, label=label)
    ax.set_xscale("logit")
    ax.set_yscale("logit")
    ticks = [0.001, 0.01, 0.1, 0.5, 0.9, 0.99, 0.999]
    labels = [f"{t:g}".replace(".", ",") for t in ticks]
    ax.set_xticks(ticks, labels)
    ax.set_yticks(ticks, labels)
    ax.minorticks_off()
    ax.set_xlabel("Peluang kode pemicu menurut AI 1 (skala logit)")
    ax.set_ylabel("Porsi klaim yang berkode pemicu, teramati")
    ax.set_title(f"Kalibrasi AI 1 modus fiktif di klaim RS jujur, {world_label()}", loc="left")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=160)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(A.SEED)
    w = load_world(world_dir(), with_key=True, key=key_dir())
    c, h, kh = w["claims"], w["hospitals"], w["key_hospitals"]
    k = c[["nomor_sep"]].merge(w["key_claims"], on="nomor_sep", how="left")
    rs = c.kode_rs
    honest_rows = rs.isin(kh.kode_rs[honest_hospitals(kh)]).to_numpy()
    size = pd.qcut(rs.value_counts(), 3, labels=["kecil", "sedang", "besar"])
    y_f, elig_f = A.has_trigger(c), A.eligible_fictitious(c)
    win, y_p = A.prolonged_window(c), (c.ventilator_hour >= A.GARIS).to_numpy()
    cand_f, cand_p = y_f & A.in_line(c), win & y_p
    rules = S.point_score_rules(c)
    point = rules.sum(axis=1).to_numpy().astype(float)

    def t6(p: np.ndarray, cand: np.ndarray, modes, rival: np.ndarray | None = None, other: str = "skor_poin") -> dict:
        positive = k.modus.isin(modes).to_numpy()
        pool = cand & (positive | (k.modus == "").to_numpy())
        score = point if rival is None else 1 - rival
        return ranking_metrics(1 - p[pool], score[pool], positive[pool], (k.selisih_rupiah.to_numpy() * positive)[pool],
                               rs.to_numpy()[pool], k.modus.to_numpy()[pool], kh, size, rng, other)

    report = {"versi_model": MODEL_VERSION, "dunia": world_label(), "klaim": len(c), "rs": int(rs.nunique())}
    runs, placebo, c0 = {}, {}, w["key_placebo_claims"]
    for variant, with_costs, status in (("lengkap", True, False), ("tanpa_rincian_tarif", False, False),
                                        ("dengan_status_pulang", True, True)):
        vocab, X, mf, mp = runs[variant] = detect(c, h, with_costs, status=status)
        _, _, f0, p0 = placebo[variant] = detect(c0, h, with_costs, status=status)
        flags = mf.table.ditandai | mp.table.ditandai
        report[variant] = {
            "fitur": X.shape[1],
            "auc_rs_jujur": {
                "fiktif_semua_klaim": round(roc_auc_score(y_f[honest_rows], mf.p_raw[honest_rows]), 3),
                "fiktif_klaim_layak": round(roc_auc_score(y_f[honest_rows & elig_f], mf.p_raw[honest_rows & elig_f]), 3),
                "diperpanjang_jendela": round(roc_auc_score(y_p[honest_rows & win], mp.p_raw[honest_rows & win]), 3),
            },
            "kalibrasi_total_rs_jujur_fiktif": round(float(y_f[honest_rows].sum() / mf.p[honest_rows].sum()), 3),
            "kalibrasi_total_rs_jujur_fiktif_sebelum_isotonik": round(float(y_f[honest_rows].sum() / mf.p_raw[honest_rows].sum()), 3),
            "kalibrasi_bin_fiktif": {"sebelum isotonik": calibration_bins(y_f[honest_rows], mf.p_raw[honest_rows]),
                                     "sesudah isotonik": calibration_bins(y_f[honest_rows], mf.p[honest_rows])},
            "t1_fiktif": recall_table(mf.table, kh, "fiktif"),
            "t1_diperpanjang": recall_table(mp.table, kh, "diperpanjang"),
            "rme_meragukan_ditandai_lewat_fiktif": recall_table(mf.table, kh, "rme_meragukan"),
            "t2": false_alarms(flags, kh, (mf.table.n_layak >= S.MIN_KLAIM) | (mp.table.n_layak >= S.MIN_KLAIM)),
            "rs_jujur_ditandai_per_kelompok": honest_shares(flags.index[flags], kh, size),
            "ditandai_putaran1_vs_akhir": {"fiktif": [int(mf.table.ditandai_putaran1.sum()), int(mf.table.ditandai.sum())],
                                          "diperpanjang": [int(mp.table.ditandai_putaran1.sum()), int(mp.table.ditandai.sum())]},
            "t5_fiktif": rupiah_errors(c, h, k, kh, mf, y_f, elig_f, "fiktif", rng),
            "t5_diperpanjang": rupiah_errors(c, h, k, kh, mp, y_p, win, "diperpanjang", rng),
            "porsi_rupiah_tertanam_di_rs_ditandai": {m: embedded_share(k, t.index[t.ditandai], m)
                                                     for m, t in (("fiktif", mf.table), ("diperpanjang", mp.table))},
            "t6_fiktif": t6(mf.p_raw, cand_f, ["fiktif"]),
            "t6_fiktif_termasuk_rme_meragukan": t6(mf.p_raw, cand_f, FAKE),
            "t6_diperpanjang": t6(mp.p_raw, cand_p, ["diperpanjang"]),
            "plasebo": {"ditandai_fiktif": int(f0.table.ditandai.sum()), "ditandai_diperpanjang": int(p0.table.ditandai.sum()),
                        "rs_ditandai": {m: t.loc[t.ditandai, ["n_layak", "O", "E", "z_robust", "p_bh"]].round(3).reset_index().to_dict("records")
                                        for m, t in (("fiktif", f0.table), ("diperpanjang", p0.table))}},
        }
        print(variant, json.dumps(report[variant]["auc_rs_jujur"]), flush=True)

    vocab, X, mf, mp = runs["lengkap"]
    variants = {"lengkap": mp.table, "tanpa_rincian_tarif": runs["tanpa_rincian_tarif"][3].table,
                "z_mentah": mp.table.assign(ditandai=raw_z_flags(mp.table))}
    report["diagnosis_diperpanjang"] = {
        "per_rs_pelaku": prolonged_diagnosis(kh, variants),
        "recall_varian": {name: recall_table(t, kh, "diperpanjang") for name, t in variants.items()},
        "alarm_palsu_varian_z_mentah": false_alarms(variants["z_mentah"].ditandai, kh, mp.table.n_layak >= S.MIN_KLAIM),
    }
    n_layak_f, n_layak_p = mf.table.n_layak, mp.table.n_layak
    flags_f, flags_p = rule_flags(c, rules, elig_f, n_layak_f), rule_flags(c, rules, win, n_layak_p)
    assessable = (n_layak_f >= S.MIN_KLAIM) | (n_layak_p >= S.MIN_KLAIM)
    report["pembanding_tanpa_ai"] = {
        col: {"fiktif": recall_table(pd.DataFrame({"ditandai": flags_f[col], "n_layak": n_layak_f}), kh, "fiktif")["recall_biasa"],
              "diperpanjang": recall_table(pd.DataFrame({"ditandai": flags_p[col], "n_layak": n_layak_p}), kh, "diperpanjang")["recall_biasa"],
              "t2": false_alarms(flags_f[col] | flags_p[col], kh, assessable)["t2_porsi"]}
        for col in flags_f.columns}

    _, _, mf0, mp0 = placebo["lengkap"]
    flags0 = mf0.table.ditandai | mp0.table.ditandai
    trap = kh.set_index("kode_rs").jebakan.reindex(flags0.index)
    truth0 = c0[["nomor_sep"]].merge(w["key_claims"][["nomor_sep", "ventilasi"]], on="nomor_sep", how="left").ventilasi.astype(bool)
    report["plasebo_kembaran_bebas_fraud"] = {
        "rs": len(flags0), "rs_dinilai": int(((mf0.table.n_layak >= S.MIN_KLAIM) | (mp0.table.n_layak >= S.MIN_KLAIM)).sum()),
        "ditandai_fiktif": int(mf0.table.ditandai.sum()), "ditandai_diperpanjang": int(mp0.table.ditandai.sum()),
        "ditandai_putaran1_fiktif": int(mf0.table.ditandai_putaran1.sum()),
        "porsi_tanpa_sakit_tersembunyi": round(float(flags0[trap != "sakit_tersembunyi"].mean()), 3),
        "per_jebakan": {j or "bukan jebakan": f"{int(g.sum())}/{len(g)}" for j, g in flags0.groupby(trap)},
        "fiktif": placebo_details(mf0, c0, truth0.to_numpy(), kh),
    }
    report["pindai_kebocoran_dev"] = A.leakage_scan(X[elig_f], y_f[elig_f].astype(int), rs.to_numpy()[elig_f])

    for name, status in (("model_sederhana", True), ("model_sederhana_tanpa_status_pulang", False)):
        _, _, sf, sp = detect(c, h, True, fit=cross_fit_simple, status=status)
        _, _, sf0, sp0 = detect(c0, h, True, fit=cross_fit_simple, status=status)
        flags_s, flags_s0 = sf.table.ditandai | sp.table.ditandai, sf0.table.ditandai | sp0.table.ditandai
        report[name] = {
            "fitur": ["umur", "lama_rawat", "dx_primer"] + (["discharge_status"] if status else []),
            "auc_rs_jujur": {"fiktif_semua_klaim": round(roc_auc_score(y_f[honest_rows], sf.p_raw[honest_rows]), 3),
                             "diperpanjang_jendela": round(roc_auc_score(y_p[honest_rows & win], sp.p_raw[honest_rows & win]), 3)},
            "t1_fiktif": recall_table(sf.table, kh, "fiktif"),
            "t1_diperpanjang": recall_table(sp.table, kh, "diperpanjang"),
            "t2": false_alarms(flags_s, kh, (sf.table.n_layak >= S.MIN_KLAIM) | (sp.table.n_layak >= S.MIN_KLAIM)),
            "plasebo": {"ditandai_fiktif": int(sf0.table.ditandai.sum()), "ditandai_diperpanjang": int(sp0.table.ditandai.sum()),
                        "per_jebakan": {j or "bukan jebakan": f"{int(g.sum())}/{len(g)}"
                                        for j, g in flags_s0.groupby(kh.set_index("kode_rs").jebakan.reindex(flags_s0.index))}},
            "presisi_pada_k_fiktif": t6(mf.p_raw, cand_f, ["fiktif"], sf.p_raw, "model_sederhana"),
            "presisi_pada_k_diperpanjang": t6(mp.p_raw, cand_p, ["diperpanjang"], sp.p_raw, "model_sederhana"),
        }

    biasa = (k.tingkat == "biasa").to_numpy()
    fake_rows = y_f & k.modus.isin(FAKE).to_numpy()
    long_rows = cand_p & (k.modus == "diperpanjang").to_numpy()
    tau_f = float(np.quantile(mf.p[fake_rows & biasa], 0.90, method="higher"))
    tau_p = float(np.quantile(mp.p[long_rows & biasa], 0.90, method="higher"))
    fast = (mf.p > tau_f) & (~cand_p | (mp.p > tau_p))
    report["ambang"] = {
        "fiktif": round(tau_f, 4), "diperpanjang": round(tau_p, 4),
        "aturan": ("sementara: ≤10% klaim curang tingkat biasa di DEV lolos bagian AI 1; jalur cepat hanya bila AI 1 rendah risiko "
                   "dan lapis cepat AI 2 bersih; ambang final setelah AI 2"),
        "klaim_jujur_lolos_ai1": round(float(fast[cand_f & ~k.dimanipulasi.to_numpy()].mean()), 3),
        "klaim_curang_lolos_ai1_per_tingkat": {f"{m} {t}": f"{int(fast[g.index].sum())}/{len(g)}"
                                                 for (m, t), g in k[(fake_rows | long_rows)].groupby(["modus", "tingkat"])},
        "n_klaim_biasa": {"fiktif": int((fake_rows & biasa).sum()), "diperpanjang": int((long_rows & biasa).sum())},
    }

    clean_f = ~rs.isin(mf.table.index[mf.table.ditandai]).to_numpy()
    clean_p = ~rs.isin(mp.table.index[mp.table.ditandai]).to_numpy()
    # Not cached: a model reloaded from the cache pickles to different bytes and would change the recorded fingerprint.
    models = {"fiktif": A.final_model(X[clean_f], y_f[clean_f].astype(int), rs.to_numpy()[clean_f]),
              "panjang": A.final_model(X[win & clean_p], y_p[win & clean_p].astype(int), rs.to_numpy()[win & clean_p])}
    dx3 = c.diagnosa.str[:3].to_numpy()
    ref_rows = cand_f & clean_f
    q = np.linspace(0, 1, 101)
    percentiles = {"_semua": np.quantile(mf.p[ref_rows], q).tolist()}
    percentiles.update({d: np.quantile(mf.p[ref_rows & (dx3 == d)], q).tolist()
                        for d, n in pd.Series(dx3[ref_rows]).value_counts().items() if n >= 30})
    bundle = A.Bundle(MODEL_VERSION, vocab, models, A.reference_values(X, y_f & clean_f & (mf.p >= 0.5)), percentiles,
                      {"fiktif": tau_f, "panjang": tau_p},
                      {"dilatih_pada": f"{world_label()} tanpa RS yang ditandai", "klaim_fiktif": int(clean_f.sum()),
                       "klaim_jendela": int((win & clean_p).sum())})
    report["model_tersimpan"] = A.save_bundle(bundle, (A.MODELS_DIR if canonical_dev() else OUT) / f"ai1-{MODEL_VERSION}.joblib")
    report["rs_ditandai"] = {
        "fiktif": flagged_hospitals(mf, elig_f & y_f, rs, X, bundle, "fiktif", report["lengkap"]["t5_fiktif"]["rs"]),
        "diperpanjang": flagged_hospitals(mp, cand_p, rs, X, bundle, "panjang", report["lengkap"]["t5_diperpanjang"]["rs"]),
    }
    pd.DataFrame({"nomor_sep": c.nomor_sep, "p_fiktif": mf.p, "p_fiktif_mentah": mf.p_raw, "p_panjang": mp.p,
                  "p_panjang_mentah": mp.p_raw}).to_parquet(OUT / "skor_luar_lipatan_dev.parquet")

    order = np.argsort(np.where(cand_f & ~clean_f, mf.p_raw, np.inf))[:5]
    p_model = bundle.predict(X.iloc[order], "fiktif")
    report["contoh_alasan"] = [{"nomor_sep": c.nomor_sep.iat[i], "p_luar_lipatan": round(float(mf.p[i]), 3), "p_model": round(float(pm), 3),
                                "modus_kunci": k.modus.iat[i] or "-", "tingkat": k.tingkat.iat[i] or "-",
                                "status": bundle.status(float(pm), None, None), "alasan": a}
                               for i, pm, a in zip(order, p_model, bundle.reasons(X.iloc[order], "fiktif"))]
    calibration_plot(report["lengkap"]["kalibrasi_bin_fiktif"], OUT / "kalibrasi_fiktif_dev.png")
    (OUT / "ai1_dev.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str))
    print(f"ditulis: {OUT / 'ai1_dev.json'}")


if __name__ == "__main__":
    main()
