# Numbers marked DS come from Data Sampel and eICU from eICU-CRD Demo; the rest are invented ("dikarang").
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from engine.contracts import TARGET_DIAGNOSIS_CODES, TRIGGER_CODES
from engine.synth import grouper as G

ROOT = Path(__file__).resolve().parents[2]
CALIBRATION_DIR = ROOT / "data/calibration"
MONTHS = 12

N_RS_BY_CLASS = {"A": 8, "B": 35, "C": 77, "D": 30}
# Ventilated stays per hospital per month; the ratios reproduce the hospital-class shares of DS line claims.
VENT_PER_RS_MONTH = {"A": 40.0, "B": 18.8, "C": 7.4, "D": 1.3}
# Ventilated share among ICU stays, invented because DS has no ICU flag.
VENT_SHARE = {"medis_sasaran": 0.45, "medis_lain": 0.45, "operasi": 1 / 3}
VENT_HOURS = {"medis": (42.0, 1.30), "operasi": (20.0, 1.10)}  # lognormal median and sigma, tuned to the DS 96.72 share
# Ventilated mortality falls smoothly with log hours (no step at the 96-hour tariff line); intercept and slope are fitted so the
# averages match DS by code (96.71: 0.68, 96.72: 0.59). Non-ventilated ICU mortality is invented.
DEATH_LOGIT = (0.502, -0.179)
DEATH_P_NONVENT = 0.12
OTHER_MEDICAL = ("N18", "E11", "A16", "I69", "I13", "I12")
FULL_ICD10 = {
    "J96": "J96.0", "J18": "J18.9", "J80": "J80", "J90": "J90", "I63": "I63.9", "I61": "I61.9", "I64": "I64",
    "G93": "G93.6", "I21": "I21.9", "I50": "I50.0", "A41": "A41.9", "R57": "R57.0", "S06": "S06.9",
    "N18": "N18.5", "E11": "E11.9", "A16": "A16.2", "I69": "I69.3", "I13": "I13.2", "I12": "I12.0",
    "E87": "E87.1", "D64": "D64.9", "E88": "E88.9", "I46": "I46.9", "D63": "D63.8", "I10": "I10", "N17": "N17.9",
    "E83": "E83.5", "J15": "J15.9", "I11": "I11.9", "D69": "D69.6", "I48": "I48.9", "J81": "J81", "K92": "K92.2",
    "O99": "O99.8", "G81": "G81.9", "I25": "I25.1", "E10": "E10.9", "E78": "E78.5", "K30": "K30", "A09": "A09.9",
    "E86": "E86",
}
SURGERY_DX = {
    "G-1-10": ("I61.9", "S06.5", "D32.0", "C71.9"), "K-1-20": ("K63.1", "K65.0", "K56.6", "C18.9"),
    "G-1-11": ("G91.9",), "N-1-12": ("N18.5",), "K-1-40": ("K25.5", "K35.8", "K80.2"), "I-1-07": ("I25.1",),
    "I-1-04": ("I35.0",), "M-1-03": ("M41.1",), "I-1-06": ("Q21.1", "I71.0"),
}
SURGERY_CODE = {g: c for c, g in G.SURGERY_CODES.items()}
RULE_CODES = TRIGGER_CODES | G.DEFAULT.trach_codes | set(G.SURGERY_CODES) | {"34.04", "93.90"}
NONVENT_DEVICES = ("nasal_kanul", "udara_ruang", "niv", "nrm", "hfnc")
WRITING_STYLES = ("formal", "singkatan", "telegrafis", "campur_inggris")  # the last one is held out for TEST
FILLER_RATE = 1.0  # mild comorbidities per patient beyond the DS top-30 codes
ICU_PULL = 0.25  # non-ventilated ICU patients sit a quarter of the way from ward (DS) to ventilated (DS) rates
COST_KEYS = ("prosedur_non_bedah", "prosedur_bedah", "konsultasi", "tenaga_ahli", "keperawatan", "penunjang",
             "radiologi", "laboratorium", "pelayanan_darah", "rehabilitasi", "kamar", "rawat_intensif", "obat",
             "obat_kronis", "obat_kemoterapi", "alkes", "bmhp", "sewa_alat")


