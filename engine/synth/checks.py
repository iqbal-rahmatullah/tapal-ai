# Key-dependent checks run on DEV only, because TEST stays sealed.
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from engine.contracts import (MAJOR_SURGERY_CODES, MAJOR_SURGERY_GROUPS, TARGET_DIAGNOSIS_CODES, GroupedClaim,
                              RmeDocument, VitalSign, is_eligible_fictitious)
from engine.synth import grouper as G
from engine.synth.world import load_calibration

LINE = ["J-1-20", "J-1-02", "J-1-01"]


def _claim_record(row: pd.Series) -> dict:
    d = {k: row[k] for k in GroupedClaim.model_fields if k in row and k not in ("tarif_rs", "ventilator")}
    d["tarif_rs"] = {k[len("tarif_rs_"):]: int(row[k]) for k in row.index if k.startswith("tarif_rs_")}
    if row.ventilator_use_ind:
        d["ventilator"] = {"use_ind": 1, "start_dttm": row.ventilator_start_dttm, "stop_dttm": row.ventilator_stop_dttm}
    for k in ("umur", "jenis_rawat", "kelas_rawat", "icu_indikator", "icu_los", "ventilator_hour", "discharge_status", "tarif_ina_cbg"):
        d[k] = int(d[k])
    return d


def key_free_checks(world: Path, n: int = 300) -> dict:
    c = pd.read_parquet(world / "claims.parquet")
    rng = np.random.default_rng(0)
    sample = c.iloc[rng.choice(len(c), min(n, len(c)), replace=False)]
    tsv = pd.read_csv(G.TARIFF_TSV, sep="\t", dtype=str)
    tsv = tsv[tsv.jenis == "RI"].set_index(["regional", "kelas_rs", "kode"])
    h = pd.read_parquet(world / "hospitals.parquet").set_index("kode_rs")
    mismatch = 0
    for r in sample.itertuples():
        hr = h.loc[r.kode_rs]
        label = f"KELAS {hr.kelas_rs} {'PEMERINTAH' if hr.kepemilikan == 'pemerintah' else 'SWASTA'}"
        expected = int(tsv.loc[(str(hr.regional), label, r.cbg), f"tarif_kelas{r.kelas_rawat}"].replace(".", ""))
        mismatch += expected != r.tarif_ina_cbg
    invalid = 0
    for _, r in sample.iterrows():
        try:
            GroupedClaim.model_validate(_claim_record(r))
        except Exception:
            invalid += 1
    out = {"klaim": len(c), "rs": int(c.kode_rs.nunique()), "tarif_tidak_cocok_tsv": int(mismatch),
           "klaim_tidak_sah_kontrak": int(invalid), "sampel": len(sample)}
    if (world / "rme_documents.parquet").exists():
        docs = pd.read_parquet(world / "rme_documents.parquet")
        vit = pd.read_parquet(world / "rme_vitals.parquet")
        bad_docs = sum(1 for _, d in docs.sample(min(n, len(docs)), random_state=0).iterrows() if not _valid(RmeDocument, d))
        bad_vit = sum(1 for _, v in vit.sample(min(n, len(vit)), random_state=0).iterrows() if not _valid(VitalSign, v))
        out.update({"dokumen_rme": len(docs), "baris_tanda_vital": len(vit), "dokumen_tidak_sah": bad_docs,
                    "tanda_vital_tidak_sah": bad_vit, "tulis_sebelum_layanan": int((docs.waktu_tulis < docs.waktu_layanan).sum())})
    return out


def _valid(model, row: pd.Series) -> bool:
    try:
        model.model_validate({k: (None if pd.isna(v) else v) for k, v in row.items() if k in model.model_fields})
        return True
    except Exception:
        return False


def asymmetry(hours: np.ndarray, line: int, width: int = 8) -> float:
    up = ((hours >= line) & (hours < line + width)).sum()
    down = ((hours >= line - width) & (hours < line)).sum()
    return float(np.log((up + 0.5) / (down + 0.5)))


