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
