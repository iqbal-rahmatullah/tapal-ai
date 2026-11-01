from datetime import datetime

import httpx
import pandas as pd
import pytest

from engine import ai2 as B
from engine.contracts import RmeReading


def record(rows):
    return pd.DataFrame([{"jenis": j, "waktu_layanan": pd.Timestamp(t), "penulis_peran": "perawat", "teks": x} for j, t, x in rows])


HONEST = record([
    ("laporan_tindakan", "2025-03-30 14:00", "30/3 14:00 intubasi ETT 8.0 -> vent PC."),
    ("cppt", "2025-03-30 14:30", "vent PC FiO2 50 PEEP 5. 30/3 14:30 ekstubasi ditunda, SBT gagal."),
    ("catatan_perawat", "2025-03-31 08:00", "31/3 08:00 mode diganti PS."),
    ("catatan_perawat", "2025-04-01 20:00", "Masih vent, PC."),
    ("catatan_perawat", "2025-04-02 20:37", "2/4 20:37 aff ETT, NRM 12 lpm."),
    ("resume_medis", "2025-04-03 10:00", "Selama perawatan ICU pasien menggunakan vent sejak 30/3 14:00 sampai 2/4 20:37."),
])


def reading(episodes, quotes=("intubasi ETT 8.0 -> vent PC", "aff ETT, NRM 12 lpm"), invasive="ya"):
    return RmeReading(kutipan=[{"fakta": "f", "teks": q} for q in quotes], alat_napas_tertinggi="ventilator_invasif" if invasive == "ya" else "nrm",
                      ventilasi_invasif=invasive, mode_ventilator="PC", episode=[{"mulai": a, "selesai": b} for a, b in episodes])


def test_times_in_every_written_format_are_parsed_by_code():
    ref = datetime(2025, 12, 31, 9, 0)
    assert B.parse_time("22 Juni 2025 pukul 10.23 WIB", ref) == datetime(2025, 6, 22, 10, 23)
    assert B.parse_time("04/11/2025 jam 21.23", ref) == datetime(2025, 11, 4, 21, 23)
    assert B.parse_time("30-03-2025 14:00", ref) == datetime(2025, 3, 30, 14, 0)
    assert B.parse_time("1/1 08:00", ref) == datetime(2026, 1, 1, 8, 0)
    assert B.parse_time("pukul 07.15", ref) == datetime(2025, 12, 31, 7, 15)


def test_honest_reading_is_accepted_and_hours_come_from_code():
    rec = B.assemble(HONEST)
    c = B.check_reading(reading([("30/3 14:00", "31/3 08:00"), ("31/3 08:00", "2/4 20:37")]), rec)
    assert c.accepted and c.quotes_ok == 2 and round(c.hours, 2) == 78.62 and len(c.episodes) == 1


def test_made_up_quote_cut_episode_and_later_ventilator_note_are_refused():
    rec = B.assemble(HONEST)
    assert not B.check_reading(reading([("30/3 14:00", "2/4 20:37")], quotes=("pasien diintubasi jam dua",)), rec).accepted
    cut = B.check_reading(reading([("30/3 14:00", "30/3 14:30")]), rec)
    assert not cut.accepted and any("tanpa bukti ekstubasi" in r for r in cut.reasons) and any("sesudah waktu selesai" in r for r in cut.reasons)


HEADER_TIMED = record([("cppt", "2026-01-02 10:30", "Dilakukan intubasi ETT no. 7,5 kedalaman 22 cm. Pasien dihubungkan ke ventilator mode SIMV."),
                       ("catatan_perawat", "2026-01-03 06:00", "Pasien terpasang ventilator mode SIMV, pH 7.21."),
                       ("cppt", "2026-01-07 21:30", "Dilakukan ekstubasi. Rencana turunkan ke nasal kanul."),
                       ("catatan_perawat", "2026-01-08 07:00", "O2 nasal kanul 3 lpm jam 07.00, SpO2 96%.")])


def test_untimed_notes_carry_their_time_in_the_header_for_llm_and_rules():
    rec = B.assemble(HEADER_TIMED)
    heads = [h for h, _, _, _ in rec.lines]
    assert heads[0].endswith("2026-01-02 10:30]") and heads[1].endswith("2026-01-03 06:00]") and heads[3] == "[catatan_perawat, perawat]"
    llm = B.check_reading(reading([("2026-01-02 10:30", "2026-01-07 21:30")], quotes=("Pasien dihubungkan ke ventilator mode SIMV", "Dilakukan ekstubasi")), rec)
    assert llm.accepted and llm.hours == 131
    rules = B.read_claim(HEADER_TIMED, {"96.72"}, 131, use_llm=False)
    assert rules.verdict == "mendukung" and rules.hours == 131


