# 牌九撲克驗證紀錄

日期：2026-09-12。規格：GitHub #11、#12。
實作提交：13734d99a1e3faa8b3937f29ba0aa95cadfe5f7e。
Review 補強提交：df8ef88（只新增固定牌例及規則說明，未修改產品程式）。

## 自動化結果

- Windows、Python 3.10.6、專案 .venv；discord.py 2.7.1、mypy 2.3.1。
- 完整套件：RUN_DB_TESTS=1，python -m unittest discover -s tests -q。
  實作提交上的 151 項測試全部通過，耗時 600.605 秒，exit 0，無 skip。
  含既有骰子、二十一點、水晶、獎勵、查帳及連線恢復回歸。
- Review 後新增五個固定 House Way 牌例；在 df8ef88 內容上重新執行
  test_paigow.py 的 7 項規則測試，全部通過。測試方法總數不變。
- 牌九隔離資料庫切面：7 項全部通過，涵蓋原子扣款／派彩、提交前失敗與提交後回應遺失、
  逾時確認競態、重啟、重送／再開、非法狀態退款、大額整數及 Discord 文字端到端流程。
- 牌九 UI 切面：5 項全部通過，含牌桌可解碼、全萬用 Joker 素材、文字與上傳回退、
  owner guard、舊版本圖片不可覆蓋新選牌、active 圖片暗牌遮蔽。
- mypy --follow-imports=silent --ignore-missing-imports --check-untyped-defs
  paigow.py casino_store.py casino_commands.py casino_images.py：四檔通過。
- 差異空白檢查通過；變更檔案 UTF-8 嚴格解碼通過，無新增 U+FFFD 取代字元。

資料庫測試使用測試 fixture 建立的隨機隔離 schema，測試後清除；沒有遷移正式帳戶資料。
輸出中的圖片失敗、網路失敗、連線失效等 warning 來自故障注入情境，不表示測試失敗。

## 圖片驗證

生成初始選牌、已選前二後五及結算預覽；目視檢查已選與結算圖片。
1200×800 牌桌中，手牌編號、Joker 及代表牌、雙墩牌型、勝負與金額未見裁切或重疊。
這是本機圖片驗證，不能證明 Discord 手機客戶端的實際呈現。

## Standards

書面規範違反：0。判斷性建議：1（低優先）。
House Way 候選分墩使用 tuple 與數字牌型索引；可改為具名候選結構與牌型常數，
減少修改規則時解讀索引的負擔。這是可讀性建議，不是硬性違規或已確認功能錯誤，
本次未另做結構重整。

## Spec

Review 最初指出固定牌例缺少順子／同花重疊及 Joker 改變分組的情境。
已新增五例、補充 Joker 分類與實際替代可以不同的說明，並通過針對性測試。
補驗沒有發現剩餘可重現的 Joker 評分、派彩、遮蔽、固定期限或跨遊戲互斥錯誤。

仍有 1 項已知验收限制：#12 的 Discord 桌面／手機實機驗收未完成。
使用者已明確選擇「先保留實機驗收待辦」；#12 保持開啟並標為 ready-for-human。
包含手機辨識性的第一項及實機驗收項不以本機圖片或互動替身勾選完成。

Review 結果：Standards 0 硬性違規、1 非阻擋建議；Spec 0 未修功能／測試缺口、1 已接受的實機驗收待辦。
