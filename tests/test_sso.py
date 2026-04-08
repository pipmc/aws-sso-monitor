import datetime
import json
import pathlib

import aws_sso_monitor.sso as sso


def test_parse_sso_sessions_single(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config"
    config.write_text(
        "[sso-session myorg]\n"
        "sso_start_url = https://myorg.awsapps.com/start\n"
        "sso_region = us-east-1\n"
        "\n"
        "[profile dev]\n"
        "sso_session = myorg\n"
        "sso_account_id = 123456\n"
    )
    sessions = sso.parse_sso_sessions(config)
    assert len(sessions) == 1
    assert sessions[0].name == "myorg"
    assert sessions[0].start_url == "https://myorg.awsapps.com/start"
    assert sessions[0].region == "us-east-1"


def test_parse_sso_sessions_multiple(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config"
    config.write_text(
        "[sso-session org1]\n"
        "sso_start_url = https://org1.awsapps.com/start\n"
        "sso_region = us-east-1\n"
        "\n"
        "[sso-session org2]\n"
        "sso_start_url = https://org2.awsapps.com/start\n"
        "sso_region = eu-west-1\n"
    )
    sessions = sso.parse_sso_sessions(config)
    assert len(sessions) == 2
    names = {s.name for s in sessions}
    assert names == {"org1", "org2"}


def test_parse_sso_sessions_no_sessions(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config"
    config.write_text("[profile dev]\nregion = us-east-1\n")
    sessions = sso.parse_sso_sessions(config)
    assert sessions == []


def test_parse_sso_sessions_missing_file(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "nonexistent"
    sessions = sso.parse_sso_sessions(config)
    assert sessions == []


def _write_cache_file(
    cache_dir: pathlib.Path,
    filename: str,
    start_url: str,
    expires_at: datetime.datetime,
) -> None:
    (cache_dir / filename).write_text(
        json.dumps(
            {
                "startUrl": start_url,
                "accessToken": "fake-token",
                "expiresAt": expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "clientId": "fake-client",
                "clientSecret": "fake-secret",
            }
        )
    )


def _make_session(
    name: str = "myorg", start_url: str = "https://myorg.awsapps.com/start"
) -> sso.SSOSession:
    return sso.SSOSession(name=name, start_url=start_url, region="us-east-1")


def test_session_status_valid(tmp_path: pathlib.Path) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    now = datetime.datetime.now(datetime.UTC)
    _write_cache_file(
        cache_dir, "abc.json", "https://myorg.awsapps.com/start", now + datetime.timedelta(hours=2)
    )

    states = sso.get_session_statuses([_make_session()], cache_dir, now=now)
    assert len(states) == 1
    assert states[0].status == sso.SessionStatus.VALID
    assert states[0].expires_at is not None


def test_session_status_expired(tmp_path: pathlib.Path) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    now = datetime.datetime.now(datetime.UTC)
    _write_cache_file(
        cache_dir, "abc.json", "https://myorg.awsapps.com/start", now - datetime.timedelta(hours=1)
    )

    states = sso.get_session_statuses([_make_session()], cache_dir, now=now)
    assert states[0].status == sso.SessionStatus.EXPIRED


def test_session_status_expiring_soon(tmp_path: pathlib.Path) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    now = datetime.datetime.now(datetime.UTC)
    _write_cache_file(
        cache_dir,
        "abc.json",
        "https://myorg.awsapps.com/start",
        now + datetime.timedelta(minutes=5),
    )

    states = sso.get_session_statuses([_make_session()], cache_dir, now=now)
    assert states[0].status == sso.SessionStatus.EXPIRING_SOON


def test_session_status_no_cache(tmp_path: pathlib.Path) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    states = sso.get_session_statuses([_make_session()], cache_dir)
    assert states[0].status == sso.SessionStatus.UNKNOWN


def test_ignores_client_registration_files(tmp_path: pathlib.Path) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    # Client registration: has clientId but no startUrl/accessToken
    (cache_dir / "client.json").write_text(
        json.dumps(
            {"clientId": "abc", "clientSecret": "secret", "expiresAt": "2099-01-01T00:00:00Z"}
        )
    )
    states = sso.get_session_statuses([_make_session()], cache_dir)
    assert states[0].status == sso.SessionStatus.UNKNOWN


def test_session_status_cache_dir_missing(tmp_path: pathlib.Path) -> None:
    cache_dir = tmp_path / "nonexistent"
    states = sso.get_session_statuses([_make_session()], cache_dir)
    assert states[0].status == sso.SessionStatus.UNKNOWN
