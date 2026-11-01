"""Línea de comandos para ejecutar los pasos del producto fuera de Airflow.

Ejemplos::

    python -m reposicion.cli simular
    python -m reposicion.cli ingerir --corte 2017-07-10
    python -m reposicion.cli entrenar --corte 2017-07-10
    python -m reposicion.cli pronosticar --corte 2017-07-10
    python -m reposicion.cli seguimiento --fecha 2017-07-20
    python -m reposicion.cli operar --desde 2017-07-02 --hasta 2017-08-16
"""

from __future__ import annotations

import argparse
import json
import logging

import pandas as pd

from .config import cargar_config


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="reposicion")
    sub = p.add_subparsers(dest="comando", required=True)
    s = sub.add_parser("simular", help="Genera carga histórica y bandeja desde los CSV de Kaggle")
    s.add_argument("--forzar", action="store_true")
    for nombre in ("ingerir", "preparar", "entrenar", "pronosticar"):
        sub.add_parser(nombre).add_argument("--corte", required=True)
    sub.add_parser("seguimiento").add_argument("--fecha", required=True)
    o = sub.add_parser("operar", help="Ejecuta el flujo diario completo para un rango de fechas")
    o.add_argument("--desde", required=True)
    o.add_argument("--hasta", required=True)
    args = p.parse_args(argv)

    cfg = cargar_config()
    from . import entrenamiento, ingesta, pronostico, seguimiento, simulador

    if args.comando == "simular":
        meta = simulador.simular(cfg, forzar=args.forzar)
        print(json.dumps({k: v for k, v in meta.items() if k != "firma"}, indent=2))
    elif args.comando == "ingerir":
        print(json.dumps(ingesta.ingerir(cfg, args.corte)["faltantes"], indent=2))
    elif args.comando == "preparar":
        from .features import preparar

        print(json.dumps({k: v for k, v in preparar(cfg, args.corte).items() if k != "cortes"}, indent=2))
    elif args.comando == "entrenar":
        print(json.dumps(entrenamiento.entrenar(cfg, args.corte), indent=2, default=str))
    elif args.comando == "pronosticar":
        print(json.dumps(pronostico.pronosticar(cfg, args.corte), indent=2, default=str))
    elif args.comando == "seguimiento":
        print(seguimiento.seguimiento(cfg, args.fecha).to_string())
    elif args.comando == "operar":
        for fecha in pd.date_range(args.desde, args.hasta):
            ingesta.ingerir(cfg, fecha)
            if entrenamiento.es_dia_pronostico(cfg, fecha):
                entrenamiento.entrenar(cfg, fecha)
                pronostico.pronosticar(cfg, fecha)
            seguimiento.seguimiento(cfg, fecha)


if __name__ == "__main__":
    main()