@dataclass(frozen=True)
class WorldParams:
    seed: int
    scale: float = 1.0
    evidence_noise: float = 1.0
    code_effect_sd: float = 0.30
    intubation_code_mean: float = 0.18  # DS
    rounding_mean: float = 0.15
    rent_styles: tuple[float, float, float] = (0.45, 0.40, 0.15)  # per hour, per day, package
    write_lag_median_min: float = 30.0
    late_note_share: float = 0.03
    late_note_median_h: float = 10.0
    bulk_note_share: float = 0.40  # honest bulk-writing trap hospitals: notes and procedure reports written in the batch
    bulk_report_share: float = 0.10
    bulk_busy_share: float = 0.0
    held_out_style: bool = False
    grouper: G.GrouperConfig = G.DEFAULT
    traps: dict = field(default_factory=lambda: {"bulat_kuat": 6, "sakit_terlihat": 4, "sakit_tersembunyi": 2,
                                                 "tulis_massal_jujur": 4})


def load_calibration() -> dict:
    files = {"ds": "data_sampel.json", "icu": "icu_open.json"}
    missing = [f for f in files.values() if not (CALIBRATION_DIR / f).exists()]
    if missing:
        raise FileNotFoundError(f"kalibrasi belum ada: {missing}; jalankan engine.synth.calibration dan engine.synth.icu_open")
    return {k: json.loads((CALIBRATION_DIR / f).read_text()) for k, f in files.items()}


def expit(x):
    return 1 / (1 + np.exp(-x))


def logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def from_quantiles(rng, q: dict, n: int, lo: float, hi: float) -> np.ndarray:
    xs = [0.0] + [float(k) for k in q] + [1.0]
    ys = [lo] + list(q.values()) + [hi]
    return np.interp(rng.random(n), xs, ys)


def full_icd10(code3: str) -> str:
    return FULL_ICD10.get(code3, f"{code3}.9")


def weights(d: dict, keys) -> np.ndarray:
    w = np.array([float(d.get(k) or 1) for k in keys])
    return w / w.sum()


def make_hospitals(rng: np.random.Generator, cal: dict, p: WorldParams) -> pd.DataFrame:
    mix = cal["ds"]["rs"]["kelas_kepemilikan"]
    gov = {k: mix.get(f"{k} pemerintah", 0) / (mix.get(f"{k} pemerintah", 0) + mix.get(f"{k} swasta", 0)) for k in "ABCD"}
    reg = cal["ds"]["rs"]["regional"]
    kelas = np.repeat(list(N_RS_BY_CLASS), list(N_RS_BY_CLASS.values()))
    n = len(kelas)
    # Inverse-CDF draws use one uniform each, so changing a habit parameter never shifts the rest of the random stream.
    beta = lambda mean, k: stats.beta.ppf(rng.random(n), mean * k, (1 - mean) * k)
    h = pd.DataFrame({
        "kode_rs": [f"RS-{i + 1:03d}" for i in rng.permutation(n)],
        "kelas_rs": kelas,
        "kepemilikan": np.where(rng.random(n) < np.array([gov[k] for k in kelas]), "pemerintah", "swasta"),
        "regional": rng.choice([int(r) for r in reg], n, p=weights(reg, reg)),
        "p_kode_intubasi": beta(p.intubation_code_mean, 6),
        "porsi_bulat24": beta(p.rounding_mean, 5),
        "gaya_sewa": rng.choice(["per_jam", "per_hari", "paket"], n, p=list(p.rent_styles)),
        "efek_kode": rng.normal(0, p.code_effect_sd, n),
        "efek_ventilasi": rng.normal(0, 0.25, n),
        "geser_keparahan": 0.0,
        "pengali_biaya": np.exp(rng.normal(0, 0.10, n)),
        "jeda_tulis_menit": np.exp(rng.normal(np.log(p.write_lag_median_min), 0.6, n)),
        "porsi_catatan_telat": beta(p.late_note_share, 20),
        "jeda_telat_jam": p.late_note_median_h * np.exp(rng.normal(0, 0.3, n)),
        "porsi_massal_catatan": beta(p.bulk_note_share, 20),
        "porsi_massal_tindakan": beta(p.bulk_report_share, 20),
        "porsi_hari_sibuk": p.bulk_busy_share,
        "gaya_tulis": rng.choice(WRITING_STYLES if p.held_out_style else WRITING_STYLES[:-1], n),
        "jebakan": "",
    })
    # Traps go to class A-C only: class D hospitals are too small to be judged anyway (TARGETS F3).
    picks = rng.permutation(h.index[h.kelas_rs != "D"].to_numpy())
    start = 0
    for trap, k in p.traps.items():
        h.loc[picks[start:start + k], "jebakan"] = trap
        start += k
    h.loc[h.jebakan == "bulat_kuat", "porsi_bulat24"] = 0.85
    h.loc[h.jebakan.isin(["sakit_terlihat", "sakit_tersembunyi"]), "efek_ventilasi"] += 0.6
    h.loc[h.jebakan == "sakit_terlihat", "geser_keparahan"] = 0.6
    return h.sort_values("kode_rs").reset_index(drop=True)


