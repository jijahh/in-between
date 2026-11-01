from typing import Optional
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ValidationError
import json
from .connection import room_manager
from .main_game import Game


class GameAction(BaseModel):
    action: str
    amount: Optional[int] = None
    data: Optional[dict] = None


router = APIRouter(tags=["WebSocket"])


async def send_error(websocket: WebSocket, message: str):
    await websocket.send_json({"type": "ERROR", "message": message})


@router.websocket("/ws/{room_id}")
async def game_websocket_endpoint(
    websocket: WebSocket,
    room_id: str,
    name: str = Query(...),
):
    try:
        player_id, role = await room_manager.connect(room_id, name, websocket)
    except ValueError as exc:
        await websocket.close(code=1008, reason=str(exc))
        return

    room = room_manager.get_room(room_id)
    client = room.connections[player_id]
    await websocket.send_json(
        {
            "type": "WELCOME",
            "room_id": room_id,
            "player_id": player_id,
            "player_name": client.name,
            "role": role,
            "status": room.status,
        }
    )
    await room_manager.broadcast_to_room(
        room_id,
        {
            "type": "PLAYER_JOINED",
            "player_id": player_id,
            "player_name": client.name,
            "role": role,
        },
    )

    try:
        while True:
            try:
                raw_data = await websocket.receive_json()
            except json.JSONDecodeError:
                await send_error(
                    websocket, "Malformed JSON. Please send a valid JSON object"
                )
                continue
            except WebSocketDisconnect:
                break
            try:
                packet = GameAction(**raw_data)
            except (ValidationError, TypeError) as exc:
                await send_error(websocket, f"Invalid action message: {exc}")
                continue

            # Re-fetch shared room/client state on each message.
            room = room_manager.get_room(room_id)
            if room is None or player_id not in room.connections:
                await send_error(websocket, "This room is no longer available.")
                break
            client = room.connections[player_id]
            action = packet.action.strip().upper()

            if action == "START_GAME":
                if client.role != "host":
                    await send_error(websocket, "Only the host can start the game.")
                    continue
                if room.status != "waiting":
                    await send_error(websocket, "The game has already started.")
                    continue
                names = [c.name for c in room.connections.values()]
                if len(names) < 2:
                    await send_error(
                        websocket, "At least two players must join before starting."
                    )
                    continue
                try:
                    room.game = Game(names)
                except ValueError as exc:
                    await send_error(websocket, str(exc))
                    continue
                room.status = "playing"
                await room_manager.broadcast_to_room(
                    room_id,
                    {
                        "type": "GAME_STARTED",
                        "state": room.game.to_dict(),
                    },
                )
                continue

            if room.status != "playing" or room.game is None:
                await send_error(websocket, "The host must start the game first.")
                continue

            try:
                events = room.game.handle_action(client.name, action, packet.data)
            except ValueError as exc:
                await send_error(websocket, str(exc))
                continue

            for event in events:
                await room_manager.broadcast_to_room(room_id, event)

    except WebSocketDisconnect:
        pass
    finally:
        room_manager.disconnect(room_id, player_id, websocket)
        await room_manager.broadcast_to_room(
            room_id,
            {
                "type": "PLAYER_LEFT",
                "player_id": player_id,
                "player_name": client.name,
            },
        )
