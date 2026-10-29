# CI 驗證流程與文件分流

本批流程須推送後以確切提交驗收 GitHub runner，本機模擬不代表遠端已通過。Repository 維持私人，未修改 branch protection 或其他 GitHub 設定。

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

本批包含 CI 腳本與工作流程，推送後應選完整模式，核對八項工作及全部測試。後續還需真正的純文件提交確認 skipped 與 validation；本機分類測試不等於 GitHub 編排已驗收。手動 workflow_dispatch 永遠全跑，不能用來驗證文件捷徑。
