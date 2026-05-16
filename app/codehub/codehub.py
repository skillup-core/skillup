"""
CodeHub App - SVN-based code management platform.

Usage:
    skillup.py --app:codehub
"""

import os
import sys
from typing import List, Optional, TYPE_CHECKING

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.appmgr import AppContext, register_app_class
from lib.baseapp import BaseApp, BaseAppState

if TYPE_CHECKING:
    from lib.webui import WebUIEngine

# App directory (where bin/svn lives)
_APP_DIR = os.path.dirname(os.path.abspath(__file__))


class CodeHubApp(BaseApp):

    def __init__(self, engine: Optional['WebUIEngine'], context: AppContext):
        super().__init__(engine, context)
        self._db = None
        self._svn = None
        self._account_db_path = ''
        self._current_account = ''

    # ── BaseApp required ─────────────────────────────────────────────────────

    def on_run_cli(self, args: List[str]) -> int:
        print("[codehub] CLI mode not implemented", file=sys.stderr)
        return 0

    # ── desktop init ─────────────────────────────────────────────────────────

    def on_run_desktop_initialize(self) -> int:
        from .db_service import CodeHubDB
        from .svn_service import SvnService, SvnError

        # Load config
        config = self.load_config({
            'codehub.svn_repo_url': '',
            'codehub.svn_checkout_root': '',
            'codehub.db_path': '',
        })

        # Resolve SVN repo URL
        svn_repo_url = config.get('codehub.svn_repo_url', '').strip()

        # Resolve DB path
        db_path = config.get('codehub.db_path', '').strip()
        if not db_path:
            db_path = os.path.join(_APP_DIR, 'data', 'db', 'codehub.db')

        # Resolve checkout root
        checkout_root = config.get('codehub.svn_checkout_root', '').strip()
        if not checkout_root:
            checkout_root = os.path.join(_APP_DIR, 'data', 'svn', 'codehub')
        checkout_root = os.path.expandvars(checkout_root)

        # Account DB from skillup_default_config.ini ([desktop] section)
        from lib.config import load_config, get_desktop_config_path
        desktop_cfg = load_config(get_desktop_config_path(), {
            'general.account_db': '',
        }, app_id='desktop')
        self._account_db_path = desktop_cfg.get('general.account_db', '')
        if self._account_db_path:
            self._account_db_path = os.path.expanduser(self._account_db_path)

        # Get current logged-in account
        self._current_account = self._get_current_account()
        self._checkout_root = checkout_root

        # Init DB
        self._db = CodeHubDB(db_path)
        self._db.init_schema()

        # Init SVN service (may be empty string if not configured yet)
        bin_dir = os.path.join(_APP_DIR, 'bin')
        self._svn_bin_dir = bin_dir
        self._svn_repo_url = svn_repo_url

        if svn_repo_url:
            self._svn = SvnService(bin_dir, svn_repo_url)
            try:
                self._svn.ensure_repo()
            except SvnError as e:
                print(f"[warn ] SVN repo init failed: {e}", file=sys.stderr)

        # Register handlers
        self.register_handlers({
            'get_init_state':       self._handle_get_init_state,
            'save_svn_repo_url':    self._handle_save_svn_repo_url,
            'list_projects':        self._handle_list_projects,
            'create_project':       self._handle_create_project,
            'get_project':          self._handle_get_project,
            'delete_project':       self._handle_delete_project,
            'list_accounts':        self._handle_list_accounts,
            'get_workdir_tree':     self._handle_get_workdir_tree,
            'read_local_file':      self._handle_read_local_file,
            'svn_cat':              self._handle_svn_cat,
            'svn_log':              self._handle_svn_log,
            'get_changed_files':    self._handle_get_changed_files,
            'revert_file':          self._handle_revert_file,
            'revert_all':           self._handle_revert_all,
            'get_revision_detail':  self._handle_get_revision_detail,
            'list_at_revision':     self._handle_list_at_revision,
            'rollback':             self._handle_rollback,
            'deploy':               self._handle_deploy,
            'toggle_favorite':      self._handle_toggle_favorite,
            'set_members':          self._handle_set_members,
            'open_terminal':        self._handle_open_terminal,
            'add_file':             self._handle_add_file,
            'open_in_skillbot':     self._handle_open_in_skillbot,
            'get_revision_state':   self._handle_get_revision_state,
            'preview_update':       self._handle_preview_update,
            'apply_update':         self._handle_apply_update,
            'update_description':   self._handle_update_description,
            'transfer_owner':       self._handle_transfer_owner,
            'list_orphan_dirs':     self._handle_list_orphan_dirs,
            'delete_orphan_dirs':   self._handle_delete_orphan_dirs,
            'dismiss_orphan_dirs':  self._handle_dismiss_orphan_dirs,
        })

        return 0

    # ── helpers ──────────────────────────────────────────────────────────────

    def _get_current_account(self) -> str:
        """Return current logged-in account id (= $USER by convention)."""
        try:
            import sqlite3
            if not self._account_db_path or not os.path.exists(self._account_db_path):
                # Fallback: use system user
                return os.environ.get('USER', '')
            conn = sqlite3.connect(self._account_db_path, timeout=5)
            # Use the system user name to look up account
            user = os.environ.get('USER', '')
            row = conn.execute(
                "SELECT id FROM accounts WHERE id = ? AND activated = 1 LIMIT 1",
                (user,)
            ).fetchone()
            conn.close()
            return row[0] if row else user
        except Exception:
            return os.environ.get('USER', '')

    def _require_svn(self):
        if self._svn is None:
            raise ValueError("SVN repo URL not configured")

    def _project_checkout_path(self, owner: str, project: str) -> str:
        return os.path.join(self._checkout_root, owner, project)

    # ── handlers ─────────────────────────────────────────────────────────────

    def _handle_get_init_state(self, data: dict, language: str) -> dict:
        from desktop.account import list_accounts
        accounts = list_accounts(self._account_db_path) if self._account_db_path else []
        return {
            'success': True,
            'svn_configured': bool(self._svn_repo_url),
            'svn_repo_url': self._svn_repo_url,
            'current_account': self._current_account,
            'accounts': accounts,
        }

    def _handle_save_svn_repo_url(self, data: dict, language: str) -> dict:
        from .svn_service import SvnService, SvnError
        url = data.get('url', '').strip()
        if not url:
            return {'success': False, 'error': 'URL is required'}

        current = self.load_config({
            'codehub.svn_repo_url': '',
            'codehub.svn_checkout_root': '',
            'codehub.db_path': '',
        })
        current['codehub.svn_repo_url'] = url
        self.save_config(current)
        self._svn_repo_url = url
        self._svn = SvnService(self._svn_bin_dir, url)
        try:
            self._svn.ensure_repo()
        except SvnError as e:
            return {'success': False, 'error': str(e)}
        return {'success': True}

    def _handle_list_projects(self, data: dict, language: str) -> dict:
        search = data.get('search', '')
        section = data.get('section', 'all')  # 'master' | 'member' | 'all'
        limit = int(data.get('limit', 20))
        page = max(1, int(data.get('page', 1)))
        offset = (page - 1) * limit
        account = self._current_account

        try:
            if section == 'master':
                result = self._db.list_projects_by_owner(account, search, limit, offset)
            elif section == 'member':
                result = self._db.list_projects_by_member(account, search, limit, offset)
            else:
                result = self._db.list_projects(search, limit, offset)

            projects = result['projects']
            total = result['total']

            # Annotate favorite status from config
            favorites = self._get_favorites()
            for p in projects:
                p['favorited'] = p['id'] in favorites

            return {'success': True, 'projects': projects, 'total': total, 'page': page, 'limit': limit}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _handle_create_project(self, data: dict, language: str) -> dict:
        from .svn_service import SvnError
        import re

        name = data.get('name', '').strip()
        description = data.get('description', '').strip()
        members = data.get('members', [])
        owner = self._current_account

        if not name:
            return {'success': False, 'error': 'Project name is required'}
        if not re.match(r'^[A-Za-z0-9_\-]+$', name):
            return {'success': False, 'error': 'Name must be alphanumeric, hyphens, underscores only'}
        if not owner:
            return {'success': False, 'error': 'Not logged in'}

        # Check duplicate
        existing = self._db.get_project_by_owner_name(owner, name)
        if existing:
            return {'success': False, 'error': 'Project already exists'}

        try:
            self._require_svn()
            self._svn.create_project(owner, name, f'create project {name}')
        except (SvnError, ValueError) as e:
            return {'success': False, 'error': str(e)}

        project_id = self._db.create_project(name, owner, description, members)
        return {'success': True, 'project_id': project_id}

    def _handle_get_project(self, data: dict, language: str) -> dict:
        from desktop.account import list_accounts
        project_id = data.get('project_id')
        if project_id is None:
            return {'success': False, 'error': 'project_id required'}
        project = self._db.get_project(int(project_id))
        if project is None:
            return {'success': False, 'error': 'Not found'}
        account = self._current_account
        project['favorited'] = project['id'] in self._get_favorites()
        project['starred'] = self._db.is_starred(project['id'], account)
        project['is_master'] = (account == project['owner_account'])
        project['is_member'] = (account in project['members'])
        project['workdir'] = self._project_checkout_path(
            project['owner_account'], project['name']
        )
        # Enrich owner and member info for UI display
        all_accounts = {a['id']: a for a in (list_accounts(self._account_db_path) if self._account_db_path else [])}
        owner_id = project['owner_account']
        owner_info = all_accounts.get(owner_id, {'id': owner_id, 'display_name': owner_id, 'avatar_small': None, 'avatar_mime': 'image/jpeg'})
        project['owner_info'] = owner_info
        project['members_info'] = [
            all_accounts.get(m, {'id': m, 'display_name': m, 'avatar_small': None, 'avatar_mime': 'image/jpeg'})
            for m in project['members']
        ]
        return {'success': True, 'project': project}

    def _handle_delete_project(self, data: dict, language: str) -> dict:
        from .svn_service import SvnError
        project_id = data.get('project_id')
        if project_id is None:
            return {'success': False, 'error': 'project_id required'}

        project = self._db.get_project(int(project_id))
        if project is None:
            return {'success': False, 'error': 'Not found'}
        if self._current_account != project['owner_account']:
            return {'success': False, 'error': 'Permission denied'}

        try:
            self._require_svn()
            self._svn.delete_project(project['owner_account'], project['name'])
        except (SvnError, ValueError) as e:
            return {'success': False, 'error': str(e)}

        self._db.delete_project(int(project_id))
        return {'success': True}

    def _handle_list_accounts(self, data: dict, language: str) -> dict:
        from desktop.account import list_accounts
        accounts = list_accounts(self._account_db_path) if self._account_db_path else []
        return {'success': True, 'accounts': accounts}

    def _handle_get_workdir_tree(self, data: dict, language: str) -> dict:
        from .svn_service import SvnError
        project_id = data.get('project_id')
        rel_path = data.get('path', '')

        project = self._db.get_project(int(project_id))
        if project is None:
            return {'success': False, 'error': 'Not found'}
        try:
            self._require_svn()
            local_path = self._project_checkout_path(
                project['owner_account'], project['name']
            )
            # Ensure working copy exists (do NOT update — local changes must be preserved)
            self._svn.checkout_if_missing(project['owner_account'], project['name'], local_path)
            entries = self._svn.get_workdir_tree(local_path, rel_path)
            return {'success': True, 'entries': entries, 'local_path': local_path}
        except (SvnError, ValueError) as e:
            return {'success': False, 'error': str(e)}

    def _handle_read_local_file(self, data: dict, language: str) -> dict:
        import base64
        project_id = data.get('project_id')
        rel_path = data.get('path', '').lstrip('/')

        project = self._db.get_project(int(project_id))
        if project is None:
            return {'success': False, 'error': 'Not found'}

        local_path = self._project_checkout_path(project['owner_account'], project['name'])
        full_path = os.path.normpath(os.path.join(local_path, rel_path))
        if not full_path.startswith(os.path.normpath(local_path) + os.sep):
            return {'success': False, 'error': 'Access denied'}
        if not os.path.isfile(full_path):
            return {'success': False, 'error': 'File not found'}

        try:
            with open(full_path, 'rb') as f:
                content_bytes = f.read()
            try:
                return {'success': True, 'content': content_bytes.decode('utf-8'), 'encoding': 'utf8'}
            except UnicodeDecodeError:
                return {'success': True, 'content': base64.b64encode(content_bytes).decode('ascii'), 'encoding': 'base64'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _handle_svn_cat(self, data: dict, language: str) -> dict:
        from .svn_service import SvnError
        import base64
        project_id = data.get('project_id')
        path = data.get('path', '')
        revision = data.get('revision', 'HEAD')

        project = self._db.get_project(int(project_id))
        if project is None:
            return {'success': False, 'error': 'Not found'}
        try:
            self._require_svn()
            content_bytes = self._svn.cat_file(
                project['owner_account'], project['name'], path, revision
            )
            # Try to decode as text; fall back to base64 for binary
            try:
                content_text = content_bytes.decode('utf-8')
                return {'success': True, 'content': content_text, 'encoding': 'utf8'}
            except UnicodeDecodeError:
                return {
                    'success': True,
                    'content': base64.b64encode(content_bytes).decode('ascii'),
                    'encoding': 'base64'
                }
        except (SvnError, ValueError) as e:
            return {'success': False, 'error': str(e)}

    def _handle_svn_log(self, data: dict, language: str) -> dict:
        from .svn_service import SvnError
        project_id = data.get('project_id')
        limit = int(data.get('limit', 50))

        project = self._db.get_project(int(project_id))
        if project is None:
            return {'success': False, 'error': 'Not found'}
        try:
            self._require_svn()
            entries = self._svn.log(project['owner_account'], project['name'], limit)
            return {'success': True, 'entries': entries}
        except (SvnError, ValueError) as e:
            return {'success': False, 'error': str(e)}

    def _handle_get_changed_files(self, data: dict, language: str) -> dict:
        from .svn_service import SvnError
        project_id = data.get('project_id')
        project = self._db.get_project(int(project_id))
        if project is None:
            return {'success': False, 'error': 'Not found'}
        try:
            self._require_svn()
            local_path = self._project_checkout_path(
                project['owner_account'], project['name']
            )
            files = self._svn.get_changed_files(local_path)
            return {'success': True, 'files': files}
        except (SvnError, ValueError) as e:
            return {'success': False, 'error': str(e)}

    def _handle_revert_file(self, data: dict, language: str) -> dict:
        from .svn_service import SvnError
        project_id = data.get('project_id')
        rel_path   = data.get('path', '').lstrip('/')
        if not rel_path:
            return {'success': False, 'error': 'path required'}
        project = self._db.get_project(int(project_id))
        if project is None:
            return {'success': False, 'error': 'Not found'}
        account = self._current_account
        if account != project['owner_account'] and account not in project['members']:
            return {'success': False, 'error': 'Permission denied'}
        try:
            self._require_svn()
            local_path = self._project_checkout_path(
                project['owner_account'], project['name']
            )
            self._svn.revert_file(local_path, rel_path)
            return {'success': True}
        except (SvnError, ValueError) as e:
            return {'success': False, 'error': str(e)}

    def _handle_revert_all(self, data: dict, language: str) -> dict:
        from .svn_service import SvnError
        project_id = data.get('project_id')
        project = self._db.get_project(int(project_id))
        if project is None:
            return {'success': False, 'error': 'Not found'}
        account = self._current_account
        if account != project['owner_account'] and account not in project['members']:
            return {'success': False, 'error': 'Permission denied'}
        try:
            self._require_svn()
            local_path = self._project_checkout_path(
                project['owner_account'], project['name']
            )
            self._svn.revert_all(local_path)
            return {'success': True}
        except (SvnError, ValueError) as e:
            return {'success': False, 'error': str(e)}

    def _handle_get_revision_detail(self, data: dict, language: str) -> dict:
        from .svn_service import SvnError
        project_id = data.get('project_id')
        revision   = str(data.get('revision', ''))
        if not revision:
            return {'success': False, 'error': 'revision required'}
        project = self._db.get_project(int(project_id))
        if project is None:
            return {'success': False, 'error': 'Not found'}
        try:
            self._require_svn()
            detail = self._svn.get_revision_detail(
                project['owner_account'], project['name'], revision
            )
            return {'success': True, 'detail': detail}
        except (SvnError, ValueError) as e:
            return {'success': False, 'error': str(e)}

    def _handle_list_at_revision(self, data: dict, language: str) -> dict:
        from .svn_service import SvnError
        project_id = data.get('project_id')
        path       = data.get('path', '')
        revision   = str(data.get('revision', 'HEAD'))
        project = self._db.get_project(int(project_id))
        if project is None:
            return {'success': False, 'error': 'Not found'}
        try:
            self._require_svn()
            entries = self._svn.list_at_revision(
                project['owner_account'], project['name'], path, revision
            )
            return {'success': True, 'entries': entries}
        except (SvnError, ValueError) as e:
            return {'success': False, 'error': str(e)}

    def _handle_rollback(self, data: dict, language: str) -> dict:
        from .svn_service import SvnError
        project_id = data.get('project_id')
        revision   = str(data.get('revision', ''))
        if not revision:
            return {'success': False, 'error': 'revision required'}
        project = self._db.get_project(int(project_id))
        if project is None:
            return {'success': False, 'error': 'Not found'}
        account = self._current_account
        if account != project['owner_account']:
            return {'success': False, 'error': 'Permission denied'}
        try:
            self._require_svn()
            local_path = self._project_checkout_path(
                project['owner_account'], project['name']
            )
            new_rev = self._svn.rollback(
                project['owner_account'], project['name'], local_path, revision
            )
            return {'success': True, 'revision': new_rev}
        except SvnError as e:
            err = str(e)
            if err == 'working_copy_dirty':
                msg = '변경된 내용이 있어 롤백할 수 없습니다.' if language == 'ko' else 'Cannot rollback: working copy has uncommitted changes.'
                return {'success': False, 'error': msg}
            return {'success': False, 'error': err}
        except ValueError as e:
            return {'success': False, 'error': str(e)}

    def _handle_deploy(self, data: dict, language: str) -> dict:
        from .svn_service import SvnError
        project_id = data.get('project_id')
        message = data.get('message', '').strip() or 'deploy'

        project = self._db.get_project(int(project_id))
        if project is None:
            return {'success': False, 'error': 'Not found'}

        account = self._current_account
        is_master = (account == project['owner_account'])
        is_member = (account in project['members'])
        if not (is_master or is_member):
            return {'success': False, 'error': 'Permission denied'}

        try:
            self._require_svn()
            local_path = self._project_checkout_path(
                project['owner_account'], project['name']
            )
            state = self._svn.get_revision_state(local_path)
            if state['wc_revision'] < state['head_revision']:
                return {
                    'success': False,
                    'error': 'behind_head',
                    'wc_revision': state['wc_revision'],
                    'head_revision': state['head_revision'],
                }
            revision = self._svn.deploy(local_path, message)
            self._db.update_last_deployed_at(int(project_id))
            return {'success': True, 'revision': revision}
        except (SvnError, ValueError) as e:
            return {'success': False, 'error': str(e)}

    def _handle_get_revision_state(self, data: dict, language: str) -> dict:
        from .svn_service import SvnError
        project_id = data.get('project_id')
        project = self._db.get_project(int(project_id))
        if project is None:
            return {'success': False, 'error': 'Not found'}
        account = self._current_account
        if account != project['owner_account'] and account not in project['members']:
            return {'success': False, 'error': 'Permission denied'}
        try:
            self._require_svn()
            local_path = self._project_checkout_path(
                project['owner_account'], project['name']
            )
            state = self._svn.get_revision_state(local_path)
            return {'success': True, **state}
        except (SvnError, ValueError) as e:
            return {'success': False, 'error': str(e)}

    def _handle_preview_update(self, data: dict, language: str) -> dict:
        from .svn_service import SvnError
        project_id = data.get('project_id')
        project = self._db.get_project(int(project_id))
        if project is None:
            return {'success': False, 'error': 'Not found'}
        account = self._current_account
        if account != project['owner_account'] and account not in project['members']:
            return {'success': False, 'error': 'Permission denied'}
        try:
            self._require_svn()
            local_path = self._project_checkout_path(
                project['owner_account'], project['name']
            )
            result = self._svn.preview_update(local_path)
            return {'success': True, **result}
        except (SvnError, ValueError) as e:
            return {'success': False, 'error': str(e)}

    def _handle_apply_update(self, data: dict, language: str) -> dict:
        from .svn_service import SvnError
        project_id = data.get('project_id')
        resolutions = data.get('resolutions', {})
        project = self._db.get_project(int(project_id))
        if project is None:
            return {'success': False, 'error': 'Not found'}
        account = self._current_account
        if account != project['owner_account'] and account not in project['members']:
            return {'success': False, 'error': 'Permission denied'}
        try:
            self._require_svn()
            local_path = self._project_checkout_path(
                project['owner_account'], project['name']
            )
            result = self._svn.apply_update(local_path, resolutions)
            return {'success': True, **result}
        except (SvnError, ValueError) as e:
            return {'success': False, 'error': str(e)}

    def _get_favorites(self) -> set:
        cfg = self.load_config({'codehub.favorites': ''})
        raw = cfg.get('codehub.favorites', '').strip()
        if not raw:
            return set()
        return set(int(x) for x in raw.split(',') if x.strip().isdigit())

    def _set_favorites(self, favorites: set):
        cfg = self.load_config({'codehub.favorites': ''})
        cfg['codehub.favorites'] = ','.join(str(x) for x in sorted(favorites))
        self.save_config(cfg)

    def _handle_toggle_favorite(self, data: dict, language: str) -> dict:
        project_id = data.get('project_id')
        if project_id is None:
            return {'success': False, 'error': 'project_id required'}
        pid = int(project_id)
        account = self._current_account

        # DB star toggle (shown in project sidebar as star_count)
        starred = self._db.toggle_star(pid, account)
        project = self._db.get_project(pid)
        star_count = project['star_count'] if project else 0

        # Local config favorite toggle (used by project list section headers)
        favorites = self._get_favorites()
        if starred:
            favorites.add(pid)
        else:
            favorites.discard(pid)
        self._set_favorites(favorites)

        return {'success': True, 'favorited': starred, 'starred': starred, 'star_count': star_count}

    def _handle_update_description(self, data: dict, language: str) -> dict:
        project_id = data.get('project_id')
        description = data.get('description', '').strip()
        if project_id is None:
            return {'success': False, 'error': 'project_id required'}
        project = self._db.get_project(int(project_id))
        if project is None:
            return {'success': False, 'error': 'Not found'}
        if self._current_account != project['owner_account']:
            return {'success': False, 'error': 'Permission denied'}
        self._db.update_description(int(project_id), description)
        return {'success': True}

    def _handle_set_members(self, data: dict, language: str) -> dict:
        project_id = data.get('project_id')
        members = data.get('members', [])

        project = self._db.get_project(int(project_id))
        if project is None:
            return {'success': False, 'error': 'Not found'}
        if self._current_account != project['owner_account']:
            return {'success': False, 'error': 'Permission denied'}

        self._db.set_members(int(project_id), members)
        return {'success': True}

    def _handle_transfer_owner(self, data: dict, language: str) -> dict:
        import shutil
        from .svn_service import SvnError
        project_id = data.get('project_id')
        new_owner = data.get('new_owner', '').strip()
        force = data.get('force', False)
        if not project_id or not new_owner:
            return {'success': False, 'error': 'project_id and new_owner required'}
        project = self._db.get_project(int(project_id))
        if project is None:
            return {'success': False, 'error': 'Not found'}
        if self._current_account != project['owner_account']:
            return {'success': False, 'error': 'Permission denied'}
        if new_owner not in project['members']:
            return {'success': False, 'error': 'New owner must be a member'}
        old_owner = project['owner_account']
        name = project['name']
        old_checkout = self._project_checkout_path(old_owner, name)
        # Check for local changes
        if self._svn and os.path.isdir(old_checkout):
            try:
                changed = self._svn.get_changed_files(old_checkout)
            except SvnError:
                changed = []
            if changed and not force:
                return {'success': False, 'error': 'has_changes'}
            if changed:
                try:
                    self._svn.revert_all(old_checkout)
                except SvnError as e:
                    return {'success': False, 'error': str(e)}
        # Move SVN repo path
        if self._svn:
            try:
                self._svn.move_project(old_owner, name, new_owner)
            except SvnError as e:
                return {'success': False, 'error': str(e)}
        # Replace local checkout: svn relocate cannot retarget within the same repo
        # to a different path, so discard the old WC and re-checkout from the new URL.
        new_checkout = self._project_checkout_path(new_owner, name)
        for path in (old_checkout, new_checkout):
            if os.path.isdir(path):
                shutil.rmtree(path)
        if self._svn:
            try:
                self._svn.checkout_if_missing(new_owner, name, new_checkout)
            except Exception:
                pass
        # Update DB
        self._db.transfer_owner(int(project_id), old_owner, new_owner)
        return {'success': True}

    def _handle_add_file(self, data: dict, language: str) -> dict:
        """Explicitly svn add a single unregistered file."""
        from .svn_service import SvnError
        project_id = data.get('project_id')
        rel_path   = data.get('path', '').lstrip('/')
        if not rel_path:
            return {'success': False, 'error': 'path required'}
        project = self._db.get_project(int(project_id))
        if project is None:
            return {'success': False, 'error': 'Not found'}
        account = self._current_account
        if account != project['owner_account'] and account not in project['members']:
            return {'success': False, 'error': 'Permission denied'}
        try:
            self._require_svn()
            local_path = self._project_checkout_path(
                project['owner_account'], project['name']
            )
            full_path = os.path.join(local_path, rel_path)
            self._svn._run([self._svn.svn, 'add', '--parents', '--force', full_path])
            return {'success': True}
        except (SvnError, ValueError) as e:
            return {'success': False, 'error': str(e)}

    def _handle_open_terminal(self, data: dict, language: str) -> dict:
        import shutil
        import subprocess

        workdir = data.get('workdir', '')
        if not workdir or not os.path.isdir(workdir):
            return {'success': False, 'error': 'Directory not found: ' + workdir}

        # Ordered preference: detect first available terminal
        candidates = [
            ('gnome-terminal', ['gnome-terminal', '--working-directory={workdir}']),
            ('konsole',        ['konsole', '--workdir', '{workdir}']),
            ('xfce4-terminal', ['xfce4-terminal', '--working-directory={workdir}']),
            ('tilix',          ['tilix', '--working-directory={workdir}']),
            ('lxterminal',     ['lxterminal', '--working-directory={workdir}']),
            ('kitty',          ['kitty', '--directory={workdir}']),
            ('alacritty',      ['alacritty', '--working-directory', '{workdir}']),
            ('xterm',          ['xterm', '-e', 'bash -c "cd {workdir}; exec bash"']),
        ]

        cmd = None
        for name, template in candidates:
            if shutil.which(name):
                cmd = [part.replace('{workdir}', workdir) for part in template]
                break

        if cmd is None:
            return {'success': False, 'error': 'No supported terminal emulator found'}

        try:
            # Detach from parent process so the terminal survives skillup exit.
            # start_new_session=True creates a new process group.
            subprocess.Popen(
                cmd,
                cwd=workdir,
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _handle_open_in_skillbot(self, data: dict, language: str) -> dict:
        from lib.config import get_app_config_path, load_config, save_config

        workdir = data.get('workdir', '')
        if not workdir or not os.path.isdir(workdir):
            return {'success': False, 'error': 'Directory not found: ' + workdir}

        skillbot_config_path = get_app_config_path('sk1llb0t', app_id_name='skillbot')
        try:
            config = load_config(skillbot_config_path, app_id='sk1llb0t')
            config['pending.open_dir'] = workdir
            save_config(skillbot_config_path, config)
        except Exception as e:
            return {'success': False, 'error': str(e)}

        return {'success': True}


    def _orphan_dismiss_until(self) -> float:
        """Return the stored dismiss-until timestamp (epoch seconds), or 0."""
        cfg = self.load_config({'codehub.orphan_dismiss_until': ''})
        raw = cfg.get('codehub.orphan_dismiss_until', '').strip()
        try:
            return float(raw) if raw else 0.0
        except ValueError:
            return 0.0

    def _handle_list_orphan_dirs(self, data: dict, language: str) -> dict:
        """Scan checkout_root for directories not in DB. Respects dismiss period."""
        import time
        if time.time() < self._orphan_dismiss_until():
            return {'success': True, 'orphans': []}
        orphans = []
        root = self._checkout_root
        if not os.path.isdir(root):
            return {'success': True, 'orphans': []}
        try:
            for owner in sorted(os.listdir(root)):
                owner_dir = os.path.join(root, owner)
                if not os.path.isdir(owner_dir):
                    continue
                for project in sorted(os.listdir(owner_dir)):
                    proj_dir = os.path.join(owner_dir, project)
                    if not os.path.isdir(proj_dir):
                        continue
                    if self._db.get_project_by_owner_name(owner, project) is None:
                        orphans.append({'owner': owner, 'name': project, 'path': proj_dir})
        except Exception as e:
            return {'success': False, 'error': str(e)}
        return {'success': True, 'orphans': orphans}

    def _handle_dismiss_orphan_dirs(self, data: dict, language: str) -> dict:
        """Store dismiss-until = now + 7 days."""
        import time
        until = time.time() + 7 * 24 * 3600
        cfg = self.load_config({'codehub.orphan_dismiss_until': ''})
        cfg['codehub.orphan_dismiss_until'] = str(until)
        self.save_config(cfg)
        return {'success': True}

    def _handle_delete_orphan_dirs(self, data: dict, language: str) -> dict:
        """Delete all orphan checkout directories (re-scanned server-side)."""
        import shutil
        root = self._checkout_root
        root_norm = os.path.normpath(root) + os.sep
        if not os.path.isdir(root):
            return {'success': True, 'deleted': [], 'failed': []}
        deleted = []
        failed = []
        try:
            for owner in sorted(os.listdir(root)):
                owner_dir = os.path.join(root, owner)
                if not os.path.isdir(owner_dir):
                    continue
                for project in sorted(os.listdir(owner_dir)):
                    proj_dir = os.path.normpath(os.path.join(owner_dir, project))
                    if not proj_dir.startswith(root_norm):
                        continue
                    if not os.path.isdir(proj_dir):
                        continue
                    if self._db.get_project_by_owner_name(owner, project) is None:
                        try:
                            shutil.rmtree(proj_dir)
                            deleted.append(owner + '/' + project)
                        except Exception as e:
                            failed.append({'path': owner + '/' + project, 'error': str(e)})
                # Remove empty owner dir
                try:
                    if os.path.isdir(owner_dir) and not os.listdir(owner_dir):
                        os.rmdir(owner_dir)
                except Exception:
                    pass
        except Exception as e:
            return {'success': False, 'error': str(e)}
        return {'success': True, 'deleted': deleted, 'failed': failed}


register_app_class(CodeHubApp)
