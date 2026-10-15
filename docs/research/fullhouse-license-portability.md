# fullhouse-bot：授權與 Termux 可攜性核查

查核日期：2026-09-15。固定版本：`e504793d480b1b975f25258d25939b45c6dbd5a4`。本分支只做原始碼與公開資料查核，未安裝、訓練或執行外部程式，未在手機實測。

## 結論

值得進入離線原型驗證，但尚不適合直接當作已驗證的 Termux 高手 NPC 上線。現成權重確實存在；正式整合前仍要釐清權重授權、驗證 eval7 在實際手機 Python 環境可用，以及量測整條決策路徑，不能只測 NumPy 矩陣運算。

## 授權與來源

- [LICENSE](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/LICENSE#L21-L29) 的 MIT 授權明確限定作者在 `bot/`、`training/`、`tooling/`、`scripts/`、`tests/`、`docs/` 的程式；要求保留版權與授權聲明。
- 同一份 LICENSE 排除 `engine_vendored/`，要求依上游引擎條款；不能把整個倉庫一概當成 MIT。
- 該限定沒有列出 `data/`。已提供的 `deep_cfr_model.npz`、`preflop_equity.npz` 未見獨立授權或 model card，因此「可下載」與「已明確授權整合／再散布權重」必須分開。這是授權文字範圍尚不明確，不是判定作者禁止使用。
- LICENSE 提到 publishing notes，但固定版本完整 tree 中未找到名稱含 publishing 的文件；README 與 `docs/research/` 也未提供可解決上述範圍的權重授權。後續若選用，需取得明確權重條款；本次未聯絡作者。
- [README](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/README.md) 說明權重來自該專案 Deep CFR 訓練並稱其他內容為作者自己的工作，但這不是額外授權條款。

## 實際執行依賴

| 項目 | 查核結果 |
|---|---|
| Python、NumPy | 三個 `bot/` 執行檔直接使用；網路服務、Torch、CUDA 並非決策必要條件。 |
| eval7 | 必要：`features.py` 的手牌強度編碼呼叫 eval7。只是神經網路前向計算使用 NumPy，整個 NPC 不是純 Python。 |
| scipy、treys、scikit-learn | 未見於三個 `bot/` 檔的 imports／決策路徑；requirements 是本機開發／訓練合集，不等於最小部署需求。 |
| numba、PyTorch | README 將它們用於訓練；現成權重決策路徑不需要。 |
| 模型資料 | Git tree 確認主模型 590,758 bytes（576.9 KiB）；翻牌前表 2,160 bytes。這是檔案大小，不是程序記憶體。 |

來源：[bot.py](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/bot/bot.py)、[features.py](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/bot/features.py)、[lookup](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/bot/deep_cfr_lookup.py)、[requirements](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/requirements.txt)、[固定 tree metadata](https://api.github.com/repos/advitrocks9/fullhouse-bot/git/trees/e504793d480b1b975f25258d25939b45c6dbd5a4?recursive=1)。本分支沒有解析 NPZ 內部形狀；51 特徵／5 動作是文件與原始碼契約。

特別注意：`bot.py` 預熱時吞掉 eval7 例外，`decide` 又捕捉所有例外並退回 check/call/fold。缺少 eval7 時，單純看到程式有回傳動作不代表模型正常。驗證須直接覆蓋翻牌後特徵編碼／策略輸出並記錄 fallback 次數。

## Termux 判斷

- Termux 官方有 [python-numpy 配方](https://github.com/termux/termux-packages/blob/master/packages/python-numpy/build.sh)，依賴 Python、libopenblas、libc++，並明確處理 aarch64／Android wheel；這支持技術可行性，不能推導本 bot 已在 Zenfone 9 通過。
- [eval7 0.1.10 setup.py](https://github.com/julianandrews/pyeval7/blob/master/setup.py) 使用 Cython extensions，依賴 pyparsing、future。它是需匹配平台的原生擴充，不應把 Windows 的已安裝環境直接搬到手機；必須在相符 Android／Python 環境安裝或編譯驗證。
- 原專案競賽環境是 Python 3.10；requirements 特別記錄舊版 eval7 對 Python 3.11+ 的建置問題。使用者手機 Python 版本未知，因此不能承諾目前 eval7 組合可直接安裝。
- 沒有從固定版本找到 Android／Termux 實測證據。競賽限制 2 秒／768MB 是作者描述的環境限制，不是手機實測數字。
- 合理後續：部署最小執行檔與兩份資料，使用獨立低並行 worker，先做完整翻牌前／翻牌後決策冒煙測試，再測五桌 p95、最大延遲、RSS 與持續運作；上線前零未預期 fallback。這是建議，尚未執行。
