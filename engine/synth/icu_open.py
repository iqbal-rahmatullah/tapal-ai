# eICU and MIMIC are ODbL-licensed, so this data and everything derived from it stays out of the repo.
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT.parent / "tapal-data-terbuka"
EICU = DATA / "eicu-crd-demo-2.0.1/eicu-collaborative-research-database-demo-2.0.1"
MIMIC = DATA / "mimic-iv-demo-2.2/mimic-iv-clinical-database-demo-2.2"
OUT_JSON = ROOT / "data/calibration/icu_open.json"
OUT_DIR = ROOT / "data/icu_open"

DEVICE_ORDER = ["ventilator_invasif", "niv", "hfnc", "nrm", "nasal_kanul", "udara_ruang"]
DEVICE_TEXT = {
    "ventilator_invasif": ["ventilator", "vent", "mechanical ventilator", "t piece", "t-piece"],
    "niv": ["bi-pap", "bipap", "bipap/cpap", "cpap"],
    "hfnc": ["high flow nasal cannula", "heated high flow nasal cannula", "high flow nc", "hfnc", "high flow vaporthrem"],
    "nrm": ["non-rebreather mask", "non-rebreather", "simple mask", "face mask", "venturi mask", "aerosol mask",
            "cool aerosol mask", "high flow mask", "oxymask", "oxy mask"],
    "nasal_kanul": ["nasal cannula", "nc", "nch", "oxymizer", "other-oximizer"],
    "udara_ruang": ["none (room air)", "room air", "ra", "r/a"],
}
TEXT_TO_DEVICE = {t: d for d, ts in DEVICE_TEXT.items() for t in ts}
VENT_SETTINGS = ["Vent Rate", "Tidal Volume (set)", "Plateau Pressure", "Peak Insp. Pressure", "Mean Airway Pressure",
                 "Exhaled MV", "Pressure Support"]
FORWARD_FILL_HOURS = 12
EPISODE_GAP_HOURS = 6
VITALS = ["spo2", "fio2", "peep", "rr_set", "rr_total", "heartrate"]


def _device_rank(device: pd.Series) -> pd.Series:
    return device.map({d: i for i, d in enumerate(DEVICE_ORDER)})


def eicu_hourly(root: Path = EICU) -> pd.DataFrame:
    p = pd.read_csv(root / "patient.csv.gz", usecols=["patientunitstayid", "hospitalid", "unitdischargeoffset", "unitadmittime24"])
    rch = pd.read_csv(root / "respiratoryCharting.csv.gz",
                      usecols=["patientunitstayid", "respchartoffset", "respchartvaluelabel", "respchartvalue"])
    nc = pd.read_csv(root / "nurseCharting.csv.gz",
                     usecols=["patientunitstayid", "nursingchartoffset", "nursingchartcelltypevallabel", "nursingchartvalue"])
    vp = pd.read_csv(root / "vitalPeriodic.csv.gz", usecols=["patientunitstayid", "observationoffset", "sao2", "respiration", "heartrate"])

    rch["jam"] = rch.respchartoffset // 60
    nc["jam"] = nc.nursingchartoffset // 60
    vp["jam"] = vp.observationoffset // 60

    dev_r = rch[rch.respchartvaluelabel.isin(["O2 Device", "Oxygen Delivery Method"])]
    dev_r = dev_r.assign(alat=dev_r.respchartvalue.astype(str).str.strip().str.lower().map(TEXT_TO_DEVICE))
    dev_n = nc[nc.nursingchartcelltypevallabel == "O2 Admin Device"]
    dev_n = dev_n.assign(alat=dev_n.nursingchartvalue.astype(str).str.strip().str.lower().map(TEXT_TO_DEVICE))
    settings = rch[rch.respchartvaluelabel.isin(VENT_SETTINGS)].assign(alat="ventilator_invasif")
    niv = rch[rch.respchartvaluelabel == "NIV Setting EPAP"].assign(alat="niv")
    events = pd.concat([d[["patientunitstayid", "jam", "alat"]] for d in (dev_r, dev_n, settings, niv)]).dropna()
    events = events.assign(r=_device_rank(events.alat)).sort_values("r").drop_duplicates(["patientunitstayid", "jam"])

    def num(labels, scale_fraction=False):
        s = rch[rch.respchartvaluelabel.isin(labels)].copy()
        s["v"] = pd.to_numeric(s.respchartvalue.astype(str).str.replace("%", ""), errors="coerce")
        if scale_fraction:
            s.loc[s.v <= 1, "v"] *= 100
        return s.dropna(subset=["v"]).groupby(["patientunitstayid", "jam"]).v.median()

    hourly = pd.concat({
        "spo2": vp.groupby(["patientunitstayid", "jam"]).sao2.median(),
        "rr_total": vp.groupby(["patientunitstayid", "jam"]).respiration.median(),
        "heartrate": vp.groupby(["patientunitstayid", "jam"]).heartrate.median(),
        "fio2": num(["FiO2", "FIO2 (%)", "O2 Percentage"], scale_fraction=True),
        "peep": num(["PEEP", "PEEP/CPAP"]),
        "rr_set": num(["Vent Rate"]),
    }, axis=1).reset_index()
    hourly = hourly.merge(events[["patientunitstayid", "jam", "alat"]], on=["patientunitstayid", "jam"], how="outer")
    hourly = hourly.merge(p, on="patientunitstayid", how="left")
    hourly = hourly[(hourly.jam >= 0) & (hourly.jam * 60 <= hourly.unitdischargeoffset)]
    hourly = hourly.sort_values(["patientunitstayid", "jam"])
    hourly["alat"] = hourly.groupby("patientunitstayid").alat.ffill(limit=FORWARD_FILL_HOURS)
    hourly.loc[hourly.fio2.notna() & ~hourly.fio2.between(21, 100), "fio2"] = np.nan
    hourly.loc[hourly.spo2.notna() & ~hourly.spo2.between(50, 100), "spo2"] = np.nan
    return hourly.rename(columns={"patientunitstayid": "rawatan_id", "hospitalid": "rs_id"})


