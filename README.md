# In-Between

A real-time multiplayer card game inspired by the card game **In-Between**. Players take turns betting whether a drawn card's value will be higher than, lower than, or between their two dealt cards (non-inclusive).

**Live game Front End:** [https://in-between-web-zeta.vercel.app](https://in-between-web-zeta.vercel.app)

**Live game API:** [https://in-between-ronl.onrender.com](https://in-between-ronl.onrender.com)

**Repository:** [https://github.com/jijahh/in-between](https://github.com/jijahh/in-between)

## Overview

In-Between is a multiplayer card game with a Python backend built using FastAPI and WebSockets.

Players can create or join game rooms and play together through real-time communication. The server manages game logic, player turns, balances, and room state.

The application uses Redis to maintain shared room and game state across server instances. Redis Pub/Sub distributes game events between instances, while local WebSocket connections handle communication with the clients connected to each instance.

## Features

- Multiplayer game rooms with unique room codes.
- Real-time communication using WebSockets.
- Support for up to 8 players per room.
- Randomized player order and card dealing.
- Betting options: Higher, Lower, and Between.
- Player balances and a shared betting pot.
- Host privileges and game initialization.
- Player reconnection using their existing player name.
- Shared game state through Redis.
- Cross-instance event broadcasting using Redis Pub/Sub.
- Connection leases and token-guarded heartbeats.
- Automatic recovery of the latest game state upon reconnection.
- Optimistic concurrency control to prevent conflicting game-state updates.

## Game Rules

### Setup

- Each player starts with **$1,000**.
- A standard 52-card deck is shuffled.
- Each player is dealt two cards.
- Every round, each player contributes **$20** to the pot.
- Player order is randomized when a game starts.

### Gameplay

Players take turns and can choose between two actions:

**PASS**

- Skips the player's turn.
- Does not change their balance or the pot.

**BET**

- Places a wager and predicts the value of the next drawn card.
- The bet amount cannot exceed the player's balance or the current pot.
- Players can also bet all in, subject to those same limits.

The available betting choices are:

| Choice  | Winning condition                                           |
| ------- | ----------------------------------------------------------- |
| Higher  | Drawn card is higher than both dealt cards.                 |
| Lower   | Drawn card is lower than both dealt cards.                  |
| Between | Drawn card's value is strictly between the two dealt cards. |

If the player wins, the wager is transferred from the pot to their balance.

If the player loses, the wager is transferred from their balance to the pot.

**Current betting validation:** The implementation only permits Higher and Lower bets when the two dealt cards have equal values. Between is only permitted when the two dealt cards have different values.

### Round Progression

- A new round starts after every player has taken their turn.
- Players receive two new cards at the beginning of each round.
- Each player contributes another $20 to the pot.
- If the pot reaches zero, a new round is started.
- The game ends when only one player has money remaining.

### Card Values

| Card  | Value |
| ----- | ----: |
| Ace   |     1 |
| 2–10  |  2–10 |
| Jack  |    11 |
| Queen |    12 |
| King  |    13 |

All four suits are included: Hearts, Diamonds, Clubs, and Spades.

## Tech Stack

| Technology    | Purpose                           |
| ------------- | --------------------------------- |
| Python        | Backend programming language      |
| FastAPI       | HTTP API and WebSocket server     |
| WebSockets    | Real-time communication           |
| Redis         | Shared room and game state        |
| Redis Pub/Sub | Cross-instance event broadcasting |
| redis-py      | Asynchronous Redis client         |
| Uvicorn       | ASGI server                       |
| Pydantic      | Request validation                |

## Project Structure

```text
src/
└── in_between/
    ├── __init__.py
    ├── main.py
    ├── main_game.py
    ├── connection.py
    ├── websocket.py
    └── api_routes.py

requirements.txt
.python-version
```

### Application Modules

**`main.py`**

Initializes the FastAPI application, configures CORS, registers HTTP and WebSocket routes, and manages the application's Redis connection lifecycle.

**`main_game.py`**

Contains the core game implementation.

The `Game` class manages:

- Player creation and initialization.
- Card deck generation and shuffling.
- Dealing cards.
- Player balances and the shared pot.
- Turn order and round progression.
- Bet validation and outcome calculation.
- Game-over conditions.
- Game-state serialization and reconstruction.

It provides two methods for Redis compatibility:

- `to_storage_dict()` converts a game into a JSON-compatible dictionary.
- `from_storage_dict()` reconstructs a `Game` object from stored data.

This allows game logic to remain independent of Redis while supporting state recovery across server instances.

**`connection.py`**

Contains the `RoomManager`, which handles shared room state and connection management.

Its responsibilities include:

- Creating and retrieving rooms.
- Connecting and reconnecting players.
- Managing player identities and connection IDs.
- Tracking connection leases.
- Handling disconnects.
- Processing game actions.
- Updating room state in Redis.
- Publishing game events through Redis Pub/Sub.

**`websocket.py`**

Handles WebSocket connections and real-time communication.

It:

- Accepts player connections.
- Sends welcome messages and game-state snapshots.
- Receives and validates player actions.
- Processes heartbeat messages.
- Subscribes to Redis Pub/Sub channels.
- Forwards room events to locally connected players.
- Handles connection replacement and disconnection.

**`api_routes.py`**

Contains HTTP endpoints for creating and validating game rooms.

## Backend Architecture

### Redis as the Shared State Store

Each room and its associated game state are stored in Redis as JSON.

A room contains:

- Room ID and status.
- Player IDs, names, and roles.
- Current host.
- Player connection IDs.
- Serialized game state.
- Room version number.

Example Redis key:

```text
room:ABC123
```

The game state includes the remaining deck, player balances, dealt cards, current player index, pot, and winner.

Unlike local Python memory, Redis provides shared data accessible to every running backend instance.

### Redis Pub/Sub

Every WebSocket connection subscribes to its room's event channel.

Example:

```text
room:ABC123:events
```

When a player performs an action:

1. The backend retrieves the latest room state from Redis.
2. The game action is processed.
3. The updated state is saved.
4. The resulting events are published to the room's Redis channel.
5. Every subscribed backend instance receives the events.
6. Each instance forwards the events to its locally connected players.

This allows players connected to different server instances to receive the same game updates.

Actual WebSocket objects are kept in local server memory and are never stored in Redis.

### Optimistic Concurrency Control

To prevent simultaneous game actions from overwriting each other's updates, room modifications use Redis transactions with `WATCH`, `MULTI`, and `EXEC`.

Each room has a version number that increments whenever its state is modified.

If another instance modifies the room while an update is being processed, Redis detects the conflict and the operation is retried using the latest state.

This helps prevent lost updates when multiple players interact with the same room.

### Connection Management and Reconnection

Each WebSocket connection is assigned a unique connection ID.

Redis stores the currently active connection ID for every player.

When a player reconnects using their existing name:

- Their existing player ID is retained.
- A new connection ID is generated.
- Redis updates the player's active connection.
- The old connection is notified that it has been replaced.
- The reconnecting player receives the latest game state.

Connection IDs also protect against stale disconnect handlers. An old connection cannot accidentally remove or overwrite a newer connection.

### Heartbeat and Connection Leases

The application uses periodic heartbeats to monitor active connections.

The frontend sends a heartbeat every 15 seconds.

Each heartbeat is validated against the connection ID stored in Redis. A valid heartbeat renews:

- The player's connection lease.
- The room's expiration time.

The connection lease has a 45-second TTL. If heartbeats stop, Redis automatically expires the lease.

The connection lease uses a token-guarded mechanism so an old connection cannot renew or delete a newer connection's lease.

### Room Expiration

Rooms have a 24-hour TTL.

Successful room updates refresh the expiration time. Valid heartbeats also refresh the room TTL, allowing inactive games to remain available while players are still connected.

Rooms that remain inactive eventually expire.

### Game-State Recovery

Redis Pub/Sub does not retain messages for disconnected subscribers.

To handle missed events, the backend sends a fresh `GAME_STATE` snapshot whenever a player connects or reconnects to a room with an existing game.

This allows players to recover the current game state without needing to replay every missed event.

## API Reference

### HTTP Endpoints

| Method | Endpoint            | Description                                    |
| ------ | ------------------- | ---------------------------------------------- |
| GET    | `/`                 | Checks whether the API is running.             |
| GET    | `/health`           | Health check endpoint.                         |
| POST   | `/api/rooms/create` | Creates a new game room.                       |
| POST   | `/api/rooms/join`   | Validates whether a room is available to join. |

### Create Room

```http
POST /api/rooms/create
```

Example response:

```json
{
  "success": true,
  "room_id": "abc12345",
  "message": "Room initialized successfully."
}
```

The player who creates the room connects through the WebSocket endpoint to join as the host.

### Join Room

```http
POST /api/rooms/join
Content-Type: application/json
```

Request:

```json
{
  "room_code": "abc12345"
}
```

Example response:

```json
{
  "success": true,
  "room_id": "abc12345",
  "message": "Room found. Connect over WebSocket to join."
}
```

This endpoint validates the room but does not establish a player connection. Players must connect through WebSockets afterward.

### WebSocket Endpoint

```text
/ws/{room_id}?name={player_name}
```

Example:

```text
wss://in-between-ronl.onrender.com/ws/abc12345?name=PlayerA
```

Use `ws://` for local development and `wss://` for HTTPS-hosted environments.

## WebSocket Message Reference

### Client-to-Server Messages

**Start Game**

Only the host can start the game.

```json
{
  "action": "START_GAME"
}
```

**Pass**

```json
{
  "action": "PASS"
}
```

**Place a Bet**

```json
{
  "action": "BET",
  "data": {
    "amount": 100,
    "choice": "between"
  }
}
```

Valid choices:

- `higher`
- `lower`
- `between`

**All-In Bet**

```json
{
  "action": "BET",
  "data": {
    "amount": "all_in",
    "choice": "higher"
  }
}
```

**Heartbeat**

The frontend sends this message every 15 seconds while the WebSocket is connected.

```json
{
  "action": "HEARTBEAT"
}
```

### Server-to-Client Events

| Event           | Description                                              |
| --------------- | -------------------------------------------------------- |
| `WELCOME`       | Confirms the connection and provides player information. |
| `PLAYER_JOINED` | A player joins the room.                                 |
| `PLAYER_LEFT`   | A player disconnects.                                    |
| `GAME_STARTED`  | The host starts the game.                                |
| `GAME_STATE`    | Provides the current game state.                         |
| `CARD_DRAWN`    | A player draws a card.                                   |
| `PLAYER_WON`    | A player wins their bet.                                 |
| `PLAYER_LOST`   | A player loses their bet.                                |
| `PLAYER_PASSED` | A player passes their turn.                              |
| `ROUND_STARTED` | A new round begins.                                      |
| `GAME_OVER`     | The game ends and a winner is announced.                 |
| `ERROR`         | An action or connection-related error occurs.            |

## Frontend Integration

The following example uses native JavaScript WebSockets and the Fetch API. It can be adapted to React, Vue, or another frontend framework.

### 1. Configure the API URL

```javascript
const API_URL = "https://in-between-ronl.onrender.com";

const WS_URL = API_URL.replace(/^http/, "ws");
```

For local development:

```javascript
const API_URL = "http://localhost:8000";
const WS_URL = "ws://localhost:8000";
```

### 2. Create a Room

```javascript
async function createRoom() {
  const response = await fetch(`${API_URL}/api/rooms/create`, {
    method: "POST",
  });

  if (!response.ok) {
    throw new Error("Failed to create room.");
  }

  return await response.json();
}
```

Usage:

```javascript
const room = await createRoom();

console.log("Room ID:", room.room_id);
```

### 3. Join a Room

Before connecting, another player can validate the room using:

```javascript
async function validateRoom(roomCode) {
  const response = await fetch(`${API_URL}/api/rooms/join`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      room_code: roomCode,
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Unable to join room.");
  }

  return await response.json();
}
```

This checks whether the room exists and is still waiting for players.

### 4. Connect Through WebSockets

```javascript
function connectToRoom(roomId, playerName, onEvent) {
  const url =
    `${WS_URL}/ws/${encodeURIComponent(roomId)}` +
    `?name=${encodeURIComponent(playerName)}`;

  const socket = new WebSocket(url);

  let heartbeatInterval = null;

  socket.addEventListener("open", () => {
    console.log("Connected to room:", roomId);

    heartbeatInterval = setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(
          JSON.stringify({
            action: "HEARTBEAT",
          }),
        );
      }
    }, 15000);
  });

  socket.addEventListener("message", (event) => {
    try {
      const message = JSON.parse(event.data);

      console.log("Server event:", message);

      if (onEvent) {
        onEvent(message);
      }
    } catch (error) {
      console.error("Invalid server message:", error);
    }
  });

  socket.addEventListener("close", (event) => {
    console.log("Disconnected:", event.code, event.reason);

    if (heartbeatInterval) {
      clearInterval(heartbeatInterval);
      heartbeatInterval = null;
    }
  });

  socket.addEventListener("error", (error) => {
    console.error("WebSocket error:", error);
  });

  function send(action, data = {}) {
    if (socket.readyState !== WebSocket.OPEN) {
      console.error("WebSocket is not connected.");
      return false;
    }

    socket.send(
      JSON.stringify({
        action,
        ...(Object.keys(data).length > 0 ? { data } : {}),
      }),
    );

    return true;
  }

  function close() {
    if (heartbeatInterval) {
      clearInterval(heartbeatInterval);
      heartbeatInterval = null;
    }

    socket.close();
  }

  return {
    socket,
    send,
    close,
  };
}
```

### 5. Handle Server Events

Example event handler:

```javascript
function handleGameEvent(message) {
  switch (message.type) {
    case "WELCOME":
      console.log("Welcome:", message.player_name);
      console.log("Your role:", message.role);
      break;

    case "PLAYER_JOINED":
      console.log(`${message.player_name} joined the room.`);
      break;

    case "PLAYER_LEFT":
      console.log(`${message.player_name} disconnected.`);
      break;

    case "GAME_STARTED":
      console.log("Game started!");
      console.log(message.state);
      break;

    case "GAME_STATE":
      console.log("Updated game state:", message.state);
      break;

    case "CARD_DRAWN":
      console.log(`${message.player} drew a card.`);
      break;

    case "PLAYER_WON":
      console.log(`${message.player} won ${message.amount}.`);
      break;

    case "PLAYER_LOST":
      console.log(`${message.player} lost ${message.amount}.`);
      break;

    case "PLAYER_PASSED":
      console.log(`${message.previous_player} passed.`);
      break;

    case "ROUND_STARTED":
      console.log("A new round has started.");
      break;

    case "GAME_OVER":
      console.log("Winner:", message.winner);
      break;

    case "ERROR":
      console.error(message.message);
      break;

    default:
      console.log("Unknown event:", message);
  }
}
```

### 6. Send Game Actions

After connecting:

```javascript
const connection = connectToRoom("abc12345", "PlayerA", handleGameEvent);
```

Start the game:

```javascript
connection.send("START_GAME");
```

Pass:

```javascript
connection.send("PASS");
```

Place a bet:

```javascript
connection.send("BET", {
  amount: 100,
  choice: "between",
});
```

Bet all in:

```javascript
connection.send("BET", {
  amount: "all_in",
  choice: "higher",
});
```

Disconnect:

```javascript
connection.close();
```

### 7. Reconnect to an Existing Game

Players can reconnect using their original room ID and player name.

```javascript
const reconnectedPlayer = connectToRoom("abc12345", "PlayerA", handleGameEvent);
```

The backend identifies the existing player, retains their player ID, replaces their old connection ID, and sends the latest game state.

When reconnecting to a game that has already started, connect directly through the WebSocket endpoint. The HTTP join endpoint is intended for players entering waiting rooms.

## Testing

Testing should cover both normal gameplay and communication between separate backend instances.

### Prerequisites

- Python 3.12 or a compatible Python version.
- pip
- Docker (for running Redis locally).
- A frontend or WebSocket client for testing connections.

### 1. Install Dependencies

Clone the repository:

```bash
git clone https://github.com/jijahh/in-between.git
cd in-between
```

Create and activate a virtual environment:

**Windows PowerShell:**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**macOS / Linux:**

```bash
python -m venv .venv
source .venv/bin/activate
```

Install the requirements:

```bash
pip install -r requirements.txt
```

### 2. Start Redis Locally

Using Docker:

```bash
docker run --name in-between-redis -p 6379:6379 -d redis:7
```

Set the Redis connection URL.

**Windows PowerShell:**

```powershell
$env:REDIS_URL="redis://localhost:6379/0"
```

**macOS / Linux:**

```bash
export REDIS_URL="redis://localhost:6379/0"
```

### 3. Start the Backend

The application package is located inside `src/`.

**Windows PowerShell:**

```powershell
$env:PYTHONPATH="src"
uvicorn in_between.main:app --reload
```

**macOS / Linux:**

```bash
PYTHONPATH=src uvicorn in_between.main:app --reload
```

The local API will be available at:

```text
http://127.0.0.1:8000
```

### 4. Test the HTTP Endpoints

Check whether the backend is running:

```bash
curl http://127.0.0.1:8000/health
```

Create a room:

```bash
curl -X POST http://127.0.0.1:8000/api/rooms/create
```

Join a room:

```bash
curl -X POST http://127.0.0.1:8000/api/rooms/join \
-H "Content-Type: application/json" \
-d '{"room_code":"abc12345"}'
```

Replace the example room code with an actual room code returned by the create endpoint.

### 5. Test Multiple Backend Instances

An important test is verifying that players connected to different backend processes can still participate in the same game.

Start the first backend instance:

```powershell
$env:REDIS_URL="redis://localhost:6379/0"
$env:PYTHONPATH="src"
uvicorn in_between.main:app --port 8000
```

Start a second instance in another terminal:

```powershell
$env:REDIS_URL="redis://localhost:6379/0"
$env:PYTHONPATH="src"
uvicorn in_between.main:app --port 8001
```

Both instances must use the same Redis database.

Test the following scenarios:

| Test                                          | Expected result                                         |
| --------------------------------------------- | ------------------------------------------------------- |
| Create a room on port 8000                    | Room is saved in Redis.                                 |
| Validate the room on port 8001                | The second instance finds the same room.                |
| Connect Player A to port 8000                 | Player A joins successfully.                            |
| Connect Player B to port 8001                 | Player B joins the same room.                           |
| Start the game                                | Both players receive the game-start event.              |
| Player A makes a bet                          | Player B receives the resulting game events.            |
| Player A disconnects                          | Player A remains in the active game.                    |
| Player A reconnects through port 8001         | The same player ID and current game state are restored. |
| Old connection disconnects after reconnection | It does not remove the new connection.                  |
| Heartbeats stop                               | The connection lease expires after its TTL.             |

This test simulates the behavior of multiple Render instances without needing to deploy multiple services.

### 6. Test Reconnection

A particularly important test is reconnecting a player to another backend instance.

For example:

1. Connect Player A to `localhost:8000`.
2. Connect Player B to `localhost:8001`.
3. Start the game.
4. Let Player A make a move.
5. Disconnect Player A.
6. Reconnect Player A to `localhost:8001` using the same room code and name.
7. Confirm that Player A receives the current game state and can continue playing.

The player should retain their existing game identity and balance.

## Architecture Considerations

- Redis is the shared source of truth for rooms and game state.
- WebSocket objects remain local to their respective server instances.
- Redis Pub/Sub is used for real-time event distribution, not permanent event storage.
- Reconnected clients receive a fresh game-state snapshot to recover missed updates.
- Heartbeat leases help detect stale connections and refresh room expiration.
- Connection IDs prevent outdated connections from modifying newer connection state.
- Redis transactions with optimistic locking protect against concurrent state modifications.
- Rooms expire after 24 hours without successful updates or valid heartbeats.

**Note:** The current implementation identifies returning players by their room code and player name. A future improvement would be to issue private player session tokens so that knowing another player's name and room code is not sufficient to take over their connection.
