# Mundial 2026 Data Pipeline

Pipeline de extracción y transformación de datos del **Mundial de Fútbol 2026** desde la API no oficial de [Sofascore](https://www.sofascore.com).

Transforma JSONs anidados de partidos, estadísticas e incidentes en tablas planas listas para análisis.

---

## Arquitectura

```
Sofascore API
      │
      ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Extract   │ ──▶ │  Transform  │ ──▶ │   Silver    │
│  (bronze)   │     │   (silver)  │     │  artifacts  │
│  raw JSONs  │     │ CSV/Parquet │     │  (GitHub)   │
└─────────────┘     └─────────────┘     └─────────────┘
```

| Capa | Formato | Contenido |
|---|---|---|
| **Bronze** | `data/raw/*.json` | Respuestas crudas de la API |
| **Silver** | `data/silver/*.csv` + `*.parquet` | Tablas normalizadas con pandas |

---

## Estructura del repositorio

```
.
├── src/
│   ├── extract/
│   │   ├── extract.py              # Pipeline de extracción masiva
│   │   └── sofascore_client.py     # Cliente HTTP con curl_cffi + backoff
│   ├── transform/
│   │   └── transform.py            # Normalización a tablas planas
│   └── utils/
│       └── config.py               # URLs, IDs y rutas
├── .github/workflows/
│   └── pipeline.yml                # CI/CD: Docker + artifacts
├── Dockerfile                      # Imagen del pipeline completo
├── docker-compose.yml              # Orquestación local
├── requirements.txt                # Dependencias Python
└── plan_hitos_sofascore_mundial2026.md  # Plan original del proyecto
```

---

## Tablas generadas (capa Silver)

| Tabla | Filas | Descripción |
|---|---|---|
| `matches` | 72 | Info base de cada partido (equipos, marcador, estadio, árbitro) |
| `team_stats` | 144 | Estadísticas por equipo/partido (posesión, tiros, xG, tarjetas, etc.) |
| `events_incidents` | 1,421 | Todos los incidentes: goles, tarjetas, sustituciones |
| `match_goals` | 215 | Subconjunto: solo goles (con asistencia, bodyPart, coordenadas) |
| `match_cards` | 189 | Subconjunto: tarjetas amarillas/rojas |
| `match_substitutions` | 688 | Subconjunto: cambios de jugadores |

> **Nota:** El Mundial 2026 tiene **104 partidos** totales. Hoy hay **72 partidos finalizados** disponibles. El pipeline se ejecuta automáticamente para capturar los nuevos.

---

## Cómo usar

### Local (con Docker)

```bash
# Extraer datos + transformar en un solo comando
docker compose up --build
```

Los archivos se guardan en el volumen Docker `mundial_data`.

### Local (sin Docker)

```bash
pip install -r requirements.txt

# 1. Extraer datos crudos (bronze)
python -m src.extract.extract

# 2. Transformar a tablas planas (silver)
python -m src.transform.transform
```

Output en `data/raw/` y `data/silver/`.

---

## CI/CD con GitHub Actions

El workflow ejecuta el pipeline automáticamente:

- **Cada día a las 06:00 UTC** (`cron`)
- **En cada push a `main`**
- **Manualmente** desde la UI de GitHub (`workflow_dispatch`)

Los artifacts de la capa Silver (CSV + Parquet) se guardan como ZIP descargable en cada ejecución.

---

## Tecnologías

- **Python 3.11**
- **curl_cffi** — impersonación de navegador para evitar bloqueos 403
- **pandas + pyarrow** — transformación y exportación a CSV/Parquet
- **Docker + Docker Compose** — contenerización del pipeline
- **GitHub Actions** — orquestación programada

---

## API endpoints utilizados

```
https://api.sofascore.com/api/v1
├── /unique-tournament/16/seasons
├── /unique-tournament/16/season/58210/events/round/{round}
├── /event/{id}/statistics
├── /event/{id}/incidents
└── /event/{id}
```

**Tournament ID:** `16`  
**Season ID:** `58210` (World Cup 2026)

---

## Roadmap / Hitos completados

| Hito | Estado |
|---|---|
| 1. Exploración y mapeo de endpoints | ✅ |
| 2. Script de extracción (bronze) | ✅ |
| 3. Transformación y modelo de datos (silver) | ✅ |
| 5. Dockerización | ✅ |
| 6. CI/CD con GitHub Actions | ✅ |

---

## Licencia

Datos propiedad de Sofascore. Este repositorio contiene solo el código del pipeline, no los datos en sí.
