# Synthetic INA-CBG grouper on Data Sampel payment routes, where rules the data cannot show (some surgery codes, I69/I13/I12, CC/MCC, 34.04) are TARGETS F9 assumptions.
from dataclasses import dataclass, replace
from functools import cache
from pathlib import Path

import pandas as pd

from engine.contracts import CARDIAC_GROUPS_NOT_MOVING, MAJOR_SURGERY_CODES

TARIFF_TSV = Path(__file__).with_name("inacbg_tariff_permenkes_3_2023.tsv")
ROMAN = {1: "I", 2: "II", 3: "III"}

SURGERY_CODES = MAJOR_SURGERY_CODES
MEDICAL_GROUPS = {
    "J96": "J-4-11", "J18": "J-4-16", "J80": "J-4-21", "J90": "J-4-20",
    "I63": "G-4-14", "I61": "G-4-13", "I64": "G-4-15", "G93": "G-4-21",
    "I21": "I-4-10", "I50": "I-4-12", "A41": "A-4-10", "R57": "I-4-14", "S06": "G-4-25",
    "A16": "J-4-15", "E11": "E-4-10", "N18": "N-4-10", "I69": "G-4-15", "I13": "I-4-12", "I12": "N-4-10",
}
MCC = frozenset({"J96", "R57", "A41", "I46", "N17", "G93", "J80"})
CC = frozenset({"E87", "D64", "E88", "E11", "J18", "D63", "N18", "E83", "I50"})


@dataclass(frozen=True)
class GrouperConfig:
    long_vent_code: str = "96.72"
    long_vent_min_hours: int | None = None
    j120_triggers: frozenset = frozenset({"96.70", "96.71", "96.04", "34.04"})
    trach_codes: frozenset = frozenset({"31.1", "31.21", "31.29"})
    cardiac_not_moving: frozenset = CARDIAC_GROUPS_NOT_MOVING
    fallback_group: str = "J-4-21"


DEFAULT = GrouperConfig()
# iDRG mock in which the long-ventilation line moves to 72 hours by hour count and NIV/CPAP (93.90) becomes a J-1-20 trigger.
IDRG_MOCK = replace(DEFAULT, long_vent_min_hours=72, j120_triggers=DEFAULT.j120_triggers | {"93.90"})
VENT_CODES = frozenset({"96.70", "96.71", "96.72"})


def severity(secondary_dx3: list[str]) -> int:
    codes = set(secondary_dx3)
    return 3 if codes & MCC else 2 if codes & CC else 1


def group(dx3: str, procedures: set[str], secondary_dx3: list[str], ventilator_hour: int, cfg: GrouperConfig = DEFAULT) -> str:
    surgeries = [SURGERY_CODES[c] for c in procedures if c in SURGERY_CODES]
    surgery = next((g for g in surgeries if g in cfg.cardiac_not_moving), surgeries[0] if surgeries else None)
    if cfg.long_vent_min_hours is None:
        long_vent = cfg.long_vent_code in procedures
    else:
        long_vent = bool(procedures & VENT_CODES) and ventilator_hour >= cfg.long_vent_min_hours
    if surgery and (surgery in cfg.cardiac_not_moving or not long_vent):
        g = surgery
    elif long_vent:
        g = "J-1-01" if procedures & cfg.trach_codes else "J-1-02"
    elif procedures & cfg.j120_triggers:
        g = "J-1-20"
    else:
        g = MEDICAL_GROUPS.get(dx3, cfg.fallback_group)
    return f"{g}-{ROMAN[severity(secondary_dx3)]}"


@cache
def tariff_table() -> dict[tuple[str, str, str], tuple[int, int, int]]:
    t = pd.read_csv(TARIFF_TSV, sep="\t", dtype=str)
    t = t[t.jenis == "RI"]
    num = lambda s: int(s.replace(".", ""))
    return {(r.regional, r.kelas_rs, r.kode): (num(r.tarif_kelas1), num(r.tarif_kelas2), num(r.tarif_kelas3))
            for r in t.itertuples()}


@cache
def has_tariff(kelas_rs: str, group: str) -> bool:
    return any(key[1].startswith(f"KELAS {kelas_rs} ") and key[2].startswith(group) for key in tariff_table())


def tariff(regional: int, kelas_rs: str, kepemilikan: str, cbg: str, kelas_rawat: int) -> int:
    label = f"KELAS {kelas_rs} {'PEMERINTAH' if kepemilikan == 'pemerintah' else 'SWASTA'}"
    return tariff_table()[(str(regional), label, cbg)][kelas_rawat - 1]
