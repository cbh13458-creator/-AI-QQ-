#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""轻量管理面板（纯标准库，无需额外依赖）

启动：  python ~/qq-bot/panel.py
访问：  http://127.0.0.1:8080
局域网访问：在 .env 里设置 PANEL_HOST=0.0.0.0 后重启面板
"""
import json
import os
import subprocess
import sys
import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

BASE = os.path.dirname(os.path.abspath(__file__))
HOME = os.environ.get("HOME", os.path.expanduser("~"))
sys.path.insert(0, BASE)

import config  # noqa: E402
import groups  # noqa: E402
import scheduler  # noqa: E402

PANEL_HOST = config.PANEL_HOST
PANEL_PORT = config.PANEL_PORT
PANEL_PASSWORD = getattr(config, "PANEL_PASSWORD", "")

_AUTH_COOKIE = "panel_auth"


def _auth_token() -> str:
    """由密码派生的登录令牌（避免明文存储 cookie）。"""
    import hashlib
    return hashlib.sha256(f"qq-bot-panel::{PANEL_PASSWORD}".encode("utf-8")).hexdigest()


LOGIN_HTML = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>管理面板登录</title>
<style>
body{font-family:system-ui;background:#0f172a;color:#e2e8f0;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}
.card{background:#1e293b;padding:32px;border-radius:12px;width:300px}
h2{margin:0 0 16px;font-size:18px}
input{width:100%;padding:10px;margin-bottom:12px;border-radius:8px;border:1px solid #334155;background:#0f172a;color:#e2e8f0;box-sizing:border-box}
button{width:100%;padding:10px;border:0;border-radius:8px;background:#3b82f6;color:#fff;font-size:15px;cursor:pointer}
.err{color:#f87171;font-size:13px;min-height:18px}
</style></head><body><div class="card"><h2>机器人管理面板</h2>
<input type="password" id="pw" placeholder="面板密码" autofocus>
<div class="err" id="err"></div>
<button onclick="login()">登录</button></div>
<script>
async function login(){
  const r = await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:document.getElementById('pw').value})});
  if(r.ok){location.href='/';}
  else{document.getElementById('err').textContent='密码不对';}
}
document.getElementById('pw').addEventListener('keydown',e=>{if(e.key==='Enter')login();});
</script></body></html>"""



def _read_tail(path: str, lines: int = 50) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            data = f.readlines()
        return "".join(data[-int(lines):])
    except Exception:
        return ""


def _running(pattern: str) -> bool:
    try:
        return subprocess.run(
            ["pgrep", "-f", pattern], capture_output=True, timeout=5
        ).returncode == 0
    except Exception:
        return False


def _uptime(state_file: str) -> str:
    try:
        with open(state_file, "r", encoding="utf-8") as f:
            start = int((f.read() or "0").strip() or 0)
        delta = int(datetime.datetime.now().timestamp()) - start
        if delta < 0:
            return "未知"
        return f"{delta // 86400}天{delta % 86400 // 3600}时{delta % 3600 // 60}分"
    except Exception:
        return "未知"


def _version() -> str:
    try:
        with open(os.path.join(HOME, "VERSION"), "r", encoding="utf-8") as f:
            return (f.read() or "").strip() or "未知"
    except Exception:
        return "未知"


ENV_FILE = os.path.join(BASE, ".env")
# 允许在面板里改的配置项（其它项保持原样）
EDITABLE_KEYS = (
    "AI_BASE_URL", "AI_MODEL", "AI_API_KEY", "AI_SYSTEM_PROMPT",
    "ENABLE_GROUP_TOOLS", "ENABLE_IMAGE_SEND", "AI_WEB_SEARCH",
)


def _read_env_lines() -> list[str]:
    try:
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            return f.readlines()
    except Exception:
        return []


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
        value = value.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")
    return value


def load_config() -> dict:
    result = {key: "" for key in EDITABLE_KEYS}
    for line in _read_env_lines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key in result:
            result[key] = _unquote(value)
    return result


