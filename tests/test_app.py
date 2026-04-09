import threading
import unittest.mock

import aws_sso_monitor.app as app
import aws_sso_monitor.notifications as notifications


def test_send_notification_builds_correct_alerter_command():
    notif = notifications.PendingNotification(
        title="AWS SSO Expiring Soon",
        message="Session 'dev' expires in 5 minutes",
        url="https://start.awsapps.com/start",
        group="dev",
    )

    with unittest.mock.patch.object(threading, "Thread") as mock_thread:
        mock_thread_instance = unittest.mock.MagicMock()
        mock_thread.return_value = mock_thread_instance

        app._send_notification(notif)

        mock_thread.assert_called_once()
        call_kwargs = mock_thread.call_args
        assert call_kwargs.kwargs["daemon"] is True
        mock_thread_instance.start.assert_called_once()
