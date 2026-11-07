#!/data/data/com.termux/files/usr/bin/bash
# QQ 机器人 + 微信龙虾 后台管理器（Pro 版：清幽灵锁 + 内存限制 + 日志轮转）
STATE="$HOME/.botstate"
LOG_QQ="$HOME/qq-bot.log"
LOG_OC="$HOME/openclaw.log"
DIR_QQ="$HOME/qq-bot"
mkdir -p "$STATE"

# 限制 Node 内存，防止低内存手机 OOM 被杀
export NODE_OPTIONS="--max-old-space-size=512"

is_qq() { pgrep -f "main\.py" >/dev/null 2>&1; }
is_oc() { pgrep -f "openclaw" >/dev/null 2>&1; }

# 日志轮转：超过 5MB 截断保留末尾 200 行
rotate_log() {
  local f="$1" max=5242880 sz
  [ -f "$f" ] || return 0
  sz=$(wc -c < "$f" 2>/dev/null || echo 0)
  if [ "$sz" -gt "$max" ]; then
    tail -n 200 "$f" > "$f.tmp" 2>/dev/null && mv "$f.tmp" "$f"
  fi
}

fmt_uptime() {
  local f="$1" s now d
  [ -f "$f" ] || { printf '未知'; return; }
  s=$(cat "$f"); now=$(date +%s); d=$((now-s))
  printf '%d天%d时%d分%d秒' $((d/86400)) $((d%86400/3600)) $((d%3600/60)) $((d%60))
}

start_qq() {
  if is_qq; then echo "QQ 机器人：已在运行"; return; fi
  panel_sync_bg
  rotate_log "$LOG_QQ"
  ( cd "$DIR_QQ" && nohup python main.py >>"$LOG_QQ" 2>&1 & )
  date +%s > "$STATE.qq.start"
  echo "QQ 机器人：已启动"
}
start_oc() {
  if is_oc; then echo "微信龙虾：已在运行"; return; fi
  # 清幽灵锁：上次非正常退出留下的锁文件
  rm -f "$HOME"/.openclaw/tmp/openclaw-*/gateway*lock* 2>/dev/null
  rotate_log "$LOG_OC"
  nohup openclaw gateway run --force >>"$LOG_OC" 2>&1 &
  date +%s > "$STATE.oc.start"
  echo "微信龙虾：已启动"
}
stop_qq() {
  if is_qq; then pkill -f "main\.py"; echo "QQ 机器人：已停止"; else echo "QQ 机器人：本来就没在跑"; fi
}
stop_oc() {
  if is_oc; then pkill -f "openclaw"; echo "微信龙虾：已停止"; else echo "微信龙虾：本来就没在跑"; fi
}

status() {
  echo "================ 机器人状态 ================"
  if is_qq; then echo "QQ 机器人：运行中，已跑 $(fmt_uptime "$STATE.qq.start")"; else echo "QQ 机器人：已停止"; fi
  if is_oc; then echo "微信龙虾：运行中，已跑 $(fmt_uptime "$STATE.oc.start")"; else echo "微信龙虾：已停止"; fi
  echo "============================================"
}

start_all() {
  if ! check_activated; then return 1; fi
  start_qq; start_oc
}
stop_all() { stop_qq; stop_oc; }

# 单独启动也走激活门禁
start_qq_checked() { check_activated && start_qq; }
start_oc_checked() { check_activated && start_oc; }

# ============ 定时消息（QQ 独占）============
SCHED_PY="$HOME/qq-bot/scheduler.py"
sched() { python "$SCHED_PY" "$@"; }
sched_menu() {
  while :; do
    echo ""
    echo "---- 定时消息（QQ 群）----"
    python "$SCHED_PY" list
    echo " 1) 新增定时消息"
    echo " 2) 删除定时消息"
    echo " 3) 暂停 / 恢复"
    echo " 4) 查看已知群"
    echo " 0) 返回"
    printf "请选择: "; read -r c
    case "$c" in
      1)
        read -rp "发送时间(HH:MM，如 08:00): " _t
        read -rp "发送内容: " _x
        read -rp "目标 [all=所有已知群 / group:群ID / c2c:openid] (默认all): " _s
        python "$SCHED_PY" add "$_t" "$_x" --scope "${_s:-all}"
        ;;
      2)
        read -rp "要删除的任务ID: " _id
        python "$SCHED_PY" del "$_id"
        ;;
      3)
        read -rp "任务ID: " _id
        read -rp "输入 on 恢复 / off 暂停: " _sw
        python "$SCHED_PY" "$_sw" "$_id"
        ;;
      4) python "$SCHED_PY" groups ;;
      0) break ;;
      *) echo "无效选项" ;;
    esac
  done
}

