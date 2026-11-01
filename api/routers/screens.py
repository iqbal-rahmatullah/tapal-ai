import hashlib
import logging
import os
import subprocess
import tempfile
import time
from contextlib import closing
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel

from api import samples
from api.machine import Dev
from api.utils import runtime
from engine import narrative as N
from engine.contracts import canonical_json, open_decision_log, read_decisions

router = APIRouter(prefix="/api/v1", tags=["Data layar"])


def _example(payload: dict) -> dict:
    return {200: {"content": {"application/json": {"example": payload}}}}


def _dev(request: Request) -> Dev | None:
    # None when the DEV engine outputs are missing; every screen then falls back to the design samples and says so.
    return getattr(request.app.state, "dev", None)


def _decisions(request: Request) -> list[dict]:
    with closing(open_decision_log(request.app.state.db)) as conn:
        return read_decisions(conn)


@router.get("/antrean", responses=_example(samples.QUEUE))
def queue(request: Request) -> dict[str, Any]:
    dev = _dev(request)
    return dev.queue(_decisions(request)) if dev else samples.QUEUE


@router.get("/rs/{kode_rs}", responses=_example(samples.PROFILES["RS-092"]))
def hospital(kode_rs: str, request: Request) -> dict[str, Any]:
    if dev := _dev(request):
        profile = dev.profile(kode_rs, _decisions(request))
        if profile is None:
            raise HTTPException(404, f"{kode_rs} tidak ada di antrean kerja")
        return {k: v for k, v in profile.items() if k != "templat"}
    if kode_rs in samples.PROFILES:
        return samples.PROFILES[kode_rs]
    row = next((r for r in samples.FLAGGED if r["kode_rs"] == kode_rs), None)
    if row is None:
        raise HTTPException(404, f"{kode_rs} tidak ada di antrean kerja")
    return {"sumber_data": samples.SAMPLE, "hanya_ringkas": True, **row}


MEANING = {
    "rs": "kode rumah sakit", "periode": "periode penilaian RS",
    "diakui": "jumlah klaim garis ventilator yang diajukan RS", "wajar": "jumlah klaim yang didukung bukti di klaim menurut AI 1",
    "wajar_bawah": "batas bawah rentang 95% klaim wajar", "wajar_atas": "batas atas rentang 95% klaim wajar",
    "kelebihan": "jumlah klaim kelebihan yang dihitung kode dari klaim diakui dan klaim wajar", "rupiah": "perkiraan kelebihan bayar",
    "dibaca": "jumlah RME yang sudah dibaca AI 2", "tidak_mendukung": "jumlah RME yang tidak mendukung kode ventilasi",
    "kembar": "jumlah pasien dengan catatan RME nyaris identik", "kemiripan": "median kemiripan catatan kelompok kembar",
    "gelombang": "jumlah gelombang penulisan catatan secara massal", "serentak": "jumlah klaim yang seluruh catatannya ditulis dalam satu sesi",
    "ditahan": "jumlah klaim yang ditahan bacaan RME",
}
MEANING_BY_MODE = {
    "diperpanjang": {"diakui": "jumlah klaim dengan ventilasi 96 jam atau lebih yang diajukan RS",
                     "tidak_mendukung": "jumlah RME yang mencatat jam ventilasi di bawah garis 96 jam"},
    "rme_meragukan": {"rupiah": "nilai yang dipertaruhkan, bukan perkiraan kelebihan bayar"},
}


class Segment(BaseModel):
    teks: str
    token: str | None
    asal: str | None


class SummarySource(BaseModel):
    angka: str
    asal: str
    label: list[str]


class Summary(BaseModel):
    kode_rs: str
    sumber: str
    durasi_ms: int
    segmen: list[Segment]
    asal_angka: list[SummarySource]
    catatan: list[str]
    sumber_data: str


