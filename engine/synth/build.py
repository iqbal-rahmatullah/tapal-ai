# A TEST build prints only counts and the manifest hash, never key contents.
import argparse
import hashlib
import json
import secrets
import shutil
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from engine.synth import fraud as F
from engine.synth import grouper as G
from engine.synth import rme as R
from engine.synth import world as W

SEED_DEV = 20261031  # TARGETS v2 bagian 5
DATA = W.ROOT / "data"
SEALED = DATA / "sealed"
MANIFEST = SEALED / "MANIFEST.sha256"
# iDRG mock candidates for TEST (moved hour line, one new trigger), excluding DEV's 72 h and 93.90 and the comparators 120/144/168.
IDRG_HOURS = (48, 60, 84)
IDRG_CODES = ("38.93", "96.07", "57.94")
CLAIM_COLUMNS = (
    ["nomor_sep", "kode_rs", "bulan", "umur", "jenis_kelamin", "jenis_rawat", "kelas_rawat", "cara_masuk", "tgl_masuk",
     "tgl_pulang", "diagnosa", "procedure", "icu_indikator", "icu_los", "ventilator_hour", "ventilator_use_ind",
     "ventilator_start_dttm", "ventilator_stop_dttm", "discharge_status"]
    + [f"tarif_rs_{k}" for k in W.COST_KEYS] + ["cbg", "tarif_ina_cbg"]
)
KEY_COLUMNS = [
    "nomor_sep", "kode_rs", "bulan", "segmen", "grup_operasi", "dx3", "ventilasi", "jam_ventilasi_benar",
    "mulai_ventilasi", "selesai_ventilasi", "icu_masuk", "icu_keluar", "alat_tertinggi", "meninggal",
    "meninggal_saat_ventilasi", "trakeostomi", "bukti_ringan", "keparahan", "jebakan", "dimanipulasi", "modus",
    "tingkat", "varian", "rme_versi", "sumber_kloning", "cbg_jujur", "tarif_jujur", "selisih_rupiah",
    "klaim_layak_fiktif", "klaim_layak_diperpanjang", "populasi_garis",
]


def world_spec(seed: int, condition: str, test: bool) -> dict:
    cond = F.CONDITIONS[condition]
    late = cond.late_note_factor
    if not test:
        grouper = G.IDRG_MOCK if cond.idrg else G.DEFAULT
        params = W.WorldParams(seed=seed, evidence_noise=cond.evidence_noise, grouper=grouper, bulk_busy_share=cond.busy_day_share,
                               late_note_share=W.WorldParams.late_note_share * late,
                               late_note_median_h=W.WorldParams.late_note_median_h * late)
        return {"params": params, "condition": cond, "hidden": F.DEV_HIDDEN_MODE, "second": F.DEV_SECOND_LINE}
    # TEST shifts documentation habits and evidence noise away from DEV (TARGETS v2 bagian 3 aturan 2); every draw happens
    # for every condition in the same order, so conditions sharing a seed share their honest world.
    rng = np.random.default_rng([seed, 0])
    params = W.WorldParams(
        seed=seed,
        evidence_noise=float(rng.uniform(1.0, 1.3)) * cond.evidence_noise,
        code_effect_sd=float(rng.uniform(0.30, 0.45)),
        intubation_code_mean=float(rng.uniform(0.12, 0.25)),
        rounding_mean=float(rng.uniform(0.10, 0.30)),
        rent_styles=tuple(float(x) for x in rng.dirichlet([9, 8, 3])),
        write_lag_median_min=float(rng.uniform(20, 60)),
        late_note_share=float(rng.uniform(0.02, 0.06)) * late,
        late_note_median_h=float(rng.uniform(6, 18)) * late,
        bulk_note_share=float(rng.uniform(0.30, 0.50)),
        bulk_report_share=float(rng.uniform(0.05, 0.15)),
        held_out_style=True,
        bulk_busy_share=cond.busy_day_share,
        traps={"bulat_kuat": int(rng.integers(4, 9)), "sakit_terlihat": int(rng.integers(3, 7)),
               "sakit_tersembunyi": int(rng.integers(2, 5)), "tulis_massal_jujur": int(rng.integers(3, 7))},
    )
    hidden, second = F.ALLOWED_PAIRS[int(rng.integers(len(F.ALLOWED_PAIRS)))]
    idrg_hours, idrg_code = int(rng.choice(IDRG_HOURS)), str(rng.choice(IDRG_CODES))
    if cond.idrg:
        params = replace(params, grouper=replace(G.DEFAULT, long_vent_min_hours=idrg_hours,
                                                 j120_triggers=G.DEFAULT.j120_triggers | {idrg_code}))
    return {"params": params, "condition": cond, "hidden": hidden, "second": second}


