import json
from dataclasses import replace

import numpy as np
import pandas as pd

from engine import ai1_dev as A1D
from engine import ai2 as B2
from engine import ai2_assertion as AS
from engine import ai2_dev as D2
from engine import ai2_fast as F2
from engine import ai2_physiology as P2
from engine import ai3_dev as D
from engine.contracts import split_codes
from engine.data import DEV, is_dev, key_dir, load_world, world_dir
from engine.synth import build as Bd
from engine.synth import fraud as Fr
from engine.synth import rme as R
from engine.synth import world as W

OUTCOMES = ("kurangi", "ganti", "naik")
# The generator draws the cut-back factor from 0.2-0.5 per hospital; one variant world at the midpoint stands in for the draw.
CUT_BACK = 0.35
HEADS = {"sebutan": "embedding", "alat": "embedding", "asersi": "ngram"}


def outcome(role: pd.Series, u: float) -> str | None:
    # The branches of engine.synth.fraud.adapt, with the draw passed in so the simulation owns the randomness.
    if role.modus not in Fr.MAIN_MODES:
        return None
    if u < 0.5:
        return "kurangi"
    if u < 0.8 and role.modus in ("fiktif", "diperpanjang"):
        return "ganti"
    return "naik" if role.tingkat in Fr.TIER_ORDER[:-1] else "kurangi"


def adapted_roles(roles: pd.DataFrame, kind: str) -> pd.DataFrame:
    r = roles.copy()
    if kind == "kurangi":
        main = r.modus.isin(Fr.MAIN_MODES)
        r.loc[main, "intensitas"] = r.loc[main, "intensitas"] * CUT_BACK
    elif kind == "ganti":
        swap = r.modus.isin(["fiktif", "diperpanjang"])
        r.loc[swap, "modus"] = r.loc[swap, "modus"].map({"fiktif": "diperpanjang", "diperpanjang": "fiktif"})
    else:
        up = r.tingkat.isin(Fr.TIER_ORDER[:-1])
        r.loc[up, "tingkat"] = r.loc[up, "tingkat"].map(lambda t: Fr.TIER_ORDER[Fr.TIER_ORDER.index(t) + 1])
    return r


def generate(kind: str, with_rme: bool = True) -> dict:
    # Same seeds and steps as engine.synth.build.build for DEV dasar, so SEP and RS numbers match the base world exactly.
    seed = json.loads((key_dir() / "key_world.json").read_text())["seed"]
    spec = Bd.world_spec(seed, world_dir().name, not is_dev())
    p = replace(spec["params"], scale=1.0)
    cal = W.load_calibration()
    h, s = W.build_world(p, cal)
    roles = adapted_roles(Fr.assign_roles(np.random.default_rng([seed, 1]), h, spec["condition"], spec["hidden"], spec["second"]), kind)
    c = Fr.inject(s, h, roles, p.grouper, np.random.default_rng([seed, 2]))
    h, roles, s, c = Bd.anonymise(h, roles, s, c, np.random.default_rng([seed, 3]))
    c["klaim_layak_fiktif"] = Fr.eligible_fictitious(c)
    c["klaim_layak_diperpanjang"] = Fr.eligible_prolonged(s, p.grouper)
    c["populasi_garis"] = Fr.in_line_population(c)
    if not with_rme:
        return {"claims": c[Bd.CLAIM_COLUMNS].copy(), "hospitals": h[["kode_rs", "kelas_rs", "kepemilikan", "regional"]].copy()}
    docs, _, vitals, stories = R.generate(c, h, cal["icu"]["eicu"]["tanda_vital_per_alat"], seed)
    key = c[Bd.KEY_COLUMNS].merge(stories.drop(columns="rme_versi"), on="nomor_sep", how="left")
    return {"claims": c[Bd.CLAIM_COLUMNS].copy(), "hospitals": h[["kode_rs", "kelas_rs", "kepemilikan", "regional"]].copy(), "key_claims": key,
            "rme_documents": docs, "rme_vitals": vitals}


def fold_readers() -> tuple[dict, dict]:
    # The same five hospital-fold readers that read the base world (ai2_dev.assertion_population), trained once on base DEV.
    D2.use_embedding_cache(HEADS)
    w = load_world(DEV / "dasar", with_key=True)
    c, k = w["claims"].set_index("nomor_sep"), w["key_claims"].set_index("nomor_sep")
    docs = pd.read_parquet(DEV / "dasar" / "rme_documents.parquet")
    labelled = pd.read_parquet(DEV / "dasar" / "key" / "key_sentences.parquet")
    fold = pd.Series(pd.factorize(c.kode_rs)[0] % 5, index=c.index)
    readers = {}
    for f in range(5):
        held = fold.index[fold == f]
        data = AS.training_sentences(docs[~docs.nomor_sep.isin(held)], labelled[~labelled.nomor_sep.isin(held)], k.gaya_tulis)
        readers[f] = AS.AssertionReader.fit(data, HEADS)
    return readers, dict(zip(c.kode_rs, fold))


