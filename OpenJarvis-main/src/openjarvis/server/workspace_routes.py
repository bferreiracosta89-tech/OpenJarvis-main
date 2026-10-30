"""Authenticated workspace endpoints used by the JARVIS screens."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from openjarvis.server.workspace_store import WorkspaceStore

router = APIRouter(prefix="/api/workspace", tags=["workspace"])


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    color: str = Field(default="blue", max_length=32)


class ConversationCreate(BaseModel):
    title: str = Field(default="Nova conversa", max_length=200)
    model: str = Field(default="", max_length=200)
    project_id: str | None = None


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    model: str | None = Field(default=None, max_length=200)
    project_id: str | None = None
    pinned: bool | None = None


class MessageCreate(BaseModel):
    role: str = "user"
    content: str = Field(min_length=1, max_length=200_000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10_000)
    project_id: str | None = None
    conversation_id: str | None = None
    priority: str = Field(default="normal", max_length=32)
    due_at: float | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    status: str | None = Field(default=None, max_length=32)
    priority: str | None = Field(default=None, max_length=32)
    project_id: str | None = None
    conversation_id: str | None = None
    due_at: float | None = None


class ConclaveCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    objective: str = Field(default="", max_length=10_000)
    agent_ids: list[str] = Field(default_factory=list, max_length=32)


class SettingsUpdate(BaseModel):
    values: dict[str, Any]


def _store(request: Request) -> WorkspaceStore:
    return request.app.state.workspace_store


def _user_id(request: Request) -> str:
    principal = getattr(request.state, "auth", None)
    user_id = getattr(principal, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Autenticação necessária")
    return user_id


@router.get("/projects")
async def projects(request: Request) -> dict[str, Any]:
    return {"projects": _store(request).list_projects(_user_id(request))}


@router.post("/projects")
async def create_project(body: ProjectCreate, request: Request) -> dict[str, Any]:
    return _store(request).create_project(_user_id(request), body.name, body.description, body.color)


@router.delete("/projects/{project_id}")
async def archive_project(project_id: str, request: Request) -> dict[str, Any]:
    if not _store(request).archive_project(_user_id(request), project_id):
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    return {"status": "archived", "id": project_id}


@router.get("/conversations")
async def conversations(request: Request, project_id: str | None = None) -> dict[str, Any]:
    return {"conversations": _store(request).list_conversations(_user_id(request), project_id)}


@router.post("/conversations")
async def create_conversation(body: ConversationCreate, request: Request) -> dict[str, Any]:
    try:
        return _store(request).create_conversation(_user_id(request), body.title, body.model, body.project_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, request: Request) -> dict[str, Any]:
    result = _store(request).get_conversation(_user_id(request), conversation_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")
    return result


@router.patch("/conversations/{conversation_id}")
async def update_conversation(conversation_id: str, body: ConversationUpdate, request: Request) -> dict[str, Any]:
    try:
        result = _store(request).update_conversation(_user_id(request), conversation_id, **body.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")
    return result


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, request: Request) -> dict[str, Any]:
    if not _store(request).delete_conversation(_user_id(request), conversation_id):
        raise HTTPException(status_code=404, detail="Conversa não encontrada")
    return {"status": "deleted", "id": conversation_id}


@router.post("/conversations/{conversation_id}/messages")
async def append_message(conversation_id: str, body: MessageCreate, request: Request) -> dict[str, Any]:
    try:
        return _store(request).append_message(_user_id(request), conversation_id, body.role, body.content, body.metadata)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/tasks")
async def tasks(request: Request, status: str | None = None) -> dict[str, Any]:
    return {"tasks": _store(request).list_tasks(_user_id(request), status)}


@router.post("/tasks")
async def create_task(body: TaskCreate, request: Request) -> dict[str, Any]:
    try:
        return _store(request).create_task(_user_id(request), body.title, body.description, body.project_id, body.conversation_id, body.priority, body.due_at)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/tasks/{task_id}")
async def update_task(task_id: str, body: TaskUpdate, request: Request) -> dict[str, Any]:
    try:
        result = _store(request).update_task(_user_id(request), task_id, **body.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    return result


@router.get("/conclaves")
async def conclaves(request: Request) -> dict[str, Any]:
    return {"conclaves": _store(request).list_conclaves(_user_id(request))}


@router.post("/conclaves")
async def create_conclave(body: ConclaveCreate, request: Request) -> dict[str, Any]:
    return _store(request).create_conclave(_user_id(request), body.title, body.objective, body.agent_ids)


@router.get("/notifications")
async def notifications(request: Request, unread_only: bool = False) -> dict[str, Any]:
    return {"notifications": _store(request).list_notifications(_user_id(request), unread_only)}


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str, request: Request) -> dict[str, Any]:
    if not _store(request).mark_notification_read(_user_id(request), notification_id):
        raise HTTPException(status_code=404, detail="Notificação não encontrada")
    return {"status": "read", "id": notification_id}


@router.get("/settings")
async def get_settings(request: Request) -> dict[str, Any]:
    return {"settings": _store(request).get_settings(_user_id(request))}


@router.patch("/settings")
async def update_settings(body: SettingsUpdate, request: Request) -> dict[str, Any]:
    return {"settings": _store(request).update_settings(_user_id(request), body.values)}


__all__ = ["router"]