def honest_line_statistic(k: pd.DataFrame, c: pd.DataFrame, reps: int = 300) -> dict:
    # The honest world must not bunch at 96 hours by itself.
    m = c.merge(k[["nomor_sep", "dimanipulasi"]], on="nomor_sep")
    m = m[(m.ventilator_use_ind == 1) & ~m.dimanipulasi]
    by_rs = [g.ventilator_hour.to_numpy() for _, g in m.groupby("kode_rs")]
    stat = lambda hs: asymmetry(hs, 96) - np.mean([asymmetry(hs, L) for L in (120, 144, 168)])
    rng = np.random.default_rng(1)
    boot = [stat(np.concatenate([by_rs[i] for i in rng.integers(0, len(by_rs), len(by_rs))])) for _ in range(reps)]
    hs = m.ventilator_hour.to_numpy()
    return {"S96_jujur": round(stat(hs), 3), "rentang95": [round(float(np.quantile(boot, q)), 3) for q in (0.025, 0.975)]}


# Tolerances fixed on 31 Oct 2026, after the first DEV build was seen and before regeneration.
def tolerance_ok(kind: str, value: float, ref) -> bool | None:
    if ref is None or pd.isna(value):
        return None
    if kind == "porsi":
        return bool(abs(value - ref) <= 0.05)
    if kind == "rasio":
        return bool(abs(value - ref) <= 0.10 * ref)
    if kind == "ukuran":
        return bool(abs(value - ref) <= max(0.10 * ref, 1.0))
    lo, hi = ref
    return bool(lo * 0.9 <= value <= hi * 1.1)


FIXED = "muncul sendiri (mekanisme diperbaiki setelah gagal di versi pertama)"


