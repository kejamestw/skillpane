# Skillpane

繁體中文優先的本機 Agent Skills 技能庫。理解每個技能的用途與呼叫方式，把個人技能、工具管理內容與外掛快取分開整理。

以 Apple 介面設計的層次、排版與互動原則規劃，使用系統字型、側欄／列表／詳情三欄結構、深淺主題、鍵盤搜尋與減少動態效果支援。

## 開始使用

需要 Python 3.10 以上，沒有第三方 Python／JavaScript 執行相依套件，也不需要 Node 建置。

```sh
python -m skillpane
```

開啟 <http://127.0.0.1:8766>。連接埠可用 `--port` 指定。

Windows 可雙擊 `Open-Skillpane.cmd`。啟動器優先使用 `SKILLPANE_PYTHON` 指定的 Python、Codex 內附 Python，再尋找 PATH 上的 Python；使用 `Start.ps1 -NoBrowser` 可只啟動服務。停止服務執行 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Stop.ps1`。

## 功能

- 預設瀏覽個人技能，另列 Claude 同步、系統內建與外掛快取。
- 依實體路徑合併 junction／symlink 別名；外掛相同技能的不同快取版本收合顯示。
- 搜尋名稱、用途、分類與本機筆記；支援名稱／修改時間排序。
- 常見設計技能提供中文名稱與使用範例，其他技能採用原始描述；不改寫 SKILL.md。
- 顯示 Codex CLI／Claude Code 呼叫格式，以及兩種工具各自的自動呼叫宣告。
- 同名、完全相同內容與設計用途相近分別呈現；用途相近僅為人工檢查候選。
- 收藏、筆記與整理標記另存本機 `.data/annotations.json`，備份使用唯一檔名。
- 原始內容以純文字顯示；不渲染 skill 中的 HTML、不執行 scripts。
- 匯出技能中繼資料，不包含技能全文與來源路徑。

## 安全與資料範圍

技能原始檔維持唯讀；目前不提供新增、修改、刪除或封存技能。只有收藏／筆記／標記會寫入本機 `.data/`。`.data/`、`.runtime/`、環境檔、測試產物皆排除於 Git；不將真實 skills 或個人掃描清單放入此 repository。

HTTP 服務僅監聽 `127.0.0.1`，檢查 Host、Origin 與 Fetch Metadata。整理資料寫入另要求同源 JSON 與自訂 header，不提供 CORS。靜態資源使用允許清單；內容 API 只接受掃描過的技能 ID。單一 skill 大小上限為 2 MiB。

這是本機個人工具，沒有登入系統；同一位作業系統使用者的其他程式仍能讀取本機服務。不要將服務對外轉送。

### 數量的定義

「我的技能」計算個人技能本體；「內建與外掛」包含工具管理內容。外掛顯示版本排序較新的磁碟快取，無法據此確認當前對話實際啟用的版本。不同來源或外掛的同名技能不會直接合併。

目前沒有可靠的使用次數、最近呼叫時間或自動淘汰判定；修改時間不視為使用時間。

## 開發與驗證

```sh
python -m unittest discover -s tests -v
node --check web/app.js
```

Windows junction 測試需允許建立工作目錄內的 junction；其他平台會略過該項。測試只使用 `.runtime/test-runs/` 內的假資料。Node 僅用於可選的語法檢查。

## 來源與授權

Skillpane 是以 [oh-my-skills](https://github.com/AIjunja/oh-my-skills) 為起點的獨立衍生專案。保留其 frontmatter 解析邏輯的部分實作，重新設計掃描分類、HTTP 服務、整理資料儲存與前端。詳細來源與上游 MIT 聲明見 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

MIT License。
