"""macOS menu bar app that monitors AWS SSO session expiry."""

import datetime
import pathlib
import webbrowser

import rumps

# rumps.__init__ shadows the notifications module with the decorator function,
# so we must import the Notification class directly
from rumps.notifications import Notification as _RumpsNotification

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
    def _on_notification_click(self, notification: _RumpsNotification) -> None:
        data = notification.data
        if isinstance(data, dict):
            url = data.get("url")
            if isinstance(url, str):
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
