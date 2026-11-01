"""DAG diario del Motor de Reposición de Inventario.

Solo orquesta: cada tarea llama una función de ``reposicion.tareas``.

    simular_origen -> ingerir_y_validar -> es_dia_pronostico -> preparar_datos
                                   |                              -> entrenar_y_evaluar -> pronosticar_y_publicar
                                   +--------------------------------------------------------> seguimiento

- Cada ejecución procesa la fecha de corte ``ds`` (catchup = backfill del periodo completo).
- ``max_active_runs=1``: los días se procesan en orden (el modelo vigente depende del corte anterior).
- Los días que no son de pronóstico, el short-circuit omite preparar/entrenar/pronosticar
  (situación esperada, no falla) y el seguimiento corre igual.
"""

from __future__ import annotations

from datetime import timedelta

import pendulum
from airflow.sdk import dag, task
from airflow.task.trigger_rule import TriggerRule

from reposicion import tareas

INICIO, FIN = tareas.rango_operacion()


@dag(
    dag_id="reposicion_diaria",
    schedule="@daily",
    start_date=pendulum.instance(INICIO.to_pydatetime(), tz="UTC"),
    end_date=pendulum.instance(FIN.to_pydatetime(), tz="UTC"),
    catchup=True,
    max_active_runs=1,
    is_paused_upon_creation=False,
    default_args={"retries": 1, "retry_delay": timedelta(seconds=30)},
    tags=["reposicion"],
    doc_md=__doc__,
)
def reposicion_diaria():
    @task
    def simular_origen():
        return tareas.simular_origen()

    @task
    def ingerir_y_validar(ds=None):
        return tareas.ingerir(ds)

    @task.short_circuit(ignore_downstream_trigger_rules=False)
    def es_dia_pronostico(ds=None):
        return tareas.es_dia_pronostico(ds)

    @task
    def preparar_datos(ds=None):
        return tareas.preparar(ds)

    @task
    def entrenar_y_evaluar(ds=None):
        return tareas.entrenar(ds)

    @task
    def pronosticar_y_publicar(ds=None):
        return tareas.pronosticar(ds)

    @task(trigger_rule=TriggerRule.NONE_FAILED)
    def seguimiento(ds=None):
        return tareas.dar_seguimiento(ds)

    origen, ingesta, decision = simular_origen(), ingerir_y_validar(), es_dia_pronostico()
    prep, entren, publicar, segui = preparar_datos(), entrenar_y_evaluar(), pronosticar_y_publicar(), seguimiento()

    origen >> ingesta >> decision >> prep >> entren >> publicar >> segui
    ingesta >> segui


reposicion_diaria()
