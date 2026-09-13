"""Seed the LLMModel database with the absolute latest from llm-stats.com (May 2026)."""
from backend.database import engine
from sqlmodel import Session, SQLModel
from backend.models import LLMModel

# Recreate tables just in case (safe if they already exist)
SQLModel.metadata.create_all(engine)

INITIAL_MODELS = [
    # OpenAI
    {"id": "gpt-5.5",   "name": "GPT-5.5",    "provider": "openai",    "context": "2M", "in": 10.0, "out": 30.0},
    {"id": "gpt-5.4",   "name": "GPT-5.4",    "provider": "openai",    "context": "1M", "in": 5.0, "out": 15.0},
    {"id": "gpt-5.2-pro-2025-12-11", "name": "GPT-5.2 Pro", "provider": "openai", "context": "1M", "in": 2.5, "out": 7.5},
    {"id": "gpt-5.1-thinking-2025-11-12", "name": "GPT-5.1 Thinking", "provider": "openai", "context": "512k", "in": 1.5, "out": 4.5},
    {"id": "gpt-oss-120b", "name": "GPT OSS 120B", "provider": "openai", "context": "256k", "in": 0.5, "out": 1.5},
    
    # Anthropic
    {"id": "claude-mythos-preview",  "name": "Claude Mythos Preview",   "provider": "anthropic", "context": "4M", "in": 15.0, "out": 75.0},
    {"id": "claude-opus-4-7",        "name": "Claude Opus 4.7", "provider": "anthropic", "context": "2M", "in": 10.0, "out": 30.0},
    {"id": "claude-opus-4-6",        "name": "Claude Opus 4.6", "provider": "anthropic", "context": "1M", "in": 5.0, "out": 15.0},
    
    # Google
    {"id": "gemini-3.1-pro-preview", "name": "Gemini 3.1 Pro",  "provider": "google", "context": "10M", "in": 7.0, "out": 21.0},
    {"id": "gemini-3-pro-preview",   "name": "Gemini 3.0 Pro",  "provider": "google", "context": "5M", "in": 3.5, "out": 10.5},
    {"id": "gemini-3-flash-preview", "name": "Gemini 3.0 Flash", "provider": "google", "context": "5M", "in": 0.1, "out": 0.3},
    
    # DeepSeek
    {"id": "deepseek-v4-pro-max",    "name": "DeepSeek V4 Pro Max",     "provider": "deepseek", "context": "512k", "in": 0.5, "out": 1.5},
    {"id": "deepseek-r1-0528",       "name": "DeepSeek R1 (0528)",      "provider": "deepseek", "context": "512k", "in": 0.14, "out": 0.28},
    
    # xAI
    {"id": "grok-4.20-beta-0309-non-reasoning", "name": "Grok 4.20 Beta", "provider": "xai", "context": "2M", "in": 2.0, "out": 6.0},
    {"id": "grok-4-heavy",           "name": "Grok 4 Heavy", "provider": "xai", "context": "1M", "in": 5.0, "out": 15.0},
    
    # Moonshot / Other
    {"id": "kimi-k2.6",      "name": "Kimi K2.6",       "provider": "moonshot",    "context": "1M", "in": 0.95, "out": 0.95},
    {"id": "mercury-2",      "name": "Mercury 2",       "provider": "mercury",     "context": "128k", "in": 0.1, "out": 0.1},
    {"id": "qwen3.6-plus",   "name": "Qwen 3.6 Plus",   "provider": "alibaba",  "context": "2M",   "in": 0.50, "out": 1.50},
    {"id": "glm-4.6",        "name": "GLM 4.6",         "provider": "zhipu",    "context": "1M", "in": 0.5, "out": 1.5},
    {"id": "seed-2.0-pro",   "name": "Seed 2.0 Pro",    "provider": "seed",     "context": "256k", "in": 1.0, "out": 3.0},
    {"id": "muse-spark",     "name": "Muse Spark",      "provider": "muse",     "context": "128k", "in": 0.1, "out": 0.3},
]

def seed_models():
    with Session(engine) as session:
        # Optional: Deactivate old models to clean up the UI
        # We'll just append these new ones and ensure they are active
        for m in INITIAL_MODELS:
            existing = session.get(LLMModel, m["id"])
            if not existing:
                new_model = LLMModel(
                    id=m["id"],
                    name=m["name"],
                    provider=m["provider"],
                    context_window=m["context"],
                    input_cost_per_m=m["in"],
                    output_cost_per_m=m["out"],
                    is_active=True
                )
                session.add(new_model)
            else:
                existing.is_active = True
                existing.input_cost_per_m = m["in"]
                existing.output_cost_per_m = m["out"]
                existing.name = m["name"]
                existing.provider = m["provider"]
                existing.context_window = m["context"]
                session.add(existing)
                
        session.commit()
        print("Seeded database with the absolute latest llm-stats.com models.")

if __name__ == "__main__":
    seed_models()
