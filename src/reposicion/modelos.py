"""Modelos de pronóstico e incertidumbre.

- ``baseline``: promedio del mismo día de la semana en las últimas 4 semanas conocidas.
- ``lightgbm``: modelo global (todas las series) sobre ``log1p(ventas)``.

La incertidumbre se estima igual para ambos modelos: cuantiles empíricos de los residuos
fuera de muestra en escala log, por familia, tanto diarios (para publicar p10/p50/p90)
como de la suma semanal (para el pedido). Guardar la distribución completa permite
calcular cualquier cuantil crítico, así que cambiar costos no requiere reentrenar.
"""

from __future__ import annotations

from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from .features import CATEGORICAS, COLUMNAS_FEATURES

NIVELES = np.round(np.arange(0.01, 1.0, 0.01), 2)
GLOBAL = "__global__"


class ModeloBaseline:
    nombre = "baseline"

    def ajustar(self, df: pd.DataFrame) -> "ModeloBaseline":
        return self

    def predecir(self, df: pd.DataFrame) -> np.ndarray:
        p = df["v_dow4"].fillna(df["v_m28"]).fillna(0.0)
        return np.clip(p.to_numpy(dtype=float), 0, None)


class ModeloLGBM:
    nombre = "lightgbm"

    def __init__(self, params: dict, semilla: int):
        self.params = {
            "objective": "regression",
            "verbose": -1,
            "deterministic": True,
            "force_col_wise": True,
            "seed": semilla,
            **params,
        }
        self.booster: lgb.Booster | None = None

    def ajustar(self, df: pd.DataFrame) -> "ModeloLGBM":
        df = df[df["y"].notna()]
        p = dict(self.params)
        rondas = int(p.pop("n_estimators"))
        ds = lgb.Dataset(
            df[COLUMNAS_FEATURES], label=np.log1p(df["y"].clip(lower=0)), categorical_feature=CATEGORICAS,
            free_raw_data=True,
        )
        self.booster = lgb.train(p, ds, num_boost_round=rondas)
        return self

    def predecir(self, df: pd.DataFrame) -> np.ndarray:
        return np.clip(np.expm1(self.booster.predict(df[COLUMNAS_FEATURES])), 0, None)

    def guardar(self, ruta: Path) -> None:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        tmp = ruta.with_name(f".{ruta.name}.tmp")
        self.booster.save_model(str(tmp))
        tmp.replace(ruta)

    @classmethod
    def cargar(cls, ruta: Path) -> "ModeloLGBM":
        m = cls({}, 0)
        m.booster = lgb.Booster(model_file=str(ruta))
        return m


def crear_modelo(nombre: str, cfg_modelo: dict):
    if nombre == "baseline":
        return ModeloBaseline()
    if nombre == "lightgbm":
        return ModeloLGBM(cfg_modelo["lightgbm"], int(cfg_modelo["semilla"]))
    raise ValueError(f"Modelo desconocido: {nombre}")


# ---------------------------------------------------------------- incertidumbre

def _tabla_cuantiles(e: pd.Series, familia: pd.Series) -> pd.DataFrame:
    tabla = e.groupby(familia).quantile(list(NIVELES)).unstack()
    tabla.loc[GLOBAL] = e.quantile(list(NIVELES)).to_numpy()
    tabla.columns = [f"{q:.2f}" for q in NIVELES]
    return tabla


def agregar_semana(df: pd.DataFrame, horizonte: int) -> pd.DataFrame:
    """Suma por (corte, tienda, familia) solo cuando los ``horizonte`` días tienen real."""
    d = df[df["y"].notna()]
    g = d.groupby(["corte", "store_nbr", "family"]).agg(Y=("y", "sum"), Yhat=("yhat", "sum"), n=("y", "size"))
    return g[g["n"] == horizonte].drop(columns="n").reset_index()


def residuos(df: pd.DataFrame, horizonte: int) -> dict[str, pd.DataFrame]:
    """Tablas de cuantiles de residuos log (diarios y semanales) por familia."""
    d = df[df["y"].notna()]
    e_dia = np.log1p(d["y"].clip(lower=0)) - np.log1p(d["yhat"])
    s = agregar_semana(df, horizonte)
    e_sem = np.log1p(s["Y"]) - np.log1p(s["Yhat"])
    return {"diarios": _tabla_cuantiles(e_dia, d["family"]), "semanales": _tabla_cuantiles(e_sem, s["family"])}


def aplicar_cuantil(yhat: np.ndarray, familias: pd.Series, tabla: pd.DataFrame, q) -> np.ndarray:
    """``expm1(log1p(yhat) + e_q(familia))``. ``q`` puede ser escalar o un arreglo por fila."""
    yhat = np.asarray(yhat, dtype=float)
    q = np.broadcast_to(np.asarray(q, dtype=float), len(yhat))
    fam = familias.where(familias.isin(tabla.index), GLOBAL).to_numpy()
    e = np.empty(len(yhat))
    pares = pd.DataFrame({"f": fam, "q": q})
    for (f, qi), idx in pares.groupby(["f", "q"]).indices.items():
        e[idx] = np.interp(qi, NIVELES, tabla.loc[f].to_numpy())
    return np.clip(np.expm1(np.log1p(yhat) + e), 0, None)
