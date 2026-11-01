import json
import time
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from engine import MODEL_VERSION
from engine import ai1 as A1
from engine import ai2 as B2
from engine import ai2_fast as F2
from engine import ai3 as A3
from engine import stats as S
from engine.contracts import TRIGGER_CODES, RmeReading, split_codes
from engine.data import LAB, ROOT
from engine.line_config import line_id
from engine.synth import grouper as G

SOURCE = "mesin_dev"
FILES = {
    "ai1": LAB / "ai1-dev" / "ai1_dev.json",
    "skor": LAB / "ai1-dev" / "skor_luar_lipatan_dev.parquet",
    "kata_kunci": LAB / "ai2-dev" / "kata_kunci_per_klaim.parquet",
    "lapis_cepat": LAB / "ai2-dev" / "lapis_cepat_per_klaim.parquet",
    "fisiologi": LAB / "ai2-dev" / "fisiologi_per_klaim.parquet",
    "fisiologi_jam": LAB / "ai2-dev" / "fisiologi_per_jam_dev.parquet",
    "fisiologi_laporan": LAB / "ai2-dev" / "fisiologi_laporan.json",
    "asersi": LAB / "ai2-dev" / "asersi_per_klaim_embedding_embedding_ngram.parquet",
    "bacaan_llm": LAB / "ai2-dev" / "bacaan_llm.jsonl",
    "bacaan_ulang": LAB / "ai2-dev" / "bacaan_llm_ulang.jsonl",
    "ai3_contoh": LAB / "ai3-dev" / "contoh_ulangan0.json",
    "ai3_simulasi": LAB / "ai3-dev" / "simulasi_adaptasi_laporan.json",
    "ai3_beban": LAB / "ai3-dev" / "beban_rs_jujur.json",
    "ai3_urutan": LAB / "ai3-dev" / "dasar_urutan_laporan.json",
    "ai4": LAB / "ai4-dev" / "ai4_dev.json",
    "ai4_idrg": LAB / "ai4-dev" / "ai4_idrg.json",
    "ai4_kenyataan": LAB / "ai4-kenyataan" / "hasil.json",
    "garis": LAB / "garis-dev" / "garis_dev.json",
}
# Answer-key columns stored beside the detector outputs; the app must never show them.
KEY_COLUMNS = ["rme_versi", "jebakan", "meragukan", "lapis", "ventilasi_benar", "rme_ventilasi", "rme_jam", "dimanipulasi"]
LLM_FIELDS = ("verdict", "source", "quotes_verified", "reasons", "hours", "reading", "total_ms", "prompt_tokens")

MONTHS = ("Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember")
MON = tuple(m[:3] for m in MONTHS)
MODE_LABEL = {"fiktif": "ventilasi fiktif", "diperpanjang": "ventilasi diperpanjang", "rme_meragukan": "RME meragukan"}
DISCHARGE = {1: "Sehat", 2: "Dirujuk", 3: "Pulang paksa", 4: "Meninggal", 5: "Lain-lain"}
DOC_NAMES = {"cppt": "CPPT", "catatan_perawat": "Catatan perawat", "laporan_tindakan": "Laporan tindakan", "resume_medis": "Resume medis"}
DEVICE = {"ventilator_invasif": "ventilator invasif", "niv": "NIV", "hfnc": "HFNC", "nrm": "NRM", "nasal_kanul": "nasal kanul",
          "udara_ruang": "udara ruang", "tidak_jelas": "tidak jelas"}
LAYER_TEXT = {"kata_kunci": "Kata kunci tidak menemukan ventilasi", "asersi": "Model asersi: tanpa ventilasi invasif",
              "klaim_vs_lembar": "Lembar tanda vital jauh di bawah klaim", "teks_vs_lembar": "Lembar tanda vital jauh di bawah teks RME"}
COST_CHIP = {"prosedur_non_bedah": "non bedah", "prosedur_bedah": "bedah", "rawat_intensif": "rawat intensif", "laboratorium": "lab",
             "tenaga_ahli": "tenaga ahli", "pelayanan_darah": "darah"}
LAYER_CHIP = {"kata_kunci": "kata kunci", "asersi": "asersi", "klaim_vs_lembar": "lembar vital", "teks_vs_lembar": "teks vs lembar"}
HELD_TEXT = {"asal_usul": "asal-usul catatan meragukan", "jejak_waktu": "dokumen kunci ditulis terlambat",
             "fisiologi": "angka lembar tanda vital tidak mendukung", "asersi": "model asersi berbeda pendapat"}
CODE_NAMES = {**A1.CODE_NAMES, "96.71": "ventilasi kurang dari 96 jam", "96.04": "intubasi", "38.95": "kateter vena untuk dialisis",
              "E87": "gangguan elektrolit"}
STATUS_FROM_DECISION = {"minta_klarifikasi": "diklarifikasi", "masukkan_rencana_audit": "diaudit", "ajukan_audit": "diaudit", "setujui_audit": "diaudit"}
TEMPLATES = {
    ("AI 1", "fiktif"): ["{rs} mengajukan {diakui} garis ventilator selama 12 bulan; bukti di klaim hanya mendukung {wajar} (rentang {wajar_bawah}–{wajar_atas}).",
                         "Kelebihan {kelebihan} setara perkiraan {rupiah}.", "Dari {dibaca} teratas, {tidak_mendukung} ditahan bacaan RME."],
    ("AI 1", "diperpanjang"): ["{rs} mencatat {diakui} dengan ventilasi 96 jam atau lebih; bukti di klaim hanya mendukung {wajar} (rentang {wajar_bawah}–{wajar_atas}).",
                               "Kelebihan {kelebihan} setara perkiraan {rupiah}.", "Dari {dibaca} teratas, {tidak_mendukung} ditahan bacaan RME."],
    ("AI 2", "fiktif"): ["{rs} lolos pemeriksaan klaim: diakui {diakui}, wajar {wajar}.",
                         "Bacaan RME menahan {ditahan} dari {dibaca} klaim layak.", "Nilai yang dipertaruhkan {rupiah}; isinya baru bisa dipastikan lewat audit."],
    ("AI 2", "diperpanjang"): ["{rs} mencatat {diakui} dengan ventilasi 96 jam atau lebih, wajar {wajar}.",
                               "Bacaan RME mencatat jam di bawah garis 96 jam pada {ditahan} dari {dibaca} klaim.",
                               "Nilai yang dipertaruhkan {rupiah}; isinya baru bisa dipastikan lewat audit."],
    ("AI 2", "rme_meragukan"): ["{rs} lolos pemeriksaan klaim: diakui {diakui}, wajar {wajar}.",
                                "Catatan RME {kembar} nyaris identik (median kemiripan {kemiripan}) dan {serentak} ditulis dalam satu sesi.",
                                "Nilai yang dipertaruhkan {rupiah}; isinya baru bisa dipastikan lewat audit."],
}


def num(x: float, digits: int = 0) -> str:
    # Half-up from the decimal text, so 2,15 reads 2,2 as in the reports rather than the binary 2,1.
    q = Decimal(str(float(x))).quantize(Decimal(1).scaleb(-digits), ROUND_HALF_UP)
    return f"{q:,.{digits}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def rp(x: float) -> str:
    return f"Rp{num(x)}"


def miliar(x: float, digits: int = 2) -> str:
    return f"Rp{num(x / 1e9, digits)} miliar"


def juta(x: float, digits: int = 1) -> str:
    return f"Rp{num(x / 1e6, digits)} juta"


def q_text(q: float) -> str:
    return "q < 0,001" if q < 0.001 else f"q = {num(q, 3 if q < 0.01 else 2)}"


def short_rp(x: float) -> str:
    return f"Rp{num(x / 1e9, 1)} M" if x >= 1e8 else f"Rp{num(x / 1e6)} jt"


def billions(x: float) -> str:
    return "0" if x == 0 else num(x / 1e9, 1)


def short_range(lo: float, hi: float) -> str:
    return f"rentang {billions(lo)}–{billions(hi)} M" if hi >= 1e8 else f"rentang {num(lo / 1e6)}–{num(hi / 1e6)} jt"


def day_month(t: pd.Timestamp) -> str:
    return f"{t.day:02d} {MON[t.month - 1]}"


def stay(a: pd.Timestamp, b: pd.Timestamp) -> str:
    return f"{a.day:02d}–{day_month(b)} {b.year}" if a.month == b.month else f"{day_month(a)}–{day_month(b)} {b.year}"


def stamp(t: pd.Timestamp) -> str:
    return f"{t:%d-%m-%Y %H.%M}"


def confidence(q: float) -> str:
    # Bands follow the design examples: q 0,004 and 0,02 read "sedang", q 0,03 and 0,04 read "lemah".
    return "kuat" if q < 0.001 else "sedang" if q < 0.025 else "lemah"


def count_range(p: np.ndarray) -> tuple[int, int]:
    # 95% range of the supported-claim count from the exact Poisson-binomial sum of AI 1 probabilities.
    dist = np.ones(1)
    for x in p:
        dist = np.convolve(dist, (1 - x, x))
    cdf = dist.cumsum()
    return int(np.searchsorted(cdf, 0.025)), int(np.searchsorted(cdf, 0.975))


def nice_max(x: float) -> float:
    step = next(s for s in (0.1e9, 0.25e9, 0.5e9, 1e9, 2e9, 5e9) if x / s <= 5)
    return float(np.ceil(x / step) * step)


def jitter(i: int) -> float:
    return 0.15 + 0.7 * ((i * 0.6180339887) % 1)


def histogram(p: np.ndarray) -> list[int]:
    counts = np.histogram(p, bins=10, range=(0, 1))[0]
    return [int(round(100 * x / max(len(p), 1))) for x in counts]


def read_jsonl(path) -> dict[str, dict]:
    if not path.exists():
        return {}
    return {r["nomor_sep"]: {k: r.get(k) for k in LLM_FIELDS} for r in map(json.loads, path.open())}


def latest_decisions(rows: list[dict], kind: str) -> dict[str, str]:
    return {r["objek_id"]: r["keputusan"] for r in rows if r["objek_jenis"] == kind and r["keputusan"] != "koreksi"}


