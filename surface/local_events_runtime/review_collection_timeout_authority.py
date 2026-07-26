from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from . import event_review as _review

_APPLIED = False
_BASE_COLLECT_EVENT_CANDIDATES = None
_CHILD_ENV = "INFOSCREEN_REVIEW_COLLECTION_CHILD"
_TIMEOUT_ENV = "INFOSCREEN_REVIEW_COLLECTION_TIMEOUT_SECONDS"
_DEFAULT_TIMEOUT_SECONDS = 600
_TERMINATE_GRACE_SECONDS = 5


class ReviewCollectionTimeout(TimeoutError):
    """Raised when the isolated Review collector exceeds its wall-clock budget."""


def timeout_seconds() -> int:
    try:
        configured = int(os.environ.get(_TIMEOUT_ENV, str(_DEFAULT_TIMEOUT_SECONDS)))
    except (TypeError, ValueError):
        configured = _DEFAULT_TIMEOUT_SECONDS
    return max(30, configured)


def _terminate_process_group(process: subprocess.Popen[str]) -> None:
    """Stop the worker and every Chromium descendant started in its session."""

    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (AttributeError, ProcessLookupError, PermissionError):
        process.terminate()

    try:
        process.wait(timeout=_TERMINATE_GRACE_SECONDS)
        return
    except subprocess.TimeoutExpired:
        pass

    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (AttributeError, ProcessLookupError, PermissionError):
        process.kill()
    process.wait(timeout=_TERMINATE_GRACE_SECONDS)


def _worker_command(
    store: _review.EventReviewStore,
    result_path: Path,
) -> tuple[list[str], dict[str, str], Path]:
    surface_dir = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment[_CHILD_ENV] = "1"
    command = [
        sys.executable,
        "-m",
        "local_events_runtime.review_collection_timeout_authority",
        "--worker",
        "--review-root",
        str(store.root),
        "--config-path",
        str(store.config_path),
        "--result-path",
        str(result_path),
    ]
    return command, environment, surface_dir


def _run_isolated_collection(
    store: _review.EventReviewStore,
    result_path: Path,
    timeout: int,
) -> None:
    command, environment, cwd = _worker_command(store, result_path)
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _terminate_process_group(process)
        raise ReviewCollectionTimeout(
            f"review_event_collection_timeout_after_{timeout}_seconds"
        ) from exc

    if process.returncode != 0:
        detail = " ".join((stderr or stdout or "").split())[-2000:]
        raise RuntimeError(
            "review_event_collection_worker_failed"
            + (f": {detail}" if detail else "")
        )
    if not result_path.is_file():
        raise RuntimeError("review_event_collection_worker_result_missing")


def collect_event_candidates(store: _review.EventReviewStore) -> _review.ReviewState:
    """Run the complete Review collection in a killable process boundary.

    Normal extraction semantics stay inside the worker. The parent only owns the hard
    wall-clock boundary, so a stuck Playwright or Chromium close cannot block the HTTP
    service forever. EventReviewStore writes are atomic; a killed worker therefore
    leaves the previous valid state intact unless it completed the final save.
    """

    result_path = store.root / f".collection-result.{os.getpid()}.{uuid.uuid4().hex}.json"
    try:
        _run_isolated_collection(store, result_path, timeout_seconds())
        return _review.ReviewState.model_validate_json(
            result_path.read_text(encoding="utf-8")
        )
    finally:
        try:
            result_path.unlink()
        except FileNotFoundError:
            pass


def _worker(review_root: str, config_path: str, result_path: str) -> int:
    """Execute the already-configured production collector inside the child process."""

    os.environ[_CHILD_ENV] = "1"
    from .http1_browser import apply as apply_runtime

    apply_runtime()
    store = _review.EventReviewStore(root=review_root, config_path=config_path)
    state = _review.collect_event_candidates(store)

    target = Path(result_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        state.model_dump_json(indent=2, exclude_none=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, target)
    return 0


def apply() -> None:
    """Install the process boundary only in the long-lived HTTP parent process."""

    global _APPLIED, _BASE_COLLECT_EVENT_CANDIDATES
    if _APPLIED:
        return
    if os.environ.get(_CHILD_ENV) == "1":
        _APPLIED = True
        return

    _BASE_COLLECT_EVENT_CANDIDATES = _review.collect_event_candidates
    _review.collect_event_candidates = collect_event_candidates
    _APPLIED = True


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--review-root")
    parser.add_argument("--config-path")
    parser.add_argument("--result-path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if not args.worker:
        raise SystemExit("worker mode is required")
    if not args.review_root or not args.config_path or not args.result_path:
        raise SystemExit("worker paths are required")
    return _worker(args.review_root, args.config_path, args.result_path)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ReviewCollectionTimeout",
    "apply",
    "collect_event_candidates",
    "main",
    "timeout_seconds",
    "_run_isolated_collection",
    "_terminate_process_group",
    "_worker",
]
