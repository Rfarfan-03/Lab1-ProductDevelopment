"""Generación y publicación del pronóstico y del pedido sugerido de un corte.

Lo publicado en ``publicados/corte=<fecha>/`` es inmutable: si ya existe, no se vuelve a
escribir (la re-ejecución es idempotente). Para reproducirlo se borra la carpeta y se
vuelve a ejecutar con la misma versión de código y datos.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from . import archivos as io
from .config import Config
from .entrenamiento import cargar_residuos, ruta_modelo
from .features import cargar_datos, construir
from .modelos import ModeloBaseline, ModeloLGBM, aplicar_cuantil
from .pedido import pedido_semanal

log = logging.getLogger(__name__)


def ruta_publicado(cfg: Config, corte) -> Path:
    return cfg.ruta("publicados") / f"corte={pd.Timestamp(corte).strftime('%Y-%m-%d')}"


def pronosticar(cfg: Config, corte, forzar: bool = False) -> dict:
    corte = pd.Timestamp(corte)
    destino = ruta_publicado(cfg, corte)
    if (destino / "metadata.json").exists() and not forzar:
        log.info("Pronóstico del corte %s ya publicado; no se modifica.", corte.date())
        return io.leer_json(destino / "metadata.json")

    entrenamiento = ruta_modelo(cfg, corte) / "entrenamiento.json"
    if not entrenamiento.exists():
        raise FileNotFoundError(f"No hay modelo entrenado para el corte {corte.date()}")
    vigente = io.leer_json(entrenamiento)["decision"]["vigente"]
    modelo = (ModeloLGBM.cargar(ruta_modelo(cfg, corte) / "modelo_lightgbm.txt")
              if vigente == "lightgbm" else ModeloBaseline())
    tablas = cargar_residuos(cfg, corte)

    horizonte = int(cfg["operacion"]["horizonte_dias"])
    x = construir(cargar_datos(cfg, corte), [corte], horizonte, con_objetivo=False)
    pron = x[["corte", "store_nbr", "family", "date", "h"]].copy()
    pron["yhat"] = modelo.predecir(x)
    for q in cfg["operacion"]["cuantiles"]:
        pron[f"p{int(round(q * 100))}"] = aplicar_cuantil(pron["yhat"].to_numpy(), pron["family"], tablas["diarios"], q)
    pron["modelo"] = vigente
    pedido = pedido_semanal(pron, tablas["semanales"], cfg)
    pedido["modelo"] = vigente

    io.escribir_parquet(pron, destino / "pronostico.parquet")
    io.escribir_parquet(pedido, destino / "pedido.parquet")
    io.escribir_csv(pedido, destino / "pedido.csv")
    meta = {
        "corte": corte.strftime("%Y-%m-%d"),
        "modelo": vigente,
        "horizonte": [pron["date"].min().strftime("%Y-%m-%d"), pron["date"].max().strftime("%Y-%m-%d")],
        "series": int(len(pedido)),
        "pedido_total": float(pedido["pedido"].sum()),
        "pronostico_total": float(pedido["pronostico_semana"].sum()),
        "costos": cfg["costos"],
    }
    io.escribir_json(meta, destino / "metadata.json")  # se escribe al final: marca de publicación completa
    log.info("Publicado corte %s con modelo %s", meta["corte"], vigente)
    return meta
