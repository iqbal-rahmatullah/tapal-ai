import hashlib
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import httpx
import joblib
import numpy as np
import pandas as pd

from engine import ai2 as B
from engine import ai1 as A1
from engine.ai1_dev import honest_hospitals
from engine import ai2_assertion as A
from engine import ai2_fast as F
from engine import ai2_physiology as P
from engine import narrative as N
from engine import stats as S
from engine.contracts import RmeReading, split_codes
from engine.data import DEV, LAB, is_dev, key_dir, load_world, out_dir, world_dir

OUT = out_dir("ai2-dev")
OUT.mkdir(parents=True, exist_ok=True)
# Readers trained on DEV, their embedding caches, and the stored DEV readings stay in the DEV folder whatever world is evaluated.
DEV_OUT = LAB / "ai2-dev"
READINGS = OUT / "bacaan_llm.jsonl"
TEST_DOCS = DEV_OUT.parent / "uji-llm-ai2"
WORLD, KEY = world_dir(), key_dir()
WORLD_EMBEDDINGS = ("embedding_kalimat_dunia_bge_m3.npy", "embedding_kalimat_dunia_teks.parquet")
# Frozen LLM build: a run stops unless Ollama serves exactly this digest of the model (TARGETS riwayat baris 13).
LLM_DIGEST = "ee665637121887cf3befff38abbb1be4ee117c7db867d97a67e29049ecd7e15f"
EMBEDDINGS = (("embedding_kalimat_bge_m3.npy", "embedding_kalimat_teks.parquet"),
              ("embedding_kalimat_lain_bge_m3.npy", "embedding_kalimat_lain_teks.parquet"))
# Strata mirror TARGETS N_LLM (modus x tingkat x gaya tulisan); the honest stratum is the largest so accuracy has a base.
STRATA = {"jujur": 120, "kelas_naik": 15, "fiktif_biasa": 30, "fiktif_cerdik_1": 30, "karangan": 30, "kloning": 30, "massal": 30,
          "diperpanjang": 20, "intubasi_saja": 15}
# TARGETS N_LLM is 300 for the blind set: the DEV strata scaled to 300, same seed and style round-robin, written before the key opens.
STRATA_300 = {"jujur": 112, "kelas_naik": 14, "fiktif_biasa": 28, "fiktif_cerdik_1": 28, "karangan": 28, "kloning": 28, "massal": 28,
              "diperpanjang": 19, "intubasi_saja": 15}


def stratum(k: pd.DataFrame) -> pd.Series:
    return pd.Series(np.select(
        [k.varian == "intubasi_saja", k.rme_versi == "karangan", k.rme_versi == "kloning", k.rme_versi == "massal",
         k.modus == "diperpanjang", (k.modus == "fiktif") & (k.tingkat == "biasa"), (k.modus == "fiktif") & (k.tingkat == "cerdik_1"),
         k.modus == "kelas_naik", k.modus == ""],
        ["intubasi_saja", "karangan", "kloning", "massal", "diperpanjang", "fiktif_biasa", "fiktif_cerdik_1", "kelas_naik", "jujur"], "lain"),
        index=k.index)


def sample(k: pd.DataFrame, seed: int = 0, strata: dict[str, int] | None = None, total: int | None = None) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    pop = k[k.populasi_garis.fillna(False)].assign(lapis=lambda d: stratum(d))
    picks, order = [], {}
    for name, n in (strata or STRATA).items():
        # Round-robin over writing styles, so a style short of claims hands its share to the others.
        pool = pop[pop.lapis == name].sample(frac=1, random_state=int(rng.integers(1 << 31)))
        order[name] = list(pool.assign(r=pool.groupby("gaya_tulis").cumcount()).sort_values("r", kind="mergesort").index)
        picks += order[name][:n]
    if total is not None and len(picks) < total:
        # N_LLM may not shrink: a short stratum's shortfall is filled from the honest stratum, in the same style order (rule set before the key opens).
        picks += [s for s in order["jujur"] if s not in set(picks)][:total - len(picks)]
    return pop.loc[picks]


def llm_digest() -> str:
    tags = httpx.get(f"{B.OLLAMA}/api/tags", timeout=10).raise_for_status().json()["models"]
    return next(m["digest"] for m in tags if m["name"] == B.MODEL)


