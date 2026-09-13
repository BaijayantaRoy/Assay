from typing import List, Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel

# --- Prompt Schemas ---

class PromptBase(BaseModel):
    name: str
    description: Optional[str] = None
    tags: List[str] = []

class PromptCreate(PromptBase):
    project_id: UUID

class PromptRead(PromptBase):
    id: UUID
    created_at: datetime
    latest_version_id: Optional[UUID] = None

class PromptUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None

# --- Version Schemas ---

class PromptVersionBase(BaseModel):
    version_number: int
    content: str
    config: dict = {}
    variables: List[str] = []
    commit_message: Optional[str] = None

class PromptVersionCreate(BaseModel):
    prompt_id: UUID
    content: str
    config: dict = {}
    commit_message: Optional[str] = None
    # Variables will be auto-extracted in the backend logic

class PromptVersionRead(PromptVersionBase):
    id: UUID
    created_at: datetime
    prompt_id: UUID

# --- Project Schemas ---

class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None

class ProjectCreate(ProjectBase):
    organization_id: UUID

class ProjectRead(ProjectBase):
    id: UUID
    organization_id: UUID
