# CI 驗證流程與文件分流

完整與純文件流程已分別以確切提交驗收 GitHub runner，證據如下；後續啟動器診斷等變更仍須驗收自己的 SHA。Repository 維持私人，未修改 branch protection 或其他 GitHub 設定。

## 耗時依據

0.4.0 的 [393fb5c CI](https://github.com/kejamestw/skillpane/actions/runs/40879179409) 於台灣時間 2026-10-29 21:08:12 至 21:26:32 全部成功，約 18 分鐘。兩組 Windows Python 階段為 1075.137／1024.359 秒，Linux 約 14 秒、browser 工作約 67 秒。等待集中在含真實 PowerShell 啟停的 Windows 階段；尚未精確量測每個子指令。

本批改善純文件修改的等待，不宣稱完整 Windows 測試已變快。保留八個啟動器案例、四組 Python 矩陣、24 項 browser，以及每次指令 60 秒／Windows 工作 25 分鐘限制。

## 保守選擇範圍

`changes` 工作先執行分流及文件連結負向測試、相對連結檢查，再由 `scripts/ci_scope.py detect` 輸出固定的 `full=true`／`full=false`。事件文字、分支及檔名不插入 shell。

| 條件 | 流程 |
| --- | --- |
| 只有 README 中英文、CHANGELOG、SECURITY、SUPPORT、CONTRIBUTING、THIRD_PARTY_NOTICES、LICENSE | 文件流程 |
| 只有 `docs/` 內 Markdown、`docs/images/` 直接子層 PNG，或與前列文件混合 | 文件流程 |
| 程式、測試、腳本、啟動器、相依套件、AGENTS、`.github/` 或任一未知路徑 | 完整測試 |
| 混合非文件路徑、空差異、手動執行、未知事件、新分支零值基準、缺失 commit 或讀取錯誤 | 完整測試 |

Push 比較 before／after 並核對 checkout HEAD；PR 比較 base 與 head 的 merge-base，確認 head 包含在目前 checkout。Git 指令停用 fsmonitor、外部 diff 與 textconv，SHA 限完整十六進位；檔名使用 NUL 分隔、停用 rename 合併，搬移跨出文件範圍時全跑。分類不取代機密或惡意內容掃描。

## 每次執行與最終結果

- `secrets` 不依賴分流，每次 push／PR／手動流程都掃私有路徑及完整可到達歷史、核對 Gitleaks checksum。沒有 workflow 級 paths-ignore。
- 完整流程執行四組 Python 與 Chromium／Firefox；文件流程明確略過這些工作，不能稱作已執行通過。
- `validation` 以 `always()` 等待 changes、tests、browser、secrets。分流與 secrets 必須成功；完整模式須 tests／browser 成功，文件模式須是預期的 skipped。空輸出、失敗、取消及非預期略過均失敗。
- 完整流程預期八項工作；文件模式的 matrix 可能折疊為單一 skipped 工作，不假設仍有四項。
- 若既有 required checks 指定舊矩陣名稱，啟用前需確認相容性。未來可評估固定的 `validation` 作為 required check，但 GitHub 設定變更仍須擁有者另外授權，本批沒有設定。

官方依據：[工作條件](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-jobs-with-conditions)、[needs 與 always](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idneeds)、[輸出變數](https://docs.github.com/en/actions/reference/workflows-and-actions/variables)。GitHub 可能把 skipped 工作視為可合併狀態，因此另設最終驗證。

## 驗收與限制

本批本機全套 135 項（134 通過、1 項 POSIX 平台略過），其中新增分流十項及文件連結兩項；135／24 才是新完整流程的預期數量，0.4.0 舊提交的 123／24 證據仍獨立保留。Bandit 為 0 高、0 中、8 低：原有 4 低之外，新增兩個開發腳本各有 subprocess import／參數陣列呼叫提示。逐項確認使用可信 PATH 的 Git、固定子命令、SHA 驗證、30 秒限制、未開 shell；沒有以 nosec 或排除規則隱藏提示。

```sh
python -B -m unittest discover -s tests -p test_ci_scope.py -v
python -B -m unittest discover -s tests -p test_docs.py -v
python -B scripts/check_docs.py
actionlint -shellcheck= -pyflakes= .github/workflows/ci.yml
```

合成 Git 歷史涵蓋 push、PR merge-base 與缺失基準；負向測試涵蓋混合路徑、無效編碼／字元、空差異、無效事件及工作結果組合。相對連結檢查讀取 Git 追蹤／未忽略候選 Markdown，檢查行內檔案／圖片及 HTML img，不連外、不驗證 fragment。

本批包含 CI 腳本與工作流程，其完整模式及後續真正純文件提交已依下列提交分別驗收。手動 workflow_dispatch 永遠全跑，不能用來驗證文件捷徑。後續程式變更應執行完整矩陣，不能沿用先前的測試數量或成功結論。

## 本批完整流程：遠端證據

`2bbdbf64026badedd0e6ad3f271d76da69960fdf` 的 [完整 CI](https://github.com/kejamestw/skillpane/actions/runs/40889112628) 於 2026-10-29 22:34:00 至 2026-10-29 22:52:54（台灣時間，UTC+8）完成，八項工作全部成功。Windows Python 3.11／3.13 各 135 項（134 通過、1 項 POSIX 平台略過），Linux 兩組各 135 項（126 通過、9 項平台略過）；Chromium 三種尺寸與 Firefox 桌面共 24 項通過。

分流工作另執行十項分類測試、兩項文件連結測試與相對連結檢查，實際選擇 `full=true`。確認 secrets 的完整歷史掃描、Gitleaks checksum 與最終 validation 成功；八份工作日誌另在記憶體掃描通過，未保存原始日誌。回讀 repository 維持私人、該 run 沒有 artifacts，未變更 GitHub 設定。

這是相同提交的第二次完整執行。首次執行的 Windows Python 3.13 在持鎖案例最初的 `self.start()` 超過 60 秒，當時尚未建立持鎖程序；其他三組 Python、browser 與 secrets 成功，最終 validation 正確判失敗。[首次執行紀錄](https://github.com/kejamestw/skillpane/actions/runs/40889112628/attempts/1) 保留。本機單獨重驗該案例於 13.014 秒通過；維持原 60 秒限制及所有案例，沒有修改程式後重跑。首次啟動超時的根因尚未確認；第二次成功不代表間歇性問題已修復。

## 純文件流程：遠端證據

`a10e9c829bc51d607e0442c3bf0e2eb0c379b22c` 的 [文件 CI](https://github.com/kejamestw/skillpane/actions/runs/40896305956) 於 2026-10-29 22:55:18 至 22:55:36（台灣時間，UTC+8）完成，約 18 秒。12 個路徑均為 Markdown／PNG，實際選擇 `full=false`；changes、secrets、validation 成功，tests 與 browser 依預期 skipped，沒有執行完整 Python／瀏覽器套件。另核對三份實際工作日誌的機密掃描、checksum、repository 私人及零 artifacts。

## 後續啟動器診斷

Windows 啟停測試會印出允許清單內的階段耗時，說明與安全限制見 [測試指南](TESTING.md#windows-啟動超時診斷)。固定上限、真實安全負向案例與不自動重試的規則維持不變；這類程式／測試變更屬完整流程，新增數量須以該版本實際執行結果為準。

`95b7f6df531ad14438084d2fa331f1e787343339` 的 [完整 CI](https://github.com/kejamestw/skillpane/actions/runs/40901150133) 於 2026-10-29 23:23:59 至 23:44:18（台灣時間，UTC+8）首次執行八項成功。四組 Python 各 144 項，Windows 各 143 通過／1 略過、Linux 各 133 通過／11 略過；browser 24 項通過。兩組 Windows 各 48 次啟停無超時，八份日誌在記憶體掃描通過，repo 私人、零 artifacts。

該提交 Windows PowerShell 5.1 的成功 Start 中位約 20.6／25.4 秒（各七筆），PowerShell 7 各一筆約 1.4／1.7 秒；健康回應等待約半秒。當時只有階段耗時，無法區分建立呼叫、首次進入腳本及退出等待，因此不將差距直接當作特定版本或防毒程式的根因。

後續新增的 spawn_ms、first_stage_seen_ms、exit_stage_seen_ms、process_end_ms、script_elapsed_ms 與六次最小 Probe 觀測，仍須以它自己的提交在 GitHub 驗收；不能沿用 95b7f6d 的成功結論。未知值為 -1，輪詢觀測有取樣誤差；Probe 不啟動應用程式，亦不代表真實啟動案例的等量工作負載。每次新提交應核對實際測試數量、48 次真實啟停與六次 Probe，另保留 24 項 browser、secrets 及最終 validation。

上述父程序觀測已由 `9bbe35dbb7572f3f709fe6a01d565231f84cd5ca` 的 [完整 CI](https://github.com/kejamestw/skillpane/actions/runs/40997806303) 於 2026-10-30 11:30:53 至 11:50:48（台灣時間，UTC+8）首次執行驗收：八項成功，四組 Python 各 150 項（Windows 各 149 通過／1 略過，Linux 各 139 通過／11 略過），browser 24 項通過。兩組 Windows 各 48 次啟停及六次 Probe 沒有 timeout／spawn-error／cleanup-error；八份日誌在記憶體掃描通過，repo 私人、零 artifacts。

本輪 Windows PowerShell 5.1 成功 Start 首次標記觀測中位數約 21.4／24.1 秒，但最小 Probe 僅約 0.3 秒。根因仍未確認，不能將差距直接歸因於一般 PowerShell 啟動或特定防毒程式。

## 手動因素診斷工作

`Launcher startup diagnosis` 僅接受 workflow_dispatch，兩組固定 shell 矩陣各執行七組隔離案例。它不執行應用程式或既有完整回歸，也不替代八項 CI；僅保留固定數值摘要、不上傳原始日誌或 artifacts，說明見 [測試指南](TESTING.md#手動啟動因素診斷)。

`0aa65d1dc6b5ef53f2bdeabb4603681a7fa7d5e5` 的 [完整 CI](https://github.com/kejamestw/skillpane/actions/runs/41003073015) 於 2026-10-30 12:28:20 至 12:48:26（台灣時間，UTC+8）首次執行八項成功。四組 Python 各 158 項，Windows 各 157 通過／1 略過、Linux 各 147 通過／11 略過；browser 24 項通過，兩組 Windows 各 48 次啟停及六次 Probe 均無 timeout／spawn-error／cleanup-error。八份日誌在記憶體機密掃描通過，repo 私人、零 artifacts。

同 SHA 的 [手動診斷](https://github.com/kejamestw/skillpane/actions/runs/41003075815) 於 2026-10-30 12:28:22 至 12:29:16（台灣時間，UTC+8）兩組成功、共 14 筆；兩份日誌在記憶體掃描通過，零 artifacts。Windows PowerShell 5.1 的 `header-join` 首次路徑步驟約 19.8 秒，`header-qualified` 整筆約 0.2 秒；舊 `entry-body-parse` 首次路徑步驟約 12 秒。PowerShell 7 各筆約 0.4～0.6 秒。每案例僅一次、固定順序，可能受快取與排程影響；這縮小了未限定命令探索的慢點，未確認底層原因，也不證明先前 60 秒超時已修復。

## 入口限定修正與剩餘等待

`652ae380291b6b0551a9a386a0ec1afaf13e71c3` 的 [完整 CI](https://github.com/kejamestw/skillpane/actions/runs/41008788228) 於 2026-10-30 13:30:15 至 13:48:33（台灣時間，UTC+8）首次執行八項成功。四組 Python 各 158 項，Windows 各 157 通過／1 略過、Linux 各 147 通過／11 略過；browser 24 項通過。兩組 Windows 各 48 次啟停及六次 Probe 無 timeout／spawn-error／cleanup-error。八份日誌在記憶體掃描通過，repo 私人、零 artifacts。

同 SHA 的 [手動診斷](https://github.com/kejamestw/skillpane/actions/runs/41008807663) 於 2026-10-30 13:30:26 至 13:31:27（台灣時間，UTC+8）兩組、共 14 筆成功；兩份日誌另掃描通過、零 artifacts。Windows PowerShell 5.1 的舊未限定基準約 33.2 秒，使用目前入口限定方式的 `entry-body-parse` 約 0.33 秒。

正式 Start 首標記已縮短，但完整啟停尚未一致加速：Windows Python 3.11 的成功 Start 中位數約 25.1→20.0 秒，3.13 則約 25.1→25.3 秒。3.11 的 `record-read` 中位數約 18.7 秒，顯示等待移到紀錄讀取階段；不能把入口探針改善當作完整問題已修復，也未確認底層探索為何變慢。

下一批改由共用腳本明確載入 `$PSHOME/Modules/` 內 Utility 與 CimCmdlets manifest，不更改 PSModulePath 或執行原則。新版本完整測試預期 159 項；手動案例仍為兩組各七筆，但 `shared-ready` 現在包含上述載入成本，最小 Probe 的工作量亦隨共用腳本增加。仍須用新 SHA 另外驗收八項完整 CI 與兩組手動診斷，不沿用 `652ae38` 的成功或將不同工作量當成嚴格效能基準。
