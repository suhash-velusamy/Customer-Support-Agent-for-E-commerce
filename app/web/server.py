"""Minimal web UI backend. Run: python -m app.web.server  (then open http://127.0.0.1:8000)

The API returns only customer-safe data: the reply, human-readable activity events, and
the handoff summary. Raw tool payloads and internal state are never sent to the browser.
"""

import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.graph.graph import SupportAgent
from app.graph.nodes.handoff import render_summary

STATIC = Path(__file__).with_name("static")
MAX_MESSAGE_CHARS = 2000


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    session_id: str | None = Field(default=None, max_length=64)


def create_app(agent: SupportAgent | None = None) -> FastAPI:
    app = FastAPI(title="Customer Support Agent", docs_url=None, redoc_url=None)
    state = {"agent": agent, "seen": {}}

    def get_agent() -> SupportAgent:
        if state["agent"] is None:
            state["agent"] = SupportAgent()
        return state["agent"]

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/api/session")
    async def session() -> dict:
        support = get_agent()
        return {
            "session_id": uuid.uuid4().hex,
            "customer_id": support.customer_id,
            "triage_mode": "LLM + rules" if support.deps.llm else "rules",
            "web_search": support.deps.web.available,
        }

    @app.post("/api/chat")
    async def chat(req: ChatRequest) -> dict:
        message = req.message.strip()
        if not message:
            raise HTTPException(422, "Message is empty.")
        support = get_agent()
        session_id = req.session_id or uuid.uuid4().hex
        result = await support.achat(message, thread_id=session_id)

        actions = result.get("actions_taken", [])
        seen = state["seen"].get(session_id, 0)
        state["seen"][session_id] = len(actions)

        order = result.get("order_data") or {}
        summary = result.get("handoff_summary")
        escalated_now = "Escalated to human support" in actions[seen:]
        return {
            "session_id": session_id,
            "reply": result.get("final_response") or "",
            "activity": actions[seen:],
            "intent": result.get("intent"),
            "handed_off": bool(result.get("handed_off")),
            "escalated_now": escalated_now,
            "context": {
                "customer_id": support.customer_id,
                "order_id": result.get("order_id"),
                "order_status": order.get("status"),
            },
            "handoff": {
                "case_id": result.get("case_id"),
                "summary": summary,
                "text": render_summary(summary),
            } if summary and escalated_now else None,
        }

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    from app.logging_setup import configure_logging

    configure_logging()
    uvicorn.run("app.web.server:app", host="127.0.0.1", port=8000)
