#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同步 QQ 官方指令面板（纯标准库，不需要额外依赖）

在群里输入 / 或点机器人头像时弹出的面板，属于 QQ 开放平台侧的配置，
不随代码走。这个脚本用 .env 里的 QQ_APP_ID / QQ_APP_SECRET 登录开放平台，
自动创建或补齐群聊/单聊面板，新装用户配置好就是完整菜单。

用法：
    python panel_setup.py          创建或补齐面板
    python panel_setup.py --check  只显示当前面板，不修改
"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import config  # noqa: E402

TIMEOUT = 20

GROUP_ITEMS = [
    {"name": "菜单", "desc": "查看全部功能", "type": "command"},
    {"name": "摸摸", "desc": "摸摸头互动", "type": "command"},
    {"name": "表情包", "desc": "随机搜一张表情包", "type": "command"},
    {"name": "定时", "desc": "查看定时消息", "type": "command"},
    {"name": "状态", "desc": "查看版本与运行状态", "type": "command"},
    {"name": "签到", "desc": "每日签到攒积分，连签更多", "type": "command"},
    {"name": "排行榜", "desc": "群积分排行榜前10", "type": "command"},
    {"name": "我的积分", "desc": "查看自己的积分和排名", "type": "command"},
    {"name": "昵称", "desc": "设置排行榜显示的名字", "type": "command"},
    {"name": "词云", "desc": "查看群里最近的热词", "type": "command"},
]

C2C_ITEMS = [
    {"name": "菜单", "desc": "查看全部功能", "type": "command"},
    {"name": "摸摸", "desc": "摸摸头互动", "type": "command"},
    {"name": "表情包", "desc": "随机搜一张表情包", "type": "command"},
    {"name": "定时", "desc": "查看定时消息", "type": "command"},
    {"name": "状态", "desc": "查看版本与运行状态", "type": "command"},
]

REMARK = "AI机器人功能面板"


def _request(url, token=None, method="GET", body=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "QQBot " + token
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_token():
    """返回 (access_token, openapi_base)。

    QQ 开放平台新接口用 clientSecret，老接口用 appSecret，这里两种都试，
    谁成功就用谁的域名，避免新老机器人账号不兼容。
    """
    appid = (config.QQ_APP_ID or "").strip()
    secret = (config.QQ_APP_SECRET or "").strip()
    if not appid or not secret:
        raise RuntimeError("没有配置 QQ_APP_ID / QQ_APP_SECRET")

    attempts = [
        ("https://api.bot.qq.com/app/getAppAccessToken", {"appId": appid, "clientSecret": secret}, "https://api.bot.qq.com"),
        ("https://bots.qq.com/app/getAppAccessToken", {"appId": appid, "appSecret": secret}, "https://api.sgroup.qq.com"),
    ]
    last_error = ""
    for url, payload, base in attempts:
        try:
            data = _request(url, method="POST", body=payload)
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            continue
        token = data.get("access_token")
        if token:
            return token, base
        last_error = data.get("message") or str(data)
    raise RuntimeError("取 access_token 失败：" + (last_error or "未知错误"))


def _merge(existing, wanted):
    names = {item.get("name") for item in existing if isinstance(item, dict)}
    added = 0
    for item in wanted:
        if item["name"] not in names:
            existing.append(dict(item))
            added += 1
    return added


def _sync_scope(api, token, scope, wanted, check_only=False):
    records = api("/v2/panels?scope=%s&limit=50" % scope, token)
    panels = [r for r in records.get("records") or [] if r.get("target_type") == "all"]
    if check_only:
        if panels:
            for rec in panels:
                names = [i.get("name") for i in rec["panel"].get("items") or []]
                print("%s 面板 %s：%s" % (scope, rec["panel_id"], " / ".join(names)))
        else:
            print("%s 面板：未创建" % scope)
        return

    if panels:
        for rec in panels:
            items = rec["panel"].get("items") or []
            added = _merge(items, wanted)
            body = {"panel": {"items": items, "remark": rec["panel"].get("remark") or REMARK}}
            api("/v2/panels/" + rec["panel_id"], token, "PUT", body)
            print("%s 面板已同步：新增 %d 项，共 %d 项" % (scope, added, len(items)))
        return

    body = {"scope": scope, "target_type": "all",
            "panel": {"items": [dict(i) for i in wanted], "remark": REMARK}}
    result = api("/v2/panels", token, "POST", body)
    print("%s 面板已创建：%d 项（%s）" % (scope, len(wanted), result.get("panel_id", "") ))


def main():
    check_only = "--check" in sys.argv
    try:
        token, base = get_token()
    except RuntimeError as exc:
        print("面板同步失败：%s" % exc)
        print("请检查 qq-bot/.env 里的 QQ_APP_ID 和 QQ_APP_SECRET 是否与开放平台一致。")
        return 1

    def api(path, tok, method="GET", body=None):
        return _request(base + path, tok, method, body)

    try:
        wanted_group = list(GROUP_ITEMS) if config.ENABLE_GROUP_TOOLS else GROUP_ITEMS[:5]
        _sync_scope(api, token, "group", wanted_group, check_only)
        _sync_scope(api, token, "c2c", C2C_ITEMS, check_only)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")[:200]
        print("面板同步失败：HTTP %s %s" % (exc.code, detail))
        return 1
    except Exception as exc:  # noqa: BLE001
        print("面板同步失败：%s" % exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
