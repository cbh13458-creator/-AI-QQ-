#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""QQ 定时消息 + 群记录（QQ 独占功能）

命令行用法：
    python scheduler.py list                 列出所有定时任务
    python scheduler.py groups               列出已知的群
    python scheduler.py add HH:MM 内容 [--scope all|group:<openid>|c2c:<openid>]
    python scheduler.py del <任务ID>
    python scheduler.py on <任务ID>          恢复任务
    python scheduler.py off <任务ID>         暂停任务

任务保存在 schedule.json，发送状态保存在 schedule.state.json，
群记录保存在 .groups.json（机器人收到群消息时自动记录）。
"""
import datetime
import json
import os
import sys
import uuid

BASE = os.path.dirname(os.path.abspath(__file__))
SCHEDULE_FILE = os.path.join(BASE, "schedule.json")
STATE_FILE = os.path.join(BASE, "schedule.state.json")
GROUPS_FILE = os.path.join(BASE, ".groups.json")
TARGETS_FILE = os.path.join(BASE, ".targets.json")


def _load(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if data is not None else default
    except Exception:
        return default


def _save(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def load_tasks():
    data = _load(SCHEDULE_FILE, [])
    if isinstance(data, dict):
        data = data.get("tasks", [])
    return data if isinstance(data, list) else []


def save_tasks(tasks):
    _save(SCHEDULE_FILE, {"tasks": tasks})


def record_group(group_openid, name=""):
    """机器人收到群消息时调用，记录群 openid，供定时消息使用。"""
    if not group_openid:
        return
    groups = _load(GROUPS_FILE, {})
    if not isinstance(groups, dict):
        groups = {}
    old = groups.get(group_openid) or {}
    groups[group_openid] = {
        "name": name or old.get("name", ""),
        "seen": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    _save(GROUPS_FILE, groups)


def list_groups():
    groups = _load(GROUPS_FILE, {})
    return groups if isinstance(groups, dict) else {}


def rename_group(group_openid, name):
    """手动给群改一个面板显示名（QQ 不向普通机器人提供群名接口）。"""
    if not group_openid:
        return False
    groups = _load(GROUPS_FILE, {})
    if not isinstance(groups, dict):
        groups = {}
    old = groups.get(group_openid) or {}
    groups[group_openid] = {
        "name": (name or "").strip()[:30],
        "seen": old.get("seen") or datetime.datetime.now().isoformat(timespec="seconds"),
    }
    _save(GROUPS_FILE, groups)
    return True


def record_target(kind, target_id):
    """记录收到过消息的会话（group / c2c），供版本更新推送使用。"""
    if not target_id:
        return
    targets = _load(TARGETS_FILE, {})
    if not isinstance(targets, dict):
        targets = {}
    targets[f"{kind}:{target_id}"] = {
        "seen": datetime.datetime.now().isoformat(timespec="seconds")
    }
    _save(TARGETS_FILE, targets)


def list_targets():
    """返回 [(kind, id), ...]，kind 为 group 或 c2c。"""
    targets = _load(TARGETS_FILE, {})
    result = []
    if isinstance(targets, dict):
        for key in targets:
            if ":" in key:
                kind, tid = key.split(":", 1)
                if kind in ("group", "c2c") and tid:
                    result.append((kind, tid))
    return result


def add_task(time_str, text, scope="all"):
    try:
        hh, mm = [int(x) for x in str(time_str).split(":")]
        if not (0 <= hh < 24 and 0 <= mm < 60):
            raise ValueError
    except Exception:
        raise ValueError("时间格式应为 HH:MM，例如 08:00")
    if not text or not text.strip():
        raise ValueError("发送内容不能为空")
    tasks = load_tasks()
    task = {
        "id": uuid.uuid4().hex[:8],
        "time": f"{hh:02d}:{mm:02d}",
        "text": text.strip(),
        "scope": (scope or "all").strip(),
        "enabled": True,
        "sent_date": "",
    }
    tasks.append(task)
    save_tasks(tasks)
    return task


def del_task(task_id):
    tasks = load_tasks()
    kept = [t for t in tasks if t.get("id") != task_id]
    save_tasks(kept)
    return len(kept) != len(tasks)


def set_enabled(task_id, enabled):
    tasks = load_tasks()
    ok = False
    for t in tasks:
        if t.get("id") == task_id:
            t["enabled"] = bool(enabled)
            ok = True
    save_tasks(tasks)
    return ok


def due_tasks(now=None):
    """返回当前分钟应发送、且今天尚未发送过的任务。"""
    now = now or datetime.datetime.now()
    hhmm = now.strftime("%H:%M")
    today = now.strftime("%Y-%m-%d")
    result = []
    for t in load_tasks():
        if not t.get("enabled", True):
            continue
        if t.get("time") != hhmm:
            continue
        if t.get("sent_date") == today:
            continue
        result.append(t)
    return result


def mark_sent(task_id, status="ok"):
    tasks = load_tasks()
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    for t in tasks:
        if t.get("id") == task_id:
            t["sent_date"] = today
            t["last_status"] = status
            t["last_run"] = datetime.datetime.now().isoformat(timespec="seconds")
    save_tasks(tasks)


def resolve_targets(scope):
    """把 scope 解析成 [(kind, id), ...]。kind 为 group 或 c2c。"""
    scope = (scope or "all").strip()
    if scope.startswith("c2c:"):
        return [("c2c", scope[4:].strip())]
    if scope.startswith("group:"):
        return [("group", scope[6:].strip())]
    return [("group", gid) for gid in list_groups().keys()]


def _print_tasks():
    tasks = load_tasks()
    if not tasks:
        print("（还没有定时任务）")
        return
    print(f"{'ID':<10}{'时间':<8}{'状态':<6}{'目标':<22}内容")
    for t in tasks:
        state = "启用" if t.get("enabled", True) else "暂停"
        scope = t.get("scope", "all")
        if scope == "all":
            scope = f"所有群({len(list_groups())})"
        print(f"{t.get('id',''):<10}{t.get('time',''):<8}{state:<6}{scope:<22}{t.get('text','')}")


def _cli(argv):
    cmd = argv[0] if argv else "list"
    if cmd in ("list", "ls"):
        _print_tasks()
    elif cmd == "groups":
        groups = list_groups()
        if not groups:
            print("（还没有记录到群。让机器人在群里被 @ 一次即可自动记录）")
        for gid, info in groups.items():
            print(f"{gid}  {info.get('name','')}  (最近活跃 {info.get('seen','')})")
    elif cmd == "add":
        args = argv[1:]
        scope = "all"
        if "--scope" in args:
            idx = args.index("--scope")
            if idx + 1 < len(args):
                scope = args[idx + 1]
            del args[idx:idx + 2]
        if len(args) < 2:
            print("用法: python scheduler.py add HH:MM 内容 [--scope all|group:<id>|c2c:<id>]")
            return 2
        time_str, text = args[0], " ".join(args[1:])
        task = add_task(time_str, text, scope)
        print(f"✅ 已添加：{task['id']}  每天 {task['time']}  {task['text']}  -> {task['scope']}")
    elif cmd == "del":
        if len(argv) < 2:
            print("用法: python scheduler.py del <任务ID>")
            return 2
        print("✅ 已删除" if del_task(argv[1]) else "❌ 没找到该任务")
    elif cmd in ("on", "off"):
        if len(argv) < 2:
            print(f"用法: python scheduler.py {cmd} <任务ID>")
            return 2
        if set_enabled(argv[1], cmd == "on"):
            print("✅ 设置成功")
        else:
            print("❌ 没找到该任务")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
