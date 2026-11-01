import numpy as np
import pandas as pd
import pytest

from reposicion import features as ft
from reposicion.archivos import hash_archivo
from reposicion.entrenamiento import entrenar, es_dia_pronostico
from reposicion.evaluacion import decidir
from reposicion.ingesta import ingerir
from reposicion.modelos import NIVELES, GLOBAL, aplicar_cuantil
from reposicion.pedido import costo_newsvendor, pedido_semanal
from reposicion.pronostico import pronosticar, ruta_publicado
from reposicion.seguimiento import seguimiento
from reposicion.simulador import simular


def _primer_lunes(meta):
    fechas = pd.date_range(pd.Timestamp(meta["fecha_fin_historico"]) + pd.Timedelta(days=1), periods=7)
    return next(f for f in fechas if f.dayofweek == 0)


@pytest.fixture
def operado(cfg_modelo):
    meta = simular(cfg_modelo)
    lunes = _primer_lunes(meta)
    ingerir(cfg_modelo, lunes)
    return cfg_modelo, lunes


def test_features_no_usan_ventas_desde_el_corte(operado):
    cfg, lunes = operado
    datos = ft.cargar_datos(cfg, lunes)
    t = lunes - pd.Timedelta(days=28)
    a = ft.construir(datos, [t], 7, con_objetivo=False)
    datos.ventas.loc[datos.ventas["date"] >= t, "sales"] = 99999.0  # alterar el "futuro" de t
    b = ft.construir(datos, [t], 7, con_objetivo=False)
    pd.testing.assert_frame_equal(a[ft.COLUMNAS_FEATURES], b[ft.COLUMNAS_FEATURES])


def test_v_dow4_es_promedio_mismo_dia_semana(operado):
    cfg, lunes = operado
    datos = ft.cargar_datos(cfg, lunes)
    x = ft.construir(datos, [lunes], 7, con_objetivo=False)
    fila = x[(x["store_nbr"] == 1) & (x["family"] == "PRODUCE") & (x["h"] == 3)].iloc[0]
    v = datos.ventas.set_index(["store_nbr", "family", "date"])["sales"]
    esperado = np.mean([v[(1, "PRODUCE", fila["date"] - pd.Timedelta(days=7 * k))] for k in (1, 2, 3, 4)])
    assert fila["v_dow4"] == pytest.approx(esperado)


def test_cortes_entrenamiento_tienen_horizonte_conocido():
    corte = pd.Timestamp("2017-07-03")
    cortes = ft.cortes_entrenamiento(corte, 10, 7, pd.Timestamp("2016-01-01"))
    assert len(cortes) == 10
    assert all(c + pd.Timedelta(days=7) < corte for c in cortes)


def test_cuantiles_monotonos_y_pedido_responde_a_costos(cfg):
    tabla = pd.DataFrame([np.linspace(-1, 1, len(NIVELES))], index=[GLOBAL], columns=[f"{q:.2f}" for q in NIVELES])
    fam = pd.Series(["X"] * 3)
    qs = aplicar_cuantil(np.array([10.0, 10.0, 10.0]), fam, tabla, [0.1, 0.5, 0.9])
    assert qs[0] < qs[1] < qs[2]

    pred = pd.DataFrame({"corte": pd.Timestamp("2017-07-03"), "store_nbr": 1, "family": "AUTOMOTIVE",
                         "date": pd.date_range("2017-07-04", periods=7), "yhat": 10.0})
    antes = pedido_semanal(pred, tabla, cfg)["pedido"].iloc[0]
    cfg.datos["costos"]["default"]["costo_merma"] = 5.0  # merma mucho más cara => pedir menos
    despues = pedido_semanal(pred, tabla, cfg)["pedido"].iloc[0]
    assert despues < antes


def test_costo_newsvendor():
    c = costo_newsvendor(np.array([10.0, 10.0]), np.array([7.0, 12.0]), np.array([1.0, 1.0]), np.array([0.5, 0.5]))
    assert c.tolist() == [3.0, 1.0]


@pytest.mark.parametrize(
    "costo_retador, wape_retador, reemplaza",
    [(90.0, 0.20, True), (99.0, 0.20, False), (90.0, 0.30, False)],
)
def test_criterio_de_reemplazo(costo_retador, wape_retador, reemplaza):
    metricas = {"baseline": {"costo_negocio": 100.0, "wape": 0.20},
                "lightgbm": {"costo_negocio": costo_retador, "wape": wape_retador}}
    d = decidir(metricas, "baseline", {"mejora_minima_costo": 0.02, "tolerancia_wape": 0.01})
    assert d["reemplaza"] is reemplaza
    assert d["vigente"] == ("lightgbm" if reemplaza else "baseline")


def test_flujo_completo_idempotente_y_reproducible(operado):
    cfg, lunes = operado
    assert es_dia_pronostico(cfg, lunes)
    info = entrenar(cfg, lunes)
    assert set(info["metricas"]) == {"baseline", "lightgbm"}
    meta = pronosticar(cfg, lunes)
    destino = ruta_publicado(cfg, lunes)
    pron = pd.read_parquet(destino / "pronostico.parquet")
    assert len(pron) == 3 * 3 * 7 and (pron["p10"] <= pron["p90"]).all()
    assert pron["date"].min() == lunes + pd.Timedelta(days=1)
    h1 = {p.name: hash_archivo(p) for p in destino.iterdir()}

    assert pronosticar(cfg, lunes) == meta  # ya publicado: no se modifica
    # Reproducibilidad: re-entrenar y re-publicar desde cero da exactamente lo mismo.
    entrenar(cfg, lunes)
    pronosticar(cfg, lunes, forzar=True)
    assert {p.name: hash_archivo(p) for p in destino.iterdir()} == h1


def test_seguimiento_compara_con_reales(operado):
    cfg, lunes = operado
    entrenar(cfg, lunes)
    pronosticar(cfg, lunes)
    fecha = lunes + pd.Timedelta(days=9)  # ventas de toda la semana ya entregadas
    ingerir(cfg, fecha)
    res = seguimiento(cfg, fecha)
    assert len(res) == 1 and res["dias_con_real"].iloc[0] == 7
    assert {"wape", "costo_negocio", "nivel_servicio"} <= set(res.columns)
    assert (cfg.ruta("reportes") / "seguimiento.md").exists()
