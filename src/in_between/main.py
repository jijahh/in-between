from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from in_between.api_routes import router as rooms_router
from in_between.websocket import router as websocket_router

app = FastAPI(
    title="In Between WebSocket API",
    description="Room management and real-time In Between game actions.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rooms_router)
app.include_router(websocket_router)


@app.get("/")
async def root():
    return {"message": "In Between WebSocket API is running."}


@app.get("/health")
async def health():
    return {"status": "ok"}
