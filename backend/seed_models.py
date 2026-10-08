"""Seed the LLMModel table for the legacy 0.x workbench routes.

Only providers the legacy runner in ``backend/services/llm_service.py`` can actually call
are listed. Prices are USD per million tokens (standard tier, short-context rates), checked
against each provider's pricing and model pages on 2026-10-08. They drift; the ``/v1``
surface reads ``assay_core.catalog`` and ``assay models sync`` instead of this table.
"""
from backend.database import engine
from sqlmodel import Session, SQLModel
from backend.models import LLMModel

# Recreate tables just in case (safe if they already exist)
SQLModel.metadata.create_all(engine)

INITIAL_MODELS = [
    # OpenAI
    {"id": "gpt-6-astra", "name": "GPT-6 Astra", "provider": "openai", "context": "1.05M", "in": 10.0, "out": 50.0},
    {"id": "gpt-6.1-sol", "name": "GPT-6.1 Sol", "provider": "openai", "context": "1.05M", "in": 2.0,  "out": 10.0},
    {"id": "gpt-6-luna",  "name": "GPT-6 Luna",  "provider": "openai", "context": "1.05M", "in": 0.10, "out": 0.50},

    # Anthropic
    {"id": "claude-opus-5-5",   "name": "Claude Opus 5.5",   "provider": "anthropic", "context": "1M", "in": 4.0,  "out": 20.0},
    {"id": "claude-sonnet-5-5", "name": "Claude Sonnet 5.5", "provider": "anthropic", "context": "1M", "in": 2.0,  "out": 10.0},
    {"id": "claude-haiku-5-5",  "name": "Claude Haiku 5.5",  "provider": "anthropic", "context": "1M", "in": 0.10, "out": 0.50},

    # Google
    {"id": "gemini-3.1-pro-preview", "name": "Gemini 3.1 Pro (preview)", "provider": "google", "context": "1M", "in": 2.0,  "out": 12.0},
    {"id": "gemini-3.8-flash",       "name": "Gemini 3.8 Flash",         "provider": "google", "context": "1M", "in": 0.75, "out": 3.75},
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
        print(f"Seeded {len(INITIAL_MODELS)} models.")

if __name__ == "__main__":
    seed_models()