def make_stays(rng: np.random.Generator, h: pd.DataFrame, cal: dict, p: WorldParams) -> pd.DataFrame:
    ds, icu = cal["ds"], cal["icu"]
    jalur = ds["populasi_garis"]["jalur"]
    medis_frac = jalur["medis"] / (jalur["medis"] + jalur["operasi"] + jalur.get("lain", 0))
    target = ds["medis"]["porsi_dx_sasaran"]
    vent_mix = {"medis_sasaran": medis_frac * target, "medis_lain": medis_frac * (1 - target), "operasi": 1 - medis_frac}

    segs = list(vent_mix)
    rs_i, month, seg = (a.ravel() for a in np.meshgrid(np.arange(len(h)), np.arange(-1, MONTHS), np.arange(len(segs)), indexing="ij"))
    lam = (h.kelas_rs.map(VENT_PER_RS_MONTH).to_numpy()[rs_i] * p.scale
           * np.array([vent_mix[x] / VENT_SHARE[x] for x in segs])[seg])
    counts = rng.poisson(lam)
    rs_i, month, seg = np.repeat(rs_i, counts), np.repeat(month, counts), np.repeat(seg, counts)
    n = len(rs_i)
    hs = h.iloc[rs_i].reset_index(drop=True)
    s = pd.DataFrame({"kode_rs": hs.kode_rs, "segmen": np.array(segs)[seg]})
    base_share = np.array([VENT_SHARE[x] for x in segs])[seg]
    vent = rng.random(n) < expit(logit(base_share) + hs.efek_ventilasi.to_numpy())
    s["ventilasi"] = vent
    surg = (s.segmen == "operasi").to_numpy()

    target_codes = sorted(TARGET_DIAGNOSIS_CODES)
    w_vent = weights(ds["medis"]["dx3"], target_codes)
    w_ward = weights(ds["nonventilasi_dx_sasaran"]["dx3"], target_codes)
    w_icu = np.sqrt(w_vent * w_ward) / np.sqrt(w_vent * w_ward).sum()
    dx3 = np.full(n, "", object)
    m = (s.segmen == "medis_sasaran").to_numpy()
    dx3[m & vent] = rng.choice(target_codes, (m & vent).sum(), p=w_vent)
    dx3[m & ~vent] = rng.choice(target_codes, (m & ~vent).sum(), p=w_icu)
    m = (s.segmen == "medis_lain").to_numpy()
    dx3[m] = rng.choice(OTHER_MEDICAL, m.sum(), p=weights(ds["medis"]["dx3"], OTHER_MEDICAL))
    grp = np.full(n, "", object)
    n_line = {g: v["n_line"] for g, v in ds["operasi"]["grup"].items()}
    for k in N_RS_BY_CLASS:
        # Cardiac surgery (and craniotomy at class D) has no tariff at smaller hospitals, so they never do it.
        groups = [g for g in n_line if G.has_tariff(k, g)]
        m = surg & (hs.kelas_rs == k).to_numpy()
        grp[m] = rng.choice(groups, m.sum(), p=weights(n_line, groups))
    s["grup_operasi"] = grp
    primary = np.array([full_icd10(d) if d else "" for d in dx3], object)
    primary[surg] = [rng.choice(SURGERY_DX[g]) for g in grp[surg]]
    s["dx_primer"] = primary
    s["dx3"] = [d[:3] for d in primary]

    s["bukti_ringan"] = vent & (hs.jebakan == "sakit_tersembunyi").to_numpy() & (rng.random(n) < 0.5)
    s["keparahan"] = rng.normal(0, 1, n) + 0.5 * vent - 0.5 * s.bukti_ringan + hs.geser_keparahan.to_numpy()
    vq = ds["ventilasi"]
    s["umur"] = np.round(from_quantiles(rng, vq["umur_kuantil"], n, 1, 90)).astype(int)
    s["jenis_kelamin"] = np.where(rng.random(n) < vq["porsi_laki"], "L", "P")
    kr = vq["kelas_rawat"]
    s["kelas_rawat"] = rng.choice([int(k) for k in kr], n, p=weights(kr, kr))
    s["cara_masuk"] = np.where(surg, rng.choice(["gp", "emd"], n, p=[0.6, 0.4]),
                               rng.choice(["emd", "gp", "hosp-trans"], n, p=[0.6, 0.3, 0.1]))

    # Invented timeline in hours from admission, checked against DS length of stay.
    ward_first = ~surg & (rng.random(n) < 0.5)
    pre_icu = np.where(surg, rng.gamma(2, 10, n) + rng.uniform(2, 6, n),
                       np.where(ward_first, rng.gamma(2, 48, n), rng.exponential(3, n)))
    vent_offset = np.where(surg, 0.0, np.where(rng.random(n) < 0.5, -rng.uniform(0, 2, n), rng.exponential(8, n)))
    vent_offset = np.maximum(vent_offset, -pre_icu)
    med = np.where(surg, VENT_HOURS["operasi"][0], VENT_HOURS["medis"][0])
    sig = np.where(surg, VENT_HOURS["operasi"][1], VENT_HOURS["medis"][1])
    hours = np.exp(np.log(med) + sig * rng.normal(0, 1, n) + 0.15 * s.keparahan.to_numpy())
    hours = np.where(vent, np.clip(np.round(hours, 2), 2, 700), 0.0)
    base = np.where(vent, DEATH_LOGIT[0] + DEATH_LOGIT[1] * np.log(np.maximum(hours, 1) / 96), logit(DEATH_P_NONVENT))
    p_die = expit(base + 0.3 * hs.geser_keparahan.to_numpy() - 0.6 * s.bukti_ringan.to_numpy())
    died = rng.random(n) < p_die
    died_on_vent = died & vent & (rng.random(n) < 0.8)
    icu_in = pre_icu
    vent_start = np.where(vent, icu_in + vent_offset, np.nan)
    vent_stop = vent_start + hours
    nonvent_icu = from_quantiles(rng, icu["eicu"]["lama_rawatan_tanpa_ventilasi_jam"], n, 4, 240)
    post_vent = np.where(died_on_vent, 0.0, rng.gamma(2, 12, n))
    icu_out = np.where(vent, vent_stop + post_vent, icu_in + nonvent_icu)
    died_in_icu = died & (died_on_vent | (rng.random(n) < 0.6))
    ward_after = np.where(died_in_icu, 0.0, rng.poisson(4, n) * 24 + rng.uniform(0, 24, n))
    discharge = icu_out + ward_after

    t0 = pd.Timestamp("2025-01-01") + pd.to_timedelta(month * 43_776 + rng.integers(0, 30 * 24 * 60, n), unit="min")  # 30.4 days
    at = lambda hrs: t0 + pd.to_timedelta(np.round(np.nan_to_num(hrs) * 60), unit="min")
    s["tgl_masuk"] = t0
    s["icu_masuk"] = at(icu_in)
    s["icu_keluar"] = at(icu_out)
    s["mulai_ventilasi"] = at(vent_start).where(vent)
    s["selesai_ventilasi"] = at(vent_stop).where(vent)
    s["tgl_pulang"] = at(discharge)
    s["jam_ventilasi_benar"] = hours
    s["meninggal"] = died
    s["meninggal_saat_ventilasi"] = died_on_vent
    s["jam_icu"] = icu_out - icu_in
    s["icu_los"] = np.maximum(1, np.ceil(s.jam_icu / 24)).astype(int)
    s["lama_rawat"] = (s.tgl_pulang.dt.normalize() - s.tgl_masuk.dt.normalize()).dt.days.astype(int)
    eicu = icu["eicu"]["alat_tertinggi_rawatan_tanpa_ventilasi"]
    s["alat_tertinggi"] = np.where(vent, "ventilator_invasif", rng.choice(NONVENT_DEVICES, n, p=weights(eicu, NONVENT_DEVICES)))
    s["bulan"] = s.tgl_pulang.dt.month
    s["trakeostomi"] = vent & (hours >= 96) & (rng.random(n) < np.clip(0.03 + (hours - 96) / 700, 0, 0.4))
    # A claim belongs to its discharge month, and the year is January-December 2025 (TARGETS v2 PERIODE).
    return s[s.tgl_pulang.dt.year == 2025].reset_index(drop=True)


