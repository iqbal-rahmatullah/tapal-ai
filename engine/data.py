# The only gate to the worlds: data/test and data/sealed stay closed until task 720 (TARGETS v2 bagian 3).
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEV = ROOT / "data" / "dev"
BLOCKED = ("test", "sealed")


class BlindTestError(PermissionError):
    pass


def load_world(path: Path, with_key: bool = False) -> dict[str, pd.DataFrame]:
    path = Path(path).resolve()
    if any(path.is_relative_to((ROOT / "data" / b).resolve()) for b in BLOCKED):
        raise BlindTestError(f"{path} is part of the blind test; it opens only at task 720")
    out = {name: pd.read_parquet(path / f"{name}.parquet") for name in ("claims", "hospitals")}
    if with_key:
        out |= {name: pd.read_parquet(path / "key" / f"{name}.parquet") for name in ("key_claims", "key_hospitals", "key_placebo_claims")}
    return out
