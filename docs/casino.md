# 水晶賭場（Issue #7、#8）

## 啟用

沿用水晶帳戶的 DATABASE_URL。先備份資料庫，再在停止 Bot 的維護時段執行：

```sh
python -m database migrate
python -m database check
python bot.py
```

全新資料庫使用 `python -m database init`。init／migrate 均增量建立
casino_preferences、casino_games、casino_ledger；可重跑，不重置帳戶或簽到日期。
Bot 啟動只做 schema 檢查，不會自動遷移或清除歷史。

每次開啟大廳會從 Mei 目錄的六張 JPEG 隨機選一張（允許連續抽到同圖）。
CASINO_DEALER_IMAGE 可覆寫為單張本機圖片；留空使用整個 Mei 圖池。
啟動時預載素材，更換後重啟 Bot 以更新快取；讀取／上傳失敗時顯示文字大廳。

## 玩家流程

公開 /賭場 → 21 點或 18 豆仔 → 基本下注與倍率 → 開局。
21 點：單副 52 張不放回，A 取最佳不爆牌點數，J/Q/K 為 10。
雙方首兩張先檢查天然：雙天然平手，單方天然立即結算；天然勝利返還原注 2.5 倍。
要牌／停牌／首兩張加倍；加倍額外扣原注、只補一張即停牌，不提供分牌或保險。
爆牌立即負，21 自動停牌；莊家不足 17 補牌，軟 17 停牌。
普通勝利返還累計下注兩倍、平手一倍、負零。加倍後再開仍使用原始基本下注及倍率。
玩家回合 120 秒，有效要牌且仍在玩家回合才刷新；無效／重送不延長。
重新 /賭場 與重啟保留原牌組、手牌及期限；背景每兩秒掃描到期局，正常停牌結算。
即使舊訊息無法編輯，交易結果仍保存，重新 /賭場 可恢復。
所有按鈕與 Modal 提交只允許面板主人；其他玩家收到私人提示。
面板 10 分鐘後停止互動，重新 /賭場 可找回持久結果。

基本下注至少 2 且為偶數；倍率為正整數。不接受小數、負數、科學記號。
固定選項不清除最後自訂值；設定與返回不扣款。
Discord 自訂欄位自身最多 4000 字元，畫面的大額數字可能省略顯示；
帳戶、下注與金流以精確整數處理，沒有另外設定產品下注上限。

三骰順序：豹子依面值 > 456 > 對子外單點 > 123 > 散骰。
對子先比單點，同級再比總和，再同則平手。散骰不重擲，不抽水。
下注 100：勝利返還 200（淨 +100）、負返還 0（淨 -100）、平手返還 100（淨 0）。

結算僅提供再來一局、修改下注、返回大廳。
再來一局沿用原局基本下注與倍率；同一結算面板只建立一個後續局。
牌局結果可能是上次提交時的餘額，最新餘額在下注設定與大廳查詢。

## 交易與故障處理

- CasinoStore 使用既有 CrystalStore 的連線及帳戶列鎖，與每日簽到共用同一餘額。
- 扣款、完整六骰、進行中牌局、下注流水與消耗設定 token 在同一交易提交。
- 跨 store／伺服器以帳戶列鎖及每人單一 active 局的部分唯一索引限制並行。
- 每個設定 token 對應唯一開局 operation_id；每個 parent_id 只能有一個後續局。
- 骰子派彩／退款、終局狀態和流水在另一個交易中一起提交；唯一流水索引防重複返還。
  21 點每次有效操作的手牌／版本／期限與扣款、結算同交易；加倍流水 kind=double 每局唯一。
- /賭場 優先恢復未完局，使用已保存骰序結算，絕不重新擲骰。
  完成局在返回／修改前仍可找回。
- 不可恢復的骰序以 invalid_persisted_dice 原因作廢，退回全額下注一次。
  網路／訊息傳送失敗不觸發退款。
