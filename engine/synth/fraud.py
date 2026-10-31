from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from engine.contracts import CARDIAC_GROUPS_NOT_MOVING
from engine.synth import grouper as G
from engine.synth.world import assign_group_and_tariff

MAIN_MODES = ("fiktif", "diperpanjang", "rme_meragukan")
# Candidates fixed before any engine exists, from which TEST draws and seals one of each (TARGETS v2 bagian 3 aturan 3).
HIDDEN_MODES = ("trakeostomi_fiktif", "sepsis_fiktif")
SECOND_LINES = ("dx_sekunder_fiktif", "wsd_fiktif")
# Sepsis and the secondary-diagnosis line share a mechanism (a fake secondary diagnosis), so they are never drawn together.
ALLOWED_PAIRS = (("trakeostomi_fiktif", "dx_sekunder_fiktif"), ("trakeostomi_fiktif", "wsd_fiktif"), ("sepsis_fiktif", "wsd_fiktif"))
# DEV practice modes sit outside the TEST candidates, so neither the audit agent nor AI 4 is tuned to a candidate.
DEV_HIDDEN_MODE = "kelas_naik"
DEV_SECOND_LINE = "akses_dialisis_fiktif"
TIER_ORDER = ("biasa", "cerdik_1", "cerdik_2", "cerdik_3")
DEVICE_PREFERENCE = {"niv": 2.0, "hfnc": 2.0, "nrm": 2.0, "nasal_kanul": 1.0, "udara_ruang": 0.5}  # v1: fakers pick patients on oxygen
RESPIRATORY_DX = ("J18", "J90", "J96", "J80")


@dataclass(frozen=True)
class Condition:
    name: str
    rs_share: tuple[float, float] = (0.06, 0.15)  # per main mode
    intensity: tuple[float, float] = (0.08, 0.30)
    tiers: dict = field(default_factory=lambda: {"biasa": 0.40, "cerdik_1": 0.35, "cerdik_2": 0.25})
    evidence_noise: float = 1.0
    late_note_factor: float = 1.0  # scales the invented late tail of honest notes
    busy_day_share: float = 0.0  # honest bulk writers deferring every note of a patient (sensitivity, Kasus sulit only)
    claim_share: float | None = None  # share of the ventilation-line population that is manipulated
    max_rs: int | None = None
    idrg: bool = False


CONDITIONS = {
    "dasar": Condition("dasar"),
    "kasus_sulit": Condition("kasus_sulit", evidence_noise=1.5, late_note_factor=2.0, busy_day_share=0.3,
                             tiers={"biasa": 0.15, "cerdik_1": 0.35, "cerdik_2": 0.30, "cerdik_3": 0.20}),
    "jarang": Condition("jarang", claim_share=0.005),
    "sering": Condition("sering", claim_share=0.10),
    "terkonsentrasi": Condition("terkonsentrasi", max_rs=5, intensity=(0.40, 0.60)),
    "idrg_tiruan": Condition("idrg_tiruan", idrg=True),
}


def line_value(cfg: G.GrouperConfig) -> int:
    return cfg.long_vent_min_hours or 96


def in_line_population(c: pd.DataFrame) -> np.ndarray:
    has_trigger = c.procedure.str.contains(r"96\.04|96\.7[012]", regex=True)
    return (c.cbg.str[:6].isin(["J-1-20", "J-1-02", "J-1-01"]) | has_trigger).to_numpy()


def eligible_fictitious(c: pd.DataFrame) -> np.ndarray:
    # Truth-side definition (TARGETS bagian 6): medical ICU patient with a target diagnosis, whatever the group.
    return (c.segmen == "medis_sasaran").to_numpy()


def eligible_prolonged(c: pd.DataFrame, cfg: G.GrouperConfig) -> np.ndarray:
    line = line_value(cfg)
    true_h = c.jam_ventilasi_benar.to_numpy()
    return (c.procedure.str.contains("96.71", regex=False).to_numpy()
            & (true_h >= line - 24) & (true_h < line)
            & ~c.grup_operasi.isin(CARDIAC_GROUPS_NOT_MOVING).to_numpy())