def _quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def save_config(updates: dict) -> None:
    lines = _read_env_lines()
    if not lines:
        lines = ["# 由管理面板生成\n"]
    pending = {}
    for key, value in updates.items():
        if key in EDITABLE_KEYS:
            pending[key] = str(value)
    written = set()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.partition("=")[0].strip()
        if key in pending:
            value = pending[key]
            rendered = _quote(value) if key == "AI_SYSTEM_PROMPT" else value
            lines[index] = f"{key}={rendered}\n"
            written.add(key)
    for key, value in pending.items():
        if key not in written:
            rendered = _quote(value) if key == "AI_SYSTEM_PROMPT" else value
            lines.append(f"{key}={rendered}\n")
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)


def get_status() -> dict:
    return {
        "qq": _running(r"main\.py"),
        "oc": _running("openclaw"),
        "watch": _running(r"bot\.sh watch"),
        "panel": True,
        "qq_uptime": _uptime(os.path.join(HOME, ".botstate.qq.start")),
        "oc_uptime": _uptime(os.path.join(HOME, ".botstate.oc.start")),
        "version": _version(),
        "edition": "Pro" if os.path.exists(os.path.join(HOME, "keys.dat")) else "普通",
    }


HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>机器人管理面板</title>
<style>
* { box-sizing: border-box; }
body {
  margin: 0; padding: 16px; font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
  background: #0f1220; color: #e7e9f3; min-height: 100vh;
}
.wrap { max-width: 980px; margin: 0 auto; }
header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; margin-bottom: 18px; }
h1 { font-size: 22px; margin: 0; font-weight: 700; }
h1 span { color: #7c8bff; }
.ver { font-size: 13px; color: #8b90a8; margin-left: 8px; }
.pill { display: inline-flex; align-items: center; gap: 6px; padding: 5px 12px; border-radius: 999px; font-size: 13px; background: #1a1e33; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: #5b6079; }
.dot.on { background: #35d07f; box-shadow: 0 0 8px #35d07f88; }
.dot.off { background: #ff5c6c; box-shadow: 0 0 8px #ff5c6c88; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 18px; }
.card { background: linear-gradient(160deg, #1a1e35, #15182b); border: 1px solid #262b45; border-radius: 14px; padding: 16px; }
.card .label { font-size: 13px; color: #8b90a8; margin-bottom: 8px; }
.card .value { font-size: 20px; font-weight: 700; }
.card .sub { font-size: 12px; color: #8b90a8; margin-top: 6px; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 18px; }
button { cursor: pointer; border: 1px solid #303757; background: #1c2138; color: #e7e9f3; border-radius: 10px; padding: 9px 14px; font-size: 14px; transition: .15s; }
button:hover { background: #262c4a; border-color: #4a5490; }
button.primary { background: linear-gradient(135deg, #6a5cff, #8b5cf6); border: none; }
button.danger { background: #3a1d28; border-color: #6b2b3d; color: #ffb3c0; }
section { background: #14172a; border: 1px solid #262b45; border-radius: 14px; padding: 16px; margin-bottom: 16px; }
section h2 { font-size: 16px; margin: 0 0 12px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { text-align: left; padding: 8px 6px; border-bottom: 1px solid #232840; }
th { color: #8b90a8; font-weight: 500; }
.form { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
input, select { background: #0f1220; border: 1px solid #303757; color: #e7e9f3; border-radius: 9px; padding: 9px 11px; font-size: 14px; }
input[type=text] { flex: 1; min-width: 160px; }
textarea { width: 100%; min-height: 170px; background: #0b0e19; color: #c9cee8; border: 1px solid #262b45; border-radius: 10px; padding: 12px; font-family: ui-monospace, Menlo, monospace; font-size: 12px; resize: vertical; }
.hint { font-size: 12px; color: #8b90a8; margin-top: 8px; line-height: 1.6; }
.tag { font-size: 12px; padding: 2px 8px; border-radius: 6px; background: #232840; color: #aab0c8; }
.tag.on { background: #16351f; color: #6fe39a; }
.tag.off { background: #3a1d28; color: #ff9db0; }
#toast { position: fixed; left: 50%; bottom: 24px; transform: translateX(-50%); background: #262c4a; padding: 10px 18px; border-radius: 10px; font-size: 14px; opacity: 0; transition: .25s; pointer-events: none; }
#toast.show { opacity: 1; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div><h1>🤖 机器人<span>管理面板</span><span class="ver" id="ver"></span></div></div>
    <div class="pill"><span class="dot" id="dot-qq"></span>QQ</div>
    <div class="pill"><span class="dot" id="dot-oc"></span>微信</div>
  </header>

  <div class="grid">
    <div class="card"><div class="label">QQ 机器人</div><div class="value" id="st-qq">—</div><div class="sub" id="up-qq"></div></div>
    <div class="card"><div class="label">微信龙虾</div><div class="value" id="st-oc">—</div><div class="sub" id="up-oc"></div></div>
    <div class="card"><div class="label">当前版本</div><div class="value" id="st-ver">—</div><div class="sub" id="st-edition"></div></div>
    <div class="card"><div class="label">断线守护</div><div class="value" id="st-watch">—</div><div class="sub">掉线后自动拉起</div></div>
  </div>

  <div class="actions">
    <button class="primary" onclick="act('start')">一键启动</button>
    <button onclick="act('start-qq')">只启动 QQ</button>
    <button onclick="act('start-oc')">只启动微信</button>
    <button onclick="act('watch')">开启守护</button>
    <button onclick="act('watch-stop')">关闭守护</button>
    <button class="danger" onclick="act('stop')">停止全部</button>
    <button onclick="loadLogs()">刷新日志</button>
  </div>

  <section>
    <h2>群互动数据（QQ 独占）</h2>
    <div id="group-box"><div class="hint">加载中…</div></div>
    <div class="hint">群友在群里 @机器人 发「签到」即可参与；数据保存在 qq-bot/groupstats.json。</div>
  </section>

  <section>
    <h2>⏰ 定时消息（QQ 独占）</h2>
    <div id="sched-box"><div class="hint">加载中…</div></div>
    <div class="form">
      <input type="text" id="f-time" placeholder="时间 HH:MM，如 08:00" style="max-width:150px">
      <input type="text" id="f-text" placeholder="发送内容">
      <select id="f-scope"></select>
      <button class="primary" onclick="addTask()">添加</button>
    </div>
    <div class="hint">目标选「所有已知群」时，需先在群里 @ 机器人一次，让它记住这个群。QQ 主动消息受官方配额限制，超限会发送失败。群名可直接在下方备注。</div>
  </section>

  <section>
    <h2>基础配置（改完重启机器人生效）</h2>
    <div class="form" style="margin-top:0">
      <input type="text" id="c-model" placeholder="模型，如 glm-4.7-flash" style="max-width:220px">
      <input type="text" id="c-url" placeholder="接口地址，如 https://open.bigmodel.cn/api/paas/v4">
      <input type="text" id="c-key" placeholder="API Key">
    </div>
    <div class="form">
      <select id="c-tools" style="max-width:190px">
        <option value="true">群互动：开启</option>
        <option value="false">群互动：关闭</option>
      </select>
      <select id="c-image" style="max-width:190px">
        <option value="true">发图功能：开启</option>
        <option value="false">发图功能：关闭</option>
      </select>
      <select id="c-search" style="max-width:190px">
        <option value="true">联网搜索：开启</option>
        <option value="false">联网搜索：关闭</option>
      </select>
    </div>
    <div class="form" style="margin-top:8px">
      <textarea id="c-prompt" placeholder="机器人人格设定（AI_SYSTEM_PROMPT）"></textarea>
    </div>
    <div class="form">
      <button class="primary" onclick="saveConfig()">保存配置</button>
      <button onclick="loadConfig()">重新读取</button>
    </div>
    <div class="hint">留空的项不会修改；这里只改 .env 里的常用项，其它内容原样保留。</div>
  </section>

  <section>
    <h2>📜 日志</h2>
    <div class="form" style="margin-top:0">
      <select id="log-which" onchange="loadLogs()">
        <option value="qq">QQ 机器人</option>
        <option value="oc">微信龙虾</option>
        <option value="panel">面板</option>
      </select>
      <button onclick="loadLogs()">刷新</button>
    </div>
    <textarea id="log-box" readonly></textarea>
  </section>
</div>
<div id="toast"></div>

<script>
let groups = {};
function toast(msg){const t=document.getElementById('toast');t.textContent=msg;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),1800);}
async function jget(u){const r=await fetch(u);return await r.json();}
async function jpost(u,d){const r=await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d||{})});return await r.json();}
async function refresh(){
  const s=await jget('/api/status');
  document.getElementById('st-qq').textContent = s.qq?'运行中':'已停止';
  document.getElementById('st-oc').textContent = s.oc?'运行中':'已停止';
  document.getElementById('st-watch').textContent = s.watch?'守护中':'未开启';
  document.getElementById('up-qq').textContent = s.qq?'已运行 '+s.qq_uptime:'—';
  document.getElementById('up-oc').textContent = s.oc?'已运行 '+s.oc_uptime:'—';
  document.getElementById('st-ver').textContent = 'v'+s.version;
  document.getElementById('st-edition').textContent = s.edition+' 版';
  document.getElementById('ver').textContent = 'v'+s.version;
  document.getElementById('dot-qq').className = 'dot '+(s.qq?'on':'off');
  document.getElementById('dot-oc').className = 'dot '+(s.oc?'on':'off');
}
async function act(cmd){
  const r=await jpost('/api/action',{cmd});
  toast(r.output||('已执行：'+cmd));
  setTimeout(refresh,800);
  if(cmd.startsWith('start')) setTimeout(loadLogs,1200);
}
let gidList=[];
function groupLabel(gid){
  const name=(groups[gid]&&groups[gid].name)||'';
  const short=(gid||'').slice(-6);
  return name?(name+'（'+short+'）'):('群 '+short);
}
function scopeLabel(scope){
  if(scope==='all'){return '所有群('+Object.keys(groups).length+')';}
  if((scope||'').indexOf('group:')===0){return groupLabel(scope.slice(6));}
  return escapeHtml(scope);
}
async function loadSched(){
  const d=await jget('/api/schedule');
  groups=d.groups||{};
  const box=document.getElementById('sched-box');
  const tasks=d.tasks||[];
  let h='';
  if(!tasks.length){h='<div class="hint">还没有定时任务</div>';}
  else{
    h='<table><tr><th>时间</th><th>内容</th><th>目标</th><th>状态</th><th></th></tr>';
    for(const t of tasks){
      h+='<tr><td>'+t.time+'</td><td>'+escapeHtml(t.text)+'</td><td>'+scopeLabel(t.scope)+'</td>'+
         '<td><span class="tag '+(t.enabled?'on':'off')+'">'+(t.enabled?'启用':'暂停')+'</span></td>'+
         '<td><button onclick="toggleTask(\\''+t.id+'\\','+(!t.enabled)+')">'+(t.enabled?'暂停':'恢复')+'</button> '+
         '<button class="danger" onclick="delTask(\\''+t.id+'\\')">删除</button></td></tr>';
    }
    h+='</table>';
  }
  const gids=Object.keys(groups);
  gidList=gids;
  if(gids.length){
    h+='<div class="hint" style="margin-top:14px">群名备注：QQ 不向普通机器人提供群名，这里只是面板显示名，不影响发送。</div>';
    h+='<table><tr><th>群</th><th>显示名称</th><th></th></tr>';
    gids.forEach((gid,i)=>{
      const name=(groups[gid]&&groups[gid].name)||'';
      h+='<tr><td>'+(gid||'').slice(-6)+'</td><td><input type="text" id="gn-'+i+'" value="'+escapeHtml(name)+'" placeholder="给这个群起个名字" style="width:100%"></td>'+
         '<td><button onclick="renameGroup('+i+')">保存</button></td></tr>';
    });
    h+='</table>';
  }
  box.innerHTML=h;
  const sel=document.getElementById('f-scope');
  let opts='<option value="all">所有已知群</option>';
  for(const gid of gids){opts+='<option value="group:'+gid+'">'+escapeHtml(groupLabel(gid))+'</option>';}
  sel.innerHTML=opts;
}
async function renameGroup(i){
  const gid=gidList[i];
  const name=document.getElementById('gn-'+i).value.trim();
  const r=await jpost('/api/group-name',{openid:gid,name});
  toast(r.ok?'已保存':(r.error||'保存失败'));
  if(r.ok) loadSched();
}
function escapeHtml(s){return (s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
async function addTask(){
  const time=document.getElementById('f-time').value.trim();
  const text=document.getElementById('f-text').value.trim();
  const scope=document.getElementById('f-scope').value;
  if(!time||!text){toast('请填写时间和内容');return;}
  const r=await jpost('/api/schedule',{action:'add',time,text,scope});
  toast(r.ok?'已添加':(r.error||'添加失败'));
  if(r.ok){document.getElementById('f-text').value='';loadSched();}
}
async function delTask(id){const r=await jpost('/api/schedule',{action:'del',id});toast(r.ok?'已删除':'删除失败');loadSched();}
async function toggleTask(id,enabled){const r=await jpost('/api/schedule',{action:'toggle',id,enabled});toast(r.ok?'已更新':'更新失败');loadSched();}
async function loadGroupStats(){
  const d=await jget('/api/groupstats');
  const rows=d.groups||[];
  const box=document.getElementById('group-box');
  if(!rows.length){box.innerHTML='<div class="hint">还没有群数据。让群友在群里 @机器人 发「签到」。</div>';return;}
  let h='<table><tr><th>群</th><th>成员</th><th>消息</th><th>今日签到</th><th>积分前三</th></tr>';
  for(const g of rows){
    const top=(g.top||[]).map(t=>t.name+' '+t.points).join('、')||'—';
    const label=g.name?g.name+'（'+((g.group||'').slice(-6))+'）':('群 '+((g.group||'').slice(-6)));
    h+='<tr><td>'+escapeHtml(label)+'</td><td>'+g.members+'</td><td>'+g.messages+'</td><td>'+g.checked_today+'</td><td>'+escapeHtml(top)+'</td></tr>';
  }
  h+='</table>';box.innerHTML=h;
}
async function loadConfig(){
  const d=await jget('/api/config');
  document.getElementById('c-model').value=d.AI_MODEL||'';
  document.getElementById('c-url').value=d.AI_BASE_URL||'';
  document.getElementById('c-key').value=d.AI_API_KEY||'';
  document.getElementById('c-prompt').value=d.AI_SYSTEM_PROMPT||'';
  document.getElementById('c-tools').value=(d.ENABLE_GROUP_TOOLS||'').toLowerCase()==='false'?'false':'true';
  document.getElementById('c-image').value=(d.ENABLE_IMAGE_SEND||'').toLowerCase()==='false'?'false':'true';
  document.getElementById('c-search').value=(d.AI_WEB_SEARCH||'').toLowerCase()==='false'?'false':'true';
}
async function saveConfig(){
  const d={
    AI_MODEL:document.getElementById('c-model').value.trim(),
    AI_BASE_URL:document.getElementById('c-url').value.trim(),
    AI_API_KEY:document.getElementById('c-key').value.trim(),
    AI_SYSTEM_PROMPT:document.getElementById('c-prompt').value,
    ENABLE_GROUP_TOOLS:document.getElementById('c-tools').value,
    ENABLE_IMAGE_SEND:document.getElementById('c-image').value,
    AI_WEB_SEARCH:document.getElementById('c-search').value
  };
  if(!d.AI_MODEL){delete d.AI_MODEL;}
  if(!d.AI_BASE_URL){delete d.AI_BASE_URL;}
  if(!d.AI_API_KEY){delete d.AI_API_KEY;}
  if(!d.AI_SYSTEM_PROMPT.trim()){delete d.AI_SYSTEM_PROMPT;}
  const r=await jpost('/api/config',d);
  toast(r.ok?'已保存，重启机器人生效':(r.error||'保存失败'));
}
async function loadLogs(){
  const which=document.getElementById('log-which').value;
  const d=await jget('/api/logs?which='+which+'&lines=60');
  document.getElementById('log-box').value=d.text||'（暂无日志）';
  document.getElementById('log-box').scrollTop=document.getElementById('log-box').scrollHeight;
}
refresh();loadSched();loadLogs();loadGroupStats();loadConfig();
setInterval(()=>{refresh();loadGroupStats();},5000);
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _authed(self) -> bool:
        """设置了密码就必须带有效 cookie；未设置密码则只允许本机访问。"""
        if not PANEL_PASSWORD:
            return self.client_address[0] in ("127.0.0.1", "::1", "localhost")
        cookie = self.headers.get("Cookie", "")
        return f"{_AUTH_COOKIE}={_auth_token()}" in cookie

    def _deny(self):
        if self.path.startswith("/api/"):
            self._json({"error": "unauthorized"}, 401)
        else:
            self._send(LOGIN_HTML.encode("utf-8"), "text/html; charset=utf-8", 401)

    def _send(self, body: bytes, content_type: str, code: int = 200):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8", code)

    def do_GET(self):
        if not self._authed():
            self._deny()
            return
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            self._send(HTML.encode("utf-8"), "text/html; charset=utf-8")
        elif path == "/api/status":
            self._json(get_status())
        elif path == "/api/schedule":
            self._json({
                "tasks": scheduler.load_tasks(),
                "groups": scheduler.list_groups(),
            })
        elif path == "/api/groupstats":
            rows = groups.stats()
            known = scheduler.list_groups()
            for row in rows:
                row["name"] = (known.get(row.get("group")) or {}).get("name", "")
            self._json({"groups": rows})
        elif path == "/api/config":
            self._json(load_config())
        elif path == "/api/logs":
            qs = parse_qs(parsed.query)
            which = (qs.get("which", ["qq"])[0] or "qq").lower()
            try:
                lines = int(qs.get("lines", ["50"])[0])
            except Exception:
                lines = 50
            files = {
                "qq": os.path.join(HOME, "qq-bot.log"),
                "oc": os.path.join(HOME, "openclaw.log"),
                "panel": os.path.join(HOME, "panel.log"),
            }
            text = _read_tail(files.get(which, files["qq"]), lines)
            self._json({"text": text})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}

        if parsed.path == "/api/login":
            ok = bool(PANEL_PASSWORD) and payload.get("password") == PANEL_PASSWORD
            if ok:
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header(
                    "Set-Cookie",
                    f"{_AUTH_COOKIE}={_auth_token()}; Path=/; HttpOnly; Max-Age=604800",
                )
                body = b'{"ok":true}'
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self._json({"error": "bad password"}, 401)
            return

        if not self._authed():
            self._deny()
            return

        if parsed.path == "/api/action":
            cmd = (payload.get("cmd") or "").strip()
            allowed = {
                "start", "stop", "start-qq", "start-oc", "stop-qq", "stop-oc",
                "watch", "watch-stop",
            }
            if cmd not in allowed:
                self._json({"ok": False, "error": "不允许的命令"}, 400)
                return
            try:
                out = subprocess.run(
                    ["bash", os.path.join(HOME, "bot.sh"), cmd],
                    capture_output=True, text=True, timeout=90,
                )
                output = (out.stdout or "") + (out.stderr or "")
                self._json({"ok": out.returncode == 0, "output": output.strip()[-800:]})
            except Exception as exc:  # noqa: BLE001
                self._json({"ok": False, "error": str(exc)}, 500)
            return

        if parsed.path == "/api/config":
            try:
                save_config(payload)
                self._json({"ok": True})
            except Exception as exc:  # noqa: BLE001
                self._json({"ok": False, "error": str(exc)}, 500)
            return

        if parsed.path == "/api/group-name":
            ok = scheduler.rename_group(
                payload.get("openid", ""), payload.get("name", "")
            )
            self._json({"ok": ok})
            return

        if parsed.path == "/api/schedule":
            action = (payload.get("action") or "").strip()
            try:
                if action == "add":
                    task = scheduler.add_task(
                        payload.get("time", ""),
                        payload.get("text", ""),
                        payload.get("scope", "all"),
                    )
                    self._json({"ok": True, "task": task})
                elif action == "del":
                    self._json({"ok": scheduler.del_task(payload.get("id", ""))})
                elif action == "toggle":
                    self._json({"ok": scheduler.set_enabled(
                        payload.get("id", ""), bool(payload.get("enabled")))})
                else:
                    self._json({"ok": False, "error": "未知操作"}, 400)
            except Exception as exc:  # noqa: BLE001
                self._json({"ok": False, "error": str(exc)}, 400)
            return

        self._json({"error": "not found"}, 404)


def main():
    exposed = PANEL_HOST not in ("127.0.0.1", "localhost", "::1")
    if exposed and not PANEL_PASSWORD:
        print("拒绝启动：PANEL_HOST 已对局域网开放，但未设置 PANEL_PASSWORD。")
        print("请先在 .env 里设置 PANEL_PASSWORD=你的密码，再重启面板。")
        sys.exit(1)
    server = ThreadingHTTPServer((PANEL_HOST, PANEL_PORT), Handler)
    print(f"管理面板已启动：http://{PANEL_HOST}:{PANEL_PORT}")
    if exposed:
        print("已对局域网开放，访问需要面板密码。")
    elif PANEL_PASSWORD:
        print("已启用密码保护。")
    else:
        print("仅本机可访问。局域网访问请在 .env 设置 PANEL_HOST=0.0.0.0 并设置 PANEL_PASSWORD。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
