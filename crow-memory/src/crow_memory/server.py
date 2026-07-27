"""FastAPI memory service. Loads both embedders once at startup (~5GB resident)
and serves the LanceDB store over HTTP. Run: `crow-memory` (or uvicorn)."""

import base64
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import JSONResponse

from .embed import Embedders
from .schemas import (
    AddMessageRequest,
    AddMessageResponse,
    AgentResponse,
    BatchMessagesRequest,
    CreateAgentRequest,
    LoadResponse,
    PromptResponse,
    SearchRequest,
    SearchResponse,
    UpsertPromptRequest,
)
from .store import MemoryStore

DEFAULT_PATH = str(Path.home() / ".crow" / "memory.lance")


def build_app(store_path: str | None = None, image_max_dim: int = 1024) -> FastAPI:
    path = store_path or os.environ.get("CROW_MEMORY_PATH", DEFAULT_PATH)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        embedders = Embedders(image_max_dim=image_max_dim)
        app.state.store = MemoryStore(path, embedders)
        yield

    app = FastAPI(title="crow-memory", version="0.1.26", lifespan=lifespan)

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

    # ---- sessions ----
    @app.get("/sessions/{session_id}/max-idx")
    def max_idx(session_id: str):
        return {"session_id": session_id, "max_agent_idx": store().get_max_agent_idx(session_id)}

    # ---- prompts ----
    @app.post("/prompts", response_model=PromptResponse)
    def upsert_prompt(req: UpsertPromptRequest):
        return store().upsert_prompt(req.id, req.name, req.template)

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
