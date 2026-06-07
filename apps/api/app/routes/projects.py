"""Project CRUD endpoints. RLS enforced via JWT-validated user_id."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services import projects as svc
from app.services.auth import CurrentUser

router = APIRouter()


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    icon: str | None = None
    entry_type: str = "fresh_idea"


class ProjectOut(BaseModel):
    id: str
    user_id: str
    name: str
    icon: str | None = None
    entry_type: str
    created_at: str
    updated_at: str | None = None
    project_brief: str | None = None
    north_star: str | None = None


@router.get("", response_model=list[ProjectOut])
async def list_projects(user_id: CurrentUser) -> list[dict]:
    return svc.list_for_user(user_id)


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(payload: ProjectIn, user_id: CurrentUser) -> dict:
    return svc.create(user_id, payload.name, payload.icon, payload.entry_type)


@router.get("/{project_id}")
async def get_project(project_id: str, user_id: CurrentUser) -> dict:
    """Return the full project (including project_brief + north_star).

    Wrapped in `{ project: ... }` so the MCP server gets a consistent shape.
    """
    project = svc.get(user_id, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"project": project}


@router.delete("/{project_id}")
async def delete_project(project_id: str, user_id: CurrentUser) -> dict[str, str]:
    if not svc.delete(user_id, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return {"status": "deleted"}
