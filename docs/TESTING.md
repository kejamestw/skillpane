# 自動化測試與安裝升級驗證

CI 在 GitHub Actions runner 執行。它在 runner 的 `127.0.0.1` 啟動獨立服務，不會連線維護者電腦的 8766，也不使用真實技能、筆記或提示詞。日常執行 Skillpane 只需要 Python；以下 npm 套件僅供開發測試。

本批新增 [保守文件分流](CI.md)：完整執行仍包含四組 Python 與 24 項 browser；純文件明確略過這些工作，分流負向測試、文件連結、secrets 與最後 validation 仍執行。新的 GitHub 編排須於其提交推送後驗收。

## Python 與 CLI 流程

```sh
python -B -m unittest discover -s tests -v
```

GitHub 的四組矩陣為 Windows／Linux × Python 3.11／3.13。`tests/test_lifecycle.py` 每個案例把應用程式與前端複製到包含空白的全新目錄，沒有 `.git`、Node 套件或既有整理資料。以真正的 `python -m skillpane --port 0` 子程序執行，使用 OS 配發的 loopback port，並覆寫 HOME／USERPROFILE 為合成目錄。子程序只繼承必要的 OS 環境變數，不繼承憑證或 Python import 設定。

| 案例 | 驗證 |
| --- | --- |
| 全新來源程式包 | CLI help 不建立資料、健康檢查、七項前端資源及 CSP、儲存筆記／提示詞、停止後不再回應、重啟延續識別與資料 |
| 未版本化舊資料 | 首次升級轉為 format 2、原始位元組備份、收藏／筆記／標記延續、還原預覽不改資料、套用與防重用、重啟後保留 |
| 不含提示詞的 format 2 | 舊自訂欄位／比較／設定延續、新增提示詞、可攜備份匯出、預覽與套用、重啟後完整保留 |
| 損壞／未來格式 | 仍可讀技能、拒絕整理寫入，啟停期間保留原檔 |

所有案例另核對合成 SKILL.md 指紋不變。這驗證新版對舊資料格式的相容性，不表示執行了所有歷史版本 binary、Python 安裝程式或每種 OS 設定。跨平台 CLI 與下述 Windows 啟動器分別測試；雙擊 `.cmd`、實際開啟瀏覽器及其他 OS 桌面互動仍需人工驗收。

## 掃描變更紀錄（0.4）

`tests/test_changes.py` 使用合成技能，驗證首次基準、去重、重啟、唯一搬移、外掛版本與舊快取內容、略過讀取時抑制消失事件、300 筆上限、備份排除、損壞／重複鍵／未來格式／超大檔案、外部改寫與原子替換失敗、symlink／Windows junction、容量與事件型別、並行重掃及同源 HTTP。連結測試只指向本案自己的合成目錄。

`tests/e2e/changes.spec.cjs` 在四種瀏覽器設定驗證面板基準、14 筆合成變更、搜尋／類型篩選、惡意名稱以純文字顯示、返回技能保留草稿、滾輪、重掃去重、重新載入與大字級邊界。測試專用的變更準備端點只存在 `tests/browser_fixture.py`，正式伺服器不提供此端點。這些測試不代表即時監控、所有檔案差異或真實安裝／使用紀錄已驗證。

## Windows 啟動器

`tests/test_launcher.py` 在 Windows 執行八個真實子程序案例，自動納入原有 Windows Python CI；Linux 明確略過。每案將程式與啟動腳本複製到含空白及中文的獨立路徑，只使用合成 home、整理資料與非 8766 的 OS 配發測試連接埠。測試只停止本案自己啟動、保留原始身分紀錄的服務，不以被篡改的 PID 執行清理。

Windows CI 的整個測試工作上限為 25 分鐘，Linux 維持 10 分鐘；每次啟停子程序仍有 60 秒上限，不略過 Windows 案例。首次遠端驗證顯示 hosted Windows runner 反覆啟動 PowerShell 明顯慢於本機，原 10 分鐘總額度在第五項啟動器案例尚未完成時取消工作。調整總額度後仍須重新核對確切提交的完整結果，逾時取消不能計為通過。

