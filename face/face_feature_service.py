"""POST raw PNG/JPEG /features; GET /latest or /health. Loopback only, serial inference."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
from face_feature_pipeline import MAX_BYTES, extract, save
OUTPUT=Path('/home/yyy/digital-human/artifacts/face/latest.json')
class Handler(BaseHTTPRequestHandler):
    def send_json(self,status,data):
        payload=json.dumps(data,ensure_ascii=False,allow_nan=False).encode()
        self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(payload))); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(payload)
    def do_GET(self):
        if self.path=='/revision': return self.send_json(200,dict(revision=str(OUTPUT.stat().st_mtime_ns) if OUTPUT.exists() else ''))
        if self.path=='/health': return self.send_json(200,dict(ready=True,schemaVersion=1))
        if self.path=='/latest' and OUTPUT.exists(): return self.send_json(200,json.loads(OUTPUT.read_text()))
        self.send_json(404,dict(error='Unknown endpoint or no processed photo'))
    def do_POST(self):
        if self.path!='/features': return self.send_json(404,dict(error='Unknown endpoint'))
        try:
            length=int(self.headers.get('Content-Length',0))
            if not 0<length<=MAX_BYTES: return self.send_json(413,dict(error='Photo must be <=16 MiB'))
            self.connection.settimeout(30); packet=extract(self.rfile.read(length)); save(packet,OUTPUT); self.send_json(200,packet)
        except (ValueError,OSError) as exc: self.send_json(422,dict(error=str(exc)))
if __name__=='__main__': HTTPServer(('127.0.0.1',9882),Handler).serve_forever()
