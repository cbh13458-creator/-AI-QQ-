import asyncio
import base64
import json
import os
import re
import subprocess
import tempfile
import threading
import xml.etree.ElementTree as ET
from html import unescape

import httpx

import config

# 每条搜索的内容最多保留多少字，避免上下文过长
_CONFIG_MAX_CONTENT_CHARS = 300
# 最多取前几条搜索结果
_MAX_RESULTS = 5
# 每个会话最多保留的历史消息条数（可在 .env 用 AI_MEMORY_MESSAGES 调整，默认 20 条约 10 轮）
_MAX_HISTORY_MESSAGES = int(os.getenv("AI_MEMORY_MESSAGES", "20"))
# emoji / 表情符号字符范围，输出前统一过滤
_EMOJI_RE = re.compile(
    "["
    "\U0001F1E6-\U0001F1FF"
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U00002B00-\U00002BFF"
    "\U0000FE00-\U0000FE0F"
    "\U0001F3FB-\U0001F3FF"
    "\U0000200D"
    "\U000020E3"
    "\U0000200B-\U0000200F"
    "]+"
)
# 记忆持久化文件（重启不丢）
_MEMORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory.json")
# 这些纯闲聊/打招呼的话无需联网搜索，直接正常回复
_SKIP_SEARCH_MSGS = {
    "你好", "您好", "嗨", "哈喽", "hi", "hello", "hey", "在吗", "在不在",
    "早上好", "中午好", "下午好", "晚上好", "早安", "午安", "晚安", "早",
    "大家好", "谢谢", "多谢", "谢谢啦", "好的", "收到", "嗯", "哦", "哈哈",
    "嘿嘿", "再见", "拜拜", "88", "666",
}


