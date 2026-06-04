# Python Agent Service (FastAPI + Google ADK). Build context: apps/agent
FROM python:3.11-slim

WORKDIR /app

# Install deps first (better layer caching), then the app package.
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

EXPOSE 8000

# Reads env (GOOGLE_GENAI_USE_VERTEXAI / GOOGLE_CLOUD_PROJECT for Vertex+ADC, or
# GEMINI_API_KEY for AI Studio) from the process env injected by compose. For
# Vertex+ADC in a container, mount a service-account JSON and point
# GOOGLE_APPLICATION_CREDENTIALS at it (gcloud user ADC is host-only).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
