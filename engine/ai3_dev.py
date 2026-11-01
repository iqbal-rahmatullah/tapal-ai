import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from engine import ai1 as A1
from engine import ai3 as A
from engine.ai1_dev import honest_hospitals
from engine import stats as S
from engine.contracts import split_codes
from engine.data import DEV, load_world

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT.parent / "tapal-percobaan" / "ai3-dev"
AI2 = OUT.parent / "ai2-dev"
POLICIES = ["agen", "statis_gabungan", "statis_ai1", "aturan", "acak"]
Z95 = 1.959964


def build_tables(pop: pd.DataFrame, h: pd.DataFrame, score: pd.DataFrame, kw_verdict: pd.Series, kw_hours: pd.Series, sheet: pd.Series,
                 clone: pd.Series, one_session: pd.Series, assertion: pd.Series, key: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    # Features never read the key; the oracle holds what an audit would find, used only as the simulated audit result.
    seps = pop.nomor_sep
    billed = pop.procedure.map(lambda x: bool(set(split_codes(x)) & {"96.04", "96.70", "96.71", "96.72"})).to_numpy()
    claimed = pop.ventilator_hour.to_numpy(float)
    text_h = np.nan_to_num(kw_hours.reindex(seps).to_numpy(float), nan=0.0)
    sheet_h = sheet.reindex(seps).to_numpy(float)
    f = pd.DataFrame({
        "nomor_sep": seps, "bulan": pop.bulan.to_numpy(), "kode_rs": pop.kode_rs.to_numpy(),
        "kelas_rs": h.set_index("kode_rs").kelas_rs.reindex(pop.kode_rs).to_numpy(),
        "p_fiktif": score.p_fiktif.reindex(seps).to_numpy(), "p_panjang": score.p_panjang.reindex(seps).to_numpy(),
        "kata_kunci": kw_verdict.reindex(seps).eq("tidak_mendukung").to_numpy(),
        "asersi": billed & assertion.reindex(seps).eq("tidak").to_numpy(),
        "klaim_vs_lembar": (claimed >= 12) & (sheet_h < 0.2 * claimed),
        "teks_vs_lembar": (text_h >= 12) & (sheet_h < 0.2 * text_h),
        "kloning_kuat": clone.reindex(seps).fillna(False).astype(bool).to_numpy(),
        "tulis_serentak": one_session.reindex(seps).fillna(False).astype(bool).to_numpy(),
        "dipertaruhkan": A1.tariff_deltas(pop, h, "fiktif", np.ones(len(pop), bool)),
        "skor_poin": S.point_score_rules(pop).sum(axis=1).to_numpy(),
    })
    kk = key.loc[seps]
    kh = load_world(DEV / "dasar", with_key=True)["key_hospitals"]
    honest_rs = kh.kode_rs[honest_hospitals(kh)]
    # The hidden mode is read from the world record, so no candidate name is written into the engine (TARGETS bagian 3).
    hidden = json.loads((DEV / "dasar" / "key" / "key_world.json").read_text())["modus_tersembunyi"]
    o = pd.DataFrame({"nomor_sep": seps, "temuan": kk.dimanipulasi.to_numpy().astype(int),
                      "rupiah": np.where(kk.dimanipulasi, kk.selisih_rupiah, 0.0), "tersembunyi": kk.modus.eq(hidden).to_numpy(),
                      "rs_jujur": pop.kode_rs.isin(honest_rs).to_numpy()})
    return f, o


def world() -> tuple[pd.DataFrame, pd.DataFrame]:
    path_f, path_o = OUT / "fitur_dev.parquet", OUT / "oracle_dev.parquet"
    if path_f.exists() and path_o.exists():
        return pd.read_parquet(path_f), pd.read_parquet(path_o)
    OUT.mkdir(parents=True, exist_ok=True)
    w = load_world(DEV / "dasar", with_key=True)
    c, h, k = w["claims"], w["hospitals"], w["key_claims"].set_index("nomor_sep")
    pop = c[c.nomor_sep.isin(k.index[k.populasi_garis.fillna(False)])].reset_index(drop=True)
    kw = pd.read_parquet(AI2 / "kata_kunci_per_klaim.parquet")
    fast = pd.read_parquet(AI2 / "lapis_cepat_per_klaim.parquet")
    f, o = build_tables(pop, h, pd.read_parquet(OUT.parent / "ai1-dev" / "skor_luar_lipatan_dev.parquet").set_index("nomor_sep"), kw.verdict, kw.jam,
                        pd.read_parquet(AI2 / "fisiologi_per_klaim.parquet").lembar, fast.kloning_kuat, fast.tulis_serentak,
                        pd.read_parquet(AI2 / "asersi_per_klaim_embedding_embedding_ngram.parquet").ventilasi, k)
    f.to_parquet(path_f)
    o.to_parquet(path_o)
    return f, o


def _top(value: np.ndarray, rng: np.random.Generator, k: int = A.CAPACITY) -> np.ndarray:
    # Ties are broken at random so a coarse score such as rule points does not always pick the same claims.
    return np.lexsort((rng.random(len(value)), -value))[:k]


def _month(worlds: dict, home: dict, month: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    # Each hospital's claims come from the world it lives in: the base world, or its adapted variant once caught.
    parts = []
    for name, (f, o) in worlds.items():
        here = ~f.kode_rs.isin(list(home)) if name == "dasar" else f.kode_rs.isin([rs for rs, w in home.items() if w == name])
        rows = np.flatnonzero((f.bulan.to_numpy() == month) & here.to_numpy())
        if len(rows):
            parts.append((f.iloc[rows], o.iloc[rows]))
    return pd.concat([p[0] for p in parts]), pd.concat([p[1] for p in parts])


def run_once(worlds: dict, policy: str, rng: np.random.Generator, calibrate: bool = False, mix: float = 0.0,
             roles: pd.DataFrame | None = None, trace: bool = False) -> list[dict]:
    from engine import ai3_worlds as V
    audited_rows, audited = [], pd.DataFrame({"kode_rs": pd.Series(dtype=str), "temuan": pd.Series(dtype=int)})
    home, adapted, records = {}, {}, []
    for month in range(1, A.MONTHS + 1):
        fm, om = _month(worlds, home, month)
        stake = fm.dipertaruhkan.to_numpy()
        pi, predicted, why, calib, spread = None, None, None, {}, None
        if policy in ("agen", "agen_peluang"):
            X = A.design(fm, A.rs_history(fm.kode_rs, audited))
            model = None
            if audited_rows:
                train = pd.concat(audited_rows)
                model = A.OutcomeModel.fit(train[A.FEATURES], train.temuan.to_numpy(), train.pi.to_numpy(), rng)
            p, sd = model.predict(X) if model else (A.static_probability(fm), np.zeros(len(fm)))
            if calibrate and model is not None:
                plain = A.OutcomeModel.fit(train[A.FEATURES], train.temuan.to_numpy(), np.ones(len(train)), rng, cap=None)
                calib = {"rerata_prediksi_berbobot": float(p.mean()), "rerata_prediksi_tanpa_bobot": float(plain.predict(X)[0].mean()),
                         "laju_sebenarnya": float(om.temuan.mean())}
            value, bonus = p * stake, A.EXPLORE * sd * stake
            # Ordering basis is a policy choice (TARGETS bagian 8): expected rupiah by default, or the chance of a finding alone.
            order, order_bonus = (p, A.EXPLORE * sd) if policy == "agen_peluang" else (value, bonus)
            pi = (1 - mix) * A.inclusion(order + order_bonus) + mix * A.CAPACITY / len(fm)
            picked = A.systematic(pi, rng)
            predicted, why, spread = value, A.reasons(order, order_bonus, pi, picked), p * (1 - p) * stake ** 2
            audited_rows.append(X.iloc[picked].assign(temuan=om.temuan.to_numpy()[picked], pi=pi[picked]))
        elif policy == "acak":
            pi = np.full(len(fm), A.CAPACITY / len(fm))
            picked, predicted = A.systematic(pi, rng), np.zeros(len(fm))
        else:
            value = {"statis_gabungan": A.static_probability(fm) * stake, "statis_ai1": A.doubt(fm) * stake,
                     "aturan": fm.skor_poin.to_numpy(float)}[policy]
            picked = _top(value, rng)
        found, hit = om.rupiah.to_numpy()[picked], om.temuan.to_numpy()[picked]
        audited = pd.concat([audited, pd.DataFrame({"kode_rs": fm.kode_rs.to_numpy()[picked], "temuan": hit})])
        caught = sorted(set(fm.kode_rs.to_numpy()[picked][hit == 1]))
        for rs in caught:
            if rs in adapted and adapted[rs]["tertangkap_lagi"] is None and month > adapted[rs]["bulan"]:
                adapted[rs]["tertangkap_lagi"] = month
        if roles is not None:
            # A hospital adapts once, from the month after its first caught audit, following the generator's adapt() branches.
            for rs in caught:
                if rs not in home and rs in roles.index and (kind := V.outcome(roles.loc[rs], rng.random())) in worlds:
                    home[rs] = kind
                    adapted[rs] = {"bulan": month, "hasil": kind, "tertangkap_lagi": None}
        rec = {"bulan": month, "rupiah": float(found.sum()), "temuan": int(hit.sum()), "tersembunyi": int(om.tersembunyi.to_numpy()[picked].sum()),
               "klaim_rs_jujur": int(om.rs_jujur.to_numpy()[picked].sum()), "rs_diaudit": sorted(set(fm.kode_rs.to_numpy()[picked])),
               "kebocoran_sebenarnya": float(om.rupiah.sum()), **calib}
        if why is not None:
            rec["porsi_eksplorasi"] = float(np.mean([r == A.EXPLORE_REASON for r in why]))
            rec["pi_lantai_audit"] = float(A.PI_MIN * len(fm))
        if pi is not None:
            rec |= A.estimate(predicted, picked, found, pi, spread)
        if trace:
            rec["daftar"] = pd.DataFrame({"nomor_sep": fm.nomor_sep.to_numpy()[picked], "kode_rs": fm.kode_rs.to_numpy()[picked],
                                          "alasan": why or [""] * len(picked), "pi": pi[picked] if pi is not None else np.nan,
                                          "dipertaruhkan": stake[picked], "temuan": hit, "rupiah": found}).to_dict(orient="records")
        records.append(rec)
    if roles is not None:
        records[-1]["adaptasi"] = adapted
    return records


def _coverage(est: np.ndarray, var: np.ndarray, truth: np.ndarray) -> dict:
    half = Z95 * np.sqrt(np.maximum(var, 0))
    return {"periode": f"setahun ({A.MONTHS} bulan)", "rerata": float(est.mean()), "bias_relatif": float(est.mean() / truth.mean() - 1),
            "cakupan_95": float(np.mean((est - half <= truth) & (truth <= est + half))), "lebar_rerata": float(np.mean(2 * half)),
            "lebar_dibanding_total_ditanam": float(np.mean(2 * half) / truth.mean())}


def summarise(runs: dict[str, list[list[dict]]]) -> dict:
    kh = load_world(DEV / "dasar", with_key=True)["key_hospitals"].set_index("kode_rs")
    honest = set(kh.index[honest_hospitals(kh.reset_index()).to_numpy()])
    out = {"kapasitas": A.CAPACITY, "ulangan": {p: len(r) for p, r in runs.items()}}
    for policy, reps in runs.items():
        truth = np.array([sum(m["kebocoran_sebenarnya"] for m in r) for r in reps])
        total = np.array([sum(m["rupiah"] for m in r) for r in reps])
        hidden_month = [next((m["bulan"] for m, cum in zip(r, np.cumsum([m["tersembunyi"] for m in r])) if cum >= 3), None) for r in reps]
        honest_rs = [len(set().union(*[set(m["rs_diaudit"]) for m in r]) & honest) for r in reps]
        s = {"kebocoran_setahun_sebenarnya_rerata": float(truth.mean()), "rupiah_setahun_rerata": float(total.mean()),
             "porsi_kebocoran_ditemukan": float((total / truth).mean()),
             "rupiah_per_100_audit": float(total.mean() / (A.CAPACITY * A.MONTHS) * 100),
             "kurva_rupiah_per_bulan": [float(np.mean([r[i]["rupiah"] for r in reps])) for i in range(A.MONTHS)],
             "bulan_modus_tersembunyi_median": float(np.median([m if m else 13 for m in hidden_month])),
             "porsi_ulangan_modus_tersembunyi_sampai_bulan_6": float(np.mean([bool(m) and m <= 6 for m in hidden_month])),
             "rs_jujur_diaudit_rerata": float(np.mean(honest_rs)),
             "klaim_rs_jujur_per_100_audit": float(np.mean([sum(m["klaim_rs_jujur"] for m in r) for r in reps]) / (A.CAPACITY * A.MONTHS) * 100)}
        if "ppi" in reps[0][0]:
            def year(key: str) -> np.ndarray:
                return np.array([sum(m[key] for m in r) for r in reps])
            if "var_ppi_model" in reps[0][0]:
                official = np.array([A.official_variance(d, m) for d, m in zip(year("var_ppi"), year("var_ppi_model"))])
                s["ppi_resmi"] = _coverage(year("ppi"), official, truth)
            s["ppi_varians_desain"] = _coverage(year("ppi"), year("var_ppi"), truth)
            s["ht"] = _coverage(year("ht"), year("var_ht"), truth)
            monthly = [(m["kebocoran_sebenarnya"], m["ppi"], m["var_ppi"]) for r in reps for m in r]
            s["cakupan_95_per_bulan_ppi"] = float(np.mean([abs(e - t) <= Z95 * np.sqrt(v) for t, e, v in monthly]))
        if policy.startswith("agen"):
            s["porsi_eksplorasi_rerata"] = float(np.mean([m["porsi_eksplorasi"] for r in reps for m in r]))
            s["audit_dari_lantai_pi"] = float(np.mean([m["pi_lantai_audit"] for r in reps for m in r]))
            cal = [m for r in reps for m in r if "laju_sebenarnya" in m]
            if cal:
                s["kalibrasi"] = {k: float(np.mean([m[k] for m in cal])) for k in
                                  ("rerata_prediksi_berbobot", "rerata_prediksi_tanpa_bobot", "laju_sebenarnya")}
        events = [e for r in reps for e in r[-1].get("adaptasi", {}).values()]
        if events:
            gaps = [e["tertangkap_lagi"] - e["bulan"] for e in events if e["tertangkap_lagi"]]
            s["adaptasi"] = {"rs_beradaptasi_per_ulangan": len(events) / len(reps),
                             "hasil": pd.Series([e["hasil"] for e in events]).value_counts(normalize=True).round(3).to_dict(),
                             "porsi_tertangkap_lagi": len(gaps) / len(events),
                             "bulan_sampai_tertangkap_lagi_median": float(np.median(gaps)) if gaps else None}
        out[policy] = s
    if "statis_gabungan" in out:
        out["t16_agen_dibanding_statis_gabungan"] = out["agen"]["rupiah_setahun_rerata"] / out["statis_gabungan"]["rupiah_setahun_rerata"]
    return out


def ordering(reps: int = 200) -> dict:
    from engine import ai3_worlds as V
    worlds = {"dasar": world(), **{kind: V.variant(kind) for kind in V.OUTCOMES}}
    roles = load_world(DEV / "dasar", with_key=True)["key_hospitals"].set_index("kode_rs")
    runs = {p: [run_once(worlds, p, np.random.default_rng([r, 0]), roles=roles) for r in range(reps)] for p in ("agen", "agen_peluang")}
    keep = ("rupiah_setahun_rerata", "porsi_kebocoran_ditemukan", "klaim_rs_jujur_per_100_audit", "rs_jujur_diaudit_rerata",
            "bulan_modus_tersembunyi_median", "ppi_resmi")
    report = {p: {k: v for k, v in s.items() if k in keep} for p, s in summarise(runs).items() if p in runs}
    (OUT / "dasar_urutan_laporan.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    return report


def honest_ai1(f: pd.DataFrame, kind: str) -> pd.DataFrame:
    s = pd.read_parquet(OUT / f"skor_ai1_jujur_{kind}.parquet").set_index("nomor_sep")
    return f.assign(p_fiktif=s.p_fiktif.reindex(f.nomor_sep).to_numpy(), p_panjang=s.p_panjang.reindex(f.nomor_sep).to_numpy())


def burden(reps: int = 100) -> dict:
    # How often an honest hospital is audited in a year, and why: the question "has almost every honest RS been audited?".
    from engine import ai3_worlds as V
    worlds = {"dasar": world(), **{kind: V.variant(kind) for kind in V.OUTCOMES}}
    kh = load_world(DEV / "dasar", with_key=True)["key_hospitals"]
    honest = set(kh.kode_rs[honest_hospitals(kh)])
    roles = kh.set_index("kode_rs")
    out = {"rs_jujur": len(honest), "ulangan": reps}
    for policy in ("agen", "statis_gabungan", "acak"):
        rows = []
        for r in range(reps):
            picks = pd.concat([pd.DataFrame(m["daftar"]) for m in run_once(worlds, policy, np.random.default_rng([r, POLICIES.index(policy)]),
                                                                          roles=roles, trace=True)])
            mine = picks[picks.kode_rs.isin(honest)]
            per_rs = mine.groupby("kode_rs").size().reindex(sorted(honest), fill_value=0)
            rows.append({"tersentuh": int((per_rs > 0).sum()), "audit_rerata_per_rs": float(per_rs.mean()),
                         "audit_maks_per_rs": int(per_rs.max()), "rs_diaudit_3_kali_atau_lebih": int((per_rs >= 3).sum()),
                         "porsi_eksplorasi": float((mine.alasan == A.EXPLORE_REASON).mean()) if len(mine) else 0.0,
                         "audit_di_rs_jujur_per_100": float(len(mine) / len(picks) * 100),
                         "audit_rs_jujur_per_rs_tersentuh": float(per_rs[per_rs > 0].mean()) if (per_rs > 0).any() else 0.0})
        out[policy] = {k: round(float(np.mean([x[k] for x in rows])), 2) for k in rows[0]}
    (OUT / "beban_rs_jujur.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    return out


def simulate(reps: int = A.N_REPEAT, adapt: bool = False, calibration_reps: int = 50, ai1: str = "lengkap",
             policies: tuple = tuple(POLICIES)) -> dict:
    worlds = {"dasar": world()}
    roles = None
    if adapt:
        from engine import ai3_worlds as V
        worlds |= {kind: V.variant(kind) for kind in V.OUTCOMES}
        roles = load_world(DEV / "dasar", with_key=True)["key_hospitals"].set_index("kode_rs")
    if ai1 == "jujur":
        worlds = {name: (honest_ai1(f, "dev" if name == "dasar" else name), o) for name, (f, o) in worlds.items()}
    runs = {p: [] for p in policies}
    started = time.time()
    for r in range(reps):
        for p in policies:
            if p in ("statis_gabungan", "statis_ai1", "aturan") and r >= 50:
                continue
            runs[p].append(run_once(worlds, p, np.random.default_rng([r, POLICIES.index(p)]), calibrate=p == "agen" and r < calibration_reps,
                                    roles=roles))
        if r % 25 == 0:
            print(f"ulangan {r}/{reps} · {time.time() - started:.0f} dtk", flush=True)
    report = summarise(runs)
    name = ("simulasi_adaptasi" if adapt else "simulasi") + ("_ai1_jujur" if ai1 == "jujur" else "") + "_laporan.json"
    (OUT / name).write_text(json.dumps(report, ensure_ascii=False, indent=1))
    return report


if __name__ == "__main__":
    if sys.argv[1:2] == ["beban"]:
        print(json.dumps(burden(), ensure_ascii=False, indent=1))
        sys.exit()
    if sys.argv[1:2] == ["urutan"]:
        print(json.dumps(ordering(), ensure_ascii=False, indent=1))
        sys.exit()
    args = [a for a in sys.argv[1:] if a not in ("adaptasi", "ai1_jujur")]
    print(json.dumps(simulate(int(args[0]) if args else A.N_REPEAT, adapt="adaptasi" in sys.argv, ai1="jujur" if "ai1_jujur" in sys.argv else "lengkap"),
                     ensure_ascii=False, indent=1))
