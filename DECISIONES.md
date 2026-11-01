# Decisiones técnicas y de producto

## Producto

### D1. Pedido sugerido con el modelo newsvendor y costos por familia
- **Decisión:** el pedido es el cuantil crítico `costo_quiebre / (costo_quiebre + costo_merma)` de la demanda pronosticada. Los costos se definen por familia en `config/config.yaml`.
- **Alternativas:** stock de seguridad fijo (media + k·σ); un solo par de costos para todas las familias.
- **Justificación:** traduce directamente el trade-off quiebre vs. merma en una cantidad y cambia con la configuración, sin tocar código. Los perecederos tienen merma más cara y por eso se pide un cuantil más bajo. Los valores de costo son **supuestos**, porque Kaggle no incluye márgenes ni costos.

### D2. Pronóstico semanal (lunes) con horizonte de 7 días
- **Decisión:** el pronóstico y el pedido se emiten cada lunes para los 7 días siguientes. La ingesta y el seguimiento corren a diario.
- **Alternativas:** emitir pronósticos diarios; horizonte de 14 días.
- **Justificación:** el negocio pide una sugerencia semanal y un horizonte corto reduce el error. El día y el horizonte son configurables.

## Disponibilidad de la información en el tiempo

### D3. Cada fuente llega con distinto retraso o anticipación
- **Decisión:**

  | Fuente | Disponible |
  |---|---|
  | Ventas | día siguiente (D+1); algunos archivos llegan 2 días tarde |
  | Transacciones | dos días después (D+2); algunos archivos no llegan |
  | Petróleo | D+1, solo días hábiles |
  | Promociones | 14 días antes |
  | Feriados | 30 días antes |
  | Tiendas | carga inicial |

- **Alternativas:** que todas las fuentes lleguen el mismo día.
- **Justificación:** refleja la operación real que describe el enunciado. Los CSV de Kaggle traen petróleo y feriados posteriores a la última venta; usarlos sin este filtro filtraría información del futuro.

### D4. Point-in-time por fecha de entrega
- **Decisión:** cada archivo de la bandeja indica en su nombre la fecha del dato y la fecha de entrega. En cada fecha de corte solo se usan los archivos entregados hasta ese día.
- **Alternativas:** filtrar solo por la fecha del dato.
- **Justificación:** filtrar por fecha del dato no evita usar correcciones ni datos tardíos que en ese momento aún no existían. Así se garantiza que cada pronóstico se pueda reconstruir con lo que se sabía al emitirlo.

### D5. Corte del histórico derivado de los datos
- **Decisión:** la carga histórica termina `dias_bandeja` (45) días antes de la última fecha de `train.csv`; todo lo posterior se convierte en archivos de la bandeja. La fecha se puede fijar en la config.
- **Alternativas:** una fecha fija en el código.
- **Justificación:** el producto se evaluará sobre un periodo no publicado. Si se calcula a partir de los archivos colocados, el flujo funciona con cualquier rango de fechas sin cambiar el código.

## Validación de datos y correcciones

### D6. Validación en dos niveles con cuarentena
- **Decisión:** se valida el esquema, los tipos, los rangos (por ejemplo, ventas negativas), las tiendas y familias desconocidas, la fecha que no coincide con la del archivo y las llaves duplicadas. Si menos del 1% de las filas son inválidas, se descartan solo esas filas; si se supera el 1%, el archivo completo va a `data/cuarentena/` con un JSON que explica el motivo y se usa la última versión válida anterior, si existe.
- **Alternativas:** fallar la tarea ante cualquier error; descartar siempre solo las filas malas.
- **Justificación:** fallar detiene toda la operación por un archivo, y descartar siempre filas deja pasar archivos sistemáticamente corruptos. Las situaciones esperadas (un archivo que no llegó, petróleo sin precio, ventas en cero) se reportan como aviso y no fallan.

### D7. Correcciones como nuevas versiones; el staging se reconstruye en cada corte
- **Decisión:** una corrección llega como un archivo nuevo `__v2` (la bandeja nunca se sobreescribe). En cada fecha de corte, la ingesta reconstruye el staging desde cero con la versión válida más reciente entregada hasta ese día.
- **Alternativas:** aplicar las correcciones de forma incremental (upsert) sobre una tabla acumulada.
- **Justificación:** reconstruir es idempotente y reproduce exactamente lo que se sabía en un corte pasado, lo que permite el backfill. Con un upsert, el estado depende del orden de ejecución. Con estos datos el costo es bajo (~4 s por corte).

## Modelado

### D8. Las features solo usan lo conocido en el corte
- **Decisión:** para el corte `c` y el día objetivo `c+h`, las ventas se toman hasta `c-1`. Las promociones y los feriados del día objetivo se usan porque ya fueron publicados en `c`. Los rezagos del mismo día de la semana saltan las semanas que todavía no se conocen.
- **Justificación:** es el principio point-in-time aplicado al modelo. Una prueba lo verifica: si se alteran las ventas desde `c`, las features no cambian.

