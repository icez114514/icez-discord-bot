# 賭場後續議題交接

[#9：戰績統計與管理查帳](https://github.com/icez114514/icez-discord-bot/issues/9) 的程式實作已完成。
本次從 `dca0b16f537ece9b7698a4ebc6e7be994a7b7eae` 的乾淨 main 接續；
完整執行結果與 Standards／Spec 審查見 [#9 驗證紀錄](casino-issue9-validation.md)。

下一個部署工作是 [#10：正式部署與 Discord 實機驗收](https://github.com/icez114514/icez-discord-bot/issues/10)。
父規格 [#6](https://github.com/icez114514/icez-discord-bot/issues/6) 的正式部署驗收仍未完成。

## 已完成可沿用

- CasinoStore 支援 dice／blackjack 的持久牌局、加倍、恢復與到期結算。
- CasinoRecords 使用既有 schema，從 stake／double／payout／refund 流水重算；
  按遊戲、玩家與狀態查詢，保留 dismissed 歷史，不自動清除。
- 大廳新增我的紀錄／莊家統計。玩家明細另發 ephemeral，莊家僅公開彙總。
- Bot 應用程式擁有者或 CASINO_AUDITOR_IDS 明列 ID 可收到私人管理入口；
  透過玩家 ID／牌局 UUID 查詢，每次操作及傳送結果前重驗權限。
- 不註冊獨立查帳指令；不輸出暗牌、牌組、骰序或操作 token。
- 每次翻頁重新查詢，更新後舊頁失效。統計每頁三組，明細每頁一局。
- 原下注 = base × multiplier；wager 含加倍；returned 含本金。
  settled 正常局與 active 在途／void 退款分開；玩家淨額 = returned - wager，莊家相反。
- 每筆流水 balance_after = balance_before + amount；簽到可穿插，不假設不同流水餘額相連。

## 部署前

1. 閱讀 [操作說明](casino.md)、[#8 驗證紀錄](casino-issue8-validation.md) 與 [#9 驗證紀錄](casino-issue9-validation.md)。
2. 在停止 Bot 的維護時段完成正式備份／還原演練，再執行 migrate／check。
   #9 不需新增遷移；舊版本仍需 #8 增量 schema。不要把隔離測試當成正式備份。
3. 設定 CASINO_AUDITOR_IDS；修改 .env 後重啟載入。驗收普通玩家、明列 ID、
   Bot 擁有者、撤權與舊頁，以及公開大廳／私人結果的可見性。
4. 在 Discord 桌面／手機驗收兩款遊戲、分頁、Modal、圖片失敗回退及更新延遲。
   六張 Mei JPEG 是提供的荷官圖片；其他美術仍可替換，不代表正式美術驗收完成。

## 重跑測試

沿用公開操作／查詢契約、Discord interaction 替身及隔離 PostgreSQL 三個已確認的 TDD 邊界。
Windows 使用專案 .venv/Scripts/python.exe，PowerShell 設定 RUN_DB_TESTS=1 再執行完整 unittest discovery。
測試自行建立並刪除 casino_test_<UUID>／crystal_test_<UUID> schema，不寫入 public。
未執行或 skip 的資料庫測試必須明列，不能只用 Mock 宣稱交易安全。
