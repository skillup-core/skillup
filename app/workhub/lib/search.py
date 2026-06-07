"""
WorkHub FTS5 search + tag filter + access control.
"""

import sqlite3
import threading

_lock = threading.Lock()


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=DELETE")
    return conn


def _fts5_quote(token: str) -> str:
    # Quoted prefix: "token"* matches any word starting with token
    return '"' + token.replace('"', '""') + '"*'


def _access_cond(user_id: str, group_ids: list, alias: str = 'w') -> tuple:
    a = alias + '.'
    if group_ids:
        ph = ','.join('?' * len(group_ids))
        cond = (
            f"({a}owner_id = ? OR {a}visibility = 'all' "
            f"OR ({a}visibility = 'group' AND {a}group_id IN ({ph})))"
        )
        params = [user_id] + list(group_ids)
    else:
        cond = f"({a}owner_id = ? OR {a}visibility = 'all')"
        params = [user_id]
    return cond, params


def parse_query(query: str) -> tuple:
    """Split query into (tag_list, fts_tokens)."""
    tags = []
    tokens = []
    for part in query.split():
        if part.startswith('#') and len(part) > 1:
            tags.append(part[1:])
        else:
            tokens.append(part)
    return tags, tokens


def search(db_path: str, query: str, user_id: str, group_ids: list, limit: int = 50) -> list:
    tags, tokens = parse_query(query)
    if not tags and not tokens:
        return []

    acc_cond, acc_params = _access_cond(user_id, group_ids)

    _SELECT = (
        "SELECT w.id, w.title, w.template, w.tags, "
        "w.owner_id, w.visibility, w.group_id, w.owner_write_only, w.created_at, w.updated_at"
    )

    with _lock:
        conn = _connect(db_path)
        try:
            params = list(acc_params)
            conditions = [acc_cond]

            if tokens:
                match_expr = ' '.join(_fts5_quote(t) for t in tokens)
                conditions.append("w.id IN (SELECT rowid FROM works_fts WHERE works_fts MATCH ?)")
                params.append(match_expr)

            for tag in tags:
                safe_tag = tag.replace('%', '').replace('_', '').replace(',', '').replace("'", '')
                if not safe_tag:
                    continue
                conditions.append("(',' || w.tags || ',') LIKE ?")
                params.append(f'%,{safe_tag},%')

            where = ' AND '.join(conditions)

            if tokens:
                sql = (
                    f"{_SELECT}, bm25(works_fts) AS score "
                    f"FROM works w JOIN works_fts ON works_fts.rowid = w.id "
                    f"WHERE {where} ORDER BY score, w.updated_at DESC LIMIT ?"
                )
            else:
                sql = (
                    f"{_SELECT} FROM works w WHERE {where} "
                    f"ORDER BY w.updated_at DESC LIMIT ?"
                )
            params.append(limit)

            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            # FTS5 not available - fall back to LIKE search
            like_conds = [acc_cond]
            like_p = list(acc_params)
            for t in tokens:
                like_conds.append("(w.title LIKE ? OR w.tags LIKE ?)")
                patt = f'%{t}%'
                like_p.extend([patt, patt])
            for tag in tags:
                safe_tag = tag.replace('%', '').replace('_', '').replace(',', '')
                like_conds.append("(',' || w.tags || ',') LIKE ?")
                like_p.append(f'%,{safe_tag},%')
            where2 = ' AND '.join(like_conds)
            sql2 = (
                f"{_SELECT} FROM works w WHERE {where2} "
                f"ORDER BY w.updated_at DESC LIMIT ?"
            )
            like_p.append(limit)
            rows = conn.execute(sql2, like_p).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
