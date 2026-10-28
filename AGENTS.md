# Skillpane 專案協作規則

- 使用者授權範圍優先；commit、push、對外發文及可見度變更是分開的操作，不能互相推定。
- 個人技能、工具設定及原始技能內容維持唯讀。不要在測試、截圖、文件或提交中使用真實使用者資料。
- `.data/`、`.runtime/`、環境檔、備份與憑證不得進 Git；不要以 `git add .` 取代逐項檢查，也不要強制加入忽略檔案。
- 每次 push 前檢查 staged／候選程式文件與完整可到達歷史，執行 `python scripts/check_publication.py --history --include-untracked`，以及 `gitleaks git . --log-opts=--all --redact=100 --no-banner --exit-code 1`。只掃歷史不涵蓋未提交檔案；候選檔案還需獨立機密掃描。
- 掃描輸出不得顯示完整秘密或上傳報告。發現可能洩漏先停止 push；先處理憑證撤銷，再由維護者決定歷史清理方式。
- 安全寫入、HTTP、路徑或格式改動需執行適用負向測試；使用獨立假資料服務驗證 UI，勿在真實面板執行會寫入的測試。
- 更新操作文件、CHANGELOG 與安全邊界，使其符合實作。說明未驗證範圍，不能把掃描或測試通過稱為無漏洞保證。
- Repository 可公開不代表本機 HTTP 服務可公開部署。不得默默放寬 loopback、同源檢查、CSP 或技能唯讀邊界。

詳細開發流程見 `docs/DEVELOPMENT.md`；漏洞回報見 `SECURITY.md`。公開專案不要求私人任務系統 ID。
