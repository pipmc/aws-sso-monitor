# macOS App Bundle Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Bundle aws-sso-monitor as a signed macOS `.app` with a `.pkg` installer, replacing the alerter CLI with the desktop-notifier library.

**Architecture:** Replace the alerter subprocess with `desktop_notifier.DesktopNotifierSync` for native macOS notifications with action buttons. Bundle the app with py2app, sign with codesign, and package with pkgbuild. The app fails fast if not running as a `.app` bundle.

**Tech Stack:** Python 3.13, desktop-notifier, rumps, py2app, pkgbuild, codesign

---

### Task 1: Update dependencies and .gitignore

**Files:**
- Modify: `pyproject.toml`
- Modify: `.gitignore`

**Step 1: Add desktop-notifier to runtime dependencies**

In `pyproject.toml`, change the `dependencies` list (line 6-9) to:

```toml
dependencies = [
    "rumps>=0.4",
    "pyobjc-framework-Cocoa>=10.0",
    "desktop-notifier>=6.0",
]
```

**Step 2: Add py2app to dev dependencies**

In `pyproject.toml`, change the `dev` dependency group (lines 12-17) to:

```toml
[dependency-groups]
dev = [
    "pytest>=8.0",
    "pillow>=11.0",
    "ruff>=0.9.0",
    "basedpyright>=1.20",
    "py2app>=0.28",
]
```

**Step 3: Add build/ to .gitignore**

Append to `.gitignore`:

```
build/
dist/
```

**Step 4: Install dependencies**

Run: `cd /Users/pip/Code/aws-sso-monitor && uv sync`

**Step 5: Commit**

```bash
git add pyproject.toml uv.lock .gitignore
git commit -m "chore: add desktop-notifier and py2app dependencies"
```

---

### Task 2: Replace _send_notification with desktop-notifier

**Files:**
- Modify: `src/aws_sso_monitor/app.py:3-9` (imports), `app.py:41-66` (`_send_notification`)
- Rewrite: `tests/test_app.py` (first two tests)

**Step 1: Write the failing tests**

Replace the entire contents of `tests/test_app.py` with:

```python
import unittest.mock
import webbrowser

import pytest

import aws_sso_monitor.app as app
import aws_sso_monitor.notifications as notifications


def test_send_notification_calls_desktop_notifier():
    notif = notifications.PendingNotification(
        title="AWS SSO Expiring Soon",
        message="Session 'dev' expires in 5 minutes",
        url="https://start.awsapps.com/start",
        group="dev",
    )

    with unittest.mock.patch.object(app._notifier, "send") as mock_send:
        app._send_notification(notif)

        mock_send.assert_called_once()
        kwargs = mock_send.call_args.kwargs
        assert kwargs["title"] == "AWS SSO Expiring Soon"
        assert kwargs["message"] == "Session 'dev' expires in 5 minutes"
        assert kwargs["thread"] == "dev"
        assert len(kwargs["buttons"]) == 1
        assert kwargs["buttons"][0].title == "Open SSO"
        assert kwargs["sound"] is not None


def test_send_notification_button_opens_url():
    notif = notifications.PendingNotification(
        title="AWS SSO Expired",
        message="Session 'prod' has expired",
        url="https://my-sso.awsapps.com/start",
        group="prod",
    )

    with unittest.mock.patch.object(app._notifier, "send") as mock_send:
        app._send_notification(notif)
        button = mock_send.call_args.kwargs["buttons"][0]

    with unittest.mock.patch.object(webbrowser, "open") as mock_open:
        button.on_pressed()
        mock_open.assert_called_once_with("https://my-sso.awsapps.com/start")


def test_main_exits_if_alerter_not_found():
    import shutil

    with (
        unittest.mock.patch.object(shutil, "which", return_value=None),
        unittest.mock.patch.object(app, "SSOMonitorApp"),
    ):
        with pytest.raises(SystemExit) as exc_info:
            app.main()
        assert exc_info.value.code == 1


def test_main_starts_app_if_alerter_found():
    import shutil

    with (
        unittest.mock.patch.object(shutil, "which", return_value="/opt/homebrew/bin/alerter"),
        unittest.mock.patch.object(app, "SSOMonitorApp") as mock_app_cls,
    ):
        app.main()
        mock_app_cls.return_value.run.assert_called_once()
```

