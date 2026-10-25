"""Expired polling jobs must not advertise audio that cleanup may remove."""
import time
import unittest
from unittest.mock import patch

from fastapi import HTTPException
import httpx
from gateway import app as module


class ChatExpiryTests(unittest.IsolatedAsyncioTestCase):
    def fixtures(self):
        now = time.monotonic()
        return now, {
            'expired': {'done': True, 'created': now-601, 'clips': [{'audio_url': '/audio/expired.wav'}]},
            'boundary': {'done': True, 'created': now-600, 'clips': []},
            'recent': {'done': True, 'created': now-1, 'clips': []},
            'active': {'done': False, 'created': now-900, 'clips': []},
        }

    async def test_poll_sweeps_expired_jobs_but_preserves_active_and_boundary(self):
        now, jobs = self.fixtures()
        with patch.object(module, 'jobs', jobs), patch.object(module.time, 'monotonic', return_value=now):
            result = await module.get_chat_job('recent')
            self.assertIs(result, jobs['recent'])
            self.assertNotIn('expired', jobs)
            self.assertEqual(set(jobs), {'boundary', 'recent', 'active'})
            self.assertIs(await module.get_chat_job('active'), jobs['active'])
            self.assertIs(await module.get_chat_job('boundary'), jobs['boundary'])

    async def test_expired_poll_and_cancel_both_return_404(self):
        for endpoint in (module.get_chat_job, module.cancel_chat_job):
            now, jobs = self.fixtures()
            with self.subTest(endpoint=endpoint.__name__), patch.object(module, 'jobs', jobs), \
                 patch.object(module.time, 'monotonic', return_value=now):
                with self.assertRaises(HTTPException) as error:
                    await endpoint('expired')
                self.assertEqual(error.exception.status_code, 404)
                self.assertNotIn('expired', jobs)
                self.assertFalse(jobs['active']['done'])

    async def test_http_poll_stops_advertising_expired_audio(self):
        now, jobs = self.fixtures()
        with patch.object(module, 'jobs', jobs), patch.object(module.time, 'monotonic', return_value=now):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app), base_url='http://test') as client:
                response = await client.get('/api/chat/jobs/expired')
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json(), {'detail': '对话已过期'})
                response = await client.delete('/api/chat/jobs/expired')
                self.assertEqual(response.status_code, 404)
                response = await client.get('/api/chat/jobs/boundary')
                self.assertEqual(response.status_code, 200)
                response = await client.get('/api/chat/jobs/active')
                self.assertEqual(response.status_code, 200)
                self.assertFalse(response.json()['done'])


if __name__ == '__main__':
    unittest.main()
