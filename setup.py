"""py2app build configuration for AWS SSO Monitor."""

from setuptools import setup

APP = ["run_app.py"]

OPTIONS = {
    "argv_emulation": False,
    "iconfile": "build/icon.icns",
    "packages": ["aws_sso_monitor"],
    "includes": ["Foundation"],
    "plist": {
        "CFBundleName": "AWS SSO Monitor",
        "CFBundleDisplayName": "AWS SSO Monitor",
        "CFBundleIdentifier": "systems.intelligible.aws-sso-monitor",
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        "LSUIElement": True,
        "LSMinimumSystemVersion": "14.0",
    },
}

setup(
    app=APP,
    name="AWS SSO Monitor",
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
