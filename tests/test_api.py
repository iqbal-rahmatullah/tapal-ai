import json
import os
import re
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from api import machine, samples
from api.utils import runtime
from engine.data import DEV
from engine.narrative import TOKEN

pytestmark = pytest.mark.skipif(not (DEV / "dasar" / "claims.parquet").exists() or not all(p.exists() for p in machine.FILES.values()),
                                reason="dunia DEV atau keluaran mesin DEV belum ada")
SCREENS = ("/api/v1/antrean", "/api/v1/pemindai", "/api/v1/audit/rencana", "/api/v1/laporan")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    mp.setenv("TAPAL_DB", str(tmp_path_factory.mktemp("db") / "tapal.db"))
    # Every test runs with the local LLM switched off, so the keyword fallback answers and no test waits on Ollama.
    runtime.set_switch(False)
    from api.main import app
    with TestClient(app) as c:
        yield c
    runtime.set_switch(True)
    mp.undo()


def test_screens_serve_engine_outputs_and_404(client):
    queue = client.get("/api/v1/antrean").json()
    first = queue["rs"][0]["kode_rs"]
    profile = client.get(f"/api/v1/rs/{first}").json()
    sep = profile["klaim"][0]["nomor_sep"]
    for path in (*SCREENS, f"/api/v1/rs/{first}", f"/api/v1/klaim/{sep}", f"/api/v1/klaim/{sep}/bacaan"):
        r = client.get(path)
        assert r.status_code == 200 and r.json()["sumber_data"] == "mesin_dev" and r.json()["bagian_contoh"] == [], path
    assert queue["ringkasan"]["n_ditandai"] == len(queue["rs"]) == len(queue["urutan_keyakinan"])
    assert sum(queue["ringkasan"]["per_mesin"].values()) == len(queue["rs"])
    claim = client.get(f"/api/v1/klaim/{sep}").json()
    assert sum(a["diklaim"] for a in claim["tangga"]["anak"]) == 1 and claim["rme"]["hasil"].endswith("/bacaan")
    reading = client.get(f"/api/v1/klaim/{sep}/bacaan").json()
    assert reading["dokumen"] and reading["sumber"] in ("llm_lokal", "aturan") and reading["hasil"]["verdict_jenis"]
    assert client.get("/api/v1/rs/RS-999").status_code == 404
    assert client.get("/api/v1/klaim/SIN-000-25-00000").status_code == 404
    assert client.get("/api/v1/audit/rencana?anggaran=80").json()["catatan_permintaan"]
    assert client.get("/api/v1/audit/rencana?anggaran=500").status_code == 422


def test_flags_and_rupiah_reproduce_the_stored_ai1_run(client):
    dev = client.app.state.dev
    stored = json.loads(machine.FILES["ai1"].read_text())["rs_ditandai"]
    for mode, rows in stored.items():
        table = dev.ai1_modes[mode]["table"]
        assert sorted(table.index[table.ditandai]) == sorted(r["rs"] for r in rows), mode
    queue = {r["kode_rs"]: r for r in client.get("/api/v1/antrean").json()["rs"]}
    m = dev.ai1_modes["fiktif"]
    for r in stored["fiktif"]:
        row = queue[r["rs"]]
        assert (row["mesin_penanda"], row["diakui"], row["rupiah"]) == ("AI 1", r["O"], r["rupiah"])
        # The profile explains rupiah as excess claims times a weighted mean tariff gap; that product must give back the stored estimate.
        mine = m["pop"] & dev.rs_mask(r["rs"])
        delta = dev.deltas(mine & m["y"], "fiktif")[mine]
        weights = (1 - m["p"][mine]) * m["y"][mine]
        assert abs(max(m["y"][mine].sum() - m["p"][mine].sum(), 0) * np.average(delta, weights=weights) - r["rupiah"]) < 1


def test_screen_reading_follows_the_llm_switch_for_samples(client):
    assert client.get("/api/v1/klaim/SIN-092-25-00412/bacaan").json()["jenis"] == "aturan"
    runtime.set_switch(True)
    try:
        reading = client.get("/api/v1/klaim/SIN-092-25-00412/bacaan").json()
        assert reading["jenis"] == ("baca" if runtime.llm_active() else "aturan")
    finally:
        runtime.set_switch(False)


def test_decision_log_api_appends_verifies_and_exports(client):
    body = {"objek_jenis": "klaim", "objek_id": "SIN-092-25-00412", "keputusan": "minta_klarifikasi", "catatan": "RME hanya menyebut nasal kanul",
            "dasar_ai": {"mesin": ["AI 1", "AI 2"], "versi_model": "tapal-1.0"}}
    first = client.post("/api/v1/keputusan", json=body)
    assert first.status_code == 201 and len(first.json()["sidik"]) == 64
    fix = client.post("/api/v1/keputusan", json={**body, "keputusan": "koreksi", "koreksi_untuk": first.json()["id"], "catatan": "menambah kutipan NRM"})
    assert fix.status_code == 201 and fix.json()["sidik_sebelum"] == first.json()["sidik"]
    log = client.get("/api/v1/keputusan").json()
    assert log["rantai_utuh"] and log["baris"][0]["keputusan"] == "koreksi"
    assert client.get("/api/v1/klaim/SIN-092-25-00412").json()["keputusan_terakhir"]["keputusan"] == "koreksi"
    no_note = client.post("/api/v1/keputusan", json={**body, "catatan": " "})
    assert no_note.status_code == 422
    ghost = client.post("/api/v1/keputusan", json={**body, "keputusan": "koreksi", "koreksi_untuk": 999})
    assert ghost.status_code == 422 and ghost.json()["detail"][0]["kolom"] == "koreksi_untuk"
    formula = client.post("/api/v1/keputusan", json={**body, "objek_id": "SEP-0000000001", "catatan": "=1+1"})
    assert formula.status_code == 201
    csv = client.get("/api/v1/keputusan.csv?objek_jenis=klaim")
    assert csv.text.startswith("﻿id,waktu,peran") and "menambah kutipan NRM" in csv.text and ",'=1+1," in csv.text
    rs = client.get("/api/v1/antrean").json()["rs"][0]["kode_rs"]
    client.post("/api/v1/keputusan", json={**body, "objek_jenis": "rs", "objek_id": rs, "catatan": "minta dokumen ventilator"})
    assert next(r for r in client.get("/api/v1/antrean").json()["rs"] if r["kode_rs"] == rs)["status_penanganan"] == "diklarifikasi"


