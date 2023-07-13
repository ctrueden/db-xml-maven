from pathlib import Path


def read(p: Path, mode: str):
    with open(p, mode) as f:
        return f.read()


def text(p: Path) -> str:
    return read(p, "r")


def binary(p: Path) -> bytes:
    return read(p, "rb")
