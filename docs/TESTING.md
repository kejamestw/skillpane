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

每組執行六個案例：核心、管理、XSS 文字顯示、提示詞回歸、使用 Playwright 真實輸入／點擊／滾輪操作，以及掃描變更紀錄，共 24 個。四個既有腳本保留合成服務標記檢查；額外案例檢查搜尋、筆記草稿、儲存、側欄與字級偏好重載、清單及詳情捲動與水平溢出。

每個案例建立全新的合成服務、browser context 與動態 port；不重用既有服務、不接受外部 base URL。瀏覽器封鎖服務以外的網路請求，提示詞腳本攔截複製操作，不碰 OS 剪貼簿；未捕捉的 JavaScript 錯誤使測試失敗。預期的衝突或錯誤輸入 HTTP 回應由個別腳本驗證。服務子程序在測試結束時停止。失敗時不自動重試，以免掩蓋不穩定案例。

輸出採終端文字；不錄製 screenshot、trace、video，也不在 CI 上傳 artifacts。失敗診斷與合成資料只留在 Git 忽略的 `.runtime/`，不加入 repo。人工逐步除錯仍可依 [開發指南](DEVELOPMENT.md) 開啟獨立 fixture，逐一執行既有腳本。

## 結果判讀與限制

推送後核對確切 commit SHA 的工作結果。完整流程有 changes、四個 Python jobs、browser、secrets 及 validation，共八項；文件流程的 tests／browser 預期略過，其餘三項仍必須成功，見 [CI 流程](CI.md)。僅本機通過或已有 workflow，不代表遠端已成功。畫面測試驗證的是操作與排版邊界，不是字體美觀、實機流暢度或完整無障礙認證；Firefox 只驗證桌面，Safari／WebKit 與真實手機尚未涵蓋。

## Windows 啟動超時診斷

`test_launcher.py` 建立獨立程式副本、合成 home 與動態 port，於該子程序設定 `SKILLPANE_LAUNCHER_DIAGNOSTICS=1`；正式啟動器預設不印診斷。每個 Start／Stop 保持 60 秒上限，沒有自動重試；Windows CI 工作維持 25 分鐘限制。

```sh
python -B -m unittest discover -s tests -p test_launcher_diagnostics.py -v
python -B -m unittest discover -s tests -p test_launcher.py -v
```

單次摘要包含 Start／Stop、PowerShell 類型、結果、整體毫秒數、最後階段、尚未結束的最內層階段，以及已完成階段耗時。可區分排他鎖、紀錄讀寫、程序及 CIM 身分查詢、監聽查詢、Python 啟動、健康回應與停止等待。整體時間包含 PowerShell 啟動／退出，階段鐘從載入共用腳本開始；兩者差距不能直接當成純 PowerShell 啟動耗時。`no-marker` 只表示沒有可辨識階段，不能據此判定根因。

父程序另以單調時鐘觀察下列欄位，皆為同一輪測試起點之後的毫秒數；`script_elapsed_ms` 使用子程序自己的階段鐘，兩種時鐘不能當作相同起點直接相減。

| 欄位 | 意義 |
| --- | --- |
| `spawn_ms` | 呼叫 Popen 前至建立呼叫返回，包含可觀察的 OS 程序建立等待 |
| `first_stage_seen_ms` | 父程序首次讀到允許清單內標記的時間上界 |
| `exit_stage_seen_ms` | 父程序首次讀到 launcher-exit 標記的時間上界 |
| `process_end_ms` | 父程序觀察到正常結束／非零退出的時間；超時或尚未觀察到則為 -1 |
| `script_elapsed_ms` | 最後有效標記的子程序時鐘值；未必代表完整腳本已結束 |

每 100 ms 輪詢受限的 stderr 尾端與自有程序，排程及檔案 I/O 仍可能增加取樣延遲。很短的腳本可能在同一次取樣才看到首尾標記；`-1` 表示未知，不能當作零，也不能把觀測時間直接當成標記實際寫入時間。`process_end_ms - exit_stage_seen_ms` 只反映已觀測到的退出等待；若兩者同次取得，無法排除較短的實際等待。

原有診斷開關案例亦輸出 `action=Probe`：在同一隔離副本只載入共用腳本、測試固定標記及開關，不啟動 Skillpane、查詢技能或呼叫 HTTP。兩種 PowerShell 各有未設定、關閉與開啟三種探針，開關關閉時標記時間應保持未知。它可作為命令前後等待的觀測對照，不是不同版本的正式效能基準。

測試從呼叫 Popen 前開始計算同一份 60 秒預算，建立呼叫返回後只等待剩餘時間，不另外重新給 60 秒；若建立已耗盡預算，即使程序已結束也判逾時。測試沒有另設可中斷 OS 建立呼叫的監督程序，因此該呼叫若阻塞，須等它返回才能處理；不宣稱硬性牆鐘上限。逾時只終止本次 Popen 持有的程序，清理最多再等 10 秒，清理失敗維持失敗。不依紀錄檔或輸出取得 PID 來終止其他程序，亦不自動重試。

摘要只接受固定標籤及 ASCII 毫秒數，讀取 stderr 尾端最多 16 KiB、保留最多 128 個事件；忽略原始文字、未知標籤與倒退的時間。超時仍印出已完成及未完成階段，維持測試失敗，不把 TimeoutExpired 的完整命令或輸出帶入錯誤訊息。原始 stdout／stderr 留在 Git 忽略的合成 fixture，CI 不上傳；檢查失敗也只印安全摘要。

觀測欄位拒絕未知 key、字串、布林及小於 -1 的值；建立與清理錯誤採固定的 spawn-error／cleanup-error 摘要，原始例外鏈不附在失敗訊息。測試涵蓋模擬時鐘、仍存活及已結束的慢速建立、超時後自有程序清理，以及實際的合成 Python 子程序。