def assign_roles(rng: np.random.Generator, h: pd.DataFrame, cond: Condition, hidden: str | None,
                 second: str | None) -> pd.DataFrame:
    r = h[["kode_rs", "kelas_rs", "jebakan"]].copy()
    r["modus"], r["tingkat"], r["intensitas"] = "", "", 0.0
    r["modus_tersembunyi"], r["intensitas_tersembunyi"] = "", 0.0
    r["garis_kedua"], r["intensitas_garis_kedua"] = "", 0.0
    # Perpetrators come from non-trap hospitals, one role each, so every flag maps to exactly one answer.
    free = list(rng.permutation(r.index[r.jebakan == ""].to_numpy()))
    if cond.max_rs:
        counts = [2, 2, 1][: len(MAIN_MODES)]
    else:
        counts = [int(round(rng.uniform(*cond.rs_share) * len(r))) for _ in MAIN_MODES]
    for mode, k in zip(MAIN_MODES, counts):
        idx = [free.pop() for _ in range(k)]
        r.loc[idx, "modus"] = mode
        r.loc[idx, "intensitas"] = rng.uniform(*cond.intensity, k)
        tiers = {"kloning": 0.5, "massal": 0.5} if mode == "rme_meragukan" else cond.tiers
        r.loc[idx, "tingkat"] = _spread_tiers(rng, r.loc[idx, "kelas_rs"], tiers)
    # Hidden mode (T17) and second line (T20) go to class A-C hospitals, where a year holds enough claims to judge them.
    def take(k: int) -> list:
        picked = [i for i in free if r.at[i, "kelas_rs"] != "D"][:k]
        for i in picked:
            free.remove(i)
        return picked

    if hidden:
        idx = take(int(rng.integers(4, 7)))
        r.loc[idx, "modus_tersembunyi"] = hidden
        r.loc[idx, "intensitas_tersembunyi"] = rng.uniform(0.25, 0.50, len(idx))
    if second:
        idx = take(int(rng.integers(6, 11)))
        r.loc[idx, "garis_kedua"] = second
        r.loc[idx, "intensitas_garis_kedua"] = rng.uniform(0.10, 0.30, len(idx))
    return r


def _spread_tiers(rng: np.random.Generator, kelas: pd.Series, tiers: dict) -> np.ndarray:
    # Tiers keep their shares but are interleaved along hospital size, so no tier lands only on tiny hospitals.
    k = len(kelas)
    shares = np.array(list(tiers.values()))
    counts = np.floor(shares * k).astype(int)
    for i in rng.choice(len(tiers), k - counts.sum(), replace=False, p=shares):
        counts[i] += 1
    names, pos = [], []
    for name, n in zip(tiers, counts):
        names += [name] * n
        pos += list((np.arange(n) + rng.random()) / max(n, 1))
    deck = np.array(names, object)[np.argsort(pos)]
    order = np.lexsort((rng.random(k), kelas.map({"A": 0, "B": 1, "C": 2, "D": 3}).to_numpy()))
    out = np.empty(k, object)
    out[order] = deck
    return out


def scale_to_claim_share(r: pd.DataFrame, s: pd.DataFrame, share: float, cfg: G.GrouperConfig) -> pd.DataFrame:
    elig = {
        "fiktif": eligible_fictitious(s) & ~s.ventilasi.to_numpy(),
        "diperpanjang": eligible_prolonged(s, cfg),
        "rme_meragukan": in_line_population(s),
    }
    per_rs = {m: pd.Series(e, index=s.index).groupby(s.kode_rs).sum() for m, e in elig.items()}
    expected = sum(per_rs[m].reindex(r.kode_rs).fillna(0).to_numpy() * r.intensitas.where(r.modus == m, 0).to_numpy()
                   for m in MAIN_MODES).sum()
    r = r.copy()
    r["intensitas"] = np.clip(r.intensitas * share * in_line_population(s).sum() / max(expected, 1), 0, 0.95)
    return r


def adapt(role: pd.Series, rng: np.random.Generator) -> pd.Series:
    # After a caught audit a hospital cuts back, switches main mode, or hides better (task 630).
    r = role.copy()
    u = rng.random()
    if u < 0.5 or not r.modus:
        r["intensitas"] = r.intensitas * rng.uniform(0.2, 0.5)
    elif u < 0.8 and r.modus in ("fiktif", "diperpanjang"):
        r["modus"] = "diperpanjang" if r.modus == "fiktif" else "fiktif"
    elif r.tingkat in TIER_ORDER[:-1]:
        r["tingkat"] = TIER_ORDER[TIER_ORDER.index(r.tingkat) + 1]
    else:
        r["intensitas"] = r.intensitas * rng.uniform(0.2, 0.5)
    return r


def minutes(hours: np.ndarray) -> pd.TimedeltaIndex:
    # Whole minutes keep the datetime64[us] columns lossless (pandas 3).
    return pd.to_timedelta(np.round(hours * 60), unit="min")


def _add_code(c: pd.DataFrame, rows: np.ndarray, code: str, drop: str | None = None) -> None:
    for i in np.flatnonzero(rows):
        codes = set(c.at[i, "prosedur"]) - ({drop} if drop else set())
        c.at[i, "prosedur"] = sorted(codes | {code})