# ============ 断线自愈（看门狗）============
WATCH_LOG="$HOME/watchdog.log"
watch_start() {
  if pgrep -f "bot\.sh watch" >/dev/null 2>&1; then
    echo "断线守护已在运行（日志：$WATCH_LOG）"
    return
  fi
  nohup bash "$HOME/bot.sh" watch >> "$WATCH_LOG" 2>&1 &
  echo "断线守护已启动：每 30 秒检查一次，掉线自动拉起"
}
watch_stop() {
  if pkill -f "bot\.sh watch" >/dev/null 2>&1; then
    echo "断线守护已停止"
  else
    echo "断线守护本来就没运行"
  fi
}
watch_loop() {
  echo "[$(date '+%F %T')] 断线守护启动，每 30 秒检查一次"
  local watch_oc=0
  command -v openclaw >/dev/null 2>&1 && [ -f "$STATE.oc.start" ] && watch_oc=1
  while :; do
    if ! is_qq; then
      echo "[$(date '+%F %T')] QQ 机器人掉线，自动重启..."
      start_qq
    fi
    if [ "$watch_oc" = "1" ] && ! is_oc; then
      echo "[$(date '+%F %T')] 微信龙虾掉线，自动重启..."
      start_oc
    fi
    sleep 30
  done
}

# ============ 管理面板 ============
panel_start() {
  if pgrep -f "panel\.py" >/dev/null 2>&1; then
    echo "管理面板已在运行：http://127.0.0.1:8080"
    return
  fi
  nohup python "$HOME/qq-bot/panel.py" >> "$HOME/panel.log" 2>&1 &
  sleep 1
  echo "管理面板已启动：http://127.0.0.1:8080"
  echo "（手机浏览器打开；局域网访问请在 .env 设置 PANEL_HOST=0.0.0.0）"
}
panel_stop() {
  if pkill -f "panel\.py" >/dev/null 2>&1; then echo "管理面板已停止"; else echo "管理面板本来就没运行"; fi
}
panel_toggle() {
  if pgrep -f "panel\.py" >/dev/null 2>&1; then panel_stop; else panel_start; fi
}

# ============ 官方指令面板同步 ============
PANEL_SYNC_LOG="$HOME/panel-setup.log"
PANEL_STAMP="$DIR_QQ/.panel.synced"
panel_sync() {
  local force="${1:-}" ver
  [ -f "$DIR_QQ/panel_setup.py" ] || return 0
  ver=$(cat "$HOME/VERSION" 2>/dev/null || echo "")
  if [ -z "$force" ] && [ -f "$PANEL_STAMP" ] && [ "$(cat "$PANEL_STAMP" 2>/dev/null)" = "$ver" ]; then
    return 0
  fi
  if ( cd "$DIR_QQ" && python panel_setup.py >> "$PANEL_SYNC_LOG" 2>&1 ); then
    printf '%s' "$ver" > "$PANEL_STAMP"
  fi
}
panel_sync_bg() { ( panel_sync ) >/dev/null 2>&1 & }

# ============ 一键更新（保留配置）============
do_update() { bash "$HOME/update.sh"; }

