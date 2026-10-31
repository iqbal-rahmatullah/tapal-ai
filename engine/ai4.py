from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import false_discovery_control, poisson
from sklearn.tree import DecisionTreeClassifier

from engine.ai1 import _multi_hot
from engine.contracts import split_codes
from engine.stats import BH_Q
from engine.synth import grouper as G

# TARGETS v2 bagian 5 (LOMPATAN_MIN); the tariff table is the public Permenkes 3/2023 one shared with the generator.
JUMP = 1.2
MIN_CLAIMS = 30
MIN_AFFECTED = 10
GRIDS = {"jam_ventilasi": np.arange(1, 241), "lama_rawat": np.arange(1, 61), "umur": np.arange(1, 101)}
ROMAN = {1: "I", 2: "II", 3: "III"}


def frame_from_claims(c: pd.DataFrame, h: pd.DataFrame) -> pd.DataFrame:
    hosp = h.set_index("kode_rs")
    dx = c.diagnosa.map(split_codes)
    days = (pd.to_datetime(c.tgl_pulang).dt.normalize() - pd.to_datetime(c.tgl_masuk).dt.normalize()).dt.days
    return pd.DataFrame({
        "kode_rs": c.kode_rs, "codes": c.procedure.map(lambda s: frozenset(split_codes(s))), "dx1": dx.map(lambda d: d[0][:3]),
        "dx2": dx.map(lambda d: frozenset(x[:3] for x in d[1:])), "jam_ventilasi": c.ventilator_hour.astype(float),
        "lama_rawat": days.astype(float), "umur": c.umur.astype(float), "grup": c.cbg.str[:6],
        "sev": c.cbg.str.split("-").str[-1].map({"I": 1, "II": 2, "III": 3}), "regional": c.kode_rs.map(hosp.regional).astype(str),
        "kelas_rs": c.kode_rs.map(hosp.kelas_rs), "kepemilikan": c.kode_rs.map(hosp.kepemilikan), "kelas_rawat": c.kelas_rawat.astype(int),
    }, index=c.index)


@dataclass
class Design:
    codes: list
    dx2: list
    dx1: list
    numeric: list


@dataclass
class Surrogate:
    design: Design
    group: DecisionTreeClassifier
    severity: DecisionTreeClassifier
    accuracy: dict


def fit_design(f: pd.DataFrame) -> Design:
    codes, dx2, dx1 = f.codes.explode().value_counts(), f.dx2.explode().value_counts(), f.dx1.value_counts()
    return Design(sorted(codes[codes >= MIN_CLAIMS].index), sorted(dx2[dx2 >= MIN_CLAIMS].index),
                  sorted(dx1[dx1 >= MIN_CLAIMS].index), [a for a in GRIDS if a in f and f[a].notna().any()])


def matrix(f: pd.DataFrame, d: Design) -> pd.DataFrame:
    dx1 = pd.get_dummies(pd.Categorical(f.dx1, categories=d.dx1)).set_index(f.index).add_prefix("dx1_")
    return pd.concat([_multi_hot(f.codes, d.codes, "px_"), _multi_hot(f.dx2, d.dx2, "dx2_"), dx1, f[d.numeric].fillna(-1)],
                     axis=1).astype(np.float32)


def fit_surrogate(f: pd.DataFrame, X: pd.DataFrame, d: Design, min_leaf: int = 20, seed: int = 0) -> Surrogate:
    tree = lambda y: DecisionTreeClassifier(min_samples_leaf=min_leaf, random_state=seed).fit(X, y)
    group, severity = tree(f.grup), tree(f.sev)
    accuracy = {"grup": round(float((group.predict(X) == f.grup).mean()), 4), "keparahan": round(float((severity.predict(X) == f.sev).mean()), 4)}
    return Surrogate(d, group, severity, accuracy)


