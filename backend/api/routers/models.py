"""
Models Router — Manually Manage LLM Providers and Models
GET /models
POST /models
PUT /models/{id}
DELETE /models/{id}
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List
from datetime import datetime, timezone

from ...database import get_session
from ...models import LLMModel

router = APIRouter(prefix="/models", tags=["models"])

@router.get("/", response_model=List[dict])
def list_models(session: Session = Depends(get_session)):
    """List all active LLM models from the database."""
    models = session.exec(select(LLMModel).where(LLMModel.is_active == True)).all()
    # Format exactly as frontend expects
    return [{"id": m.id, "name": m.name, "provider": m.provider, "context": m.context_window} for m in models]

@router.post("/")
def create_model(model_data: dict, session: Session = Depends(get_session)):
    """Manually add a new LLM model/provider."""
    existing = session.get(LLMModel, model_data.get("id"))
    if existing:
        raise HTTPException(status_code=400, detail="Model ID already exists")
    
    new_model = LLMModel(
        id=model_data.get("id"),
        name=model_data.get("name"),
        provider=model_data.get("provider", "custom"),
        context_window=model_data.get("context_window", "128k"),
        input_cost_per_m=model_data.get("input_cost_per_m", 0.0),
        output_cost_per_m=model_data.get("output_cost_per_m", 0.0),
        is_active=True
    )
    session.add(new_model)
    session.commit()
    session.refresh(new_model)
    return new_model

@router.put("/{model_id}")
def update_model(model_id: str, model_data: dict, session: Session = Depends(get_session)):
    """Update pricing or details for an existing model."""
    model = session.get(LLMModel, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
        
    for k, v in model_data.items():
        if hasattr(model, k):
            setattr(model, k, v)
    model.updated_at = datetime.now(timezone.utc)
    
    session.add(model)
    session.commit()
    session.refresh(model)
    return model

@router.delete("/{model_id}")
def delete_model(model_id: str, session: Session = Depends(get_session)):
    """Deactivate a model."""
    model = session.get(LLMModel, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
        
    model.is_active = False
    session.add(model)
    session.commit()
    return {"status": "deactivated"}