def reality_table(c: pd.DataFrame, k: pd.DataFrame, h: pd.DataFrame, cal: dict) -> pd.DataFrame:
    # Only "muncul sendiri" rows were never tuned, so only they test the world against reality.
    ds, icu = cal["ds"], cal["icu"]
    v = c[c.ventilator_use_ind == 1].merge(k[["nomor_sep", "dimanipulasi", "meninggal"]], on="nomor_sep")
    v = v[~v.dimanipulasi]
    c71, c72 = v.procedure.str.contains("96.71", regex=False), v.procedure.str.contains("96.72", regex=False)
    g = v.cbg.str[:6]
    sev = v.cbg.str.split("-").str[-1]
    n_dx2 = v.diagnosa.str.count("#").clip(upper=4)
    dv = ds["ventilasi"]
    honest = c.merge(k[["nomor_sep", "dimanipulasi"]], on="nomor_sep")
    honest = honest[~honest.dimanipulasi]
    line = honest[honest.cbg.str[:6].isin(LINE) | honest.procedure.str.contains(r"96\.04|96\.7[012]", regex=True)]
    line_class = line.kode_rs.map(h.set_index("kode_rs").kelas_rs)
    intub_only = honest[honest.procedure.str.contains("96.04", regex=False) & ~honest.procedure.str.contains(r"96\.7[012]", regex=True)]
    pv = dv["prosedur_lain_medis"]
    sev_by = dv["severitas_menurut_n_dx2"]
    vent_hours = k[k.ventilasi].jam_ventilasi_benar
    rows = [
        ("Klaim 96.71 yang masuk J-1-20", (g[c71] == "J-1-20").mean(), 0.73, "porsi", "muncul sendiri"),
        ("Klaim intubasi saja yang masuk J-1-20 (acuan 27 dari 33 klaim bukan bayi)", (intub_only.cbg.str[:6] == "J-1-20").mean(),
         ds["intubasi_saja"]["porsi_ke_j120"], "porsi", "muncul sendiri"),
        ("Severitas III pada klaim berventilasi dengan 1 diagnosis sekunder", (sev[n_dx2 == 1] == "III").mean(), sev_by["1"]["3"], "porsi", FIXED),
        ("Severitas III pada klaim berventilasi dengan ≥4 diagnosis sekunder", (sev[n_dx2 == 4] == "III").mean(), sev_by["4"]["3"], "porsi", FIXED),
        ("Median durasi ventilasi (jam), acuan rentang eICU–MIMIC", vent_hours.median(),
         (icu["eicu"]["durasi_episode_jam"]["0.5"], icu["mimic"]["durasi_episode_jam"]["0.5"]), "rentang", "muncul sendiri"),
        ("Rasio klaim 96.71 : 96.72", c71.sum() / c72.sum(), dv["rasio_9671_9672"], "rasio", "disetel"),
        ("Klaim 96.72 yang masuk J-1-01 (trakeostomi)", (g[c72] == "J-1-01").mean(), dv["porsi_9672_ke_j101"], "porsi", "disetel"),
        ("Median lama rawat (hari), klaim 96.71", v[c71].lama_rawat_hari.median(), dv["lama_rawat_kuantil"]["96.71"]["0.5"], "ukuran", "disetel"),
        ("Median lama rawat (hari), klaim 96.72", v[c72].lama_rawat_hari.median(), dv["lama_rawat_kuantil"]["96.72"]["0.5"], "ukuran", "disetel"),
        ("Persentil 90 lama rawat (hari), klaim 96.71", v[c71].lama_rawat_hari.quantile(0.9), dv["lama_rawat_kuantil"]["96.71"]["0.9"], "ukuran", "disetel"),
        ("Severitas III, klaim berventilasi", (sev == "III").mean(), dv["severitas"]["3"], "porsi", "disetel"),
        ("Severitas I, klaim berventilasi", (sev == "I").mean(), dv["severitas"]["1"], "porsi", "disetel"),
        ("Median jumlah diagnosis sekunder", v.diagnosa.str.count("#").median(), dv["n_dx_sekunder_kuantil"]["0.5"], "ukuran", "disetel"),
        ("Klaim berventilasi yang tetap di grup operasi besar", g.isin(MAJOR_SURGERY_GROUPS).mean(),
         dv["jalur"]["operasi"] / sum(dv["jalur"].values()), "porsi", "masukan"),
        ("Kode intubasi 96.04 pada klaim berventilasi", v.procedure.str.contains("96.04", regex=False).mean(), dv["porsi_kode_intubasi"], "porsi", "masukan"),
        ("Kode analisa gas darah 89.65 pada klaim berventilasi", v.procedure.str.contains("89.65", regex=False).mean(), dv["porsi_kode_agd"], "porsi", "masukan"),
        ("Kode RJP 99.60 pada klaim berventilasi", v.procedure.str.contains("99.60", regex=False).mean(), pv.get("99.60"), "porsi", "masukan"),
        ("Kode kateter vena sentral 38.93 pada klaim berventilasi", v.procedure.str.contains("38.93", regex=False).mean(), pv.get("38.93"), "porsi", "masukan"),
        ("Kematian, klaim 96.71", v[c71].meninggal.mean(), dv["porsi_meninggal"]["96.71"], "porsi", "masukan"),
        ("Kematian, klaim 96.72", v[c72].meninggal.mean(), dv["porsi_meninggal"]["96.72"], "porsi", "masukan"),
        ("Median umur (tahun)", v.umur.median(), dv["umur_kuantil"]["0.5"], "ukuran", "masukan"),
        ("Porsi laki-laki", (v.jenis_kelamin == "L").mean(), dv["porsi_laki"], "porsi", "masukan"),
        ("Porsi kelas rawat 3", (v.kelas_rawat == 3).mean(), dv["kelas_rawat"]["3"], "porsi", "masukan"),
        ("Porsi RS kelas A di populasi garis", (line_class == "A").mean(), _ds_class_share(ds, "A"), "porsi", "masukan"),
        ("Porsi RS kelas C di populasi garis", (line_class == "C").mean(), _ds_class_share(ds, "C"), "porsi", "masukan"),
        ("Nasal kanul sebagai alat tertinggi, ICU tanpa ventilasi", (k[~k.ventilasi].alat_tertinggi == "nasal_kanul").mean(),
         icu["eicu"]["alat_tertinggi_rawatan_tanpa_ventilasi"]["nasal_kanul"], "porsi", "masukan"),
        ("Porsi ventilasi di antara rawat ICU", k.ventilasi.mean(), None, "porsi", "dikarang (Data Sampel tanpa penanda ICU)"),
        ("Rincian tarif RS (sewa alat, rawat intensif, obat, dst.)", None, None, "porsi", "dikarang (Data Sampel tanpa rincian tagihan)"),
        ("Jeda tulis RME dan keterlambatan catatan", None, None, "porsi", "dikarang"),
        ("Kebiasaan mencatat jam dalam hari penuh (rerata 15% klaim)", None, None, "porsi", "dikarang"),
    ]
    tol = {"porsi": "±0,05", "rasio": "±10%", "ukuran": "±10% atau ±1", "rentang": "rentang ±10%"}
    notes = {
        "Klaim intubasi saja yang masuk J-1-20 (acuan 27 dari 33 klaim bukan bayi)": "dibiarkan gagal (keputusan pengguna 31 Okt)",
        "Severitas III pada klaim berventilasi dengan 1 diagnosis sekunder": "versi pertama 0,208 (gagal); koder kini menulis diagnosis terpenting lebih dulu, tidak disetel ke acuan",
        "Severitas III pada klaim berventilasi dengan ≥4 diagnosis sekunder": "versi pertama 0,764",
        "Median jumlah diagnosis sekunder": "lolos secara teknis (±1), tetapi selisihnya 33%; dibiarkan karena menambah komorbid merusak dua baris severitas",
    }
    t = pd.DataFrame(rows, columns=["ukuran", "sintetis", "acuan", "jenis", "label"])
    t["lolos"] = [tolerance_ok(j, s, r) for j, s, r in zip(t.jenis, t.sintetis, t.acuan)]
    t["toleransi"] = t.jenis.map(tol).where(t.lolos.notna(), "")
    t["sintetis"] = t.sintetis.astype(float).round(3)
    t["acuan"] = [r if r is None or isinstance(r, tuple) else round(float(r), 3) for r in t.acuan]
    t["catatan"] = t.ukuran.map(notes).fillna("")
    return t[["ukuran", "label", "sintetis", "acuan", "toleransi", "lolos", "catatan"]]


