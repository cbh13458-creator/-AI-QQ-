# -AI-QQ- 🤖

一台安卓手机同时跑起 **QQ + 微信 AI 机器人**，支持多家大模型，自带开机自启、定时消息、网页管理面板和一键更新。

> **QQ 和微信互相独立，可以只用 QQ、只用微信，或者两个都用。**
> 定时消息、摸摸互动、图片/表情包理解为 QQ 侧功能；微信（OpenClaw）通道支持文字对话。

---

## 📥 下载

| 版本 | 下载 | 说明 |
|------|------|------|
| 🟢 普通版 | [android-bot-normal.zip](https://github.com/cbh13458-creator/-AI-QQ-/releases/latest/download/android-bot-normal.zip) | 多 AI 厂家 + 一键部署 + 开机自启 |
| 🔴 Pro 版 | [android-bot-pro.zip](https://github.com/cbh13458-creator/-AI-QQ-/releases/latest/download/android-bot-pro.zip) | 普通版全部功能 + 一次性激活密钥、进程守护、健康检查、日志轮转、内存限制 |

前往 [Releases 页面](https://github.com/cbh13458-creator/-AI-QQ-/releases) 查看全部版本与更新日志。

---

## ✨ 功能一览（v1.1.0）

| 功能 | 说明 | 通道 |
|------|------|------|
| 多 AI 厂家 | 智谱 / OpenAI / DeepSeek / 自定义 OpenAI 兼容接口 | QQ + 微信 |
| 定时消息 | 每天固定时间自动在群里发消息 | **QQ 独占** |
| 摸摸互动 | @机器人发「摸摸 / 拍拍 / 抱抱」会有回应 | **QQ 独占** |
| 看图片 / 表情包 | 群友发图、发表情包，机器人都能看懂并回应 | QQ |
| 联网搜索 | 默认开启，问实时信息会自动搜网 | QQ |
| 网页管理面板 | 手机浏览器打开 `http://127.0.0.1:8080`，看状态 / 启停 / 管定时消息 / 看日志 | QQ |
| 一键更新 | `bash ~/update.sh`，自动拉新版且**不改动你的配置** | QQ |
| 开机自启 | Termux:Boot 自动拉起 | QQ + 微信 |
| 进程守护（Pro） | 进程挂了自动拉起，每 30 秒检查 | Pro |
| 一次性激活密钥（Pro） | 密钥一用即废，绑定设备 | Pro |

---

## 📦 包里有什么

```
├── apk/                    # Termux 三件套安装包
├── qq-bot/                 # QQ 机器人源码
│   ├── main.py / ai.py / config.py
│   ├── scheduler.py        # 定时消息
│   ├── panel.py            # 网页管理面板
│   └── .env.example        # AI / QQ 配置模板
├── setup.sh                # 一键安装
├── bot.sh                  # 启停 / 状态 / 定时消息 / 面板
├── update.sh               # 一键更新（保留配置）
├── boot-start.sh           # 开机自启
├── VERSION                 # 版本号
└── (Pro) activate.sh / watchdog.sh / health-check.sh / keys.dat
```

---

## 🎯 三种使用方式

QQ 和微信是两个独立进程，**想用哪个就启动哪个**。

### 方式一：QQ + 微信都用（默认）

```bash
bash ~/bot.sh start
```

### 方式二：只用 QQ（不需要微信）

1. 填好 `qq-bot/.env` 里的 QQ 凭证
2. **不要**执行 `openclaw channels login`
3. 启动：

```bash
bash ~/bot.sh start-qq
```

### 方式三：只用微信（不需要 QQ）

1. 绑定微信：`openclaw channels login --channel openclaw-weixin`
2. `qq-bot/.env` 里的 QQ 凭证可以不填
3. 启动：

```bash
bash ~/bot.sh start-oc
```

---

## 🚀 安装

1. 安装 `apk/` 里的三个 APK（Termux、Termux:API、Termux:Boot）
2. 打开一次 Termux:Boot App（激活开机广播）
3. 把解压后的所有文件拷到 Termux 家目录：

```bash
cp -r /sdcard/Download/android-bot/* ~/
```

4. 一键安装：

```bash
bash ~/setup.sh
```

按提示填写 QQ 凭证、选择 AI 厂家并填 API Key。

5. 绑定微信（只用 QQ 可跳过）：

```bash
openclaw channels login --channel openclaw-weixin
```

6. 启动：

```bash
bash ~/bot.sh start
```

---

## ⏰ 定时消息（QQ 独占）

```bash
bash ~/bot.sh sched                 # 交互式管理
bash ~/bot.sh sched add 08:00 早安   # 每天 8 点发「早安」
bash ~/bot.sh sched list
bash ~/bot.sh sched groups
bash ~/bot.sh sched del <任务ID>
```

> 先让机器人在群里被 @ 一次，它才会记住这个群。QQ 主动消息有官方配额，超限会失败。

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
bash ~/update.sh           # 检查并更新
bash ~/update.sh --check   # 只检查
bash ~/update.sh --force   # 强制重装
```

更新会备份旧文件到 `~/backup/时间戳/`，并**保留**：

- `qq-bot/.env`（API Key / QQ 凭证）
- `memory.json`（对话记忆）
- `schedule.json` / `.groups.json`（定时任务与群记录）
- Pro 版激活状态与密钥池
- OpenClaw 的微信绑定

> v1.0.0 用户没有 `update.sh`，请手动下载 v1.1.0 新包解压覆盖（覆盖前先备份 `qq-bot/.env`）。

---

## 🔴 Pro 版激活

```bash
bash ~/activate.sh
```

输入 `ABOT-XXXX-XXXX-XXXX` 格式的一次性密钥（向作者单独获取）。激活后绑定本设备，重启无需重复激活。

---

## 🎮 常用命令

```bash
bash ~/bot.sh                 # 菜单
bash ~/bot.sh start           # 启动 QQ + 微信
bash ~/bot.sh start-qq        # 只启动 QQ
bash ~/bot.sh start-oc        # 只启动微信
bash ~/bot.sh status          # 状态
bash ~/bot.sh stop            # 停止全部
bash ~/bot.sh sched           # 定时消息
bash ~/bot.sh panel           # 管理面板
bash ~/bot.sh update          # 检查更新
```

Pro 版额外：

```bash
bash ~/watchdog.sh &          # 进程守护
bash ~/health-check.sh        # 健康检查
```

---

## ⚙️ 开机自启

在手机设置里给 Termux 放行：

1. 自启动权限 → 允许
2. 耗电保护 / 电池优化 → 无限制
3. 允许后台运行

> 只想自启一个通道：编辑 `~/.termux/boot/start.sh`，把 `start` 改成 `start-qq` 或 `start-oc`。

---

## ⚠️ 注意事项

- 发布包内**不含任何真实 API Key 或 QQ 凭证**，全部为占位符。
- Pro 版激活密钥**不随包分发**，需向作者单独获取。
- 微信登录后不要主动退出，否则需重新扫码。
- QQ 主动消息（定时任务）受官方配额限制。

---

## ❓ 常见问题

**Q: 我只想用 QQ，微信那边会出问题吗？**
A: 不会。不绑定微信，用 `bash ~/bot.sh start-qq` 即可。

**Q: 我只想用微信，QQ 凭证不填行不行？**
A: 行，QQ 机器人没凭证会自动退出，不影响微信。

**Q: 更新会覆盖我的 API Key 吗？**
A: 不会。`update.sh` 明确保留 `.env`、记忆、定时任务和激活状态，并会先备份。

**Q: Pro 版密钥提示已使用？**
A: 密钥一次性，绑定首次激活的设备。换设备需重新获取。

---

**项目地址**：https://github.com/cbh13458-creator/-AI-QQ-
