import pandas as pd
import pytest

from reposicion.validacion import Catalogo, validar

CAT = Catalogo(tiendas={1, 2}, familias={"A", "B"})
REGLAS = {"max_fraccion_filas_invalidas": 0.2, "max_venta_razonable": 1000}
FECHA = pd.Timestamp("2017-01-10")


def ventas(filas):
    return pd.DataFrame(filas, columns=["date", "store_nbr", "family", "sales"]).astype(str)


def test_archivo_valido_se_acepta_y_tipa():
    df = ventas([("2017-01-10", 1, "A", 5.0), ("2017-01-10", 2, "B", 0.0)])
    res = validar(df, "ventas", CAT, REGLAS, FECHA)
    assert res.aceptado and res.filas_invalidas == 0
    assert res.df["sales"].dtype == float and res.df["store_nbr"].dtype == "int64"


def test_columna_faltante_rechaza_archivo():
    df = ventas([("2017-01-10", 1, "A", 5.0)]).drop(columns="sales")
    res = validar(df, "ventas", CAT, REGLAS, FECHA)
    assert not res.aceptado and "columnas faltantes" in res.motivos[0]


def test_archivo_vacio_se_rechaza():
    assert not validar(ventas([]), "ventas", CAT, REGLAS, FECHA).aceptado


@pytest.mark.parametrize(
    "fila_mala",
    [
        ("2017-01-10", 1, "A", -3.0),       # venta negativa
        ("2017-01-10", 9, "A", 1.0),        # tienda desconocida
        ("2017-01-10", 1, "Z", 1.0),        # familia desconocida
        ("2017-01-10", 1, "A", "abc"),      # no numérica
        ("2017-01-10", 1, "A", 99999.0),    # fuera de rango
        ("2017-01-11", 1, "A", 1.0),        # fecha distinta a la del archivo
    ],
)
def test_filas_invalidas_bajo_umbral_se_descartan(fila_mala):
    buenas = [("2017-01-10", t, f, 1.0) for t in (1, 2) for f in ("A", "B")]
    df = ventas(buenas + [fila_mala])
    res = validar(df, "ventas", CAT, {**REGLAS, "max_fraccion_filas_invalidas": 0.25}, FECHA)
    assert res.aceptado and res.filas_invalidas == 1 and len(res.df) == 4


def test_demasiadas_filas_invalidas_rechazan_el_archivo():
    df = ventas([("2017-01-10", 1, "A", -1.0), ("2017-01-10", 2, "A", -1.0), ("2017-01-10", 1, "B", 1.0)])
    res = validar(df, "ventas", CAT, REGLAS, FECHA)
    assert not res.aceptado and "supera el umbral" in res.motivos[0]


def test_duplicados_exactos_se_colapsan_y_conflictivos_se_descartan():
    df = ventas([
        ("2017-01-10", 1, "A", 5.0), ("2017-01-10", 1, "A", 5.0),   # exacto
        ("2017-01-10", 2, "B", 1.0), ("2017-01-10", 2, "B", 7.0),   # conflicto
        ("2017-01-10", 1, "B", 1.0), ("2017-01-10", 2, "A", 1.0),
    ])
    res = validar(df, "ventas", CAT, {**REGLAS, "max_fraccion_filas_invalidas": 0.5}, FECHA)
    assert res.aceptado
    assert len(res.df) == 3 and res.filas_invalidas == 2


def test_petroleo_sin_precio_es_esperado():
    df = pd.DataFrame({"date": ["2017-01-10"], "dcoilwtico": [""]})
    res = validar(df, "petroleo", CAT, REGLAS, FECHA)
    assert res.aceptado and res.df["dcoilwtico"].isna().all()
