# 賭場後續議題交接

更新：Issue #8 的 21 點與圖片牌桌現已實作；最新契約、驗證與尚待部署事項見
[Issue #8 驗證與交接](casino-issue8-validation.md)。以下保留 #7 完成時的歷史交接，
其中「目前僅支援骰子」描述是 #8 開發前的基準，不是現在功能狀態。

Issue #7 的正式實作基準是 main 的 `6087b67`；既有水晶功能已先保存為
`eddedc6`。請從最新 main 接續，不要以舊原型分支重建 Bot。

下一票：[Issue #8：21 點與圖片牌桌](https://github.com/icez114514/icez-discord-bot/issues/8)。
[Issue #9：戰績統計與管理查帳](https://github.com/icez114514/icez-discord-bot/issues/9)
也只依賴 #7，可在協調共用資料契約後獨立開發。
完整玩法以 [父規格 #6](https://github.com/icez114514/icez-discord-bot/issues/6) 為準。

## 已可沿用

- `casino_commands.py`：CasinoFeature 註冊 /賭場、OwnedView 主人檢查、
  SettingsView／BetModal、ResultView 三按鈕、render 的圖片失敗文字回退。
- `casino_store.py`：CasinoStore 沿用 CrystalStore 連線與帳戶列鎖；
  preferences／settings／choose、start／replay／leave／recover／ledger。
- `casino_rules.py`：精確整數 Bet、輸入驗證及三骰規則。
- `casino_schema.sql`：偏好、牌局與流水；跨玩家帳戶共用，不按伺服器拆帳。
- `database.py` 的 init／migrate 已接入 CasinoStore.initialize；
  Bot 啟動只 check，正式遷移需要明確執行。
- `tests/test_casino_database.py`：隔離 PostgreSQL schema、固定骰序、
  COMMIT 前後故障注入、並行、恢復及 binary COPY 備份還原。
  `tests/test_casino_ui.py` 提供 interaction 替身。

## #8 必須擴充的現有邊界

目前 start 僅接受 game='dice'，recover／settle_transaction 僅結算骰子；
LobbyView 的 21 點停用。應在持久狀態、恢復與驗收完成後才開啟入口。

目前 schema 的 wager 約束是 `wager = base * multiplier`，ledger 的
kind 只有 stake／payout／refund 且 `UNIQUE(game_id, kind)`。
這些是骰子初版契約，不能直接套用兩次扣款的 21 點加倍。
以可重入 ALTER 遷移區分原始下注與累計下注，並提供額外扣款的唯一操作識別；
既有骰子牌局與流水必須完整保留。只修改 CREATE TABLE IF NOT EXISTS
不會更新已存在的資料表。

需新增持久牌組／雙方手牌／回合／期限等狀態，讓重啟使用原局與原期限。
維持帳戶列鎖、跨遊戲單一 active 局、一次性操作、唯一後續局及終局返還去重。
再來一局仍使用原始 Bet；異常退款需涵蓋加倍的全部扣款。
一般逾時應正常停牌結算，不可退款。

圖片由已提交的牌局版本產生，避免舊合圖覆蓋新狀態。
目前 Game 投影是骰子用資料，不應把未揭露的 21 點暗牌或剩餘牌組送入
公開圖片／文字回覆。UI 逾時與 120 秒牌局期限是不同概念。

## #9 共用查詢契約

資料庫 games 已有 game、user_id、status、outcome、base、multiplier、
wager、returned、balance_after、created_at、finished_at、reason。
目前 Game dataclass 未包含全部查詢欄位，可新增專用查詢投影；
不要因目前只有骰子就將查詢固定成單一遊戲。

ledger.amount 帶正負號，kind 為 stake／payout／refund；
每筆均有 balance_before／balance_after。簽到可能穿插一局的兩筆金流，
不能假设上一筆賭場流水的末餘額就是下一筆的初餘額。
正常終局與 active、void 應分開統計，系統莊家淨額為玩家合計的相反數。

#8 會涉及累計下注與額外扣款遷移，兩票並行時需先協調 schema／ledger
欄位與操作種類。#9 可以先用已存在的骰子結算與作廢資料實作查詢與授權，
不必等 21 點上線。

## 驗證與待辦

[操作說明](casino.md) 與 [實際測試／審查紀錄](casino-validation.md)
已保存本票證據：36 項非 DB 測試與 23 項真實 PostgreSQL 測試分次通過、
mypy 通過，Standards／Spec 審查無實作發現。
測試紀錄明列最初舊替身錯誤、修正與重跑範圍。

接續請沿用父規格已確認的 TDD 邊界：操作契約、interaction 替身、
隔離 PostgreSQL。固定牌序與時鐘，覆蓋天然、軟 A、首兩張加倍、逾時、
舊面板競爭、未知提交、圖片失敗及暗牌遮蔽。
使用 `RUN_DB_TESTS=1 python -m unittest discover -s tests -v` 執行完整驗證；
PowerShell 先設定 `$env:RUN_DB_TESTS='1'`。

尚待部署階段及 #8 的實機驗收：
- 明確執行並核對正式資料庫備份與增量遷移。
- 測試 Discord 伺服器的手機／桌面圖片、按鈕與 ephemeral 行為。
- #8 記錄合圖／更新延遲及測試條件；正式美術素材的驗收仍需實際完成。

#7 沒有啟動正式 Bot、對 public 做資料遷移，或完成 Discord 實機驗收。
這些待辦保留在父議題與後續開發票，避免將本地替身測試當成部署驗收。
