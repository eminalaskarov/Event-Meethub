import asyncio
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.seat_realtime import server_time

router = APIRouter(tags=["realtime"])


async def _send_updates(websocket: WebSocket, queue: asyncio.Queue[str]) -> None:
    while True:
        await websocket.send_text(await queue.get())


async def _wait_for_disconnect(websocket: WebSocket) -> None:
    while True:
        await websocket.receive_text()


@router.websocket("/ws/events/{event_id}/seats")
async def event_seats_socket(websocket: WebSocket, event_id: UUID) -> None:
    pool = websocket.app.state.db_pool
    hub = websocket.app.state.realtime_hub

    await websocket.accept()

    event_status = await pool.fetchval("SELECT status FROM events WHERE id = $1", event_id)
    if event_status is None or event_status == "draft":
        await websocket.close(code=4404, reason="Event not found")
        return

    # Register before announcing readiness so updates after the snapshot aren't missed.
    queue = hub.connect(event_id)
    tasks: set[asyncio.Task[None]] = set()

    try:
        await websocket.send_json(
            {"type": "connected", "event_id": str(event_id), "server_time": server_time()}
        )
        tasks = {
            asyncio.create_task(_send_updates(websocket, queue)),
            asyncio.create_task(_wait_for_disconnect(websocket)),
        }
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        hub.disconnect(event_id, queue)