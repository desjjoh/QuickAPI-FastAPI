# QuickAPI-FastAPI

A modular, production-grade FastAPI template designed for scalable backend services, strong security defaults, and consistent architectural patterns shared across the **QuickAPI** ecosystem (Express, NestJS, FastAPI).

---

## Features

- **Strict Pydantic validation** for configuration, requests, and responses
- **ASGI middleware suite**: header sanitization, security headers, body size limiting, rate limiting, request context, structured logging
- **Prometheus metrics** with protected `/metrics` endpoint
- **Unified error model** replacing default FastAPI 422 responses
- **Structured logging** using `structlog` with colored, contextual logs
- **OpenAPI documentation** with corrected schemas and custom error responses
- **Graceful shutdown** via FastAPI lifespan context
- **Modular folder structure** optimized for large-scale APIs
- **CORS + CSP** with strict production defaults
- **Developer‑friendly architecture** inspired by Express & NestJS templates

---

## Folder Structure

```bash
app/
├── config/                # Environment configuration
├── controllers/           # High-level request orchestration
├── database/
│   ├── entities/          # ORM models
│   └── repositories/      # Database abstraction layer
├── docs/                  # OpenAPI utilities & schema customization
├── handlers/              # Process-level handlers (signals, shutdown helpers)
├── middleware/            # All ASGI middleware (security, logging, rate limiting)
├── models/                # Pydantic schemas (ErrorModel, domain models, etc.)
├── routes/                # Router modules, metrics, system endpoints
├── store/                 # Request-scoped state (contextvars-backed)
└── main.py                # Application factory + middleware wiring
```

---

## Environment Variables (`.env`)

```bash
APP_NAME=QuickAPI
APP_VERSION=1.0.0

ENV=development
LOG_LEVEL=DEBUG

HOST=0.0.0.0
PORT=5000

DATABASE_URL=sqlite:///./dev.db
METRICS_API_KEY=dev-metrics
```

All values are validated on startup.
If validation fails, the application prints a clear diagnostic report and exits safely.

---

## Running the Application

### Local Development

```bash
pip install -r requirements.txt
uvicorn app.main:create_app --factory --reload --port 5000
```

### Swagger & ReDoc

```bash
http://localhost:5000/docs
http://localhost:5000/redoc
```

### Prometheus Metrics

```bash
http://localhost:5000/metrics
```

---

## Observability

### Logging

- colorized structured logs
- contextual `request_id`
- mute noisy framework logs
- environment-controlled log level

### Metrics

Prometheus middleware emits:

- request counts
- request latency histogram
- status code distribution

Example metric:

```bash
http_requests_total{method="GET",path="/api/v1/items",status="200"} 42
```

---

## Security Hardening

### Header Sanitization

Prevents:

- header injection
- smuggling vectors
- duplicate headers
- invalid characters

Trims non-whitelisted headers while allowing standard browser headers (connection, keep-alive, etc.).

### Body Size Limiting

Rejects large requests (`413 Payload Too Large`) with custom error model.

### Rate Limiting

Burst + sustained limits with lightweight in‑memory store.

### CORS & CSP

Secure-by-default configurations mirroring Express/Nest templates.

---

## Unified Error Model

All errors follow the same JSON envelope:

```json
{
  "status": 400,
  "message": "Missing required field: email",
  "timestamp": 1764310185
}
```

FastAPI’s 422 validation responses are fully overridden and documented in OpenAPI.

---

## Design Principles

- **Fail-fast validation** at every layer
- **Strict input sanitation**
- **Deterministic behavior** across environments
- **Predictable, platform-level architecture**
- **Production-first mindset** (observability, errors, shutdown, metrics)

---

## License

MIT License — Free for personal and commercial use.

---

QuickAPI-FastAPI — part of the **QuickAPI** ecosystem by **John Desjardins**.
