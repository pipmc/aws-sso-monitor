#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Generating icons..."
uv run scripts/generate_icons.py

echo "==> Building app bundle..."
uv run python setup.py py2app --dist-dir build/dist

echo "==> Signing app..."
APP="build/dist/AWS SSO Monitor.app"
sudo codesign --sign "metr-santa-cert" --force --deep "$APP"

echo "==> Building installer package..."
PKG_ROOT=$(mktemp -d)
trap 'rm -rf "$PKG_ROOT"' EXIT

mkdir -p "$PKG_ROOT/Applications"
cp -R "$APP" "$PKG_ROOT/Applications/"

mkdir -p "$PKG_ROOT/Library/LaunchAgents"
cp systems.intelligible.aws-sso-monitor.plist "$PKG_ROOT/Library/LaunchAgents/"

pkgbuild \
    --root "$PKG_ROOT" \
    --identifier systems.intelligible.aws-sso-monitor \
    --version 0.1.0 \
    "build/AWS SSO Monitor.pkg"

echo "==> Done: build/AWS SSO Monitor.pkg"
