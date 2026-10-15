# 免自行訓練的德撲 NPC 候選

查證日期：2026-09-15。此為文件及公開檔案查證，未下載執行模型、未開始訓練，也未驗證 Termux 效能。先前聚焦 NoRegrets 不足以排除其他現成模型。

| 候選 | 現成資產與用途 | 尚未滿足的條件 |
| --- | --- | --- |
| [fullhouse-bot](https://github.com/advitrocks9/fullhouse-bot) | 六人 NLHE Deep CFR；已公開 [約 577KB 權重](https://github.com/advitrocks9/fullhouse-bot/blob/main/data/deep_cfr_model.npz)，以 NumPy 推理，無需重新訓練才可評估。作者描述競賽限制為每動作 2 秒、768MB、無網路。 | 競賽限制不是手機實测；5 種抽象動作、短碼查表，需驗證本案籌碼深度、邊池與介面；不是 GTO 能力證明。 |
| [deepbot-poker](https://github.com/tamlhp/deepbot-poker) | README 提供預訓練 6max_full 玩家執行方式，屬神經網路＋遺傳演算法。 | 六人訓練場景是 sit-and-go；較舊 Python 及原生依賴，無本案現金桌高手／Android 驗證。 |
| [D1 tiny poker model](https://huggingface.co/braitoli/d1-poker-ev-psych-v6) | 模型卡列 MIT 與 TFLite int8 約 307KB 現成輸出，適合列為小模型比較候選。 | 作者測試承認輸給 pot-odds 對手，且含執行期規則修正；不能當成近似 GTO 高手。 |
| [NoRegrets](https://github.com/conorarmstrong/noregrets#licensing) | 作者提供預訓練 blueprint 商業授權路線，可避免自行訓練。 | 公開 repo 不附免費預訓練產物；授權價格、模型大小、Android 適配及能力未驗證，未詢價／採購。 |
| [PokerData](https://pokerdata.io/) | 可下載六人 NLHE preflop 策略包，20～200BB 部分深度可選。 | 資料包不是完整 NPC；現列策略含抽水設定，不能直接當本案無抽水策略。嵌入產品授權、翻牌後多人及任意下注覆蓋未確認。 |

fullhouse-bot 的 [LICENSE](https://raw.githubusercontent.com/advitrocks9/fullhouse-bot/main/LICENSE) 說 MIT 適用於作者程式碼，列出的目錄未含 data；另排除第三方 engine_vendored。不能僅看根目錄 MIT 就宣稱所有權重與附帶引擎可直接再散布；應先釐清模型使用授權。

研究建議：優先評估 fullhouse-bot 的現成權重與介面，將 deepbot 作備選；不再把自行訓練當成唯一前提。此建議未取代使用者要求的單一近似 GTO 高手，也未把候選直接選為正式引擎。若只能驗證一般 NPC 實力，應再由使用者決定能力定位。