- 未知 COMMIT 結果先依 operation_id 或牌局 ID 查證；若仍無法確認，只提示重新
  /賭場，不盲目重扣或派錢。歷史和流水沒有 TTL 或自動清除。

核對每局：stake 為負原注，double 為負額外原注，payout 或 refund 為返還，
所有 amount 合計等於 returned - wager。每筆 balance_after =
balance_before + amount。簽到可穿插兩筆賭場流水，因此不要假設
某局 stake 的餘額等於其 payout 的起始餘額。
查帳 UI 與統計已接入大廳；操作及授權設定見下方「紀錄與查帳」。

## 驗證

圖片牌桌使用 Pillow 在背景執行緒合成；只傳入已遮蔽暗牌的公開投影。
圖片或上傳失敗保留完整文字手牌、點數、下注、返還、淨盈虧及餘額，不重抽／重扣。
每張訊息依牌局版本更新，較慢的舊圖片不得覆蓋新結果；倒數使用 Discord 相對時間，不逐秒重畫。
程式記錄 compose_ms、update_ms 及版本，更新延遲包含 Discord 編輯與可能的文字回退。

CASINO_ASSET_DIR 可指定替换素材目錄，預設 casino_assets；未提供或無法解碼時使用內建佔位圖。
background.png 為 1200×800、back.png 及 cards/0.png 至 cards/51.png 為 144×200、
dice/1.png 至 dice/6.png 為 164×164。其他尺寸會等比例裁切。
牌面 ID = 花色索引 × 13 + 點數索引；花色順序黑桃／紅心／方塊／梅花，點數順序 A、2…10、J、Q、K。
所有牌面與牌背均預載；真正未揭露的暗牌 ID 不會送入圖片合成或訊息文字。

v1 升級會增量加入 cards／deadline，更新累計下注與 double 流水約束；可重跑且保留原骰子歷史。
正式環境需先備份、停止 Bot，再明確執行 migrate／check。隔離測試不等於正式備份或實機驗收。

```sh
python -m unittest discover -s tests -q
RUN_DB_TESTS=1 python -m unittest discover -s tests -q
python -m mypy --follow-imports=silent --ignore-missing-imports --check-untyped-defs casino_rules.py casino_store.py casino_commands.py
```

PowerShell 設定 `$env:RUN_DB_TESTS='1'` 後執行 unittest。
DB 測試只建立及刪除 casino_test_<UUID>／crystal_test_<UUID> schema，
不對 public 資料表寫入。需要 DATABASE_URL 具備建 schema 權限。

測試覆蓋固定骰序、精確大額、偏好重啟／重複遷移、主人檢查、Modal、
訊息失敗、重送、並行再開／簽到、扣款及派彩 COMMIT 前後中斷、作廢退款。
若未設定 RUN_DB_TESTS，整合測試會明確 skip，不代表交易安全已驗證。

部署前仍需在測試 Discord 伺服器手動確認桌面／手機按鈕與圖片、私人提示。
本地 interaction 替身不會連線 Discord，也不會替代實際裝置驗收。

備份還原整合測試以 PostgreSQL binary COPY 將隔離 schema 的帳戶、偏好、牌局與流水還原至另一隔離 schema，並恢復流水序號及結算在途牌局。這不等於已替正式環境執行 pg_dump／供應商備份還原；部署者仍須驗證其正式備份流程。

本次實際執行結果與審查紀錄見 [casino-validation.md](casino-validation.md)。

## 紀錄與查帳（Issue #9）

大廳新增「我的紀錄」與「莊家統計」；遊戲中與結算面板保持原有操作。
我的紀錄另發 ephemeral，保留公開大廳；莊家統計另發公開訊息且只有分遊戲彙總。
統計每頁至多三個遊戲／狀態組合，牌局明細每頁一局；可切換統計／明細及上一頁／下一頁。
「遊戲篩選」輸入 dice、blackjack 或其他已記錄遊戲識別，留空查全部。
每次翻頁重新查詢目前資料，完成更新後舊頁失效；新牌局可能改變歷史排序。
歷史含已返回大廳的牌局，不會因 dismissed 隱藏或自動清除。

