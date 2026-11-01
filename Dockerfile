FROM apache/airflow:3.1.8-python3.12

# LightGBM necesita la librería de OpenMP del sistema.
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
USER airflow

# Dependencias de la lógica del producto (misma lista que usa el CI).
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
