from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    """Keeps track of socket connections grouped by room.

    Rooms:
      - ``global``              → the class group chat
      - ``dm:<small>:<large>``  → a private conversation
      - ``assignment:<id>``     → comments for one assignment
    """

    def __init__(self) -> None:
        self._rooms: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(
        self, websocket: WebSocket, room: str, *, accept: bool = True
    ) -> None:
        # `accept=False` is used when the caller already completed the
        # handshake (e.g. to reject an invalid token with a real close code
        # instead of a bare 403 handshake failure).
        if accept:
            await websocket.accept()
        self._rooms[room].add(websocket)

    def disconnect(self, websocket: WebSocket, room: str) -> None:
        room_sockets = self._rooms.get(room)
        if not room_sockets:
            return
        room_sockets.discard(websocket)
        if not room_sockets:
            self._rooms.pop(room, None)

    async def broadcast(self, room: str, payload: dict) -> None:
        dead: list[WebSocket] = []
        for websocket in list(self._rooms.get(room, ())):
            try:
                await websocket.send_json(payload)
            except Exception:
                dead.append(websocket)
        for websocket in dead:
            self.disconnect(websocket, room)

    async def broadcast_message(self, room: str, message: dict) -> None:
        await self.broadcast(room, {"type": "message", "data": message})

    async def send_error(self, websocket: WebSocket, detail: str) -> None:
        try:
            await websocket.send_json({"type": "error", "detail": detail})
        except Exception:
            pass

    def room_size(self, room: str) -> int:
        return len(self._rooms.get(room, ()))


manager = ConnectionManager()
