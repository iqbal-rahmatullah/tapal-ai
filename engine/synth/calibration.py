# Runs locally on Data Sampel and keeps only counts and shares, with cells under MIN_CELL suppressed.
import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from engine.contracts import LINE_GROUPS, MAJOR_SURGERY_GROUPS, TARGET_DIAGNOSIS_CODES, TRIGGER_CODES

MIN_CELL = 5
DEFAULT_DATA = Path.home() / "Downloads/2025/Data Sampel Reguler Edisi 2025/data"
DEFAULT_OUT = Path(__file__).resolve().parents[2] / "data/calibration/data_sampel.json"
QUANTILES = [0.1, 0.25, 0.5, 0.75, 0.9]


def dotted(code: str) -> str:
    code = code.strip()
    return f"{code[:2]}.{code[2:]}" if len(code) > 2 and "." not in code else code


def count(n) -> int | None:
    n = int(n)
    return n if n >= MIN_CELL else None


def counts(series: pd.Series, top: int | None = None) -> dict:
    vc = series.value_counts()
    if top:
        vc = vc.head(top)
    return {str(k): int(v) for k, v in vc.items() if v >= MIN_CELL}


def shares(series: pd.Series) -> dict:
    vc = series.value_counts()
    vc = vc[vc >= MIN_CELL]
    return {str(k): round(float(v / vc.sum()), 4) for k, v in vc.items()}


def quantiles(series: pd.Series) -> dict | None:
    s = series.dropna()
    if len(s) < MIN_CELL:
        return None
    return {str(q): round(float(s.quantile(q)), 2) for q in QUANTILES}


def histogram(series: pd.Series, top: int = 30) -> list[float]:
    s = series.dropna().clip(upper=top).astype(int)
    h = s.value_counts().reindex(range(top + 1), fill_value=0)
    return [round(float(x), 4) for x in (h / h.sum())]


def code_shares(df: pd.DataFrame, top: int = 30) -> dict:
    c = Counter(x for codes in df.kode for x in codes if x not in TRIGGER_CODES)
    return {k: round(n / len(df), 4) for k, n in c.most_common(top) if n >= MIN_CELL}


def load(data_dir: Path) -> pd.DataFrame:
    cols = ["FKL02", "FKL03", "FKL04", "FKL07", "FKL09", "FKL10", "FKL13", "FKL14", "FKL17A",
            "FKL19", "FKL23", "FKL30", "FKL31", "PSTV01"]
    f = pd.read_stata(data_dir / "202403_fkrtl.dta", columns=cols)
    ri = f[f.FKL10 == "RITL"].copy()
    peserta = (pd.read_stata(data_dir / "2015202401_kepesertaan.dta", columns=["PSTV01", "PSTV03", "PSTV05"])
               .drop_duplicates("PSTV01"))
    ri = ri.merge(peserta, on="PSTV01", how="left")
    dx2 = pd.read_stata(data_dir / "202405_diagnosissekunder.dta", columns=["FKL02", "FKL24A"])
    ri["n_dx2"] = ri.FKL02.map(dx2.FKL02.value_counts()).fillna(0).astype(int)
    ri["umur"] = (ri.FKL03 - ri.PSTV03).dt.days / 365.25
    ri["los"] = (ri.FKL04 - ri.FKL03).dt.days
    ri["kode"] = ri.FKL30.fillna("").astype(str).str.split(";").apply(
        lambda xs: frozenset(dotted(x.split(" - ")[0]) for x in xs if x.strip()))
    ri["g"] = ri.FKL19.astype(str).str[:6]
    ri["sev"] = ri.FKL23.astype(str).str.extract(r"keparahan (\d)")[0]
    ri["meninggal"] = ri.FKL14.astype(str) == "Meninggal"
    ri["dx3"] = ri.FKL17A.astype(str)
    tipe = ri.FKL09.astype(str)
    huruf = tipe.str.extract(r"(?:Kelas|Type) ([ABCD])$")[0]
    swasta = tipe.str.startswith("RS Swasta") | ri.FKL07.astype(str).isin(["Swasta", "BUMN"])
    ri["kelas_rs"] = huruf.where(tipe.str.match(r"RS (Kelas|Swasta)"))
    ri["kepemilikan"] = np.where(swasta, "swasta", "pemerintah")
    ri["regional"] = ri.FKL31.astype(str).str[-1]
    return ri, dx2


