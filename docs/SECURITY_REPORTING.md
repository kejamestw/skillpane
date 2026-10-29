# 私下漏洞回報管道：維護者驗收

這是維護者的設定與驗收流程。研究者應依 [安全政策](../SECURITY.md) 回報；本文件本身不代表管道已啟用。

維護者於 2026-10-29（台灣時間，UTC+8）選定：暫不設安全信箱，公開時啟用 GitHub 原生回報。Repository 目前維持私人；啟用、入口與實際收件均尚未驗收。

## 私人期間

GitHub 原生 private vulnerability reporting 供公開 repository 啟用，目前 Skillpane 維持私人。一般 repository API 可讀取，但回報功能 API 回傳 404；這不能單獨當成登入失敗的證據。

已授權協作者可以透過與維護者既有的私下管道聯絡。外部人士沒有私人 repo 的存取權時，也不能建立 Issue 要求聯絡方式。因此公開前必須選定回報管道並備妥啟用、驗收操作；目前不可用的連結須明列狀態。

## 公開時啟用 GitHub 原生回報

以下操作以維護者明確決定公開為前提。一般 commit／push 授權不包含變更 repository 可見度、GitHub 設定或對外送出測試報告。

1. 公開前重新確認候選檔案、完整歷史、Git 以外附件與確切 SHA 的 CI；由擁有者另行授權可見度變更。
2. 在 repository 的 Settings → Advanced Security 確認 Private vulnerability reporting 可用，列出設定差異並取得啟用授權。
3. 啟用後讀取 `GET /repos/kejamestw/skillpane/private-vulnerability-reporting`，確認回應 `enabled: true`。404 不代表已啟用；若 repo 已公開仍回傳錯誤，應再檢查帳號權限與功能可用性。
4. 使用一般研究者帳號確認 Security → Advisories → Report a vulnerability 入口及表單可開啟。擁有者看到按鈕不代表已驗證一般回報者的操作流程。
5. 若要端到端驗收，先取得送出合成測試報告的授權，由維護者確認報告維持私下可見且收到通知。僅能開啟表單時，紀錄為「入口已驗證」，不可寫成「收件已驗證」。
6. 完成後同步安全政策與 Issue 表單，確認引導至正確入口；測試報告的後續關閉或處理依維護者授權，不自動公開 advisory 或申請 CVE。

GitHub 功能必須在公開後才能啟用，因此公開前先準備好同一時段的設定與驗收操作；公開後立即執行。未確認入口與收件前，不對外宣傳回報管道或發布新版本。若功能不可用或驗收失敗，先停止公開發布流程，由維護者決定替代管道或其他處置；不自行變更可見度。

驗收紀錄至少包含確認日期（台灣時間）、repository、當時提交 SHA、API 啟用結果、一般回報者入口結果及維護者收件結果。僅保存必要狀態，不將真實漏洞細節、測試報告全文、私人連結、信箱後台或通知個資加入 repo。

## 回報後的處理

- 先確認受影響版本、平台、必要權限與最小合成重現步驟，避免要求研究者傳送真實技能或備份。
- 若包含有效憑證，先由憑證擁有者撤銷／輪替，避免把它複製到 Issue、log 或測試檔。
- 評估影響、修正及回歸測試，與回報者協調揭露時機。未取得授權前不對外發文。
- 將修正及適用版本寫入 CHANGELOG；是否發布 advisory／CVE 依實際影響及維護者決定。
- 管道變更、公開或發版前重做入口及收件驗收。設定成功不等於收件成功，也不是獨立安全審查。

參考：[GitHub 設定私下漏洞回報](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository)、[GitHub 私下回報漏洞](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/report-privately)。
