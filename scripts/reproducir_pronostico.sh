#!/usr/bin/env bash
# Reproduce un pronóstico publicado en el pasado y verifica con DVC que es idéntico.
#
# Uso (desde la raíz del repo, con Docker corriendo):
#   git checkout <commit-o-tag>        # versión de código y de .dvc a reproducir
#   bash scripts/reproducir_pronostico.sh 2017-07-17
#
# Pasos:
#   1. dvc pull / checkout: restaura los datos exactamente como estaban versionados.
#   2. Borra features, modelo y pronóstico publicado de ese corte.
#   3. Los regenera en el contenedor de Airflow (mismo entorno de ejecución).
#   4. dvc status: si no reporta cambios, lo regenerado es idéntico byte a byte.
set -euo pipefail

CORTE="${1:?Uso: $0 AAAA-MM-DD}"
DVC="${DVC:-dvc}"
export MSYS_NO_PATHCONV=1   # Git Bash en Windows: no convertir rutas /opt/...
SALIDAS="data/features.dvc data/modelos.dvc data/publicados.dvc"

echo "== 1. Restaurar datos versionados (git $(git rev-parse --short HEAD))"
$DVC pull -q || $DVC checkout -q

echo "== 2. Borrar artefactos del corte $CORTE"
rm -rf "data/features/corte=$CORTE" "data/modelos/corte=$CORTE" "data/publicados/corte=$CORTE"
$DVC status $SALIDAS || true

echo "== 3. Regenerar en el contenedor"
docker compose run --rm --no-deps airflow-cli bash -c "cd /opt/airflow/proyecto \
  && python -m reposicion.cli preparar --corte $CORTE \
  && python -m reposicion.cli entrenar --corte $CORTE > /dev/null \
  && python -m reposicion.cli pronosticar --corte $CORTE > /dev/null" 2>&1 | grep -E "Publicado|Decisión|Error|Traceback" || true

echo "== 4. Comparar contra la versión en DVC"
$DVC status $SALIDAS
md5sum "data/publicados/corte=$CORTE/pedido.parquet" "data/publicados/corte=$CORTE/pronostico.parquet"