設定 CASINO_AUDITOR_IDS 為逗號或空白分隔的 Discord 使用者 ID。
Bot 應用程式擁有者（團隊應用程式為團隊擁有者）亦可查帳，其他團隊成員、
一般伺服器管理權限均不自動授權。授權者開大廳另收到私人「查玩家／查牌局」入口；
輸入玩家 ID 或牌局 UUID 後，結果及分頁皆為私人。沒有新增獨立查帳指令。
每次按鈕、Modal、分頁及結果傳送前重新檢查目前設定／擁有者，查不到擁有者時拒絕授權。
修改 .env 後須重啟 Bot 載入；舊互動隨重啟失效。執行中若更新程序環境設定，
下一次權限檢查即生效；不把開頁時的授權快取在面板中。

正常完成局只統計 settled；active 在途與 void 退款另列，不計正常局數或勝負。
下注由 stake／double 流水重算；返還含本金由 payout／refund 重算。
玩家淨額 = 返還 - 下注；莊家收取／支出方向相反，勝負也與玩家相反。
明細含原下注、累計下注、返還／退款、淨額、狀態、時間、原因及每笔流水前後餘額。
進行中淨額是目前在途資金，尚不是最終輸贏。
查詢投影不讀取或輸出 cards、骰序、莊家暗牌、剩餘牌組或操作 token。

本功能沿用 #8 schema，不需要新增資料欄位或遷移；從舊版本升級仍須依上方執行 migrate。
查詢不呼叫恢復或結算，不改變帳戶、牌局、期限或流水。


## 連線池與延遲修正（2026-09-06）

本次效能更新不需要資料遷移。先安裝 `python -m pip install -r requirements.txt`，
停止並重新啟動 Bot。每個程序的 CrystalStore 共用一個 psycopg_pool 連線池，
水晶、賭場、查帳與逾時工作均透過同一個 store 借用；最少 1、最多 4 條連線，
取得連線最多等待 5 秒，啟動預熱最多等待 15 秒。Bot 與 CLI 退出時關池。
`python bot.py --check` 只驗證本機設定；`python -m database check` 才連線查驗。

大廳恢復／清理、返回／修改下注的來源驗證與狀態更新在同一交易內完成。
設定畫面的偏好與餘額來自同一操作快照，開局與加倍仍鎖帳戶重新檢查餘額。
交易結束才合圖與更新 Discord；池滿時回覆忙碌，不重試整筆下注或派彩。
失效連線會丟棄並補建；觸發失效的操作可能收到暫時不可用，使用 /賭場 查證即可。

`Operation timing` 以 action 區分開局／下注／返回等固定操作類別，並以隨機 id 關聯 owner_wait_ms、db_ms、pool_wait_ms、compose_ms、
update_ms、auth_ms 與 total_ms；db_ms 包含等待、交易設定及提交／回滾，pool_wait_ms 是其中一部分，
不可將兩者相加。update_ms 含 Discord 確認／傳送、訊息更新鎖等待、編輯及文字回退；auth_ms 是即時權限檢查耗時。
`bot.database_startup` 記錄含预熱與 schema 查驗的冷啟動。
connection=cold 表示啟動或該 store 首次借用，warm 表示已暖機；不代表外部網路或圖片快取一定命中。
首次借用若在啟動查驗時完成，之後玩家操作會標示 warm。背景逾時工作也有獨立關聯 id。
日誌不記錄操作 token、連線字串、玩家識別、暗牌或餘額明細。授權結果不快取。

量測與完整限制見 [casino-latency-validation.md](casino-latency-validation.md)。
要重新量測，執行 `python benchmark_casino.py --optimized --samples 20 --output latency-after.json`；
只使用隨機隔離 schema，完成後刪除測試資料。基準模式需搭配修正前版本，
不可在新版用未加 --optimized 的結果當成修正前效能。
回退時還原程式版本並重啟 Bot，不修改水晶、牌局或流水資料。