**Step 2: Run tests to verify the first two fail**

Run: `cd /Users/pip/Code/aws-sso-monitor && uv run pytest tests/test_app.py::test_send_notification_calls_desktop_notifier tests/test_app.py::test_send_notification_button_opens_url -v`
Expected: FAIL with `AttributeError: module 'aws_sso_monitor.app' has no attribute '_notifier'`

**Step 3: Replace imports and _send_notification in app.py**

In `src/aws_sso_monitor/app.py`, replace the imports (lines 3-9) with:

```python
import datetime
import logging
import pathlib
import shutil
import webbrowser

import desktop_notifier
import rumps
```

Note: `subprocess` and `threading` are removed. `desktop_notifier` is added. `shutil` is kept (still used by the alerter startup check until Task 3).

Then replace `_send_notification` (lines 41-66) with:

```python
_notifier = desktop_notifier.DesktopNotifierSync(app_name="AWS SSO Monitor")


def _send_notification(notif: notifications.PendingNotification) -> None:
    """Send a macOS notification with an 'Open SSO' action button."""
    _notifier.send(
        title=notif.title,
        message=notif.message,
        buttons=[
            desktop_notifier.Button(
                title="Open SSO",
                on_pressed=lambda: webbrowser.open(notif.url),
            ),
        ],
        sound=desktop_notifier.DEFAULT_SOUND,
        thread=notif.group,
    )
```

**Step 4: Run tests to verify the first two pass**

Run: `cd /Users/pip/Code/aws-sso-monitor && uv run pytest tests/test_app.py -v`
Expected: First two PASS, last two PASS (alerter startup check is still in place)

**Step 5: Run full test suite**

Run: `cd /Users/pip/Code/aws-sso-monitor && uv run pytest -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add src/aws_sso_monitor/app.py tests/test_app.py
git commit -m "feat: replace alerter with desktop-notifier for notifications"
```

---

### Task 3: Replace alerter startup check with bundle check

**Files:**
- Modify: `src/aws_sso_monitor/app.py:6` (remove shutil import), `app.py:168-176` (`main()`)
- Modify: `tests/test_app.py` (last two tests)

**Step 1: Write the failing tests**

In `tests/test_app.py`, replace the last two tests (`test_main_exits_if_alerter_not_found` and `test_main_starts_app_if_alerter_found`) with:

```python
def test_main_exits_if_not_bundled():
    with (
        unittest.mock.patch.object(app, "_is_bundled", return_value=False),
        unittest.mock.patch.object(app, "SSOMonitorApp"),
    ):
        with pytest.raises(SystemExit) as exc_info:
            app.main()
        assert exc_info.value.code == 1


def test_main_starts_app_if_bundled():
    with (
        unittest.mock.patch.object(app, "_is_bundled", return_value=True),
        unittest.mock.patch.object(app, "SSOMonitorApp") as mock_app_cls,
    ):
        app.main()
        mock_app_cls.return_value.run.assert_called_once()
```

Also remove the `import shutil` lines from the deleted tests (they were local imports inside the old test functions).

**Step 2: Run tests to verify the last two fail**

Run: `cd /Users/pip/Code/aws-sso-monitor && uv run pytest tests/test_app.py::test_main_exits_if_not_bundled tests/test_app.py::test_main_starts_app_if_bundled -v`
Expected: FAIL with `AttributeError: module 'aws_sso_monitor.app' has no attribute '_is_bundled'`

**Step 3: Add _is_bundled() and update main()**

In `src/aws_sso_monitor/app.py`, remove the `import shutil` line (line 6).

Replace `main()` (lines 168-176) with:

```python
def _is_bundled() -> bool:
    """Check whether we're running inside a macOS .app bundle."""
    import Foundation

    return Foundation.NSBundle.mainBundle.bundleIdentifier is not None


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    if not _is_bundled():
        print(
            "Error: AWS SSO Monitor must be run as a bundled .app.\n"
            "Build and install with: scripts/build.sh"
        )
        raise SystemExit(1)
    SSOMonitorApp().run()
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/pip/Code/aws-sso-monitor && uv run pytest tests/test_app.py -v`
Expected: ALL PASS

