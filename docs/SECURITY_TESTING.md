# 安全測試紀錄

## 公開與 GitHub 安全設定（2026-10-31）

擁有者授權後，repository 於 2026-10-31 00:12:58（台灣時間，UTC+8）改為公開，當時 main 為 `ce12e1f0b520bb1dcd8307ec31e134e9c6961385`。公開前重查候選檔、完整歷史、Git 以外內容與最新 CI 日誌，結果見 [回報管道驗收](SECURITY_REPORTING.md)。

公開後立即以 API 設定並回讀：私下漏洞回報 `enabled: true`；secret scanning、push protection 與 Dependabot 安全更新為 enabled，Dependabot alerts 原已啟用；CodeQL default setup 為 configured，涵蓋 Actions、JavaScript／TypeScript 與 Python。首次 CodeQL 分析於 00:13:48 至 00:15:04 成功，開啟中的 code scanning 與 secret scanning 警示均為零；這只代表當次規則集的結果，不等於沒有漏洞。

`main` 分支保護：禁止 force push 與刪除，必要檢查為 GitHub Actions（app 15368）回報的 `validation`；不要求 PR 審查，也不對管理員強制，擁有者可直接推送，外部 PR 須通過 CI。一般回報者入口與維護者收件尚未驗收，正式版本待驗收後發布。

## 公開前審查修正：本機及遠端驗收

2026-10-30 晚間（台灣時間，UTC+8）以 `76d69e3` 為基準完成程式碼審查，之後 13 筆提交（`b8c5225` 至 `626ab6a`）逐項修正。這是維護期間的內部審查，不是獨立滲透測試。

- **可用性（已重現）**：SKILL.md 前置資料以 JSON 跳脫寫出孤立 Unicode 代理字元時，寫入整理資料會在 UTF-8 編碼失敗：重新掃描回 400、`/api/state` 中斷連線、重啟時服務無法建立。掃描範圍含外掛快取，第三方內容即可觸發；寫入前就失敗，資料未損壞。已在合成 home 重現，改為欄位無法判讀並退回資料夾名稱。
- **錯誤處理**：未預期例外改回通用 JSON 500，保留安全標頭；stderr 只記錄例外類型。
- **Git 來源查詢（深度防禦）**：修正前未發現可執行程式的路徑，但 git 會往上採用家目錄等較高層的 repository，也會把 bare 版面的技能資料夾當成 repository 並讀其 config。現以 `GIT_CEILING_DIRECTORIES` 及 `safe.bareRepository=explicit` 限制；範圍內 repository 的設定仍會讀取。
- **來源網址**：新儲存的值另檢查片段參數與常見 token 開頭；既有資料與匯入沿用原規則以免升級後無法讀取。這是防誤貼提示，不是機密掃描。
- **儲存與效能**：內容相同的寫入不改寫、不新增備份；替換失敗只清除自身暫存檔，換向的資料目錄不跟隨；替換前 fsync。狀態快照沿用未變更的對應結果；比較單次讀取並在鎖外計算差異；前端檔案啟動時載入；搜尋略過輸入法組字中的文字。
- **CI 與執行環境**：push 限 `main`、同一 PR 取消過時執行、`actions/setup-node` 升至 v7.1.0（已核對 tag SHA）；低於 Python 3.11 時啟動即結束。

每項新增回歸都先確認移除修正後失敗、套用後通過。23:38 前於 Windows 11（build 26200）、Python 3.14.6、Node 24.15.0 對 `626ab6a` 完成：完整單元測試 185 項（183 通過、2 平台略過），Playwright Chromium 三種尺寸與 Firefox 共 28 項通過、未重試。Gitleaks 8.30.1 以官方 checksum 驗證，並與 CI 釘選的 Linux 雜湊交叉核對；37 筆可到達提交與 HEAD 的 92 個檔案均無發現，公開邊界檢查 0 項。

刻意未變更：備份維持預設全部保留、不自動刪除，只新增總量提醒；以內容指紋綁定的內建中文別名及分類關鍵字為既有功能，不影響其他使用者的技能。私下漏洞回報、secret scanning、CodeQL 與分支保護須在公開後設定，本批未修改 GitHub 設定或可見度。

