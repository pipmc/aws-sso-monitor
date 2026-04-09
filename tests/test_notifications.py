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
    state = _make_state(
        status=sso.SessionStatus.VALID,
        expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=2),
    )
    pending = tracker.check([state])
    assert pending == []


def test_expired_fires_once() -> None:
    tracker = notifications.NotificationTracker()
    state = _make_state(
        status=sso.SessionStatus.EXPIRED,
        expires_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1),
    )

    first = tracker.check([state])
    assert len(first) == 1
    assert "expired" in first[0].title.lower()

    second = tracker.check([state])
    assert second == []


def test_expiring_soon_fires_once() -> None:
    tracker = notifications.NotificationTracker()
    state = _make_state(
        status=sso.SessionStatus.EXPIRING_SOON,
        expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=5),
    )

    first = tracker.check([state])
    assert len(first) == 1
    assert "expiring" in first[0].title.lower()
    assert "minutes" in first[0].message

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
    state = _make_state(
        status=sso.SessionStatus.EXPIRED,
        expires_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1),
    )
    pending = tracker.check([state])
    assert pending[0].url == "https://myorg.awsapps.com/start"


def test_unknown_status_no_notification() -> None:
    tracker = notifications.NotificationTracker()
    state = _make_state(status=sso.SessionStatus.UNKNOWN, expires_at=None)
    pending = tracker.check([state])
    assert pending == []


def test_pending_notification_has_group_field() -> None:
    notif = notifications.PendingNotification(
        title="AWS SSO Expiring Soon",
        message="Session 'dev' expires in 5 minutes",
        url="https://start.awsapps.com/start",
        group="dev",
    )
    assert notif.group == "dev"
