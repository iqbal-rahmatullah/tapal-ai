import json
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / "config" / "garis.json"
STATUSES = ("aktif", "temuan", "rencana", "ditolak")


def line_id(line: dict) -> str:
    if line["jenis"] == "ambang":
        return f"ambang:{line['atribut']}:{line['ambang']}"
    return f"kode:{line['atribut']}:{line['kode']}"


def load(path: Path = CONFIG) -> list[dict]:
    lines = json.loads(path.read_text())["garis"]
    if bad := [x["id"] for x in lines if x["status"] not in STATUSES]:
        raise ValueError(f"unknown line status in {bad}")
    return lines


def save(lines: list[dict], path: Path = CONFIG) -> None:
    path.write_text(json.dumps({"versi": 1, "garis": lines}, ensure_ascii=False, indent=1))


def active_hour_lines(lines: list[dict]) -> tuple[int, ...]:
    return tuple(sorted(x["ambang"] for x in lines if x["status"] == "aktif" and x["jenis"] == "ambang" and x["atribut"] == "jam_ventilasi"))


def add_found(lines: list[dict], found: list[dict]) -> list[dict]:
    # Lines found by AI 4 wait as "temuan" until an admin approves them; known lines keep their status.
    known = {x["id"] for x in lines}
    fresh = [{**x, "id": line_id(x), "status": "temuan", "sumber": "AI 4"} for x in found if line_id(x) not in known]
    return lines + fresh


def set_status(lines: list[dict], line: str, status: str) -> list[dict]:
    if status not in STATUSES or line not in {x["id"] for x in lines}:
        raise ValueError(f"cannot set {line} to {status}")
    return [{**x, "status": status} if x["id"] == line else x for x in lines]
