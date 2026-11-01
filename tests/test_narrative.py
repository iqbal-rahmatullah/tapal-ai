import httpx

from engine import narrative as N

FACTS = {"jam_rme": N.Fact("50,0 jam", "dihitung kode dari kutipan RME", "jam ventilasi menurut RME"),
         "jam_lembar": N.Fact("0 jam", "pembaca fisiologi atas lembar tanda vital", "jam berventilasi menurut lembar tanda vital")}
TEMPLATE = ["RME mencatat ventilasi {jam_rme}, lembar tanda vital {jam_lembar}."]


def llm(*sentences):
    return lambda _: N.Narrative(kalimat=list(sentences))


def test_numbers_come_only_from_code():
    ok = N.narrate(FACTS, TEMPLATE, use_llm=True, call=llm("Teks RME mencatat ventilasi {jam_rme}, tetapi lembar tanda vital hanya {jam_lembar}."))
    assert ok.source == "llm_lokal" and [s["teks"] for s in ok.segments if s["token"]] == ["50,0 jam", "0 jam"]
    digits = N.narrate(FACTS, TEMPLATE, use_llm=True, call=llm("RME mencatat 50 jam ventilasi."))
    assert digits.source == "aturan" and "LLM menulis angka sendiri" in digits.reasons
    unknown = N.narrate(FACTS, TEMPLATE, use_llm=True, call=llm("Selisih {rupiah}."))
    assert unknown.source == "aturan" and unknown.reasons[0].startswith("token tidak dikenal")
    assert N.narrate(FACTS, TEMPLATE, use_llm=True, call=llm("Klaim ini terbukti {jam_rme}.")).source == "aturan"


def test_template_when_llm_is_down():
    def down(_):
        raise httpx.ConnectError("mati")
    s = N.narrate(FACTS, TEMPLATE, use_llm=True, call=down)
    assert s.source == "aturan" and "".join(x["teks"] for x in s.segments) == "RME mencatat ventilasi 50,0 jam, lembar tanda vital 0 jam."


def test_repeated_units_are_dropped_and_engine_names_allowed():
    ok = N.narrate(FACTS, TEMPLATE, use_llm=True, call=llm("Menurut AI 2, RME mencatat {jam_rme} jam, lembar {jam_lembar}."))
    assert ok.source == "llm_lokal" and "".join(x["teks"] for x in ok.segments) == "Menurut AI 2, RME mencatat 50,0 jam, lembar 0 jam."


def test_numbers_are_hidden_from_the_llm_and_own_comparisons_rejected():
    seen = []
    N.narrate(FACTS, TEMPLATE, use_llm=True, call=lambda text: seen.append(text) or N.Narrative(kalimat=["RME mencatat {jam_rme}."]))
    assert "50,0" not in seen[0] and "(angka, diisi kode)" in seen[0]
    bad = N.narrate(FACTS, TEMPLATE, use_llm=True, call=llm("Terdapat perbedaan antara {jam_rme} dan {jam_lembar}."))
    assert bad.source == "aturan" and "LLM membandingkan angka sendiri" in bad.reasons
