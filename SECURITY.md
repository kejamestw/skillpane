# 安全政策 / Security policy

Skillpane 是早期的本機個人工具。目前只對最新 0.4 修訂版提供盡力而為的安全修正；尚未接受獨立滲透測試，也沒有安全認證或保證回應時間。

## 支援的使用情境

- 掃描變更紀錄保存在本機，限制事件數、基準數與大小，沿用同源重掃與技能唯讀邊界。名稱等文字仍可能敏感；紀錄不包含於可攜備份。它不偵測所有檔案變更，也不是惡意程式掃描器。
- 服務僅綁定 `127.0.0.1`，由同一位作業系統使用者在本機瀏覽器使用。
- Repository 公開不代表服務可對外部署。沒有登入、TLS、租戶隔離或公共服務的資源限制。
- 不支援 LAN／公開網路、共享主機、反向代理、port forwarding 或 tunnel。Python 官方也不建議將 `http.server` 當作正式網路服務。
- 應使用仍受安全支援的 Python、瀏覽器及 Git，且不以 root／系統管理員執行。

同帳號的惡意程式、惡意瀏覽器擴充功能、已被控制的作業系統，以及能直接修改資料／技能目錄的攻擊者，不在此服務可隔離的信任邊界內。執行來源不明技能的風險也不會因本面板而消失。

## 現有防護與限制

- 固定 loopback、Host／Origin／Fetch Metadata 檢查；寫入需同源 JSON 與自訂 header，不開放 CORS。
- 靜態資源使用允許清單；技能內容以掃描識別取得，讀取與 Git 來源查詢前重新檢查 canonical path 與大小，沒有任意檔案路徑 API。Git 來源查詢只在技能所屬的掃描根目錄內尋找 repository，不採用 bare repository 版面，並停用 fsmonitor、pager、外部 diff、textconv 與延遲下載；仍會讀取該範圍內 repository 自己的設定。掃描的排除規則也套用到連結解析後的位置；超長識別會略過並計數。
- 不執行技能腳本，不把原文當 HTML。動態文字經 escaping／textContent；CSP 禁止 inline script 與外部 script、frame、object。
- HTTP body、整理資料、匯入筆數及欄位有上限；拒絕歧義 JSON、非有限數值與不支援的分塊寫入。
- 常用提示詞只保存與複製文字；每個技能最多 20 筆，名稱及內容分別最多 80／4,000 字。儲存時比對編輯前的提示詞，衝突回傳 409 並保留草稿。提示詞及其他個人文字可能含機密，會隨整理資料備份匯出。
- 整理資料寫入獨立目錄，內容有變更時先備份再原子替換，內容相同的儲存不改寫也不新增備份；預覽 token 限時、檢查資料 revision。寫入及預覽套用會檢查磁碟資料指紋，清理預覽也會先檢查，外部改寫時停止操作。它不是跨程序資料庫鎖，也不是跨多檔案的交易；每個 checkout 請只執行一個實例。
- 清理只針對通過檢查的備份名稱，先列出清單再明確確認，並比對內容指紋；多檔刪除若遇到檔案系統錯誤，可能只完成部分刪除。
- 機密掃描與 Git 忽略規則不會清除使用者輸入文字中的所有秘密；備份並未加密。

本機 HTTP 仍可能被同帳號程式存取。大量請求可能影響可用性，本專案不宣稱具備對抗惡意本機程序的 DoS 防護。檔案系統同時被外部程序惡意替換的完整防護亦不在目前保證範圍。

## 私下回報漏洞

請勿把漏洞利用細節、真實技能、個人筆記或憑證貼在公開 Issue／PR。

Repository 已於 2026-10-31（台灣時間，UTC+8）公開，並已啟用 GitHub 原生 private vulnerability reporting（API 確認 `enabled: true`）。請透過 [Report a vulnerability](https://github.com/kejamestw/skillpane/security/advisories/new) 私下回報。不設專用安全信箱；不要猜測聯絡信箱，或將 Git 提交使用的 noreply 地址當作收件管道。

一般回報者的表單入口與維護者收件尚待驗收；完成前維護者不另行宣傳回報管道，也不發布新版本。設定、收件驗收與後續處理見 [回報管道驗收](docs/SECURITY_REPORTING.md)。

報告請提供版本、平台、受影響功能、最小合成重現步驟、攻擊所需權限及影響範圍。以測試值替代憑證；若真實憑證已暴露，請先向發行者撤銷／輪替。

## 公開與發版前

本機攻擊情境回歸、工具使用方式及尚未驗證範圍見 [安全測試紀錄](docs/SECURITY_TESTING.md)。這是維護過程中的內部驗證，不是獨立滲透測試。

請完成 [開發指南的檢查表](docs/DEVELOPMENT.md#公開前檢查)，並確認 CI 結果。公開後已啟用私下漏洞回報、secret scanning 與 push protection、Dependabot 安全更新、CodeQL default setup，以及 `main` 的分支保護（禁止 force push 與刪除；PR 須通過 CI `validation`）。設定紀錄見 [安全測試紀錄](docs/SECURITY_TESTING.md)；啟用設定不等於沒有漏洞。

回報入口與收件驗收完成前，不對外宣傳回報管道或發布新版本，不能把已啟用的設定寫成已驗收的收件流程。

參考：[Python HTTP server 安全限制](https://docs.python.org/3/library/http.server.html)、[OWASP DOM XSS 防護](https://cheatsheetseries.owasp.org/cheatsheets/DOM_based_XSS_Prevention_Cheat_Sheet.html)、[GitHub 私下漏洞回報](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository)。

The repository became public on 2026-10-31 (UTC+8), and GitHub private vulnerability reporting is enabled (confirmed through the API). Report privately through [Report a vulnerability](https://github.com/kejamestw/skillpane/security/advisories/new). There is no dedicated security mailbox. Maintainer verification of the reporter-side form and of report receipt is still pending; until then the channel is not separately announced and no new release is published. Do not disclose exploit details in public issues or send reports to a Git noreply address. This is a local-only, early-stage tool, not a public hosting service or independently audited security product.
