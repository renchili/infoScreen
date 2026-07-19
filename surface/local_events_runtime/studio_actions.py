from __future__ import annotations

from typing import Any, Iterable

from .studio_rules import BrowserActionRule


class StudioActionError(RuntimeError):
    """Raised when a required recorded browser action cannot be replayed."""


def settle_page(page: Any, wait_ms: int) -> None:
    """Wait for navigation/network settling, then fall back to a fixed delay."""

    try:
        page.wait_for_load_state(
            "networkidle",
            timeout=max(1000, wait_ms + 1000),
        )
    except Exception:
        if wait_ms:
            page.wait_for_timeout(wait_ms)


def execute_browser_actions(
    page: Any,
    actions: Iterable[BrowserActionRule],
) -> list[dict[str, Any]]:
    """Replay validated operator actions and return per-action diagnostic rows."""

    diagnostics: list[dict[str, Any]] = []
    for index, action in enumerate(actions):
        row: dict[str, Any] = {
            "index": index,
            "action": action.action,
            "selector": action.selector,
            "optional": action.optional,
            "ok": False,
        }
        try:
            if action.action == "scroll_to_bottom":
                page.evaluate(
                    """
                    async () => {
                      const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
                      let previous = -1;
                      for (let round = 0; round < 30; round += 1) {
                        const height = Math.max(
                          document.documentElement.scrollHeight,
                          document.body?.scrollHeight || 0
                        );
                        window.scrollTo(0, height);
                        await pause(180);
                        const next = Math.max(
                          document.documentElement.scrollHeight,
                          document.body?.scrollHeight || 0
                        );
                        if (next === previous || next === height) break;
                        previous = next;
                      }
                    }
                    """
                )
                settle_page(page, action.wait_ms)
                row["ok"] = True
                diagnostics.append(row)
                continue

            if action.action == "wait":
                page.wait_for_timeout(action.wait_ms)
                row["ok"] = True
                diagnostics.append(row)
                continue

            locator = page.locator(str(action.selector)).first
            if locator.count() <= 0:
                if action.optional:
                    row.update(
                        {
                            "ok": True,
                            "skipped": True,
                            "reason": "optional_target_missing",
                        }
                    )
                    diagnostics.append(row)
                    continue
                raise StudioActionError(
                    f"action_target_missing:{action.selector}"
                )

            if action.action == "select_option":
                locator.select_option(value=action.value, timeout=5000)
                settle_page(page, action.wait_ms)
                row["ok"] = True
                diagnostics.append(row)
                continue

            if action.action == "click":
                if not locator.is_visible() or not locator.is_enabled():
                    if action.optional:
                        row.update(
                            {
                                "ok": True,
                                "skipped": True,
                                "reason": "optional_target_unavailable",
                            }
                        )
                        diagnostics.append(row)
                        continue
                    raise StudioActionError(
                        f"action_target_unavailable:{action.selector}"
                    )
                locator.click(timeout=5000)
                settle_page(page, action.wait_ms)
                row.update({"ok": True, "rounds": 1})
                diagnostics.append(row)
                continue

            if action.action == "click_repeat":
                rounds = 0
                for _ in range(action.max_rounds):
                    locator = page.locator(str(action.selector)).first
                    if (
                        locator.count() <= 0
                        or not locator.is_visible()
                        or not locator.is_enabled()
                    ):
                        break
                    locator.click(timeout=5000)
                    rounds += 1
                    settle_page(page, action.wait_ms)
                if rounds == 0 and not action.optional:
                    raise StudioActionError(
                        f"repeat_action_never_clicked:{action.selector}"
                    )
                row.update(
                    {
                        "ok": True,
                        "rounds": rounds,
                        "skipped": rounds == 0,
                    }
                )
                diagnostics.append(row)
                continue

            raise StudioActionError(f"unsupported_action:{action.action}")
        except Exception as exc:
            row.update(
                {
                    "error": type(exc).__name__,
                    "detail": str(exc)[:300],
                }
            )
            diagnostics.append(row)
            if not action.optional:
                raise StudioActionError(
                    f"action_{index}_{action.action}_failed:{str(exc)[:300]}"
                ) from exc
    return diagnostics


__all__ = [
    "StudioActionError",
    "execute_browser_actions",
    "settle_page",
]
