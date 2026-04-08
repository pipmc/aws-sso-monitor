import configparser
import dataclasses
import pathlib

SSO_SESSION_PREFIX = "sso-session "


@dataclasses.dataclass(frozen=True)
class SSOSession:
    name: str
    start_url: str
    region: str


def parse_sso_sessions(config_path: pathlib.Path) -> list[SSOSession]:
    """Parse ~/.aws/config for [sso-session X] sections."""
    if not config_path.exists():
        return []

    parser = configparser.ConfigParser()
    parser.read(config_path)

    sessions: list[SSOSession] = []
    for section in parser.sections():
        if not section.startswith(SSO_SESSION_PREFIX):
            continue
        name = section[len(SSO_SESSION_PREFIX) :]
        sessions.append(
            SSOSession(
                name=name,
                start_url=parser.get(section, "sso_start_url"),
                region=parser.get(section, "sso_region"),
            )
        )
    return sessions