def build(seed: int, condition: str, test: bool, scale: float = 1.0, with_rme: bool | None = None) -> dict:
    spec = world_spec(seed, condition, test)
    p = replace(spec["params"], scale=scale)
    cond = spec["condition"]
    cal = W.load_calibration()
    h, s = W.build_world(p, cal)
    roles = F.assign_roles(np.random.default_rng([seed, 1]), h, cond, spec["hidden"], spec["second"])
    if cond.claim_share:
        roles = F.scale_to_claim_share(roles, s, cond.claim_share, p.grouper)
    c = F.inject(s, h, roles, p.grouper, np.random.default_rng([seed, 2]))
    h, roles, s, c = anonymise(h, roles, s, c, np.random.default_rng([seed, 3]))
    c["klaim_layak_fiktif"] = F.eligible_fictitious(c)
    c["klaim_layak_diperpanjang"] = F.eligible_prolonged(s, p.grouper)
    c["populasi_garis"] = F.in_line_population(c)
    tables = {
        "claims": c[CLAIM_COLUMNS],
        "hospitals": h[["kode_rs", "kelas_rs", "kepemilikan", "regional"]],
        "key_claims": c[KEY_COLUMNS],
        "key_hospitals": h.merge(roles.drop(columns=["kelas_rs", "jebakan"]), on="kode_rs").merge(
            realized(c, s, roles, p.grouper), on="kode_rs", how="left"),
    }
    # Fraud-free twin of the same world for the eval kit's placebo test; it lives with the key because the difference
    # reveals which claims were manipulated.
    twin = s.assign(modus="", rme_versi="jujur", sumber_kloning="")
    tables["key_placebo_claims"] = twin[CLAIM_COLUMNS]
    # The iDRG mock only serves T21 (finding the moved lines), which reads claims, not records.
    if with_rme if with_rme is not None else not cond.idrg:
        vital_table = cal["icu"]["eicu"]["tanda_vital_per_alat"]
        docs, sentences, vitals, stories = R.generate(c, h, vital_table, seed)
        tables["rme_documents"] = docs
        tables["rme_vitals"] = vitals
        tables["key_sentences"] = sentences
        tables["key_claims"] = tables["key_claims"].merge(stories.drop(columns="rme_versi"), on="nomor_sep", how="left")
        twin_docs, _, twin_vitals, _ = R.generate(twin, h, vital_table, seed)
        tables["key_placebo_rme_documents"] = twin_docs
        tables["key_placebo_rme_vitals"] = twin_vitals
    g = p.grouper
    tables["key_world"] = {
        "seed": seed, "kondisi": condition, "uji": "TEST" if test else "DEV", "skala": scale,
        "modus_tersembunyi": spec["hidden"], "garis_kedua": spec["second"],
        "grouper": {"garis_jam": g.long_vent_min_hours or 96, "pemicu_j120": sorted(g.j120_triggers)},
        "parameter_dunia": {k: v for k, v in asdict(p).items() if k != "grouper"},
        "kondisi_spesifikasi": asdict(cond),
        "dibuat": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sidik_generator": generator_fingerprint(),
    }
    return tables


def anonymise(h: pd.DataFrame, roles: pd.DataFrame, s: pd.DataFrame, c: pd.DataFrame,
              rng: np.random.Generator) -> tuple:
    # Fresh hospital numbers and random SEP numbers after the roles are dealt, plus shuffled rows, so no ID or row order
    # carries a role (eval-kit leakage rule).
    new_rs = dict(zip(h.kode_rs, [f"RS-{i + 1:03d}" for i in rng.permutation(len(h))]))
    seps = pd.Series([f"SEP-{x:010d}" for x in rng.choice(9_000_000_000, len(c), replace=False) + 1_000_000_000], index=c.index)
    old_to_new = dict(zip(c.nomor_sep, seps))
    for df in (s, c):
        df["kode_rs"] = df.kode_rs.map(new_rs)
        df["nomor_sep"] = seps
    c["sumber_kloning"] = c.sumber_kloning.map(old_to_new).fillna("")
    order = rng.permutation(len(c))
    s, c = s.iloc[order].reset_index(drop=True), c.iloc[order].reset_index(drop=True)
    h = h.assign(kode_rs=h.kode_rs.map(new_rs)).sort_values("kode_rs").reset_index(drop=True)
    return h, roles.assign(kode_rs=roles.kode_rs.map(new_rs)), s, c


