# AWS SSO Session Monitor

A macOS menu bar app that watches your AWS SSO sessions and notifies you when they're about to expire or have expired. Click the notification to open your SSO login page.

## Features

- Monitors all SSO sessions defined in `~/.aws/config`
- Warns 10 minutes before expiry, notifies again once expired
- One notification per event — no nagging
- Click notification to open SSO login page in browser
- Menu bar icon shows session status at a glance
- Respects screen lock (queues notifications until unlock)
- Respects Do Not Disturb / Focus mode

## Requirements

- macOS 14+
- Python 3.13+
- [uv](https://docs.astral.sh/uv/)

## Install

```sh
git clone https://github.com/pip/aws-sso-monitor.git
cd aws-sso-monitor
uv sync
```

### Start at login

```sh
cp systems.intelligible.aws-sso-monitor.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/systems.intelligible.aws-sso-monitor.plist
```

### Run manually

```sh
uv run aws-sso-monitor
```

## How it works

The app reads `[sso-session]` sections from `~/.aws/config`, then polls `~/.aws/sso/cache/` every 5 minutes to check token expiry times. When a session is expiring or expired, it sends a macOS notification. Clicking the notification opens the SSO start URL in your default browser.
