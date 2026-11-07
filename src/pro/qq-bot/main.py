import asyncio
import json
import os
import random
import re
import time
from html import unescape

import aiohttp
import botpy
from botpy.connection import ConnectionState
from botpy.message import C2CMessage, GroupMessage

import config
import groups
import scheduler
from ai import AIClient

# botpy 内部用 aiohttp 发请求。aiohttp 默认不读系统代理（trust_env=False），
# 而且对 wss:// 这种 WebSocket 地址，就算 trust_env=True 也不会自动套用
# HTTPS_PROXY（它只会按 http/https 去环境变量里找代理），导致直连 QQ 网关超时。
# 这里做两件事：
#   1) ClientSession 默认 trust_env=True，让取 token 等 https 请求走代理；
#   2) ws_connect 自动从环境变量注入 proxy，让 wss 连接也走代理。
# 未设置代理时无任何影响。
_orig_client_session_init = aiohttp.ClientSession.__init__


def _client_session_init(self, *args, **kwargs):
    kwargs.setdefault("trust_env", True)
    _orig_client_session_init(self, *args, **kwargs)


aiohttp.ClientSession.__init__ = _client_session_init

_orig_ws_connect = aiohttp.ClientSession.ws_connect


def _ws_connect(self, url, **kwargs):
    if kwargs.get("proxy") is None:
        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or ""
        if proxy:
            kwargs["proxy"] = proxy
    return _orig_ws_connect(self, url, **kwargs)


aiohttp.ClientSession.ws_connect = _ws_connect

# 群聊 @机器人、C2C 私聊消息事件
intents = botpy.Intents(public_messages=True)

# botpy 1.2.1 的 GroupMessage 只保留 content / message_reference 等少数字段，
# 网关下发的 msg_elements（引用、聊天记录）和 message_scene 会被直接丢弃。
# 这里接管群消息解析，把原始数据先存下来，处理消息时再提取引用内容。
_RAW_GROUP_DATA: dict[str, dict] = {}
_RAW_GROUP_LIMIT = 300


