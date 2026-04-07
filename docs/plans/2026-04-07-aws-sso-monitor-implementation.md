# AWS SSO Session Monitor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a macOS menu bar app that monitors AWS SSO session expiry and sends native notifications.

**Architecture:** A `rumps` menu bar app that parses `~/.aws/config` for SSO sessions, polls `~/.aws/sso/cache/` every 5 minutes, and sends notifications via `NSUserNotification` when sessions expire. Screen lock awareness defers notifications until unlock.

**Tech Stack:** Python 3.13, uv, rumps, pyobjc (via rumps), Pillow (dev only for icon generation)

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/aws_sso_monitor/__init__.py`

**Step 1: Create pyproject.toml**

```toml
[project]
name = "aws-sso-monitor"
version = "0.1.0"
description = "macOS menu bar app that monitors AWS SSO session expiry"
requires-python = ">=3.13"
dependencies = [
    "rumps>=0.4.0",
]

[project.scripts]
aws-sso-monitor = "aws_sso_monitor.app:main"

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pillow>=11.0",
    "ruff>=0.9.0",
    "basedpyright>=1.20",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/aws_sso_monitor"]

[tool.ruff]
line-length = 100
src = ["src"]

[tool.basedpyright]
pythonVersion = "3.13"
typeCheckingMode = "standard"
venvPath = "."
venv = ".venv"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

**Step 2: Create empty `__init__.py`**

```python
```

(Empty file.)

**Step 3: Create directories and sync**

```bash
mkdir -p src/aws_sso_monitor tests
touch src/aws_sso_monitor/__init__.py
uv sync
```

Expected: lock file created, dependencies installed including rumps and pyobjc.

**Step 4: Commit**

```bash
git add pyproject.toml uv.lock src/aws_sso_monitor/__init__.py
git commit -m "feat: project scaffolding with uv and rumps"
```

---

### Task 2: SSO Config Parsing (TDD)

**Files:**
- Create: `tests/test_sso.py`
- Create: `src/aws_sso_monitor/sso.py`

**Step 1: Write the failing tests**

```python
import pathlib

import aws_sso_monitor.sso as sso


def test_parse_sso_sessions_single(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config"
    config.write_text(
        "[sso-session myorg]\n"
        "sso_start_url = https://myorg.awsapps.com/start\n"
        "sso_region = us-east-1\n"
        "\n"
        "[profile dev]\n"
        "sso_session = myorg\n"
        "sso_account_id = 123456\n"
    )
    sessions = sso.parse_sso_sessions(config)
    assert len(sessions) == 1
    assert sessions[0].name == "myorg"
    assert sessions[0].start_url == "https://myorg.awsapps.com/start"
    assert sessions[0].region == "us-east-1"


def test_parse_sso_sessions_multiple(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config"
    config.write_text(
        "[sso-session org1]\n"
        "sso_start_url = https://org1.awsapps.com/start\n"
        "sso_region = us-east-1\n"
        "\n"
        "[sso-session org2]\n"
        "sso_start_url = https://org2.awsapps.com/start\n"
        "sso_region = eu-west-1\n"
    )
    sessions = sso.parse_sso_sessions(config)
    assert len(sessions) == 2
    names = {s.name for s in sessions}
    assert names == {"org1", "org2"}


def test_parse_sso_sessions_no_sessions(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config"
    config.write_text("[profile dev]\nregion = us-east-1\n")
    sessions = sso.parse_sso_sessions(config)
    assert sessions == []


def test_parse_sso_sessions_missing_file(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "nonexistent"
    sessions = sso.parse_sso_sessions(config)
    assert sessions == []
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_sso.py -v
```

Expected: `ModuleNotFoundError` or `ImportError` — `sso` module doesn't exist yet.

**Step 3: Write minimal implementation**

Create `src/aws_sso_monitor/sso.py`:

