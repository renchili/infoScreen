from __future__ import annotations

import sys
from types import SimpleNamespace

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime import artscience_preview_authority as artscience  # noqa: E402
from local_events_runtime import preview_collector_authority as preview  # noqa: E402


class Store:
    def __init__(self, root, source_id: str) -> None:
        self.root = root
        self._source_id = source_id

    def load(self):
        return SimpleNamespace(
            listing_pages=[
                SimpleNamespace(decision="confirmed", source_id=self._source_id),
            ]
        )


def test_only_artscience_temporary_preview_uses_source_authority(tmp_path) -> None:
    artscience_store = Store(tmp_path / "infoscreen-event-preview-artscience", "artscience")
    other_store = Store(tmp_path / "infoscreen-event-preview-other", "sciencecentre")
    persisted_store = Store(tmp_path / "review", "artscience")

    assert artscience._is_artscience_preview(artscience_store) is True
    assert artscience._is_artscience_preview(other_store) is False
    assert artscience._is_artscience_preview(persisted_store) is False


def test_artscience_wrapper_swaps_and_restores_single_pass_script(monkeypatch, tmp_path) -> None:
    store = Store(tmp_path / "infoscreen-event-preview-artscience", "artscience")
    generic_script = "generic-preview-script"
    observed: list[str] = []

    def base_collect(actual_store):
        assert actual_store is store
        observed.append(preview.PREVIEW_LISTING_JS)
        return "preview-state"

    monkeypatch.setattr(artscience, "_BASE_COLLECT", base_collect)
    monkeypatch.setattr(preview, "PREVIEW_LISTING_JS", generic_script)

    result = artscience.collect_event_candidates(store)

    assert result == "preview-state"
    assert observed == [artscience.ARTSCIENCE_PREVIEW_JS]
    assert preview.PREVIEW_LISTING_JS == generic_script


def test_non_artscience_preview_keeps_generic_script(monkeypatch, tmp_path) -> None:
    store = Store(tmp_path / "infoscreen-event-preview-sciencecentre", "sciencecentre")
    generic_script = "generic-preview-script"
    observed: list[str] = []

    def base_collect(actual_store):
        observed.append(preview.PREVIEW_LISTING_JS)
        return "preview-state"

    monkeypatch.setattr(artscience, "_BASE_COLLECT", base_collect)
    monkeypatch.setattr(preview, "PREVIEW_LISTING_JS", generic_script)

    assert artscience.collect_event_candidates(store) == "preview-state"
    assert observed == [generic_script]
    assert preview.PREVIEW_LISTING_JS == generic_script


def test_artscience_script_requires_positive_route_one_activity_and_rendered_title() -> None:
    script = artscience.ARTSCIENCE_PREVIEW_JS

    assert "/museum\\/(?:exhibitions|events|programmes|programs|experiences)" in script
    assert "activityAnchors(element)" in script
    assert "urls.size === 1 && urls.has(detailUrl)" in script
    assert "titleFrom(element, detailUrl)" in script
    assert "sameActivityAnchors(element, detailUrl)" in script
    assert "data-infoscreen-preview-index" in script
    assert "document.querySelectorAll(\"a[href]\")" not in script
    assert "root.querySelectorAll(\"a[href]\")" in script


def test_preview_pipeline_composes_artscience_before_transport() -> None:
    source = read_text(
        "surface/local_events_runtime/preview_final_detail_handoff_authority.py"
    )

    collector = source.index("apply_preview_collector()")
    artscience_apply = source.index("apply_artscience_preview()")
    transport = source.index("apply_preview_transport()")
    assert collector < artscience_apply < transport