def _parse_group_at_message_create(self, payload):
    data = payload.get("d", {}) or {}
    message = GroupMessage(self.api, payload.get("id"), data)
    try:
        if message.id:
            _RAW_GROUP_DATA[message.id] = data
            if len(_RAW_GROUP_DATA) > _RAW_GROUP_LIMIT:
                for key in list(_RAW_GROUP_DATA)[: _RAW_GROUP_LIMIT // 3]:
                    _RAW_GROUP_DATA.pop(key, None)
    except Exception:  # noqa: BLE001 - 原始数据仅为辅助，不能影响正常消息
        pass
    self._dispatch("group_at_message_create", message)


ConnectionState.parse_group_at_message_create = _parse_group_at_message_create

# 去掉消息里 @机器人 的占位符，例如 <@!123456>
_MENTION_RE = re.compile(r"<@!?\d+>")
# QQ 表情包常以 [微笑] 这类文本代码出现
_EMOJI_RE = re.compile(r"^\[[^\[\]]{1,8}\]$")

# 摸摸触发词（QQ 独占互动）
_PAT_WORDS = {"摸摸", "摸摸头", "摸摸你", "揉揉", "拍拍", "拍拍头", "rua", "抱抱", "蹭蹭", "贴贴"}
_PAT_REPLIES = [
    "摸摸头～乖乖的 (｡･ω･｡)ﾉ♡",
    "摸摸～今天也辛苦啦 (๑•́ ₃ •̀๑)",
    "嘿嘿，摸一下 ✋ 心情有没有好一点～",
    "摸摸 (づ｡◕‿‿◕｡)づ 顺毛～",
    "拍拍～别不开心啦 (๑>ᴗ<๑)",
]

# 收到纯表情包时的回应
_EMOJI_REPLIES = [
    "哈哈这个表情我懂 (≧▽≦)",
    "收到你的表情包啦～ (๑•̀ㅂ•́)و✧",
    "这个表情好可爱，回你一个 (｡･ω･｡)ﾉ♡",
]

# 触发频率/每日限额时的回复
_RATE_REPLIES = [
    "你聊太快啦，歇会儿喵～",
    "先喘口气，等下再聊 (´･ω･`)",
    "消息太多啦，我脑子转不过来了喵",
]

# 「来个表情包/找张图」这类请求
_IMAGE_REQUEST_RE = re.compile(
    r"(来|发|找|整|要|求|给|换|有没有).{0,8}(表情包|表情|图|图片|照片|壁纸|头像)"
    r"|(表情包|图片|壁纸|头像).{0,6}(来|发|整|求)"
)
_IMAGE_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
_IMAGE_BLOCK_WORDS = ("r18", "nsfw", "porn", "sex", "xxx", "裸", "色情")


def is_image_request(text: str) -> bool:
    return bool(_IMAGE_REQUEST_RE.search(text or ""))


def image_keyword(text: str) -> str:
    """从「来个猫猫表情包」里抽出搜索词。"""
    keyword = re.sub(
        r"^(?:帮我|给我|请|麻烦)?(?:有没有|来|发|找|整|要|求|给|换)",
        "",
        (text or "").strip(),
    )
    keyword = re.sub(r"^(?:一个|一张|一些|点|个|张)", "", keyword)
    keyword = re.sub(
        r"(表情包|图片|壁纸|头像)(?:来|发|整|求)(?:一个|一张|点)?$",
        r"\1",
        keyword,
    )
    keyword = re.sub(r"[，。！？、,.!?～~]", " ", keyword)
    keyword = re.sub(r"(吧|呗|呀|啊|嘛|吗)$", "", keyword)
    keyword = re.sub(r"\s+", " ", keyword).strip()
    if keyword in ("", "图", "图片", "表情", "表情包"):
        return "猫猫 表情包"
    if not any(word in keyword for word in ("表情包", "表情", "图", "壁纸", "头像")):
        keyword += " 表情包"
    return keyword


# 每个关键词最近发过的图，避免一直发同一张
_IMAGE_RECENT: dict[str, list[str]] = {}
_IMAGE_RECENT_MAX = 12


async def search_image_urls(keyword: str, limit: int = 10) -> list[str]:
    """用必应图片搜索找几张候选图，免费、不需要 Key。"""
    # 每次随机翻一页，避免同一关键词永远返回同样几张
    params = {"q": keyword, "form": "HDRSC2", "first": random.choice([1, 36, 71, 106]), "adlt": "strict"}
    headers = {"User-Agent": _IMAGE_UA, "Accept-Language": "zh-CN,zh;q=0.9"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://cn.bing.com/images/search", params=params, headers=headers
            ) as resp:
                html = await resp.text()
    except Exception as exc:  # noqa: BLE001
        botpy.logger.warning(f"图片搜索失败：{exc}")
        return []

    urls = re.findall(r'murl&quot;:&quot;(.*?)&quot;', html)
    if not urls:
        urls = re.findall(r'"murl":"(.*?)"', html)
    result = []
    for raw in urls:
        url = unescape(raw).replace("\\/", "/").strip()
        low = url.lower()
        if not low.startswith(("http://", "https://")):
            continue
        if not re.search(r"\.(jpg|jpeg|png)(\?|$)", low):
            continue
        if any(word in low for word in _IMAGE_BLOCK_WORDS):
            continue
        result.append(url)
        if len(result) >= limit:
            break
    return result


def clean_content(content: str) -> str:
    return _MENTION_RE.sub("", content or "").strip()


# 引用 / 聊天记录里可能出现的文字字段
_TEXT_KEYS = ("content", "text", "prompt", "title", "desc", "summary", "name", "nickname")


def _collect_text(value, out: list[str], depth: int = 0) -> None:
    """从引用/聊天记录的 JSON 里把所有可读文字捞出来。"""
    if depth > 5:
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, str):
                text = item.strip()
                if text.startswith(("{", "[")):
                    try:
                        _collect_text(json.loads(text), out, depth + 1)
                    except Exception:  # noqa: BLE001
                        pass
                elif key.lower() in _TEXT_KEYS and text:
                    out.append(text)
            else:
                _collect_text(item, out, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _collect_text(item, out, depth + 1)


_QUOTE_DEBUG_COUNT = 0


def _has_reference(data) -> bool:
    """是否真的是「引用回复」。普通 @ 消息也会带 msg_elements，不能直接当引用。"""
    for ext in (data.get("message_scene") or {}).get("ext") or []:
        if isinstance(ext, str) and ext.startswith("ref_msg_idx="):
            return True
    return False


def quote_text(message) -> str:
    """取出被引用的消息内容；没有引用则返回空字符串。"""
    global _QUOTE_DEBUG_COUNT
    data = _RAW_GROUP_DATA.get(getattr(message, "id", None)) or {}
    if not _has_reference(data):
        return ""
    parts: list[str] = []
    for element in data.get("msg_elements") or []:
        if not isinstance(element, dict):
            continue
        try:
            mtype = int(element.get("message_type") or 0)
        except Exception:  # noqa: BLE001
            mtype = 0
        if mtype == 101:  # 101 是当前消息正文，跳过避免重复
            continue
        content = element.get("content")
        if isinstance(content, str):
            text = content.strip()
            if text.startswith(("{", "[")):
                try:
                    _collect_text(json.loads(text), parts)
                except Exception:  # noqa: BLE001
                    pass
            elif text:
                parts.append(text)
        else:
            _collect_text(content, parts)
    if not parts:
        for ext in (data.get("message_scene") or {}).get("ext") or []:
            if isinstance(ext, str):
                try:
                    _collect_text(json.loads(ext), parts)
                except Exception:  # noqa: BLE001
                    continue
    seen = set()
    result = []
    for part in parts:
        part = re.sub(r"\s+", " ", part).strip()
        if 2 <= len(part) <= 200 and part not in seen:
            seen.add(part)
            result.append(part)
        if len(result) >= 3:
            break
    # 诊断用：收到了扩展字段但没解析出内容时，把原始结构打进日志（最多 3 次）
    if not result and (data.get("msg_elements") or data.get("message_scene")) and _QUOTE_DEBUG_COUNT < 3:
        _QUOTE_DEBUG_COUNT += 1
        try:
            botpy.logger.info(
                "群消息扩展字段未解析出引用："
                + json.dumps(
                    {
                        "msg_elements": data.get("msg_elements"),
                        "message_scene": data.get("message_scene"),
                    },
                    ensure_ascii=False,
                )[:800]
            )
        except Exception:  # noqa: BLE001
            pass
    return "\n".join(result)


_IMG_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")
_VID_EXTS = (".mp4", ".mov", ".webm", ".mkv")


def get_media(message) -> list[tuple[str, str]]:
    """从消息里取出图片/视频附件，返回 [(content_type, url), ...]"""
    media = []
    for att in getattr(message, "attachments", None) or []:
        ct = (getattr(att, "content_type", "") or "").strip().lower()
        url = (getattr(att, "url", "") or "").strip()
        # QQ 有时不给 content_type（尤其表情包），用文件名/宽高兜底判断
        if not ct:
            name = (getattr(att, "filename", "") or "").lower()
            if name.endswith(_IMG_EXTS):
                ct = "image/jpeg"
            elif name.endswith(_VID_EXTS):
                ct = "video/mp4"
            elif getattr(att, "width", 0) and getattr(att, "height", 0):
                ct = "image/jpeg"
        if url and (ct.startswith("image/") or ct.startswith("video/")):
            media.append((ct, url))
    return media


def is_pat(text: str) -> bool:
    return text.strip().lower() in _PAT_WORDS


# 「菜单 / 目录 / 帮助」这类请求，返回功能目录
_MENU_WORDS = {
    "菜单", "目录", "功能", "功能目录", "帮助", "help", "menu",
    "/菜单", "/help", "/功能", "?", "？",
}
_UPDATE_STATE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".update.state.json"
)