def _add_secondary(c: pd.DataFrame, rows: np.ndarray, code3: str, full: str) -> None:
    for i in np.flatnonzero(rows):
        c.at[i, "dx_sekunder3"] = sorted(set(c.at[i, "dx_sekunder3"]) | {code3})
        c.at[i, "diagnosa"] = c.at[i, "diagnosa"] + "#" + full


def _vent_rent(style: np.ndarray, hours: np.ndarray, cls: np.ndarray) -> np.ndarray:
    return np.select([style == "per_jam", style == "per_hari"], [hours * 60_000, np.ceil(hours / 24) * 1_440_000], 0) * cls


def _extend_icu(c: pd.DataFrame, rows: np.ndarray, start: pd.Series, hours: np.ndarray) -> None:
    # Keep icu_los x 24 >= recorded hours, and stretch the stay when the new ICU days run past discharge.
    need = np.ceil(((start - c.icu_masuk) / pd.Timedelta(hours=1) + hours + 2) / 24).to_numpy()
    new_los = np.where(rows, np.maximum(c.icu_los.to_numpy(), need), c.icu_los.to_numpy()).astype(int)
    extra_days = new_los - c.icu_los.to_numpy()
    c["icu_los"] = new_los
    out = c.icu_masuk + pd.to_timedelta(new_los * 24, unit="h")
    late = rows & (out > c.tgl_pulang).to_numpy()
    c.loc[late, "tgl_pulang"] = out[late] + pd.Timedelta(hours=6)
    c["lama_rawat"] = (c.tgl_pulang.dt.normalize() - c.tgl_masuk.dt.normalize()).dt.days.astype(int)
    c["tarif_rs_rawat_intensif"] += (extra_days * 2_500_000).astype(np.int64)


