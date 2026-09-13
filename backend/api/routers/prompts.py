from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List
from uuid import UUID
import re

from ...database import get_session
from ...models import Prompt, PromptVersion
from ...schemas import PromptRead, PromptCreate, PromptUpdate, PromptVersionRead, PromptVersionCreate
from ...services.vector_db import add_prompt_embedding, search_prompts

router = APIRouter(prefix="/prompts", tags=["prompts"])

def extract_variables(content: str) -> List[str]:
    """Auto-extract {{ variable }} from prompt content."""
    # Simple regex for handlebars/jinja style variables
    return list(set(re.findall(r"\{\{\s*(\w+)\s*\}\}", content)))

@router.post("/", response_model=PromptRead)
def create_prompt(prompt: PromptCreate, session: Session = Depends(get_session)):
    db_prompt = Prompt.model_validate(prompt)
    session.add(db_prompt)
    session.commit()
    session.refresh(db_prompt)
    
    # Add to vector DB
    try:
        add_prompt_embedding(db_prompt.id, db_prompt.name + " " + (db_prompt.description or ""), {"project_id": str(db_prompt.project_id)})
    except Exception as e:
        print(f"Vector DB Error: {e}")

    return db_prompt

@router.get("/", response_model=List[PromptRead])
def read_prompts(project_id: UUID, session: Session = Depends(get_session)):
    # Filter by project_id
    prompts = session.exec(select(Prompt).where(Prompt.project_id == project_id)).all()
    return prompts

@router.get("/all", response_model=List[PromptRead])
def read_all_prompts(session: Session = Depends(get_session)):
    """Return all prompts across all projects."""
    prompts = session.exec(select(Prompt).order_by(Prompt.created_at.desc())).all()
    return prompts

@router.get("/search/", response_model=List[PromptRead])
def search_prompts_endpoint(query: str, session: Session = Depends(get_session)):
    """Semantic search for prompts."""
    results = search_prompts(query)
    
    if not results['ids'] or len(results['ids'][0]) == 0:
        return []
        
    prompt_ids = results['ids'][0]
    prompts = session.exec(select(Prompt).where(Prompt.id.in_(prompt_ids))).all()
    return prompts

@router.get("/{prompt_id}", response_model=PromptRead)
def read_prompt(prompt_id: UUID, session: Session = Depends(get_session)):
    prompt = session.get(Prompt, prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return prompt

@router.post("/{prompt_id}/versions", response_model=PromptVersionRead)
def create_version(prompt_id: UUID, version: PromptVersionCreate, session: Session = Depends(get_session)):
    prompt = session.get(Prompt, prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    
    # Calculate next version number 
    # (naive implementation - race condition possible in high concurrency, fix with locking later)
    last_version = session.exec(select(PromptVersion).where(PromptVersion.prompt_id == prompt_id).order_by(PromptVersion.version_number.desc())).first()
    new_version_num = (last_version.version_number + 1) if last_version else 1
    
    variables = extract_variables(version.content)
    
    db_version = PromptVersion(
        prompt_id=prompt_id,
        version_number=new_version_num,
        content=version.content,
        config=version.config,
        variables=variables,
        commit_message=version.commit_message
    )
    session.add(db_version)
    session.commit()
    session.refresh(db_version)
    
    # Update latest pointer
    prompt.latest_version_id = db_version.id
    session.add(prompt)
    session.commit()
    
    return db_version

@router.get("/{prompt_id}/versions", response_model=List[PromptVersionRead])
def read_versions(prompt_id: UUID, session: Session = Depends(get_session)):
    versions = session.exec(select(PromptVersion).where(PromptVersion.prompt_id == prompt_id).order_by(PromptVersion.version_number.desc())).all()
    return versions

# Note: /search/ and /all endpoints moved above /{prompt_id} to avoid route conflicts

@router.put("/{prompt_id}", response_model=PromptRead)
def update_prompt(prompt_id: UUID, prompt_update: PromptUpdate, session: Session = Depends(get_session)):
    db_prompt = session.get(Prompt, prompt_id)
    if not db_prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    
    if prompt_update.name is not None:
        db_prompt.name = prompt_update.name
    if prompt_update.description is not None:
        db_prompt.description = prompt_update.description
    if prompt_update.tags is not None:
        db_prompt.tags = prompt_update.tags
        
    session.add(db_prompt)
    session.commit()
    session.refresh(db_prompt)
    
    # Update embedding (naively re-add, vector db setup should handle update or we delete/add)
    # Ideally we should have an update_embedding function, but add might overwrite if ID matches
    try:
        add_prompt_embedding(db_prompt.id, db_prompt.name + " " + (db_prompt.description or ""), {"project_id": str(db_prompt.project_id)})
    except Exception as e:
        print(f"Vector DB Update Error: {e}")
        
    return db_prompt

@router.delete("/{prompt_id}")
def delete_prompt(prompt_id: UUID, session: Session = Depends(get_session)):
    prompt = session.get(Prompt, prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    
    # Delete related versions first (cascade usually handles this in DB, but let's be safe if no cascade)
    versions = session.exec(select(PromptVersion).where(PromptVersion.prompt_id == prompt_id)).all()
    for v in versions:
        session.delete(v)
        
    session.delete(prompt)
    session.commit()
    return {"ok": True}

@router.post("/{prompt_id}/copy", response_model=PromptRead)
def copy_prompt(prompt_id: UUID, session: Session = Depends(get_session)):
    # 1. Get original
    original = session.get(Prompt, prompt_id)
    if not original:
        raise HTTPException(status_code=404, detail="Prompt not found")
        
    # 2. Create new prompt
    new_prompt = Prompt(
        name=f"Copy of {original.name}",
        description=original.description,
        project_id=original.project_id,
        tags=original.tags
    )
    session.add(new_prompt)
    session.commit()
    session.refresh(new_prompt)
    
    # 3. Get latest version content
    latest_version = None
    if original.latest_version_id:
        latest_version = session.get(PromptVersion, original.latest_version_id)
    
    if latest_version:
        # Create initial version for copy
        new_version = PromptVersion(
            prompt_id=new_prompt.id,
            version_number=1,
            content=latest_version.content,
            config=latest_version.config,
            variables=latest_version.variables,
            commit_message="Copied from original"
        )
        session.add(new_version)
        session.commit()
        session.refresh(new_version)
        
        # Link back
        new_prompt.latest_version_id = new_version.id
        session.add(new_prompt)
        session.commit()
    
    # 4. Add to vector db
    try:
        add_prompt_embedding(new_prompt.id, new_prompt.name + " " + (new_prompt.description or ""), {"project_id": str(new_prompt.project_id)})
    except Exception as e:
        print(f"Vector DB Copy Error: {e}")
        
    return new_prompt
