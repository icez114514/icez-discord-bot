# 賭場後續議題交接

下一張實作票是 [#9：戰績統計與管理查帳](https://github.com/icez114514/icez-discord-bot/issues/9)。
从最新 main 接續；#8 實作提交為 `2679d60`，本文件收尾提交位於其後。
父規格：[水晶賭場正式開發規格 #6](https://github.com/icez114514/icez-discord-bot/issues/6)。

## 開始前

1. 確認本地最新 main 並保存既有未提交變更；功能基準包含 #7 與 #8，原型不是目前 Bot 基準。
2. 閱讀 #9 的驗收條件、[操作說明](casino.md) 與 [#8 驗證紀錄](casino-issue8-validation.md)。
3. 沿用父規格已確認的 TDD 邊界：公開操作／查詢契約、Discord interaction 替身、隔離 PostgreSQL schema。
4. 完成查詢與權限後跑相關測試、完整測試及 Standards／Spec 審查；未執行或 skip 的 DB 測試如實列出。

## 已完成並可沿用

- CasinoStore 支援 `dice` 與 `blackjack`；start／play／replay／recover／expire_pending 均使用持久牌局。
- CrystalStore 帳戶跨伺服器共用；帳戶列鎖、每人一個 active 局、每個結算面板一個後續局與唯一返還仍有效。
- CasinoFeature 提供大廳、下注、PlayView、ResultView、主人檢查、Modal 與圖片失敗文字回退。
- 每次開啟大廳從六張 Mei JPEG 隨機選圖；casino_images 僅接收已遮蔽暗牌的 Game 投影。
- Bot 啟動預載素材並掃描到期局；init／migrate 明確執行增量遷移，啟動 check 不會自動遷移。
- tests/test_casino_database.py、tests/test_blackjack_database.py 有真實交易、並行、故障及備份還原測試。
  tests/test_casino_ui.py、tests/test_blackjack_ui.py 提供 Discord 替身與圖片故障／亂序測試。

## #9 查詢契約

`casino_games.game` 為遊戲識別；查詢同時涵蓋兩款遊戲，其他已記錄識別亦應採相同查詢契約。
既有欄位包括 user_id、status、outcome、base、multiplier、wager、returned、
balance_after、created_at、finished_at、reason，以及 version、parent_id、dismissed。

- 原下注 = base × multiplier；wager 是累計下注，21 點加倍後為原注兩倍。
- 正常完成局 = status='settled'；outcome 為 win／loss／tie。
  active 與 void／退款另列，不能虛增正常局數、投注量或胜率。
- returned 包含本金；玩家淨盈虧 = returned - wager。莊家淨額為相反數。
- casino_ledger.kind 有 stake／double／payout／refund；amount 帶正負號，double 為額外原注的負數。
  每局每種 kind 唯一，payout／refund 合計最多一筆；每局流水合計應等於 returned - wager。
- 每筆流水保存 balance_before／balance_after；簽到可能穿插，不能把前一筆賭場末餘額當成下一筆初餘額。
- dismissed 只表示玩家離開結果頁，不表示刪除歷史。歷史沒有 TTL 或自動清除。
- Game 為遊戲畫面投影，未包含所有查詢欄位；#9 可新增專用查詢投影。
  cards 含私密牌組與暗牌，紀錄／管理查詢不得直接輸出 active 局 cards 或剩餘牌組。

## #9 接入位置與權限

從 LobbyView 新增我的紀錄／莊家統計入口。私人歷史使用另發 ephemeral，
保留公開大廳；公開莊家統計不含他人明細。授權者的管理入口另發私人訊息。

Bot 擁有者或明確指定 ID 才可查帳，一般伺服器管理員不自動授權。
每次按鈕、Modal 與分頁重驗當下權限，涵蓋撤權與舊面板。
沿用現有 /賭場 註冊，不新增獨立查帳指令。具體功能以 #9 為準。

## 已驗證基準

#8 完整測試 75 項通過，含 34 項真實 PostgreSQL，沒有 skip。
審查修正後最終 discovery 為 77 項：43 項非 DB 通過、34 項 DB 明列 skip；
這 34 項已在上述完整測試驗證，修正沒有更改 DB 實作。型別與雙軸複查通過。
詳細條件與圖像量測見 [#8 驗證紀錄](casino-issue8-validation.md)。

Windows 使用專案 `.venv/Scripts/python.exe`；系統 Python 可能缺少依賴。
PowerShell 設 `$env:RUN_DB_TESTS='1'` 後執行
`rtk .venv/Scripts/python.exe -m unittest discover -s tests -v`。
僅使用測試自行建立的隔離 schema，避免寫入 public。

## 部署驗收獨立追蹤

[#10：正式部署與 Discord 實機驗收](https://github.com/icez114514/icez-discord-bot/issues/10)
承接正式備份／還原、增量遷移、手機／桌面、真實更新延遲及正式素材驗收。
這些尚未執行，不因 #8 實作結案而視為通過；不阻擋 #9 程式開發。