def test_death_on_the_ventilator_ends_the_episode():
    rec = B.assemble(record([("laporan_tindakan", "2025-02-24 09:00", "24/2 09:00 intubasi ETT 7.5 -> vent SIMV."),
                             ("catatan_perawat", "2025-02-25 14:11", "25/2 14:11 exitus, vent terpasang.")]))
    c = B.check_reading(reading([("24/2 09:00", "25/2 14:11")], quotes=("intubasi ETT 7.5 -> vent SIMV", "exitus, vent terpasang")), rec)
    assert c.accepted and round(c.hours, 2) == 29.18


def test_verdict_against_the_claim():
    rec = B.assemble(HONEST)
    r = reading([("30/3 14:00", "2/4 20:37")])
    c = B.check_reading(r, rec)
    assert B.judge(c, r, {"96.72"}, 100)[0] == "tidak_mendukung"
    assert B.judge(c, r, {"96.71"}, 78)[0] == "mendukung"
    none = reading([], quotes=("aff ETT, NRM 12 lpm",), invasive="tidak")
    assert B.judge(B.check_reading(none, rec), none, {"96.71"}, 40)[0] == "tidak_mendukung"
    assert B.judge(B.check_reading(none, rec), none, {"96.04"}, 0)[0] == "tidak_mendukung"
    assert B.judge(B.check_reading(none, rec), none, {"34.04"}, 0)[0] == "mendukung"


def test_rules_take_over_when_the_llm_is_down_and_say_so():
    def down(_):
        raise httpx.ConnectError("mati")
    r = B.read_claim(HONEST, {"96.71"}, 78, use_llm=True, call=down)
    assert r.source == "aturan" and r.verdict == "mendukung" and round(r.hours, 2) == 78.62 and "LLM tidak tersedia" in r.reasons[0]
    bad = B.read_claim(HONEST, {"96.71"}, 78, use_llm=True, call=lambda _: B.LlmCall(None, "keluaran LLM tidak sah terhadap skema"))
    assert bad.source == "llm_lokal" and bad.verdict == "tidak_dapat_disimpulkan"


def test_second_reader_and_vital_sheet_can_only_withhold_a_verdict():
    agree = B.read_claim(HONEST, {"96.71"}, 78, use_llm=False, second=lambda _: "ya", sheet_hours=70)
    assert agree.verdict == "mendukung" and agree.second_reader == "ya"
    differ = B.read_claim(HONEST, {"96.71"}, 78, use_llm=False, second=lambda _: "tidak")
    assert differ.verdict == "tidak_dapat_disimpulkan" and "model asersi" in differ.reasons[-1]
    assert B.read_claim(HONEST, {"96.71"}, 78, use_llm=False, sheet_hours=10).verdict == "tidak_dapat_disimpulkan"
    assert B.cross_check("tidak_dapat_disimpulkan", ["x"], "ya", None, "ya", 80) == ("tidak_dapat_disimpulkan", ["x"], ["bacaan"])
    assert B.cross_check("mendukung", [], "ya", 11.0, None, 0)[0] == "mendukung"
    held = B.read_claim(HONEST, {"96.71"}, 78, use_llm=False, sheet_hours=70, provenance="seluruh catatan ditulis dalam satu sesi")
    assert held.verdict == "tidak_dapat_disimpulkan" and held.held_by == ["asal_usul"] and "satu sesi" in held.reasons[-1]


def test_switch_and_cloud_models():
    assert B.read_claim(HONEST, {"96.71"}, 78, use_llm=False).source == "aturan"
    silent = B.read_claim(record([("cppt", "2025-03-30 14:00", "Pasien tenang, makan habis.")]), {"96.71"}, 40, use_llm=False)
    assert silent.verdict == "tidak_dapat_disimpulkan" and "tidak menemukan" in silent.reasons[-1]
    with pytest.raises(ValueError):
        B.call_ollama("teks", model="gpt-oss:20b-cloud")


def test_clone_and_bulk_writing_layers():
    from engine import ai2_fast as F
    pool = ["Pasien tampak tenang.", "Suction lendir kental.", "Posisi miring tiap dua jam.", "Urin output cukup.", "Balans cairan ketat.",
            "Cek analisa gas darah ulang."]
    picks = [(0, 1, 2), (3, 4, 5), (0, 3, 4), (1, 4, 5), (2, 3, 5), (0, 1, 2)]
    rows, rs = [], {}
    for i, pick in enumerate(picks):
        sep = f"SEP-{i}"
        rs[sep] = "RS-001"
        texts = [f"{pool[p]} Hari ke-{i + p}." for p in pick]
        for j, t in enumerate(texts):
            when = pd.Timestamp("2025-03-01") + pd.Timedelta(days=j)
            written = pd.Timestamp("2025-03-20 21:00") + pd.Timedelta(minutes=10 * j) if i == 1 else when + pd.Timedelta(minutes=30)
            rows.append({"nomor_sep": sep, "jenis": "catatan_perawat", "waktu_layanan": when, "waktu_tulis": written, "teks": t})
        rows.append({"nomor_sep": sep, "jenis": "catatan_perawat", "waktu_layanan": pd.Timestamp("2025-03-04"),
                     "waktu_tulis": pd.Timestamp("2025-03-20 21:40") if i == 1 else pd.Timestamp("2025-03-04 00:30"), "teks": "Catatan."})
    docs = pd.DataFrame(rows)
    clones = F.clone_scores(docs, pd.Series(rs))
    assert clones.kloning.tolist() == [True, False, False, False, False, True]
    trail = F.write_trail(docs, pd.Series({s: pd.Timestamp("2025-03-05") for s in rs}))
    assert trail.tulis_massal.tolist() == [False, True, False, False, False, False]