@router.post("/rs/{kode_rs}/ringkasan")
def summarise(kode_rs: str, request: Request) -> Summary:
    dev = _dev(request)
    profile = dev.profile(kode_rs, _decisions(request)) if dev else samples.PROFILES.get(kode_rs)
    if profile is None:
        raise HTTPException(404, f"ringkasan untuk {kode_rs} belum tersedia")
    template = profile["templat"] if dev else samples.SUMMARY_TEMPLATES[profile["modus"]]
    meaning = MEANING | MEANING_BY_MODE.get(profile["modus"], {})
    if profile.get("mesin_penanda") == "AI 2":
        meaning["rupiah"] = MEANING_BY_MODE["rme_meragukan"]["rupiah"]
    period = dev.period()["penilaian"].removeprefix("data 12 bulan, ") if dev else "Jan–Des 2025"
    facts = {"rs": N.Fact(kode_rs, "kode RS sintetis", meaning["rs"]), "periode": N.Fact("12 bulan", period, meaning["periode"])}
    facts |= {k: N.Fact(v[0], v[1], meaning.get(k, v[1])) for k, v in profile["fakta_ringkasan"].items()}
    start = time.perf_counter()
    story = N.narrate(facts, template, use_llm=runtime.llm_active())
    sources = [SummarySource(angka=v[0], asal=v[1], label=v[2]) for v in profile["fakta_ringkasan"].values()]
    return Summary(kode_rs=kode_rs, sumber=story.source, durasi_ms=int((time.perf_counter() - start) * 1000), segmen=story.segments,
                   asal_angka=sources, catatan=story.reasons, sumber_data=profile["sumber_data"])


def latest_decision(request: Request, kind: str, object_id: str) -> dict | None:
    rows = [r for r in _decisions(request) if r["objek_jenis"] == kind and r["objek_id"] == object_id]
    return rows[-1] if rows else None


@router.get("/klaim/{nomor_sep}", responses=_example({k: v for k, v in samples.CLAIMS["SIN-092-25-00412"].items() if not k.startswith("rme")}))
def claim(nomor_sep: str, request: Request) -> dict[str, Any]:
    dev = _dev(request)
    c = dev.claim(nomor_sep) if dev else None
    if c is None:
        sample = samples.CLAIMS.get(nomor_sep)
        if sample is None:
            raise HTTPException(404, f"klaim {nomor_sep} tidak ada di dunia DEV")
        c = {**{k: v for k, v in sample.items() if not k.startswith("rme")}, "rme": {"status": "diproses", "hasil": f"/api/v1/klaim/{nomor_sep}/bacaan"}}
    return {**c, "keputusan_terakhir": latest_decision(request, "klaim", nomor_sep)}


@router.get("/klaim/{nomor_sep}/bacaan")
def claim_reading(nomor_sep: str, request: Request) -> dict[str, Any]:
    dev = _dev(request)
    if dev and (reading := dev.reading(nomor_sep)) is not None:
        return reading
    sample = samples.CLAIMS.get(nomor_sep)
    if sample is None:
        raise HTTPException(404, f"tidak ada bacaan RME untuk {nomor_sep}")
    rme = sample["rme_aturan"] if "rme_aturan" in sample and not runtime.llm_active() else sample["rme"]
    return {"status": "selesai", "tahap": "selesai", **rme, "sumber_data": samples.SAMPLE}


class LlmSwitch(BaseModel):
    aktif: bool


@router.get("/llm", tags=["Sistem"])
def llm_status() -> dict[str, Any]:
    return runtime.llm_state()


@router.put("/llm", tags=["Sistem"])
def llm_switch(body: LlmSwitch) -> dict[str, Any]:
    runtime.set_switch(body.aktif)
    return runtime.llm_state()


@router.get("/pemindai", responses=_example(samples.LINES))
def line_scanner(request: Request) -> dict[str, Any]:
    dev = _dev(request)
    return dev.lines() if dev else samples.LINES


