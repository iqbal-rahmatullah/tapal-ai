import time

import httpx

from engine.ai2 import MODEL, OLLAMA, llm_enabled

_probe = {"at": 0.0, "ok": False}
# The switch on Cek klaim masuk simulates an LLM outage for every screen at once; it never stops Ollama itself.
_switch = {"on": True}


def llm_reachable() -> bool:
    if time.monotonic() - _probe["at"] > 10:
        try:
            _probe["ok"] = httpx.get(f"{OLLAMA}/api/tags", timeout=0.5).status_code == 200
        except httpx.HTTPError:
            _probe["ok"] = False
        _probe["at"] = time.monotonic()
    return _probe["ok"]


def set_switch(on: bool) -> None:
    _switch["on"] = on


def llm_active() -> bool:
    return _switch["on"] and llm_enabled() and llm_reachable()


def llm_state() -> dict:
    # With TAPAL_LLM=off the probe is skipped, so a disabled LLM never sends even a model listing request to Ollama.
    return {"aktif": llm_active(), "sakelar": _switch["on"], "tersedia": llm_enabled() and llm_reachable(), "model": MODEL}
