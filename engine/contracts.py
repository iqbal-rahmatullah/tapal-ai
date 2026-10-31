# Field names follow E-Klaim set_claim_data as in halimkun/laravel-eklaim-api v1.0.6, not yet the official guide (adapter if they differ).

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, ValidationInfo, field_validator, model_validator

from engine import MODEL_VERSION

VENTILATION_CODES = frozenset({"96.70", "96.71", "96.72"})
TRIGGER_CODES = VENTILATION_CODES | {"96.04"}
LINE_GROUPS = frozenset({"J-1-20", "J-1-02", "J-1-01"})
NEONATAL_PREFIX = "P-8"

# Data Sampel-based proxy for an ICU stay, not a definitive marker; the other ~54% of medical line claims stay visible to AI 2 and the audit agent.
TARGET_DIAGNOSES: dict[str, tuple[str, ...]] = {
    "gagal napas dan pneumonia": ("J96", "J18", "J80", "J90"),
    "stroke dan perdarahan otak": ("I63", "I61", "I64", "G93"),
    "jantung akut": ("I21", "I50"),
    "sepsis dan syok": ("A41", "R57"),
    "cedera kepala": ("S06",),
}
TARGET_DIAGNOSIS_CODES = frozenset(c for codes in TARGET_DIAGNOSES.values() for c in codes)

# Option A, reported next to T22 only to show how much the population choice moves the AUC.
TARGET_DIAGNOSES_BROAD = (
    "J96", "J18", "I63", "I61", "N18", "I21", "E11", "S06", "A16", "J80",
    "I50", "I69", "I64", "A41", "I13", "G93", "I12", "J90", "R57",
)

# 80% of surgical ventilation-line claims in Data Sampel; the generator draws surgical patients only from these.
MAJOR_SURGERY_GROUPS: dict[str, str] = {
    "G-1-10": "Kraniotomi",
    "K-1-20": "Prosedur intestinal kompleks",
    "G-1-11": "Prosedur ventricular shunt",
    "N-1-12": "Membuat baru, merevisi, dan memindahkan alat dialisis",
    "K-1-40": "Prosedur sistem pencernaan lain-lain",
    "I-1-07": "Prosedur bypass koroner tanpa kateterisasi jantung",
    "I-1-04": "Prosedur katup jantung tanpa kateterisasi jantung",
    "M-1-03": "Prosedur fusi tulang belakang",
    "I-1-06": "Prosedur kardiotorasik lain",
}

# Checked alongside the group, because a surgical patient moved to J-1-02 by 96.72 keeps this code (one per group, TARGETS v2 F9).
MAJOR_SURGERY_CODES: dict[str, str] = {
    "36.13": "I-1-07", "35.24": "I-1-04", "34.02": "I-1-06", "01.24": "G-1-10", "02.34": "G-1-11",
    "46.20": "K-1-20", "54.11": "K-1-40", "38.95": "N-1-12", "81.05": "M-1-03",
}

# They stay put past 96 hours in Data Sampel; G-1-01 also did but with under 5 claims, so it is treated as chance (F9).
CARDIAC_GROUPS_NOT_MOVING = frozenset({"I-1-07", "I-1-04"})

DischargeStatus = Literal[1, 2, 3, 4, 5]  # 1 doctor's approval, 2 referred, 3 own request, 4 died, 5 other
Device = Literal["ventilator_invasif", "niv", "hfnc", "nrm", "nasal_kanul", "udara_ruang", "tidak_jelas"]
CheckStatus = Literal["lolos_cepat", "periksa_manual", "didukung_rme"]
RmeVerdict = Literal["mendukung", "tidak_mendukung", "tidak_dapat_disimpulkan"]
Engine = Literal["Kode", "AI 1", "AI 2", "AI 3", "AI 4", "Statistik", "LLM"]
DecisionKind = Literal["setujui", "ajukan_audit", "minta_klarifikasi"]