```python
import configparser
import dataclasses
import pathlib

SSO_SESSION_PREFIX = "sso-session "


@dataclasses.dataclass(frozen=True)
class SSOSession:
    name: str
    start_url: str
    region: str


def parse_sso_sessions(config_path: pathlib.Path) -> list[SSOSession]:
    """Parse ~/.aws/config for [sso-session X] sections."""
    if not config_path.exists():
        return []

    parser = configparser.ConfigParser()
    parser.read(config_path)

    sessions: list[SSOSession] = []
    for section in parser.sections():
        if not section.startswith(SSO_SESSION_PREFIX):
            continue
        name = section[len(SSO_SESSION_PREFIX) :]
        sessions.append(
            SSOSession(
                name=name,
                start_url=parser.get(section, "sso_start_url"),
                region=parser.get(section, "sso_region"),
            )
        )
    return sessions
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_sso.py -v
```

Expected: all 4 tests PASS.

**Step 5: Commit**

```bash
git add src/aws_sso_monitor/sso.py tests/test_sso.py
git commit -m "feat: parse SSO sessions from AWS config"
```

---

### Task 3: SSO Cache Status Detection (TDD)

**Files:**
- Modify: `tests/test_sso.py` (append tests)
- Modify: `src/aws_sso_monitor/sso.py` (add types + function)

**Step 1: Write the failing tests**

Append to `tests/test_sso.py`:

```python
import datetime
import json


def _write_cache_file(
    cache_dir: pathlib.Path,
    filename: str,
    start_url: str,
    expires_at: datetime.datetime,
) -> None:
    (cache_dir / filename).write_text(
        json.dumps(
            {
                "startUrl": start_url,
                "accessToken": "fake-token",
                "expiresAt": expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "clientId": "fake-client",
                "clientSecret": "fake-secret",
            }
        )
    )


def _make_session(
    name: str = "myorg", start_url: str = "https://myorg.awsapps.com/start"
) -> sso.SSOSession:
    return sso.SSOSession(name=name, start_url=start_url, region="us-east-1")


def test_session_status_valid(tmp_path: pathlib.Path) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    now = datetime.datetime.now(datetime.UTC)
    _write_cache_file(cache_dir, "abc.json", "https://myorg.awsapps.com/start", now + datetime.timedelta(hours=2))

    states = sso.get_session_statuses([_make_session()], cache_dir, now=now)
    assert len(states) == 1
    assert states[0].status == sso.SessionStatus.VALID
    assert states[0].expires_at is not None


def test_session_status_expired(tmp_path: pathlib.Path) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    now = datetime.datetime.now(datetime.UTC)
    _write_cache_file(cache_dir, "abc.json", "https://myorg.awsapps.com/start", now - datetime.timedelta(hours=1))

    states = sso.get_session_statuses([_make_session()], cache_dir, now=now)
    assert states[0].status == sso.SessionStatus.EXPIRED


def test_session_status_expiring_soon(tmp_path: pathlib.Path) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    now = datetime.datetime.now(datetime.UTC)
    _write_cache_file(cache_dir, "abc.json", "https://myorg.awsapps.com/start", now + datetime.timedelta(minutes=5))

    states = sso.get_session_statuses([_make_session()], cache_dir, now=now)
    assert states[0].status == sso.SessionStatus.EXPIRING_SOON


def test_session_status_no_cache(tmp_path: pathlib.Path) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    states = sso.get_session_statuses([_make_session()], cache_dir)
    assert states[0].status == sso.SessionStatus.UNKNOWN


def test_ignores_client_registration_files(tmp_path: pathlib.Path) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    # Client registration: has clientId but no startUrl/accessToken
    (cache_dir / "client.json").write_text(
        json.dumps({"clientId": "abc", "clientSecret": "secret", "expiresAt": "2099-01-01T00:00:00Z"})
    )
    states = sso.get_session_statuses([_make_session()], cache_dir)
    assert states[0].status == sso.SessionStatus.UNKNOWN


def test_session_status_cache_dir_missing(tmp_path: pathlib.Path) -> None:
    cache_dir = tmp_path / "nonexistent"
    states = sso.get_session_statuses([_make_session()], cache_dir)
    assert states[0].status == sso.SessionStatus.UNKNOWN
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_sso.py -v
```

Expected: `AttributeError` — `SessionStatus`, `get_session_statuses` don't exist yet.

**Step 3: Write implementation**

