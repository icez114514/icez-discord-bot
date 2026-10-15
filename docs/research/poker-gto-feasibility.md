# 多人德撲 GTO 高手 NPC 可行性

研究日期：2026-09-15。對應 [德州撲克：多人 GTO 高手 NPC 的可行性與驗證](https://github.com/icez114514/icez-discord-bot/issues/14)。本文是研究結果，尚未決定成本、引擎或降低需求；未安裝、訓練或實測候選引擎。

## 結論與適用範圍

六人無限注德撲的高手 AI 已有研究實證；但「實測高手」、「近似均衡策略」及「完整遊戲具有可證明誤差上界的 GTO」是不同承諾。Pluribus 採自我對弈藍圖加即時搜尋，在六人職業玩家實驗勝出，並未提供多人必勝或均衡收斂保證。不能把這份成果直接當成可下載的完整 GTO NPC。[CMU 原研究團隊說明](https://www.cmu.edu/news/stories/archives/2019/july/cmu-facebook-ai-beats-poker-pros.html)

本遊戲要求 2～6 人、10/20 盲注、400～2,000 帶入、全街下注、單一高手難度。初始帶入為 20～100 BB；連續贏牌後桌上籌碼可能超過 100 BB，輸牌後也可能低於 20 BB。因此不能只訓練固定 100 BB 六人策略。德撲籌碼獨立於既有水晶；真人與 NPC 共用德撲經濟，NPC 輸贏會使系統發行或回收籌碼。以上是需求及其算術推論。

## 理論與實測能力

- OpenSpiel 的 CFR 實作明確將近似 Nash 收斂描述限定為雙人零和；不得把 heads-up 的保證套用到三人以上。[CFR 原始碼](https://github.com/google-deepmind/open_spiel/blob/master/open_spiel/python/algorithms/cfr.py)
- 多人可以用 NashConv 衡量各玩家單方面偏離策略可增加的收益總和；OpenSpiel 的 exploitability 函式則只實作雙人常和。完整大型遊戲精確最佳回應成本高，縮小遊戲的分數不能當成完整 NLHE 誤差上界。[評估原始碼](https://github.com/google-deepmind/open_spiel/blob/master/open_spiel/python/algorithms/exploitability.py)
- 單靠 Monte Carlo 勝率、起手牌表或 LLM 決策，未提供本需求的均衡或高手驗證；不得默默以這些方法替代「單一 GTO 高手」。這是依上述證據制定的需求界線。

## 候選與限制

| 候選 | 可以利用的部分 | 缺口／授權狀態 |
| --- | --- | --- |
| Pluribus 論文架構 | 多人藍圖、資訊／下注抽象、有限深度即時搜尋 | 原技術大量程式受專屬授權；本次未確認可直接採用的官方完整權重及生產引擎。需自研或另取得明確授權。[CMU](https://www.cmu.edu/news/stories/archives/2019/july/cmu-facebook-ai-beats-poker-pros.html) |
| OpenSpiel | CFR、最佳回應與小型遊戲驗證框架 | Apache-2.0 主專案；是研究基礎，不是現成 2～6 人高手策略，依賴另核對。[專案](https://github.com/google-deepmind/open_spiel)、[授權](https://raw.githubusercontent.com/google-deepmind/open_spiel/master/LICENSE) |
| b-inary/postflop-solver | Rust DCFR postflop 引擎、計算策略與測試局面 | AGPL-3.0；開發暫停。範例介面為 OOP/IP 兩方，四名已棄牌者的 bunching 支援不等於多人仍在池中。不能包辦多人全街。[README](https://github.com/b-inary/postflop-solver)、[API 與範例](https://b-inary.github.io/postflop_solver/postflop_solver/) |
| TexasSolver | postflop 求解、命令列、JSON 策略輸出 | 頁面標 AGPL-v3，FAQ 另稱網路服務須商業授權，應釐清具體版本與權利人條件後才選用，不能假定免費 SaaS 整合。[作者 README](https://github.com/bupticybee/TexasSolver) |
| NoRegrets（原 conorarmstrong/pluribus） | 作者宣稱支援 2～6 人、MCCFR 訓練與 postflop 重新求解，MIT；可列為多人民間實作調查候選 | 獨立重現，非原版 Pluribus；作者自報的基準與牌譜動作吻合率不是職業高手或 GTO 證明。本次未執行，亦未核實動態深度、邊池及資源覆蓋。[作者專案](https://github.com/conorarmstrong/noregrets) |

以上授權是來源標示與整合待核對項，不是法律判定；若引入引擎，需固定版本與依賴清單。

## 計算與即時服務

Pluribus 藍圖耗約 12,400 CPU core-hours／8 天，線上使用 28 核心；這是原研究環境，不是本專案訓練預算或現代硬體報價。[CMU](https://www.cmu.edu/news/stories/archives/2019/july/cmu-facebook-ai-beats-poker-pros.html) 原論文記載線上記憶體低於 128 GB，每個子局搜尋 1～33 秒、自我對弈平均 20 秒／手；20 秒不是每次動作的延遲。[原論文](https://doi.org/10.1126/science.aay2400)

TexasSolver 的作者基準是特定 SPR=10 flop 樹，6 執行緒、1,600 MB、172 秒收斂至作者標示 0.275% accuracy；不能外推成任意多人牌局的即時效能。[作者基準](https://github.com/bupticybee/TexasSolver#speed-benchmark-with-piosolver)

架構推論：NPC 應獨立工作程序／服務，離線訓練與線上推理分離；按人數、完整籌碼向量、位置、公開牌與行動歷史定位策略，再針對未覆蓋下注重新求解。多人不能只用單一最小有效籌碼取代各席深度與邊池。記錄模型版本、覆蓋範圍、搜尋截止時間及 p50/p95/p99 延遲，使用實際目標硬體測試多桌併發。超時處理必須明列為故障政策，不能宣稱降級動作仍是 GTO。

## 驗證門檻草案（待確認）

1. 規則相容：2、3、6 人，低於 20 BB／20、50、100／高於 100 BB，不對稱籌碼，多人全下與邊池，最小加注、非抽象下注及重開加注權。遊戲引擎和 NPC 對合法動作一致。
2. 策略驗證：小型可解遊戲算 NashConv；heads-up 固定子局計算 exploitability，明示範圍、下注樹與誤差單位。多人使用最佳回應探針只能提供受限測試，無法聲稱完整不可剝削。勝過隨機／跟注 bot 只算基本測試。
3. 高手能力：固定候選版本與測試集，多種對手、輪換座位、配對牌序降低變異；報告 BB/100、信賴區間、手數與 NPC 數量分層結果。高手門檻與對手資格需先定義；動作吻合原牌譜比例不能代替能力測試。
4. 隱藏資訊隔離：NPC 僅收到自己手牌、公開行動／公共牌、席位籌碼和合法動作；不傳完整牌堆、亂數種子、他人私牌、未公開牌史。不同 NPC 不交換私牌或協調收益。可共享唯讀模型，但不得共享私牌狀態或共同決策亂數。
5. 隔離測試：固定自身資訊與 NPC 隨機種子，替換未知對手手牌及未發公共牌，策略輸出分布應不變；服務帳號無讀取全牌狀態與其他 NPC 記憶體的權限。OpenSpiel 也提醒其 policy 資訊集限制並非框架強制，因此必須由遊戲介面保障。[評估程式警語](https://github.com/google-deepmind/open_spiel/blob/master/open_spiel/python/algorithms/exploitability.py)

上列為本專案驗收建議，並非聲稱已通過的測試。

## 留給使用者的決策

- 若要求完整 2～6 人、任意合法下注與動態深度的可證明 GTO，現有證據不足以承諾交付；需先設定研究成功條件，未達前不可用 GTO 高手名義上線。
- 若接受「以均衡方法訓練、經指定基準驗證的近似 GTO 高手」，可評估授權策略或自研／重現引擎，再決定開發與訓練預算、線上硬體、可接受的思考時間，以及驗證門檻。
- 若先發佈真人遊戲、NPC 延後，會變更第一版交付範圍，必須由使用者選擇；不能在研究階段自行排除 NPC，亦不能換成規則 bot。

本次研究沒有採購、對外詢價、選定引擎、變更玩法或執行訓練。


## 手機部署補充（2026-09-15）

使用者確認：Android ASUS Zenfone 9；NPC 計算全部在此手機，不使用其他電腦或付費雲端。RAM 與 Bot 執行環境尚未確認。3 秒／10 秒及五桌均保留為待驗證目標。

查證補充：[NoRegrets 授權說明](https://github.com/conorarmstrong/noregrets#licensing) 明示預訓練策略不在公開 repo 提供，需商業授權；公開 MIT 原始碼不等於可免費取得訓練完成的策略。採此公開程式路線需要自行生成策略，再驗證能力及本案玩法覆蓋。

訓練、策略查詢與即時搜尋是不同階段；即使已有策略也不能直接承諾手機的延遲與併發。作者的 [訓練實驗](https://github.com/conorarmstrong/noregrets/blob/main/BASELINES.md) 使用桌機環境，不能外推成 Android 相容或手機推理已達標。

尚未選定模型、購買授權或執行訓練。僅手機條件下的完整 NPC 可行性仍未驗證，不能將規則 bot 視為已滿足近似 GTO 高手需求。
