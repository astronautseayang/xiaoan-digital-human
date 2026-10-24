#!/usr/bin/env python3
"""Run a local WAV or raw 16k/16-bit/mono PCM through the real ASR endpoint."""
import argparse
import json
import re
from pathlib import Path
import httpx
parser=argparse.ArgumentParser()
parser.add_argument('audio',type=Path)
parser.add_argument('--expected',help='Reference transcript for character error rate')
parser.add_argument('--url',default='http://127.0.0.1:9881')
args=parser.parse_args()
with httpx.Client(trust_env=False,timeout=180) as client:
    response=client.post(args.url+'/api/asr?care_commands=false',files={'file':(args.audio.name,args.audio.read_bytes(),'audio/pcm' if args.audio.suffix=='.pcm' else 'audio/wav')})
    response.raise_for_status();result=response.json()
# Does not submit a chat or execute reminders; care_commands=False bypasses
# enrolled-speaker checks, preserving a faithful transcript for comparison.
if args.expected:
    def normalized(text):return re.sub(r'[^\u4e00-\u9fffA-Za-z0-9]','',text)
    expected=normalized(args.expected);actual=normalized(result['text'])
    previous=list(range(len(actual)+1))
    for i,a in enumerate(expected,1):
        current=[i]
        for j,b in enumerate(actual,1):
            current.append(min(current[-1]+1,previous[j]+1,previous[j-1]+(a!=b)))
        previous=current
    result['expected']=args.expected
    result['character_error_rate']=previous[-1]/max(1,len(expected))
print(json.dumps(result,ensure_ascii=False,indent=2))
