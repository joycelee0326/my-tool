# 音樂小工具

所有工具集中在這個 repo，用 GitHub Pages 部署。

網址：https://joycelee0326.github.io/my-tool/

| 資料夾 | 工具 | 網址 |
|---|---|---|
| `exam-prep/` | 臺藝國樂所筆試準備 | https://joycelee0326.github.io/my-tool/exam-prep/ |
| `score-video/` | 樂譜 × 演奏影片對照 | https://joycelee0326.github.io/my-tool/score-video/ |
| `sight-reading/` | 揚琴視奏練習產生器 | https://joycelee0326.github.io/my-tool/sight-reading/ |
| `concerts/` | 音樂會搶票資訊欄 | https://joycelee0326.github.io/my-tool/concerts/ |

## 新增一個工具

1. 開一個新資料夾（名稱用英文小寫和連字號，例如 `sight-reading`），把工具的 `index.html` 放進去。
2. 打開最外層的 `index.html`，複製一段 `<li class="tool">…</li>`，改成新工具的連結、標題和說明。
3. 在上面的表格加一行。

## 音樂會資訊欄怎麼更新

- `scripts/fetch_concerts.py` 負責抓資料，寫進 `concerts/data.json`；`scripts/cache/opentix.json` 是 OPENTIX 節目頁的快取，只重抓有變動的節目。
- `.github/workflows/concerts.yml` 每天台灣時間 07:00、12:00、19:00 自動執行，有新資料就 commit。也可以到 GitHub 的 Actions 頁面手動按 Run workflow。
- 自己電腦上手動更新：`python scripts/fetch_concerts.py`（只需要 Python，不用裝套件）。
- 某個網站抓失敗時會沿用上次的資料，頁面上方會標示是哪個來源失敗。
- 樂種分類規則在 `fetch_concerts.py` 的 `GENRE_RULES`，分錯的話在對應的那一行加關鍵字即可。

## 更新樂譜對照工具時

`score-video/sw.js` 會把檔案存起來供離線使用。改了 `score-video/` 裡的檔案以後，把 `sw.js` 第一行的版本號加 1（例如 `my-tool-score-video-v1` → `v2`），手機上的版本才會更新。
