"""Wake WebSocket subscriptions/tasks are released on either direction failing."""
import asyncio
import unittest
from unittest.mock import patch

from fastapi import WebSocketDisconnect
from gateway import app as module


class WakeSocketTests(unittest.IsolatedAsyncioTestCase):
    async def test_disconnect_during_initial_status_does_not_leak_subscription(self):
        await self.check_disconnect('initial')

    async def test_sender_disconnect_stops_receiver(self):
        await self.check_disconnect('sender')

    async def test_receiver_disconnect_stops_sender(self):
        await self.check_disconnect('receiver')

    async def check_disconnect(self, failure):
        class Service:
            clients = set()

            def snapshot(self):
                return {'type': 'status'}

            async def receive_control(self, data):
                pass

        service = Service()

        class Socket:
            sends = 0

            async def accept(self):
                pass

            async def send_json(self, data):
                self.sends += 1
                if failure == 'initial' or (failure == 'sender' and self.sends > 1):
                    raise WebSocketDisconnect()
                if failure == 'sender':
                    next(iter(service.clients)).put_nowait({'type': 'state'})

            async def receive_json(self):
                if failure == 'receiver':
                    raise WebSocketDisconnect()
                await asyncio.Event().wait()

        with patch.object(module.app.state, 'wake', service, create=True):
            await asyncio.wait_for(module.wake_socket(Socket()), .5)
        self.assertFalse(service.clients)
        self.assertFalse([t for t in asyncio.all_tasks() if t is not asyncio.current_task()])


if __name__ == '__main__':
    unittest.main()