def read_version() -> str:
    """读取当前版本号（优先 ~/VERSION，其次代码目录上一级）。"""
    here = os.path.dirname(os.path.abspath(__file__))
    for path in (os.path.expanduser("~/VERSION"), os.path.join(here, "..", "VERSION")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                version = f.read().strip()
            if version:
                return version
        except Exception:  # noqa: BLE001
            continue
    return "unknown"


def is_menu_request(text: str) -> bool:
    return slash_command(text) in _MENU_WORDS or (text or "").strip().lower() in _MENU_WORDS


# 「忘记 / 清除记忆」这类请求：直接清空当前会话的上下文
_FORGET_WORDS = {
    "忘记", "忘掉", "忘了吧", "忘记吧", "忘掉吧", "忘记刚才的", "忘掉刚才的",
    "清除记忆", "清空记忆", "重置记忆", "忘记聊天", "清除聊天记录",
    "forget", "reset",
}


def is_forget_request(text: str) -> bool:
    cleaned = re.sub(r"\s+", "", text or "").strip("。．.!！~～")
    return slash_command(cleaned) in _FORGET_WORDS or cleaned.lower() in _FORGET_WORDS


# 斜杠指令：/菜单 /摸摸 /表情包 /定时 /状态
_SLASH_RE = re.compile(r"^[\/／]([^\s]{1,16})\s*(.*)$")


def slash_command(text: str) -> str:
    """解析 /指令 参数，返回指令名（小写）；不是斜杠指令返回空串。"""
    match = _SLASH_RE.match((text or "").strip())
    return match.group(1).lower() if match else ""


def slash_args(text: str) -> str:
    match = _SLASH_RE.match((text or "").strip())
    return (match.group(2) or "").strip() if match else ""


def menu_text() -> str:
    """群内功能目录（纯文本版）。

    QQ 群管家里那种可折叠面板是官方插件的界面，第三方机器人不能往里加项；
    这里用同样的层级样式发一条消息，效果等价。
    """
    version = read_version()
    return (
        f"功能目录  v{version}\n"
        "━━━━━━━━━━━━━━\n"
        "▸ 聊天\n"
        "   /菜单 ······ 打开这个目录\n"
        "   @我 + 说话 ·· 闲聊 / 问答 / 联网搜索\n"
        "   @我 + 引用消息 ·· 能看到被引用的内容\n"
        "   /忘记 ······ 清空当前会话记忆\n"
        "▸ 娱乐\n"
        "   /摸摸 ······ 摸摸头互动\n"
        "   /表情包 ···· 随机搜一张表情包\n"
        "   /表情包 猫猫 ·· 按关键词搜图\n"
        + ("" if not config.ENABLE_GROUP_TOOLS else (
            "▸ 群互动\n"
            "   /昵称 名字 ··· 设置排行榜显示名\n"
            "   /签到 ······ 每天签到攒积分，连签更多\n"
            "   /排行榜 ···· 群积分排行榜前 10\n"
            "   /我的积分 ··· 查看自己的积分和排名\n"
            "   /词云 ······ 群里最近的热词\n"
        )) +
        "▸ 管理\n"
        "   /定时 ······ 查看定时消息\n"
        "   /状态 ······ 查看版本和运行状态\n"
        "   管理面板 ···· http://127.0.0.1:8080\n"
        "━━━━━━━━━━━━━━\n"
        "指令在群里输入 / 就能看到；也可以直接 @我 说上面的话。"
    )


# 群互动指令：支持 /签到 或直接 @我 说「签到」
_GROUP_ALIASES = {
    "签到": "checkin",
    "打卡": "checkin",
    "排行榜": "board",
    "积分榜": "board",
    "排行": "board",
    "榜单": "board",
    "我的积分": "me",
    "积分": "me",
    "我的": "me",
    "词云": "words",
    "热词": "words",
    "词频": "words",
    "群词云": "words",
}


def group_action(text: str):
    """把「签到 / 排行榜 / 我的积分 / 词云」解析成动作名，不是则返回 None。"""
    stripped = (text or "").strip().lstrip("/／").strip()
    return _GROUP_ALIASES.get(stripped)


# 设置显示名：/昵称 名字、/改名 名字（也可以不带斜杠，但名字前要有空格或冒号）
_NAME_ARG_RE = re.compile(r"^[\/／]?\s*(?:设置昵称|改昵称|昵称|改名)[\s:：,，]+(.+)$")
_NAME_BARE_RE = re.compile(r"^[\/／]\s*(?:设置昵称|改昵称|昵称|改名)$")


def group_name_arg(text: str):
    """解析「昵称 名字」；不是改名指令返回 None，缺名字返回空串。"""
    stripped = (text or "").strip()
    match = _NAME_ARG_RE.match(stripped)
    if match:
        return match.group(1).strip()
    if _NAME_BARE_RE.match(stripped):
        return ""
    return None


def group_member_id(message) -> str:
    return (
        getattr(message.author, "member_openid", "")
        or getattr(message.author, "user_openid", "")
        or "unknown"
    )


def group_nickname(message) -> str:
    name = (
        getattr(message.author, "nickname", "")
        or getattr(message.author, "username", "")
        or ""
    )
    if not name:
        # botpy 的 GroupMessageAuthor 不保留 username，但原始事件里有。
        data = _RAW_GROUP_DATA.get(getattr(message, "id", None)) or {}
        author = data.get("author") or {}
        if isinstance(author, dict):
            name = (author.get("username") or author.get("nickname") or "").strip()
    return name


def _version_tuple(version: str) -> tuple:
    """把 1.1.5 / v1.1.5 转成可比较的数字元组。"""
    parts = []
    for piece in (version or "").lstrip("v").split("."):
        digits = re.sub(r"[^0-9]", "", piece)
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def _load_update_state() -> dict:
    try:
        with open(_UPDATE_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _save_update_state(data: dict) -> None:
    try:
        with open(_UPDATE_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        pass


class AIBotClient(botpy.Client):
    def __init__(self, intents):
        super().__init__(intents=intents)
        self.ai = AIClient()
        self._schedule_task = None
        self._update_task = None
        # 最近回复缓存（会话 -> 规范化文本），用于识别「引用了机器人自己的话」
        self._recent_replies: dict[str, list[str]] = {}
        # 上一次回复（会话 -> (文本, 时间)），用于抑制短时间内重复刷同一句
        self._last_reply: dict[str, tuple[str, float]] = {}
        # 限额计数：分钟滑动窗口 + 按天计数
        self._rate_min: dict[str, list[float]] = {}
        self._rate_day: dict[str, tuple[str, int]] = {}

    async def on_ready(self):
        botpy.logger.info(f"机器人已上线：{self.robot.name}")
        # 启动定时消息循环（QQ 独占）
        if config.SCHEDULE_ENABLED and (self._schedule_task is None or self._schedule_task.done()):
            self._schedule_task = asyncio.create_task(self._schedule_loop())
            botpy.logger.info("定时消息服务已启动")
        # 启动版本更新推送循环
        if config.ENABLE_UPDATE_PUSH and (self._update_task is None or self._update_task.done()):
            self._update_task = asyncio.create_task(self._update_loop())
            botpy.logger.info(
                f"版本更新推送已启动（每 {config.UPDATE_CHECK_INTERVAL_HOURS} 小时检查一次）"
            )

    @staticmethod
    def _session_id(message) -> str:
        """会话 id：私聊按用户隔离，群聊按「群 + 成员」隔离记忆。"""
        if isinstance(message, GroupMessage):
            return f"group:{message.group_openid}:{message.author.member_openid}"
        return f"c2c:{message.author.user_openid}"

    @staticmethod
    def _norm_text(text: str) -> str:
        return re.sub(r"\s+", "", text or "")

    def _remember_reply(self, session_id: str, text: str) -> None:
        """记下最近发出去的回复，供引用识别使用。"""
        if not session_id or not text:
            return
        key = self._norm_text(text)[:400]
        if not key:
            return
        bucket = self._recent_replies.setdefault(session_id, [])
        if key not in bucket:
            bucket.append(key)
            if len(bucket) > 20:
                del bucket[: len(bucket) - 20]

    def _is_self_quote(self, session_id: str, quote: str) -> bool:
        """判断被引用的内容是否就是机器人自己刚说过的话。"""
        if not session_id or not quote:
            return False
        bucket = self._recent_replies.get(session_id) or []
        for part in quote.split("\n"):
            key = self._norm_text(part)[:400]
            if len(key) < 4:
                continue
            for old in bucket:
                if key == old or (len(key) >= 6 and (key in old or old in key)):
                    return True
        return False

    def _is_repeat_reply(self, session_id: str, text: str, window: float = 90.0) -> bool:
        """同一会话内、90 秒内出现完全相同的回复就不再发，避免复读刷屏。"""
        key = self._norm_text(text)
        if not key:
            return False
        last = self._last_reply.get(session_id)
        now = time.time()
        if last and last[0] == key and now - last[1] < window:
            return True
        self._last_reply[session_id] = (key, now)
        return False

    @staticmethod
    def _user_key(message) -> str:
        """按人限额的 key：群里用 member_openid，私聊用 user_openid。"""
        author = getattr(message, "author", None)
        uid = (
            getattr(author, "member_openid", None)
            or getattr(author, "user_openid", None)
            or "unknown"
        )
        gid = getattr(message, "group_openid", "") or "c2c"
        return f"{gid}:{uid}"

    def _rate_ok(self, user_key: str) -> bool:
        """检查并计入一次 AI 调用。超限返回 False。"""
        now = time.time()
        per_min = getattr(config, "AI_RATE_PER_MINUTE", 0)
        per_day = getattr(config, "AI_RATE_PER_DAY", 0)

        if per_min > 0:
            win = [t for t in self._rate_min.get(user_key, []) if now - t < 60]
            if len(win) >= per_min:
                self._rate_min[user_key] = win
                botpy.logger.info(f"触发分钟限额：{user_key[-8:]}")
                return False
            win.append(now)
            self._rate_min[user_key] = win

        if per_day > 0:
            today = time.strftime("%Y-%m-%d")
            day, cnt = self._rate_day.get(user_key, (today, 0))
            if day != today:
                day, cnt = today, 0
            if cnt >= per_day:
                botpy.logger.info(f"触发每日限额：{user_key[-8:]}")
                return False
            self._rate_day[user_key] = (day, cnt + 1)
        return True

    async def _schedule_loop(self):
        """每 20 秒检查一次是否有到点的定时消息。"""
        while True:
            try:
                for task in scheduler.due_tasks():
                    await self._send_scheduled(task)
            except Exception as exc:  # noqa: BLE001 - 定时任务不能影响主流程
                botpy.logger.error(f"定时消息检查异常：{exc}")
            await asyncio.sleep(20)

    async def _send_scheduled(self, task):
        text = task.get("text", "")
        targets = scheduler.resolve_targets(task.get("scope"))
        ok = False
        if not targets:
            botpy.logger.warning(f"定时任务 {task.get('id')} 没有可发送的群（先在群里 @ 机器人一次）")
        for kind, target_id in targets:
            try:
                if kind == "c2c":
                    await self.api.post_c2c_message(openid=target_id, msg_type=0, content=text)
                else:
                    await self.api.post_group_message(group_openid=target_id, msg_type=0, content=text)
                ok = True
                botpy.logger.info(f"定时消息已发送 -> {kind}:{target_id}")
            except Exception as exc:  # noqa: BLE001
                botpy.logger.error(f"定时消息发送失败 {kind}:{target_id}：{exc}")
        scheduler.mark_sent(task["id"], "ok" if ok else "fail")

    async def _update_loop(self):
        """定期检查 GitHub 最新版本，有更新就推送到记录过的群/私聊。"""
        await asyncio.sleep(60)
        while True:
            try:
                await self._check_update()
            except Exception as exc:  # noqa: BLE001 - 检查失败不能影响主流程
                botpy.logger.warning(f"版本更新检查失败：{exc}")
            await asyncio.sleep(max(1, config.UPDATE_CHECK_INTERVAL_HOURS) * 3600)

    async def _check_update(self):
        local = read_version()
        url = f"https://api.github.com/repos/{config.GITHUB_REPO}/releases/latest"
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "qq-ai-bot"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return
                data = await resp.json()
        tag = (data.get("tag_name") or "").strip().lstrip("v")
        if not tag or _version_tuple(tag) <= _version_tuple(local):
            return
        if _load_update_state().get("notified") == tag:
            return

        body = re.sub(r"\s+", " ", (data.get("body") or "")).strip()
        if len(body) > 100:
            body = body[:100] + "…"
        text = f"【版本更新】机器人有新版本 v{tag}（当前 v{local}）"
        if body:
            text += f"\n更新内容：{body}"
        text += "\n更新不会覆盖你的配置，执行：bash ~/bot.sh update"

        pushed = 0
        for kind, target_id in scheduler.list_targets():
            try:
                if kind == "c2c":
                    await self.api.post_c2c_message(openid=target_id, msg_type=0, content=text)
                else:
                    await self.api.post_group_message(group_openid=target_id, msg_type=0, content=text)
                pushed += 1
            except Exception as exc:  # noqa: BLE001 - 单个会话失败不影响其它会话
                botpy.logger.warning(f"版本更新推送失败 {kind}:{target_id}：{exc}")
        _save_update_state({"notified": tag})
        botpy.logger.info(f"版本更新推送完成：v{local} -> v{tag}，成功 {pushed} 个会话")

    async def _handle_slash(self, message, text: str) -> bool:
        """处理 /菜单 /摸摸 /表情包 /定时 /状态 这类斜杠指令。
        返回 True 表示已处理，False 表示交给普通流程。
        """
        cmd = slash_command(text)
        if not cmd:
            return False
        args = slash_args(text)

        if cmd in ("菜单", "目录", "功能", "功能目录", "帮助", "help", "menu"):
            await message.reply(content=menu_text())
            return True

        if cmd in ("摸摸", "摸摸头", "拍拍", "拍拍头", "rua", "抱抱", "贴贴", "蹭蹭"):
            await message.reply(content=random.choice(_PAT_REPLIES))
            return True

        if cmd in ("表情包", "表情", "图", "图片", "来图", "找图", "壁纸", "头像"):
            await self._send_image(message, args or "猫猫 表情包")
            return True

        if cmd in ("定时", "定时消息", "sched"):
            tasks = scheduler.load_tasks()
            if not tasks:
                reply = "还没有定时任务。\n用命令行添加：bash ~/bot.sh sched add 08:00 早安"
            else:
                lines = ["当前定时消息："]
                for task in tasks:
                    state = "启用" if task.get("enabled", True) else "暂停"
                    lines.append(f"{task.get('time','')}  {task.get('text','')}  ({state})")
                reply = "\n".join(lines)
            await message.reply(content=reply)
            return True

        if cmd in ("状态", "status", "版本", "version"):
            await message.reply(
                content=(
                    f"当前版本：v{read_version()}\n"
                    f"会话类型：{'群聊' if isinstance(message, GroupMessage) else '私聊'}\n"
                    f"群互动：{'开启' if config.ENABLE_GROUP_TOOLS else '关闭'}\n"
                    "功能目录：发 /菜单"
                )
            )
            return True

        return False

    async def _handle_group_tool(self, message, text: str) -> bool:
        """签到 / 排行榜 / 我的积分 / 词云。返回 True 表示已处理。"""
        if not (isinstance(message, GroupMessage) and config.ENABLE_GROUP_TOOLS):
            return False
        gid = message.group_openid
        mid = group_member_id(message)
        name = group_nickname(message)
        name_arg = group_name_arg(text)
        if name_arg is not None:
            reply = groups.nickname_text(groups.set_nickname(gid, mid, name_arg))
        else:
            action = group_action(text)
            if not action:
                return False
            try:
                if action == "checkin":
                    reply = groups.checkin_text(groups.checkin(gid, mid, name))
                elif action == "board":
                    reply = groups.leaderboard_text(groups.leaderboard(gid), gid)
                elif action == "me":
                    reply = groups.profile_text(groups.profile(gid, mid))
                else:
                    reply = groups.wordcloud_text(groups.wordcloud(gid))
            except Exception as exc:  # noqa: BLE001 - 统计文件异常时给出提示
                botpy.logger.error(f"群互动指令失败：{exc}")
                reply = "统计暂时出错了，等会儿再试试～"
        await message.reply(content=reply)
        return True

    async def _send_image(self, message, text: str):
        """搜一张图并通过官方富媒体接口发出去。"""
        keyword = image_keyword(text)
        urls = await search_image_urls(keyword)
        if not urls:
            await message.reply(content="这次没找到合适的图，换个词再试试～")
            return
        recent = _IMAGE_RECENT.setdefault(keyword, [])
        candidates = [u for u in urls if u not in recent] or urls
        random.shuffle(candidates)
        for url in candidates[:4]:
            try:
                if isinstance(message, GroupMessage):
                    uploaded = await self.api.post_group_file(
                        group_openid=message.group_openid, file_type=1, url=url
                    )
                else:
                    uploaded = await self.api.post_c2c_file(
                        openid=message.author.user_openid, file_type=1, url=url
                    )
                info = (uploaded or {}).get("file_info")
                if not info:
                    continue
                await message.reply(msg_type=7, media={"file_info": info})
                recent.append(url)
                del recent[: max(0, len(recent) - _IMAGE_RECENT_MAX)]
                botpy.logger.info(f"已发送图片：{keyword} -> {url}")
                return
            except Exception as exc:  # noqa: BLE001 - 单张失败就换下一张
                botpy.logger.warning(f"图片发送失败（{url}）：{exc}")
        await message.reply(content="图找到了但没发出去，等会儿再试试～")

    async def _handle(self, message):
        text = clean_content(message.content)
        media = get_media(message)
        session_id = self._session_id(message)

        # 记录群 openid，供定时消息使用
        if isinstance(message, GroupMessage):
            scheduler.record_group(message.group_openid)
            scheduler.record_target("group", message.group_openid)
            # 群互动统计：活跃度 + 热词（指令本身不计入）
            if config.ENABLE_GROUP_TOOLS and text and not group_action(text) and group_name_arg(text) is None:
                try:
                    groups.record_activity(
                        message.group_openid, group_member_id(message),
                        group_nickname(message), text,
                    )
                except Exception as exc:  # noqa: BLE001 - 统计失败不影响聊天
                    botpy.logger.warning(f"群互动统计失败：{exc}")
        else:
            scheduler.record_target("c2c", message.author.user_openid)

        # 斜杠指令：/菜单 /摸摸 /表情包 /定时 /状态
        if await self._handle_slash(message, text):
            return

        # 「忘记 / 清除记忆」：清空当前会话上下文，不再走 AI
        if is_forget_request(text):
            cleared = self.ai.forget(session_id)
            await message.reply(
                content="好，刚才聊的我都忘了，重新开始吧～"
                if cleared else "我本来就没记住啥，重新开始吧～"
            )
            return

        # 群互动：/签到 /排行榜 /我的积分 /词云
        if await self._handle_group_tool(message, text):
            return

        # 「菜单 / 目录 / 帮助」：返回功能目录，不再走 AI
        if config.ENABLE_MENU and is_menu_request(text):
            await message.reply(content=menu_text())
            return

        # 「来个表情包/找张图」：先发图，不再走 AI
        if config.ENABLE_IMAGE_SEND and is_image_request(text):
            await self._send_image(message, text)
            return

        pat = config.ENABLE_PAT and is_pat(text)

        # 频率/额度限制：只对真正调用 AI 的路径生效（菜单、找图、摸摸不耗 AI）
        user_key = self._user_key(message)
        needs_ai = bool(media) or (not pat and not _EMOJI_RE.match(text))
        if needs_ai and not self._rate_ok(user_key):
            await message.reply(content=random.choice(_RATE_REPLIES))
            return

        # 引用消息：把被引用的内容一起交给 AI，否则它只能看到自己那条 @
        if isinstance(message, GroupMessage):
            quote = quote_text(message)
            if quote:
                if self._is_self_quote(session_id, quote):
                    # 引用的是机器人自己的回复：不再回灌给 AI，避免「解释自己 → 被引用 → 再解释」的死循环
                    botpy.logger.info("忽略机器人自身回复的引用")
                    if not text.strip():
                        return
                else:
                    botpy.logger.info(f"收到引用消息：{quote[:60]}")
                    text = f"（对方引用了这条消息：{quote}）\n{text}"

        if media:
            botpy.logger.info(f"收到媒体 {len(media)} 个：{[ct for ct, _ in media]}")
            reply_text = await self.ai.chat_media(media, "" if pat else text, session_id)
            if pat:
                reply_text = random.choice(_PAT_REPLIES) + "\n" + reply_text
        elif pat:
            reply_text = random.choice(_PAT_REPLIES)
        elif _EMOJI_RE.match(text):
            # 群友只发了一个表情包文本代码，回一个可爱的反应
            reply_text = random.choice(_EMOJI_REPLIES)
        else:
            reply_text = await self.ai.chat(text, session_id)

        if self._is_repeat_reply(session_id, reply_text):
            botpy.logger.info("重复回复已抑制（90 秒内同一句）")
            return

        await message.reply(content=reply_text)
        self._remember_reply(session_id, reply_text)

    async def on_group_at_message_create(self, message: GroupMessage):
        await self._handle(message)

    async def on_c2c_message_create(self, message: C2CMessage):
        await self._handle(message)


if __name__ == "__main__":
    if not config.QQ_APP_ID or not config.QQ_APP_SECRET:
        raise SystemExit("请先复制 .env.example 为 .env，并填写 QQ_APP_ID 和 QQ_APP_SECRET。")

    # Python 3.12+ 不会自动创建事件循环，而 botpy 内部用 asyncio.get_event_loop()，
    # 需先手动新建一个循环并设为当前，否则报 "no current event loop"。
    asyncio.set_event_loop(asyncio.new_event_loop())

    client = AIBotClient(intents=intents)
    client.run(appid=config.QQ_APP_ID, secret=config.QQ_APP_SECRET)