def llm_key(text: str, digest: str) -> str:
    # A stored reading is reused only for the same model build, prompt, schema, options, and record text.
    return hashlib.sha256(json.dumps([digest, B.PROMPT, B.SCHEMA, B.OPTIONS, text], ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def prompt_key() -> str:
    return hashlib.sha256(json.dumps([LLM_DIGEST, B.PROMPT, B.SCHEMA, B.OPTIONS], ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def stored_readings() -> dict[str, dict]:
    path, proof = DEV_OUT / "bacaan_llm.jsonl", DEV_OUT / "verifikasi_bacaan_tersimpan.json"
    if not path.exists() or path.resolve() == READINGS.resolve() or not proof.exists():
        return {}
    # Reuse needs proof that this model build and prompt reproduce the stored readings exactly (a fresh re-read of a DEV sample).
    if json.loads(proof.read_text()).get("kunci_prompt") != prompt_key():
        return {}
    rows = [json.loads(line) for line in path.open()]
    docs = pd.read_parquet(DEV / "dasar" / "rme_documents.parquet")
    texts = {sep: B.assemble(d).text for sep, d in docs[docs.nomor_sep.isin([r["nomor_sep"] for r in rows])].groupby("nomor_sep")}
    return {llm_key(texts[r["nomor_sep"]], LLM_DIGEST): r for r in rows}


def parallel_slots() -> int:
    workers = int(os.environ.get("TAPAL_LLM_PARALEL", "1"))
    if workers > 1:
        # Requests sharing the GPU can outlast the app's 120-second limit; the batch run waits longer instead of failing a reading.
        B.TIMEOUT = httpx.Timeout(600.0, connect=5.0)
    return workers


def run(limit: int | None = None) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if (digest := llm_digest()) != LLM_DIGEST:
        raise SystemExit(f"versi LLM {digest[:12]} bukan versi beku {LLM_DIGEST[:12]}")
    w = load_world(WORLD, with_key=True, key=KEY)
    c, k = w["claims"].set_index("nomor_sep"), w["key_claims"].set_index("nomor_sep")
    docs = pd.read_parquet(WORLD / "rme_documents.parquet")
    chosen = sample(k) if is_dev() else sample(k, strata=STRATA_300, total=sum(STRATA_300.values()))
    done = {json.loads(line)["nomor_sep"] for line in READINGS.open()} if READINGS.exists() else set()
    todo = [s for s in chosen.index if s not in done][:limit]
    by_sep = dict(tuple(docs[docs.nomor_sep.isin(todo)].groupby("nomor_sep")))
    reuse = stored_readings()
    hits = {s: reuse.get(llm_key(B.assemble(by_sep[s]).text, LLM_DIGEST)) for s in todo}
    print(f"sampel {len(chosen)}, sudah {len(done)}, dikerjakan sekarang {len(todo)}, dipakai ulang {sum(v is not None for v in hits.values())}",
          flush=True)

    def one(sep: str) -> str:
        if hits[sep] is not None:
            return json.dumps(hits[sep], ensure_ascii=False, default=str) + "\n"
        row, key = c.loc[sep], chosen.loc[sep]
        r = B.read_claim(by_sep[sep], set(split_codes(row.procedure)), float(row.ventilator_hour))
        truth_hours = (key.rme_selesai - key.rme_mulai).total_seconds() / 3600 if key.rme_ventilasi else 0.0
        return json.dumps({"nomor_sep": sep, "lapis": key.lapis, "gaya": key.gaya_tulis, "modus": key.modus, "tingkat": key.tingkat,
                           "rme_versi": key.rme_versi, "ventilasi_benar": bool(key.ventilasi), "rme_ventilasi": bool(key.rme_ventilasi),
                           "rme_jam": truth_hours, "klaim_jam": float(row.ventilator_hour), "kode": sorted(split_codes(row.procedure)),
                           **asdict(r)}, ensure_ascii=False, default=str) + "\n"

    with READINGS.open("a") as out, ThreadPoolExecutor(parallel_slots()) as pool:
        # Each finished reading is written at once, so a stopped run resumes from the readings already on disk.
        for i, line in enumerate(pool.map(one, todo), 1):
            out.write(line)
            out.flush()
            print(f"{i}/{len(todo)} {json.loads(line)['nomor_sep']}", flush=True)
    retries = DEV_OUT / "bacaan_llm_ulang.jsonl"
    if is_dev() and reuse and retries.exists() and not (OUT / retries.name).exists():
        # DEV readings predate the inline retry; their stored retries travel with them so the layered report sees the same inputs.
        (OUT / retries.name).write_text(retries.read_text())


def parallel_check(n: int = 20) -> dict:
    # The first n stored sequential DEV readings, read again with the current parallel setting; verdicts must not change.
    rows = [json.loads(line) for line in (DEV_OUT / "bacaan_llm.jsonl").open()][:n]
    docs = pd.read_parquet(DEV / "dasar" / "rme_documents.parquet")
    records = {s: B.assemble(d) for s, d in docs[docs.nomor_sep.isin([r["nomor_sep"] for r in rows])].groupby("nomor_sep")}
    workers = parallel_slots()
    start = time.time()
    with ThreadPoolExecutor(workers) as pool:
        calls = list(pool.map(lambda r: B.call_ollama(records[r["nomor_sep"]].text), rows))
    seconds = time.time() - start

    def verdict(reading: dict, r: dict) -> tuple:
        rd = RmeReading.model_validate(reading)
        check = B.check_reading(rd, records[r["nomor_sep"]])
        return B.judge(check, rd, set(r["kode"]), r["klaim_jam"])[0], rd.ventilasi_invasif, check.hours

    pairs = [(call.reading.model_dump(), r["reading"], r) for call, r in zip(calls, rows) if call.reading is not None and r["reading"] is not None]
    report = {"permintaan_paralel": workers, "rme": len(rows), "detik_per_rme": round(seconds / len(rows), 1),
              "detik_per_rme_berurutan_tersimpan": round(float(np.median([r["total_ms"] for r in rows])) / 1000, 1),
              "bacaan_sah": len(pairs), "bacaan_identik": sum(a == b for a, b, _ in pairs),
              "putusan_sama": sum(verdict(a, r) == verdict(b, r) for a, b, r in pairs),
              "beda": [r["nomor_sep"] for a, b, r in pairs if verdict(a, r) != verdict(b, r)]}
    report["kunci_prompt"] = prompt_key()
    (OUT / f"uji_paralel_{workers}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    if report["bacaan_identik"] == report["bacaan_sah"] == report["rme"]:
        (DEV_OUT / "verifikasi_bacaan_tersimpan.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    return report


def truth(k: pd.DataFrame) -> pd.DataFrame:
    rme_hours = ((k.rme_selesai - k.rme_mulai) / pd.Timedelta(hours=1)).where(k.rme_ventilasi, 0.0)
    return pd.DataFrame({"lapis": stratum(k), "ventilasi_benar": k.ventilasi.astype(bool), "rme_ventilasi": k.rme_ventilasi.astype(bool),
                         "rme_jam": rme_hours, "jam_benar": k.jam_ventilasi_benar.fillna(0.0).astype(float),
                         "dimanipulasi": k.modus.isin(["fiktif", "diperpanjang"])}, index=k.index)


def _held_group(held) -> str:
    held = list(held) if held is not None else []
    if not held or "bacaan" in held:
        return "gagal_membaca:bacaan"
    for layer, group in (("asal_usul", "asal_usul_meragukan"), ("jejak_waktu", "asal_usul_meragukan"), ("fisiologi", "asal_usul_meragukan"),
                         ("asersi", "gagal_membaca")):
        if layer in held:
            return f"{group}:{layer}"
    return "gagal_membaca:bacaan"


def score(r: pd.DataFrame, key: pd.DataFrame) -> dict:
    # T7 judges the reading against the record text; T8 follows TARGETS: a wrong status, or hours off by more than 2 against the key.
    x = r.join(key, how="inner")
    acc = x[x.verdict != "tidak_dapat_disimpulkan"]
    yes = acc.invasif == "ya"
    both = yes & acc.ventilasi_benar & acc.jam.notna()
    wrong = (yes != acc.ventilasi_benar) | (both & ((acc.jam - acc.jam_benar).abs() > 2))
    flagged = x.verdict == "tidak_mendukung"
    held = x[x.verdict == "tidak_dapat_disimpulkan"]
    groups = (held.held if "held" in held else pd.Series(["bacaan"] * len(held), index=held.index)).map(_held_group)
    return {
        "n": len(x), "diterima": len(acc),
        "t7_akurasi_status_vs_teks": round(float((yes == acc.rme_ventilasi).mean()), 4),
        "t8_diterima_salah": round(float(wrong.mean()), 4), "t8_diterima_salah_n": int(wrong.sum()),
        "t8_salah_per_lapis": acc[wrong].lapis.value_counts().to_dict(),
        "t9_tidak_dapat_disimpulkan": round(float((x.verdict == "tidak_dapat_disimpulkan").mean()), 4),
        "t9_rincian": {g: round(n / len(x), 4) for g, n in groups.value_counts().items()},
        "t10_galat_jam_median_vs_kunci": round(float((acc.jam[both] - acc.jam_benar[both]).abs().median()), 2) if both.any() else None,
        "t10_galat_jam_median_vs_teks": round(float((acc.jam[both] - acc.rme_jam[both]).abs().median()), 2) if both.any() else None,
        "tidak_mendukung_presisi": round(float(x.dimanipulasi[flagged].mean()), 4) if flagged.any() else None,
        "tidak_mendukung_recall": round(float(flagged[x.dimanipulasi].mean()), 4) if x.dimanipulasi.any() else None,
        "putusan_per_lapis": pd.crosstab(x.lapis, x.verdict).to_dict(orient="index"),
    }


def keyword_rows(c: pd.DataFrame, docs: pd.DataFrame, pop: pd.Index) -> pd.DataFrame:
    rows = []
    for sep, d in docs[docs.nomor_sep.isin(pop)].groupby("nomor_sep"):
        r = B.read_claim(d, set(split_codes(c.at[sep, "procedure"])), float(c.at[sep, "ventilator_hour"]), use_llm=False)
        reading = r.reading or {"ventilasi_invasif": "tidak_jelas", "alat_napas_tertinggi": "tidak_jelas"}
        rows.append((sep, r.verdict, reading["ventilasi_invasif"], reading["alat_napas_tertinggi"], r.hours, r.quotes_verified))
    return pd.DataFrame(rows, columns=["nomor_sep", "verdict", "invasif", "alat", "jam", "kutipan_cocok"]).set_index("nomor_sep")


def keyword_layer() -> dict:
    w = load_world(WORLD, with_key=True, key=KEY)
    c, k = w["claims"].set_index("nomor_sep"), w["key_claims"].set_index("nomor_sep")
    pop = k.index[k.populasi_garis.fillna(False)]
    out = keyword_rows(c, pd.read_parquet(WORLD / "rme_documents.parquet"), pop)
    out.to_parquet(OUT / "kata_kunci_per_klaim.parquet")
    report = score(out, truth(k.loc[pop]))
    (OUT / "kata_kunci_laporan.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str))
    return report


def physiology_report() -> dict:
    icu = Path(__file__).resolve().parents[1] / "data" / "icu_open"
    model, report = P.train(pd.read_parquet(icu / "eicu_hourly.parquet"), pd.read_parquet(icu / "mimic_hourly.parquet"))
    w = load_world(WORLD, with_key=True, key=KEY)
    c, k = w["claims"].set_index("nomor_sep"), w["key_claims"].set_index("nomor_sep")
    pop = k.index[k.populasi_garis.fillna(False)]
    vitals = pd.read_parquet(WORLD / "rme_vitals.parquet")
    hourly = P.hourly_ventilation(model, vitals[vitals.nomor_sep.isin(pop)])
    hourly.to_parquet(OUT / "fisiologi_per_jam_dev.parquet")
    x = truth(k.loc[pop]).assign(lembar=P.ventilated_hours(hourly), klaim=c.loc[pop].ventilator_hour.astype(float),
                                 rme_versi=k.loc[pop].rme_versi, kode_rs=c.loc[pop].kode_rs)
    x = x[x.lembar.notna()]
    honest = x[(x.lapis == "jujur") & x.rme_ventilasi]
    x["teks_vs_lembar"] = (x.rme_jam >= B.SHEET_MIN_HOURS) & (x.lembar < B.SHEET_SHARE * x.rme_jam)
    x["klaim_vs_lembar"] = (x.klaim >= B.SHEET_MIN_HOURS) & (x.lembar < B.SHEET_SHARE * x.klaim)
    report["dev"] = {
        "klaim_berlembar": len(x), "klaim_tanpa_lembar": int(len(pop) - len(x)),
        "jujur_galat_jam_median": round(float((honest.lembar - honest.rme_jam).abs().median()), 1),
        "jujur_rasio_jam_median": round(float((honest.lembar / honest.rme_jam).median()), 3),
        "porsi_tertandai_per_lapis": x.groupby("lapis")[["teks_vs_lembar", "klaim_vs_lembar"]].mean().round(4).to_dict(orient="index"),
        "n_per_lapis": x.lapis.value_counts().to_dict(),
    }
    (OUT / "fisiologi_laporan.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str))
    x.to_parquet(OUT / "fisiologi_per_klaim.parquet")
    return report


def use_embedding_cache(heads) -> None:
    if "embedding" in set(heads.values() if isinstance(heads, dict) else heads):
        for vectors, texts in EMBEDDINGS:
            A.load_embeddings(DEV_OUT / vectors, DEV_OUT / texts)
        if (OUT / WORLD_EMBEDDINGS[0]).exists() and OUT.resolve() != DEV_OUT.resolve():
            A.load_embeddings(OUT / WORLD_EMBEDDINGS[0], OUT / WORLD_EMBEDDINGS[1])


def world_sentences() -> set[str]:
    k = load_world(WORLD, with_key=True, key=KEY)["key_claims"]
    pop = set(k.nomor_sep[k.populasi_garis.fillna(False)])
    texts = set()
    for path in (WORLD / "rme_documents.parquet", KEY / "key_placebo_rme_documents.parquet"):
        if path.exists():
            docs = pd.read_parquet(path)
            texts |= {s for _, d in docs[docs.nomor_sep.isin(pop)].groupby("nomor_sep") for s in B.sentences(B.assemble(d))}
    if (KEY / "key_sentences.parquet").exists():
        lab = pd.read_parquet(KEY / "key_sentences.parquet")
        style = pd.read_parquet(KEY / "key_claims.parquet", columns=["nomor_sep", "gaya_tulis"]).set_index("nomor_sep").gaya_tulis
        texts |= set(A.training_sentences(pd.read_parquet(WORLD / "rme_documents.parquet"), lab, style).teks)
    return texts


def embed_world() -> dict:
    # The evaluated world's sentences are embedded once, before the LLM starts, so the two never share the GPU (user rule 1 Nov 2026).
    OUT.mkdir(parents=True, exist_ok=True)
    use_embedding_cache(["embedding"])
    cache = A._CACHE.setdefault(A.EMBED_MODEL, {})
    todo = sorted(world_sentences() - set(cache))
    A.OllamaEmbedding().transform(todo)
    np.save(OUT / WORLD_EMBEDDINGS[0], np.vstack([cache[t] for t in todo]) if todo else np.empty((0, 1024), np.float32))
    pd.DataFrame({"teks": todo}).to_parquet(OUT / WORLD_EMBEDDINGS[1])
    return {"kalimat_baru": len(todo)}


def assertion_world(heads: dict[str, str]) -> dict:
    # T14 on the evaluated world's labelled sentences, read by the frozen reader trained on all DEV sentences, as for D1-D11.
    use_embedding_cache(heads)
    reader = A.AssertionReader.fit(assertion_data(), heads)
    lab = pd.read_parquet(KEY / "key_sentences.parquet")
    style = pd.read_parquet(KEY / "key_claims.parquet", columns=["nomor_sep", "gaya_tulis"]).set_index("nomor_sep").gaya_tulis
    data = A.training_sentences(pd.read_parquet(WORLD / "rme_documents.parquet"), lab, style)
    models = {"sebutan": reader.mention, "alat": reader.device, "asersi": reader.assertion}
    out = {}
    for head, model in models.items():
        rows = data if head == "sebutan" else data[data.sebutan]
        right = model.predict(rows.teks) == rows[head].to_numpy()
        out[head] = {g: _per_class(rows[head][rows.gaya == g], right[(rows.gaya == g).to_numpy()]) for g in sorted(rows.gaya.dropna().unique())}
    report = {"pembaca": heads, "kalimat": len(data), "per_gaya": out}
    (OUT / "asersi_dunia_laporan.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    return report


def assertion_data() -> pd.DataFrame:
    labelled = pd.read_parquet(DEV / "dasar" / "key" / "key_sentences.parquet")
    style = pd.read_parquet(DEV / "dasar" / "key" / "key_claims.parquet", columns=["nomor_sep", "gaya_tulis"]).set_index("nomor_sep").gaya_tulis
    return A.training_sentences(pd.read_parquet(DEV / "dasar" / "rme_documents.parquet"), labelled, style)


def _per_class(truth, correct) -> dict:
    per = pd.Series(np.asarray(correct, float)).groupby(np.asarray(truth)).mean()
    return {"rata_per_kelas": round(float(per.mean()), 3), "per_kelas": {str(k): round(float(v), 3) for k, v in per.items()}}


def leave_one_style(data: pd.DataFrame, backend: str) -> dict:
    out = {}
    for head in A.HEADS:
        rows, out[head] = (data if head == "sebutan" else data[data.sebutan]), {}
        for held in sorted(rows.gaya.unique()):
            train, test = rows[rows.gaya != held], rows[rows.gaya == held]
            pred = A.classifier(backend).fit(train.teks, train[head]).predict(test.teks)
            out[head][held] = _per_class(test[head], pred == test[head].to_numpy())
    return out


def choose(scores: dict) -> dict[str, str]:
    # Criterion written in Notion task 575 before the embedding run: best worst-style score per head, n-gram on a tie under 0.005.
    worst = {b: {h: min(v["rata_per_kelas"] for v in scores[b][h].values()) for h in A.HEADS} for b in scores}
    return {h: "embedding" if worst["embedding"][h] - worst["ngram"][h] >= 0.005 else "ngram" for h in A.HEADS}


def on_test_docs(reader: A.AssertionReader, note_text_only: bool = True) -> dict:
    rows = pd.DataFrame(json.loads((TEST_DOCS / "label_kalimat.json").read_text())["kalimat"])
    if note_text_only:
        # The record handed to AI 2 carries note headers and the patient banner as fields, never as note text.
        rows = rows[~(rows.teks.str.startswith("[") | (rows.i <= 2))].reset_index(drop=True)
    read = reader.read(rows.teks.tolist())
    known = rows.sebutan.notna()
    out = {"sebutan": _per_class(rows.sebutan[known].astype(bool), (read.sebutan == rows.sebutan)[known])}
    gold = rows[rows.sebutan.eq(True) & rows.boleh.notna()]
    device, assertion = reader.device.predict(gold.teks), reader.assertion.predict(gold.teks)
    out["alat"] = _per_class([b[0][0] for b in gold.boleh], [d in {x[0] for x in b} for d, b in zip(device, gold.boleh)])
    out["asersi"] = _per_class([b[0][1] for b in gold.boleh], [a in {x[1] for x in b} for a, b in zip(assertion, gold.boleh)])
    out["pasangan_benar"] = round(float(np.mean([[d, a] in b for d, a, b in zip(device, assertion, gold.boleh)])), 3)
    vent = read.sebutan & (read.alat == "ventilator_invasif") & (read.asersi == "terpasang")
    allowed = rows.boleh.map(lambda b: b is not None and ["ventilator_invasif", "terpasang"] in b)
    out["ventilator_terpasang_palsu"] = rows.teks[vent & ~allowed].tolist()
    key = json.loads((TEST_DOCS / "kunci_jawaban.json").read_text())
    calls = {d: A.ventilation(read[rows.dokumen == d]) for d in rows.dokumen.unique()}
    out["dokumen_benar"] = sum(c == key[d]["invasif"] for d, c in calls.items())
    out["dokumen"] = {d: {"bacaan": c, "kunci": key[d]["invasif"]} for d, c in calls.items()}
    return out


def assertion_report(backends: tuple[str, ...] = ("ngram", "embedding")) -> dict:
    use_embedding_cache(backends)
    data = assertion_data()
    scores = {b: leave_one_style(data, b) for b in backends}
    pick = choose(scores) if len(backends) > 1 else dict.fromkeys(A.HEADS, backends[0])
    readers = {b: dict.fromkeys(A.HEADS, b) for b in backends} | {"terpilih": pick}
    tests = {}
    for name, heads in readers.items():
        if name != "terpilih" or len(set(pick.values())) > 1:
            reader = A.AssertionReader.fit(data, heads)
            tests[name] = {"teks_catatan": on_test_docs(reader), "semua_baris": on_test_docs(reader, note_text_only=False)}
    report = {"kalimat": {"total": len(data), "sebutan": int(data.sebutan.sum())}, "tinggalkan_satu_gaya": scores, "pilihan": pick,
              "dokumen_uji_d1_d11": tests}
    (OUT / "asersi_laporan.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    return report


def fast_layers() -> dict:
    w = load_world(WORLD, with_key=True, key=KEY)
    c, k, h = w["claims"].set_index("nomor_sep"), w["key_claims"].set_index("nomor_sep"), w["key_hospitals"].set_index("kode_rs")
    docs = pd.read_parquet(WORLD / "rme_documents.parquet")
    clones, trail = F.clone_scores(docs, c.kode_rs), F.write_trail(docs, c.tgl_pulang)
    origin = F.provenance(clones, trail, pd.read_parquet(WORLD / "rme_vitals.parquet"))
    per = clones.join(trail).join(origin.add_suffix("_asal_usul").rename(columns={"kloning_kuat_asal_usul": "kloning_kuat",
                                                                                 "tulis_serentak_asal_usul": "tulis_serentak"}))
    per = per.join(k[["rme_versi", "jebakan"]]).assign(rs=c.kode_rs)
    per["meragukan"] = per.kloning | per.tulis_massal
    flags = F.rs_flags(per.meragukan, per.rs).join(h[["kelas_rs", "modus", "tingkat", "intensitas_terwujud", "jebakan", "modus_tersembunyi"]])
    perp = flags[(flags.modus == "rme_meragukan") & (flags.intensitas_terwujud > 0)]
    honest = flags[flags.index.isin(h.index[honest_hospitals(h)])]
    layers = {}
    for layer in ("kloning", "tulis_massal"):
        f = F.rs_flags(per[layer], per.rs).join(h[["modus", "tingkat", "modus_tersembunyi", "jebakan"]])
        mine = (f.modus == "rme_meragukan") & (f.tingkat == ("kloning" if layer == "kloning" else "massal"))
        layers[layer] = {"rs_pelaku_lapis_ini_ditandai": f"{int(f.ditandai[mine].sum())}/{int(mine.sum())}",
                         "rs_lain_ditandai": f[f.ditandai & ~mine].reset_index()[["index", "modus", "tingkat", "jebakan"]].to_dict(orient="records")}
    report = {
        "per_lapis_rs": layers,
        "per_klaim": per.groupby("rme_versi")[["kloning", "tulis_massal", "meragukan"]].mean().round(4).to_dict(orient="index"),
        "per_klaim_jebakan_jujur": per[per.rme_versi == "jujur"].groupby("jebakan")[["kloning", "tulis_massal"]].mean().round(4)
                                   .to_dict(orient="index"),
        "t13_rs_pelaku_ditandai": f"{int(perp.ditandai.sum())}/{len(perp)}",
        "rs_pelaku": perp[["tingkat", "kelas_rs", "n_layak", "O", "E", "z_robust", "p_bh", "ditandai"]].round(4).reset_index()
                     .to_dict(orient="records"),
        "rs_jujur_ditandai": honest[honest.ditandai].reset_index()[["index", "jebakan", "n_layak", "O", "E"]].to_dict(orient="records"),
        "rs_jujur_diuji": int((honest.n_layak >= 30).sum()),
        "rs_modus_lain_ditandai": flags[flags.ditandai & ~flags.index.isin(perp.index) & ~flags.index.isin(honest.index)]
                                  .reset_index()[["index", "modus", "tingkat"]].to_dict(orient="records"),
        "ditulis_sesudah_pulang_median": per.groupby("rme_versi").porsi_ditulis_sesudah_pulang.median().round(3).to_dict(),
        "penahanan_asal_usul_per_versi": {v: {"n": len(g), "kloning_kuat": int(g.kloning_kuat.sum()), "tulis_serentak": int(g.tulis_serentak.sum()),
                                              "porsi_tertahan": round(float((g.kloning_kuat | g.tulis_serentak).mean()), 4)}
                                          for v, g in per.groupby("rme_versi")},
        "penahanan_asal_usul_klaim_jujur_per_jebakan": per[per.rme_versi == "jujur"].assign(tahan=lambda d: d.kloning_kuat | d.tulis_serentak)
                                                        .groupby("jebakan").tahan.agg(["mean", "sum", "size"]).round(4).to_dict(orient="index"),
    }
    per.to_parquet(OUT / "lapis_cepat_per_klaim.parquet")
    (OUT / "lapis_cepat_laporan.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str))
    return report


def sample_doc_notes(name: str) -> pd.DataFrame:
    # The hand-written documents carry a three-line patient banner, then notes headed "[jenis] tanggal jam · unit · penulis".
    rows, ref = [], datetime(2026, 1, 1)
    for line in (TEST_DOCS / "dokumen_rme" / f"{name}.txt").read_text().splitlines()[2:]:
        if m := re.match(r"\[(.+?)\]\s*(.*)", line):
            when = B.parse_time(m.group(2), ref)
            rows.append({"jenis": m.group(1), "waktu_layanan": pd.Timestamp(when), "teks": "",
                         "penulis_peran": "perawat" if "perawat" in line.lower() or "Catatan" in m.group(1) else "dokter"})
        elif rows and line.strip():
            rows[-1]["teks"] = (rows[-1]["teks"] + " " + line.strip()).strip()
    return pd.DataFrame(rows)


def llm_on_sample_docs(heads: dict[str, str] | None = None) -> dict:
    key = json.loads((TEST_DOCS / "kunci_jawaban.json").read_text())
    path = OUT / "bacaan_d1_d11.jsonl"
    done = {json.loads(line)["dokumen"]: json.loads(line) for line in path.open()} if path.exists() else {}
    with path.open("a") as f:
        for name in (n for n in key if not n.startswith("_") and n not in done):
            r = B.read_claim(sample_doc_notes(name), {"96.71"}, 0.0, use_llm=True)
            done[name] = {"dokumen": name, **asdict(r)}
            f.write(json.dumps(done[name], ensure_ascii=False, default=str) + "\n")
            f.flush()
    heads = heads or dict.fromkeys(A.HEADS, "ngram")
    use_embedding_cache(heads)
    reader = A.AssertionReader.fit(assertion_data(), heads)
    out = {}
    for name, r in done.items():
        truth_, reading = key[name], r["reading"] or {}
        status, hours = reading.get("ventilasi_invasif", "tidak_jelas"), r["hours"]
        second = A.ventilation(reader.read(B.sentences(B.assemble(sample_doc_notes(name)))))
        right = status == truth_["invasif"] and (truth_["jam"] is None or (hours is not None and abs(hours - truth_["jam"]) <= truth_.get("toleransi", 1.0)))
        out[name] = {"bacaan": status, "kunci": truth_["invasif"], "jam": hours, "jam_kunci": truth_["jam"], "putusan_llm": r["verdict"],
                     "benar": right, "asersi": second, "putusan_berlapis": B.cross_check(r["verdict"], [], status, hours, second, None)[0]}
    count = lambda col: {"diterima_benar": sum(v[col] != "tidak_dapat_disimpulkan" and v["benar"] for v in out.values()),
                         "diterima_salah": sum(v[col] != "tidak_dapat_disimpulkan" and not v["benar"] for v in out.values()),
                         "tidak_dapat_disimpulkan": sum(v[col] == "tidak_dapat_disimpulkan" for v in out.values())}
    report = {"llm": count("putusan_llm"), "llm_asersi": count("putusan_berlapis"), "per_dokumen": out}
    (OUT / "d1_d11_berlapis.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str))
    return report


VERDICT_TEXT = {"mendukung": "mendukung", "tidak_mendukung": "tidak mendukung", "tidak_dapat_disimpulkan": "tidak dapat disimpulkan"}
STORY = ["Klaim mencatat kode {kode} dengan {jam_klaim} ventilasi.",
         "RME mencatat alat napas tertinggi {alat} dan ventilasi invasif {jam_rme} ({banding_jam}), dengan {kutipan} terverifikasi.",
         "Putusan AI 2: {putusan}."]


def compare_hours(rme: float | None, claim: float) -> str:
    if rme is None:
        return "jam RME tidak dapat dibandingkan"
    gap = rme - claim
    return "sesuai dengan jam klaim" if abs(gap) <= B.HOUR_SLACK else f"{B._hours(abs(gap))} jam {'lebih pendek' if gap < 0 else 'lebih panjang'} dari klaim"


def claim_facts(r: dict) -> dict[str, N.Fact]:
    reading = r["reading"] or {}
    hours = f"{B._hours(r['hours'])} jam" if r["hours"] is not None else "tidak tercatat"
    return {"kode": N.Fact(", ".join(c for c in r["kode"] if c in B.VENT_CODES | {"96.04"}) or "tanpa kode ventilasi", "kolom procedure E-Klaim",
                           "kode intubasi/ventilasi yang ditagih"),
            "jam_klaim": N.Fact(f"{r['klaim_jam']:.0f} jam", "kolom ventilator_hour E-Klaim", "jam ventilasi yang diklaim"),
            "jam_rme": N.Fact(hours, "dihitung kode dari waktu yang dikutip persis dari RME", "jam ventilasi invasif menurut RME"),
            "kutipan": N.Fact(f"{r['quotes_verified']} kutipan", "dicocokkan kode kata per kata dengan RME", "jumlah kutipan yang cocok"),
            "alat": N.Fact(reading.get("alat_napas_tertinggi", "tidak_jelas").replace("_", " "), "dibaca LLM lokal, kutipannya dicek kode",
                           "alat napas tertinggi menurut RME"),
            "banding_jam": N.Fact(compare_hours(r["hours"], r["klaim_jam"]), "dibandingkan kode dengan selisih toleransi 1 jam",
                                  "perbandingan jam RME dengan jam klaim"),
            "putusan": N.Fact(VERDICT_TEXT[r["verdict"]], "aturan putusan AI 2", "putusan AI 2 atas klaim")}


def narratives(n: int = 12, path: Path = READINGS) -> dict:
    rows = [json.loads(line) for line in path.open()]
    picked = [rows[i] for i in np.linspace(0, len(rows) - 1, n).astype(int)]
    stories = [N.narrate(claim_facts(r), STORY, use_llm=True) for r in picked]
    report = {"n": n, "lolos_llm": sum(s.source == "llm_lokal" for s in stories),
              "alasan_ditolak": [s.reasons for s in stories if s.source != "llm_lokal"],
              "contoh": ["".join(x["teks"] for x in s.segments) for s in stories]}
    (OUT / "narasi_laporan.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    return report


def second_opinions(seps: list[str], records: dict, group: pd.Series, heads: dict[str, str]) -> dict[str, str]:
    # Cross-fitted: the reader never trains on sentences of the claims it judges, nor on their hospital or style group.
    docs = pd.read_parquet(DEV / "dasar" / "rme_documents.parquet")
    labelled = pd.read_parquet(DEV / "dasar" / "key" / "key_sentences.parquet")
    style = pd.read_parquet(DEV / "dasar" / "key" / "key_claims.parquet", columns=["nomor_sep", "gaya_tulis"]).set_index("nomor_sep").gaya_tulis
    out = {}
    for g in pd.unique(group.loc[seps]):
        held = group.index[group == g]
        data = A.training_sentences(docs[~docs.nomor_sep.isin(held)], labelled[~labelled.nomor_sep.isin(held)], style)
        reader = A.AssertionReader.fit(data, heads)
        for sep in [s for s in seps if group.get(s) == g]:
            out[sep] = A.ventilation(reader.read(B.sentences(records[sep])))
    return out


def late_population(c: pd.DataFrame, k: pd.DataFrame, docs: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    # Every line-population claim feeds its hospital's baseline, unlabelled, as the app does with a hospital's stored records.
    pop = k.index[k.populasi_garis.fillna(False)]
    delays = F.key_document_delay(docs[docs.nomor_sep.isin(pop)], F.ventilation_windows(c.loc[pop]))
    return delays, F.delay_scores(delays, c.kode_rs, F.delay_baseline(delays, c.kode_rs))


def late_thresholds() -> dict:
    # Honest records only set the limit (no manipulation, honest RME version), so it says how far an honest note strays from its own hospital.
    w = load_world(DEV / "dasar", with_key=True)
    c, k = w["claims"].set_index("nomor_sep"), w["key_claims"].set_index("nomor_sep")
    delays, z = late_population(c, k, pd.read_parquet(DEV / "dasar" / "rme_documents.parquet"))
    honest = z.index[(k.rme_versi.reindex(z.index) == "jujur") & ~k.dimanipulasi.reindex(z.index).fillna(False).astype(bool)]
    made_up = z.index[k.rme_versi.reindex(z.index) == "karangan"]
    base = F.delay_baseline(delays, c.kode_rs)
    out = {"dibuat": pd.Timestamp.now(tz="Asia/Jakarta").isoformat(timespec="seconds"), "persentil": 99, "dasar": "kebiasaan tulis masing-masing RS", "jenis": {}}
    for kind in F.KEY_DOCUMENTS:
        h, m = z.loc[honest, kind].dropna(), z.loc[made_up, kind].dropna()
        limit = float(np.quantile(h, 0.99))
        out["jenis"][kind] = {"klaim_jujur": int(len(h)), "p99_jujur_skor": round(limit, 2), "rs_dasar_sendiri": int((base[kind].n >= S.MIN_KLAIM).sum()),
                              "rs_dasar_gabungan": int((base[kind].n < S.MIN_KLAIM).sum()), "skala_lantai": round(float(base[kind].skala.min()), 3),
                              "klaim_karangan": int(len(m)), "karangan_di_atas_p99": round(float((m > limit).mean()), 3) if len(m) else None}
    (OUT / "jejak_waktu_rs_ambang.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    return out


def late_burden() -> dict:
    # The RS-level route is measured only to be reported; T12 does not use it (user decision 1 Nov 2026).
    w = load_world(WORLD, with_key=True, key=KEY)
    c, k, h = w["claims"].set_index("nomor_sep"), w["key_claims"].set_index("nomor_sep"), w["key_hospitals"].set_index("kode_rs")
    delays, z = late_population(c, k, pd.read_parquet(WORLD / "rme_documents.parquet"))
    pop = k.index[k.populasi_garis.fillna(False)]
    held = F.late_key_documents(delays, z).ne("").reindex(pop, fill_value=False)
    x = pd.DataFrame({"ditahan": held, "lapis": truth(k.loc[pop]).lapis, "jebakan": h.jebakan.reindex(c.kode_rs.loc[pop]).to_numpy()})
    honest = x[x.lapis == "jujur"]
    flags = F.rs_flags(held, c.kode_rs).join(h[["modus", "tingkat"]])
    honest_rs = h.index[honest_hospitals(h.reset_index()).to_numpy()]
    cerdik = flags[(flags.modus.isin(["fiktif", "diperpanjang"])) & (flags.tingkat == "cerdik_2") & (flags.n_layak >= S.MIN_KLAIM)]
    report = {"batas_skor": F.LATE_Z_LIMIT, "jujur_ditahan": f"{int(honest.ditahan.sum())}/{len(honest)}",
              "jujur_ditahan_per_jebakan": {t or "tanpa_jebakan": f"{int(g.ditahan.sum())}/{len(g)}" for t, g in honest.groupby("jebakan")},
              "ditahan_per_lapis": {l: f"{int(g.ditahan.sum())}/{len(g)}" for l, g in x.groupby("lapis")},
              "jalur_rs_info_saja": {"cerdik_2_ditandai": {m: f"{int(g.ditandai.sum())}/{len(g)}" for m, g in cerdik.groupby("modus")},
                                     "rs_jujur_ditandai": f"{int(flags.loc[flags.index.isin(honest_rs)].ditandai.sum())}/{int((flags.loc[flags.index.isin(honest_rs)].n_layak >= S.MIN_KLAIM).sum())}",
                                     "rs_jujur_ditandai_kode": flags.index[flags.ditandai & flags.index.isin(honest_rs)].tolist()}}
    (OUT / "jejak_waktu_beban.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    return report


RETRIES = OUT / "bacaan_llm_ulang.jsonl"


def retry_readings(path: Path = READINGS) -> dict:
    # The same one retry read_claim makes, run only for stored readings whose quotes were not found verbatim.
    rows = [json.loads(line) for line in path.open()]
    docs = pd.read_parquet(WORLD / "rme_documents.parquet")
    seps = [r["nomor_sep"] for r in rows if r["reading"] is not None]
    records = {s: B.assemble(d) for s, d in docs[docs.nomor_sep.isin(seps)].groupby("nomor_sep")}
    done = {json.loads(line)["nomor_sep"] for line in RETRIES.open()} if RETRIES.exists() else set()
    todo = [(r, missing) for r in rows if r["reading"] is not None and r["nomor_sep"] not in done
            and (missing := B._unmatched(RmeReading.model_validate(r["reading"]), records[r["nomor_sep"]]))]
    with RETRIES.open("a") as f:
        for i, (r, missing) in enumerate(todo, 1):
            call = B.call_ollama(records[r["nomor_sep"]].text + B.RETRY_NOTE.format(quotes="; ".join(f'"{q}"' for q in missing)))
            f.write(json.dumps({"nomor_sep": r["nomor_sep"], "reading": call.reading.model_dump() if call.reading else None, "error": call.error,
                                "total_ms": call.total_ms, "prompt_tokens": call.prompt_tokens}, ensure_ascii=False) + "\n")
            f.flush()
            print(f"{i}/{len(todo)} {r['nomor_sep']} {len(missing)} kutipan diulang {call.total_ms} ms", flush=True)
    return {"diulang": len(todo) + len(done)}


def layered(heads: dict[str, str] | None = None, path: Path = READINGS) -> dict:
    heads = heads or dict.fromkeys(A.HEADS, "ngram")
    use_embedding_cache(heads)
    w = load_world(WORLD, with_key=True, key=KEY)
    c, k = w["claims"].set_index("nomor_sep"), w["key_claims"].set_index("nomor_sep")
    rows = {r["nomor_sep"]: r for r in map(json.loads, path.open())}
    seps = list(rows)
    docs = pd.read_parquet(WORLD / "rme_documents.parquet")
    records = {s: B.assemble(d) for s, d in docs[docs.nomor_sep.isin(seps)].groupby("nomor_sep")}
    sheet = pd.read_parquet(OUT / "fisiologi_per_klaim.parquet").lembar
    # An explicit map: Series.replace("", None) pads the previous row's value into the gap instead of clearing it.
    origin = {sep: why for sep, why in pd.read_parquet(OUT / "lapis_cepat_per_klaim.parquet").alasan_asal_usul.items() if why}
    late = {sep: why for sep, why in F.late_key_documents(*late_population(c, k, docs)).items() if why and sep in rows}
    retried = {r["nomor_sep"]: r for r in map(json.loads, RETRIES.open())} if RETRIES.exists() else {}
    cache = OUT / path.name.replace("bacaan_llm", f"pembaca_kedua_{'_'.join(heads[h] for h in A.HEADS)}").replace(".jsonl", ".parquet")
    if cache.exists():
        second = pd.read_parquet(cache).to_dict()
    else:
        # The hospital-fold readers are the shared ones; a claim with no sentence reads "tidak_jelas", as ventilation() of an empty read does.
        by_rs = read_by_fold(heads, docs[docs.nomor_sep.isin(seps)], pd.Index(seps), c.kode_rs).reindex(seps).fillna("tidak_jelas")
        # Outside DEV no reader has seen these claims or their style, so the deployed hospital-fold readers serve both schemes.
        second = {"rs": by_rs.to_dict(), "gaya": second_opinions(seps, records, k.gaya_tulis, heads) if is_dev() else by_rs.to_dict()}
        pd.DataFrame(second).to_parquet(cache)
    out = []
    for sep, r in rows.items():
        if r["reading"] is None:
            out += [(sep, v, "tidak_dapat_disimpulkan", "tidak_jelas", None, ["bacaan"]) for v in VARIANTS]
            continue
        reading = RmeReading.model_validate(r["reading"])
        if B._unmatched(reading, records[sep]) and (again := retried.get(sep)) and again["reading"] is not None:
            reading = RmeReading.model_validate(again["reading"])
        check = B.check_reading(reading, records[sep])
        base = B.judge(check, reading, set(r["kode"]), r["klaim_jam"])
        for name, (scheme, physiology, provenance) in VARIANTS.items():
            v, _, held = B.cross_check(*base, reading.ventilasi_invasif, check.hours, second[scheme][sep] if scheme else None,
                                       sheet.get(sep) if physiology else None, origin.get(sep) if provenance else None,
                                       late.get(sep) if provenance else None)
            out.append((sep, name, v, reading.ventilasi_invasif, check.hours, held))
    per = pd.DataFrame(out, columns=["nomor_sep", "varian", "verdict", "invasif", "jam", "held"])
    per.assign(held=per.held.map(",".join)).to_parquet(OUT / path.name.replace("bacaan_llm", "berlapis_per_klaim").replace(".jsonl", ".parquet"))
    key = truth(k.loc[seps])
    report = {name: score(g.set_index("nomor_sep"), key) for name, g in per.groupby("varian", sort=False)}
    report["kata_kunci"] = score(pd.read_parquet(OUT / "kata_kunci_per_klaim.parquet").loc[seps], key)
    report["llm_kutipan"] = {"bacaan": len(rows), "keluaran_tidak_sah": sum(r["reading"] is None for r in rows.values()),
                             "ditolak_kutipan": sum(any("kutipan tidak cocok" in x for x in r["reasons"]) for r in rows.values()),
                             "median_detik": round(float(np.median([r["total_ms"] for r in rows.values()])) / 1000, 1),
                             "token_prompt_maks": max(r["prompt_tokens"] for r in rows.values())}
    report["jejak_waktu"] = {"klaim_ditahan_di_sampel": len(late), "per_lapis": pd.Series({s: truth(k.loc[[s]]).lapis.iat[0] for s in late}).value_counts().to_dict(),
                             "batas_skor": F.LATE_Z_LIMIT, "bacaan_diulang": len(retried),
                             "ulang_berhasil_cocok": int(sum(1 for s, a in retried.items() if a["reading"] and not B._unmatched(RmeReading.model_validate(a["reading"]), records[s])))}
    report["pembaca_kedua_beda_dari_llm"] = {g: int(sum(second[g][s] != (rows[s]["reading"] or {}).get("ventilasi_invasif") for s in seps))
                                            for g in second}
    (OUT / path.name.replace("bacaan_llm", "berlapis_laporan").replace(".jsonl", ".json")).write_text(
        json.dumps(report, ensure_ascii=False, indent=1, default=str))
    return report


def fold_readers(heads: dict[str, str]) -> tuple[dict[int, A.AssertionReader], dict[str, int]]:
    # The five hospital-fold readers are identical in the layered, RS-mode, and twin reports, so they are trained once per backend choice.
    w = load_world(DEV / "dasar", with_key=True)
    c, k = w["claims"].set_index("nomor_sep"), w["key_claims"].set_index("nomor_sep")
    fold_of = dict(zip(c.kode_rs, pd.factorize(c.kode_rs)[0] % 5))
    path = DEV_OUT / f"pembaca_lipat_rs_{'_'.join(heads[h] for h in A.HEADS)}.joblib"
    if path.exists():
        return joblib.load(path), fold_of
    use_embedding_cache(heads)
    train_docs = pd.read_parquet(DEV / "dasar" / "rme_documents.parquet")
    labelled = pd.read_parquet(DEV / "dasar" / "key" / "key_sentences.parquet")
    readers = {}
    for f in range(5):
        held = c.index[c.kode_rs.map(fold_of) == f]
        data = A.training_sentences(train_docs[~train_docs.nomor_sep.isin(held)], labelled[~labelled.nomor_sep.isin(held)], k.gaya_tulis)
        readers[f] = A.AssertionReader.fit(data, heads)
    joblib.dump(readers, path)
    return readers, fold_of


def read_by_fold(heads: dict[str, str], docs: pd.DataFrame, pop: pd.Index, rs: pd.Series) -> pd.Series:
    # Cross-fitted by hospital fold, so no claim is read by a model trained on its own hospital's DEV sentences.
    readers, fold_of = fold_readers(heads)
    out = {}
    for f, reader in readers.items():
        mine = pop[rs.reindex(pop).map(fold_of).to_numpy() == f]
        pairs = [(sep, s) for sep, d in docs[docs.nomor_sep.isin(mine)].groupby("nomor_sep") for s in B.sentences(B.assemble(d))]
        read = reader.read([s for _, s in pairs]).assign(nomor_sep=[sep for sep, _ in pairs])
        out |= {sep: A.ventilation(g) for sep, g in read.groupby("nomor_sep")}
    return pd.Series(out, name="ventilasi")


def assertion_population(heads: dict[str, str]) -> pd.Series:
    path = OUT / f"asersi_per_klaim_{'_'.join(heads[h] for h in A.HEADS)}.parquet"
    if path.exists():
        return pd.read_parquet(path).ventilasi
    use_embedding_cache(heads)
    w = load_world(WORLD, with_key=True, key=KEY)
    c, k = w["claims"].set_index("nomor_sep"), w["key_claims"].set_index("nomor_sep")
    series = read_by_fold(heads, pd.read_parquet(WORLD / "rme_documents.parquet"), k.index[k.populasi_garis.fillna(False)], c.kode_rs)
    series.to_frame().to_parquet(path)
    return series


def mode_layers(c: pd.DataFrame, pop: pd.Index, kw: pd.DataFrame, vent: pd.Series, sheet: pd.DataFrame, fast: pd.DataFrame) -> pd.DataFrame:
    kw, sheet, fast = kw.reindex(pop), sheet.reindex(pop), fast.reindex(pop)
    billed = c.loc[pop].procedure.map(lambda x: bool(set(split_codes(x)) & (B.VENT_CODES | {"96.04"})))
    # Text hours come from the keyword reader, never from the key, so this is the same indicator the app can compute.
    return pd.DataFrame({"kata_kunci": kw.verdict.eq("tidak_mendukung"), "asersi": billed & vent.reindex(pop).eq("tidak"),
                         "klaim_vs_lembar": sheet.klaim_vs_lembar.fillna(False).astype(bool),
                         "teks_vs_lembar": (kw.jam >= B.SHEET_MIN_HOURS) & (sheet.lembar < B.SHEET_SHARE * kw.jam),
                         "kloning": fast.kloning.fillna(False).astype(bool), "tulis_massal": fast.tulis_massal.fillna(False).astype(bool)}, index=pop)


def mode_tests(layers: pd.DataFrame, c: pd.DataFrame, pop: pd.Index) -> dict[str, dict[str, pd.DataFrame]]:
    # "sesudah" counts MIN_KLAIM over every eligible claim of the mode as AI 1 does (TARGETS 116-117, bug fix riwayat baris 11); "sebelum" counted only the tested pool.
    cc = c.loc[pop]
    pools = {"fiktif": cc.index[A1.eligible_fictitious(cc)], "diperpanjang": cc.index[A1.prolonged_window(cc)], "rme_meragukan": pop}
    count = lambda mask: pd.Series(mask, index=c.index).groupby(c.kode_rs).sum()
    eligible = {"fiktif": count(A1.eligible_fictitious(c)), "diperpanjang": count(A1.eligible_prolonged(c)), "rme_meragukan": count(A1.in_line(c))}
    out = {}
    for name, n_layak in (("sesudah", eligible), ("sebelum", None)):
        f = F.mode_flags(layers, pools, c.kode_rs, n_layak)
        f["fiktif_fisiologi_saja"] = F.rs_flags(layers.loc[pools["fiktif"], ["klaim_vs_lembar", "teks_vs_lembar"]].any(axis=1), c.kode_rs,
                                                (n_layak or {}).get("fiktif"))
        out[name] = f
    return out


def mode_summary(flags: dict[str, pd.DataFrame], h: pd.DataFrame, honest_rs: pd.Index) -> dict:
    report = {}
    for name, f in flags.items():
        mode = name.split("_fisiologi")[0]
        f = f.join(h[["modus", "tingkat", "intensitas_terwujud"]])
        honest = f[f.index.isin(honest_rs)]
        tiers = {}
        for tier in sorted(f[f.modus == mode].tingkat.unique()):
            p = f[(f.modus == mode) & (f.tingkat == tier) & (f.intensitas_terwujud > 0)]
            ok = p[(p.intensitas_terwujud >= 0.10) & (p.n_layak >= S.MIN_KLAIM)]
            tiers[tier] = {"layak_ditandai": f"{int(ok.ditandai.sum())}/{len(ok)}", "semua_ditandai": f"{int(p.ditandai.sum())}/{len(p)}"}
        report[name] = {"tingkat": tiers, "rs_jujur_ditandai": f"{int(honest.ditandai.sum())}/{int((honest.n_layak >= S.MIN_KLAIM).sum())}",
                        "rs_dinilai": int((f.n_layak >= S.MIN_KLAIM).sum()),
                        "rs_lain_ditandai": f[f.ditandai & (f.modus != mode) & ~f.index.isin(honest_rs)].modus.replace("", "garis lain").value_counts().to_dict()}
    return report


def status_changes(tests: dict[str, dict[str, pd.DataFrame]], h: pd.DataFrame, honest_rs: pd.Index) -> dict:
    out = {}
    for mode, after in tests["sesudah"].items():
        before = tests["sebelum"][mode].n_layak.reindex(after.index, fill_value=0) >= S.MIN_KLAIM
        new = after.index[(after.n_layak >= S.MIN_KLAIM) & ~before]
        kind = pd.Series(np.where(h.modus.reindex(new) == mode.split("_fisiologi")[0], "pelaku_modus_ini",
                                  np.where(new.isin(honest_rs), "jujur", "lain")), index=new)
        out[mode] = {"tidak_dinilai_menjadi_dinilai": len(new), "rincian": kind.value_counts().to_dict(),
                     "ditandai_di_antaranya": int(after.loc[new].ditandai.sum())}
    return out


def rs_modes(heads: dict[str, str] | None = None) -> dict:
    heads = heads or dict.fromkeys(A.HEADS, "ngram")
    w = load_world(WORLD, with_key=True, key=KEY)
    c, k, h = w["claims"].set_index("nomor_sep"), w["key_claims"].set_index("nomor_sep"), w["key_hospitals"].set_index("kode_rs")
    kw = pd.read_parquet(OUT / "kata_kunci_per_klaim.parquet")
    pop = kw.index
    layers = mode_layers(c, pop, kw, assertion_population(heads), pd.read_parquet(OUT / "fisiologi_per_klaim.parquet"),
                         pd.read_parquet(OUT / "lapis_cepat_per_klaim.parquet"))
    tests = mode_tests(layers, c, pop)
    honest_rs = h.index[honest_hospitals(h.reset_index()).to_numpy()]
    report = {"per_klaim": layers.join(truth(k.loc[pop])).groupby("lapis")[list(layers.columns)].mean().round(4).to_dict(orient="index")}
    report |= mode_summary(tests["sesudah"], h, honest_rs)
    report["sebelum_perbaikan_kelayakan"] = mode_summary(tests["sebelum"], h, honest_rs)
    report["rs_berubah_status"] = status_changes(tests, h, honest_rs)
    (OUT / "rs_per_modus_laporan.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str))
    return report


def placebo_modes(heads: dict[str, str]) -> dict:
    # The fraud-free twin of DEV (same hospitals and patients, honest RME), read with the same layers; every RS it flags is a false alarm.
    key = KEY
    c = pd.read_parquet(key / "key_placebo_claims.parquet").set_index("nomor_sep")
    pop = c.index[A1.in_line(c)]
    docs = pd.read_parquet(key / "key_placebo_rme_documents.parquet")
    base_path, vent_path = OUT / "plasebo_lapis_dasar.parquet", OUT / f"plasebo_asersi_{'_'.join(heads[x] for x in A.HEADS)}.parquet"
    if not base_path.exists():
        vitals = pd.read_parquet(key / "key_placebo_rme_vitals.parquet")
        icu = Path(__file__).resolve().parents[1] / "data" / "icu_open"
        model, _ = P.train(pd.read_parquet(icu / "eicu_hourly.parquet"), pd.read_parquet(icu / "mimic_hourly.parquet"))
        claimed = c.loc[pop].ventilator_hour.astype(float)
        base = keyword_rows(c, docs, pop)[["verdict", "jam"]].reindex(pop)
        base["lembar"] = P.ventilated_hours(P.hourly_ventilation(model, vitals[vitals.nomor_sep.isin(pop)])).reindex(pop)
        base["klaim_vs_lembar"] = (claimed >= B.SHEET_MIN_HOURS) & (base.lembar < B.SHEET_SHARE * claimed)
        base = base.join(F.clone_scores(docs, c.kode_rs)[["kloning"]]).join(F.write_trail(docs, c.tgl_pulang)[["tulis_massal"]])
        base.to_parquet(base_path)
    if not vent_path.exists():
        use_embedding_cache(heads)
        read_by_fold(heads, docs, pop, c.kode_rs).to_frame().to_parquet(vent_path)
    base = pd.read_parquet(base_path)
    layers = mode_layers(c, pop, base, pd.read_parquet(vent_path).ventilasi, base, base)
    tests = mode_tests(layers, c, pop)
    report = {"klaim_populasi": len(pop), "per_klaim": layers.mean().round(4).to_dict()}
    for name, flags in tests.items():
        report[name] = {mode: {"rs_dinilai": int((f.n_layak >= S.MIN_KLAIM).sum()), "rs_ditandai": f.index[f.ditandai].tolist()} for mode, f in flags.items()}
    (OUT / "plasebo_rs_per_modus_laporan.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str))
    return report


# Variant -> (assertion cross-fit scheme, physiology on, provenance on); "semua_lapis" is T8 with every layer active.
VARIANTS = {"llm": (None, False, False), "llm_asersi_rs": ("rs", False, False), "llm_asersi_gaya": ("gaya", False, False),
            "llm_asersi_rs_fisiologi": ("rs", True, False), "semua_lapis_rs": ("rs", True, True), "semua_lapis_gaya": ("gaya", True, True)}

if __name__ == "__main__":
    if sys.argv[1:2] == ["baca"]:
        run(int(sys.argv[2]) if len(sys.argv) > 2 else None)
    elif sys.argv[1:2] == ["uji_paralel"]:
        print(json.dumps(parallel_check(int(sys.argv[2]) if len(sys.argv) > 2 else 20), ensure_ascii=False, indent=1))
    elif sys.argv[1:2] == ["embed_dunia"]:
        print(json.dumps(embed_world(), ensure_ascii=False))
    elif sys.argv[1:2] == ["asersi_dunia"]:
        print(json.dumps(assertion_world(dict(zip(A.HEADS, sys.argv[2:5]))), ensure_ascii=False, indent=1))
    elif sys.argv[1:2] == ["ulang_kutipan"]:
        print(json.dumps(retry_readings(), ensure_ascii=False))
    elif sys.argv[1:2] == ["plasebo_modus"]:
        print(json.dumps(placebo_modes(dict(zip(A.HEADS, sys.argv[2:5]))), ensure_ascii=False, indent=1, default=str))
    elif sys.argv[1:2] == ["beban_jejak"]:
        print(json.dumps(late_burden(), ensure_ascii=False, indent=1))
    elif sys.argv[1:2] == ["ambang_jejak"]:
        print(json.dumps(late_thresholds(), ensure_ascii=False, indent=1))
    elif sys.argv[1:2] == ["rs_modus"]:
        print(json.dumps(rs_modes(dict(zip(A.HEADS, sys.argv[2:5])) if len(sys.argv) > 4 else None), ensure_ascii=False, indent=1, default=str))
    elif sys.argv[1:2] == ["narasi"]:
        print(json.dumps(narratives(path=OUT / sys.argv[2]) if len(sys.argv) > 2 else narratives(), ensure_ascii=False, indent=1))
    elif sys.argv[1:2] == ["d1_d11"]:
        print(json.dumps(llm_on_sample_docs(dict(zip(A.HEADS, sys.argv[2:5])) if len(sys.argv) > 4 else None), ensure_ascii=False, indent=1, default=str))
    elif sys.argv[1:2] == ["berlapis"]:
        print(json.dumps(layered(dict(zip(A.HEADS, sys.argv[2:5])), OUT / sys.argv[5] if len(sys.argv) > 5 else READINGS), ensure_ascii=False,
                         indent=1, default=str))
    elif sys.argv[1:2] == ["fisiologi"]:
        print(json.dumps(physiology_report(), ensure_ascii=False, indent=1, default=str))
    elif sys.argv[1:2] == ["kata_kunci"]:
        print(json.dumps(keyword_layer(), ensure_ascii=False, indent=1, default=str))
    elif sys.argv[1:2] == ["cepat"]:
        print(json.dumps(fast_layers(), ensure_ascii=False, indent=1, default=str))
    elif sys.argv[1:2] == ["asersi"]:
        print(json.dumps(assertion_report(tuple(sys.argv[2:]) or ("ngram", "embedding")), ensure_ascii=False, indent=1))
    else:
        run(int(sys.argv[1]) if len(sys.argv) > 1 else None)
