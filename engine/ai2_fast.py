import re

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

from engine import stats as S

CLONE_SIMILARITY = 0.95
BULK_WINDOW_MIN = 180
BULK_SHARE = 0.8
BULK_MIN_NOTES = 4
SHEET_COPY = 0.9
SHEET_VALUES = ["spo2", "fio2", "peep", "rr_set", "rr_total"]
KEY_DOCUMENTS = ("laporan_tindakan", "catatan_perawat")
# p99 of the hospital-relative delay score on honest DEV claims (ai2_dev.late_thresholds, jejak_waktu_rs_ambang.json 12.25 WIB), fixed 1 Nov 2026 before the re-run (TARGETS riwayat baris 11).
LATE_Z_LIMIT = {"laporan_tindakan": 13.15, "catatan_perawat": 16.1}


def _normalized(text: str) -> str:
    # A clone keeps the source's words and shifts its dates, so numbers are blanked before comparing.
    return re.sub(r"\d+", "0", text.lower())


def clone_scores(docs: pd.DataFrame, rs: pd.Series) -> pd.DataFrame:
    d = docs[docs.jenis != "resume_medis"].sort_values(["nomor_sep", "waktu_layanan"])
    text = d.groupby("nomor_sep").teks.agg(" ".join).map(_normalized)
    X = TfidfVectorizer(analyzer="word", ngram_range=(1, 3), min_df=2, sublinear_tf=True).fit_transform(text.to_numpy())
    hospital = rs.reindex(text.index).to_numpy()
    best, near, partner = np.zeros(len(text)), np.zeros(len(text), int), np.full(len(text), "", dtype=object)
    for h in np.unique(hospital):
        idx = np.flatnonzero(hospital == h)
        if len(idx) < 2:
            continue
        sim = (X[idx] @ X[idx].T).toarray()
        np.fill_diagonal(sim, 0)
        top = sim.argmax(axis=1)
        best[idx], partner[idx] = sim[np.arange(len(idx)), top], text.index.to_numpy()[idx[top]]
        near[idx] = (sim >= CLONE_SIMILARITY).sum(axis=1)
    return pd.DataFrame({"kemiripan_maks": best.round(4), "pasangan_teratas": partner, "n_klaim_mirip": near,
                         "kloning": best >= CLONE_SIMILARITY}, index=text.index)


def write_trail(docs: pd.DataFrame, discharge: pd.Series) -> pd.DataFrame:
    d = docs[docs.jenis != "resume_medis"].assign(tulis=lambda x: pd.to_datetime(x.waktu_tulis), layan=lambda x: pd.to_datetime(x.waktu_layanan))
    d["pulang"] = pd.to_datetime(discharge.reindex(d.nomor_sep).to_numpy())

    def one(g: pd.DataFrame) -> pd.Series:
        t = np.sort(g.tulis.to_numpy().astype("datetime64[m]").astype(np.int64))
        together = max(np.searchsorted(t, x + BULK_WINDOW_MIN, side="right") - i for i, x in enumerate(t))
        return pd.Series({"n_catatan": len(g), "porsi_tulis_serentak": together / len(g), "porsi_ditulis_sesudah_pulang": float((g.tulis > g.pulang).mean()),
                          "jeda_tulis_median_jam": float(((g.tulis - g.layan).dt.total_seconds() / 3600).median())})
    cols = ["n_catatan", "porsi_tulis_serentak", "porsi_ditulis_sesudah_pulang", "jeda_tulis_median_jam"]
    # A record holding only a discharge summary has no timed notes to compare (seen on single-claim API checks).
    out = d.groupby("nomor_sep").apply(one) if len(d) else pd.DataFrame(columns=cols, dtype=float)
    # Writing after discharge is shown, not flagged: honest hospitals that batch summaries do it too (DEV trap tulis_massal_jujur).
    out["tulis_massal"] = (out.porsi_tulis_serentak >= BULK_SHARE) & (out.n_catatan >= BULK_MIN_NOTES)
    return out.round(3)


def rs_flags(indicator: pd.Series, rs: pd.Series, n_layak: pd.Series | None = None) -> pd.DataFrame:
    # Same exact test, robust z, and BH as every other layer, with the pooled rate of all RS as the expectation (TARGETS v2 bagian 6).
    y = indicator.astype(int).to_numpy()
    hospital = rs.reindex(indicator.index)
    if n_layak is None:
        n_layak = pd.Series(1, index=indicator.index).groupby(hospital.to_numpy()).sum()
    return S.per_rs_test(hospital.reset_index(drop=True), y, np.full(len(y), y.mean()), np.ones(len(y), bool), n_layak)


MODE_LAYERS = {"fiktif": ("kata_kunci", "asersi", "klaim_vs_lembar", "teks_vs_lembar"), "diperpanjang": ("kata_kunci",),
               "rme_meragukan": ("kloning", "tulis_massal")}


def mode_flags(layers: pd.DataFrame, pools: dict[str, pd.Index], rs: pd.Series, n_layak: dict[str, pd.Series] | None = None) -> dict[str, pd.DataFrame]:
    # One indicator per claim and one exact test per mode (user decision 1 Nov 2026); MIN_KLAIM counts the mode's eligible claims as AI 1 does (TARGETS 117).
    n_layak = n_layak or {}
    return {mode: rs_flags(layers.loc[pools[mode], [c for c in cols if c in layers]].any(axis=1), rs, n_layak.get(mode))
            for mode, cols in MODE_LAYERS.items()}