def inject(s: pd.DataFrame, h: pd.DataFrame, roles: pd.DataFrame, cfg: G.GrouperConfig,
           rng: np.random.Generator) -> pd.DataFrame:
    c = s.copy()
    n = len(c)
    c["cbg_jujur"], c["tarif_jujur"] = c.cbg, c.tarif_ina_cbg
    c["dimanipulasi"], c["modus"], c["tingkat"], c["varian"] = False, "", "", ""
    c["rme_versi"] = "jujur"
    r = roles.set_index("kode_rs").loc[c.kode_rs].reset_index()
    hs = h.set_index("kode_rs").loc[c.kode_rs].reset_index()
    mode, tier, inten = r.modus.to_numpy(), r.tingkat.to_numpy(), r.intensitas.to_numpy()
    style = hs.gaya_sewa.to_numpy()
    cls = c.kelas_rs.map({"A": 1.4, "B": 1.2, "C": 1.0, "D": 0.8}).to_numpy() * hs.pengali_biaya.to_numpy()
    vent = c.ventilasi.to_numpy()
    line_pop = in_line_population(c)
    u = rng.random((n, 8))

    # Dubious-RME claims are fictitious claims too, papered over with cloned or bulk-written notes.
    pool = eligible_fictitious(c) & ~vent
    w = c.alat_tertinggi.map(DEVICE_PREFERENCE).to_numpy() * pool
    mean_w = pd.Series(w, index=c.index).groupby(c.kode_rs).transform("sum") / np.maximum(
        pd.Series(pool, index=c.index).groupby(c.kode_rs).transform("sum"), 1)
    p_fake = inten * w / np.maximum(mean_w.to_numpy(), 1e-9)
    n_line_rs = pd.Series(line_pop, index=c.index).groupby(c.kode_rs).transform("sum").to_numpy()
    n_pool_rs = pd.Series(pool, index=c.index).groupby(c.kode_rs).transform("sum").to_numpy()
    p_dubious = np.where(pool, inten * n_line_rs / np.maximum(n_pool_rs, 1), 0)
    fake = pool & (((mode == "fiktif") & (u[:, 0] < p_fake)) | ((mode == "rme_meragukan") & (u[:, 0] < p_dubious)))
    intub_only = fake & (mode == "fiktif") & (u[:, 1] < 0.25)
    vent_fake = fake & ~intub_only
    smart = fake & ((tier != "biasa") | (mode == "rme_meragukan"))
    fake_h = np.round(rng.uniform(24, 72, n)).astype(int)
    fake_start = c.icu_masuk + minutes(rng.uniform(0.5, 6, n))
    c["sumber_kloning"] = ""
    clone = vent_fake & (tier == "kloning")
    if clone.any():
        _pick_clone_sources(c, clone, fake_h, fake_start, rng)
    _add_code(c, vent_fake, "96.71")
    _add_code(c, intub_only | (vent_fake & (u[:, 2] < np.where(smart, 0.9, hs.p_kode_intubasi.to_numpy()))), "96.04")
    _add_code(c, smart & (u[:, 3] < 0.7), "89.65")
    c.loc[vent_fake, "ventilator_hour"] = fake_h[vent_fake]
    c.loc[vent_fake, "ventilator_use_ind"] = 1
    c.loc[vent_fake, "ventilator_start_dttm"] = fake_start[vent_fake]
    c.loc[vent_fake, "ventilator_stop_dttm"] = (fake_start + pd.to_timedelta(fake_h, unit="h"))[vent_fake]
    _extend_icu(c, vent_fake & (smart | (u[:, 4] < 0.5)), fake_start, fake_h)
    sv = vent_fake & smart
    c.loc[sv, "tarif_rs_sewa_alat"] += _vent_rent(style, fake_h, cls)[sv].round(-2).astype(np.int64)
    c.loc[sv, "tarif_rs_alkes"] += np.round(1_500_000 * cls[sv], -2).astype(np.int64)
    c.loc[smart, "tarif_rs_prosedur_non_bedah"] += np.round(1_200_000 * cls[smart], -2).astype(np.int64)
    c.loc[fake, "modus"] = np.where(mode[fake] == "rme_meragukan", "rme_meragukan", "fiktif")
    c.loc[fake, "varian"] = np.where(intub_only[fake], "intubasi_saja", "ventilasi")
    c.loc[fake, "tingkat"] = tier[fake]
    c.loc[fake, "rme_versi"] = np.select(
        [mode[fake] == "rme_meragukan", tier[fake] == "cerdik_2", tier[fake] == "cerdik_3"],
        [tier[fake], "karangan", "karangan_konsisten"], "jujur")

    # Measured against the grouper's hour line, which the iDRG mock moves.
    line = line_value(cfg)
    # Death on the ventilator pins its end, so those patients are skipped and the rest picked more often.
    elig = eligible_prolonged(c, cfg)
    alive = elig & ~c.meninggal_saat_ventilasi.to_numpy()
    by_rs = lambda x: pd.Series(x, index=c.index).groupby(c.kode_rs).transform("sum").to_numpy()
    p_long = np.minimum(1.0, inten * by_rs(elig) / np.maximum(by_rs(alive), 1))
    long_ = (mode == "diperpanjang") & alive & (u[:, 5] < p_long)
    new_h = rng.integers(line, line + 9, n)
    old_h = c.ventilator_hour.to_numpy()
    _add_code(c, long_ & (new_h >= 96), "96.72", drop="96.71")
    c.loc[long_, "ventilator_hour"] = new_h[long_]
    c.loc[long_, "ventilator_stop_dttm"] = (c.ventilator_start_dttm + pd.to_timedelta(new_h, unit="h"))[long_]
    smart_l = long_ & (tier != "biasa")
    _extend_icu(c, long_ & (smart_l | (u[:, 6] < 0.5)), c.ventilator_start_dttm, new_h)
    c.loc[smart_l, "tarif_rs_sewa_alat"] += (_vent_rent(style, new_h, cls) - _vent_rent(style, old_h, cls))[smart_l].round(-2).astype(np.int64)
    c.loc[smart_l, "tarif_rs_laboratorium"] += np.round(360_000 * cls[smart_l], -2).astype(np.int64)
    c.loc[long_, "modus"], c.loc[long_, "tingkat"] = "diperpanjang", tier[long_]
    c.loc[long_, "rme_versi"] = np.select([tier[long_] == "cerdik_2", tier[long_] == "cerdik_3"],
                                          ["karangan", "karangan_konsisten"], "jujur")

    hidden = _inject_hidden(c, r, u, rng, cfg)
    second = _inject_second_line(c, r, u, rng)

    changed = fake | long_ | hidden | second
    c.loc[changed, "procedure"] = c.loc[changed, "prosedur"].map("#".join)
    c.loc[changed, "dimanipulasi"] = True
    sub = assign_group_and_tariff(c.loc[changed].copy(), cfg)
    c.loc[changed, ["cbg", "tarif_ina_cbg"]] = sub[["cbg", "tarif_ina_cbg"]]
    # Perpetrators only manipulate when it pays, so unprofitable manipulations roll back to the honest claim.
    undo = changed & (c.tarif_ina_cbg <= c.tarif_jujur).to_numpy()
    c.loc[undo, s.columns] = s.loc[undo, s.columns]
    c.loc[undo, ["dimanipulasi", "modus", "tingkat", "varian", "rme_versi", "sumber_kloning"]] = [False, "", "", "", "jujur", ""]
    c["selisih_rupiah"] = (c.tarif_ina_cbg - c.tarif_jujur).astype(np.int64)
    c["bulan"] = c.tgl_pulang.dt.month
    return c


