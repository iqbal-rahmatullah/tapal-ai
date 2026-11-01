import re
from dataclasses import dataclass, field

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from engine.ai2 import MODEL, OLLAMA, OPTIONS, TIMEOUT, _inline, llm_enabled

TOKEN = re.compile(r"\{([a-z_]+)\}")
COMPARISON = re.compile(r"\b(perbedaan|berbeda|selisih|lebih (?:tinggi|rendah|panjang|pendek|besar|kecil|banyak|sedikit)|kurang dari|melebihi|sama dengan)\b",
                        re.I)
PROMPT = """Anda menulis ringkasan kasus untuk verifikator BPJS Kesehatan dalam bahasa Indonesia baku: 2 sampai 4 kalimat, netral, dan tidak menuduh.
Aturan:
1. Jangan menulis angka, tanggal, jam, kode, persen, atau rupiah sendiri. Setiap nilai ditulis sebagai token dari daftar fakta, persis seperti {nama_token}. Nilai token sudah memuat satuannya, jadi jangan menulis satuan lagi sesudah token. Nama mesin boleh ditulis AI 1, AI 2, AI 3, atau AI 4.
2. Pakai hanya fakta di daftar. Jangan menambah fakta, dugaan, atau saran tindakan yang tidak tertulis, dan jangan membandingkan atau menilai angka sendiri; perbandingan hanya lewat token yang tersedia.
3. Jangan memakai kata curang, fraud, pelaku, atau terbukti."""


@dataclass
class Fact:
    value: str
    source: str
    meaning: str


class Narrative(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kalimat: list[str] = Field(min_length=1, max_length=5)


@dataclass
class Story:
    source: str
    segments: list[dict]
    reasons: list[str] = field(default_factory=list)


def call_narrative(facts_text: str, model: str = MODEL) -> Narrative:
    if model.endswith(":cloud") or "-cloud" in model:
        raise ValueError(f"model awan ditolak: {model}")
    body = {"model": model, "stream": False, "think": False, "format": _inline(Narrative.model_json_schema()), "options": OPTIONS,
            "keep_alive": "30m", "messages": [{"role": "system", "content": PROMPT}, {"role": "user", "content": facts_text}]}
    data = httpx.post(f"{OLLAMA}/api/chat", json=body, timeout=TIMEOUT).raise_for_status().json()
    return Narrative.model_validate_json(data["message"]["content"])


def problems(sentences: list[str], facts: dict[str, Fact]) -> list[str]:
    text = " ".join(sentences)
    out = [f"token tidak dikenal: {{{t}}}" for t in sorted(set(TOKEN.findall(text)) - facts.keys())]
    # Every number must come from code, so a digit left after removing tokens means the LLM wrote one itself.
    if re.search(r"\d", re.sub(r"\bAI [1-4]\b", "", TOKEN.sub("", text))):
        out.append("LLM menulis angka sendiri")
    if re.search(r"curang|fraud|pelaku|terbukti", text, re.I):
        out.append("LLM memakai kata yang dilarang")
    # Comparisons must come from a code-computed token; the LLM once called 74 and 74,2 hours "berbeda".
    if COMPARISON.search(TOKEN.sub("", text)):
        out.append("LLM membandingkan angka sendiri")
    return out


def render(sentences: list[str], facts: dict[str, Fact]) -> list[dict]:
    text, segments, last = " ".join(sentences), [], 0
    for m in TOKEN.finditer(text):
        if m.start() > last:
            segments.append({"teks": text[last:m.start()], "token": None, "asal": None})
        fact = facts[m.group(1)]
        segments.append({"teks": fact.value, "token": m.group(1), "asal": fact.source})
        last = m.end()
        # A unit the LLM repeats after a token that already carries it ("10 jam jam") is dropped.
        unit = fact.value.split()[-1] if fact.value.split() else ""
        if unit and not unit[0].isdigit() and (rep := re.match(rf"\s+{re.escape(unit)}\b", text[last:], re.I)):
            last += rep.end()
    if last < len(text):
        segments.append({"teks": text[last:], "token": None, "asal": None})
    return segments


def narrate(facts: dict[str, Fact], template: list[str], use_llm: bool | None = None, call=call_narrative) -> Story:
    note = []
    if use_llm is None:
        use_llm = llm_enabled()
    if use_llm:
        # Numeric values are withheld from the LLM, so it can place them but cannot compare or misread them.
        listing = "\n".join(f"- {{{k}}} = {'(angka, diisi kode)' if re.search(r'[0-9]', f.value) else f.value}: {f.meaning}"
                             for k, f in facts.items())
        try:
            sentences = call(f"Fakta:\n{listing}").kalimat
            if not (note := problems(sentences, facts)):
                return Story("llm_lokal", render(sentences, facts))
        except (httpx.HTTPError, OSError, ValidationError):
            note = ["LLM tidak tersedia atau keluarannya tidak sah"]
    return Story("aturan", render(template, facts), note + ["narasi templat dari aturan"])
