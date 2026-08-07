import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers.conversation import router as conversation_router
from .routers.pages import router as pages_router


# uvicorn's logging.dictConfig sets disable_existing_loggers=True, which
# silences all application loggers. Attach a dedicated handler directly
# to our loggers so they are independent of uvicorn's logging config.
_app_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s")
_app_handler = logging.StreamHandler(sys.stderr)
_app_handler.setFormatter(_app_fmt)
_app_handler.setLevel(logging.DEBUG)

_app_loggers = (
    "app.services.memory_service",
    "app.services.conversation_store",
    "app.services.llm_client",
    "app.services.page_generator",
    "app.routers.conversation",
    "app.routers.pages",
    "app.agent.runner",
    "app.agent.nodes.input_guard",
    "app.agent.nodes.plan",
    "app.agent.nodes.execute",
    "app.agent.nodes.reflect",
    "app.agent.nodes.answer",
)
for _name in _app_loggers:
    _lg = logging.getLogger(_name)
    _lg.setLevel(logging.DEBUG)
    _lg.propagate = False
    _lg.addHandler(_app_handler)


app = FastAPI(title="Page Generator Agent", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pages_router)
app.include_router(conversation_router)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