def _pick_clone_sources(c: pd.DataFrame, clone: np.ndarray, fake_h: np.ndarray, fake_start: pd.Series,
                        rng: np.random.Generator) -> None:
    # A clone takes over a real ventilated patient's hours and time of day (24-72 h, same hospital if possible), shifted by whole days.
    true_h = c.jam_ventilasi_benar.to_numpy()
    src = np.flatnonzero(c.ventilasi.to_numpy() & (true_h >= 24) & (true_h <= 72) & ~c.meninggal_saat_ventilasi.to_numpy()
                         & c.procedure.str.contains("96.71", regex=False).to_numpy())
    by_rs = pd.Series(src).groupby(c.kode_rs.to_numpy()[src]).apply(list).to_dict()
    for i in np.flatnonzero(clone):
        j = int(rng.choice(by_rs.get(c.kode_rs.iat[i]) or src))
        start = c.icu_masuk.iat[i].normalize() + (c.mulai_ventilasi.iat[j] - c.mulai_ventilasi.iat[j].normalize())
        if start < c.icu_masuk.iat[i]:
            start += pd.Timedelta(days=1)
        fake_start.iat[i] = start
        fake_h[i] = c.ventilator_hour.iat[j]
        c.at[i, "sumber_kloning"] = c.nomor_sep.iat[j]


def _inject_hidden(c: pd.DataFrame, r: pd.DataFrame, u: np.ndarray, rng: np.random.Generator,
                   cfg: G.GrouperConfig) -> np.ndarray:
    n = len(c)
    hm = r.modus_tersembunyi.to_numpy()
    pick = (u[:, 7] < r.intensitas_tersembunyi.to_numpy()) & (c.modus == "").to_numpy()
    done = np.zeros(n, bool)
    if (hm == "trakeostomi_fiktif").any():
        elig = np.array(["96.72" in p and not set(p) & cfg.trach_codes for p in c.prosedur])
        rows = (hm == "trakeostomi_fiktif") & elig & pick
        _add_code(c, rows, "31.1")
        done |= rows
    if (hm == "sepsis_fiktif").any():
        elig = in_line_population(c) & (~c.cbg.str.endswith("-III") & (c.dx3 != "A41")
                                         & ~c.dx_sekunder3.map(lambda d: "A41" in d)).to_numpy()
        rows = (hm == "sepsis_fiktif") & elig & pick
        _add_secondary(c, rows, "A41", "A41.9")
        done |= rows
    if (hm == DEV_HIDDEN_MODE).any():
        rows = (hm == DEV_HIDDEN_MODE) & in_line_population(c) & (c.kelas_rawat > 1).to_numpy() & pick
        c.loc[rows, "kelas_rawat"] = 1
        done |= rows
    c.loc[done, "modus"], c.loc[done, "tingkat"] = hm[done], "biasa"
    return done


def _inject_second_line(c: pd.DataFrame, r: pd.DataFrame, u: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    sl, si = r.garis_kedua.to_numpy(), r.intensitas_garis_kedua.to_numpy()
    pick = rng.random(len(c)) < si
    rows = np.zeros(len(c), bool)
    if (sl == "dx_sekunder_fiktif").any():
        elig = (~c.cbg.str.endswith("-III") & ~c.dx_sekunder3.map(lambda d: "N17" in d)).to_numpy()
        rows = (sl == "dx_sekunder_fiktif") & elig & pick & (c.modus == "").to_numpy()
        _add_secondary(c, rows, "N17", "N17.9")
    if (sl == "wsd_fiktif").any():
        elig = (c.segmen != "operasi").to_numpy() & ~c.ventilasi.to_numpy() & c.dx3.isin(RESPIRATORY_DX).to_numpy()
        rows = (sl == "wsd_fiktif") & elig & pick & (c.modus == "").to_numpy()
        _add_code(c, rows, "34.04")
    if (sl == DEV_SECOND_LINE).any():
        elig = (c.dx3 == "N18").to_numpy() & (c.segmen != "operasi").to_numpy()
        rows = (sl == DEV_SECOND_LINE) & elig & pick & (c.modus == "").to_numpy()
        _add_code(c, rows, "38.95")
    c.loc[rows, "modus"], c.loc[rows, "tingkat"] = sl[rows], "biasa"
    return rows
