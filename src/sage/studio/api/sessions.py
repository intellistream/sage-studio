"""Chat session management routes with JSON-file persistence.

Sessions survive backend restarts by being stored as a JSON file at
``~/.local/share/sage/studio/chat_sessions.json`` (XDG data directory).

The file is read once at process start and flushed synchronously after every
mutating operation.  For a single-user local tool this is simple and reliable
enough without introducing a database dependency.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sessions_file() -> Path:
    """Return the path to the persistent sessions JSON file."""
    try:
        from sage.common.config.user_paths import get_user_paths

        data_dir = get_user_paths().data_dir / "studio"
    except Exception:
        data_dir = Path.home() / ".local" / "share" / "sage" / "studio"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "chat_sessions.json"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class MessageDTO(BaseModel):
    role: str
    content: str
    timestamp: str = Field(default_factory=lambda: _now_iso())
    metadata: dict[str, Any] | None = None


class SessionSummary(BaseModel):
    id: str
    title: str
    created_at: str
    last_active: str
    message_count: int


class SessionDetail(SessionSummary):
    messages: list[MessageDTO]
    metadata: dict[str, Any] | None = None


class CreateSessionRequest(BaseModel):
    title: str | None = None


class UpdateTitleRequest(BaseModel):
    title: str


class AddMessageRequest(BaseModel):
    role: str
    content: str
    metadata: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Session record
# ---------------------------------------------------------------------------


class _SessionRecord:
    __slots__ = ("id", "title", "created_at", "last_active", "messages", "metadata")

    def __init__(self, session_id: str, title: str) -> None:
        self.id = session_id
        self.title = title
        self.created_at = _now_iso()
        self.last_active = self.created_at
        self.messages: list[dict[str, Any]] = []
        self.metadata: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at,
            "last_active": self.last_active,
            "messages": list(self.messages),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "_SessionRecord":
        rec = object.__new__(cls)
        rec.id = data["id"]
        rec.title = data.get("title", "Chat")
        rec.created_at = data.get("created_at", _now_iso())
        rec.last_active = data.get("last_active", rec.created_at)
        rec.messages = data.get("messages", [])
        rec.metadata = data.get("metadata", {})
        return rec

    # ------------------------------------------------------------------
    # DTO conversion
    # ------------------------------------------------------------------

    def to_summary(self) -> SessionSummary:
        return SessionSummary(
            id=self.id,
            title=self.title,
            created_at=self.created_at,
            last_active=self.last_active,
            message_count=len(self.messages),
        )

    def to_detail(self) -> SessionDetail:
        msgs = [MessageDTO(**m) for m in self.messages]
        return SessionDetail(
            id=self.id,
            title=self.title,
            created_at=self.created_at,
            last_active=self.last_active,
            message_count=len(msgs),
            messages=msgs,
            metadata=self.metadata or None,
        )


# ---------------------------------------------------------------------------
# Persistent store
# ---------------------------------------------------------------------------


class _SessionStore:
    """Thread-safe session store backed by a JSON file."""

    def __init__(self, store_path: Path | None = None) -> None:
        self._lock = Lock()
        self._path: Path = store_path or _sessions_file()
        # ordered list of session IDs (most-recently-active first)
        self._order: list[str] = []
        self._sessions: dict[str, _SessionRecord] = {}
        self._load()

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load sessions from the JSON file; silent if file is missing/corrupt."""
        if not self._path.exists():
            return
        try:
            with open(self._path, encoding="utf-8") as f:
                data: dict[str, Any] = json.load(f)
            self._order = data.get("order", [])
            raw_sessions: dict[str, Any] = data.get("sessions", {})
            self._sessions = {
                sid: _SessionRecord.from_dict(rec) for sid, rec in raw_sessions.items()
            }
            # Repair order: remove IDs that no longer exist
            self._order = [sid for sid in self._order if sid in self._sessions]
            # Append any sessions not referenced in order
            for sid in self._sessions:
                if sid not in self._order:
                    self._order.append(sid)
            logger.debug("Loaded %d chat sessions from %s", len(self._sessions), self._path)
        except Exception as exc:
            logger.warning("Failed to load sessions from %s: %s", self._path, exc)

    def _flush(self) -> None:
        """Write the current state to the JSON file (must be called under lock)."""
        try:
            data = {
                "order": self._order,
                "sessions": {sid: rec.to_dict() for sid, rec in self._sessions.items()},
            }
            tmp = self._path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            tmp.replace(self._path)  # atomic replace on POSIX
        except Exception as exc:
            logger.error("Failed to persist sessions to %s: %s", self._path, exc)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(self, title: str | None = None) -> _SessionRecord:
        session_id = uuid.uuid4().hex
        effective_title = title or f"Chat {datetime.now().strftime('%m-%d %H:%M')}"
        record = _SessionRecord(session_id, effective_title)
        with self._lock:
            self._sessions[session_id] = record
            self._order.insert(0, session_id)
            self._flush()
        return record

    def get(self, session_id: str) -> _SessionRecord | None:
        with self._lock:
            return self._sessions.get(session_id)

    def list_all(self) -> list[_SessionRecord]:
        with self._lock:
            return [self._sessions[sid] for sid in self._order if sid in self._sessions]

    def delete(self, session_id: str) -> bool:
        with self._lock:
            if session_id not in self._sessions:
                return False
            del self._sessions[session_id]
            try:
                self._order.remove(session_id)
            except ValueError:
                pass
            self._flush()
            return True

    def clear_messages(self, session_id: str) -> bool:
        with self._lock:
            record = self._sessions.get(session_id)
            if record is None:
                return False
            record.messages.clear()
            record.last_active = _now_iso()
            self._flush()
            return True

    def update_title(self, session_id: str, title: str) -> _SessionRecord | None:
        with self._lock:
            record = self._sessions.get(session_id)
            if record is None:
                return None
            record.title = title
            record.last_active = _now_iso()
            self._flush()
            return record

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        with self._lock:
            record = self._sessions.get(session_id)
            if record is None:
                return False
            record.messages.append(
                {
                    "role": role,
                    "content": content,
                    "timestamp": _now_iso(),
                    "metadata": metadata,
                }
            )
            record.last_active = _now_iso()
            # Push to front of order list (most-recently-active first)
            try:
                self._order.remove(session_id)
            except ValueError:
                pass
            self._order.insert(0, session_id)
            self._flush()
            return True


