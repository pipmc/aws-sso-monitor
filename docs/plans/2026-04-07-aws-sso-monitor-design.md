# AWS SSO Session Monitor - Design

## Problem

AWS SSO sessions expire silently. You discover the expiry only when a CLI command or SDK call fails, interrupting your flow. There's no proactive warning.

## Solution

A macOS menu bar app that monitors AWS SSO session tokens and sends native notifications when sessions are about to expire or have expired. Clicking a notification opens the SSO portal login page.

## Architecture

A `rumps` (Ridiculously Uncomplicated macOS Python Statusbar apps) menu bar application.

### Components

**`sso.py` - AWS config/cache parsing**
- Parses `~/.aws/config` for `[sso-session X]` sections, extracting `sso_start_url` and `sso_region`
- Scans `~/.aws/sso/cache/*.json` for session token files (identified by presence of `startUrl` + `accessToken` fields, as opposed to client registration files which only have `clientId`)
- Matches cache files to known sessions via `startUrl`
- Returns structured session state: session name, start URL, expiry time, expired/expiring/valid status

**`app.py` - Menu bar app and notification logic**
- `rumps.App` subclass with sad AWS logo as menu bar icon
- 5-minute repeating timer to check session status
- Menu items showing each session's status (e.g., "metr: expires in 2h 15m" or "metr: EXPIRED")
- "Check Now" menu item
- "Quit" menu item
- Notification management:
  - Fires "expiring soon" notification ~10 minutes before expiry
  - Fires "expired" notification once session has expired
  - Each notification fires once per expiry event (no nagging)
  - State resets when token file is refreshed (new `expiresAt` detected)
- Screen lock awareness:
  - Subscribes to `com.apple.screenIsLocked` / `com.apple.screenIsUnlocked` via `NSDistributedNotificationCenter`
  - Queues notifications while screen is locked
  - Delivers queued notifications on unlock
- DND/Focus mode handled natively by macOS (no custom logic needed)
- Notification click handler opens the SSO start URL in default browser via `webbrowser.open()`

**`icon.py` - Embedded icon**
- Sad AWS logo (Amazon smile inverted to a frown) as base64-encoded PNG
- Used for menu bar icon (template image, retina-ready)
- Used for notification identity image

### Project structure

```
~/Code/aws-sso-monitor/
  pyproject.toml
  src/
    aws_sso_monitor/
      __init__.py
      app.py
      sso.py
      icon.py
  assets/
    sad-aws.png
  systems.intelligible.aws-sso-monitor.plist
```

### Dependencies

- `rumps` - menu bar app framework (brings `pyobjc` as transitive dep)
- Python 3.13, managed via `uv`

### Startup

A launchd LaunchAgent (`~/Library/LaunchAgents/systems.intelligible.aws-sso-monitor.plist`) runs the app at login via `uv run`.

## SSO session detection

1. Parse `~/.aws/config` for `[sso-session X]` sections -> extract `sso_start_url`
2. Scan `~/.aws/sso/cache/*.json`
3. For each file containing both `startUrl` and `accessToken` fields: match `startUrl` to a known session
4. Read `expiresAt` (ISO 8601 UTC timestamp), compare against `datetime.now(UTC)`
5. Classify: valid (>10 min remaining), expiring soon (<=10 min remaining), or expired

## Notification behavior

| Condition | Notification | Fires |
|-----------|-------------|-------|
| <= 10 min to expiry | "AWS SSO session 'metr' expires in N minutes" | Once |
| Expired | "AWS SSO session 'metr' has expired" | Once |
| Re-authenticated | State resets | - |

Clicking either notification opens the SSO start URL in the default browser.

## Trade-offs and risks

- `rumps` uses `NSUserNotification`, which Apple deprecated in macOS 11 but still works through macOS 15. If Apple removes it, we'd need to migrate to a `py2app`-bundled `.app` with `UNUserNotificationCenter`.
- The menu bar icon uses a template image, so macOS handles light/dark mode automatically.
- Session detection relies on the AWS CLI's cache file format, which is stable but not a public API contract.
