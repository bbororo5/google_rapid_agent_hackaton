"""Force STUB mode for tests, regardless of a populated repo-root .env.

Pre-setting these to "" before app.config imports means config's
load_dotenv(override=False) won't overwrite them, so tests stay deterministic
(no real Gemini / Elastic / Phoenix calls).
"""
import os

for _key in (
    "GEMINI_API_KEY",
    "GOOGLE_GENAI_USE_VERTEXAI",
    "GOOGLE_CLOUD_PROJECT",
    "ELASTIC_URL",
    "ELASTIC_API_KEY",
    "ELASTIC_MCP_URL",
    "ELASTIC_USE_MCP",
    "PHOENIX_API_KEY",
    "PHOENIX_USE_MCP",
):
    os.environ[_key] = ""