def _ds_class_share(ds: dict, k: str) -> float:
    mix = {key: n for key, n in ds["rs"]["kelas_kepemilikan"].items() if not key.startswith("lain")}
    return sum(n for key, n in mix.items() if key.startswith(k)) / sum(mix.values())


def hour_peaks(c: pd.DataFrame) -> dict:
    hrs = c.loc[(c.ventilator_use_ind == 1) & (c.ventilator_hour >= 24), "ventilator_hour"]
    at = hrs[hrs % 24 == 0].size
    near = hrs[(hrs % 24).isin([1, 2, 3, 21, 22, 23])].size / 6
    return {"klaim_di_kelipatan_24": int(at), "rerata_jam_tetangga": round(float(near), 1), "rasio_puncak": round(at / max(near, 1), 2)}


def dev_checks(world: Path) -> dict:
    cal = load_calibration()
    c = pd.read_parquet(world / "claims.parquet")
    k = pd.read_parquet(world / "key" / "key_claims.parquet")
    h = pd.read_parquet(world / "hospitals.parquet")
    c["lama_rawat_hari"] = (c.tgl_pulang.dt.normalize() - c.tgl_masuk.dt.normalize()).dt.days
    out = {"tanpa_kunci": key_free_checks(world)}
    m = k[k.dimanipulasi]
    out["kunci"] = {
        "nomor_sep_sama": bool(set(c.nomor_sep) == set(k.nomor_sep)),
        "kolom_kunci_bocor_ke_klaim": sorted(set(c.columns) & {"ventilasi", "jam_ventilasi_benar", "dimanipulasi", "modus", "selisih_rupiah"}),
        "manipulasi_per_modus": m.groupby(["modus", "tingkat"]).size().rename("n").reset_index().to_dict("records"),
        "selisih_tidak_positif": int((m.selisih_rupiah <= 0).sum()),
        "rupiah_tertanam_juta": round(m.selisih_rupiah.sum() / 1e6, 1),
    }
    p = c.merge(k[["nomor_sep", "modus", "jam_ventilasi_benar"]], on="nomor_sep")
    long_ = p[p.modus == "diperpanjang"]
    out["kunci"]["diperpanjang_jam_tercatat_96_104"] = bool(long_.ventilator_hour.between(96, 104).all())
    out["kunci"]["diperpanjang_jam_benar_72_95"] = bool(long_.jam_ventilasi_benar.between(72, 96, inclusive="left").all())
    out["puncak_24_jam"] = hour_peaks(c.merge(k[["nomor_sep", "dimanipulasi"]], on="nomor_sep").query("~dimanipulasi"))
    out["garis_96_dunia_jujur"] = honest_line_statistic(k, c)
    out["kelayakan_kontrak_sama_dengan_kunci"] = eligibility_agreement(c, k)
    out["pindai_kebocoran"] = leakage_scan(c.drop(columns="lama_rawat_hari"), k)
    if (world / "rme_documents.parquet").exists():
        out["rme"] = rme_consistency(world, k)
        out["jeda_tulis"] = write_lag_overlap(world, k)
        out["pindai_kebocoran_fitur_rme"] = rme_feature_scan(world, c, k)
    vent_by_dx = k[k.segmen == "medis_sasaran"].groupby("dx3").ventilasi.mean().round(3).to_dict()
    out["porsi_ventilasi_per_diagnosis_sasaran"] = vent_by_dx
    table = reality_table(c, k, h, cal)
    return out, table


