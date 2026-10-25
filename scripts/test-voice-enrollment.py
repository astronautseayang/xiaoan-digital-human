"""Voice enrollment is committed only after preview and config storage succeed."""
import asyncio
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave
import httpx
from fastapi import UploadFile, HTTPException
from gateway import app as module

class EnrollmentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.audio=self.root/'artifacts/audio';self.audio.mkdir(parents=True)
        self.config=self.root/'config/voice.json';self.config.parent.mkdir()
        self.config.write_text('{"label":"working voice"}')
        data=io.BytesIO()
        with wave.open(data,'wb') as wav:
            wav.setparams((1,2,16000,0,'NONE','NONE'));wav.writeframes(b'\1\0'*96000)
        self.data=data.getvalue()
        for name,value in [('ROOT',self.root),('AUDIO',self.audio),('VOICE_FILE',self.config)]:
            p=patch.object(module,name,value);p.start();self.addCleanup(p.stop)
        p=patch.object(module,'normalize_speech',side_effect=lambda data,**kw:data);p.start();self.addCleanup(p.stop)
    async def enroll(self):
        file=UploadFile(file=io.BytesIO(self.data),filename='reference.wav')
        try:return await module.enroll_voice(file,text='你好，这是录入的参考声音。')
        finally:await file.close()
    def assert_rolled_back(self):
        self.assertEqual(self.config.read_text(),'{"label":"working voice"}')
        self.assertEqual(list(self.audio.iterdir()),[])
        self.assertEqual(list((self.root/'assets/reference/enrolled').glob('*')),[])
        self.assertEqual(list(self.config.parent.iterdir()),[self.config])
    async def test_cancelled_preview_removes_reference(self):
        entered=asyncio.Event()
        async def synth(*a,**kw):
            entered.set();await asyncio.Event().wait()
        with patch.object(module,'synthesize',synth):
            task=asyncio.create_task(self.enroll())
            await asyncio.wait_for(entered.wait(),1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
        self.assert_rolled_back()
    async def test_storage_failure_preserves_voice_and_removes_files(self):
        async def synth(*a,**kw):return b'preview'
        original=Path.replace
        def replace(path,target):
            if Path(target)==self.config:raise OSError('Injected config replacement failure')
            return original(path,target)
        with patch.object(module,'synthesize',synth),patch.object(Path,'replace',replace):
            with self.assertRaises(HTTPException) as caught:await self.enroll()
            self.assertEqual(caught.exception.status_code, 503)
        self.assert_rolled_back()

    async def test_storage_errors_return_service_unavailable(self):
        async def synth(*a, **kw):return b'preview'
        original_mkdir, original_write, original_replace = Path.mkdir, Path.write_bytes, Path.replace
        references = self.root/'assets/reference/enrolled'
        for failure in ('directory', 'reference', 'preview', 'config'):
            with self.subTest(failure=failure):
                def mkdir(path, *args, **kwargs):
                    if path == references and failure == 'directory':
                        raise PermissionError('Injected reference directory failure')
                    return original_mkdir(path, *args, **kwargs)
                def write(path, data):
                    if (path.parent == references and failure == 'reference') or (path.parent == self.audio and failure == 'preview'):
                        original_write(path, data[:3])
                        raise OSError('Injected partial audio write')
                    return original_write(path, data)
                def replace(path, target):
                    if Path(target) == self.config and failure == 'config':
                        raise PermissionError('Injected configuration failure')
                    return original_replace(path, target)
                with patch.object(module, 'synthesize', synth), patch.object(Path, 'mkdir', mkdir), patch.object(Path, 'write_bytes', write), patch.object(Path, 'replace', replace):
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app, raise_app_exceptions=False), base_url='http://test') as client:
                        response = await client.post('/api/voice/enroll', files={'file':('reference.wav',self.data,'audio/wav')}, data={'text':'你好，这是录入的参考声音。'})
                self.assertEqual(response.status_code, 503)
                self.assertIn('保存失败', response.json()['detail'])
                self.assert_rolled_back()
        with patch.object(module, 'synthesize', synth):
            result = await self.enroll()
        self.assertTrue((self.audio/Path(result['audio_url']).name).exists())
    async def test_success_retains_reference_and_preview(self):
        async def synth(*a,**kw):return b'preview'
        with patch.object(module,'synthesize',synth):result=await self.enroll()
        import json
        config=json.loads(self.config.read_text())
        self.assertEqual(Path(config['ref_audio_path']).read_bytes(),self.data)
        self.assertEqual((self.audio/Path(result['audio_url']).name).read_bytes(),b'preview')
        self.assertEqual(len(list(self.config.parent.iterdir())),1)

    async def test_preview_failure_and_partial_write_are_cleaned(self):
        async def fail(*a,**kw):raise RuntimeError('Injected preview failure')
        with patch.object(module,'synthesize',fail):
            with self.assertRaises(RuntimeError):await self.enroll()
        self.assert_rolled_back()
        async def synth(*a,**kw):return b'preview'
        original=Path.write_bytes
        def write(path,data):
            if path.parent==self.audio:
                original(path,b'partial')
                raise OSError('Injected preview disk failure')
            return original(path,data)
        with patch.object(module,'synthesize',synth),patch.object(Path,'write_bytes',write):
            with self.assertRaises(HTTPException) as caught:await self.enroll()
            self.assertEqual(caught.exception.status_code, 503)
        self.assert_rolled_back()

if __name__=='__main__':unittest.main()