_ICD10 = r"^[A-Z][0-9]{2}(\.[0-9A-Z]{1,2})?$"
_ICD9CM = r"^[0-9]{2}(\.[0-9]{1,2})?$"


def split_codes(value: str) -> list[str]:
    return [c for c in value.split("#") if c]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TarifRs(_Strict):
    prosedur_non_bedah: int = Field(0, ge=0)
    prosedur_bedah: int = Field(0, ge=0)
    konsultasi: int = Field(0, ge=0)
    tenaga_ahli: int = Field(0, ge=0)
    keperawatan: int = Field(0, ge=0)
    penunjang: int = Field(0, ge=0)
    radiologi: int = Field(0, ge=0)
    laboratorium: int = Field(0, ge=0)
    pelayanan_darah: int = Field(0, ge=0)
    rehabilitasi: int = Field(0, ge=0)
    kamar: int = Field(0, ge=0)
    rawat_intensif: int = Field(0, ge=0)
    obat: int = Field(0, ge=0)
    obat_kronis: int = Field(0, ge=0)
    obat_kemoterapi: int = Field(0, ge=0)
    alkes: int = Field(0, ge=0)
    bmhp: int = Field(0, ge=0)
    sewa_alat: int = Field(0, ge=0)


class Ventilator(_Strict):
    use_ind: Literal[0, 1]
    start_dttm: datetime | None = None
    stop_dttm: datetime | None = None

    @field_validator("stop_dttm")
    @classmethod
    def _after_start(cls, v: datetime | None, info: ValidationInfo) -> datetime | None:
        start = info.data.get("start_dttm")
        if v is not None and start is not None and v < start:
            raise ValueError("stop_dttm lebih awal dari start_dttm")
        return v


class Claim(_Strict):
    nomor_sep: str = Field(min_length=1)
    kode_rs: str = Field(min_length=1)
    umur: int
    jenis_kelamin: Literal["L", "P"]
    jenis_rawat: Literal[1, 2, 3] = 1
    kelas_rawat: Literal[1, 2, 3]
    cara_masuk: Literal["gp", "hosp-trans", "mp", "outp", "inp", "emd", "born", "nursing", "psych", "rehab", "other"] = "gp"
    tgl_masuk: datetime
    tgl_pulang: datetime
    diagnosa: str
    procedure: str = ""
    icu_indikator: Literal[0, 1] = 0
    icu_los: int = Field(0, ge=0)
    ventilator_hour: int = Field(0, ge=0)
    ventilator: Ventilator | None = None
    discharge_status: DischargeStatus
    tarif_rs: TarifRs

    @field_validator("umur")
    @classmethod
    def _age(cls, v: int) -> int:
        if v < 0:
            raise ValueError("umur harus ≥ 0")
        return v

    @field_validator("tgl_pulang")
    @classmethod
    def _discharge_after_admission(cls, v: datetime, info: ValidationInfo) -> datetime:
        if "tgl_masuk" in info.data and v < info.data["tgl_masuk"]:
            raise ValueError("tgl_pulang lebih awal dari tgl_masuk")
        return v

    @field_validator("diagnosa")
    @classmethod
    def _diagnoses(cls, v: str) -> str:
        codes = split_codes(v)
        if not codes:
            raise ValueError("diagnosa wajib diisi")
        bad = [c for c in codes if not _matches(_ICD10, c)]
        if bad:
            raise ValueError(f"kode diagnosa tidak sah: {', '.join(bad)}")
        return v

    @field_validator("procedure")
    @classmethod
    def _procedures(cls, v: str) -> str:
        bad = [c for c in split_codes(v) if not _matches(_ICD9CM, c)]
        if bad:
            raise ValueError(f"kode prosedur tidak sah: {', '.join(bad)}")
        return v

    @field_validator("ventilator_hour")
    @classmethod
    def _hours_for_long_ventilation(cls, v: int, info: ValidationInfo) -> int:
        if v == 0 and "96.72" in split_codes(info.data.get("procedure", "")):
            raise ValueError("ventilator_hour wajib diisi bila prosedur 96.72")
        return v

    @property
    def diagnoses(self) -> list[str]:
        return split_codes(self.diagnosa)

    @property
    def procedures(self) -> list[str]:
        return split_codes(self.procedure)

    @property
    def primary_dx3(self) -> str:
        return self.diagnoses[0][:3]


