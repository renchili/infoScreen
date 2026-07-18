from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.backend

ROOT = Path(__file__).resolve().parents[1]
JOB_PATH = ROOT / "surface" / "jobs" / "local_event_search.py"


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def test_local_event_job_applies_studio_between_collection_and_normalization() -> None:
    source = JOB_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }

    studio_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _call_name(node) == "apply_runtime_studio_rules"
    ]
    assert len(studio_calls) == 1
    studio_call = studio_calls[0]
    assert len(studio_call.args) == 1
    assert isinstance(studio_call.args[0], ast.Call)
    assert _call_name(studio_call.args[0]) == "collect_events"

    parent = parents.get(studio_call)
    while parent is not None and not isinstance(parent, ast.Call):
        parent = parents.get(parent)
    assert isinstance(parent, ast.Call)
    assert _call_name(parent) == "normalize_payload"


def test_local_event_job_keeps_existing_writer_and_partial_protection() -> None:
    source = JOB_PATH.read_text(encoding="utf-8")
    assert "verified_previous_payload" in source
    assert "kept_previous_verified_result" in source
    assert "write_payload" in source
    assert "apply_detail_authority" not in source
    assert "apply_listing_url_authority" not in source
    assert "apply_source_overrides" not in source
