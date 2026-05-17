from collections import defaultdict
from datetime import timedelta
import json
from pathlib import Path

import re
import os

from sqlalchemy import create_engine
from sqlmodel import Session
from config.loader import load

from config.models import SecretConfig
from migration.antifraud import process_log
from migration.game import parse_log
from migration.player import process_passwords_file, process_player_file
from migration.study import process_study


IS_TEST = os.getenv("STAGE", "TEST")
BACKUP_FOLDER = os.getenv("INTELLECTOR_BACKUP_DIR") or "C:/Users/mitmi/YandexDisk/backup"
SECRET_CONFIG = load('secret', SecretConfig)
DB_ENGINE = create_engine(SECRET_CONFIG.db.url.replace("aiomysql", "pymysql"))
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
    backup_day = prompt("Enter backup folder name (leave empty for most recent): ", completer=completer) or backups[0]
    root = Path(f'{BACKUP_FOLDER}/{backup_day}')
else:
    root = Path.cwd()


revived_dts = json.loads(Path('revived_dts.json').read_text(encoding='utf-8'))
player_rated_games = defaultdict(list)
first_games = {}


iterated_paths = sorted(
    (root / 'game').iterdir(),
    key=lambda x: int(x.stem)
)
for path in iterated_paths:
    if path.stem == '5524':
        continue
    print(f'Game {path.stem}')

    full_log = path.read_text(encoding='utf-8')
    db_objects, rated_info, white_ref, black_ref, started_at = parse_log(int(path.stem), full_log, revived_dts.get(path.stem))
    SESSION.add_all(db_objects)
    SESSION.commit()

    if started_at.year > 2020:
        if white_ref not in first_games:
            first_games[white_ref] = started_at - timedelta(minutes=3)
        if black_ref not in first_games:
            first_games[black_ref] = started_at - timedelta(minutes=3)

    if rated_info:
        for login, elo in rated_info.prior_player_elo.items():
            player_rated_games[login].append(rated_info)


follow_rows = []
last_activities = {}
for path in (root / 'player').iterdir():
    print(f'Player {path.stem}')

    data = json.loads(path.read_text(encoding='utf-8'))
    new_follow_rows, last_active_at = process_player_file(path.stem, data)
    assert last_active_at
    follow_rows += new_follow_rows
    last_activities[path.stem] = last_active_at // 1000


print('Passwords')
raw_passwords = json.loads(Path('converted_passes.json').read_text(encoding='utf-8'))
players, passwords = process_passwords_file(raw_passwords, first_games, last_activities)
SESSION.add_all(players)
SESSION.commit()
SESSION.add_all(passwords)
SESSION.commit()
SESSION.add_all(follow_rows)
SESSION.commit()


iterated_paths = sorted(
    (root / 'study').iterdir(),
    key=lambda x: int(x.stem)
)
for path in iterated_paths:
    print(f'Study {path.stem}')

    data = json.loads(path.read_text(encoding='utf-8'))
    study = process_study(int(path.stem), data)
    SESSION.add(study)
    SESSION.commit()


print('Antifraud')
antifraud_log = (root / 'logs/antifraud.txt').read_text(encoding='utf-8')
SESSION.add_all(process_log(antifraud_log, player_rated_games))
SESSION.commit()


SESSION.close()
