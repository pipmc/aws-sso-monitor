# Alerter Notification Rewrite

## Goal

Replace the osascript-based notification in `app.py` with [vjeantet/alerter](https://github.com/vjeantet/alerter), gaining actionable alert-style notifications with click handling.

## Decisions

- **Action buttons:** "Open SSO" action + "Dismiss" close button. Clicking "Open SSO" opens the session's start URL in the browser.
- **Alerter dependency:** Check at startup via `shutil.which`; exit with install instructions if missing.
- **Grouping:** Use `--group` with the session name so stale alerts are replaced (e.g. "expiring" replaced by "expired").
- **Click handling:** Spawn alerter in a background thread; read stdout to detect "Open SSO" clicks.
- **Icon:** Use `--appIcon` with `notification-icon-sad.png` for all alerts.

## Changes

### `notifications.py`

Add `group: str` field to `PendingNotification`. Set it to the session name in `NotificationTracker.check()`.

### `app.py`

- **Startup check:** `main()` calls `shutil.which("alerter")` before launching. If missing, print error with `brew install vjeantet/tap/alerter` instructions and `sys.exit(1)`.
- **`_send_notification` replacement:** Build alerter command (`--message`, `--title`, `--closeLabel Dismiss`, `--actions "Open SSO"`, `--group`, `--sound default`, `--appIcon`). Spawn via `subprocess.Popen` in a `threading.Thread`. Thread reads stdout; if result is `Open SSO`, call `webbrowser.open(url)`.
- **`_fire_notification`:** Pass full `PendingNotification` instead of just title/message.

### No other changes

- `NotificationTracker` logic, screen lock queuing, menu bar, icon, periodic check — all unchanged.

## Alerter command

```
alerter --message MSG --title TITLE --closeLabel Dismiss --actions "Open SSO" --group SESSION_NAME --sound default --appIcon /path/to/notification-icon-sad.png
```
