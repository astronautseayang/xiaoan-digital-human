"""Conservative, local correction of command-shaped Chinese input.

Never rewrite arbitrary conversation, negations, reminder times, or task content.
City homophones are resolved only inside an explicit location/weather command.
"""
from dataclasses import dataclass
from functools import lru_cache
import re
from pypinyin import pinyin, Style
from gateway.chinese import simplified

# Common cities, including homophone pairs: ambiguity must not pick by popularity.
CITIES = tuple('''北京 上海 天津 重庆 杭州 宁波 温州 嘉兴 湖州 绍兴 金华 衢州 舟山 台州 丽水
南京 无锡 徐州 常州 苏州 南通 连云港 淮安 盐城 扬州 镇江 泰州 宿迁
合肥 芜湖 蚌埠 淮南 马鞍山 淮北 铜陵 安庆 黄山 滁州 阜阳 宿州 六安 亳州 池州 宣城
福州 厦门 莆田 三明 泉州 漳州 南平 龙岩 宁德
济南 青岛 淄博 枣庄 东营 烟台 潍坊 济宁 泰安 威海 日照 临沂 德州 聊城 滨州 菏泽
广州 深圳 珠海 汕头 佛山 韶关 湛江 肇庆 江门 茂名 惠州 梅州 汕尾 河源 阳江 清远 东莞 中山 潮州 揭阳 云浮
武汉 黄石 十堰 宜昌 襄阳 鄂州 荆门 孝感 荆州 黄冈 咸宁 随州 恩施
长沙 株洲 湘潭 衡阳 邵阳 岳阳 常德 张家界 益阳 郴州 永州 怀化 娄底 湘西
郑州 开封 洛阳 平顶山 安阳 鹤壁 新乡 焦作 濮阳 许昌 漯河 三门峡 南阳 商丘 信阳 周口 驻马店 济源
石家庄 唐山 秦皇岛 邯郸 邢台 保定 张家口 承德 沧州 廊坊 衡水
太原 大同 阳泉 长治 晋城 朔州 晋中 运城 忻州 临汾 吕梁
西安 铜川 宝鸡 咸阳 渭南 延安 汉中 榆林 安康 商洛
成都 自贡 攀枝花 泸州 德阳 绵阳 广元 遂宁 内江 乐山 南充 眉山 宜宾 广安 达州 雅安 巴中 资阳 阿坝 甘孜 凉山
南昌 景德镇 萍乡 九江 新余 鹰潭 赣州 吉安 宜春 抚州 上饶
沈阳 大连 鞍山 抚顺 本溪 丹东 锦州 营口 阜新 辽阳 盘锦 铁岭 朝阳 葫芦岛
长春 吉林 四平 辽源 通化 白山 松原 白城 延边
哈尔滨 齐齐哈尔 鸡西 鹤岗 双鸭山 大庆 伊春 佳木斯 七台河 牡丹江 黑河 绥化 大兴安岭
南宁 柳州 桂林 梧州 北海 防城港 钦州 贵港 玉林 百色 贺州 河池 来宾 崇左
海口 三亚 三沙 儋州 贵阳 六盘水 遵义 安顺 毕节 铜仁 黔西南 黔东南 黔南
昆明 曲靖 玉溪 保山 昭通 丽江 普洱 临沧 楚雄 红河 文山 西双版纳 大理 德宏 怒江 迪庆
兰州 嘉峪关 金昌 白银 天水 武威 张掖 平凉 酒泉 庆阳 定西 陇南 临夏 甘南
银川 石嘴山 吴忠 固原 中卫 西宁 海东 海北 黄南 海南 果洛 玉树 海西
呼和浩特 包头 乌海 赤峰 通辽 鄂尔多斯 呼伦贝尔 巴彦淖尔 乌兰察布 兴安 锡林郭勒 阿拉善
乌鲁木齐 克拉玛依 吐鲁番 哈密 昌吉 博尔塔拉 巴音郭楞 阿克苏 克孜勒苏 喀什 和田 伊犁 塔城 阿勒泰 石河子
拉萨 日喀则 昌都 林芝 山南 那曲 阿里 香港 澳门 台北 高雄 台中 台南 新北 基隆 新竹 嘉义'''.split())

