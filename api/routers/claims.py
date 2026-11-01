import json
import os
import queue
import sqlite3
import threading
import time
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

import joblib
import numpy as np
import pandas as pd
from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from api.utils import runtime
from engine import MODEL_VERSION
from engine import ai1 as A1
from engine import ai2 as B2
from engine import ai2_assertion as AS
from engine import ai2_fast as F2
from engine import ai2_physiology as P2
from engine.contracts import CheckResponse, Claim, RmeResult, Step, TarifRs, split_codes, validation_issues
from engine.data import DEV, ROOT, load_world
from engine.synth import grouper as G

router = APIRouter(prefix="/api/v1", tags=["Klaim"])
DOC_EXAMPLE = {"nomor_sep": "SEP-4760758990", "kode_rs": "RS-077", "umur": 60, "jenis_kelamin": "P", "jenis_rawat": 1, "kelas_rawat": 1, "cara_masuk": "emd",
               "tgl_masuk": "2025-08-13T18:20:00+07:00", "tgl_pulang": "2025-08-24T14:38:00+07:00", "diagnosa": "S06.9#A09.9#I10#K30",
               "procedure": "93.11#96.04#96.71#99.18", "icu_indikator": 1, "icu_los": 1, "ventilator_hour": 28,
               "ventilator": {"use_ind": 1, "start_dttm": "2025-08-19T19:40:00+07:00", "stop_dttm": "2025-08-20T23:40:00+07:00"}, "discharge_status": 4,
               "tarif_rs": {"prosedur_non_bedah": 391800, "konsultasi": 217600, "tenaga_ahli": 3303300, "keperawatan": 3027900, "penunjang": 3970200,
                            "radiologi": 1741200, "laboratorium": 7693700, "kamar": 6338400, "rawat_intensif": 4891200, "obat": 15536600, "alkes": 1481600,
                            "bmhp": 2445200}}
MODELS = ROOT / "models"
QUICK_LAYERS = ("kata_kunci", "asersi", "klaim_vs_lembar", "teks_vs_lembar", "kloning_kuat", "tulis_serentak")
QUICK_TEXT = {"kata_kunci": "aturan kata kunci tidak menemukan ventilasi di RME", "asersi": "model asersi membaca tidak ada ventilasi invasif",
              "klaim_vs_lembar": "lembar tanda vital jauh di bawah jam yang diklaim", "teks_vs_lembar": "lembar tanda vital jauh di bawah jam yang tertulis di RME",
              "kloning_kuat": "catatan dan lembar tanda vital sama dengan pasien lain", "tulis_serentak": "seluruh catatan ditulis dalam satu sesi"}


@dataclass
class Ai2Models:
    physiology: Any
    readers: dict
    rs_fold: dict


@dataclass
class Engine:
    bundle: A1.Bundle
    hospitals: pd.DataFrame
    claims: pd.DataFrame
    docs: dict[str, pd.DataFrame]
    vitals: dict[str, pd.DataFrame]
    ai2: Ai2Models | None = None
    ai2_error: str | None = None
    rs_corpus: dict[str, pd.DataFrame] = field(default_factory=dict)
    late_baseline: dict[str, pd.DataFrame] = field(default_factory=dict)


@dataclass
class Job:
    token: int
    claim: Claim
    codes: set[str]
    created: float
    initial: str
    ai1_ms: int
    quick: dict
    started: float | None = None


@dataclass
class State:
    engine: Engine
    db: Path
    jobs: dict[str, Job] = field(default_factory=dict)
    pending: queue.Queue = field(default_factory=queue.Queue)
    lock: threading.Lock = field(default_factory=threading.Lock)


QUEUE_DDL = """
CREATE TABLE IF NOT EXISTS antrean_rme (
    nomor_sep TEXT PRIMARY KEY,
    token INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('antre', 'berjalan', 'selesai', 'gagal')),
    diperbarui TEXT NOT NULL,
    hasil TEXT
);
"""


