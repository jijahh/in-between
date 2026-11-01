import uuid
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from .connection import room_manager

router = APIRouter(prefix="/api/rooms", tags=["Rooms"])


class JoinRoomRequest(BaseModel):
    room_code: str


@router.post("/create", status_code=status.HTTP_201_CREATED)
async def create_room():
    # Retry on the extremely unlikely chance of a short-code collision.
    for _ in range(5):
        room_id = uuid.uuid4().hex[:8]
        if room_manager.get_room(room_id) is None:
            room_manager.create_room(room_id)
            return {
                "success": True,
                "room_id": room_id,
                "message": "Room initialized successfully.",
            }
    raise HTTPException(status_code=503, detail="Could not allocate a room code.")


@router.post("/join")
async def join_room(payload: JoinRoomRequest):
    room_id = payload.room_code.strip().lower()
    room = room_manager.get_room(room_id)
    if room is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The requested game room code does not exist.",
        )
    if room.status != "waiting":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The game has already started.",
        )
    return {
        "success": True,
        "room_id": room_id,
        "message": "Room found. Connect over WebSocket to join.",
    }
