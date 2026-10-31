from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from engine.synth import grouper as G
from engine.synth.world import CALIBRATION_DIR

pytestmark = pytest.mark.skipif(not (CALIBRATION_DIR / "data_sampel.json").exists(),
                                reason="kalibrasi lokal belum dibuat (Data Sampel hanya ada di laptop)")


@pytest.fixture(scope="module")
def dev():
    from engine.synth.build import SEED_DEV, build
    return build(SEED_DEV, "dasar", test=False, scale=0.25)


def test_grouper_follows_data_sampel_routes():
    medical, cardiac, crani = "J96", ("36.13",), ("01.24",)
    assert G.group(medical, {"96.71"}, [], 40).startswith("J-1-20")
    assert G.group(medical, {"96.04"}, [], 0).startswith("J-1-20")
    assert G.group(medical, {"96.72"}, [], 120).startswith("J-1-02")
    assert G.group(medical, {"96.72", "31.1"}, [], 200).startswith("J-1-01")
    assert G.group("I61", {"96.71", *crani}, [], 40).startswith("G-1-10")
    assert G.group("I61", {"96.72", *crani}, [], 120).startswith("J-1-02")
    assert G.group("I25", {"96.72", *cardiac}, [], 120).startswith("I-1-07")
    assert G.group(medical, {"96.71"}, ["J96", "E87"], 40).endswith("-III")
    assert G.group(medical, {"96.71"}, [], 80, G.IDRG_MOCK).startswith("J-1-02")
    assert G.group(medical, {"93.90"}, [], 0, G.IDRG_MOCK).startswith("J-1-20")


def test_tariff_reads_permenkes_row():
    t = pd.read_csv(G.TARIFF_TSV, sep="\t", dtype=str)
    row = t[(t.jenis == "RI") & (t.regional == "1") & (t.kelas_rs == "KELAS C SWASTA") & (t.kode == "J-1-02-III")].iloc[0]
    assert G.tariff(1, "C", "swasta", "J-1-02-III", 3) == int(row.tarif_kelas3.replace(".", ""))


def test_same_seed_same_world_and_honest_rounding_never_crosses_96():
    from engine.synth.world import WorldParams, build_world
    p = WorldParams(seed=7, scale=0.1)
    _, a = build_world(p)
    _, b = build_world(p)
    pd.testing.assert_frame_equal(a, b)
    v = a[a.ventilasi & ~a.prosedur.map(lambda x: "96.04" in x and "96.71" not in x and "96.72" not in x)]
    long_code = v.procedure.str.contains("96.72", regex=False)
    assert (long_code == (v.ventilator_hour >= 96)).all()
    assert (v.jam_ventilasi_benar[long_code] >= 95.5).all()  # only hour rounding at 95.5-96 crosses upward
    assert long_code[v.jam_ventilasi_benar >= 96].all()


def test_key_stays_out_of_claims_and_every_manipulation_pays(dev):
    claims, key = dev["claims"], dev["key_claims"]
    assert not {"ventilasi", "jam_ventilasi_benar", "dimanipulasi", "modus", "selisih_rupiah"} & set(claims.columns)
    assert set(claims.nomor_sep) == set(key.nomor_sep)
    m = key[key.dimanipulasi]
    assert (m.selisih_rupiah > 0).all()
    assert {"fiktif", "diperpanjang", "rme_meragukan"} <= set(m.modus)


def test_prolonged_moves_72_95_hours_to_96_104(dev):
    m = dev["claims"].merge(dev["key_claims"], on=["nomor_sep", "kode_rs", "bulan"])
    m = m[m.modus == "diperpanjang"]
    assert len(m) > 0
    assert m.ventilator_hour.between(96, 104).all()
    assert m.jam_ventilasi_benar.between(72, 96, inclusive="left").all()
    assert not m.meninggal_saat_ventilasi.any()


def test_fictitious_claims_come_from_eligible_unventilated_patients(dev):
    k = dev["key_claims"]
    f = k[k.modus.isin(["fiktif", "rme_meragukan"])]
    assert (f.segmen == "medis_sasaran").all() and not f.ventilasi.any()


def test_honest_record_tells_the_truth_and_fabricated_record_tells_the_claim(dev):
    k, s = dev["key_claims"], dev["key_sentences"]
    honest = k[(k.rme_versi == "jujur") & k.ventilasi & k.populasi_garis]
    assert (honest.rme_mulai == honest.mulai_ventilasi).all()
    starts = set(s[s.peristiwa == "mulai"].nomor_sep)
    honest_fake = k[(k.modus == "fiktif") & (k.rme_versi == "jujur")]
    assert not honest_fake.nomor_sep.isin(starts).any()
    made_up = k[k.rme_versi == "karangan"]
    assert made_up.nomor_sep.isin(starts).all()


def test_clone_copies_source_text_except_dates(dev):
    k, docs = dev["key_claims"], dev["rme_documents"]
    clone = k[k.rme_versi == "kloning"].iloc[0]
    strip = lambda sep: [t for t in docs[docs.nomor_sep == sep].sort_values("waktu_layanan").teks
                         if not t.startswith("Pasien usia")]
    digits = lambda texts: ["".join(ch for ch in t if not ch.isdigit()) for t in texts]
    assert digits(strip(clone.nomor_sep)) == digits(strip(clone.sumber_kloning))


def test_bulk_written_records_share_one_evening(dev):
    k, docs = dev["key_claims"], dev["rme_documents"]
    bulk = docs[docs.nomor_sep.isin(k[k.rme_versi == "massal"].nomor_sep)]
    assert (bulk.waktu_tulis > bulk.waktu_layanan + pd.Timedelta(hours=12)).mean() > 0.8


