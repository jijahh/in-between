# In-Between

A multiplayer card game inspired by the classic **In-Between** (also known as Acey-Deucey). Players take turns betting whether a drawn card's value will fall higher than, lower than, or between their two dealt cards.

**Live deployment:** [https://in-between-ronl.onrender.com](https://in-between-ronl.onrender.com)

## Overview

In-Between is a real-time multiplayer game with a Python backend built using FastAPI and WebSockets.

Players can create or join game rooms, connect with other players, and play together through real-time communication. The server manages each room's game state and broadcasts updates to connected players.

## Game Rules

### Setup

- Each player starts with **$1,000**.
- A standard 52-card deck is shuffled.
- Each player is dealt two cards.
- Every round, each player contributes **$20** to the pot.
- The turn order is randomized when the game starts.

### Gameplay

On their turn, a player can:

- **PASS** — Skip their turn without placing a bet.
- **BET** — Place a bet and predict the value of the next drawn card.

There are three betting choices:

| Choice  | Winning condition                                           |
| ------- | ----------------------------------------------------------- |
| Higher  | Drawn card is higher than both dealt cards.                 |
| Lower   | Drawn card is lower than both dealt cards.                  |
| Between | Drawn card's value is strictly between the two dealt cards. |

If the player wins:

- The bet amount is transferred from the pot to the player's balance.

If the player loses:

- The bet amount is transferred from the player's balance to the pot.

Players can also bet **all in**, subject to the current pot amount.

### Round and Game End

- Once every player has taken their turn, a new round begins.
- Each new round deals fresh cards and collects another $20 from each player.
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

- **Python** — Backend programming language
- **FastAPI** — HTTP API and WebSocket server
- **WebSockets** — Real-time communication between players and the server
- **Uvicorn** — ASGI server
- **Render** — Backend hosting and deployment

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

_Adjust the filenames above if your actual repository uses different names._

## Backend Architecture

The backend is divided into three main responsibilities:

### 1. Game Logic (`main_game.py`)

Contains the core game implementation.

The `Game` class manages:

- Player creation and initialization.
- Card deck generation and shuffling.
- Dealing cards.
- Player balances and the shared pot.
- Turn order and round progression.
- Bet validation and outcome calculation.
- Game-over conditions.
- Game state serialization.

The game logic is kept separate from the WebSocket implementation.

### 2. Connection Management (`connection.py`)

Manages active player connections and room membership.

It is responsible for keeping track of connected clients so the server can communicate with players in their respective rooms.

### 3. WebSocket Handling (`websocket.py`)

Handles real-time communication between the clients and the backend.

It processes incoming player messages, executes the corresponding game actions, and broadcasts game events and state updates to connected players.

### 4. API Routes (`api_routes.py`)

Contains the HTTP endpoints exposed by the backend.

### 5. Application Entry Point (`main.py`)

Initializes the FastAPI application and registers the API routes and WebSocket handlers.

## Real-Time Communication

The game uses WebSockets to maintain persistent connections between players and the backend.

Instead of repeatedly polling an HTTP endpoint, connected players receive events as they happen.

Examples of game events include:

| Event           | Description                                   |
| --------------- | --------------------------------------------- |
| `GAME_STATE`    | Sends the current game state.                 |
| `CARD_DRAWN`    | Notifies clients that a player drew a card.   |
| `PLAYER_WON`    | Indicates that a player won their bet.        |
| `PLAYER_LOST`   | Indicates that a player lost their bet.       |
| `PLAYER_PASSED` | Notifies clients that a player passed.        |
| `ROUND_STARTED` | Announces the beginning of a new round.       |
| `GAME_OVER`     | Announces the winner and the end of the game. |

The server is responsible for validating player actions and updating the authoritative game state.

## Local Development

### Prerequisites

- Python 3.12 or a compatible Python version.
- pip
- Git

### 1. Clone the repository

```bash
git clone https://github.com/jijahh/in-between.git
cd in-between
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

Activate it:

**Windows (PowerShell):**

```powershell
.venv\Scripts\Activate.ps1
```

**macOS / Linux:**

```bash
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the server

Since the application package is inside `src/`, run:

```bash
PYTHONPATH=src uvicorn in_between.main:app --reload
```

On Windows PowerShell, if needed:

```powershell
$env:PYTHONPATH="src"
uvicorn in_between.main:app --reload
```

The server will be available at:

```text
http://127.0.0.1:8000
```

## Deployment

The backend is deployed using [Render](https://render.com/) as a Python Web Service.

**Build command:**

```bash
pip install -r requirements.txt
```

**Start command:**

```bash
PYTHONPATH=src uvicorn in_between.main:app --host 0.0.0.0 --port $PORT
```

### Deployment Considerations

This deployment currently uses in-memory state management rather than Redis or another shared data store.

Consequently:

- All connected players must reach the same running server process to share room state.
- Room and game state are not persisted between server restarts.
- A server restart or redeployment clears active rooms and games.
- Running multiple server instances would cause each instance to maintain its own independent room state.

The current architecture is suitable for a small-scale deployment running a single server instance. A shared data store would be needed to reliably support multiple instances and persistent game sessions.

## Future Improvements

Potential improvements include:

- Persistent room and game state.
- Shared state management for multi-instance deployments.
- Improved reconnection and session recovery.
- More robust handling of disconnected players.
- Game history and statistics.
- Additional betting options and game settings.

## License

This project is open source. Add a license file if you intend to specify permissions for reuse and distribution.