| 案例 | 驗證 |
| --- | --- |
| 啟停與重啟 | 健康、合成技能、重複啟動不改紀錄及資料、連續停止、重啟延續識別 |
| 錯誤連接埠與篡改紀錄 | 建立時間、root、port、Python、PID 型別及未支援版本不符時拒絕，原服務繼續回應 |
| 其他 checkout | 改寫紀錄 root 仍不能接管或停止另一份程式 |
| 連接埠占用 | 一般服務及偽裝成 Skillpane 的健康回應都被拒絕，不建立整理資料 |
| 缺少／損壞／舊格式紀錄 | 無紀錄停止不做事，無效連接埠拒絕；損壞或仍指向活程序的舊紀錄不自動改寫 |
| 啟動失敗 | 子程序錯誤不回報 ready，不遺留可連線服務 |
| 同時操作 | 另一程序持有 launcher.lock 時，啟動及停止都拒絕，原服務與紀錄保留 |
| PowerShell 7 | 和 Windows PowerShell 5.1 共用紀錄及程序身分驗證；未安裝 7 時略過此案 |

單獨執行：`python -B -m unittest discover -s tests -p test_launcher.py -v`。呼叫啟動器使用檔案捕捉診斷，不以 pipe EOF 判定背景服務已停止；診斷及合成產物只留在忽略目錄。測試使用 `-NoBrowser`，沒有驗證雙擊及預設瀏覽器開啟。

啟動器依賴 Windows 的 CIM 與 NetTCPIP 查詢；查詢不可用時拒絕操作，不把查詢失敗當成沒有程序或空閒連接埠。程序身分檢查不是對惡意同帳號程式的隔離；舊格式活程序需先由升級前啟動器停止。

啟動參數的引號及監聽查詢依據：[Microsoft Start-Process](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.management/start-process?view=powershell-7.5)、[Get-NetTCPConnection](https://learn.microsoft.com/en-us/powershell/module/nettcpip/get-nettcpconnection?view=windowsserver2025-ps)。程序 handle 的生命週期見 [Process 類別](https://learn.microsoft.com/en-US/dotnet/api/System.Diagnostics.Process)。

## 掃描邊界

`tests/test_scan_boundaries.py` 以六項合成案例驗證：含 SKILL.md 的技能資料夾停止向下掃描；沒有該檔案的集合、系統與外掛版本目錄仍展開；進入目錄前排除範圍外路徑與被排除目錄；合法連結別名保留，循環停止；無效的外層技能不使內附副本變成獨立技能；先前副本的筆記與收藏仍以未關聯資料保留。

這是面板的清單邊界，不推定各工具的載入行為。測試核對合成技能位元組不變；不使用真實技能、筆記或提示詞。0.3.2 的瀏覽器 fixture 另外放入兩個巢狀鏡像，核心案例確認它們不影響總數，也確認範圍說明可見。

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

## 文件展示素材

README 與操作導覽的四張 PNG 使用正式前端及 `scripts/demo_fixture.py` 的虛構資料：六個個人技能、一個內建項目、自訂中文名稱、筆記與一筆常用提示詞。另在隔離 home 事先準備新增、SKILL.md 變更與移到排除目錄三種情境，產生三筆掃描事件；掃描與基準時間固定為示範值，不使用真實技能或原始作者內容。

只預覽合成展示需要 Python，不需要 Node：

```sh
python -B scripts/demo_fixture.py
```

開啟終端印出的動態 loopback 位址，以 Ctrl+C 停止。每次建立新的 `.runtime/docs-demo-*`，不讀取既有個人整理資料，不占用正式 8766，也不自動清理歷次合成產物。

重製圖片需先依上方步驟安裝鎖定的開發套件與 Chromium，再執行：

```sh
node scripts/capture-docs.cjs
```

同樣支援 `SKILLPANE_TEST_PYTHON` 與 `PLAYWRIGHT_BROWSERS_PATH`。腳本只連自己啟動的全新合成服務，不接受外部 base URL；確認展示標記、七個目前項目及三種類型事件、封鎖外部請求、檢查未捕捉錯誤與截圖期間合成原文不變。圖片寫入 `docs/images/desktop.png`、`prompt-editor.png`、`mobile.png`、`changes.png`，會取代同名素材；更新後需人工逐張檢視，再檢查 Git 候選檔案。PNG 不包含瀏覽器網址列；不要用真實面板截圖替換。

這是手動執行的文件產生流程，未加入 CI，也不改變 CI 不錄製／上傳畫面的政策。PNG 內容需要來源控管及人工視覺檢查，文字型機密掃描不能代替這項檢查；字型可能隨 OS 改變。手機圖僅為視窗模擬。

截圖先完整寫入 `.runtime/` 暫存 PNG，再原子替換目標，避免檔案正被讀取時直接覆寫失敗或留下半張圖；失敗暫存檔保留於忽略目錄供診斷。
