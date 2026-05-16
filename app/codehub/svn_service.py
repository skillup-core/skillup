"""
CodeHub SVN service - wraps svn/svnadmin subprocess calls.
All SVN operations use the statically built binary at bin/svn.
"""

import os
import re
import subprocess
import xml.etree.ElementTree as ET
from typing import List, Optional, Dict, Tuple

# ── file classification constants ─────────────────────────────────────────────

# Directories whose names match these patterns are hidden from the file list
# and excluded from svn add/commit.  Patterns are matched against the bare
# directory name (case-sensitive).
CODEHUB_HIDE_DIRNAMES: List[str] = [
    r'^__pycache__$',
    r'^\.git$',
    r'^\.svn$',
    r'^node_modules$',
    r'^\.idea$',
    r'^\.vscode$',
    r'^\.mypy_cache$',
    r'^\.pytest_cache$',
    r'^\.tox$',
    r'^dist$',
    r'^build$',
    r'^\.eggs$',
    r'^\.cache$',
    r'^target$',        # Java/Rust build output
    r'^__MACOSX$',
]

# Files whose extensions (or full names) match these patterns are hidden from
# the file list and excluded from svn add/commit.  Patterns are matched against
# the bare filename (case-sensitive).
CODEHUB_HIDE_EXTENSIONS: List[str] = [
    r'\.pyc$',
    r'\.pyo$',
    r'\.pyd$',
    r'\.class$',
    r'\.o$',
    r'\.obj$',
    r'\.a$',
    r'\.so(\.[0-9]+)*$',
    r'\.lo$',
    r'\.la$',
    r'\.al$',
    r'\.dll$',
    r'\.exe$',
    r'\.dylib$',
    r'\.rej$',
    r'~$',
    r'\.swp$',
    r'\.swo$',
    r'^#.*#$',          # Emacs lock files
    r'^\.\#',           # Emacs lock files
    r'\.DS_Store$',
    r'[Tt]humbs\.db$',
    r'\.coverage$',
    r'\.egg-info$',
]

# Extensions that are always considered "known" (safe to track automatically).
# Files NOT in this set are shown with status 'unregistered' and require manual
# "추가하기" to be included in svn add.
CODEHUB_KNOWN_EXTENSIONS: set = {
    # source code
    'c', 'cc', 'cpp', 'cxx', 'c++', 'h', 'hh', 'hpp', 'hxx',
    'py', 'pyi', 'pyw',
    'java', 'kt', 'kts', 'scala', 'groovy',
    'js', 'mjs', 'cjs', 'ts', 'tsx', 'jsx',
    'go', 'rs', 'swift', 'rb', 'pl', 'pm', 'lua', 'r', 'jl',
    'cs', 'vb', 'fs', 'fsx',
    'php', 'php3', 'php4', 'php5', 'phtml',
    'sh', 'bash', 'zsh', 'fish', 'ksh', 'csh', 'tcsh', 'bat', 'cmd', 'ps1',
    'asm', 's', 'il', 'skill', 'ils',
    'm', 'mm',          # Objective-C / MATLAB
    'ex', 'exs',        # Elixir
    'erl', 'hrl',       # Erlang
    'hs', 'lhs',        # Haskell
    'ml', 'mli',        # OCaml
    'clj', 'cljs',      # Clojure
    'lisp', 'el',       # Lisp / Emacs Lisp
    'vim', 'vimrc',
    # web
    'html', 'htm', 'xhtml',
    'css', 'scss', 'sass', 'less',
    'xml', 'xsl', 'xslt', 'xsd', 'wsdl',
    'json', 'jsonc', 'json5',
    'yaml', 'yml',
    'toml', 'ini', 'cfg', 'conf', 'config', 'properties',
    'env',
    # docs / text
    'md', 'markdown', 'rst', 'txt', 'text',
    'tex', 'bib',
    'adoc', 'asciidoc',
    'csv', 'tsv',
    'log',
    # images (always tracked)
    'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp',
    'svg', 'svgz',
    'ico', 'cur',
    'tif', 'tiff',
    'psd', 'ai', 'eps',
    # data / misc  (db/sqlite/lock excluded: they change frequently and are not suitable for VCS)
    'sql',
    'proto', 'thrift', 'avro',
    'dockerfile', 'makefile', 'cmake',
    'gradle', 'pom',
    'editorconfig', 'gitignore', 'gitattributes', 'svnignore',
    'htaccess',
}

