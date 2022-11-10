#!/usr/bin/env python
import time
import asyncio
import websockets

async def connect():
    async with websockets.connect("ws://localhost:8113/websocket") as websocket:
        await websocket.send('{ "config": {"mac": "test"}, "devType": "IOT_GW_V1_CC_WIFI", "load_meter": { "voltage": 23.4 } }')
        data = await websocket.recv()
        # data = await asyncio.wait_for(websocket.recv(), timeout=10)
        print(f"received: {data}")
        time.sleep(10)

while True:
    asyncio.run(connect())
