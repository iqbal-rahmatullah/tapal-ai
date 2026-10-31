# Data Sampel never leaves this laptop: only national aggregates are written and no hospital is assessed (pakta integritas).
import json
from pathlib import Path

import numpy as np
import pandas as pd

from engine import ai4 as F4
from engine import reality as R
from engine.contracts import TRIGGER_CODES

OUT = Path(__file__).resolve().parents[2] / "tapal-percobaan" / "ai4-kenyataan"
# T24 routes known from the 31 Okt 2026 research (uji kenyataan, not a blind test).
T24 = {"96.71": "J-1-20", "96.72": "J-1-02", "96.04": "J-1-20", "trakeostomi": "J-1-01"}
TRACH = ("31.1", "31.21", "31.29")
VENT = {"96.70", "96.71", "96.72"}


def frame(ri: pd.DataFrame) -> pd.DataFrame:
    tipe = ri.FKL09.astype(str)
    letter = tipe.str.extract(r"(?:Kelas|Type) ([ABCD])$")[0].where(tipe.str.match(r"RS (Kelas|Swasta)"))
    private = tipe.str.startswith("RS Swasta") | ri.FKL07.astype(str).isin(["Swasta", "BUMN"])
    return pd.DataFrame({
        "codes": ri.codes, "dx1": ri.FKL17A.astype(str).str[:3],
        "dx2": ri.dx.map(lambda d: frozenset(x.replace(".", "")[:3] for x in d[1:])), "jam_ventilasi": np.nan,
        "lama_rawat": (ri.FKL04 - ri.FKL03).dt.days.astype(float), "umur": ri.umur_hari / 365.25, "grup": ri.grup,
        "sev": pd.to_numeric(ri.FKL23.astype(str).str.extract(r"keparahan (\d)")[0], errors="coerce"),
        "regional": ri.FKL31.astype(str).str[-1], "kelas_rs": letter, "kepemilikan": np.where(private, "swasta", "pemerintah"),
        "kelas_rawat": pd.to_numeric(ri.FKL13.astype(str).str[-1], errors="coerce"),
    })


def t24(lines: list[dict]) -> dict:
    codes = {x["kode"]: x for x in lines}
    found = {k: codes.get(k, {}).get("grup_tujuan", "").startswith(g) for k, g in T24.items() if k != "trakeostomi"}
    found["trakeostomi"] = any(k in TRACH and x["grup_tujuan"].startswith(T24["trakeostomi"]) for k, x in codes.items())
    return found


def route_claims(f: pd.DataFrame) -> dict:
    # Claims on each known route in this set, to judge whether the set can show the route at all.
    has = lambda k: f.codes.map(lambda c: k in c)
    vent, trach = f.codes.map(lambda c: bool(c & VENT)), f.codes.map(lambda c: bool(c & set(TRACH)))
    return {"96.71": int((has("96.71") & (f.grup == "J-1-20")).sum()), "96.72": int((has("96.72") & (f.grup == "J-1-02")).sum()),
            "96.04": int((has("96.04") & ~vent & (f.grup == "J-1-20")).sum()), "trakeostomi": int((trach & (f.grup == "J-1-01")).sum())}


def scan(data_dir: Path) -> dict:
    ri = R.load(data_dir)
    severity = pd.read_stata(next(data_dir.glob("*fkrtl.dta")), columns=["FKL02", "FKL23"]).drop_duplicates("FKL02")
    ri = ri.merge(severity, on="FKL02", how="left")
    f = frame(ri)
    keep = (ri.umur_hari > 28).to_numpy() & f.sev.between(1, 3).to_numpy() & f.kelas_rs.notna().to_numpy() & f.kelas_rawat.between(1, 3).to_numpy()
    f = f[keep].astype({"sev": int, "kelas_rawat": int})
    found = F4.find_lines(f, np.random.default_rng(0), min_leaf=50)
    found.pop("surrogate")
    lines = found["kode"] + found["kode_setara_ambang"]
    routes = route_claims(f)
    enough = {k: v >= F4.MIN_AFFECTED for k, v in routes.items()}
    before, after = t24([x for x in lines if x.get("sumber") == "pohon"]), t24(lines)
    return {"n_klaim": int(len(f)), **found, "klaim_per_jalur": routes, "jalur_cukup_klaim": enough,
            "t24_pohon_saja": {"jalur": before, "lolos": all(before.values())},
            "t24": {"jalur": after, "lolos": all(after.values()), "lolos_di_jalur_cukup_klaim": all(after[k] for k in after if enough[k])},
            "kandidat_kode": {s: sum(x.get("sumber") == s for x in found["kode"]) for s in ("pohon", "kontras langsung")},
            "kode_pemicu_lain_ke_grup_ventilasi": sorted(x["kode"] for x in lines if x["grup_tujuan"][:6] in ("J-1-20", "J-1-02", "J-1-01")
                                                         and x["kode"] not in TRIGGER_CODES)}


def main() -> None:
    out = {"sumber": "Data Sampel Reguler dan DM Edisi 2025, rawat inap bukan bayi; dihitung lokal, hanya agregat nasional",
           "reguler": scan(R.REGULER), "dm": scan(R.DM)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "hasil.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    print(json.dumps({k: {kk: out[k][kk] for kk in ("n_klaim", "akurasi_model_pengganti", "klaim_per_jalur", "t24_pohon_saja", "t24", "kandidat_kode")}
                      for k in ("reguler", "dm")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