def ventilation_episodes(hourly: pd.DataFrame, stay: str = "rawatan_id") -> pd.DataFrame:
    v = hourly[hourly.alat == "ventilator_invasif"][[stay, "jam"]].sort_values([stay, "jam"])
    new = (v[stay] != v[stay].shift()) | (v.jam - v.jam.shift() > EPISODE_GAP_HOURS)
    v = v.assign(ep=new.cumsum())
    return v.groupby("ep").agg(rawatan_id=(stay, "first"), mulai=("jam", "min"), selesai=("jam", "max")).assign(
        jam=lambda d: d.selesai - d.mulai + 1)


def mimic_hourly(root: Path = MIMIC) -> tuple[pd.DataFrame, pd.DataFrame]:
    st = pd.read_csv(root / "icu/icustays.csv.gz", usecols=["stay_id", "intime", "outtime"], parse_dates=["intime", "outtime"])
    pe = pd.read_csv(root / "icu/procedureevents.csv.gz", usecols=["stay_id", "itemid", "starttime", "endtime"],
                     parse_dates=["starttime", "endtime"])
    items = {220277: "spo2", 223835: "fio2", 220339: "peep", 224688: "rr_set", 220210: "rr_total", 220045: "heartrate"}
    ce = pd.read_csv(root / "icu/chartevents.csv.gz", usecols=["stay_id", "itemid", "charttime", "valuenum"], parse_dates=["charttime"])
    ce = ce[ce.itemid.isin(items)].merge(st[["stay_id", "intime"]], on="stay_id")
    ce["jam"] = ((ce.charttime - ce.intime).dt.total_seconds() // 3600).astype(int)
    hourly = ce.pivot_table(index=["stay_id", "jam"], columns="itemid", values="valuenum", aggfunc="median").rename(columns=items)
    hourly = hourly.reset_index()
    inv = pe[pe.itemid == 225792].merge(st[["stay_id", "intime"]], on="stay_id")
    inv = inv.assign(mulai=((inv.starttime - inv.intime).dt.total_seconds() // 3600).astype(int),
                     selesai=((inv.endtime - inv.intime).dt.total_seconds() // 3600).astype(int))
    hourly["ventilasi_invasif"] = False
    for r in inv.itertuples():
        hourly.loc[(hourly.stay_id == r.stay_id) & hourly.jam.between(r.mulai, r.selesai), "ventilasi_invasif"] = True
    episodes = inv.assign(jam=(inv.endtime - inv.starttime).dt.total_seconds() / 3600)[["stay_id", "mulai", "selesai", "jam"]]
    return hourly.rename(columns={"stay_id": "rawatan_id"}), episodes


def _quantiles(s: pd.Series) -> dict | None:
    s = s.dropna()
    return {str(q): round(float(s.quantile(q)), 1) for q in (0.1, 0.25, 0.5, 0.75, 0.9)} if len(s) >= 30 else None


def summarize(eicu: pd.DataFrame, mimic: pd.DataFrame, mimic_episodes: pd.DataFrame) -> dict:
    eps = ventilation_episodes(eicu)
    end_clock = eps.merge(eicu.drop_duplicates("rawatan_id")[["rawatan_id", "unitadmittime24"]], on="rawatan_id")
    admit_hour = pd.to_datetime(end_clock.unitadmittime24, format="%H:%M:%S").dt.hour
    extub_hour = ((admit_hour + end_clock.selesai + 1) % 24).value_counts(normalize=True).reindex(range(24), fill_value=0)
    by_device = {}
    for d in DEVICE_ORDER:
        s = eicu[eicu.alat == d]
        by_device[d] = {"jam": int(len(s)), **{v: _quantiles(s[v]) for v in VITALS},
                        "porsi_terisi": {v: round(float(s[v].notna().mean()), 3) for v in VITALS}}
    mimic_by_state = {str(k): {v: _quantiles(g[v]) for v in VITALS if v in g} for k, g in mimic.groupby("ventilasi_invasif")}
    nonvent = eicu[~eicu.rawatan_id.isin(eps.rawatan_id) & eicu.alat.notna()]
    highest = nonvent.assign(r=_device_rank(nonvent.alat)).sort_values("r").drop_duplicates("rawatan_id").alat
    nonvent_hours = nonvent.groupby("rawatan_id").jam.agg(lambda s: s.max() - s.min() + 1)
    return {
        "sumber": "eICU-CRD Demo v2.0.1 dan MIMIC-IV Demo v2.2 (PhysioNet, ODbL v1.0)",
        "dibuat": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pemetaan": {
            "alat_dari_teks": DEVICE_TEXT,
            "setelan_ventilator_berarti_invasif": VENT_SETTINGS,
            "isi_maju_jam": FORWARD_FILL_HOURS, "jeda_episode_jam": EPISODE_GAP_HOURS,
            "eicu_tanda_vital": "vitalPeriodic (sao2, respiration, heartrate; median per jam), respiratoryCharting (FiO2, PEEP, Vent Rate)",
            "mimic_ventilasi": "procedureevents itemid 225792 (Invasive Ventilation); chartevents 220277, 223835, 220339, 224688, 220210, 220045",
        },
        "eicu": {
            "rawatan": int(eicu.rawatan_id.nunique()), "rs": int(eicu.rs_id.nunique()), "jam_teramati": int(len(eicu)),
            "rawatan_berventilasi": int(eps.rawatan_id.nunique()), "episode": int(len(eps)),
            "durasi_episode_jam": _quantiles(eps.jam), "porsi_episode_96_jam": round(float((eps.jam >= 96).mean()), 3),
            "jam_ekstubasi_menurut_jam_dinding": [round(float(x), 4) for x in extub_hour],
            "tanda_vital_per_alat": by_device,
            "alat_tertinggi_rawatan_tanpa_ventilasi": {k: round(float(v), 3) for k, v in highest.value_counts(normalize=True).items()},
            "lama_rawatan_tanpa_ventilasi_jam": _quantiles(nonvent_hours),
        },
        "mimic": {
            "rawatan": int(mimic.rawatan_id.nunique()), "rawatan_berventilasi": int(mimic_episodes.stay_id.nunique()),
            "episode": int(len(mimic_episodes)), "durasi_episode_jam": _quantiles(mimic_episodes.jam),
            "porsi_episode_96_jam": round(float((mimic_episodes.jam >= 96).mean()), 3),
            "tanda_vital_menurut_status_ventilasi": mimic_by_state,
        },
    }


def main() -> None:
    eicu = eicu_hourly()
    mimic, mimic_eps = mimic_hourly()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    eicu.to_parquet(OUT_DIR / "eicu_hourly.parquet", index=False)
    mimic.to_parquet(OUT_DIR / "mimic_hourly.parquet", index=False)
    mimic_eps.to_parquet(OUT_DIR / "mimic_episodes.parquet", index=False)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summarize(eicu, mimic, mimic_eps), ensure_ascii=False, indent=1))
    print(f"ditulis: {OUT_JSON}")


if __name__ == "__main__":
    main()
