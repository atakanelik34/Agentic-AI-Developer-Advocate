# Kairos Rain Chat Panel

Kairos için matrix-style frontend paneli. Bu UI, `revenuecat-agent` FastAPI backend'iyle konuşur.

## Features

- `/chat` ile interaktif konuşma
- `/health` ile canlı durum göstergesi
- Panel üstünden workflow tetikleme:
  - `trigger-content`
  - `trigger-community`
  - `trigger-feedback`
  - `trigger-report`

## Local Setup

```bash
npm install
```

`.env` dosyası oluştur:

```bash
VITE_BACKEND_URL=http://localhost:8000
```

Dev server:

```bash
npm run dev
```

Build:

```bash
npm run build
```

## Backend Requirements

`revenuecat-agent` tarafında API açık olmalı:

- `POST /chat`
- `GET /health`
- `POST /webhook/trigger-content`
- `POST /webhook/trigger-community`
- `POST /webhook/trigger-feedback`
- `POST /webhook/trigger-report`

Not: Vite local origin için backend tarafında CORS açılmış olmalı.
