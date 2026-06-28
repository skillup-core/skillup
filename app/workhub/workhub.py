"""
WorkHub - Personal work log and notes manager.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from typing import List
from lib.baseapp import BaseApp
from lib.appmgr import register_app_class
from desktop.account import get_current_user_id, get_default_account_db_path, enrich_user_info, list_accounts
from desktop import group as _group_mod

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_DB = os.path.join(_APP_DIR, 'data', 'workhub.db')
_DEFAULT_NOTIFY_DIR = os.path.join(_APP_DIR, 'data', 'notify')

CONFIG_DEFAULTS = {
    'workhub.db_path': _DEFAULT_DB,
    'workhub.notify_dir': _DEFAULT_NOTIFY_DIR,
    'workhub.autosave_count': '10',
    'workhub.action_history_limit': '200',
}

import importlib.util as _ilu


def _load_local(name):
    path = os.path.join(_APP_DIR, 'lib', name + '.py')
    spec = _ilu.spec_from_file_location('workhub_' + name, path)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_db = _load_local('db')
_search = _load_local('search')


class WorkHubApp(BaseApp):

    _instance_id = str(os.getpid())

    def on_run_cli(self, args: List[str]) -> int:
        print("WorkHub: use the desktop UI to manage work logs.", file=sys.stderr)
        return 0

    def on_run_desktop_initialize(self) -> int:
        config = self.load_config(CONFIG_DEFAULTS)
        db_path = config.get('workhub.db_path', _DEFAULT_DB)
        current_user = get_current_user_id()
        fts5_ok = _db.init_db(db_path, current_user)
        if not fts5_ok:
            print("[warn ] WorkHub: FTS5 not available, falling back to LIKE search", file=sys.stderr)

        self._cleanup_notify_dir()

        self.register_handlers({
            'work_list':         self._handle_work_list,
            'work_list_my':      self._handle_work_list_my,
            'work_get':          self._handle_work_get,
            'work_create':       self._handle_work_create,
            'work_save':         self._handle_work_save,
            'work_delete':       self._handle_work_delete,
            'work_search':       self._handle_work_search,
            'tag_list':          self._handle_tag_list,
            'user_info':         self._handle_user_info,
            'work_poll':         self._handle_work_poll,
            'history_save':      self._handle_history_save,
            'history_list':      self._handle_history_list,
            'history_get':       self._handle_history_get,
            'command_run':       self._handle_command_run,
            'work_copy':         self._handle_work_copy,
            'link_list':         self._handle_link_list,
            'link_add':          self._handle_link_add,
            'link_remove':       self._handle_link_remove,
            'link_resolve':      self._handle_link_resolve,
            'account_list':      self._handle_account_list,
            'work_get_titles':   self._handle_work_get_titles,
            'action_log_list':        self._handle_action_log_list,
            'search_history_load':    self._handle_search_history_load,
            'search_history_save':    self._handle_search_history_save,
            'sticky_load':            self._handle_sticky_load,
            'sticky_save':            self._handle_sticky_save,
            'channel_list':           self._handle_channel_list,
            'channel_create':         self._handle_channel_create,
            'channel_get':            self._handle_channel_get,
            'channel_update':         self._handle_channel_update,
            'channel_member_add':     self._handle_channel_member_add,
            'channel_member_remove':  self._handle_channel_member_remove,
            'channel_set_admin':      self._handle_channel_set_admin,
            'channel_delete':         self._handle_channel_delete,
            'channel_active_load':    self._handle_channel_active_load,
            'channel_active_save':    self._handle_channel_active_save,
            'group_list_all':         self._handle_group_list_all,
        })
        return 0

    def _db_path(self) -> str:
        config = self.load_config(CONFIG_DEFAULTS)
        return config.get('workhub.db_path', _DEFAULT_DB)

    def _notify_dir(self) -> str:
        config = self.load_config(CONFIG_DEFAULTS)
        return config.get('workhub.notify_dir', _DEFAULT_NOTIFY_DIR)

    def _notify_evt_path(self, work_id: int) -> str:
        return os.path.join(self._notify_dir(), f'{work_id}.evt')

    def _touch_notify(self, work_id: int, user_id: str = ''):
        import tempfile
        ndir = self._notify_dir()
        try:
            os.makedirs(ndir, exist_ok=True)
            # All users on shared NFS must be able to enter the dir and replace files
            try:
                os.chmod(ndir, 0o777)
            except OSError:
                pass
            path = os.path.join(ndir, f'{work_id}.evt')
            fd, tmp = tempfile.mkstemp(dir=ndir)
            try:
                # 666: all accounts on shared NFS need read access;
                # os.replace() (rename) succeeds via dir write perm regardless,
                # but 666 makes intent explicit and avoids edge cases
                os.chmod(tmp, 0o666)
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    f.write(f'{user_id}:{self._instance_id}')
                os.replace(tmp, path)
            except Exception:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
        except OSError as e:
            print(f"[warn ] WorkHub: notify touch failed: {e}", file=sys.stderr)

    def _cleanup_notify_dir(self):
        import time
        ndir = self._notify_dir()
        if not os.path.isdir(ndir):
            return
        cutoff = time.time() - 30 * 86400
        try:
            for fname in os.listdir(ndir):
                if not fname.endswith('.evt'):
                    continue
                fpath = os.path.join(ndir, fname)
                try:
                    if os.path.getmtime(fpath) < cutoff:
                        os.remove(fpath)
                except OSError:
                    pass
        except OSError as e:
            print(f"[warn ] WorkHub: notify cleanup failed: {e}", file=sys.stderr)

    def _action_history_limit(self) -> int:
        config = self.load_config(CONFIG_DEFAULTS)
        try:
            return int(config.get('workhub.action_history_limit', '200'))
        except (ValueError, TypeError):
            return 200

    def _get_account_db_path(self) -> str:
        from lib.config import get_desktop_config
        cfg = get_desktop_config('general.account_db', '').strip()
        return cfg if cfg else get_default_account_db_path()

    def _get_user_context(self):
        user_id = get_current_user_id()
        account_db_path = self._get_account_db_path()
        groups = _group_mod.list_groups(account_db_path, user_id)
        group_ids = [g['id'] for g in groups]
        group_names = [g['name'] for g in groups]
        channel_ids = _db.get_user_channel_ids(self._db_path(), user_id, group_ids,
                                               group_names=group_names)
        return user_id, group_ids, account_db_path, groups, channel_ids

    def _enrich_items(self, items: list, user_id: str, account_db_path: str) -> list:
        """Add is_owner, owner_display_name, owner_avatar_small, owner_avatar_mime to each item."""
        owner_ids = list({
            it['owner_id'] for it in items
            if it.get('owner_id') and it['owner_id'] != user_id
        })
        owner_info_map = {}
        for oid in owner_ids:
            owner_info_map[oid] = enrich_user_info(account_db_path, oid)
        for it in items:
            oid = it.get('owner_id', '')
            it['is_owner'] = (oid == user_id)
            if oid and oid != user_id:
                info = owner_info_map.get(oid, {})
                it['owner_display_name'] = info.get('display_name', oid)
                it['owner_avatar_small'] = info.get('avatar_small')
                it['owner_avatar_mime'] = info.get('avatar_mime')
            else:
                it['owner_display_name'] = None
                it['owner_avatar_small'] = None
                it['owner_avatar_mime'] = None
        return items

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _handle_user_info(self, data: dict, language: str) -> dict:
        user_id, group_ids, account_db_path, groups, channel_ids = self._get_user_context()
        info = enrich_user_info(account_db_path, user_id)
        return {
            'success': True,
            'user_id': user_id,
            'display_name': info['display_name'],
            'avatar_small': info['avatar_small'],
            'avatar_mime': info['avatar_mime'],
            'groups': [{'id': g['id'], 'name': g['name']} for g in groups],
        }

    def _handle_work_list(self, data: dict, language: str) -> dict:
        user_id, group_ids, account_db_path, _, channel_ids = self._get_user_context()
        channel_id = data.get('channel_id') or None
        # Verify client-supplied channel_id is accessible
        if channel_id and channel_id not in channel_ids:
            channel_id = None
        items = _db.work_list(self._db_path(), user_id, group_ids,
                              channel_id=channel_id, channel_ids=channel_ids)
        items = self._enrich_items(items, user_id, account_db_path)
        return {'success': True, 'items': items, 'current_user_id': user_id}

    def _handle_work_list_my(self, data: dict, language: str) -> dict:
        user_id, _, account_db_path, _, _ = self._get_user_context()
        items = _db.work_list_my(self._db_path(), user_id)
        items = self._enrich_items(items, user_id, account_db_path)
        return {'success': True, 'items': items, 'current_user_id': user_id}

    def _handle_work_get(self, data: dict, language: str) -> dict:
        work_id = data.get('id')
        if not work_id:
            return {'success': False, 'error': 'missing_id'}
        user_id, group_ids, account_db_path, _, channel_ids = self._get_user_context()
        item, err = _db.work_get(self._db_path(), int(work_id), user_id, group_ids,
                                 channel_ids=channel_ids)
        if err:
            return {'success': False, 'error': err}
        item['is_owner'] = (item.get('owner_id') == user_id)
        if not item['is_owner']:
            oid = item.get('owner_id', '')
            info = enrich_user_info(account_db_path, oid)
            item['owner_display_name'] = info.get('display_name', oid)
            item['owner_avatar_small'] = info.get('avatar_small')
            item['owner_avatar_mime'] = info.get('avatar_mime')
        return {'success': True, 'item': item}

    def _handle_work_create(self, data: dict, language: str) -> dict:
        user_id, _, _, _, channel_ids = self._get_user_context()
        template = data.get('template', 'note')
        title = data.get('title', '')
        body = data.get('body', '')
        tags = data.get('tags', '')
        history_body = data.get('history_body', '')
        channel_id = data.get('channel_id') or None
        # Verify client-supplied channel_id is accessible
        if channel_id and channel_id not in channel_ids:
            channel_id = None
        new_id, updated_at = _db.work_create(
            self._db_path(), template, user_id, title, body, tags,
            history_body=history_body,
            action_history_limit=self._action_history_limit(),
            channel_id=channel_id,
        )
        return {'success': True, 'id': new_id, 'version': 1, 'updated_at': updated_at}

    def _handle_work_save(self, data: dict, language: str) -> dict:
        work_id = data.get('id')
        if not work_id:
            return {'success': False, 'error': 'missing_id'}
        user_id, group_ids, account_db_path, _, channel_ids = self._get_user_context()
        title = data.get('title', '')
        body = data.get('body', '')
        tags = data.get('tags', '')
        visibility = data.get('visibility', 'me')
        group_id = data.get('group_id') or None
        version = int(data.get('version', 1))
        owner_write_only = 1 if data.get('owner_write_only', True) else 0
        skip_body = bool(data.get('skip_body', False))
        history_body = data.get('history_body', '')
        history_title = data.get('history_title', '')
        config = self.load_config(CONFIG_DEFAULTS)
        try:
            autosave_count = int(config.get('workhub.autosave_count', '10'))
        except (ValueError, TypeError):
            autosave_count = 10
        result = _db.work_save(
            self._db_path(), int(work_id), user_id, group_ids,
            title, body, tags, visibility, group_id, version,
            owner_write_only=owner_write_only,
            skip_body=skip_body,
            history_body=history_body, history_title=history_title,
            autosave_count=autosave_count,
            action_history_limit=self._action_history_limit(),
            channel_ids=channel_ids,
        )
        if result.get('success'):
            self._touch_notify(int(work_id), user_id)
            if not skip_body and result.get('prev_body') is not None:
                _db.sync_inline_links(
                    self._db_path(), int(work_id),
                    result['prev_body'], body,
                    user_id, group_ids,
                    action_history_limit=self._action_history_limit()
                )
        elif result.get('error') == 'conflict' and result.get('server_item'):
            srv = result['server_item']
            srv['is_owner'] = (srv.get('owner_id') == user_id)
            if not srv['is_owner']:
                info = enrich_user_info(account_db_path, srv.get('owner_id', ''))
                srv['owner_display_name'] = info.get('display_name', srv.get('owner_id', ''))
        return result

    def _handle_work_poll(self, data: dict, language: str) -> dict:
        work_id = data.get('id')
        if not work_id:
            return {'success': False, 'error': 'missing_id'}
        user_id, group_ids, account_db_path, _, channel_ids = self._get_user_context()
        _, err = _db.work_get(self._db_path(), int(work_id), user_id, group_ids,
                              channel_ids=channel_ids)
        if err == 'not_found':
            return {'success': False, 'error': 'not_found'}
        known_mtime = data.get('mtime', 0)
        path = self._notify_evt_path(int(work_id))
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return {'success': True, 'changed': False, 'mtime': known_mtime}
        changed = mtime > known_mtime + 0.001
        if not changed:
            return {'success': True, 'changed': False, 'mtime': mtime}
        # Read editor from file content; format: "user_id:instance_id"
        editor_id = ''
        editor_instance = ''
        try:
            with open(path, 'r', encoding='utf-8') as f:
                raw = f.read().strip()
            if ':' in raw:
                editor_id, editor_instance = raw.split(':', 1)
            else:
                editor_id = raw  # legacy: no instance_id
        except OSError:
            pass
        # Same user AND same instance = this desktop; suppress notification
        is_self = (editor_id == user_id and editor_instance == self._instance_id)
        editor = None
        editor_avatar = None
        editor_avatar_mime = None
        if editor_id and not is_self:
            info = enrich_user_info(account_db_path, editor_id)
            editor = info.get('display_name') or editor_id
            editor_avatar = info.get('avatar_small')
            editor_avatar_mime = info.get('avatar_mime')
        return {
            'success': True, 'changed': True, 'mtime': mtime,
            'editor': editor,
            'editor_avatar': editor_avatar,
            'editor_avatar_mime': editor_avatar_mime,
        }

    def _handle_work_delete(self, data: dict, language: str) -> dict:
        work_id = data.get('id')
        if not work_id:
            return {'success': False, 'error': 'missing_id'}
        user_id = get_current_user_id()
        result = _db.work_delete(self._db_path(), int(work_id), user_id,
                                 action_history_limit=self._action_history_limit())
        if result.get('success'):
            try:
                os.remove(self._notify_evt_path(int(work_id)))
            except OSError:
                pass
        return result

    def _handle_work_copy(self, data: dict, language: str) -> dict:
        work_id = data.get('id')
        if not work_id:
            return {'success': False, 'error': 'missing_id'}
        user_id, group_ids, _, _, channel_ids = self._get_user_context()
        result = _db.work_copy(self._db_path(), int(work_id), user_id, group_ids,
                               action_history_limit=self._action_history_limit(),
                               channel_ids=channel_ids)
        return result

    def _handle_work_search(self, data: dict, language: str) -> dict:
        query = data.get('query', '').strip()
        if not query:
            return {'success': True, 'items': []}
        user_id, group_ids, account_db_path, _, channel_ids = self._get_user_context()
        items = _search.search(self._db_path(), query, user_id, group_ids,
                               channel_ids=channel_ids)
        items = self._enrich_items(items, user_id, account_db_path)
        return {'success': True, 'items': items}

    def _handle_tag_list(self, data: dict, language: str) -> dict:
        user_id, group_ids, _, _, channel_ids = self._get_user_context()
        tags = _db.tag_list(self._db_path(), user_id, group_ids, channel_ids=channel_ids)
        return {'success': True, 'tags': tags}

    def _handle_history_save(self, data: dict, language: str) -> dict:
        work_id = data.get('id')
        if not work_id:
            return {'success': False, 'error': 'missing_id'}
        body = data.get('body', '')
        title = data.get('title', '')
        edited_at = data.get('edited_at', '')
        if not edited_at:
            return {'success': False, 'error': 'missing_edited_at'}
        user_id = get_current_user_id()
        config = self.load_config(CONFIG_DEFAULTS)
        try:
            autosave_count = int(config.get('workhub.autosave_count', '10'))
        except (ValueError, TypeError):
            autosave_count = 10
        return _db.work_history_save(
            self._db_path(), int(work_id), body, user_id, edited_at, autosave_count,
            title=title, action_history_limit=self._action_history_limit()
        )

    def _handle_history_list(self, data: dict, language: str) -> dict:
        work_id = data.get('id')
        if not work_id:
            return {'success': False, 'error': 'missing_id'}
        user_id, group_ids, account_db_path, _, channel_ids = self._get_user_context()
        entries, err = _db.work_history_list(self._db_path(), int(work_id), user_id, group_ids,
                                             channel_ids=channel_ids)
        if err:
            return {'success': False, 'error': err}
        info_cache = {}
        for e in entries:
            sb = e.get('saved_by') or ''
            if sb and sb not in info_cache:
                info_cache[sb] = enrich_user_info(account_db_path, sb)
            info = info_cache.get(sb, {})
            e['saved_by_display'] = info.get('display_name', sb)
            e['saved_by_avatar'] = info.get('avatar_small')
            e['saved_by_avatar_mime'] = info.get('avatar_mime')
        return {'success': True, 'entries': entries}

    def _handle_history_get(self, data: dict, language: str) -> dict:
        history_id = data.get('history_id')
        if not history_id:
            return {'success': False, 'error': 'missing_history_id'}
        user_id, group_ids, _, _, channel_ids = self._get_user_context()
        entry, err = _db.work_history_get(self._db_path(), int(history_id), user_id, group_ids,
                                          channel_ids=channel_ids)
        if err:
            return {'success': False, 'error': err}
        return {'success': True, 'entry': entry}

    def _handle_command_run(self, data: dict, language: str) -> dict:
        import re
        import shlex
        import shutil
        import subprocess

        command = data.get('command', '').strip()
        if not command:
            return {'success': False, 'error': 'missing_command'}

        overrides = data.get('overrides') or {}

        # Collect all $VAR and ${VAR} references in the command
        var_pattern = re.compile(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)')
        referenced = []
        seen = set()
        for m in var_pattern.finditer(command):
            name = m.group(1) or m.group(2)
            if name not in seen:
                seen.add(name)
                referenced.append(name)

        # Resolve each variable: overrides first, then environment
        undefined = [v for v in referenced if v not in overrides and v not in os.environ]
        if undefined:
            return {'success': False, 'error': 'undefined_vars', 'vars': undefined}

        # Substitute all variables in the command string.
        # shlex.quote wraps each value in single quotes and escapes embedded
        # single quotes, preventing word-splitting and glob expansion.
        def replace_var(m):
            name = m.group(1) or m.group(2)
            value = overrides[name] if name in overrides else os.environ[name]
            return shlex.quote(value)

        resolved = var_pattern.sub(replace_var, command)

        # Prepend skillup-tool dir to PATH if skillup-executor.sh exists there
        skillup_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        executor_dir = os.path.join(skillup_root, 'skillup-tool')
        if os.path.isfile(os.path.join(executor_dir, 'skillup-executor.sh')):
            path_prefix = 'export PATH={}:"$PATH"\n'.format(shlex.quote(executor_dir))
        else:
            path_prefix = ''

        # Script: run the resolved command then wait for a keypress before closing
        script = "{}{}\necho\nread -n 1 -s -r -p 'Press any key to close...'".format(path_prefix, resolved)

        # Terminal emulator probe table: binary -> argv builder
        # Each builder receives the bash script string and returns a Popen argv list.
        # Terminals that accept '-- bash -c' can pass the script directly;
        # those that require a single -e string get it shell-quoted.
        terminals = [
            ('gnome-terminal', lambda s: ['gnome-terminal', '--', 'bash', '-c', s]),
            ('konsole',        lambda s: ['konsole', '-e', 'bash', '-c', s]),
            ('xfce4-terminal', lambda s: ['xfce4-terminal', '-e', 'bash -c ' + shlex.quote(s)]),
            ('mate-terminal',  lambda s: ['mate-terminal', '-e', 'bash -c ' + shlex.quote(s)]),
            ('lxterminal',     lambda s: ['lxterminal', '-e', 'bash -c ' + shlex.quote(s)]),
            ('x-terminal-emulator', lambda s: ['x-terminal-emulator', '-e', 'bash', '-c', s]),
            ('xterm',          lambda s: ['xterm', '-e', 'bash', '-c', s]),
        ]

        for binary, build_argv in terminals:
            if shutil.which(binary):
                argv = build_argv(script)
                subprocess.Popen(
                    argv,
                    start_new_session=True,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return {'success': True}

        return {'success': False, 'error': 'no_terminal'}


    # ------------------------------------------------------------------
    # Link handlers
    # ------------------------------------------------------------------

    def _handle_account_list(self, data: dict, language: str) -> dict:
        account_db_path = self._get_account_db_path()
        accounts = list_accounts(account_db_path)
        return {'success': True, 'accounts': accounts}

    def _handle_work_get_titles(self, data: dict, language: str) -> dict:
        ids = data.get('ids', [])
        if not isinstance(ids, list):
            return {'success': False, 'error': 'invalid_ids'}
        ids = [int(i) for i in ids if str(i).isdigit() or (isinstance(i, int) and i > 0)]
        if not ids:
            return {'success': True, 'items': []}
        user_id, group_ids, _, _, channel_ids = self._get_user_context()
        items = _db.work_get_titles(self._db_path(), ids, user_id, group_ids,
                                    channel_ids=channel_ids)
        return {'success': True, 'items': items}

    def _handle_link_list(self, data: dict, language: str) -> dict:
        work_id = data.get('id')
        if not work_id:
            return {'success': False, 'error': 'missing_id'}
        user_id, group_ids, account_db_path, _, channel_ids = self._get_user_context()
        items, err = _db.link_list(self._db_path(), int(work_id), user_id, group_ids,
                                   channel_ids=channel_ids)
        if err:
            return {'success': False, 'error': err}
        items = self._enrich_items(items, user_id, account_db_path)
        return {'success': True, 'items': items}

    def _handle_link_add(self, data: dict, language: str) -> dict:
        work_id = data.get('id')
        linked_id = data.get('linked_id')
        if not work_id or not linked_id:
            return {'success': False, 'error': 'missing_id'}
        user_id, group_ids, _, _, channel_ids = self._get_user_context()
        return _db.link_add(self._db_path(), int(work_id), int(linked_id), user_id, group_ids,
                            action_history_limit=self._action_history_limit(),
                            channel_ids=channel_ids)

    def _handle_link_remove(self, data: dict, language: str) -> dict:
        work_id = data.get('id')
        linked_id = data.get('linked_id')
        if not work_id or not linked_id:
            return {'success': False, 'error': 'missing_id'}
        user_id, group_ids, _, _, channel_ids = self._get_user_context()
        return _db.link_remove(self._db_path(), int(work_id), int(linked_id), user_id, group_ids,
                               action_history_limit=self._action_history_limit(),
                               channel_ids=channel_ids)

    def _handle_action_log_list(self, data: dict, language: str) -> dict:
        user_id = get_current_user_id()
        limit = self._action_history_limit()
        items = _db.action_log_list(self._db_path(), user_id, limit)
        return {'success': True, 'items': items}

    def _handle_search_history_load(self, data: dict, language: str) -> dict:
        config = self.load_config(CONFIG_DEFAULTS)
        raw = config.get('workhub.search_history', '[]')
        try:
            items = json.loads(raw)
            if not isinstance(items, list):
                items = []
        except (ValueError, TypeError):
            items = []
        return {'success': True, 'items': items}

    def _handle_search_history_save(self, data: dict, language: str) -> dict:
        items = data.get('items')
        if not isinstance(items, list):
            return {'success': False, 'error': 'invalid_items'}
        items = [str(x) for x in items if isinstance(x, str)][:64]
        config = self.load_config(CONFIG_DEFAULTS)
        config['workhub.search_history'] = json.dumps(items, ensure_ascii=False)
        self.save_config(config)
        return {'success': True}

    def _handle_sticky_load(self, data: dict, language: str) -> dict:
        config = self.load_config(CONFIG_DEFAULTS)
        raw = config.get('workhub.sticky_ids', '[]')
        try:
            items = json.loads(raw)
            if not isinstance(items, list):
                items = []
            items = [x for x in items if isinstance(x, int)]
        except (ValueError, TypeError):
            items = []
        return {'success': True, 'items': items}

    def _handle_sticky_save(self, data: dict, language: str) -> dict:
        items = data.get('items')
        if not isinstance(items, list):
            return {'success': False, 'error': 'invalid_items'}
        items = [x for x in items if isinstance(x, int)]
        config = self.load_config(CONFIG_DEFAULTS)
        config['workhub.sticky_ids'] = json.dumps(items, ensure_ascii=False)
        self.save_config(config)
        return {'success': True}

    def _handle_link_resolve(self, data: dict, language: str) -> dict:
        target_id = data.get('target_id')
        if not target_id:
            return {'success': False, 'error': 'missing_id'}
        user_id, group_ids, account_db_path, _, channel_ids = self._get_user_context()
        item, err = _db.link_resolve(self._db_path(), int(target_id), user_id, group_ids,
                                     channel_ids=channel_ids)
        if err:
            return {'success': False, 'error': err}
        item['is_owner'] = (item.get('owner_id') == user_id)
        if not item['is_owner']:
            info = enrich_user_info(account_db_path, item.get('owner_id', ''))
            item['owner_display_name'] = info.get('display_name', item.get('owner_id', ''))
            item['owner_avatar_small'] = info.get('avatar_small')
            item['owner_avatar_mime'] = info.get('avatar_mime')
        return {'success': True, 'item': item}


    # ------------------------------------------------------------------
    # Channel handlers
    # ------------------------------------------------------------------

    def _handle_channel_list(self, data: dict, language: str) -> dict:
        user_id, group_ids, account_db_path, groups, _ = self._get_user_context()
        group_names = [g['name'] for g in groups]
        channels = _db.channel_list(self._db_path(), user_id, group_ids, group_names=group_names)
        return {'success': True, 'channels': channels}

    def _handle_channel_create(self, data: dict, language: str) -> dict:
        name = (data.get('name') or '').strip()
        if not name:
            return {'success': False, 'error': 'missing_name'}
        user_id = get_current_user_id()
        return _db.channel_create(self._db_path(), name, user_id)

    def _handle_channel_get(self, data: dict, language: str) -> dict:
        channel_id = data.get('channel_id')
        if not channel_id:
            return {'success': False, 'error': 'missing_id'}
        user_id, group_ids, account_db_path, groups, _ = self._get_user_context()
        group_names = [g['name'] for g in groups]
        result = _db.channel_get(self._db_path(), channel_id, user_id, group_ids,
                                 group_names=group_names)
        if not result.get('success'):
            return result
        # Enrich user member display names
        members = result.get('members', [])
        enriched = []
        for m in members:
            entry = dict(m)
            if m['member_type'] == 'user':
                info = enrich_user_info(account_db_path, m['member_id'])
                entry['display_name'] = info.get('display_name', m['member_id'])
                entry['avatar_small'] = info.get('avatar_small')
                entry['avatar_mime'] = info.get('avatar_mime')
            else:
                # Group: use member_id as display; no avatar
                entry['display_name'] = m['member_id']
                entry['avatar_small'] = None
                entry['avatar_mime'] = None
            enriched.append(entry)
        # Enrich group names using account DB
        all_groups = _group_mod.list_groups(account_db_path)
        group_name_map = {g['id']: g['name'] for g in all_groups}
        for entry in enriched:
            if entry['member_type'] == 'group':
                entry['display_name'] = group_name_map.get(entry['member_id'], entry['member_id'])
        result['members'] = enriched
        return result

    def _handle_channel_update(self, data: dict, language: str) -> dict:
        channel_id = data.get('channel_id')
        name = (data.get('name') or '').strip()
        if not channel_id or not name:
            return {'success': False, 'error': 'missing_params'}
        user_id = get_current_user_id()
        return _db.channel_update(self._db_path(), channel_id, user_id, name)

    def _handle_channel_member_add(self, data: dict, language: str) -> dict:
        channel_id = data.get('channel_id')
        member_type = data.get('member_type')
        member_id = (data.get('member_id') or '').strip()
        if not channel_id or not member_type or not member_id:
            return {'success': False, 'error': 'missing_params'}
        user_id = get_current_user_id()
        if member_type == 'group':
            # member_id may be a group name; resolve to UUID
            account_db_path = self._get_account_db_path()
            all_groups = _group_mod.list_groups(account_db_path)
            matched = [g for g in all_groups if g['name'] == member_id or g['id'] == member_id]
            if not matched:
                return {'success': False, 'error': 'group_not_found'}
            member_id = matched[0]['id']
        return _db.channel_member_add(self._db_path(), channel_id, user_id, member_type, member_id)

    def _handle_channel_member_remove(self, data: dict, language: str) -> dict:
        channel_id = data.get('channel_id')
        member_type = data.get('member_type')
        member_id = (data.get('member_id') or '').strip()
        if not channel_id or not member_type or not member_id:
            return {'success': False, 'error': 'missing_params'}
        user_id = get_current_user_id()
        return _db.channel_member_remove(self._db_path(), channel_id, user_id, member_type, member_id)

    def _handle_channel_delete(self, data: dict, language: str) -> dict:
        channel_id = data.get('channel_id')
        if not channel_id:
            return {'success': False, 'error': 'missing_params'}
        user_id = get_current_user_id()
        return _db.channel_delete(self._db_path(), channel_id, user_id)

    def _handle_channel_set_admin(self, data: dict, language: str) -> dict:
        channel_id = data.get('channel_id')
        new_admin_id = (data.get('new_admin_id') or '').strip()
        if not channel_id or not new_admin_id:
            return {'success': False, 'error': 'missing_params'}
        user_id = get_current_user_id()
        return _db.channel_set_admin(self._db_path(), channel_id, user_id, new_admin_id)

    def _handle_channel_active_load(self, data: dict, language: str) -> dict:
        config = self.load_config(CONFIG_DEFAULTS)
        channel_id = config.get('workhub.active_channel_id', '') or None
        return {'success': True, 'channel_id': channel_id}

    def _handle_channel_active_save(self, data: dict, language: str) -> dict:
        channel_id = data.get('channel_id') or ''
        config = self.load_config(CONFIG_DEFAULTS)
        config['workhub.active_channel_id'] = channel_id
        self.save_config(config)
        return {'success': True}

    def _handle_group_list_all(self, data: dict, language: str) -> dict:
        account_db_path = self._get_account_db_path()
        groups = _group_mod.list_groups(account_db_path)
        return {'success': True, 'groups': [{'id': g['id'], 'name': g['name']} for g in groups]}


register_app_class(WorkHubApp)
