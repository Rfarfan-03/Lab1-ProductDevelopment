import copy

import pytest

from reposicion.config import Config, cargar_config


def test_config_del_repo_carga():
    cfg = cargar_config()
    assert cfg["operacion"]["horizonte_dias"] >= 1
    assert cfg.ruta("kaggle").name == "kaggle"


def test_cuantil_critico_usa_costos_por_familia():
    cfg = cargar_config()
    default = cfg.costos_familia("AUTOMOTIVE")
    perecedero = cfg.costos_familia("PRODUCE")
    # La merma de perecederos es más cara => se pide un cuantil más bajo.
    assert perecedero.cuantil_critico < default.cuantil_critico
    assert 0 < perecedero.cuantil_critico < 1


def test_cambiar_costos_cambia_cuantil_sin_tocar_codigo(datos_config, tmp_path):
    datos = copy.deepcopy(datos_config)
    datos["costos"]["default"] = {"costo_quiebre": 1.0, "costo_merma": 1.0}
    cfg = Config(datos, tmp_path)
    assert cfg.costos_familia("AUTOMOTIVE").cuantil_critico == pytest.approx(0.5)


@pytest.mark.parametrize(
    "seccion, clave, valor",
    [
        ("operacion", "horizonte_dias", 0),
        ("operacion", "dia_pronostico", 7),
        ("operacion", "cuantiles", [0.5, 1.2]),
    ],
)
def test_config_invalida_falla(datos_config, tmp_path, seccion, clave, valor):
    datos = copy.deepcopy(datos_config)
    datos[seccion][clave] = valor
    with pytest.raises(ValueError):
        Config(datos, tmp_path)


def test_costo_no_positivo_falla(datos_config, tmp_path):
    datos = copy.deepcopy(datos_config)
    datos["costos"]["default"]["costo_merma"] = 0
    with pytest.raises(ValueError):
        Config(datos, tmp_path)