**Step 5: Run full test suite and checks**

Run: `cd /Users/pip/Code/aws-sso-monitor && uv run pytest -v && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add src/aws_sso_monitor/app.py tests/test_app.py
git commit -m "feat: replace alerter startup check with app bundle check"
```

---

### Task 4: Remove unused icon resources

**Files:**
- Modify: `src/aws_sso_monitor/icon.py:9`
- Delete: `src/aws_sso_monitor/resources/notification-icon-sad.png`
- Modify: `scripts/generate_icons.py:149-172` (remove `generate_notification_icon`), `generate_icons.py:175-180` (update `__main__`)

**Step 1: Remove NOTIFICATION_ICON_SAD from icon.py**

In `src/aws_sso_monitor/icon.py`, remove line 9:

```python
NOTIFICATION_ICON_SAD = _RESOURCES / "notification-icon-sad.png"
```

The file should now be:

```python
"""Paths to icon resources."""

import pathlib

_RESOURCES = pathlib.Path(__file__).parent / "resources"

MENUBAR_ICON = _RESOURCES / "menubar-icon.png"
MENUBAR_ICON_SAD = _RESOURCES / "menubar-icon-sad.png"
```

**Step 2: Delete the notification icon PNG**

Run: `rm src/aws_sso_monitor/resources/notification-icon-sad.png`

**Step 3: Remove generate_notification_icon() from generate_icons.py**

In `scripts/generate_icons.py`, remove the entire `generate_notification_icon` function (lines 149-172) and update the `__main__` block (lines 175-180) to:

```python
if __name__ == "__main__":
    print("Generating AWS SSO Monitor icons...")
    RESOURCES_DIR.mkdir(parents=True, exist_ok=True)
    generate_menubar_icons()
    print(f"Done. Icons in {RESOURCES_DIR}")
```

**Step 4: Run full test suite**

Run: `cd /Users/pip/Code/aws-sso-monitor && uv run pytest -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/aws_sso_monitor/icon.py scripts/generate_icons.py
git rm src/aws_sso_monitor/resources/notification-icon-sad.png
git commit -m "chore: remove unused notification icon resources"
```

---

### Task 5: Add .icns generation

**Files:**
- Modify: `scripts/generate_icons.py`

**Step 1: Add generate_app_icon() function**

In `scripts/generate_icons.py`, add the following function after `generate_menubar_icons()` (after line 146) and before the `if __name__` block:

```python
def generate_app_icon() -> None:
    """Generate .icns app icon (sad AWS face) for the macOS app bundle."""
    import shutil
    import subprocess

    build_dir = pathlib.Path(__file__).parent.parent / "build"
    iconset_dir = build_dir / "icon.iconset"
    if iconset_dir.exists():
        shutil.rmtree(iconset_dir)
    iconset_dir.mkdir(parents=True)

    sizes = [
        ("icon_16x16.png", 16),
        ("icon_16x16@2x.png", 32),
        ("icon_32x32.png", 32),
        ("icon_32x32@2x.png", 64),
        ("icon_128x128.png", 128),
        ("icon_128x128@2x.png", 256),
        ("icon_256x256.png", 256),
        ("icon_256x256@2x.png", 512),
        ("icon_512x512.png", 512),
        ("icon_512x512@2x.png", 1024),
    ]

    for filename, size in sizes:
        # SVG viewBox is 304x182 (landscape). Fit by width.
        render_w = size
        render_h = int(size * 182 / 304)

        svg = _build_svg(sad=True, colour=True, text_stroke_width=2)
        rendered = _svg_to_pil(svg, render_w, render_h)

        # Center on a square canvas with white background
        img = PIL.Image.new("RGBA", (size, size), (255, 255, 255, 255))
        offset_x = (size - render_w) // 2
        offset_y = (size - render_h) // 2
        img.paste(rendered, (offset_x, offset_y), rendered)

        img.save(iconset_dir / filename)

    icns_path = build_dir / "icon.icns"
    subprocess.run(
        ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(icns_path)],
        check=True,
    )
    shutil.rmtree(iconset_dir)
    print(f"  Created {icns_path}")
```

**Step 2: Update __main__ block to call generate_app_icon()**

Update the `__main__` block to:

