import numpy as np
import pandas as pd
import pytest
from sklearn.dummy import DummyClassifier

from engine import ai1 as A
from engine import stats as S
from engine.contracts import TRIGGER_CODES, GroupedClaim, is_eligible_fictitious, is_eligible_prolonged, split_codes
from engine.data import ROOT, BlindTestError, load_world
from engine.synth.world import CALIBRATION_DIR

needs_world = pytest.mark.skipif(not (CALIBRATION_DIR / "data_sampel.json").exists(), reason="kalibrasi lokal belum dibuat")


@pytest.fixture(scope="module")
def small():
    from engine.synth.world import WorldParams, build_world
    h, s = build_world(WorldParams(seed=3, scale=0.1))
    return h, s


@needs_world
def test_features_ignore_forbidden_columns_and_trigger_codes(small):
    h, s = small
    vocab = A.fit_vocab(A.evidence(s, h))
    base = A.features(A.evidence(s, h), vocab)
    rng = np.random.default_rng(0)
    scrambled = s.assign(
        ventilator_hour=rng.integers(0, 500, len(s)), ventilator_use_ind=rng.integers(0, 2, len(s)),
        cbg=rng.permutation(s.cbg.to_numpy()), tarif_ina_cbg=rng.permutation(s.tarif_ina_cbg.to_numpy()),
        nomor_sep="X", discharge_status=rng.permutation(s.discharge_status.to_numpy()),
        procedure=s.procedure.map(lambda p: "#".join(c for c in split_codes(p) if c not in TRIGGER_CODES)))
    pd.testing.assert_frame_equal(base, A.features(A.evidence(scrambled, h), vocab))
    assert not set(vocab.procedures) & TRIGGER_CODES
    assert not {c for c in base.columns for f in A.FORBIDDEN if f in c} and "discharge_status" not in base.columns



@needs_world
def test_vectorised_populations_match_the_contracts(small):
    from engine.synth.checks import _claim_record
    _, s = small
    claims = [GroupedClaim.model_validate(_claim_record(r)) for _, r in s.iterrows()]
    np.testing.assert_array_equal(A.eligible_fictitious(s), [is_eligible_fictitious(c) for c in claims])
    np.testing.assert_array_equal(A.eligible_prolonged(s), [is_eligible_prolonged(c) for c in claims])

def test_per_rs_test_flags_the_hospital_with_excess_codes():
    rng = np.random.default_rng(1)
    rs = pd.Series(np.repeat([f"RS-{i:03d}" for i in range(40)], 100))
    p = np.full(len(rs), 0.3)
    y = (rng.random(len(rs)) < 0.3).astype(int)
    y[:100] = (rng.random(100) < 0.7)
    n_layak = pd.Series(100, index=sorted(rs.unique()))
    t = S.per_rs_test(rs, y, p, np.ones(len(rs), bool), n_layak)
    assert t.ditandai["RS-000"] and t.ditandai.sum() <= 2



def test_calibration_tames_overconfident_tails():
    rng = np.random.default_rng(0)
    true = rng.uniform(0.001, 0.05, 20_000)
    y = (rng.random(len(true)) < true).astype(int)
    raw = true / 20
    q = A.calibrate(raw, y, np.repeat(np.arange(100), 200), np.ones(len(y), bool))
    assert raw.sum() / y.sum() < 0.1 and abs(q.sum() / y.sum() - 1) < 0.1


def test_single_feature_scan_catches_a_label_copy():
    rng = np.random.default_rng(0)
    y = (rng.random(3000) < 0.1).astype(int)
    X = pd.DataFrame({"salinan": y.astype(float), "acak": rng.random(3000),
                      "kategori": pd.Categorical(np.where(y == 1, "v", rng.choice(["a", "b"], 3000)))})
    auc = A.single_feature_auc(X, y, np.repeat(np.arange(30), 100))
    assert auc["salinan"] == 1.0 and auc["kategori"] > 0.95 and auc["acak"] < 0.6


def test_exact_z_is_the_binomial_mid_p():
    from scipy.stats import norm
    assert abs(S.exact_z([(0.5, 0.5)] * 10, 8) - norm.isf((11 + 22.5) / 1024)) < 1e-9


def test_precision_at_k_averages_over_ties_at_the_cut():
    assert S.precision_at_k(np.array([5, 3, 3, 1]), np.array([1, 1, 0, 0]), 2) == 0.75
    assert S.precision_at_k(np.array([3, 3, 3, 3, 1]), np.array([1, 0, 1, 0, 1]), 2) == 0.5