def test_held_out_style_only_in_test_worlds(dev):
    assert "campur_inggris" not in set(dev["key_sentences"].gaya)


def test_adapt_changes_course():
    from engine.synth.fraud import adapt
    role = pd.Series({"modus": "fiktif", "tingkat": "biasa", "intensitas": 0.3})
    out = [adapt(role, np.random.default_rng(i)) for i in range(30)]
    assert any(r.intensitas < 0.3 for r in out)
    assert any(r.modus == "diperpanjang" for r in out)
    assert any(r.tingkat == "cerdik_1" for r in out)


def test_idrg_mock_moves_the_line():
    from engine.synth.build import build
    t = build(11, "idrg_tiruan", test=False, scale=0.15)
    c = t["claims"]
    v = c[c.procedure.str.contains("96.71", regex=False) & (c.ventilator_hour >= 72)]
    assert len(v) and v.cbg.str[:6].isin({"J-1-02", "J-1-01", *G.DEFAULT.cardiac_not_moving}).all()
    assert (v.cbg.str[:6] == "J-1-02").mean() > 0.9
    assert "rme_documents" not in t


def test_test_draws_keep_dev_practice_and_comparator_lines_out():
    from engine.synth import build as B
    from engine.synth import fraud as F
    assert F.DEV_HIDDEN_MODE not in F.HIDDEN_MODES and F.DEV_SECOND_LINE not in F.SECOND_LINES
    assert ("sepsis_fiktif", "dx_sekunder_fiktif") not in F.ALLOWED_PAIRS
    assert not set(B.IDRG_HOURS) & {72, 96, 120, 144, 168} and "93.90" not in B.IDRG_CODES
    pairs = {(sp["hidden"], sp["second"]) for sp in (B.world_spec(s, "dasar", test=True) for s in range(200))}
    assert pairs == set(F.ALLOWED_PAIRS)


def test_fake_sepsis_raises_severity_but_never_eligibility():
    from engine.synth import fraud as F
    from engine.synth.world import WorldParams, build_world
    h, s = build_world(WorldParams(seed=5, scale=0.15))
    roles = F.assign_roles(np.random.default_rng(1), h, F.CONDITIONS["dasar"], "sepsis_fiktif", None)
    c = F.inject(s, h, roles, G.DEFAULT, np.random.default_rng(2))
    m = c.modus == "sepsis_fiktif"
    assert m.sum() > 0
    assert c[m].dx_sekunder3.map(lambda d: "A41" in d).all() and c[m].cbg.str.endswith("-III").all()
    assert (c.dx3 == s.dx3).all() and (F.eligible_fictitious(c) == F.eligible_fictitious(s)).all()


def test_coder_writes_the_most_important_diagnoses_first():
    from engine.synth.world import code_by_importance
    rng = np.random.default_rng(0)
    assert code_by_importance(rng, {"I10", "E87", "J96"}, 1) == ["J96"]
    assert code_by_importance(rng, {"I10", "E87", "J96"}, 2) == ["E87", "J96"]
    assert code_by_importance(rng, {"I10"}, 0) == []


def test_test_conditions_share_one_honest_world():
    from dataclasses import asdict
    from engine.synth.build import world_spec
    spec = {c: world_spec(42, c, test=True) for c in ("dasar", "jarang", "sering", "terkonsentrasi", "kasus_sulit", "idrg_tiruan")}
    base = asdict(spec["dasar"]["params"])
    for c in ("jarang", "sering", "terkonsentrasi"):
        assert asdict(spec[c]["params"]) == base and (spec[c]["hidden"], spec[c]["second"]) == (spec["dasar"]["hidden"], spec["dasar"]["second"])
    hard = spec["kasus_sulit"]["params"]
    assert hard.late_note_share == 2 * base["late_note_share"] and hard.evidence_noise == 1.5 * base["evidence_noise"]
    assert spec["idrg_tiruan"]["params"].grouper.long_vent_min_hours in (48, 60, 84)
    from engine.synth.world import build_world
    _, a = build_world(replace(spec["dasar"]["params"], scale=0.1))
    _, b = build_world(replace(hard, scale=0.1))
    same = [col for col in a.columns if not col.startswith("tarif_rs_")]
    pd.testing.assert_frame_equal(a[same], b[same])


def test_placebo_twin_is_the_world_without_any_manipulation(dev):
    twin, claims, key = dev["key_placebo_claims"], dev["claims"], dev["key_claims"]
    honest = key[~key.dimanipulasi].nomor_sep
    a = claims[claims.nomor_sep.isin(honest)].set_index("nomor_sep").sort_index()
    b = twin[twin.nomor_sep.isin(honest)].set_index("nomor_sep").sort_index()
    pd.testing.assert_frame_equal(a, b)
    manipulated = key[key.dimanipulasi].merge(twin, on="nomor_sep")
    assert (manipulated.tarif_ina_cbg == manipulated.tarif_jujur).all()


def test_honest_bulk_writers_batch_the_summary_but_not_procedure_reports(dev):
    k, docs = dev["key_claims"], dev["rme_documents"]
    d = docs.merge(k[["nomor_sep", "jebakan", "rme_versi"]], on="nomor_sep")
    trap = d[(d.jebakan == "tulis_massal_jujur") & (d.rme_versi == "jujur")]
    assert len(trap) > 0
    late = (trap.waktu_tulis - trap.waktu_layanan) > pd.Timedelta(hours=24)
    assert late[trap.jenis == "resume_medis"].mean() > 0.9
    assert late[trap.jenis == "laporan_tindakan"].mean() < 0.2
