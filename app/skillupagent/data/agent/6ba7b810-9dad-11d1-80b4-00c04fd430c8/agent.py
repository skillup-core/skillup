"""
create_path agent plugin

on_init     — store the current edit cellview in CIW via deGetEditCellView
on_post_req — parse the <command> block from the LLM response and run dbCreatePath.
              if a previous path exists, delete it with dbDeleteObject first.
"""
import re

_sessions = {}  # session_id → {'has_path': bool}


def on_init(session_id, agent, agent_dir, system_prompt):
    print(f'[create_path] on_init session={session_id}')
    _sessions[session_id] = {'has_path': False}
    # store the current edit cellview in a CIW SKILL variable
    agent['call_skill']('_cp_cv = deGetEditCellView()')
    return {'hyperparameter': {'temperature': 0.2}}


def on_pre_req(session_id, agent, messages, new_message):
    print(f'[create_path] on_pre_req turns={len(messages)} msg={new_message[:60]!r}')


def _parse_command(response):
    # LLM output sometimes wraps the block in a ``` fence; strip that first
    # so the <command> regex still matches either way.
    stripped = re.sub(r'```(?:\w+)?\s*(<command>.*?</command>)\s*```',
                       r'\1', response, flags=re.DOTALL)
    m = re.search(r'<command>(.*?)</command>', stripped, re.DOTALL)
    if not m:
        return None
    values = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if '=' in line:
            name, _, value = line.partition('=')
            values[name.strip()] = value.strip()
    return values


def on_post_req(session_id, agent, messages, response):
    print(f'[create_path] on_post_req response_len={len(response)}')

    values = _parse_command(response)
    if values is None:
        # No <command> block: the LLM asked a clarifying question instead —
        # show that question as-is, it's already natural language.
        return {'response': response.strip()}

    layer_raw = values.get('layer', '').strip()
    points_raw = values.get('points', '').strip()
    width_raw = values.get('width', '').strip()

    if not layer_raw or not points_raw or not width_raw:
        print(f'[create_path] incomplete command: {values}')
        return {'response': response.strip()}

    # numeric layer is passed as-is; string layer is quoted
    try:
        int(layer_raw)
        layer_skill = layer_raw
    except ValueError:
        layer_skill = f'"{layer_raw}"'

    # wrap space-separated points in a SKILL list()
    points_skill = f'list({points_raw})'

    session_data = _sessions.get(session_id, {})

    # delete the previous path before drawing a new one
    if session_data.get('has_path'):
        agent['call_skill']('dbDeleteObject(_cp_path)')

    # create new path; store the return value so it can be deleted on the next call
    skill_code = f'_cp_path = dbCreatePath(_cp_cv {layer_skill} {points_skill} {width_raw})'
    ok = agent['call_skill'](skill_code)

    if ok:
        session_data['has_path'] = True
        _sessions[session_id] = session_data
        print(f'[create_path] path created: {skill_code}')
        return {'response': f'{layer_raw} 레이어에 폭 {width_raw}의 경로를 그렸습니다 ({points_raw}).'}
    else:
        print(f'[create_path] call_skill failed')
        return {'response': 'CIW에 SKILL 코드 전달에 실패했습니다.'}


def on_exit(session_id, agent, messages):
    print('[create_path] on_exit')
    _sessions.pop(session_id, None)