def test_counterfactual_rupiah_counts_excess_claims_times_delta():
    d = pd.DataFrame({"y": [1.0] * 4, "p": [0.0] * 4, "delta": [1_000_000.0] * 4})
    r = S.counterfactual_rupiah(d, np.random.default_rng(0), reps=50)
    assert r.rupiah == 4_000_000 and r.rupiah_bawah == r.rupiah_atas == 4_000_000


def test_main_and_simple_models_share_the_same_folds(monkeypatch):
    test_folds = []

    class Recorded(A.GroupKFold):
        def split(self, X, y=None, groups=None):
            for tr, te in super().split(X, y, groups):
                test_folds.append(sorted(set(groups[te])))
                yield tr, te

    rng = np.random.default_rng(0)
    n = 400
    groups = rng.choice([f"KAB-{i:02d}" for i in range(20)], n)
    X = pd.DataFrame({"umur": rng.uniform(20, 80, n), "lama_rawat": rng.integers(1, 15, n).astype(float),
                      "dx_primer": pd.Categorical(rng.choice(["J96", "J18", "I63"], n))})
    y, everyone = rng.integers(0, 2, n), np.ones(n, bool)
    monkeypatch.setattr(A, "GroupKFold", Recorded)
    monkeypatch.setattr(A, "new_model", lambda *_: DummyClassifier())
    A.cross_fit(X, y, groups, everyone, everyone)
    main, test_folds[:] = list(test_folds), []
    A.cross_fit_simple(X, y, groups, everyone, everyone)
    assert len(main) == A.N_FOLD and main == test_folds


def test_robust_scale_is_at_least_chance_and_flags_need_an_excess():
    idx = [f"RS-{i:03d}" for i in range(40)]
    n = pd.Series(100, index=idx)
    z = pd.Series(np.linspace(-0.01, 0.01, 40), index=idx)
    z.iloc[0] = 0.5
    assert not S.robust_flags(z, n).ditandai.any()
    z.iloc[0] = 8.0
    assert S.robust_flags(z, n).ditandai.iloc[0]
    assert not S.robust_flags(z, n, pd.Series(False, index=idx)).ditandai.any()


def test_blind_test_folders_are_refused(monkeypatch):
    for value in (None, "ya", "1"):
        if value is None:
            monkeypatch.delenv("TAPAL_BUKA_SEGEL", raising=False)
        else:
            monkeypatch.setenv("TAPAL_BUKA_SEGEL", value)
        for blocked in ("test/dasar", "sealed/test/dasar"):
            with pytest.raises(BlindTestError):
                load_world(ROOT / "data" / blocked)
        with pytest.raises(BlindTestError):
            load_world(ROOT / "data" / "dev" / "dasar", with_key=True, key=ROOT / "data" / "sealed" / "x")


@needs_world
def test_saved_model_loads_only_with_its_fingerprint(small, tmp_path):
    h, s = small
    vocab = A.fit_vocab(A.evidence(s, h))
    X = A.features(A.evidence(s, h), vocab)
    y = A.has_trigger(s).astype(int)
    bundle = A.Bundle(A.MODEL_VERSION, vocab, {"fiktif": A.final_model(X, y, s.kode_rs.to_numpy()), "panjang": A.new_model().fit(X, y)},
                      A.reference_values(X, y == 1), {"_semua": list(np.linspace(0, 1, 101))}, {"fiktif": 0.5, "panjang": 0.5})
    path = tmp_path / f"ai1-{A.MODEL_VERSION}.joblib"
    A.save_bundle(bundle, path)
    loaded = A.load_bundle(path)
    np.testing.assert_allclose(loaded.predict(X.head(20), "fiktif"), bundle.predict(X.head(20), "fiktif"))
    assert loaded.status(0.9, None, None) == "periksa_manual" and loaded.status(0.9, 0.9, True) == "lolos_cepat"
    assert loaded.status(0.4, None, True) == "periksa_manual"
    reasons = loaded.reasons(X.head(2), "fiktif")
    assert all({"teks", "arah", "besar"} <= set(r) for rs in reasons for r in rs)
    path.write_bytes(path.read_bytes() + b"x")
    with pytest.raises(ValueError):
        A.load_bundle(path)


def test_asymmetry_sees_a_pile_up_above_the_line_and_not_at_placebo_lines():
    from engine import lines as L
    rng = np.random.default_rng(0)
    honest = rng.uniform(40, 200, 6000).round()
    hours = np.concatenate([honest, rng.uniform(96, 101, 300).round()])
    rs = rng.integers(0, 60, len(hours))
    t = L.asymmetry_table(hours, rs, rng, reps=200).set_index("garis")
    assert t.at[96, "bawah"] > 0 and t.at[120, "bawah"] <= 0 <= t.at[120, "atas"] and t.at[144, "bawah"] <= 0 <= t.at[144, "atas"]


