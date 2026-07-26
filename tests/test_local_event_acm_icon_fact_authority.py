from __future__ import annotations

import subprocess
import sys

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime import acm_icon_fact_authority as authority  # noqa: E402


def test_acm_detail_script_reads_icon_rows_not_global_text_order(tmp_path) -> None:
    script = authority._wrap_script("() => ({title: 'Activity', lines: []})")

    assert authority._MARKER in script
    assert "const iconKind = element" in script
    assert "const rowForIcon = (icon, kind)" in script
    assert "icon[-_ ]?date" in script
    assert "map[-_ ]?pin" in script
    assert "groups.sort((left, right) => left.top - right.top" in script
    assert "primary_facts: facts" in script
    assert "dates: [when]" in script
    assert "venues: [facts.venue]" in script

    target = tmp_path / "acm-detail-script.js"
    target.write_text(f'"use strict";\nconst extractor = {script};\n', encoding="utf-8")
    subprocess.run(["node", "--check", str(target)], check=True)


def test_icon_fact_authority_runs_after_parent_fact_preservation_before_review_binding() -> None:
    bootstrap = read_text("surface/local_events_runtime/http1_browser.py")
    gardens = read_text("surface/local_events_runtime/gardens_field_authority.py")

    assert bootstrap.index("apply_acm_primary_fact_sequence_authority()") < bootstrap.index(
        "apply_gardens_field_authority()"
    )
    assert bootstrap.index("apply_gardens_field_authority()") < bootstrap.index(
        "_bind_final_browser_runtime_to_review()"
    )
    assert "apply_acm_icon_fact_authority()" in gardens
