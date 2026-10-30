from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from engine import MODEL_VERSION

app = FastAPI(title="TAPAL API", version=MODEL_VERSION)


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "versi_model": MODEL_VERSION}


WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
if WEB_DIST.is_dir():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
