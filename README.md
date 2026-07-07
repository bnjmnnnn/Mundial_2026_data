# Mundial 2026 Data Pipeline

Pipeline de extracción y transformación de datos del **Mundial de Fútbol 2026** desde la API no oficial de [Sofascore](https://www.sofascore.com).

Transforma JSONs anidados de partidos, estadísticas e incidentes en tablas planas listas para análisis.

---

## Arquitectura

```
┌─────────────┐     ┌─────────────────────────────────────────────┐
│   EXTRACT   │     │              CI/CD (GitHub Actions)          │
│  (bronze)   │     │                                             │
│  Tu PC      │ ──▶ │  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  Docker     │     │  │validate │  │ transform│  │validate  │  │
│             │     │  │   raw    │──▶│ silver   │──▶│ quality  │  │
└─────────────┘     │  └──────────┘  └──────────┘  └──────────┘  │
                    └─────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  Artifacts ZIP  │
                    │  - silver/      │
                    │  - gold/        │
                    │  - quality/     │
                    └─────────────────┘
```

| Capa | Formato | Contenido |
|---|---|---|
| **Bronze** | `data/raw/*.json` | Respuestas crudas de la API |
| **Silver** | `data/silver/*.csv` + `*.parquet` | Tablas normalizadas (matches, stats, incidents) |
| **Gold** | `data/gold/*.csv` + `*.parquet` | Datasets ML por equipo, comparativas y agregados |

---

## Flujo de trabajo híbrido (local + CI/CD)

| Paso | Quién | Qué hace | Resultado |
|---|---|---|---|
| **1. Extraer** | **Tu PC** | `docker-compose up --build` | `data/raw/*.json` |
| **2. Subir** | **Tú** | `git add data/raw/ && git push` | Dispara CI/CD |
| **3. Validar raw** | **GitHub Actions** | Verifica que existan JSONs | ✅ o ❌ |
| **4. Transformar** | **GitHub Actions** | Genera silver + gold | CSV/Parquet |
| **5. Validar calidad** | **GitHub Actions** | Checks de calidad de datos | Reporte MD |
| **6. Descargar** | **Tú** | Artifact `mundial2026-datasets-XX.zip` | Todo listo |

---

## Estructura del repositorio

```
.
├── data/
│   ├── raw/                        # JSONs crudos (se suben al repo)
│   │   ├── events/
│   │   ├── stats/
│   │   ├── incidents/
│   │   ├── details/
│   │   └── rounds/
│   ├── silver/                     # Generado por CI/CD (no se versiona)
│   └── gold/                       # Generado localmente (no se versiona)
│
├── src/
│   ├── extract/
│   │   ├── extract.py              # Pipeline de extracción masiva
│   │   └── sofascore_client.py     # Cliente HTTP con curl_cffi + backoff
│   ├── transform/
│   │   ├── transform.py            # Normalización a tablas planas (silver)
│   │   └── gold.py                 # Datasets ML por selección (gold)
│   ├── validate/
│   │   └── quality_checks.py       # Validación de calidad de datos
│   └── utils/
│       └── config.py               # URLs, IDs y rutas
│
├── .github/workflows/
│   └── pipeline.yml                # CI/CD: transformación + artifacts
├── Dockerfile                      # Imagen de EXTRACCIÓN LOCAL (bronze)
├── docker-compose.yml              # Orquestación local
├── requirements.txt                # Dependencias Python
└── README.md                       # Este archivo
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

## Capa Gold — ML & Apuestas Deportivas

Datasets optimizados para **modelos de Machine Learning** y análisis de apuestas. Cada fila representa una selección o un partido con features derivadas.

| Tabla | Filas | Descripción | Uso |
|---|---|---|---|
| `team_features` | 144 | Cada fila = una selección en un partido. Stats + contexto + targets | ML por equipo (regresión, clasificación) |
| `match_ml_dataset` | 72 | Cada fila = un partido. Comparativa Home vs Away con diferenciales | Predecir resultado 1X2, over/under, BTTS |
| `team_tournament_agg` | 48 | Stats agregadas por selección en todo el torneo | Dashboards, análisis comparativo, power rankings |

### Targets de apuestas incluidos

- `result` — W / D / L (clasificación)
- `goals_scored`, `goals_conceded` — regresión
- `over_2_5` — True/False (más de 2.5 goles en el partido)
- `btts` — Both Teams To Score (True/False)
- `clean_sheet` — Portería a cero (True/False)

### Features diferenciales (match_ml_dataset)

Columnas tipo `diff_*` que miden la **ventaja numérica** del local sobre el visitante:
- `diff_ballPossession` — diferencia de posesión
- `diff_expectedGoals` — diferencia de xG
- `diff_totalShotsOnGoal` — diferencia de tiros totales
- `diff_bigChanceCreated` — diferencia de ocasiones claras

Ideal para modelos que predicen resultados directos (1X2) o mercados de goles.

---

## Cómo usar

### 1. Extracción local (Bronze)

```bash
# Opción A: Con Docker (recomendada) — solo extracción
docker-compose up --build

# Opción B: Sin Docker
pip install -r requirements.txt
python -m src.extract.extract
```

Esto genera archivos JSON en `data/raw/` (capa bronze).

### 2. Subir datos al repositorio

```bash
git add data/raw/
git commit -m "data: add raw match data"
git push origin main
```

### 3. Transformación en CI/CD (Silver)

El push automáticamente dispara el workflow de GitHub Actions. Ve a tu repositorio:

1. **Actions** → **Mundial 2026 Pipeline**
2. Espera a que termine (sección verde ✅)
3. Al final de la página verás **Artifacts** → descarga `mundial2026-datasets-XX.zip`

El ZIP incluye **ambas capas**:
- `silver/*.csv` + `*.parquet` — Tablas normalizadas
- `gold/*.csv` + `*.parquet` — Datasets ML listos para usar

---

## CI/CD con GitHub Actions

Arquitectura de **3 jobs encadenados** con paso de artifacts entre ellos:

```
validate_raw  ──▶  transform  ──▶  validate_load
    │                  │                │
    ▼                  ▼                ▼
  ✅/❌          silver+gold      quality_report
```

### Triggers (cuándo corre)

| Trigger | Descripción |
|---|---|
| `push` | Cuando modificas `data/raw/` o código de transformación |
| `schedule` | **Cada día a las 06:00 UTC** (`cron: 0 6 * * *`) |
| `workflow_dispatch` | Manualmente desde la UI de GitHub (botón verde) |

### Jobs

| Job | Propósito | Output |
|---|---|---|
| **`validate_raw`** | Verifica que `data/raw/events/` tenga archivos | ✅ o ❌ |
| **`transform`** | Genera silver + gold | Artifacts: `silver-layer-XX`, `gold-layer-XX` |
| **`validate_load`** | Chequea calidad de datos + genera reporte | Artifact: `quality-report-XX` |

### Artifacts generados

| Artifact | Contenido | Retención |
|---|---|---|
| `silver-layer-XX` | `matches`, `team_stats`, `events_incidents`, etc. | 30 días |
| `gold-layer-XX` | `team_features`, `match_ml_dataset`, `team_tournament_agg` | 30 días |
| `quality-report-XX` | `quality_report.json` + `quality_report.md` | 30 días |

### Validaciones de calidad (job 3)

- ✅ Existencia de archivos silver/gold
- ✅ Columnas obligatorias sin nulos
- ✅ Rangos razonables (posesión 0-100, goles >= 0)
- ✅ Cardinalidad esperada (filas por tabla)
- ✅ Consistencia entre tablas (2 filas por match en team_stats)

> **Nota:** Tú solo subes `data/raw/`. El CI/CD hace el resto automáticamente.

---

## Tecnologías

- **Python 3.11**
- **curl_cffi** — impersonación de navegador para evitar bloqueos 403 (solo local)
- **pandas + pyarrow** — transformación y exportación a CSV/Parquet
- **Docker + Docker Compose** — contenerización para desarrollo local
- **GitHub Actions** — transformación programada en la nube

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
| 6. CI/CD con GitHub Actions (flujo híbrido) | ✅ |

---

## Nota sobre CI/CD

Sofascore bloquea con **HTTP 403** las peticiones provenientes de IPs de datacenter (incluyendo los runners públicos de GitHub). Por esta razón, la **extracción** se ejecuta localmente con `curl_cffi`, que imita un navegador real. La **transformación** sí puede correr en GitHub Actions porque opera sobre los archivos locales ya descargados.

---

## Licencia

Datos propiedad de Sofascore. Este repositorio contiene solo el código del pipeline, no los datos en sí.
