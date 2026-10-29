# 安全測試紀錄

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

遠端 CI、GitHub 安全設定與私下回報管道的實際確認屬於後續階段。尚未推送本次修改，也沒有因這份紀錄而變更 repository 可見度。公開或發版前須重新驗證確切提交、候選檔案與遠端結果；獨立滲透測試仍需另外安排。
