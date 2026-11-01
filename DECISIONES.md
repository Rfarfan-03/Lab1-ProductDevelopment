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
  | Ventas | día siguiente (D+1) |
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
