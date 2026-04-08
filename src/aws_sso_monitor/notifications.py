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
