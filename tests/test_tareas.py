import pandas as pd
import pytest

from reposicion import tareas
from reposicion.features import cargar_features, preparar, ruta_features
from reposicion.ingesta import ingerir
from reposicion.simulador import simular


def test_rango_operacion_se_deriva_de_los_datos(cfg):
    inicio, fin = tareas.rango_operacion(cfg)
    train = pd.read_csv(cfg.ruta("kaggle") / "train.csv", parse_dates=["date"])
    fecha_max = train["date"].max()
    assert inicio == fecha_max - pd.Timedelta(days=20) + pd.Timedelta(days=1)
    assert fin == fecha_max + pd.Timedelta(days=tareas.DIAS_EXTRA_OPERACION)
    meta = simular(cfg)
    assert inicio == pd.Timestamp(meta["fecha_fin_historico"]) + pd.Timedelta(days=1)


def test_rango_operacion_sin_datos_no_falla(cfg):
    (cfg.ruta("kaggle") / "train.csv").unlink()
    inicio, fin = tareas.rango_operacion(cfg)
    assert inicio < fin


def test_preparar_persiste_features(cfg_modelo):
    meta = simular(cfg_modelo)
    lunes = next(f for f in pd.date_range(pd.Timestamp(meta["fecha_fin_historico"]) + pd.Timedelta(days=1), periods=7)
                 if f.dayofweek == 0)
    ingerir(cfg_modelo, lunes)
    info = preparar(cfg_modelo, lunes)
    assert (ruta_features(cfg_modelo, lunes) / "entrenamiento.parquet").exists()
    entren, pred, cortes = cargar_features(cfg_modelo, lunes)
    assert len(pred) == info["filas_prediccion"] and pred["corte"].eq(lunes).all()
    assert entren["corte"].max() < lunes and len(cortes) == entren["corte"].nunique()


def test_dag_estructura():
    # Solo corre donde Airflow está instalado (contenedor); en el CI se omite.
    DagBag = pytest.importorskip("airflow.models").DagBag

    bag = DagBag(dag_folder="dags", include_examples=False)
    assert not bag.import_errors
    dag = bag.get_dag("reposicion_diaria")
    assert dag.max_active_runs == 1 and dag.catchup
    assert dag.get_task("seguimiento").trigger_rule == "none_failed"
