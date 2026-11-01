import logging
import os
from contextlib import asynccontextmanager, closing
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from api import machine
from api.routers import claims, decisions, screens
from engine import MODEL_VERSION
from engine.contracts import open_decision_log, read_decisions, verify_chain

ROOT = Path(__file__).resolve().parents[1]
WEB_DIST = ROOT / "web" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = Path(os.environ.get("TAPAL_DB", ROOT / "data" / "tapal.db"))
    app.state.db.parent.mkdir(parents=True, exist_ok=True)
    with closing(open_decision_log(app.state.db)) as conn:
        broken = verify_chain(read_decisions(conn))
    if broken is not None:
        logging.getLogger("tapal").error("rantai sidik jejak keputusan rusak mulai baris %s", broken)
    app.state.claims = claims.start(app.state.db)
    try:
        app.state.dev = machine.Dev(app.state.claims.engine)
    except FileNotFoundError as e:
        app.state.dev = None
        logging.getLogger("tapal").error("layar memakai data contoh desain: %s", e)
    yield
    app.state.claims.pending.put(None)


app = FastAPI(
    title="TAPAL API",
    version=MODEL_VERSION,
    lifespan=lifespan,
    description="Pemeriksa garis tarif ventilator. Semua data adalah data sintetis, bukan data peserta JKN.",
)
# Security: only local host names are served, which also closes DNS rebinding from a page open in the same browser.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
app.include_router(claims.router)
app.include_router(screens.router)
app.include_router(decisions.router)


@app.get("/api/v1/health", tags=["Sistem"])
def health() -> dict[str, str]:
    return {"status": "ok", "versi_model": MODEL_VERSION}


if WEB_DIST.is_dir():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
