from datetime import UTC, datetime
from auth.models import PlayerPassword
from player.datatypes import UserRole
from player.models import Player, PlayerFollowedPlayer, PlayerRole


def process_player_file(login: str, data: dict) -> list[PlayerFollowedPlayer]:
    return [
        PlayerFollowedPlayer(follower_login=login, followed_login=followed_login)
        for followed_login in data.get("friends", [])
    ]


def process_passwords_file(data: dict[str, str], first_games: dict[str, datetime]) -> tuple[list[Player], list[PlayerPassword]]:
    players = []
    passwords = []

    for login, md5hash in data.items():
        if login == "aleksandragabdrahmanova79gmailcom" or login == "PaulNotIntellector":  # Too long (first) and duplicate (second)
            continue
        if len(login) > 32:
            raise ValueError(login)

        roles = []
        if login == "gulvan":
            roles = [UserRole.ADMIN]
        elif login in ("mrolegus", "agent", "pike", "lesha181", "canaconda"):
            roles = [UserRole.ANACONDA_DEVELOPER]

        nickname = login
        if login == "gulvan":
            nickname = "Gulvan"
        elif login == "mrolegus":
            nickname = "MrOlegus"
        elif login == "paulnotintellector":
            nickname = "PaulNotIntellector"

        players.append(
            Player(
                login=login,
                joined_at=first_games.get(login, datetime.now(UTC)),
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
