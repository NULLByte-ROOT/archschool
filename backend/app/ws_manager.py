from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    """Keeps track of socket connections grouped by room.

    Rooms:
      - ``global``              → the class group chat
      - ``dm:<small>:<large>``  → a private conversation
      - ``assignment:<id>``     → comments for one assignment
      - ``pulse``               → notifications-only channel (unread counts).

    Every socket is additionally registered under the id of its user so
    unread-ping events can reach users who are not currently inside the room
    the message was written in.
    """

    def __init__(self) -> None:
        self._rooms: dict[str, set[WebSocket]] = defaultdict(set)
        # socket of the owning user — used to deliver pulse notifications
        self._users: dict[int, set[WebSocket]] = defaultdict(set)

    async def connect(
        self,
        websocket: WebSocket,
        room: str,
        *,
        accept: bool = True,
        user_id: int | None = None,
    ) -> None:
        # `accept=False` is used when the caller already completed the
        # handshake (e.g. to reject an invalid token with a real close code
        # instead of a bare 403 handshake failure).
        if accept:
            await websocket.accept()
        self._rooms[room].add(websocket)
        if user_id is not None:
            self._users[user_id].add(websocket)

    def disconnect(self, websocket: WebSocket, room: str) -> None:
        room_sockets = self._rooms.get(room)
        if room_sockets:
            room_sockets.discard(websocket)
            if not room_sockets:
                self._rooms.pop(room, None)
        self._discard_user_socket(websocket)

    def _discard_user_socket(self, websocket: WebSocket) -> None:
        empty_users: list[int] = []
        for user_id, sockets in self._users.items():
            sockets.discard(websocket)
            if not sockets:
                empty_users.append(user_id)
        for user_id in empty_users:
            self._users.pop(user_id, None)

    async def broadcast(self, room: str, payload: dict) -> None:
        dead: list[WebSocket] = []
        for websocket in list(self._rooms.get(room, ())):
            try:
                await websocket.send_json(payload)
            except Exception:
                dead.append(websocket)
        for websocket in dead:
            self._discard_user_socket(websocket)
            self.disconnect(websocket, room)

    async def broadcast_message(self, room: str, message: dict) -> None:
        await self.broadcast(room, {"type": "message", "data": message})

    def all_user_ids(self, *, exclude: int | None = None) -> list[int]:
        return [user_id for user_id in self._users if user_id != exclude]

    async def notify_users(self, user_ids, payload: dict) -> None:
        dead: list[WebSocket] = []
        for user_id in user_ids:
            for websocket in list(self._users.get(user_id, ())):
                try:
                    await websocket.send_json(payload)
                except Exception:
                    dead.append(websocket)
        for websocket in dead:
            self._discard_user_socket(websocket)

    async def notify_message_pulses(self, payload: dict) -> None:
        """Unread ping fan-out for one freshly created message.

        Payload is the exact ``MessageOut`` JSON the room already received.
        For a private conversation only the two participants learn about it —
        a DM must never leak to the whole class. For global/assignment rooms
        every connected user is a potential reader.
        """
        sender_id = payload.get("sender_id")
        receiver_id = payload.get("receiver_id")
        if receiver_id is not None:
            recipients = {sender_id, receiver_id} - {sender_id}
        else:
            recipients = set(self.all_user_ids(exclude=sender_id))
        if not recipients:
            return
        await self.notify_users(
            recipients, {"type": "pulse_ping", "data": payload}
        )

    async def send_error(self, websocket: WebSocket, detail: str) -> None:
        try:
            await websocket.send_json({"type": "error", "detail": detail})
        except Exception:
            pass

    def room_size(self, room: str) -> int:
        return len(self._rooms.get(room, ()))


manager = ConnectionManager()
