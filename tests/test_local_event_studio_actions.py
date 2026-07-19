from __future__ import annotations

import pytest

from surface.local_events_runtime.studio_actions import (
    StudioActionError,
    execute_browser_actions,
)
from surface.local_events_runtime.studio_rules import BrowserActionRule

pytestmark = pytest.mark.backend


class FakeLocator:
    def __init__(
        self,
        *,
        present: bool = True,
        visible: bool = True,
        enabled: bool = True,
        disappear_after: int | None = None,
    ) -> None:
        self.present = present
        self.visible = visible
        self.enabled = enabled
        self.disappear_after = disappear_after
        self.clicks = 0
        self.selected: list[str | None] = []

    @property
    def first(self) -> "FakeLocator":
        return self

    def count(self) -> int:
        return 1 if self.present else 0

    def is_visible(self) -> bool:
        return self.present and self.visible

    def is_enabled(self) -> bool:
        return self.present and self.enabled

    def click(self, timeout: int) -> None:
        assert timeout == 5000
        self.clicks += 1
        if self.disappear_after is not None and self.clicks >= self.disappear_after:
            self.present = False

    def select_option(self, *, value: str | None, timeout: int) -> None:
        assert timeout == 5000
        self.selected.append(value)


class FakePage:
    def __init__(self, locators: dict[str, FakeLocator] | None = None) -> None:
        self.locators = locators or {}
        self.waits: list[int] = []
        self.evaluations = 0

    def locator(self, selector: str) -> FakeLocator:
        return self.locators.setdefault(selector, FakeLocator(present=False))

    def wait_for_load_state(self, state: str, timeout: int) -> None:
        assert state == "networkidle"
        raise RuntimeError("fixture has no network lifecycle")

    def wait_for_timeout(self, wait_ms: int) -> None:
        self.waits.append(wait_ms)

    def evaluate(self, script: str) -> None:
        assert "scrollTo" in script
        self.evaluations += 1


def action(payload: dict) -> BrowserActionRule:
    return BrowserActionRule.model_validate(payload)


def test_replays_click_select_scroll_and_wait_actions() -> None:
    accept = FakeLocator()
    select = FakeLocator()
    page = FakePage({"button.accept": accept, "select.genre": select})

    diagnostics = execute_browser_actions(
        page,
        [
            action(
                {
                    "action": "click",
                    "selector": "button.accept",
                    "wait_ms": 100,
                }
            ),
            action(
                {
                    "action": "select_option",
                    "selector": "select.genre",
                    "value": "music",
                    "wait_ms": 200,
                }
            ),
            action({"action": "scroll_to_bottom", "wait_ms": 300}),
            action({"action": "wait", "wait_ms": 400}),
        ],
    )

    assert all(row["ok"] for row in diagnostics)
    assert accept.clicks == 1
    assert select.selected == ["music"]
    assert page.evaluations == 1
    assert page.waits == [100, 200, 300, 400]


def test_repeat_click_stops_when_target_disappears() -> None:
    load_more = FakeLocator(disappear_after=3)
    page = FakePage({"button.more": load_more})

    diagnostics = execute_browser_actions(
        page,
        [
            action(
                {
                    "action": "click_repeat",
                    "selector": "button.more",
                    "max_rounds": 20,
                    "wait_ms": 50,
                }
            )
        ],
    )

    assert load_more.clicks == 3
    assert diagnostics[0]["rounds"] == 3


def test_optional_missing_action_is_skipped_but_required_action_fails() -> None:
    page = FakePage()

    optional = execute_browser_actions(
        page,
        [
            action(
                {
                    "action": "click",
                    "selector": "button.cookie",
                    "optional": True,
                }
            )
        ],
    )
    assert optional[0]["ok"] is True
    assert optional[0]["skipped"] is True

    with pytest.raises(StudioActionError, match="action_target_missing"):
        execute_browser_actions(
            page,
            [action({"action": "click", "selector": "button.required"})],
        )
