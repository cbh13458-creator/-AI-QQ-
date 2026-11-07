#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""群互动统计（QQ 独占）：签到 / 积分榜 / 热词

数据保存在 qq-bot/groupstats.json，与聊天记忆 memory.json 分开，互不影响。

命令行：
    python groups.py stats              查看所有群概况
    python groups.py board <群ID>       查看积分榜
    python groups.py words <群ID>       查看热词
"""
import datetime
import json
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE, "groupstats.json")

# 词频只保留这么多，避免文件无限膨胀
_WORD_KEEP = 400

_STOPWORDS = {
    "的", "了", "是", "我", "你", "他", "她", "它", "们", "在", "有", "和", "就",
    "都", "也", "不", "没", "很", "太", "又", "再", "还", "要", "会", "能", "可以",
    "吗", "啊", "呀", "吧", "呢", "哦", "嗯", "哈", "呵", "唉", "诶", "嘛", "啦",
    "这", "那", "啥", "什么", "怎么", "为什么", "一个", "一下", "一点", "这个",
    "那个", "我们", "你们", "他们", "自己", "现在", "今天", "明天", "昨天",
    "然后", "因为", "所以", "但是", "如果", "就是", "不是", "没有", "知道",
    "觉得", "真的", "好像", "一样", "时候", "东西", "事情", "问题", "感觉",
    "哈哈", "哈哈哈", "哈哈哈", "呵呵", "嘿嘿", "呜呜", "嘤嘤", "啊啊",
    "the", "and", "you", "for", "are", "but", "not", "what", "this", "that",
    "with", "have", "just", "your", "from", "they", "will", "can", "all",
}


def _load():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(data):
    try:
        tmp = DATA_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DATA_FILE)
    except Exception:
        pass


def _group(data, group_id):
    if not group_id:
        group_id = "unknown"
    return data.setdefault(group_id, {
        "members": {},
        "words": {},
        "msgs": 0,
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
    })


def _member(group, member_id, nickname=""):
    member = group["members"].setdefault(member_id or "unknown", {
        "name": "",
        "points": 0,
        "streak": 0,
        "last": "",
        "total": 0,
        "msg": 0,
    })
    if nickname:
        member["name"] = nickname
    return member


def _display_name(member_id, member):
    name = (member.get("name") or "").strip()
    if name:
        return name
    tail = (member_id or "")[-4:]
    return f"群友{tail}" if tail else "群友"


def _tokens(text):
    """把一句话拆成词：中文取整词/二元组，英文取单词。"""
    text = re.sub(r"<@!?\d+>", " ", text or "")
    text = re.sub(r"https?://\S+", " ", text)
    words = []
    for raw in re.findall(r"[A-Za-z][A-Za-z0-9_]{1,15}", text):
        low = raw.lower()
        if low not in _STOPWORDS:
            words.append(low)
    for run in re.findall(r"[\u4e00-\u9fa5]{2,}", text):
        # 短句整体当词，长句拆成二元组/三元组
        if len(run) <= 6:
            if run not in _STOPWORDS:
                words.append(run)
            continue
        for i in range(len(run) - 1):
            bigram = run[i:i + 2]
            if bigram not in _STOPWORDS:
                words.append(bigram)
        for i in range(len(run) - 2):
            trigram = run[i:i + 3]
            if trigram not in _STOPWORDS:
                words.append(trigram)
    return words


def record_activity(group_id, member_id, nickname, text):
    """收到群消息时调用：记活跃度 + 累计热词。"""
    if not group_id:
        return
    data = _load()
    group = _group(data, group_id)
    member = _member(group, member_id, nickname)
    member["msg"] = int(member.get("msg", 0)) + 1
    group["msgs"] = int(group.get("msgs", 0)) + 1

    words = group.setdefault("words", {})
    for word in _tokens(text):
        words[word] = int(words.get(word, 0)) + 1
    if len(words) > _WORD_KEEP:
        top = sorted(words.items(), key=lambda kv: kv[1], reverse=True)[:_WORD_KEEP]
        group["words"] = dict(top)
    _save(data)


def checkin(group_id, member_id, nickname=""):
    """每日签到。返回 dict：ok / points_added / streak / total / rank / already。"""
    data = _load()
    group = _group(data, group_id)
    member = _member(group, member_id, nickname)

    today = datetime.date.today()
    today_str = today.isoformat()
    yesterday_str = (today - datetime.timedelta(days=1)).isoformat()

    if member.get("last") == today_str:
        return {
            "ok": False,
            "already": True,
            "streak": int(member.get("streak", 0)),
            "total": int(member.get("points", 0)),
            "rank": _rank(group, member_id),
            "members": len(group["members"]),
        }

    if member.get("last") == yesterday_str:
        member["streak"] = int(member.get("streak", 0)) + 1
    else:
        member["streak"] = 1

    streak = int(member["streak"])
    points_added = 10 + min(streak - 1, 5) * 2
    member["points"] = int(member.get("points", 0)) + points_added
    member["total"] = int(member.get("total", 0)) + 1
    member["last"] = today_str
    _save(data)

    return {
        "ok": True,
        "already": False,
        "points_added": points_added,
        "streak": streak,
        "total": member["points"],
        "rank": _rank(group, member_id),
        "members": len(group["members"]),
    }


def _rank(group, member_id):
    rows = sorted(group.get("members", {}).items(),
                  key=lambda kv: int(kv[1].get("points", 0)), reverse=True)
    for index, (mid, _member_info) in enumerate(rows, 1):
        if mid == member_id:
            return index
    return len(rows)


def profile(group_id, member_id):
    data = _load()
    group = _group(data, group_id)
    member = _member(group, member_id)
    return {
        "points": int(member.get("points", 0)),
        "streak": int(member.get("streak", 0)),
        "rank": _rank(group, member_id),
        "members": len(group["members"]),
        "checked_today": member.get("last") == datetime.date.today().isoformat(),
    }


def leaderboard(group_id, limit=10):
    data = _load()
    group = _group(data, group_id)
    rows = sorted(group.get("members", {}).items(),
                  key=lambda kv: int(kv[1].get("points", 0)), reverse=True)
    result = []
    for mid, member in rows[:limit]:
        if int(member.get("points", 0)) <= 0:
            continue
        result.append({
            "name": _display_name(mid, member),
            "points": int(member.get("points", 0)),
            "streak": int(member.get("streak", 0)),
        })
    return result


def wordcloud(group_id, limit=15):
    data = _load()
    group = _group(data, group_id)
    words = group.get("words") or {}
    rows = sorted(words.items(), key=lambda kv: kv[1], reverse=True)
    result = [{"word": w, "count": int(c)} for w, c in rows if c >= 2][:limit]
    # 样本太少时也给出一些，避免永远是「热词还不够」
    if not result:
        result = [{"word": w, "count": int(c)} for w, c in rows[:min(limit, 10)]]
    return result


def stats():
    """给管理面板用的总览。"""
    data = _load()
    result = []
    today = datetime.date.today().isoformat()
    for gid, group in data.items():
        members = group.get("members", {}) or {}
        checked = sum(1 for m in members.values() if m.get("last") == today)
        result.append({
            "group": gid,
            "members": len(members),
            "messages": int(group.get("msgs", 0)),
            "checked_today": checked,
            "top": leaderboard(gid, 3),
        })
    return result


# ====================== 群内回复文案 ======================

_NAME_MAX = 20


def set_nickname(group_id, member_id, nickname):
    """手动设置排行榜显示名。返回 dict：ok / name / error。"""
    name = re.sub(r"\s+", " ", (nickname or "")).strip()
    if not name:
        return {"ok": False, "error": "empty"}
    if len(name) > _NAME_MAX:
        return {"ok": False, "error": "too_long"}
    data = _load()
    group = _group(data, group_id)
    member = _member(group, member_id, name)
    _save(data)
    return {"ok": True, "name": member["name"]}


def nickname_text(result):
    if result.get("ok"):
        return (
            f"昵称已设为「{result['name']}」\n"
            f"签到、排行榜、我的积分都会显示这个名字。"
        )
    if result.get("error") == "too_long":
        return f"名字太长了，最多 {_NAME_MAX} 个字符，换个短点的吧～"
    return f"用法：/昵称 你的名字（最多 {_NAME_MAX} 个字符）\n例：/昵称 小明"


def checkin_text(result):
    if result.get("already"):
        return (
            f"今天已经签到过啦，明天再来～\n"
            f"连续签到 {result['streak']} 天 · 总积分 {result['total']} · 群内第 {result['rank']} 名"
        )
    return (
        f"签到成功 +{result['points_added']} 积分！\n"
        f"连续签到 {result['streak']} 天 · 总积分 {result['total']} · 群内第 {result['rank']} 名\n"
        f"（连签每天多拿积分，断签从 1 天重新算）"
    )


def leaderboard_text(rows, group_id):
    if not rows:
        return "本群还没有人签到，发「签到」抢第一个吧～"
    lines = ["群积分排行榜"]
    for index, row in enumerate(rows, 1):
        streak = f" 连签{row['streak']}天" if row["streak"] > 1 else ""
        lines.append(f"{index}. {row['name']}  {row['points']} 分{streak}")
    lines.append("（每天签到 +10，连续签到有额外积分）")
    return "\n".join(lines)


def profile_text(info):
    if info["points"] <= 0:
        return "你还没签到过，发「签到」开始攒积分吧～"
    today = "今天已签到" if info["checked_today"] else "今天还没签到"
    return (
        f"积分 {info['points']} · 连续签到 {info['streak']} 天\n"
        f"群内排名：第 {info['rank']} / {info['members']} 名 · {today}"
    )


def wordcloud_text(rows):
    if not rows:
        return "热词还不够，多在群里 @ 我聊几句就出来了～"
    lines = ["群热词 TOP"]
    for index, row in enumerate(rows, 1):
        lines.append(f"{index}. {row['word']}（{row['count']}）")
    lines.append("（只统计 @我 的聊天，样本越多越准）")
    return "\n".join(lines)


def _cli(argv):
    cmd = argv[0] if argv else "stats"
    if cmd == "stats":
        rows = stats()
        if not rows:
            print("（还没有群数据）")
        for row in rows:
            print(f"{row['group']}  成员 {row['members']}  消息 {row['messages']}  "
                  f"今日签到 {row['checked_today']}")
    elif cmd == "board":
        gid = argv[1] if len(argv) > 1 else ""
        print(leaderboard_text(leaderboard(gid), gid))
    elif cmd == "words":
        gid = argv[1] if len(argv) > 1 else ""
        print(wordcloud_text(wordcloud(gid)))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_cli(sys.argv[1:]))