class GroupedClaim(Claim):
    cbg: str = Field(pattern=r"^[A-Z]-[0-9]-[0-9]{2}-(0|I|II|III)$")
    tarif_ina_cbg: int = Field(ge=0)

    @property
    def group(self) -> str:
        return self.cbg[:6]


def in_line_population(claim: GroupedClaim) -> bool:
    if claim.cbg.startswith(NEONATAL_PREFIX):
        return False
    return claim.group in LINE_GROUPS or bool(TRIGGER_CODES & set(claim.procedures))


def is_eligible_fictitious(claim: GroupedClaim) -> bool:
    # Only the primary diagnosis counts, so a fake secondary diagnosis (e.g. A41.9) never changes membership.
    return (
        claim.icu_indikator == 1
        and claim.primary_dx3 in TARGET_DIAGNOSIS_CODES
        and claim.group not in MAJOR_SURGERY_GROUPS
        and not set(claim.procedures) & set(MAJOR_SURGERY_CODES)
        and not claim.cbg.startswith(NEONATAL_PREFIX)
    )


def is_eligible_prolonged(claim: GroupedClaim) -> bool:
    return (
        bool({"96.71", "96.72"} & set(claim.procedures))
        and claim.group not in CARDIAC_GROUPS_NOT_MOVING
        and not claim.cbg.startswith(NEONATAL_PREFIX)
    )


class Hospital(_Strict):
    kode_rs: str = Field(min_length=1)
    kelas_rs: Literal["A", "B", "C", "D"]
    kepemilikan: Literal["pemerintah", "swasta"]
    regional: Literal[1, 2, 3, 4, 5]


class RmeDocument(_Strict):
    dokumen_id: str = Field(min_length=1)
    nomor_sep: str = Field(min_length=1)
    jenis: Literal["cppt", "observasi_icu", "catatan_perawat", "laporan_tindakan", "resume_medis"]
    waktu_layanan: datetime
    waktu_tulis: datetime  # server write time (FHIR meta.lastUpdated), not typed in by the hospital
    penulis_peran: Literal["dokter", "perawat"]
    teks: str = Field(min_length=1)

    @field_validator("waktu_tulis")
    @classmethod
    def _written_after_service(cls, v: datetime, info: ValidationInfo) -> datetime:
        if "waktu_layanan" in info.data and v < info.data["waktu_layanan"]:
            raise ValueError("waktu_tulis lebih awal dari waktu_layanan")
        return v


class VitalSign(_Strict):
    nomor_sep: str = Field(min_length=1)
    waktu: datetime
    alat: Device
    spo2: float | None = Field(None, ge=0, le=100)
    fio2: float | None = Field(None, ge=21, le=100)
    peep: float | None = Field(None, ge=0, le=30)
    rr_set: float | None = Field(None, ge=0, le=60)
    rr_total: float | None = Field(None, ge=0, le=80)


class Quote(_Strict):
    fakta: str
    teks: str


class Episode(_Strict):
    mulai: str  # copied verbatim from the record; code parses the date
    selesai: str


class RmeReading(_Strict):  # its JSON schema is sent to Ollama as `format`
    kutipan: list[Quote]
    alat_napas_tertinggi: Device
    ventilasi_invasif: Literal["ya", "tidak", "tidak_jelas"]
    mode_ventilator: str
    episode: list[Episode]


