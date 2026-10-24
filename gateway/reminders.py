"""Parse explicit reminder requests locally; only confirm committed schedules."""
from datetime import datetime, timedelta
import re
import uuid

NUMBER = r'[0-9零〇一二两三四五六七八九十百]+'


def number(value):
    if value.isdigit():
        return int(value)
    digits = dict(zip('零〇一二两三四五六七八九', [0, 0, 1, 2, 2, 3, 4, 5, 6, 7, 8, 9]))
    if '十' in value:
        left, right = value.split('十', 1)
        if (left and left not in digits) or (right and right not in digits):
            raise ValueError('Invalid Chinese number')
        return (digits[left] if left else 1) * 10 + (digits[right] if right else 0)
    return int(''.join(str(digits[c]) for c in value))


def initialize(db):
    db.execute('''CREATE TABLE IF NOT EXISTS reminders (
        id TEXT PRIMARY KEY, task TEXT NOT NULL, due TEXT NOT NULL,
        daily INTEGER NOT NULL DEFAULT 0, state TEXT NOT NULL DEFAULT 'scheduled')''')
    db.commit()


def command(engine, text, now=None, replace_id=None):
    now = (now or datetime.now(engine.zone)).astimezone(engine.zone)
    value = re.sub(r'\s+', '', text).strip('。！？!?')
    listing = re.fullmatch(r'(?:查看|看看|查询|列出|我有|有哪些|查看我的|我的)(?:一下|哪些|什么)?(?:备忘|提醒)(?:事项|任务)?(?:有哪些|列表)?', value)
    if listing:
        rows = engine.db.execute("SELECT * FROM reminders WHERE state='scheduled' ORDER BY due, id").fetchall()
        return '目前没有待办提醒。' if not rows else '您已设置的提醒：' + '；'.join(
            f"{'每天' if r['daily'] else r['due'][:10] + ' '}{r['due'][11:16]}，{r['task']}" for r in rows) + '。'
    ordinal = re.fullmatch(rf'(?:取消|删除)第({NUMBER})(?:个|条)提醒', value)
    if ordinal:
        try:
            index = number(ordinal[1])-1
        except (ValueError, KeyError):
            return '请先查看提醒，再告诉我要取消第几个。'
        rows = engine.db.execute("SELECT id FROM reminders WHERE state='scheduled' ORDER BY due, id").fetchall()
        if not 0 <= index < len(rows):
            return '没有找到这条提醒，请先说“查看提醒”。'
        with engine.db:
            engine.db.execute("UPDATE reminders SET state='cancelled' WHERE id=?", (rows[index]['id'],))
        return '已取消这条提醒。'
    cancel_task = re.fullmatch(r'(?:取消|删除)(.+?)(?:的)?提醒', value)
    cancel = re.fullmatch(r'(?:取消|删除)(?:全部|所有)?(?:的)?(?:备忘|提醒)(?:事项|任务)?(?:[：:]?(.+))?', value)
    if not cancel and cancel_task and cancel_task[1] not in ('全部', '所有'):
        value = '取消提醒' + cancel_task[1].removesuffix('的')
        cancel = re.fullmatch(r'取消提醒(.+)', value)
    if cancel:
        target = cancel.group(1)
        rows = engine.db.execute("SELECT * FROM reminders WHERE state='scheduled'").fetchall()
        matches = [r for r in rows if target and (r['id'].startswith(target) or r['task'] == target)]
        if not target and ('全部' in value or '所有' in value):
            matches = rows
        if not matches:
            return '没有找到对应提醒。可以说“查看提醒”，再说“取消喝水提醒”或“取消第一个提醒”；取消全部请说“取消全部提醒”。'
        if len(matches) > 1 and target:
            return '有多个同名提醒，请查看提醒后说明取消第几个提醒。'
        with engine.db:
            engine.db.executemany("UPDATE reminders SET state='cancelled' WHERE id=?", [(r['id'],) for r in matches])
        return f'已取消{len(matches)}条提醒。'
    if '提醒我' not in value:
        # Unsupported changes must never be handed to a model that could claim success.
        if re.search(r'(修改|更改|调整|取消|删除|设置|添加|创建).*(提醒|备忘)', value):
            return '请说清提醒时间和事情，例如“明天上午八点提醒我吃药”。修改时间请先取消原提醒，再重新设置。'
        return None
    if re.search(r'(不要|不用|别|不必|取消|能不能|能否|可以|如何|怎么|如果|假如)', value):
        return '设置提醒时，请直接告诉我时间和事情，例如“今天下午三点提醒我喝水”。如需取消，请说“查看提醒”后说明取消第几个提醒。'
    if value.count('提醒我') > 1 or len(re.findall(rf'{NUMBER}[点时:：]', value)) > 1:
        return '还没有设置提醒。请一次告诉我一个明确的时间和事项，多条提醒可以分别设置。'
    # Both “今天12点52的时候提醒我吃药” and “提醒我今天12:52吃药”.
    before, after = value.split('提醒我', 1)
    # Polite prefixes and assistant names are not time expressions. Search the
    # side containing a time, so “小安，请提醒我一分钟后喝水” works too.
    time_pattern = rf'{NUMBER}(?:分钟|小时)(?:以后|之后|后)|{NUMBER}[点时:：]'
    time_before = re.search(time_pattern, before)
    time_after = re.search(time_pattern, after)
    if time_before and time_after:
        return '还没有设置提醒。请一次告诉我一个明确的时间和事项，多条提醒可以分别设置。'
    source_before = bool(time_before)
    source = before if source_before else after
    try:
        relative = re.search(rf'({NUMBER})(分钟|小时)(?:以后|之后|后)', source)
        clock = re.search(rf'({NUMBER})[点时:：](?:(半|一刻|三刻)|({NUMBER})(?:分)?)?', source)
        if relative:
            count = number(relative[1])
            if count <= 0 or count > 10000:
                raise ValueError()
            due = now + timedelta(**({'minutes': count} if relative[2] == '分钟' else {'hours': count}))
            match = relative
        elif clock:
            hour, minute = number(clock[1]), number(clock[3]) if clock[3] else 0
            if clock[2]:
                minute = {'半': 30, '一刻': 15, '三刻': 45}[clock[2]]
            if re.search(r'下午|晚上|傍晚', source) and 1 <= hour < 12:
                hour += 12
            if '凌晨' in source and hour == 12:
                hour = 0
            if '中午' in source and 1 <= hour <= 2:
                hour += 12
            due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            days = 2 if '后天' in source else 1 if '明天' in source else 0
            due += timedelta(days=days)
            if due <= now and ('每天' in source or not re.search(r'今天|明天|后天', source)):
                due += timedelta(days=1)
            match = clock
        else:
            return '还没有设置提醒。请告诉我具体时间，例如“今天下午三点提醒我吃药”。'
        if due <= now:
            return f'今天{due:%H:%M}已经过了，没有设置提醒。请确认新的时间，例如“明天{due:%H:%M}提醒我吃药”。'
        if re.search(r'每周|每月|周[一二三四五六日天]|星期|月|年|[号日]|下周|工作日|每隔|秒', source) or (relative and '每天' in source):
            return '目前支持今天、明天、后天、每天，或几分钟后提醒。请用这些时间重新设置。'
        task = after if source_before else after[match.end():]
        task = re.sub(r'^(?:的时候|时候|时|再|要|我|请)+', '', task).strip('，,。 ')
        if not task or len(task) > 200:
            return '还没有设置提醒。请告诉我要提醒您做什么。'
        daily = '每天' in source
        due_text = due.isoformat(timespec='seconds')
        existing = engine.db.execute("SELECT id FROM reminders WHERE task=? AND due=? AND daily=? AND state='scheduled'", (task, due_text, int(daily))).fetchone()
        key = existing['id'] if existing else uuid.uuid4().hex
        with engine.db:
            if replace_id:
                target = engine.db.execute("SELECT id FROM reminders WHERE id=? AND state='scheduled'", (replace_id,)).fetchone()
                if not target:
                    return '原提醒已失效，尚未修改。请说“查看提醒”确认。'
                if key != replace_id:
                    engine.db.execute("UPDATE reminders SET state='cancelled' WHERE id=?", (replace_id,))
            if not existing:
                engine.db.execute('INSERT INTO reminders(id,task,due,daily) VALUES(?,?,?,?)', (key, task, due_text, int(daily)))
        when = '每天' + due.strftime('%H:%M') if daily else due.strftime('%Y年%m月%d日 %H:%M')
        return f"{'已修改提醒' if replace_id else '已设置提醒'}：{when}，提醒您{task}。"
    except (ValueError, KeyError):
        return '时间格式不正确，还没有设置提醒。请使用零到二十三点、零到五十九分，例如“今天12点52分提醒我吃药”。'


