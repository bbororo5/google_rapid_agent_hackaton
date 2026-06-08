# Python Agent Service (FastAPI + Google ADK). Build context: apps/agent
FROM python:3.11-slim

WORKDIR /app

# Node 20 + the MCP servers the evidence/reflection wrappers spawn via npx
# (Elastic ES|QL + Phoenix reflection, contract 04/06 method B). Installed and
# pre-cached at build so the running container needs no network npx download and
# works fully on `docker compose up` (no host node required). This heavy, stable
# layer is first so it caches across app/dep changes.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && npm install -g @tocharianou/elasticsearch-mcp@0.8.0 @arizeai/phoenix-mcp@4.0.13 \
 && apt-get purge -y gnupg && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/* /root/.npm

# Install deps first against a stub package so this heavy layer (google-adk,
# phoenix, ...) is cached and only re-runs when pyproject.toml changes — not on
# every app code edit. The real source is overlaid afterwards and takes
# precedence on sys.path (uvicorn runs from /app).
COPY pyproject.toml ./
RUN mkdir -p app && touch app/__init__.py && pip install --no-cache-dir . && rm -rf app
COPY app ./app

EXPOSE 8000

# Reads env (GOOGLE_GENAI_USE_VERTEXAI / GOOGLE_CLOUD_PROJECT for Vertex+ADC, or
# GEMINI_API_KEY for AI Studio) from the process env injected by compose. For
# Vertex+ADC in a container, mount a service-account JSON and point
# GOOGLE_APPLICATION_CREDENTIALS at it (gcloud user ADC is host-only).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