@router.get("/audit/rencana", responses=_example(samples.AUDIT))
def audit_plan(request: Request, anggaran: Annotated[int, Query(ge=20, le=200)] = 60, kebijakan: Literal["agen", "statis", "acak"] = "agen",
               urutan: Literal["rupiah", "peluang"] = "rupiah") -> dict[str, Any]:
    if dev := _dev(request):
        return dev.audit(anggaran, kebijakan, urutan)
    same = anggaran == 60 and kebijakan == "agen" and urutan == "rupiah"
    return {**samples.AUDIT, "permintaan": {"anggaran": anggaran, "kebijakan": kebijakan, "urutan": urutan},
            "catatan_permintaan": None if same else "Rencana untuk pengaturan ini menunggu keluaran AI 3; daftar dan takaran di bawah adalah agen belajar, anggaran 60."}


def _story(facts: dict[str, list], template: list[str]) -> dict[str, Any]:
    start = time.perf_counter()
    story = N.narrate({k: N.Fact(v[0], v[1], v[1]) for k, v in facts.items()}, template, use_llm=runtime.llm_active())
    return {"sumber": story.source, "durasi_ms": int((time.perf_counter() - start) * 1000), "segmen": story.segments, "catatan": story.reasons}


_NARRATIVE: dict[str, Any] = {}


def _report(request: Request) -> dict[str, Any]:
    dev = _dev(request)
    return dev.report(_decisions(request)) if dev else samples.REPORT


@router.get("/laporan", responses=_example(samples.REPORT))
def report(request: Request) -> dict[str, Any]:
    full = _report(request)
    body = {k: v for k, v in full.items() if not k.startswith(("fakta", "templat"))}
    return {**body, "sidik_dokumen": hashlib.sha256(canonical_json(full).encode()).hexdigest()[:8]}


@router.post("/laporan/narasi")
def report_narrative(request: Request) -> dict[str, Any]:
    full = _report(request)
    _NARRATIVE["terakhir"] = _story(full["fakta_narasi"], full["templat_narasi"])
    return _NARRATIVE["terakhir"]


@router.get("/laporan/narasi")
def last_report_narrative(request: Request) -> dict[str, Any]:
    return _NARRATIVE.get("terakhir") or report_narrative(request)


@router.post("/laporan/surat/{kode_rs}")
def letter(kode_rs: str, request: Request) -> dict[str, Any]:
    dev = _dev(request)
    spec = dev.letter(kode_rs, _decisions(request)) if dev else samples.LETTER.get(kode_rs)
    if spec is None:
        raise HTTPException(404, f"draf surat untuk {kode_rs} belum tersedia")
    return {**{k: v for k, v in spec.items() if k not in ("fakta", "templat")}, "kode_rs": kode_rs, **_story(spec["fakta"], spec["templat"])}


CHROME = os.environ.get("TAPAL_CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
# Chrome prints only our own page, so its update, sync, and telemetry traffic is switched off.
CHROME_QUIET = ["--disable-background-networking", "--disable-component-update", "--disable-sync", "--no-first-run", "--disable-extensions"]


@router.get("/laporan.pdf", response_class=Response, responses={200: {"content": {"application/pdf": {}}}})
def report_pdf(request: Request) -> Response:
    # Security: the print URL comes from the server socket, never from the Host header, so a forged Host cannot point Chrome elsewhere.
    base = os.environ.get("TAPAL_WEB_URL") or f"http://127.0.0.1:{request.scope['server'][1]}"
    if not Path(CHROME).exists():
        raise HTTPException(503, "Chrome tidak ditemukan untuk mencetak PDF; setel TAPAL_CHROME")
    _report(request)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "laporan.pdf"
        cmd = [CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", *CHROME_QUIET, f"--user-data-dir={tmp}",
               "--virtual-time-budget=15000", f"--print-to-pdf={out}", f"{base}/#/cetak"]
        try:
            subprocess.run(cmd, check=True, timeout=60, capture_output=True)
        except (subprocess.SubprocessError, OSError) as e:
            logging.getLogger("tapal").exception("cetak PDF gagal")
            raise HTTPException(503, "PDF gagal dicetak; rincian ada di log server") from e
        return Response(out.read_bytes(), media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="tapal-laporan-desember-2025.pdf"'})