def tariffs(f: pd.DataFrame, group: np.ndarray, sev: np.ndarray) -> np.ndarray:
    table = G.tariff_table()
    out = np.full(len(f), np.nan)
    for i, (reg, kls, own, g, s, kr) in enumerate(zip(f.regional, f.kelas_rs, f.kepemilikan, group, sev, f.kelas_rawat)):
        t = table.get((reg, f"KELAS {kls} {'PEMERINTAH' if own == 'pemerintah' else 'SWASTA'}", f"{g}-{ROMAN[int(s)]}"))
        if t:
            out[i] = t[int(kr) - 1]
    return out


def _cbg(group: np.ndarray, sev: np.ndarray) -> pd.Series:
    return pd.Series([f"{g}-{ROMAN[int(s)]}" for g, s in zip(group, sev)])


def code_lines(f: pd.DataFrame, sur: Surrogate, X: pd.DataFrame) -> list[dict]:
    g1, s1 = sur.group.predict(X), sur.severity.predict(X)
    t1 = tariffs(f, g1, s1)
    out = []
    for col in [c for c in X.columns if c.startswith(("px_", "dx2_"))]:
        rows = np.flatnonzero(X[col].to_numpy() == 1)
        Xo = X.iloc[rows].copy()
        Xo[col] = 0
        g0, s0 = sur.group.predict(Xo), sur.severity.predict(Xo)
        ratio = t1[rows] / tariffs(f.iloc[rows], g0, s0)
        hit = ratio >= JUMP
        if hit.sum() < MIN_AFFECTED:
            continue
        out.append({"jenis": "kode", "atribut": "prosedur" if col.startswith("px_") else "diagnosis_sekunder", "kode": col.split("_", 1)[1],
                    "n_klaim": len(rows), "n_terdampak": int(hit.sum()), "porsi_terdampak": round(float(hit.mean()), 3),
                    "kelipatan_median": round(float(np.median(ratio[hit])), 2),
                    "grup_asal": _cbg(g0[hit], s0[hit]).mode()[0], "grup_tujuan": _cbg(g1[rows][hit], s1[rows][hit]).mode()[0], "sumber": "pohon"})
    return out


def direct_code_lines(f: pd.DataFrame, sur: Surrogate, X: pd.DataFrame, known: set) -> list[dict]:
    # A route too rare for a tree leaf (96.04 alone, tracheostomy in Data Sampel) still shows as claims with the code paid above the
    # tree's no-code guess more often than claims without it in the same leaf (decision after T24, TARGETS riwayat baris 9).
    paid = tariffs(f, f.grup.to_numpy(), f.sev.to_numpy())
    ok = np.isfinite(paid)
    lifted0 = ok & (paid / tariffs(f, sur.group.predict(X), sur.severity.predict(X)) >= JUMP)
    leaf0, size = sur.group.apply(X), sur.group.tree_.node_count
    all_n, all_l = np.bincount(leaf0, weights=ok, minlength=size), np.bincount(leaf0, weights=lifted0, minlength=size)
    scanned = []
    for col in [c for c in X.columns if c.startswith(("px_", "dx2_")) and c.split("_", 1)[1] not in known]:
        rows = np.flatnonzero((X[col].to_numpy() == 1) & ok)
        Xo = X.iloc[rows].copy()
        Xo[col] = 0
        g0, s0, leaf = sur.group.predict(Xo), sur.severity.predict(Xo), sur.group.apply(Xo)
        ratio = paid[rows] / tariffs(f.iloc[rows], g0, s0)
        hit = ratio >= JUMP
        n = all_n - np.bincount(leaf0[rows], weights=ok[rows], minlength=size)
        k = all_l - np.bincount(leaf0[rows], weights=lifted0[rows], minlength=size)
        expected = float(np.where(n[leaf] > 0, k[leaf] / np.maximum(n[leaf], 1), lifted0.mean()).sum())
        observed = int(hit.sum())
        p = float(poisson.sf(observed, expected) + 0.5 * poisson.pmf(observed, expected)) if expected > 0 else float(observed == 0)
        line = None
        if observed - expected >= MIN_AFFECTED:
            line = {"jenis": "kode", "atribut": "prosedur" if col.startswith("px_") else "diagnosis_sekunder", "kode": col.split("_", 1)[1],
                    "n_klaim": len(rows), "n_terdampak": observed, "harapan_terdampak": round(expected, 1),
                    "porsi_terdampak": round(observed / len(rows), 3), "kelipatan_median": round(float(np.median(ratio[hit])), 2),
                    "grup_asal": _cbg(g0[hit], s0[hit]).mode()[0],
                    "grup_tujuan": _cbg(f.grup.to_numpy()[rows][hit], f.sev.to_numpy()[rows][hit]).mode()[0], "sumber": "kontras langsung"}
        scanned.append((p, line))
    if not scanned:
        return []
    q = false_discovery_control([p for p, _ in scanned], method="bh")
    return [line for (_, line), qq in zip(scanned, q) if line and qq <= BH_Q]


