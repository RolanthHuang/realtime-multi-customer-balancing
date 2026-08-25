# Multi-Channel Cash-Flow Balancing Simulator

這份交付將多商戶交易流入、結算流出與決策方案評估改成可逐期執行的即時模擬。每次呼叫 `SimulationState.step()` 只計算一個結算週期，並回傳當期的 Settlement Margin、Stability Support、Risk Exposure 與最終執行方案。原始計算邏輯和預設值保持不變。

## 1. Python Matplotlib 即時版

檔案：[profit_control_realtime.py](./profit_control_realtime.py)

需要 NumPy 與 Matplotlib：

```bash
python3 -m pip install numpy matplotlib
```

執行預設值：

```bash
python3 profit_control_realtime.py
```

執行時視窗會邊計算邊更新。可用參數：

```bash
python3 profit_control_realtime.py \
  --lowerbounds 0.0 \
  --upperbounds 0.03 \
  --runclients 10 \
  --candidate-count 100 \
  --cycles 500 \
  --controlrate 25
```

`lowerbounds` 與 `upperbounds` 分別對應 Target Margin Floor 與 Target Margin Ceiling，可給單一值套用到所有商戶；也可給逗號分隔的每商戶值，例如 `--lowerbounds 0,0,0.01`。若使用多個值，數量必須等於 `runclients`。

`--candidate-count` 可設定 1–1000 個離散 Decision Options，預設為 100。改變方案數量時，一般交易流與指定流量分群的分布位置會按照 100 個方案的基準比例縮放；方案數也會同步用於結算流出維度。

測試或不開啟視窗：

```bash
python3 profit_control_realtime.py --cycles 20 --no-show --seed 7
```

如果視窗更新太慢，可提高 `--draw-every`，例如每 5 個 period 畫一次：

```bash
python3 profit_control_realtime.py --draw-every 5 --interval-ms 10
```

## 2. 瀏覽器 HTML 互動版

檔案：[profit_control_realtime.html](./profit_control_realtime.html)

直接雙擊 HTML，或在輸出資料夾執行：

```bash
python3 -m http.server 8000
```

接著開啟 <http://localhost:8000/profit_control_realtime.html>。HTML 不需要額外 JavaScript 套件或網路連線。

HTML 畫面提供 Target Margin Floor、Target Margin Ceiling、Merchant Count、Decision Option Count、Simulation Periods 與 Policy Application Rate。按「開始／重新開始」後，模擬會以 step loop 邊算邊更新；也可暫停、單步執行與下載 CSV。為保持既有程式介面相容，底層仍使用 `lowerbounds`、`upperbounds`、`runclients`、`candidateCount`、`cycles`、`controlrate`。

頁面右側提供 Stability Support ↑ / Risk Exposure ↓ 3D 圖：

- 綠色為 Available Options。
- 黃色為當期 Policy Shortlist。
- 紅色為當期 Executed Option；標題會註明是 `Policy-Guided` 或 `Baseline Sampling`。
- 拖曳可旋轉、滾輪可縮放、雙擊可重設視角。
- 游標移到柱體可查看 Decision Option、Stability Support、Risk Exposure、Constraint Flags 與狀態。

3D 圖不會每一期強制重建。初始更新間隔為 `ceil(candidateCount / 40)` 期，並有 50–250ms 的最低時間間隔；瀏覽器也會依實際繪圖耗時自動放慢或恢復更新。模型仍然每一期完整計算，第 1 期、最後一期、暫停和單步操作一定會顯示最新狀態。

每一期代表一個結算窗口：系統比較各 Decision Option 對不同商戶 Settlement Margin 的 Stability Support 與 Risk Exposure，再依 Policy Application Rate 執行政策引導或基準抽樣決策。這項定義可用於支付路由、平台結算、資金分配，以及其他高頻交易風險情境。

## 與原始檔案的關係

原始檔案 `profitcontrolsimulator16.py` 沒有被修改。新 Python 檔使用獨立的 `SimulationState`，因此可以由其他 Python 程式匯入：

```python
from profit_control_realtime import SimulationState

sim = SimulationState(lowerbounds=0.0, upperbounds=0.03,
                      runclients=10, candidate_count=100,
                      cycles=500, controlrate=25)
while sim.cycle_index < sim.cycles:
    snapshot = sim.step()
    print(snapshot.cycle, snapshot.latest_profitrates)
```

為了讓互動版在極端輸入下不中斷，對原始分群函式加入了空集合／小樣本保護；正常參數下的模型流程不變。
