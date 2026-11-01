"""Ingesta point-in-time de la bandeja.

Para una fecha de corte se consideran solo los archivos con ``fecha_entrega <= corte``.
Por cada (fuente, fecha_dato) se usa la versión más reciente que pase la validación; las
versiones rechazadas se copian a cuarentena. El resultado se reconstruye completo en cada
ejecución (idempotente) y se guarda en ``staging/corte=<fecha>/``. Así una corrección
que llega después se incorpora automáticamente en los cortes posteriores, y re-ejecutar
un corte pasado reproduce exactamente lo que se sabía ese día.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from . import archivos as io
from . import bandeja
from .config import Config
from .validacion import Catalogo, validar

log = logging.getLogger(__name__)


def _fecha(corte) -> str:
    return pd.Timestamp(corte).strftime("%Y-%m-%d")


def ruta_staging(cfg: Config, corte) -> Path:
    return cfg.ruta("staging") / f"corte={_fecha(corte)}"


def metadata_historico(cfg: Config) -> dict:
    ruta = cfg.ruta("historico") / "metadata.json"
    if not ruta.exists():
        raise FileNotFoundError(f"No existe la carga histórica ({ruta}). Ejecute primero la simulación.")
    return io.leer_json(ruta)


def cargar_catalogo(cfg: Config) -> Catalogo:
    hist = cfg.ruta("historico")
    tiendas = pd.read_parquet(hist / "tiendas.parquet")["store_nbr"]
    familias = pd.read_parquet(hist / "ventas.parquet", columns=["family"])["family"]
    return Catalogo(set(tiendas.astype(int)), set(familias.unique()))


def _leer_csv(ruta: Path) -> pd.DataFrame:
    return pd.read_csv(ruta, dtype=str, keep_default_na=False, na_values=[""])


def ingerir(cfg: Config, corte) -> dict:
    """Construye el staging as-of ``corte``. Devuelve un reporte (también se guarda en JSON)."""
    corte = pd.Timestamp(corte).normalize()
    meta = metadata_historico(cfg)
    fin_hist = pd.Timestamp(meta["fecha_fin_historico"])
    catalogo = cargar_catalogo(cfg)
    grupos = bandeja.disponibles(bandeja.listar(cfg.ruta("bandeja")), corte)

    destino = ruta_staging(cfg, corte)
    reporte: dict = {"corte": _fecha(corte), "fuentes": {}}
    for fuente in bandeja.FUENTES:
        partes, usados, rechazados, descartadas = [], [], [], 0
        fechas = sorted(f for (fu, f) in grupos if fu == fuente)
        for fecha in fechas:
            for archivo in grupos[(fuente, fecha)]:
                try:
                    res = validar(_leer_csv(archivo.ruta), fuente, catalogo, cfg["validacion"], fecha)
                except Exception as e:  # archivo ilegible: se trata como inválido
                    res = None
                    motivos = [f"archivo ilegible: {type(e).__name__}: {e}"]
                if res is not None and res.aceptado:
                    partes.append(res.df)
                    usados.append(archivo.ruta.name)
                    descartadas += res.filas_invalidas
                    break
                motivos = res.motivos if res is not None else motivos
                _a_cuarentena(cfg, archivo, motivos)
                rechazados.append({"archivo": archivo.ruta.name, "motivos": motivos})
                log.warning("Archivo rechazado %s/%s: %s", fuente, archivo.ruta.name, motivos)

        df = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=bandeja.COLUMNAS[fuente])
        if df.empty:
            df["date"] = pd.to_datetime(df["date"])
        io.escribir_parquet(df, destino / f"{fuente}.parquet")
        reporte["fuentes"][fuente] = {
            "archivos_usados": usados,
            "rechazados": rechazados,
            "filas": len(df),
            "filas_descartadas": descartadas,
        }

    reporte["faltantes"] = _faltantes(cfg, reporte, fin_hist, corte, grupos)
    io.escribir_json(reporte, destino / "reporte.json")
    return reporte


def _faltantes(cfg, reporte, fin_hist, corte, grupos) -> dict:
    """Fechas cuya entrega ya se esperaba y no hay versión válida (aviso, no falla)."""
    res = {}
    for fuente in ("ventas", "transacciones"):
        retraso = int(cfg["simulacion"]["fuentes"][fuente]["retraso_dias"])
        esperadas = pd.date_range(fin_hist + pd.Timedelta(days=1), corte - pd.Timedelta(days=retraso))
        usados = {pd.Timestamp(n.split("__")[0]) for n in reporte["fuentes"][fuente]["archivos_usados"]}
        res[fuente] = [_fecha(f) for f in esperadas if f not in usados]
    return res


def _a_cuarentena(cfg: Config, archivo: bandeja.ArchivoBandeja, motivos: list[str]) -> None:
    destino = cfg.ruta("cuarentena") / archivo.fuente / archivo.ruta.name
    io.copiar(archivo.ruta, destino)
    io.escribir_json({"archivo": str(archivo.ruta.name), "motivos": motivos}, destino.with_suffix(".json"))


def cargar_asof(cfg: Config, corte, fuente: str) -> pd.DataFrame:
    """Histórico + staging del corte: todo lo que se sabía de ``fuente`` en ``corte``."""
    ruta = ruta_staging(cfg, corte) / f"{fuente}.parquet"
    if not ruta.exists():
        raise FileNotFoundError(f"No existe staging para {fuente} en el corte {_fecha(corte)}; ejecute la ingesta.")
    hist = pd.read_parquet(cfg.ruta("historico") / f"{fuente}.parquet")
    nuevo = pd.read_parquet(ruta)
    if nuevo.empty:
        return hist.reset_index(drop=True)
    df = pd.concat([hist, nuevo], ignore_index=True)
    return df.drop_duplicates(subset=bandeja.LLAVES[fuente], keep="last").reset_index(drop=True)
