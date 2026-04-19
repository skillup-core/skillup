"""
Example: Python caller for skillform GUI.

Run from repo root:
    python3 app/skillform/example/caller/python/caller.py
"""

import sys
import os

# Allow running from anywhere inside the repo
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'lib', 'python'))
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


SkillForm(FORM).run(on_event)
