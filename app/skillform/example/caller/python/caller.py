"""
Example: Python caller for skillform GUI.

Usage:
    python3 caller.py [<skillup.py path> <python3 path>]

If arguments are omitted, skillup.py is auto-detected by walking up from this
file, and the invoking Python interpreter is used as python3.
"""

import sys
import os

def _find_skillup_py(start):
    path = os.path.dirname(os.path.abspath(start))
    while True:
        candidate = os.path.join(path, 'skillup.py')
        if os.path.exists(candidate):
            return candidate
        parent = os.path.dirname(path)
        if parent == path:
            raise FileNotFoundError('skillup.py not found walking up from ' + start)
        path = parent

if len(sys.argv) >= 3:
    SKILLUP_PY = sys.argv[1]
    PYTHON_BIN = sys.argv[2]
else:
    SKILLUP_PY = _find_skillup_py(__file__)
    PYTHON_BIN = sys.executable

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(SKILLUP_PY)),
                                'app', 'skillform', 'lib', 'python'))
from libform import SkillForm # type: ignore

FORM      = os.path.join(os.path.dirname(__file__), '..', '..', 'form', 'form01.json')
SAVE_FILE = '/tmp/skillform_example.json'


def on_event(form, ev):
    t = ev.get('type')

    if t == 'ready':
        print('Form window opened.')

    elif t == 'button_click':
        btn = ev['button_id']
        v   = ev.get('values', {})

        print(f"\nButton pressed: {btn}")
        print(f"  name      : {v.get('name', '')}")
        print(f"  cell_name : {v.get('cell_name', '')}")
        print(f"  run_drc   : {v.get('run_drc', False)}")
        print(f"  layer     : {v.get('layer', '')}")
        print(f"  count     : {v.get('count', 0)}")
        print(f"  note      : {v.get('note', '')}")

        if btn == 'btn_save':
            form.save_values(v, SAVE_FILE)

        elif btn == 'btn_load':
            saved = form.load_values(SAVE_FILE)
            if saved:
                print(f"  -> loaded: {saved}")
                form.set_values(saved)

        elif btn == 'btn_count_plus':
            new_count = int(v.get('count', 0)) + 1
            print(f"  -> count: {v.get('count', 0)} + 1 = {new_count}")
            form.set_values({'count': new_count})

        elif btn in ('btn_ok', 'btn_cancel'):
            form.close()

    elif t == 'window_closed':
        print('Form window closed by user.')


SkillForm(FORM, skillup_py=SKILLUP_PY, python_bin=PYTHON_BIN).run(on_event)
