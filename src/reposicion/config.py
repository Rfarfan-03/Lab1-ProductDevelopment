"""Carga de la configuración del producto.

La configuración vive en ``config/config.yaml`` (versionada en Git). Se puede
apuntar a otro archivo con la variable de entorno ``REPOSICION_CONFIG`` y a otra
raíz de proyecto con ``REPOSICION_ROOT``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

RAIZ_REPO = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Costos:
    costo_quiebre: float
    costo_merma: float

    @property
    def cuantil_critico(self) -> float:
        """Cuantil óptimo del problema newsvendor: cu / (cu + co)."""
        return self.costo_quiebre / (self.costo_quiebre + self.costo_merma)


class Config:
    """Envoltorio liviano sobre el diccionario de configuración."""

    def __init__(self, datos: dict[str, Any], raiz: Path):
        self.datos = datos
        self.raiz = raiz
        _validar(datos)

    def __getitem__(self, clave: str) -> Any:
        return self.datos[clave]

    def ruta(self, nombre: str) -> Path:
        """Ruta absoluta de una entrada de ``rutas``."""
        return (self.raiz / self.datos["rutas"][nombre]).resolve()

    def costos_familia(self, familia: str) -> Costos:
        c = dict(self.datos["costos"]["default"])
        c.update(self.datos["costos"].get("por_familia", {}).get(familia, {}))
        return Costos(float(c["costo_quiebre"]), float(c["costo_merma"]))


def _validar(d: dict[str, Any]) -> None:
    for seccion in ("rutas", "simulacion", "operacion", "validacion", "modelo", "costos"):
        if seccion not in d:
            raise ValueError(f"Falta la sección '{seccion}' en la configuración")
    if d["operacion"]["horizonte_dias"] < 1:
        raise ValueError("horizonte_dias debe ser >= 1")
    if not 0 <= d["operacion"]["dia_pronostico"] <= 6:
        raise ValueError("dia_pronostico debe estar entre 0 (lunes) y 6 (domingo)")
    for q in d["operacion"]["cuantiles"]:
        if not 0 < q < 1:
            raise ValueError(f"Cuantil fuera de (0, 1): {q}")
    todos = [d["costos"]["default"], *d["costos"].get("por_familia", {}).values()]
    for c in todos:
        for k in ("costo_quiebre", "costo_merma"):
            if k in c and float(c[k]) <= 0:
                raise ValueError(f"{k} debe ser positivo")


def cargar_config(ruta: str | os.PathLike | None = None) -> Config:
    raiz = Path(os.environ.get("REPOSICION_ROOT", RAIZ_REPO))
    ruta = Path(ruta or os.environ.get("REPOSICION_CONFIG", raiz / "config" / "config.yaml"))
    with open(ruta, encoding="utf-8") as f:
        datos = yaml.safe_load(f)
    return Config(datos, raiz)
