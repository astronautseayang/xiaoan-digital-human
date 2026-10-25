"""Keep accidental English out of Chinese companion speech and captions."""
import re
from gateway.chinese import simplified

WORDS = {
    'ok': '好的', 'okay': '好的', 'hello': '您好', 'hi': '您好',
    'sorry': '抱歉', 'thanks': '谢谢', 'thank you': '谢谢',
    'bye': '再见', 'goodbye': '再见',
    'deepseek': '深度求索', 'qwen': '千问', 'doubao': '豆包',
    'ai': '人工智能', 'app': '应用', 'wifi': '无线网络',
}


def common_chinese(text):
    text = simplified(text)
    return re.sub(r'(?i)(?<![a-z])(?:' + '|'.join(re.escape(w) for w in sorted(WORDS, key=len, reverse=True)) + r')(?![a-z])',
                  lambda m: WORDS[m[0].lower()], text)


def has_english(text):
    return bool(re.search(r'[A-Za-z]', text))


async def chinese_reply(text, rewrite):
    text = common_chinese(text)
    if not has_english(text):
        return text
    try:
        result = await rewrite(text)
        if not isinstance(result, str):
            raise TypeError('Chinese rewrite must return text')
        result = common_chinese(result.strip())
    except Exception:
        return '这部分我还没能用中文说明清楚，请您换个问法。'
    if not result or has_english(result):
        return '这部分我还没能用中文说明清楚，请您换个问法。'
    return result
