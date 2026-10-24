"""Explicit desktop integration test using real PulseAudio capture and KWS.

Moves only DigitalHumanWake's recording stream to a temporary test monitor,
restores it in finally, and never changes the system default audio devices.
Close the normal single-instance Unity client before running this script.
"""
import json
import sys
import os
from pathlib import Path
import subprocess
import threading
import time
from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT/'artifacts/validation/offline-wake'

def pactl(*args):
    return subprocess.check_output(['pactl', *map(str, args)], text=True).strip()

def main():
    FOLDER.mkdir(parents=True, exist_ok=True)
    report_path=FOLDER/'unity-runtime.json'
    report_path.unlink(missing_ok=True)
    streams=json.loads(pactl('--format=json','list','source-outputs'))
    stream=next(s for s in streams if s['properties'].get('application.name')=='DigitalHumanWake')
    module=None;client=None;events=[];done=threading.Event()
    def observe():
        with connect('ws://127.0.0.1:9881/ws/wake') as ws:
            while not done.is_set():
                try: event=json.loads(ws.recv(timeout=1))
                except TimeoutError: continue
                if event.get('type')!='level':events.append({'elapsed':round(time.monotonic()-began,3),**event})
    began=time.monotonic();reader=threading.Thread(target=observe,daemon=True);reader.start()
    try:
        module=pactl('load-module','module-null-sink','sink_name=human_wake_test','rate=16000','channels=1')
        pactl('move-source-output',stream['index'],'human_wake_test.monitor')
        env={**os.environ,'DISPLAY':':1','XDG_RUNTIME_DIR':'/run/user/1000',
             '__NV_PRIME_RENDER_OFFLOAD':'1','__GLX_VENDOR_LIBRARY_NAME':'nvidia'}
        with (ROOT/'logs/wake-unity-launch.log').open('w') as out:
            client=subprocess.Popen([str(ROOT/'build/LocalDigitalHuman.x86_64'),'-screen-width','1280','-screen-height','720',
                '-screen-fullscreen','0','-avatar','man','-offline-wake-self-test',
                *(['-automatic-capture-test'] if '--automatic' in sys.argv else []),
                '-logFile',str(ROOT/'logs/wake-unity-runtime.log')],cwd=ROOT,env=env,stdout=out,stderr=out)
        sent=False;deadline=time.monotonic()+230
        while client.poll() is None and time.monotonic()<deadline:
            if not sent and report_path.exists():
                try: report=json.loads(report_path.read_text())
                except ValueError: report={}
                if report.get('stage')=='awaiting_real_audio':
                    subprocess.run(['paplay','--device=human_wake_test',str(FOLDER/'wake-command.wav')],check=True)
                    sent=True
            time.sleep(.15)
        if client.poll() is None:raise TimeoutError('Unity integration exceeded 230 seconds')
        report=json.loads(report_path.read_text());print(json.dumps(report,ensure_ascii=False,indent=2))
        if not report['passed']:raise RuntimeError('Unity wake integration failed')
    finally:
        if client and client.poll() is None:client.terminate();client.wait(timeout=10)
        try:pactl('move-source-output',stream['index'],stream['source'])
        finally:
            if module:pactl('unload-module',module)
        done.set();reader.join(timeout=3)
        (FOLDER/'websocket-events.json').write_text(json.dumps(events,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
