"""Construcción de features point-in-time.

Para un corte ``c`` y un horizonte ``h`` (1..H), el objetivo es la venta del día
``c + h`` y todas las features se calculan con información conocida en ``c``:
ventas hasta ``c - 1`` y calendario/promociones/feriados ya publicados.

Las ventas se pivotean a una matriz (serie x día) para calcular ventanas de forma
vectorizada; los entrenamientos usan muchos cortes semanales pasados.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import Config
from .ingesta import cargar_asof

TIPOS_FERIADO = {"Holiday", "Transfer", "Additional", "Bridge"}
VENTANAS = (7, 14, 28, 56)
HISTORIA_MINIMA_DIAS = 70  # historia previa necesaria para las ventanas más largas

COLUMNAS_FEATURES = [
    "store_nbr", "family_cod", "tipo_cod", "cluster", "h", "dow", "dia_mes", "mes", "quincena",
    "v_m7", "v_m14", "v_m28", "v_m56", "v_std28", "v_ceros28", "v_dow4", "v_dow8", "v_lag_sem",
    "promo_d", "promo_m28", "tx_m28", "petroleo", "fer_nac", "evento", "fer_loc",
]
CATEGORICAS = ["store_nbr", "family_cod", "tipo_cod", "cluster"]


@dataclass
class DatosAsOf:
    corte: pd.Timestamp
    ventas: pd.DataFrame
    promociones: pd.DataFrame
    transacciones: pd.DataFrame
    petroleo: pd.DataFrame
    feriados: pd.DataFrame
    tiendas: pd.DataFrame


def cargar_datos(cfg: Config, corte) -> DatosAsOf:
    corte = pd.Timestamp(corte)
    f = {fu: cargar_asof(cfg, corte, fu) for fu in ("ventas", "promociones", "transacciones", "petroleo", "feriados")}
    tiendas = pd.read_parquet(cfg.ruta("historico") / "tiendas.parquet")
    # Seguridad point-in-time: las ventas del día del corte aún no se conocen.
    f["ventas"] = f["ventas"][f["ventas"]["date"] < corte]
    return DatosAsOf(corte, tiendas=tiendas, **f)


def _nanmean(a: np.ndarray, axis: int = 1) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        return np.nanmean(a, axis=axis)


class Matrices:
    """Ventas y promociones como matrices (serie x día) entre ``inicio`` y ``fin``."""

    def __init__(self, datos: DatosAsOf, inicio: pd.Timestamp, fin: pd.Timestamp):
        self.tiendas = sorted(datos.tiendas["store_nbr"].astype(int))
        self.familias = sorted(datos.ventas["family"].unique())
        self.series = pd.MultiIndex.from_product([self.tiendas, self.familias], names=["store_nbr", "family"])
        self.inicio, self.fin = inicio, fin
        self.fechas = pd.date_range(inicio, fin)
        self.ventas = self._llenar(datos.ventas, "sales", datos.corte - pd.Timedelta(days=1))
        self.promo = self._llenar(datos.promociones, "onpromotion", fin)

    def idx(self, fecha) -> int:
        return int((pd.Timestamp(fecha) - self.inicio).days)

    def _llenar(self, df: pd.DataFrame, col: str, hasta) -> np.ndarray:
        m = np.full((len(self.series), len(self.fechas)), np.nan)
        hasta = min(pd.Timestamp(hasta), self.fin)
        df = df[(df["date"] >= self.inicio) & (df["date"] <= hasta)]
        si = self.series.get_indexer(pd.MultiIndex.from_frame(df[["store_nbr", "family"]]))
        ti = (df["date"] - self.inicio).dt.days.to_numpy()
        ok = si >= 0
        m[si[ok], ti[ok]] = df[col].to_numpy(dtype=float)[ok]
        return m


def _exogenas(datos: DatosAsOf, matrices: Matrices) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """Tablas de feriados (nacional por fecha y local por tienda-fecha), transacciones y petróleo."""
    fer = datos.feriados
    fer = fer[~fer["transferred"].astype(bool)]
    nac = fer[fer["locale"] == "National"]
    nac_tab = pd.DataFrame({
        "date": matrices.fechas,
        "fer_nac": matrices.fechas.isin(nac[nac["type"].isin(TIPOS_FERIADO)]["date"]).astype(int),
        "evento": matrices.fechas.isin(nac[nac["type"] == "Event"]["date"]).astype(int),
    })
    t = datos.tiendas[["store_nbr", "city", "state"]]
    reg = fer[fer["locale"] == "Regional"].merge(t, left_on="locale_name", right_on="state")
    loc = fer[fer["locale"] == "Local"].merge(t, left_on="locale_name", right_on="city")
    loc_tab = pd.concat([reg, loc])[["date", "store_nbr"]].drop_duplicates().assign(fer_loc=1)

    tx = datos.transacciones.pivot_table(index="date", columns="store_nbr", values="transactions")
    tx = tx.reindex(matrices.fechas)
    pet = datos.petroleo.set_index("date")["dcoilwtico"].reindex(matrices.fechas)
    return nac_tab, loc_tab, tx, pet


def construir(datos: DatosAsOf, cortes: list[pd.Timestamp], horizonte: int, con_objetivo: bool) -> pd.DataFrame:
    """Filas (corte, tienda, familia, fecha, h) con features y, opcionalmente, el objetivo ``y``."""
    cortes = sorted(pd.Timestamp(c) for c in cortes)
    inicio = cortes[0] - pd.Timedelta(days=HISTORIA_MINIMA_DIAS)
    fin = cortes[-1] + pd.Timedelta(days=horizonte)
    m = Matrices(datos, inicio, fin)
    nac_tab, loc_tab, tx, pet = _exogenas(datos, m)
    tx_arr = tx.to_numpy()  # dia x tienda
    tienda_col = {s: k for k, s in enumerate(tx.columns)}
    pet_ffill = pet.ffill()

    S = len(m.series)
    s_tienda = m.series.get_level_values("store_nbr").to_numpy()
    fam_cod = pd.Categorical(m.series.get_level_values("family"), categories=m.familias).codes
    partes = []
    for c in cortes:
        i = m.idx(c) - 1  # último día con ventas conocidas
        V = m.ventas[:, : i + 1]
        base = {f"v_m{w}": _nanmean(V[:, -w:]) for w in VENTANAS}
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            base["v_std28"] = np.nanstd(V[:, -28:], axis=1)
            base["v_ceros28"] = _nanmean((V[:, -28:] == 0).astype(float) + 0 * V[:, -28:])
        base["promo_m28"] = _nanmean(m.promo[:, i - 27 : i + 1])
        ultimo_tx = _nanmean(tx_arr[i - 27 : i + 1, :], axis=0)
        base["tx_m28"] = np.array([ultimo_tx[tienda_col[s]] if s in tienda_col else np.nan for s in s_tienda])
        base["petroleo"] = np.full(S, pet_ffill.iloc[i] if i < len(pet_ffill) else np.nan)

        for h in range(1, horizonte + 1):
            j = i + 1 + h  # índice del día objetivo (c + h)
            k0 = int(np.ceil((j - i) / 7))  # primera semana completa hacia atrás ya conocida
            dows = [j - 7 * k for k in range(k0, k0 + 8) if j - 7 * k >= 0]
            fila = dict(base)
            fila["v_dow4"] = _nanmean(m.ventas[:, dows[:4]])
            fila["v_dow8"] = _nanmean(m.ventas[:, dows[:8]])
            fila["v_lag_sem"] = m.ventas[:, dows[0]]
            fila["promo_d"] = m.promo[:, j]
            fila["h"] = np.full(S, h)
            fila["store_nbr"] = s_tienda
            fila["family_cod"] = fam_cod
            fila["date"] = np.full(S, m.fechas[j])
            fila["corte"] = np.full(S, c)
            if con_objetivo:
                fila["y"] = m.ventas[:, j] if j <= m.idx(datos.corte) - 1 else np.full(S, np.nan)
            partes.append(pd.DataFrame(fila))

    df = pd.concat(partes, ignore_index=True)
    df["family"] = np.asarray(m.familias, dtype=object)[df["family_cod"]]
    df["dow"] = df["date"].dt.dayofweek
    df["dia_mes"] = df["date"].dt.day
    df["mes"] = df["date"].dt.month
    df["quincena"] = ((df["dia_mes"] == 15) | df["date"].dt.is_month_end).astype(int)
    df = df.merge(nac_tab, on="date", how="left").merge(loc_tab, on=["date", "store_nbr"], how="left")
    df["fer_loc"] = df["fer_loc"].fillna(0).astype(int)
    t = datos.tiendas.set_index("store_nbr")
    tipos = sorted(t["type"].unique())
    df["tipo_cod"] = pd.Categorical(df["store_nbr"].map(t["type"]), categories=tipos).codes
    df["cluster"] = df["store_nbr"].map(t["cluster"]).astype(int)
    return df


def cortes_entrenamiento(corte: pd.Timestamp, n: int, horizonte: int, inicio_datos: pd.Timestamp) -> list[pd.Timestamp]:
    """Cortes semanales anteriores cuyo horizonte completo ya es conocido en ``corte``."""
    corte = pd.Timestamp(corte)
    ultimo = corte - pd.Timedelta(days=7 * int(np.ceil((horizonte + 1) / 7)))
    cortes = [ultimo - pd.Timedelta(days=7 * k) for k in range(n)]
    minimo = inicio_datos + pd.Timedelta(days=HISTORIA_MINIMA_DIAS)
    return sorted(c for c in cortes if c >= minimo)
