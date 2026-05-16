"""
Agent Builder plugin

on_init     — detect account_id, check staging path, inject warning into system_prompt
              if existing work is found. Caches staging path for on_post_req.
on_post_req — parse <command> block, write agent files to staging path.
on_exit     — clean up session cache.
"""
import os
import re
import shutil
from pathlib import Path

ZERO_UUID = '00000000-0000-0000-0000-000000000000'

# session_id → staging Path; populated in on_init so on_post_req can find it
_staging_path_cache = {}

PLUGIN_SKELETON = '''\
"""
{name} agent plugin

Hooks called by skillupagent:
  on_init(session_id, agent, agent_dir, system_prompt) -> dict or None
  on_pre_req(session_id, agent, messages, new_message)  -> dict or None
  on_post_req(session_id, agent, messages, response)    -> dict or None
  on_exit(session_id, agent, messages)
"""


def on_init(session_id, agent, agent_dir, system_prompt):
    print(f\'[{name}] on_init session={{session_id}}\')
    return {{'hyperparameter': {{'temperature': 0.3}}}}


def on_pre_req(session_id, agent, messages, new_message):
    print(f\'[{name}] on_pre_req msg={{new_message[:60]!r}}\')


def on_post_req(session_id, agent, messages, response):
    print(f\'[{name}] on_post_req response_len={{len(response)}}\')


def on_exit(session_id, agent, messages):
    print(f\'[{name}] on_exit\')
'''


def _get_account_id():
    return os.environ.get('USER', os.environ.get('USERNAME', 'user'))


def _get_staging_path(agent_dir):
    """Return <agent.dir>/00000000.../account_id/"""
    agent_base = Path(agent_dir).parent
    account_id = _get_account_id()
    return agent_base / ZERO_UUID / account_id


def _extract_tag(text, tag):
    """Extract content between <tag> and </tag>. Returns stripped string or ''."""
    m = re.search(rf'<{tag}>(.*?)</{tag}>', text, re.DOTALL)
    return m.group(1).strip() if m else ''


def on_init(session_id, agent, agent_dir, system_prompt):
    print(f'[agent_builder] on_init session={session_id}')
    staging = _get_staging_path(agent_dir)
    _staging_path_cache[session_id] = staging

    if staging.exists():
        warning = (
            '\n\n[SYSTEM NOTE] The staging path already contains existing work.\n'
            'Before collecting any new fields, tell the user in Korean:\n'
            '"이전 작업 중인 자료가 있습니다. 삭제하고 새로 시작할까요? (yes/no)"\n'
            'Wait for confirmation before proceeding.'
        )
        return {'system_prompt': system_prompt + warning}

    return None


def on_post_req(session_id, agent, messages, response):
    print(f'[agent_builder] on_post_req response_len={len(response)}')

    m = re.search(r'<command>(.*?)</command>', response, re.DOTALL)
    if not m:
        return

    block = m.group(1)

    # Parse scalar key = value lines (stop at the first child tag)
    scalars = {}
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith('<'):
            break
        if '=' in stripped:
            k, _, v = stripped.partition('=')
            scalars[k.strip()] = v.strip()

    action = scalars.get('action', '').strip()
    if action != 'create':
        print(f'[agent_builder] unknown action: {action!r}')
        return

    name        = scalars.get('name', '').strip()
    desc        = scalars.get('desc', '').strip()
    require_ciw = scalars.get('require_ciw', 'false').strip().lower()

    system_content = _extract_tag(block, 'system')
    usage_content  = _extract_tag(block, 'usage')
    plugin_flag    = _extract_tag(block, 'plugin').lower()

    if not name or not desc or not system_content:
        print('[agent_builder] incomplete command: name/desc/system required')
        return

    if require_ciw not in ('true', 'false'):
        require_ciw = 'true' if require_ciw in ('yes', '1', 'y') else 'false'

    staging = _staging_path_cache.get(session_id)
    if staging is None:
        print('[agent_builder] staging path not cached — on_init may not have run')
        return

    # Remove existing staging dir if present (user confirmed deletion via LLM conversation)
    if staging.exists():
        shutil.rmtree(str(staging))
        print(f'[agent_builder] removed existing staging: {staging}')

    staging.mkdir(parents=True, exist_ok=True)
    print(f'[agent_builder] writing to staging: {staging}')

    # config.ini
    config_lines = [
        '[config]',
        f'id = {ZERO_UUID}',
        f'name = {name}',
        f'desc = {desc}',
        f'require_ciw = {require_ciw}',
    ]
    (staging / 'config.ini').write_text('\n'.join(config_lines) + '\n', encoding='utf-8')

    # system.txt
    (staging / 'system.txt').write_text(system_content + '\n', encoding='utf-8')

    # usage.txt
    if usage_content:
        (staging / 'usage.txt').write_text(usage_content + '\n', encoding='utf-8')

    # agent.py skeleton
    if plugin_flag == 'yes':
        skeleton = PLUGIN_SKELETON.format(name=name)
        (staging / 'agent.py').write_text(skeleton, encoding='utf-8')

    print(f'[agent_builder] done — staging: {staging}')

    if agent.get('language') == 'ko':
        notice = (
            f'\n\n---\nAgent Builder가 완료되었습니다.\n'
            f'{staging}\n'
            f'경로의 파일을 직접 확인하세요.'
        )
    else:
        notice = (
            f'\n\n---\nAgent Builder complete.\n'
            f'{staging}\n'
            f'Please review the files at the path above.'
        )
    return {'response': response + notice}


def on_exit(session_id, agent, messages):
    print(f'[agent_builder] on_exit session={session_id}')
    _staging_path_cache.pop(session_id, None)