修正與本紀錄一併推送為 `783156ebc65d7f7bdab94bb93ccc30de7fe1ef19`。該提交的 [完整 CI](https://github.com/kejamestw/skillpane/actions/runs/41082646694) 於 2026-10-30 23:38:57 至 23:41:39（台灣時間，UTC+8）首次執行八項成功，分流判定為完整流程。四組 Python 各 185 項：Windows 3.11／3.13 各 184 通過、1 平台略過，Linux 兩組各 173 通過、12 平台略過；browser 的 Chromium／Firefox 共 28 項通過。secrets 的 Gitleaks checksum、全歷史掃描與 92 個路徑的公開邊界，以及最終 validation 皆成功。八份工作日誌另以 Gitleaks 在記憶體掃描、無發現（同次以合成 token 確認掃描器會回報），零 artifacts、repo 私人。Dependabot PR #1 在 main 含相同版本後已自動關閉。

## Skillpane 公開前唯讀核對（2026-10-30 晚間）

範圍僅 `kejamestw/skillpane`，當時 main 為 `767b59ad58bca3fbefb88a672967894f0bfb6c26`；沒有修改 repository 設定、內容可見度或其他專案。候選 92 個檔案及本機可到達歷史的公開邊界、機密與 workflow lint 檢查通過。

另建立全新本機 mirror，涵蓋 GitHub 當時提供的 main、Dependabot 分支及 PR #1 的 head／merge refs，共 25 筆可到達提交；完整歷史機密掃描通過，三個提交信箱均為 GitHub noreply。這比既有 checkout 的 23 筆歷史多包含未合併 PR，不宣稱涵蓋 GitHub 未提供的已刪除或不可到達資料。

21:54:00（台灣時間，UTC+8）完成 Git 之外文字檢查：一筆 Issue／PR 項目，對話留言、PR review 本文、review comments 與 commit comments 均為零；文字只在記憶體掃描，無機密命中，未發現附件連結。當時 Releases／release assets 與 Actions artifacts 均為零；新附件或新提交出現後須再驗收，不沿用此快照。

已回讀 repo 維持私人、Actions 僅允許 GitHub 官方 Actions、要求完整 SHA、預設工作流程唯讀且不能核准 PR；Dependabot alerts 已啟用。這不等於沒有相依套件漏洞。`767b59a` 的 [完整 CI](https://github.com/kejamestw/skillpane/actions/runs/41029582717) 八項成功，四組 Python 各 171 項及 browser 24 項，原八份日誌機密掃描通過、零 artifacts。

LICENSE 保留 MIT 全文及上游版權聲明，來源說明與上游完整授權檔均存在；GitHub API 當時的自動辨識仍為 `NOASSERTION`，須在公開前確認顯示與 README 說明一致，不能由自動辨識結果推定缺少授權。操作驗收及鍵盤效率待改善見 [驗收清單](MANUAL_ACCEPTANCE.md)。私下回報依既定決定在公開後立即啟用並驗收，目前不宣稱可用。公開前仍須針對當時的最終版本及 Git 之外新增內容重查，repository 不會因這份核對而自動公開。

## 本機瀏覽器啟動診斷與隔離快取

2026-10-30（台灣時間，UTC+8），對 Playwright 1.64.1 管理的 Firefox 157.0／build 1555 進行獨立啟動診斷；不載入 Skillpane 時，Node 回傳 `spawn UNKNOWN`，Python 建立程序回傳 Windows 14001。Windows SideBySide 事件 33 指向 `mozglue` 相依組件解析失敗，故不能把這六項啟動失敗歸因於面板程式或電腦效能。這是測試用瀏覽器，不是使用者一般 Firefox 的故障判定。

從 Playwright 官方管道重新下載相同版本至獨立路徑可成功啟動；逐檔內容雜湊核對沒有缺檔或內容差異。保留原快取備份後，將相同內容重建於原共用路徑仍失敗。因此僅確認與路徑相關的啟動現象，沒有確認 Windows 解析失敗的最終原因，不宣稱修好原共用快取；沒有修改系統 DLL、安全軟體、ACL 或全域環境。官方下載最初遇到 Node 憑證鏈錯誤，使用此次子程序的系統信任庫後成功，沒有關閉 TLS 驗證。

新增可選的專案快取入口，見 [測試指南](TESTING.md)。Windows x64／OS build 26200、Node 24.15.0、本機 Python 3.12.14 下，專案快取 Chromium 156.0.8078.4 與 Firefox 157.0 都能啟動。於 16:37:21 完成四種設定共 24 項合成瀏覽器回歸，零失敗、未重試；日誌在記憶體機密掃描通過。基準為 `7f4cdde` 加上尚未提交的開發入口，原有程式與 CI 流程未修改。

另以獨立合成服務完成有介面 Chromium 的字級、側欄、搜尋快捷鍵、彈窗焦點及長內容操作；細節見 [操作驗收](MANUAL_ACCEPTANCE.md)。沒有操作真實面板或筆記。原生 Windows 視窗控制的核准逾時，未完成預設瀏覽器及原生 200% 縮放；實體觸控、觸控板與 Safari／WebKit 保留未測。這些限制不以視窗模擬或本機 24 項通過取代。

## Windows 儲存替換：本機與遠端已驗收

修正已提交為 `7f4cdde2118892f856a3e2333338e571a80a9178`。[該提交完整 CI](https://github.com/kejamestw/skillpane/actions/runs/41022808942) 於 2026-10-30 15:53:02 至 15:55:38（台灣時間，UTC+8）首次執行八項成功；四組 Python 各 171 項，Windows 各 170 通過／1 平台略過、Linux 各 159 通過／12 平台略過，browser 24 項通過。八份工作日誌在記憶體機密掃描通過，repo 私人、零 artifacts。以下保留提交前的本機觀測；舊提示詞 HTTP 400 是否同因仍未證實。


2026-10-30 14:43:56（台灣時間，UTC+8）完成受限例外分類觀測：538d14a 的完整 160 項再次在掃描紀錄保留案例失敗，之後八輪兩案例中該案例另失敗三次；提示詞案例八輪均通過。四次失敗都在 `ScanHistory.commit` 的 `Path.replace`，例外為 PermissionError、errno 13、winerror 5。這定位了檔案替換拒絕，未識別造成拒絕的程序；不能據此判定防毒、索引或電腦效能，也未證明先前提示詞 HTTP 400 是同一原因。

候選修改共用替換函式：僅 Windows 5／32／33 可再試，最多五次、主動等待總量 375 ms，每次重新檢查原檔與資料目錄及暫存檔指紋。備份不因重試重做，成功後才提交記憶體；持續拒絕與安全檢查失敗仍回報錯誤。Windows 檔案替換可能受分享權限限制，見 [Microsoft 檔案移動與替換說明](https://learn.microsoft.com/en-us/windows/win32/fileio/moving-and-replacing-files)；此說明不是本機持有者的證據。

2026-10-30 14:53:42（台灣時間，UTC+8）完成修正後本機驗證：完整 171 項於 184.454 秒完成，170 通過、1 平台略過；隨後八輪原兩案例共 16 項於 113.937 秒全部通過。觀測仍捕捉三次掃描紀錄替換的 Windows 5，但均在有限重試後成功，沒有向 commit 傳出失敗。新增十一項回歸另已通過，涵蓋永久拒絕、非 Windows／其他錯誤、外部改寫、暫存變更及實際 junction／symlink 換向；沒有放寬既有斷言或自動重跑失敗測試。兩階段原始日誌均僅在記憶體掃描，未儲存。

瀏覽器於 2026-10-30 14:54:28（台灣時間，UTC+8）完成：Chromium 三種尺寸 18 項通過；Firefox 六項均在 `browserType.launch: spawn UNKNOWN` 失敗，不能列為已驗證操作。隨後不啟動 Skillpane、只呼叫 headless Firefox 的隔離檢查也回傳同一建立程序錯誤，支持錯誤發生於瀏覽器啟動前；實際系統原因未確認，不放寬斷言或以換瀏覽器隱藏。日誌在記憶體機密掃描通過，既有 Playwright 合成錯誤背景留在 Git 忽略目錄，未上傳。

91 個候選檔、完整可到達歷史機密掃描、Git 資料邊界及差異檢查通過；19 份 Markdown 相對連結零錯誤。上述為提交前狀態；其後已依本節開頭核對 7f4cdde 的遠端四組矩陣。538d14a 的既有八項遠端成功只涵蓋下節舊版本；本機有限重試成功不代表 Windows 永不拒絕或提示詞舊失敗已證實同因。

## 必要模組負向測試修復：遠端已驗收，本機寫入失敗待追查

`538d14a9d27b1593f2ae80101e8a7cd51e6d5ce1` 的 [完整 CI](https://github.com/kejamestw/skillpane/actions/runs/41014722654) 於 2026-10-30 14:35:32（台灣時間，UTC+8）完成，八項全部成功；四組 Python 各 160 項、browser 24 項與機密掃描已核對。Windows 各 159 通過／1 平台略過，Linux 各 148 通過／12 平台略過。兩組 Windows 各 48 次啟停及六次 Probe 完成；原始失敗與手動驗收來源見 [CI 紀錄](CI.md)。這個遠端結果不抵銷下列本機失敗，也不代表零漏洞。

本批僅調整測試及文件，保留 `47f7c70` 的正式模組載入與所有安全驗證。負向測試改用 Function provider 直接檢查未定義函式，避免缺失命令搜尋；每次仍限 60 秒。新增固定階段標記，逾時只讀 stderr 尾端 16 KiB 的允許階段，未知文字不回印；程序建立錯誤亦使用固定摘要且隱藏原始例外鏈。新增一項跨平台測試覆蓋上述診斷邊界，完整預期 160 項，實際本機及遠端結果另記錄。

模組失敗四組子案例及跨平台摘要測試已在本機成功。兩次完整本機均執行 160 項，耗時 242.698／192.986 秒；啟停相關案例完成，但整套分別在既有提示詞新增回傳 400、掃描紀錄保留 300 筆案例失敗，不能稱整套通過。日誌在記憶體掃描通過。另以受限例外分類觀測執行七項提示詞測試，以及對兩個曾失敗案例觀察原子替換，均未重現、未捕捉寫入例外。首次與第二次失敗保留，原因未確認；沒有修改正式寫入邏輯或放寬斷言，後續新 SHA 仍須驗收完整 CI。

## 明確載入必要內建模組：本機驗證，遠端待驗收

共用啟停腳本在定義函式前，從目前 `$PSHOME/Modules/` 的固定 manifest 載入 Microsoft.PowerShell.Utility 及 CimCmdlets，保留原本 JSON 解析、CIM provider 與 HTTP 命令。沒有改成自製解析或略過身分驗證，不修改 PSModulePath、全域執行原則或自動載入偏好；不使用 Force，不下載套件，也不回退到其他模組來源。任一載入失敗即停止，包含原先無程序紀錄的 Stop 情境也必須先完成初始化。

新增一項 Windows 回歸，在 PowerShell 5.1／7 分別模擬兩個模組載入失敗，核對固定 manifest 與 Stop 錯誤處理契約、啟停函式尚未定義及沒有產生應用程式資料。原有 provider 查詢錯誤、偽裝健康回應、紀錄竄改、跨 checkout、鎖衝突與程序身分測試仍完整執行。

於 2026-10-30 14:01:02（台灣時間，UTC+8）完成 Windows／Python 3.12.14 全套 159 項：158 通過、1 項 POSIX 平台略過，耗時 238.703 秒。48 次合成啟停及六次 Probe 無 timeout／spawn-error／cleanup-error，完整日誌在記憶體機密掃描通過。另完成兩種 shell 共 14 筆手動診斷、未啟動服務、日誌掃描通過；本機目前入口案例的共用腳本載入步驟約 236／67 ms，包含新 import。這不是雲端速度保證，新 SHA 的完整 CI 與兩組手動診斷仍待驗收，不沿用 `652ae38` 的成功。

提交 `47f7c701e03f2addd712d3110a610a95580a7cdd` 的 [首次完整 CI](https://github.com/kejamestw/skillpane/actions/runs/41012067273) 於 2026-10-30 14:05:41 至 14:10:19（台灣時間，UTC+8）失敗，原因是新增必要模組失敗測試中，Windows Python 3.11 的兩個 Windows PowerShell 子案例各超過 60 秒；validation 正確失敗。其他三組 Python 各執行 159 項並成功、browser 24 項成功。兩組 Windows 的原有 48 次啟停及六次 Probe 均完成、無超時；3.11 正式 Start 中位數約 1.56 秒、record-read 約 41 ms，不能將這些局部成功當成整體 CI 通過。

同 SHA 的 [手動診斷](https://github.com/kejamestw/skillpane/actions/runs/41012087671) 於 2026-10-30 14:05:54 至 14:06:51（台灣時間，UTC+8）兩組、14 筆成功，沒有啟動應用程式。十份實際工作日誌在記憶體機密掃描通過，repo 私人、兩個 run 零 artifacts。首次失敗保留，不重跑原提交；測試查詢與診斷修復另列上方，實際超時行因舊版缺少標記尚未確認。

## 入口首次命令模組限定：本機及遠端驗收

Start／Stop 僅將首次 `Join-Path` 呼叫限定為 `Microsoft.PowerShell.Management\Join-Path`，保留 provider 路徑行為與原有身分驗證。共用啟停腳本、HTTP、資料格式與安全負向案例未放寬；不修改 ExecutionPolicy 或 PSModulePath。診斷工具的入口截斷契約同步更新，保留舊 `header-join` 基準，讓 `entry-body-parse` 使用目前正式入口的首次限定方式。

於 2026-10-30 13:14:45（台灣時間，UTC+8）完成 Windows／Python 3.12.14 全套 158 項：157 通過、1 項 POSIX 平台略過，耗時 188.811 秒。48 次合成啟停與六次 Probe 均完成，無 timeout／spawn-error／cleanup-error；全套日誌在記憶體機密掃描通過。另完成兩種 PowerShell 共 14 筆實際診斷，未啟動服務，日誌掃描通過。入口截斷、CRLF 與固定輸出契約仍受八項診斷回歸檢查。

提交 `652ae380291b6b0551a9a386a0ec1afaf13e71c3` 的 [完整 CI](https://github.com/kejamestw/skillpane/actions/runs/41008788228) 於 2026-10-30 13:30:15 至 13:48:33（台灣時間，UTC+8）首次執行八項成功。四組 Python 各 158 項，Windows 各 157 通過／1 略過、Linux 各 147 通過／11 略過；browser 24 項通過，兩組 Windows 各 48 次啟停及六次 Probe 無 timeout／spawn-error／cleanup-error。八份日誌在記憶體掃描通過，repo 私人、零 artifacts。

同 SHA 的 [手動診斷](https://github.com/kejamestw/skillpane/actions/runs/41008807663) 於 2026-10-30 13:30:26 至 13:31:27（台灣時間，UTC+8）兩組、共 14 筆成功；兩份日誌另掃描通過、零 artifacts。Windows PowerShell 5.1 的舊未限定基準約 33.2 秒，目前入口方式約 0.33 秒。但正式 Start 中位數在 Python 3.11 約 25.1→20.0 秒、3.13 約 25.1→25.3 秒，尚未一致加速；3.11 的 record-read 中位數約 18.7 秒，等待已移到紀錄讀取。上方必要模組修正仍須另以新 SHA 驗收，不能將本批成功視為完整慢速已修復或零漏洞保證。

## 手動啟動因素診斷：本機及遠端驗收

本批新增開發用 `tests/startup_probe.py` 與僅 workflow_dispatch 執行的 Windows 診斷。每個 shell 七組固定案例，涵蓋 session 執行原則、Join-Path／.NET／模組限定命令、明確載入模組及只解析剩餘入口文字。正式啟停、安全邊界、HTTP 與資料格式未修改，不把這些子程序加入既有完整回歸。

本機兩種 PowerShell 共 14 筆實際案例完成，日誌在記憶體掃描通過。逐步輸出只接受固定階段與有限長度 ASCII 毫秒數，缺少、重複、倒退或過長時間值明確失敗。環境變數為必要 OS 允許清單及合成 home，不繼承憑證、PSModulePath 或程序執行原則；入口在任何服務操作前 return，原始來源指紋保持不變，副本沒有建立應用程式的 `.runtime/` 或 `.data/`。工作產物留在已忽略目錄，不上傳 artifacts。

於 2026-10-30 12:19:46（台灣時間，UTC+8）完成 Windows／Python 3.12.14 全套 158 項：157 通過、1 項 POSIX 平台略過，耗時 301.377 秒。原有 48 次啟停與六次 Probe 均完成，沒有 timeout／spawn-error／cleanup-error；全套日誌在記憶體掃描通過。新增八項回歸涵蓋階段輸入拒絕、有限讀取、合成環境、入口截斷及 CRLF 相容；既有安全負向案例維持執行。

先行本機對照沒有重現雲端二十多秒等待，Bypass 開關也沒有穩定慢速差異。首次 Join-Path 約 0.55 秒、純 .NET 組路徑僅數毫秒；明確 Import-Module 後路徑操作變快，當時僅支持模組／provider 首次初始化值得在雲端對照。

提交 `0aa65d1dc6b5ef53f2bdeabb4603681a7fa7d5e5` 的 [完整 CI](https://github.com/kejamestw/skillpane/actions/runs/41003073015) 於 2026-10-30 12:28:20 至 12:48:26（台灣時間，UTC+8）首次執行八項成功。四組 Python 各 158 項，Windows 各 157 通過／1 略過、Linux 各 147 通過／11 略過；browser 24 項通過。兩組 Windows 各 48 次啟停及六次 Probe 無 timeout／spawn-error／cleanup-error；八份日誌在記憶體掃描通過，repo 私人、零 artifacts。

同提交的 [手動診斷](https://github.com/kejamestw/skillpane/actions/runs/41003075815) 於 2026-10-30 12:28:22 至 12:29:16（台灣時間，UTC+8）兩組、共 14 筆成功；日誌在記憶體機密掃描通過，零 artifacts。Windows PowerShell 5.1 未限定 Join-Path 的首次路徑步驟約 19.8 秒，模組限定整筆約 0.2 秒；舊入口解析案例首次路徑步驟約 12 秒。PowerShell 7 約 0.4～0.6 秒。這是各一次、固定順序的對照，未確認底層搜尋為何變慢，亦未重現先前 60 秒超時；正式入口修正另列上方待驗收批次。

## 父程序時間觀測：本機及遠端驗收

於 2026-10-30 00:05:41（台灣時間，UTC+8）完成 Windows／Python 3.12.14 全套 150 項測試：149 通過、1 項 POSIX 平台略過，耗時 162.649 秒。48 次合成啟停與六次最小 Probe 均完成，沒有 timeout、spawn-error 或 cleanup-error；測試日誌在記憶體經 Gitleaks 掃描通過，沒有保存原始日誌。

本批只調整測試觀測及文件，正式 PowerShell 啟停邏輯、安全邊界與服務資料格式不變。新增六項診斷回歸，包含實際合成 Python 子程序、模擬慢速建立耗盡原有預算、逾時自有程序清理、建立／清理錯誤不回印原始例外及觀測欄位型別拒絕；原有 Windows 負向案例完整執行。Probe 只載入隔離的共用腳本，兩種 PowerShell 各驗證診斷未設定、關閉及開啟三種模式，不啟動應用程式或存取真實技能。

每 100 ms 觀察 stderr 尾端及自有程序，未知值為 -1，標記觀測時間是上界並有排程／I/O 延遲；子程序階段鐘與父程序起點不同，不能直接相減當作精準啟動時間。60 秒預算自 Popen 前開始；OS 建立呼叫本身無法由此監督方式中斷，返回後若超過預算仍判逾時，清理最多另等 10 秒。這不是硬性牆鐘上限，也沒有重試或依紀錄 PID 終止其他程序。

後續提交 `9bbe35dbb7572f3f709fe6a01d565231f84cd5ca` 的 [完整 CI](https://github.com/kejamestw/skillpane/actions/runs/40997806303) 於 2026-10-30 11:30:53 至 11:50:48（台灣時間，UTC+8）首次執行八項成功。四組 Python 各 150 項，Windows 各 149 通過／1 略過，Linux 各 139 通過／11 略過；browser 24 項通過。兩組 Windows 各 48 次啟停及六次 Probe 沒有 timeout／spawn-error／cleanup-error；八份日誌在記憶體機密掃描通過，repo 私人、零 artifacts。

Windows PowerShell 5.1 成功 Start 首標記觀測中位數約 21.4／24.1 秒，建立返回僅 0／2 ms，而最小 Probe 約 0.3 秒。本輪把範圍縮到正式入口首次標記之前；取樣有延遲，沒有確認一般 PowerShell 啟動、防毒或特定元件的根因，也未重現先前 60 秒超時。

## Windows 啟動診斷與監聽查詢：本機及遠端驗收

本批於 2026-10-29 23:16（台灣時間，UTC+8）完成 Windows／Python 3.12.14 全套 144 項測試：143 通過、1 項 POSIX 平台略過，約 163 秒；48 次合成啟停的診斷摘要沒有超時，測試日誌另在記憶體經 Gitleaks 掃描通過。真實占用／偽裝健康回應、紀錄竄改、其他 checkout、排他鎖、啟停重啟及 PowerShell 5.1／7 案例仍全部執行。

新增七項跨平台診斷測試，涵蓋 stderr 限量讀取、未知／原始文字與倒退時間拒絕、未結束的巢狀階段、超時保持失敗且不回印原始命令／輸出；另在兩種 PowerShell 驗證診斷未設定／關閉時安靜、開啟時只接受固定標籤。監聽查詢契約驗證成功空結果、提供者錯誤繼續向外傳遞，以及非法 port 在查詢前拒絕。

監聽查詢使用相同 Windows TCP 提供者，改在查詢端限制目標 port 與 Listen 狀態；保留 loopback、程序建立時間、完整命令列及 socket 擁有者核對。本機自有 socket 小樣本比較：Windows PowerShell 的原查詢 1405／1514 ms、目標查詢 901／902 ms；PowerShell 7 為 954／978 ms 與 601／665 ms。兩種方式都核對相同合成程序身分，關閉 socket 後目標查詢成功回傳空集合。這不是雲端量測，也未證明能消除先前 60 秒超時。

提交 `95b7f6df531ad14438084d2fa331f1e787343339` 的 [完整 CI](https://github.com/kejamestw/skillpane/actions/runs/40901150133) 於 2026-10-29 23:23:59 至 23:44:18（台灣時間，UTC+8）首次執行八項成功：四組 Python 各 144 項，Windows 各 143 通過／1 略過，Linux 各 133 通過／11 略過；browser 24 項通過。兩組 Windows 各 48 次啟停沒有超時。八份日誌在記憶體掃描通過，repo 維持私人、零 artifacts；詳細時間觀察見 [CI 紀錄](CI.md#後續啟動器診斷)。

診斷只輸出固定階段、結果及毫秒數，不印出 PID、路徑、環境變數、完整命令或原始服務日誌；後者仍留在忽略的合成 fixture，不上傳 artifacts。當時的 60 秒測試指令限制、25 分鐘 Windows job 與不自動重試規則維持不變；首次超時根因仍未確認。

## 0.4.0 掃描變更紀錄：遠端驗收

`393fb5c661b764714d79551d0984bbd9b418c9e2` 的 [CI](https://github.com/kejamestw/skillpane/actions/runs/40879179409) 於 2026-10-29 21:08:12 至 21:26:32（台灣時間，UTC+8）完成，六項全部通過。Windows Python 3.11／3.13 各 123 項（122 通過、1 項 POSIX 平台略過），Linux 兩組各 123 項（114 通過、9 項平台略過）；Chromium 三種尺寸與 Firefox 桌面共 24 項通過，含變更紀錄及名稱注入純文字驗證。持鎖測試修正已在兩組 Windows 驗收。

核對確切 SHA、必要步驟、Gitleaks 下載 checksum 與完整歷史機密掃描；六份日誌另在記憶體掃描通過，未保存原始日誌。回讀 repository 維持私人、該 run 沒有 artifacts。本機 Firefox 的 Windows SideBySide／mozglue 啟動問題仍未修復；遠端 Linux Firefox 通過不代表本機環境已修復。

## 0.4 開發流程與文件分流：完整 CI 驗收

`2bbdbf64026badedd0e6ad3f271d76da69960fdf` 的 [完整 CI](https://github.com/kejamestw/skillpane/actions/runs/40889112628) 於 2026-10-29 22:34:00 至 2026-10-29 22:52:54（台灣時間，UTC+8）完成，八項工作全部成功。Windows Python 3.11／3.13 各 135 項（134 通過、1 項 POSIX 平台略過），Linux 兩組各 135 項（126 通過、9 項平台略過）；Chromium 三種尺寸與 Firefox 桌面共 24 項通過。

分流工作另執行十項分類測試、兩項文件連結測試與相對連結檢查，實際選擇 `full=true`。確認 secrets 的完整歷史掃描、Gitleaks checksum 與最終 validation 成功；八份工作日誌另在記憶體掃描通過，未保存原始日誌。回讀 repository 維持私人、該 run 沒有 artifacts，未變更 GitHub 設定。

這是相同提交的第二次完整執行。首次執行的 Windows Python 3.13 在持鎖案例最初的 `self.start()` 超過 60 秒，當時尚未建立持鎖程序；其他三組 Python、browser 與 secrets 成功，最終 validation 正確判失敗。[首次執行紀錄](https://github.com/kejamestw/skillpane/actions/runs/40889112628/attempts/1) 保留。本機單獨重驗該案例於 13.014 秒通過；維持原 60 秒限制及所有案例，沒有修改程式後重跑。首次啟動超時的根因尚未確認；第二次成功不代表間歇性問題已修復。

本批本機全套亦為 135 項（134 通過、1 項平台略過）；候選 84 個檔案與含新提交的完整可到達歷史分別掃描通過。Bandit 1.9.4 為 0 高、0 中、8 低；新增兩個開發腳本各有 subprocess import／參數陣列呼叫提示，已確認可信 PATH、固定子命令、完整 SHA 驗證、30 秒限制及未開 shell，沒有用 nosec 或排除規則隱藏。下方較早的 4 低紀錄保留當時範圍。純文件分流尚需下一筆真正的文件提交另驗收，不把預期 skipped 當成執行測試通過，也不將本次內部驗證稱為獨立滲透測試。

## 0.3.3 Windows 啟動器

### 遠端 CI 追蹤

`9943bddd66c97b93b95e60c29fb10b155aa9e914` 已推送。[首次 CI](https://github.com/kejamestw/skillpane/actions/runs/40849972444) 於 2026-10-29 17:29:01 至 17:39:19（台灣時間，UTC+8）執行，Linux 兩組、browser 與 secrets 成功；Windows 兩組在 10 分鐘總上限取消。兩組日誌均顯示前四項啟動器案例通過，第五項身分竄改案例執行中被取消，沒有完整測試結論；不推定其餘案例已通過，也不能排除尚未跑完部分的問題。沒有上傳 artifacts。

Windows 工作總上限調整至 25 分鐘，每次啟停指令仍限 60 秒，沒有減少或略過測試。修正已於 `c700b458c1e37792fcade3b4ebebf67ec8974f8f` 提交推送，[該提交 CI](https://github.com/kejamestw/skillpane/actions/runs/40852014885) 於 2026-10-29 17:44:37 至 18:03:13（台灣時間，UTC+8）執行，六項工作全部通過。

已核對四組 Python 的完整測試結論：Windows 兩組各 108 項、107 通過及 1 項 POSIX 略過；Linux 兩組各 108 項、99 通過及 9 項 Windows 略過。Windows Python 3.11／3.13 的單元測試分別耗時約 17 分 17 秒／18 分 8 秒。Chromium 三種視窗及 Firefox 桌面共 20 項通過，secrets 工作成功；六份工作日誌均在記憶體另經 Gitleaks 檢查，沒有上傳 artifacts。下列本機紀錄及其他未驗收範圍仍適用。

### 本機紀錄

執行日期：2026-10-29（台灣時間，UTC+8）。Windows／Python 3.12.14 完整回歸 108 項：107 通過、1 項 POSIX 案例略過；其中新增八項真正啟動器案例全部通過，涵蓋 Windows PowerShell 5.1 與 PowerShell 7.6.5。所有案例使用含空白／中文路徑的獨立程式副本、合成 home 及非 8766 的隔離連接埠，並核對技能原檔指紋不變。

修正範圍是本機程序辨識、拒絕接管與啟停可靠性：新增絕對專案入口、建立時間與 Python／完整命令列核對、socket 擁有者檢查及排他鎖。停止前保留程序 handle，不把紀錄中的裸 PID 直接交給停止指令。未知服務即使回傳 Skillpane 健康回應也不會被沿用；錯誤 port、root、時間、Python、PID 型別及其他 checkout 的程序均拒絕處理，原服務持續可用。

跨版本測試發現 PowerShell 7 寫入的無 BOM UTF-8 中文路徑會被 5.1 預設編碼誤讀，現已明確指定 UTF-8；也處理兩版本 JSON 整數及日期型別差異。活的舊格式紀錄無法證明絕對 checkout 入口，保守拒絕；升級前需先用舊版啟動器停止服務。

PowerShell 語法及 Bandit 中高風險檢查通過；公開邊界及機密結果另在提交／推送前重掃。本批沒有變更 HTTP、整理資料格式、預設 8766 或瀏覽器介面；本機未重跑沒有變動的瀏覽器套件，遠端 20 項結果另見上節。雙擊 `.cmd`、預設瀏覽器開啟及其他實體 Windows 裝置尚未驗證。這仍是內部驗證，不是獨立審查或無漏洞保證。

## 0.3.2 掃描邊界

執行日期：2026-10-29（台灣時間，UTC+8）。以獨立合成資料重現巢狀 checkout 與其他工具鏡像被算成技能：修正前應為 2 項的案例計為 8 項；修正後為 2 項，沒有假的重疊群組。這是清單正確性問題；未由此確認遠端可利用的越界讀寫。

新增六項掃描回歸，覆蓋集合／系統／外掛版本、排除目錄與範圍外連結的進入前檢查、別名與循環、無效外層技能及舊整理資料保留。Windows／Python 3.12.14 完整測試共 100 項：99 通過、1 項 POSIX 案例略過。技能原檔維持唯讀，舊副本的整理資料不自動刪除。

本批遠端 CI 尚未執行；不得沿用下述 3b3c043 的成功結果作為 0.3.2 證據。

Playwright 的 Chromium 桌面／小視窗／行動模擬與 Firefox 桌面共 20 個案例全部通過；核心腳本桌面 43、行動 42 項檢查，包含巢狀鏡像未進入清單及掃描範圍說明。Bandit 中高風險檢查沒有命中；候選程式文件與完整可到達 Git 歷史分別通過 Gitleaks，公開邊界、actionlint 及差異空白檢查通過。以上仍為內部驗證，不代表獨立滲透測試或無漏洞保證。

### 文件展示驗收

2026-10-29（台灣時間，UTC+8）補充三張合成截圖與操作導覽。展示腳本另建 runtime home／state，以 OS 配發 port 啟動正式前端；固定七個虛構項目與示範掃描時間。禁止 `Path.home()` 的檢查仍能成功建立展示，確認沒有回退至真實 home。截圖流程核對合成標記、項目數、原文前後相同、沒有頁面外部請求或未捕捉 JavaScript 錯誤；三張 PNG 經逐張人工檢視，尺寸符合設定，沒有 PNG 文字或 EXIF 中繼資料，42 個本機文件連結有效。腳本語法及 Bandit 中高風險檢查通過。

此批未改動應用程式執行碼或正式面板資料，不重複宣稱完整回歸已重新執行。展示是手動文件產生流程，未加入 CI，不上傳 CI artifacts；PNG 不依賴文字型機密掃描證明隱私，素材來源隔離與人工檢視仍必要。

## Unreleased：瀏覽器自動化與安裝升級

執行日期：2026-10-29（台灣時間，UTC+8）。本機 Windows／Python 3.12.14 完整回歸 94 項：93 通過、1 項 POSIX 案例略過。新增四項真正 CLI 子程序案例，分別覆蓋全新程式包啟停重啟、未版本化資料升級與還原、不含提示詞的第 2 版資料升級與可攜備份還原、損壞及未來格式拒絕寫入。全部使用合成 home，並核對技能原檔指紋。

Playwright 1.64.1 在 Chromium 桌面／小視窗／行動模擬與 Firefox 桌面共 20 個案例全部通過。每組包含核心（桌面 41、行動 40 項檢查）、管理（33）、文字注入（17）、提示詞（20），另有真實輸入、點擊、滾輪與偏好重載案例。測試服務逐案建立，不讀寫正式面板；瀏覽器外部請求被阻擋，未捕捉的 JavaScript 錯誤會使測試失敗。

完整測試曾顯示既有超限請求案例在 Windows 提前關閉連線時可能產生 TCP reset。測試改為只送不合法標頭，仍要求實際 HTTP 400；另直接確認 Handler 在超限或 Transfer-Encoding 請求中不呼叫 body read，並核對整理資料不變及健康檢查成功。沒有捕捉並忽略 ConnectionResetError，也沒有修改伺服器拒絕條件。

鎖定 npm 開發依賴並禁止安裝 scripts；本次 npm audit 回傳 0 個已知漏洞。這只代表查詢當下的資料庫結果。GitHub workflow 新增獨立 browser job；推送前尚未執行新遠端流程，Windows／Linux × Python 3.11／3.13 與 Linux 瀏覽器結果須核對後續確切 SHA，不以本機通過代替。

後續遠端核對：提交 `3b3c04382fd0085f879143ebb60270605b025afd` 的 [GitHub Actions](https://github.com/kejamestw/skillpane/actions/runs/40837881601) 已成功，四個 Python jobs 各 94 項（93 通過、1 項平台案例略過）、browser job 20 項通過及 secrets job 通過。此為先前批次的確切提交結果，不包含後續 0.3.2 修改。

完整操作、CI 範圍、供應鏈與未涵蓋的 launcher／實機／WebKit 限制見 [自動化測試](TESTING.md)。本次不變更應用程式版本、資料格式、安全邊界或 repository 可見度。

## 0.3.1 本機加強驗證

執行日期：2026-10-29（台灣時間，UTC+8）。由確切 0.3.0 審查包重現：20 筆合法長提示詞超過舊 24 KB 整理請求上限，造成儲存失敗。0.3.1 將該 PATCH 端點上限改為 2 MiB，容納前後兩組提示詞及 JSON 跳脫；保留 20 筆、80／4,000 字、整份資料 4 MiB 與其他端點限制。

新增七項合成回歸：12 個同時編輯者僅一筆成功、並行筆記與提示詞不互相覆蓋、最大 Unicode 與舊版本陣列往返、超過請求上限時不讀取 body、備份失敗及原子替換失敗後資料不變且可重試、整份資料超限不寫入或新增備份。測試只使用獨立合成服務，沒有攻擊正式面板。

Windows／Python 3.12.14 與原生 Linux／Python 3.14.4 的完整測試各 90 項：89 通過、1 項平台案例略過。Bandit 對程式與公開檢查腳本沒有中高風險命中。

此問題屬於容量與可用性限制不一致，未發現因此造成越界讀寫或資料外洩。仍是內部安全驗證，沒有獨立第三方認證；0.3.0 的遠端 CI 不代表後續未推送修正已在遠端驗證。

## 0.3.0 增量驗證

本機執行日期：2026-10-28（台灣時間，UTC+8）。Windows 與原生 Linux 各 83 項測試，皆通過並各略過 1 項不適用的平台案例。新增提示詞格式、持久化、舊資料相容、備份往返、跨來源拒絕及多視窗衝突測試；衝突或錯誤輸入不改寫原整理資料。

瀏覽器提示詞回歸 20 項、文字注入回歸 17 項通過；390×844 行動版核心回歸 40 項、1024×480 桌面核心回歸 41 項通過。三種字級搭配側邊欄開／關沒有水平溢出，重新載入可保留偏好。介面測試只操作獨立合成服務。

程式與 workflow 語法檢查通過；Bandit 沒有中高風險命中。候選檔案及可到達 Git 歷史另於提交／推送前掃描。遠端 CI 必須核對實際提交 SHA 的 run，不能由上述本機結果推定。這些結果仍是內部驗證，沒有獨立第三方滲透測試。

## 0.2.2 歷史紀錄

適用版本：0.2.2。執行日期：2026-10-28（台灣時間，UTC+8）。這是內部程式審查與攻擊情境回歸，不是獨立第三方滲透測試，也不是零漏洞證明。

## 範圍與資料

涵蓋本機 HTTP 邊界、JSON／匯入驗證、預覽生命週期、備份完整性、來源路徑及 Git 查詢、瀏覽器 HTML 顯示。測試使用合成 home 與獨立整理資料；永久清理以 mock `Path.unlink` 驗證，未執行真實備份刪除。所有暫存產物留在 Git 忽略目錄或獨立測試工作區，不上傳。

未進行公開網路掃描、長時間壓力測試、OS／瀏覽器漏洞利用或第三方服務測試。惡意本機程式可以同時修改檔案時，路徑與指紋檢查不能取代 OS 隔離、檔案鎖或消除所有檢查與使用之間的競態。

## 本次修正

風險等級為專案內部排序，未做 CVSS 評分；均須結合本機安裝內容或檔案變更，沒有確認可由未授權遠端網路直接利用的漏洞。

| 問題 | 前提與影響 | 內部排序 | 0.2.2 處理 |
| --- | --- | --- | --- |
| 備份清理未檢查外部改寫的整理資料 | 預覽後另一個程序改寫資料；舊預覽仍可能清理原本可用於復原的備份 | 中：本機資料完整性 | 清理預覽及所有預覽套用重新檢查磁碟指紋；變更時拒絕，且不呼叫 unlink |
| 被排除目錄經連結別名重新出現在清單 | Windows junction 指向掃描根內的 `.trash` 等排除位置；違反掃描範圍預期 | 低：範圍與隱私 | 對 canonical path 再套用排除規則；原有根目錄邊界仍保留 |
| 單一過長識別導致啟動失敗 | 安裝名稱／外掛識別超過支援長度的技能；整理資料驗證失敗，中斷整個服務 | 中：本機可用性 | 在掃描時略過錯誤紀錄並累計 skipped，不截斷或修改原始檔 |
| Git 來源查詢未重新驗證路徑 | 掃描後有程序替換來源資料夾的連結目標；可能在範圍外查詢 Git 中繼資料 | 低：路徑邊界 | 使用共用來源路徑驗證，快取命中前也檢查；失效時不啟動 Git |

另外將公開檔案檢查腳本的 Git 執行檔先以 `shutil.which` 解析，再以參數陣列啟動；找不到時明確失敗。

## 回歸結果

| 檢查 | 結果 |
| --- | --- |
| Windows，Python 3.12.14 | 76 項：75 通過，1 項 POSIX 權限案例跳過 |
| 原生 Linux 檔案系統，Python 3.14.4 | 76 項：75 通過，1 項 Windows junction 案例跳過；新增連結案例以 symlink 驗證 |
| 新增攻擊情境 | 14 項，包含 31 組不合法匯入／整理欄位變異、9 組編碼或平台路徑及所有 POST 管理入口的跨來源／缺少 client header 拒絕 |
| 瀏覽器 XSS | 17 個檢查通過；三組 img／svg／結束 textarea 加 script 輸入及原始技能 script 標籤都維持文字，來源指紋不變 |
| 瀏覽器跨站 | 另一個 loopback origin 嘗試讀取、JSON 寫入、簡單寫入、表單及 iframe；CORS／CORP／403／frame-ancestors 阻擋，合成整理資料雜湊不變 |

跨站攻擊頁的 console 出現預期的 CORS、CORP 與 CSP 拒絕訊息；不應將這些防護訊息列為主介面程式錯誤。直接 HTTP 測試可確認伺服器拒絕狀態；瀏覽器的 opaque response 或 fetch 失敗本身不等於完成全部後端驗證。

執行單元與瀏覽器回歸方式見 [開發指南](DEVELOPMENT.md#驗證)。測試矩陣紀錄的是實際本機環境，不表示 GitHub Actions 的 Python 3.11／3.13 矩陣已在遠端執行。

## 靜態與機密檢查

本次使用 Bandit 1.9.4、actionlint 1.7.12 及 Gitleaks 8.30.1。工具只安裝在獨立開發環境，未加入執行相依套件。

```sh
bandit -r skillpane scripts -f json -o .runtime/bandit-report.json
actionlint -shellcheck= -pyflakes= .github/workflows/ci.yml
python scripts/check_publication.py --history --include-untracked
gitleaks git . --log-opts=--all --redact=100 --no-banner --exit-code 1
```

報告應存放 Git 忽略／工作目錄；不要提交含個人路徑的原始掃描報告。候選檔案還須用 Gitleaks dir 獨立掃描，不能以歷史掃描代替。

- Bandit：0 高、0 中、4 低，未用 `nosec` 或全域排除隱藏提示。4 低是兩個 subprocess import（B404）及兩個參數陣列呼叫（B603）。逐項確認執行檔來自 `shutil.which`、未開 shell、Git 子命令與選項由程式固定；技能路徑在查詢前重新驗證，Git log 另有超時與禁用互動／外部工具設定。公開檢查腳本的額外參數僅由程式內的已知分支組成。仍依賴可信的本機 PATH、Git 及作業系統，不能當成惡意本機執行環境的隔離。
- actionlint：通過工作流程結構與 expression 檢查。未執行 ShellCheck 或 Pyflakes，命令明確停用這兩個外部工具；不宣稱包含其檢查範圍。
- Gitleaks：本機可到達的三個 commit 及本次候選程式／文件分別掃描，未發現規則可辨識的機密。掃描器不保證識別所有秘密或個資，也未涵蓋 GitHub 附件、歷史 artifacts 等 Git 之外內容。
- 私有路徑邊界與差異空白檢查須通過；不得包含真實 `.data/`、`.runtime/`、技能原文或環境設定。

工具依據：[Bandit](https://bandit.readthedocs.io/en/latest/)、[actionlint](https://github.com/rhysd/actionlint)、[Gitleaks](https://github.com/gitleaks/gitleaks)。攻擊情境參考 [OWASP WSTG](https://owasp.org/www-project-web-security-testing-guide/stable/)。

## 後續關卡

0.4 本機驗證：123 項 Python 測試（122 通過、1 項 POSIX 平台案例略過），持鎖測試修正後另單獨重驗通過；Chromium 桌面、低高度及手機共 18 項瀏覽器測試通過，桌面與手機合成預覽已人工檢視。本機 Firefox 六項因啟動相依錯誤未通過；該提交的 Linux Firefox 已於上方 CI 驗收。Bandit 當時為 0 高、0 中、4 低；候選檔、可到達歷史、公開路徑及 actionlint 檢查通過，後續提交仍須重掃。

0.4 新增掃描紀錄的負向驗證：損壞、重複鍵、未支援格式、超大檔、外部改寫、原子替換失敗、路徑連結與並行重掃；確認原檔保留、技能唯讀、私有檔不可透過靜態資源讀取、跨來源重掃被拒絕。瀏覽器另驗證名稱注入以純文字顯示。這是內部合成測試，不是獨立滲透測試；仍不保證抵禦惡意本機程序同時替換檔案。

先前版本的遠端 CI 證據依上方確切提交紀錄；新版本須另確認其 SHA 的工作結果，不沿用舊版通過結論。私下回報入口仍待公開後完成 [驗收](SECURITY_REPORTING.md)，repository 維持私人。公開或發版前須重掃當時候選檔案及完整歷史、核對遠端結果；獨立滲透測試仍需另外安排。
