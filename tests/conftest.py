# Patch desktop-notifier to use the dummy backend before any test module
# imports aws_sso_monitor.app (which creates a DesktopNotifierSync at module
# level).  The real macOS backend crashes outside a signed app bundle.
import desktop_notifier.backends.dummy
import desktop_notifier.main

desktop_notifier.main.get_backend_class = lambda: (
    desktop_notifier.backends.dummy.DummyNotificationCenter
)
