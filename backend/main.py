from fastapi import FastAPI, WebSocket
import asyncio

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        await websocket.send_json({"risk": "medium", "score": 45})
        await asyncio.sleep(2)