def _db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, autocommit=True, timeout=5.0)
    conn.executescript(QUEUE_DDL)
    return conn


def _save(state: State, sep: str, token: int, status: str, result: dict | None = None) -> None:
    # The queue table is working state, not the decision log, so rows are updated in place; a stale token never overwrites a newer job.
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with closing(_db(state.db)) as conn:
        conn.execute("INSERT INTO antrean_rme (nomor_sep, token, status, diperbarui, hasil) VALUES (?, ?, ?, ?, ?) "
                     "ON CONFLICT (nomor_sep) DO UPDATE SET token = excluded.token, status = excluded.status, diperbarui = excluded.diperbarui, "
                     "hasil = excluded.hasil WHERE excluded.token >= antrean_rme.token",
                     (sep, token, status, now, json.dumps(result, ensure_ascii=False) if result is not None else None))


def _load(state: State, sep: str) -> tuple[int, str, dict | None] | None:
    with closing(_db(state.db)) as conn:
        row = conn.execute("SELECT token, status, hasil FROM antrean_rme WHERE nomor_sep = ?", (sep,)).fetchone()
    return (row[0], row[1], json.loads(row[2]) if row[2] else None) if row else None


def load_engine() -> Engine:
    w = load_world(DEV / "dasar")
    claims = w["claims"].set_index("nomor_sep")
    docs = pd.read_parquet(DEV / "dasar" / "rme_documents.parquet")
    vitals = pd.read_parquet(DEV / "dasar" / "rme_vitals.parquet")
    # Each hospital's usual write delay comes from its stored line-population records, as in ai2_dev.late_population.
    line = claims[A1.in_line(claims)]
    delays = F2.key_document_delay(docs[docs.nomor_sep.isin(line.index)], F2.ventilation_windows(line))
    return Engine(A1.load_bundle(), w["hospitals"].set_index("kode_rs"), claims, {s: g for s, g in docs.groupby("nomor_sep")},
                  {s: g for s, g in vitals.groupby("nomor_sep")}, late_baseline=F2.delay_baseline(delays, claims.kode_rs))


def warm_ai2(engine: Engine) -> None:
    from engine import ai2_dev as D2
    from engine import ai3_worlds as V
    try:
        D2.use_embedding_cache(V.HEADS)
        path_p, path_r = MODELS / f"ai2-fisiologi-{MODEL_VERSION}.joblib", MODELS / f"ai2-asersi-{MODEL_VERSION}.joblib"
        if path_p.exists():
            physiology = joblib.load(path_p)
        else:
            icu = ROOT / "data" / "icu_open"
            physiology, _ = P2.train(pd.read_parquet(icu / "eicu_hourly.parquet"), pd.read_parquet(icu / "mimic_hourly.parquet"))
            joblib.dump(physiology, path_p)
        if path_r.exists():
            readers, rs_fold = joblib.load(path_r)
        else:
            readers, rs_fold = V.fold_readers()
            joblib.dump((readers, rs_fold), path_r)
        # Embeds the example records once, so a demo check never waits behind an LLM read for Ollama's embedding call.
        for _, _, sep, _ in EXAMPLES:
            if sep in engine.docs:
                rs = engine.claims.at[sep, "kode_rs"]
                readers[rs_fold.get(rs, 0)].read(B2.sentences(B2.assemble(engine.docs[sep])))
        engine.ai2 = Ai2Models(physiology, readers, rs_fold)
    except Exception as e:  # noqa: BLE001 - any failure leaves AI 1 serving and is reported in every response
        engine.ai2_error = f"lapis AI 2 gagal dimuat: {e}"


