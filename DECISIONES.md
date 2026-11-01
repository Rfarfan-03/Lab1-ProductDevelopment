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
