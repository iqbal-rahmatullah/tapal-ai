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
    canonical_json,
    fingerprint,
    in_line_population,
    is_eligible_fictitious,
    is_eligible_prolonged,
    open_decision_log,
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

    assert all(in_line_population(c) for c in (medical, intubation_only, craniotomy, bypass))
    assert not in_line_population(neonate)
    assert is_eligible_fictitious(medical) and not is_eligible_fictitious(craniotomy)
    assert not is_eligible_fictitious(diabetes)
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


def decision(sep, waktu):
    return Decision(waktu=waktu, nomor_sep=sep, kode_rs="RS-092", keputusan="ajukan_audit",
                    catatan="RME tidak mendukung kode 96.71", peran="verifikator", bukti={"peluang": 0.04})


def append(conn, d):
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT sidik FROM jejak_keputusan ORDER BY id DESC LIMIT 1").fetchone()
        previous = row[0] if row else GENESIS
        rec = d.model_dump(mode="json")
        conn.execute(
            "INSERT INTO jejak_keputusan (waktu, nomor_sep, kode_rs, keputusan, catatan, peran, versi_model, bukti, sidik_sebelum, sidik)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (rec["waktu"], rec["nomor_sep"], rec["kode_rs"], rec["keputusan"], rec["catatan"], rec["peran"],
             rec["versi_model"], canonical_json(rec["bukti"]), previous, fingerprint(d, previous)),
        )
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def test_decision_log_is_append_only_and_chained(tmp_path):
    conn = open_decision_log(tmp_path / "jejak.db")
    first = decision("SIN-092-25-00412", datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc))
    second = decision("SIN-092-25-00519", datetime(2026, 1, 5, 9, 5, tzinfo=timezone.utc))
    append(conn, first)
    append(conn, second)

    rows = conn.execute("SELECT sidik_sebelum, sidik FROM jejak_keputusan ORDER BY id").fetchall()
    assert rows[0] == (GENESIS, fingerprint(first, GENESIS))
    assert rows[1] == (rows[0][1], fingerprint(second, rows[0][1]))

    for sql in (
        "UPDATE jejak_keputusan SET catatan = 'diubah' WHERE id = 1",
        "DELETE FROM jejak_keputusan WHERE id = 1",
        "INSERT OR REPLACE INTO jejak_keputusan (id, waktu, nomor_sep, kode_rs, keputusan, catatan, peran, versi_model, bukti, sidik_sebelum, sidik)"
        " VALUES (1, 'x', 'x', 'x', 'setujui', 'x', 'verifikator', 'x', '{}', 'x', 'x')",
    ):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(sql)
    assert conn.execute("SELECT count(*) FROM jejak_keputusan").fetchone()[0] == 2


def test_decision_time_needs_timezone():
    with pytest.raises(ValidationError):
        decision("X", datetime(2026, 1, 5, 9, 0))