def eligibility_agreement(c: pd.DataFrame, k: pd.DataFrame, n: int = 2000) -> dict:
    procs = c.procedure.str.split("#")
    claim_side = (
        (c.icu_indikator == 1) & c.diagnosa.str[:3].isin(TARGET_DIAGNOSIS_CODES)
        & ~c.cbg.str[:6].isin(MAJOR_SURGERY_GROUPS) & ~procs.map(lambda p: bool(set(p) & set(MAJOR_SURGERY_CODES)))
    ).to_numpy()
    key_side = c[["nomor_sep"]].merge(k[["nomor_sep", "klaim_layak_fiktif"]], on="nomor_sep").klaim_layak_fiktif.to_numpy()
    sample = c.sample(min(n, len(c)), random_state=0)
    contract = [is_eligible_fictitious(GroupedClaim.model_validate(_claim_record(r))) for _, r in sample.iterrows()]
    return {"klaim_berbeda": int((claim_side != key_side).sum()),
            "sampel_kontrak_berbeda_dari_versi_kolom": int((np.array(contract) != claim_side[c.index.get_indexer(sample.index)]).sum())}


def one_feature_auc(x: pd.Series, y: np.ndarray) -> float:
    from sklearn.metrics import roc_auc_score
    if x.dtype.kind == "M":
        x = x.astype("int64").where(x.notna())
    elif x.dtype.kind not in "biuf":
        x = pd.Series(pd.factorize(x.astype(str), sort=True)[0], index=x.index)
    a = roc_auc_score(y, x.astype(float).fillna(-1))
    return round(float(max(a, 1 - a)), 3)


def _scan(frame: pd.DataFrame, cols: list, sets: dict, limit: float) -> dict:
    out = {}
    for name, (d, label) in sets.items():
        y = label(d).to_numpy()
        scores = sorted(((col, one_feature_auc(d[col], y)) for col in cols), key=lambda kv: -kv[1])
        out[name] = {"positif": int(y.sum()), "teratas": dict(scores[:5]), "melewati_ambang": [c for c, v in scores if v > limit]}
    return out


def leakage_scan(c: pd.DataFrame, k: pd.DataFrame, limit: float = 0.80) -> dict:
    # Eval-kit rule: any public column (IDs and row order included) whose one-feature AUC tops 0.80 is a bug until explained.
    m = c.merge(k[["nomor_sep", "dimanipulasi", "modus", "populasi_garis", "klaim_layak_fiktif"]], on="nomor_sep")
    m["indeks_baris"] = np.arange(len(m))
    window = m.procedure.str.contains(r"96\.7[12]", regex=True) & m.ventilator_hour.between(72, 119)
    sets = {
        "populasi garis, semua modus": (m[m.populasi_garis], lambda d: d.dimanipulasi),
        "klaim layak fiktif, fiktif dan RME meragukan": (m[m.populasi_garis & m.klaim_layak_fiktif],
                                                         lambda d: d.modus.isin(["fiktif", "rme_meragukan"])),
        "jendela 72-119 jam, diperpanjang": (m[window], lambda d: d.modus == "diperpanjang"),
    }
    return _scan(m, list(c.columns) + ["indeks_baris"], sets, limit)


