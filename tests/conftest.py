"""Fixtures compartidas: un mini dataset con el formato de Kaggle y una config apuntando a él."""

import copy

import numpy as np
import pandas as pd
import pytest
import yaml

from reposicion.config import RAIZ_REPO, Config

FECHA_INICIO = "2017-01-01"
DIAS = 60
TIENDAS = [1, 2, 3]
FAMILIAS = ["GROCERY I", "PRODUCE", "AUTOMOTIVE"]


def escribir_kaggle(carpeta, semilla=0):
    rng = np.random.default_rng(semilla)
    carpeta.mkdir(parents=True, exist_ok=True)
    fechas = pd.date_range(FECHA_INICIO, periods=DIAS)
    filas = []
    for f in fechas:
        for t in TIENDAS:
            for fam in FAMILIAS:
                base = {"GROCERY I": 100, "PRODUCE": 40, "AUTOMOTIVE": 3}[fam] * (1 + 0.3 * (f.dayofweek >= 5))
                filas.append((f, t, fam, float(rng.poisson(base)), int(rng.integers(0, 5))))
    train = pd.DataFrame(filas, columns=["date", "store_nbr", "family", "sales", "onpromotion"])
    train.insert(0, "id", range(len(train)))
    train.to_csv(carpeta / "train.csv", index=False, date_format="%Y-%m-%d")

    pd.DataFrame(
        {"store_nbr": TIENDAS, "city": "Quito", "state": "Pichincha", "type": "D", "cluster": 1}
    ).to_csv(carpeta / "stores.csv", index=False)

    habiles = fechas[fechas.dayofweek < 5]
    oil = pd.DataFrame({"date": habiles, "dcoilwtico": np.round(rng.uniform(40, 60, len(habiles)), 2)})
    oil.loc[3, "dcoilwtico"] = np.nan  # hueco esperado como en Kaggle
    oil.to_csv(carpeta / "oil.csv", index=False, date_format="%Y-%m-%d")

    pd.DataFrame(
        {
            "date": pd.to_datetime(["2017-01-01", "2017-02-20", "2017-03-05", "2017-03-25"]),
            "type": ["Holiday", "Holiday", "Event", "Holiday"],
            "locale": "National",
            "locale_name": "Ecuador",
            "description": ["A", "B", "C", "D"],
            "transferred": [False, False, False, True],
        }
    ).to_csv(carpeta / "holidays_events.csv", index=False, date_format="%Y-%m-%d")

    tx = pd.DataFrame([(f, t, int(rng.integers(500, 2000))) for f in fechas for t in TIENDAS],
                      columns=["date", "store_nbr", "transactions"])
    tx.to_csv(carpeta / "transactions.csv", index=False, date_format="%Y-%m-%d")


@pytest.fixture
def datos_config():
    with open(RAIZ_REPO / "config" / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def cfg(tmp_path, datos_config):
    """Config del repo con rutas dentro de tmp_path y una bandeja de 20 días."""
    datos = copy.deepcopy(datos_config)
    datos["simulacion"]["dias_bandeja"] = 20
    escribir_kaggle(tmp_path / datos["rutas"]["kaggle"])
    return Config(datos, tmp_path)