def _frame(claim: Claim, h: pd.Series) -> pd.DataFrame:
    rec = claim.model_dump()
    tarif = rec.pop("tarif_rs")
    vent = rec.pop("ventilator") or {}
    row = {**rec, **{f"tarif_rs_{k}": tarif.get(k, 0) for k in TarifRs.model_fields},
           "ventilator_use_ind": vent.get("use_ind", 0), "bulan": claim.tgl_pulang.month}
    df = pd.DataFrame([row])
    for c in ("tgl_masuk", "tgl_pulang"):
        df[c] = pd.to_datetime(df[c]).dt.tz_localize(None)
    dx = split_codes(claim.diagnosa)
    df["cbg"] = G.group(dx[0][:3], set(claim.procedures), [d[:3] for d in dx[1:]], claim.ventilator_hour)
    df["tarif_ina_cbg"] = G.tariff(int(h.regional), h.kelas_rs, h.kepemilikan, df.cbg.iat[0], claim.kelas_rawat)
    return df


def _rs_docs(engine: Engine, rs: str) -> pd.DataFrame:
    if rs not in engine.rs_corpus:
        seps = [s for s in engine.claims.index[engine.claims.kode_rs == rs] if s in engine.docs]
        engine.rs_corpus[rs] = pd.concat([engine.docs[s] for s in seps]) if seps else pd.DataFrame(columns=["nomor_sep", "jenis", "teks"])
    return engine.rs_corpus[rs]


def quick_layers(engine: Engine, claim: Claim, codes: set[str]) -> dict:
    sep = claim.nomor_sep
    docs = engine.docs.get(sep)
    if docs is None:
        return {"tersedia": False, "alasan": "RME untuk SEP ini tidak ditemukan di penyimpanan RME"}
    if engine.ai2 is None:
        return {"tersedia": False, "alasan": engine.ai2_error or "lapis cepat AI 2 sedang dimuat"}
    claimed = float(claim.ventilator_hour)
    kw = B2.read_claim(docs, codes, claimed, use_llm=False)
    reader = engine.ai2.readers[engine.ai2.rs_fold.get(claim.kode_rs, 0)]
    record = B2.assemble(docs)
    sentences = B2.sentences(record)
    read = reader.read(sentences)
    second = AS.ventilation(read)
    vit = engine.vitals.get(sep)
    sheet = float(P2.ventilated_hours(P2.hourly_ventilation(engine.ai2.physiology, vit)).get(sep, np.nan)) if vit is not None else None
    corpus = _rs_docs(engine, claim.kode_rs)
    corpus = corpus if sep in set(corpus.nomor_sep) else pd.concat([corpus, docs])
    rs = pd.Series(claim.kode_rs, index=pd.Index(corpus.nomor_sep.unique()))
    clones = F2.clone_scores(corpus, rs)
    if sep not in clones.index:
        # Clone scores skip discharge summaries, so a record with only a summary has nothing to compare.
        clones.loc[sep] = {"kemiripan_maks": 0.0, "pasangan_teratas": "", "n_klaim_mirip": 0, "kloning": False}
    trail = F2.write_trail(docs, pd.Series({sep: pd.Timestamp(claim.tgl_pulang).tz_localize(None)}))
    partner = clones.pasangan_teratas.get(sep, "")
    vit_pair = pd.concat([v for s in (sep, partner) if (v := engine.vitals.get(s)) is not None]) if vit is not None else pd.DataFrame(columns=F2.SHEET_VALUES + ["nomor_sep", "waktu"])
    origin = F2.provenance(clones.loc[[sep]], trail, vit_pair).loc[sep]
    billed = bool(codes & (B2.VENT_CODES | {"96.04"}))
    text_hours = kw.hours or 0.0
    flags = {
        "kata_kunci": kw.verdict == "tidak_mendukung",
        "asersi": billed and second == "tidak",
        "klaim_vs_lembar": sheet is not None and claimed >= 12 and sheet < 0.2 * claimed,
        "teks_vs_lembar": sheet is not None and text_hours >= 12 and sheet < 0.2 * text_hours,
        "kloning_kuat": bool(origin.kloning_kuat),
        "tulis_serentak": bool(origin.tulis_serentak),
    }
    window = pd.DataFrame({"mulai": [pd.Timestamp(claim.ventilator.start_dttm if claim.ventilator and claim.ventilator.start_dttm else claim.tgl_masuk)],
                           "selesai": [pd.Timestamp(claim.ventilator.stop_dttm if claim.ventilator and claim.ventilator.stop_dttm else claim.tgl_pulang)]},
                          index=[sep]).apply(lambda col: col.dt.tz_localize(None))
    delays = F2.key_document_delay(docs, window)
    late = F2.late_key_documents(delays, F2.delay_scores(delays, pd.Series(claim.kode_rs, index=delays.index), engine.late_baseline)).get(sep, "")
    mentions = read[read.sebutan]
    return {"tersedia": True, "bendera": flags, "bersih": not any(flags.values()), "kata_kunci": kw.verdict, "pembaca_kedua": second,
            "dokumen_kunci_terlambat": late or None,
            "jam_lembar": sheet, "jam_teks": kw.hours, "kemiripan_maks": float(clones.kemiripan_maks.get(sep, 0.0)),
            "asal_usul": str(origin.alasan) or None,
            "sebutan": [{"teks": t, "alat": a, "asersi": s} for t, a, s in mentions[["teks", "alat", "asersi"]].head(6).itertuples(index=False)]}


