# Plan de Hitos: Pipeline de Datos Sofascore - Mundial 2026

## Estructura general del proyecto

El pipeline se divide en 5 fases: extraccion, transformacion, almacenamiento, orquestacion y CI/CD.
La API de Sofascore expone el Mundial bajo el tournament id 16, y desde ahi se navega a season -> events -> statistics por partido.

---

## Hito 1: Exploracion y mapeo de endpoints (2-3 dias)

- Confirmar el `seasonId` vigente del Mundial 2026 via `/tournament/16/seasons`
- Listar todos los partidos con `/tournament/{id}/season/{seasonId}/events` (o por ronda si el torneo es grande)
- Probar endpoint de estadisticas por partido `/event/{id}/statistics` y guardar un JSON de ejemplo
- Documentar los campos relevantes (posesion, tiros, xG, tarjetas, lineups) en un mapping propio

## Hito 2: Script de extraccion (extract) (3-4 dias)

- Funcion `get_events()` para traer todos los partidos del torneo, filtrando por seleccion o fase de grupos
- Funcion `get_event_statistics(event_id)` que recorre cada partido finalizado (status code 100)
- Manejo de rate-limiting y reintentos (backoff exponencial) para evitar bloqueos por headers/user-agent
- Guardar output crudo en formato JSON como capa "raw" (bronze) antes de transformar

## Hito 3: Transformacion y modelo de datos (transform) (3-4 dias)

- Normalizar JSON anidado a tablas planas con pandas: `matches`, `team_stats`, `player_stats`, `events_incidents`
- Definir esquema final (match_id, seleccion, rival, fecha, posesion, tiros, xG, resultado)
- Validaciones de calidad de datos (nulls, duplicados, tipos) con `pandera` o `pydantic`
- Exportar a CSV/Parquet como capa "silver"

## Hito 4: Almacenamiento y carga (load) (2-3 dias)

Dado el stack en Google Cloud, esta capa se integra naturalmente con experiencia previa en GCP e IAM.

- Elegir destino: BigQuery (recomendado para analisis) o Cloud Storage + capa Parquet
- Configurar service account con permisos minimos (principio de menor privilegio)
- Script de carga incremental (solo partidos nuevos/actualizados) usando `event_id` como clave

## Hito 5: Contenerizacion (2 dias)

- Dockerizar el pipeline completo (extract + transform + load) en un solo `Dockerfile`
- Variables de entorno para credenciales (nunca hardcodeadas) via secrets
- Prueba local con `docker-compose` simulando ejecucion programada

## Hito 6: CI/CD con GitHub Actions (3-4 dias)

- Workflow de CI: lint + tests unitarios en cada push/PR (pytest sobre funciones de extraccion/transformacion)
- Workflow de CD: build y push de imagen Docker a Artifact Registry (GCP) en merge a main
- Workflow programado (`schedule: cron`) que ejecuta el pipeline diario/cada X horas durante el Mundial
- Notificacion de fallos (Slack/email) si el job de scraping falla

## Hito 7: Monitoreo y dataset final (2-3 dias)

- Dashboard simple (Looker Studio o notebook) para verificar cobertura de partidos por seleccion
- Documentacion del dataset final (diccionario de columnas, fuente, frecuencia de actualizacion)
- Backup versionado del dataset en Cloud Storage con timestamp

---

## Resumen de cronograma

| Hito | Duracion estimada | Dependencia clave |
|---|---|---|
| 1. Exploracion endpoints | 2-3 dias | Ninguna |
| 2. Extraccion | 3-4 dias | Hito 1 |
| 3. Transformacion | 3-4 dias | Hito 2 |
| 4. Carga a GCP | 2-3 dias | Hito 3, IAM configurado |
| 5. Dockerizacion | 2 dias | Hitos 2-4 completos |
| 6. CI/CD | 3-4 dias | Hito 5 |
| 7. Monitoreo | 2-3 dias | Hito 6 |

**Total estimado:** 3-4 semanas trabajando part-time.
