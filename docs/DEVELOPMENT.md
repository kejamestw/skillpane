# 開發與公開準備

## 結構

| 路徑 | 職責 |
| --- | --- |
| `skillpane/catalog.py` | 唯讀掃描、分類、版本收合及候選群組 |
| `skillpane/metadata.py` | 不執行內容的保守 YAML 欄位判讀 |
| `skillpane/library.py` | 穩定識別、來源證據及比較 |
| `skillpane/changes.py` | 有上限的本機掃描基準與變更紀錄 |
| `skillpane/storage.py` | 格式驗證、原子替換與本機備份 |
| `skillpane/transfers.py` | 有效期／revision 綁定的匯入、關聯與清理預覽 |
| `skillpane/server.py` | loopback HTTP、同源驗證與資源允許清單 |
| `web/` | 無建置流程的 HTML、CSS、原生 JavaScript modules |
| `tests/` | 合成資料測試與瀏覽器回歸腳本 |
| `Start.ps1`、`Stop.ps1`、`scripts/Launcher.ps1` | Windows 啟停、排他鎖、程序及監聽身分驗證 |
| `scripts/launcher_entry.py` | Windows 絕對啟動入口，供命令列核對 checkout |
| `.data/`、`.runtime/` | 忽略於 Git 的個人資料與執行產物 |

一個 checkout 同時只執行一個服務。儲存採程序內 lock、外部變更指紋檢查、原子替換與備份；不提供跨程序鎖或共享資料庫的隔離保證。

## 驗證

使用受安全支援的 Python，執行：

```sh
python -B -m unittest discover -s tests -v
node --check web/app.js
node --check web/management.js
node --check web/prompts.js
node --check web/changes.js
node --check tests/browser-regression.js
node --check tests/browser-management.js
node --check tests/browser-security.js
node --check tests/browser-prompts.js
python scripts/check_publication.py --history --include-untracked
git diff --check
```

Windows junction 測試需要權限建立工作目錄內的 junction。POSIX 檔案模式案例只在 POSIX 系統執行；請在原生 Linux 檔案系統驗證，不以 Windows 掛載目錄模擬 Unix 權限。測試保留合成產物於 `.runtime/` 供診斷，不讀取真實 home。永久清理的後端測試 mock unlink，不會刪除使用者備份。

瀏覽器測試另啟動獨立服務：

```sh
python -B tests/browser_fixture.py --port 8779
```

開啟該測試位址，將 `tests/browser-regression.js` 函式貼入開發者工具，執行 `await runSkillpaneRegression()`；再貼 `tests/browser-management.js` 並執行 `await runManagementRegression()`。兩者會檢查測試服務標記，禁止對真實資料操作。服務每次啟動使用新的合成 home。

上述腳本也由 Playwright 自動執行：Chromium 驗證 1280×720、1024×480 與 390×844，Firefox 驗證 1280×720。獨立的 CI browser job 會檢查搜尋選取、草稿、列表及詳情捲動、主題、自訂資訊、匯入還原、重新關聯與比較，並補充真正的輸入、點擊、滑鼠滾輪及偏好重載測試。自動測試驗證行為及幾何邊界，不代替人工視覺或實機觸控驗收。完整命令及隔離方式見 [自動化測試](TESTING.md)。

同一個合成服務也可貼入 `tests/browser-security.js` 並執行 `await runSecurityRegression()`，驗證名稱、摘要、標籤、筆記等惡意 HTML 維持文字顯示，沒有建立注入元素或執行事件。

貼入 `tests/browser-prompts.js` 並執行 `await runPromptRegression()`，驗證字級、側邊欄、提示詞 CRUD、草稿、文字跳脫、搜尋、備份及多視窗衝突。腳本同樣只允許合成測試服務。

