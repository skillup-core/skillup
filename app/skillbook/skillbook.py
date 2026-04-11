"""
SKILL Book App

SKILL function reference viewer for Cadence Virtuoso
Displays SKILL function documentation from searchable database

Usage:
    skillup.py --desktop [--app:skillbook]
    Launches desktop mode with skillbook app or opens skillbook in existing desktop

Link Handling:
    @function_name          Jumps to function by name (internal link)
    ${doc_base}/path/...    Opens external documentation in new Firefox window
                            Uses SKILLBOOK_DOC_BASE environment variable or config

Configuration:
    When using SKILLUP_DEFAULT_CONFIG, define the following in the defaults file:

        [b00k5k1l]
        skillbook.skillbook_db_path = /path/to/skillbook.db
        skillbook.custom_db_path = /path/to/skillbook_custom.db
        skillbook.doc_base = /path/to/doc_base

    skillbook.skillbook_db_path
        Path to the SkillBook SQLite database file containing SKILL function
        documentation. If the file does not exist, an error dialog is shown.
        Default: ${skillbook_app_dir}/data/skillbook.db
        (${skillbook_app_dir} is replaced with the skillbook app directory path)

    skillbook.custom_db_path
        Path to the user-writable SQLite database for favorites and comments.
        Created automatically if it does not exist.
        Default: ${skillbook_app_dir}/data/skillbook_custom.db

    skillbook.doc_base
        Base URL/path for ${doc_base} substitution in function documentation links.
        Example: /cadence/IC618/doc
        Priority (highest to lowest):
        1. SKILLBOOK_DOC_BASE environment variable
        2. skillbook.doc_base config setting
        3. Empty string (links will be disabled)

Environment Variables:
    SKILLBOOK_DOC_BASE      Base URL/path for documentation links (highest priority)
                            Example: export SKILLBOOK_DOC_BASE="/cadence/IC618/doc"
                            Overrides skillbook.doc_base config setting
"""

import sys
import os
import sqlite3
import gzip
import re
import base64
from pathlib import Path

# Add parent directories to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.baseapp import BaseApp
from lib.appmgr import register_app_class
from lib.msgbox import show as msgbox_show
from lib.util import browse_firefox
from lib.config import get_desktop_config
import app.skillbook.custom_db as custom_db
from desktop import account as account_module


def extract_images_from_db(conn: sqlite3.Connection, html_content: str, output_dir: Path = None) -> str:
    """Extract images from database and replace skb-data-image-id with base64 data URIs"""
    cursor = conn.cursor()

    # Find all skb-data-image-id attributes
    img_pattern = r'<img\s+([^>]*skb-data-image-id="(\d+)"[^>]*)>'

    def replace_img(match):
        img_attrs = match.group(1)
        image_id = int(match.group(2))

        # Get image from database
        cursor.execute('SELECT image_data, mime_type FROM images WHERE id = ?', (image_id,))
        row = cursor.fetchone()

        if not row:
            return match.group(0)

        compressed_data, mime_type = row

        # Decompress image data
        image_data = gzip.decompress(compressed_data)

        # Convert to base64 data URI
        import base64
        b64_data = base64.b64encode(image_data).decode('ascii')
        data_uri = f'data:{mime_type};base64,{b64_data}'

        # Replace skb-data-image-id with src
        new_attrs = re.sub(r'skb-data-image-id="\d+"', f'src="{data_uri}"', img_attrs)
        # Remove hardcoded width/height attributes so CSS controls sizing
        new_attrs = re.sub(r'\s*width="\d+"', '', new_attrs)
        new_attrs = re.sub(r'\s*height="\d+"', '', new_attrs)
        return f'<img {new_attrs}>'

    return re.sub(img_pattern, replace_img, html_content)


