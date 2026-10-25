"""Bounded, process-local reuse of successfully processed speech."""
from collections import OrderedDict
import hashlib
import json
from pathlib import Path
import time


def speech_key(text, language, voice):
    reference = hashlib.sha256(Path(voice['ref_audio_path']).read_bytes()).hexdigest()
    return hashlib.sha256(json.dumps(
        [text, language, voice, reference], ensure_ascii=False, sort_keys=True,
    ).encode()).hexdigest()


class SpeechCache:
    def __init__(self, max_entries=32, max_bytes=32 * 1024 * 1024, ttl=600, clock=time.monotonic):
        self.max_entries, self.max_bytes, self.ttl = max_entries, max_bytes, ttl
        self.clock = clock
        self.entries = OrderedDict()
        self.size = 0

    def _remove(self, key):
        _, data = self.entries.pop(key)
        self.size -= len(data)

    def _expire(self):
        now = self.clock()
        for key, (expires, _) in list(self.entries.items()):
            if expires <= now:
                self._remove(key)

    def get(self, key):
        self._expire()
        entry = self.entries.get(key)
        if entry is None:
            return None
        self.entries.move_to_end(key)
        return entry[1]

    def put(self, key, data):
        self._expire()
        if key in self.entries:
            self._remove(key)
        if len(data) > self.max_bytes or self.max_entries < 1:
            return
        self.entries[key] = (self.clock() + self.ttl, data)
        self.size += len(data)
        while len(self.entries) > self.max_entries or self.size > self.max_bytes:
            self._remove(next(iter(self.entries)))
