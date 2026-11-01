"""Entrenamiento semanal: backtest de candidatos, decisión de reemplazo y artefactos del vigente.

Los artefactos quedan en ``modelos/corte=<fecha>/`` y dependen solo de los datos as-of
ese corte y de la decisión del corte de entrenamiento anterior, así que re-ejecutar un
corte (backfill) reproduce el mismo resultado.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from . import archivos as io
from .config import Config
from .evaluacion import decidir, evaluar
from .features import cargar_datos, construir, cortes_entrenamiento
from .modelos import crear_modelo, residuos
from .reportes import reporte_comparacion

log = logging.getLogger(__name__)

CANDIDATOS = ("baseline", "lightgbm")
VIGENTE_INICIAL = "baseline"


def _f(fecha) -> str:
    return pd.Timestamp(fecha).strftime("%Y-%m-%d")


def es_dia_pronostico(cfg: Config, fecha) -> bool:
    return pd.Timestamp(fecha).dayofweek == int(cfg["operacion"]["dia_pronostico"])


def ruta_modelo(cfg: Config, corte) -> Path:
    return cfg.ruta("modelos") / f"corte={_f(corte)}"


def cortes_con_modelo(cfg: Config) -> list[pd.Timestamp]:
    raiz = cfg.ruta("modelos")
    if not raiz.exists():
        return []
    return sorted(pd.Timestamp(p.name.split("=")[1]) for p in raiz.glob("corte=*") if (p / "entrenamiento.json").exists())


def vigente_anterior(cfg: Config, corte) -> str:
    previos = [c for c in cortes_con_modelo(cfg) if c < pd.Timestamp(corte)]
    if not previos:
        return VIGENTE_INICIAL
    return io.leer_json(ruta_modelo(cfg, previos[-1]) / "entrenamiento.json")["decision"]["vigente"]


def entrenar(cfg: Config, corte) -> dict:
    corte = pd.Timestamp(corte)
    mcfg = cfg["modelo"]
    horizonte = int(cfg["operacion"]["horizonte_dias"])
    n_val = int(mcfg["semanas_validacion"])

    datos = cargar_datos(cfg, corte)
    cortes = cortes_entrenamiento(corte, int(mcfg["semanas_entrenamiento"]) + n_val, horizonte,
                                  datos.ventas["date"].min())
    if len(cortes) < n_val + 4:
        raise ValueError(f"Historia insuficiente para entrenar en {_f(corte)}: {len(cortes)} cortes")
    df = construir(datos, cortes, horizonte, con_objetivo=True)
    es_val = df["corte"].isin(cortes[-n_val:])
    entren, valid = df[~es_val], df[es_val]

    metricas, preds = {}, {}
    for nombre in CANDIDATOS:
        modelo = crear_modelo(nombre, mcfg).ajustar(entren)
        preds[nombre] = valid[["corte", "store_nbr", "family", "date", "y"]].assign(yhat=modelo.predecir(valid))
        metricas[nombre] = evaluar(preds[nombre], cfg)
        log.info("Backtest %s en %s: %s", nombre, _f(corte), metricas[nombre])

    decision = decidir(metricas, vigente_anterior(cfg, corte), mcfg["criterio_reemplazo"])
    vigente = decision["vigente"]
    log.info("Decisión de modelo en %s: %s", _f(corte), decision)

    destino = ruta_modelo(cfg, corte)
    if vigente == "lightgbm":  # el vigente se re-entrena con toda la historia (incluida la validación)
        crear_modelo("lightgbm", mcfg).ajustar(df).guardar(destino / "modelo_lightgbm.txt")
    tablas = residuos(preds[vigente], horizonte)
    for tipo, tabla in tablas.items():
        io.escribir_parquet(tabla.reset_index(names="family"), destino / f"residuos_{tipo}.parquet")

    info = {
        "corte": _f(corte),
        "metricas": metricas,
        "decision": decision,
        "cortes_entrenamiento": [_f(cortes[0]), _f(cortes[-n_val - 1])],
        "filas_entrenamiento": int(entren["y"].notna().sum()),
    }
    io.escribir_json(info, destino / "entrenamiento.json")
    reporte_comparacion(cfg)
    return info


def cargar_residuos(cfg: Config, corte) -> dict[str, pd.DataFrame]:
    destino = ruta_modelo(cfg, corte)
    return {t: pd.read_parquet(destino / f"residuos_{t}.parquet").set_index("family") for t in ("diarios", "semanales")}
