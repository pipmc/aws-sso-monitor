import dataclasses
import datetime

import aws_sso_monitor.sso as sso


@dataclasses.dataclass(frozen=True)
class PendingNotification:
    title: str
    message: str
    group: str


@dataclasses.dataclass
class _TrackedSession:
    last_expires_at: str
    notified_expiring: bool = False
    notified_expired: bool = False


def _minutes_remaining(expires_at: datetime.datetime | None) -> int:
    if expires_at is None:
        return 0
    delta = expires_at - datetime.datetime.now(datetime.UTC)
    return max(0, int(delta.total_seconds()) // 60)


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
                minutes = _minutes_remaining(state.expires_at)
                pending.append(
                    PendingNotification(
                        title="AWS SSO Expiring Soon",
                        message=f"Session '{name}' expires in {minutes} minutes",
                        group=name,
                    )
                )
            elif state.status == sso.SessionStatus.EXPIRED and not tracked.notified_expired:
                tracked.notified_expired = True
                pending.append(
                    PendingNotification(
                        title="AWS SSO Session Expired",
                        message=f"Session '{name}' has expired",
                        group=name,
                    )
                )

        return pending