診斷預設關閉與標籤拒絕在 Windows PowerShell 5.1／7 驗證。查詢契約另測成功空結果、提供者錯誤向外傳遞，以及非法／可疑 port 在查詢前拒絕；真實占用、偽裝健康回應、紀錄竄改、不同 checkout 與持鎖案例仍須全部執行。

監聽查詢改用 `Get-CimInstance` 的 provider filter，仍讀相同 `root/StandardCimv2` 的 `MSFT_NetTCPConnection`，保留 `State = 2`（Listen）、port 與後續 loopback／socket 擁有者檢查；查詢失敗不能視為 port 可用。依據：[Microsoft Get-CimInstance 的 Filter](https://learn.microsoft.com/en-us/powershell/module/cimcmdlets/get-ciminstance?view=powershell-5.1#-filter)、[Get-NetTCPConnection](https://learn.microsoft.com/en-us/powershell/module/nettcpip/get-nettcpconnection)。Listen 數值另核對 Windows 內建 `NetTCPIP/MSFT_NetTCPConnection.cdxml`。

首次 GitHub 超時發生在雲端 Windows runner 的初始 `self.start()`，不是使用者電腦，也尚未進入持鎖競爭。同一舊提交第二次成功，只能確認未必每次重現。階段診斷與查詢改善已由 `95b7f6d` 的遠端 CI 驗收；後續父程序觀測仍須核對自己的新 SHA，不能把本機較快或先前遠端成功視為雲端超時根因已修復，見 [CI 紀錄](CI.md#後續啟動器診斷)。

維護新版本時先跑受影響案例，再執行必要完整回歸；本機驗證不取代遠端矩陣。發布前仍須檢查候選檔案、Git 歷史與公開邊界，這些測試不是零漏洞證明或獨立安全審查。

依據：[Playwright 安裝](https://playwright.dev/docs/intro)、[測試瀏覽器](https://playwright.dev/docs/browsers)。

## 手動啟動因素診斷

`tests/startup_probe.py` 是開發工具，不是面板功能，也不是效能基準。先前雲端正式案例的首標記前約有 21～24 秒等待，而最小探針僅約 0.3 秒；此工具用固定案例縮小差異來源，不把成功執行當作超時根因已修復。

在 Windows repository 根目錄執行：

```sh
python -B tests/startup_probe.py
python -B tests/startup_probe.py --shell windows-powershell
python -B tests/startup_probe.py --shell powershell7
```

預設兩種 shell 都必須可用，缺少指定 shell 時明確失敗；不靜默略過。每個 shell 七組、各執行一次，沒有自動重試：

| 案例 | 對照 |
| --- | --- |
| minimal-default／minimal-bypass | 相同最小載入，僅差本次程序的 ExecutionPolicy 參數 |
| header-join | 以 Join-Path 組合 runtime 與共用腳本路徑 |
| header-dotnet | 僅用 .NET 組合路徑，不提前使用管理模組 cmdlet |
| header-qualified | 明確以 Microsoft.PowerShell.Management 指定 Join-Path |
| header-import | 在路徑操作前明確 Import-Module，分開觀察載入時間 |
| entry-body-parse | 保留正式入口的剩餘文字供解析，但放在頂層 return 後，不執行 |

逐步 `steps_ms` 由獨立腳本時鐘記錄 entry、preferences-ready、module-ready、runtime-path-ready、shared-path-ready、shared-ready、exit。父程序的首次標記在入口處輸出，輪詢仍有 100 ms 取樣及排程誤差；共用腳本自己的時鐘在載入時才開始，不能把不同起點的欄位直接相減當作精準啟動分解。

工具只複製共用腳本與受檢查的入口文字到 `.runtime/startup-probes/`，環境變數使用與正式啟停測試相同的必要 OS 允許清單、合成 HOME／USERPROFILE，不沿用 PSModulePath、既有程序執行原則或憑證。這是隔離測試條件，不代表使用者的原生 shell 設定。入口排版不符安全截斷契約時拒絕產生腳本，LF／CRLF 均支援；最後核對原始檔指紋，以及副本沒有建立 `.data/`／`.runtime/`。

所有案例在服務操作前返回，未啟動 Python 服務、讀取技能、查詢連接埠、開瀏覽器或修改系統執行原則。固定 port 參數只是解析輸入，不繫結 socket。原始 stdout／stderr 留在忽略的合成 fixture，不清理既有資料、不上傳 artifacts；console 只印固定案例、shell、階段名稱及數值。失敗不回印原始例外或命令。

同一工具可由 GitHub Actions 的 `Launcher startup diagnosis` 手動執行。它使用兩組 Windows 工作，每組七筆、10 分鐘工作上限，每筆沿用 60 秒預算與最多另等 10 秒的自有程序清理。OS 建立呼叫無法由此方式中斷，整體上限仍由 Actions 控制。它不因 push／PR 自動執行，不影響既有八項 CI；推送工具後仍需另外手動執行並核對確切 SHA，工具尚未推送前不能宣稱已在雲端驗收。

PowerShell 初次使用模組內命令可能觸發自動載入，Join-Path 也依賴 provider；因此換成 .NET 可能只是把初始化成本移到後續 cmdlet，這裡僅作診斷，不據此改寫正式路徑與身分檢查。依據：[模組自動載入](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_modules?view=powershell-5.1)、[Join-Path](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.management/join-path?view=powershell-5.1)。命令列 ExecutionPolicy 僅作用於該 session，不改 registry，見 [powershell.exe 參數](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_powershell_exe?view=powershell-5.1)。

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
