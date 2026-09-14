# Realtime Multi-Customer Balancing

以可逐期執行的通用決策模型為基礎，展示多商戶 Settlement Margin、資金流入與決策方案之間的即時動態平衡。

## Files

- `outputs/profit_control_realtime.py` — Python + Matplotlib 即時版本
- `outputs/profit_control_realtime.html` — 不需安裝套件的瀏覽器互動版本
- `outputs/algorithm-autopsy.html` — 逐關拆解原始決策函數與數字流向的互動展示
- `outputs/README_profit_control_realtime.md` — 安裝、執行與參數說明

兩個版本都支援 `lowerbounds`、`upperbounds`、`runclients`、`candidateCount`、`cycles`、`controlrate`，並提供預設值；HTML 畫面將它們呈現為 Target Margin、Merchant Count、Decision Option Count、Simulation Periods 與 Policy Application Rate。

瀏覽器版同時顯示商戶 Settlement Margin／當期資金流入，以及可拖曳旋轉的 Stability Support ↑ / Risk Exposure ↓ 3D 圖。每一期代表一個結算窗口，系統比較多個決策方案後執行 Policy-Guided 或 Baseline Sampling 決策；3D 圖會依方案數量和實際繪圖耗時自動調整更新頻率，模型計算仍逐期完整執行。

`algorithm-autopsy.html` 使用可重現的合成數字，把同一個決策週期拆成九關：共同候選空間、異常流量權重、`wanted / unwanted / blacked` 三維離散向量、`targetfunctionbeta`、`penLayers`、平方距離選層、`deepwanted`、政策／基準抽樣，以及共同結果回饋。每一關都可看到問題、原始函數、輸入輸出與候選集合如何改變。

九個階段各自搭配對應圖形；流量門檻、W 切分、層間距離與 deepwanted 使用數值圖，`penLayers` 可重播逐層排除動畫，政策分支會移動 Random Draw 指標，共同結果則以動態路徑回饋所有商戶。動畫只在進入階段或手動重播時執行，不會持續循環。