def reference_id(engine, when, task):
    rows = engine.db.execute("SELECT * FROM reminders WHERE task=? AND state='scheduled'", (task,)).fetchall()
    matches=[]
    for row in rows:
        due=datetime.fromisoformat(row['due'])
        label='每天'+due.strftime('%H:%M') if row['daily'] else due.strftime('%Y年%m月%d日 %H:%M')
        if label==when:matches.append(row['id'])
    return matches[0] if len(matches)==1 else None


def tick(engine, now):
    for row in engine.db.execute("SELECT * FROM reminders WHERE state='scheduled' AND due<=?", (now.isoformat(timespec='seconds'),)).fetchall():
        due = datetime.fromisoformat(row['due'])
        # Atomic event + schedule update; a restart cannot duplicate a dose reminder.
        with engine.db:
            if now - due < timedelta(minutes=2):
                text = f"到提醒时间了，请您{row['task']}。"
                if '药' in row['task']:
                    text += '请核对药盒和医嘱，已经服过请不要重复服药。'
                engine.create('reminder', '备忘提醒', text, 'custom:' + row['id'] + ':' + row['due'], commit=False)
            if row['daily']:
                next_due = due.replace(year=now.year, month=now.month, day=now.day)
                if next_due <= now:
                    next_due += timedelta(days=1)
                engine.db.execute('UPDATE reminders SET due=? WHERE id=?', (next_due.isoformat(timespec='seconds'), row['id']))
            else:
                engine.db.execute('UPDATE reminders SET state=? WHERE id=?', ('fired' if now - due < timedelta(minutes=2) else 'missed', row['id']))
