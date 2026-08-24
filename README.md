# Realtime Multi-Customer Balancing

以原始 `profitcontrolsimulator16.py` 模型為基礎的即時動態版本。

## Files

- `outputs/profit_control_realtime.py` — Python + Matplotlib 即時版本
- `outputs/profit_control_realtime.html` — 不需安裝套件的瀏覽器互動版本
- `outputs/README_profit_control_realtime.md` — 安裝、執行與參數說明

兩個版本都支援 `lowerbounds`、`upperbounds`、`runclients`、`candidateCount`、`cycles`、`controlrate`，並提供預設值。

瀏覽器版同時顯示商戶 profit rate／投注圖，以及可拖曳旋轉的 Wanted ↑ / Unwanted ↓ 3D 圖。3D 圖會依候選數量和實際繪圖耗時自動調整更新頻率，模型計算仍逐期完整執行。