提示詞存於第 2 版 annotation 的可選 `prompts` 欄位。PATCH 包含提示詞時必須同送 `prompts_base`（開啟編輯器時的完整提示詞陣列）；後端在儲存 lock 內比對，過期時回傳 HTTP 409，不寫入。此檢查不阻擋其他視窗單獨修改筆記。`prompts_base` 不持久化。含新欄位的資料需 0.3 以上版本讀取。

`tests/test_adversarial.py` 會自動被 unittest discovery 收錄，涵蓋外部改寫、失效／重用預覽、備份變更、連結換向、超長識別及惡意請求。具體範圍、靜態工具與結果見 [安全測試紀錄](SECURITY_TESTING.md)。

## 機密掃描與 CI

`scripts/check_publication.py` 僅檢查 Git 檔案邊界，不是機密掃描器。另使用 [Gitleaks](https://github.com/gitleaks/gitleaks) 掃描：

```sh
gitleaks git . --log-opts=--all --redact=100 --no-banner --exit-code 1
```

此命令只涵蓋本機可到達的歷史。提交前還須檢查 staged 與未追蹤程式文件，可將明確列出的候選程式檔複製到獨立暫存目錄，再用 `gitleaks dir 候選目錄 --redact=100 --no-banner --exit-code 1`。不要掃描或複製 `.data/`、真實技能及其他個人目錄到公開測試產物。

CI 使用固定完整 commit 的官方 Actions、`contents: read` 與 `persist-credentials: false`。Gitleaks 固定版本並比對 Linux archive 的 SHA256；不使用會寫入 PR 的 token，不上傳秘密報告或測試產物。Dependabot 只追蹤 Actions 更新。CI 的執行相依套件與 GitHub 基礎設施仍有供應鏈風險，應持續維護固定版本。

Playwright 1.64.1 是鎖定於 package-lock.json 的開發相依套件，使用 `npm ci --ignore-scripts` 安裝；瀏覽器另以本機鎖定 CLI 下載。Node 24 只供 CI 測試使用，不進應用程式執行期。Dependabot 同時追蹤 Actions 與 npm；測試不接受既有服務 URL，不上傳截圖、trace、影片或假資料。公開路徑檢查拒絕 node_modules、playwright-report 及 test-results。

每次 push 後須核對確切 SHA 的四個 Python matrix、browser 與 secrets jobs，共六個；不能把「已加入 workflow」當成「遠端 CI 已通過」。

## 公開前檢查

1. 使用合成資料完成適用測試、瀏覽器驗證及 Git 差異檢查。
2. 檢查全部候選檔案、staged 內容與完整可到達歷史；檢查 author email、附件及已刪除檔案，不只看目前工作目錄。
3. 確認沒有 `.data/`、`.runtime/`、真實技能、備份、環境檔、憑證、內部服務資訊或真實環境截圖。也檢查 Issues、PR、Actions artifacts、release 附件與 wiki 等 Git 之外的資料。
4. 機密若曾進 Git，先撤銷／輪替；由維護者決定歷史清理方式。不要以移除當前檔案就認定已消除歷史洩漏。
5. 確認 README、操作手冊、支援、安全政策、授權及第三方聲明符合實際版本。
6. 檢查 GitHub 簡介與 topics；不要把本機 URL、私有服務、內部專案或個人資料當成公開範例。
7. 確認遠端 CI，視 GitHub 方案啟用適用的 secret scanning、push protection、CodeQL 與分支保護。已決定公開時採用 GitHub 原生漏洞回報：公開前依 [回報管道驗收](SECURITY_REPORTING.md) 備妥授權與操作，公開後立即啟用並驗證入口及收件；目前 repo 私人，尚未設外部回報管道，未驗收前不宣布可回報或發布新版本。
8. 由 repository 擁有者明確決定何時改為 public；一般 commit／push 不應自動修改可見度。

這是一份可重複執行的風險檢查程序，不是無漏洞證明。需要更高保證時，應安排獨立安全審查與持續維護。