# Files larger than this byte size are treated as 'unregistered' even if their
# extension is known.  Prevents accidentally committing large binaries or data dumps.
CODEHUB_TRACK_MAX_BYTES: int = 10 * 1024 * 1024  # 10 MB

_hide_dir_patterns  = [re.compile(p) for p in CODEHUB_HIDE_DIRNAMES]
_hide_file_patterns = [re.compile(p) for p in CODEHUB_HIDE_EXTENSIONS]


def _is_hidden_dir(name: str) -> bool:
    return any(p.search(name) for p in _hide_dir_patterns)


def _is_hidden_file(name: str) -> bool:
    return any(p.search(name) for p in _hide_file_patterns)


def _exceeds_track_size(abs_path: str) -> bool:
    """Return True if the file is larger than CODEHUB_TRACK_MAX_BYTES."""
    try:
        return os.path.getsize(abs_path) > CODEHUB_TRACK_MAX_BYTES
    except OSError:
        return False


def _is_known_extension(name: str) -> bool:
    """Return True if the file has a known (auto-trackable) extension."""
    lower = name.lower()
    # Match dotfiles with no extension (e.g. .gitignore, Makefile)
    if lower.startswith('.') and '.' not in lower[1:]:
        return True
    ext = lower.rsplit('.', 1)[-1] if '.' in lower else ''
    # Bare names without extension (Makefile, Dockerfile, etc.)
    if not ext or lower == ext:
        return lower in CODEHUB_KNOWN_EXTENSIONS
    return ext in CODEHUB_KNOWN_EXTENSIONS


class SvnError(Exception):
    pass


