import io
import re
import tokenize
from pathlib import Path

from engine.synth import rme

ROOT = Path(__file__).resolve().parents[1]
HELD_OUT = "campur_inggris"
# Words in the held-out templates that are generic English or Indonesian (or shared Indonesian month abbreviations)
# and say nothing about the style itself.
GENERIC = {"from", "not", "now", "one", "use", "while", "with", "done", "size", "still", "start", "kalau", "air", "support",
           "failed", "needed", "connected", "desaturasi", "jan", "feb", "mar", "apr", "jun", "jul", "sep", "nov"}
TEXT_SUFFIXES = {".txt", ".json", ".yaml", ".yml", ".md", ".jinja", ".j2", ".prompt", ".toml", ".csv"}


def words(texts) -> set[str]:
    return {w.lower() for t in texts for w in re.findall(r"[A-Za-z]{3,}", t)}


def held_out_vocabulary() -> set[str]:
    style = lambda keep: words(v for kind in rme.T.values() for s, vs in kind.items() if keep(s) for v in vs) | words(
        n for s, d in rme.DEVICE_NAME.items() if keep(s) for n in d.values())
    other = style(lambda s: s != HELD_OUT) | words(rme.MONTHS_ID[1:])
    return (style(lambda s: s == HELD_OUT) | words(rme.MONTHS_EN[1:])) - other - GENERIC


def scanned_text(path: Path) -> str:
    # In Python files only string literals can carry vocabulary or rules; comments and names are left alone.
    if path.suffix != ".py":
        return path.read_text(errors="ignore")
    kinds = {tokenize.STRING, tokenize.FSTRING_MIDDLE}
    return " ".join(t.string for t in tokenize.generate_tokens(io.StringIO(path.read_text()).readline) if t.type in kinds)


def test_engines_hold_no_vocabulary_of_the_held_out_style():
    # TARGETS v2 bagian 3 aturan 4: AI 2, its LLM prompts, and its keyword lists may not use the held-out style.
    vocab = held_out_vocabulary()
    assert {"extubated", "intubated", "tracheostomy", "oct"} <= vocab
    hits = {}
    for base in ("engine", "api"):
        for f in (ROOT / base).rglob("*"):
            rel = f.relative_to(ROOT)
            if f.is_file() and "synth" not in rel.parts and (f.suffix == ".py" or f.suffix in TEXT_SUFFIXES):
                found = vocab & words([scanned_text(f)])
                if found:
                    hits[str(rel)] = sorted(found)
    assert not hits