Add to `src/aws_sso_monitor/sso.py`:

```python
import datetime
import enum
import json

EXPIRING_SOON_MINUTES = 10


class SessionStatus(enum.Enum):
    VALID = "valid"
    EXPIRING_SOON = "expiring_soon"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


@dataclasses.dataclass(frozen=True)
class SessionState:
    session: SSOSession
    status: SessionStatus
    expires_at: datetime.datetime | None


def get_session_statuses(
    sessions: list[SSOSession],
    cache_dir: pathlib.Path,
    now: datetime.datetime | None = None,
) -> list[SessionState]:
    """Check SSO cache files and classify each session's status."""
    if now is None:
        now = datetime.datetime.now(datetime.UTC)

    # Build a map of start_url -> (expires_at) from cache files
    cache_tokens: dict[str, datetime.datetime] = {}
    if cache_dir.exists():
        for cache_file in cache_dir.glob("*.json"):
            try:
                data = json.loads(cache_file.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            # Session tokens have startUrl + accessToken; client registrations don't
            if "startUrl" not in data or "accessToken" not in data:
                continue
            start_url = data["startUrl"]
            expires_at = datetime.datetime.fromisoformat(data["expiresAt"])
            # Keep the latest expiry if multiple files match
            if start_url not in cache_tokens or expires_at > cache_tokens[start_url]:
                cache_tokens[start_url] = expires_at

    states: list[SessionState] = []
    for session in sessions:
        expires_at = cache_tokens.get(session.start_url)
        if expires_at is None:
            states.append(SessionState(session=session, status=SessionStatus.UNKNOWN, expires_at=None))
            continue

        remaining = expires_at - now
        if remaining.total_seconds() <= 0:
            status = SessionStatus.EXPIRED
        elif remaining.total_seconds() <= EXPIRING_SOON_MINUTES * 60:
            status = SessionStatus.EXPIRING_SOON
        else:
            status = SessionStatus.VALID

        states.append(SessionState(session=session, status=status, expires_at=expires_at))

    return states
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_sso.py -v
```

Expected: all 10 tests PASS.

**Step 5: Commit**

```bash
git add src/aws_sso_monitor/sso.py tests/test_sso.py
git commit -m "feat: detect SSO session expiry from cache files"
```

---

### Task 4: Notification Tracker (TDD)

A pure-logic class that decides which notifications to send, with no rumps dependency. This makes the notification-once-per-event logic fully testable.

**Files:**
- Create: `src/aws_sso_monitor/notifications.py`
- Create: `tests/test_notifications.py`

**Step 1: Write the failing tests**