```python
if __name__ == "__main__":
    print("Generating AWS SSO Monitor icons...")
    RESOURCES_DIR.mkdir(parents=True, exist_ok=True)
    generate_menubar_icons()
    generate_app_icon()
    print("Done.")
```

**Step 3: Run the script to verify it works**

Run: `cd /Users/pip/Code/aws-sso-monitor && uv run scripts/generate_icons.py`
Expected: Output shows creation of menubar icons and `build/icon.icns`. Verify: `ls -la build/icon.icns`

**Step 4: Commit**

```bash
git add scripts/generate_icons.py
git commit -m "feat: generate .icns app icon for macOS app bundle"
```

---

### Task 6: Create setup.py and launcher script

**Files:**
- Create: `run_app.py`
- Create: `setup.py`

**Step 1: Create run_app.py**

Create `run_app.py` in the project root:

```python
"""Launcher script for py2app."""

import aws_sso_monitor.app

aws_sso_monitor.app.main()
```

**Step 2: Create setup.py**

Create `setup.py` in the project root:

```python
"""py2app build configuration for AWS SSO Monitor."""

from setuptools import setup

APP = ["run_app.py"]

OPTIONS = {
    "argv_emulation": False,
    "iconfile": "build/icon.icns",
    "packages": ["aws_sso_monitor"],
    "includes": ["Foundation"],
    "plist": {
        "CFBundleName": "AWS SSO Monitor",
        "CFBundleDisplayName": "AWS SSO Monitor",
        "CFBundleIdentifier": "systems.intelligible.aws-sso-monitor",
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        "LSUIElement": True,
        "LSMinimumSystemVersion": "14.0",
    },
}

setup(
    app=APP,
    name="AWS SSO Monitor",
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
```

**Step 3: Test alias build**

Run: `cd /Users/pip/Code/aws-sso-monitor && uv run python setup.py py2app -A`
Expected: Creates `dist/AWS SSO Monitor.app` (alias mode — symlinks to source). Verify: `ls -la dist/`

**Step 4: Clean up test build**

Run: `rm -rf dist/`

**Step 5: Commit**

```bash
git add run_app.py setup.py
git commit -m "feat: add py2app configuration for macOS app bundle"
```

---

### Task 7: Update launchd plist

**Files:**
- Modify: `systems.intelligible.aws-sso-monitor.plist`

**Step 1: Update ProgramArguments**

Replace the entire `systems.intelligible.aws-sso-monitor.plist` with:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>systems.intelligible.aws-sso-monitor</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Applications/AWS SSO Monitor.app/Contents/MacOS/AWS SSO Monitor</string>
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

**Step 2: Commit**

```bash
git add systems.intelligible.aws-sso-monitor.plist
git commit -m "chore: update launchd plist to launch .app bundle"
```

---

### Task 8: Create build script

**Files:**
- Create: `scripts/build.sh`

**Step 1: Create scripts/build.sh**

```bash
#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Generating icons..."
uv run scripts/generate_icons.py

echo "==> Building app bundle..."
uv run python setup.py py2app --dist-dir build/dist

echo "==> Signing app..."
APP="build/dist/AWS SSO Monitor.app"
sudo codesign --sign "metr-santa-cert" --force --deep "$APP"

echo "==> Building installer package..."
PKG_ROOT=$(mktemp -d)
trap 'rm -rf "$PKG_ROOT"' EXIT

mkdir -p "$PKG_ROOT/Applications"
cp -R "$APP" "$PKG_ROOT/Applications/"

mkdir -p "$PKG_ROOT/Library/LaunchAgents"
cp systems.intelligible.aws-sso-monitor.plist "$PKG_ROOT/Library/LaunchAgents/"

pkgbuild \
    --root "$PKG_ROOT" \
    --identifier systems.intelligible.aws-sso-monitor \
    --version 0.1.0 \
    "build/AWS SSO Monitor.pkg"

echo "==> Done: build/AWS SSO Monitor.pkg"
```

**Step 2: Make it executable**

Run: `chmod +x scripts/build.sh`

**Step 3: Run full test suite and checks**

Run: `cd /Users/pip/Code/aws-sso-monitor && uv run pytest -v && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add scripts/build.sh
git commit -m "feat: add build script for app bundle, signing, and packaging"
```
