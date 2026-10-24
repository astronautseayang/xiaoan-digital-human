"""Type real pinyin keys and paste traditional text into the Unity-only input."""
import ctypes as c
import json
import os
import re
from pathlib import Path
import subprocess
import time
os.environ['DISPLAY']=':1'
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk
ROOT=Path('/home/yyy/digital-human')
FOLDER=ROOT/'artifacts/validation/chinese-input'
FOLDER.mkdir(parents=True,exist_ok=True)
report=FOLDER/'runtime.json'
report.unlink(missing_ok=True)
x=c.CDLL('libX11.so.6');xt=c.CDLL('libXtst.so.6')
x.XOpenDisplay.restype=c.c_void_p;x.XOpenDisplay.argtypes=[c.c_char_p]
d=x.XOpenDisplay(b':1')
x.XFlush.argtypes=[c.c_void_p]
x.XKeysymToKeycode.argtypes=[c.c_void_p,c.c_ulong];x.XKeysymToKeycode.restype=c.c_uint
xt.XTestFakeKeyEvent.argtypes=[c.c_void_p,c.c_uint,c.c_int,c.c_ulong]
def pump(seconds):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  while Gtk.events_pending():Gtk.main_iteration_do(False)
  time.sleep(.01)
def key(symbol,pressed):
 xt.XTestFakeKeyEvent(d,x.XKeysymToKeycode(d,symbol),pressed,0);x.XFlush(d)
def tap(symbol):key(symbol,1);pump(.04);key(symbol,0);pump(.05)
def type_pinyin(text,commit):
 for char in text:tap(ord(char))
 pump(.8);tap(commit);pump(.4)
env={**os.environ,'XDG_RUNTIME_DIR':'/run/user/1000','__NV_PRIME_RENDER_OFFLOAD':'1','__GLX_VENDOR_LIBRARY_NAME':'nvidia'}
with (ROOT/'logs/chinese-input-launch.log').open('w') as output:
 client=subprocess.Popen([str(ROOT/'build/LocalDigitalHuman.x86_64'),'-screen-width','1280','-screen-height','720','-screen-fullscreen','0','-chinese-input-self-test','-logFile',str(ROOT/'logs/chinese-input-runtime.log')],cwd=ROOT,env=env,stdout=output,stderr=output)
try:
 deadline=time.monotonic()+80
 while time.monotonic()<deadline:
  if client.poll() is not None:raise RuntimeError('Client exited before input')
  if report.exists() and json.loads(report.read_text()).get('stage')=='awaiting_keyboard':break
  pump(.1)
 else:raise TimeoutError('Input not ready')
 # XTest sends keys to the desktop focus; explicitly focus this client's window.
 tree=subprocess.check_output(['xwininfo','-root','-tree'],text=True)
 for window in re.findall(r'^\s*(0x[0-9a-f]+) ',tree,re.M):
  props=subprocess.run(['xprop','-id',window,'_NET_WM_PID'],capture_output=True,text=True).stdout
  if re.search(r'=\s*'+str(client.pid)+r'\s*$',props):
   x.XRaiseWindow.argtypes=[c.c_void_p,c.c_ulong]
   x.XSetInputFocus.argtypes=[c.c_void_p,c.c_ulong,c.c_int,c.c_ulong]
   x.XRaiseWindow(d,int(window,16));x.XSetInputFocus(d,int(window,16),2,0);x.XFlush(d)
   pump(.4)
   break
 else:raise RuntimeError('Unity window not found for keyboard focus')
 # Enter confirms a candidate and must never submit an uncommitted composition.
 type_pinyin('nihao',0xff0d)
 type_pinyin('yeye',0x20)
 clipboard=Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
 clipboard.set_text('今天天氣很好。',-1);pump(.2)
 key(0xffe3,1);tap(ord('v'));key(0xffe3,0)
 while client.poll() is None and time.monotonic()<deadline:pump(.1)
 result=json.loads(report.read_text())
 tree=subprocess.check_output(['xwininfo','-root','-tree'],text=True)
 assert '数字人中文输入' not in tree,'External input dialog opened'
 assert result['passed'],result
 print(json.dumps(result,ensure_ascii=False,indent=2))
finally:
 if client.poll() is None:client.terminate();client.wait(timeout=10)
