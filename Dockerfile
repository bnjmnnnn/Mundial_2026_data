# Mundial 2026 - Pipeline de Datos Sofascore
# Dockerfile para EXTRACCIÓN LOCAL (bronze)
# La transformación (silver + gold) corre en CI/CD de GitHub Actions

FROM python:3.11-slim

# Dependencias del sistema necesarias para curl_cffi y compilación
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

# ---------------------------------------------------------------------------
# Crear directorio de salida
# ---------------------------------------------------------------------------
RUN mkdir -p /app/data/raw

# ---------------------------------------------------------------------------
# Variables de entorno por defecto
# ---------------------------------------------------------------------------
ENV PYTHONUNBUFFERED=1
ENV RAW_DATA_PATH=/app/data/raw

# ---------------------------------------------------------------------------
# Ejecución: solo extracción (bronze)
# ---------------------------------------------------------------------------
CMD ["python", "-m", "src.extract.extract"]
