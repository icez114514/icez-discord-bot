# 在原本的 Android 手機首次啟動德撲

安裝目標為原生 Termux、ARM64、Python 3.14。使用同一個系統 Python，
德撲套件放在 `poker/.venv`，既有水晶 bot 使用專案根目錄的 `.venv`。
Node 只用來建置前端；網站啟動後由 Python 提供頁面與 WebSocket。

目前手機提供的版本為 Python 3.14.6、SQLite 3.53.4、Node 26.4.0。
Windows 的獨立 Python 3.12.14 與 3.14.6 環境各通過 152 項德撲測試；
固定 NPC 也能在 3.14.6 載入並產生決策。
Android ARM64 仍需在實體手機驗收。安裝腳本會在手機上檢查
原生套件、SQLite 版本及真正的 NPC 子程序；後續仍需驗證登入與實際牌局。

## 1. 安裝套件及建置網站

先用原本的 bot 更新腳本取得最新程式。在另一個 Termux 分頁執行：

```bash
bash ~/icez-discord-bot/update_bot.sh
cd ~/icez-discord-bot
bash install_poker_termux.sh
```

腳本會安裝 Termux 的 `python-numpy`、`python-cryptography` 與 C 編譯工具，
建立可讀取系統套件的 `poker/.venv`，以固定 Cython 工具鏈重新編譯 eval7，
再執行原生套件／NPC 啟動檢查及 `npm ci`、`npm run build`。
後續步驟以看到 `Poker dependencies and website build ready.` 為準；失敗時先處理錯誤。

Pydantic 核心使用 [Termux User Repository](https://termux-user-repository.github.io/pypi/pydantic-core/)
提供的 Python 3.14 / ARM64 wheel；版本、下載位址與 SHA-256 固定於
`requirements-termux.txt`，其餘套件仍由正常 PyPI 來源安裝。
這個來源是 Termux 社群的編譯版本，不是 Pydantic 上游提供的 Android wheel。
腳本不會加入全域 pip index，也不會執行資料庫初始化或啟動服務。

桌面仍使用 `requirements.txt`。Python 3.14 若需要從原始碼安裝 eval7，
先安裝 `requirements-build.txt`，並以 `--no-build-isolation` 編譯 eval7；
Windows 額外需要 Visual C++ Build Tools。

## 2. 設定 Discord 登入及 .env

在 Discord Developer Portal 選擇原本 bot 的應用程式，在 OAuth2 的 Redirects 加入：

```text
https://poker.ice-z.net/auth/callback
```

Application ID 是應用程式 ID；Client Secret 在 OAuth2 頁面取得，與 Bot Token 不同。
Bot 必須已加入指定的 Discord 伺服器。

在手機開啟原本的設定檔，保留現有 bot 設定，在文末加入以下欄位：

```bash
cd ~/icez-discord-bot
nano .env
```

```dotenv
POKER_ENV=production
POKER_ORIGIN=https://poker.ice-z.net
POKER_CLIENT_ID=原本bot的Application_ID
POKER_CLIENT_SECRET=OAuth2的Client_Secret
POKER_GUILD_ID=Discord伺服器ID
POKER_READER_TOKEN=第一組隨機字串
POKER_FUNDS_TOKEN=第二組不同的隨機字串
POKER_TABLE_ADMINS=你的Discord使用者ID
POKER_FUNDS_ADMINS=你的Discord使用者ID
```

`POKER_BOT_TOKEN` 未設定時沿用原本的 `DISCORD_TOKEN`。
用下列指令在手機產生兩組不同的內部憑證，分別填入上方兩個 TOKEN 欄位：

```bash
poker/.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(32)); print(secrets.token_urlsafe(32))'
chmod 600 .env
```

未設定 `POKER_DATA_DIR` 時，資料保存在手機私有 HOME 的
`.local/share/icez-poker/poker.db`。`.env` 不會展開 `$HOME`；需要自訂目錄時填完整絕對路徑。
預設備份位於專案的 `backups/poker/snapshots`，每 15 分鐘建立一次；同一支手機上的
快照不能防止整支手機遺失，應定期依 [部署文件](DEPLOYMENT.md) 匯出到其他裝置。

## 3. 檢查、初始化及啟動

這一節用於第一次建立德撲資料庫；網站尚未啟動時執行：

```bash
cd ~/icez-discord-bot
poker/.venv/bin/python -m poker check
poker/.venv/bin/python -m poker migrate
termux-wake-lock
tmux new -s poker
```

在新開啟的 `poker` 工作階段執行：

```bash
cd ~/icez-discord-bot
poker/.venv/bin/python -u -m poker serve
```

按 Ctrl+B、放開再按 D，讓服務留在背景。在另一個 Termux 分頁檢查：

```bash
cd ~/icez-discord-bot
poker/.venv/bin/python -m poker status
```

確認 `npc.status` 為 `ready`，`backup.completed_at` 有值且 `backup.error` 為 null。
若 `maintenance` 為 true，等待第一次備份完成後執行：

```bash
poker/.venv/bin/python -m poker resume
```

## 4. 讓外部瀏覽器連入

在 Cloudflare 的專用 `icez-poker` Tunnel 設定公開 hostname `poker.ice-z.net`，
service 指向 `http://127.0.0.1:8765`；保留 WebSocket。8766 是內部管理與 bot API，
不要設定公開路由。若之前有其他裝置連到同一個 Tunnel，先停止舊的 connector，
避免把玩家分流到不同的本機資料庫。

在 Termux 安裝 cloudflared，將該 Tunnel 的 token 存入私有檔案：

```bash
pkg install cloudflared
mkdir -p ~/.cloudflared
chmod 700 ~/.cloudflared
nano ~/.cloudflared/icez-poker.token
chmod 600 ~/.cloudflared/icez-poker.token
tmux new -s pokertunnel
```

檔案內只放該 Tunnel 的 token。在新工作階段執行：

```bash
cloudflared tunnel run --token-file ~/.cloudflared/icez-poker.token
```

按 Ctrl+B、D 留在背景，然後用瀏覽器開啟 `https://poker.ice-z.net`，實測 Discord 登入、
建立牌桌、NPC 與籌碼結算。若要啟用 Discord `/德撲` 查詢，設定完成後重新啟動 bot。

手機須允許 Termux 背景執行，將電池限制設為不受限制；tmux 不會在手機重新開機後自動啟動。
既有 `update_bot.sh` 只管理水晶 bot。德撲後續更新要先 drain、等待牌局結束、備份並停止，
再更新依賴與前端，依 [受控升級流程](DEPLOYMENT.md#controlled-upgrade-and-rollback) 完成重新啟動。
