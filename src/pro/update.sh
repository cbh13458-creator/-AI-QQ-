#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
#  一键更新：从 GitHub 拉取最新发布包
#  只覆盖程序文件，保留你的 .env / 记忆 / 定时任务 / 激活状态
#  用法：bash ~/update.sh          检查并更新
#        bash ~/update.sh --check  只检查是否有新版本
#        bash ~/update.sh --force  强制重新下载覆盖
# ============================================================
REPO="cbh13458-creator/chashuijian"
DIR="$HOME"
cd "$DIR" || exit 1

# 判断是普通版还是 Pro 版
if [ -f "$DIR/activate.sh" ] || [ -f "$DIR/keys.dat" ]; then
  ASSET="android-bot-pro.zip"; EDITION="pro"; NAME="Pro 版"
else
  ASSET="android-bot-normal.zip"; EDITION="normal"; NAME="普通版"
fi

LOCAL_VER=$(cat "$DIR/VERSION" 2>/dev/null || echo "未知")
echo "当前版本：$LOCAL_VER（$NAME）"
echo "正在检查 GitHub 最新发布..."

REL_JSON=$(curl -sfL --max-time 20 "https://api.github.com/repos/$REPO/releases/latest") || {
  echo "❌ 无法访问 GitHub，请检查网络后重试。"; exit 1; }

URL=$(printf '%s' "$REL_JSON" | python3 -c "
import json,sys
d=json.load(sys.stdin)
for a in d.get('assets',[]):
    if a.get('name')=='$ASSET':
        print(a.get('browser_download_url','')); break
")
TAG=$(printf '%s' "$REL_JSON" | python3 -c "import json,sys;print(json.load(sys.stdin).get('tag_name','') or '')")
[ -z "$URL" ] && { echo "❌ 最新发布里没有找到 $ASSET"; exit 1; }
echo "最新版本：$TAG"

if [ "${1:-}" = "--check" ]; then
  echo "下载地址：$URL"
  exit 0
fi

TAG_VER=${TAG#v}
FORCE=0
[ "${1:-}" = "--force" ] && FORCE=1
if [ "$FORCE" -eq 0 ] && [ -n "$TAG_VER" ] && [ "$TAG_VER" = "$LOCAL_VER" ]; then
  echo "✅ 已是最新版本（$LOCAL_VER）。如需强制重装：bash ~/update.sh --force"
  exit 0
fi

TMP=$(mktemp -d) || exit 1
echo "下载中..."
curl -fL --max-time 180 -o "$TMP/pkg.zip" "$URL" || { echo "❌ 下载失败"; rm -rf "$TMP"; exit 1; }
python3 -m zipfile -e "$TMP/pkg.zip" "$TMP/x" || { echo "❌ 解压失败"; rm -rf "$TMP"; exit 1; }
SRC="$TMP/x/$EDITION"
[ -d "$SRC" ] || { echo "❌ 包结构异常（缺少 $EDITION 目录）"; rm -rf "$TMP"; exit 1; }

BACKUP="$DIR/backup/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP"
echo "备份现有程序文件到 $BACKUP ..."
for rel in qq-bot/ai.py qq-bot/config.py qq-bot/main.py qq-bot/groups.py qq-bot/scheduler.py qq-bot/panel.py qq-bot/requirements.txt bot.sh setup.sh boot-start.sh update.sh watchdog.sh health-check.sh activate.sh README.md VERSION; do
  if [ -f "$DIR/$rel" ]; then
    mkdir -p "$BACKUP/$(dirname "$rel")"
    cp -p "$DIR/$rel" "$BACKUP/$rel"
  fi
done

echo "覆盖程序文件（保留配置）..."
find "$SRC" -type f | while read -r f; do
  rel="${f#"$SRC"/}"
  case "$rel" in
    *.apk)
      continue ;;
    qq-bot/.env|qq-bot/memory.json|qq-bot/groupstats.json|qq-bot/schedule.json|qq-bot/schedule.state.json|qq-bot/.groups.json|keys.dat|.pro_activated|.pro_keys_used|*.log)
      echo "  保留 $rel"; continue ;;
  esac
  mkdir -p "$DIR/$(dirname "$rel")"
  cp -f "$f" "$DIR/$rel"
done

chmod +x "$DIR"/*.sh 2>/dev/null || true

echo "更新 Python 依赖..."
pip install -r "$DIR/qq-bot/requirements.txt" >/dev/null 2>&1 || \
  pip install --break-system-packages -r "$DIR/qq-bot/requirements.txt" >/dev/null 2>&1 || true

rm -rf "$TMP"
echo ""
echo "✅ 更新完成：$LOCAL_VER -> $TAG"
echo "   备份在：$BACKUP"
echo "   你的 .env / 记忆 / 定时任务 / 激活状态 均已保留"
echo ""
echo "重启机器人生效："
echo "   bash ~/bot.sh stop && bash ~/bot.sh start"
