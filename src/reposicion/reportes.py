"""Reportes en Markdown (comparación de modelos y seguimiento del desempeño)."""

from __future__ import annotations

import pandas as pd

from . import archivos as io
from .config import Config


def _tabla_md(df: pd.DataFrame) -> str:
    if df.empty:
        return "_Sin datos todavía._\n"

    def fmt(v):
        if isinstance(v, float):
            return "" if pd.isna(v) else f"{v:.3f}"
        if isinstance(v, pd.Timestamp):
            return v.strftime("%Y-%m-%d")
        return str(v)

    filas = ["| " + " | ".join(df.columns) + " |", "|" + "---|" * len(df.columns)]
    filas += ["| " + " | ".join(fmt(v) for v in r) + " |" for r in df.itertuples(index=False)]
    return "\n".join(filas) + "\n"


def _escribir(cfg: Config, nombre: str, texto: str) -> None:
    ruta = cfg.ruta("reportes") / nombre
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_name(f".{nombre}.tmp")
    tmp.write_text(texto, encoding="utf-8")
    tmp.replace(ruta)


def reporte_comparacion(cfg: Config) -> None:
    raiz = cfg.ruta("modelos")
    filas = []
    for p in sorted(raiz.glob("corte=*/entrenamiento.json")):
        info = io.leer_json(p)
        for nombre, m in info["metricas"].items():
            filas.append({
                "corte": info["corte"], "modelo": nombre, "wape": m["wape"], "sesgo": m["sesgo"],
                "cobertura_p10_p90": m["cobertura_p10_p90"], "costo_por_unidad": m["costo_por_unidad_vendida"],
                "vigente": "✅" if info["decision"]["vigente"] == nombre else "",
                "reemplazo": "sí" if info["decision"]["reemplaza"] and info["decision"]["vigente"] == nombre else "",
            })
    texto = (
        "# Comparación de modelos (backtest temporal)\n\n"
        "Generado automáticamente en cada entrenamiento semanal. Validación: últimos cortes semanales "
        "anteriores a cada corte (misma ventana para todos los modelos). `costo_por_unidad` = costo "
        "newsvendor del pedido semanal / unidades vendidas.\n\n" + _tabla_md(pd.DataFrame(filas))
    )
    _escribir(cfg, "comparacion_modelos.md", texto)


def reporte_seguimiento(cfg: Config, res: pd.DataFrame, fecha: pd.Timestamp) -> None:
    texto = (
        f"# Seguimiento del desempeño (al {fecha.strftime('%Y-%m-%d')})\n\n"
        "Pronósticos publicados comparados con las ventas reales conocidas a la fecha. Las métricas de "
        "pedido (costo, nivel de servicio, sobrante) aparecen cuando la semana completa ya tiene ventas reales.\n\n"
        + _tabla_md(res)
    )
    _escribir(cfg, "seguimiento.md", texto)