def threshold_lines(f: pd.DataFrame, sur: Surrogate, X: pd.DataFrame, rng: np.random.Generator, sample: int = 3000) -> list[dict]:
    out = []
    for a in sur.design.numeric:
        cand = np.flatnonzero(f[a].to_numpy() > 0)
        idx = rng.choice(cand, min(sample, len(cand)), replace=False)
        Xs, fs = X.iloc[idx].copy(), f.iloc[idx]
        prev = None
        for v in GRIDS[a]:
            Xs[a] = v
            g, s = sur.group.predict(Xs), sur.severity.predict(Xs)
            t = tariffs(fs, g, s)
            if prev is not None:
                hit = t / prev[0] >= JUMP
                if hit.sum() >= max(MIN_AFFECTED, 0.01 * len(idx)):
                    out.append({"jenis": "ambang", "atribut": a, "ambang": int(v), "lewat_kode": None, "n_terdampak_sampel": int(hit.sum()),
                                "porsi_sampel": round(float(hit.mean()), 3), "kelipatan_median": round(float(np.median((t / prev[0])[hit])), 2),
                                "grup_asal": _cbg(prev[1][hit], prev[2][hit]).mode()[0], "grup_tujuan": _cbg(g[hit], s[hit]).mode()[0]})
            prev = (t, g, s)
    return out


def code_thresholds(f: pd.DataFrame, codes: list[dict], numeric: list) -> list[dict]:
    # A trigger code that is present exactly when an attribute is high encodes a threshold line (96.72 for >=96 ventilation hours).
    out = []
    for line in codes:
        has = (f.codes if line["atribut"] == "prosedur" else f.dx2).map(lambda c, k=line["kode"]: k in c).to_numpy()
        for a in numeric:
            m = f[a].to_numpy() > 0
            if has[m].sum() < MIN_CLAIMS or (~has[m]).sum() < MIN_CLAIMS:
                continue
            stump = DecisionTreeClassifier(max_depth=1).fit(f.loc[m, [a]], has[m])
            if stump.tree_.node_count < 3:
                continue
            cut = float(stump.tree_.threshold[0])
            high = f[a].to_numpy()[m] > cut
            balanced = (has[m][high].mean() + (~has[m][~high]).mean()) / 2
            if balanced >= 0.95:
                out.append({"jenis": "ambang", "atribut": a, "ambang": int(np.ceil(f[a].to_numpy()[m][high & has[m]].min())), "lewat_kode": line["kode"],
                            "akurasi_seimbang": round(float(balanced), 3), "kelipatan_median": line["kelipatan_median"],
                            "grup_asal": line["grup_asal"], "grup_tujuan": line["grup_tujuan"]})
    return out


def _destination_follows(f: pd.DataFrame, t: dict) -> bool:
    # A coded threshold is a tariff line only if its destination group is (almost) absent below it; under iDRG J-1-02 starts at 72 hours.
    m = f[t["atribut"]].to_numpy() > 0
    a, to = f[t["atribut"]].to_numpy()[m], f.grup.to_numpy()[m] == t["grup_tujuan"][:6]
    return bool(to[a < t["ambang"]].mean() <= 0.1 * to[a >= t["ambang"]].mean())