def to_payload(sep: str, r: pd.Series) -> dict:
    # DEV times are wall-clock WIB, written with their offset as E-Klaim would send them.
    def iso(t):
        return None if pd.isna(t) else pd.Timestamp(t).strftime("%Y-%m-%dT%H:%M:%S+07:00")
    vent = {"use_ind": 1, "start_dttm": iso(r.ventilator_start_dttm), "stop_dttm": iso(r.ventilator_stop_dttm)} if r.ventilator_use_ind else None
    return {"nomor_sep": sep, "kode_rs": r.kode_rs, "umur": int(r.umur), "jenis_kelamin": r.jenis_kelamin, "jenis_rawat": int(r.jenis_rawat),
            "kelas_rawat": int(r.kelas_rawat), "cara_masuk": r.cara_masuk, "tgl_masuk": iso(r.tgl_masuk), "tgl_pulang": iso(r.tgl_pulang),
            "diagnosa": r.diagnosa, "procedure": r.procedure, "icu_indikator": int(r.icu_indikator), "icu_los": int(r.icu_los),
            "ventilator_hour": int(r.ventilator_hour), "ventilator": vent, "discharge_status": int(r.discharge_status),
            "tarif_rs": {k: int(r[f"tarif_rs_{k}"]) for k in TarifRs.model_fields if int(r[f"tarif_rs_{k}"])}}


def _reasons(bundle: A1.Bundle, X: pd.DataFrame, mode: str) -> list[dict]:
    return [{"teks": r["teks"], "arah": "turun" if r["arah"] == "menurunkan" else "naik", "mesin": "AI 1"} for r in bundle.reasons(X, mode)[0]]


