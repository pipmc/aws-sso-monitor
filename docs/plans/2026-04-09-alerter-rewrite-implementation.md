# Alerter Notification Rewrite Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace osascript notifications with vjeantet/alerter for actionable alert-style notifications with "Open SSO" click handling.

**Architecture:** Replace `_send_notification` in `app.py` with an alerter-based function that spawns the alerter binary in a background thread, reads stdout for click results, and opens the SSO URL on "Open SSO" click. Add `group` field to `PendingNotification` for notification deduplication.

**Tech Stack:** Python 3.13, subprocess, threading, vjeantet/alerter CLI

---

### Task 1: Add `group` field to `PendingNotification`

**Files:**
- Modify: `src/aws_sso_monitor/notifications.py:7-11`
- Test: `tests/test_notifications.py`

**Step 1: Write the failing test**

Create `tests/test_notifications.py`:

```python
import aws_sso_monitor.notifications as notifications


def test_pending_notification_has_group_field():
    notif = notifications.PendingNotification(
        title="AWS SSO Expiring Soon",
        message="Session 'dev' expires in 5 minutes",
        url="https://start.awsapps.com/start",
        group="dev",
    )
    assert notif.group == "dev"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/pip/Code/aws-sso-monitor && uv run pytest tests/test_notifications.py::test_pending_notification_has_group_field -v`
Expected: FAIL with `TypeError` — unexpected keyword argument `group`

**Step 3: Add `group` field to `PendingNotification`**

In `src/aws_sso_monitor/notifications.py`, change the `PendingNotification` dataclass (lines 7-11) to:

```python
@dataclasses.dataclass(frozen=True)
class PendingNotification:
    title: str
    message: str
    url: str
    group: str
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/pip/Code/aws-sso-monitor && uv run pytest tests/test_notifications.py::test_pending_notification_has_group_field -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_notifications.py src/aws_sso_monitor/notifications.py
git commit -m "feat: add group field to PendingNotification"
```

---

### Task 2: Set `group` in `NotificationTracker.check()`

**Files:**
- Modify: `src/aws_sso_monitor/notifications.py:34-66`
- Test: `tests/test_notifications.py`

**Step 1: Write the failing test**

Append to `tests/test_notifications.py`:

```python
import datetime

import aws_sso_monitor.sso as sso


def test_tracker_sets_group_to_session_name():
    tracker = notifications.NotificationTracker()
    session = sso.SSOSession(name="dev", start_url="https://start.awsapps.com/start", region="us-east-1")
    expires_at = datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=5)
    state = sso.SessionState(session=session, status=sso.SessionStatus.EXPIRING_SOON, expires_at=expires_at)

    pending = tracker.check([state])

    assert len(pending) == 1
    assert pending[0].group == "dev"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/pip/Code/aws-sso-monitor && uv run pytest tests/test_notifications.py::test_tracker_sets_group_to_session_name -v`
Expected: FAIL with `TypeError` — missing `group` argument in `PendingNotification()`

**Step 3: Add `group=name` to both `PendingNotification` constructors in `check()`**

In `src/aws_sso_monitor/notifications.py`, update the two `PendingNotification(...)` calls in the `check` method (lines 50-56 and 59-65):

First occurrence (expiring soon, ~line 50):
```python
                pending.append(
                    PendingNotification(
                        title="AWS SSO Expiring Soon",
                        message=f"Session '{name}' expires in {minutes} minutes",
                        url=state.session.start_url,
                        group=name,
                    )
                )
```

Second occurrence (expired, ~line 59):
```python
                pending.append(
                    PendingNotification(
                        title="AWS SSO Session Expired",
                        message=f"Session '{name}' has expired",
                        url=state.session.start_url,
                        group=name,
                    )
                )
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/pip/Code/aws-sso-monitor && uv run pytest tests/test_notifications.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/aws_sso_monitor/notifications.py tests/test_notifications.py
git commit -m "feat: set group to session name in NotificationTracker"
```

---

### Task 3: Replace `_send_notification` with alerter

**Files:**
- Modify: `src/aws_sso_monitor/app.py:1-8` (imports), `app.py:40-49` (`_send_notification`), `app.py:119-120` (`_fire_notification`)
- Test: `tests/test_app.py`

**Step 1: Write the failing test**

Create `tests/test_app.py`. We test that `_send_notification` builds the correct alerter command and spawns it. We mock `subprocess.Popen` and `threading.Thread` to avoid actually running alerter.

