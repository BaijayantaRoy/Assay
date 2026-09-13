from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from typing import List
from uuid import UUID

from ...database import get_session
from ...models import Organization

router = APIRouter(prefix="/organizations", tags=["organizations"])

@router.get("/", response_model=List[Organization])
def read_organizations(session: Session = Depends(get_session)):
    return session.exec(select(Organization)).all()