def test_check_rejects_bad_claims_with_per_field_errors(client):
    examples = {e["kunci"]: e for e in client.get("/api/v1/klaim/contoh").json()}
    r = client.post("/api/v1/klaim/periksa", json=examples["data_rusak"]["payload"])
    assert r.status_code == 422
    assert {g["kolom"] for g in r.json()["galat"]} == {"umur", "tgl_pulang", "ventilator_hour"}
    unknown = {**examples["bukti_lemah"]["payload"], "kode_rs": "RS-999"}
    assert client.post("/api/v1/klaim/periksa", json=unknown).json()["galat"][0]["kolom"] == "kode_rs"
    mixed = {**examples["bukti_lemah"]["payload"]}
    mixed["tgl_pulang"] = mixed["tgl_pulang"].removesuffix("+07:00")
    r = client.post("/api/v1/klaim/periksa", json=mixed)
    assert r.status_code == 422 and [g["kolom"] for g in r.json()["galat"]] == ["tgl_pulang"]


def test_pdf_ignores_a_forged_host(client):
    assert client.get("/api/v1/laporan.pdf", headers={"host": "evil.example"}).status_code == 400


def test_check_answers_ai1_first_then_rme_with_fallback(client):
    examples = {e["kunci"]: e for e in client.get("/api/v1/klaim/contoh").json()}
    payload = examples["bukti_lemah"]["payload"]
    r = client.post("/api/v1/klaim/periksa", json=payload)
    assert r.status_code == 200
    first = r.json()
    assert first["status"] == "periksa_manual" and first["rme"]["status"] == "diproses" and first["versi_model"] == "tapal-1.0"
    assert [s["nama"] for s in first["langkah"]][:3] == ["Validasi skema", "Fitur bukti", "Peluang didukung"]
    assert first["selisih_tarif_dipertaruhkan"] > 0
    if os.environ.get("TAPAL_AI2_OFF") == "1":
        assert any("TAPAL_AI2_OFF" in reason for reason in first["alasan"])
    deadline = time.time() + 60
    while (rme := client.get(f"/api/v1/klaim/{payload['nomor_sep']}/rme").json())["status"] != "selesai":
        assert time.time() < deadline, rme
        time.sleep(0.5)
    assert rme["tahap"] == "selesai" and rme["sumber"] == "aturan" and rme["status_klaim"] == "periksa_manual"


def test_narratives_insert_code_numbers_and_say_when_templated(client):
    rs = [r["kode_rs"] for r in client.get("/api/v1/antrean").json()["rs"]]
    letter_rs = client.get("/api/v1/laporan").json()["surat_rs"]
    for path in (f"/api/v1/rs/{rs[0]}/ringkasan", f"/api/v1/rs/{rs[-1]}/ringkasan", "/api/v1/laporan/narasi", f"/api/v1/laporan/surat/{letter_rs}",
                 f"/api/v1/laporan/surat/{rs[-1]}"):
        story = client.post(path).json()
        assert story["sumber"] == "aturan", path
        text = "".join(s["teks"] for s in story["segmen"])
        assert "{" not in text and any(s["token"] for s in story["segmen"]), path


def test_every_template_token_is_valid_and_backed_by_a_fact(client):
    pairs = [(samples.REPORT["fakta_narasi"], samples.REPORT["templat_narasi"]), (samples.LETTER["RS-092"]["fakta"], samples.LETTER["RS-092"]["templat"])]
    pairs += [(p["fakta_ringkasan"], samples.SUMMARY_TEMPLATES[p["modus"]]) for p in samples.PROFILES.values()]
    dev = client.app.state.dev
    report = dev.report([])
    pairs.append((report["fakta_narasi"], report["templat_narasi"]))
    for row in dev.flagged:
        profile = dev.profile(row["kode_rs"], [])
        letter = dev.letter(row["kode_rs"], [])
        pairs += [(profile["fakta_ringkasan"], profile["templat"]), (letter["fakta"], letter["templat"])]
    for facts, template in pairs:
        used = set(re.findall(r"\{(\w+)\}", " ".join(template)))
        assert all(TOKEN.fullmatch("{" + t + "}") for t in used)
        assert used <= set(facts) | {"rs", "periode"}


def test_llm_switch_round_trip(client):
    assert client.put("/api/v1/llm", json={"aktif": False}).json()["sakelar"] is False
    assert client.get("/api/v1/llm").json()["aktif"] is False


def test_docs_example_runs_and_docs_page_is_served(client):
    from api.routers.claims import DOC_EXAMPLE
    assert client.post("/api/v1/klaim/periksa", json=DOC_EXAMPLE).status_code == 200
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").json()["paths"]["/api/v1/klaim/periksa"]["post"]["requestBody"]["content"]["application/json"]["example"] == DOC_EXAMPLE
