# Termux 運行 Discord Bot 簡易指南

這份文件整理常用的 Termux 操作。指令可以直接複製，但其中的使用者名稱、IP 和 Token 要換成自己的資料。

## 每次最常用的操作

啟動 Bot：

```bash
tmux new -s discordbot
~/start-discord-bot.sh
```

讓 Bot 留在背景：

1. 按 `Ctrl+B`。
2. 放開按鍵。
3. 按 `D`。

重新查看 Bot：

```bash
tmux attach -t discordbot
```

## 1. 安裝 Termux

建議從官方來源安裝：

- F-Droid：https://f-droid.org/packages/com.termux/
- GitHub：https://github.com/termux/termux-app/releases

不要混用 F-Droid、GitHub 和 Google Play 的 Termux 或外掛，否則可能因簽章不同而無法更新。

第一次開啟後執行：

```bash
pkg update
pkg upgrade
pkg install git python openssh tmux nano
```

如果更新失敗，先切換套件來源：

```bash
termux-change-repo
pkg update
pkg upgrade
```

## 2. 從電腦遠端操作 Termux

只需設定一次：

```bash
pkg install openssh
passwd
whoami
sshd
```

各指令的意思：

- `passwd`：設定 SSH 登入密碼。輸入時不會顯示文字，這是正常的。
- `whoami`：顯示 Termux 使用者名稱，例如 `u0_a123`。
- `sshd`：啟動 SSH 伺服器，預設使用 `8022` 埠。

### 查看手機 IP

到 Android 的「設定 → Wi-Fi → 目前連線的網路」查看 IP，例如：

```text
192.168.0.172
```

也可以在 Termux 嘗試：

```bash
ip addr show wlan0
```

電腦與手機必須在同一個 Wi-Fi。不要使用 `127.0.0.1`。

### 從 Windows 連線

在 PowerShell 輸入：

```powershell
ssh -p 8022 u0_a123@192.168.0.172
```

將 `u0_a123` 和 IP 換成自己的資料。

第一次連線若看到：

```text
Are you sure you want to continue connecting?
```

確認 IP 是自己的手機後輸入：

```text
yes
```

離開 SSH：

```bash
exit
```

停止手機上的 SSH 伺服器：

```bash
pkill sshd
```

## 3. 從 GitHub 下載 Bot

公開倉庫：

```bash
cd ~
git clone https://github.com/icez114514/icez-discord-bot.git
cd icez-discord-bot
```

如果 GitHub 要求 Username 和 Password，代表倉庫可能是私人的。不要輸入 GitHub 帳號密碼，改用：

```bash
pkg install gh
gh auth login
```

依畫面選擇 `GitHub.com`、`HTTPS` 和瀏覽器登入，然後執行：

```bash
gh repo clone icez114514/icez-discord-bot
```

## 4. 安裝 Bot 依賴

進入 Bot 資料夾：

```bash
cd ~/icez-discord-bot
python -m pip install -r requirements.txt
```

## 5. 永久保存 Discord Token

Token 不要放進 Git 專案，也不要傳給其他人。

建立私人設定檔：

```bash
nano ~/.discord_bot_env
```

填入：

```bash
export DISCORD_TOKEN='你的 Discord Bot Token'
```

儲存方式：

1. 按 `Ctrl+O`。
2. 按 Enter。
3. 按 `Ctrl+X` 離開。

限制檔案權限：

```bash
chmod 600 ~/.discord_bot_env
```

## 6. 建立 Bot 啟動腳本

建立腳本：

```bash
nano ~/start-discord-bot.sh
```

填入：

```bash
#!/data/data/com.termux/files/usr/bin/bash

source "$HOME/.discord_bot_env"
cd "$HOME/icez-discord-bot"
termux-wake-lock
exec python bot.py
```

設定只有自己可以執行：

```bash
chmod 700 ~/start-discord-bot.sh
```

之後只要執行：

```bash
~/start-discord-bot.sh
```

## 7. 使用 tmux 讓 Bot 在背景運行

建立名為 `discordbot` 的工作階段：

```bash
tmux new -s discordbot
```

進入後啟動 Bot：

```bash
~/start-discord-bot.sh
```

看到以下訊息代表 Bot 已成功連線：

```text
Connected to Gateway
Logged in as Bot名稱
```

### 離開但不停止 Bot

1. 按 `Ctrl+B`。
2. 放開按鍵。
3. 按 `D`。

### 查看工作階段

```bash
tmux ls
```

### 回到 Bot 畫面

```bash
tmux attach -t discordbot
```

### 停止 Bot

進入 tmux 後按：

```text
Ctrl+C
```

再輸入：

```bash
exit
```

## 8. 更新 Bot 功能

電腦修改並推送 GitHub 後，在 Termux 執行：

```bash
tmux attach -t discordbot
```

按 `Ctrl+C` 停止舊版，然後：

```bash
cd ~/icez-discord-bot
git pull --ff-only
python -m pip install -r requirements.txt
~/start-discord-bot.sh
```

最後按 `Ctrl+B`，放開後按 `D`，讓新版 Bot 留在背景。

## 9. 使用 Neon 雲端資料庫

Neon 的連線字串也是秘密，不要提交到 GitHub。

編輯設定檔：

```bash
nano ~/.discord_bot_env
```

內容可以同時保存兩個秘密：

```bash
export DISCORD_TOKEN='你的 Discord Bot Token'
export DATABASE_URL='你的 Neon 連線字串'
```

再次限制權限：

```bash
chmod 600 ~/.discord_bot_env
```

Python Bot 常用的非同步 PostgreSQL 套件：

```bash
python -m pip install asyncpg
```

只有 Bot 程式已加入資料庫連線程式碼後，`DATABASE_URL` 才會實際被使用。

## 10. 電池與網路設定

防止手機休眠時暫停 Bot：

```bash
termux-wake-lock
```

解除：

```bash
termux-wake-unlock
```

Android 設定中還要：

- 將 Termux 電池用量設為「不受限制」。
- 允許 Termux 在背景執行。
- 不要強制關閉 Termux。
- 使用穩定的 Wi-Fi 或行動網路。

## 11. 常見訊息

### `PyNaCl is not installed` 或 `davey is not installed`

這只代表 Discord 語音功能不可用。若 Bot 沒有語音功能，可以忽略。

### `/ping` 顯示約 200 至 300 ms

這是手機和 Discord Gateway 的心跳延遲。Bot 沒有斷線且指令正常回覆時，通常不用處理。

### SSH 斷線後 Bot 是否會停止？

如果 Bot 在 tmux 裡運行，就不會因 SSH 斷線而停止。

### 手機重新開機後怎麼辦？

開啟 Termux，然後重新執行：

```bash
tmux new -s discordbot
~/start-discord-bot.sh
```

## 安全提醒

- 不要公開 Discord Token、GitHub Token 或 Neon 連線字串。
- 不要將秘密寫進 `bot.py`、README 或其他 Git 檔案。
- Token 若曾曝光，立即到服務網站重新產生。
- 不要直接將手機的 SSH `8022` 埠公開到網際網路。
