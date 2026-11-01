import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from fastapi import WebSocket


@dataclass
class ConnectedPlayer:
    player_id: str
    name: str
    role: str
    websocket: Optional[WebSocket] = None


@dataclass
class RoomSession:
    room_id: str
    status: str = "waiting"
    connections: Dict[str, ConnectedPlayer] = field(default_factory=dict)
    host_player_id: Optional[str] = None
    game: Any = None


class RoomManager:
    def __init__(self):
        self.rooms: Dict[str, RoomSession] = {}

    def create_room(self, room_id: str) -> RoomSession:
        if room_id in self.rooms:
            raise ValueError("Room code already exists.")
        room = RoomSession(room_id=room_id)
        self.rooms[room_id] = room
        return room

    def get_room(self, room_id: str) -> Optional[RoomSession]:
        return self.rooms.get(room_id)

    async def connect(self, room_id: str, name: str, websocket: WebSocket):
        room = self.get_room(room_id)
        if not room:
            print(f"[CONNECT] Room not found: {room_id}")
            raise ValueError("Room does not exist.")

        name = name.strip()
        if not name:
            raise ValueError("A player name is required.")

        # Allow a disconnected player to reconnect to an in-progress game by name.
        if room.status == "playing":
            for client in room.connections.values():
                if client.name.casefold() == name.casefold():
                    print(
                        f"[CONNECT] Existing player: {client.name}, "
                        f"websocket is None: {client.websocket is None}"
                    )
                    if client.websocket is not None:
                        raise ValueError("That player name is already connected.")
                    await websocket.accept()
                    client.websocket = websocket
                    return client.player_id, client.role
            raise ValueError("The game has already started; new players cannot join.")

        if any(c.name.casefold() == name.casefold() for c in room.connections.values()):
            raise ValueError("That player name is already in this room.")
        if len(room.connections) >= 8:
            raise ValueError("This room is full.")

        player_id = uuid.uuid4().hex[:12]
        role = "host" if room.host_player_id is None else "client"
        await websocket.accept()
        room.connections[player_id] = ConnectedPlayer(
            player_id=player_id, name=name, role=role, websocket=websocket
        )
        if role == "host":
            room.host_player_id = player_id
        return player_id, role

    def disconnect(self, room_id: str, player_id: str, websocket):
        room = self.get_room(room_id)
        if not room:
            print(f"[DISCONNECT] Room not found: {room_id}")
            return
        client = room.connections.get(player_id)
        if not client:
            print(f"[DISCONNECT] Player not found: {player_id}")
            return

        print(f"[DISCONNECT] Player: {client.name}")
        print(f"[DISCONNECT] Room status: {room.status}")
        print(f"[DISCONNECT] Same websocket: {client.websocket is websocket}")
        print(f"[DISCONNECT] Websocket reference: {client.websocket}")

        if client.websocket is not websocket:
            print("[DISCONNECT] Skipping cleanup: websocket mismatch")
            return

        if room.status == "playing":
            # Keep the player in the game so they can reconnect by the same name.
            client.websocket = None
            print("[DISCONNECT] Player retained; websocket cleared")

        else:
            room.connections.pop(player_id, None)
            print("[DISCONNECT] Player removed")
        if room.host_player_id == player_id:
            room.host_player_id = None
            for remaining in room.connections.values():
                remaining.role = "host"
                room.host_player_id = remaining.player_id
                break

    async def broadcast_to_room(self, room_id: str, payload: dict):
        room = self.get_room(room_id)
        if room is None:
            return

        connected = [c for c in room.connections.values() if c.websocket is not None]
        results = await asyncio.gather(
            *(client.websocket.send_json(payload) for client in connected),
            return_exceptions=True,
        )
        for client, result in zip(connected, results):
            if isinstance(result, BaseException):
                self.disconnect(room_id, client.player_id)


room_manager = RoomManager()
