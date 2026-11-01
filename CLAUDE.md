# CLAUDE.md — Reglas del proyecto

Motor de Reposición de Inventario (Laboratorio 1, Product Development). Pronostica ventas
diarias por tienda y familia (datos de Corporación Favorita / Kaggle), sugiere pedidos con
base en costos de negocio y da seguimiento al desempeño. Orquestado con Airflow 3, datos
versionados con DVC.

## Estructura
- `src/reposicion/` — toda la lógica (módulos de Python con pruebas).
- `dags/` — DAGs de Airflow. **Solo orquestan**: llaman funciones de `reposicion`, sin lógica de negocio.
- `config/config.yaml` — rutas, parámetros de simulación, costos, criterio de reemplazo de modelo.
- `tests/` — pruebas con pytest. Se ejecutan en cada PR con GitHub Actions.
- `data/` — datos (nunca en Git; versionados con DVC).

## Reglas no negociables
1. **Point-in-time**: toda predicción usa únicamente información entregada (fecha de entrega en
   la bandeja) hasta la fecha de corte. Nunca leer `data/kaggle` ni la bandeja completa sin filtrar
   por fecha de entrega al construir features o entrenar.
2. **La bandeja es de solo lectura**: el flujo nunca escribe, mueve ni borra archivos en `data/bandeja`.
3. **Idempotencia**: cada tarea reconstruye su salida de forma determinista a partir de sus entradas
   (escritura atómica a archivo temporal + rename). Ejecutar dos veces = ejecutar una vez.
4. **Publicados inmutables**: un pronóstico publicado para una fecha de corte no se sobreescribe con
   otro distinto; re-ejecutar debe producir el mismo archivo.
5. **Datos inválidos se detienen** (cuarentena + log); **situaciones esperadas no fallan**
   (archivo que no llegó, feriado, tienda cerrada, sin ventas).
6. **Nada de valores de negocio en el código**: costos, horizonte, cuantiles y umbrales van en
   `config/config.yaml`.
7. **Ningún dato ni modelo en Git**: usar DVC.

## Convenciones
- Código y nombres en español, Python 3.12, pandas + parquet.
- Fechas como `datetime64` normalizadas (sin hora); en nombres de archivo `YYYY-MM-DD`.
- Semillas fijas para reproducibilidad (`modelo.semilla`).
- Toda función nueva en `src/` lleva prueba en `tests/`. Correr `pytest` antes de abrir un PR.

## Flujo de trabajo Git
- `main` protegida: cambios solo mediante ramas `feat/*`, `fix/*`, `docs/*` y Pull Request.
- El CI (pytest) debe pasar antes de hacer merge.

## Comandos útiles
- Pruebas: `pytest`
- Levantar Airflow: ver `README.md`.
