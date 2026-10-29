"""Documentation-only synthetic library. Never opens the real user's data."""
import argparse
from pathlib import Path
import sys
from uuid import uuid4
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from skillpane.catalog import Catalog
from skillpane.server import AppServer

STAMP = '2026-01-01T00:00:00+00:00'
DEMO_SKILLS = (
    ('demo-page-review', '檢查頁面細節', '設計與動畫', '檢查排版、文字層次與互動回饋，列出可以逐項改善的地方。'),
    ('demo-motion-plan', '規劃互動動畫', '設計與動畫', '先釐清動畫的目的，再安排進出場與減少動態效果。'),
    ('demo-api-notes', '整理 API 文件', '開發工具', '整理請求、回應及錯誤範例，協助團隊理解介面。'),
    ('demo-test-plan', '規劃回歸測試', '開發工具', '依實際變更列出正常流程、邊界與失敗情境。'),
    ('demo-log-reader', '閱讀範例紀錄', '維運與資料', '從合成紀錄中整理事件時間線，不連線任何真實服務。'),
    ('demo-release-notes', '撰寫更新摘要', '開發工具', '將已確認的變更整理成容易閱讀的版本說明。'),
)


class DemoCatalog(Catalog):
    def snapshot(self):
        return {**super().snapshot(), 'demo_fixture': True, 'generated_at': STAMP}


def create_demo(port=0):
    # No configurable home/state paths and no reused state: every run is isolated.
    base = ROOT / '.runtime' / ('docs-demo-' + uuid4().hex)
    home = base / 'synthetic-home'
    for name, _, _, description in DEMO_SKILLS:
        if name == 'demo-release-notes':
            continue  # Added after the first scan to demonstrate history.
        target = home / '.agents/skills' / name / 'SKILL.md'
        target.parent.mkdir(parents=True)
        target.write_text(f'---\nname: {name}\ndescription: {description}\n---\n'
                          '# 文件展示用合成技能\n\n這是虛構內容，不是可安裝技能。\n', encoding='utf-8')
    target = home / '.codex/skills/.system/demo-built-in/SKILL.md'
    target.parent.mkdir(parents=True)
    target.write_text('---\nname: demo-built-in\ndescription: 文件展示用的虛構內建項目。\n---\n', encoding='utf-8')
    old = home / '.agents/skills/demo-retired-check'
    old.mkdir()
    (old / 'SKILL.md').write_text('---\nname: demo-retired-check\ndescription: 已移出掃描範圍的虛構項目。\n---\n', encoding='utf-8')
    with patch('skillpane.changes.now', return_value=STAMP):
        server = AppServer(port=port, home=home, state_dir=base / 'state')
    try:
        hidden = home / '.agents/skills/.trash/demo-retired-check'
        hidden.parent.mkdir()
        if home.resolve() not in old.resolve().parents or home.resolve() not in hidden.resolve().parents:
            raise ValueError('Synthetic fixture move escaped its own home.')
        old.rename(hidden)
        target = home / '.agents/skills/demo-release-notes/SKILL.md'
        target.parent.mkdir()
        target.write_text('---\nname: demo-release-notes\ndescription: 將已確認的變更整理成容易閱讀的版本說明。\n---\n# 文件展示用合成技能\n', encoding='utf-8')
        target = home / '.agents/skills/demo-api-notes/SKILL.md'
        target.write_text(target.read_text(encoding='utf-8') + '\n新增合成的錯誤回應檢查說明。\n', encoding='utf-8')
        server.catalog = DemoCatalog(home)
        server.library.catalog = server.catalog
        with patch('skillpane.changes.now', return_value=STAMP):
            server.library.rescan()
        skills = {s['name']: s for s in server.library.snapshot()['skills']}
        for name, alias, category, _ in DEMO_SKILLS:
            payload = {'alias': alias, 'category': category, 'status': 'keep'}
            if name == 'demo-page-review':
                payload.update(favorite=True, note='示範筆記：畫面完成後，先檢查閱讀順序，再檢查小視窗。',
                               prompts=[{'id': 'demo-prompt-review', 'title': '上線前的介面檢查',
                                         'body': '請用 demo-page-review 檢查這個頁面。\n先列出影響閱讀的問題，再提出三項可執行的改善。'}])
            if name == 'demo-motion-plan':
                payload['status'] = 'review'
            server.annotations.update(skills[name]['id'], payload,
                                      expected_prompts=[] if 'prompts' in payload else None)
    except Exception:
        server.server_close()
        raise
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=0)
    args = parser.parse_args()
    server = create_demo(args.port)
    print(f'Synthetic documentation demo: {server.origin}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
