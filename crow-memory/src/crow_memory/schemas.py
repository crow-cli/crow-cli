"""Shared pydantic schemas — the API contract between server and client."""

from typing import Any, Literal

from pydantic import BaseModel, Field


# ---- agents ----
class CreateAgentRequest(BaseModel):
    agent_id: str
    session_id: str
    agent_idx: int = 1
    cwd: str = "/tmp"
    prompt_id: str | None = None
    prompt_args: dict[str, Any] = Field(default_factory=dict)
    system_prompt: str = ""
    tool_definitions: list[dict] = Field(default_factory=list)
    request_params: dict[str, Any] = Field(default_factory=dict)
    model_identifier: str = ""
    initial_messages: list[dict] = Field(default_factory=list)


class AgentResponse(BaseModel):
    agent_id: str
    session_id: str
    agent_idx: int
    cwd: str
    prompt_id: str
    prompt_args: dict[str, Any]
    system_prompt: str
    tool_definitions: list[dict]
    request_params: dict[str, Any]
    model_identifier: str
    status: str
    created_at: str = ""


class LoadResponse(BaseModel):
    agent: AgentResponse
    messages: list[dict]


# ---- messages ----
class AddMessageRequest(BaseModel):
    message: dict
    usage: dict | None = None


class BatchMessagesRequest(BaseModel):
    messages: list[dict]


class MessageQueryRequest(BaseModel):
    session_id: str | None = None
    agent_id: str | None = None
    agent_idx: int | None = None
    roles: list[str] | None = None
    after: str | None = None
    before: str | None = None
    order: Literal["asc", "desc"] = "asc"
    limit: int = 1_000_000
    offset: int = 0


class MessageRecord(BaseModel):
    id: int
    agent_id: str
    session_id: str
    agent_idx: int
    role: str
    created_at: str
    data: dict


class AddMessageResponse(BaseModel):
    id: int
    agent_id: str
    role: str
    image_ids: list[str] = Field(default_factory=list)


# ---- prompts ----
class LookupPromptRequest(BaseModel):
    template: str
    name: str = "crow-default"


class PromptResponse(BaseModel):
    id: str
    name: str
    template: str
    created: bool = False


# ---- search ----
Modality = Literal["text", "image", "both"]


class SearchRequest(BaseModel):
    query: str | None = None
    modality: Modality = "text"
    filters: dict[str, Any] | None = None
    limit: int = 10
    query_image_b64: str | None = None  # for image->image search


class MessageHit(BaseModel):
    agent_id: str
    role: str
    created_at: str
    data: dict
    score: float


class ImageHit(BaseModel):
    image_id: str
    mime: str
    w: int
    h: int
    score: float


class SearchResponse(BaseModel):
    messages: list[MessageHit] = Field(default_factory=list)
    images: list[ImageHit] = Field(default_factory=list)
