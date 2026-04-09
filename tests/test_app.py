import subprocess
import threading
import unittest.mock
import webbrowser

import aws_sso_monitor.app as app
import aws_sso_monitor.icon as icon
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

        # Extract the target callable and invoke it with mocked subprocess.run
        target_fn = call_kwargs.kwargs["target"]
        with unittest.mock.patch.object(subprocess, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="Dismiss\n", stderr=""
            )
            target_fn()

            mock_run.assert_called_once()
            cmd = mock_run.call_args.args[0]
            assert cmd[0] == "alerter"
            assert "--message" in cmd
            assert cmd[cmd.index("--message") + 1] == notif.message
            assert "--title" in cmd
            assert cmd[cmd.index("--title") + 1] == notif.title
            assert "--closeLabel" in cmd
            assert cmd[cmd.index("--closeLabel") + 1] == "Dismiss"
            assert "--actions" in cmd
            assert cmd[cmd.index("--actions") + 1] == "Open SSO"
            assert "--group" in cmd
            assert cmd[cmd.index("--group") + 1] == notif.group
            assert "--sound" in cmd
            assert cmd[cmd.index("--sound") + 1] == "default"
            assert "--appIcon" in cmd
            assert cmd[cmd.index("--appIcon") + 1] == str(icon.NOTIFICATION_ICON_SAD)


def test_send_notification_opens_url_on_open_sso_click():
    notif = notifications.PendingNotification(
        title="AWS SSO Expired",
        message="Session 'prod' has expired",
        url="https://my-sso.awsapps.com/start",
        group="prod",
    )

    with unittest.mock.patch.object(threading, "Thread") as mock_thread:
        mock_thread_instance = unittest.mock.MagicMock()
        mock_thread.return_value = mock_thread_instance

        app._send_notification(notif)

        target_fn = mock_thread.call_args.kwargs["target"]

    with (
        unittest.mock.patch.object(subprocess, "run") as mock_run,
        unittest.mock.patch.object(webbrowser, "open") as mock_open,
    ):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="Open SSO\n", stderr=""
        )
        target_fn()

        mock_run.assert_called_once()
        mock_open.assert_called_once_with("https://my-sso.awsapps.com/start")
