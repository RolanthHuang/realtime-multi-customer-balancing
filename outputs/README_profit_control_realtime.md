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
  --cycles 500 \
  --controlrate 25
```

`lowerbounds` 與 `upperbounds` 可給單一值，套用到所有商戶；也可給逗號分隔的每商戶值，例如 `--lowerbounds 0,0,0.01`。若使用多個值，數量必須等於 `runclients`。

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

可在頁面輸入 `lowerbounds`、`upperbounds`、`runclients`、`cycles`、`controlrate`，按「開始／重新開始」後，模擬會以 step loop 邊算邊重畫 Canvas；也可暫停、單步執行與下載 CSV。

## 與原始檔案的關係

原始檔案 `profitcontrolsimulator16.py` 沒有被修改。新 Python 檔使用獨立的 `SimulationState`，因此可以由其他 Python 程式匯入：

```python
from profit_control_realtime import SimulationState

sim = SimulationState(lowerbounds=0.0, upperbounds=0.03,
                      runclients=10, cycles=500, controlrate=25)
while sim.cycle_index < sim.cycles:
    snapshot = sim.step()
    print(snapshot.cycle, snapshot.selected_position)
```

為了讓互動版在極端輸入下不中斷，對原始分群函式加入了空集合／小樣本保護；正常參數下的模型流程不變。
