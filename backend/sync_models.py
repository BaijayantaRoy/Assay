"""
Script to periodically sync LLM models and prices from an external registry (e.g. OpenRouter).
Run via cron: `python -m backend.sync_models`
"""
import httpx
from sqlmodel import Session, select
from datetime import datetime, timezone
from .database import engine
from .models import LLMModel

def sync_from_openrouter():
    print("Fetching latest model pricing from OpenRouter API...")
    try:
        resp = httpx.get("https://openrouter.ai/api/v1/models", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        models_data = data.get("data", [])
        
        with Session(engine) as session:
            updated_count = 0
            new_count = 0
            for m in models_data:
                # OpenRouter returns pricing in USD per token. We want USD per million tokens.
                pricing = m.get("pricing", {})
                prompt_cost = float(pricing.get("prompt", 0) or 0) * 1_000_000
                completion_cost = float(pricing.get("completion", 0) or 0) * 1_000_000
                
                context_length = str(m.get("context_length", "128k"))
                provider = m.get("id", "").split("/")[0] if "/" in m.get("id", "") else "openai"
                model_id = m.get("id", "").split("/")[-1] if "/" in m.get("id", "") else m.get("id")
                
                existing = session.get(LLMModel, model_id)
                if existing:
                    existing.input_cost_per_m = prompt_cost
                    existing.output_cost_per_m = completion_cost
                    existing.updated_at = datetime.now(timezone.utc)
                    session.add(existing)
                    updated_count += 1
                else:
                    new_model = LLMModel(
                        id=model_id,
                        name=m.get("name", model_id),
                        provider=provider,
                        context_window=context_length,
                        input_cost_per_m=prompt_cost,
                        output_cost_per_m=completion_cost,
                        is_active=True
                    )
                    session.add(new_model)
                    new_count += 1
            session.commit()
            print(f"Sync complete. Added {new_count} new models. Updated {updated_count} existing models.")
    except Exception as e:
        print(f"Failed to sync models: {e}")

if __name__ == "__main__":
    sync_from_openrouter()
