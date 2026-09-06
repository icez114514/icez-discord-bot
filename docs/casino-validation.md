# Issue #7 驗證紀錄

日期：2026-09-06。基準：eddedc6f786bd9989a5608ba7c83ca2b15fcf162。

## 測試

- 型別檢查：casino_rules.py、casino_store.py、casino_commands.py 的 mypy
  --follow-imports=silent --ignore-missing-imports --check-untyped-defs 通過。
- RUN_DB_TESTS=1 的完整 unittest discovery 執行 59 項，58 項通過、1 項舊水晶
  測試替身錯誤；其中 **23 項 PostgreSQL 整合測試全部通過、沒有跳過**。
- 唯一錯誤是舊替身缺少 CrystalStore.schema；同時更新新增 /賭場 後的指令集合。
  修正只涉及 tests/test_crystals.py，該檔 19 項測試重跑全部通過。
- 修正後重跑完整非資料庫 discovery：**36 項通過，23 項 DB 測試因
  RUN_DB_TESTS=0 明確跳過**。這 23 項已在上一輪真實 PostgreSQL 驗證通過；
  修正後沒有重新跑 DB，因為沒有更改正式程式或 DB 測試。
- 因此 59 項測試均有通過證據，並非宣稱修正後另有一次 59 項單次全綠執行。

PostgreSQL 測試均使用隨機命名的隔離 schema，涵蓋精確大額、規則排序、
偏好重啟／重複遷移、跨 store 重送與再開、並行簽到、扣款／派彩 COMMIT
前後中斷、未知結果查證、一次退款，以及 binary COPY 備份還原在途牌局。
沒有對 public 正式資料表執行遷移或資料寫入。

Discord interaction 替身覆蓋公開大廳、停用 21 點、主人限制、Modal 預填、
完整下注／再開／返回、舊面板失效、訊息失敗恢復及圖片上傳失敗文字回退。
預設荷官 JPEG 可解碼為 1840 × 1432；圖片視覺預覽工具因本機沙箱初始化故障
未能使用。尚未在實際 Discord 伺服器進行手機／桌面外觀與互動驗收。

## Standards

獨立審查未發現文件規範違反、重大 Fowler 程式異味或可確認的正確性問題。
最後的舊測試替身差異也已獨立複查，未發現問題。

## Spec

獨立審查核對 Issue #7 與父 #6 的下注、偏好、權限、三骰、金流、恢復、
單局限制、唯一再開、遷移與歷史保存，未發現可確認的實作缺陷或範圍外功能。
圖片預設值與回退測試的最後差異亦已複查。實際 Discord 裝置驗收仍待完成。

Standards：0 項發現；Spec：0 項實作發現，1 項待完成的實機驗收。