class SvnService:
    def __init__(self, bin_dir: str, repo_url: str):
        """
        Args:
            bin_dir: Directory containing svn and svnadmin binaries.
            repo_url: Base SVN repo URL, e.g. file:///path/to/codehub
        """
        self.svn = os.path.join(bin_dir, 'svn')
        self.svnadmin = os.path.join(bin_dir, 'svnadmin')
        self.repo_url = repo_url.rstrip('/')

    # ── internal helpers ────────────────────────────────────────────────────

    def _run(self, cmd: List[str], input_data: Optional[bytes] = None) -> str:
        try:
            result = subprocess.run(
                cmd,
                input=input_data,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60
            )
            if result.returncode != 0:
                raise SvnError(result.stderr.decode('utf-8', errors='replace').strip())
            return result.stdout.decode('utf-8', errors='replace')
        except subprocess.TimeoutExpired:
            raise SvnError("SVN command timed out")
        except FileNotFoundError:
            raise SvnError(f"SVN binary not found: {cmd[0]}")

    def _run_bytes(self, cmd: List[str]) -> bytes:
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60
            )
            if result.returncode != 0:
                raise SvnError(result.stderr.decode('utf-8', errors='replace').strip())
            return result.stdout
        except subprocess.TimeoutExpired:
            raise SvnError("SVN command timed out")
        except FileNotFoundError:
            raise SvnError(f"SVN binary not found: {cmd[0]}")

    def _project_url(self, owner: str, project: str) -> str:
        return f"{self.repo_url}/{owner}/{project}"

    # ── repo bootstrap ───────────────────────────────────────────────────────

    def ensure_repo(self):
        """Create the SVN repo if it does not exist (file:// only)."""
        if not self.repo_url.startswith('file://'):
            return
        repo_path = self.repo_url[7:]  # strip file://
        if not os.path.isdir(repo_path):
            os.makedirs(os.path.dirname(repo_path), exist_ok=True)
            self._run([self.svnadmin, 'create', repo_path])

    # ── project operations ───────────────────────────────────────────────────

    def create_project(self, owner: str, project: str, message: str = 'init'):
        """Create owner/project directory in the SVN repo."""
        url = self._project_url(owner, project)
        self._run([
            self.svn, 'mkdir', '--parents', '-m', message, url
        ])

    def delete_project(self, owner: str, project: str, message: str = 'delete project'):
        url = self._project_url(owner, project)
        self._run([self.svn, 'delete', '-m', message, url])

    def _svn_exists(self, url: str) -> bool:
        try:
            self._run([self.svn, 'info', url])
            return True
        except Exception:
            return False

    def move_project(self, old_owner: str, project: str, new_owner: str,
                     message: str = 'transfer owner'):
        """Move owner/project to new_owner/project in the SVN repo."""
        src_url = self._project_url(old_owner, project)
        dst_url = self._project_url(new_owner, project)
        # Already at destination — nothing to move
        if not self._svn_exists(src_url) and self._svn_exists(dst_url):
            return
        # Ensure new_owner directory exists
        owner_url = f"{self.repo_url}/{new_owner}"
        if not self._svn_exists(owner_url):
            self._run([self.svn, 'mkdir', '--parents', '-m', f'create {new_owner}', owner_url])
        self._run([self.svn, 'move', '-m', message, src_url, dst_url])

    # ── file browsing ────────────────────────────────────────────────────────

    def list_path(self, owner: str, project: str,
                  path: str = '', revision: str = 'HEAD') -> List[Dict]:
        """Return directory listing at path@revision."""
        base = self._project_url(owner, project)
        url = f"{base}/{path}".rstrip('/') + '@' + revision if path else f"{base}@{revision}"
        xml_output = self._run([self.svn, 'list', '--xml', url])
        return self._parse_list_xml(xml_output)

    def _parse_list_xml(self, xml_str: str) -> List[Dict]:
        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError as e:
            raise SvnError(f"Failed to parse svn list output: {e}")
        entries = []
        for entry in root.findall('.//entry'):
            kind = entry.get('kind', 'file')
            name_el = entry.find('name')
            size_el = entry.find('size')
            commit_el = entry.find('commit')
            date_el = entry.find('commit/date') if commit_el is not None else None
            author_el = entry.find('commit/author') if commit_el is not None else None
            rev = commit_el.get('revision') if commit_el is not None else ''
            entries.append({
                'name': name_el.text if name_el is not None else '',
                'kind': kind,
                'size': int(size_el.text) if size_el is not None else 0,
                'revision': rev,
                'date': date_el.text if date_el is not None else '',
                'author': author_el.text if author_el is not None else '',
            })
        return entries

    def cat_file(self, owner: str, project: str,
                 path: str, revision: str = 'HEAD') -> bytes:
        """Return raw bytes of a file at path@revision."""
        base = self._project_url(owner, project)
        url = f"{base}/{path}@{revision}"
        return self._run_bytes([self.svn, 'cat', url])

    # ── log / revisions ──────────────────────────────────────────────────────

    def log(self, owner: str, project: str, limit: int = 50) -> List[Dict]:
        """Return commit log entries."""
        url = self._project_url(owner, project)
        xml_output = self._run([
            self.svn, 'log', '--xml', f'--limit={limit}', url
        ])
        return self._parse_log_xml(xml_output)

    def _parse_log_xml(self, xml_str: str) -> List[Dict]:
        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError as e:
            raise SvnError(f"Failed to parse svn log output: {e}")
        entries = []
        for entry in root.findall('logentry'):
            author_el = entry.find('author')
            date_el = entry.find('date')
            msg_el = entry.find('msg')
            entries.append({
                'revision': entry.get('revision', ''),
                'author': author_el.text if author_el is not None else '',
                'date': date_el.text if date_el is not None else '',
                'message': msg_el.text if msg_el is not None else '',
            })
        return entries

    def get_revision_detail(self, owner: str, project: str, revision: str) -> Dict:
        """Return detail for a single revision: author, date, message, changed_paths."""
        url = self._project_url(owner, project)
        xml_output = self._run([
            self.svn, 'log', '--xml', '-v', f'-r{revision}', url
        ])
        try:
            root = ET.fromstring(xml_output)
        except ET.ParseError as e:
            raise SvnError(f"Failed to parse svn log output: {e}")
        entry = root.find('logentry')
        if entry is None:
            raise SvnError(f"Revision {revision} not found")
        author_el = entry.find('author')
        date_el   = entry.find('date')
        msg_el    = entry.find('msg')
        paths = []
        # Strip the leading /owner/project/ prefix from paths
        prefix = f"/{owner}/{project}/"
        for p in entry.findall('.//path'):
            raw = p.text or ''
            rel = raw[len(prefix):] if raw.startswith(prefix) else raw
            paths.append({'path': rel, 'action': p.get('action', '')})
        return {
            'revision': entry.get('revision', ''),
            'author':   author_el.text if author_el is not None else '',
            'date':     date_el.text   if date_el   is not None else '',
            'message':  msg_el.text    if msg_el    is not None else '',
            'paths':    paths,
        }

    def list_at_revision(self, owner: str, project: str,
                         path: str, revision: str) -> List[Dict]:
        """List directory contents at a specific revision (read-only, no working copy)."""
        return self.list_path(owner, project, path, revision)

    def rollback(self, owner: str, project: str, local_path: str,
                 revision: str) -> str:
        """
        Roll back to revision: merge HEAD..REV-1 into working copy then commit.
        Raises SvnError if working copy has local changes.
        Returns new revision string.
        """
        # Refuse if working copy has uncommitted changes
        xml_output = self._run([self.svn, 'status', '--xml', local_path])
        status_map = self._parse_status_xml(xml_output)
        dirty = [p for p, s in status_map.items() if s != 'unmodified']
        if dirty:
            raise SvnError('working_copy_dirty')

        url = self._project_url(owner, project)
        # Get current HEAD revision number
        info_xml = self._run([self.svn, 'info', '--xml', url])
        try:
            info_root = ET.fromstring(info_xml)
        except ET.ParseError as e:
            raise SvnError(f"Failed to parse svn info: {e}")
        rev_el = info_root.find('.//commit')
        head_rev = int(rev_el.get('revision', '0')) if rev_el is not None else 0
        target_rev = int(revision)
        if target_rev >= head_rev:
            raise SvnError(f"Already at or beyond revision {revision}")

        # Update working copy to HEAD first to resolve mixed-revision state,
        # then merge backwards to target revision.
        self._run([self.svn, 'update', local_path])
        self._run([
            self.svn, 'merge', '-r', f'{head_rev}:{target_rev - 1}', url, local_path
        ])

        message = f'Rollback to revision {revision}'
        output = self._run([self.svn, 'commit', '-m', message, local_path])
        for line in output.splitlines():
            if 'Committed revision' in line:
                parts = line.strip().rstrip('.').split()
                if parts:
                    return parts[-1]
        return ''

    def revert_file(self, local_path: str, rel_path: str):
        """Revert a single file/dir to its last committed state (svn revert)."""
        full_path = os.path.join(local_path, rel_path)
        self._run([self.svn, 'revert', '--depth', 'infinity', full_path])

    def revert_all(self, local_path: str):
        """Revert all local changes in the working copy (svn revert -R)."""
        self._run([self.svn, 'revert', '-R', local_path])

    # ── checkout / update / commit ───────────────────────────────────────────

    def checkout(self, owner: str, project: str, local_path: str,
                 revision: str = 'HEAD'):
        """Checkout or update project to local_path at revision."""
        url = self._project_url(owner, project)
        if os.path.isdir(os.path.join(local_path, '.svn')):
            self._run([self.svn, 'update', '-r', revision, local_path])
        else:
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            self._run([self.svn, 'checkout', '-r', revision, url, local_path])

    def checkout_if_missing(self, owner: str, project: str, local_path: str):
        """Checkout project to local_path only if working copy does not exist yet."""
        if not os.path.isdir(os.path.join(local_path, '.svn')):
            url = self._project_url(owner, project)
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            self._run([self.svn, 'checkout', url, local_path])

    def get_workdir_tree(self, local_path: str, rel_path: str = '') -> List[Dict]:
        """
        Return entries under local_path/rel_path combining FS listing and
        svn status.  Each entry has:
          name, kind ('file'|'dir'), status ('unmodified'|'modified'|
          'added'|'deleted'|'untracked'|'missing')
        """
        scan_dir = os.path.join(local_path, rel_path) if rel_path else local_path

        # Build status map from svn status --xml (keyed by absolute path).
        # global-ignores patterns (e.g. __pycache__) are intentionally excluded.
        status_map: Dict[str, str] = {}
        try:
            xml_output = self._run([self.svn, 'status', '--xml', scan_dir])
            status_map = self._parse_status_xml(xml_output)
        except SvnError:
            pass

        # If scan_dir itself (or an ancestor within local_path) is untracked/added,
        # every child inherits that status because svn won't report them individually.
        inherited_status: Optional[str] = None
        if rel_path:
            # Walk from local_path toward scan_dir checking each ancestor
            parts = rel_path.split('/')
            for i in range(len(parts)):
                ancestor = os.path.join(local_path, *parts[:i + 1])
                s = status_map.get(ancestor)
                if s in ('untracked', 'added'):
                    inherited_status = 'untracked'
                    break

        # Enumerate local filesystem entries
        entries: List[Dict] = []
        if os.path.isdir(scan_dir):
            for name in sorted(os.listdir(scan_dir)):
                if name == '.svn':
                    continue
                full = os.path.join(scan_dir, name)
                kind = 'dir' if os.path.isdir(full) else 'file'
                # Skip hidden dirs/files entirely
                if kind == 'dir' and _is_hidden_dir(name):
                    continue
                if kind == 'file' and _is_hidden_file(name):
                    continue
                if inherited_status:
                    svn_status = inherited_status
                else:
                    svn_status = status_map.get(full, 'unmodified')
                # Untracked files with unknown extension or exceeding size limit are 'unregistered'
                if svn_status == 'untracked' and kind == 'file':
                    if not _is_known_extension(name) or _exceeds_track_size(full):
                        svn_status = 'unregistered'
                entries.append({'name': name, 'kind': kind, 'status': svn_status})

        # Add 'missing' entries (svn-tracked but deleted from disk)
        for abs_path, svn_status in status_map.items():
            if svn_status == 'missing' and os.path.dirname(abs_path) == scan_dir:
                name = os.path.basename(abs_path)
                entries.append({'name': name, 'kind': 'file', 'status': 'missing'})

        entries.sort(key=lambda e: (0 if e['kind'] == 'dir' else 1, e['name']))
        return entries

    def _parse_status_xml(self, xml_str: str) -> Dict[str, str]:
        """Parse svn status --xml output into {abs_path: status_str}."""
        item_map = {
            'normal': 'unmodified',
            'modified': 'modified',
            'added': 'added',
            'deleted': 'deleted',
            'missing': 'missing',
            'unversioned': 'untracked',
            'ignored': None,
            'obstructed': 'modified',
            'conflicted': 'modified',
            'replaced': 'modified',
        }
        result: Dict[str, str] = {}
        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError:
            return result
        for entry in root.findall('.//entry'):
            path = entry.get('path', '')
            wc = entry.find('wc-status')
            if wc is None:
                continue
            item = wc.get('item', '')
            mapped = item_map.get(item)
            if mapped is not None:
                result[path] = mapped
        return result

    def get_changed_files(self, local_path: str) -> List[Dict]:
        """
        Return a flat list of changed files under local_path.
        Each entry: {path: str (relative), status: str}
        Only non-unmodified entries are included.
        Untracked directories are expanded recursively (svn doesn't list their contents).
        """
        xml_output = self._run([self.svn, 'status', '--xml', local_path])
        status_map = self._parse_status_xml(xml_output)
        result = []
        for abs_path, status in sorted(status_map.items()):
            if status == 'unmodified':
                continue
            name = os.path.basename(abs_path)
            # Skip hidden dirs/files
            if os.path.isdir(abs_path) and _is_hidden_dir(name):
                continue
            if not os.path.isdir(abs_path) and _is_hidden_file(name):
                continue
            try:
                rel = os.path.relpath(abs_path, local_path)
            except ValueError:
                rel = abs_path
            if status == 'untracked' and os.path.isdir(abs_path):
                # Expand untracked directory: list all files inside recursively
                for root, dirs, files in os.walk(abs_path):
                    dirs[:] = [d for d in sorted(dirs) if d != '.svn' and not _is_hidden_dir(d)]
                    for fname in sorted(files):
                        if _is_hidden_file(fname):
                            continue
                        fpath = os.path.join(root, fname)
                        try:
                            frel = os.path.relpath(fpath, local_path)
                        except ValueError:
                            frel = fpath
                        if _is_known_extension(fname) and not _exceeds_track_size(fpath):
                            fstatus = 'untracked'
                        else:
                            fstatus = 'unregistered'
                        result.append({'path': frel, 'status': fstatus})
            else:
                if status == 'untracked':
                    if not _is_known_extension(name) or _exceeds_track_size(abs_path):
                        status = 'unregistered'
                result.append({'path': rel, 'status': status})
        return result

    def get_revision_state(self, local_path: str) -> Dict:
        """
        Return {'wc_revision': int, 'head_revision': int} for the working copy.
        wc_revision: the revision the WC is currently checked out at.
        head_revision: the latest revision of the project in the SVN repo.
        """
        info_xml = self._run([self.svn, 'info', '--xml', local_path])
        try:
            root = ET.fromstring(info_xml)
        except ET.ParseError as e:
            raise SvnError(f"Failed to parse svn info: {e}")
        entry = root.find('.//entry')
        if entry is None:
            raise SvnError("svn info returned no entry")
        wc_revision = int(entry.get('revision', '0'))
        url_el = entry.find('url')
        if url_el is None or not url_el.text:
            raise SvnError("svn info returned no URL")
        repo_url = url_el.text

        head_xml = self._run([self.svn, 'info', '--xml', repo_url])
        try:
            head_root = ET.fromstring(head_xml)
        except ET.ParseError as e:
            raise SvnError(f"Failed to parse svn info (head): {e}")
        head_commit = head_root.find('.//commit')
        if head_commit is None:
            raise SvnError("svn info (head) returned no commit element")
        head_revision = int(head_commit.get('revision', '0'))
        return {'wc_revision': wc_revision, 'head_revision': head_revision}

    def preview_update(self, local_path: str) -> Dict:
        """
        Preview what an update would do WITHOUT touching the WC.

        Returns:
            {
                'wc_revision': int,
                'head_revision': int,
                'potential_conflicts': [
                    {
                        'path': str (relative),
                        'mine': str | None   (local file content, utf-8 or None if binary),
                        'theirs': str | None (repo HEAD content, utf-8 or None if binary),
                    }
                ]
            }
        """
        # 1. Get WC revision and repo URL
        info_xml = self._run([self.svn, 'info', '--xml', local_path])
        try:
            root = ET.fromstring(info_xml)
        except ET.ParseError as e:
            raise SvnError(f"Failed to parse svn info: {e}")
        entry = root.find('.//entry')
        if entry is None:
            raise SvnError("svn info returned no entry")
        wc_revision = int(entry.get('revision', '0'))
        url_el = entry.find('url')
        if url_el is None or not url_el.text:
            raise SvnError("svn info returned no URL")
        repo_url = url_el.text

        # 2. Get HEAD revision
        head_xml = self._run([self.svn, 'info', '--xml', repo_url])
        try:
            head_root = ET.fromstring(head_xml)
        except ET.ParseError as e:
            raise SvnError(f"Failed to parse svn info (head): {e}")
        head_commit = head_root.find('.//commit')
        if head_commit is None:
            raise SvnError("svn info (head) returned no commit element")
        head_revision = int(head_commit.get('revision', '0'))

        if wc_revision >= head_revision:
            return {'wc_revision': wc_revision, 'head_revision': head_revision, 'potential_conflicts': []}

        # 3. Files changed in repo since WC revision
        log_xml = self._run([
            self.svn, 'log', '--xml', '-v',
            f'-r{wc_revision + 1}:{head_revision}', repo_url
        ])
        try:
            log_root = ET.fromstring(log_xml)
        except ET.ParseError as e:
            raise SvnError(f"Failed to parse svn log: {e}")

        # Strip /owner/project/ prefix to get relative paths
        # repo_url is like file:///...../owner/project, so split on last two segments
        url_parts = repo_url.rstrip('/').split('/')
        prefix = '/' + '/'.join(url_parts[-2:]) + '/'  # e.g. /work/my-project/

        repo_changed: set = set()
        for path_el in log_root.findall('.//path'):
            raw = path_el.text or ''
            kind = path_el.get('kind', 'file')
            if kind != 'file':
                continue
            if raw.startswith(prefix):
                repo_changed.add(raw[len(prefix):])

        if not repo_changed:
            return {'wc_revision': wc_revision, 'head_revision': head_revision, 'potential_conflicts': []}

        # 4. Locally modified files
        status_xml = self._run([self.svn, 'status', '--xml', local_path])
        status_map = self._parse_status_xml(status_xml)
        local_modified: set = set()
        for abs_path, status in status_map.items():
            if status in ('modified', 'added'):
                try:
                    rel = os.path.relpath(abs_path, local_path)
                except ValueError:
                    rel = abs_path
                local_modified.add(rel)

        # 5. Intersection = potential conflicts
        conflict_paths = repo_changed & local_modified

        potential_conflicts = []
        for rel_path in sorted(conflict_paths):
            abs_path = os.path.join(local_path, rel_path)

            # mine: local file content
            mine_content = None
            if os.path.isfile(abs_path):
                try:
                    with open(abs_path, 'rb') as f:
                        raw = f.read()
                    mine_content = raw.decode('utf-8')
                except (UnicodeDecodeError, OSError):
                    mine_content = None  # binary

            # theirs: repo HEAD content
            theirs_content = None
            try:
                raw = self._run_bytes([self.svn, 'cat', f'{repo_url}/{rel_path}@HEAD'])
                theirs_content = raw.decode('utf-8')
            except (SvnError, UnicodeDecodeError):
                theirs_content = None  # binary or missing

            potential_conflicts.append({
                'path': rel_path,
                'mine': mine_content,
                'theirs': theirs_content,
            })

        return {
            'wc_revision': wc_revision,
            'head_revision': head_revision,
            'potential_conflicts': potential_conflicts,
        }

    def apply_update(self, local_path: str, resolutions: Dict[str, str]) -> Dict:
        """
        Apply update to the WC.

        resolutions: {rel_path: 'mine-full' | 'theirs-full'}
          - Files listed here are updated with the given --accept option (no sidecars).
          - All other files are updated normally via svn update on the whole WC.

        Returns {'new_revision': int}.
        """
        norm_root = os.path.normpath(local_path)

        # Per-file update with explicit accept for potential conflict files
        # 'keep' -> mine-conflict: attempt auto-merge, keep mine where lines conflict (no sidecars)
        _ACCEPT_MAP = {'keep': 'mine-conflict', 'mine-full': 'mine-full', 'theirs-full': 'theirs-full'}
        for rel_path, accept in resolutions.items():
            svn_accept = _ACCEPT_MAP.get(accept)
            if svn_accept is None:
                raise SvnError(f"Invalid accept value: {accept}")
            abs_path = os.path.normpath(os.path.join(local_path, rel_path))
            if not abs_path.startswith(norm_root + os.sep):
                raise SvnError(f"path escapes local_path: {rel_path}")
            self._run([self.svn, 'update', f'--accept={svn_accept}', abs_path])

        # Update the rest of the WC (non-conflicting files + WC root revision)
        self._run([self.svn, 'update', local_path])

        info_xml = self._run([self.svn, 'info', '--xml', local_path])
        try:
            root = ET.fromstring(info_xml)
        except ET.ParseError as e:
            raise SvnError(f"Failed to parse svn info after update: {e}")
        entry = root.find('.//entry')
        new_revision = int(entry.get('revision', '0')) if entry is not None else 0
        return {'new_revision': new_revision}

    def deploy(self, local_path: str, message: str) -> str:
        """
        Stage all untracked/missing changes and commit the entire working copy.
        Returns the new revision string, or '' if nothing to commit.
        """
        # Add untracked files/dirs
        xml_output = self._run([self.svn, 'status', '--xml', local_path])
        status_map = self._parse_status_xml(xml_output)

        # Hidden and unregistered files are excluded from auto-add.
        # Unregistered files (unknown extension) must be added explicitly by the user.
        def _auto_addable(abs_path: str) -> bool:
            name = os.path.basename(abs_path)
            if os.path.isdir(abs_path):
                return not _is_hidden_dir(name)
            return (not _is_hidden_file(name)
                    and _is_known_extension(name)
                    and not _exceeds_track_size(abs_path))

        to_add = [p for p, s in status_map.items()
                  if s == 'untracked' and _auto_addable(p)]
        to_rm  = [p for p, s in status_map.items() if s == 'missing']

        # Add in sorted order so parent dirs come before children
        for path in sorted(to_add):
            self._run([self.svn, 'add', '--parents', '--force', path])

        for path in sorted(to_rm, reverse=True):
            self._run([self.svn, 'rm', path])

        # Commit — if nothing changed svn exits 0 with no revision line
        output = self._run([self.svn, 'commit', '-m', message, local_path])
        revision = ''
        for line in output.splitlines():
            if 'Committed revision' in line:
                parts = line.strip().rstrip('.').split()
                if parts:
                    revision = parts[-1]
                    break

        # svn commit only bumps per-file revisions; the WC root entry/@revision
        # stays at the last svn update point (mixed-revision WC).  Update now so
        # get_revision_state() returns the correct WC revision on the next call.
        if revision:
            self._run([self.svn, 'update', local_path])

        return revision
