
# Video/Audio Streaming Platform 🎬

A modern distributed video/audio streaming platform with:
- Async media processing (RQ workers)
- Real-time CDC (Debezium + Kafka)
- PostgreSQL + FTS search
- S3-compatible storage (RustFS)
- FastAPI backend + simple frontend

---

## 🚀 Features

- 🎥 Media upload & streaming (MP4, HLS)
- ⚙️ Background processing with Redis Queue (RQ)
- 🔄 Change Data Capture (Debezium + Kafka)
- 🗄 PostgreSQL full-text search (FTS triggers)
- ☁️ S3-compatible storage (RustFS)
- 📡 REST API (FastAPI + OpenAPI docs)
- 🐳 Fully containerized (Podman/Docker Compose)

---

## 🏗️ Architecture

```
Frontend → FastAPI → PostgreSQL
                ↓
        Redis Queue (RQ Workers)
                ↓
              RustFS (Storage)

PostgreSQL → Debezium → Kafka (CDC Stream)
```

---

## 📁 Project Structure

```
videoaudionstreaming/
├── backend
│   ├── alembic
│   │   ├── env.py
│   │   └── versions/
│   ├── core/
│   │   └── settings.py
│   ├── media/
│   │   ├── models.py
│   │   ├── repository.py
│   │   ├── routers.py
│   │   ├── schemas.py
│   │   ├── services.py
│   │   └── workers.py
│   ├── scripts/
│   │   ├── commands/
│   │   ├── commons/
│   │   └── main.py
│   ├── utils/
│   │   ├── database.py
│   │   ├── queue.py
│   │   ├── s3storage.py
│   │   └── validators.py
│   ├── docker-compose.yaml
│   ├── main.py
│   ├── pyproject.toml
│   └── uv.lock
├── frontend
│   ├── css/
│   ├── js/
│   ├── index.html
│   └── server.py
└── README.md
```

---

## ⚙️ Prerequisites

- Python 3.14+
- Podman or Docker
- 8GB RAM minimum
- 50GB storage recommended

---

## 🚀 Full Setup Guide

### 1. Clone project

```bash
git clone <your-repo-url>
cd videoaudionstreaming
```

---

### 2. Start infrastructure (Docker/Podman)

```bash
cd backend
podman compose up -d
```

Services started:
- PostgreSQL (5432)
- Redis (6379)
- Kafka (9092)
- Debezium Connect (8083)
- Kafka UI (8090)
- Adminer (8080)
- RedisInsight (5540)
- RustFS (9000)

---

### 3. Setup backend environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

---

### 4. Run migrations

```bash
alembic upgrade head
```

---

### 5. Bootstrap system (IMPORTANT)

```bash
python -m scripts.main run-all
```

This will:
- Install DB triggers (FTS + slug)
- Setup PostgreSQL replication settings
- Create Debezium publication
- Generate `debezium_config.json`

---

### 6. Start backend API

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API:
- http://localhost:8000/docs
- http://localhost:8000/redoc

---

### 7. Start RQ workers

```bash
rq worker media thumbnails waveform
```

---

### 8. Start frontend (optional)

```bash
cd frontend
python server.py
```

Frontend:
- http://localhost:3000

---

### 9. Register Debezium connector

```bash
curl -X POST http://localhost:8083/connectors \
  -H "Content-Type: application/json" \
  -d @debezium_config.json
```

---

## 🧪 Common Commands

### Database

```bash
alembic upgrade head
alembic downgrade -1
alembic history
```

### System bootstrap

```bash
python -m scripts.main run-all
python -m scripts.main triggers status
python -m scripts.main debezium status
```

### Docker/Podman

```bash
podman compose up -d
podman compose ps
podman compose logs -f
```

### Workers

```bash
rq worker media thumbnails waveform
```

### Debug Redis

```bash
redis-cli ping
```

---

## 📡 API Endpoints

### Media

```
POST   /media-assets/upload
GET    /media-assets/{id}
GET    /media-assets
DELETE /media-assets/{id}
GET    /media-assets/{id}/stream
GET    /media-assets/{id}/thumbnail
```

---

## 🔄 Media Pipeline

1. Upload file
2. Store temporary file
3. Create processing job (Redis Queue)
4. Worker transcodes media
5. Store in RustFS
6. PostgreSQL updated
7. Debezium captures changes
8. Kafka streams events

---

## ⚠️ Known Issues / Fixes

### Redis connection refused

```bash
podman compose restart redis
```

Ensure:
```
REDIS_URL=redis://localhost:6379/0
```

---

### Debezium not capturing

Check:

```bash
SHOW wal_level;
```

Must be:
```
logical
```

---

## 🔧 Environment Variables

```env
POSTGRES_USER=videoaudionstreaming
POSTGRES_PASSWORD=strong_password
POSTGRES_DB=videoaudionstreaming_db

REDIS_URL=redis://localhost:6379/0

RUSTFS_ACCESS_KEY=admin
RUSTFS_SECRET_KEY=secret
RUSTFS_BUCKET_NAME=media
RUSTFS_ENDPOINT=http://localhost:9000
```

---

## 📦 Services

| Service | Port |
|--------|------|
| FastAPI | 8000 |
| PostgreSQL | 5432 |
| Redis | 6379 |
| Kafka | 9092 |
| Debezium | 8083 |
| Kafka UI | 8090 |
| RustFS | 9000 |
| Adminer | 8080 |
| RedisInsight | 5540 |

---
