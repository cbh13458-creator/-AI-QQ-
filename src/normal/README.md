# QQ AI 机器人 + 微信龙虾 安卓版（普通版）

在安卓 Termux 上一键部署 QQ AI 机器人 + 微信（OpenClaw）机器人。

## 包含

- `qq-bot/` —— QQ 机器人（文字、图片、表情包、视频、联网搜索、多厂家 AI、摸摸、定时消息）
- `setup.sh` —— 一键安装脚本
- `bot.sh` —— 启停/状态/定时消息/面板管理
- `boot-start.sh` —— 开机自启
- `update.sh` —— 一键更新（保留你的配置）
- `apk/` —— Termux、Termux:Boot、Termux:API 安装包

## ✨ 功能亮点（v1.2.5）

| 功能 | 说明 | 通道 |
|------|------|------|
| 引用防循环 | 群友引用机器人自己的回复时不再复读，只对新增内容作答 | **QQ 独占** |
| 面板密码 | 管理面板支持登录密码（PANEL_PASSWORD）；对局域网开放时强制要求密码 | 面板 |
| 记忆可调 | 每个会话的记忆条数可配置（AI_MEMORY_MESSAGES，默认 20 条） | QQ |
| 每人限额 | 每人每分钟 / 每天触发 AI 回复次数限制（AI_RATE_PER_MINUTE / AI_RATE_PER_DAY），防刷爆额度 | QQ |
| 群签到 / 积分 | 群友发「签到」攒积分，连签有奖励 | **QQ 独占** |
| 昵称设置 | `/昵称 名字` 自定义排行榜显示名（官方接口拿不到 QQ 昵称） | **QQ 独占** |
| 积分排行榜 | 发「排行榜」看群内前 10 名 | **QQ 独占** |
| 群热词 | 发「词云」看群里最近在聊什么 | **QQ 独占** |
| 断线自愈 | 掉线 30 秒内自动拉起，不用手动重启 | **QQ 独占** |
| 定时消息 | 每天固定时间自动在群里发消息 | **QQ 独占** |
| 摸摸互动 | @机器人发「摸摸 / 拍拍 / 抱抱」有回应 | **QQ 独占** |
| 看图片/表情包 | 群友发图、发表情包，机器人都能看懂并回应 | QQ |
| 联网搜索 | 默认开启，走免费必应搜索，无需额外 Key，问实时信息自动搜网 | QQ |
| 管理面板 | 网页版可视化后台，手机浏览器打开就能用 | QQ |
| 官方指令面板 | 首次启动自动创建/补齐，输入 `/` 就能看到全部指令 | QQ |
| 群名备注 | 面板里给群起名字，定时目标不再显示一长串乱码 | QQ |
| 一键更新 | 自动拉取新版本，**不改动你的设置** | QQ |

> 微信（OpenClaw）通道支持文字对话；定时消息、摸摸是 QQ 侧功能。

## 安装

1. 安装 `apk/` 里的三个 APK（Termux、Termux:Boot、Termux:API）
2. 打开一次 Termux:Boot（激活开机广播）
3. 把本目录所有文件拷到 Termux 的 `$HOME`
4. 执行：
   ```bash
   bash setup.sh
   ```
5. 按提示填写 QQ 凭证、选择 AI 厂家并填 API Key
6. 绑定微信：
   ```bash
   openclaw channels login --channel openclaw-weixin
   ```

## 日常管理

```bash
bash ~/bot.sh start       # 启动 QQ + 微信
bash ~/bot.sh start-qq    # 只启动 QQ
bash ~/bot.sh start-oc    # 只启动微信
bash ~/bot.sh status      # 查看状态
bash ~/bot.sh stop        # 停止全部
bash ~/bot.sh stop-qq     # 只停止 QQ
bash ~/bot.sh stop-oc     # 只停止微信
bash ~/bot.sh sched       # 定时消息管理（QQ 专属）
bash ~/bot.sh panel       # 开/关网页管理面板
bash ~/bot.sh panel-sync  # 手动重新同步官方 / 指令面板
bash ~/bot.sh watch       # 开启断线守护（掉线自动拉起）
bash ~/bot.sh watch-stop  # 关闭断线守护
bash ~/bot.sh update      # 检查并更新版本
bash ~/bot.sh             # 进入菜单
```

