import configparser
import dataclasses
import datetime
import enum
import json
import pathlib

SSO_SESSION_PREFIX = "sso-session "
EXPIRING_SOON_MINUTES = 10


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


class SessionStatus(enum.Enum):
    VALID = "valid"
    EXPIRING_SOON = "expiring_soon"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


@dataclasses.dataclass(frozen=True)
class SessionState:
    session: SSOSession
    status: SessionStatus
    expires_at: datetime.datetime | None


def get_session_statuses(
    sessions: list[SSOSession],
    cache_dir: pathlib.Path,
    now: datetime.datetime | None = None,
) -> list[SessionState]:
    """Check SSO cache files and classify each session's status."""
    if now is None:
        now = datetime.datetime.now(datetime.UTC)

    # Build a map of start_url -> (expires_at) from cache files
    cache_tokens: dict[str, datetime.datetime] = {}
    if cache_dir.exists():
        for cache_file in cache_dir.glob("*.json"):
            try:
                data = json.loads(cache_file.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            # Session tokens have startUrl + accessToken; client registrations don't
            if "startUrl" not in data or "accessToken" not in data:
                continue
            start_url = data["startUrl"]
            expires_at = datetime.datetime.fromisoformat(data["expiresAt"])
            # Keep the latest expiry if multiple files match
            if start_url not in cache_tokens or expires_at > cache_tokens[start_url]:
                cache_tokens[start_url] = expires_at

    states: list[SessionState] = []
    for session in sessions:
        expires_at = cache_tokens.get(session.start_url)
        if expires_at is None:
            states.append(
                SessionState(session=session, status=SessionStatus.UNKNOWN, expires_at=None)
            )
            continue

        remaining = expires_at - now
        if remaining.total_seconds() <= 0:
            status = SessionStatus.EXPIRED
        elif remaining.total_seconds() <= EXPIRING_SOON_MINUTES * 60:
            status = SessionStatus.EXPIRING_SOON
        else:
            status = SessionStatus.VALID

        states.append(SessionState(session=session, status=status, expires_at=expires_at))

    return states
