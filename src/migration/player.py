from datetime import UTC, datetime
from typing import Mapping
from auth.models import PlayerPassword
from player.datatypes import UserRole
from player.models import Player, PlayerFollowedPlayer, PlayerRole


def process_player_file(login: str, data: dict) -> tuple[list[PlayerFollowedPlayer], int | None]:
    """v1 logins were case-sensitive, v3 ones are lowercase: the file of a colliding pair is expected to be merged beforehand"""
    return [
        PlayerFollowedPlayer(follower_login=login.lower(), followed_login=followed_login.lower())
        for followed_login in data.get("friends", [])
    ], data.get("lastMessageTimestamp")


def process_passwords_file(data: dict[str, str], first_messages: dict[str, datetime], first_games: dict[str, datetime], last_activity: Mapping[str, int | None]) -> tuple[list[Player], list[PlayerPassword]]:
    players = []
    passwords = []

    # v1 logins were case-sensitive, so some players exist twice (Divan and divan), or only with capitals (Groot).
    # The lowercase login is the account; the capitalized spelling, if there is one, is kept as the nickname
    nicknames: dict[str, str] = {}
    for login in data:
        if login != login.lower():
            nicknames[login.lower()] = login

    for original_login, md5hash in data.items():
        login = original_login.lower()
        if login == "aleksandragabdrahmanova79gmailcom" or original_login == "Kirill123":  # Too long (first) and duplicate (second)
            continue
        if original_login != login and login in data:
            continue  # the lowercase twin carries the account and its password
        if len(login) > 32:
            raise ValueError(login)

        roles = []
        if login == "gulvan":
            roles = [UserRole.ADMIN]
        elif login in ("mrolegus", "agent", "pike", "lesha181", "canaconda", "grizzly"):
            roles = [UserRole.ANACONDA_DEVELOPER]

        nickname = nicknames.get(login, login)
        if login == "gulvan":
            nickname = "Gulvan"
        elif login == "mrolegus":
            nickname = "MrOlegus"

        if login in first_messages:
            joined_at = first_messages[login]
        elif login == "gulvan":
            joined_at = datetime(2021, 5, 19, tzinfo=UTC)
        else:
            joined_at = first_games.get(login, datetime.now(UTC))

        players.append(
            Player(
                login=login,
                joined_at=joined_at,
                last_ws_activity=last_activity.get(login) or int(joined_at.timestamp()),
                nickname=nickname,
                roles=[PlayerRole(role=role) for role in roles]
            )
        )
        passwords.append(
            PlayerPassword(
                login=login,
                password_hash=bytes(),
                normal_md5=md5hash
            )
        )

    return players, passwords