> `start` / `start-qq` 会自动开启断线守护；`stop` / `stop-qq` 会一并关闭。

## 群互动（QQ 独占）

在群里 @机器人 发以下指令（也可以带 `/`）：

| 指令 | 作用 |
|------|------|
| 签到 / 打卡 | 每天一次，+10 积分，连签有额外奖励 |
| 昵称 / 改名 | `/昵称 张三` 设置排行榜里显示的名字 |
| 排行榜 / 积分榜 | 群积分前 10 名 |
| 我的积分 | 自己的积分、连签天数、群内排名 |
| 词云 / 热词 | 群里最近 @机器人 聊天的热词 TOP |

数据保存在 `qq-bot/groupstats.json`；不想要这些功能，在 `.env` 里设 `ENABLE_GROUP_TOOLS=false`。

## 定时消息（QQ 独占）

```bash
bash ~/bot.sh sched                 # 打开交互式管理
bash ~/bot.sh sched add 08:00 早安   # 每天 8 点在所有已知群发「早安」
bash ~/bot.sh sched list            # 查看所有任务
bash ~/bot.sh sched groups          # 查看已知群
bash ~/bot.sh sched del <任务ID>     # 删除任务
```

> 先让机器人在群里被 @ 一次，它才会记住这个群；之后定时消息才能发进去。
> QQ 主动消息有官方配额，超限会发送失败（日志里能看到原因）。

## 管理面板（小白友好）

```bash
bash ~/bot.sh panel        # 启动面板
```

启动后用手机浏览器打开 `http://127.0.0.1:8080`，可以：
- 查看 QQ / 微信运行状态、运行时长、断线守护状态
- 一键启动 / 停止 / 开关断线守护
- 添加、暂停、删除定时消息
- 查看群签到与积分排行数据
- 直接改模型、接口地址、API Key、人格设定（改完重启生效）
- 查看日志

> 想让同一局域网的电脑也能访问，在 `qq-bot/.env` 里设置 `PANEL_HOST=0.0.0.0` 后重启面板。

## 一键更新（保留配置）

```bash
bash ~/update.sh           # 检查并更新
bash ~/update.sh --check   # 只检查是否有新版本
```

更新时会：
- ✅ 覆盖程序代码（`ai.py`、`main.py`、`bot.sh` 等）
- ✅ 自动备份旧文件到 `~/backup/时间戳/`
- ✅ **保留** `.env`（API Key / QQ 凭证）、记忆、定时任务、Pro 激活状态
- ❌ 不会动你的 APK 和 OpenClaw 绑定

## 只用 QQ 或只用微信

两个通道互相独立，可以只跑其中一个：

**只用 QQ：**
1. 填好 `qq-bot/.env` 里的 QQ 凭证
2. 不要执行 `openclaw channels login`（不绑微信）
3. 启动：`bash ~/bot.sh start-qq`

**只用微信：**
1. 执行 `openclaw channels login --channel openclaw-weixin` 绑定微信
2. `qq-bot/.env` 里的 QQ 凭证可以不填（QQ 机器人不会启动）
3. 启动：`bash ~/bot.sh start-oc`

> 开机自启默认两个都启动。如果只想自启其中一个，编辑 `~/.termux/boot/start.sh`，把 `bash "$HOME/bot.sh" start` 改成 `start-qq` 或 `start-oc`。

## AI 厂家配置

编辑 `qq-bot/.env`，支持：智谱、OpenAI、DeepSeek、自定义 OpenAI 兼容接口。见 `.env.example`。

## 开机自启

设置里给 Termux 放行：自启动权限、耗电保护设为「无限制」、电池优化关闭。重启后自动拉起。