def test_provenance_holds_only_on_strong_signals():
    import numpy as np
    from engine import ai2_fast as F
    clones = pd.DataFrame({"kloning": [True, True, True], "pasangan_teratas": ["B", "A", "A"]}, index=["A", "B", "C"])
    trail = pd.DataFrame({"porsi_tulis_serentak": [0.5, 0.5, 1.0], "n_catatan": [6, 6, 6]}, index=["A", "B", "C"])
    hours = pd.date_range("2025-03-01", periods=4, freq="h")
    sheet = lambda spo2: pd.DataFrame({"waktu": hours, "spo2": spo2, "fio2": 40.0, "peep": 5.0, "rr_set": 14.0, "rr_total": np.nan})
    vitals = pd.concat([sheet([95, 96, 97, 98]).assign(nomor_sep="A"), sheet([95, 96, 97, 98]).assign(nomor_sep="B"),
                        sheet([90, 91, 92, 93]).assign(nomor_sep="C")])
    out = F.provenance(clones, trail, vitals)
    assert out.kloning_kuat.tolist() == [True, True, False] and out.tulis_serentak.tolist() == [False, False, True]
    assert out.alasan["C"] == "seluruh catatan ditulis dalam satu sesi" and out.alasan["A"].endswith("klaim B")


def test_late_key_documents_are_judged_against_each_hospitals_own_habit():
    from engine import ai2_fast as F
    seps = [f"S{i}" for i in range(80)]
    served = pd.Timestamp("2025-01-02 10:00")
    # Hospital A writes within the hour except S39 (300 hours late); hospital B always writes days late.
    late = [0.5 + i / 100 for i in range(39)] + [300.0] + [50.0 + 9 * i for i in range(40)]
    docs = pd.DataFrame({"nomor_sep": seps, "jenis": "laporan_tindakan", "waktu_layanan": served, "waktu_tulis": [served + pd.Timedelta(hours=h) for h in late]})
    windows = pd.DataFrame({"mulai": served - pd.Timedelta(hours=2), "selesai": served + pd.Timedelta(hours=2)}, index=seps)
    rs = pd.Series(["A"] * 40 + ["B"] * 40, index=seps)
    delays = F.key_document_delay(docs, windows)
    why = F.late_key_documents(delays, F.delay_scores(delays, rs, F.delay_baseline(delays, rs)))
    assert why["S39"].startswith("laporan tindakan ditulis 300 jam setelah layanan") and (why.drop("S39") == "").all()
    verdict, reasons, held = B.cross_check("mendukung", [], "ya", 50.0, None, None, late=why["S39"])
    assert verdict == "tidak_dapat_disimpulkan" and held == ["jejak_waktu"]


def test_quotes_get_one_retry_with_the_missing_quotes_named():
    docs = pd.DataFrame({"dokumen_id": ["d1"], "nomor_sep": ["S"], "jenis": ["cppt"], "waktu_layanan": [pd.Timestamp("2025-01-02 08:00")],
                         "waktu_tulis": [pd.Timestamp("2025-01-02 08:30")], "penulis_peran": ["dokter"], "teks": ["Pasien memakai nasal kanul 3 lpm, SpO2 96%."]})
    asked = []
    def call(text):
        asked.append(text)
        quote = "nasal kanul 3 lpm" if len(asked) > 1 else "kanul hidung 3 liter"
        return B.LlmCall(RmeReading(kutipan=[{"fakta": "alat", "teks": quote}], alat_napas_tertinggi="nasal_kanul", ventilasi_invasif="tidak",
                                    mode_ventilator="", episode=[]), None, 1000)
    r = B.read_claim(docs, {"96.71"}, 40.0, use_llm=True, call=call)
    assert len(asked) == 2 and "kanul hidung 3 liter" in asked[1] and r.quotes_verified == 1
    assert r.verdict == "tidak_mendukung" and r.reasons[0].startswith("dibaca ulang sekali")
