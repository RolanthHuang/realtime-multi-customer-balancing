# Profit Control 即時動態版本

這份交付保留 `profitcontrolsimulator16.py` 的核心投注、`wanted / unwanted / blacked` 投票，以及控制率選點邏輯，改成每次呼叫 `SimulationState.step()` 只計算一個 cycle。

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

`lowerbounds` 與 `upperbounds` 可給單一值，套用到所有商戶；也可給逗號分隔的每商戶值，例如 `--lowerbounds 0,0,0.01`。若使用多個值，數量必須等於 `runclients`。

`--candidate-count` 可設定 1–1000 個離散候選位置，預設為 100。改變候選數量時，一般投注與特定玩家投注的位置數會按照原始 100 候選模型的比例縮放；候選數也會同步用於賠付維度。

測試或不開啟視窗：

```bash
python3 profit_control_realtime.py --cycles 20 --no-show --seed 7
```

如果視窗更新太慢，可提高 `--draw-every`，例如每 5 個 cycle 畫一次：

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

可在頁面輸入 `lowerbounds`、`upperbounds`、`runclients`、`candidateCount`、`cycles`、`controlrate`，按「開始／重新開始」後，模擬會以 step loop 邊算邊更新；也可暫停、單步執行與下載 CSV。

頁面右側新增 Wanted ↑ / Unwanted ↓ 3D 圖：

- 綠色為一般候選。
- 黃色為當期 wanted 階段候選。
- 紅色為當期實際選點；標題會註明是 `Controlled` 或 `Random`。
- 拖曳可旋轉、滾輪可縮放、雙擊可重設視角。
- 游標移到柱體可查看 candidate、wanted、unwanted、blacked 與狀態。

3D 圖不會每一期強制重建。初始更新間隔為 `ceil(candidateCount / 40)` 期，並有 50–250ms 的最低時間間隔；瀏覽器也會依實際繪圖耗時自動放慢或恢復更新。模型仍然每一期完整計算，第 1 期、最後一期、暫停和單步操作一定會顯示最新狀態。

## 與原始檔案的關係

原始檔案 `profitcontrolsimulator16.py` 沒有被修改。新 Python 檔使用獨立的 `SimulationState`，因此可以由其他 Python 程式匯入：

```python
from profit_control_realtime import SimulationState

sim = SimulationState(lowerbounds=0.0, upperbounds=0.03,
                      runclients=10, candidate_count=100,
                      cycles=500, controlrate=25)
while sim.cycle_index < sim.cycles:
    snapshot = sim.step()
    print(snapshot.cycle, snapshot.selected_position, snapshot.wanted)
```

為了讓互動版在極端輸入下不中斷，對原始分群函式加入了空集合／小樣本保護；正常參數下的模型流程不變。
