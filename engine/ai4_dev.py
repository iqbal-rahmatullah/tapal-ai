import json
from pathlib import Path

import numpy as np
import pandas as pd

from engine import ai1 as A
from engine import ai1_dev as D
from engine import ai4 as F4
from engine import lines as L
from engine import stats as S
from engine.data import DEV, load_world

OUT = Path(__file__).resolve().parents[2] / "tapal-percobaan" / "ai4-dev"
# What each embedded second line adds (engine.synth.fraud); used only to score T19/T20 against the open DEV key.
SECOND_LINE_CODE = {"akses_dialisis_fiktif": "38.95", "dx_sekunder_fiktif": "N17", "wsd_fiktif": "34.04"}


def code_test(c: pd.DataFrame, f: pd.DataFrame, sur: F4.Surrogate, X: pd.DataFrame, line: dict, rng: np.random.Generator) -> dict:
    # "Diakui vs wajar" per RS (TARGETS v2 bagian 6): the AI 1 machinery with the code itself as the label.
    sets = f.codes if line["atribut"] == "prosedur" else f.dx2
    y = sets.map(lambda s, k=line["kode"]: k in s).to_numpy().astype(int)
    col = ("px_" if line["atribut"] == "prosedur" else "dx2_") + line["kode"]
    Xc = X.drop(columns=[x for x in (col, "n_prosedur", "n_dx_sekunder") if x in X])
    everyone = np.ones(len(c), bool)
    n_layak = pd.Series(1, index=c.index).groupby(c.kode_rs).sum()
    run = A.run_mode(Xc, y, c.kode_rs, everyone, everyone, n_layak, fit=D.cross_fit)
    flagged = run.table.index[run.table.ditandai]
    d = pd.DataFrame({"rs": c.kode_rs.to_numpy(), "y": y.astype(float), "p": run.p, "delta": F4.toggle_delta(f, sur, line)})
    money = [S.counterfactual_rupiah(g, rng) for _, g in d[d.rs.isin(flagged)].groupby("rs")]
    return {"menyala": bool(len(flagged)), "rs_ditandai": sorted(flagged), "rupiah": round(sum(m.rupiah for m in money)),
            "rupiah_jumlah_rentang_per_rs": [round(sum(m.rupiah_bawah for m in money)), round(sum(m.rupiah_atas for m in money))]}


def threshold_test(c: pd.DataFrame, line: dict, delta: float, rng: np.random.Generator) -> dict:
    if line["atribut"] != "jam_ventilasi":
        return {"menyala": False, "catatan": "TARGETS hanya menetapkan uji asimetri untuk jam ventilasi"}
    pop = A.eligible_prolonged(c) & (c.ventilator_hour > 0).to_numpy()
    hours, rs, cut = c.ventilator_hour.to_numpy()[pop].astype(float), c.kode_rs.to_numpy()[pop], line["ambang"]
    t = L.asymmetry_table(hours, rs, rng, lines=(cut,), tariff_lines=(cut,)).iloc[0]
    comps = L.comparators(cut, (cut,))
    # Natural log ratios differ between 24-hour lines (DEV twin: +0.14 at 96 h without fraud), so the range adds that spread to RS resampling.
    spread = float(np.std([L.log_ratio(hours, k) for k in range(cut + 24, 241, 24)], ddof=1) * np.sqrt(1 + 1 / len(comps)))

    def excess(h: np.ndarray, shift: float = 0.0) -> float:
        expected = np.count_nonzero((h >= cut - L.WIDTH) & (h < cut)) * np.exp(np.mean([L.log_ratio(h, k) for k in comps]) + shift)
        return np.count_nonzero((h >= cut) & (h < cut + L.WIDTH)) - expected

    boot = [max(excess(hours[pick], rng.normal(0, spread)), 0) * delta for pick in L._resample(rs, rng, S.B_BOOT)]
    low, high = np.percentile(boot, [2.5, 97.5])
    return {"menyala": bool(t.p_satu_sisi <= S.BH_Q), "S": round(float(t.S), 3), "rentang95": [round(float(t.bawah), 3), round(float(t.atas), 3)],
            "p_satu_sisi": round(float(t.p_satu_sisi), 4), "sebaran_alami_log_rasio": round(spread, 3),
            "kelebihan_klaim": round(float(excess(hours)), 1), "selisih_per_klaim": round(delta), "rupiah": round(max(excess(hours), 0) * delta),
            "rupiah_rentang95": [round(float(low)), round(float(high))], "rupiah_terukur": bool(low > 0)}