def code_by_importance(rng: np.random.Generator, conditions: set[str], depth: int) -> list[str]:
    rank = lambda c: 0 if c in G.MCC else 1 if c in G.CC else 2
    ordered = sorted(rng.permutation(sorted(conditions)), key=rank)
    return sorted(ordered[:depth])


def _rates(listed: dict, codes, floor: float) -> np.ndarray:
    return np.array([listed.get(c, floor) for c in codes])


def add_evidence(rng: np.random.Generator, s: pd.DataFrame, h: pd.DataFrame, cal: dict, p: WorldParams) -> pd.DataFrame:
    ds = cal["ds"]
    n = len(s)
    rs = h.set_index("kode_rs").loc[s.kode_rs].reset_index()
    vent = s.ventilasi.to_numpy()
    vent_profile = vent & ~s.bukti_ringan.to_numpy()
    z = s.keparahan.to_numpy() - 0.5 * vent
    surg = (s.segmen == "operasi").to_numpy()

    # One Bernoulli per condition at DS secondary-diagnosis rates; the coder below decides which ones get written.
    v2, w2 = ds["ventilasi"]["dx_sekunder_teratas"], ds["nonventilasi_dx_sasaran"]["dx_sekunder_teratas"]
    nv, nw = ds["ventilasi"]["n_klaim"], ds["nonventilasi_dx_sasaran"]["n"]
    dx_codes = sorted(set(v2) | set(w2))
    rv = _rates({k: c / nv for k, c in v2.items()}, dx_codes, 0.005)
    rw = _rates({k: c / nw for k, c in w2.items()}, dx_codes, 0.003)
    base = np.where(vent_profile[:, None], rv[None, :], (rw + ICU_PULL * (rv - rw))[None, :])
    has = rng.random((n, len(dx_codes))) < expit(logit(base) + 0.35 * z[:, None] + 0.15 * vent_profile[:, None])
    has &= np.array(dx_codes)[None, :] != s.dx3.to_numpy()[:, None]
    fillers = np.array(["E78", "K30", "I10", "A09"])
    n_fill = rng.poisson(FILLER_RATE, n)
    conditions = [(set(np.array(dx_codes)[has[i]]) | set(rng.choice(fillers, n_fill[i]))) - {s.dx3.iat[i]} for i in range(n)]
    # Coders write the most important diagnoses first and stop at a depth drawn from DS, as real coders do (fixed 31 Oct 2026
    # after the first DEV build failed the "severity III with one secondary diagnosis" reality row).
    vq, wq = ds["ventilasi"]["n_dx_sekunder_kuantil"], ds["nonventilasi_dx_sasaran"]["n_dx_sekunder_kuantil"]
    icu_q = {q: wq[q] + ICU_PULL * (vq[q] - wq[q]) for q in vq}
    depth = np.round(np.where(vent_profile, from_quantiles(rng, vq, n, 0, 12), from_quantiles(rng, icu_q, n, 0, 12))).astype(int)
    sec = [code_by_importance(rng, conditions[i], depth[i]) for i in range(n)]
    s["dx_sekunder3"] = sec
    s["diagnosa"] = ["#".join([d] + [full_icd10(c) for c in cs]) for d, cs in zip(s.dx_primer, sec)]

    # A code missing from one DS top-30 list gets half that list's smallest rate.
    pv, pw = ds["ventilasi"]["prosedur_lain_medis"], ds["nonventilasi_dx_sasaran"]["prosedur_lain"]
    codes = np.array(sorted((set(pv) | set(pw)) - RULE_CODES))
    rv = _rates(pv, codes, min(pv.values()) / 2)
    rw = _rates(pw, codes, min(pw.values()) / 2)
    base = np.where(vent_profile[:, None], rv[None, :], (rw + ICU_PULL * (rv - rw))[None, :])
    shift = 0.30 * z + rs.efek_kode.to_numpy() - np.where(surg, 0.35, 0.0)
    has = rng.random((n, len(codes))) < expit(logit(base) + shift[:, None])
    procs = [set(codes[row]) for row in has]

    true_h = s.jam_ventilasi_benar.to_numpy()
    floor24 = rng.random(n) < rs.porsi_bulat24.to_numpy()
    # The honest 24-hour habit floors hours to whole days, adding peaks every 24 hours without ever crossing the 96-hour line.
    recorded = np.where(floor24 & (true_h >= 24), np.floor(true_h / 24) * 24, np.maximum(np.round(true_h), 1))
    recorded = np.where(vent, recorded, 0).astype(int)
    brief_only = vent & (true_h < 6) & (rng.random(n) < 0.3)
    p_intub = rs.p_kode_intubasi.to_numpy()
    u = rng.random((n, 4))
    top = ds["operasi"]["grup"]
    for i in np.flatnonzero(vent | surg | (s.alat_tertinggi == "niv").to_numpy() | s.dx3.isin(["J90", "J18"]).to_numpy()):
        pc = procs[i]
        if vent[i]:
            if brief_only[i]:
                pc.add("96.04")
            else:
                pc.add("96.72" if recorded[i] >= 96 else "96.71")
                if u[i, 0] < p_intub[i]:
                    pc.add("96.04")
            if s.trakeostomi.iat[i]:
                pc.add("31.1" if u[i, 1] < 0.8 else "31.29")
        elif s.alat_tertinggi.iat[i] == "niv" and u[i, 2] < 0.10:
            pc.add("93.90")
        elif s.dx3.iat[i] in ("J90", "J18") and u[i, 3] < 0.04:
            pc.add("34.04")
        if surg[i]:
            g = s.grup_operasi.iat[i]
            pc.add(SURGERY_CODE[g])
            n_line = top[g]["n_line"] or 1
            for c, k in top[g]["top_procedures"].items():
                if c not in RULE_CODES and rng.random() < k / n_line:
                    pc.add(c)
    s["prosedur"] = [sorted(pc) for pc in procs]
    s["procedure"] = ["#".join(pc) for pc in s.prosedur]
    coded_vent = np.array([bool({"96.71", "96.72"} & set(pc)) for pc in s.prosedur])
    s["ventilator_hour"] = np.where(coded_vent, recorded, 0)
    s["ventilator_use_ind"] = coded_vent.astype(int)
    s["ventilator_start_dttm"] = s.mulai_ventilasi.where(coded_vent)
    s["ventilator_stop_dttm"] = (s.mulai_ventilasi + pd.to_timedelta(s.ventilator_hour, unit="h")).where(coded_vent)
    s["icu_indikator"] = 1
    s["discharge_status"] = np.where(s.meninggal, 4, rng.choice([1, 2, 3], n, p=[0.9, 0.05, 0.05]))
    s["jenis_rawat"] = 1
    return add_costs(rng, s, rs, p)