@dataclass(frozen=True)
class Interpretation:
    text: str
    clarification: str = ''

@lru_cache(maxsize=1024)
def sounds(text):
    return tuple(frozenset(pinyin(char, style=Style.NORMAL, heteronym=True)[0]) for char in text)


def city_candidates(value, hotwords=()):
    base = re.sub(r'市$', '', value)
    # Keep correctly spelled city names, even when their pronunciation is shared.
    names = tuple(dict.fromkeys((*CITIES, *(w.removesuffix('市') for w in hotwords if w.endswith('市') and re.fullmatch(r'[\u4e00-\u9fff]{2,12}市',w)))))
    if base in names:
        return [value]
    source = sounds(base)
    return [city for city in names if len(city) == len(base) and
            all(a & b for a, b in zip(source, sounds(city)))]


def interpret(text, hotwords=()):
    original = simplified(text)
    value = re.sub(r'\s+', '', original).strip('。！？?!，,')
    # Only complete affirmative commands. Quoted examples, questions, negations,
    # stories and multi-action utterances do not match this grammar.
    match = re.fullmatch(
        r'(?:小安[，,]*)?(?:请|麻烦你|帮我)?(?:把)?'
        r'(?:定位|定为|订位|订为|定卫|位置|所在城市)'
        r'(?:设置为|切换到|改到|设为|改为|设到|到)'
        r'([\u4e00-\u9fff]{2,12})(?:吧|一下)?', value)
    if match:
        city = match[1]
        # Avoid swallowing conversational qualifiers as part of a place name.
        city = re.sub(r'(?:一下|吧)$', '', city)
        if re.search(r'不要|不用|取消|别|如果|假如|不是|还是|或者|然后|再|吗|呢|怎么|说|提醒',city):
            return Interpretation(original)
        candidates = city_candidates(city, hotwords)
        if len(candidates) > 1:
            return Interpretation(original, '城市名听起来有多个可能：'+'、'.join(candidates)+
                                  '。请用文字输入您要选择的完整城市名。')
        return Interpretation('定位到'+(candidates[0] if candidates else city))
    # Reminder homophones: require both an explicit time and “...我”. Preserve
    # every digit, time unit, negation and task verbatim.
    if re.search(r'[零〇一二两三四五六七八九十百\d]+(?:分钟|小时|点|时|:|：)', value):
        value, count = re.subn(r'(?:提酲|提省|替醒|体醒|题醒)我', '提醒我', value, count=1)
        if not count and '提醒' in hotwords:
            keyword = re.search(r'([\u4e00-\u9fff]{2})我',value)
            if keyword and all(a & b for a,b in zip(sounds(keyword[1]),sounds('提醒'))):
                value=value[:keyword.start()]+'提醒我'+value[keyword.end():]
                count=1
        if count:
            return Interpretation(value)
    # Weather-only city correction. No writes; keep surrounding question intact.
    weather = re.fullmatch(r'((?:今天|明天|后天)?)([\u4e00-\u9fff]{2,6}?)(的?(?:今天|明天|后天)?(?:天气|气温|会下雨|会下雪).*)',value)
    if weather:
        candidates = city_candidates(weather[2], hotwords)
        if len(candidates) == 1:
            return Interpretation(weather[1]+candidates[0]+weather[3])
        if len(candidates) > 1:
            return Interpretation(original,'您要查询哪个城市的天气：'+'、'.join(candidates)+'？请用完整城市名告诉我。')
    return Interpretation(original)


def asr_prompt(city=None):
    # Vocabulary hints, not a transcript to copy. No prompt history across clips.
    names = '杭州、上海、北京、苏州、宁波、广州、深圳'
    if city and re.fullmatch(r'[\u4e00-\u9fff]{2,12}',city):
        names = city+'、'+names
    return ('这是中文日常对话，请按实际声音转写，不补充未说出的内容。'
            '常用词：小安、定位、天气、提醒我、分钟后、喝水、吃药。城市名：'+names+'。')