class AIClient:
    """OpenAI 兼容的大模型客户端，默认走智谱 GLM-4-Flash（免费），支持联网搜索。"""

    def __init__(self):
        self._client = httpx.AsyncClient(timeout=60)
        self._lock = threading.Lock()
        self._history: dict[str, list[dict]] = self._load_memory()  # 会话 id -> 历史消息

    async def chat(self, user_message: str, session_id: str = "") -> str:
        if not user_message or not user_message.strip():
            return "你@了我，但没发内容哦～想问什么直接说就行。"

        if not config.AI_API_KEY:
            return "AI 未配置：请在 .env 中填写 AI_API_KEY。"

        # 1) 联网搜索（失败则退回纯对话，不影响主流程）
        results = []
        if config.AI_WEB_SEARCH and self._should_search(user_message):
            results = await self._search(user_message)

        # 2) 组装消息：系统提示词 + 历史 + 当前问题（有搜索结果时附资料）
        messages = [{"role": "system", "content": config.AI_SYSTEM_PROMPT}]
        messages.extend(self._get_history(session_id))
        if results:
            messages.append({
                "role": "user",
                "content": (
                    "以下是针对用户问题联网搜索到的资料：\n"
                    f"{self._compile(results)}\n\n"
                    f"用户问题：{user_message}\n\n"
                    "请基于以上资料回答用户问题：简洁、不啰嗦，也不要列出来源链接或编号。"
                    "如果问题是“有哪些／还有什么／列举”这类，请尽量完整列出要点，不要为了简短而省略。"
                    "如果资料与问题无关（例如打招呼或闲聊），请直接简短地正常回答。"
                ),
            })
        else:
            messages.append({"role": "user", "content": user_message})

        reply = await self._post_chat(config.AI_MODEL, messages, self._fallback_model())
        self._remember(session_id, user_message, reply)
        return reply

    def _load_memory(self) -> dict[str, list[dict]]:
        """从文件加载历史记忆，失败或格式不对则返回空。"""
        try:
            with open(_MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return {k: v for k, v in data.items() if isinstance(v, list)}
        except Exception:  # noqa: BLE001
            return {}
        return {}

    def _save_memory(self) -> None:
        """把记忆写回文件（文件很小，同步写即可）。"""
        with self._lock:
            try:
                with open(_MEMORY_FILE, "w", encoding="utf-8") as f:
                    json.dump(self._history, f, ensure_ascii=False)
            except Exception:  # noqa: BLE001
                pass

    def _get_history(self, session_id: str) -> list[dict]:
        """取某个会话的历史消息（不含 system）。"""
        if not session_id:
            return []
        return list(self._history.get(session_id, []))

    def _remember(self, session_id: str, user_content: str, assistant_content: str) -> None:
        """把一轮对话写入历史，并裁剪到最近若干条。"""
        if not session_id or not assistant_content:
            return
        hist = self._history.setdefault(session_id, [])
        hist.append({"role": "user", "content": user_content or ""})
        hist.append({"role": "assistant", "content": assistant_content})
        if len(hist) > _MAX_HISTORY_MESSAGES:
            del hist[: len(hist) - _MAX_HISTORY_MESSAGES]
        self._save_memory()

    @staticmethod
    def _strip_emoji(text: str) -> str:
        """过滤掉模型输出里的 emoji / 表情符号，只保留纯文字。"""
        text = _EMOJI_RE.sub("", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = re.sub(r" +([，。！？、；：,.!?])", r"\1", text)
        return text.strip()

    @staticmethod
    def _fallback_model() -> str:
        """主模型过载时的备用模型：显式配置优先，智谱默认降级到 glm-4-flash。"""
        if config.AI_FALLBACK_MODEL:
            return config.AI_FALLBACK_MODEL
        if "bigmodel.cn" in config.AI_BASE_URL and config.AI_MODEL != "glm-4-flash":
            return "glm-4-flash"
        return ""

    async def _post_chat(self, model: str, messages: list[dict], fallback_model: str = "") -> str:
        url = config.AI_BASE_URL.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.AI_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": config.AI_MAX_TOKENS,
            "temperature": config.AI_TEMPERATURE,
        }
        models = [model]
        if fallback_model and fallback_model != model:
            models.append(fallback_model)

        last_detail = ""
        for name in models:
            payload["model"] = name
            for attempt in range(3):
                try:
                    resp = await self._client.post(url, json=payload, headers=headers)
                    # 免费模型高峰期限流/过载（429），退避重试
                    if resp.status_code == 429:
                        last_detail = "当前模型访问量过大"
                        if attempt < 2:
                            await asyncio.sleep(2 + attempt * 2)
                            continue
                        break
                    resp.raise_for_status()
                    data = resp.json()
                    content = (data["choices"][0]["message"].get("content") or "").strip()
                    if content:
                        return self._strip_emoji(content)
                    last_detail = "模型返回空内容"
                    if attempt < 2:
                        await asyncio.sleep(1)
                        continue
                    break
                except httpx.HTTPStatusError as exc:
                    # 尽量把 API 返回的真实错误信息透出，方便定位问题
                    detail = ""
                    try:
                        detail = exc.response.json().get("error", {}).get("message", "")
                    except Exception:  # noqa: BLE001
                        detail = exc.response.text[:200] if exc.response is not None else ""
                    status = exc.response.status_code if exc.response is not None else 0
                    overload = (
                        status in (429, 500, 502, 503, 504)
                        or "访问量" in detail
                        or "overload" in detail.lower()
                        or "rate" in detail.lower()
                    )
                    if overload:
                        last_detail = detail or f"HTTP {status}"
                        break  # 换下一个备用模型
                    return f"AI 调用失败：{detail or exc}"
                except Exception as exc:  # noqa: BLE001 - 对外返回友好提示
                    last_detail = str(exc)
                    if attempt < 2:
                        await asyncio.sleep(1)
                        continue
                    break
        return f"AI 调用失败：{last_detail or '暂时没生成回复，请稍后再试。'}"

    async def chat_image(self, image_bytes: bytes, mime_type: str, user_message: str = "", history: list[dict] | None = None) -> str:
        """识别图片/表情包：转成 base64 交给视觉模型看。"""
        if not config.AI_API_KEY:
            return "AI 未配置：请在 .env 中填写 AI_API_KEY。"
        image_bytes, mime_type = self._normalize_image(image_bytes, mime_type)
        b64 = base64.b64encode(image_bytes).decode()
        # 智谱（bigmodel）要求 image_url.url 直接传 base64 字符串；
        # OpenAI 及其它兼容接口要求 data URI 格式。
        if "bigmodel.cn" in config.AI_BASE_URL or "zhipu" in config.AI_BASE_URL.lower():
            image_url = b64
        else:
            image_url = f"data:{mime_type};base64,{b64}"
        text = (user_message.strip() + "，") if user_message.strip() else ""
        instruction = f"{text}请你看看这张图/表情的内容，用自然、简短的话描述一下，两三句以内。"
        messages = [
            {"role": "system", "content": config.AI_SYSTEM_PROMPT},
            *(history or []),
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": image_url}},
                {"type": "text", "text": instruction},
            ]},
        ]
        return await self._post_chat(config.AI_VISION_MODEL, messages)

    async def chat_video(self, video_bytes: bytes, user_message: str = "", history: list[dict] | None = None) -> str:
        """识别视频：抽一帧画面再交给视觉模型看。"""
        frame, mime = await self._extract_frame(video_bytes)
        if frame is None:
            return "收到视频啦，但我暂时看不清这个视频的画面～"
        text = (user_message.strip() + "，") if user_message.strip() else ""
        return await self.chat_image(frame, mime, f"{text}这是视频里的一个画面截图", history)

    async def chat_media(self, media: list[tuple[str, str]], user_message: str = "", session_id: str = "") -> str:
        """处理消息里带的图片/视频。media 为 [(content_type, url), ...]"""
        history = self._get_history(session_id)
        parts = []
        for content_type, url in media[:3]:
            data = await self._download(url)
            if not data:
                continue
            if content_type.lower().startswith("video/"):
                parts.append(await self.chat_video(data, user_message, history))
            else:
                parts.append(await self.chat_image(data, content_type, user_message, history))
        reply = "\n".join(parts) if parts else "我收到图片/视频了，但没下载成功～"
        if parts:
            self._remember(session_id, user_message or "（发来一张图片/视频）", reply)
        return reply

    async def _download(self, url: str) -> bytes:
        try:
            resp = await self._client.get(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    )
                },
                follow_redirects=True,
            )
            resp.raise_for_status()
            return resp.content
        except Exception:  # noqa: BLE001
            return b""

    @staticmethod
    def _normalize_image(data: bytes, mime: str) -> tuple[bytes, str]:
        # png/jpeg 直接交给模型，gif/webp 等先转成 png 避免解析失败
        if mime in ("image/png", "image/jpeg"):
            return data, mime
        try:
            from PIL import Image
            import io
            im = Image.open(io.BytesIO(data))
            im = im.convert("RGB")
            buf = io.BytesIO()
            im.save(buf, format="PNG")
            return buf.getvalue(), "image/png"
        except Exception:  # noqa: BLE001
            return data, mime or "image/png"

    async def _extract_frame(self, video_bytes: bytes):
        return await asyncio.to_thread(self._extract_frame_sync, video_bytes)

    @staticmethod
    def _extract_frame_sync(video_bytes: bytes):
        try:
            with tempfile.TemporaryDirectory() as td:
                vpath = os.path.join(td, "in.mp4")
                fpath = os.path.join(td, "frame.png")
                with open(vpath, "wb") as f:
                    f.write(video_bytes)
                duration = 0.0
                try:
                    probe = subprocess.run(
                        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                         "-of", "default=noprint_wrappers=1:nokey=1", vpath],
                        capture_output=True, text=True, timeout=20,
                    )
                    duration = float((probe.stdout or "").strip() or 0)
                except Exception:  # noqa: BLE001
                    duration = 0.0
                t = duration / 2 if duration > 0 else 0.1
                r = subprocess.run(
                    ["ffmpeg", "-y", "-ss", str(t), "-i", vpath,
                     "-frames:v", "1", fpath],
                    capture_output=True, timeout=30,
                )
                if r.returncode != 0 or not os.path.exists(fpath):
                    return None, None
                with open(fpath, "rb") as f:
                    return f.read(), "image/png"
        except Exception:  # noqa: BLE001
            return None, None

    @staticmethod
    def _should_search(message: str) -> bool:
        """判断是否需要联网搜索：过短或纯闲聊直接跳过。"""
        m = message.strip()
        if len(m) <= 2:
            return False
        return m.lower() not in _SKIP_SEARCH_MSGS

    async def _search(self, query: str) -> list[dict]:
        """按配置选择搜索提供方；失败返回空列表，不影响正常对话。"""
        if config.AI_SEARCH_PROVIDER == "zhipu":
            return await self._search_zhipu(query)
        return await self._search_bing(query)

    async def _search_bing(self, query: str) -> list[dict]:
        """免费必应搜索：取 RSS 结果，无需 API Key。"""
        params = {"q": query, "format": "rss", "mkt": "zh-CN"}
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        for base in (config.AI_SEARCH_BING_URL, "https://www.bing.com/search"):
            try:
                resp = await self._client.get(
                    base.rstrip("/"), params=params, headers=headers, follow_redirects=True
                )
                resp.raise_for_status()
                root = ET.fromstring(resp.text)
            except Exception:  # noqa: BLE001
                continue
            items = root.findall(".//item")[:_MAX_RESULTS]
            results = []
            for it in items:
                title = unescape((it.findtext("title") or "").strip())
                content = unescape((it.findtext("description") or "").strip())
                url = (it.findtext("link") or "").strip()
                if not title and not content:
                    continue
                results.append({"title": title, "content": content, "url": url})
            if results:
                return results
        return []

    async def _search_zhipu(self, query: str) -> list[dict]:
        """调用智谱 Web Search API（按次计费），返回结构化结果列表。"""
        url = config.AI_SEARCH_BASE_URL.rstrip("/")
        headers = {
            "Authorization": f"Bearer {config.AI_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "search_engine": config.AI_SEARCH_ENGINE,
            "search_query": query,
            "count": _MAX_RESULTS,
        }
        try:
            resp = await self._client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return (data.get("search_result") or [])[:_MAX_RESULTS]
        except Exception:  # noqa: BLE001 - 搜索失败不影响回答
            return []

    @staticmethod
    def _compile(results: list[dict]) -> str:
        parts = []
        for i, it in enumerate(results, 1):
            title = (it.get("title") or "").strip()
            media = (it.get("media") or "").strip()
            content = (it.get("content") or "").strip()
            if len(content) > _CONFIG_MAX_CONTENT_CHARS:
                content = content[:_CONFIG_MAX_CONTENT_CHARS] + "……"
            head = f"[{i}] {title}" + (f"（{media}）" if media else "")
            parts.append(f"{head}\n{content}")
        return "\n\n".join(parts)

    async def close(self):
        await self._client.aclose()