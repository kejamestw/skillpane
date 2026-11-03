# Windows 桌面原型

此為選用的本機原型，尚非正式桌面 release。沿用目前的 HTML、CSS、JavaScript 與 Python 後端，使用 pywebview／WebView2 顯示獨立視窗。瀏覽器版的啟動方式與零第三方執行相依需求不變。

## 啟動與退出

已打包的資料夾內雙擊 `Skillpane.exe`，不需自行安裝 Python。整個資料夾必須一起保留，不能只搬走 EXE。Windows 需要 Microsoft WebView2 Runtime 與 .NET Framework 4.6.2 以上版本；原型不會默默下載執行環境、更改系統設定或要求管理員權限。

從原始碼啟動時，先依下節建立選用環境，再雙擊根目錄 `Open-Skillpane-Desktop.cmd`。啟動器不經 PowerShell，也不自動安裝套件。

再次啟動相同桌面資料目錄的實例時，只通知既有視窗恢復顯示，不另開服務。Windows 可能限制其他程序搶前景；若未移到最前面，可從工作列選取。關閉視窗會結束此應用程式內的 HTTP 服務，不接管或停止 `Start.ps1` 啟動的服務。沒有系統匣常駐或開機自啟動。

正常退出會檢查未儲存筆記、整理資訊與 Prompt 草稿；有草稿才詢問是否離開，正在操作時請等完成。應用程式當機、強制結束或關機仍可能遺失尚未儲存的草稿。

## 資料位置與搬移

