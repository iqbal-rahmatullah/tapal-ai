# Templates instead of an LLM keep every assertion label exact; no template copies a real document.
from dataclasses import dataclass

import numpy as np
import pandas as pd

from engine.synth.fraud import in_line_population

MONTHS_ID = ("", "Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober",
             "November", "Desember")
MONTHS_EN = ("", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
MAX_DAYS = 14  # longer stays keep their first and last 7 ICU days, so the record fits the LLM context (8192)

DEVICE_NAME = {
    "formal": {"ventilator_invasif": "ventilator mekanik", "niv": "NIV (BiPAP)", "hfnc": "high flow nasal cannula",
               "nrm": "sungkup non-rebreathing", "nasal_kanul": "kanul hidung", "udara_ruang": "udara ruangan"},
    "singkatan": {"ventilator_invasif": "MV", "niv": "NIV", "hfnc": "HFNC", "nrm": "NRM", "nasal_kanul": "NK",
                  "udara_ruang": "RA"},
    "telegrafis": {"ventilator_invasif": "vent", "niv": "BiPAP", "hfnc": "HFNC", "nrm": "NRM", "nasal_kanul": "nasal",
                   "udara_ruang": "udara bebas"},
    "campur_inggris": {"ventilator_invasif": "mechanical ventilator", "niv": "BiPAP", "hfnc": "high flow",
                       "nrm": "non-rebreather mask", "nasal_kanul": "nasal cannula", "udara_ruang": "room air"},
}
FLOW = {"nasal_kanul": (2, 4), "nrm": (10, 15), "hfnc": (30, 60), "niv": (10, 14), "udara_ruang": (0, 0)}
VENT_MODES = ("SIMV", "PC", "VC", "PSIMV", "PS")

T = {
    "status_vent": {
        "formal": ["Pasien terpasang {alat} mode {mode}, FiO2 {fio2}%, PEEP {peep} cmH2O.",
                   "Saat ini pasien masih menggunakan {alat} dengan mode {mode}, FiO2 {fio2}%."],
        "singkatan": ["Pasien on {alat} mode {mode}, FiO2 {fio2}%, PEEP {peep}.", "Tetap on {alat}, setting {mode} FiO2 {fio2}%."],
        "telegrafis": ["{alat} {mode} FiO2 {fio2} PEEP {peep}.", "Masih {alat}, {mode}."],
        "campur_inggris": ["Patient still on {alat}, mode {mode}, FiO2 {fio2}%.", "Currently on {alat} dengan setting {mode}, PEEP {peep}."],
    },
    "status_o2": {
        "formal": ["Pasien bernapas spontan dengan {alat} {flow} liter per menit.", "Pasien menggunakan {alat} {flow} lpm."],
        "singkatan": ["Napas spontan dgn {alat} {flow} lpm.", "Terpasang {alat} {flow} lpm."],
        "telegrafis": ["{alat} {flow} lpm.", "Spontan, {alat} {flow} lpm."],
        "campur_inggris": ["Breathing spontaneously on {alat} {flow} lpm.", "Pasien on {alat} {flow} lpm, stable."],
    },
    "status_ra": {
        "formal": ["Pasien bernapas spontan dengan {alat}."],
        "singkatan": ["Napas spontan {alat}."],
        "telegrafis": ["Spontan {alat}."],
        "campur_inggris": ["Breathing spontaneously on {alat}."],
    },
    "status_niv": {
        "formal": ["Pasien menggunakan {alat} dengan IPAP {flow} dan EPAP 5 cmH2O."],
        "singkatan": ["Pasien on {alat} IPAP {flow} EPAP 5."],
        "telegrafis": ["{alat} IPAP {flow}/EPAP 5."],
        "campur_inggris": ["Patient on {alat} with IPAP {flow}, EPAP 5."],
    },
    "mulai": {
        "formal": ["Pada {waktu} dilakukan intubasi endotrakeal dengan ETT nomor {ett}, kemudian pasien dihubungkan ke {alat} mode {mode}."],
        "singkatan": ["{waktu} intubasi ETT no {ett}, sambung {alat} mode {mode}."],
        "telegrafis": ["{waktu} intubasi ETT {ett} -> {alat} {mode}."],
        "campur_inggris": ["Intubated at {waktu} with ETT size {ett}, connected to {alat} mode {mode}."],
    },
    "selesai": {
        "formal": ["Pada {waktu} dilakukan ekstubasi, pasien bernapas spontan dengan {alat} {flow} lpm."],
        "singkatan": ["{waktu} ekstubasi, lanjut {alat} {flow} lpm."],
        "telegrafis": ["{waktu} aff ETT, {alat} {flow} lpm."],
        "campur_inggris": ["Extubated at {waktu}, now on {alat} {flow} lpm."],
    },
    "meninggal": {
        "formal": ["Pasien dinyatakan meninggal dunia pada {waktu} dengan {alat} masih terpasang."],
        "singkatan": ["{waktu} pasien meninggal, masih on {alat}."],
        "telegrafis": ["{waktu} exitus, {alat} terpasang."],
        "campur_inggris": ["Patient expired at {waktu} while still on {alat}."],
    },
    "trakeostomi": {
        "formal": ["Pada {waktu} dilakukan trakeostomi, kanul trakeostomi terpasang dan tersambung ke {alat}."],
        "singkatan": ["{waktu} trakeostomi, kanul trakea sambung {alat}."],
        "telegrafis": ["{waktu} trakeostomi -> {alat}."],
        "campur_inggris": ["Tracheostomy done at {waktu}, connected to {alat}."],
    },
    "disangkal": {
        "formal": ["Pasien tidak terpasang {alat}.", "Tidak ada indikasi pemasangan {alat} saat ini."],
        "singkatan": ["Tdk terpasang {alat}.", "{alat} (-)."],
        "telegrafis": ["{alat} tidak.", "Tanpa {alat}."],
        "campur_inggris": ["No {alat} needed.", "Pasien not on {alat}."],
    },
    "rencana_intubasi": {
        "formal": ["Rencana pemasangan {alat} apabila terjadi perburukan.", "Siapkan {alat} bila saturasi terus turun."],
        "singkatan": ["Rencana intubasi + {alat} bila perburukan.", "Siapkan {alat} jika SpO2 drop."],
        "telegrafis": ["Rcn {alat} bila jelek.", "Siap {alat}."],
        "campur_inggris": ["Plan to start {alat} if deteriorating.", "Standby {alat} kalau desaturasi."],
    },
    "rencana_lepas": {
        "formal": ["Rencana penyapihan dan pelepasan {alat} besok pagi bila hemodinamik stabil."],
        "singkatan": ["Plan weaning {alat} besok pagi."],
        "telegrafis": ["Rcn weaning {alat} besok."],
        "campur_inggris": ["Plan weaning from {alat} tomorrow morning."],
    },
    "ditunda": {
        "formal": ["Rencana ekstubasi pagi ini ditunda karena pasien masih gelisah dan saturasi turun saat uji napas spontan."],
        "singkatan": ["Ekstubasi ditunda, pasien blm stabil saat SBT."],
        "telegrafis": ["Ekstubasi tunda, SBT gagal."],
        "campur_inggris": ["Extubation postponed, SBT failed."],
    },
    "riwayat": {
        "formal": ["Riwayat dirawat di ICU dengan {alat} pada tahun {thn}."],
        "singkatan": ["Riw. pakai {alat} th {thn}."],
        "telegrafis": ["Riw {alat} {thn}."],
        "campur_inggris": ["History of {alat} use in {thn}."],
    },
    "templat": {
        "formal": ["Alat bantu napas: {daftar} (coret yang tidak perlu)."],
        "singkatan": ["Alat napas: {daftar} *coret yg tdk perlu."],
        "telegrafis": ["Alat: {daftar} (pilih)."],
        "campur_inggris": ["Respiratory support: {daftar} (circle one)."],
    },
}
KIND_LABEL = {"status_vent": "terpasang", "status_o2": "terpasang", "status_ra": "terpasang", "status_niv": "terpasang",
              "mulai": "terpasang", "selesai": "terpasang", "meninggal": "terpasang", "trakeostomi": "terpasang",
              "disangkal": "disangkal", "rencana_intubasi": "rencana", "rencana_lepas": "rencana", "ditunda": "rencana",
              "riwayat": "riwayat", "templat": "templat"}
DX_NAME = {
    "J96": "gagal napas akut", "J18": "pneumonia", "J80": "ARDS", "J90": "efusi pleura", "I63": "stroke infark",
    "I61": "perdarahan intraserebral", "I64": "stroke", "G93": "edema serebri", "I21": "infark miokard akut",
    "I50": "gagal jantung akut", "A41": "sepsis", "R57": "syok", "S06": "cedera kepala berat", "N18": "penyakit ginjal kronik",
    "E11": "ketoasidosis diabetik", "A16": "tuberkulosis paru", "I69": "gejala sisa stroke", "I13": "penyakit jantung dan ginjal hipertensi",
    "I12": "penyakit ginjal hipertensi",
}
SURGERY_NAME = {"G-1-10": "pasca kraniotomi", "K-1-20": "pasca laparotomi", "G-1-11": "pasca pemasangan VP shunt",
                "N-1-12": "pasca pemasangan akses dialisis", "K-1-40": "pasca operasi saluran cerna", "I-1-07": "pasca CABG",
                "I-1-04": "pasca operasi katup", "M-1-03": "pasca fusi tulang belakang", "I-1-06": "pasca operasi kardiotorasik"}
FILLER = {
    "S": ["Keluarga mengatakan pasien sesak sejak kemarin.", "Pasien tampak gelisah.", "Keluhan nyeri berkurang.",
          "Pasien tidur cukup semalam.", "Batuk berdahak masih ada."],
    "A": ["{dx}.", "{dx}, perbaikan.", "{dx}, kondisi kritis."],
    "P": ["Lanjutkan antibiotik sesuai jadwal.", "Cek AGD dan elektrolit ulang.", "Fisioterapi dada dua kali sehari.",
          "Balans cairan ketat.", "Konsul gizi klinik.", "Evaluasi foto toraks besok."],
    "N": ["Suction lendir kental.", "Posisi miring kiri-kanan tiap 2 jam.", "Pasien tampak tenang.", "Urin output cukup."],
}


@dataclass
class Story:
    icu_in: pd.Timestamp
    icu_out: pd.Timestamp
    segments: list  # (start, end, device), in time order
    vent: bool
    start: pd.Timestamp | None
    stop: pd.Timestamp | None
    death: pd.Timestamp | None
    death_on_vent: bool
    trach_at: pd.Timestamp | None
    dx_text: str
    pre_device: str


def fmt_time(ts: pd.Timestamp, style: str) -> str:
    if style == "formal":
        return f"{ts.day} {MONTHS_ID[ts.month]} {ts.year} pukul {ts:%H.%M} WIB"
    if style == "singkatan":
        return f"{ts:%d/%m/%Y} jam {ts:%H.%M}"
    if style == "telegrafis":
        return f"{ts.day}/{ts.month} {ts:%H:%M}"
    return f"{ts.day} {MONTHS_EN[ts.month]} {ts.year} at {ts:%H:%M}"


def _segments(icu_in, icu_out, pre_device, start, stop, after_device, death_on_vent):
    if start is None:
        return [(icu_in, icu_out, pre_device)]
    segs = []
    if start > icu_in:
        segs.append((icu_in, start, pre_device))
    segs.append((max(start, icu_in), stop, "ventilator_invasif"))
    if not death_on_vent and stop < icu_out:
        mid = min(stop + pd.Timedelta(hours=6), icu_out)
        segs.append((stop, mid, after_device))
        if mid < icu_out:
            segs.append((mid, icu_out, "nasal_kanul"))
    return segs


def make_story(row, truth: bool) -> Story:
    # truth=True renders what happened; truth=False renders what the claim says (fabricated records).
    pre = row.alat_tertinggi if row.alat_tertinggi != "ventilator_invasif" else "nrm"
    dx = SURGERY_NAME.get(row.grup_operasi) or DX_NAME.get(row.dx3, "penyakit kritis")
    if truth:
        vent, start, stop = row.ventilasi, row.mulai_ventilasi, row.selesai_ventilasi
        death_on_vent = bool(row.meninggal_saat_ventilasi)
    else:
        vent, start, stop = True, row.ventilator_start_dttm, row.ventilator_stop_dttm
        death_on_vent = False
        if pd.isna(start):  # an intubation-only claim gets a made-up short intubation
            start = row.icu_masuk + pd.Timedelta(hours=1)
            stop = start + pd.Timedelta(hours=3)
    if not vent:
        start = stop = None
    icu_in, icu_out = row.icu_masuk, row.icu_keluar
    if vent:
        icu_in, icu_out = min(icu_in, start), max(icu_out, stop + (pd.Timedelta(0) if death_on_vent else pd.Timedelta(hours=2)))
    death = stop if death_on_vent else (row.tgl_pulang if row.meninggal else None)
    trach_at = start + (stop - start) * 0.6 if (truth and row.trakeostomi) else None
    return Story(icu_in, icu_out, _segments(icu_in, icu_out, pre, start, stop, "nrm", death_on_vent), bool(vent),
                 start, stop, death, death_on_vent, trach_at, dx, pre)


def device_at(story: Story, t: pd.Timestamp) -> str:
    for a, b, d in story.segments:
        if a <= t < b:
            return d
    return story.segments[-1][2]


class Writer:
    def __init__(self, rng: np.random.Generator, style: str):
        self.rng, self.style = rng, style
        self.mode = rng.choice(VENT_MODES)
        self.ett = rng.choice(["7.0", "7.5", "8.0"])
        self.fio2 = int(rng.choice([30, 35, 40, 50, 60]))
        self.peep = int(rng.choice([5, 5, 6, 8]))

    def say(self, kind: str, device: str | None = None, when: pd.Timestamp | None = None, **kw):
        names = DEVICE_NAME[self.style]
        variants = T[kind][self.style]
        text = variants[self.rng.integers(len(variants))]
        lo, hi = FLOW.get(device, (0, 0))
        fields = {"alat": names.get(device, ""), "mode": self.mode, "fio2": self.fio2, "peep": self.peep, "ett": self.ett,
                  "flow": int(self.rng.integers(lo, hi + 1)) if hi else "", "thn": int(self.rng.integers(2015, 2024)),
                  "waktu": fmt_time(when, self.style) if when is not None else ""}
        fields.update(kw)
        event = kind if kind in ("mulai", "selesai", "meninggal") else ""
        return text.format(**fields), device, KIND_LABEL[kind], event

    def status(self, device: str):
        kind = {"ventilator_invasif": "status_vent", "udara_ruang": "status_ra", "niv": "status_niv"}.get(device, "status_o2")
        return self.say(kind, device)

    def plain(self, part: str, dx: str = ""):
        options = FILLER[part]
        text = options[self.rng.integers(len(options))].format(dx=dx)
        return text[0].upper() + text[1:], None, None, ""


def render(story: Story, style: str, rng: np.random.Generator, discharge: pd.Timestamp, age: int) -> list[dict]:
    w = Writer(rng, style)
    docs = []

    def doc(kind, role, t, sentences):
        docs.append({"jenis": kind, "penulis_peran": role, "waktu_layanan": t, "kalimat": sentences})

    days = pd.date_range(story.icu_in.normalize(), story.icu_out.normalize(), freq="D")
    if len(days) > MAX_DAYS:
        days = days[:7].append(days[-7:])
    for k, day in enumerate(days):
        t = max(day + pd.Timedelta(minutes=int(rng.integers(7 * 60, 10 * 60))), story.icu_in + pd.Timedelta(minutes=30))
        if t < story.icu_out:
            dev = device_at(story, t)
            s = [w.plain("S"), w.status(dev)]
            if dev != "ventilator_invasif" and rng.random() < 0.35:
                s.append(w.say("disangkal", "ventilator_invasif"))
            if k == 0 and rng.random() < 0.15:
                daftar = ", ".join(DEVICE_NAME[style][d] for d in ("ventilator_invasif", "niv", "nrm", "nasal_kanul"))
                s.append(w.say("templat", "ventilator_invasif", daftar=daftar))
            if rng.random() < 0.05:
                s.append(w.say("riwayat", "ventilator_invasif"))
            s.append(w.plain("A", story.dx_text))
            s.append(w.plain("P"))
            if dev == "ventilator_invasif" and story.stop is not None and not story.death_on_vent:
                left = (story.stop - t) / pd.Timedelta(hours=1)
                if 12 < left < 36:
                    s.append(w.say("rencana_lepas", "ventilator_invasif"))
                elif left >= 36 and rng.random() < 0.15:
                    s.append(w.say("ditunda", "ventilator_invasif"))
            elif dev != "ventilator_invasif" and not story.vent and rng.random() < 0.25:
                s.append(w.say("rencana_intubasi", "ventilator_invasif"))
            doc("cppt", "dokter", t, s)
        t = day + pd.Timedelta(minutes=int(rng.integers(19 * 60, 22 * 60)))
        if story.icu_in <= t < story.icu_out:
            doc("catatan_perawat", "perawat", t, [w.status(device_at(story, t)), w.plain("N")])
    if story.vent:
        doc("laporan_tindakan", "dokter", story.start,
            [w.say("mulai", "ventilator_invasif", story.start), (("Tindakan berjalan lancar tanpa komplikasi."), None, None, "")])
        if story.trach_at is not None:
            doc("laporan_tindakan", "dokter", story.trach_at, [w.say("trakeostomi", "ventilator_invasif", story.trach_at)])
        if story.death_on_vent:
            doc("catatan_perawat", "perawat", story.stop, [w.say("meninggal", "ventilator_invasif", story.stop)])
        else:
            doc("catatan_perawat", "perawat", story.stop, [w.say("selesai", "nrm", story.stop), w.plain("N")])
    summary = [(f"Pasien usia {age} tahun dirawat dengan {story.dx_text}.", None, None, "")]
    if story.vent:
        summary.append((f"Selama perawatan ICU pasien menggunakan {DEVICE_NAME[style]['ventilator_invasif']} sejak "
                        f"{fmt_time(story.start, style)} sampai {fmt_time(story.stop, style)}.", "ventilator_invasif", "terpasang", ""))
    else:
        summary.append(w.say("disangkal", "ventilator_invasif"))
    if story.death is not None and not story.death_on_vent:
        summary.append((f"Pasien meninggal dunia pada {fmt_time(story.death, style)}.", None, None, ""))
    doc("resume_medis", "dokter", max(discharge, story.icu_out), summary)
    return sorted(docs, key=lambda d: d["waktu_layanan"])


def _quantile_sampler(table: dict, device: str, var: str):
    q = (table.get(device) or {}).get(var)
    if not q:
        return None
    xs = np.array([0.0] + [float(k) for k in q] + [1.0])
    ys = np.array(list(q.values()), float)
    ys = np.concatenate([[ys[0] - (ys[1] - ys[0])], ys, [ys[-1] + (ys[-1] - ys[-2])]])
    return xs, ys


VITAL_RANGE = {"spo2": (50, 100), "fio2": (21, 100), "peep": (0, 30), "rr_set": (0, 60), "rr_total": (0, 80)}


def vitals(shown: list, physiology: list, table: dict, rng: np.random.Generator, window: tuple) -> pd.DataFrame:
    # `shown` is the written device column and `physiology` drives the numbers, so cerdik-2 can write "ventilator" over a breathing patient.
    start, end = window
    hours = pd.date_range(start.ceil("h"), end, freq="h")
    if len(hours) == 0:
        return pd.DataFrame()
    if len(hours) > MAX_DAYS * 24:
        hours = hours[: 7 * 24].append(hours[-7 * 24:])
    dev_of = lambda segs, t: next((d for a, b, d in segs if a <= t < b), segs[-1][2])
    shown_dev = np.array([dev_of(shown, t) for t in hours])
    phys_dev = np.array([dev_of(physiology, t) for t in hours])
    out = {"waktu": hours, "alat": shown_dev}
    for var, (lo, hi) in VITAL_RANGE.items():
        col = np.full(len(hours), np.nan)
        level = rng.random()
        for dev in np.unique(phys_dev):
            m = phys_dev == dev
            sampler = _quantile_sampler(table, dev, var)
            fill = (table.get(dev) or {}).get("porsi_terisi", {}).get(var, 0.0)
            if sampler is None or fill == 0:
                continue
            u = np.clip(level + rng.normal(0, 0.18, m.sum()), 0, 1)
            vals = np.clip(np.round(np.interp(u, *sampler), 0), lo, hi)
            col[m] = np.where(rng.random(m.sum()) < fill, vals, np.nan)
        out[var] = col
    return pd.DataFrame(out)


def write_times(docs: list[dict], version: str, truth_stop: pd.Timestamp | None, habit: dict,
                discharge: pd.Timestamp, batch: pd.Timestamp | None, rng: np.random.Generator,
                backfill: bool = False, bulk: dict | None = None) -> list[pd.Timestamp]:
    # Honest notes follow the hospital's lag with a heavy late tail, cerdik-2 notes come after discharge or a day late, bulk notes in one evening.
    out = []
    for d in docs:
        t = d["waktu_layanan"]
        if d["jenis"] == "resume_medis":
            lag = pd.Timedelta(hours=min(float(np.exp(rng.normal(np.log(18), 1.0))), 240))
        else:
            lag = pd.Timedelta(minutes=float(np.exp(rng.normal(np.log(habit["lag_min"]), 0.5))))
            if rng.random() < habit["late_share"]:
                lag += pd.Timedelta(hours=min(float(np.exp(rng.normal(np.log(habit["late_h"]), 1.0))), 240))
        fabricated = version == "karangan" and (truth_stop is None or t >= truth_stop or d["jenis"] == "resume_medis")
        if fabricated and backfill:
            w = t + pd.Timedelta(minutes=int(rng.integers(12 * 60, 40 * 60)))
        elif fabricated:
            w = max(discharge, t) + pd.Timedelta(minutes=int(rng.integers(120, 72 * 60)))
        elif batch is not None and (version == "massal" or (bulk and (d["jenis"] == "resume_medis"
                                                                        or rng.random() < bulk.get(d["jenis"], 0.0)))):
            # Honest bulk-writing hospitals (a trap) batch every summary, some notes, and a few procedure reports.
            w = max(batch, t) + pd.Timedelta(minutes=int(rng.integers(0, 150)))
        else:
            w = t + lag
        out.append(w.round("s"))
    return out


def generate(c: pd.DataFrame, h: pd.DataFrame, icu_table: dict, seed: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    # Records exist for the ventilation-line population only, which is what AI 2 reads (TARGETS v2 bagian 6).
    rs = h.set_index("kode_rs")
    index = {sep: i for i, sep in enumerate(c.nomor_sep)}
    rows = np.flatnonzero(in_line_population(c))
    docs, sentences, vit, stories = [], [], [], []
    batch_of = {}
    for i in rows:
        row = c.iloc[i]
        style = rs.at[row.kode_rs, "gaya_tulis"]
        version = row.rme_versi
        truth = make_story(row, truth=True)
        told = truth if version == "jujur" else make_story(row, truth=False)
        text_seed, vital_seed = [seed, i, 1], [seed, i, 2]
        if version == "kloning" and row.sumber_kloning in index:
            j = index[row.sumber_kloning]
            src = c.iloc[j]
            shift = row.ventilator_start_dttm.normalize() - src.mulai_ventilasi.normalize()
            base = make_story(src, truth=True)
            told = Story(base.icu_in + shift, base.icu_out + shift, [(a + shift, b + shift, d) for a, b, d in base.segments],
                         True, base.start + shift, base.stop + shift, None, False, None, base.dx_text, base.pre_device)
            text_seed, vital_seed = [seed, j, 1], [seed, j, 2]
        rng_text = np.random.default_rng(text_seed)
        rendered = render(told, style, rng_text, row.tgl_pulang, int(row.umur))
        rng_misc = np.random.default_rng([seed, i, 3])
        batch = None
        bulk = None
        if rs.at[row.kode_rs, "jebakan"] == "tulis_massal_jujur":
            notes, reports = float(rs.at[row.kode_rs, "porsi_massal_catatan"]), float(rs.at[row.kode_rs, "porsi_massal_tindakan"])
            busy = rs.at[row.kode_rs, "porsi_hari_sibuk"] > 0 and rng_misc.random() < rs.at[row.kode_rs, "porsi_hari_sibuk"]
            bulk = {"cppt": 1.0 if busy else notes, "catatan_perawat": 1.0 if busy else notes, "laporan_tindakan": reports}
        if version == "massal" or bulk:
            key = (row.kode_rs, row.bulan)
            if key not in batch_of:
                # Bulk writing happens in one evening session just before the month's claims are submitted.
                month_end = (row.tgl_pulang + pd.offsets.MonthEnd(0)).normalize()
                day = month_end + pd.Timedelta(days=int(rng_misc.integers(1, 6)))
                batch_of[key] = day + pd.Timedelta(minutes=int(rng_misc.integers(19 * 60, 22 * 60)))
            batch = max(batch_of[key], row.tgl_pulang)
        habit = {"lag_min": float(rs.at[row.kode_rs, "jeda_tulis_menit"]), "late_share": float(rs.at[row.kode_rs, "porsi_catatan_telat"]),
                 "late_h": float(rs.at[row.kode_rs, "jeda_telat_jam"])}
        # Invented share of cerdik-2 perpetrators who backfill made-up notes a day later.
        backfill = version == "karangan" and rng_misc.random() < 0.4
        times = write_times(rendered, version, truth.stop if row.modus == "diperpanjang" else None, habit, row.tgl_pulang,
                            batch, rng_misc, backfill, bulk)
        if version == "karangan" and row.modus == "diperpanjang":
            # Only notes after the true extubation are rewritten; earlier ones stay honest.
            honest = render(truth, style, np.random.default_rng(text_seed), row.tgl_pulang, int(row.umur))
            keep = [d for d in honest if d["waktu_layanan"] < truth.stop and d["jenis"] != "laporan_tindakan"
                    and d["jenis"] != "resume_medis"]
            rewritten = [(d, t) for d, t in zip(rendered, times) if d["waktu_layanan"] >= truth.stop or d["jenis"] in ("laporan_tindakan", "resume_medis")]
            keep_times = write_times(keep, "jujur", None, habit, row.tgl_pulang, None, rng_misc)
            pairs = sorted(list(zip(keep, keep_times)) + rewritten, key=lambda x: x[0]["waktu_layanan"])
            rendered, times = [d for d, _ in pairs], [t for _, t in pairs]
        for k, (d, t) in enumerate(zip(rendered, times)):
            doc_id = f"{row.nomor_sep}-{k + 1:02d}"
            docs.append({"dokumen_id": doc_id, "nomor_sep": row.nomor_sep, "jenis": d["jenis"], "waktu_layanan": d["waktu_layanan"],
                         "waktu_tulis": t, "penulis_peran": d["penulis_peran"], "teks": " ".join(s[0] for s in d["kalimat"])})
            for n, (text, device, label, event) in enumerate(d["kalimat"]):
                if device:
                    sentences.append({"dokumen_id": doc_id, "nomor_sep": row.nomor_sep, "kalimat_ke": n, "teks": text,
                                      "alat": device, "asersi": label, "peristiwa": event, "gaya": style})
        shown, physiology = told.segments, truth.segments
        if version in ("karangan_konsisten", "massal", "kloning"):
            physiology = told.segments
        # A clone copies the source's sheet exactly, so its window is the shifted source stay.
        window = (told.icu_in, told.icu_out) if version == "kloning" else (min(told.icu_in, truth.icu_in), max(told.icu_out, truth.icu_out))
        v = vitals(shown, physiology, icu_table, np.random.default_rng(vital_seed), window)
        if len(v):
            v.insert(0, "nomor_sep", row.nomor_sep)
            vit.append(v)
        stories.append({"nomor_sep": row.nomor_sep, "rme_versi": version, "rme_ventilasi": told.vent,
                        "rme_mulai": told.start, "rme_selesai": told.stop, "gaya_tulis": style})
    docs = pd.DataFrame(docs)
    return docs, pd.DataFrame(sentences), pd.concat(vit, ignore_index=True), pd.DataFrame(stories)
