import sqlite3
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from engine.contracts import (
    CARDIAC_GROUPS_NOT_MOVING,
    GENESIS,
    MAJOR_SURGERY_GROUPS,
    TARGET_DIAGNOSES_BROAD,
    TARGET_DIAGNOSIS_CODES,
    TRIGGER_CODES,
    CheckResponse,
    Claim,
    Decision,
    GroupedClaim,
    RmeReading,
    RmeResult,
    fingerprint,
    in_line_population,
    is_eligible_fictitious,
    is_eligible_prolonged,
    append_decision,
    open_decision_log,
    read_decisions,
    verify_chain,
    validation_issues,
)

CONTOH_1 = {
    "nomor_sep": "SIN-031-26-00018",
    "kode_rs": "RS-031",
    "umur": 54,
    "jenis_kelamin": "L",
    "kelas_rawat": 3,
    "tgl_masuk": "2026-01-02T08:00:00+07:00",
    "tgl_pulang": "2026-01-13T10:00:00+07:00",
    "diagnosa": "J96.0#J18.9",
    "procedure": "96.72#96.04#89.65",
    "icu_indikator": 1,
    "icu_los": 7,
    "ventilator_hour": 131,
    "ventilator": {"use_ind": 1, "start_dttm": "2026-01-02T10:30:00+07:00", "stop_dttm": "2026-01-07T21:30:00+07:00"},
    "discharge_status": 1,
    "tarif_rs": {"sewa_alat": 7860000, "rawat_intensif": 18900000, "laboratorium": 2140000},
}


def grouped(cbg, **changes):
    return GroupedClaim(**{**CONTOH_1, "cbg": cbg, "tarif_ina_cbg": 1, **changes})


def test_contoh_1_is_valid():
    c = Claim(**CONTOH_1)
    assert c.diagnoses == ["J96.0", "J18.9"]
    assert c.procedures == ["96.72", "96.04", "89.65"]
    assert c.primary_dx3 == "J96"


def test_422_matches_layar_4_design():
    bad = {**CONTOH_1, "umur": -3, "procedure": "96.72", "ventilator_hour": 0, "tgl_pulang": "2026-01-01T08:00:00+07:00"}
    with pytest.raises(ValidationError) as e:
        Claim(**bad)
    issues = {i.kolom: i for i in validation_issues(e.value)}
    assert set(issues) == {"umur", "tgl_pulang", "ventilator_hour"}
    assert issues["umur"].pesan == "umur harus ≥ 0" and issues["umur"].nilai_diterima == -3
    assert issues["ventilator_hour"].pesan == "ventilator_hour wajib diisi bila prosedur 96.72"
    assert issues["tgl_pulang"].pesan == "tgl_pulang lebih awal dari tgl_masuk"


def test_unknown_field_and_bad_codes_are_rejected():
    with pytest.raises(ValidationError) as e:
        Claim(**{**CONTOH_1, "kolom_asing": 1, "diagnosa": "J96.0#xyz"})
    assert {i.kolom for i in validation_issues(e.value)} == {"kolom_asing", "diagnosa"}


def test_populations_follow_targets_v2():
    medical = grouped("J-1-20-II", procedure="96.71", ventilator_hour=60)
    intubation_only = grouped("J-1-20-II", procedure="96.04", ventilator_hour=0)
    craniotomy = grouped("G-1-10-I", procedure="96.71#01.24", ventilator_hour=40)
    bypass = grouped("I-1-07-I", procedure="96.72#36.10", ventilator_hour=110)
    neonate = grouped("P-8-07-I")
    diabetes = grouped("J-1-20-II", diagnosa="E11.9", procedure="96.71", ventilator_hour=30)
    craniotomy_moved = grouped("J-1-02-II", diagnosa="I61.9", procedure="96.72#01.24", ventilator_hour=120)
    fake_sepsis = grouped("J-1-20-III", diagnosa="J96.0#A41.9", procedure="96.71", ventilator_hour=60)

    assert all(in_line_population(c) for c in (medical, intubation_only, craniotomy, bypass))
    assert not in_line_population(neonate)
    assert is_eligible_fictitious(medical) and not is_eligible_fictitious(craniotomy)
    assert not is_eligible_fictitious(diabetes)
    assert not is_eligible_fictitious(craniotomy_moved)
    assert is_eligible_fictitious(fake_sepsis) == is_eligible_fictitious(medical)
    assert is_eligible_prolonged(craniotomy) and not is_eligible_prolonged(bypass)
    assert not is_eligible_prolonged(intubation_only)


