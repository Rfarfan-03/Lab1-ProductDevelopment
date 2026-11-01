import pandas as pd
import pytest

from reposicion import bandeja
from reposicion.archivos import hash_archivo
from reposicion.ingesta import cargar_asof, ingerir, ruta_staging
from reposicion.simulador import simular


def _sin_eventos(cfg):
    sim = cfg.datos["simulacion"]
    sim["correcciones"]["fraccion_archivos"] = 0.0
    sim["invalidos"]["fraccion_archivos"] = 0.0
    sim["tardios"]["fraccion_archivos"] = 0.0
    sim["faltantes"]["fraccion_archivos_transacciones"] = 0.0


def test_point_in_time_solo_usa_lo_entregado(cfg):
    _sin_eventos(cfg)
    meta = simular(cfg)
    fin = pd.Timestamp(meta["fecha_fin_historico"])
    corte = fin + pd.Timedelta(days=5)
    ingerir(cfg, corte)
    v = cargar_asof(cfg, corte, "ventas")
    assert v["date"].max() == corte - pd.Timedelta(days=1)  # ventas llegan D+1
    t = cargar_asof(cfg, corte, "transacciones")
    assert t["date"].max() == corte - pd.Timedelta(days=2)  # transacciones D+2
    p = cargar_asof(cfg, corte, "promociones")
    assert p["date"].max() > corte  # promociones futuras ya conocidas


def test_correccion_se_incorpora_cuando_llega(cfg):
    cfg.datos["simulacion"]["correcciones"]["fraccion_archivos"] = 1.0
    cfg.datos["simulacion"]["invalidos"]["fraccion_archivos"] = 0.0
    cfg.datos["simulacion"]["tardios"]["fraccion_archivos"] = 0.0
    simular(cfg)
    archivos = [a for a in bandeja.listar(cfg.ruta("bandeja")) if a.fuente == "ventas"]
    v1 = min((a for a in archivos if a.version == 1), key=lambda a: a.fecha_dato)
    v2 = next(a for a in archivos if a.version == 2 and a.fecha_dato == v1.fecha_dato)

    antes = ingerir(cfg, v1.fecha_entrega)
    assert v1.ruta.name in antes["fuentes"]["ventas"]["archivos_usados"]
    despues = ingerir(cfg, v2.fecha_entrega)
    assert v2.ruta.name in despues["fuentes"]["ventas"]["archivos_usados"]
    assert v1.ruta.name not in despues["fuentes"]["ventas"]["archivos_usados"]


def test_archivo_invalido_va_a_cuarentena_y_no_contamina(cfg):
    cfg.datos["simulacion"]["invalidos"]["fraccion_archivos"] = 1.0
    cfg.datos["simulacion"]["tardios"]["fraccion_archivos"] = 0.0
    simular(cfg)
    archivos = [a for a in bandeja.listar(cfg.ruta("bandeja")) if a.fuente == "ventas"]
    v1 = min((a for a in archivos if a.version == 1), key=lambda a: a.fecha_dato)
    rep = ingerir(cfg, v1.fecha_entrega)
    assert rep["fuentes"]["ventas"]["rechazados"][0]["archivo"] == v1.ruta.name
    assert (cfg.ruta("cuarentena") / "ventas" / v1.ruta.name).exists()
    v = cargar_asof(cfg, v1.fecha_entrega, "ventas")
    assert (v["sales"] >= 0).all()
    assert v1.fecha_dato.strftime("%Y-%m-%d") in rep["faltantes"]["ventas"]  # aviso, no falla


def test_transacciones_faltantes_no_fallan(cfg):
    cfg.datos["simulacion"]["faltantes"]["fraccion_archivos_transacciones"] = 1.0
    meta = simular(cfg)
    corte = pd.Timestamp(meta["fecha_max_datos"]) + pd.Timedelta(days=3)
    rep = ingerir(cfg, corte)
    assert rep["fuentes"]["transacciones"]["filas"] == 0
    assert len(rep["faltantes"]["transacciones"]) > 0
    assert not cargar_asof(cfg, corte, "transacciones").empty  # queda el histórico


def test_ingesta_idempotente_y_no_modifica_bandeja(cfg):
    meta = simular(cfg)
    corte = pd.Timestamp(meta["fecha_fin_historico"]) + pd.Timedelta(days=10)
    antes = {p: hash_archivo(p) for p in cfg.ruta("bandeja").rglob("*.csv")}
    ingerir(cfg, corte)
    h1 = {p.name: hash_archivo(p) for p in ruta_staging(cfg, corte).iterdir()}
    ingerir(cfg, corte)
    h2 = {p.name: hash_archivo(p) for p in ruta_staging(cfg, corte).iterdir()}
    assert h1 == h2
    assert antes == {p: hash_archivo(p) for p in cfg.ruta("bandeja").rglob("*.csv")}


def test_cargar_asof_sin_ingesta_falla_claro(cfg):
    simular(cfg)
    with pytest.raises(FileNotFoundError):
        cargar_asof(cfg, "2017-02-25", "ventas")