def sheet_match(a: np.ndarray, b: np.ndarray) -> float:
    # Share of hours, aligned from each stay's first sheet row, where every reading is the same; a copied sheet scores 1.
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    same = (a[:n] == b[:n]) | (np.isnan(a[:n]) & np.isnan(b[:n]))
    return float(same.all(axis=1).mean())


def provenance(clones: pd.DataFrame, trail: pd.DataFrame, vitals: pd.DataFrame) -> pd.DataFrame:
    # Only strong signals hold a verdict (user decision 1 Nov 2026): a text clone with the same vital sheet, or every note in one session.
    sheets = {sep: g[SHEET_VALUES].to_numpy(float) for sep, g in vitals.sort_values(["nomor_sep", "waktu"]).groupby("nomor_sep")}
    empty = np.empty((0, len(SHEET_VALUES)))
    match = pd.Series({sep: sheet_match(sheets.get(sep, empty), sheets.get(partner, empty))
                       for sep, partner in clones.pasangan_teratas[clones.kloning].items()}, dtype=float)
    out = pd.DataFrame(index=clones.index.union(trail.index))
    out["kemiripan_lembar"] = match.reindex(out.index).fillna(0.0)
    out["kloning_kuat"] = clones.kloning.reindex(out.index, fill_value=False).astype(bool) & (out.kemiripan_lembar >= SHEET_COPY)
    one = trail.reindex(out.index)
    out["tulis_serentak"] = (one.porsi_tulis_serentak >= 1.0).fillna(False) & (one.n_catatan >= BULK_MIN_NOTES).fillna(False)
    partner = clones.pasangan_teratas.reindex(out.index)
    out["alasan"] = np.where(out.kloning_kuat, "catatan dan lembar tanda vital sama dengan klaim " + partner.astype(str),
                             np.where(out.tulis_serentak, "seluruh catatan ditulis dalam satu sesi", ""))
    return out


def key_document_delay(docs: pd.DataFrame, windows: pd.DataFrame) -> pd.DataFrame:
    # Key notes written during the claimed ventilation, so a record made up after the fact shows its late write times (TARGETS cerdik-2).
    d = docs[docs.jenis.isin(KEY_DOCUMENTS)].join(windows, on="nomor_sep")
    served = pd.to_datetime(d.waktu_layanan)
    d = d[(served >= d.mulai) & (served <= d.selesai)]
    delay = (pd.to_datetime(d.waktu_tulis) - pd.to_datetime(d.waktu_layanan)) / pd.Timedelta(hours=1)
    return delay.groupby([d.nomor_sep, d.jenis]).median().unstack().reindex(columns=list(KEY_DOCUMENTS))


def _mad(x: pd.Series) -> float:
    return 1.4826 * float((x - x.median()).abs().median())


def delay_baseline(delays: pd.DataFrame, rs: pd.Series) -> dict[str, pd.DataFrame]:
    # Each hospital's own typical write delay, so a hospital that always writes late is compared with itself (user decision 1 Nov 2026).
    out, pooled = {}, {}
    for kind in KEY_DOCUMENTS:
        u = np.log1p(delays[kind].dropna())
        g = u.groupby(rs.reindex(u.index).to_numpy())
        t = pd.DataFrame({"median": g.median(), "skala": g.apply(_mad), "n": g.size()})
        # A hospital with too few key documents borrows the pooled baseline instead of a noisy one of its own.
        t = t[t.n >= S.MIN_KLAIM]
        floor = float(t.skala.median())
        out[kind] = t.assign(skala=t.skala.clip(lower=floor))
        pooled[kind] = {"median": float(u.median()), "skala": max(_mad(u), floor)}
    out["gabungan"] = pd.DataFrame(pooled).T
    return out


def delay_scores(delays: pd.DataFrame, rs: pd.Series, baseline: dict[str, pd.DataFrame]) -> pd.DataFrame:
    hospital = rs.reindex(delays.index)
    out = pd.DataFrame(index=delays.index)
    for kind in KEY_DOCUMENTS:
        b, pooled = baseline[kind], baseline["gabungan"].loc[kind]
        centre = hospital.map(b["median"]).fillna(pooled["median"])
        spread = hospital.map(b["skala"]).fillna(pooled["skala"])
        out[kind] = (np.log1p(delays[kind]) - centre) / spread
    return out


def late_key_documents(delays: pd.DataFrame, scores: pd.DataFrame) -> pd.Series:
    names = {"laporan_tindakan": "laporan tindakan", "catatan_perawat": "catatan perawat"}
    def why(sep: str) -> str:
        # Reasons are shown in the app, so decimals are written the Indonesian way (EYD), as in ai2._hours.
        late = [f"{names[k]} ditulis {delays.at[sep, k]:.0f} jam setelah layanan, jauh di atas kebiasaan RS ini "
                f"(skor keterlambatan {scores.at[sep, k]:.1f} melewati batas {LATE_Z_LIMIT[k]:.2f})".replace(".", ",")
                for k in KEY_DOCUMENTS if pd.notna(scores.at[sep, k]) and scores.at[sep, k] > LATE_Z_LIMIT[k]]
        return "; ".join(late)
    return pd.Series({sep: why(sep) for sep in scores.index}, dtype=str)


def ventilation_windows(claims: pd.DataFrame) -> pd.DataFrame:
    # The claimed ventilator start and stop; a claim without them (intubation only) falls back to the whole stay.
    return pd.DataFrame({"mulai": pd.to_datetime(claims.ventilator_start_dttm).fillna(pd.to_datetime(claims.tgl_masuk)),
                         "selesai": pd.to_datetime(claims.ventilator_stop_dttm).fillna(pd.to_datetime(claims.tgl_pulang))}, index=claims.index)