def test_lists_from_data_sampel():
    assert len(TARGET_DIAGNOSIS_CODES) == 13
    assert TARGET_DIAGNOSIS_CODES <= set(TARGET_DIAGNOSES_BROAD) and len(TARGET_DIAGNOSES_BROAD) == 19
    assert CARDIAC_GROUPS_NOT_MOVING <= set(MAJOR_SURGERY_GROUPS) and "G-1-01" not in MAJOR_SURGERY_GROUPS
    assert TRIGGER_CODES == {"96.70", "96.71", "96.72", "96.04"}


def test_llm_schema_is_closed():
    schema = RmeReading.model_json_schema()
    assert schema["additionalProperties"] is False
    assert len(schema["properties"]["alat_napas_tertinggi"]["enum"]) == 7


def test_rme_result_must_be_complete():
    with pytest.raises(ValidationError):
        RmeResult(status="diproses")
    with pytest.raises(ValidationError):
        RmeResult(status="selesai", verdict="mendukung")
    assert RmeResult(status="diproses", hasil="/api/v1/klaim/X/rme").hasil


def test_response_carries_model_version():
    r = CheckResponse(
        nomor_sep="X", status="lolos_cepat", peluang_didukung_bukti=0.94, alasan=[],
        selisih_tarif_dipertaruhkan=0, rme=RmeResult(status="diproses", hasil="/x"), waktu_proses_ms=38,
    )
    assert r.versi_model == "tapal-1.0"


def decision(sep, waktu, **changes):
    return Decision(**{"waktu": waktu, "peran": "verifikator", "objek_jenis": "klaim", "objek_id": sep, "keputusan": "ajukan_audit",
                       "catatan": "RME tidak mendukung kode 96.71", "dasar_ai": {"mesin": ["AI 1", "AI 2"], "sumber_bacaan": "llm_lokal"},
                       "bukti": {"peluang": 0.04}, **changes})


def test_decision_log_is_append_only_and_chained(tmp_path):
    conn = open_decision_log(tmp_path / "jejak.db")
    first = decision("SIN-092-25-00412", datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc))
    second = decision("SIN-092-25-00519", datetime(2026, 1, 5, 9, 5, tzinfo=timezone.utc))
    append_decision(conn, first)
    append_decision(conn, second)

    rows = conn.execute("SELECT sidik_sebelum, sidik FROM jejak_keputusan ORDER BY id").fetchall()
    assert rows[0] == (GENESIS, fingerprint(first, GENESIS))
    assert rows[1] == (rows[0][1], fingerprint(second, rows[0][1]))

    for sql in (
        "UPDATE jejak_keputusan SET catatan = 'diubah' WHERE id = 1",
        "DELETE FROM jejak_keputusan WHERE id = 1",
        "INSERT OR REPLACE INTO jejak_keputusan (id, waktu, peran, objek_jenis, objek_id, keputusan, catatan, dasar_ai, versi_model, bukti,"
        " sidik_sebelum, sidik) VALUES (1, 'x', 'verifikator', 'klaim', 'x', 'setujui', 'x', '{}', 'x', '{}', 'x', 'x')",
    ):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(sql)
    assert conn.execute("SELECT count(*) FROM jejak_keputusan").fetchone()[0] == 2
    assert verify_chain(read_decisions(conn)) is None


def test_correction_is_a_new_row_and_tampering_is_detected(tmp_path):
    conn = open_decision_log(tmp_path / "jejak.db")
    t = datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc)
    append_decision(conn, decision("SIN-092-25-00412", t))
    rid, _ = append_decision(conn, decision("SIN-092-25-00412", t, keputusan="koreksi", koreksi_untuk=1, catatan="menambah kutipan"))
    assert rid == 2
    with pytest.raises(ValueError):
        append_decision(conn, decision("SIN-092-25-00412", t, keputusan="koreksi", koreksi_untuk=99))
    rows = read_decisions(conn)
    assert [r["catatan"] for r in rows] == ["RME tidak mendukung kode 96.71", "menambah kutipan"]
    rows[0]["catatan"] = "diubah diam-diam"
    assert verify_chain(rows) == 1


def test_decision_rules():
    t = datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc)
    with pytest.raises(ValidationError):
        decision("X", datetime(2026, 1, 5, 9, 0))
    with pytest.raises(ValidationError):
        decision("X", t, catatan=" ")
    with pytest.raises(ValidationError):
        decision("X", t, keputusan="koreksi")
    assert decision("Laporan Des 2025", t, objek_jenis="laporan", keputusan="setujui_laporan", catatan="", peran="kepala_cabang")
