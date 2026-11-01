"""Línea de comandos para ejecutar los pasos del producto fuera de Airflow.

Ejemplos::

    python -m reposicion.cli simular
    python -m reposicion.cli ingerir --corte 2017-07-10
"""

from __future__ import annotations

import argparse
import json
import logging

from .config import cargar_config


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="reposicion")
    sub = p.add_subparsers(dest="comando", required=True)
    s = sub.add_parser("simular", help="Genera carga histórica y bandeja desde los CSV de Kaggle")
    s.add_argument("--forzar", action="store_true")
    i = sub.add_parser("ingerir", help="Ingesta y validación as-of una fecha de corte")
    i.add_argument("--corte", required=True)
    args = p.parse_args(argv)

    cfg = cargar_config()
    if args.comando == "simular":
        from .simulador import simular

        meta = simular(cfg, forzar=args.forzar)
        print(json.dumps({k: v for k, v in meta.items() if k != "firma"}, indent=2))
    elif args.comando == "ingerir":
        from .ingesta import ingerir

        rep = ingerir(cfg, args.corte)
        print(json.dumps(rep, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