# Module-level singleton
_store = _SessionStore()


def get_session_store() -> _SessionStore:
    """Return the module-level singleton session store."""
    return _store


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


def build_sessions_router() -> APIRouter:
    router = APIRouter(prefix="/api/chat", tags=["sessions"])

    @router.get("/sessions", response_model=list[SessionSummary])
    async def list_sessions() -> list[SessionSummary]:
        return [r.to_summary() for r in _store.list_all()]

    @router.post("/sessions", response_model=SessionDetail, status_code=201)
    async def create_session(body: CreateSessionRequest) -> SessionDetail:
        record = _store.create(title=body.title)
        return record.to_detail()

    @router.get("/sessions/{session_id}", response_model=SessionDetail)
    async def get_session(session_id: str) -> SessionDetail:
        record = _store.get(session_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return record.to_detail()

    @router.delete("/sessions/{session_id}", status_code=204)
    async def delete_session(session_id: str) -> None:
        if not _store.delete(session_id):
            raise HTTPException(status_code=404, detail="Session not found")

    @router.post("/sessions/{session_id}/clear", status_code=200)
    async def clear_session(session_id: str) -> dict[str, str]:
        if not _store.clear_messages(session_id):
            raise HTTPException(status_code=404, detail="Session not found")
        return {"status": "ok"}

    @router.patch("/sessions/{session_id}/title", response_model=SessionSummary)
    async def update_title(session_id: str, body: UpdateTitleRequest) -> SessionSummary:
        record = _store.update_title(session_id, body.title)
        if record is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return record.to_summary()

    @router.post("/sessions/{session_id}/messages", status_code=201)
    async def add_message(session_id: str, body: AddMessageRequest) -> dict[str, str]:
        ok = _store.add_message(session_id, body.role, body.content, body.metadata)
        if not ok:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"status": "ok"}

    return router


__all__ = [
    "build_sessions_router",
    "get_session_store",
    "MessageDTO",
    "SessionSummary",
    "SessionDetail",
]
