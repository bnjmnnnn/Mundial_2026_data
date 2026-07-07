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
| **Silver** | `data/silver/*.csv` + `*.parquet` | Tablas normalizadas (matches, stats, incidents) |
| **Gold** | `data/gold/*.csv` + `*.parquet` | Datasets ML por equipo, comparativas y agregados |

---

## Flujo de trabajo híbrido (local + CI/CD)

Dado que Sofascore bloquea IPs de datacenter, la **extracción** corre en tu PC local (IP residencial) y la **transformación** corre en GitHub Actions:

| Paso | Dónde | Comando |
|---|---|---|
| **1. Extraer** | **Tu PC** | `python -m src.extract.extract` o `docker-compose up --build` |
| **2. Subir raw** | **Git** | `git add data/raw/ && git push origin main` |
| **3. Transformar** | **GitHub Actions** | Automático al detectar `data/raw/**` |
| **4. Descargar silver** | **GitHub Actions** | Artifact `silver-data-XX.zip` |

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
│   └── utils/
│       └── config.py               # URLs, IDs y rutas
│
├── .github/workflows/
│   └── pipeline.yml                # CI/CD: transformación + artifacts
├── Dockerfile                      # Imagen del pipeline completo (local)
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
# Opción A: Con Docker (recomendada)
docker-compose up --build

# Opción B: Sin Docker
pip install -r requirements.txt
python -m src.extract.extract
```

Esto genera archivos JSON en `data/raw/`.

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
3. Al final de la página verás **Artifacts** → descarga `silver-data-XX.zip`

### 4. Generar capa Gold (ML) — local

La capa Gold se genera **localmente** a partir de la silver. No está en CI/CD porque es una transformación pura que no requiere IP específica.

```bash
# Con los datos silver ya generados (locales o descargados del artifact)
python -m src.transform.gold
```

Esto genera en `data/gold/`:
- `team_features.csv` — Dataset ML por selección
- `match_ml_dataset.csv` — Dataset ML por partido (comparativa)
- `team_tournament_agg.csv` — Agregados por selección

---

## CI/CD con GitHub Actions

El workflow se ejecuta automáticamente:

- **En cada push** que modifique `data/raw/` o `src/transform/`
- **Manualmente** desde la UI de GitHub (`workflow_dispatch`)

Pasos del workflow:
1. Checkout del código (incluye `data/raw/`)
2. Setup Python 3.11
3. Instalar dependencias
4. Verificar que existan datos raw
5. Ejecutar `python -m src.transform.transform` (capa silver)
6. Subir `data/silver/*.csv` y `*.parquet` como artifact ZIP

> **Nota:** La capa Gold se genera localmente con `python -m src.transform.gold` porque no requiere acceso a la API.

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