def add_costs(rng: np.random.Generator, s: pd.DataFrame, rs: pd.DataFrame, p: WorldParams) -> pd.DataFrame:
    # Invented hospital charges (DS has no itemised bill), where package hospitals fold ventilator rent into the ICU charge.
    n = len(s)
    noise = lambda sd: np.exp(rng.normal(0, sd * p.evidence_noise, n))
    vent = s.ventilator_use_ind.to_numpy() == 1
    days, icu_days = np.maximum(s.lama_rawat.to_numpy(), 1), s.icu_los.to_numpy()
    cls = s.kelas_rs.map({"A": 1.4, "B": 1.2, "C": 1.0, "D": 0.8}).to_numpy() * rs.pengali_biaya.to_numpy()
    room = s.kelas_rawat.map({1: 400_000, 2: 300_000, 3: 200_000}).to_numpy()
    style = rs.gaya_sewa.to_numpy()
    dev = s.alat_tertinggi.to_numpy()
    support = np.isin(dev, ["niv", "hfnc"]) & ~vent
    oxygen = np.isin(dev, ["nasal_kanul", "nrm"]) & ~vent
    hours = s.ventilator_hour.to_numpy()
    rent = np.select(
        [vent & (style == "per_jam"), vent & (style == "per_hari"), support & (style != "paket"), oxygen & (style != "paket")],
        [hours * 60_000, np.ceil(hours / 24) * 1_440_000, icu_days * 600_000, icu_days * 50_000], 0)
    z = s.keparahan.to_numpy()
    surg = (s.segmen == "operasi").to_numpy()
    transfusion = np.array(["99.04" in pc for pc in s.prosedur])
    bill = {
        "kamar": np.maximum(days - icu_days, 0) * room * cls * noise(0.15),
        "rawat_intensif": icu_days * 2_500_000 * cls * np.where(vent, np.where(style == "paket", 1.6, 1.25), 1.0) * noise(0.2),
        "sewa_alat": rent * noise(0.1),
        "obat": days * 800_000 * cls * np.where(vent, 1.5, 1.0) * np.exp(0.15 * z) * noise(0.35),
        "laboratorium": days * 400_000 * cls * np.where(vent | support, 1.3, 1.0) * noise(0.3),
        "radiologi": rng.poisson(1 + days / 3) * 300_000 * cls,
        "penunjang": days * 200_000 * cls * noise(0.2),
        "keperawatan": days * 250_000 * cls * noise(0.2),
        "tenaga_ahli": np.power(days, 0.7) * 500_000 * cls * noise(0.2),
        "konsultasi": rng.poisson(2, n) * 150_000 * cls,
        "prosedur_non_bedah": np.where(vent, 1_500_000, 300_000) * cls * noise(0.3),
        "prosedur_bedah": np.where(surg, 25_000_000, 0) * cls * noise(0.4),
        "pelayanan_darah": transfusion * 1_000_000 * rng.integers(1, 4, n),
        "bmhp": days * 150_000 * cls * noise(0.3),
        "alkes": np.where(vent, 2_000_000, 500_000) * cls * noise(0.3),
    }
    for k in COST_KEYS:
        s[f"tarif_rs_{k}"] = (np.round(np.asarray(bill.get(k, np.zeros(n)), float) / 100) * 100).astype(np.int64)
    return s


