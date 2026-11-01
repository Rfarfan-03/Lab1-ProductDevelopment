"""Escritura atómica de archivos (base de la idempotencia).

Se escribe primero a un temporal en el mismo directorio y luego se reemplaza el
destino con ``os.replace``: una tarea interrumpida nunca deja un archivo a medias.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any

import pandas as pd


def _tmp(ruta: Path) -> Path:
    return ruta.with_name(f".{ruta.name}.tmp{os.getpid()}")


def escribir_parquet(df: pd.DataFrame, ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp(ruta)
    df.to_parquet(tmp, index=False)
    os.replace(tmp, ruta)


def escribir_csv(df: pd.DataFrame, ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp(ruta)
    df.to_csv(tmp, index=False)
    os.replace(tmp, ruta)


def escribir_json(datos: Any, ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp(ruta)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=2, ensure_ascii=False, default=str, sort_keys=True)
    os.replace(tmp, ruta)


def leer_json(ruta: Path) -> Any:
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def copiar(origen: Path, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp(destino)
    shutil.copyfile(origen, tmp)
    os.replace(tmp, destino)


def reemplazar_directorio(nuevo: Path, destino: Path) -> None:
    """Sustituye ``destino`` por ``nuevo`` (ambos en el mismo disco)."""
    if destino.exists():
        viejo = destino.with_name(f".{destino.name}.old{os.getpid()}")
        os.replace(destino, viejo)
        os.replace(nuevo, destino)
        shutil.rmtree(viejo)
    else:
        destino.parent.mkdir(parents=True, exist_ok=True)
        os.replace(nuevo, destino)


def hash_archivo(ruta: Path) -> str:
    h = hashlib.md5()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()
