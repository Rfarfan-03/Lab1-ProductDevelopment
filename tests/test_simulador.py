import pandas as pd

from reposicion import bandeja
from reposicion.archivos import hash_archivo
from reposicion.simulador import simular


def _hashes(carpeta):
    return {p.relative_to(carpeta).as_posix(): hash_archivo(p) for p in sorted(carpeta.rglob("*.csv"))}


def test_historico_termina_en_fecha_fin(cfg):
    meta = simular(cfg)
    fin = pd.Timestamp(meta["fecha_fin_historico"])
    assert fin == pd.Timestamp(meta["fecha_max_datos"]) - pd.Timedelta(days=20)
    for fuente in ("ventas", "promociones", "transacciones", "petroleo", "feriados"):
        df = pd.read_parquet(cfg.ruta("historico") / f"{fuente}.parquet")
        assert df["date"].max() <= fin


def test_bandeja_respeta_retrasos_y_anticipacion(cfg):
    simular(cfg)
    archivos = bandeja.listar(cfg.ruta("bandeja"))
    assert {a.fuente for a in archivos} == set(bandeja.FUENTES)
    for a in archivos:
        if a.fuente == "transacciones":
            assert a.fecha_entrega - a.fecha_dato == pd.Timedelta(days=2)
        if a.fuente == "promociones":
            assert a.fecha_entrega < a.fecha_dato  # se conoce por adelantado
        if a.fuente == "ventas":
            assert a.fecha_entrega > a.fecha_dato  # nunca antes del cierre del día


def test_correcciones_v2_traen_valores_reales(cfg):
    cfg.datos["simulacion"]["correcciones"]["fraccion_archivos"] = 1.0
    cfg.datos["simulacion"]["invalidos"]["fraccion_archivos"] = 0.0
    simular(cfg)
    train = pd.read_csv(cfg.ruta("kaggle") / "train.csv", parse_dates=["date"])
    v2 = [a for a in bandeja.listar(cfg.ruta("bandeja")) if a.fuente == "ventas" and a.version == 2]
    assert v2
    a = v2[0]
    df = pd.read_csv(a.ruta, parse_dates=["date"])
    real = train[train["date"] == a.fecha_dato][["store_nbr", "family", "sales"]]
    comp = df.merge(real, on=["store_nbr", "family"], suffixes=("", "_real"))
    assert (comp["sales"] == comp["sales_real"]).all()


def test_simulacion_determinista_e_idempotente(cfg):
    simular(cfg)
    primero = _hashes(cfg.ruta("bandeja"))
    mtime = (cfg.ruta("historico") / "metadata.json").stat().st_mtime
    simular(cfg)  # mismas entradas => no regenera
    assert (cfg.ruta("historico") / "metadata.json").stat().st_mtime == mtime
    simular(cfg, forzar=True)  # regenerar => mismo contenido
    assert _hashes(cfg.ruta("bandeja")) == primero
