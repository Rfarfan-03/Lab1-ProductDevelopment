# Comparación de modelos (backtest temporal)

Generado automáticamente en cada entrenamiento semanal. Validación: últimos cortes semanales anteriores a cada corte (misma ventana para todos los modelos). `costo_por_unidad` = costo newsvendor del pedido semanal / unidades vendidas.

| corte | modelo | wape | sesgo | cobertura_p10_p90 | costo_por_unidad | vigente | reemplazo |
|---|---|---|---|---|---|---|---|
| 2017-07-03 | baseline | 0.151 | 0.002 | 0.823 | 0.058 |  |  |
| 2017-07-03 | lightgbm | 0.127 | -0.029 | 0.821 | 0.042 | ✅ | sí |
| 2017-07-10 | baseline | 0.150 | 0.010 | 0.827 | 0.048 |  |  |
| 2017-07-10 | lightgbm | 0.124 | -0.018 | 0.823 | 0.041 | ✅ |  |
| 2017-07-17 | baseline | 0.144 | 0.002 | 0.812 | 0.052 |  |  |
| 2017-07-17 | lightgbm | 0.117 | -0.029 | 0.816 | 0.042 | ✅ |  |
| 2017-07-24 | baseline | 0.144 | 0.007 | 0.824 | 0.054 |  |  |
| 2017-07-24 | lightgbm | 0.116 | -0.019 | 0.817 | 0.047 | ✅ |  |
| 2017-07-31 | baseline | 0.140 | 0.006 | 0.814 | 0.051 |  |  |
| 2017-07-31 | lightgbm | 0.114 | -0.016 | 0.814 | 0.045 | ✅ |  |
| 2017-08-07 | baseline | 0.134 | 0.018 | 0.818 | 0.049 |  |  |
| 2017-08-07 | lightgbm | 0.116 | -0.017 | 0.803 | 0.050 | ✅ |  |
| 2017-08-14 | baseline | 0.139 | 0.009 | 0.803 | 0.060 |  |  |
| 2017-08-14 | lightgbm | 0.117 | -0.006 | 0.782 | 0.054 | ✅ |  |
