"""Resolve short follow-ups from the last completed turn, without global state."""
from dataclasses import dataclass
import re
from gateway.input_logic import interpret, city_candidates

TIME = r'(?:今天|明天|后天|每天)?(?:上午|下午|晚上|中午|早上)?[零〇一二两三四五六七八九十百\d]+(?:分钟后|小时后|[点:：](?:[零〇一二两三四五六七八九十\d]+分?|半)?)(?:的时候)?'

@dataclass(frozen=True)
class ContextInput:
    text: str
    reply: str = ''
    replace_id: str | None = None
    reminder_ref: tuple[str, str] | None = None
    cancel: bool = False


def resolve(text, history=()):
    value = re.sub(r'\s+', '',text).strip('。！？?!，,')
    short = re.sub(r'^(?:小安[，,]*|请|麻烦你|帮我)+','',value)
    # Use the immediately preceding complete pair only. A topic change therefore
    # invalidates old operational references; no shared state across clients.
    if len(history)<2 or history[-1].role!='assistant' or history[-2].role!='user':
        if re.fullmatch(r'(?:那)?(?:明天|后天)呢|(?:改成|换成).+|取消(?:这个|刚才的)提醒',short):
            return ContextInput(text,'请告诉我您接着说的是哪个城市的天气，或哪一条提醒。')
        return ContextInput(text)
    user = interpret(history[-2].content).text
    answer = history[-1].content

    # Resolve a previous city clarification only to one of the offered names.
    if ('城市名听起来有多个可能' in answer or '您要查询哪个城市的天气' in answer):
        city = re.sub(r'^(?:是|我要|选|选择)','',short).removesuffix('市')
        if city in city_candidates(city) and city in answer:
            if '城市名听起来' in answer:
                return ContextInput('定位到'+city)
            day = '后天' if '后天' in user else '明天' if '明天' in user else '今天'
            return ContextInput(city+day+'天气')
        if len(short)<=8:
            return ContextInput(text,'请从刚才列出的城市中选择，并说出或输入准确城市名。')

    key = re.search(r'编号([0-9a-f]{8})',answer)
    reference = re.search(r'已(?:设置|修改)提醒：(.+?)，提醒您(.+?)。',answer)
    reminder = '提醒' in user or '提醒' in answer
    if reminder:
        change = re.fullmatch(r'(?:把(?:这个|刚才的)?提醒)?(?:改成|改为|改到|换成|换到)('+TIME+r')',short)
        cancel = re.fullmatch(r'(?:取消|删除)(?:这个|刚才的|刚刚的|上一个)提醒',short)
        if change or cancel:
            if reference:
                return ContextInput(change[1] if change else '', reminder_ref=(reference[1],reference[2]), cancel=bool(cancel))
            if not key:
                return ContextInput(text,'还不能确定您要修改哪一条提醒。请先说“查看提醒”，再说明提醒的时间和事项。')
            if cancel:
                return ContextInput('取消提醒'+key[1])
            return ContextInput(change[1],replace_id=key[1])
        # Fill a missing time or task only when the previous parser requested it.
        if '还没有设置提醒' in answer and '提醒我' in user:
            if '具体时间' in answer and re.fullmatch(TIME,short):
                task = user.split('提醒我',1)[1]
                if task:
                    return ContextInput(short+'提醒我'+task)
            if '提醒您做什么' in answer and 1<=len(short)<=30 and not re.search(r'不要|取消|天气|定位|改成|吗|呢|[，,。！？]',short):
                return ContextInput(user+short)

    # Factual replies provide the city and day used by the tool, including
    # temporary cross-city queries that do not change the saved home location.
    city = re.search(r'([\u4e00-\u9fff]{2,12})(?:目前|(?:今天|明天|后天)（)',answer) if '来源为开放气象' in answer else None
    located = re.search(r'已将天气位置设置为([\u4e00-\u9fff]{2,12})。',answer)
    if city or located:
        name = re.sub(r'^(?:爷爷|奶奶|您)[，,]?','',(city or located)[1])
        # Assistant salutation is normally separated by punctuation, so the
        # name capture starts after it. Retain explicit city from the tool.
        day = '后天' if re.search(r'后天（',answer) else '明天' if re.search(r'明天（',answer) else '今天'
        next_day = re.fullmatch(r'(?:那|那么)?(今天|明天|后天)(?:呢|的呢|怎么样|天气呢|天气怎么样)?',short)
        rain = re.fullmatch(r'(?:那|那么)?(?:要不要|需要|需不需要|要)?带伞(?:吗|呢)?|(?:那)?会(?:不会)?下雨(?:吗|呢)?',short)
        if next_day:
            return ContextInput(name+next_day[1]+'天气')
        if rain:
            return ContextInput(name+day+'天气')
        other = re.fullmatch(r'(?:那|那么)?(?:换成|换到|改成|改为)?([\u4e00-\u9fff]{2,6}?)(?:呢|吧)?',short)
        if other:
            candidates = city_candidates(other[1])
            if len(candidates)==1:
                if located and re.match(r'(?:换成|换到|改成|改为)',short):
                    return ContextInput('定位到'+candidates[0])
                return ContextInput(candidates[0]+day+'天气')
            if len(candidates)>1:
                return ContextInput(text,('城市名听起来有多个可能：' if located else '您要查询哪个城市的天气：')+'、'.join(candidates)+'。请说出准确城市名。')
    if re.fullmatch(r'(?:改成|改为|改到|换成)('+TIME+r')',short):
        return ContextInput(text,'请先告诉我您要修改哪一条提醒，可以说“查看提醒”。')
    if re.fullmatch(r'(?:那|那么)?(?:今天|明天|后天)呢',short):
        return ContextInput(text,'您想继续问哪个城市的天气，还是其他事情？')
    return ContextInput(text)