def extract(data_dir: Path) -> dict:
    ri, dx2 = load(data_dir)
    neonatal = ri.g.str.startswith("P-8")
    has_vent = ri.kode.apply(lambda c: bool(c & {"96.70", "96.71", "96.72"}))
    trigger = ri.kode.apply(lambda c: bool(c & TRIGGER_CODES))
    line = ~neonatal & (ri.g.isin(LINE_GROUPS) | trigger)
    pop = ri[line].copy()
    pop["jalur"] = np.select([pop.g.isin(LINE_GROUPS), pop.g.isin(MAJOR_SURGERY_GROUPS)], ["medis", "operasi"], "lain")
    v = pop[has_vent[line]]
    c71 = v.kode.apply(lambda c: "96.71" in c)
    c72 = v.kode.apply(lambda c: "96.72" in c)

    medis_v = v[v.jalur == "medis"]
    target = ri.dx3.isin(TARGET_DIAGNOSIS_CODES)
    no_proc = ri.kode.apply(len) == 0
    medical_groups = {}
    for dx in sorted(set(TARGET_DIAGNOSIS_CODES) | set(medis_v.dx3.value_counts().head(12).index)):
        s = ri[(ri.dx3 == dx) & no_proc & ri.g.str.match(r"^[A-Z]-4-")]
        if len(s) < MIN_CELL:
            continue
        top = s.g.value_counts()
        medical_groups[dx] = {"group": top.index[0], "share": round(float(top.iloc[0] / len(s)), 3),
                              "n": count(len(s)), "severity": shares(s[s.g == top.index[0]].sev)}

    surgical = {}
    for grp in MAJOR_SURGERY_GROUPS:
        s = pop[pop.g == grp]
        sv = s[s.kode.apply(lambda c: bool(c & {"96.71", "96.72"}))]
        procs = Counter(x for c in s.kode for x in c if x not in TRIGGER_CODES)
        surgical[grp] = {
            "n_line": count(len(s)),
            "share_9672_among_vent": round(float(sv.kode.apply(lambda c: "96.72" in c).mean()), 3) if len(sv) >= MIN_CELL else None,
            "top_procedures": {k: n for k, n in procs.most_common(6) if n >= MIN_CELL},
        }
    surgical_all = ri[ri.g.isin(MAJOR_SURGERY_GROUPS) & ~neonatal]
    surg_vent_share = {g: round(float(has_vent[surgical_all.index][surgical_all.g == g].mean()), 3)
                       for g in MAJOR_SURGERY_GROUPS if (surgical_all.g == g).sum() >= MIN_CELL}

    nonvent_target = ri[target & ~neonatal & ~trigger & ri.g.str.match(r"^[A-Z]-4-")]
    intub_only = pop[pop.kode.apply(lambda c: "96.04" in c and not (c & {"96.70", "96.71", "96.72"}))]
    vent_ids = set(v.FKL02)
    dx2_vent = dx2[dx2.FKL02.isin(vent_ids)].FKL24A.astype(str)
    dx2_nonvent = dx2[dx2.FKL02.isin(set(nonvent_target.FKL02))].FKL24A.astype(str)
    sev_by_ndx2 = {str(k): shares(g.sev) for k, g in v.assign(b=v.n_dx2.clip(upper=4)).groupby("b")}

    return {
        "sumber": "Data Sampel BPJS Reguler Edisi 2025 (klaim pulang 2024), dihitung lokal, hanya agregat",
        "dibuat": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "min_cell": MIN_CELL,
        "rawat_inap_total": count(len(ri)),
        "populasi_garis": {"total": count(len(pop)), "jalur": counts(pop.jalur)},
        "ventilasi": {
            "n_9671": count(c71.sum()), "n_9672": count(c72.sum()),
            "rasio_9671_9672": round(float(c71.sum() / c72.sum()), 3),
            "porsi_9672_ke_j101": round(float((v[c72].g == "J-1-01").mean()), 3),
            "porsi_kode_intubasi": round(float(v.kode.apply(lambda c: "96.04" in c).mean()), 3),
            "porsi_kode_agd": round(float(v.kode.apply(lambda c: "89.65" in c).mean()), 3),
            "porsi_meninggal": {"96.71": round(float(v[c71].meninggal.mean()), 3), "96.72": round(float(v[c72].meninggal.mean()), 3)},
            "lama_rawat_kuantil": {"96.71": quantiles(v[c71].los), "96.72": quantiles(v[c72].los)},
            "lama_rawat_histogram": {"96.71": histogram(v[c71].los), "96.72": histogram(v[c72].los)},
            "umur_kuantil": quantiles(v.umur), "porsi_laki": round(float((v.PSTV05.astype(str).str.upper().str[0] == "L").mean()), 3),
            "kelas_rawat": shares(v.FKL13.astype(str).str[-1]), "severitas": shares(v.sev),
            "n_dx_sekunder_kuantil": quantiles(v.n_dx2), "severitas_menurut_n_dx2": sev_by_ndx2,
            "dx_sekunder_teratas": counts(dx2_vent, top=30),
            "n_klaim": count(len(v)),
            "prosedur_lain_medis": code_shares(medis_v),
            "jalur": counts(v.jalur),
        },
        "medis": {
            "dx3": counts(medis_v.dx3, top=40),
            "porsi_dx_sasaran": round(float(medis_v.dx3.isin(TARGET_DIAGNOSIS_CODES).mean()), 3),
            "grup_medis_per_dx3": medical_groups,
        },
        "nonventilasi_dx_sasaran": {
            "n": count(len(nonvent_target)), "dx3": counts(nonvent_target.dx3),
            "lama_rawat_kuantil": quantiles(nonvent_target.los), "porsi_meninggal": round(float(nonvent_target.meninggal.mean()), 3),
            "severitas": shares(nonvent_target.sev), "umur_kuantil": quantiles(nonvent_target.umur),
            "dx_sekunder_teratas": counts(dx2_nonvent, top=30), "n_dx_sekunder_kuantil": quantiles(nonvent_target.n_dx2),
            "prosedur_lain": code_shares(nonvent_target),
            "catatan": "rawat inap berdiagnosis sasaran tanpa kode pemicu; Data Sampel tidak punya penanda ICU, jadi ini bukan khusus ICU",
        },
        "operasi": {"grup": surgical, "porsi_berventilasi_per_grup": surg_vent_share},
        "intubasi_saja": {"n": count(len(intub_only)), "porsi_ke_j120": round(float((intub_only.g == "J-1-20").mean()), 3) if len(intub_only) else None},
        "rs": {"kelas_kepemilikan": counts(pop.kelas_rs.fillna("lain") + " " + pop.kepemilikan),
               "regional": counts(pop.regional), "kelas_rawat_semua_rawat_inap": shares(ri.FKL13.astype(str).str[-1])},
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, default=DEFAULT_DATA)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    a = p.parse_args()
    out = extract(a.data)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"ditulis: {a.out}")


if __name__ == "__main__":
    main()
