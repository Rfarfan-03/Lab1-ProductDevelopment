#!/usr/bin/env bash
# Versiona con DVC el estado actual de los datos (entradas, procesados, modelos,
# pronósticos publicados y seguimiento) y lo sube al remoto.
#
# Uso (desde la raíz del repo, después de que Airflow procesó un periodo):
#   bash scripts/versionar_datos.sh
#   git add data/*.dvc && git commit -m "data: versión de datos al <fecha>"
set -euo pipefail

DVC="${DVC:-dvc}"
CARPETAS="kaggle historico bandeja staging cuarentena features modelos publicados seguimiento"

for c in $CARPETAS; do
  [ -d "data/$c" ] && $DVC add -q "data/$c"
done
$DVC push
git status --short data/
echo "Listo. Haga commit de los archivos data/*.dvc para registrar esta versión de datos."
