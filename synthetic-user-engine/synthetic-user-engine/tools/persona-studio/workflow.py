"""The workflow Persona Studio works on, and its knowledge groups (2026-10-19).

The groups used to be written into the Studio's code for Version A. They now come from the
workflow definition (flow.json, key knowledgeGroups), so another workflow needs only its own
flow.json: set SUE_FLOW to its path, or start the server with --flow. tools/sync_flow.py
checks that the groups cover every item.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FLOW = ROOT / 'data' / 'version-a' / 'flow.json'
_cache: dict[str, dict] = {}


def flow_path() -> Path:
    return Path(os.environ.get('SUE_FLOW') or DEFAULT_FLOW)


def load_flow() -> dict:
    path = flow_path()
    if str(path) not in _cache:
        flow = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(flow.get('knowledgeGroups'), list) or not flow['knowledgeGroups']:
            raise ValueError(f'{path.name} has no knowledgeGroups; add them and run tools/sync_flow.py')
        _cache[str(path)] = flow
    return _cache[str(path)]


def knowledge_groups(visible_only: bool = False) -> list[dict]:
    """visible_only: leave out hidden groups, which keep the role's baseline and are not asked
    in interviews or varied in batches."""
    return [g for g in load_flow()['knowledgeGroups'] if not (visible_only and g.get('hidden'))]
