# Python Agent Service (FastAPI + Google ADK). Build context: apps/agent
FROM python:3.11-slim

WORKDIR /app

# Install deps first (better layer caching), then the app package.
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

EXPOSE 8000

# Reads env (GEMINI_API_KEY etc.) from the process env injected by compose.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