check_activated() {
  ACTIVATED_FILE="$HOME/.pro_activated"
  KEYS_FILE="$HOME/keys.dat"
  # 如果 keys.dat 不存在（比如被删了），放行（兼容手动部署）
  [ ! -f "$KEYS_FILE" ] && return 0
  if [ ! -f "$ACTIVATED_FILE" ]; then
    echo "❌ Pro 版未激活，请先运行：bash ~/activate.sh"
    return 1
  fi
  # 校验设备绑定
  DEVICE_ID=$(getprop ro.serialno 2>/dev/null)
  [ -z "$DEVICE_ID" ] && DEVICE_ID="$(hostname)-$(stat -c %i /data/data/com.termux 2>/dev/null || echo unknown)"
  SAVED=$(cat "$ACTIVATED_FILE" 2>/dev/null)
  CUR=$(echo -n "$DEVICE_ID" | sha256sum | cut -d' ' -f1)
  if [ "$SAVED" != "$CUR" ]; then
    echo "❌ 激活凭证与设备不匹配，请重新运行：bash ~/activate.sh"
    return 1
  fi
  return 0
}

case "${1:-menu}" in
  start)       start_all; watch_start; status ;;
  stop)        watch_stop; stop_all ;;
  start-qq)    start_qq_checked && watch_start ;;
  start-oc)    start_oc_checked ;;
  stop-qq)     watch_stop; stop_qq ;;
  stop-oc)     stop_oc ;;
  watch)       watch_start ;;
  watch-stop)  watch_stop ;;
  watch-log)   tail -n 40 "$WATCH_LOG" ;;
  watch-fg)    watch_loop ;;
  status|st)   status ;;
  sched)       shift; sched "$@" ;;
  panel)       panel_toggle ;;
  panel-sync)  panel_sync force ;;
  update)      do_update ;;
  menu|"")
    while :; do
      echo ""
      echo "======== 机器人后台管理（Pro）========"
      echo " 1) 只启动 QQ"
      echo " 2) 一键启动 QQ+微信"
      echo " 3) 只启动微信"
      echo " 4) 查看状态 / 运行时长"
      echo " 5) 停止全部"
      echo " 6) 看 QQ 日志(最近30行)"
      echo " 7) 看微信日志(最近30行)"
      echo " 8) 健康检查"
      echo " 9) 激活 Pro 版"
      echo "10) 定时消息（QQ 专属）"
      echo "11) 管理面板 开/关"
      echo "12) 检查并更新版本"
      echo "13) 开启断线守护"
      echo "14) 关闭断线守护"
      echo " 0) 退出"
      printf "请选择: "; read -r c
      case "$c" in
        1) start_qq_checked && watch_start ;;
        2) start_all; watch_start ;;
        3) start_oc_checked ;;
        4) status ;;
        5) watch_stop; stop_all ;;
        6) tail -n 30 "$LOG_QQ" ;;
        7) tail -n 30 "$LOG_OC" ;;
        8) bash "$HOME/health-check.sh" ;;
        9) bash "$HOME/activate.sh" ;;
        10) sched_menu ;;
        11) panel_toggle ;;
        12) do_update ;;
        13) watch_start ;;
        14) watch_stop ;;
        0) break ;;
        *) echo "无效选项" ;;
      esac
    done ;;
  *)
    echo "用法: bash ~/bot.sh [命令]"
    echo ""
    echo "命令:"
    echo "  start       启动 QQ + 微信（默认，需先激活，自动开启断线守护）"
    echo "  start-qq    只启动 QQ（需先激活，自动开启断线守护）"
    echo "  start-oc    只启动微信（需先激活）"
    echo "  stop        停止全部"
    echo "  stop-qq     只停止 QQ"
    echo "  stop-oc     只停止微信"
    echo "  status      查看状态"
    echo "  watch       开启断线守护（掉线自动拉起）"
    echo "  watch-stop  关闭断线守护"
    echo "  watch-log   查看守护日志"
    echo "  sched      定时消息管理（QQ 专属，可加 list/add/del 等子命令）"
    echo "  panel      开/关管理面板（http://127.0.0.1:8080）"
    echo "  panel-sync 重新同步官方 / 指令面板"
    echo "  update     检查并从 GitHub 更新（保留你的配置）"
    echo "  (无参数)    进入菜单"
    ;;
esac