def run_world(name: str, evaluate: bool) -> dict:
    rng = np.random.default_rng(0)
    w = load_world(DEV / name, with_key=evaluate)
    c, h = w["claims"], w["hospitals"]
    f = F4.frame_from_claims(c, h)
    found = F4.find_lines(f, rng)
    sur = found.pop("surrogate")
    report = {"dunia": f"DEV {name}", **found}
    if not evaluate:
        return report
    X = A.features(A.evidence(c, h), A.fit_vocab(A.evidence(c, h)))
    for line in report["kode"]:
        line["uji"] = code_test(c, f, sur, X, line, rng)
        print(line["kode"], line["uji"]["menyala"], len(line["uji"]["rs_ditandai"]), flush=True)
    for line in report["ambang"]:
        delta = F4.threshold_delta(f, line)
        above = (c.ventilator_hour >= line["ambang"]).to_numpy() & (c.ventilator_hour < line["ambang"] + L.WIDTH).to_numpy() & (delta > 0)
        line["uji"] = threshold_test(c, line, float(delta[above].mean()) if above.any() else 0.0, rng)
    lit = [x for x in report["ambang"] + report["kode"] if x["uji"]["menyala"]]
    report["urutan_rupiah"] = [{"garis": x.get("kode") or f"{x['atribut']} {x['ambang']}", "rupiah": x["uji"]["rupiah"],
                                "rentang95": x["uji"].get("rupiah_rentang95") or x["uji"].get("rupiah_jumlah_rentang_per_rs"),
                                "terukur": x["uji"].get("rupiah_terukur", True)}
                               for x in sorted(lit, key=lambda x: (not x["uji"].get("rupiah_terukur", True), -x["uji"]["rupiah"]))]
    kw = json.loads((DEV / name / "key" / "key_world.json").read_text())
    manipulated = {"96.71", "96.04", f"jam_ventilasi {kw['grouper']['garis_jam']}", SECOND_LINE_CODE[kw["garis_kedua"]]}
    names = {x.get("kode") or f"{x['atribut']} {x['ambang']}": x for x in report["ambang"] + report["kode"]}
    k = c[["nomor_sep"]].merge(w["key_claims"], on="nomor_sep", how="left")
    paid = k.selisih_rupiah.to_numpy() * k.dimanipulasi.fillna(False).to_numpy().astype(bool)
    # Embedded rupiah per manipulated line from the open DEV key, to check the estimates; a claim with two added codes counts for both.
    report["rupiah_perkiraan_vs_tertanam"] = {
        g: {"perkiraan": names[g]["uji"]["rupiah"] if g in names else None,
            "tertanam": round(float(paid[(k.modus == "diperpanjang").to_numpy()].sum() if g.startswith("jam_ventilasi")
                                    else paid[(f.codes.map(lambda s, g=g: g in s) | f.dx2.map(lambda s, g=g: g in s)).to_numpy()
                                              & ~k.modus.isin(["diperpanjang", "kelas_naik"]).to_numpy()].sum()))}
        for g in sorted(manipulated)}
    trach = any(x["kode"] in ("31.1", "31.21", "31.29") and x["grup_tujuan"].startswith("J-1-01") for x in report["kode"])
    report["t19"] = {"ditemukan": {k: k in names for k in sorted(manipulated)} | {"trakeostomi -> J-1-01": trach}}
    report["t19"]["lolos"] = all(report["t19"]["ditemukan"].values())
    report["t20"] = {"dimanipulasi_menyala": {k: bool(names.get(k, {}).get("uji", {}).get("menyala")) for k in sorted(manipulated)},
                     "tidak_dimanipulasi_menyala": sorted(k for k, x in names.items() if k not in manipulated and x["uji"]["menyala"])}
    report["t20"]["lolos"] = all(report["t20"]["dimanipulasi_menyala"].values()) and len(report["t20"]["tidak_dimanipulasi_menyala"]) <= 1
    return report


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    idrg = run_world("idrg_tiruan", evaluate=False)
    lines = {x.get("kode") or f"{x['atribut']} {x['ambang']}" for x in idrg["ambang"] + idrg["kode"]}
    idrg["t21"] = {"ambang jam_ventilasi 72": "jam_ventilasi 72" in lines, "kode 93.90": "93.90" in lines, "tanpa garis 96 jam": "jam_ventilasi 96" not in lines}
    idrg["t21"]["lolos"] = all(idrg["t21"].values())
    (OUT / "ai4_idrg.json").write_text(json.dumps(idrg, ensure_ascii=False, indent=1, default=str))
    print("T21", idrg["t21"], flush=True)
    report = run_world("dasar", evaluate=True)
    (OUT / "ai4_dev.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str))
    print("T19", report["t19"], "\nT20", report["t20"])


if __name__ == "__main__":
    main()