- 桌面版資料：`%LOCALAPPDATA%\Skillpane\data\`，包含收藏、筆記、常用提示詞、備份及掃描基準。
- 桌面顯示偏好：`%LOCALAPPDATA%\Skillpane\desktop-preferences.json`，只儲存主題、字級與側欄開關；正常關閉時儲存。強制結束可能失去此次顯示設定。
- 獨立 WebView2 快取：`%LOCALAPPDATA%\Skillpane\webview\`；不匯入或使用一般瀏覽器的個人設定與擴充功能。

瀏覽器版預設仍使用 checkout 的 `.data/`，兩版不共用整理檔，也不自動掃描或搬移舊版資料。若要搬移，先在原面板的「資料與備份」下載備份，再到桌面版預覽匯入，確認後套用。掃描紀錄不在整理資料備份內；桌面版會重新建立觀察基準。字級與主題可在桌面版重新選擇。

升級時更換程式資料夾即可，保留上述使用者資料目錄。刪除程式不代表同意刪除使用者資料；原型未提供會清除資料的解除安裝程式。

## 建立隔離環境與打包

目前打包鎖定 **Windows x64、CPython 3.12**。在專案根目錄執行，`python` 須指向此版本；其他平台繼續使用瀏覽器版。這些是開發命令，不是一般使用者必須執行的步驟。

```powershell
python -m venv .runtime/desktop-build/venv
.runtime/desktop-build/venv/Scripts/python.exe -m pip install --require-hashes --only-binary=:all: -r requirements-desktop-bootstrap.lock
.runtime/desktop-build/venv/Scripts/python.exe -m pip install --require-hashes --no-build-isolation -r requirements-desktop.lock
.runtime/desktop-build/venv/Scripts/python.exe -m pip check
.runtime/desktop-build/venv/Scripts/python.exe -B scripts/build_desktop.py
```

版本與下載檔 SHA256 皆固定。proxy-tools 0.1.0 僅提供原始碼套件；它的 setup.py 已檢閱，使用固定的 setuptools／wheel 在隔離環境建置，不允許浮動的 build isolation 安裝。鎖定檔不代表依賴沒有漏洞；更新時仍須重新評估。

每次打包建立新的 `.runtime/desktop-build/<時間與隨機值>/dist/Skillpane/`，不覆蓋既有成品。採資料夾式輸出，不使用每次啟動解壓的 onefile。只收集明確的前端允許清單與套件資源，不包含 `.data/`、真實技能、測試資料、環境檔或 Git；附帶 Python、上游與桌面依賴的授權文件及中繼資料。

## 安全邊界與驗證

桌面服務綁定 `127.0.0.1` 的系統分配連接埠，不搶用 8766；保留 Host、Origin、Fetch Metadata、寫入 header 與 CSP 檢查。不提供遠端存取、CORS 或 HTTP 關機／啟動 API。技能仍唯讀，原文不當 HTML 執行。

不暴露 Python `js_api`；WebView2 host objects、web messaging、外部視窗、非應用程式頁面的導向與權限要求被停用／拒絕。下載僅接受本服務來源的 JSON Blob，需由使用者在儲存對話框選擇位置。沒有檔案任意讀寫或命令執行橋接，也不以放寬 CSP 的 `unsafe-eval` 來讀取狀態。

單一實例使用 Windows session-local mutex／event；訊號僅要求顯示視窗，不傳指令、URL 或技能資料。與瀏覽器版相同，同一 OS 使用者的其他程式仍可存取本機服務或資料，並非隔離惡意同使用者程序的沙箱。

```powershell
python -B -m unittest discover -s tests -p test_desktop.py -v
```

單元測試不需要 GUI 相依套件，使用合成 home 與資料；Windows 另測試實際 mutex／event。正式發行前還需要實際 EXE 的 WebView2 操作回歸、無 Python 的乾淨 Windows 環境、備份搬移與更新驗證、依賴與授權複核、發行簽章及安裝器。尚未提供自動更新、安裝器、macOS／Linux 桌面包，不能把本機打包成功當成正式發行驗收完成。

## 本機原型驗證（2026-11-03）

台灣時間（UTC+8），Windows x64、CPython 3.12.14、pywebview 6.2.1；以下為提交前的本機原型紀錄。只使用合成技能及隔離資料目錄：

- 桌面單元測試 10 項通過；既有 server、security、adversarial 回歸 37 項中 36 通過、1 個 POSIX 專項略過。
- 真實 WebView2 整合 17 項通過，涵蓋搜尋、主題／字級、草稿關閉取消、筆記儲存、單一實例、原生導向限制、JSON 下載、正常退出及技能原文未變。使用程式內測試操作與測試用對話框回覆，不等同實體滑鼠／鍵盤或人工驗收。
- PyInstaller 成品搬至含空白的新路徑，將 PATH 限為 System32，7 項檢查通過：獨立啟動、僅讀合成 home、前端版本與 CSP、獨立整理儲存、第二次啟動沿用實例、技能原文未變，以及強制結束測試程序後釋放連接埠。這不代表已在完全未安裝 Python 的乾淨 Windows 上驗收；EXE 的實際關閉按鈕仍待人工確認。
- 鎖定依賴安裝核對、pip check、候選檔／完整 Git 歷史機密掃描與文件連結檢查通過。這些檢查不能保證不存在漏洞。
- 原生控制工具連續初始化逾時，未進行中文輸入法、實體剪貼簿、儲存位置選擇器與視覺驗收。完整 Playwright 瀏覽器回歸遇到合成服務啟動逾時，即使指定 Python 與單一 worker 仍重現，未列為通過；獨立量測同一個 150 筆合成服務耗時 42.42 秒才就緒，超過既有 30 秒啟動上限；未確認是磁碟、掃描軟體或其他系統因素，也未調高測試門檻。桌面整合與成品檢查不能代替這項回歸。

可重跑的選用整合檢查：

```powershell
.runtime/desktop-build/venv/Scripts/python.exe -B tests/desktop_smoke.py
.runtime/desktop-build/venv/Scripts/python.exe -B tests/desktop_bundle_smoke.py '<打包資料夾>/Skillpane.exe'
```

兩者只建立合成測試資料；成品檢查會複製整個程式資料夾，結束時僅強制終止自己啟動的測試實例。測試產物保留在 `.runtime/`，不應加入 Git 或公開發行。正式發行前先完成上述未測項目，再決定安裝器、簽章及桌面發行 CI。

## 應用程式圖示

桌面視窗與 EXE 使用選定的青綠卡片／SP 多尺寸 ICO；瀏覽器分頁與側欄使用同一原稿輸出的 SVG 容器。主圖、尺寸及來源見 [圖示說明](../assets/brand/README.md)。重新打包會讀取固定圖示，不需 Pillow，也不重新呼叫影像生成服務。舊 EXE 不會自動更新，請從新打包資料夾啟動；Windows 可能快取舊圖示。

## 圖示套用與打包驗證（2026-11-03）

台灣時間（UTC+8），上述同一 Windows 與桌面環境，僅使用合成資料。本輪 48 項適用單元／安全／公開邊界案例中 47 通過、1 個 POSIX 專項略過；WebView2 整合擴為 18 項通過，新增原 CSP 下的品牌圖片載入。成品搬移與獨立儲存檢查擴為 8 項通過，另逐一核對 EXE 的十個圖示資源與選定 ICO 相符。這些是本機原型驗證，未取代前述人工及乾淨環境驗收。

本機完整 Playwright 批次為 32 通過、2 個不適用案例略過，遇到 WebKit 重新載入後清單未在 10 秒內出現，因停止於首筆失敗，另有 1 項中止及 9 項未執行。其後一次 WebKit 獨立重跑遇到合成服務 30 秒啟動逾時；改以明確的 CPython 執行檔，單 worker 的 WebKit 9 項與原批次未完成的 Firefox 2 項皆通過。未修改測試門檻或加自動重試；不能把分批補驗稱為單輪完整通過，也未確認逾時根因。遠端完整結果應核對同一提交的 GitHub CI。

107 個候選檔案與完整歷史機密掃描、22 份 Markdown 的相對連結檢查通過。向 OSV 僅送出 16 個桌面套件的公開名稱／版本，查詢未回報已知漏洞；沒有上傳程式碼、技能、筆記或路徑。這是當次已知公告查核，不是無漏洞證明或持續依賴監控。
