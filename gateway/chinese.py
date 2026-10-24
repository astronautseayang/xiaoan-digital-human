"""Simplified text and local pinyin candidates, scoped to the avatar UI."""
import ctypes as c
from functools import lru_cache
import re
from threading import Lock
from opencc import OpenCC

_converter = OpenCC('t2s')

def simplified(text):
    return _converter.convert(text)

class Pinyin:
    def __init__(self):
        self.lib = c.CDLL('libpinyin.so.13')
        self.glib = c.CDLL('libglib-2.0.so.0')
        self.glib.g_free.argtypes = [c.c_void_p]
        p, s, b = c.c_void_p, c.c_char_p, c.c_bool
        declarations = {
            'init': ([s, s], p), 'alloc_instance': ([p], p),
            'free_instance': ([p], None), 'reset': ([p], b),
            'parse_more_full_pinyins': ([p, s], c.c_size_t),
            'guess_sentence': ([p], b),
            'guess_candidates': ([p, c.c_size_t, c.c_int], b),
            'get_n_candidate': ([p, c.POINTER(c.c_uint)], b),
            'get_candidate': ([p, c.c_uint, c.POINTER(p)], b),
            'choose_candidate': ([p, c.c_size_t, p], c.c_int),
            'get_sentence': ([p, c.c_ubyte, c.POINTER(p)], b),
        }
        for name, (args, result) in declarations.items():
            fn = getattr(self.lib, 'pinyin_' + name)
            fn.argtypes, fn.restype = args, result
            setattr(self, name, fn)
        self.context = self.init(b'/usr/lib/x86_64-linux-gnu/libpinyin/data', None)
        if not self.context:
            raise RuntimeError('本地拼音词库未就绪')
        self.lock = Lock()

    @lru_cache(maxsize=256)
    def candidates(self, spelling):
        if not re.fullmatch(r"[a-z']{1,64}", spelling):
            return []
        with self.lock:
            instance = self.alloc_instance(self.context)
            try:
                result = []
                for index in range(24):
                    self.reset(instance)
                    parsed = self.parse_more_full_pinyins(instance, spelling.encode())
                    if parsed != len(spelling):
                        break
                    self.guess_sentence(instance)
                    if index:
                        self.guess_candidates(instance, 0, 0)
                        count = c.c_uint()
                        self.get_n_candidate(instance, c.byref(count))
                        if index - 1 >= count.value:
                            break
                        candidate = c.c_void_p()
                        self.get_candidate(instance, index - 1, c.byref(candidate))
                        self.choose_candidate(instance, 0, candidate)
                        self.guess_sentence(instance)
                    sentence = c.c_void_p()
                    if self.get_sentence(instance, 0, c.byref(sentence)) and sentence.value:
                        text = simplified(c.string_at(sentence).decode())
                        self.glib.g_free(sentence)
                        if text and text not in result:
                            result.append(text)
                return result
            finally:
                self.free_instance(instance)

@lru_cache(maxsize=1)
def pinyin_engine():
    return Pinyin()
