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

@app.websocket("/audio")
async def audio_stream(websocket: WebSocket):
    await websocket.accept()
    print("Client connected for audio streaming")

    try:
        while True:
            data = await websocket.receive_bytes()
            print(f"Received audio chunk of size {len(data)} bytes")
            await websocket.send_text(f"Chunk of {len(data)} bytes received")
    except Exception as e:
        print("Connection closed:", e)


