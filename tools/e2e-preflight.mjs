import fs from "node:fs";
import path from "node:path";

const envFile = process.env.E2E_ENV_FILE ?? ".env";
const envPath = path.resolve(process.cwd(), envFile);

function fail(message) {
  console.error(`E2E preflight failed: ${message}`);
  process.exit(1);
}

if (!fs.existsSync(envPath)) {
  fail(`missing env file ${envFile}. Set E2E_ENV_FILE=s.env or create .env from .env.example.`);
}

const raw = fs.readFileSync(envPath, "utf8");
const env = Object.fromEntries(
  raw
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith("#") && line.includes("="))
    .map((line) => {
      const index = line.indexOf("=");
      return [line.slice(0, index), line.slice(index + 1).replace(/^["']|["']$/g, "")];
    }),
);

function value(name) {
  return process.env[name] ?? env[name] ?? "";
}

const hasAiStudio = Boolean(value("GEMINI_API_KEY"));
const hasVertex = value("GOOGLE_GENAI_USE_VERTEXAI").toUpperCase() === "TRUE" && Boolean(value("GOOGLE_CLOUD_PROJECT"));
const llmProvider = value("LLM_PROVIDER") || "gemini";
const hasLocalLlm = ["ollama", "local"].includes(llmProvider.toLowerCase()) && Boolean(value("LOCAL_LLM_MODEL"));
if (!hasLocalLlm && !hasAiStudio && !hasVertex) {
  fail("LLM configuration is required. Set LLM_PROVIDER=ollama + LOCAL_LLM_MODEL, GEMINI_API_KEY, or GOOGLE_GENAI_USE_VERTEXAI=TRUE + GOOGLE_CLOUD_PROJECT.");
}

if (!value("ELASTIC_URL")) {
  fail("Elastic URL is required. Set ELASTIC_URL.");
}

if (hasVertex) {
  const adcFile = value("GOOGLE_ADC_FILE") || "./secrets/adc.json";
  if (!fs.existsSync(path.resolve(process.cwd(), adcFile))) {
    fail(`Vertex ADC file not found at ${adcFile}. Set GOOGLE_ADC_FILE or use GEMINI_API_KEY.`);
  }
}

if (process.env.E2E_REQUIRE_PHOENIX === "true" && !value("PHOENIX_API_KEY")) {
  fail("E2E_REQUIRE_PHOENIX=true requires PHOENIX_API_KEY.");
}

const llmLabel = hasLocalLlm ? `${llmProvider}:${value("LOCAL_LLM_MODEL")}` : `gemini:${hasAiStudio ? "ai-studio" : "vertex"}`;
const elasticLabel = value("ELASTIC_API_KEY") ? "cloud" : "local";
console.log(`E2E preflight passed using ${envFile}. LLM=${llmLabel} Elastic=${elasticLabel} Phoenix=${value("PHOENIX_API_KEY") ? "enabled" : "optional-off"}`);
