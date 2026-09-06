# Discord 水晶 Bot

Python 3.10 以上；本機 Windows 與 Android Termux 使用同一份程式及 Neon PostgreSQL 資料庫。

## 指令

| 操作 | 行為 |
| --- | --- |
| `/ping` | 顯示 Gateway 延遲 |
| `/水晶` | 預設簽到／查詢：未簽到就領獎，當天已領只顯示餘額 |
| `/水晶 操作:簽到／查詢` | 與預設操作相同 |
| `/水晶 操作:排行榜` | 顯示全域前 5 名，不領獎、不建立帳戶 |
| 單獨傳送 `<:crystal:431483260468592641>` | 與簽到／查詢相同，容許前後空白 |

只有一個水晶 Slash 指令。水晶與每日領取資格跨伺服器共用，僅在伺服器內使用。其他聊天內容、Bot、Webhook 及私人訊息不觸發。

## Windows 本機設定

在專案目錄的 PowerShell 執行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path -LiteralPath .env)) { Copy-Item -LiteralPath .env.example -Destination .env }
notepad .env
```

填入設定（不要把 Token 或連線字串傳給其他人）：

```dotenv
DISCORD_TOKEN=你的BotToken
DISCORD_GUILD_ID=你的測試伺服器ID
DATABASE_URL="Neon提供的完整PostgreSQL連線字串"
```

`DATABASE_URL` 保留 Neon 提供的 SSL 與 channel binding 參數；可使用 pooled endpoint。
環境變數優先於程式所在目錄的 `.env`，從其他工作目錄啟動也適用。Token、匯入資料及虛擬環境已被 Git 忽略。

在 [Discord Developer Portal](https://discord.com/developers/applications)：

1. 於 Bot 頁面的 Privileged Gateway Intents 開啟 **Message Content Intent**，供表情訊息觸發使用。
2. 邀請網址包含 `bot` 與 `applications.commands` scopes。
3. 測試頻道開放 View Channel、Send Messages、Embed Links 與使用應用程式指令；若在討論串使用，另需 Send Messages in Threads。不需要 Administrator 或 Members Intent。

`DISCORD_GUILD_ID` 留空會同步全域指令；填入時只同步該測試伺服器。每次啟動同步一次，重連不重複同步。
變更同步範圍不會自動刪除其他範圍的既有指令，測試期間請固定範圍。

## 初始化與啟動

初始化是明確執行的管理操作，不會在 Bot 啟動時自動建表：

```powershell
.\.venv\Scripts\python.exe -m database init
.\.venv\Scripts\python.exe -m database check
.\.venv\Scripts\python.exe bot.py --check
```

`database init` 可重複執行並保留既有帳戶。`database check` 唯讀驗證連線、SSL 與資料表；
`bot.py --check` 只做本機設定格式檢查，不驗證憑證。Bot 正常啟動前會先檢查資料表是否可用。

**若要匯入舊帳戶，先完成下節匯入，再開放簽到。**

```powershell
.\.venv\Scripts\python.exe bot.py
```

看到 `Logged in as ...` 後，在 Discord 測試指令。按 `Ctrl+C` 停止。
PyNaCl 或 davey 未安裝的語音警告不影響此 Bot 的文字功能。

## 舊帳戶匯入

在已忽略的 `imports/` 資料夾建立 UTF-8 JSON 檔，例如 `imports/balances.json`：

```json
[
  {"user_id": "123456789012345678", "balance": "1000", "display_name": "顯示名稱"},
  {"user_id": "234567890123456789", "balance": "500"}
]
```

使用者 ID 必須是字串，避免編輯器或 JavaScript 將大整數四捨五入。`display_name` 可省略；不以暱稱猜測帳戶。
餘額必須是非負整數，可用 JSON 整數或十進位字串；巨額資產建議用字串。資料庫使用不指定精度的 PostgreSQL NUMERIC，程式使用 Python int 精確加總，避免 BIGINT 溢位與浮點數捨入。拒絕小數、負值、NaN、無限值、重複 ID 或未知欄位；NUMERIC 仍有 PostgreSQL 實作上限，並非無限容量。

先預檢，再正式匯入：

```powershell
.\.venv\Scripts\python.exe -m database import imports/balances.json --dry-run
.\.venv\Scripts\python.exe -m database import imports/balances.json --apply
```

未指定旗標時預設預檢。預檢只查詢、不寫入；正式匯入採單一交易，出錯整批回滾。
已存在帳戶拒絕覆蓋，因此請在開放簽到前匯入；不要刪帳戶來繞過衝突。

匯入帳戶可領當日獎勵，但不補新人起始 10 顆。匯入工具不自動修正或修改使用者原始檔案。
排行榜上尚未有名稱的帳戶會顯示 ID，帳戶下次簽到／查詢時更新顯示名稱。


## 舊水晶與銀行資料合併

既有 BIGINT 資料庫先執行明確遷移，再匯入；Bot 啟動不自動遷移：

```powershell
.\.venv\Scripts\python.exe -m database migrate
.\.venv\Scripts\python.exe -m database check
```

遷移以單一交易將餘額改成 NUMERIC，加入「有限、非負整數」約束，保留既有餘額。
若既有資料不符合約束，整筆遷移失敗並保留原狀，不自動歸零正式資料。

離線合併來源：

```powershell
.\.venv\Scripts\python.exe -m database merge-legacy --crystals imports/crystals.json --bank imports/bankfile.json --output imports/balances.json
.\.venv\Scripts\python.exe -m database import imports/balances.json --dry-run
.\.venv\Scripts\python.exe -m database import imports/balances.json --apply
```

- 每位使用者的最終餘額為 `max(crystals, 0) + max(savings, 0)`；兩項分別歸零負值。
- 保留全部水晶帳戶，以及只有銀行紀錄但存款大於零者。
- 貸款與舊簽到 Time 不匯入，銀行沒有後續利息或其他功能。
- 來源科學記號精確解析成整數，合併輸出將 ID、餘額保存為十進位字串。
- 工具同時輸出 `balances.json.report.json`，包含 SHA-256、帳戶數、總額及負值修正明細。
- 原始檔保持原樣；輸出或報告已存在時拒絕覆蓋，重跑請選新輸出路徑。
- 合併命令不連線 Neon，只有明確的 import --apply 會寫入帳戶。
- 匯入帳戶首次仍可領當日獎勵，但不補起始 10 顆；重複匯入會拒絕，不會再加存款。

本次來源固定為 commit `365b68d48215b1fcb894267aaa33f638fd9f6f2b`，原始檔、manifest 與結果保存在忽略目錄 `imports/legacy-365b68d48215/`。
預期匯入 2,377 個帳戶，略過 4,438 個；精確总額為 **16,078,667,357,324,830,231,885,012**。
`manifest.json` 記錄来源網址與檔案雜湊，實際核對結果另存 `verification.json`。

## 獎勵規則

- 依 [原始水晶模組](https://github.com/mxicat/mei-bot/blob/master/%3C%3Acrystal%3A431483260468592641%3E.js) 的規則重新以 Python 實作。
- 原版 20 組身分組名稱／等級完整列於 `crystal_rules.py`，必須精確同名；不自動建立或分配。
- 多個等級取最高，無符合者為 LV.1。
- 基礎獎勵為 `floor(U × 等級 × 2.5 + ceil(等級 ÷ 1.5))`，`0 ≤ U < 1`。
- 身分組 ID `586253482227400912` 使基礎獎勵乘以 2；不存在該身分組的伺服器不套用雙倍。
- 新帳戶額外取得一次起始 10 顆，這 10 顆不加倍；20% 專屬身分組加成暫不實作。
- 每日以資料庫時間換算 `Asia/Taipei` 完整日期，午夜可再領，無需執行重置排程。
- 所有伺服器共用資格，但獎勵以當次伺服器的身分組判定。
- PostgreSQL 帳戶列鎖與交易保護並發簽到；領獎提交成功後才回覆。回覆失敗時重試不重發獎勵。

## Termux 搬移

依 [Termux 官方安裝說明](https://github.com/termux/termux-app#installation) 選擇來源，Termux 與外掛使用同一來源。

```bash
pkg update
pkg upgrade
pkg install python git tmux libpq clang make pkg-config nano
cd ~
git clone https://github.com/icez114514/icez-discord-bot.git
cd icez-discord-bot
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp -n .env.example .env
nano .env
chmod 600 .env
.venv/bin/python -m database check
.venv/bin/python bot.py --check
termux-wake-lock
tmux new -s discordbot
.venv/bin/python bot.py
```

GitHub clone 只有已推送的版本；也可手動複製程式與 requirements.txt。不要複製 Windows 的 `.venv`，在手機重建。
Windows 安裝 Psycopg binary；Termux 安裝純 Python Psycopg，使用系統 `libpq`，不需在手機啟動 PostgreSQL 伺服器。
手機設定相同的 Neon 連線字串即可使用原有帳戶，無需重新匯入。

按 `Ctrl+B`、放開再按 `D` 離開 tmux；使用 `tmux attach -t discordbot` 返回。
停止 Bot 後執行 `termux-wake-unlock`。搬移完成後停止電腦版本。
允許 Termux 背景執行並將電池設為不受限制；Android 仍可能終止程序，重開機後需手動啟動。
手機環境尚未實測。

既有 [Termux 詳細指南](TERMUX_GUIDE.md) 可供 SSH 操作參考；Bot 安裝與啟動命令以本文件為準。

## 測試與驗收

離線測試不登入 Discord，資料庫整合測試預設跳過：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

明確啟用 Neon 整合測試：

```powershell
$env:RUN_DB_TESTS = '1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
Remove-Item Env:RUN_DB_TESTS
```

測試只在隨機 `crystal_test_...` schema 建立帳戶，結束後清除該 schema，不動正式帳戶表。
資料庫角色需有建 schema 權限；強制中斷測試可能留下該次測試 schema。

Discord 手動驗收：

1. `/ping` 正常，只有一個 `/水晶` 且「操作」選項可省略。
2. 首次 `/水晶` 回覆獎勵與餘額；同日再傳水晶表情只回覆餘額。
3. `/水晶 操作:排行榜` 顯示榜單且不領獎；混合文字的表情訊息不觸發。
4. 在不同伺服器以同一帳戶操作不會再領，身分組仍以首次領取所在伺服器為準。
5. 檢查粉色 Embed、圖片與名稱顯示；名稱不應觸發提及。

API 依據：[discord.py Intents](https://discordpy.readthedocs.io/en/stable/intents.html)、[Psycopg 非同步連線](https://www.psycopg.org/psycopg3/docs/advanced/async.html)。
