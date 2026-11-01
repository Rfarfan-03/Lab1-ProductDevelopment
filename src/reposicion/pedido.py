"""Pedido sugerido (newsvendor) y su costo de negocio.

El pedido de cada tienda-familia para la semana del horizonte es el cuantil crítico
``cu / (cu + co)`` de la demanda semanal pronosticada. No hay datos de inventario en
la fuente, así que se asume inventario inicial cero (el pedido cubre la demanda).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Config
from .modelos import aplicar_cuantil

LLAVE = ["corte", "store_nbr", "family"]


def costos_por_fila(familias: pd.Series, cfg: Config) -> tuple[np.ndarray, np.ndarray]:
    unicos = {f: cfg.costos_familia(f) for f in familias.unique()}
    cu = familias.map({f: c.costo_quiebre for f, c in unicos.items()}).to_numpy(dtype=float)
    co = familias.map({f: c.costo_merma for f, c in unicos.items()}).to_numpy(dtype=float)
    return cu, co


def pedido_semanal(pred: pd.DataFrame, tabla_semanal: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """``pred`` tiene una fila por (corte, tienda, familia, fecha) con ``yhat``."""
    g = pred.groupby(LLAVE, as_index=False).agg(
        semana_inicio=("date", "min"), semana_fin=("date", "max"), pronostico_semana=("yhat", "sum")
    )
    cu, co = costos_por_fila(g["family"], cfg)
    g["cuantil_critico"] = cu / (cu + co)
    g["pedido"] = np.round(aplicar_cuantil(g["pronostico_semana"].to_numpy(), g["family"], tabla_semanal,
                                           g["cuantil_critico"].to_numpy()), 2)
    return g


def costo_newsvendor(real: np.ndarray, pedido: np.ndarray, cu: np.ndarray, co: np.ndarray) -> np.ndarray:
    """Costo por quiebre (demanda no cubierta) + costo por merma (sobrante)."""
    return cu * np.maximum(real - pedido, 0) + co * np.maximum(pedido - real, 0)