def rme_features(docs: pd.DataFrame, c: pd.DataFrame) -> pd.DataFrame:
    # Claim-level write-time features that only appear once columns are combined, such as which document kinds sit in a
    # bulk session (other patients' notes written within 90 minutes at the same hospital).
    d = docs.merge(c[["nomor_sep", "kode_rs", "tgl_pulang"]], on="nomor_sep")
    d["lag"] = (d.waktu_tulis - d.waktu_layanan) / pd.Timedelta(hours=1)
    d["setelah_pulang"] = d.waktu_tulis > d.tgl_pulang
    d["menit"] = (d.waktu_tulis - pd.Timestamp("2024-01-01")) / pd.Timedelta(minutes=1)
    window = lambda t: np.searchsorted(t, t + 90, "right") - np.searchsorted(t, t - 90, "left")
    d = d.sort_values(["kode_rs", "menit"])
    d["n_rs"] = d.groupby("kode_rs").menit.transform(lambda x: window(x.to_numpy()))
    d = d.sort_values(["nomor_sep", "menit"])
    d["n_klaim"] = d.groupby("nomor_sep").menit.transform(lambda x: window(x.to_numpy()))
    d["sesi_massal"] = (d.n_rs - d.n_klaim) >= 10
    f = d.pivot_table(index="nomor_sep", columns="jenis", values=["lag", "sesi_massal", "setelah_pulang"],
                      aggfunc={"lag": "max", "sesi_massal": "mean", "setelah_pulang": "mean"})
    f.columns = [f"{a}_{b}" for a, b in f.columns]
    f["sesi_massal_semua"] = d.groupby("nomor_sep").sesi_massal.mean()
    f["lag_maksimum"] = d.groupby("nomor_sep").lag.max()
    return f.reset_index()


def rme_feature_scan(world: Path, c: pd.DataFrame, k: pd.DataFrame, limit: float = 0.80) -> dict:
    docs = pd.read_parquet(world / "rme_documents.parquet", columns=["nomor_sep", "jenis", "waktu_layanan", "waktu_tulis"])
    f = rme_features(docs, c).merge(k[["nomor_sep", "rme_versi", "jebakan"]], on="nomor_sep")
    honest = f.rme_versi == "jujur"
    bulk_trap = honest & (f.jebakan == "tulis_massal_jujur")
    sets = {
        "RME massal vs semua RME jujur": (f[honest | (f.rme_versi == "massal")], lambda d: d.rme_versi == "massal"),
        "RME massal vs RS jujur yang menulis massal": (f[bulk_trap | (f.rme_versi == "massal")], lambda d: d.rme_versi == "massal"),
        "RME karangan (cerdik-2) vs semua RME jujur": (f[honest | (f.rme_versi == "karangan")], lambda d: d.rme_versi == "karangan"),
        "RME kloning vs semua RME jujur": (f[honest | (f.rme_versi == "kloning")], lambda d: d.rme_versi == "kloning"),
    }
    cols = [col for col in f.columns if col not in ("nomor_sep", "rme_versi", "jebakan")]
    return _scan(f, cols, sets, limit)


