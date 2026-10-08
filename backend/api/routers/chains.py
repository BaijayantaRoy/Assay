"""
Prompt Chains Router
GET /chains
POST /chains
DELETE /chains/{id}
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List
from datetime import datetime, timezone
import uuid

from ...database import get_session
from ...models import PromptChain, ChainStep

router = APIRouter(prefix="/chains", tags=["chains"])


@router.get("/", response_model=List[dict])
def list_chains(session: Session = Depends(get_session)):
    """List all prompt chains with their steps."""
    chains = session.exec(select(PromptChain)).all()
    res = []
    for c in chains:
        steps = session.exec(select(ChainStep).where(ChainStep.chain_id == c.id)).all()
        cd = {
            "id": str(c.id),
            "project_id": str(c.project_id) if c.project_id else None,
            "name": c.name,
            "description": c.description,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "steps": [
                {
                    "id": str(s.id),
                    "chain_id": str(s.chain_id),
                    "step_order": s.step_order,
                    "prompt_version_id": str(s.prompt_version_id),
                    "model": s.model,
                    "output_variable": s.output_variable,
                    "config": s.config,
                }
                for s in steps
            ],
        }
        res.append(cd)
    return res


@router.post("/")
def create_chain(body: dict, session: Session = Depends(get_session)):
    """Create a new prompt chain."""
    name = body.get("name", "New Chain")
    description = body.get("description", "")
    project_id_str = body.get("project_id")
    project_id_val = uuid.UUID(project_id_str) if project_id_str else None
    
    chain = PromptChain(
        project_id=project_id_val,
        name=name,
        description=description,
        created_at=datetime.now(timezone.utc)
    )
    session.add(chain)
    session.commit()
    session.refresh(chain)
    
    steps_data = body.get("steps", [])
    for idx, s in enumerate(steps_data):
        pv_id = s.get("prompt_version_id")
        step = ChainStep(
            chain_id=chain.id,
            step_order=idx + 1,
            prompt_version_id=uuid.UUID(pv_id) if pv_id else uuid.uuid4(),
            model=s.get("model", "gpt-6.1-sol"),
            output_variable=s.get("output_variable", f"step_{idx+1}_output"),
            config=s.get("config", {}),
        )
        session.add(step)
        
    session.commit()
    
    cd = {
        "id": str(chain.id),
        "project_id": str(chain.project_id) if chain.project_id else None,
        "name": chain.name,
        "description": chain.description,
        "created_at": chain.created_at.isoformat() if chain.created_at else None,
        "steps": []
    }
    return cd


@router.delete("/{chain_id}")
def delete_chain(chain_id: str, session: Session = Depends(get_session)):
    """Delete a prompt chain."""
    chain = session.get(PromptChain, chain_id)
    if not chain:
        raise HTTPException(status_code=404, detail="Chain not found")
        
    # Steps are cascade-deleted by DB or we can manually delete
    steps = session.exec(select(ChainStep).where(ChainStep.chain_id == chain_id)).all()
    for s in steps:
        session.delete(s)
        
    session.delete(chain)
    session.commit()
    return {"status": "success"}
