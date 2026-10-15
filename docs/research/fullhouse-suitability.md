# fullhouse-bot 適用性評估

查核日期：2026-09-15。固定 commit：`e504793d480b1b975f25258d25939b45c6dbd5a4`。

## 判定

適合作為免自行訓練、輕量離線 NPC 的候選；目前不足以直接驗收為本遊戲的 2～6 人近似 GTO 高手。推理的資源需求比先前大型策略訓練方案低很多，但玩法整合、能力證據及模型授權仍有缺口。這次未訓練、未改遊戲程式、未部署到手機、未聯絡作者。

## 本機實測

以現成模型和固定版本的三個 runtime 檔執行，依賴只放入隔離評估目錄；未安裝到全域 Python。Python 3.10.6、NumPy 2.2.6、eval7 0.1.11；BLAS 工作執行緒設為 1。

- 模型檔 590,758 bytes；解壓後數值陣列共 586,776 bytes，能直接載入，無需自訓。SHA-256：`1102326b68da95564de147106612df71cb891b42f0726ba0212d3b9a5bcae295`。
- 60 組合成輸入，涵蓋 2～6 人、四街及 20／100／200BB 表示；檢查機率有限、非負、合計 1 且符合模型自身動作遮罩。這些不是正式引擎重播的完整牌局，不代表所有遊戲規則已驗證。
- 3,000 次序列化 decide 呼叫：p50 0.099ms、p95 0.107ms、p99 0.131ms、此次最大 0.483ms；程序 RSS 約 35.5MiB；零回退。
- 程式匯入及模型載入約 102ms，計時開始前已載入 NumPy，故不是完整 Python 冷啟動時間。
- 缺少 eval7 的獨立測試：直接策略呼叫拋出錯誤，但 decide 仍回傳 check，確認存在會掩蓋故障的回退。
- 10/20 盲注下的 400 籌碼是 20BB；直接餵入原程式會誤入短碼規則。全部金額放大五倍後，該案例不再進入短碼規則。

以上只代表 Windows 桌機、單一程序的合成輸入測試，不能外推成手機五桌效能、實戰勝率、GTO 或邊池結算正確。完整結果見 [desktop results](fullhouse-desktop-results.json)，可重跑檢查程式見 [probe](fullhouse-desktop-probe.py)；probe 預設使用本工作區的隔離評估目錄，也可用 FULLHOUSE_REVIEW_ROOT 指向含固定版本 runtime/data/deps 的目錄。

## 必須處理的差距

| 面向 | 證據及影響 |
| --- | --- |
| 授權 | [LICENSE](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/LICENSE) 將 MIT 範圍限定列出的作者程式目錄，未列 data，第三方引擎另行排除。權重使用／再散布條款尚不明確，不等於作者明文禁止；正式選用前要釐清。 |
| 金額及合法動作 | [runtime](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/bot/bot.py) 使用 50/100 盲注和 10,000 參考籌碼。需一致轉換狀態、行動紀錄及輸出金額，並由遊戲伺服器再次驗證合法性。 |
| 打法 | 混合機率選擇是真的，但只有五種抽象動作；低於或等於 12BB 的翻牌前改用手寫規則，不能直接稱整套皆為已解 GTO。 |
| 多人及籌碼 | [特徵](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/bot/features.py) 沒有明確每個邊池的資格／金額向量。程式能處理不同人數不等於在每個人數都夠強；任意深碼及反覆補碼也未驗證。 |
| 實力來源 | [實驗紀錄](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/docs/research/experiments.md) 區分主線 v17 和決賽 v29＋overlay，不能直接把宣傳的決賽名次當作此權重成績。尚缺本案高手對手集的勝率與可信區間。 |
| 手機 | NumPy 前向計算很小，但翻後特徵還需要 eval7 原生擴充。Android／Termux 安裝、Python 版本及持续負載未實測；僅看到 NPC 回傳動作不足以判定模型工作正常。 |

## 建議下一步

維持不自行訓練的優先方向。先釐清現成權重條款，再設計薄的遊戲介面轉接，處理金額、完整當手紀錄、各 NPC 的隨機源及故障可見性；後續分開驗證手機完整決策路徑和 2～6 人的實力。若只通過可玩 NPC 而未達高手門檻，需與使用者再決定能力定位，不默默降低標準。

詳細來源見 [模型與玩法查核](fullhouse-model-fit.md) 及 [授權與手機查核](fullhouse-license-portability.md)。


## 後續使用者決定

使用者在本評估之後明確決定直接選用此模型、將盲注改為 50/100，並取消追加模型驗證與自行訓練。本文保留為當時查核紀錄，不再作為選型關卡；正式決定以 [NPC 能力承諾與運算預算](https://github.com/icez114514/icez-discord-bot/issues/21#issuecomment-5673927561) 為準。


## 後續範圍決議：僅固定 NPC

外來 Bot 功能全部取消。正式遊戲僅部署選定的 fullhouse-bot 決策模組、NPZ 資料與必要依賴；不提供投稿、上傳、匯入、自訂 Bot／模型或任意路徑與遠端執行介面。外來 Bot 驗證器、競賽平台、其他對手 Bot、訓練／叢集工具及未使用的 pickle 分類器皆不納入正式部署。遊戲伺服器仍負責動作合法性檢查與執行期限。

權威決議：[德州撲克：NPC 能力承諾與運算預算](https://github.com/icez114514/icez-discord-bot/issues/21#issuecomment-5674365369)。
