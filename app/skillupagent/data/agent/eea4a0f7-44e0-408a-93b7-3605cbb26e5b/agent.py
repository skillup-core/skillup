"""
Path Leader plugin

on_post_req — parse the <command action=delegate> block from the LLM
              response and call agent['call_subagent'] to run the Path
              Agent sub-agent. Width verification happens here in Python,
              not by re-invoking the leader LLM: the leader already knows
              the width it sent (parsed from its own delegate message), so
              if it's <= 3 (DRC violation) this hook immediately re-delegates
              with width=4 to the same sub-session. Path Agent's own
              on_post_req (create_path) tracks the previously drawn path per
              session and deletes it before redrawing, so the second
              delegation replaces the width=3 path with a width=4 one.
"""
import re

MIN_WIDTH = 3


def _parse_command(response):
    m = re.search(r'<command>(.*?)</command>', response, re.DOTALL)
    if not m:
        return None
    values = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if '=' in line:
            k, _, v = line.partition('=')
            values[k.strip()] = v.strip()
    return values


def _parse_width(message):
    m = re.search(r'width=(\S+)', message)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _with_width(message, new_width):
    return re.sub(r'width=\S+', f'width={new_width}', message)


def _humanize_message(message):
    """Turn the compact 'layer=X points=x1:y1 x2:y2 width=W' delegate
    message (meant for create_path's LLM to parse) into a natural-language
    sentence for display in the UI's streamed leader turn. Falls back to the
    raw message if the expected fields aren't all present."""
    m = re.search(r'layer=(\S+)\s+points=([\d:\-\s]+?)\s+width=(\S+)', message)
    if not m:
        return message
    layer, points_raw, width = m.group(1), m.group(2).strip(), m.group(3)
    points = ' → '.join(p.replace(':', ',') for p in points_raw.split())
    return f'{layer} 레이어에 ({points}) 경로를 폭 {width}로 그려줘.'


def on_post_req(session_id, agent, messages, response):
    print(f'[path_leader] on_post_req response_len={len(response)}')

    values = _parse_command(response)
    if not values or values.get('action') != 'delegate':
        return

    agent_id = values.get('agent_id', '').strip()
    message  = values.get('message', '').strip()
    if not agent_id or not message:
        print(f'[path_leader] incomplete delegate command: {values}')
        return

    print(f'[path_leader] delegating to {agent_id}: {message!r}')
    reply = agent['call_subagent'](agent_id, message, display=_humanize_message(message))
    if reply is None:
        print(f'[path_leader] call_subagent failed for {agent_id}')
        return {'response': 'Path Agent 호출에 실패했습니다.'}

    # The delegate <command> block and the sub-agent's raw reply are not
    # shown here — the nested transcript (agent['call_subagent'] records)
    # already carries them via the subagents[] payload. This return value
    # is only the leader's own short summary.
    width = _parse_width(message)
    if width is not None and width <= MIN_WIDTH:
        fixed_width = MIN_WIDTH + 1
        fixed_message = _with_width(message, fixed_width)
        print(f'[path_leader] width={width:g} <= {MIN_WIDTH}, re-delegating: {fixed_message!r}')
        reply2 = agent['call_subagent'](agent_id, fixed_message, display=_humanize_message(fixed_message))
        if reply2 is None:
            print(f'[path_leader] call_subagent (retry) failed for {agent_id}')
            return {'response': f'width={width:g} 규격 위반을 감지했지만 보정 재그리기에 실패했습니다.'}
        return {'response': f'width={width:g}는 최소 규격({MIN_WIDTH}) 위반이라 width={fixed_width}로 다시 그렸습니다.'}

    return {'response': 'Path를 그렸습니다.'}


def on_exit(session_id, agent, messages):
    print('[path_leader] on_exit')
