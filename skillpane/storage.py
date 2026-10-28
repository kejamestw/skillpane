"""Local organization metadata only. Never writes to skill folders."""
from __future__ import annotations
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import threading
from uuid import uuid4

STATUSES = {'keep', 'review', 'merge', 'archive'}


class Annotations:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.path = self.directory / 'annotations.json'
        self.lock = threading.RLock()
        self.data = {}
        if self.path.exists():
            if self.path.is_symlink() or self.path.stat().st_size > 4 * 1024 * 1024:
                raise ValueError('本機整理資料的路徑或大小異常。')
            value = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(value, dict):
                raise ValueError('本機整理資料格式錯誤；請保留檔案並檢查。')
            self.data = value

    def snapshot(self):
        with self.lock:
            return json.loads(json.dumps(self.data))

    def update(self, skill_id, payload):
        if not isinstance(payload, dict) or set(payload) - {'favorite', 'status', 'note'}:
            raise ValueError('整理資料包含不支援的欄位。')
        if 'favorite' in payload and type(payload['favorite']) is not bool:
            raise ValueError('收藏狀態格式錯誤。')
        if 'status' in payload and payload['status'] not in STATUSES:
            raise ValueError('不支援的整理狀態。')
        if 'note' in payload and (not isinstance(payload['note'], str) or len(payload['note']) > 4000):
            raise ValueError('筆記上限為 4000 字。')
        with self.lock:
            next_data = self.snapshot()
            next_data[skill_id] = {**next_data.get(skill_id, {}), **payload}
            self.directory.mkdir(parents=True, exist_ok=True)
            if self.directory.resolve() != self.directory or self.path.is_symlink():
                raise ValueError('本機資料目錄已變更，停止寫入。')
            if self.path.exists():
                backup_dir = self.directory / 'backups'
                backup_dir.mkdir(exist_ok=True)
                backup = backup_dir / f'{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid4().hex}.json'
                shutil.copy2(self.path, backup)
            temporary = self.directory / f'annotations-{uuid4().hex}.tmp'
            temporary.write_text(json.dumps(next_data, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(self.path)
            self.data = next_data
            return dict(next_data[skill_id])