def check(state: State, claim: Claim, t_valid: float) -> CheckResponse:
    engine = state.engine
    start = time.perf_counter()
    h = engine.hospitals.loc[claim.kode_rs]
    df = _frame(claim, h)
    hosp = engine.hospitals.reset_index()
    X = A1.features(A1.evidence(df, hosp), engine.bundle.vocab)
    t_feat = time.perf_counter()
    p_f = float(engine.bundle.predict(X, "fiktif")[0])
    window = bool(A1.prolonged_window(df)[0])
    p_p = float(engine.bundle.predict(X, "panjang")[0]) if window else None
    t_ai1 = time.perf_counter()
    in_line = bool(A1.in_line(df)[0])
    codes = set(claim.procedures)
    stake = int(A1.tariff_deltas(df, hosp, "fiktif", np.ones(1, bool))[0])
    reasons = _reasons(engine.bundle, X, "fiktif") + (_reasons(engine.bundle, X, "panjang") if window else [])
    steps = [Step(nama="Validasi skema", mesin="Kode", waktu_ms=round(t_valid)), Step(nama="Fitur bukti", mesin="Kode", waktu_ms=round((t_feat - start) * 1000)),
             Step(nama="Peluang didukung", mesin="AI 1", waktu_ms=round((t_ai1 - t_feat) * 1000))]
    if not in_line:
        steps += [Step(nama="Pilih jalur", mesin="Kode", waktu_ms=0)]
        note = "di luar populasi garis ventilator; TAPAL tidak menilai klaim ini"
        return CheckResponse(nomor_sep=claim.nomor_sep, status="lolos_cepat", peluang_didukung_bukti=round(p_f, 4), alasan=[note],
                             alasan_rinci=[{"teks": note, "arah": None, "mesin": "Kode"}], selisih_tarif_dipertaruhkan=0,
                             rme=RmeResult(status="dilewati"), waktu_proses_ms=round(t_valid + (time.perf_counter() - start) * 1000), langkah=steps)
    quick = quick_layers(engine, claim, codes)
    t_quick = time.perf_counter()
    steps.append(Step(nama="Lapis cepat RME", mesin="AI 2", waktu_ms=round((t_quick - t_ai1) * 1000)))
    status = engine.bundle.status(p_f, p_p, quick["bersih"] if quick["tersedia"] else None)
    if quick["tersedia"]:
        reasons += [{"teks": QUICK_TEXT[k], "arah": "turun", "mesin": "AI 2"} for k, v in quick["bendera"].items() if v]
    else:
        reasons.append({"teks": f"lapis cepat AI 2 belum tersedia ({quick['alasan']}); jalur cepat ditahan", "arah": None, "mesin": "AI 2"})
    steps.append(Step(nama="Pilih jalur", mesin="Kode", waktu_ms=round((time.perf_counter() - t_quick) * 1000)))
    ai1_ms = round(t_valid + (time.perf_counter() - start) * 1000)
    with state.lock:
        # Wall-clock tokens keep rising across restarts, so a row left by an earlier process never blocks a newer job.
        job = Job(time.time_ns(), claim, codes, time.perf_counter() - ai1_ms / 1000, status, ai1_ms, quick)
        state.jobs[claim.nomor_sep] = job
    _save(state, claim.nomor_sep, job.token, "antre")
    state.pending.put((claim.nomor_sep, job.token))
    steps.append(Step(nama="Baca RME", mesin="AI 2", waktu_ms=None))
    return CheckResponse(nomor_sep=claim.nomor_sep, status=status, peluang_didukung_bukti=round(p_f, 4), alasan=[r["teks"] for r in reasons],
                         alasan_rinci=reasons, peluang_panjang=round(p_p, 4) if p_p is not None else None, selisih_tarif_dipertaruhkan=stake, rme=RmeResult(status="diproses", hasil=f"/api/v1/klaim/{claim.nomor_sep}/rme"),
                         waktu_proses_ms=ai1_ms, langkah=steps)


def _final_status(initial: str, verdict: str) -> tuple[str, str | None]:
    # An unreadable record keeps the first answer: holding every inconclusive claim would send most honest claims to manual review.
    if verdict == "tidak_mendukung" and initial != "periksa_manual":
        return "periksa_manual", initial
    if verdict == "mendukung" and initial == "periksa_manual":
        return "didukung_rme", initial
    return initial, None


