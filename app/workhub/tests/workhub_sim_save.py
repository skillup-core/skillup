"""
다른 사람(work1)이 문서를 주기적으로 저장하는 상황을 시뮬레이션.

사용법:
  python3 workhub_sim_save.py [interval]   # 기본 interval=1.0초

동작:
  - skillup_default_config.ini 또는 기본 경로에서 db_path, notify_dir 자동 탐색
  - work1 계정으로 "[TEST]" 제목의 메모를 찾거나 없으면 생성
  - interval 초마다 본문 맨 앞에 "a" 추가 후 저장 + evt touch
  - Ctrl+C로 중단
"""
import sys
import os
import sqlite3
import time
import configparser

# 출력 즉시 flush
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None

# ------------------------------------------------------------------
# 경로 탐색
# ------------------------------------------------------------------
_TESTS_DIR   = os.path.dirname(os.path.abspath(__file__))
_APP_DIR     = os.path.dirname(_TESTS_DIR)
_SKILLUP_FULL = os.path.dirname(os.path.dirname(_APP_DIR))   # skillup-full/
_SKILLUP_CORE = os.path.dirname(_SKILLUP_FULL)               # skillup-core/

_DEFAULT_DB         = os.path.join(_APP_DIR, 'data', 'workhub.db')
_DEFAULT_NOTIFY_DIR = os.path.join(_APP_DIR, 'data', 'notify')

def _find_default_config():
    for d in (_SKILLUP_CORE, _SKILLUP_FULL):
        candidate = os.path.join(d, 'skillup_default_config.ini')
        if os.path.exists(candidate):
            return candidate
    return None

def _expand(value, ini_dir):
    return value.replace('${ini_dir}', ini_dir)

def _load_paths():
    cfg_path = _find_default_config()
    if not cfg_path:
        return _DEFAULT_DB, _DEFAULT_NOTIFY_DIR, None

    ini_dir = os.path.dirname(os.path.abspath(cfg_path))
    cp = configparser.ConfigParser()
    cp.read(cfg_path, encoding='utf-8')

    db_path    = _DEFAULT_DB
    notify_dir = _DEFAULT_NOTIFY_DIR
    account_db = None

    for section in cp.sections():
        opts = dict(cp[section])
        if 'workhub.db_path' in opts:
            db_path = _expand(opts['workhub.db_path'], ini_dir)
        if 'workhub.notify_dir' in opts:
            notify_dir = _expand(opts['workhub.notify_dir'], ini_dir)
        if 'general.account_db' in opts:
            account_db = _expand(opts['general.account_db'], ini_dir)

    return db_path, notify_dir, account_db

# ------------------------------------------------------------------
# 메인
# ------------------------------------------------------------------
interval = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
db_path, notify_dir, account_db = _load_paths()

print(f"db_path    : {db_path}")
print(f"notify_dir : {notify_dir}")
print(f"interval   : {interval}s")
print()

USER_ID = 'work1'

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
conn.execute("PRAGMA journal_mode=DELETE")

# [TEST] 메모 찾기 또는 생성
row = conn.execute(
    "SELECT id, body, version FROM works WHERE title=? AND owner_id=? AND template='note' LIMIT 1",
    ('[TEST]', USER_ID)
).fetchone()

if row:
    work_id = row['id']
    print(f"기존 문서 사용: id={work_id} version={row['version']}")
else:
    now = time.strftime('%Y-%m-%dT%H:%M:%S')
    cur = conn.execute(
        "INSERT INTO works (title, template, body, tags, owner_id, visibility, version, created_at, updated_at) "
        "VALUES (?, 'note', '', '', ?, 'all', 1, ?, ?)",
        ('[TEST]', USER_ID, now, now)
    )
    conn.commit()
    work_id = cur.lastrowid
    print(f"새 문서 생성: id={work_id}")

os.makedirs(notify_dir, exist_ok=True)
evt_path = os.path.join(notify_dir, f'{work_id}.evt')

print(f"work_id={work_id} 문서에 {interval}초마다 'a' 추가 중... (Ctrl+C로 중단)")
print()

try:
    while True:
        row = conn.execute("SELECT body, version FROM works WHERE id=?", (work_id,)).fetchone()
        new_body = 'a' + (row['body'] or '')
        now = time.strftime('%Y-%m-%dT%H:%M:%S')
        conn.execute(
            "UPDATE works SET body=?, version=version+1, updated_at=? WHERE id=?",
            (new_body, now, work_id)
        )
        conn.commit()
        new_version = row['version'] + 1
        with open(evt_path, 'a'):
            os.utime(evt_path, None)
        print(f"[{now}] version={new_version} body길이={len(new_body)}")
        time.sleep(interval)
except KeyboardInterrupt:
    print("\n중단됨")
finally:
    conn.close()
