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
