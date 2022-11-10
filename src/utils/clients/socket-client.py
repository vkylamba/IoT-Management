#!/usr/bin/env python
import time
import asyncio
import websockets

async def connect():
    async with websockets.connect("ws://localhost:8113/websocket") as websocket:
        await websocket.send('{ "config": {"mac": "test"}, "devType": "IOT_GW_V1_CC_WIFI", "load_meter": { "voltage": 23.4 } }')
        data = await websocket.recv()
        print("received:", data)

while True:
    asyncio.run(connect())
    time.sleep(10)
