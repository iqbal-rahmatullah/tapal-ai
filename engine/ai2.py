import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import httpx
import pandas as pd
from pydantic import ValidationError

from engine.contracts import RmeReading

MODEL = "gemma4:e4b-it-qat"
OLLAMA = "http://127.0.0.1:11434"
NUM_CTX = 8192
TIMEOUT = httpx.Timeout(120.0, connect=5.0)
OPTIONS = {"temperature": 0, "seed": 42, "num_ctx": NUM_CTX}
MERGE_GAP = timedelta(hours=1)
LONG_HOURS = 96
HOUR_SLACK = 1.0
VENT_CODES = {"96.70", "96.71", "96.72"}
# DEV: this caught 24 of 51 made-up records (the rest have 3-hour or stretched episodes) and 0 of 19,118 honest ones.
SHEET_MIN_HOURS = 12
SHEET_SHARE = 0.2

PROMPT = """Anda adalah pengekstrak fakta dari rekam medis elektronik (RME) ICU. Setiap baris RME adalah satu catatan, urut menurut waktu, diawali [jenis catatan, penulis], ditambah waktu catatan bila teksnya tidak memuat waktu.
Tentukan alat bantu napas yang BENAR-BENAR dipakai pasien selama rawat inap ini, dan waktu ventilasi mekanik invasif.
Aturan:
1. Hanya fakta yang tertulis sudah terjadi. Abaikan penyangkalan ("tidak ada indikasi intubasi", "tidak terpasang"), rencana ("rencana intubasi", "bila perburukan", "disiapkan"), ceklis templat yang tidak dicentang, dan riwayat rawat inap sebelumnya.
2. Ventilasi invasif = ventilator melalui ETT atau trakeostomi, termasuk mode CPAP/PSV saat penyapihan bila masih melalui ETT. NIV/BiPAP/CPAP lewat sungkup, HFNC, NRM, dan nasal kanul BUKAN ventilasi invasif.
3. alat_napas_tertinggi: alat dengan tingkat tertinggi yang benar-benar dipakai, urutan ventilator_invasif > niv > hfnc > nrm > nasal_kanul > udara_ruang. Bila jenis alat tidak bisa dipastikan dari dokumen, isi tidak_jelas.
4. ventilasi_invasif: ya, tidak, atau tidak_jelas. Bila jenis alat tidak bisa dipastikan (alat_napas_tertinggi = tidak_jelas), ventilasi_invasif juga tidak_jelas. Jangan menyimpulkan 'tidak' hanya karena ventilator tidak disebut.
5. episode: untuk setiap episode ventilasi invasif, waktu mulai (intubasi atau mulai dihubungkan ke ventilator) dan selesai (ekstubasi, ventilator dilepas, atau pasien meninggal saat masih memakai ventilator), disalin PERSIS dari kalimat tempat kejadian itu ditulis (tanggal dan jam, tanpa mengubah atau menggabungkan format); bila kalimat itu tidak memuat waktu, salin waktu dari kepala catatannya. Ekstubasi yang ditunda atau gagal bukan akhir episode. Kosongkan bila tidak ada ventilasi invasif. Jangan menghitung jumlah jam.
6. kutipan: 1 sampai 6 kutipan pendek untuk fakta penting (alat napas tertinggi, mulai dan selesai tiap episode), masing-masing disalin PERSIS kata per kata dari dokumen, tanpa mengubah, menyingkat, atau menerjemahkan. Kutipan harus potongan kalimat yang benar-benar ada di dokumen, bukan ringkasan, kesimpulan, atau nilai kolom. Kutipan yang tidak persis akan ditolak sistem.
7. mode_ventilator: mode awal yang tertulis (misalnya SIMV), atau string kosong bila tidak ada."""

MONTHS = {m: i for i, m in enumerate(("januari", "februari", "maret", "april", "mei", "juni", "juli", "agustus", "september",
                                      "oktober", "november", "desember"), 1)}
