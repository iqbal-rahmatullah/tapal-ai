import numpy as np
import pandas as pd

from engine import ai3 as A


def test_inclusion_keeps_floor_cap_and_capacity():
    rng = np.random.default_rng(0)
    score = np.concatenate([rng.exponential(1.0, 1600), [1e6, 1e6], np.zeros(48)])
    pi = A.inclusion(score)
    assert abs(pi.sum() - A.CAPACITY) < 1e-6 and pi.min() >= A.PI_MIN and pi.max() <= 1
    assert pi[1600] == 1 and np.all(pi[-48:] == A.PI_MIN)


def test_systematic_sample_takes_exactly_capacity_with_the_stated_pi():
    rng = np.random.default_rng(1)
    pi = A.inclusion(rng.exponential(1.0, 400) ** 2, capacity=40)
    counts = np.zeros(len(pi))
    for _ in range(4000):
        picked = A.systematic(pi, rng)
        assert len(picked) == 40 and len(set(picked)) == 40
        counts[picked] += 1
    assert np.abs(counts / 4000 - pi).max() < 0.03


def test_both_totals_are_unbiased_and_the_model_only_narrows_the_interval():
    rng = np.random.default_rng(2)
    n = 1500
    stake = rng.lognormal(16, 0.6, n)
    p = rng.beta(1, 8, n)
    found_all = np.where(rng.random(n) < p, stake, 0.0)
    pi = A.inclusion(p * stake, capacity=60)
    ppi, ht, width = [], [], []
    for _ in range(3000):
        picked = A.systematic(pi, rng)
        e = A.estimate(p * stake, picked, found_all[picked], pi)
        ppi.append(e["ppi"])
        ht.append(e["ht"])
        width.append((np.sqrt(e["var_ppi"]), np.sqrt(e["var_ht"])))
    truth = found_all.sum()
    assert abs(np.mean(ppi) / truth - 1) < 0.02 and abs(np.mean(ht) / truth - 1) < 0.02
    assert np.mean([a for a, _ in width]) < np.mean([b for _, b in width])


def test_model_needs_both_outcomes_and_caps_exploration_weights():
    rng = np.random.default_rng(3)
    X = pd.DataFrame(rng.normal(size=(80, len(A.FEATURES))), columns=A.FEATURES)
    assert A.OutcomeModel.fit(X, np.zeros(80, int), np.full(80, 0.5), rng) is None
    y = (X.ragu_fiktif > 0).to_numpy(int)
    m = A.OutcomeModel.fit(X, y, np.where(np.arange(80) == 0, A.PI_MIN, 0.5), rng)
    mean, sd = m.predict(X)
    assert mean.shape == (80,) and np.all(sd >= 0) and ((mean > 0.5) == y.astype(bool)).mean() > 0.8


def test_static_score_and_history_use_no_outcome_of_the_month():
    f = pd.DataFrame({"p_fiktif": [0.99, 0.99, 0.2], "p_panjang": [np.nan, 0.4, np.nan], **{c: [False] * 3 for c in A.AI2_FLAGS}})
    f.loc[0, "kata_kunci"] = True
    assert np.allclose(A.static_probability(f), [0.5, 0.6, 0.8])
    hist = A.rs_history(pd.Series(["RS-1", "RS-2"]), pd.DataFrame({"kode_rs": ["RS-1", "RS-1"], "temuan": [1, 1]}))
    assert hist.rs_audit.iloc[1] == 0 and hist.rs_laju_temuan.iloc[0] > hist.rs_laju_temuan.iloc[1]


def test_adaptation_follows_the_generator_and_moves_only_the_caught_hospital():
    from engine import ai3_dev as D
    from engine import ai3_worlds as V
    def role(modus, tingkat):
        return pd.Series({"modus": modus, "tingkat": tingkat})
    assert V.outcome(role("fiktif", "biasa"), 0.3) == "kurangi" and V.outcome(role("fiktif", "biasa"), 0.6) == "ganti"
    assert V.outcome(role("fiktif", "biasa"), 0.9) == "naik" and V.outcome(role("fiktif", "cerdik_3"), 0.9) == "kurangi"
    assert V.outcome(role("rme_meragukan", "kloning"), 0.6) == "kurangi" and V.outcome(role("", ""), 0.1) is None
    roles = pd.DataFrame({"kode_rs": ["RS-1", "RS-2", "RS-3"], "modus": ["fiktif", "diperpanjang", ""], "tingkat": ["biasa", "cerdik_2", ""],
                          "intensitas": [0.2, 0.3, 0.0]})
    assert V.adapted_roles(roles, "kurangi").intensitas.round(3).tolist() == [0.07, 0.105, 0.0]
    assert V.adapted_roles(roles, "ganti").modus.tolist() == ["diperpanjang", "fiktif", ""]
    assert V.adapted_roles(roles, "naik").tingkat.tolist() == ["cerdik_1", "cerdik_3", ""]
    base = pd.DataFrame({"kode_rs": ["RS-1", "RS-2", "RS-2"], "bulan": [1, 1, 2]})
    worlds = {"dasar": (base.assign(sumber="dasar"), base.assign(t=0)), "kurangi": (base.assign(sumber="kurangi"), base.assign(t=1))}
    f, o = D._month(worlds, {"RS-2": "kurangi"}, 1)
    assert dict(zip(f.kode_rs, f.sumber)) == {"RS-1": "dasar", "RS-2": "kurangi"} and len(o) == 2