### D9. Baseline simple y LightGBM global; sin deep learning
- **Decisión:** el baseline es el promedio del mismo día de la semana en las últimas 4 semanas. El modelo de ML es un LightGBM global (todas las tiendas-familias en un solo modelo) entrenado sobre `log1p(ventas)` con features de ventanas, calendario, promociones, feriados, transacciones y petróleo.
- **Alternativas:** un modelo por serie (ARIMA/ETS, son 1 782 series); deep learning (N-BEATS, TFT).
- **Justificación:** un modelo global comparte información entre series con poca venta y entrena en unos 30 s. El deep learning implicaría más costo de cómputo y de operación (GPU, tiempos de entrenamiento semanales) sin una ganancia demostrada en esta escala de datos, así que no se usó.

### D10. Validación temporal idéntica para todos los modelos
- **Decisión:** en cada entrenamiento semanal se usan como validación los últimos 8 cortes semanales cuyo horizonte ya es conocido, y los modelos se entrenan solo con cortes anteriores. Los primeros 4 cortes de validación calibran la incertidumbre y los últimos 4 miden cobertura y costo fuera de muestra.
- **Alternativas:** validación cruzada aleatoria (filtraría información del futuro); una sola partición fija.
- **Justificación:** respeta el orden del tiempo y compara a todos los modelos en la misma ventana, como pide el enunciado.

### D11. Incertidumbre por residuos empíricos y pedido sobre la demanda semanal
- **Decisión:** los cuantiles (p10/p50/p90 diarios) salen de los residuos fuera de muestra en escala log por familia. El pedido usa la distribución de residuos de la **suma semanal**, evaluada en el cuantil crítico de cada familia.
- **Alternativas:** LightGBM con pérdida cuantílica (un modelo por cuantil); sumar los cuantiles diarios.
- **Justificación:** se guarda la distribución completa, así que un cambio de costos cambia el pedido sin reentrenar. Sumar cuantiles diarios sobreestima el cuantil de la semana. El mismo método aplica al baseline, lo que hace justa la comparación.
- **Métricas:** técnicas: WAPE, sesgo y cobertura p10–p90. De negocio: costo newsvendor `cu·faltante + co·sobrante` del pedido semanal, por unidad vendida.

### D12. Criterio de reemplazo del modelo vigente
- **Decisión:** el vigente inicial es el baseline. Cada semana se evalúan todos los candidatos en la misma ventana. El mejor retador reemplaza al vigente si reduce el costo de negocio al menos un 2% y no empeora el WAPE más de 0.01 (configurable). El vigente se reentrena con toda la historia antes de publicar.
- **Justificación:** la decisión se basa en la métrica de negocio, con un margen para no cambiar de modelo por ruido. En el primer corte real, LightGBM redujo el costo un 27% (WAPE 0.127 vs. 0.151) y reemplazó al baseline.

## Orquestación

### D13. Un DAG diario con catchup; el pronóstico se activa los lunes
- **Decisión:** el DAG `reposicion_diaria` corre una vez por fecha de corte: `simular_origen → ingerir_y_validar → es_dia_pronostico → preparar_datos → entrenar_y_evaluar → pronosticar_y_publicar → seguimiento`. Un *short-circuit* omite los pasos de pronóstico los días que no son lunes (sin fallar) y el seguimiento corre todos los días. Las fechas de inicio y fin del DAG se derivan de `train.csv`, y tiene `catchup=True` y `max_active_runs=1`.
- **Alternativas:** varios DAGs conectados por Assets; un DAG semanal separado del diario.
- **Justificación:** con un solo DAG y los días en orden, el backfill es simplemente el catchup del periodo, y el modelo vigente de un lunes depende de la decisión del lunes anterior. Como cada tarea es idempotente, re-ejecutar cualquier día (o un rango con `airflow backfill`) da el mismo resultado. El paso `simular_origen` representa al sistema externo; si los archivos de Kaggle no cambiaron, no hace nada.

### D14. Correcciones posteriores a una publicación
- **Decisión:** un pronóstico publicado no se modifica cuando llega una corrección de datos posterior. La corrección se incorpora en la ingesta de los días siguientes: en los próximos entrenamientos y pronósticos, y en el seguimiento, que siempre compara contra la versión corregida de las ventas.
- **Alternativas:** re-publicar los pronósticos afectados.
- **Justificación:** el pedido ya se emitió con la información de ese momento. Re-publicarlo rompería la trazabilidad (qué se recomendó y con qué datos). El seguimiento sí debe medir contra la venta real corregida.
