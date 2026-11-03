import json
import os
import uuid

from typing import Any, Callable

from redis.asyncio import Redis
from redis.exceptions import WatchError

from .main_game import Game

HEARTBEAT_INTERVAL_SECONDS = 25
CONNECTION_TTL_SECONDS = 90
ROOM_TTL_SECONDS = 60 * 60 * 24


class ConnectionReplacedError(Exception):
    pass


class RoomManager:

    def __init__(self):
        self.redis: Redis | None = None

    async def startup(self):
        redis_url = os.getenv("REDIS_URL")

        if not redis_url:
            raise RuntimeError("REDIS_URL environment variable is missing.")

        self.redis = Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            health_check_interval=30,
        )

        await self.redis.ping()

        print("[REDIS] Connected successfully.")

    async def shutdown(self):
        if self.redis:
            await self.redis.aclose()
            self.redis = None

    def _get_redis(self):
        if self.redis is None:
            raise RuntimeError("Redis has not been initialized.")

        return self.redis

    def _room_key(self, room_id):
        return f"room:{room_id}"

    def _event_channel(self, room_id):
        return f"room:{room_id}:events"

    def _lease_key(self, room_id, player_id):
        return f"room:{room_id}:player:{player_id}:lease"

    async def heartbeat(self, room_id, player_id, connection_id):

        redis = self._get_redis()

        lease_key = self._lease_key(room_id, player_id)
        room_key = self._room_key(room_id)

        script = """
            local current_connection = redis.call("GET", KEYS[1])

            if current_connection ~= ARGV[1] then
                return 0
            end

            if redis.call("EXISTS", KEYS[2]) == 0 then
                return 0
            end

            redis.call("EXPIRE", KEYS[1], ARGV[2])
            redis.call("EXPIRE", KEYS[2], ARGV[3])

            return 1
        """

        result = await redis.eval(
            script,
            2,
            lease_key,
            room_key,
            connection_id,
            CONNECTION_TTL_SECONDS,
            ROOM_TTL_SECONDS,
        )

        return bool(result)

    async def release_lease(self, room_id, player_id, connection_id):

        redis = self._get_redis()

        script = """
            if redis.call("GET", KEYS[1]) == ARGV[1] then
                return redis.call("DEL", KEYS[1])
            end

            return 0
        """

        await redis.eval(script, 1, self._lease_key(room_id, player_id), connection_id)

    async def create_room(self, room_id):
        redis = self._get_redis()

        room = {
            "room_id": room_id,
            "status": "waiting",
            "players": {},
            "host_player_id": None,
            "game": None,
            "version": 0,
        }

        result = await redis.set(
            self._room_key(room_id), json.dumps(room), ex=ROOM_TTL_SECONDS, nx=True
        )

        return bool(result)

    async def get_room(self, room_id):
        redis = self._get_redis()

        raw_room = await redis.get(self._room_key(room_id))

        if raw_room is None:
            return None

        return json.loads(raw_room)

    async def subscribe(self, room_id):
        redis = self._get_redis()

        pubsub = redis.pubsub(ignore_subscribe_messages=True)

        await pubsub.subscribe(self._event_channel(room_id))

        return pubsub

    async def _mutate_room(
        self,
        room_id: str,
        mutator: Callable[[dict[str, Any]], tuple[Any, list[dict[str, Any]]]],
    ):

        redis = self._get_redis()

        key = self._room_key(room_id)
        channel = self._event_channel(room_id)

        # Retry if another process modifies the room
        # while we're processing an update.
        for attempt in range(20):

            async with redis.pipeline(transaction=True) as pipe:

                try:
                    # Watch the room key for changes.
                    await pipe.watch(key)

                    raw_room = await pipe.get(key)

                    if raw_room is None:
                        raise ValueError("Room does not exist.")

                    room = json.loads(raw_room)

                    # Apply our changes in Python.
                    # This function must not perform async operations.
                    result, events = mutator(room)

                    # Increment the room version.
                    room["version"] = int(room.get("version", 0)) + 1

                    # Start the Redis transaction.
                    pipe.multi()

                    # Save the updated room.
                    pipe.set(key, json.dumps(room), ex=ROOM_TTL_SECONDS)

                    # Publish all generated events.
                    if events:
                        envelope = {"version": room["version"], "events": events}

                        pipe.publish(channel, json.dumps(envelope))

                    # Execute both operations atomically.
                    await pipe.execute()

                    return result, room

                except WatchError:
                    # Someone else changed the room.
                    # Read the latest state and retry.
                    continue

        raise RuntimeError(
            "Room is being modified too frequently. " "Please try again."
        )

    async def connect(self, room_id, name):

        name = name.strip()

        if not name:
            raise ValueError("A player name is required.")

        connection_id = uuid.uuid4().hex

        def update(room):

            players = room["players"]

            existing = next(
                (
                    player
                    for player in players.values()
                    if player["name"].casefold() == name.casefold()
                ),
                None,
            )

            if room["status"] not in ("waiting", "playing"):
                raise ValueError("This room is no longer accepting connections.")

            if room["status"] == "playing" and existing is None:
                raise ValueError(
                    "The game has already started; " "new players cannot join."
                )

            events = []

            if existing:

                # This player is reconnecting.
                player_id = existing["player_id"]

                old_connection_id = existing.get("connection_id")

                existing["connection_id"] = connection_id

                # Restore the host role if there is currently
                # no assigned host.
                if room["host_player_id"] is None:
                    existing["role"] = "host"
                    room["host_player_id"] = player_id

                # Tell the previous connection to close itself.
                if old_connection_id:
                    events.append(
                        {
                            "type": "_CONNECTION_REPLACED",
                            "player_id": player_id,
                            "connection_id": connection_id,
                        }
                    )

                player = existing

            else:

                if len(players) >= 8:
                    raise ValueError("This room is full.")

                player_id = uuid.uuid4().hex[:12]

                role = "host" if room["host_player_id"] is None else "client"

                player = {
                    "player_id": player_id,
                    "name": name,
                    "role": role,
                    "connection_id": connection_id,
                }

                players[player_id] = player

                if role == "host":
                    room["host_player_id"] = player_id

            events.append(
                {
                    "type": "PLAYER_JOINED",
                    "player_id": player_id,
                    "player_name": player["name"],
                    "role": player["role"],
                }
            )

            return {
                "player_id": player_id,
                "connection_id": connection_id,
                "role": player["role"],
            }, events

        result, _ = await self._mutate_room(room_id, update)

        redis = self._get_redis()

        await redis.set(
            self._lease_key(room_id, result["player_id"]),
            result["connection_id"],
            ex=CONNECTION_TTL_SECONDS,
        )

        return result

    async def disconnect(self, room_id, player_id, connection_id):

        def update(room):

            player = room["players"].get(player_id)

            if not player:
                return False, []

            # Make sure this is still the player's active
            # connection before changing anything.
            if player.get("connection_id") != connection_id:
                return False, []

            player_name = player["name"]

            player["connection_id"] = None

            # In waiting rooms, disconnected players are removed.
            # In active games, they remain so they can reconnect.
            if room["status"] == "waiting":
                room["players"].pop(player_id)

            # Transfer host privileges if the host disconnects.
            if room["host_player_id"] == player_id:

                room["host_player_id"] = None

                if room["status"] == "playing":
                    player["role"] = "client"

                for candidate_id, candidate in room["players"].items():

                    if candidate_id == player_id:
                        continue

                    candidate["role"] = "host"

                    room["host_player_id"] = candidate_id

                    break

            events = [
                {
                    "type": "PLAYER_LEFT",
                    "player_id": player_id,
                    "player_name": player_name,
                }
            ]

            return True, events

        try:
            await self._mutate_room(room_id, update)

        except ValueError:
            # The room may already have expired.
            pass

        await self.release_lease(room_id, player_id, connection_id)

    async def perform_action(
        self, room_id, player_id, connection_id, action, data=None
    ):

        action = action.strip().upper()

        def update(room):

            player = room["players"].get(player_id)

            if not player:
                raise ValueError("Player is no longer in this room.")

            # Reject messages from an old WebSocket.
            if player.get("connection_id") != connection_id:
                raise ConnectionReplacedError("This connection has been replaced.")

            # Starting the game.
            if action == "START_GAME":

                if player["role"] != "host":
                    raise ValueError("Only the host can start the game.")

                if room["status"] != "waiting":
                    raise ValueError("The game has already started.")

                names = [p["name"] for p in room["players"].values()]

                if len(names) < 2:
                    raise ValueError("At least two players must join before starting.")

                game = Game(names)

                room["game"] = game.to_storage_dict()
                room["status"] = "playing"

                events = [{"type": "GAME_STARTED", "state": game.to_dict()}]

                return None, events

            # All other actions require a running game.
            if room["status"] != "playing" or room["game"] is None:
                raise ValueError("The host must start the game first.")

            # Reconstruct the Game object from Redis.
            game = Game.from_storage_dict(room["game"])

            # Reuse your existing game logic.
            events = game.handle_action(player["name"], action, data or {})

            # Save the updated game.
            room["game"] = game.to_storage_dict()

            return None, events

        result, _ = await self._mutate_room(room_id, update)

        return result


room_manager = RoomManager()
