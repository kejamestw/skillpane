# 安全政策 / Security policy

Skillpane 是早期的本機個人工具。目前只對最新 0.2 修訂版提供盡力而為的安全修正；尚未接受獨立滲透測試，也沒有安全認證或保證回應時間。

## 支援的使用情境

- 服務僅綁定 `127.0.0.1`，由同一位作業系統使用者在本機瀏覽器使用。
- Repository 公開不代表服務可對外部署。沒有登入、TLS、租戶隔離或公共服務的資源限制。
- 不支援 LAN／公開網路、共享主機、反向代理、port forwarding 或 tunnel。Python 官方也不建議將 `http.server` 當作正式網路服務。
- 應使用仍受安全支援的 Python、瀏覽器及 Git，且不以 root／系統管理員執行。

同帳號的惡意程式、惡意瀏覽器擴充功能、已被控制的作業系統，以及能直接修改資料／技能目錄的攻擊者，不在此服務可隔離的信任邊界內。執行來源不明技能的風險也不會因本面板而消失。

## 現有防護與限制

- 固定 loopback、Host／Origin／Fetch Metadata 檢查；寫入需同源 JSON 與自訂 header，不開放 CORS。
- 靜態資源使用允許清單；技能內容以掃描識別取得，讀取前檢查 canonical path 與大小，沒有任意檔案路徑 API。
- 不執行技能腳本，不把原文當 HTML。動態文字經 escaping／textContent；CSP 禁止 inline script 與外部 script、frame、object。
- HTTP body、整理資料、匯入筆數及欄位有上限；拒絕歧義 JSON、非有限數值與不支援的分塊寫入。
- 整理資料寫入獨立目錄，先備份再原子替換；預覽 token 限時、檢查資料 revision。它不是跨程序資料庫鎖，也不是跨多檔案的交易；每個 checkout 請只執行一個實例。
- 清理只針對通過檢查的備份名稱，先列出清單再明確確認，並比對內容指紋；多檔刪除若遇到檔案系統錯誤，可能只完成部分刪除。
- 機密掃描與 Git 忽略規則不會清除使用者輸入文字中的所有秘密；備份並未加密。

本機 HTTP 仍可能被同帳號程式存取。大量請求可能影響可用性，本專案不宣稱具備對抗惡意本機程序的 DoS 防護。檔案系統同時被外部程序惡意替換的完整防護亦不在目前保證範圍。

## 私下回報漏洞

請勿把漏洞利用細節、真實技能、個人筆記或憑證貼在公開 Issue／PR。

Repository 公開且維護者啟用 GitHub private vulnerability reporting 後，請使用 [Report a vulnerability](https://github.com/kejamestw/skillpane/security/advisories/new)。目前尚為私人 repository，或未顯示回報按鈕時，這個入口可能不可用。已具 repository 權限的協作者請透過既有私下管道聯絡維護者；其他人可建立只要求「安全回報聯絡管道」的 Issue，不附上可利用細節，等待維護者提供私下管道。不要猜測聯絡信箱。

報告請提供版本、平台、受影響功能、最小合成重現步驟、攻擊所需權限及影響範圍。以測試值替代憑證；若真實憑證已暴露，請先向發行者撤銷／輪替。

## 公開與發版前

請完成 [開發指南的檢查表](docs/DEVELOPMENT.md#公開前檢查)，並確認 CI 結果。私有漏洞回報、secret scanning、push protection、CodeQL 及分支保護等 GitHub 功能是否可用取決於 repository 狀態與方案，設定檔本身不表示已啟用。

公開前須先啟用或確認可用的私下回報管道，不能宣稱尚未啟用的服務已在運作。

參考：[Python HTTP server 安全限制](https://docs.python.org/3/library/http.server.html)、[OWASP DOM XSS 防護](https://cheatsheetseries.owasp.org/cheatsheets/DOM_based_XSS_Prevention_Cheat_Sheet.html)、[GitHub 私下漏洞回報](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository)。

For security reports, use GitHub private vulnerability reporting when available. If unavailable, request a private contact channel without disclosing exploit details in a public issue. This is a local-only, early-stage tool, not a public hosting service or independently audited security product.
