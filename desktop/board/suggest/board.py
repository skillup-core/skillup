"""
Suggest board handlers for the desktop settings page.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from lib import board as board_lib

_SUGGEST_DIR = os.path.dirname(os.path.abspath(__file__))
DETAIL_FORM_PATH = os.path.join(_SUGGEST_DIR, 'form', 'detail.json')
LIST_FORM_PATH   = os.path.join(_SUGGEST_DIR, 'form', 'list.json')

_FORM_ID = board_lib.read_form_id(DETAIL_FORM_PATH)


def _db_path(config: dict) -> str:
    board_dir = board_lib.get_board_dir(config)
    return board_lib.get_db_path(board_dir, system=True)


def handle_suggest_list(data: dict, config: dict) -> dict:
    form_id = _FORM_ID or ''
    if not form_id:
        return {'records': []}
    try:
        records = board_lib.list_records(_db_path(config), form_id)
        return {'records': records}
    except Exception as e:
        print(f'[error] suggest_list: {e}', file=sys.stderr)
        return {'records': [], 'error': str(e)}


def handle_suggest_post(data: dict, config: dict) -> dict:
    form_id = _FORM_ID or ''
    values = data.get('values', {})
    if not form_id:
        return {'success': False, 'error': 'no form_id'}
    try:
        record_id = board_lib.post_record(_db_path(config), form_id, values)
        return {'success': True, 'record_id': record_id}
    except Exception as e:
        print(f'[error] suggest_post: {e}', file=sys.stderr)
        return {'success': False, 'error': str(e)}


def handle_suggest_modify(data: dict, config: dict) -> dict:
    record_id = data.get('record_id', '')
    values = data.get('values', {})
    if not record_id:
        return {'success': False, 'error': 'no record_id'}
    try:
        ok = board_lib.modify_record(_db_path(config), record_id, values)
        return {'success': ok}
    except Exception as e:
        print(f'[error] suggest_modify: {e}', file=sys.stderr)
        return {'success': False, 'error': str(e)}


def handle_suggest_delete(data: dict, config: dict) -> dict:
    record_id = data.get('record_id', '')
    if not record_id:
        return {'success': False, 'error': 'no record_id'}
    try:
        ok = board_lib.delete_record(_db_path(config), record_id)
        return {'success': ok}
    except Exception as e:
        print(f'[error] suggest_delete: {e}', file=sys.stderr)
        return {'success': False, 'error': str(e)}


def handle_suggest_get(data: dict, config: dict) -> dict:
    record_id = data.get('record_id', '')
    if not record_id:
        return {'record': None}
    try:
        record = board_lib.get_record(_db_path(config), record_id)
        return {'record': record}
    except Exception as e:
        print(f'[error] suggest_get: {e}', file=sys.stderr)
        return {'record': None, 'error': str(e)}
