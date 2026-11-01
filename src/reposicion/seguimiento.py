"""Seguimiento del desempeño: pronósticos y pedidos publicados vs. ventas reales.

Se ejecuta a diario con las ventas conocidas a esa fecha (incluidas las correcciones ya
recibidas), así que las métricas de un corte se van completando y corrigiendo con el
tiempo.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import archivos as io
from .config import Config
from .evaluacion import wape
from .ingesta import cargar_asof
from .modelos import agregar_semana
from .pedido import LLAVE, costo_newsvendor, costos_por_fila
from .reportes import reporte_seguimiento


def _publicados(cfg: Config, fecha: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame]:
    raiz = cfg.ruta("publicados")
    carpetas = sorted(p for p in raiz.glob("corte=*") if (p / "metadata.json").exists()) if raiz.exists() else []
    carpetas = [p for p in carpetas if pd.Timestamp(p.name.split("=")[1]) <= fecha]
    if not carpetas:
        return pd.DataFrame(), pd.DataFrame()
    pron = pd.concat([pd.read_parquet(p / "pronostico.parquet") for p in carpetas], ignore_index=True)
    ped = pd.concat([pd.read_parquet(p / "pedido.parquet") for p in carpetas], ignore_index=True)
    return pron, ped


def seguimiento(cfg: Config, fecha) -> pd.DataFrame:
    fecha = pd.Timestamp(fecha)
    horizonte = int(cfg["operacion"]["horizonte_dias"])
    pron, ped = _publicados(cfg, fecha)
    destino = cfg.ruta("seguimiento") / f"fecha={fecha.strftime('%Y-%m-%d')}"
    if pron.empty:
        res = pd.DataFrame(columns=["corte"])
    else:
        reales = cargar_asof(cfg, fecha, "ventas").rename(columns={"sales": "y"})
        reales = reales[reales["date"] < fecha]
        d = pron.merge(reales, on=["date", "store_nbr", "family"], how="left")
        filas = []
        for corte, g in d.groupby("corte"):
            con_real = g[g["y"].notna()]
            fila = {"corte": corte, "modelo": g["modelo"].iloc[0], "dias_con_real": int(con_real["date"].nunique())}
            if not con_real.empty:
                y, yhat = con_real["y"].to_numpy(), con_real["yhat"].to_numpy()
                fila.update(wape=wape(y, yhat), sesgo=float((yhat - y).sum() / max(y.sum(), 1e-9)),
                            cobertura_p10_p90=float(((y >= con_real["p10"]) & (y <= con_real["p90"])).mean()))
            semana = agregar_semana(g, horizonte)
            if not semana.empty:  # semana completa: se evalúa el pedido
                s = semana.merge(ped[LLAVE + ["pedido"]], on=LLAVE)
                cu, co = costos_por_fila(s["family"], cfg)
                Y, O = s["Y"].to_numpy(), s["pedido"].to_numpy()
                costo = costo_newsvendor(Y, O, cu, co)
                fila.update(
                    costo_negocio=float(costo.sum()),
                    costo_por_unidad_vendida=float(costo.sum() / max(Y.sum(), 1e-9)),
                    nivel_servicio=float(np.minimum(Y, O).sum() / max(Y.sum(), 1e-9)),
                    sobrante_pct=float(np.maximum(O - Y, 0).sum() / max(O.sum(), 1e-9)),
                )
            filas.append(fila)
        res = pd.DataFrame(filas)
    io.escribir_parquet(res, destino / "seguimiento.parquet")
    # El reporte muestra la fecha más reciente: re-ejecutar un día pasado (backfill) no lo retrocede.
    fechas = [pd.Timestamp(p.name.split("=")[1]) for p in cfg.ruta("seguimiento").glob("fecha=*")]
    if fecha >= max(fechas):
        reporte_seguimiento(cfg, res, fecha)
    return res