def test_a_new_line_is_added_by_configuration_alone(tmp_path):
    from engine import line_config as LC
    lines = LC.load()
    assert LC.active_hour_lines(lines) == (96,)
    found = [{"jenis": "ambang", "atribut": "jam_ventilasi", "ambang": 72, "grup_asal": "J-1-20", "grup_tujuan": "J-1-02"}]
    lines = LC.add_found(lines, found)
    assert LC.active_hour_lines(lines) == (96,) and lines[-1]["status"] == "temuan"
    path = tmp_path / "garis.json"
    LC.save(LC.set_status(lines, "ambang:jam_ventilasi:72", "aktif"), path)
    assert LC.active_hour_lines(LC.load(path)) == (72, 96)


def test_line_finder_rediscovers_a_trigger_code_and_a_coded_hour_line():
    from engine import ai4 as F4
    rng = np.random.default_rng(0)
    n = 600
    kind = rng.choice(["medis", "vent", "panjang"], n, p=[0.5, 0.3, 0.2])
    hours = np.where(kind == "vent", rng.integers(1, 96, n), np.where(kind == "panjang", rng.integers(96, 110, n), 0)).astype(float)
    f = pd.DataFrame({"codes": [frozenset({"96.71"} if k == "vent" else {"96.72"} if k == "panjang" else set()) | {"89.65"} for k in kind],
                      "dx1": "J96", "dx2": [frozenset()] * n, "jam_ventilasi": hours, "lama_rawat": rng.integers(1, 20, n).astype(float),
                      "umur": rng.uniform(20, 80, n), "grup": np.select([kind == "vent", kind == "panjang"], ["J-1-20", "J-1-02"], "J-4-11"),
                      "sev": 1, "regional": "1", "kelas_rs": "C", "kepemilikan": "swasta", "kelas_rawat": 3})
    r = F4.find_lines(f, rng)
    codes = {x["kode"]: x for x in r["kode"] + r["kode_setara_ambang"]}
    assert codes["96.71"]["grup_tujuan"] == "J-1-20-I" and "89.65" not in codes
    assert [(x["atribut"], x["ambang"], x["lewat_kode"]) for x in r["ambang"]] == [("jam_ventilasi", 96, "96.72")]
    delta = F4.threshold_delta(f, r["ambang"][0])
    one = f.iloc[:1]
    gap = (F4.tariffs(one, np.array(["J-1-02"]), np.array([1])) - F4.tariffs(one, np.array(["J-1-20"]), np.array([1])))[0]
    assert gap > 0 and np.allclose(delta[kind == "panjang"], gap) and not delta[kind != "panjang"].any()
    assert r["ambang"][0]["grup_asal"] == "J-1-20-I"


def test_direct_scan_finds_a_route_too_rare_for_a_tree_leaf():
    from engine import ai4 as F4
    rng = np.random.default_rng(1)
    n = 900
    kind = rng.choice(["medis", "vent", "panjang"], n, p=[0.5, 0.3, 0.2])
    trach = (kind == "panjang") & (np.cumsum(kind == "panjang") <= 35)
    hours = np.where(kind == "vent", rng.integers(1, 96, n), np.where(kind == "panjang", rng.integers(96, 110, n), 0)).astype(float)
    f = pd.DataFrame({"codes": [frozenset({"96.71"} if k == "vent" else {"96.72"} if k == "panjang" else set()) | {"89.65"} | ({"31.1"} if t else set())
                                for k, t in zip(kind, trach)],
                      "dx1": "J96", "dx2": [frozenset()] * n, "jam_ventilasi": hours, "lama_rawat": rng.integers(1, 20, n).astype(float),
                      "umur": rng.uniform(20, 80, n), "grup": np.select([trach, kind == "vent", kind == "panjang"], ["J-1-01", "J-1-20", "J-1-02"], "J-4-11"),
                      "sev": 1, "regional": "1", "kelas_rs": "C", "kepemilikan": "swasta", "kelas_rawat": 3})
    r = F4.find_lines(f, rng, min_leaf=50)
    codes = {x["kode"]: x for x in r["kode"] + r["kode_setara_ambang"]}
    assert codes["31.1"]["sumber"] == "kontras langsung" and codes["31.1"]["grup_tujuan"] == "J-1-01-I" and "89.65" not in codes
