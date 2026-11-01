# -AI-QQ- 🤖

一台安卓手机跑起 **QQ + 微信 AI 机器人**，支持多家大模型，自带开机自启、定时消息、网页管理面板和一键更新。

> QQ 和微信互相独立，可以**只用 QQ**、**只用微信**，或者**两个都用**。

---

## 📥 两种安装方式（二选一，不会搞混）

**不用下载解压、不用拷文件**，直接复制下面其中一个 TXT 的全部内容，粘贴到 Termux 里回车运行即可。

### 🅰 只用 QQ（推荐新手，最省事）

复制 [install-qq-only.txt](https://ghfast.top/https://github.com/cbh13458-creator/-AI-QQ-/releases/download/v1.1.4/install-qq-only.txt) 的全部内容粘贴到 Termux。

脚本会自动：下载完整包 → 装依赖 → 填 `.env` → 开机自启只跑 QQ。

### 🅱 QQ + 微信双用

复制 [install-qq-weixin.txt](https://ghfast.top/https://github.com/cbh13458-creator/-AI-QQ-/releases/download/v1.1.4/install-qq-weixin.txt) 的全部内容粘贴到 Termux。

脚本会自动：下载完整包 → 装 QQ 依赖 → 装微信龙虾(OpenClaw) → 微信扫码登录 → 开机自启 QQ+微信。

> 两个 TXT 各自独立完整，选一个复制粘贴就行，不需要分两步。安装过程中只需填 3 项：QQ_APP_ID、QQ_APP_SECRET、智谱 API_KEY。

### 完整包下载（手动安装备用）

| 版本 | 加速下载 | 说明 |
|------|------|------|
| 🟢 普通版 | [android-bot-normal.zip](https://ghfast.top/https://github.com/cbh13458-creator/-AI-QQ-/releases/download/v1.1.4/android-bot-normal.zip) | 多 AI 厂家 + 一键部署 + 开机自启 |
| 🔴 Pro 版 | [android-bot-pro.zip](https://ghfast.top/https://github.com/cbh13458-creator/-AI-QQ-/releases/download/v1.1.4/android-bot-pro.zip) | 普通版全部功能 + 一次性激活密钥、进程守护、健康检查、日志轮转、内存限制 |

前往 [Releases 页面](https://github.com/cbh13458-creator/-AI-QQ-/releases) 查看全部版本与更新日志。

---

## ✨ 功能一览（v1.1.4）

| 功能 | 说明 | 通道 |
|------|------|------|
| 多 AI 厂家 | 智谱 / OpenAI / DeepSeek / 自定义 OpenAI 兼容接口 | QQ + 微信 |
| **引用消息识别** | 群里引用某条消息再 @机器人，机器人能看到被引用的内容（需群设置开启「允许获取上下文」） | **QQ** |
| **发表情包 / 找图** | @机器人 说「来个猫猫表情包」「找张初音未来头像」会自动搜图发送 | **QQ** |
| 看图片 / 表情包 | @机器人 且图片在同一条消息里，机器人能看懂并回应 | QQ |
| 联网搜索 | 默认开启，走**免费必应搜索**，无需额外 Key | QQ |
| emoji 自动过滤 | 模型输出里的 emoji 表情符号会被自动去掉 | QQ + 微信 |
| 模型过载自动降级 | 主模型限流时自动切换备用模型 | QQ + 微信 |
| 定时消息 | 每天固定时间自动在群里发消息 | **QQ 独占** |
| 摸摸互动 | @机器人发「摸摸 / 拍拍 / 抱抱」会有回应 | **QQ 独占** |
| 网页管理面板 | 手机浏览器打开 `http://127.0.0.1:8080` | QQ |
| 一键更新 | `bash ~/bot.sh update`，自动拉新版且**不改动你的配置** | QQ |
| 开机自启 | Termux:Boot 自动拉起 | QQ + 微信 |
| 进程守护 / 健康检查 / 日志轮转（Pro） | — | Pro |
| 一次性激活密钥（Pro） | 密钥一用即废，绑定设备 | Pro |

---

## 🎯 日常使用

```bash
bash ~/bot.sh        # 打开菜单
```

菜单第 1 项就是「只启动 QQ」：

```
 1) 只启动 QQ          ← 默认推荐
 2) 一键启动 QQ+微信
 3) 只启动微信
 4) 查看状态 / 运行时长
 5) 停止全部
 6) 看 QQ 日志
 7) 看微信日志
 8) 定时消息（QQ 专属）
 9) 管理面板 开/关
10) 检查并更新版本
```

也可以直接命令行：

```bash
bash ~/bot.sh start-qq    # 只启动 QQ
bash ~/bot.sh start       # QQ + 微信
bash ~/bot.sh stop        # 全部停止
bash ~/bot.sh status      # 查看状态
```

---

## ⏰ 定时消息（QQ 独占）

```bash
bash ~/bot.sh sched                 # 交互式管理
bash ~/bot.sh sched add 08:00 早安   # 每天 8 点发「早安」
bash ~/bot.sh sched list
bash ~/bot.sh sched groups          # 查看机器人已记住的群
bash ~/bot.sh sched del <任务ID>
```

> 先让机器人在群里被 @ 一次，它才会记住这个群。

---

## 🖥️ 网页管理面板

```bash
bash ~/bot.sh panel
```

手机浏览器打开 `http://127.0.0.1:8080`，可查看状态、一键启停、管理定时消息、查看日志。

> 局域网访问：在 `qq-bot/.env` 设置 `PANEL_HOST=0.0.0.0` 后重启面板。

---

## 🔄 一键更新（保留配置）

```bash
bash ~/bot.sh update
```

自动拉取最新版，**不覆盖你的 `.env`、记忆、定时任务、激活状态**。也可以下载热修包手动升级：

```bash
curl -L -o ~/tmp/hfix.zip https://ghfast.top/https://github.com/cbh13458-creator/-AI-QQ-/releases/download/v1.1.4/hotfix-v1.1.4.zip
rm -rf ~/hotfix && mkdir -p ~/hotfix
python3 -m zipfile -e ~/tmp/hfix.zip ~/hotfix && bash ~/hotfix/apply.sh
```

---

## 🔴 Pro 版激活

Pro 版需要激活密钥才能启动，密钥一用即废并绑定设备：

```bash
bash ~/activate.sh
```

输入你拿到的激活密钥即可。激活后 `bash ~/bot.sh` 正常使用。

---

## ❓ 常见问题

**Q：机器人看不到我引用的消息？**
A：QQ 群设置里需要开启「允许机器人获取上下文 / @10 条附近的内容」，否则网关只给消息 ID，任何框架都读不到原文。

**Q：模型回复还带 emoji？**
A：v1.1.3+ 已加入代码级 emoji 过滤，确认 `cat ~/VERSION` 是 1.1.3 以上。

**Q：AI 调用失败 / 当前模型访问量过大？**
A：免费模型高峰期有限流，已加入自动降级到 `glm-4-flash`；也可在 `.env` 里设置 `AI_FALLBACK_MODEL`。

**Q：想换 AI 厂家或模型？**
A：编辑 `~/qq-bot/.env` 里的 `AI_BASE_URL` / `AI_MODEL` / `AI_API_KEY`，然后 `bash ~/bot.sh stop-qq && bash ~/bot.sh start-qq`。

**Q：戳一戳没反应？**
A：QQ 官方机器人 API 不推送戳一戳事件，这是平台限制，不是 bug。