def assign_group_and_tariff(s: pd.DataFrame, cfg: G.GrouperConfig) -> pd.DataFrame:
    s["cbg"] = [G.group(d, set(pc), sec, hr, cfg) for d, pc, sec, hr in zip(s.dx3, s.prosedur, s.dx_sekunder3, s.ventilator_hour)]
    s["tarif_ina_cbg"] = [G.tariff(r, k, o, c, kr) for r, k, o, c, kr in zip(s.regional, s.kelas_rs, s.kepemilikan, s.cbg, s.kelas_rawat)]
    return s


def build_world(p: WorldParams, cal: dict | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    cal = cal or load_calibration()
    rng = np.random.default_rng(p.seed)
    h = make_hospitals(rng, cal, p)
    s = make_stays(rng, h, cal, p)
    s = s.merge(h[["kode_rs", "kelas_rs", "kepemilikan", "regional", "jebakan"]], on="kode_rs", how="left")
    s = add_evidence(rng, s, h, cal, p)
    s = assign_group_and_tariff(s, p.grouper)
    s = s.sort_values(["kode_rs", "tgl_masuk"]).reset_index(drop=True)
    s["nomor_sep"] = "SEP-" + s.kode_rs.str[3:] + "-" + (s.groupby("kode_rs").cumcount() + 1).astype(str).str.zfill(5)
    return h, s
