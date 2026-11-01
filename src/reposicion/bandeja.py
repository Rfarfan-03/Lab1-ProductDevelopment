"""Formato de la bandeja (sistema de origen simulado).

Estructura::

    data/bandeja/<fuente>/<fecha_dato>__entrega_<fecha_entrega>__v<version>.csv

- ``fecha_dato``: día al que corresponden los datos.
- ``fecha_entrega``: día en que el archivo queda disponible para el flujo.
- ``version``: 1 para la entrega original; >1 para correcciones.

El flujo solo lee la bandeja; nunca la modifica.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

FUENTES = ("ventas", "promociones", "transacciones", "petroleo", "feriados")

# Columnas de cada fuente (mismos nombres que Kaggle) y su llave natural.
COLUMNAS = {
    "ventas": ["date", "store_nbr", "family", "sales"],
    "promociones": ["date", "store_nbr", "family", "onpromotion"],
    "transacciones": ["date", "store_nbr", "transactions"],
    "petroleo": ["date", "dcoilwtico"],
    "feriados": ["date", "type", "locale", "locale_name", "description", "transferred"],
}
LLAVES = {
    "ventas": ["date", "store_nbr", "family"],
    "promociones": ["date", "store_nbr", "family"],
    "transacciones": ["date", "store_nbr"],
    "petroleo": ["date"],
    "feriados": ["date", "locale_name", "description"],
}

_PATRON = re.compile(
    r"^(?P<fecha>\d{4}-\d{2}-\d{2})__entrega_(?P<entrega>\d{4}-\d{2}-\d{2})__v(?P<version>\d+)\.csv$"
)


@dataclass(frozen=True)
class ArchivoBandeja:
    fuente: str
    fecha_dato: pd.Timestamp
    fecha_entrega: pd.Timestamp
    version: int
    ruta: Path


def nombre_archivo(fecha_dato, fecha_entrega, version: int = 1) -> str:
    f = pd.Timestamp(fecha_dato).strftime("%Y-%m-%d")
    e = pd.Timestamp(fecha_entrega).strftime("%Y-%m-%d")
    return f"{f}__entrega_{e}__v{version}.csv"


def listar(raiz: Path) -> list[ArchivoBandeja]:
    """Lista los archivos de la bandeja. Ignora (con aviso) nombres que no siguen el formato."""
    archivos = []
    for fuente in FUENTES:
        carpeta = raiz / fuente
        if not carpeta.is_dir():
            continue
        for ruta in sorted(carpeta.iterdir()):
            m = _PATRON.match(ruta.name)
            if not m:
                log.warning("Archivo con nombre no reconocido en la bandeja, se ignora: %s", ruta)
                continue
            archivos.append(
                ArchivoBandeja(
                    fuente=fuente,
                    fecha_dato=pd.Timestamp(m["fecha"]),
                    fecha_entrega=pd.Timestamp(m["entrega"]),
                    version=int(m["version"]),
                    ruta=ruta,
                )
            )
    return archivos


def disponibles(archivos: list[ArchivoBandeja], corte) -> dict[tuple[str, pd.Timestamp], list[ArchivoBandeja]]:
    """Agrupa por (fuente, fecha_dato) los archivos entregados hasta ``corte`` (inclusive).

    Cada lista viene ordenada de la versión más reciente a la más antigua.
    """
    corte = pd.Timestamp(corte)
    grupos: dict[tuple[str, pd.Timestamp], list[ArchivoBandeja]] = {}
    for a in archivos:
        if a.fecha_entrega <= corte:
            grupos.setdefault((a.fuente, a.fecha_dato), []).append(a)
    for lista in grupos.values():
        lista.sort(key=lambda a: (a.version, a.fecha_entrega), reverse=True)
    return grupos
