# 水晶賭場（Issue #7）

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

大廳使用現有 Mei 素材。可設定 CASINO_DEALER_IMAGE 為另一張本機 JPEG 圖片的路徑；
更換後重啟 Bot 以更新快取。讀取／上傳失敗時顯示文字大廳。

## 玩家流程

公開 /賭場 → 18 豆仔 → 基本下注與倍率 → 開局。
21 點目前停用，服務端亦拒絕其開局要求，不扣款。
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
- 派彩／退款、終局狀態和流水在另一個交易中一起提交；唯一流水索引防重複返還。
- /賭場 優先恢復未完局，使用已保存骰序結算，絕不重新擲骰。
  完成局在返回／修改前仍可找回。
- 不可恢復的骰序以 invalid_persisted_dice 原因作廢，退回全額下注一次。
  網路／訊息傳送失敗不觸發退款。
- 未知 COMMIT 結果先依 operation_id 或牌局 ID 查證；若仍無法確認，只提示重新
  /賭場，不盲目重扣或派錢。歷史和流水沒有 TTL 或自動清除。

核對每局：stake 為負下注，payout 或 refund 為返還，
所有 amount 合計等於 returned - wager。每筆 balance_after =
balance_before + amount。簽到可穿插兩筆賭場流水，因此不要假設
某局 stake 的餘額等於其 payout 的起始餘額。
查帳 UI 與統計屬後續議題；此版本僅保存可核對資料。

## 驗證

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