def run_job(state: State, sep: str, token: int) -> None:
    job = state.jobs.get(sep)
    if job is None or job.token != token:
        return
    job.started = time.perf_counter()
    _save(state, sep, token, "berjalan", {"mulai": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    engine = state.engine
    docs = engine.docs.get(sep)
    claim = job.claim
    try:
        if docs is None:
            result = B2.Result("tidak_dapat_disimpulkan", "aturan", 0, ["RME untuk SEP ini tidak ditemukan di penyimpanan RME"], None, None)
        else:
            q = job.quick
            second = (lambda sentences: q["pembaca_kedua"]) if q.get("tersedia") else None
            result = B2.read_claim(docs, job.codes, float(claim.ventilator_hour), use_llm=runtime.llm_active(), second=second,
                                   sheet_hours=q.get("jam_lembar"), provenance=q.get("asal_usul"), late=q.get("dokumen_kunci_terlambat"))
        final, before = _final_status(job.initial, result.verdict)
        quotes = (result.reading or {}).get("kutipan", [])
        payload = {"verdict": result.verdict, "sumber": result.source, "kutipan_terverifikasi": result.quotes_verified, "kutipan": quotes,
                   "alasan": result.reasons, "jam_rme": result.hours, "alat": (result.reading or {}).get("alat_napas_tertinggi"),
                   "ventilasi_invasif": (result.reading or {}).get("ventilasi_invasif"), "ditahan_oleh": result.held_by,
                   "pembaca_kedua": result.second_reader, "jam_lembar": result.sheet_hours, "model": B2.MODEL if result.source == "llm_lokal" else None,
                   "durasi_ms": round((time.perf_counter() - job.started) * 1000), "llm_total_ms": result.total_ms,
                   "token_prompt": result.prompt_tokens, "status_klaim": final, "status_sebelumnya": before,
                   "waktu_proses_ms": round((time.perf_counter() - job.created) * 1000)}
        _save(state, sep, token, "selesai", payload)
    except Exception as e:  # noqa: BLE001 - one bad record must not stop the worker; the claim falls back to manual review
        _save(state, sep, token, "gagal", {"alasan": [f"pembacaan RME gagal: {e}"], "status_klaim": "periksa_manual",
                                           "status_sebelumnya": job.initial if job.initial != "periksa_manual" else None})


def worker(state: State) -> None:
    if state.engine.ai2_error is None:
        warm_ai2(state.engine)
    while True:
        item = state.pending.get()
        if item is None:
            return
        run_job(state, *item)


def start(db: Path) -> State:
    state = State(load_engine(), db)
    # TAPAL_AI2_OFF=1 keeps Ollama's embedding model idle (blind run in progress): the AI 2 layers stay unloaded and every response says so.
    if os.environ.get("TAPAL_AI2_OFF") == "1":
        state.engine.ai2_error = "lapis AI 2 dimatikan sementara (TAPAL_AI2_OFF=1)"
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with closing(_db(db)) as conn:
        # Jobs live in memory, so reads left unfinished by a previous process are closed instead of polling forever.
        conn.execute("UPDATE antrean_rme SET status = 'gagal', diperbarui = ?, hasil = ? WHERE status IN ('antre', 'berjalan')",
                     (now, json.dumps({"alasan": ["server dimulai ulang sebelum RME selesai dibaca; kirim ulang klaim"], "status_klaim": "periksa_manual"},
                                      ensure_ascii=False)))
    threading.Thread(target=worker, args=(state,), daemon=True, name="tapal-ai2").start()
    return state


DATE_FIELDS = (("tgl_masuk",), ("tgl_pulang",), ("ventilator", "start_dttm"), ("ventilator", "stop_dttm"))


def zone_issues(body: dict) -> list[dict]:
    seen = {}
    for path in DATE_FIELDS:
        value = body
        for key in path:
            value = value.get(key) if isinstance(value, dict) else None
        if isinstance(value, str):
            try:
                seen[".".join(path)] = (value, datetime.fromisoformat(value).tzinfo is not None)
            except ValueError:
                continue
    zoned = [k for k, (_, z) in seen.items() if z]
    if not zoned or len(zoned) == len(seen):
        return []
    return [{"kolom": k, "pesan": "semua tanggal wajib memakai zona waktu yang sama, misalnya +07:00", "nilai_diterima": v}
            for k, (v, z) in seen.items() if not z]


@router.post("/klaim/periksa", responses={422: {"description": "Data klaim tidak sah; daftar galat per kolom"}},
             openapi_extra={"requestBody": {"content": {"application/json": {"schema": Claim.model_json_schema(), "example": DOC_EXAMPLE}}, "required": True}})
def check_claim(body: Annotated[dict[str, Any], Body()], request: Request) -> CheckResponse:
    t0 = time.perf_counter()
    try:
        claim = Claim.model_validate(body)
    except ValidationError as e:
        return JSONResponse(status_code=422, content={"galat": [i.model_dump(mode="json") for i in validation_issues(e)],
                                                      "waktu_proses_ms": round((time.perf_counter() - t0) * 1000)})
    except (TypeError, ValueError):
        # Mixed zoned and naive timestamps make the frozen contract's date comparisons raise instead of failing validation.
        return JSONResponse(status_code=422, content={"galat": zone_issues(body) or [{"kolom": "klaim", "pesan": "data klaim tidak dapat diperiksa", "nilai_diterima": None}],
                                                      "waktu_proses_ms": round((time.perf_counter() - t0) * 1000)})
    state: State = request.app.state.claims
    if claim.kode_rs not in state.engine.hospitals.index:
        return JSONResponse(status_code=422, content={"galat": [{"kolom": "kode_rs", "pesan": "kode_rs tidak dikenal di registri RS",
                                                                "nilai_diterima": claim.kode_rs}], "waktu_proses_ms": round((time.perf_counter() - t0) * 1000)})
    return check(state, claim, (time.perf_counter() - t0) * 1000)


@router.get("/klaim/{nomor_sep}/rme")
def claim_rme(nomor_sep: str, request: Request) -> dict[str, Any]:
    state: State = request.app.state.claims
    row = _load(state, nomor_sep)
    if row is not None:
        token, status, result = row
        job = state.jobs.get(nomor_sep)
        if status in ("antre", "berjalan"):
            waiting = sum(1 for _ in list(state.pending.queue))
            elapsed = round(time.perf_counter() - job.started, 1) if job and job.started and status == "berjalan" else 0
            return {"status": "diproses", "tahap": status, "antrean": waiting, "detik_berjalan": elapsed, "llm_aktif": runtime.llm_active(),
                    "lapis_cepat": job.quick if job else None, "sumber_data": "mesin"}
        return {"status": "selesai", "tahap": status, **(result or {}), "lapis_cepat": job.quick if job else None, "sumber_data": "mesin"}
    raise HTTPException(404, f"tidak ada pembacaan RME untuk {nomor_sep}; bacaan layar ada di /api/v1/klaim/{nomor_sep}/bacaan")


EXAMPLES = [
    ("bukti_lengkap", "Bukti lengkap", "SEP-6434053283", "klaim jujur, 96.72 dan 124 jam; lapis cepat bersih"),
    ("bukti_lemah", "Bukti lemah", "SEP-4760758990", "96.71 tanpa sewa alat; AI 1 dan lapis cepat menahan"),
    ("rme_bertentangan", "RME bertentangan", "SEP-5164404390", "data klaim rapi, lolos cepat; RME dibaca LLM tidak mendukung"),
]


@router.get("/klaim/contoh")
def examples(request: Request) -> list[dict[str, Any]]:
    engine: Engine = request.app.state.claims.engine
    out = []
    for key, label, sep, note in EXAMPLES:
        r = engine.claims.loc[sep]
        h = engine.hospitals.loc[r.kode_rs]
        out.append({"kunci": key, "label": label, "keterangan": note, "rs": f"{r.kode_rs}, Kelas {h.kelas_rs} {h.kepemilikan.capitalize()}, Regional {h.regional}",
                    "payload": to_payload(sep, r)})
    broken = {**out[1]["payload"], "umur": -3, "procedure": "96.72", "ventilator_hour": 0, "ventilator": None}
    broken["tgl_pulang"] = (pd.Timestamp(out[1]["payload"]["tgl_masuk"]) - pd.Timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S+07:00")
    out.append({"kunci": "data_rusak", "label": "Data rusak", "keterangan": "umur negatif, 96.72 tanpa jam, tanggal pulang sebelum masuk",
                "rs": out[1]["rs"], "payload": broken})
    return out
