from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import datetime, timedelta
import json
from pathlib import Path
import re
import os
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from player.models import PlayerFollowedPlayer
    from study.models import Study

from sqlalchemy import create_engine
from sqlmodel import Session
from config.loader import load
from config.models import SecretConfig
from migration.antifraud import process_log
from migration.game import parse_log, RatedGameInfo
from migration.player import process_passwords_file, process_player_file
from migration.study import process_study


IS_TEST = os.getenv("STAGE", "TEST")
BACKUP_FOLDER = os.getenv("INTELLECTOR_BACKUP_DIR") or "C:/Users/mitmi/YandexDisk/backup"
SECRET_CONFIG = load('secret', SecretConfig)
DB_ENGINE = create_engine(SECRET_CONFIG.db.url.replace("aiomysql", "pymysql"))

_GAME_COMMIT_BATCH = 50


def _read_text(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _parse_game(args: tuple[int, str, str | None]) -> tuple[list[object], RatedGameInfo | None, str, str, datetime]:
    game_id, full_log, revived_dt = args
    return parse_log(game_id, full_log, revived_dt)


if __name__ == '__main__':
    SESSION = Session(DB_ENGINE)

    if IS_TEST:
        from prompt_toolkit import prompt
        from prompt_toolkit.completion import WordCompleter

        backups = list(sorted(
            filter(
                lambda x: re.match(r"\d{4}-\d{2}-\d{2}", x) is not None,
                map(
                    lambda x: x.stem,
                    Path(BACKUP_FOLDER).iterdir()
                )
            ),
            reverse=True
        ))
        print("Available backups:\n" + "; ".join(backups))
        completer = WordCompleter(backups)
        backup_day = (
            prompt("Enter backup folder name (leave empty for most recent): ", completer=completer)
            or backups[0]
        )
        root = Path(f'{BACKUP_FOLDER}/{backup_day}')
    else:
        root = Path.cwd()

    revived_dts: dict[str, str] = json.loads(Path('revived_dts.json').read_text(encoding='utf-8'))
    player_rated_games: defaultdict[str, list[RatedGameInfo]] = defaultdict(list)
    first_games: dict[str, datetime] = {}

    # -- Games --

    game_paths = sorted(
        (root / 'game').iterdir(),
        key=lambda x: int(x.stem)
    )
    game_paths = [p for p in game_paths if p.stem != '5524']

    # Pre-read all game files concurrently (I/O bound)
    with ThreadPoolExecutor() as io_executor:
        game_contents: list[str] = list(io_executor.map(_read_text, game_paths))

    parse_args_list: list[tuple[int, str, str | None]] = [
        (int(p.stem), content, revived_dts.get(p.stem))
        for p, content in zip(game_paths, game_contents)
    ]
    del game_contents

    # Collect player data concurrently with game parsing (no DB writes in this phase)
    follow_rows: list[PlayerFollowedPlayer] = []
    last_activities: dict[str, int] = {}
    _players_exc: list[Exception] = []

    def _collect_players() -> None:
        try:
            for player_path in (root / 'player').iterdir():
                print(f'Player {player_path.stem}')
                data: dict[str, Any] = json.loads(player_path.read_text(encoding='utf-8'))
                new_follow_rows, last_active_at = process_player_file(player_path.stem, data)
                assert last_active_at
                follow_rows.extend(new_follow_rows)
                last_activities[player_path.stem] = last_active_at // 1000
        except Exception as exc:
            _players_exc.append(exc)

    players_thread = threading.Thread(target=_collect_players, name='players', daemon=True)
    players_thread.start()

    # Parse games in parallel (CPU bound), commit in batches
    pending_count = 0
    with ProcessPoolExecutor() as executor:
        for path, (db_objects, rated_info, white_ref, black_ref, started_at) in zip(
            game_paths,
            executor.map(_parse_game, parse_args_list),
        ):
            print(f'Game {path.stem}')
            SESSION.add_all(db_objects)
            pending_count += 1
            if pending_count >= _GAME_COMMIT_BATCH:
                SESSION.commit()
                pending_count = 0

            if started_at.year > 2020:
                if white_ref not in first_games:
                    first_games[white_ref] = started_at - timedelta(minutes=3)
                if black_ref not in first_games:
                    first_games[black_ref] = started_at - timedelta(minutes=3)

            if rated_info is not None:
                for login in rated_info.prior_player_elo:
                    player_rated_games[login].append(rated_info)

    if pending_count:
        SESSION.commit()

    players_thread.join()
    if _players_exc:
        raise _players_exc[0]

    # -- Passwords (needs first_games from games + last_activities from players) --

    print('Passwords')
    raw_passwords: dict[str, str] = json.loads((root / 'other/passwords.json').read_text(encoding='utf-8'))
    players, passwords = process_passwords_file(raw_passwords, first_games, last_activities)
    SESSION.add_all(players)
    SESSION.commit()
    SESSION.add_all(passwords)
    SESSION.commit()
    SESSION.add_all(follow_rows)
    SESSION.commit()

    # -- Studies (FK to player.login, so must run after players committed) --

    study_paths = sorted(
        (root / 'study').iterdir(),
        key=lambda x: int(x.stem)
    )

    def _load_study(study_path: Path) -> Study:
        data: dict[str, Any] = json.loads(study_path.read_text(encoding='utf-8'))
        return process_study(int(study_path.stem), data)

    with ThreadPoolExecutor() as io_executor:
        study_objects: list[Study] = list(io_executor.map(_load_study, study_paths))

    for path, study in zip(study_paths, study_objects):
        print(f'Study {path.stem}')
        SESSION.add(study)
    SESSION.commit()

    # -- Antifraud (FK to player.login + game.id, so must run after both committed) --

    print('Antifraud')
    antifraud_log = (root / 'logs/antifraud.txt').read_text(encoding='utf-8')
    SESSION.add_all(process_log(antifraud_log, player_rated_games))
    SESSION.commit()

    SESSION.close()