def realized(c: pd.DataFrame, s: pd.DataFrame, roles: pd.DataFrame, cfg: G.GrouperConfig) -> pd.DataFrame:
    # Realised intensity on the TARGETS v2 denominators, because a nominal perpetrator may never have had an eligible patient.
    pools = {"fiktif": F.eligible_fictitious(c) & ~c.ventilasi.to_numpy(), "diperpanjang": F.eligible_prolonged(s, cfg),
             "rme_meragukan": F.in_line_population(c)}
    mode = c.kode_rs.map(roles.set_index("kode_rs").modus).to_numpy()
    out = pd.DataFrame({"kode_rs": c.kode_rs, "pool": False, "hit": c.modus.isin(F.MAIN_MODES).to_numpy(), "any": c.dimanipulasi})
    for m, pool in pools.items():
        out.loc[mode == m, "pool"] = pool[mode == m]
    g = out.groupby("kode_rs")
    return pd.DataFrame({"klaim_kolam_modus": g.pool.sum(), "klaim_dimanipulasi_modus": g.hit.sum(),
                         "klaim_dimanipulasi_semua": g["any"].sum(),
                         "intensitas_terwujud": (g.hit.sum() / g.pool.sum().clip(lower=1)).round(4)}).reset_index()


def generator_fingerprint() -> str:
    # Hash of the generator sources and calibration, so a sealed key can be traced to the code that made it.
    h = hashlib.sha256()
    for f in sorted((W.ROOT / "engine/synth").glob("*.py")) + sorted(W.CALIBRATION_DIR.glob("*.json")):
        h.update(f.name.encode() + f.read_bytes())
    return h.hexdigest()


def write(tables: dict, public_dir: Path, key_dir: Path) -> None:
    public_dir.mkdir(parents=True, exist_ok=True)
    key_dir.mkdir(parents=True, exist_ok=True)
    for name, t in tables.items():
        target = key_dir if name.startswith("key_") else public_dir
        if isinstance(t, dict):
            (target / f"{name}.json").write_text(json.dumps(t, ensure_ascii=False, indent=1, default=str))
        else:
            t.to_parquet(target / f"{name}.parquet", index=False)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seal() -> str:
    # One manifest covers every TEST file, public and sealed; TARGETS.lock records the manifest's hash.
    files = sorted(p for d in (DATA / "test", SEALED / "test") for p in d.rglob("*") if p.is_file())
    lines = [f"{sha256(p)}  {p.relative_to(DATA)}" for p in files]
    MANIFEST.write_text("\n".join(lines) + "\n")
    return sha256(MANIFEST)


def main() -> None:
    a = argparse.ArgumentParser(description="dev: DEV (kunci terbuka di data/dev/<kondisi>/key/); test: semua kondisi TEST, kunci disegel di data/sealed/")
    a.add_argument("set", choices=["dev", "test"])
    a.add_argument("--condition", default=None, help="satu kondisi; bawaan: dasar untuk dev, semua untuk test")
    a.add_argument("--replace-test", action="store_true",
                   help="bangkitkan ulang TEST; hanya sebelum hash kuncinya dicatat di TARGETS.lock")
    args = a.parse_args()
    if args.set == "dev":
        condition = args.condition or "dasar"
        t = build(SEED_DEV, condition, test=False)
        out = DATA / "dev" / condition
        if out.exists():
            shutil.rmtree(out)
        write(t, out, out / "key")
        print(f"DEV {condition}: {len(t['claims'])} klaim, {len(t.get('rme_documents', []))} dokumen RME -> {out}")
        return
    if (SEALED / "test").exists() and not args.replace_test:
        raise SystemExit("TEST sudah ada dan tersegel; pakai --replace-test hanya bila hash belum dicatat di TARGETS.lock")
    for d in (DATA / "test", SEALED / "test"):
        if d.exists():
            shutil.rmtree(d)
    # One seed for every TEST condition keeps honest claims and perpetrators identical, so only the dials differ.
    seed = secrets.randbits(63)
    for condition in [args.condition] if args.condition else list(F.CONDITIONS):
        t = build(seed, condition, test=True)
        write(t, DATA / "test" / condition, SEALED / "test" / condition)
        print(f"TEST {condition}: {len(t['claims'])} klaim, {len(t.get('rme_documents', []))} dokumen RME")
    print(f"hash manifest kunci TEST: {seal()}  ({MANIFEST.relative_to(W.ROOT)})")


if __name__ == "__main__":
    main()