```python
import pathlib
import subprocess
import threading
import unittest.mock

import aws_sso_monitor.app as app
import aws_sso_monitor.notifications as notifications


def test_send_notification_builds_correct_alerter_command():
    notif = notifications.PendingNotification(
        title="AWS SSO Expiring Soon",
        message="Session 'dev' expires in 5 minutes",
        url="https://start.awsapps.com/start",
        group="dev",
    )

    with unittest.mock.patch.object(threading, "Thread") as mock_thread:
        mock_thread_instance = unittest.mock.MagicMock()
        mock_thread.return_value = mock_thread_instance

        app._send_notification(notif)

        mock_thread.assert_called_once()
        call_kwargs = mock_thread.call_args
        assert call_kwargs.kwargs["daemon"] is True
        mock_thread_instance.start.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/pip/Code/aws-sso-monitor && uv run pytest tests/test_app.py::test_send_notification_builds_correct_alerter_command -v`
Expected: FAIL — `_send_notification` still takes `title` and `message` string args, not a `PendingNotification`

**Step 3: Rewrite `_send_notification` and update `_fire_notification`**

In `src/aws_sso_monitor/app.py`:

Add `shutil` and `threading` to imports (top of file, lines 1-8). Replace the import block with:

```python
import datetime
import logging
import pathlib
import shutil
import subprocess
import threading
import webbrowser

import rumps

import aws_sso_monitor.icon as icon
import aws_sso_monitor.notifications as notifications
import aws_sso_monitor.sso as sso
```

Note: `Foundation` import is removed from the top level — it's only needed inside `_setup_screen_lock_observer`. Move it there (see step below).

Replace `_send_notification` (lines 40-49) with:

```python
def _send_notification(notif: notifications.PendingNotification) -> None:
    """Send a macOS notification via alerter with an 'Open SSO' action button."""
    cmd = [
        "alerter",
        "--message", notif.message,
        "--title", notif.title,
        "--closeLabel", "Dismiss",
        "--actions", "Open SSO",
        "--group", notif.group,
        "--sound", "default",
        "--appIcon", str(icon.NOTIFICATION_ICON_SAD),
    ]

    def _run() -> None:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.stdout.strip() == "Open SSO":
            webbrowser.open(notif.url)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
```

Update `_fire_notification` (line 119-120) to pass the full notification:

```python
    def _fire_notification(self, notif: notifications.PendingNotification) -> None:
        _send_notification(notif)
```

Move `Foundation` import inside `_setup_screen_lock_observer` (line 122) since it's only used there:

```python
    def _setup_screen_lock_observer(self) -> None:
        import Foundation

        center = Foundation.NSDistributedNotificationCenter.defaultCenter()
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/pip/Code/aws-sso-monitor && uv run pytest tests/test_app.py -v`
Expected: PASS

**Step 5: Run all tests**

Run: `cd /Users/pip/Code/aws-sso-monitor && uv run pytest -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add src/aws_sso_monitor/app.py tests/test_app.py
git commit -m "feat: replace osascript with alerter for notifications"
```

---

### Task 4: Add startup check for alerter binary

**Files:**
- Modify: `src/aws_sso_monitor/app.py:148-153` (`main()`)
- Test: `tests/test_app.py`

**Step 1: Write the failing test**

Append to `tests/test_app.py`:

```python
import shutil


def test_main_exits_if_alerter_not_found():
    with (
        unittest.mock.patch.object(shutil, "which", return_value=None),
        unittest.mock.patch.object(app, "SSOMonitorApp"),
    ):
        with pytest.raises(SystemExit) as exc_info:
            app.main()
        assert exc_info.value.code == 1


def test_main_starts_app_if_alerter_found():
    with (
        unittest.mock.patch.object(shutil, "which", return_value="/opt/homebrew/bin/alerter"),
        unittest.mock.patch.object(app, "SSOMonitorApp") as mock_app_cls,
    ):
        app.main()
        mock_app_cls.return_value.run.assert_called_once()
```

Add `import pytest` at the top of `tests/test_app.py`.

**Step 2: Run tests to verify they fail**

Run: `cd /Users/pip/Code/aws-sso-monitor && uv run pytest tests/test_app.py::test_main_exits_if_alerter_not_found tests/test_app.py::test_main_starts_app_if_alerter_found -v`
Expected: FAIL — `main()` doesn't check for alerter

**Step 3: Add startup check to `main()`**

In `src/aws_sso_monitor/app.py`, update `main()`:

```python
def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    if shutil.which("alerter") is None:
        print(
            "Error: 'alerter' not found. Install it with:\n"
            "  brew install vjeantet/tap/alerter"
        )
        raise SystemExit(1)
    SSOMonitorApp().run()
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/pip/Code/aws-sso-monitor && uv run pytest tests/test_app.py -v`
Expected: ALL PASS

**Step 5: Run full test suite**

Run: `cd /Users/pip/Code/aws-sso-monitor && uv run pytest -v`
Expected: ALL PASS

**Step 6: Run type checker and formatter**

Run: `cd /Users/pip/Code/aws-sso-monitor && uv run ruff check src/ tests/ && uv run ruff format src/ tests/ && uv run basedpyright src/`

**Step 7: Commit**

```bash
git add src/aws_sso_monitor/app.py tests/test_app.py
git commit -m "feat: check for alerter binary at startup"
```
