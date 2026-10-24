#!/usr/bin/env python3
"""Configure a local 5-10 second reference recording and its exact transcript."""
import argparse,json,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('audio');p.add_argument('--text',required=True);p.add_argument('--lang',default='zh',choices=['zh','en','ja','ko','yue']);a=p.parse_args()
root=Path('/home/yyy/digital-human');audio=Path(a.audio).expanduser().resolve()
if not audio.is_file():p.error('Audio file not found')
r=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','json',str(audio)],capture_output=True,text=True,check=True)
duration=float(json.loads(r.stdout)['format']['duration'])
if not 5<=duration<=10:p.error(f'Reference must be 5-10 seconds; got {duration:.3f}s')
cfg={'ref_audio_path':str(audio),'prompt_lang':a.lang,'prompt_text':a.text}
(root/'config/voice.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2))
print('Updated config/voice.json',duration,'seconds')
