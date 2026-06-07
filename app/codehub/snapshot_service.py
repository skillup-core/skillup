"""
CodeHub Snapshot service.

Snapshots are tar.gz archives of the working copy stored under the user config
directory, independent of SVN. See app/codehub/docs/codehub.md section 13.
"""

import hashlib
import json
import os
import shutil
import tarfile
import tempfile
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from .svn_service import (
    _exceeds_track_size,
    _is_hidden_dir,
    _is_hidden_file,
)


AUTO_RETENTION = 3  # max number of auto snapshots per project (13.6)


class SnapshotError(Exception):
    pass


class SnapshotService:

    def __init__(self, root_dir: str, limit_bytes: int):
        """
        Args:
            root_dir: <config_home>/app/codehub-c0d3hub1/snapshot/
            limit_bytes: total quota across data/ (manual + auto share this)
        """
        self.root      = root_dir
        self.data_dir  = os.path.join(root_dir, 'data')
        self.tmp_dir   = os.path.join(root_dir, 'tmp')
        self.list_path = os.path.join(root_dir, 'list.json')
        self.limit     = int(limit_bytes)
        self._tmp_index: Dict[str, Dict] = {}  # tmp_id -> {path, meta}
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.tmp_dir,  exist_ok=True)

    # ── tmp lifecycle ────────────────────────────────────────────────────────

    def cleanup_tmp(self):
        """Wipe tmp/ on app start (13.6 임시 파일 청소)."""
        try:
            for n in os.listdir(self.tmp_dir):
                p = os.path.join(self.tmp_dir, n)
                if os.path.isfile(p):
                    try: os.remove(p)
                    except OSError: pass
                elif os.path.isdir(p):
                    shutil.rmtree(p, ignore_errors=True)
        except OSError:
            pass

    # ── list.json ────────────────────────────────────────────────────────────

    def _load_list(self) -> List[Dict]:
        if not os.path.isfile(self.list_path):
            return []
        try:
            with open(self.list_path, 'r', encoding='utf-8') as f:
                d = json.load(f)
            return d.get('snapshots', []) or []
        except Exception:
            return []

    def _save_list(self, snapshots: List[Dict]):
        os.makedirs(os.path.dirname(self.list_path), exist_ok=True)
        tmp = self.list_path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump({'snapshots': snapshots}, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.list_path)

    def list_all(self, project_id: Optional[int] = None) -> List[Dict]:
        snaps = self._load_list()
        if project_id is not None:
            snaps = [s for s in snaps if s.get('project_id') == project_id]
        snaps.sort(key=lambda s: s.get('created_at', ''), reverse=True)
        return snaps

    def total_bytes(self) -> int:
        """Sum of all .tar.gz files currently in data/."""
        n = 0
        try:
            for fn in os.listdir(self.data_dir):
                if not fn.endswith('.tar.gz'):
                    continue
                try:
                    n += os.path.getsize(os.path.join(self.data_dir, fn))
                except OSError:
                    pass
        except OSError:
            pass
        return n

    # ── archive creation ─────────────────────────────────────────────────────

    def _should_skip(self, abs_path: str, name: str, is_dir: bool) -> bool:
        if is_dir:
            return _is_hidden_dir(name)
        if _is_hidden_file(name):
            return True
        if _exceeds_track_size(abs_path):
            return True
        return False

    def _make_archive(self, src_dir: str, dst_tgz: str):
        """tar.gz the working copy at src_dir into dst_tgz, applying ignore rules."""
        if not os.path.isdir(src_dir):
            raise SnapshotError('working_copy_missing')
        src_norm = os.path.normpath(src_dir)
        with tarfile.open(dst_tgz, 'w:gz') as tar:
            for dirpath, dirnames, filenames in os.walk(src_norm):
                # prune dirs in place (skip .svn and other hidden dirs)
                dirnames[:] = [d for d in dirnames
                               if not self._should_skip(os.path.join(dirpath, d), d, True)]
                for fn in filenames:
                    abs_p = os.path.join(dirpath, fn)
                    if self._should_skip(abs_p, fn, False):
                        continue
                    rel = os.path.relpath(abs_p, src_norm)
                    try:
                        tar.add(abs_p, arcname=rel, recursive=False)
                    except (OSError, FileNotFoundError):
                        continue

    def _new_snapshot_id(self) -> str:
        ts = datetime.now().strftime('%Y%m%d-%H%M%S')
        h  = hashlib.sha1(os.urandom(8)).hexdigest()[:4]
        return f'{ts}-{h}'

    # ── quota planning ──────────────────────────────────────────────────────

    def _auto_prune_for_project(self, project_id: int) -> List[Dict]:
        """Trim auto snapshots of this project to AUTO_RETENTION. Returns removed."""
        snaps = self._load_list()
        auto = [s for s in snaps if s.get('type') == 'auto' and s.get('project_id') == project_id]
        auto.sort(key=lambda s: s.get('created_at', ''))   # oldest first
        excess = max(0, len(auto) - AUTO_RETENTION)
        removed = auto[:excess] if excess else []
        if removed:
            removed_ids = {s['id'] for s in removed}
            kept = [s for s in snaps if s['id'] not in removed_ids]
            for s in removed:
                self._delete_file(s.get('file'))
            self._save_list(kept)
        return removed

    def _auto_prune_for_quota(self, need: int) -> List[Dict]:
        """Delete old auto snapshots until total + need <= limit. Returns removed."""
        if need <= 0:
            return []
        snaps = self._load_list()
        auto = [s for s in snaps if s.get('type') == 'auto']
        auto.sort(key=lambda s: s.get('created_at', ''))   # oldest first
        removed: List[Dict] = []
        total = self.total_bytes()
        for s in auto:
            if total + need <= self.limit:
                break
            removed.append(s)
            total -= int(s.get('size_bytes', 0) or 0)
        if removed:
            removed_ids = {s['id'] for s in removed}
            kept = [s for s in snaps if s['id'] not in removed_ids]
            for s in removed:
                self._delete_file(s.get('file'))
            self._save_list(kept)
        return removed

    def _manual_candidates_for_quota(self, need: int) -> Tuple[int, List[Dict]]:
        """Return (need_free_bytes, candidate manual snapshots ordered oldest first)."""
        total = self.total_bytes()
        over = (total + need) - self.limit
        if over <= 0:
            return 0, []
        manual = [s for s in self._load_list() if s.get('type') == 'manual']
        manual.sort(key=lambda s: s.get('created_at', ''))
        return over, manual

    def _delete_file(self, filename: Optional[str]):
        if not filename:
            return
        p = os.path.join(self.data_dir, filename)
        try:
            if os.path.isfile(p):
                os.remove(p)
        except OSError:
            pass

    # ── prepare / commit / cancel ───────────────────────────────────────────

    def prepare(self, project_id: int, project_label: str, name: str,
                wc_dir: str, kind: str = 'manual',
                source_snapshot_id: Optional[str] = None) -> Dict:
        """
        Compress the WC into tmp/, measure, run auto-prune, return one of:
          {status: 'ok',           tmp_id, size_bytes, auto_pruned}
          {status: 'need_select',  tmp_id, size_bytes, need_free_bytes, auto_pruned, candidates}
          {status: 'too_large',    size_bytes, limit_bytes}        (no tmp_id; cleaned up)
        """
        if kind not in ('manual', 'auto'):
            raise SnapshotError('invalid_kind')
        # 1. compress to tmp
        os.makedirs(self.tmp_dir, exist_ok=True)
        tmp_id = self._new_snapshot_id()
        tmp_path = os.path.join(self.tmp_dir, tmp_id + '.tar.gz')
        try:
            self._make_archive(wc_dir, tmp_path)
        except Exception as e:
            if os.path.isfile(tmp_path):
                try: os.remove(tmp_path)
                except OSError: pass
            raise SnapshotError(f'archive_failed: {e}')
        size = os.path.getsize(tmp_path)

        # 2. single-item over-limit → reject
        if size > self.limit:
            try: os.remove(tmp_path)
            except OSError: pass
            return {'status': 'too_large', 'size_bytes': size, 'limit_bytes': self.limit}

        # 3. auto-prune step (always, sufficient for auto-kind; may help manual too)
        # First trim oldest auto beyond retention for *this* project.
        retention_removed = self._auto_prune_for_project(project_id)
        # Then quota-driven auto prune.
        quota_removed = self._auto_prune_for_quota(size)
        auto_pruned = retention_removed + quota_removed

        # 4. check whether more room is needed
        total = self.total_bytes()
        if total + size <= self.limit:
            self._tmp_index[tmp_id] = {
                'path': tmp_path,
                'meta': {
                    'project_id': project_id,
                    'project_label': project_label,
                    'name': name,
                    'type': kind,
                    'source_snapshot_id': source_snapshot_id,
                    'size_bytes': size,
                },
            }
            return {'status': 'ok', 'tmp_id': tmp_id, 'size_bytes': size,
                    'auto_pruned': [self._brief(s) for s in auto_pruned]}

        # 5. auto kind cannot prompt — bail (caller decides fallback)
        if kind == 'auto':
            try: os.remove(tmp_path)
            except OSError: pass
            return {'status': 'too_large', 'size_bytes': size, 'limit_bytes': self.limit,
                    'auto_pruned': [self._brief(s) for s in auto_pruned]}

        # 6. manual kind → return candidates for user selection
        need_free, candidates = self._manual_candidates_for_quota(size)
        self._tmp_index[tmp_id] = {
            'path': tmp_path,
            'meta': {
                'project_id': project_id,
                'project_label': project_label,
                'name': name,
                'type': kind,
                'source_snapshot_id': source_snapshot_id,
                'size_bytes': size,
            },
        }
        return {
            'status': 'need_select',
            'tmp_id': tmp_id,
            'size_bytes': size,
            'need_free_bytes': need_free,
            'auto_pruned': [self._brief(s) for s in auto_pruned],
            'candidates': [self._brief(s) for s in candidates],
        }

    def commit(self, tmp_id: str, delete_ids: Optional[List[str]] = None) -> Dict:
        """Finalize a prepared tmp into data/ and update list.json.
        Optionally delete listed snapshot ids first (user-selected for quota)."""
        if tmp_id not in self._tmp_index:
            raise SnapshotError('tmp_not_found')
        info = self._tmp_index[tmp_id]
        tmp_path = info['path']
        meta = dict(info['meta'])
        size = meta['size_bytes']

        # delete user-selected snapshots
        snaps = self._load_list()
        if delete_ids:
            del_set = set(delete_ids)
            for s in [x for x in snaps if x['id'] in del_set]:
                self._delete_file(s.get('file'))
            snaps = [s for s in snaps if s['id'] not in del_set]

        # quota recheck
        # (recompute total_bytes from disk in case manual file deletions changed it)
        total = 0
        for fn in os.listdir(self.data_dir):
            if fn.endswith('.tar.gz'):
                try: total += os.path.getsize(os.path.join(self.data_dir, fn))
                except OSError: pass
        if total + size > self.limit:
            raise SnapshotError('quota_exceeded')

        # move tmp → data/<id>.tar.gz
        snap_id = tmp_id
        filename = snap_id + '.tar.gz'
        dst = os.path.join(self.data_dir, filename)
        shutil.move(tmp_path, dst)
        snapshot = {
            'id': snap_id,
            'name': meta['name'],
            'type': meta['type'],
            'project_id': meta['project_id'],
            'project_label': meta['project_label'],
            'created_at': datetime.now().isoformat(timespec='seconds'),
            'size_bytes': size,
            'file': filename,
            'source_snapshot_id': meta.get('source_snapshot_id'),
        }
        snaps.append(snapshot)
        self._save_list(snaps)
        del self._tmp_index[tmp_id]
        # Re-prune auto retention after commit: prepare()'s prune ran before
        # this snapshot was added, so an auto-commit can push the count to
        # AUTO_RETENTION + 1. Trim again here.
        if meta['type'] == 'auto':
            self._auto_prune_for_project(meta['project_id'])
        return snapshot

    def cancel(self, tmp_id: str):
        info = self._tmp_index.pop(tmp_id, None)
        if info:
            try:
                if os.path.isfile(info['path']):
                    os.remove(info['path'])
            except OSError:
                pass

    # ── restore ─────────────────────────────────────────────────────────────

    def restore(self, snap_id: str, wc_dir: str) -> None:
        """Clean WC (preserve .svn + hidden) then extract the archive."""
        snaps = self._load_list()
        snap = next((s for s in snaps if s['id'] == snap_id), None)
        if snap is None:
            raise SnapshotError('snapshot_not_found')
        archive = os.path.join(self.data_dir, snap['file'])
        if not os.path.isfile(archive):
            raise SnapshotError('archive_missing')
        os.makedirs(wc_dir, exist_ok=True)

        # Clean WC: remove tracked-eligible entries but preserve .svn and ignored items.
        wc_norm = os.path.normpath(wc_dir)
        for name in os.listdir(wc_norm):
            full = os.path.join(wc_norm, name)
            is_dir = os.path.isdir(full)
            if is_dir:
                if name == '.svn':
                    continue
                if _is_hidden_dir(name):
                    continue
                shutil.rmtree(full, ignore_errors=True)
            else:
                if _is_hidden_file(name):
                    continue
                try: os.remove(full)
                except OSError: pass

        # Extract (use a safe member filter to block absolute / parent-escaping paths).
        with tarfile.open(archive, 'r:gz') as tar:
            for member in tar.getmembers():
                if member.name.startswith('/') or '..' in member.name.split('/'):
                    continue
                tar.extract(member, wc_norm)

    # ── delete ──────────────────────────────────────────────────────────────

    def delete_many(self, ids: List[str]) -> List[str]:
        snaps = self._load_list()
        id_set = set(ids)
        to_delete = [s for s in snaps if s['id'] in id_set]
        for s in to_delete:
            self._delete_file(s.get('file'))
        kept = [s for s in snaps if s['id'] not in id_set]
        self._save_list(kept)
        return [s['id'] for s in to_delete]

    # ── helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _brief(s: Dict) -> Dict:
        return {
            'id': s.get('id'),
            'name': s.get('name'),
            'type': s.get('type'),
            'project_id': s.get('project_id'),
            'project_label': s.get('project_label'),
            'created_at': s.get('created_at'),
            'size_bytes': s.get('size_bytes', 0),
        }
