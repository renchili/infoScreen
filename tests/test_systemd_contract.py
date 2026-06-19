from __future__ import annotations

from pathlib import Path


UNIT = Path("deploy/systemd/infoscreen-http.service")
DOC = Path("docs/engineering-quality.md")


def test_systemd_unit_template_exists() -> None:
    assert UNIT.is_file(), "deploy/systemd/infoscreen-http.service is required"


def test_systemd_unit_uses_expected_runtime_contract() -> None:
    text = UNIT.read_text(encoding="utf-8")

    assert "WorkingDirectory=%h/infoscreen" in text
    assert "ExecStart=/usr/bin/python3 %h/infoscreen/serve_infoscreen.py" in text
    assert "Restart=always" in text
    assert "python3 -m http.server" not in text


def test_docs_define_surface_as_simulation_not_ci_runner() -> None:
    text = DOC.read_text(encoding="utf-8").lower()

    assert "surface" in text
    assert "simulation" in text
    assert "not a ci runner" in text
    assert "systemctl" in text
    assert "docker" in text
