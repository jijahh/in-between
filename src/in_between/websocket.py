import asyncio
import json
import logging

from contextlib import suppress
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ValidationError

from .connection import room_manager, ConnectionReplacedError

from .main_game import Game

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket"])


class GameAction(BaseModel):
    action: str
    amount: Optional[int] = None
    data: Optional[dict] = None


async def send_error(websocket: WebSocket, message: str):
    await websocket.send_json({"type": "ERROR", "message": message})


async def relay_room_events(
    websocket: WebSocket, pubsub, player_id: str, connection_id: str, last_version: int
):

    async for message in pubsub.listen():

        if message["type"] != "message":
            continue

        envelope = json.loads(message["data"])

        version = envelope.get("version", 0)

        # Ignore events that are already reflected
        # in the snapshot sent during connection.
        if version <= last_version:
            continue

        last_version = version

        for event in envelope.get("events", []):

            # Internal event used to terminate old connections.
            if event.get("type") == "_CONNECTION_REPLACED":

                if (
                    event.get("player_id") == player_id
                    and event.get("connection_id") != connection_id
                ):
                    await websocket.close(
                        code=4001, reason="This connection has been replaced."
                    )

                    return

                continue

            # Forward normal events to the client.
            try:
                await websocket.send_json(event)

            except WebSocketDisconnect, RuntimeError:
                return


@router.websocket("/ws/{room_id}")
async def game_websocket_endpoint(
    websocket: WebSocket, room_id: str, name: str = Query(...)
):

    pubsub = None
    listener_task = None

    player_id = None
    connection_id = None

    try:

        # Subscribe before registering the player.
        # This prevents us from missing events generated
        # while the connection is being established.
        pubsub = await room_manager.subscribe(room_id)

        await websocket.accept()

        try:
            connection = await room_manager.connect(room_id, name)

        except ValueError as exc:

            await send_error(websocket, str(exc))

            await websocket.close(code=1008, reason=str(exc))

            return

        player_id = connection["player_id"]
        connection_id = connection["connection_id"]

        room = await room_manager.get_room(room_id)

        if room is None:
            await send_error(websocket, "This room is no longer available.")

            await websocket.close()
            return

        client = room["players"][player_id]

        # Send connection information directly to this client.
        await websocket.send_json(
            {
                "type": "WELCOME",
                "room_id": room_id,
                "player_id": player_id,
                "player_name": client["name"],
                "role": client["role"],
                "status": room["status"],
                "players": [
                    {"player_id": p["player_id"], "name": p["name"], "role": p["role"]}
                    for p in room["players"].values()
                ],
            }
        )

        # A reconnecting player needs the latest game state.
        # Pub/Sub alone cannot provide events that were missed.
        if room["game"] is not None:

            game = Game.from_storage_dict(room["game"])

            await websocket.send_json({"type": "GAME_STATE", "state": game.to_dict()})

        # Listen for events published by any Render instance.
        listener_task = asyncio.create_task(
            relay_room_events(
                websocket, pubsub, player_id, connection_id, room["version"]
            )
        )

        # Receive actions from the player.
        while True:

            try:
                raw_data = await websocket.receive_json()

            except json.JSONDecodeError:
                await send_error(
                    websocket, "Malformed JSON. Please send a valid JSON object."
                )
                continue

            except WebSocketDisconnect:
                break

            try:
                packet = GameAction(**raw_data)

            except (ValidationError, TypeError) as exc:
                await send_error(websocket, f"Invalid action message: {exc}")
                continue

            action = packet.action.strip().upper()

            if action == "HEARTBEAT":

                alive = await room_manager.heartbeat(room_id, player_id, connection_id)

                if not alive:
                    await websocket.close(
                        code=4001, reason="Connection expired or replaced."
                    )
                    break

                continue

            try:

                await room_manager.perform_action(
                    room_id=room_id,
                    player_id=player_id,
                    connection_id=connection_id,
                    action=packet.action,
                    data=packet.data or {},
                )

            except ConnectionReplacedError:

                await websocket.close(
                    code=4001, reason="This connection has been replaced."
                )

                break

            except ValueError as exc:

                await send_error(websocket, str(exc))

                continue

    except WebSocketDisconnect:
        pass

    except Exception:
        logger.exception("Unexpected WebSocket error in room %s", room_id)

    finally:

        # Stop the Pub/Sub listener.
        if listener_task:

            listener_task.cancel()

            with suppress(asyncio.CancelledError):
                await listener_task

        # Close this connection's Pub/Sub subscription.
        if pubsub:
            await pubsub.aclose()

        # Remove or mark the player as disconnected.
        # The connection ID prevents an old socket from
        # clearing the state of a newer connection.
        if player_id and connection_id:

            await room_manager.disconnect(room_id, player_id, connection_id)
