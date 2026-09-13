from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List
from uuid import UUID

from ...database import get_session
from ...models import Project
from ...schemas import ProjectRead, ProjectCreate

router = APIRouter(prefix="/projects", tags=["projects"])

@router.post("/", response_model=ProjectRead)
def create_project(project: ProjectCreate, session: Session = Depends(get_session)):
    db_project = Project.model_validate(project)
    session.add(db_project)
    session.commit()
    session.refresh(db_project)
    return db_project

@router.get("/", response_model=List[ProjectRead])
def read_projects(organization_id: UUID, session: Session = Depends(get_session)):
    projects = session.exec(select(Project).where(Project.organization_id == organization_id)).all()
    return projects

@router.get("/{project_id}", response_model=ProjectRead)
def read_project(project_id: UUID, session: Session = Depends(get_session)):
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

@router.put("/{project_id}", response_model=ProjectRead)
def update_project(project_id: UUID, project_update: ProjectCreate, session: Session = Depends(get_session)):
    # Note: reusing ProjectCreate for simplicity, or create ProjectUpdate schema
    db_project = session.get(Project, project_id)
    if not db_project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    db_project.name = project_update.name
    db_project.description = project_update.description
    
    session.add(db_project)
    session.commit()
    session.refresh(db_project)
    return db_project

@router.delete("/{project_id}")
def delete_project(project_id: UUID, session: Session = Depends(get_session)):
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Manually cascade delete prompts and their versions
    # 1. Get all prompts
    from ...models import Prompt, PromptVersion
    prompts = session.exec(select(Prompt).where(Prompt.project_id == project_id)).all()
    
    for prompt in prompts:
        # 2. Delete versions for each prompt
        versions = session.exec(select(PromptVersion).where(PromptVersion.prompt_id == prompt.id)).all()
        for v in versions:
            session.delete(v)
        
        # 3. Delete prompt
        session.delete(prompt)
        
        # TODO: Ideally we should also delete from Vector DB, but Chroma doesn't error if ID not found, so it's "safe" to leave for now 
        # or we implement delete_embedding(prompt.id) later.

    session.delete(project)
    session.commit()
    return {"ok": True}