def find_lines(f: pd.DataFrame, rng: np.random.Generator, min_leaf: int = 20) -> dict:
    d = fit_design(f)
    X = matrix(f, d)
    # Codes are read from a model that cannot see the numeric attributes, so a code twinned with an attribute keeps its effect.
    dc, Xc = Design(d.codes, d.dx2, d.dx1, []), X.drop(columns=d.numeric)
    sur_codes = fit_surrogate(f, Xc, dc, min_leaf)
    sur = fit_surrogate(f, X, d, min_leaf)
    codes = code_lines(f, sur_codes, Xc)
    codes += direct_code_lines(f, sur_codes, Xc, {c["kode"] for c in codes})
    ice = threshold_lines(f, sur, X, rng)
    equiv = code_thresholds(f, codes, d.numeric)
    kept = [_rebase(f, t) for t in equiv if _destination_follows(f, t)]
    explained = {t["lewat_kode"] for t in equiv} - {t["lewat_kode"] for t in kept}
    thresholds = {}
    for t in ice + kept:
        key = (t["atribut"], t["ambang"])
        if key not in thresholds or t["lewat_kode"]:
            thresholds[key] = t
    merged = {t["lewat_kode"] for t in thresholds.values() if t["lewat_kode"]}
    return {"akurasi_model_pengganti": {"kode": sur_codes.accuracy, "lengkap": sur.accuracy},
            "fitur": {"kode_prosedur": len(d.codes), "diagnosis_sekunder": len(d.dx2), "diagnosis_utama": len(d.dx1), "angka": d.numeric},
            "ambang": list(thresholds.values()), "kode": [c for c in codes if c["kode"] not in merged | explained],
            "kode_dijelaskan_ambang_lain": [c for c in codes if c["kode"] in explained],
            "kode_setara_ambang": [c for c in codes if c["kode"] in merged], "surrogate": sur_codes}


def _priced_against_below(f: pd.DataFrame, line: dict, width: int = 8):
    # A claim above a line is priced against the group most claims just below it have (J-1-20 under 96 hours), not against a code switched off.
    a, cut = f[line["atribut"]].to_numpy(), line["ambang"]
    below = (a >= cut - width) & (a < cut) & (a > 0)
    rows = np.flatnonzero((a >= cut) & (f.grup.to_numpy() == line["grup_tujuan"][:6]))
    if not below.any() or not len(rows):
        return None
    origin, sev = np.full(len(rows), f.grup[below].mode()[0]), f.sev.to_numpy()[rows]
    return rows, origin, sev, tariffs(f.iloc[rows], f.grup.to_numpy()[rows], sev), tariffs(f.iloc[rows], origin, sev)


def threshold_delta(f: pd.DataFrame, line: dict) -> np.ndarray:
    delta = np.zeros(len(f))
    priced = _priced_against_below(f, line)
    if priced:
        rows, _, _, above, below = priced
        delta[rows] = np.nan_to_num(above - below)
    return np.maximum(delta, 0)


def _rebase(f: pd.DataFrame, line: dict) -> dict:
    priced = _priced_against_below(f, line)
    if not priced:
        return line
    _, origin, sev, above, below = priced
    ratio = above / below
    return {**line, "grup_asal": _cbg(origin, sev).mode()[0], "kelipatan_median": round(float(np.nanmedian(ratio)), 2)}


def toggle_delta(f: pd.DataFrame, sur: Surrogate, line: dict) -> np.ndarray:
    X = matrix(f, sur.design)
    col = ("px_" if line["atribut"] == "prosedur" else "dx2_") + line["kode"]
    delta = np.zeros(len(f))
    if col not in X:
        return delta
    rows = np.flatnonzero(X[col].to_numpy() == 1)
    Xo = X.iloc[rows].copy()
    Xo[col] = 0
    # A direct-scan line is one the tree never learned, so the claim is priced at what was actually paid.
    paid = line.get("sumber") == "kontras langsung"
    with_code = tariffs(f.iloc[rows], f.grup.to_numpy()[rows] if paid else sur.group.predict(X.iloc[rows]),
                        f.sev.to_numpy()[rows] if paid else sur.severity.predict(X.iloc[rows]))
    delta[rows] = np.nan_to_num(with_code - tariffs(f.iloc[rows], sur.group.predict(Xo), sur.severity.predict(Xo)))
    return np.maximum(delta, 0)
