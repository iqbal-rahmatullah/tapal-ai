import re
from dataclasses import dataclass
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline, make_pipeline, make_union

from engine.ai2 import OLLAMA, _sentences

EMBED_MODEL = "bge-m3"
SEED = 0
HEADS = ("sebutan", "alat", "asersi")
_CACHE: dict[str, dict[str, np.ndarray]] = {}


def load_embeddings(vectors: Path, texts: Path, model: str = EMBED_MODEL) -> None:
    # Embedding the 64k DEV training sentences takes hours on the laptop, so they are computed once and reused.
    _CACHE.setdefault(model, {}).update(zip(pd.read_parquet(texts).teks, np.load(vectors)))


class OllamaEmbedding(BaseEstimator, TransformerMixin):
    # Runs on the local Ollama like the LLM, so no sentence leaves the laptop.
    def __init__(self, model: str = EMBED_MODEL, batch: int = 128):
        self.model, self.batch = model, batch

    def fit(self, X, y=None):
        return self

    def transform(self, X) -> np.ndarray:
        cache = _CACHE.setdefault(self.model, {})
        texts = list(X)
        todo = sorted({t for t in texts if t not in cache})
        for i in range(0, len(todo), self.batch):
            part = todo[i:i + self.batch]
            r = httpx.post(f"{OLLAMA}/api/embed", json={"model": self.model, "input": part, "keep_alive": "30m"}, timeout=600)
            cache.update(zip(part, np.asarray(r.raise_for_status().json()["embeddings"], dtype=np.float32)))
        return np.vstack([cache[t] for t in texts])


def features(backend: str):
    if backend == "embedding":
        return OllamaEmbedding()
    return make_union(TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=2, sublinear_tf=True),
                      TfidfVectorizer(analyzer="word", ngram_range=(1, 2), sublinear_tf=True, token_pattern=r"(?u)\b\w+\b"))


def classifier(backend: str) -> Pipeline:
    return make_pipeline(features(backend), LogisticRegression(max_iter=3000, class_weight="balanced", C=4.0, random_state=SEED))


def training_sentences(docs: pd.DataFrame, labelled: pd.DataFrame, style: pd.Series) -> pd.DataFrame:
    # Labelled sentences mention a breathing device; the rest of each note, split into sentences, is the "no mention" class.
    by_doc = labelled.groupby("dokumen_id").teks.agg(list).to_dict()
    rest = []
    for doc_id, sep, text in docs[["dokumen_id", "nomor_sep", "teks"]].itertuples(index=False):
        for s in by_doc.get(doc_id, []):
            text = text.replace(s, " ")
        rest += [(s.strip(), sep) for s in _sentences(text) if re.search(r"[A-Za-z]{3}", s)]
    negative = pd.DataFrame(rest, columns=["teks", "nomor_sep"]).assign(sebutan=False, alat="", asersi="")
    positive = labelled.assign(sebutan=True)[["teks", "nomor_sep", "sebutan", "alat", "asersi"]]
    out = pd.concat([positive, negative], ignore_index=True)
    out["gaya"] = style.reindex(out.nomor_sep).to_numpy()
    return out.drop_duplicates(["teks", "sebutan", "alat", "asersi", "gaya"]).reset_index(drop=True)


@dataclass
class AssertionReader:
    mention: Pipeline
    device: Pipeline
    assertion: Pipeline

    @classmethod
    def fit(cls, data: pd.DataFrame, backend: dict[str, str]) -> "AssertionReader":
        m = data[data.sebutan]
        return cls(classifier(backend["sebutan"]).fit(data.teks, data.sebutan), classifier(backend["alat"]).fit(m.teks, m.alat),
                   classifier(backend["asersi"]).fit(m.teks, m.asersi))

    def read(self, sentences: list[str]) -> pd.DataFrame:
        out = pd.DataFrame({"teks": sentences, "sebutan": False, "alat": "", "asersi": ""})
        if not sentences:
            return out
        out["sebutan"] = self.mention.predict(sentences).astype(bool)
        if out.sebutan.any():
            hit = out.teks[out.sebutan].tolist()
            out.loc[out.sebutan, "alat"] = self.device.predict(hit)
            out.loc[out.sebutan, "asersi"] = self.assertion.predict(hit)
        return out


def ventilation(read: pd.DataFrame) -> str:
    present = read[read.sebutan & (read.asersi == "terpasang")]
    if (present.alat == "ventilator_invasif").any():
        return "ya"
    return "tidak" if len(present) else "tidak_jelas"