class Dev:
    def __init__(self, engine: Any):
        missing = [str(p) for p in FILES.values() if not p.exists()]
        if missing:
            raise FileNotFoundError(f"keluaran mesin DEV belum ada: {', '.join(missing)}")
        self.engine = engine
        self.updated = datetime.fromtimestamp(max(p.stat().st_mtime for p in FILES.values()))
        js = lambda k: json.loads(FILES[k].read_text())
        self.ai1, self.ai4, self.idrg, self.lines_test = js("ai1"), js("ai4"), js("ai4_idrg"), js("garis")
        self.reality = js("ai4_kenyataan")["reguler"]
        self.ai3 = {k: js(f"ai3_{k}") for k in ("contoh", "simulasi", "beban", "urutan")}
        self.physio_report = js("fisiologi_laporan")
        self.line_config = {x["id"]: x for x in json.loads((ROOT / "config" / "garis.json").read_text())["garis"]}

        c = self.c = engine.claims
        self.h = engine.hospitals
        self.p = pd.read_parquet(FILES["skor"]).set_index("nomor_sep").reindex(c.index)
        self.codes = A1.codes(c)
        self.line = A1.in_line(c)
        y_f, elig_f = A1.has_trigger(c), A1.eligible_fictitious(c)
        win, y_p = A1.prolonged_window(c), (c.ventilator_hour >= A1.GARIS).to_numpy()
        n_f = pd.Series(elig_f, index=c.index).groupby(c.kode_rs).sum()
        n_p = pd.Series(A1.eligible_prolonged(c), index=c.index).groupby(c.kode_rs).sum()
        # Same exact test the AI 1 run used on its stored out-of-fold scores, so peers and assessable counts match ai1_dev.json.
        self.ai1_modes = {
            "fiktif": {"pop": elig_f, "y": y_f, "p": self.p.p_fiktif.to_numpy(), "delta": "fiktif",
                       "table": S.per_rs_test(c.kode_rs, y_f.astype(int), self.p.p_fiktif.to_numpy(), elig_f, n_f)},
            "diperpanjang": {"pop": win, "y": y_p, "p": self.p.p_panjang.fillna(0).to_numpy(), "delta": "diperpanjang",
                             "table": S.per_rs_test(c.kode_rs, y_p.astype(int), self.p.p_panjang.fillna(0).to_numpy(), win, n_p)},
        }

        self.kw = pd.read_parquet(FILES["kata_kunci"])
        self.fast = pd.read_parquet(FILES["lapis_cepat"]).drop(columns=KEY_COLUMNS, errors="ignore")
        self.sheet = pd.read_parquet(FILES["fisiologi"]).drop(columns=KEY_COLUMNS, errors="ignore")
        self.vent = pd.read_parquet(FILES["asersi"]).ventilasi
        pop = self.kw.index
        kw, sheet, fast = self.kw.reindex(pop), self.sheet.reindex(pop), self.fast.reindex(pop)
        billed = self.codes.reindex(pop).map(lambda x: bool(x & (B2.VENT_CODES | {"96.04"})))
        # Same indicators as ai2_dev.mode_layers; text hours come from the keyword reader, never from the key.
        self.layers = pd.DataFrame({"kata_kunci": kw.verdict.eq("tidak_mendukung"), "asersi": billed & self.vent.reindex(pop).eq("tidak"),
                                    "klaim_vs_lembar": sheet.klaim_vs_lembar.fillna(False).astype(bool),
                                    "teks_vs_lembar": (kw.jam >= B2.SHEET_MIN_HOURS) & (sheet.lembar < B2.SHEET_SHARE * kw.jam),
                                    "kloning": fast.kloning.fillna(False).astype(bool), "tulis_massal": fast.tulis_massal.fillna(False).astype(bool)},
                                   index=pop)
        cc = c.loc[pop]
        self.pools = {"fiktif": cc.index[A1.eligible_fictitious(cc)], "diperpanjang": cc.index[A1.prolonged_window(cc)], "rme_meragukan": pop}
        count = lambda mask: pd.Series(mask, index=c.index).groupby(c.kode_rs).sum()
        eligible = {"fiktif": n_f, "diperpanjang": n_p, "rme_meragukan": count(self.line)}
        self.ai2_modes = F2.mode_flags(self.layers, self.pools, c.kode_rs, eligible)

        self.llm = read_jsonl(FILES["bacaan_llm"])
        self.retried = read_jsonl(FILES["bacaan_ulang"])
        hourly = pd.read_parquet(FILES["fisiologi_jam"])
        self.hourly = hourly
        self.hourly_at = hourly.groupby("nomor_sep", sort=False).indices
        self._profiles: dict[str, dict] = {}
        self.flagged = self._flagged()

    # ---------- shared pieces ----------

    def hospital(self, rs: str) -> dict:
        h = self.h.loc[rs]
        return {"kelas": h.kelas_rs, "kepemilikan": h.kepemilikan.capitalize(), "regional": int(h.regional)}

    def row_text(self, rs: str) -> str:
        h = self.hospital(rs)
        return f"Kelas {h['kelas']} {h['kepemilikan']}, Regional {h['regional']}"

    def rs_mask(self, rs: str) -> np.ndarray:
        return (self.c.kode_rs == rs).to_numpy()

    def deltas(self, rows: np.ndarray, mode: str) -> np.ndarray:
        return A1.tariff_deltas(self.c, self.h.reset_index(), "fiktif" if mode == "rme_meragukan" else mode, rows)

    def ai2_claims(self, rs: str, mode: str) -> pd.Index:
        pool = self.pools[mode]
        mine = pool[(self.c.kode_rs.reindex(pool) == rs).to_numpy()]
        cols = [x for x in F2.MODE_LAYERS[mode] if x in self.layers]
        return mine[self.layers.loc[mine, cols].any(axis=1).to_numpy()]

    def stake(self, rs: str, mode: str) -> tuple[float, int, float]:
        held = self.c.index.isin(self.ai2_claims(rs, mode))
        d = self.deltas(held, mode)[held]
        return float(d.sum()), int(held.sum()), float(d.mean()) if len(d) else 0.0

    def _flagged(self) -> list[dict]:
        stored = {m: {r["rs"]: r for r in rows} for m, rows in self.ai1["rs_ditandai"].items()}
        picks: dict[str, tuple[str, str]] = {}
        for mode, rows in stored.items():
            for rs in rows:
                picks.setdefault(rs, ("AI 1", mode))
        for mode in ("rme_meragukan", "fiktif", "diperpanjang"):
            t = self.ai2_modes[mode]
            for rs in t.index[t.ditandai]:
                picks.setdefault(rs, ("AI 2", mode))
        out = []
        for rs, (engine, mode) in picks.items():
            row = {"kode_rs": rs, **self.hospital(rs), "mesin_penanda": engine, "modus": mode}
            if engine == "AI 1":
                s, t = stored[mode][rs], self.ai1_modes[mode]["table"].loc[rs]
                m = self.ai1_modes[mode]
                lo, hi = count_range(m["p"][m["pop"] & self.rs_mask(rs)])
                row |= {"diakui": int(t.O), "wajar": int(round(t.E)), "wajar_bawah": lo, "wajar_atas": hi, "z_robust": round(float(t.z_robust), 2),
                        "q": float(t.p_bh), "keyakinan": confidence(t.p_bh), "keterangan_keyakinan": q_text(t.p_bh), "rupiah": float(s["rupiah"]),
                        "rupiah_bawah": float(s["rupiah_rentang95"][0]), "rupiah_atas": float(s["rupiah_rentang95"][1]), "n_klaim_dipertaruhkan": None}
            else:
                t = self.ai2_modes[mode].loc[rs]
                value, n, _ = self.stake(rs, mode)
                level = "pola_kuat" if mode == "rme_meragukan" and t.p_bh < 0.001 else confidence(t.p_bh)
                row |= {"diakui": None, "wajar": None, "wajar_bawah": None, "wajar_atas": None, "z_robust": round(float(t.z_robust), 2),
                        "q": float(t.p_bh), "keyakinan": level, "keterangan_keyakinan": q_text(t.p_bh), "rupiah": value, "rupiah_bawah": None,
                        "rupiah_atas": None, "n_klaim_dipertaruhkan": n}
            out.append(row)
        # AI 1 estimates first by rupiah, then AI 2 stakes, as the queue sorts by expected rupiah.
        return sorted(out, key=lambda r: (r["mesin_penanda"] != "AI 1", -r["rupiah"]))

    def period(self) -> dict:
        start, end = self.c.tgl_pulang.min(), self.c.tgl_pulang.max()
        return {"penilaian": f"data 12 bulan, {MON[start.month - 1]}–{MON[end.month - 1]} {end.year}",
                "klaim_diperiksa": f"pembebanan {MONTHS[end.month - 1]} {end.year}",
                "diperbarui": f"run DEV {self.updated.day} {MON[self.updated.month - 1]} {self.updated.year} pukul {self.updated:%H.%M}"}

    def statuses(self, decisions: list[dict]) -> dict[str, str]:
        return {k: STATUS_FROM_DECISION.get(v, "baru") for k, v in latest_decisions(decisions, "rs").items()}

    # ---------- Layar 1 ----------

    def queue(self, decisions: list[dict]) -> dict:
        status = self.statuses(decisions)
        rows = [{**r, "status_penanganan": status.get(r["kode_rs"], "baru")} for r in self.flagged]
        ai1 = [r for r in rows if r["mesin_penanda"] == "AI 1"]
        last = self.c.tgl_pulang.max()
        december = self.c.index[self.line & (self.c.tgl_pulang.dt.month == last.month).to_numpy()]
        claims = latest_decisions(decisions, "klaim")
        tf, tp, tr = (self.ai1_modes["fiktif"]["table"], self.ai1_modes["diperpanjang"]["table"], self.ai2_modes["rme_meragukan"])
        thin = tf.index[(tf.n_layak < S.MIN_KLAIM) & (tp.n_layak < S.MIN_KLAIM) & (tr.n_layak.reindex(tf.index).fillna(0) < S.MIN_KLAIM)]
        return {
            "sumber_data": SOURCE, "bagian_contoh": [], "periode": self.period(),
            "ringkasan": {"n_rs": len(self.h), "n_ditandai": len(rows),
                          "per_mesin": {m: sum(r["mesin_penanda"] == m for r in rows) for m in ("AI 1", "AI 2")},
                          "total_rupiah": sum(r["rupiah"] for r in ai1), "total_bawah": sum(r["rupiah_bawah"] for r in ai1),
                          "total_atas": sum(r["rupiah_atas"] for r in ai1),
                          "menunggu_rme": int((~december.isin(list(self.llm))).sum()), "klaim_desember": len(december),
                          "audit_kapasitas": A3.CAPACITY, "audit_terpakai": sum(v == "ajukan_audit" for v in claims.values())},
            "rs": rows,
            "urutan_keyakinan": [r["kode_rs"] for r in sorted(rows, key=lambda r: (r["q"], -r["z_robust"]))],
            "n_data_tidak_cukup": len(thin),
            "data_tidak_cukup": [{"kode_rs": rs, "kelas": self.h.at[rs, "kelas_rs"], "n_layak": int(tf.at[rs, "n_layak"])} for rs in thin],
        }

    # ---------- Layar 2 ----------

    def profile(self, rs: str, decisions: list[dict]) -> dict | None:
        row = next((r for r in self.flagged if r["kode_rs"] == rs), None)
        if row is None:
            return None
        if rs not in self._profiles:
            self._profiles[rs] = self._build_profile(row)
        return {**self._profiles[rs], "status_penanganan": self.statuses(decisions).get(rs, "baru")}

    def _line_summary(self, rs: str) -> str:
        mine = self.c[self.rs_mask(rs)]
        line = mine[self.line[self.rs_mask(rs)]]
        codes = self.codes.loc[line.index]
        n71, n72 = int(codes.map(lambda x: "96.71" in x).sum()), int(codes.map(lambda x: "96.72" in x).sum())
        only = int(codes.map(lambda x: "96.04" in x and not x & B2.VENT_CODES).sum())
        return (f"{num(int((mine.icu_indikator == 1).sum()))} rawat ICU, {num(len(line))} klaim garis ventilator "
                f"(96.71: {n71}, 96.72: {n72}, intubasi saja: {only}), {self.period()['penilaian'].removeprefix('data 12 bulan, ')}")

    def _ai1_card(self, rs: str, mode: str, flagged: bool) -> dict:
        t = self.ai1_modes[mode]["table"]
        r = t.loc[rs]
        m = self.ai1_modes[mode]
        lo, hi = count_range(m["p"][m["pop"] & self.rs_mask(rs)])
        fair = int(round(r.E))
        assessed = int((t.n_layak >= S.MIN_KLAIM).sum())
        card = {"label": ["AI 1", "Statistik"], "diakui": int(r.O), "diakui_teks": "diakui (garis ventilator)" if mode == "fiktif" else "diakui 96 jam atau lebih",
                "wajar": fair, "wajar_bawah": lo, "wajar_atas": hi}
        if flagged:
            return card | {"kelebihan_teks": f"kelebihan {int(r.O) - fair} klaim",
                           "catatan": f"Selisih diuji terhadap {assessed - 1} RS lain: z robust {num(r.z_robust, 1)}; {q_text(r.p_bh)} setelah koreksi untuk {assessed} RS."}
        detail = q_text(r.p_bh) if pd.notna(r.p_bh) else "tidak dinilai"
        return card | {"kelebihan_teks": None, "catatan": f"Selisih {num(r.O - r.E, 1)} klaim masih dalam rentang wajar ({detail}).",
                       "catatan_jujur": "Lolos pemeriksaan klaim; ditandai karena bacaan RME."}

    def _top_claims(self, rs: str, mode: str) -> pd.Index:
        m = self.ai1_modes[mode]
        rows = np.flatnonzero(m["pop"] & m["y"] & self.rs_mask(rs))
        return self.c.index[rows[np.argsort(m["p"][rows], kind="mergesort")]]

    def _ai2_status(self, sep: str) -> str:
        if sep not in self.layers.index:
            return "belum_dibaca"
        f = self.layers.loc[sep]
        if f.kloning or f.tulis_massal:
            return "asal_meragukan"
        if f[list(LAYER_TEXT)].any():
            return "tidak_mendukung"
        return "mendukung" if self.kw.at[sep, "verdict"] == "mendukung" else "tidak_dapat_disimpulkan"

    def _reason_chips(self, seps: list[str], mode: str) -> dict[str, list[str]]:
        bundle = self.engine.bundle
        df = self.c.loc[seps].reset_index()
        X = A1.features(A1.evidence(df, self.h.reset_index()), bundle.vocab)
        # One OpenMP thread is about five times faster for these small batches on a busy laptop.
        with threadpool_limits(1):
            reasons_all = bundle.reasons(X, "fiktif" if mode != "diperpanjang" else "panjang")
        out = {}
        for sep, (i, reasons) in zip(seps, enumerate(reasons_all)):
            chips = []
            for r in [x for x in reasons if x["arah"] == "menurunkan"][:2]:
                f, v, ref = r["fitur"], X.iloc[i][r["fitur"]], bundle.reference[r["fitur"]]
                if f.startswith("tarif_rs_"):
                    name = f.removeprefix("tarif_rs_")
                    chips.append(f"{COST_CHIP.get(name, name.replace('_', ' '))} {round(100 * v / ref) if ref else 0}%")
                elif f.startswith(("px_", "dx2_")):
                    chips.append(f"{'ada' if v else 'tanpa'} {f.split('_', 1)[1]}")
                elif f in ("icu_los", "lama_rawat"):
                    chips.append(f"{'ICU' if f == 'icu_los' else 'rawat'} {v:.0f} hari")
                else:
                    chips.append(r["teks"].split(" (")[0].lower())
            out[sep] = chips
        return out

    def _claim_rows(self, seps: list[str], mode: str, chips: dict[str, list[str]] | None = None) -> list[dict]:
        chips = self._reason_chips(seps, mode) if chips is None else chips
        held = self.c.index.isin(seps)
        delta = pd.Series(self.deltas(held, mode), index=self.c.index)
        p = self.p["p_panjang" if mode == "diperpanjang" else "p_fiktif"].fillna(0)
        out = []
        for sep in seps:
            r = self.c.loc[sep]
            codes = self.codes.loc[sep]
            out.append({"nomor_sep": sep, "tanggal": stay(r.tgl_masuk, r.tgl_pulang), "diagnosis": split_codes(r.diagnosa)[0],
                        "prosedur": next((x for x in ("96.72", "96.71", "96.70", "96.04") if x in codes), "-"), "jam": int(r.ventilator_hour),
                        "peluang": round(float(p[sep]), 2), "alasan": chips.get(sep, []), "selisih_tarif": int(delta[sep]),
                        "status_rme": self._ai2_status(sep)})
        return out

    def _peers_chart(self, rs: str, mode: str) -> dict:
        t = self.ai1_modes[mode]["table"]
        ok = t[(t.n_layak >= S.MIN_KLAIM) & (t.E > 0)]
        ratio = ok.O / ok.E
        kelas = self.h.kelas_rs
        peers = ratio[(kelas.reindex(ratio.index) == kelas[rs]) & (ratio.index != rs)]
        mine = float(t.at[rs, "O"] / t.at[rs, "E"]) if t.at[rs, "E"] > 0 else 1.0
        band = [round(float(peers.quantile(0.025)), 3), round(float(peers.quantile(0.975)), 3)] if len(peers) else [0.85, 1.15]
        lo, hi = min(0.6, float(ratio.min()) - 0.05), max(1.9, mine + 0.15, float(ratio.max()) + 0.05)
        what = "Rasio diakui ÷ wajar" if mode == "fiktif" else "Rasio klaim 96 jam atau lebih, diakui ÷ wajar"
        return {"jenis": "pembanding", "judul": "Pembanding RS sekelas", "label": ["Statistik"],
                "temuan": f"{what}; 1,0 berarti sesuai bukti. {rs} {num(mine, 2)} dibanding {len(peers)} RS kelas {kelas[rs]} lain; pita abu memuat 95% RS sekelas.",
                "rs": {"kode": rs, "rasio": round(mine, 3)}, "lain": [{"rasio": round(float(v), 3), "y": round(jitter(i), 3)} for i, v in enumerate(peers)],
                "rentang_wajar": band, "domain": [round(lo, 2), round(hi, 2)]}

    def _probability_chart(self, rs: str) -> dict:
        m = self.ai1_modes["fiktif"]
        coded = m["pop"] & m["y"]
        kelas = self.h.kelas_rs.reindex(self.c.kode_rs).to_numpy()
        mine = m["p"][coded & self.rs_mask(rs)]
        peers_mask = coded & (kelas == self.h.at[rs, "kelas_rs"]) & ~self.rs_mask(rs)
        others = m["p"][peers_mask]
        n_peers = self.c.kode_rs[peers_mask].nunique()
        a, b = histogram(mine), histogram(others)
        return {"jenis": "peluang", "judul": "Peluang didukung bukti", "label": ["AI 1"], "seri": [rs, f"{n_peers} RS kelas {self.h.at[rs, 'kelas_rs']} lain"],
                "temuan": f"Klaim garis ventilator yang diuji. {a[0]}% klaim {rs} berpeluang di bawah 0,1; di RS kelas {self.h.at[rs, 'kelas_rs']} lain {b[0]}%.",
                "rs": a, "lain": b}

    def _hours_chart(self, rs: str) -> dict:
        m = self.ai1_modes["diperpanjang"]
        kelas = self.h.kelas_rs.reindex(self.c.kode_rs).to_numpy()
        hours = self.c.ventilator_hour.to_numpy()
        edges = np.arange(72, 121, 4)
        mine = np.histogram(hours[m["pop"] & self.rs_mask(rs)], edges)[0]
        peers = np.histogram(hours[m["pop"] & (kelas == self.h.at[rs, "kelas_rs"]) & ~self.rs_mask(rs)], edges)[0]
        scaled = peers / max(peers.sum(), 1) * mine.sum()
        s = {x["garis"]: x for x in self.lines_test["per_kelas_rs"][self.h.at[rs, "kelas_rs"]]}
        sign = lambda v: f"{'+' if v >= 0 else '−'}{num(abs(v), 2)}"
        return {"jenis": "jam", "judul": "Jam ventilator tercatat, 72–120 jam", "label": ["Statistik"],
                "seri": [rs, f"RS kelas {self.h.at[rs, 'kelas_rs']} lain, disetarakan"],
                "temuan": f"Uji asimetri kelas {self.h.at[rs, 'kelas_rs']} di garis 96 jam {sign(s[96]['S'])} ({sign(s[96]['bawah'])} sampai {sign(s[96]['atas'])}); "
                          f"plasebo 120 jam {sign(s[120]['S'])}.",
                "awal": 72, "lebar": 4, "rs": [int(x) for x in mine], "lain": [round(float(x), 1) for x in scaled], "garis_tarif": 96, "plasebo": [72, 120]}

    def _write_chart(self, rs: str) -> dict:
        seps = [s for s in self.c.index[self.line & self.rs_mask(rs)] if s in self.engine.docs]
        held = set(self.ai2_claims(rs, "rme_meragukan"))
        year = self.c.tgl_pulang.max().year
        start = pd.Timestamp(year=year, month=1, day=1)
        when = {}
        for s in seps:
            d = self.engine.docs[s]
            w = pd.to_datetime(d.waktu_tulis[d.jenis != "resume_medis"])
            if len(w):
                when[s] = w.min() if s in held else w.median()
        others = [{"hari": round((t - start) / pd.Timedelta(days=1), 1), "y": round(jitter(i), 3)} for i, (s, t) in enumerate(when.items()) if s not in held]
        days = pd.Series({s: when[s].normalize() for s in held if s in when})
        waves = []
        for day, group in days.groupby(days).groups.items():
            first = min(when[s] for s in group)
            waves.append({"hari": round((day - start) / pd.Timedelta(days=1), 1), "tanggal": day_month(day), "jam": f"{first:%H.%M}", "n": len(group)})
        top = {w["hari"] for w in sorted(waves, key=lambda w: -w["n"])[:3]}
        waves = [w if w["hari"] in top else {**w, "tanggal": "", "jam": ""} for w in sorted(waves, key=lambda w: w["hari"])]
        return {"jenis": "waktu_tulis", "judul": "Kapan catatan ICU ditulis", "label": ["AI 2", "Kode"], "seri": ["klaim ditahan lapis asal-usul", "klaim lain"],
                "temuan": f"Satu titik per klaim: tanggal catatannya ditulis di server, {year}. Biru: {len(held)} klaim dengan catatan kembar atau ditulis serentak.",
                "bulan": list(MON), "lain": others, "gelombang": waves}

    def _similarity_chart(self, rs: str) -> dict:
        f = self.fast[self.fast.index.isin(self.c.index[self.line & self.rs_mask(rs)])]
        twins = f[f.kloning]
        median = float(twins.kemiripan_maks.median()) if len(twins) else float(f.kemiripan_maks.median())
        return {"jenis": "kemiripan", "judul": "Kemiripan catatan antarpasien", "label": ["AI 2", "Kode"],
                "temuan": f"Kemiripan teks setelah angka diseragamkan; {len(f)} klaim garis ventilator. Gambar skematis: ukuran blok dan median dari data.",
                "n_pasien": len(f), "n_kembar": len(twins), "median_kembar": round(median, 2),
                "keterangan": (f"catatan nyaris identik, median kemiripan {num(median, 2)} (blok pekat kiri atas)" if len(twins)
                               else f"tidak ada catatan nyaris identik; median kemiripan tertinggi {num(median, 2)}")}

    def _build_profile(self, row: dict) -> dict:
        rs, engine, mode = row["kode_rs"], row["mesin_penanda"], row["modus"]
        h = self.hospital(rs)
        base = {"kode_rs": rs, **h, "modus": mode, "mesin_penanda": engine, "keyakinan": row["keyakinan"], "keterangan_keyakinan": row["keterangan_keyakinan"],
                "ringkas_data": self._line_summary(rs), "sumber_data": SOURCE, "bagian_contoh": []}
        if engine == "AI 1":
            return base | self._ai1_profile(rs, mode, row)
        return base | self._ai2_profile(rs, mode, row)

    def _ai1_profile(self, rs: str, mode: str, row: dict) -> dict:
        card = self._ai1_card(rs, mode, True)
        excess = max(card["diakui"] - card["wajar"], 1)
        top = list(self._top_claims(rs, mode)[:excess])
        m = self.ai1_modes[mode]
        mine = m["pop"] & self.rs_mask(rs)
        delta = self.deltas(mine & m["y"], mode)
        weights = (1 - m["p"][mine]) * m["y"][mine]
        mean_delta = float(np.average(delta[mine], weights=weights)) if weights.sum() > 0 else 0.0
        statuses = [self._ai2_status(s) for s in top]
        read = [s for s in statuses if s != "belum_dibaca"]
        f = self.fast[self.fast.index.isin(self.c.index[self.line & self.rs_mask(rs)])]
        n_twins = int(f.kloning.sum())
        held = sum(s in ("tidak_mendukung", "asal_meragukan") for s in statuses)
        facts = {"diakui": [f"{card['diakui']} klaim", "diakui vs wajar, uji per RS", ["AI 1", "Statistik"]],
                 "wajar": [f"{card['wajar']} klaim", "diakui vs wajar, uji per RS", ["AI 1", "Statistik"]],
                 "wajar_bawah": [str(card["wajar_bawah"]), "rentang 95% wajar", ["AI 1", "Statistik"]],
                 "wajar_atas": [str(card["wajar_atas"]), "rentang 95% wajar", ["AI 1", "Statistik"]],
                 "kelebihan": [f"{excess} klaim", "diakui dikurangi wajar", ["Kode"]],
                 "rupiah": [miliar(row["rupiah"]), "kelebihan × selisih tarif Permenkes 3/2023", ["Kode"]],
                 "dibaca": [f"{len(read)} klaim", "lapis cepat RME atas klaim teratas", ["AI 2"]],
                 "tidak_mendukung": [f"{held} klaim", "lapis cepat RME atas klaim teratas", ["AI 2"]]}
        return {
            "kartu_diakui": card,
            "kartu_rupiah": {"judul": "Perkiraan kelebihan bayar", "nilai": row["rupiah"], "bawah": row["rupiah_bawah"], "atas": row["rupiah_atas"],
                             "skala": nice_max(row["rupiah_atas"]),
                             "rincian": f"{excess} klaim × rata-rata selisih tarif {juta(mean_delta)} pada baris tarif RS ini ({self.row_text(rs)})."},
            "kartu_rme": {"judul": f"Dibaca {len(read)} dari {len(top)} klaim teratas",
                          "hitungan": [["RME tidak mendukung", statuses.count("tidak_mendukung")], ["Asal-usul meragukan", statuses.count("asal_meragukan")],
                                       ["Tidak dapat disimpulkan", statuses.count("tidak_dapat_disimpulkan")], ["Mendukung", statuses.count("mendukung")]],
                          "status": [["kemiripan", f"Kemiripan catatan antarpasien: {n_twins} klaim kembar" if n_twins else "Kemiripan catatan antarpasien: tidak ada pola"],
                                     ["jejak", f"Jejak waktu: median ditulis {num(float(f.jeda_tulis_median_jam.median()), 1)} jam setelah layanan"]]},
            "grafik_kiri": self._probability_chart(rs) if mode == "fiktif" else self._hours_chart(rs),
            "grafik_kanan": self._peers_chart(rs, mode),
            "klaim_judul": "Klaim yang paling tidak didukung bukti",
            "klaim_keterangan": f"{min(4, len(top))} dari {len(top)} klaim kelebihan, urut menurut peluang terendah", "klaim_total": len(top),
            "klaim": self._claim_rows(top[:4], mode),
            "fakta_ringkasan": facts, "templat": TEMPLATES[("AI 1", mode)],
        }

    def _ai2_profile(self, rs: str, mode: str, row: dict) -> dict:
        t = self.ai2_modes[mode].loc[rs]
        held = list(self.ai2_claims(rs, mode))
        value, n, mean_delta = self.stake(rs, mode)
        card = self._ai1_card(rs, "diperpanjang" if mode == "diperpanjang" else "fiktif", False)
        pool = self.pools[mode][(self.c.kode_rs.reindex(self.pools[mode]) == rs).to_numpy()]
        codes = self.codes.loc[held]
        test_line = f"{int(t.O)} dari {int(t.n_uji)} klaim ditahan, harapan {num(t.E, 1)}; {q_text(t.p_bh)}"
        facts = {"diakui": [f"{card['diakui']} klaim", "diakui vs wajar, uji per RS", ["AI 1", "Statistik"]],
                 "wajar": [f"{card['wajar']} klaim", "diakui vs wajar, uji per RS", ["AI 1", "Statistik"]],
                 "rupiah": [miliar(value), "klaim ditahan × selisih tarif Permenkes 3/2023, nilai dipertaruhkan", ["Kode"]]}
        rupiah = {"judul": "Nilai dipertaruhkan", "nilai": value, "bawah": None, "atas": None, "skala": None,
                  "rincian": f"{n} klaim × rata-rata selisih tarif {juta(mean_delta)} pada baris tarif RS ini ({self.row_text(rs)}).",
                  "catatan": "Ini bukan perkiraan kelebihan bayar: isinya baru bisa dipastikan lewat audit."}
        if mode == "rme_meragukan":
            f = self.fast.reindex(pool)
            twins, bulk = f[f.kloning.fillna(False).astype(bool)], int(f.tulis_massal.fillna(False).astype(bool).sum())
            median = float(twins.kemiripan_maks.median()) if len(twins) else 0.0
            facts |= {"kembar": [f"{len(twins)} klaim", "kemiripan catatan antarpasien", ["AI 2", "Kode"]],
                      "kemiripan": [num(median, 2), "median kemiripan kelompok kembar", ["AI 2", "Kode"]],
                      "serentak": [f"{bulk} klaim", "jejak waktu tulis server", ["AI 2", "Kode"]]}
            kw_ok = int((self.kw.reindex(pool).verdict == "mendukung").sum())
            order = sorted(held, key=lambda s: -float(self.fast.at[s, "kemiripan_maks"]))
            chips = {s: [f"mirip {num(float(self.fast.at[s, 'kemiripan_maks']), 2)}",
                         f"serentak {round(100 * float(self.fast.at[s, 'porsi_tulis_serentak']))}%"] for s in order[:4]}
            return {
                "kartu_diakui": card,
                "kartu_rupiah": rupiah | {"subjudul": f"{n} klaim dengan RME meragukan (96.71: {int(codes.map(lambda x: '96.71' in x).sum())}, "
                                                      f"96.72: {int(codes.map(lambda x: '96.72' in x).sum())})"},
                "kartu_rme": {"judul": f"Dibaca {len(pool)} dari {len(pool)} klaim garis ventilator",
                              "hitungan": [["Catatan nyaris identik", len(twins)], ["Ditulis dalam satu sesi", bulk], ["Isi RME mendukung kode", kw_ok]],
                              "status": [["kemiripan", f"Kembar: {len(twins)} klaim, median kemiripan {num(median, 2)}" if len(twins) else "Kemiripan catatan antarpasien: tidak ada pola"],
                                         ["jejak", test_line]]},
                "grafik_kiri": self._write_chart(rs), "grafik_kanan": self._similarity_chart(rs),
                "klaim_judul": "Klaim dengan catatan RME meragukan", "klaim_keterangan": f"{min(4, len(order))} dari {len(order)} klaim, urut menurut kemiripan tertinggi",
                "klaim_total": len(order), "klaim": self._claim_rows(order[:4], mode, chips),
                "fakta_ringkasan": facts, "templat": TEMPLATES[("AI 2", mode)],
            }
        counts = self.layers.loc[pool, [x for x in F2.MODE_LAYERS[mode] if x in self.layers]].sum()
        facts |= {"ditahan": [f"{n} klaim", "lapis RME per klaim", ["AI 2"]], "dibaca": [f"{len(pool)} klaim", "klaim layak modus ini", ["AI 2"]]}
        p = self.p["p_panjang" if mode == "diperpanjang" else "p_fiktif"].fillna(0)
        order = sorted(held, key=lambda s: p[s])
        if mode == "diperpanjang":
            hours = self.kw.reindex(held).jam
            chips = {s: [f"jam RME {num(float(hours[s]), 0)}" if pd.notna(hours[s]) else "jam RME tidak terbaca"] for s in order[:4]}
            claimed = self.c.loc[held].ventilator_hour
            status = [["jam", f"Median jam menurut RME {num(float(hours.median()), 0)} jam, diklaim {num(float(claimed.median()), 0)} jam"], ["uji", test_line]]
            hitungan = [["Jam menurut RME di bawah 96", n], ["Klaim layak lain", len(pool) - n]]
        else:
            chips = {s: [LAYER_CHIP[k] for k in LAYER_TEXT if k in self.layers and self.layers.at[s, k]][:2] for s in order[:4]}
            status = [["uji", test_line]]
            hitungan = [[LAYER_TEXT[k], int(counts[k])] for k in LAYER_TEXT if k in counts and counts[k]]
        return {
            "kartu_diakui": card,
            "kartu_rupiah": rupiah | {"subjudul": f"{n} klaim ditahan bacaan RME"},
            "kartu_rme": {"judul": f"Dibaca {len(pool)} dari {len(pool)} klaim layak {MODE_LABEL[mode]}", "hitungan": hitungan, "status": status},
            "grafik_kiri": self._probability_chart(rs) if mode == "fiktif" else self._hours_chart(rs),
            "grafik_kanan": self._peers_chart(rs, "diperpanjang" if mode == "diperpanjang" else "fiktif"),
            "klaim_judul": "Klaim yang ditahan bacaan RME", "klaim_keterangan": f"{min(4, len(order))} dari {len(order)} klaim, urut menurut peluang AI 1 terendah",
            "klaim_total": len(order), "klaim": self._claim_rows(order[:4], mode, chips),
            "fakta_ringkasan": facts, "templat": TEMPLATES[("AI 2", mode)],
        }

    # ---------- Layar 3 ----------

    def _ladder(self, r: pd.Series) -> dict:
        h = self.h.loc[r.kode_rs]
        dx = split_codes(r.diagnosa)
        rest = set(self.codes.loc[r.name]) - TRIGGER_CODES
        hours = int(r.ventilator_hour)

        def rung(codes: set[str], hrs: int) -> tuple[str, int]:
            g = G.group(dx[0][:3], codes, [d[:3] for d in dx[1:]], hrs)
            return g, G.tariff(int(h.regional), h.kelas_rs, h.kepemilikan, g, int(r.kelas_rawat))

        steps = [(*rung(rest, 0), "tanpa kode"), (*rung(rest | {"96.71"}, min(hours, A1.GARIS - 1)), "96.71"),
                 (*rung(rest | {"96.72"}, max(hours, A1.GARIS)), "96.72")]
        if not any(g == r.cbg for g, _, _ in steps):
            steps[1] = (r.cbg, int(r.tarif_ina_cbg), "diklaim")
        anak = [{"tarif": int(t), "label": f"{g}, {what}" + (" (diklaim)" if g == r.cbg and what != "diklaim" else ""), "diklaim": g == r.cbg}
                for g, t, what in steps]
        code = next((x for x in ("96.72", "96.71", "96.70", "96.04") if x in self.codes.loc[r.name]), "-")
        base = steps[0][1]
        return {"selisih": int(r.tarif_ina_cbg) - base, "kali": num(r.tarif_ina_cbg / base, 1) if base else "-", "kode": code, "anak": anak}

    def claim(self, sep: str) -> dict | None:
        if sep not in self.c.index:
            return None
        r = self.c.loc[sep]
        codes = self.codes.loc[sep]
        dx = split_codes(r.diagnosa)
        bundle = self.engine.bundle
        p = float(self.p.at[sep, "p_fiktif"])
        flagged = p <= bundle.thresholds["fiktif"]
        share = bundle.percentile(p, dx[0][:3])
        ladder = self._ladder(r)
        X = A1.features(A1.evidence(self.c.loc[[sep]].reset_index(), self.h.reset_index()), bundle.vocab)
        with threadpool_limits(1):
            reasons = [["turun" if x["arah"] == "menurunkan" else "naik", x["teks"]] for x in bundle.reasons(X, "fiktif")[0]]
        ref = lambda k: bundle.reference[f"tarif_rs_{k}"]
        share_of = lambda k: round(100 * r[f"tarif_rs_{k}"] / ref(k)) if ref(k) else 0
        money = lambda x: juta(x) if x >= 1e6 else rp(x)
        cost = lambda label, k, show: [label, round(float(r[f"tarif_rs_{k}"] / ref(k)), 2) if ref(k) else 0.0,
                                       f"{money(r[f'tarif_rs_{k}'])}, {share_of(k)}%" if show else f"{share_of(k)}% dari tipikal"]
        with_ = lambda code, name: f"{'dengan' if code in codes else 'tanpa'} kode {name} {code}"
        vent = (f"{stamp(r.ventilator_start_dttm)} → {stamp(r.ventilator_stop_dttm)}" if pd.notna(r.ventilator_start_dttm) and pd.notna(r.ventilator_stop_dttm)
                else "waktu mulai dan selesai tidak tercatat")
        return {
            "sumber_data": SOURCE, "bagian_contoh": [], "nomor_sep": sep, "kode_rs": r.kode_rs,
            "rs_teks": f"{r.kode_rs}, Kelas {self.h.at[r.kode_rs, 'kelas_rs']}, {self.h.at[r.kode_rs, 'kepemilikan'].capitalize()}",
            "kelas_rawat": int(r.kelas_rawat), "periode": f"{r.tgl_masuk:%d-%m-%Y} → {r.tgl_pulang:%d-%m-%Y}",
            "eklaim": [["Pasien", f"{'Laki-laki' if r.jenis_kelamin == 'L' else 'Perempuan'}, {int(r.umur)} tahun"],
                       ["Lama rawat", f"{(r.tgl_pulang.normalize() - r.tgl_masuk.normalize()).days + 1} hari, ICU {int(r.icu_los)} hari"],
                       ["Diagnosis", dx[0]], ["Status pulang", DISCHARGE.get(int(r.discharge_status), str(r.discharge_status))],
                       ["Sekunder", ", ".join(dx[1:]) or "tidak ada"], ["CBG", f"{r.cbg}, sev. {r.cbg.rsplit('-', 1)[-1]}"]],
            "prosedur": {"kode": ladder["kode"], "keterangan": f"{with_('96.04', 'intubasi')}, {with_('89.65', 'analisa gas darah')}"},
            "ventilator": {"jam": int(r.ventilator_hour), "rentang": vent},
            "tangga": ladder,
            "biaya": [cost("Sewa alat", "sewa_alat", True), cost("Rawat intensif", "rawat_intensif", True), cost("Laboratorium", "laboratorium", False),
                      cost("Obat", "obat", False)],
            "ai1": {"peluang": round(p, 2), "ditandai": bool(flagged), "alasan": reasons,
                    "keterangan": (f"lebih rendah dari {'hampir semua' if share < 0.005 else str(round(100 * (1 - share))) + '%'} klaim garis ventilator lain, AI 1 menandai" if flagged
                                   else "setara dengan klaim garis ventilator yang didukung bukti, AI 1 tidak menandai" if share >= 0.995
                                   else f"lebih tinggi dari {round(100 * share)}% klaim garis ventilator lain, AI 1 tidak menandai"),
                    "tanpa_alasan": "Tidak ada bukti di klaim yang mengubah peluang lebih dari 0,01.",
                    "catatan": "Peluang dari model luar lipatan (RS tidak dinilai model yang dilatih dengan datanya); alasan dari model akhir, bukan ditebak LLM."},
            "rme": {"status": "diproses", "hasil": f"/api/v1/klaim/{sep}/bacaan"},
        }

    def _late(self, sep: str, r: pd.Series, docs: pd.DataFrame) -> str | None:
        window = pd.DataFrame({"mulai": [r.ventilator_start_dttm if pd.notna(r.ventilator_start_dttm) else r.tgl_masuk],
                               "selesai": [r.ventilator_stop_dttm if pd.notna(r.ventilator_stop_dttm) else r.tgl_pulang]}, index=[sep])
        delays = F2.key_document_delay(docs, window)
        if delays.empty:
            return None
        scores = F2.delay_scores(delays, pd.Series(r.kode_rs, index=delays.index), self.engine.late_baseline)
        return F2.late_key_documents(delays, scores).get(sep) or None

    def _quote(self, text: str, docs: list[dict]) -> dict:
        target = B2._norm(text)
        for d in docs:
            norm = B2._norm(d["teks"])
            if target and target in norm:
                i = d["teks"].lower().find(text.lower())
                if i >= 0:
                    return {"sebelum": d["teks"][max(0, i - 40):i], "sorot": d["teks"][i:i + len(text)], "sesudah": d["teks"][i + len(text):i + len(text) + 30],
                            "dokumen": d["judul"], "cocok": True, "_doc": d["id"]}
                return {"sebelum": "", "sorot": text, "sesudah": "", "dokumen": d["judul"], "cocok": True, "_doc": d["id"]}
        return {"sebelum": "", "sorot": text, "sesudah": "", "dokumen": "tidak ditemukan di dokumen", "cocok": False, "_doc": None}

    def _physiology(self, sep: str, r: pd.Series, text_hours: float | None) -> dict | None:
        at = self.hourly_at.get(sep)
        if at is None or sep not in self.sheet.index:
            return None
        hours = self.hourly.iloc[at].sort_values("waktu")
        start = r.ventilator_start_dttm if pd.notna(r.ventilator_start_dttm) else r.tgl_masuk
        stop = r.ventilator_stop_dttm if pd.notna(r.ventilator_stop_dttm) else r.tgl_pulang
        view = hours[(hours.waktu >= start.floor("h") - pd.Timedelta(hours=2)) & (hours.waktu <= stop.ceil("h") + pd.Timedelta(hours=3))].head(168)
        if view.empty:
            view = hours.head(168)
        times = view.waktu.reset_index(drop=True)
        inside = times[(times >= start.floor("h")) & (times <= stop.floor("h"))].index
        span = [int(inside.min()), int(inside.max()) + 1] if len(inside) else [0, 0]
        sheet = float(self.sheet.at[sep, "lembar"])
        claimed = float(r.ventilator_hour)
        report = self.physio_report
        written = f"; teks RME {num(text_hours, 1)} jam" if text_hours else ""
        return {"ringkas": f"{num(sheet)} dari {num(claimed)} jam berventilasi",
                "judul": f"Peluang ventilasi invasif per jam menurut angka lembar, {times.iat[0]:%d-%m %H.%M} sampai {times.iat[-1]:%d-%m %H.%M}",
                "per_jam": [round(float(x), 3) for x in view.p_ventilasi], "jam_tertulis": span, "ambang": 0.5,
                "pita_teks": f"pita biru muda: masa ventilasi yang diklaim, {num(claimed)} jam",
                "hari": [[f"{t:%d-%m}", int(i)] for i, t in times.items() if t.hour == 0],
                "catatan": f"Lembar tanda vital menunjukkan {num(sheet)} jam berventilasi; klaim {num(claimed)} jam{written}.",
                "kaki": f"Membaca angka, bukan kolom alat. AUC {num(report['eicu']['auc_rs_disisihkan'], 2)} (eICU, RS disisihkan); "
                        f"AUC {num(report['mimic_validasi_luar']['auc'], 2)} (MIMIC-IV)."}

    def reading(self, sep: str) -> dict | None:
        docs = self.engine.docs.get(sep)
        if sep not in self.c.index or docs is None:
            return None
        t0 = time.perf_counter()
        r = self.c.loc[sep]
        codes = set(self.codes.loc[sep])
        claimed = float(r.ventilator_hour)
        record = B2.assemble(docs)
        stored = self.llm.get(sep)
        reading = RmeReading.model_validate(stored["reading"]) if stored and stored["reading"] else None
        if reading and B2._unmatched(reading, record) and (again := self.retried.get(sep)) and again["reading"]:
            reading = RmeReading.model_validate(again["reading"])
        source = "llm_lokal" if reading else "aturan"
        reading = reading or B2.read_rules(record)
        fast = self.fast.loc[sep] if sep in self.fast.index else None
        second = self.vent.get(sep)
        sheet = float(self.sheet.at[sep, "lembar"]) if sep in self.sheet.index and pd.notna(self.sheet.at[sep, "lembar"]) else None
        provenance = (fast.alasan_asal_usul or None) if fast is not None else None
        late = self._late(sep, r, docs)
        code = next((x for x in ("96.72", "96.71", "96.70", "96.04") if x in codes), "ventilasi")
        if reading is None:
            check, verdict, why, held = None, "tidak_dapat_disimpulkan", ["aturan kata kunci tidak menemukan sebutan alat napas"], ["bacaan"]
            content = verdict
        else:
            check = B2.check_reading(reading, record)
            content, why0 = B2.judge(check, reading, codes, claimed)
            verdict, why, held = B2.cross_check(content, why0, reading.ventilasi_invasif, check.hours, second, sheet, provenance, late)
        docs_view = []
        for d in docs.sort_values("waktu_layanan").itertuples():
            served = pd.Timestamp(d.waktu_layanan)
            name = DOC_NAMES.get(d.jenis, d.jenis.replace("_", " ").capitalize())
            docs_view.append({"id": d.dokumen_id, "label": f"{name} {served:%d-%m}", "teks": d.teks, "sorot": [],
                              "judul": f"{name}, {served:%d-%m-%Y %H.%M}, {d.penulis_peran.capitalize()}, ditulis {pd.Timestamp(d.waktu_tulis):%d-%m %H.%M}"})
        quotes = [self._quote(q.teks, docs_view) for q in (reading.kutipan if reading else [])]
        for q in quotes:
            for d in docs_view:
                if d["id"] == q["_doc"]:
                    d["sorot"].append(q["sorot"])
        active = next((q["_doc"] for q in quotes if q["_doc"]), docs_view[0]["id"] if docs_view else None)
        quotes = [{k: v for k, v in q.items() if k != "_doc"} for q in quotes]
        ok = sum(q["cocok"] for q in quotes)
        hours = check.hours if check else None
        verdict_text = {"mendukung": f"Isi RME mendukung kode {code}, kutipan terverifikasi {ok} dari {len(quotes)}",
                        "tidak_mendukung": f"RME tidak mendukung kode {code}", "tidak_dapat_disimpulkan": "Tidak dapat disimpulkan"}[content]
        result = {"verdict": verdict_text, "verdict_jenis": content}
        if content == "tidak_dapat_disimpulkan":
            result["alasan"] = "; ".join(why)
        if reading is not None:
            invasive = {"ya": "ditemukan", "tidak": "tidak ditemukan", "tidak_jelas": "tidak jelas"}[reading.ventilasi_invasif]
            result["alat"] = [DEVICE[reading.alat_napas_tertinggi] + (f" {reading.mode_ventilator}" if reading.mode_ventilator else "")]
            result["baris"] = [["Ventilator invasif", invasive],
                               ["Jam ventilator", f"RME {num(hours, 1)} jam, diklaim {num(claimed)} jam" if hours is not None else f"tidak terhitung, diklaim {num(claimed)} jam"]]
        out = {"status": "selesai", "tahap": "selesai", "sumber": source, "dokumen": docs_view, "dokumen_aktif": active, "hasil": result,
               "kutipan": quotes, "kutipan_ringkas": f"terverifikasi {ok} dari {len(quotes)}" if quotes else None, "kutipan_semua_cocok": ok == len(quotes),
               "sumber_data": SOURCE, "bagian_contoh": [],
               "catatan_sumber": "bacaan LLM lokal tersimpan dari run DEV" if source == "llm_lokal" else "belum dibaca LLM di run DEV; dibaca aturan kata kunci"}
        out["durasi_ms"] = int(stored["total_ms"]) if source == "llm_lokal" else round((time.perf_counter() - t0) * 1000)
        if source == "aturan":
            vent_words = pd.Series([m.group(0).lower() for m in B2.VENT.finditer(record.text)], dtype=str).value_counts()
            vent_words.index = [k.upper() if len(k) <= 3 else k for k in vent_words.index]
            device_words = [[DEVICE[name], len(p.findall(record.text))] for name, p in B2.DEVICES]
            out |= {"jenis": "aturan", "kata": [["Kata ventilator", [[k, int(v)] for k, v in vent_words.items()] or [["ventilator", 0]]],
                                                ["Kata alat napas lain", device_words]],
                    "jam": f"{num(hours, 1)} jam menurut aturan, diklaim {num(claimed)} jam" if hours is not None else f"tidak dihitung aturan, diklaim {num(claimed)} jam",
                    "peringatan_aturan": "Aturan tidak membaca konteks (misalnya “ventilator dilepas”); periksa dokumen langsung."}
        else:
            out["jenis"] = ("asal_meragukan" if "asal_usul" in held else "fisiologi" if "fisiologi" in held
                            else "tidak_dapat_disimpulkan" if verdict == "tidak_dapat_disimpulkan" else "baca")
        if held and held != ["bacaan"]:
            out["verdict_akhir"] = f"{verdict_text.split(',')[0]}, tetapi {', '.join(HELD_TEXT[x] for x in held if x in HELD_TEXT)}, jadi tidak dapat disimpulkan"
        out["tombol_utama"] = ("ajukan_audit" if set(held) & {"asal_usul", "fisiologi", "jejak_waktu"} else "setujui" if verdict == "mendukung" else "minta_klarifikasi")
        if fast is not None:
            later = f", {round(100 * fast.porsi_ditulis_sesudah_pulang)}% catatan ditulis sesudah pulang" if fast.porsi_ditulis_sesudah_pulang > 0 else ""
            out["cek"] = [["jejak", f"Jejak waktu: median ditulis {num(fast.jeda_tulis_median_jam, 1)} jam setelah layanan{later}"],
                          ["kemiripan", f"Kemiripan: {'nyaris identik dengan ' + str(int(fast.n_klaim_mirip)) + ' klaim lain' if fast.kloning else 'tidak ada'} "
                                        f"(maks {num(fast.kemiripan_maks, 2)})"]]
            if fast.kloning:
                partner = fast.pasangan_teratas
                first = lambda s: next((t.split(". ")[0][:90] for t in self.engine.docs[s].sort_values("waktu_layanan").teks), "") if s in self.engine.docs else ""
                who = lambda s: f"{'Laki-laki' if self.c.at[s, 'jenis_kelamin'] == 'L' else 'Perempuan'}, {int(self.c.at[s, 'umur'])} th"
                out["kemiripan"] = {"judul": f"Catatan ini {round(100 * fast.kemiripan_maks)}% sama dengan catatan {int(fast.n_klaim_mirip)} pasien lain di RS ini",
                                    "pasangan": [{"sep": s, "pasien": who(s), "teks": first(s), "beda": ""} for s in (sep, partner) if s in self.c.index],
                                    "catatan": f"Kemiripan teks setelah angka diseragamkan; lembar tanda vital sama pada {round(100 * fast.kemiripan_lembar_asal_usul)}% jam."}
            if fast.tulis_massal or fast.tulis_serentak:
                w = pd.to_datetime(docs.waktu_tulis[docs.jenis != "resume_medis"])
                out["jejak"] = {"judul": f"{round(100 * fast.porsi_tulis_serentak)}% catatan ditulis dalam satu sesi tiga jam",
                                "layanan": stay(r.tgl_masuk, r.tgl_pulang), "tulis": f"{day_month(w.min())} {w.min():%H.%M}–{w.max():%H.%M}",
                                "catatan": "Jam server rekam medis (waktu tulis), bukan diisi RS."}
        if second is not None:
            same = reading is not None and second == reading.ventilasi_invasif
            out["asersi"] = {"ringkas": f"ventilasi invasif: {second.replace('_', ' ')}", "sama": same, "sebutan": [],
                             "kaki": "Pembaca kedua tanpa LLM, hasil per klaim dari run DEV; rincian sebutan per kalimat tidak disimpan."}
        out["fisiologi"] = self._physiology(sep, r, hours)
        return out

    # ---------- Layar 5 ----------

    def lines(self) -> dict:
        a = self.ai4
        found = a["ambang"] + a["kode"]
        status = lambda x: self.line_config.get(line_id(x), {}).get("status", "temuan")
        sign = lambda v: f"{'+' if v >= 0 else '−'}{num(abs(v), 2)}"
        group = lambda x: (f"keparahan {x['grup_asal'].rsplit('-', 1)[1]} → {x['grup_tujuan'].rsplit('-', 1)[1]}"
                           if x["grup_asal"].rsplit("-", 1)[0] == x["grup_tujuan"].rsplit("-", 1)[0]
                           else f"{x['grup_asal'].rsplit('-', 1)[0]} → {x['grup_tujuan'].rsplit('-', 1)[0]}")
        wrong = set(a["t20"]["tidak_dimanipulasi_menyala"])
        lit = [x for x in found if x["uji"]["menyala"]]
        lit = (sorted([x for x in lit if x["uji"].get("rupiah_terukur", True)], key=lambda x: -x["uji"]["rupiah"])
               + [x for x in lit if not x["uji"].get("rupiah_terukur", True)])
        dark = [x for x in found if not x["uji"]["menyala"]]

        def row(x: dict) -> dict:
            u = x["uji"]
            if x["jenis"] == "ambang":
                lo, hi = u["rupiah_rentang95"]
                return {"id": f"jam{x['ambang']}", "nama": f"Jam ventilasi ≥{x['ambang']}", "jenis": f"ambang, lewat kode {x['lewat_kode']}",
                        "grup": group(x), "kali": f"×{num(x['kelipatan_median'], 1)}", "menyala": u["menyala"], "uji": f"S({x['ambang']}) {sign(u['S'])}",
                        "rupiah": f"Rp{billions(lo)}–{billions(hi)} M" if not u["rupiah_terukur"] else short_rp(u["rupiah"]),
                        "rentang": "belum terukur" if not u["rupiah_terukur"] else short_range(lo, hi), "status": status(x), "rincian": True}
            name = CODE_NAMES.get(x["kode"], "")
            kind = "diagnosis sekunder" if x["atribut"] == "diagnosis_sekunder" else "kode, pindai langsung" if x["sumber"] != "pohon" else "kode prosedur"
            out = {"id": x["kode"], "nama": f"{x['kode']}, {name}" if name else x["kode"],
                   "jenis": kind + (", temuan baru" if status(x) == "temuan" and x["sumber"] == "pohon" and x["atribut"] == "prosedur" else ""),
                   "grup": group(x), "kali": f"×{num(x['kelipatan_median'], 1)}", "menyala": u["menyala"],
                   "uji": f"{len(u['rs_ditandai'])} RS ditandai" if u["menyala"] else "0 RS",
                   "rupiah": short_rp(u["rupiah"]) if u["menyala"] else None,
                   "rentang": short_range(*u["rupiah_jumlah_rentang_per_rs"]) if u["menyala"] else None, "status": status(x)}
            if u["menyala"]:
                lo, hi = u["rupiah_jumlah_rentang_per_rs"]
                out["judul"] = f"{x['kode']}, {name.capitalize()}" if name else x["kode"]
                out["fakta"] = [f"AI 4: kode ini memindahkan klaim {x['grup_asal']} → {x['grup_tujuan']}, tarif ×{num(x['kelipatan_median'], 1)}, "
                                f"pada {num(x['n_terdampak'])} dari {num(x['n_klaim'])} klaim berkode.",
                                f"Uji diakui vs wajar per RS: menyala di {len(u['rs_ditandai'])} RS, perkiraan {short_rp(u['rupiah'])} ({short_range(lo, hi)}).",
                                "Sebelum disetujui, garis ini tidak memengaruhi penandaan maupun antrean kerja." if status(x) == "temuan"
                                else "Garis ini sudah aktif dan ikut uji per RS bulanan."]
                if x["kode"] in wrong:
                    out["fakta"].append(f"Garis ini termasuk {len(wrong)} garis yang menyala di DEV padahal tidak dimanipulasi (T20 gagal).")
            return out

        rows = [row(x) for x in lit] + [row(x) for x in dark if status(x) == "aktif"]
        rest = [x for x in dark if status(x) != "aktif"]
        if rest:
            k = [x["kelipatan_median"] for x in rest]
            rows.append({"id": "lain", "nama": f"{len(rest)} garis lain", "jenis": ", ".join(x["kode"] for x in rest[:3]) + ", …", "grup": "beragam",
                         "kali": f"×{num(min(k), 1)}–{num(max(k), 1)}", "menyala": False, "uji": "0 RS", "rupiah": None, "rentang": None, "status": "temuan"})
        jam = next((x for x in a["ambang"] if x["atribut"] == "jam_ventilasi"), None)
        twin = {x["garis"]: x for x in self.lines_test["kembaran_tanpa_fraud"]}
        r = self.reality
        names = {"96.71": "96.71 → J-1-20", "96.72": "96.72 → J-1-02", "trakeostomi": "Trakeostomi → J-1-01", "96.04": "96.04 → J-1-20"}
        direct = [k for k, v in r["t24"]["jalur"].items() if v and not r["t24_pohon_saja"]["jalur"].get(k)]
        n_lit = {s: sum(status(x) == s for x in lit) for s in ("aktif", "temuan")}
        idrg = self.idrg["ambang"][0]
        start, end = self.c.tgl_pulang.min(), self.c.tgl_pulang.max()
        out = {
            "sumber_data": SOURCE, "bagian_contoh": [],
            "subjudul": "AI 4 membaca sendiri kode dan ambang tempat tarif INA-CBG melompat; setiap garis diuji dulu, lalu disetujui admin sebelum dipakai.",
            "cakupan": f"Wilayah Uji, {len(self.h)} RS, {MON[start.month - 1]}–{MON[end.month - 1]} {end.year}",
            "ubin": [{"nilai": str(len(found)), "satuan": "garis", "keterangan": f"ditemukan AI 4: {len(a['ambang'])} ambang, {len(a['kode'])} kode", "label": ["AI 4"],
                      "asal": f"pohon {num(100 * a['akurasi_model_pengganti']['lengkap']['grup'], 1)}% + pindai langsung"},
                     {"nilai": str(len(lit)), "satuan": "garis", "keterangan": f"menyala: {n_lit['aktif']} aktif, {n_lit['temuan']} temuan", "label": ["Statistik", "AI 1"],
                      "asal": "asimetri dan uji per RS"},
                     {"nilai": str(sum(status(x) == "temuan" for x in found)), "satuan": "garis", "keterangan": "garis temuan menunggu admin", "label": ["AI 4"],
                      "asal": "belum memengaruhi penandaan"},
                     {"nilai": f"{idrg['ambang']} jam", "satuan": "", "keterangan": "garis jam baru di dunia iDRG tiruan", "label": ["AI 4"],
                      "asal": "ditemukan ulang tanpa ubah kode" if self.idrg["t21"]["lolos"] else "belum ditemukan ulang"}],
            "garis": rows, "n_garis": len(found),
            "kaki_tabel": f"Menampilkan {len(rows)} baris dari {len(found)} garis; garis yang tidak menyala diringkas.",
            "terpilih": next((x["id"] for x in rows if x.get("fakta") and x["status"] == "temuan"), next((x["id"] for x in rows if x.get("fakta")), rows[0]["id"])),
            "t24": {"judul": f"Uji kenyataan T24, {num(r['n_klaim'])} klaim: {sum(r['t24']['jalur'].values())} dari {len(r['t24']['jalur'])} jalur "
                             "yang sudah diketahui ditemukan ulang tanpa diberi tahu.",
                    "jalur": [[names.get(k, k), bool(v)] for k, v in r["t24"]["jalur"].items()],
                    "catatan": (f"{' dan '.join(direct)} ditemukan lewat pindai kode langsung. " if direct else "")
                               + "Dihitung di laptop; hanya agregat nasional, tanpa menilai fasilitas tertentu."},
            "catatan_jujur": "Garis temuan adalah pola pembayaran yang dibaca model pengganti, bukan aturan grouper resmi, dan belum memengaruhi penandaan "
                             f"sebelum disetujui admin. Uji DEV T20 {'lolos' if a['t20']['lolos'] else 'gagal'}: {len(wrong)} garis yang tidak dimanipulasi ikut menyala"
                             + (f" ({' dan '.join(sorted(wrong))})." if wrong else "."),
        }
        if jam:
            u = jam["uji"]
            planted = a["rupiah_perkiraan_vs_tertanam"].get(f"jam_ventilasi {jam['ambang']}", {}).get("tertanam")
            t3 = self.lines_test["t3"]
            out["rincian_jam"] = {
                "fakta": [f"Ambang lewat kode {jam['lewat_kode']}: {group(jam)}, tarif ×{num(jam['kelipatan_median'], 1)}.",
                          f"Uji asimetri: S({jam['ambang']}) {sign(u['S'])} (rentang {sign(u['rentang95'][0])} sampai {sign(u['rentang95'][1])}). "
                          f"Plasebo 120 dan 144 jam {'bersih' if t3['lolos'] else 'tidak bersih'}.",
                          f"Rupiah {'belum terukur' if not u['rupiah_terukur'] else 'terukur'}: rentang Rp{billions(u['rupiah_rentang95'][0])}–"
                          f"{billions(u['rupiah_rentang95'][1])} M." + (f" Di DEV nilai tertanamnya {short_rp(planted)}." if planted else "")],
                "titik": [[x["garis"], x["S"], x["bawah"], x["atas"]] for x in self.lines_test["gabungan"]],
                "keterangan": "Sumbu X: garis jam ventilasi. S(L): penumpukan klaim tepat di atas garis dibanding di bawahnya, dikoreksi pola 24 jam. Garis tegak = rentang 95%.",
                "catatan": f"Uji ini lemah: di dunia kembar tanpa kecurangan pun S({jam['ambang']}) = {sign(twin[jam['ambang']]['S'])}. "
                           "Bukti per klaim datang dari AI 2, yang menghitung jam dari RME."}
        return out

    # ---------- Layar 6 ----------

    def audit(self, budget: int, policy: str, order: str) -> dict:
        sim, ex, load, by_order = self.ai3["simulasi"], self.ai3["contoh"], self.ai3["beban"], self.ai3["urutan"]
        agen, reps, cap = sim["agen"], sim["ulangan"], int(sim.get("kapasitas", A3.CAPACITY))
        official = A3.interval(ex["ppi"], A3.official_variance(ex["var_desain"], ex["var_model"]))
        design = A3.interval(ex["ppi"], ex["var_desain"])
        a, b = by_order["agen"], by_order["agen_peluang"]
        found_a, found_b = a["rupiah_setahun_rerata"], b["rupiah_setahun_rerata"]
        alike = "hampir sama" if abs(found_b / found_a - 1) < 0.05 else "lebih besar" if found_b > found_a else "lebih kecil"

        def dose(s: dict) -> str:
            k = s.get("ppi_resmi") or s.get("ppi_varians_desain")
            return f"kena {round(100 * k['cakupan_95'])}%" if k else "tidak bisa"

        same = budget == cap and policy == "agen" and order == "rupiah"
        year = self.c.tgl_pulang.max().year
        return {
            "sumber_data": SOURCE, "bagian_contoh": [], "bulan": f"Pembebanan {MON[-1]} {year}, bulan ke-{A3.MONTHS}",
            "pengaturan": {"anggaran": cap, "asal_anggaran": "2 verifikator × 3 klaim/hari × 10 hari (asumsi, bisa diubah)", "kebijakan": "agen",
                           "batas_pi": f"Batas bawah π {num(A3.PI_MIN, 3)} memakai ±{round(agen['audit_dari_lantai_pi'])} dari {cap} audit per bulan untuk eksplorasi",
                           "catatan_urutan": f"Peluang: rupiah ditemukan {alike} ({miliar(found_b)} vs {miliar(found_a)}), tetapi rentang "
                                             f"takaran sekitar {round(100 * (b['ppi_resmi']['lebar_rerata'] / a['ppi_resmi']['lebar_rerata'] - 1))}% lebih lebar."},
            "daftar": [{"nomor_sep": x["nomor_sep"], "kode_rs": x["kode_rs"], "alasan": "eksplorasi" if x["alasan"] == A3.EXPLORE_REASON else "nilai",
                        "pi": round(float(x["pi"]), 4), "dipertaruhkan": int(x["dipertaruhkan"]), "temuan": int(x["temuan"])} for x in ex["bulan12"]],
            "takaran": {"total": ex["ppi"], "rentang_resmi": list(official), "rentang_varians_desain": list(design),
                        "cakupan_varians_desain": agen["ppi_varians_desain"]["cakupan_95"], "ht": ex["ht"], "nilai_sebenarnya": ex["sebenarnya"],
                        "rupiah_ditemukan": agen["rupiah_setahun_rerata"], "porsi_ditemukan": agen["porsi_kebocoran_ditemukan"],
                        "ket_ditemukan": f"rata-rata {reps['agen']} simulasi", "skala": nice_max(official[1]),
                        "kaki": f"{reps['agen']} simulasi: rentang resmi kena {round(100 * agen['ppi_resmi']['cakupan_95'])}% kali; lebar rentang sekitar "
                                f"{num(agen['ppi_resmi']['lebar_dibanding_total_ditanam'], 1)} kali total kebocoran."},
            "kurva": {"bulan": list(MON), "agen": [round(x / 1e6) for x in agen["kurva_rupiah_per_bulan"]],
                      "statis": [round(x / 1e6) for x in sim["statis_gabungan"]["kurva_rupiah_per_bulan"]], "ulangan": reps["agen"],
                      "kaki": f"Januari: skor statis sama, tetapi klaim dipilih lewat undian berbobot π, bukan {cap} teratas. Pola yang belum diajarkan ke "
                              f"AI 1 dan AI 2 ditemukan median bulan ke-{int(agen['bulan_modus_tersembunyi_median'])}."},
            "perbandingan": [{"kebijakan": name, "rupiah_per_100": sim[k]["rupiah_per_100_audit"], "audit_rs_jujur_per_100": round(sim[k]["klaim_rs_jujur_per_100_audit"]),
                              "takaran": dose(sim[k])} for name, k in (("Agen belajar", "agen"), ("Skor statis", "statis_gabungan"), ("Acak saja", "acak"))],
            "kaki_perbandingan": f"{reps['agen']} simulasi agen dan acak, {reps['statis_gabungan']} skor statis; RS beradaptasi; agen menyentuh "
                                 f"{round(agen['rs_jujur_diaudit_rerata'])} dari {load['rs_jujur']} RS jujur.",
            "permintaan": {"anggaran": budget, "kebijakan": policy, "urutan": order},
            "catatan_permintaan": None if same else (f"Simulasi AI 3 yang tersimpan hanya untuk anggaran {cap}, agen belajar, urut rupiah harapan; mesin dibekukan dan "
                                                     "tidak dijalankan ulang dari API. Daftar dan takaran di bawah tetap untuk pengaturan itu; kurva dan perbandingan "
                                                     "memuat kebijakan lain."),
        }

    # ---------- Layar 7 ----------

    def report(self, decisions: list[dict]) -> dict:
        q = self.queue(decisions)
        rows, s = q["rs"], q["ringkasan"]
        ai1 = [r for r in rows if r["mesin_penanda"] == "AI 1"]
        doubtful = [r for r in rows if r["modus"] == "rme_meragukan"]
        others = [r for r in rows if r["mesin_penanda"] == "AI 2" and r["modus"] != "rme_meragukan"]
        status_text = {"tidak_mendukung": "lapis RME tidak mendukung", "asal_meragukan": "asal-usul catatan meragukan", "mendukung": "isi RME mendukung",
                       "tidak_dapat_disimpulkan": "tidak dapat disimpulkan", "belum_dibaca": "belum dibaca"}
        table, attach, plans = [], [], {}
        for r in rows[:5]:
            p = self.profile(r["kode_rs"], decisions)
            counts = dict((k, v) for k, v in p["kartu_rme"]["hitungan"])
            if r["mesin_penanda"] == "AI 1":
                read = p["klaim_total"]
                held = counts.get("RME tidak mendukung", 0) + counts.get("Asal-usul meragukan", 0)
                evidence = f"Lapis RME menahan {held} dari {read} klaim teratas"
                plan = "Audit" if held * 2 >= read else "Klarifikasi"
                claimed, estimate, spread = f"{r['diakui']} vs {r['wajar']}", miliar(r["rupiah"]), f"{num(r['rupiah_bawah'] / 1e9, 2)}–{num(r['rupiah_atas'] / 1e9, 2)}"
            else:
                parts = [f"{counts.get('Catatan nyaris identik', 0)} klaim catatan kembar", f"{counts.get('Ditulis dalam satu sesi', 0)} klaim ditulis dalam satu sesi"]
                evidence = ("; ".join(x for x in parts if not x.startswith("0 ")).capitalize() if r["modus"] == "rme_meragukan"
                            else f"Bacaan RME menahan {r['n_klaim_dipertaruhkan']} klaim")
                plan = "Audit" if r["modus"] == "rme_meragukan" else "Klarifikasi"
                claimed, estimate, spread = "lolos AI 1", miliar(r["rupiah"]), f"dipertaruhkan, {r['n_klaim_dipertaruhkan']} klaim"
            plans[r["kode_rs"]] = plan
            table.append({"kode_rs": r["kode_rs"], "modus": r["modus"], "diakui": claimed, "perkiraan": estimate, "rentang": spread, "bukti": evidence,
                          "tindak": plan + (" (berjalan)" if r["status_penanganan"] != "baru" else "")})
            if p["klaim"]:
                c = p["klaim"][0]
                attach.append([c["nomor_sep"], r["kode_rs"], c["selisih_tarif"], status_text[c["status_rme"]]])
        run = f"{self.updated.day} {MON[self.updated.month - 1]} {self.updated.year} {self.updated:%H.%M}"
        period = q["periode"]["penilaian"].removeprefix("data 12 bulan, ")
        facts: dict[str, list[str]] = {}
        template: list[str] = []
        if ai1:
            top = self.profile(ai1[0]["kode_rs"], decisions)
            counts = dict((k, v) for k, v in top["kartu_rme"]["hitungan"])
            facts |= {"n_rs_ai_satu": [f"{len(ai1)} RS", "RS ditandai AI 1 (AI 1, Statistik)"], "total": [miliar(s["total_rupiah"], 1), "perkiraan kelebihan bayar 12 bulan (AI 1, Kode)"],
                      "rs_teratas": [ai1[0]["kode_rs"], "RS dengan perkiraan terbesar (AI 1)"], "rupiah_teratas": [miliar(ai1[0]["rupiah"]), "perkiraan kelebihan RS itu (AI 1, Kode)"],
                      "ditahan_teratas": [f"{counts.get('RME tidak mendukung', 0) + counts.get('Asal-usul meragukan', 0)} klaim", "klaim teratas yang ditahan lapis RME (AI 2)"],
                      "dibaca_teratas": [f"{top['klaim_total']} klaim teratas", "klaim kelebihan menurut AI 1 (AI 1)"]}
            template += ["{n_rs_ai_satu} yang ditandai AI 1 menyumbang perkiraan kelebihan bayar {total} selama 12 bulan; terbesar {rs_teratas} sebesar {rupiah_teratas}.",
                         "Di {rs_teratas}, lapis RME menahan {ditahan_teratas} dari {dibaca_teratas}."]
        if doubtful:
            facts |= {"n_rme": [f"{len(doubtful)} RS", "RS dengan RME meragukan (AI 2, Kode)"], "rs_rme": [doubtful[0]["kode_rs"], "RS dengan nilai dipertaruhkan terbesar (AI 2)"],
                      "rupiah_rme": [miliar(doubtful[0]["rupiah"]), "nilai dipertaruhkan RS itu (Kode)"]}
            template.append("AI 2 menandai {n_rme} karena asal-usul catatan RME meragukan; terbesar {rs_rme} dengan nilai dipertaruhkan {rupiah_rme}.")
        if others:
            facts["n_lain"] = [f"{len(others)} RS", "RS lolos AI 1 yang klaimnya ditahan bacaan RME (AI 2)"]
            template.append("Bacaan RME juga menahan klaim di {n_lain} lain yang lolos pemeriksaan berbasis klaim.")
        audit = [k for k, v in plans.items() if v == "Audit"]
        clarify = [k for k, v in plans.items() if v == "Klarifikasi"]
        facts |= {"usul_audit": [", ".join(audit) or "tidak ada", "usulan dari tabel lima RS teratas (Kode)"],
                  "usul_klarifikasi": [", ".join(clarify) or "tidak ada", "usulan dari tabel lima RS teratas (Kode)"]}
        template.append("Usulan: audit {usul_audit}; klarifikasi {usul_klarifikasi}.")
        return {
            "sumber_data": SOURCE, "bagian_contoh": [], "periode": q["periode"]["klaim_diperiksa"].removeprefix("pembebanan ").capitalize(),
            "kepala": {"wilayah": "Wilayah Uji (data sintetis)", "dianalisis": f"Dianalisis {run}, model {MODEL_VERSION}",
                       "judul": f"Ringkasan pemeriksaan garis tarif, {q['periode']['klaim_diperiksa'].removeprefix('pembebanan ')}",
                       "sub": f"Penilaian RS memakai data 12 bulan ({period}); klaim yang diperiksa: {q['periode']['klaim_diperiksa']}."},
            "angka": [{"nilai": f"{s['n_ditandai']} dari {s['n_rs']}", "label": "RS ditandai", "sub": f"{s['per_mesin']['AI 1']} oleh AI 1, {s['per_mesin']['AI 2']} oleh AI 2"},
                      {"nilai": miliar(s["total_rupiah"], 1), "label": "perkiraan kelebihan bayar 12 bulan",
                       "sub": f"jumlah rentang Rp{num(s['total_bawah'] / 1e9, 1)}–{num(s['total_atas'] / 1e9, 1)} miliar"},
                      {"nilai": f"{len(doubtful)} RS", "label": "dengan RME meragukan", "sub": "lolos pemeriksaan klaim"}],
            "rs": table, "lampiran": attach, "surat_rs": next((t["kode_rs"] for t in table if t["tindak"].startswith("Klarifikasi")), table[0]["kode_rs"] if table else None),
            "ket_lampiran": "(daftar lengkap di Profil RS)",
            "sumber": f"Data E-Klaim dan RME dunia DEV (sintetis), penilaian RS {period}; tarif INA-CBG Permenkes 3/2023; model {MODEL_VERSION}; run DEV {run}",
            "kaki": "Sinyal untuk diperiksa, bukan tuduhan. Keputusan ada di verifikator. Jangan diedarkan sebelum klarifikasi RS.",
            "fakta_narasi": facts, "templat_narasi": template,
        }

    def letter(self, rs: str, decisions: list[dict]) -> dict | None:
        p = self.profile(rs, decisions)
        if p is None:
            return None
        start, end = self.c.tgl_pulang.min(), self.c.tgl_pulang.max()
        f = p["fakta_ringkasan"]
        facts = {"rs": [rs, "kode RS sintetis"], "periode": [f"{MONTHS[start.month - 1]}–{MONTHS[end.month - 1]} {end.year}", "periode penilaian RS"]}
        if p["mesin_penanda"] == "AI 1":
            facts |= {k: [f[k][0], f[k][1]] for k in ("diakui", "wajar", "wajar_bawah", "wajar_atas", "kelebihan")}
            template = ["Berdasarkan pemeriksaan pasca-klaim {periode}, {rs} mengajukan {diakui} garis ventilator (ventilasi mekanik atau intubasi), sedangkan bukti "
                        "pada klaim hanya mendukung sekitar {wajar} (rentang {wajar_bawah}–{wajar_atas}).",
                        "Untuk {kelebihan} terlampir, kami mohon RS mengirimkan dokumen pendukung pemakaian ventilator: laporan tindakan intubasi, lembar "
                        "observasi ventilator per jam, dan catatan penyapihan."]
            n = int(f["kelebihan"][0].split()[0])
        else:
            why = {"rme_meragukan": "catatannya nyaris identik antarpasien atau ditulis dalam satu sesi", "fiktif": "bacaan RME tidak menemukan ventilasi invasif",
                   "diperpanjang": "jam ventilasi menurut RME di bawah 96 jam"}[p["modus"]]
            n = p["klaim_total"]
            facts["ditahan"] = [f"{n} klaim", "klaim yang ditahan bacaan RME (AI 2)"]
            template = ["Berdasarkan pemeriksaan pasca-klaim {periode}, rekam medis untuk {ditahan} dari {rs} perlu diklarifikasi karena " + why + ".",
                        "Untuk klaim terlampir, kami mohon RS mengirimkan dokumen asli catatan ICU, lembar observasi ventilator per jam, dan log waktu penulisan "
                        "rekam medis."]
        today = datetime.now()
        return {"kepada": f"Direktur {rs}", "perihal": "Permintaan klarifikasi klaim ventilasi mekanik", "tanggal": f"{today.day} {MONTHS[today.month - 1]} {today.year}",
                "fakta": facts, "templat": template,
                "penutup": "Surat ini adalah permintaan klarifikasi, bukan kesimpulan pemeriksaan. Mohon dokumen dikirim sesuai jangka waktu klarifikasi yang berlaku.",
                "lampiran": f"Lampiran: daftar {n} klaim (nomor SEP, tanggal layanan, selisih tarif) dari Profil {rs}."}
