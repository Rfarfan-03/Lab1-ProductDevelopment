"""Construye la carga histórica y la bandeja a partir de los CSV de Kaggle.

Representa al sistema de origen de la empresa: es lo único que escribe en la
bandeja. El flujo de producto solo la lee.

Es determinista (semilla fija) e idempotente: si los archivos de Kaggle y la
configuración de simulación no cambiaron, no se regenera nada.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from . import archivos as io
from .bandeja import COLUMNAS, nombre_archivo
from .config import Config

log = logging.getLogger(__name__)

ARCHIVOS_KAGGLE = ("train.csv", "stores.csv", "oil.csv", "holidays_events.csv", "transactions.csv")
DIAS_FERIADOS_FUTUROS = 30  # feriados posteriores a la última venta que igual se publican


def leer_kaggle(carpeta: Path) -> dict[str, pd.DataFrame]:
    faltan = [a for a in ARCHIVOS_KAGGLE if not (carpeta / a).exists()]
    if faltan:
        raise FileNotFoundError(f"Faltan archivos de Kaggle en {carpeta}: {faltan}")
    fecha = ["date"]
    return {
        "train": pd.read_csv(carpeta / "train.csv", parse_dates=fecha),
        "stores": pd.read_csv(carpeta / "stores.csv"),
        "oil": pd.read_csv(carpeta / "oil.csv", parse_dates=fecha),
        "holidays": pd.read_csv(carpeta / "holidays_events.csv", parse_dates=fecha),
        "transactions": pd.read_csv(carpeta / "transactions.csv", parse_dates=fecha),
    }


def calcular_fecha_fin_historico(cfg: Config, fecha_max: pd.Timestamp) -> pd.Timestamp:
    fijada = cfg["simulacion"].get("fecha_fin_historico")
    if fijada:
        return pd.Timestamp(fijada)
    return fecha_max - pd.Timedelta(days=int(cfg["simulacion"]["dias_bandeja"]))


def _firma(cfg: Config) -> str:
    carpeta = cfg.ruta("kaggle")
    hashes = {a: io.hash_archivo(carpeta / a) for a in ARCHIVOS_KAGGLE}
    return json.dumps({"kaggle": hashes, "simulacion": cfg["simulacion"]}, sort_keys=True)


def simular(cfg: Config, forzar: bool = False) -> dict:
    """Genera ``historico`` y ``bandeja``. Devuelve la metadata de la simulación."""
    ruta_hist, ruta_bandeja = cfg.ruta("historico"), cfg.ruta("bandeja")
    ruta_meta = ruta_hist / "metadata.json"
    firma = _firma(cfg)
    if not forzar and ruta_meta.exists() and ruta_bandeja.exists():
        meta = io.leer_json(ruta_meta)
        if meta.get("firma") == firma:
            log.info("Simulación vigente (mismas entradas y configuración); no se regenera.")
            return meta

    datos = leer_kaggle(cfg.ruta("kaggle"))
    sim = cfg["simulacion"]
    rng = np.random.default_rng(int(sim["semilla"]))
    train = datos["train"]
    fecha_max = train["date"].max()
    fin_hist = calcular_fecha_fin_historico(cfg, fecha_max)
    if not train["date"].min() < fin_hist < fecha_max:
        raise ValueError(f"fecha_fin_historico {fin_hist.date()} fuera del rango de train.csv")

    tmp_hist = ruta_hist.with_name(ruta_hist.name + ".tmp")
    tmp_bandeja = ruta_bandeja.with_name(ruta_bandeja.name + ".tmp")
    for t in (tmp_hist, tmp_bandeja):
        shutil.rmtree(t, ignore_errors=True)

    # ---------------- Carga histórica: todo lo que se sabía al cierre de fin_hist ----------
    ventas = train[["date", "store_nbr", "family", "sales"]]
    promos = train[["date", "store_nbr", "family", "onpromotion"]]
    en_hist = lambda df: df[df["date"] <= fin_hist]  # noqa: E731
    io.escribir_parquet(en_hist(ventas), tmp_hist / "ventas.parquet")
    io.escribir_parquet(en_hist(promos), tmp_hist / "promociones.parquet")
    io.escribir_parquet(en_hist(datos["transactions"]), tmp_hist / "transacciones.parquet")
    io.escribir_parquet(en_hist(datos["oil"]), tmp_hist / "petroleo.parquet")
    io.escribir_parquet(en_hist(datos["holidays"]), tmp_hist / "feriados.parquet")
    io.escribir_parquet(datos["stores"], tmp_hist / "tiendas.parquet")

    # ---------------- Bandeja ----------------
    fuentes = sim["fuentes"]
    conteo: dict[str, int] = {}

    def entregar(fuente: str, df: pd.DataFrame, fecha, entrega, version: int = 1) -> None:
        df = df[COLUMNAS[fuente]].copy()
        df["date"] = df["date"].dt.strftime("%Y-%m-%d")
        io.escribir_csv(df, tmp_bandeja / fuente / nombre_archivo(fecha, entrega, version))
        conteo[fuente] = conteo.get(fuente, 0) + 1

    dias = lambda n: pd.Timedelta(days=int(n))  # noqa: E731
    posteriores = lambda df, hasta=fecha_max: df[(df["date"] > fin_hist) & (df["date"] <= hasta)]  # noqa: E731

    # Ventas: llegan D+retraso; algunas tarde, algunas con errores corregidos luego en v2.
    corr, inval, tard = sim["correcciones"], sim["invalidos"], sim["tardios"]
    eventos = {"correcciones": [], "invalidos": [], "tardios": []}
    for fecha, df in posteriores(ventas).groupby("date", sort=True):
        entrega = fecha + dias(fuentes["ventas"]["retraso_dias"])
        if rng.random() < tard["fraccion_archivos"]:
            entrega += dias(tard["retraso_extra_dias"])
            eventos["tardios"].append(fecha)
        u = rng.random()
        if u < inval["fraccion_archivos"]:
            malo = df.copy()
            idx = rng.choice(len(malo), max(1, int(len(malo) * inval["fraccion_filas"])), replace=False)
            malo.iloc[idx, malo.columns.get_loc("sales")] = -1.0 * (malo["sales"].iloc[idx] + 1)
            entregar("ventas", malo, fecha, entrega, 1)
            entregar("ventas", df, fecha, entrega + dias(corr["retraso_dias"]), 2)
            eventos["invalidos"].append(fecha)
        elif u < inval["fraccion_archivos"] + corr["fraccion_archivos"]:
            malo = df.copy()
            idx = rng.choice(len(malo), max(1, int(len(malo) * corr["fraccion_filas"])), replace=False)
            factor = rng.uniform(0.3, 2.0, size=len(idx))
            malo.iloc[idx, malo.columns.get_loc("sales")] = np.round(malo["sales"].iloc[idx] * factor, 3)
            entregar("ventas", malo, fecha, entrega, 1)
            entregar("ventas", df, fecha, entrega + dias(corr["retraso_dias"]), 2)
            eventos["correcciones"].append(fecha)
        else:
            entregar("ventas", df, fecha, entrega, 1)

    # Promociones: plan conocido con anticipación.
    for fecha, df in posteriores(promos).groupby("date", sort=True):
        entregar("promociones", df, fecha, fecha - dias(fuentes["promociones"]["anticipacion_dias"]))

    # Transacciones: más retraso y algunos archivos nunca llegan.
    falt = sim["faltantes"]["fraccion_archivos_transacciones"]
    for fecha, df in posteriores(datos["transactions"]).groupby("date", sort=True):
        if rng.random() < falt:
            continue
        entregar("transacciones", df, fecha, fecha + dias(fuentes["transacciones"]["retraso_dias"]))

    # Petróleo: solo días hábiles (Kaggle ya trae solo esos días).
    for fecha, df in posteriores(datos["oil"]).groupby("date", sort=True):
        entregar("petroleo", df, fecha, fecha + dias(fuentes["petroleo"]["retraso_dias"]))

    # Feriados: calendario publicado con anticipación (incluye fechas futuras al último dato).
    hasta = fecha_max + dias(DIAS_FERIADOS_FUTUROS)
    for fecha, df in posteriores(datos["holidays"], hasta).groupby("date", sort=True):
        entregar("feriados", df, fecha, fecha - dias(fuentes["feriados"]["anticipacion_dias"]))

    meta = {
        "firma": firma,
        "fecha_fin_historico": fin_hist.strftime("%Y-%m-%d"),
        "fecha_max_datos": fecha_max.strftime("%Y-%m-%d"),
        "archivos_por_fuente": conteo,
        "eventos": {k: [f.strftime("%Y-%m-%d") for f in v] for k, v in eventos.items()},
    }
    io.escribir_json(meta, tmp_hist / "metadata.json")
    io.reemplazar_directorio(tmp_bandeja, ruta_bandeja)
    io.reemplazar_directorio(tmp_hist, ruta_hist)
    log.info("Simulación generada: histórico hasta %s, %s", meta["fecha_fin_historico"], conteo)
    return meta
