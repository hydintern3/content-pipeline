# Deployment Guide

This guide covers the production-oriented path: PostgreSQL for application data, Redis for Celery, and Docker Compose for one-command startup.

## One-Command Docker Deployment

From `content_pipeline/`:

```bash
docker compose up --build -d
```

Open:

```text
http://127.0.0.1:5000
```

The Compose stack starts four services:

- `web`: Flask API plus the built Vue frontend, served by Gunicorn.
- `worker`: Celery worker for generation, variant generation, and batch jobs.
- `postgres`: PostgreSQL 16 with a persistent volume.
- `redis`: Redis with append-only persistence for the Celery broker/result backend.

## Configuration

For a quick local container run, Compose provides safe defaults except for secrets. For production, set these values in the shell or in a local `.env` file before starting:

```bash
POSTGRES_PASSWORD=replace-with-a-strong-password
CONTENT_LLM_API_KEY=sk-...
CONTENT_LLM_BASE_URL=https://api.openai.com/v1
CONTENT_LLM_MODEL=gpt-4o-mini
DATABASE_URL=mysql+pymysql://pipeline_reader:replace-with-password@81.68.133.54:3306/shangying_mvp?charset=utf8mb4
APP_PORT=5000
CELERY_WORKER_CONCURRENCY=2
```

Use `.env.docker.example` as the reference list. Do not commit real `.env` files.

## PostgreSQL Runtime

The application reads its primary database from `APP_DATABASE_URL`. In Docker Compose it is set to:

```text
postgresql+psycopg://content_pipeline:content_pipeline@postgres:5432/content_pipeline
```

For external managed PostgreSQL, replace it with your provider URL and keep the `postgresql+psycopg://` driver prefix. The app also accepts `postgres://` and `postgresql://` and normalizes them to the psycopg driver.

## External Source MySQL

`APP_DATABASE_URL` and `DATABASE_URL` are separate connections:

- `APP_DATABASE_URL`: the pipeline application's primary PostgreSQL database for tasks, articles, logs, and generated history.
- `DATABASE_URL`: the external MySQL source database used by `POST /api/materials/pull_recent`.

For the Shangying mini-program source database, set:

```text
DATABASE_URL=mysql+pymysql://pipeline_reader:replace-with-password@81.68.133.54:3306/shangying_mvp?charset=utf8mb4
```

In Docker Compose, this value is passed to both `web` and `worker`. If you configure the app with `config.json` instead of environment variables, use:

```json
{
  "database": {
    "url": "mysql+pymysql://pipeline_reader:replace-with-password@81.68.133.54:3306/shangying_mvp?charset=utf8mb4"
  }
}
```

`config.shangying.example.json` contains the same PostgreSQL + Shangying MySQL layout and can be copied to `config.json` before replacing passwords.

Environment variables take precedence over `config.json`, so a non-empty `DATABASE_URL` in `.env` overrides `database.url`.

Database connection pool settings:

```text
APP_DB_POOL_SIZE=5
APP_DB_MAX_OVERFLOW=10
APP_DB_POOL_RECYCLE_SECONDS=1800
```

## SQLite to PostgreSQL Migration

1. Back up the existing SQLite file:

```bash
cp data/pipeline.db data/pipeline.backup.db
```

2. Start PostgreSQL only:

```bash
docker compose up -d postgres
```

3. Run the migration from a Python environment that has `requirements.txt` installed:

```bash
python scripts/migrate_sqlite_to_postgres.py \
  --sqlite-url sqlite:///data/pipeline.db \
  --postgres-url postgresql+psycopg://content_pipeline:content_pipeline@127.0.0.1:5432/content_pipeline
```

The migration refuses to import into a target database that already contains rows. If you intentionally want to replace target data after making a backup:

```bash
python scripts/migrate_sqlite_to_postgres.py \
  --sqlite-url sqlite:///data/pipeline.db \
  --postgres-url postgresql+psycopg://content_pipeline:content_pipeline@127.0.0.1:5432/content_pipeline \
  --truncate-target
```

4. Start the full stack:

```bash
docker compose up --build -d
```

## Scaling Workers

Generation work is handled by Celery, so workers can be scaled independently:

```bash
docker compose up -d --scale worker=3
```

The web service and every worker share PostgreSQL for state and Redis for queue coordination. Priority queues are configured for:

- `content_pipeline`
- `content_pipeline.generation`
- `content_pipeline.batch`

## Health Checks

The web container exposes:

```text
GET /api/health
```

It verifies database connectivity and is used by the Docker health check.

## Production Notes

- Use strong PostgreSQL passwords and managed backups.
- Prefer managed PostgreSQL and Redis for serious production use.
- Keep `app_data`, `postgres_data`, and `redis_data` volumes backed up according to your recovery target.
- Scale `web` and `worker` separately based on request traffic and generation throughput.
- PostgreSQL startup or connectivity failures now fail fast instead of silently falling back to a temporary SQLite database.