```python
import datetime

import aws_sso_monitor.notifications as notifications
import aws_sso_monitor.sso as sso


def _make_state(
    name: str = "myorg",
    status: sso.SessionStatus = sso.SessionStatus.VALID,
    expires_at: datetime.datetime | None = None,
    start_url: str = "https://myorg.awsapps.com/start",
) -> sso.SessionState:
    session = sso.SSOSession(name=name, start_url=start_url, region="us-east-1")
    return sso.SessionState(session=session, status=status, expires_at=expires_at)


def test_no_notification_when_valid() -> None:
    tracker = notifications.NotificationTracker()
    state = _make_state(status=sso.SessionStatus.VALID, expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=2))
    pending = tracker.check([state])
    assert pending == []


def test_expired_fires_once() -> None:
    tracker = notifications.NotificationTracker()
    state = _make_state(status=sso.SessionStatus.EXPIRED, expires_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1))

    first = tracker.check([state])
    assert len(first) == 1
    assert "expired" in first[0].title.lower()

    second = tracker.check([state])
    assert second == []


def test_expiring_soon_fires_once() -> None:
    tracker = notifications.NotificationTracker()
    state = _make_state(status=sso.SessionStatus.EXPIRING_SOON, expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=5))

    first = tracker.check([state])
    assert len(first) == 1
    assert "expiring" in first[0].title.lower()

    second = tracker.check([state])
    assert second == []


def test_reauth_resets_state() -> None:
    tracker = notifications.NotificationTracker()
    old_expiry = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1)
    new_expiry = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=8)

    # Expire the session
    expired_state = _make_state(status=sso.SessionStatus.EXPIRED, expires_at=old_expiry)
    tracker.check([expired_state])

    # Re-auth: new expiry time, valid status
    valid_state = _make_state(status=sso.SessionStatus.VALID, expires_at=new_expiry)
    pending = tracker.check([valid_state])
    assert pending == []

    # Now expire again — should fire a new notification
    re_expired = _make_state(status=sso.SessionStatus.EXPIRED, expires_at=new_expiry)
    pending = tracker.check([re_expired])
    assert len(pending) == 1


def test_expiring_then_expired_fires_both() -> None:
    tracker = notifications.NotificationTracker()
    expiry = datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=5)

    expiring = _make_state(status=sso.SessionStatus.EXPIRING_SOON, expires_at=expiry)
    pending = tracker.check([expiring])
    assert len(pending) == 1

    expired = _make_state(status=sso.SessionStatus.EXPIRED, expires_at=expiry)
    pending = tracker.check([expired])
    assert len(pending) == 1


def test_notification_contains_url() -> None:
    tracker = notifications.NotificationTracker()
    state = _make_state(status=sso.SessionStatus.EXPIRED, expires_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1))
    pending = tracker.check([state])
    assert pending[0].url == "https://myorg.awsapps.com/start"


def test_unknown_status_no_notification() -> None:
    tracker = notifications.NotificationTracker()
    state = _make_state(status=sso.SessionStatus.UNKNOWN, expires_at=None)
    pending = tracker.check([state])
    assert pending == []
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_notifications.py -v
```

Expected: `ModuleNotFoundError` — `notifications` module doesn't exist.

**Step 3: Write implementation**

Create `src/aws_sso_monitor/notifications.py`:

```python
import dataclasses

import aws_sso_monitor.sso as sso


@dataclasses.dataclass(frozen=True)
class PendingNotification:
    title: str
    message: str
    url: str


@dataclasses.dataclass
class _TrackedSession:
    last_expires_at: str
    notified_expiring: bool = False
    notified_expired: bool = False


class NotificationTracker:
    """Tracks which sessions have been notified to avoid repeats."""

    def __init__(self) -> None:
        self._state: dict[str, _TrackedSession] = {}

    def check(self, states: list[sso.SessionState]) -> list[PendingNotification]:
        """Return notifications that should be sent, updating internal state."""
        pending: list[PendingNotification] = []

        for state in states:
            name = state.session.name
            expires_key = state.expires_at.isoformat() if state.expires_at else ""

            tracked = self._state.get(name)
            if tracked is None or tracked.last_expires_at != expires_key:
                tracked = _TrackedSession(last_expires_at=expires_key)
                self._state[name] = tracked

            if state.status == sso.SessionStatus.EXPIRING_SOON and not tracked.notified_expiring:
                tracked.notified_expiring = True
                pending.append(
                    PendingNotification(
                        title="AWS SSO Expiring Soon",
                        message=f"Session '{name}' is expiring soon",
                        url=state.session.start_url,
                    )
                )
            elif state.status == sso.SessionStatus.EXPIRED and not tracked.notified_expired:
                tracked.notified_expired = True
                pending.append(
                    PendingNotification(
                        title="AWS SSO Session Expired",
                        message=f"Session '{name}' has expired",
                        url=state.session.start_url,
                    )
                )

        return pending
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_notifications.py -v
```

Expected: all 7 tests PASS.

**Step 5: Commit**

```bash
git add src/aws_sso_monitor/notifications.py tests/test_notifications.py
git commit -m "feat: notification tracker with once-per-event logic"
```

---

### Task 5: Sad AWS Icon Generation

**Files:**
- Create: `scripts/generate_icons.py`
- Create: `src/aws_sso_monitor/resources/` (directory with generated PNGs)
- Create: `src/aws_sso_monitor/icon.py`

**Step 1: Create the icon generation script**

Create `scripts/generate_icons.py`:

```python
#!/usr/bin/env python3
"""Generate sad AWS logo icons (frown instead of smile)."""
import math
import pathlib

from PIL import Image, ImageDraw, ImageFont

RESOURCES_DIR = pathlib.Path(__file__).parent.parent / "src" / "aws_sso_monitor" / "resources"
AWS_ORANGE = (255, 153, 0)
AWS_DARK = (35, 47, 62)


def _draw_frown(
    draw: ImageDraw.ImageDraw,
    center: tuple[float, float],
    rx: float,
    ry: float,
    color: tuple[int, ...] | str,
    line_width: int,
) -> None:
    """Draw a frown arc (inverted AWS smile) with arrowhead."""
    cx, cy = center
    bbox = (cx - rx, cy - ry, cx + rx, cy + ry)
    # Arc from 200 to 340 degrees traces the upper portion of the ellipse = frown
    draw.arc(bbox, 200, 340, fill=color, width=line_width)

    # Arrowhead at the 340-degree end
    end_rad = math.radians(340)
    tip_x = cx + rx * math.cos(end_rad)
    tip_y = cy + ry * math.sin(end_rad)

    # Tangent direction (perpendicular to radius, clockwise)
    tangent = end_rad + math.pi / 2
    size = line_width * 2.5
    p1 = (tip_x + size * math.cos(tangent + 0.5), tip_y + size * math.sin(tangent + 0.5))
    p2 = (tip_x + size * math.cos(tangent - 0.5), tip_y + size * math.sin(tangent - 0.5))
    draw.polygon([(tip_x, tip_y), p1, p2], fill=color)


def generate_menubar_icon() -> None:
    """44x44 monochrome template icon for the macOS menu bar."""
    size = 44
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # "aws" text, small, upper portion
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 14)
    except OSError:
        font = ImageFont.load_default()
    text_bbox = draw.textbbox((0, 0), "aws", font=font)
    text_w = text_bbox[2] - text_bbox[0]
    draw.text(((size - text_w) / 2, 4), "aws", fill="black", font=font)

    # Frown below text
    _draw_frown(draw, (size / 2, size * 0.72), size * 0.32, size * 0.18, "black", 2)

    RESOURCES_DIR.mkdir(parents=True, exist_ok=True)
    img.save(RESOURCES_DIR / "menubar-icon.png")
    print(f"  Created menubar-icon.png ({size}x{size})")


def generate_notification_icon() -> None:
    """256x256 color icon for notifications."""
    size = 256
    img = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)

    # "aws" text, large, centered upper portion
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 72)
    except OSError:
        font = ImageFont.load_default(72)
    text_bbox = draw.textbbox((0, 0), "aws", font=font)
    text_w = text_bbox[2] - text_bbox[0]
    draw.text(((size - text_w) / 2, size * 0.12), "aws", fill=AWS_DARK, font=font)

    # Orange frown
    _draw_frown(draw, (size / 2, size * 0.72), size * 0.3, size * 0.13, AWS_ORANGE, 8)

    RESOURCES_DIR.mkdir(parents=True, exist_ok=True)
    img.save(RESOURCES_DIR / "notification-icon.png")
    print(f"  Created notification-icon.png ({size}x{size})")


if __name__ == "__main__":
    print("Generating sad AWS icons...")
    generate_menubar_icon()
    generate_notification_icon()
    print(f"Done. Icons in {RESOURCES_DIR}")
```

**Step 2: Run the generation script**

```bash
uv run python scripts/generate_icons.py
```

Expected: two PNG files created in `src/aws_sso_monitor/resources/`.

**Step 3: Verify the icons visually**

```bash
open src/aws_sso_monitor/resources/notification-icon.png
open src/aws_sso_monitor/resources/menubar-icon.png
```

Check that they show "aws" text with an upside-down smile (frown) underneath. The menu bar icon should be black-on-transparent. The notification icon should have dark text with an orange frown on white background.

If the icons need visual adjustment, tweak the coordinates in `generate_icons.py` and re-run.

**Step 4: Create icon.py module**

Create `src/aws_sso_monitor/icon.py`:

```python
"""Paths to icon resources."""
import pathlib

_RESOURCES = pathlib.Path(__file__).parent / "resources"

MENUBAR_ICON = _RESOURCES / "menubar-icon.png"
NOTIFICATION_ICON = _RESOURCES / "notification-icon.png"
```

