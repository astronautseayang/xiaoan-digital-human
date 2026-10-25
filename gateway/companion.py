"""Shared senior companion wording and a persistent, explicit form of address."""
import json
import logging
import re
import uuid

SALUTATIONS = ('您', '爷爷', '奶奶')
log = logging.getLogger('human.companion')


def salutation_for(root):
    path = root / 'config/companion.json'
    try:
        settings = json.loads(path.read_text())
        if not isinstance(settings, dict):
            raise ValueError('Expected companion settings object')
        value = settings.get('salutation', '您')
    except FileNotFoundError:
        return '您'
    except (OSError, ValueError):
        log.warning('Invalid companion settings; using neutral address', exc_info=True)
        return '您'
    return value if value in SALUTATIONS else '您'


def save_salutation(root, value):
    path = root / 'config/companion.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.' + uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps({'salutation': value}, ensure_ascii=False, indent=2) + '\n')
        temporary.replace(path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            log.warning('Could not remove temporary companion settings %s', temporary, exc_info=True)


def greeting(root, text):
    value = salutation_for(root)
    return (value + '，' if value != '您' else '') + text


def respectful_reply(text, value):
    # Repair direct infantile addresses while preserving discussion about children.
    address = value if value in ('爷爷', '奶奶') else '您'
    text = re.sub(r'(^|[。！？!?，,\n])([ \t]*)(?:好孩子|乖孩子|小朋友|小宝贝|宝贝|乖宝宝|宝宝|爷爷|奶奶)(?=[，,。！!？?呀啊哦乖]|$)',
                  lambda m: m[1] + m[2] + address, text)
    text = re.sub(r'(?:你真是|您真是|你是|您是)(?:一个|个)?(?:好孩子|乖孩子)', '您很用心', text)
    # A greeting followed by a standalone neutral address reads unnaturally
    # (including after replacing an unselected family address above).
    text = re.sub(r'^([ \t]*)(?:你好|您好)[，, \t]*您(?=[，,。！!？?呀啊哦]|$)',
                  lambda m: m[1] + '您好', text)
    return text


def address_reply(text, value):
    text = respectful_reply(text, value)
    if value == '您' or not text.strip():
        return text
    text = text.lstrip(' \n\t“"「')
    # Move a greeting's existing address to the front instead of prefixing
    # a second one. Require an address boundary to preserve family topics.
    text = re.sub(r'^(?:你好|您好)[，, \t]*(?:爷爷|奶奶)(?=[，,。！!？?]|$)',
                  value + '，您好', text, count=1)
    # Apply the explicitly selected address even if the small local LLM omits it.
    if re.match(r'^(爷爷|奶奶)', text):
        return re.sub(r'^(爷爷|奶奶)', value, text, count=1)
    return value + '，' + text


def system_prompt(root, salutation=None):
    value = salutation if salutation is not None else salutation_for(root)
    address = (f'用户已选择称呼“{value}”。在回答开头自然地叫一声“{value}”，较长对话中适当再次使用，'
               '不要每句话都重复称呼。' if value != '您' else
               '用户尚未选择爷爷或奶奶的称呼，使用“您”尊称，不猜测性别，也不交替叫爷爷奶奶。')
    return ('你是面向银发老人的中文数字人陪伴助手小安，耐心、亲切、尊重对方的自主选择。' + address +
            '身份关系固定：用户是长辈，你是陪伴助手小安。用户说我、我的指长辈自己；你、你的通常指小安。'
            '称呼用户时禁止使用好孩子、乖孩子、小朋友、宝宝、宝贝等幼儿称呼，不混淆长辈与晚辈。'
            '像家人一样平等交流，不使用幼儿口吻，不说教，不居高临下。'
            '用户说已按医嘱服药时，简短确认即可，不夸奖真棒、不假定病情好转。'
            '历史回答可能存在错误称呼或事实，不能延续错误；以当前身份设置和用户最新说明为准。'
            '结合最近对话理解省略和指代，如那、这个、刚才说的、继续；用户补充或纠正时更新理解，避免重复问已明确的信息。'
            '用户换话题时跟随新话题，不强行带回旧话题；有多个可能指代时简短询问，不猜测或虚构记忆。'
            '没有真实工具执行结果，不得声称已设置、修改、取消提醒或已保存备忘。'
            '你没有身体，不能端茶、拿药或完成现实中的动作；只能提供对话和已接入的提醒功能。'
            '天气和定位问题由真实查询工具处理；未提供查询结果时，不猜测实时天气或所在城市。其他实时信息没有工具时，应说明无法确认。'
            '用户只纠正称呼时，应确认称呼，不附加吃药等无关指令。'
            '不猜测实时天气、时间和用户经历；不确定就说明，答非所问时先确认。'
            '先理解老人刚才说的话，再用一句短句直接回应，按需要补充。'
            '语音识别的内容不清楚时温和问一句确认，不编造老人没有说过的意思。'
            '使用简体中文和常用词，句子短，每次先说一两件事；复杂问题可完整解释，不输出Markdown格式。'
            '回答只用中文，不夹杂英文单词或英文句子，英文名称尽量使用通行中文译名，不突然切换语言。'
            '不虚构已联系家属、医生或救护车，不擅自诊断或调整药物剂量。'
            '用户问吃过药是否再吃时，说明不要重复服同一剂，下一次按医嘱的时间和剂量服用；'
            '不清楚药名、剂量和时间时请其核对药盒、医嘱或询问医生药师，不笼统断言以后不需要服药。')
