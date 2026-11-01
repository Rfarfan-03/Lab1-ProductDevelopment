"""Validación de los archivos que llegan de la bandeja.

Dos niveles:
- **Archivo**: columnas faltantes, archivo vacío o ilegible, o fracción de filas inválidas
  mayor a ``validacion.max_fraccion_filas_invalidas`` => el archivo completo se rechaza
  (va a cuarentena) y no contamina el resultado.
- **Fila**: filas con valores imposibles se descartan y se reportan.

Las situaciones esperadas del negocio (ventas en cero, petróleo sin precio, filas
faltantes de una tienda) no son errores.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .bandeja import COLUMNAS, LLAVES

TIPOS_FERIADO = {"Holiday", "Transfer", "Additional", "Bridge", "Work Day", "Event"}


@dataclass
class Catalogo:
    """Valores conocidos contra los que se valida (tiendas y familias de la carga histórica)."""

    tiendas: set[int]
    familias: set[str]


@dataclass
class ResultadoValidacion:
    aceptado: bool
    df: pd.DataFrame | None
    filas_total: int = 0
    filas_invalidas: int = 0
    motivos: list[str] = field(default_factory=list)


def _numerico(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def validar(
    df: pd.DataFrame,
    fuente: str,
    catalogo: Catalogo,
    cfg_validacion: dict,
    fecha_dato: pd.Timestamp | None = None,
) -> ResultadoValidacion:
    """Valida y tipa un DataFrame crudo (leído como texto) de una fuente."""
    faltan = [c for c in COLUMNAS[fuente] if c not in df.columns]
    if faltan:
        return ResultadoValidacion(False, None, len(df), len(df), [f"columnas faltantes: {faltan}"])
    if df.empty:
        return ResultadoValidacion(False, None, 0, 0, ["archivo vacío"])

    df = df[COLUMNAS[fuente]].copy()
    total = len(df)
    malo = pd.Series(False, index=df.index)
    motivos: dict[str, int] = {}

    def marcar(mascara: pd.Series, motivo: str) -> None:
        nonlocal malo
        n = int((mascara & ~malo).sum())
        if n:
            motivos[motivo] = motivos.get(motivo, 0) + n
        malo |= mascara

    df["date"] = pd.to_datetime(df["date"], errors="coerce", format="%Y-%m-%d")
    marcar(df["date"].isna(), "fecha ilegible")
    if fecha_dato is not None:
        marcar(df["date"].notna() & (df["date"] != pd.Timestamp(fecha_dato)), "fecha distinta a la del archivo")

    if "store_nbr" in df:
        df["store_nbr"] = _numerico(df["store_nbr"])
        marcar(~df["store_nbr"].isin(catalogo.tiendas), "tienda desconocida")
    if "family" in df:
        marcar(~df["family"].isin(catalogo.familias), "familia desconocida")

    if fuente == "ventas":
        df["sales"] = _numerico(df["sales"])
        marcar(df["sales"].isna(), "venta no numérica")
        marcar(df["sales"] < 0, "venta negativa")
        marcar(df["sales"] > cfg_validacion["max_venta_razonable"], "venta fuera de rango")
    elif fuente == "promociones":
        df["onpromotion"] = _numerico(df["onpromotion"])
        marcar(df["onpromotion"].isna() | (df["onpromotion"] < 0), "promoción inválida")
    elif fuente == "transacciones":
        df["transactions"] = _numerico(df["transactions"])
        marcar(df["transactions"].isna() | (df["transactions"] < 0), "transacciones inválidas")
    elif fuente == "petroleo":
        # El precio vacío es esperado (Kaggle trae huecos); solo es inválido si es <= 0.
        df["dcoilwtico"] = _numerico(df["dcoilwtico"])
        marcar(df["dcoilwtico"] <= 0, "precio de petróleo no positivo")
    elif fuente == "feriados":
        marcar(~df["type"].isin(TIPOS_FERIADO), "tipo de feriado desconocido")
        df["transferred"] = df["transferred"].astype(str).str.lower().map({"true": True, "false": False})
        marcar(df["transferred"].isna(), "transferred inválido")

    # Duplicados: idénticos se colapsan; con valores distintos son ambiguos => inválidos.
    df = df[~malo]
    exactos = df.duplicated(keep="first")
    df = df[~exactos]
    conflicto = df.duplicated(subset=LLAVES[fuente], keep=False)
    invalidas = int(malo.sum()) + int(conflicto.sum())
    if conflicto.any():
        motivos["llave duplicada con valores distintos"] = int(conflicto.sum())
    df = df[~conflicto]
    if exactos.any():
        motivos["duplicados exactos (colapsados)"] = int(exactos.sum())

    lista_motivos = [f"{m}: {n}" for m, n in motivos.items()]
    if invalidas / total > cfg_validacion["max_fraccion_filas_invalidas"]:
        lista_motivos.insert(0, f"{invalidas}/{total} filas inválidas supera el umbral")
        return ResultadoValidacion(False, None, total, invalidas, lista_motivos)

    if "store_nbr" in df:
        df["store_nbr"] = df["store_nbr"].astype("int64")
    if fuente == "promociones":
        df["onpromotion"] = df["onpromotion"].astype("int64")
    if fuente == "feriados":
        df["transferred"] = df["transferred"].astype(bool)
    return ResultadoValidacion(True, df.reset_index(drop=True), total, invalidas, lista_motivos)
