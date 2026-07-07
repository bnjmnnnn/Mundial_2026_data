# Mundial 2026 - Pipeline de Datos Sofascore
# Dockerfile para ejecutar extract + transform en un contenedor

FROM python:3.11-slim

# ---------------------------------------------------------------------------
# Dependencias del sistema necesarias para curl_cffi y compilación
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcurl4 \
    libssl-dev \
    libffi-dev \
    python3-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# Configuración del entorno
# ---------------------------------------------------------------------------
WORKDIR /app

# Copiar e instalar dependencias Python primero (cache de Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---------------------------------------------------------------------------
# Copiar código fuente
# ---------------------------------------------------------------------------
COPY src/ ./src/
COPY plan_hitos_sofascore_mundial2026.md .

# ---------------------------------------------------------------------------
# Crear directorios de salida
# ---------------------------------------------------------------------------
RUN mkdir -p /app/data/raw /app/data/silver

# ---------------------------------------------------------------------------
# Variables de entorno por defecto
# ---------------------------------------------------------------------------
ENV PYTHONUNBUFFERED=1
ENV RAW_DATA_PATH=/app/data/raw
ENV SILVER_DATA_PATH=/app/data/silver

# ---------------------------------------------------------------------------
# Ejecución del pipeline completo
# ---------------------------------------------------------------------------
CMD ["sh", "-c", "python -m src.extract.extract && python -m src.transform.transform"]