def signals(t: dict, readers: dict, rs_fold: dict, physiology) -> tuple[pd.DataFrame, pd.DataFrame]:
    c, h, k = t["claims"], t["hospitals"], t["key_claims"].set_index("nomor_sep")
    _, _, mf, mp = A1D.detect(c, h, True, status=False)
    pop = c[c.nomor_sep.isin(k.index[k.populasi_garis.fillna(False)])].reset_index(drop=True)
    seps, by_sep = pop.nomor_sep, pop.set_index("nomor_sep")
    docs = t["rme_documents"][t["rme_documents"].nomor_sep.isin(seps)]
    kw = {sep: B2.read_claim(d, set(split_codes(by_sep.at[sep, "procedure"])), float(by_sep.at[sep, "ventilator_hour"]), use_llm=False)
          for sep, d in docs.groupby("nomor_sep")}
    rs, discharge = c.set_index("nomor_sep").kode_rs, c.set_index("nomor_sep").tgl_pulang
    clones, trail = F2.clone_scores(docs, rs), F2.write_trail(docs, discharge)
    origin = F2.provenance(clones, trail, t["rme_vitals"])
    vitals = t["rme_vitals"][t["rme_vitals"].nomor_sep.isin(seps)]
    sheet = P2.ventilated_hours(P2.hourly_ventilation(physiology, vitals))
    reading = {}
    for f, reader in readers.items():
        mine = docs[docs.nomor_sep.map(rs).map(rs_fold) == f]
        pairs = [(sep, s) for sep, d in mine.groupby("nomor_sep") for s in B2.sentences(B2.assemble(d))]
        read = reader.read([s for _, s in pairs]).assign(nomor_sep=[sep for sep, _ in pairs])
        reading |= {sep: AS.ventilation(g) for sep, g in read.groupby("nomor_sep")}
    score = pd.DataFrame({"p_fiktif": mf.p, "p_panjang": mp.p}, index=c.nomor_sep)
    return D.build_tables(pop, h, score, pd.Series({s: r.verdict for s, r in kw.items()}), pd.Series({s: r.hours for s, r in kw.items()}, dtype=float),
                          sheet, origin.kloning_kuat, origin.tulis_serentak, pd.Series(reading), k)


def variant(kind: str, readers=None, rs_fold=None, physiology=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    path_f, path_o = D.OUT / f"fitur_{kind}.parquet", D.OUT / f"oracle_{kind}.parquet"
    if path_f.exists() and path_o.exists():
        return pd.read_parquet(path_f), pd.read_parquet(path_o)
    f, o = signals(generate(kind), readers, rs_fold, physiology)
    f.to_parquet(path_f)
    o.to_parquet(path_o)
    return f, o


def ai1_scores(kind: str, with_costs: bool) -> pd.DataFrame:
    # AI 1 without the made-up hospital cost details is the honest reference (AI 1 lesson); both versions use the same two-round pipeline.
    path = D.OUT / f"skor_ai1_{'lengkap' if with_costs else 'jujur'}_{kind}.parquet"
    if path.exists():
        return pd.read_parquet(path)
    if kind == "dev":
        w = load_world(world_dir())
        c, h = w["claims"], w["hospitals"]
    else:
        t = generate(kind, with_rme=False)
        c, h = t["claims"], t["hospitals"]
    _, _, mf, mp = A1D.detect(c, h, with_costs, status=False)
    out = pd.DataFrame({"nomor_sep": c.nomor_sep.to_numpy(), "p_fiktif": mf.p, "p_panjang": mp.p})
    out.to_parquet(path)
    return out


def build_variants() -> dict:
    readers, rs_fold = fold_readers()
    icu = D.ROOT / "data" / "icu_open"
    physiology, _ = P2.train(pd.read_parquet(icu / "eicu_hourly.parquet"), pd.read_parquet(icu / "mimic_hourly.parquet"))
    out = {}
    for kind in OUTCOMES:
        f, o = variant(kind, readers, rs_fold, physiology)
        out[kind] = {"klaim_populasi": len(f), "klaim_dimanipulasi": int(o.temuan.sum()), "kebocoran": float(o.rupiah.sum())}
        print(kind, out[kind], flush=True)
    return out


if __name__ == "__main__":
    import sys
    if sys.argv[1:2] == ["skor_jujur"]:
        for kind in ("dev", *OUTCOMES):
            print(kind, ai1_scores(kind, with_costs=False).describe().round(3).to_dict(), flush=True)
    else:
        print(json.dumps(build_variants(), ensure_ascii=False, indent=1))