def get_languages(db_path: str) -> list:
    """Get all available languages from the database"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT id, code, name FROM languages ORDER BY id')
        languages = [{'id': row[0], 'code': row[1], 'name': row[2]} for row in cursor.fetchall()]
        conn.close()
        return languages
    except Exception as e:
        print(f"[error][SkillBook] Failed to load languages: {e}", file=sys.stderr)
        return []


def get_function_data(db_path: str, func_name: str, language_id: int = 1) -> dict:
    """Get all data for a function from the database"""

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get function basic info
    cursor.execute('''
        SELECT id, function_name FROM functions WHERE function_name = ?
    ''', (func_name,))

    func_row = cursor.fetchone()
    if not func_row:
        conn.close()
        return None

    func_id, function_name = func_row

    # Get all signatures for this function
    cursor.execute('''
        SELECT s.signature_text
        FROM function_signatures fs
        JOIN signatures s ON fs.signature_id = s.id
        WHERE fs.function_id = ?
        ORDER BY fs.position
    ''', (func_id,))

    signatures = [row[0] for row in cursor.fetchall()]

    # Get section name for this function
    cursor.execute('''
        SELECT s.name
        FROM function_sections fs
        JOIN sections s ON fs.section_id = s.id
        WHERE fs.function_id = ?
        LIMIT 1
    ''', (func_id,))
    section_row = cursor.fetchone()
    section_name = section_row[0] if section_row else 'NA'

    result = {
        'function_name': function_name,
        'section': section_name,
        'signatures': signatures,
        'description': None,
        'description_format': 'text',
        'example': None,
        'example_format': 'text',
        'arguments': [],
        'returns': [],
        'references': []
    }

    # Get description (prefer requested language, fallback to language_id=1)
    cursor.execute('''
        SELECT d.description, d.format
        FROM function_descriptions fd
        JOIN descriptions d ON fd.description_id = d.id
        JOIN description_types dt ON fd.type_id = dt.id
        WHERE fd.function_id = ? AND dt.type_name = 'description' AND d.language_id = ?
    ''', (func_id, language_id))
    desc_row = cursor.fetchone()
    if not desc_row and language_id != 1:
        cursor.execute('''
            SELECT d.description, d.format
            FROM function_descriptions fd
            JOIN descriptions d ON fd.description_id = d.id
            JOIN description_types dt ON fd.type_id = dt.id
            WHERE fd.function_id = ? AND dt.type_name = 'description' AND d.language_id = 1
        ''', (func_id,))
        desc_row = cursor.fetchone()
    if desc_row:
        result['description'] = desc_row[0]
        result['description_format'] = desc_row[1]

    # Get example (prefer requested language, fallback to language_id=1)
    cursor.execute('''
        SELECT d.description, d.format
        FROM function_descriptions fd
        JOIN descriptions d ON fd.description_id = d.id
        JOIN description_types dt ON fd.type_id = dt.id
        WHERE fd.function_id = ? AND dt.type_name = 'example' AND d.language_id = ?
    ''', (func_id, language_id))
    ex_row = cursor.fetchone()
    if not ex_row and language_id != 1:
        cursor.execute('''
            SELECT d.description, d.format
            FROM function_descriptions fd
            JOIN descriptions d ON fd.description_id = d.id
            JOIN description_types dt ON fd.type_id = dt.id
            WHERE fd.function_id = ? AND dt.type_name = 'example' AND d.language_id = 1
        ''', (func_id,))
        ex_row = cursor.fetchone()
    if ex_row:
        result['example'] = ex_row[0]
        result['example_format'] = ex_row[1]

    # Get arguments with multi-type support
    cursor.execute('''
        SELECT
            a.id,
            a.name,
            fa.position
        FROM function_arguments fa
        JOIN arguments a ON fa.argument_id = a.id
        WHERE fa.function_id = ?
        ORDER BY fa.position
    ''', (func_id,))

    args_rows = cursor.fetchall()
    for row in args_rows:
        arg_id, name, position = row

        # Get argument description: prefer language_id match via argument_descriptions mapping
        arg_desc = None
        arg_format = 'text'
        cursor.execute('''
            SELECT d.description, d.format
            FROM argument_descriptions ad
            JOIN descriptions d ON ad.description_id = d.id
            WHERE ad.argument_id = ? AND d.language_id = ?
        ''', (arg_id, language_id))
        desc_row = cursor.fetchone()
        if not desc_row and language_id != 1:
            # Fallback to language_id=1
            cursor.execute('''
                SELECT d.description, d.format
                FROM argument_descriptions ad
                JOIN descriptions d ON ad.description_id = d.id
                WHERE ad.argument_id = ? AND d.language_id = 1
            ''', (arg_id,))
            desc_row = cursor.fetchone()
        if not desc_row:
            # Final fallback: use description_id directly (old DB compatibility)
            cursor.execute('''
                SELECT d.description, d.format
                FROM arguments a
                JOIN descriptions d ON a.description_id = d.id
                WHERE a.id = ?
            ''', (arg_id,))
            desc_row = cursor.fetchone()
        if desc_row:
            arg_desc, arg_format = desc_row

        # Get all datatypes for this argument
        try:
            cursor.execute('''
                SELECT dt.prefix, dt.internal_name, dt.description
                FROM argument_datatypes ad
                JOIN datatypes dt ON ad.datatype_id = dt.id
                WHERE ad.argument_id = ?
                ORDER BY ad.position
            ''', (arg_id,))
        except:
            cursor.execute('''
                SELECT dt.prefix, dt.internal_name, dt.description
                FROM argument_datatypes ad
                JOIN datatypes dt ON ad.datatype_id = dt.id
                WHERE ad.argument_id = ?
                ORDER BY dt.prefix
            ''', (arg_id,))

        datatypes = cursor.fetchall()
        if datatypes:
            prefixes = [dt[0] for dt in datatypes]
            type_names = [dt[1] for dt in datatypes]
            type_descs = [dt[2] for dt in datatypes]

            result['arguments'].append({
                'name': name,
                'prefixes': prefixes,
                'type_names': type_names,
                'type_descs': type_descs,
                'description': arg_desc,
                'format': arg_format or 'text',
                'position': position
            })
        else:
            result['arguments'].append({
                'name': name,
                'prefixes': ['unknown'],
                'type_names': ['unknown'],
                'type_descs': ['unknown type'],
                'description': arg_desc,
                'format': arg_format or 'text',
                'position': position
            })

    # Get returns (base info without description)
    cursor.execute('''
        SELECT
            r.id,
            r.name,
            dt.prefix,
            dt.internal_name,
            dt.description as type_desc,
            fr.position,
            r.element_types
        FROM function_returns fr
        JOIN returns r ON fr.return_id = r.id
        JOIN datatypes dt ON r.datatype_id = dt.id
        WHERE fr.function_id = ?
        ORDER BY fr.position
    ''', (func_id,))

    for row in cursor.fetchall():
        ret_id, ret_name, ret_prefix, ret_type_name, ret_type_desc, ret_position, ret_element_types = row

        # Get return description: prefer language_id match via return_descriptions mapping
        ret_desc = None
        ret_format = 'text'
        cursor.execute('''
            SELECT d.description, d.format
            FROM return_descriptions rd
            JOIN descriptions d ON rd.description_id = d.id
            WHERE rd.return_id = ? AND d.language_id = ?
        ''', (ret_id, language_id))
        desc_row = cursor.fetchone()
        if not desc_row and language_id != 1:
            cursor.execute('''
                SELECT d.description, d.format
                FROM return_descriptions rd
                JOIN descriptions d ON rd.description_id = d.id
                WHERE rd.return_id = ? AND d.language_id = 1
            ''', (ret_id,))
            desc_row = cursor.fetchone()
        if not desc_row:
            # Final fallback: use description_id directly (old DB compatibility)
            cursor.execute('''
                SELECT d.description, d.format
                FROM returns r
                JOIN descriptions d ON r.description_id = d.id
                WHERE r.id = ?
            ''', (ret_id,))
            desc_row = cursor.fetchone()
        if desc_row:
            ret_desc, ret_format = desc_row

        result['returns'].append({
            'name': ret_name,
            'prefix': ret_prefix,
            'type_name': ret_type_name,
            'type_desc': ret_type_desc,
            'description': ret_desc,
            'format': ret_format or 'text',
            'position': ret_position,
            'element_types': ret_element_types
        })

    # Get references
    cursor.execute('''
        SELECT
            rn.text,
            rn.link,
            fr.position
        FROM function_references fr
        JOIN reference_nodes rn ON fr.reference_node_id = rn.id
        WHERE fr.function_id = ?
        ORDER BY fr.position
    ''', (func_id,))

    for row in cursor.fetchall():
        result['references'].append({
            'name': row[0],
            'link': row[1],
            'position': row[2]
        })

    conn.close()
    return result


def process_links(html_content: str, doc_base: str = '') -> str:
    """Process links in HTML content:
    - @function_name: Convert to internal link (will be handled by JavaScript)
    - ${doc_base}/path/...: Convert to onclick handler that opens Firefox with browse_firefox

    Args:
        html_content: HTML content to process
        doc_base: Base URL/path for ${doc_base} substitution (from config or environment)
    """

    def replace_link(match):
        href = match.group(1)
        content = match.group(2)  # Everything between <a> and </a>, including inner tags

        # Handle @function_name links (internal)
        if href.startswith('@'):
            func_name = href[1:]  # Remove @
            return f'<a href="#" data-jump-to="{func_name}">{content}</a>'

        # Handle ${doc_base}/path/... links (external)
        if '${doc_base}' in href:
            if doc_base:
                # Substitute ${doc_base} with actual value
                full_url = href.replace('${doc_base}', doc_base)
                # Call callPython to open URL with browse_firefox
                escaped_url = full_url.replace('"', '&quot;').replace("'", "&#39;")
                return f'<a href="#" onclick="callPython(\'openUrl\', {{\'url\': \'{escaped_url}\'}}).catch(e => console.error(\'Failed to open URL:\', e)); return false;" target="_blank">{content}</a>'
            else:
                # If SKILLBOOK_DOC_BASE not set, disable the link
                return f'<a href="#" aria-label="SKILLBOOK_DOC_BASE not set" onclick="return false" style="opacity: 0.5; cursor: not-allowed;">{content}</a>'

        # Regular links - pass through
        return match.group(0)

    # Match <a href="...">...content...</a> patterns (including inner HTML tags)
    # Use non-greedy matching and allow any content including nested tags
    pattern = r'<a\s+href=["\']([^"\']+)["\']>(.*?)</a>'
    return re.sub(pattern, replace_link, html_content, flags=re.IGNORECASE | re.DOTALL)


def format_content(content: str, format_type: str, conn: sqlite3.Connection = None, doc_base: str = '') -> str:
    """Format content based on its type

    Args:
        content: Content text to format
        format_type: Type of content ('html' or 'text')
        conn: Optional database connection for image extraction
        doc_base: Base URL/path for ${doc_base} substitution in links
    """
    if not content or content == 'X':
        return '<em>No documentation available</em>'

    if format_type == 'html':
        # HTML content - process images if connection provided
        if conn:
            content = extract_images_from_db(conn, content, None)

        # Process links (@function_name and ${doc_base}/path/...)
        content = process_links(content, doc_base)

        # Inject skb-content-table class on any <table> tags
        def _add_content_table_class(m):
            attrs = m.group(1) or ''
            cls_match = re.search(r'class=["\']([^"\']*)["\']', attrs, re.IGNORECASE)
            if cls_match:
                existing = cls_match.group(1)
                if 'skb-content-table' not in existing:
                    new_class = f'skb-content-table {existing}'.strip()
                    attrs = attrs[:cls_match.start()] + f'class="{new_class}"' + attrs[cls_match.end():]
            else:
                attrs = f' class="skb-content-table"' + attrs
            return f'<table{attrs}>'
        content = re.sub(r'<table(\s[^>]*)?>',  _add_content_table_class, content, flags=re.IGNORECASE)

        # Convert noborder tables: bullet-list tables to <ul><li>,
        # spacer tables (first col = &nbsp;) to indented divs
        def _noborder_to_list(html):
            table_pat = re.compile(
                r'<table\s[^>]*skb-class-noborder[^>]*>(.*?)</table>',
                re.DOTALL | re.IGNORECASE
            )
            def _is_spacer_cell(c):
                """Check if cell contains only whitespace/&nbsp; (spacer column)"""
                text = re.sub(r'<[^>]+>', '', c)
                text = re.sub(r'&nbsp;|\s+', '', text)
                return not text

            def _is_bullet_or_empty(c):
                text = re.sub(r'<[^>]+>', '', c)
                text = re.sub(r'&nbsp;|\s+', '', text)
                if not text:
                    return True
                if 'skb-class-bullet' in c or '•' in c or 'bullet' in c.lower():
                    return True
                return False

            def replace_table(tm):
                inner = tm.group(1)
                rows = re.findall(r'<tr[^>]*>(.*?)</tr>', inner, re.DOTALL | re.IGNORECASE)
                if not rows:
                    return tm.group(0)

                # Detect if this is a spacer table: all rows have 2+ cells
                # where the first cell is empty/&nbsp; only
                is_spacer_table = True
                has_bullet = False
                for row in rows:
                    cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL | re.IGNORECASE)
                    if len(cells) >= 2 and _is_spacer_cell(cells[0]):
                        pass  # spacer row
                    else:
                        is_spacer_table = False
                    if any('skb-class-bullet' in c or '•' in c for c in cells):
                        has_bullet = True

                # Spacer table: extract content cells as indented block
                if is_spacer_table and not has_bullet:
                    parts = []
                    for row in rows:
                        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL | re.IGNORECASE)
                        # Take all non-spacer cells
                        content_cells = [c.strip() for c in cells if not _is_spacer_cell(c)]
                        if content_cells:
                            parts.append(''.join(content_cells))
                    if parts:
                        return '<div class="skb-indented">' + ''.join(parts) + '</div>'
                    return tm.group(0)

                # Bullet-list table: convert to <ul><li>
                items = []
                for row in rows:
                    cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL | re.IGNORECASE)
                    text_cells = [c.strip() for c in cells if not _is_bullet_or_empty(c)]
                    if text_cells:
                        items.append(f'<li>{"".join(text_cells)}</li>')
                    elif len(cells) == 1:
                        items.append(f'<li>{cells[0].strip()}</li>')
                if items:
                    return '<ul class="skb-bullet-list">' + ''.join(items) + '</ul>'
                return tm.group(0)
            return table_pat.sub(replace_table, html)

        content = _noborder_to_list(content)

        # Convert spacer tables where td has skb-class-noborder but table tag doesn't
        # These are tables like: <table><tr><td class="skb-class-noborder">&nbsp;</td><td class="skb-class-noborder">content</td></tr></table>
        def _spacer_table_to_div(html):
            # Match tables that contain td elements with skb-class-noborder
            table_pat = re.compile(
                r'<table[^>]*>((?:(?!</table>).)*?<td[^>]*skb-class-noborder[^>]*>(?:(?!</table>).)*?)</table>',
                re.DOTALL | re.IGNORECASE
            )
            def replace_spacer(tm):
                inner = tm.group(1)
                rows = re.findall(r'<tr[^>]*>(.*?)</tr>', inner, re.DOTALL | re.IGNORECASE)
                if not rows:
                    return tm.group(0)

                # Verify all rows have spacer pattern
                all_spacer = True
                parts = []
                for row in rows:
                    cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL | re.IGNORECASE)
                    if len(cells) < 2:
                        all_spacer = False
                        break
                    # Check if first cell is spacer (only &nbsp; / whitespace)
                    first_text = re.sub(r'<[^>]+>', '', cells[0])
                    first_text = re.sub(r'&nbsp;|\s+', '', first_text)
                    if first_text:
                        all_spacer = False
                        break
                    # Collect content from non-spacer cells
                    for c in cells[1:]:
                        c_text = re.sub(r'<[^>]+>', '', c)
                        c_text = re.sub(r'&nbsp;|\s+', '', c_text)
                        if c_text:
                            parts.append(c.strip())

                if all_spacer and parts:
                    return '<div class="skb-indented">' + ''.join(parts) + '</div>'
                return tm.group(0)

            return table_pat.sub(replace_spacer, html)

        content = _spacer_table_to_div(content)

        # Remove <ul><table bgcolor> wrappers
        # For single-cell tables (1 tr, 1 td): unwrap both <ul> and <table> (layout wrapper)
        # For multi-cell tables: only remove <ul>, preserve table structure
        def _unwrap_ul_table(html):
            pat = re.compile(
                r'<ul>\s*(<table[^>]*bgcolor[^>]*>((?:(?!</table>).)*?)</table>)\s*</ul>',
                re.DOTALL | re.IGNORECASE
            )
            def replace_ul_table(m):
                full_table = m.group(1)
                inner = m.group(2)
                trs = re.findall(r'<tr[^>]*>', inner, re.IGNORECASE)
                tds = re.findall(r'<td[^>]*>', inner, re.IGNORECASE)
                if len(trs) == 1 and len(tds) == 1:
                    # Single-cell: unwrap table entirely
                    td_match = re.search(r'<td[^>]*>(.*?)</td>', inner, re.DOTALL | re.IGNORECASE)
                    if td_match:
                        return f'<div>{td_match.group(1)}</div>'
                # Multi-cell: just remove <ul> wrapper
                return full_table
            return pat.sub(replace_ul_table, html)

        content = _unwrap_ul_table(content)

        # Remove single-cell colspan wrapper tables
        def _unwrap_colspan_table(html):
            pat = re.compile(
                r'<table[^>]*>\s*<tr[^>]*>\s*<td[^>]*colspan="2"[^>]*>(.*?)</td>\s*</tr>\s*</table>',
                re.DOTALL | re.IGNORECASE
            )
            return pat.sub(r'<div>\1</div>', html)

        content = _unwrap_colspan_table(content)
        return content
    else:
        # Plain text: return as-is, let JavaScript handle HTML wrapping
        # This avoids double-processing since JavaScript also calls formatContent()
        return content





HISTORY_MAX = 20


class SkillbookApp(BaseApp):
    """SKILL Book app for Skillup - function reference viewer"""

    def __init__(self, engine, context):
        super().__init__(engine, context)
        self.db_path = None
        self.custom_db_path = None
        self.doc_base = ''
        self.function_names = []
        self.function_names_set = set()
        self.languages = []
        self.sections = []
        self.function_names_by_section = {}
        self.conn = None
        self._history_path = None  # Set after data dir is known
        self._current_user = os.environ.get('USER', 'user')

    def _resolve_path(self, path: str) -> str:
        """
        Resolve path variables:
        - ${skillbook_app_dir}: Replace with skillbook app directory path

        Args:
            path: Path string potentially containing ${skillbook_app_dir}

        Returns:
            Resolved absolute path
        """
        app_dir = str(Path(__file__).parent)
        return path.replace('${skillbook_app_dir}', app_dir)

    def _load_data(self) -> bool:
        """Load database and doc_base. Returns True if successful"""
        try:
            # Get skillbook_db_path, doc_base, and language from config
            config = self.load_config({
                'skillbook.skillbook_db_path': '${skillbook_app_dir}/data/skillbook.db',
                'skillbook.custom_db_path': '${skillbook_app_dir}/data/skillbook_custom.db',
                'skillbook.doc_base': '',
                'skillbook.language': '1',
            })

            # Resolve path variables (${skillbook_app_dir} -> actual path)
            db_path_template = config.get('skillbook.skillbook_db_path')
            self.db_path = self._resolve_path(db_path_template)

            custom_db_path_template = config.get('skillbook.custom_db_path')
            self.custom_db_path = self._resolve_path(custom_db_path_template)

            # Load doc_base from config or environment variable
            # Priority: SKILLBOOK_DOC_BASE env var > skillbook.doc_base config > empty string
            env_doc_base = os.environ.get('SKILLBOOK_DOC_BASE', '')
            config_doc_base = config.get('skillbook.doc_base', '')
            self.doc_base = env_doc_base or config_doc_base

            # Check if database exists
            if not Path(self.db_path).exists():
                print(f"[error][SkillBook] Database not found: {self.db_path}", file=sys.stderr)
                msgbox_show(
                    {"en": "SkillBook Database Error", "ko": "SkillBook 데이터베이스 오류"},
                    {"en": f"Database file not found:\n{self.db_path}\n\nPlease check the skillbook.skillbook_db_path configuration.",
                     "ko": f"데이터베이스 파일을 찾을 수 없습니다:\n{self.db_path}\n\nskillbook.skillbook_db_path 설정을 확인하세요."}
                )
                return False

            # Load languages
            self.languages = get_languages(self.db_path)
            if not self.languages:
                print(f"[warn ][SkillBook] No languages found in database", file=sys.stderr)

            # Load function names from database
            try:
                print(f"[SkillBook] Loading database: {Path(self.db_path).resolve()}", file=sys.stderr)
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute('SELECT function_name FROM functions ORDER BY function_name')
                self.function_names = [row[0] for row in cursor.fetchall()]
                self.function_names_set = set(self.function_names)

                # Load sections
                cursor.execute('''
                    SELECT DISTINCT s.name
                    FROM sections s
                    JOIN function_sections fs ON fs.section_id = s.id
                    ORDER BY s.name
                ''')
                self.sections = [row[0] for row in cursor.fetchall()]

                # Build function_names_by_section index: {section_name: [func_name, ...]}
                cursor.execute('''
                    SELECT f.function_name, s.name
                    FROM functions f
                    JOIN function_sections fs ON fs.function_id = f.id
                    JOIN sections s ON fs.section_id = s.id
                    ORDER BY f.function_name
                ''')
                self.function_names_by_section = {}
                for func_name, section_name in cursor.fetchall():
                    if section_name not in self.function_names_by_section:
                        self.function_names_by_section[section_name] = []
                    self.function_names_by_section[section_name].append(func_name)

                conn.close()
            except Exception as e:
                print(f"[error][SkillBook] Failed to load function names from database: {e}", file=sys.stderr)
                return False

            # Set history file path in app data directory
            data_dir = self.get_data_dir()
            self._history_path = Path(data_dir) / 'history.txt'

            # Initialize custom database (favorites + comments)
            try:
                custom_db.init_db(self.custom_db_path)
                print(f"[SkillBook] Custom DB: {self.custom_db_path}", file=sys.stderr)
            except Exception as e:
                print(f"[warn ][SkillBook] Failed to initialize custom DB: {e}", file=sys.stderr)

            print(f"[SkillBook] Loaded {len(self.function_names)} functions, {len(self.languages)} languages, {len(self.sections)} sections", file=sys.stderr)
            return True
        except Exception as e:
            print(f"[error][SkillBook] Failed to load data: {e}", file=sys.stderr)
            return False

    def on_run_cli(self, args):
        """CLI mode - print database information"""
        print(f"SKILL Book - Function Reference Viewer")
        print(f"Database: {self.db_path}")
        return 0

    def on_run_desktop_initialize(self) -> int:
        """Desktop mode initialization"""
        # Load data
        if not self._load_data():
            print(f"[error][SkillBook] Failed to initialize - database not available", file=sys.stderr)
            return 1

        # Register handlers
        self.register_handlers({
            'getFunction': self._handle_get_function,
            'autocomplete': self._handle_autocomplete,
            'jump': self._handle_jump,
            'getInfo': self._handle_get_info,
            'getSections': self._handle_get_sections,
            'getAppStateAction': self._handle_get_app_state_action,
            'openUrl': self._handle_open_url,
            'addHistory': self._handle_add_history,
            'getHistory': self._handle_get_history,
            'deleteHistory': self._handle_delete_history,
            'getSettings': self._handle_get_settings,
            'saveSettings': self._handle_save_settings,
            # Favorites
            'getFavorites': self._handle_get_favorites,
            'toggleFavorite': self._handle_toggle_favorite,
            'isFavorite': self._handle_is_favorite,
            # Comments
            'getComments': self._handle_get_comments,
            'addComment': self._handle_add_comment,
            'editComment': self._handle_edit_comment,
            'deleteComment': self._handle_delete_comment,
        })

        return 0

    def _handle_get_function(self, data: dict, language: str) -> dict:
        """Get function data for display (HTML rendering done in JavaScript)"""
        try:
            index = data.get('index', 0)
            lang_id = data.get('lang_id', 1)

            if not self.function_names:
                return {'success': False, 'error': 'No functions loaded'}

            if index < 0 or index >= len(self.function_names):
                return {'success': False, 'error': 'Invalid function index'}

            func_name = self.function_names[index]
            func_data = get_function_data(self.db_path, func_name, lang_id)

            if not func_data:
                return {'success': False, 'error': f'Function not found: {func_name}'}

            # Format content with image extraction
            conn = sqlite3.connect(self.db_path)

            # Process description
            if func_data.get('description'):
                func_data['description'] = format_content(func_data['description'], func_data.get('description_format', 'text'), conn, self.doc_base)

            # Process example
            if func_data.get('example') and func_data['example'] != 'X':
                func_data['example'] = format_content(func_data['example'], func_data.get('example_format', 'text'), conn, self.doc_base)

            # Process argument descriptions
            for arg in func_data.get('arguments', []):
                if arg.get('description'):
                    arg['description'] = format_content(arg['description'], arg.get('format', 'text'), conn, self.doc_base)

            # Process return descriptions
            for ret in func_data.get('returns', []):
                if ret.get('description'):
                    ret['description'] = format_content(ret['description'], ret.get('format', 'text'), conn, self.doc_base)

            conn.close()

            return {
                'success': True,
                'function_name': func_name,
                'index': index,
                'total': len(self.function_names),
                'data': func_data
            }
        except Exception as e:
            print(f"[error][SkillBook] Failed to get function: {e}", file=sys.stderr)
            return {'success': False, 'error': str(e)}

    def _handle_autocomplete(self, data: dict, language: str) -> dict:
        """Autocomplete search with pagination and favorites ranking"""
        try:
            q = data.get('q', '').lower()
            section = data.get('section', '')  # '' = All sections
            offset = data.get('offset', 0)  # For pagination
            limit = data.get('limit', 30)  # Items per page

            if not q:
                return {'success': True, 'results': []}

            # Get favorites set for ranking
            try:
                favorites_list = custom_db.get_favorites(self.custom_db_path)
                favorites_set = {fav['name'] for fav in favorites_list}
            except:
                favorites_set = set()

            # Choose name pool based on section filter
            if section and section in self.function_names_by_section:
                names_pool = [(self.function_names.index(n), n)
                              for n in self.function_names_by_section[section]
                              if n in self.function_names_set]
            else:
                names_pool = list(enumerate(self.function_names))

            # Parse query: if has spaces, treat as multi-word search
            query_words = [w.strip() for w in q.split()] if ' ' in q else [q]
            is_multi_word = len(query_words) > 1

            matched_items = []  # Will store (index, name, is_favorite, match_type)
            seen = set()

            # First pass: prefix matches (only first word in multi-word search)
            first_word = query_words[0]
            for idx, name in names_pool:
                name_lower = name.lower()
                if name_lower.startswith(first_word):
                    # For multi-word search, check all words are contained
                    if is_multi_word:
                        if all(word in name_lower for word in query_words):
                            is_fav = name in favorites_set
                            matched_items.append((idx, name, is_fav, 0))  # 0 = prefix match
                            seen.add(name)
                    else:
                        is_fav = name in favorites_set
                        matched_items.append((idx, name, is_fav, 0))
                        seen.add(name)

            # Second pass: contains matches (not already in results)
            for idx, name in names_pool:
                if name not in seen:
                    name_lower = name.lower()
                    # Check if all query words are contained in the name
                    if all(word in name_lower for word in query_words):
                        is_fav = name in favorites_set
                        matched_items.append((idx, name, is_fav, 1))  # 1 = contains match
                        seen.add(name)

            # Sort: favorites first (by creation time desc), then by match type, then alphabetically
            matched_items.sort(key=lambda x: (not x[2], x[3], x[1]))

            # Apply pagination
            total = len(matched_items)
            paginated = matched_items[offset:offset + limit]

            results = [{'name': item[1], 'index': item[0]} for item in paginated]

            return {
                'success': True,
                'results': results,
                'total': total,
                'offset': offset,
                'limit': limit,
                'has_more': (offset + limit) < total
            }
        except Exception as e:
            print(f"[error][SkillBook] Autocomplete failed: {e}", file=sys.stderr)
            return {'success': False, 'error': str(e)}

    def _handle_jump(self, data: dict, language: str) -> dict:
        """Jump to function by name"""
        try:
            name = data.get('name', '')
            if not name:
                return {'success': False, 'error': 'No name provided'}

            # Exact match
            if name in self.function_names:
                return {'success': True, 'index': self.function_names.index(name)}

            # Case-insensitive match
            name_lower = name.lower()
            for i, fn in enumerate(self.function_names):
                if fn.lower() == name_lower:
                    return {'success': True, 'index': i}

            return {'success': False, 'error': f'Function not found: {name}'}
        except Exception as e:
            print(f"[error][SkillBook] Jump failed: {e}", file=sys.stderr)
            return {'success': False, 'error': str(e)}

    def _handle_get_sections(self, data: dict, language: str) -> dict:
        """Get sections with indices of functions in each section"""
        try:
            result = []
            for s in self.sections:
                names = self.function_names_by_section.get(s, [])
                indices = [self.function_names.index(n) for n in names if n in self.function_names_set]
                result.append({'name': s, 'count': len(indices), 'indices': indices})
            return {'success': True, 'sections': result}
        except Exception as e:
            print(f"[error][SkillBook] Get sections failed: {e}", file=sys.stderr)
            return {'success': False, 'error': str(e)}

    def _handle_get_info(self, data: dict, language: str) -> dict:
        """Get app information"""
        return {
            'success': True,
            'total_functions': len(self.function_names),
            'languages': self.languages,
            'db_path': self.db_path
        }

    def _handle_get_app_state_action(self, _data: dict, _language: str) -> dict:
        """Get app state for state notifications"""
        return {
            'success': True,
            'state': self.state.get_all()
        }

    def _handle_open_url(self, data: dict, language: str) -> dict:
        """Open external URL in Firefox browser using browse_firefox"""
        try:
            url = data.get('url', '')
            if not url:
                return {'success': False, 'error': 'No URL provided'}

            # Use browse_firefox to open the URL
            # It handles both HTTP/HTTPS URLs and local file paths (with bookmarks)
            if browse_firefox(url):
                print(f"[SkillBook] Opened URL with Firefox: {url}", file=sys.stderr)
                return {'success': True, 'message': f'Opening {url}'}
            else:
                print(f"[error][SkillBook] Failed to open URL with Firefox: {url}", file=sys.stderr)
                return {'success': False, 'error': 'Failed to open URL with Firefox'}
        except Exception as e:
            print(f"[error][SkillBook] Failed to open URL: {e}", file=sys.stderr)
            return {'success': False, 'error': str(e)}

    def _read_history(self) -> list:
        """Read history from file. Returns list with most recent first."""
        if not self._history_path or not self._history_path.exists():
            return []
        try:
            lines = self._history_path.read_text(encoding='utf-8').splitlines()
            return [l.strip() for l in lines if l.strip()]
        except Exception:
            return []

    def _write_history(self, history: list):
        """Write history list to file (most recent first, max HISTORY_MAX entries)."""
        if not self._history_path:
            return
        try:
            entries = history[:HISTORY_MAX]
            self._history_path.write_text('\n'.join(entries) + '\n' if entries else '', encoding='utf-8')
        except Exception as e:
            print(f"[warn ][SkillBook] Failed to write history: {e}", file=sys.stderr)

    def _handle_add_history(self, data: dict, language: str) -> dict:
        """Add a function name to history (deduplicates, keeps most recent first)"""
        try:
            name = data.get('name', '').strip()
            if not name:
                return {'success': False, 'error': 'No name provided'}

            history = self._read_history()
            # Remove existing entry (case-sensitive) to move it to top
            history = [h for h in history if h != name]
            history.insert(0, name)
            self._write_history(history)
            return {'success': True, 'history': history[:HISTORY_MAX]}
        except Exception as e:
            print(f"[error][SkillBook] Failed to add history: {e}", file=sys.stderr)
            return {'success': False, 'error': str(e)}

    def _handle_get_history(self, data: dict, language: str) -> dict:
        """Get history list (most recent first)"""
        try:
            history = self._read_history()
            return {'success': True, 'history': history}
        except Exception as e:
            print(f"[error][SkillBook] Failed to get history: {e}", file=sys.stderr)
            return {'success': False, 'error': str(e)}

    def _handle_delete_history(self, data: dict, language: str) -> dict:
        """Delete a history entry by name"""
        try:
            name = data.get('name', '').strip()
            if not name:
                return {'success': False, 'error': 'No name provided'}

            history = self._read_history()
            # Remove the entry (case-sensitive)
            history = [h for h in history if h != name]
            self._write_history(history)
            return {'success': True, 'history': history}
        except Exception as e:
            print(f"[error][SkillBook] Failed to delete history: {e}", file=sys.stderr)
            return {'success': False, 'error': str(e)}

    def _handle_get_settings(self, data: dict, language: str) -> dict:
        """Get current settings (language)"""
        try:
            config = self.load_config({
                'skillbook.language': '1',
            })
            language_id = int(config.get('skillbook.language', '1'))
            return {
                'success': True,
                'language': language_id
            }
        except Exception as e:
            print(f"[error][SkillBook] Failed to get settings: {e}", file=sys.stderr)
            return {'success': False, 'error': str(e)}

    def _handle_save_settings(self, data: dict, language: str) -> dict:
        """Save settings (language)"""
        try:
            language_id = data.get('language', 1)

            # Load current config and update language
            config = self.load_config({
                'skillbook.language': '1',
            })
            config['skillbook.language'] = str(language_id)

            # Save config
            self.save_config(config)

            print(f"[SkillBook] Settings saved: language={language_id}", file=sys.stderr)
            return {'success': True}
        except Exception as e:
            print(f"[error][SkillBook] Failed to save settings: {e}", file=sys.stderr)
            return {'success': False, 'error': str(e)}

    # ── Favorites handlers ─────────────────────────────────────────────────

    def _handle_get_favorites(self, data: dict, language: str) -> dict:
        """Get all favorite function names"""
        try:
            favorites = custom_db.get_favorites(self.custom_db_path)
            return {'success': True, 'favorites': favorites}
        except Exception as e:
            print(f"[error][SkillBook] Failed to get favorites: {e}", file=sys.stderr)
            return {'success': False, 'error': str(e)}

    def _handle_toggle_favorite(self, data: dict, language: str) -> dict:
        """Toggle favorite for a function. Returns new state."""
        try:
            name = data.get('name', '').strip()
            if not name:
                return {'success': False, 'error': 'No name provided'}

            if custom_db.is_favorite(self.custom_db_path, name):
                custom_db.remove_favorite(self.custom_db_path, name)
                is_fav = False
            else:
                custom_db.add_favorite(self.custom_db_path, name)
                is_fav = True

            return {'success': True, 'is_favorite': is_fav}
        except Exception as e:
            print(f"[error][SkillBook] Failed to toggle favorite: {e}", file=sys.stderr)
            return {'success': False, 'error': str(e)}

    def _handle_is_favorite(self, data: dict, language: str) -> dict:
        """Check if a function is a favorite"""
        try:
            name = data.get('name', '').strip()
            if not name:
                return {'success': False, 'error': 'No name provided'}
            is_fav = custom_db.is_favorite(self.custom_db_path, name)
            return {'success': True, 'is_favorite': is_fav}
        except Exception as e:
            print(f"[error][SkillBook] Failed to check favorite: {e}", file=sys.stderr)
            return {'success': False, 'error': str(e)}

    # ── Comments handlers ──────────────────────────────────────────────────

    def _handle_get_comments(self, data: dict, language: str) -> dict:
        """Get all comments for a function with user info from account.db"""
        try:
            name = data.get('name', '').strip()
            if not name:
                return {'success': False, 'error': 'No name provided'}

            comments = custom_db.get_comments(self.custom_db_path, name)

            # Enrich comments with user info from account.db
            account_db_config = get_desktop_config('general.account_db', '').strip()
            account_db_path = account_db_config if account_db_config else account_module.get_default_account_db_path()
            # Ensure account DB schema is initialized (creates tables if missing)
            try:
                account_module.init_db(account_db_path)
            except Exception as e:
                print(f"[warn ][SkillBook] Failed to init account DB: {e}", file=sys.stderr)

            for comment in comments:
                user_id = comment.get('user_id')
                if user_id:
                    try:
                        acct = account_module.get_account(account_db_path, user_id)
                        if acct:
                            comment['display_name'] = acct.get('name') or user_id
                            # Get photo_small as binary and convert to base64
                            photo_binary, photo_mime = account_module.get_account_photo(account_db_path, user_id, 'small')
                            if photo_binary:
                                comment['avatar_small'] = base64.b64encode(photo_binary).decode('ascii')
                                comment['avatar_mime'] = photo_mime or 'image/jpeg'
                            else:
                                comment['avatar_small'] = None
                                comment['avatar_mime'] = None
                        else:
                            comment['display_name'] = user_id
                            comment['avatar_small'] = None
                    except Exception as e:
                        print(f"[warn ][SkillBook] Failed to get account info for {user_id}: {e}", file=sys.stderr)
                        comment['display_name'] = user_id
                        comment['avatar_small'] = None

            return {'success': True, 'comments': comments, 'current_user': self._current_user}
        except Exception as e:
            print(f"[error][SkillBook] Failed to get comments: {e}", file=sys.stderr)
            return {'success': False, 'error': str(e)}

    def _handle_add_comment(self, data: dict, language: str) -> dict:
        """Add a comment to a function"""
        try:
            name = data.get('name', '').strip()
            content = data.get('content', '').strip()
            parent_id = data.get('parent_id', None)

            if not name:
                return {'success': False, 'error': 'No function name provided'}
            if not content:
                return {'success': False, 'error': 'Comment content is empty'}

            comment = custom_db.add_comment(
                self.custom_db_path, name, self._current_user, content, parent_id
            )
            return {'success': True, 'comment': comment}
        except Exception as e:
            print(f"[error][SkillBook] Failed to add comment: {e}", file=sys.stderr)
            return {'success': False, 'error': str(e)}

    def _handle_edit_comment(self, data: dict, language: str) -> dict:
        """Edit a comment's content (only owner can edit)"""
        try:
            comment_id = data.get('id')
            content = data.get('content', '').strip()
            if comment_id is None:
                return {'success': False, 'error': 'No comment id provided'}
            if not content:
                return {'success': False, 'error': 'Comment content is empty'}

            updated = custom_db.update_comment(self.custom_db_path, comment_id, self._current_user, content)
            if updated:
                return {'success': True}
            else:
                return {'success': False, 'error': 'Comment not found or not owned by you'}
        except Exception as e:
            print(f"[error][SkillBook] Failed to edit comment: {e}", file=sys.stderr)
            return {'success': False, 'error': str(e)}

    def _handle_delete_comment(self, data: dict, language: str) -> dict:
        """Delete a comment (only owner can delete)"""
        try:
            comment_id = data.get('id')
            if comment_id is None:
                return {'success': False, 'error': 'No comment id provided'}

            deleted = custom_db.delete_comment(self.custom_db_path, comment_id, self._current_user)
            if deleted:
                return {'success': True}
            else:
                return {'success': False, 'error': 'Comment not found or not owned by you'}
        except Exception as e:
            print(f"[error][SkillBook] Failed to delete comment: {e}", file=sys.stderr)
            return {'success': False, 'error': str(e)}


# Register the app class
register_app_class(SkillbookApp)