**Step 5: Commit**

```bash
git add scripts/generate_icons.py src/aws_sso_monitor/icon.py src/aws_sso_monitor/resources/
git commit -m "feat: sad AWS logo icons for menu bar and notifications"
```

---

### Task 6: Menu Bar App with Timer, Notifications, and Screen Lock

This is the main integration task. The rumps app wires everything together.

**Files:**
- Create: `src/aws_sso_monitor/app.py`

**Step 1: Write the app**

Create `src/aws_sso_monitor/app.py`:

```python
"""macOS menu bar app that monitors AWS SSO session expiry."""
import datetime
import pathlib
import webbrowser

import rumps

import aws_sso_monitor.icon as icon
import aws_sso_monitor.notifications as notifications
import aws_sso_monitor.sso as sso

CONFIG_PATH = pathlib.Path.home() / ".aws" / "config"
CACHE_DIR = pathlib.Path.home() / ".aws" / "sso" / "cache"
CHECK_INTERVAL_SECONDS = 300  # 5 minutes


def _format_status(state: sso.SessionState) -> str:
    name = state.session.name
    if state.status == sso.SessionStatus.EXPIRED:
        return f"{name}: EXPIRED"
    if state.status == sso.SessionStatus.UNKNOWN:
        return f"{name}: no session"
    if state.expires_at is None:
        return f"{name}: unknown"
    remaining = state.expires_at - datetime.datetime.now(datetime.UTC)
    total_minutes = max(0, int(remaining.total_seconds()) // 60)
    if total_minutes >= 60:
        hours = total_minutes // 60
        mins = total_minutes % 60
        return f"{name}: {hours}h {mins}m remaining"
    return f"{name}: {total_minutes}m remaining"


class SSOMonitorApp(rumps.App):
    def __init__(self) -> None:
        super().__init__(
            "AWS SSO Monitor",
            icon=str(icon.MENUBAR_ICON),
            template=True,
            quit_button="Quit",
        )
        self.menu = [rumps.MenuItem("Check Now", callback=self._on_check_now)]
        self._tracker = notifications.NotificationTracker()
        self._screen_locked = False
        self._queued: list[notifications.PendingNotification] = []
        self._setup_screen_lock_observer()
        # Run initial check shortly after launch
        rumps.Timer(self._on_initial_check, 2).start()

    def _on_initial_check(self, timer: rumps.Timer) -> None:
        timer.stop()
        self._do_check()

    @rumps.timer(CHECK_INTERVAL_SECONDS)
    def _periodic_check(self, _timer: rumps.Timer) -> None:
        self._do_check()

    def _on_check_now(self, _sender: rumps.MenuItem) -> None:
        self._do_check()

    def _do_check(self) -> None:
        sessions = sso.parse_sso_sessions(CONFIG_PATH)
        states = sso.get_session_statuses(sessions, CACHE_DIR)
        self._rebuild_menu(states)
        pending = self._tracker.check(states)
        for notif in pending:
            self._send_notification(notif)

    def _rebuild_menu(self, states: list[sso.SessionState]) -> None:
        self.menu.clear()
        for state in states:
            self.menu.add(rumps.MenuItem(_format_status(state)))
        self.menu.add(None)  # separator
        self.menu.add(rumps.MenuItem("Check Now", callback=self._on_check_now))

    def _send_notification(self, notif: notifications.PendingNotification) -> None:
        if self._screen_locked:
            self._queued.append(notif)
        else:
            self._fire_notification(notif)

    def _fire_notification(self, notif: notifications.PendingNotification) -> None:
        rumps.notification(
            title=notif.title,
            subtitle="",
            message=notif.message,
            data={"url": notif.url},
            icon=str(icon.NOTIFICATION_ICON),
        )

    @rumps.notifications
    def _on_notification_click(self, notification: rumps.Notification) -> None:
        url = notification.data.get("url") if notification.data else None
        if url:
            webbrowser.open(url)

    def _setup_screen_lock_observer(self) -> None:
        import Foundation

        center = Foundation.NSDistributedNotificationCenter.defaultCenter()
        center.addObserverForName_object_queue_usingBlock_(
            "com.apple.screenIsLocked",
            None,
            Foundation.NSOperationQueue.mainQueue(),
            lambda _: self._on_screen_locked(),
        )
        center.addObserverForName_object_queue_usingBlock_(
            "com.apple.screenIsUnlocked",
            None,
            Foundation.NSOperationQueue.mainQueue(),
            lambda _: self._on_screen_unlocked(),
        )

    def _on_screen_locked(self) -> None:
        self._screen_locked = True

    def _on_screen_unlocked(self) -> None:
        self._screen_locked = False
        queued = self._queued.copy()
        self._queued.clear()
        for notif in queued:
            self._fire_notification(notif)


def main() -> None:
    SSOMonitorApp().run()
```

