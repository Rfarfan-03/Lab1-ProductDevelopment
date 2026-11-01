"""Métricas técnicas, métrica de negocio y criterio de reemplazo del modelo vigente.

Validación temporal (igual para todos los modelos): los últimos ``semanas_validacion``
cortes semanales anteriores al corte actual. Cada modelo se entrena solo con cortes
previos a esa ventana. Dentro de la ventana, la primera mitad calibra los residuos
(cuantiles) y la segunda mitad mide cobertura y costo de negocio fuera de muestra.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Config
from .modelos import agregar_semana, aplicar_cuantil, residuos
from .pedido import LLAVE, costo_newsvendor, costos_por_fila, pedido_semanal


def wape(y: np.ndarray, yhat: np.ndarray) -> float:
    return float(np.abs(y - yhat).sum() / max(np.abs(y).sum(), 1e-9))


def evaluar(pred_val: pd.DataFrame, cfg: Config) -> dict:
    """``pred_val``: filas (corte, store_nbr, family, date, y, yhat) de la ventana de validación."""
    horizonte = int(cfg["operacion"]["horizonte_dias"])
    d = pred_val[pred_val["y"].notna()]
    cortes = sorted(d["corte"].unique())
    calib = d[d["corte"].isin(cortes[: len(cortes) // 2])]
    ev = d[d["corte"].isin(cortes[len(cortes) // 2 :])]
    tablas = residuos(calib, horizonte)

    p10 = aplicar_cuantil(ev["yhat"].to_numpy(), ev["family"], tablas["diarios"], 0.1)
    p90 = aplicar_cuantil(ev["yhat"].to_numpy(), ev["family"], tablas["diarios"], 0.9)
    y_ev = ev["y"].to_numpy()

    reales = agregar_semana(ev, horizonte)
    ped = pedido_semanal(ev, tablas["semanales"], cfg).merge(reales[LLAVE + ["Y"]], on=LLAVE)
    cu, co = costos_por_fila(ped["family"], cfg)
    costo = costo_newsvendor(ped["Y"].to_numpy(), ped["pedido"].to_numpy(), cu, co)

    return {
        "wape": wape(d["y"].to_numpy(), d["yhat"].to_numpy()),
        "sesgo": float((d["yhat"] - d["y"]).sum() / max(d["y"].sum(), 1e-9)),
        "cobertura_p10_p90": float(((y_ev >= p10) & (y_ev <= p90)).mean()),
        "costo_negocio": float(costo.sum()),
        "costo_por_unidad_vendida": float(costo.sum() / max(ped["Y"].sum(), 1e-9)),
        "cortes_validacion": [pd.Timestamp(c).strftime("%Y-%m-%d") for c in cortes],
    }


def decidir(metricas: dict[str, dict], vigente_anterior: str, criterio: dict) -> dict:
    """El mejor retador reemplaza al vigente si baja el costo de negocio al menos
    ``mejora_minima_costo`` (relativo) y no empeora el WAPE más que ``tolerancia_wape``."""
    vig = metricas[vigente_anterior]
    retadores = {n: m for n, m in metricas.items() if n != vigente_anterior}
    mejor = min(retadores, key=lambda n: retadores[n]["costo_negocio"])
    m = retadores[mejor]
    mejora = 1 - m["costo_negocio"] / max(vig["costo_negocio"], 1e-9)
    reemplaza = mejora >= criterio["mejora_minima_costo"] and m["wape"] <= vig["wape"] + criterio["tolerancia_wape"]
    return {
        "vigente_anterior": vigente_anterior,
        "retador": mejor,
        "mejora_costo": float(mejora),
        "reemplaza": bool(reemplaza),
        "vigente": mejor if reemplaza else vigente_anterior,
    }
