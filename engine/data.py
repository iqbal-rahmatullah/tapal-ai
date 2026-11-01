# The only gate to the worlds: data/test and data/sealed stay closed until task 720 (TARGETS v2 bagian 3).
import os
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEV = ROOT / "data" / "dev"
LAB = ROOT.parent / "tapal-percobaan"
BLOCKED = ("test", "sealed")
# Set only after the freeze hash is recorded and the user gives the go-ahead at task 720; nothing else opens the blind folders.
UNSEAL_VAR, UNSEAL_VALUE = "TAPAL_BUKA_SEGEL", "720"


class BlindTestError(PermissionError):
    pass


def world_dir() -> Path:
    # One runner serves DEV and every blind condition; the world comes from the environment and defaults to DEV dasar.
    return Path(os.environ.get("TAPAL_DUNIA", DEV / "dasar"))


def key_dir() -> Path:
    return Path(os.environ.get("TAPAL_KUNCI", world_dir() / "key"))


def is_dev() -> bool:
    return world_dir().resolve() == (DEV / "dasar").resolve()


def sibling(name: str) -> tuple[Path, Path]:
    # Other conditions of a set sit next to its main world; a DEV key lives inside its world, a blind key in a tree of its own.
    world, key = world_dir(), key_dir()
    other = world.parent / name
    return other, (other / "key" if key.resolve() == (world / "key").resolve() else key.parent / name)


def canonical_dev() -> bool:
    # Only the plain DEV run may refresh the app's frozen artefacts; a DEV dry run with its own output folder writes beside its results.
    return is_dev() and "TAPAL_KELUARAN" not in os.environ


def label() -> str:
    return "DEV dasar" if is_dev() else f"{world_dir().parent.name} {world_dir().name}"


def out_dir(name: str) -> Path:
    base = os.environ.get("TAPAL_KELUARAN")
    return Path(base) / name if base else LAB / name


def opened(path: Path) -> Path:
    path = Path(path).resolve()
    if any(path.is_relative_to((ROOT / "data" / b).resolve()) for b in BLOCKED) and os.environ.get(UNSEAL_VAR) != UNSEAL_VALUE:
        raise BlindTestError(f"{path} is part of the blind test; it opens only at task 720")
    return path


def load_world(path: Path, with_key: bool = False, key: Path | None = None) -> dict[str, pd.DataFrame]:
    path = opened(path)
    out = {name: pd.read_parquet(path / f"{name}.parquet") for name in ("claims", "hospitals")}
    if with_key:
        k = opened(key if key is not None else path / "key")
        out |= {name: pd.read_parquet(k / f"{name}.parquet") for name in ("key_claims", "key_hospitals", "key_placebo_claims")}
    return out
