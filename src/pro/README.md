# QQ AI 机器人 + 微信龙虾 安卓版（Pro 版）

在普通版基础上增加：**随机网关密钥、进程守护、健康检查、日志轮转、内存限制、一次性激活密钥**，适合追求稳定运行的用户。

> Pro 版同样包含 v1.2.5 新功能：面板密码保护、记忆条数可调、每人频率/每日限额、昵称设置、引用防循环、群签到 / 积分排行榜 / 群热词、断线自愈、官方指令面板自动同步、定时消息、摸摸、联网搜索、管理面板、一键更新（保留配置）。

## Pro 版相比普通版的优化

| 优化项 | 说明 |
|--------|------|
| 随机网关密钥 | 安装时自动生成 48 位随机 token，固化到 OpenClaw 配置，避免重启后 token 变化 |
| 一次性激活密钥 | Pro 版需输入激活密钥才能使用，密钥一用即废，并绑定设备 |
| 进程守护 watchdog | 监控 QQ + 龙虾进程，挂了自动拉起（每 30 秒检查） |
| 健康检查 | 一键检测进程、网关端口、微信渠道状态 |
| 日志轮转 | 日志超过 5MB 自动截断保留末尾，防止无限增长 |
| Node 内存限制 | 限制 512MB，防止低内存手机被系统 OOM 杀 |
| 开机自启增强 | 等待网络就绪后再启动，失败自动重试 |

## 安装与激活

1. 安装 `apk/` 里的三个 APK
2. 打开一次 Termux:Boot
3. 拷文件到 `$HOME`，执行：
   ```bash
   bash setup.sh
   ```
4. 按提示填写 QQ 凭证、选择 AI 厂家
5. **激活 Pro 版**（必须，否则无法启动）：
   ```bash
   bash ~/activate.sh
   ```
   输入你拿到的激活密钥（格式 `ABOT-XXXX-XXXX-XXXX`，一次性，绑定本设备）
6. 绑定微信：
   ```bash
   openclaw channels login --channel openclaw-weixin
   ```

## 日常管理

```bash
bash ~/bot.sh start        # 启动 QQ + 微信（未激活会提示先激活）
bash ~/bot.sh start-qq     # 只启动 QQ
bash ~/bot.sh start-oc     # 只启动微信
bash ~/bot.sh status       # 状态
bash ~/bot.sh stop         # 停止全部
bash ~/bot.sh stop-qq      # 只停止 QQ
bash ~/bot.sh stop-oc      # 只停止微信
bash ~/bot.sh sched        # 定时消息管理（QQ 专属）
bash ~/bot.sh panel        # 开/关网页管理面板
bash ~/bot.sh watch        # 开启断线守护（掉线自动拉起）
bash ~/bot.sh watch-stop   # 关闭断线守护
bash ~/bot.sh update       # 检查并更新版本
bash ~/watchdog.sh &       # 启动进程守护（QQ + 龙虾，挂了自动拉起）
bash ~/health-check.sh     # 健康检查
bash ~/activate.sh         # 激活（仅需一次）
```

## 定时消息 / 管理面板 / 一键更新

- **定时消息**：`bash ~/bot.sh sched`，先让机器人在群里被 @ 一次，再添加任务。QQ 主动消息有官方配额限制。
- **管理面板**：`bash ~/bot.sh panel`，手机浏览器打开 `http://127.0.0.1:8080`，可看状态、启停、开关断线守护、管理定时消息、查看群签到数据、改模型/人格、看日志。
- **群互动**：群里 @机器人 发「签到 / 排行榜 / 我的积分 / 词云」即可使用。
- **一键更新**：`bash ~/update.sh`，自动拉取最新版本，会备份旧文件，并**保留** `.env`、记忆、定时任务、Pro 激活状态与密钥池。

## 只用 QQ 或只用微信

两个通道互相独立，可以只跑其中一个（Pro 版均需先激活）：

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

编辑 `qq-bot/.env`，支持智谱、OpenAI、DeepSeek、自定义。见 `.env.example`。

## 开机自启

给 Termux 放行自启动、耗电无限制、关电池优化。重启后 watchdog 自动启动守护（未激活则跳过）。