class Step(_Strict):
    nama: str
    mesin: Engine
    waktu_ms: int | None = Field(None, ge=0)


class RmeResult(_Strict):
    status: Literal["diproses", "selesai"]
    hasil: str | None = None
    verdict: RmeVerdict | None = None
    sumber: Literal["llm_lokal", "aturan"] | None = None
    kutipan_terverifikasi: int | None = Field(None, ge=0)

    @model_validator(mode="after")
    def _complete(self) -> "RmeResult":
        if self.status == "diproses" and not self.hasil:
            raise ValueError("rme diproses wajib membawa tautan hasil")
        if self.status == "selesai" and (self.verdict is None or self.sumber is None):
            raise ValueError("rme selesai wajib membawa verdict dan sumber")
        return self


class CheckResponse(_Strict):
    nomor_sep: str
    status: CheckStatus
    status_sebelumnya: CheckStatus | None = None
    peluang_didukung_bukti: float = Field(ge=0, le=1)
    alasan: list[str]
    selisih_tarif_dipertaruhkan: int
    rme: RmeResult
    versi_model: str = MODEL_VERSION
    waktu_proses_ms: int = Field(ge=0)
    langkah: list[Step] = []


class ValidationIssue(_Strict):
    kolom: str
    pesan: str
    nilai_diterima: Any = None


def validation_issues(error: ValidationError) -> list[ValidationIssue]:
    return [
        ValidationIssue(
            kolom=".".join(str(p) for p in e["loc"]) or "klaim",
            pesan=e["msg"].removeprefix("Value error, "),
            nilai_diterima=e.get("input"),
        )
        for e in error.errors()
    ]


class Decision(_Strict):
    waktu: datetime
    nomor_sep: str = Field(min_length=1)
    kode_rs: str = Field(min_length=1)
    keputusan: DecisionKind
    catatan: str = Field(min_length=1)
    peran: Literal["verifikator", "kepala_cabang"]
    versi_model: str = MODEL_VERSION
    bukti: dict[str, Any] = {}

    @field_validator("waktu")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("waktu wajib berzona waktu")
        return v.astimezone(timezone.utc)


GENESIS = "0" * 64

DECISION_LOG_DDL = """
CREATE TABLE IF NOT EXISTS jejak_keputusan (
    id INTEGER PRIMARY KEY,
    waktu TEXT NOT NULL,
    nomor_sep TEXT NOT NULL,
    kode_rs TEXT NOT NULL,
    keputusan TEXT NOT NULL CHECK (keputusan IN ('setujui', 'ajukan_audit', 'minta_klarifikasi')),
    catatan TEXT NOT NULL CHECK (length(catatan) > 0),
    peran TEXT NOT NULL,
    versi_model TEXT NOT NULL,
    bukti TEXT NOT NULL,
    sidik_sebelum TEXT NOT NULL,
    sidik TEXT NOT NULL UNIQUE
);
CREATE TRIGGER IF NOT EXISTS jejak_keputusan_tanpa_ubah BEFORE UPDATE ON jejak_keputusan
BEGIN SELECT RAISE(ABORT, 'jejak keputusan bersifat tambah-saja'); END;
CREATE TRIGGER IF NOT EXISTS jejak_keputusan_tanpa_hapus BEFORE DELETE ON jejak_keputusan
BEGIN SELECT RAISE(ABORT, 'jejak keputusan bersifat tambah-saja'); END;
"""


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def fingerprint(decision: Decision, previous: str) -> str:
    payload = {**decision.model_dump(mode="json"), "sidik_sebelum": previous}
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()


def open_decision_log(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, autocommit=True, timeout=5.0)
    conn.execute("PRAGMA recursive_triggers = ON")  # without it, INSERT OR REPLACE bypasses the DELETE trigger
    conn.executescript(DECISION_LOG_DDL)
    return conn


def _matches(pattern: str, value: str) -> bool:
    return re.fullmatch(pattern, value) is not None
