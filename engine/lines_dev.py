import json
from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.figure import Figure

from engine import ai1 as A
from engine import line_config as LC
from engine import lines as L
from engine.data import DEV, load_world

ROOT = Path(__file__).resolve().parents[2] / "tapal-percobaan"
OUT = ROOT / "garis-dev"


def population(c: pd.DataFrame) -> np.ndarray:
    return A.eligible_prolonged(c) & (c.ventilator_hour > 0).to_numpy()


def table(c: pd.DataFrame, rng: np.random.Generator, mask: np.ndarray | None = None) -> list[dict]:
    pop = population(c) & (np.ones(len(c), bool) if mask is None else mask)
    t = L.asymmetry_table(c.ventilator_hour.to_numpy()[pop].astype(float), c.kode_rs.to_numpy()[pop], rng,
                          tariff_lines=LC.active_hour_lines(LC.load()))
    return t.round(3).to_dict("records")


def chart(rows: list[dict], path: Path) -> None:
    fig = Figure(figsize=(6.5, 4))
    ax = fig.subplots()
    ax.axhline(0, color="#C9C7C3", lw=1)
    for r in rows:
        color = "#2A78D6" if r["garis_tarif"] else "#898781"
        ax.errorbar(r["garis"], r["S"], yerr=[[r["S"] - r["bawah"]], [r["atas"] - r["S"]]], fmt="o", ms=7, color=color, lw=2, capsize=0)
    ax.set_xticks([r["garis"] for r in rows], [f"{r['garis']} jam" + ("\n(plasebo)" if r["plasebo"] else "") for r in rows])
    ax.set_ylabel("Asimetri S(L), dikoreksi pola 24 jam")
    ax.set_title("Penumpukan jam ventilasi di tujuh kandidat garis, DEV", loc="left")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=160)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(0)
    w = load_world(DEV / "dasar", with_key=True)
    c, h, kh = w["claims"], w["hospitals"], w["key_hospitals"]
    pop = population(c)
    hours, rs = c.ventilator_hour.to_numpy()[pop].astype(float), c.kode_rs.to_numpy()[pop]
    cls = c.kode_rs.map(h.set_index("kode_rs").kelas_rs).to_numpy()
    report = {"dunia": "DEV dasar", "populasi": "klaim layak modus diperpanjang dengan jam tercatat > 0", "gabungan": table(c, rng)}
    report["per_kelas_rs"] = {k: table(c, rng, cls == k) for k in "ABCD"}
    placebo = [r for r in report["gabungan"] if r["plasebo"]]
    report["t3"] = {f"S({r['garis']})": [r["S"], r["bawah"], r["atas"]] for r in placebo}
    report["t3"]["lolos"] = all(r["bawah"] <= 0 <= r["atas"] for r in placebo)
    flagged = {x["rs"] for x in json.loads((ROOT / "ai1-dev" / "ai1_dev.json").read_text())["rs_ditandai"]["diperpanjang"]}
    report["t4"] = L.stacking_difference(hours, rs, flagged, rng) or {"catatan": "tidak dapat dihitung: 0 RS ditandai di modus diperpanjang"}
    report["kunci_dev_pelaku_diperpanjang_vs_lain"] = L.stacking_difference(hours, rs, set(kh.kode_rs[kh.modus == "diperpanjang"]), rng)
    report["kembaran_tanpa_fraud"] = table(w["key_placebo_claims"], rng)
    chart(report["gabungan"], OUT / "asimetri_garis_dev.png")
    (OUT / "garis_dev.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str))
    print(json.dumps({k: report[k] for k in ("t3", "t4", "kunci_dev_pelaku_diperpanjang_vs_lain")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
