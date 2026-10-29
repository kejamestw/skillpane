# 自動化測試與安裝升級驗證

CI 在 GitHub Actions runner 執行。它在 runner 的 `127.0.0.1` 啟動獨立服務，不會連線維護者電腦的 8766，也不使用真實技能、筆記或提示詞。日常執行 Skillpane 只需要 Python；以下 npm 套件僅供開發測試。

## Python 與 CLI 流程

```sh
python -B -m unittest discover -s tests -v
```

GitHub 的四組矩陣為 Windows／Linux × Python 3.11／3.13。`tests/test_lifecycle.py` 每個案例把應用程式與前端複製到包含空白的全新目錄，沒有 `.git`、Node 套件或既有整理資料。以真正的 `python -m skillpane --port 0` 子程序執行，使用 OS 配發的 loopback port，並覆寫 HOME／USERPROFILE 為合成目錄。子程序只繼承必要的 OS 環境變數，不繼承憑證或 Python import 設定。

| 案例 | 驗證 |
| --- | --- |
| 全新來源程式包 | CLI help 不建立資料、健康檢查、六項前端資源及 CSP、儲存筆記／提示詞、停止後不再回應、重啟延續識別與資料 |
| 未版本化舊資料 | 首次升級轉為 format 2、原始位元組備份、收藏／筆記／標記延續、還原預覽不改資料、套用與防重用、重啟後保留 |
| 不含提示詞的 format 2 | 舊自訂欄位／比較／設定延續、新增提示詞、可攜備份匯出、預覽與套用、重啟後完整保留 |
| 損壞／未來格式 | 仍可讀技能、拒絕整理寫入，啟停期間保留原檔 |

所有案例另核對合成 SKILL.md 指紋不變。這驗證新版對舊資料格式的相容性，不表示執行了所有歷史版本 binary、Python 安裝程式、Windows 雙擊啟動器或每種 OS 設定。Windows `Start.ps1`／`Stop.ps1` 的互動及 PID 身分檢查仍需適用環境人工驗收；自動測試使用真正的跨平台 CLI。

## 瀏覽器

使用 Node 22 以上（CI 固定 Node 24）與可由 `python` 呼叫的 Python：

```sh
npm ci --ignore-scripts --no-fund --no-audit
npx --no-install playwright install chromium firefox
npm run test:browser
```

Linux runner 使用 `npx --no-install playwright install --with-deps chromium firefox` 安裝必要系統函式庫。Playwright 與遞迴套件版本、registry URL 與 integrity 均鎖定於 package-lock.json；不執行 npm lifecycle scripts。下載瀏覽器仍依賴 Playwright 官方發行管道與 HTTPS。

可用 `SKILLPANE_TEST_PYTHON` 指定 Python 執行檔。公司代理環境若 Node 不信任已安裝的公司憑證，Node 24 可透過程序層級 `NODE_OPTIONS=--use-system-ca` 使用系統信任庫；不要關閉 TLS 驗證。`PLAYWRIGHT_BROWSERS_PATH` 可指向本機快取；安裝與測試時必須使用同一設定。

```sh
npm run test:browser -- --project=chromium-desktop
```

| Project | 視窗 |
| --- | --- |
| chromium-desktop | 1280×720 |
| chromium-compact | 1024×480 |
| chromium-mobile | 390×844，觸控與行動裝置模擬 |
| firefox-desktop | 1280×720 |

每組執行五個案例：核心、管理、XSS 文字顯示、提示詞回歸，以及使用 Playwright 真實輸入／點擊／滾輪操作的案例，共 20 個。四個既有腳本保留合成服務標記檢查；額外案例檢查搜尋、筆記草稿、儲存、側欄與字級偏好重載、清單及詳情捲動與水平溢出。

每個案例建立全新的合成服務、browser context 與動態 port；不重用既有服務、不接受外部 base URL。瀏覽器封鎖服務以外的網路請求，提示詞腳本攔截複製操作，不碰 OS 剪貼簿；未捕捉的 JavaScript 錯誤使測試失敗。預期的衝突或錯誤輸入 HTTP 回應由個別腳本驗證。服務子程序在測試結束時停止。失敗時不自動重試，以免掩蓋不穩定案例。

輸出採終端文字；不錄製 screenshot、trace、video，也不在 CI 上傳 artifacts。失敗診斷與合成資料只留在 Git 忽略的 `.runtime/`，不加入 repo。人工逐步除錯仍可依 [開發指南](DEVELOPMENT.md) 開啟獨立 fixture，逐一執行既有腳本。

## 結果判讀與限制

推送後核對確切 commit SHA 的四個 Python jobs、一個 browser job 及一個 secrets job。僅本機通過或已有 workflow，不代表遠端已成功。畫面測試驗證的是操作與排版邊界，不是字體美觀、實機流暢度或完整無障礙認證；Firefox 只驗證桌面，Safari／WebKit 與真實手機尚未涵蓋。

維護新版本時先跑受影響案例，再執行必要完整回歸；本機驗證不取代遠端矩陣。發布前仍須檢查候選檔案、Git 歷史與公開邊界，這些測試不是零漏洞證明或獨立安全審查。

依據：[Playwright 安裝](https://playwright.dev/docs/intro)、[測試瀏覽器](https://playwright.dev/docs/browsers)。