_HM = r"(\d{1,2})[:.](\d{2})"
_PATTERNS = (
    ("ymd", re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})\D{1,12}?" + _HM)),
    ("dmy", re.compile(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\D{1,12}?" + _HM)),
    ("dny", re.compile(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\D{1,12}?" + _HM)),
    ("dm", re.compile(r"(\d{1,2})/(\d{1,2})\D{1,12}?" + _HM)),
    ("hm", re.compile(r"(?<![\d/:.-])" + _HM + r"(?![\d/])")),
)
CLOCK = re.compile(r"\b(?:jam|pukul|pkl)\.?\s*\d{1,2}[:.]\d{2}", re.I)
END = re.compile(r"ekstubasi|\baff\b|dilepas|\blepas\b|meninggal|exitus", re.I)
NOT_YET = re.compile(r"tunda|rencana|\brcn\b|besok|\bbila\b|\bjika\b|gagal|belum", re.I)
VENT = re.compile(r"ventilator|\bvent\b|\bMV\b|\bETT\b|intubasi", re.I)
NOT_PRESENT = re.compile(r"tidak|tanpa|pasca|post|riwayat|sebelumnya|\baff\b|ekstubasi|dilepas|lepas|sampai|selama|rencana|\brcn\b"
                         r"|\bbila\b|\bjika\b|siap|indikasi", re.I)
DEVICES = (("niv", re.compile(r"\bNIV\b|BiPAP", re.I)), ("hfnc", re.compile(r"HFNC|high flow", re.I)),
           ("nrm", re.compile(r"\bNRM\b|non-rebreathing", re.I)), ("nasal_kanul", re.compile(r"nasal kanul|kanul nasal", re.I)),
           ("udara_ruang", re.compile(r"udara ruang|udara bebas", re.I)))


def _hours(x: float) -> str:
    # Reasons are shown in the app, which writes decimals the Indonesian way (EYD).
    return f"{x:.1f}".replace(".", ",")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text) if s]


def parse_time(text: str, ref: datetime) -> datetime | None:
    for kind, pattern in _PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        g = m.groups()
        try:
            if kind == "ymd":
                return datetime(int(g[0]), int(g[1]), int(g[2]), int(g[3]), int(g[4]))
            if kind == "dmy":
                return datetime(int(g[2]), int(g[1]), int(g[0]), int(g[3]), int(g[4]))
            if kind == "dny":
                if g[1].lower() not in MONTHS:
                    continue
                return datetime(int(g[2]), MONTHS[g[1].lower()], int(g[0]), int(g[3]), int(g[4]))
            if kind == "dm":
                # A day/month without a year takes the year that puts it closest to the note it was written in.
                return min((datetime(y, int(g[1]), int(g[0]), int(g[2]), int(g[3])) for y in (ref.year - 1, ref.year, ref.year + 1)),
                           key=lambda d: abs(d - ref))
            return datetime(ref.year, ref.month, ref.day, int(g[0]), int(g[1]))
        except ValueError:
            return None
    return None


@dataclass
class Record:
    text: str
    lines: list[tuple[str, str, datetime, str]]


def has_time(text: str) -> bool:
    # A bare decimal such as "pH 7.21" is not a clock time, so a lone hour needs its keyword.
    return bool(CLOCK.search(text)) or any(p.search(text) for kind, p in _PATTERNS if kind != "hm")


def assemble(docs: pd.DataFrame) -> Record:
    lines = []
    for r in docs.sort_values("waktu_layanan").itertuples():
        when = pd.Timestamp(r.waktu_layanan).to_pydatetime()
        # Only notes without a written time get the note time: a second format beside a written one made Gemma splice the two.
        head = f"[{r.jenis}, {r.penulis_peran}]" if has_time(r.teks) else f"[{r.jenis}, {r.penulis_peran}, {when:%Y-%m-%d %H:%M}]"
        lines.append((head, r.teks, when, r.jenis))
    return Record("\n".join(f"{h} {t}" for h, t, _, _ in lines), lines)


def _locate(record: Record, value: str) -> tuple[datetime, str] | None:
    target = _norm(value)
    if not target:
        return None
    for header, text, when, _ in record.lines:
        if target in _norm(text):
            return when, next((s for s in _sentences(text) if target in _norm(s)), text)
        if target in _norm(header):
            return when, next((s for s in _sentences(text) if END.search(s) and not NOT_YET.search(s)), text)
    return None


def _vent_after(record: Record, end: datetime) -> str | None:
    # A discharge summary looks back over the whole stay, so only notes written for later moments count.
    for _, text, when, kind in record.lines:
        if when <= end + MERGE_GAP or kind == "resume_medis":
            continue
        for s in _sentences(text):
            if VENT.search(s) and not NOT_PRESENT.search(s):
                return s
    return None


@dataclass
class Check:
    accepted: bool
    reasons: list[str]
    quotes_ok: int
    hours: float | None = None
    episodes: list[tuple[datetime, datetime]] = field(default_factory=list)


def check_reading(reading: RmeReading, record: Record) -> Check:
    reasons, text = [], _norm(record.text)
    quotes_ok = sum(1 for q in reading.kutipan if _norm(q.teks) and _norm(q.teks) in text)
    if not reading.kutipan:
        reasons.append("bacaan tanpa kutipan")
    elif quotes_ok < len(reading.kutipan):
        reasons.append(f"{len(reading.kutipan) - quotes_ok} kutipan tidak cocok kata per kata dengan RME")
    invasive, device = reading.ventilasi_invasif, reading.alat_napas_tertinggi
    if invasive == "tidak" and (reading.episode or device == "ventilator_invasif"):
        reasons.append("status invasif tidak konsisten dengan alat atau episode")
    if invasive != "ya":
        return Check(not reasons, reasons, quotes_ok)
    if device != "ventilator_invasif":
        reasons.append("ventilasi invasif tetapi alat tertinggi bukan ventilator")
    spans = []
    for e in reading.episode:
        a, b = _locate(record, e.mulai), _locate(record, e.selesai)
        if not a or not b:
            reasons.append("waktu episode tidak tertulis persis di RME")
            continue
        start, stop = parse_time(e.mulai, a[0]), parse_time(e.selesai, b[0])
        if not start or not stop or stop <= start:
            reasons.append("waktu episode tidak dapat diurai")
            continue
        spans.append((start, stop, b[1]))
    if not reading.episode:
        reasons.append("ventilasi invasif tanpa episode")
    merged = []
    for start, stop, sentence in sorted(spans):
        if merged and start <= merged[-1][1] + MERGE_GAP:
            if stop > merged[-1][1]:
                merged[-1] = (merged[-1][0], stop, sentence)
        else:
            merged.append((start, stop, sentence))
    for _, stop, sentence in merged:
        if not END.search(sentence) or NOT_YET.search(sentence):
            reasons.append(f"waktu selesai {stop:%d-%m %H.%M} tanpa bukti ekstubasi, alat dilepas, atau meninggal")
    if merged and (later := _vent_after(record, merged[-1][1])):
        reasons.append(f"ada catatan ventilator sesudah waktu selesai: \"{later}\"")
    hours = sum((b - a).total_seconds() for a, b, _ in merged) / 3600 if merged else None
    return Check(not reasons, reasons, quotes_ok, hours, [(a, b) for a, b, _ in merged])


def judge(check: Check, reading: RmeReading, codes: set[str], claimed_hours: float) -> tuple[str, list[str]]:
    if not check.accepted:
        return "tidak_dapat_disimpulkan", check.reasons
    if reading.ventilasi_invasif == "tidak_jelas":
        return "tidak_dapat_disimpulkan", ["RME tidak menyebut jelas alat bantu napas"]
    if reading.ventilasi_invasif == "tidak":
        # A claim can sit in the ventilator population through its group alone (DEV: 118 honest J-1-20 claims coded 34.04).
        if not codes & (VENT_CODES | {"96.04"}) and not claimed_hours:
            return "mendukung", ["klaim tidak menagih intubasi atau ventilasi, dan RME juga tidak mencatat ventilasi invasif"]
        return "tidak_mendukung", [f"RME mencatat alat napas tertinggi {reading.alat_napas_tertinggi}, bukan ventilasi invasif"]
    if (claimed_hours >= LONG_HOURS or "96.72" in codes) and check.hours < LONG_HOURS - HOUR_SLACK:
        return "tidak_mendukung", [f"RME mencatat ventilasi {_hours(check.hours)} jam, klaim {LONG_HOURS} jam atau lebih"]
    return "mendukung", [f"RME mencatat ventilasi invasif {_hours(check.hours)} jam"]


def _inline(schema: dict) -> dict:
    defs = schema.pop("$defs", {})

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(defs[node["$ref"].split("/")[-1]])
            return {k: walk(v) for k, v in node.items() if k != "title"}
        return [walk(v) for v in node] if isinstance(node, list) else node
    return walk(schema)


SCHEMA = _inline(RmeReading.model_json_schema())


@dataclass
class LlmCall:
    reading: RmeReading | None
    error: str | None
    total_ms: int = 0
    prompt_tokens: int = 0
    output_tokens: int = 0


def call_ollama(text: str, model: str = MODEL) -> LlmCall:
    # Cloud models listed in the same Ollama would send the record off the laptop (CLAUDE.md: LLM lokal saja).
    if model.endswith(":cloud") or "-cloud" in model:
        raise ValueError(f"model awan ditolak: {model}")
    body = {"model": model, "stream": False, "think": False, "format": SCHEMA, "options": OPTIONS, "keep_alive": "30m",
            "messages": [{"role": "system", "content": PROMPT}, {"role": "user", "content": text}]}
    data = httpx.post(f"{OLLAMA}/api/chat", json=body, timeout=TIMEOUT).raise_for_status().json()
    call = LlmCall(None, None, int(data.get("total_duration", 0) / 1e6), data.get("prompt_eval_count", 0), data.get("eval_count", 0))
    if call.prompt_tokens >= NUM_CTX:
        call.error = "RME terpotong: melebihi konteks LLM"
        return call
    try:
        call.reading = RmeReading.model_validate_json(data["message"]["content"])
    except ValidationError:
        call.error = "keluaran LLM tidak sah terhadap skema"
    return call


def llm_enabled() -> bool:
    return os.environ.get("TAPAL_LLM", "on").lower() != "off"


@dataclass
class Result:
    verdict: str
    source: str
    quotes_verified: int
    reasons: list[str]
    hours: float | None
    reading: dict | None
    total_ms: int = 0
    prompt_tokens: int = 0
    output_tokens: int = 0
    second_reader: str | None = None
    sheet_hours: float | None = None
    held_by: list[str] = field(default_factory=list)


def cross_check(verdict: str, reasons: list[str], invasive: str, hours: float | None, second: str | None,
                sheet_hours: float | None, provenance: str | None = None, late: str | None = None) -> tuple[str, list[str], list[str]]:
    # The extra layers can only withhold a verdict, never create one; every layer that withholds is named for the T9 breakdown.
    if verdict == "tidak_dapat_disimpulkan":
        return verdict, reasons, ["bacaan"]
    held, why = [], []
    if provenance:
        held.append("asal_usul")
        why.append(f"asal-usul catatan meragukan: {provenance}")
    if late:
        held.append("jejak_waktu")
        why.append(f"dokumen kunci masa ventilasi ditulis terlambat: {late}")
    if sheet_hours is not None and hours is not None and hours >= SHEET_MIN_HOURS and sheet_hours < SHEET_SHARE * hours:
        held.append("fisiologi")
        why.append(f"lembar tanda vital hanya menunjukkan {sheet_hours:.0f} jam berventilasi dari {_hours(hours)} jam yang tertulis")
    if second is not None and second != invasive:
        held.append("asersi")
        why.append(f"model asersi membaca ventilasi invasif '{second}', bacaan RME '{invasive}'")
    return ("tidak_dapat_disimpulkan", reasons + why, held) if held else (verdict, reasons, [])


def sentences(record: Record) -> list[str]:
    return [s for _, text, _, _ in record.lines for s in _sentences(text)]


def read_rules(record: Record) -> RmeReading | None:
    # Keyword fallback: every quote is an exact sentence, but it tells plans and templates from facts less well than the LLM.
    present, starts, ends, found = [], [], [], {}
    for _, text, when, _ in record.lines:
        # Like the LLM, an untimed event takes the note time printed in its header.
        stamp = None if has_time(text) else f"{when:%Y-%m-%d %H:%M}"
        for s in _sentences(text):
            clear = NOT_PRESENT.search(s)
            if VENT.search(s) and not clear:
                present.append(s)
            t = parse_time(s, when)
            event = (t, s, s) if t else (when, stamp, s) if stamp else None
            if event and re.search(r"intubasi", s, re.I) and not clear:
                starts.append(event)
            if event and END.search(s) and not NOT_YET.search(s):
                ends.append(event)
            for name, pattern in DEVICES:
                if pattern.search(s) and not clear:
                    found.setdefault(name, s)
    quotes, episode = [{"fakta": "ventilator", "teks": s} for s in present[:2]], []
    if present and starts:
        first = min(starts)
        if stop := next((e for e in sorted(ends) if e[0] > first[0]), None):
            episode = [{"mulai": first[1], "selesai": stop[1]}]
            quotes += [{"fakta": "mulai", "teks": first[2]}, {"fakta": "selesai", "teks": stop[2]}]
    if present:
        device, invasive = "ventilator_invasif", "ya"
    else:
        device = next((n for n, _ in DEVICES if n in found), "tidak_jelas")
        invasive = "tidak_jelas" if device == "tidak_jelas" else "tidak"
        quotes += [{"fakta": "alat", "teks": found[device]}] if device in found else []
    if not quotes:
        return None
    return RmeReading(kutipan=quotes, alat_napas_tertinggi=device, ventilasi_invasif=invasive, mode_ventilator="", episode=episode)


RETRY_NOTE = ("\n\nCatatan pemeriksa: kutipan berikut tidak ditemukan persis di RME di atas: {quotes}. "
              "Salin setiap kutipan persis, kata per kata, dari RME; jangan meringkas atau mengubah ejaan.")


def _unmatched(reading: RmeReading, record: Record) -> list[str]:
    text = _norm(record.text)
    return [q.teks for q in reading.kutipan if not _norm(q.teks) or _norm(q.teks) not in text]


def read_claim(docs: pd.DataFrame, codes: set[str], claimed_hours: float, use_llm: bool | None = None, call=call_ollama,
               second=None, sheet_hours: float | None = None, provenance: str | None = None, late: str | None = None,
               retry: bool = True) -> Result:
    record = assemble(docs)
    opinion = second(sentences(record)) if second else None
    if use_llm is None:
        use_llm = llm_enabled()
    llm = None
    retried = False
    if use_llm:
        try:
            llm = call(record.text)
            # One retry when a quote is not found verbatim, telling the model which ones; the second answer is checked the same way.
            if retry and llm.reading is not None and (missing := _unmatched(llm.reading, record)):
                again = call(record.text + RETRY_NOTE.format(quotes="; ".join(f'"{q}"' for q in missing)))
                again.total_ms += llm.total_ms
                llm, retried = (again, True) if again.reading is not None else (llm, False)
        except (httpx.HTTPError, OSError):
            llm = None
    if llm is None:
        note = "LLM tidak tersedia; aturan kata kunci, keyakinan lebih rendah"
        if (reading := read_rules(record)) is None:
            return Result("tidak_dapat_disimpulkan", "aturan", 0, [note, "aturan kata kunci tidak menemukan sebutan alat napas"], None, None,
                          second_reader=opinion, sheet_hours=sheet_hours, held_by=["bacaan"])
        check = check_reading(reading, record)
        verdict, reasons, held = cross_check(*judge(check, reading, codes, claimed_hours), reading.ventilasi_invasif, check.hours, opinion,
                                             sheet_hours, provenance, late)
        return Result(verdict, "aturan", check.quotes_ok, [note] + reasons, check.hours, reading.model_dump(), second_reader=opinion,
                      sheet_hours=sheet_hours, held_by=held)
    if llm.reading is None:
        return Result("tidak_dapat_disimpulkan", "llm_lokal", 0, [llm.error], None, None, llm.total_ms, llm.prompt_tokens, llm.output_tokens,
                      opinion, sheet_hours, ["bacaan"])
    check = check_reading(llm.reading, record)
    verdict, reasons, held = cross_check(*judge(check, llm.reading, codes, claimed_hours), llm.reading.ventilasi_invasif, check.hours, opinion,
                                         sheet_hours, provenance, late)
    reasons = (["dibaca ulang sekali karena kutipan pertama tidak cocok"] if retried else []) + reasons
    return Result(verdict, "llm_lokal", check.quotes_ok, reasons, check.hours, llm.reading.model_dump(), llm.total_ms, llm.prompt_tokens,
                  llm.output_tokens, opinion, sheet_hours, held)