def write_lag_overlap(world: Path, k: pd.DataFrame) -> dict:
    # A single cut-off ("more than 48 hours late = cheating") must not separate honest from made-up notes.
    from sklearn.metrics import roc_auc_score
    docs = pd.read_parquet(world / "rme_documents.parquet", columns=["nomor_sep", "jenis", "waktu_layanan", "waktu_tulis"])
    docs["lag"] = (docs.waktu_tulis - docs.waktu_layanan) / pd.Timedelta(hours=1)
    docs = docs.merge(k[["nomor_sep", "rme_versi", "jebakan"]], on="nomor_sep")
    docs.loc[(docs.rme_versi == "jujur") & (docs.jebakan == "tulis_massal_jujur"), "rme_versi"] = "jujur_massal"
    honest = docs[docs.rme_versi.isin(["jujur", "jujur_massal"])]
    made_up = docs[docs.rme_versi.isin(["karangan", "massal"])]
    per_claim = docs[docs.rme_versi.isin(["jujur", "jujur_massal", "karangan", "massal"])].groupby("nomor_sep").agg(
        lag_max=("lag", "max"), versi=("rme_versi", "first"))
    per_claim["curang"] = per_claim.versi.isin(["karangan", "massal"])

    def auc(v: str, honest_kinds=("jujur", "jujur_massal")) -> float:
        sub = per_claim[per_claim.versi.isin([*honest_kinds, v])]
        return round(float(roc_auc_score(sub.versi == v, sub.lag_max)), 3)
    q = lambda x: [round(float(v), 1) for v in x.quantile([0.5, 0.9, 0.99])]
    return {
        "jujur_kuantil_50_90_99_jam": q(honest.lag), "jujur_lebih_48_jam": round(float((honest.lag > 48).mean()), 4),
        "jujur_resume_lebih_48_jam": round(float((honest[honest.jenis == "resume_medis"].lag > 48).mean()), 3),
        "karangan_massal_kuantil_50_90_99_jam": q(made_up.lag), "karangan_massal_paling_lama_48_jam": round(float((made_up.lag <= 48).mean()), 3),
        "klaim_jujur_dengan_catatan_lebih_48_jam": round(float((per_claim[~per_claim.curang].lag_max > 48).mean()), 3),
        "klaim_curang_dengan_catatan_lebih_48_jam": round(float((per_claim[per_claim.curang].lag_max > 48).mean()), 3),
        "auc_jeda_maksimum_per_klaim_karangan": auc("karangan"),
        "auc_jeda_maksimum_per_klaim_massal": auc("massal"),
        "auc_jeda_maksimum_massal_vs_rs_jujur_bermassal": auc("massal", ("jujur_massal",)),
    }


def rme_consistency(world: Path, k: pd.DataFrame) -> dict:
    s = pd.read_parquet(world / "key" / "key_sentences.parquet")
    honest = k[(k.rme_versi == "jujur") & k.ventilasi & k.populasi_garis]
    events = s[s.peristiwa.isin(["mulai", "selesai", "meninggal"])].groupby(["nomor_sep", "peristiwa"]).size().unstack(fill_value=0)
    ev = events.reindex(honest.nomor_sep).fillna(0)
    honest_nonvent = k[(k.rme_versi == "jujur") & ~k.ventilasi & k.populasi_garis]
    starts = s[(s.peristiwa == "mulai")].nomor_sep
    return {
        "jujur_berventilasi": len(honest),
        "tanpa_peristiwa_mulai": int((ev.get("mulai", 0) != 1).sum()),
        "tanpa_peristiwa_akhir": int(((ev.get("selesai", 0) + ev.get("meninggal", 0)) != 1).sum()),
        "rme_mulai_sama_kebenaran": bool((honest.rme_mulai == honest.mulai_ventilasi).all()),
        "jujur_tanpa_ventilasi_menyebut_intubasi": int(honest_nonvent.nomor_sep.isin(starts).sum()),
        "label_asersi": s.asersi.value_counts().to_dict(),
        "gaya": s.gaya.value_counts().to_dict(),
    }


def main() -> None:
    a = argparse.ArgumentParser(description="contoh: python3 -m engine.synth.checks data/dev/dasar")
    a.add_argument("world", type=Path)
    a.add_argument("--tanpa-kunci", action="store_true", help="untuk TEST: hanya cek yang tidak membuka kunci")
    args = a.parse_args()
    if args.tanpa_kunci:
        print(json.dumps(key_free_checks(args.world), indent=1, ensure_ascii=False))
        return
    out, table = dev_checks(args.world)
    (args.world / "checks.json").write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str))
    table.to_csv(args.world / "reality_table.csv", index=False)
    print(json.dumps(out, indent=1, ensure_ascii=False, default=str))
    print(table.to_string(index=False))


if __name__ == "__main__":
    main()
