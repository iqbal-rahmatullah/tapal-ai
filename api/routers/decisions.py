import csv
import io
from contextlib import closing
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, ValidationError

from engine.contracts import (Decision, DecisionKind, ObjectKind, Role, append_decision, open_decision_log, read_decisions, validation_issues,
                              verify_chain)

router = APIRouter(prefix="/api/v1", tags=["Jejak keputusan"])


class DecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    peran: Role = "verifikator"
    objek_jenis: ObjectKind
    objek_id: str
    keputusan: DecisionKind
    catatan: str = ""
    dasar_ai: dict[str, Any] = {}
    koreksi_untuk: int | None = None
    bukti: dict[str, Any] = {}


class DecisionRow(BaseModel):
    id: int
    waktu: str
    peran: str
    objek_jenis: str
    objek_id: str
    keputusan: str
    catatan: str
    dasar_ai: dict[str, Any]
    koreksi_untuk: int | None
    versi_model: str
    bukti: dict[str, Any]
    sidik_sebelum: str
    sidik: str


class DecisionLog(BaseModel):
    baris: list[DecisionRow]
    total: int
    rantai_utuh: bool
    rusak_di: int | None


def _rows(request: Request) -> list[dict[str, Any]]:
    with closing(open_decision_log(request.app.state.db)) as conn:
        return read_decisions(conn)


@router.post("/keputusan", status_code=201)
def add_decision(body: DecisionIn, request: Request) -> DecisionRow:
    try:
        decision = Decision(waktu=datetime.now(timezone.utc), **body.model_dump())
    except ValidationError as e:
        raise HTTPException(422, [i.model_dump(mode="json") for i in validation_issues(e)]) from e
    with closing(open_decision_log(request.app.state.db)) as conn:
        try:
            rid, _ = append_decision(conn, decision)
        except ValueError as e:
            raise HTTPException(422, [{"kolom": "koreksi_untuk", "pesan": str(e), "nilai_diterima": body.koreksi_untuk}]) from e
        row = next(r for r in read_decisions(conn) if r["id"] == rid)
    return DecisionRow(**row)


def _filtered(rows: list[dict[str, Any]], peran: str | None, objek_jenis: str | None, keputusan: str | None, objek_id: str | None) -> list[dict]:
    keep = [r for r in rows if (peran is None or r["peran"] == peran) and (objek_jenis is None or r["objek_jenis"] == objek_jenis)
            and (keputusan is None or r["keputusan"] == keputusan) and (objek_id is None or r["objek_id"] == objek_id)]
    return keep[::-1]


@router.get("/keputusan")
def list_decisions(request: Request, peran: Annotated[str | None, Query()] = None, objek_jenis: Annotated[str | None, Query()] = None,
                   keputusan: Annotated[str | None, Query()] = None, objek_id: Annotated[str | None, Query()] = None) -> DecisionLog:
    rows = _rows(request)
    broken = verify_chain(rows)
    return DecisionLog(baris=[DecisionRow(**r) for r in _filtered(rows, peran, objek_jenis, keputusan, objek_id)], total=len(rows),
                       rantai_utuh=broken is None, rusak_di=broken)


def _cell(value: Any) -> str:
    # Security: a note starting with = + - @ tab or CR would run as a spreadsheet formula, so it is prefixed with a quote.
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


@router.get("/keputusan.csv", response_class=Response, responses={200: {"content": {"text/csv": {}}}})
def export_decisions(request: Request, peran: Annotated[str | None, Query()] = None, objek_jenis: Annotated[str | None, Query()] = None,
                     keputusan: Annotated[str | None, Query()] = None, objek_id: Annotated[str | None, Query()] = None) -> Response:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["id", "waktu", "peran", "objek_jenis", "objek_id", "keputusan", "catatan", "dasar_ai", "koreksi_untuk", "versi_model", "sidik_sebelum", "sidik"])
    for r in _filtered(_rows(request), peran, objek_jenis, keputusan, objek_id):
        w.writerow([_cell(x) for x in (r["id"], r["waktu"], r["peran"], r["objek_jenis"], r["objek_id"], r["keputusan"], r["catatan"],
                                       "; ".join(f"{k}={v}" for k, v in r["dasar_ai"].items()), r["koreksi_untuk"] or "", r["versi_model"],
                                       r["sidik_sebelum"], r["sidik"])])
    # The BOM lets spreadsheet apps read Indonesian text as UTF-8.
    return Response("﻿" + out.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="jejak-keputusan.csv"'})
