# 音樂小工具

所有工具集中在這個 repo，用 GitHub Pages 部署。

網址：https://joycelee0326.github.io/my-tool/

| 資料夾 | 工具 | 網址 |
|---|---|---|
| `exam-prep/` | 臺藝國樂所筆試準備 | https://joycelee0326.github.io/my-tool/exam-prep/ |
| `score-video/` | 樂譜 × 演奏影片對照 | https://joycelee0326.github.io/my-tool/score-video/ |

## 新增一個工具

1. 開一個新資料夾（名稱用英文小寫和連字號，例如 `sight-reading`），把工具的 `index.html` 放進去。
2. 打開最外層的 `index.html`，複製一段 `<li class="tool">…</li>`，改成新工具的連結、標題和說明。
3. 在上面的表格加一行。

## 更新樂譜對照工具時

`score-video/sw.js` 會把檔案存起來供離線使用。改了 `score-video/` 裡的檔案以後，把 `sw.js` 第一行的版本號加 1（例如 `my-tool-score-video-v1` → `v2`），手機上的版本才會更新。
