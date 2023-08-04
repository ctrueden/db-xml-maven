from pathlib import Path
from typing import Union


def read(p: Path, mode: str) -> Union[str, bytes]:
    with open(p, mode) as f:
        return f.read()


def text(p: Path) -> str:
    return read(p, "r")


def binary(p: Path) -> bytes:
    return read(p, "rb")
