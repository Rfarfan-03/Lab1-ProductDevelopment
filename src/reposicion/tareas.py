"""Puntos de entrada que llaman los DAGs de Airflow (una función por tarea).

Cada función recibe la fecha de la ejecución (``ds``), carga la configuración y delega en
los módulos de lógica. Devuelven diccionarios pequeños (se guardan como XCom).
"""

from __future__ import annotations

import logging

import pandas as pd

from .config import Config, cargar_config

log = logging.getLogger(__name__)

DIAS_EXTRA_OPERACION = 3  # días después de la última venta para recibir entregas tardías


def _ultima_fecha_train(cfg: Config) -> pd.Timestamp | None:
    """Lee la última fecha de train.csv leyendo solo el final del archivo."""
    ruta = cfg.ruta("kaggle") / "train.csv"
    if not ruta.exists():
        return None
    with open(ruta, "rb") as f:
        encabezado = f.readline().decode().strip().split(",")
        f.seek(0, 2)
        f.seek(max(0, f.tell() - 4096))
        ultima = f.read().decode(errors="ignore").strip().splitlines()[-1].split(",")
    return pd.Timestamp(ultima[encabezado.index("date")])


def rango_operacion(cfg: Config | None = None) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Primer y último día que el flujo diario debe procesar, derivados de los datos.

    Va desde el día siguiente al fin de la carga histórica hasta unos días después de la
    última venta. Si aún no hay datos, devuelve un rango por defecto (el DAG igual se puede
    cargar y la primera tarea informará que faltan los archivos).
    """
    from .simulador import calcular_fecha_fin_historico

    cfg = cfg or cargar_config()
    fecha_max = _ultima_fecha_train(cfg)
    if fecha_max is None:
        return pd.Timestamp("2017-07-02"), pd.Timestamp("2017-08-18")
    fin_hist = calcular_fecha_fin_historico(cfg, fecha_max)
    return fin_hist + pd.Timedelta(days=1), fecha_max + pd.Timedelta(days=DIAS_EXTRA_OPERACION)


# ------------------------------------------------------------------ tareas

def simular_origen() -> dict:
    from .simulador import simular

    meta = simular(cargar_config())
    return {"fecha_fin_historico": meta["fecha_fin_historico"], "archivos": meta["archivos_por_fuente"]}


def ingerir(ds: str) -> dict:
    from .ingesta import ingerir as _ingerir

    rep = _ingerir(cargar_config(), ds)
    rechazados = {f: len(v["rechazados"]) for f, v in rep["fuentes"].items() if v["rechazados"]}
    if rechazados:
        log.warning("Archivos en cuarentena en %s: %s", ds, rechazados)
    return {"rechazados": rechazados, "faltantes": rep["faltantes"]}


def es_dia_pronostico(ds: str) -> bool:
    from .entrenamiento import es_dia_pronostico as _es

    return _es(cargar_config(), ds)


def preparar(ds: str) -> dict:
    from .features import preparar as _preparar

    meta = _preparar(cargar_config(), ds)
    return {k: meta[k] for k in ("filas_entrenamiento", "filas_prediccion")}


def entrenar(ds: str) -> dict:
    from .entrenamiento import entrenar as _entrenar

    info = _entrenar(cargar_config(), ds)
    return info["decision"]


def pronosticar(ds: str) -> dict:
    from .pronostico import pronosticar as _pronosticar

    meta = _pronosticar(cargar_config(), ds)
    return {k: meta[k] for k in ("modelo", "horizonte", "pedido_total")}


def dar_seguimiento(ds: str) -> int:
    from .seguimiento import seguimiento

    return int(len(seguimiento(cargar_config(), ds)))
