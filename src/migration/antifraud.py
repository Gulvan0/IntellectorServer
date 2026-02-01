from collections import defaultdict
from datetime import UTC, datetime
from common.time_control import TimeControlKind
from migration.game import RatedGameInfo
from player.models import PlayerEloProgress

import re


def process_log(log: str, player_rated_games: dict[str, list[RatedGameInfo]]) -> list[PlayerEloProgress]:
    result = []

    game_counts = defaultdict(int)

    for line in log.splitlines():
        line = line.strip()
        if not line:
            continue

        matched = re.fullmatch(r'\|(\d+?)\|202\d-\d\d-\d\d \d\d:\d\d:\d\d.\d\d\d ELO_(\w+?) (\w+?): (\d+?) -> (\d+?) \(\+?(-?\d+?)\)', line)
        if not matched:
            raise ValueError(line)

        login = matched.group(3)
        time_control_kind = TimeControlKind(matched.group(2).lower())
        ts = datetime.fromtimestamp(int(matched.group(1)), UTC)

        game_counts[(login, time_control_kind)] += 1

        causing_game_id = None
        for game in reversed(player_rated_games.get(login, [])):
            if game.started_at > ts:
                continue
            if game.prior_player_elo[login] == int(matched.group(4)):
                causing_game_id = game.game_id
                break

        if not causing_game_id:
            raise ValueError(f'Game not found\n{line}')

        result.append(PlayerEloProgress(
            login=login,
            ts=ts,
            time_control_kind=time_control_kind,
            elo=int(matched.group(5)),
            delta=int(matched.group(6)),
            causing_game_id=causing_game_id,
            ranked_games_played=game_counts[(login, time_control_kind)]
        ))

    return result