**Step 2: Test the app manually**

```bash
uv run aws-sso-monitor
```

Expected:
- Sad AWS icon appears in the menu bar
- Clicking it shows session statuses, a separator, "Check Now", and "Quit"
- If your SSO session is expired, a notification should appear
- Clicking the notification should open the SSO start URL in your browser
- "Check Now" should force a refresh of the status display
- "Quit" should exit the app

**Step 3: Commit**

```bash
git add src/aws_sso_monitor/app.py
git commit -m "feat: rumps menu bar app with notifications and screen lock"
```

---

### Task 7: LaunchAgent Plist

**Files:**
- Create: `systems.intelligible.aws-sso-monitor.plist`

**Step 1: Determine uv path**

```bash
which uv
```

Note the output (likely `/opt/homebrew/bin/uv`). Use this in the plist below.

**Step 2: Create the plist**

Create `systems.intelligible.aws-sso-monitor.plist` (adjust the uv path if `which uv` returned something different):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>systems.intelligible.aws-sso-monitor</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/bin/uv</string>
        <string>run</string>
        <string>--project</string>
        <string>/Users/pip/Code/aws-sso-monitor</string>
        <string>aws-sso-monitor</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>StandardOutPath</key>
    <string>/tmp/aws-sso-monitor.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/aws-sso-monitor.stderr.log</string>
</dict>
</plist>
```

**Step 3: Commit**

```bash
git add systems.intelligible.aws-sso-monitor.plist
git commit -m "feat: launchd plist for login startup"
```

---

### Task 8: Format, Lint, Type-Check, Final Test

**Step 1: Format with ruff**

```bash
uv run ruff format src/ tests/ scripts/
```

**Step 2: Lint with ruff**

```bash
uv run ruff check src/ tests/ scripts/ --fix
```

Fix any issues reported.

**Step 3: Type-check with basedpyright**

```bash
uv run basedpyright src/
```

Fix any type errors. Common issues to expect:
- `rumps.Notification` type might not be in stubs — may need a `type: ignore[attr-defined]` on the notification data access if pyobjc stubs are incomplete. Investigate the actual type before resorting to this.
- `Foundation` module might lack stubs — investigate what pyobjc provides.

**Step 4: Run all tests**

```bash
uv run pytest -v
```

Expected: all tests PASS.

**Step 5: Commit any fixes**

```bash
git add -A
git commit -m "chore: formatting, lint, and type fixes"
```

---

### Task 9: Install and Verify LaunchAgent

**Step 1: Copy and load the LaunchAgent**

```bash
cp systems.intelligible.aws-sso-monitor.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/systems.intelligible.aws-sso-monitor.plist
```

**Step 2: Verify it's running**

```bash
launchctl list | grep aws-sso
```

Expected: shows the label with a PID.

**Step 3: Check logs**

```bash
cat /tmp/aws-sso-monitor.stderr.log
```

Expected: no errors.

**Step 4: Verify menu bar icon is visible**

Check the macOS menu bar for the sad AWS icon. Click it and verify the menu shows your SSO session status.

**Step 5: Test notification click**

If your session is expired, a notification should have appeared. Click it and verify it opens the SSO start URL in your browser.

If the session is valid, you can test by temporarily modifying the `EXPIRING_SOON_MINUTES` constant to a large value and clicking "Check Now", or by waiting for the session to naturally expire.
