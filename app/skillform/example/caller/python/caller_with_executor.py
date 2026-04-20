"""
Example: Python caller for skillform GUI (executor variant).

Usage:
    python3 caller_with_executor.py <skillup.py path>

python_bin is determined automatically via skillup-tool/skillup-python-selector.sh.
"""

import sys
import os

if len(sys.argv) < 2:
    print(f"Usage: {sys.argv[0]} <skillup.py>", file=sys.stderr)
    sys.exit(1)

SKILLUP_PY = sys.argv[1]

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


SkillForm.with_executor(FORM, SKILLUP_PY).run(on_event)
