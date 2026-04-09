"""RadAI — WebSocket server for real-time AI progress streaming."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.auth import validate_websocket_token

logger = structlog.get_logger(__name__)

router = APIRouter()


class ConnectionManager:
    """Manages active WebSocket connections, keyed by study ID."""

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, study_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.setdefault(study_id, []).append(ws)
        logger.info("WebSocket connected", study_id=study_id)

    def disconnect(self, study_id: str, ws: WebSocket) -> None:
        conns = self._connections.get(study_id, [])
        if ws in conns:
            conns.remove(ws)
        if not conns:
            self._connections.pop(study_id, None)
        logger.info("WebSocket disconnected", study_id=study_id)

    async def send_progress(
        self, study_id: str, *, job_type: str, pct: int, message: str = ""
    ) -> None:
        payload: dict[str, Any] = {
            "type": "progress",
            "study_id": study_id,
            "job_type": job_type,
            "pct": pct,
            "message": message,
        }
        await self._broadcast(study_id, payload)

    async def send_complete(
        self, study_id: str, *, job_type: str, result_summary: str = ""
    ) -> None:
        payload: dict[str, Any] = {
            "type": "complete",
            "study_id": study_id,
            "job_type": job_type,
            "result_summary": result_summary,
        }
        await self._broadcast(study_id, payload)

    async def send_error(self, study_id: str, *, job_type: str, error: str) -> None:
        payload: dict[str, Any] = {
            "type": "error",
            "study_id": study_id,
            "job_type": job_type,
            "error": error,
        }
        await self._broadcast(study_id, payload)

    async def _broadcast(self, study_id: str, payload: dict) -> None:
        dead: list[WebSocket] = []
        for ws in self._connections.get(study_id, []):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(study_id, ws)


manager = ConnectionManager()


@router.websocket("/studies/{study_id}")
async def study_progress(websocket: WebSocket, study_id: str, token: str) -> None:
    """WebSocket endpoint — client subscribes to AI progress for a study.

    Requires a valid JWT token passed as query parameter:
    ws://host/ws/studies/{id}?token=<jwt>

    Uses 120s timeout with heartbeat pings to keep connections alive
    during long-running AI operations (TotalSegmentator: 60-300s).
    """
    try:
        validate_websocket_token(token)
    except Exception:
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token"
        )
        return

    await manager.connect(study_id, websocket)
    try:
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=120)
            except asyncio.TimeoutError:
                # Send heartbeat ping to keep connection alive during AI runs
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(study_id, websocket)
