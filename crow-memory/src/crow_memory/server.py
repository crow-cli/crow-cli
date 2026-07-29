"""FastAPI memory service. Loads both embedders once at startup (~5GB resident)
and serves the LanceDB store over HTTP. Run: `crow-memory` (or uvicorn)."""

import base64
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import JSONResponse

from .embed import Embedders
from .logger import logger
from .schemas import (
    AddMessageRequest,
    AddMessageResponse,
    AgentResponse,
    BatchMessagesRequest,
    CreateAgentRequest,
    LoadResponse,
    LookupPromptRequest,
    MessageQueryRequest,
    MessageRecord,
    PromptResponse,
    SearchRequest,
    SearchResponse,
    SessionSummary,
)
from .store import MemoryStore

DEFAULT_PATH = str(Path.home() / ".crow" / "memory.lance")


def build_app(store_path: str | None = None, image_max_dim: int = 1024) -> FastAPI:
    path = store_path or os.environ.get("CROW_MEMORY_PATH", DEFAULT_PATH)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("crow-memory starting: loading embedders (ColBERT + ColQwen2)...")
        embedders = Embedders(image_max_dim=image_max_dim)
        app.state.store = MemoryStore(path, embedders)
        logger.info(f"crow-memory ready: store={path}")
        yield
        logger.info("crow-memory shutting down")

    app = FastAPI(title="crow-memory", version="0.1.27", lifespan=lifespan)

    def store() -> MemoryStore:
        return app.state.store

    @app.get("/health")
    def health():
        return {"status": "ok", "path": path}

    # ---- agents ----
    @app.post("/agents", response_model=AgentResponse)
    def create_agent(req: CreateAgentRequest):
        s = store()
        agent = s.add_agent(req.model_dump(exclude={"initial_messages"}))
        for m in req.initial_messages:
            if m.get("role") != "system":
                s.add_message(req.agent_id, m)
        return agent

    @app.get("/agents", response_model=list[AgentResponse])
    def list_agents(session_id: str | None = None):
        return store().list_agents(session_id=session_id)

    @app.get("/agents/{agent_id}", response_model=LoadResponse)
    def load_agent(agent_id: str, hydrate: bool = False):
        s = store()
        agent = s.get_agent(agent_id)
        if agent is None:
            raise HTTPException(404, f"agent '{agent_id}' not found")
        messages = s.load_messages(agent_id, hydrate_images=hydrate)
        return {"agent": agent, "messages": messages}

    # ---- messages ----
    @app.post("/agents/{agent_id}/messages", response_model=AddMessageResponse)
    def add_message(agent_id: str, req: AddMessageRequest):
        rec = store().add_message(agent_id, req.message, req.usage)
        return {"id": rec["id"], "agent_id": rec["agent_id"],
                "role": rec["role"], "image_ids": rec.get("image_ids", [])}

    @app.post("/agents/{agent_id}/messages/batch")
    def add_messages_batch(agent_id: str, req: BatchMessagesRequest):
        s = store()
        ids = [s.add_message(agent_id, m)["id"] for m in req.messages]
        return {"agent_id": agent_id, "ids": ids, "count": len(ids)}

    @app.post("/messages/query", response_model=list[MessageRecord])
    def query_messages(req: MessageQueryRequest):
        return store().query_messages(**req.model_dump())

    # ---- sessions ----
    @app.get("/sessions", response_model=list[SessionSummary])
    def list_sessions(limit: int = 50, offset: int = 0):
        return store().list_sessions(limit=limit, offset=offset)

    @app.get("/sessions/{session_id}/max-idx")
    def max_idx(session_id: str):
        return {"session_id": session_id, "max_agent_idx": store().get_max_agent_idx(session_id)}

    # ---- prompts ----
    @app.post("/prompts", response_model=PromptResponse)
    def lookup_or_create_prompt(req: LookupPromptRequest):
        return store().lookup_or_create_prompt(req.template, req.name)

    @app.get("/prompts/{prompt_id}", response_model=PromptResponse)
    def get_prompt(prompt_id: str):
        p = store().get_prompt(prompt_id)
        if p is None:
            raise HTTPException(404, f"prompt '{prompt_id}' not found")
        return p

    # ---- images ----
    @app.get("/images/{image_id}")
    def get_image(image_id: str):
        img = store().get_image(image_id)
        if img is None:
            raise HTTPException(404, f"image '{image_id}' not found")
        return Response(content=img["data"], media_type=img["mime"],
                        headers={"X-Image-Id": img["image_id"],
                                 "X-Image-W": str(img["w"]), "X-Image-H": str(img["h"])})

    # ---- search ----
    @app.post("/search", response_model=SearchResponse)
    def search(req: SearchRequest):
        s = store()
        out = {"messages": [], "images": []}
        if req.modality in ("text", "both") and req.query:
            out["messages"] = s.search_messages(req.query, req.filters, req.limit)
        if req.modality in ("image", "both"):
            qimg = base64.b64decode(req.query_image_b64) if req.query_image_b64 else None
            out["images"] = s.search_images(query=req.query, query_image=qimg, limit=req.limit)
        return out

    return app


app = build_app()


def main():
    import uvicorn

    uvicorn.run(
        "crow_memory.server:app",
        host=os.environ.get("CROW_MEMORY_HOST", "0.0.0.0"),
        port=int(os.environ.get("CROW_MEMORY_PORT", "8901")),
    )


if __name__ == "__main__":
    main()
