from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from board.constants.sip import DEFAULT_STARTING_SIP_V1
from board.coords import HexCoordinates
from board.deserializers.sip import position_from_sip
from board.opening import OpeningMapping, generate_mapping
from board.piece import PieceColor, PieceKind
from board.ply import Ply
from board.ply_validation import PlyImpossibleException
from board.position import Position
from board.serializers.sip import get_sip

import re

from common.time_control import TimeControlKind
from game.datatypes import OfferAction, OfferKind, OutcomeKind
from game.models.chat import GameChatMessageEvent
from game.models.main import Game
from game.models.offer import GameOfferEvent
from game.models.outcome import GameOutcome
from game.models.ply import GamePlyEvent
from game.models.rollback import GameRollbackEvent
from game.models.time_added import GameTimeAddedEvent
from game.models.time_control import GameFischerTimeControl
from game.models.time_update import GameTimeUpdate, GameTimeUpdateReason


@dataclass
class RatedGameInfo:
    game_id: int
    prior_player_elo: dict[str, int]
    started_at: datetime


TIME_PATTERN = re.compile(r'#T\|(\d+?)/(\d+?);')
PLAYER_PATTERN = re.compile(r'#P\|([A-Za-z0-9_+]+?)/([A-Za-z0-9_+]+?);')
DATETIME_PATTERN = re.compile(r'#D\|(\d+);')
ELO_PATTERN = re.compile(r'#e\|(.+?)/(.+?);')
OUTCOME_PATTERN = re.compile(r'#R\|(.+?)/(.+?)(\s*$|;)')
SIP_PATTERN = re.compile(r'#S\|(.+?);')
REMAINDERS_PATTERN = re.compile(r'#L\|(\d+?)/(\d+?)(\s*$|;)')

MSK_TZ = timezone(timedelta(hours=3))

OPENINGS = generate_mapping()


def cast_ref(raw_ref: str) -> str:
    if raw_ref == "+stconda":
        return "+Anaconda"
    else:
        return raw_ref


def cast_elo(raw_elo: str) -> tuple[int, bool]:
    if raw_elo == "n":
        return 1200, True
    elif raw_elo.startswith("p"):
        return int(raw_elo.replace('p', '')), True
    else:
        return int(raw_elo), False


def get_players(full_log: str) -> tuple[str, str] | None:
    result = PLAYER_PATTERN.search(full_log)

    if result is None:
        return None

    return cast_ref(result.group(1)), cast_ref(result.group(2))


def get_ratings(full_log: str) -> tuple[tuple[int, bool], tuple[int, bool]] | None:
    result = ELO_PATTERN.search(full_log)

    if result is None:
        return None

    return cast_elo(result.group(1)), cast_elo(result.group(2))


def get_starting_sip(full_log: str) -> str | None:
    result = SIP_PATTERN.search(full_log)
    return result.group(1) if result else None


def get_remainders(full_log: str) -> tuple[int, int] | None:
    result = REMAINDERS_PATTERN.search(full_log)
    if not result:
        return result
    return int(result.group(1)), int(result.group(2))


def get_time_control(game_id: int, full_log: str) -> GameFischerTimeControl | None:
    if game_id <= 815:
        return GameFischerTimeControl(start_seconds=600, increment_seconds=5)

    result = TIME_PATTERN.search(full_log)

    if result is None:
        print(f"{game_id}: no time found")
        return GameFischerTimeControl(start_seconds=600, increment_seconds=5)

    start_seconds = int(result.group(1))
    increment_seconds = int(result.group(2))
    if start_seconds == increment_seconds == 0:
        return None

    return GameFischerTimeControl(start_seconds=int(result.group(1)), increment_seconds=int(result.group(2)))


def get_outcome(game_id: int, full_log: str, ended_at: datetime, time_update: GameTimeUpdate | None) -> GameOutcome | None:
    if game_id in (431,):
        return GameOutcome(game_ended_at=ended_at, kind=OutcomeKind.CHEATING_ABORT, winner=PieceColor.BLACK, time_update=time_update)

    result = OUTCOME_PATTERN.search(full_log)
    if not result:
        if "+stconda" in full_log:
            return GameOutcome(game_ended_at=ended_at, kind=OutcomeKind.ABORT, winner=None, time_update=time_update)
        else:
            if '#T|0/0' not in full_log:
                raise ValueError(f"{game_id}: no outcome found")
            return None

    winner_code = result.group(1)
    reason_code = result.group(2)

    if winner_code == "w":
        winner = PieceColor.WHITE
    elif winner_code == "b":
        winner = PieceColor.BLACK
    else:
        winner = None

    reason_mapping = dict(
        unk=OutcomeKind.ABANDON if winner else OutcomeKind.ABORT,
        rep=OutcomeKind.REPETITION,
        agr=OutcomeKind.DRAW_AGREEMENT,
        abo=OutcomeKind.ABORT,
        res=OutcomeKind.RESIGN,
        bre=OutcomeKind.BREAKTHROUGH,
        mat=OutcomeKind.FATUM,
        tim=OutcomeKind.TIMEOUT,
        aba=OutcomeKind.ABANDON,
    )
    reason_mapping["100"] = OutcomeKind.NO_PROGRESS

    return GameOutcome(game_ended_at=ended_at, kind=reason_mapping[reason_code], winner=winner, time_update=time_update)


def get_datetime(full_log: str) -> datetime | None:
    result = DATETIME_PATTERN.search(full_log)
    if not result:
        return None

    unix_secs = int(result.group(1))
    return datetime.fromtimestamp(unix_secs, tz=UTC)


def clone_time_update(original: GameTimeUpdate) -> GameTimeUpdate:
    return GameTimeUpdate(
        updated_at=original.updated_at,
        white_ms=original.white_ms,
        black_ms=original.black_ms,
        ticking_side=original.ticking_side,
        reason=original.reason,
        game_id=original.game_id
    )


def parse_log(game_id: int, full_log: str, revived_dt: str | None) -> tuple[list[object], RatedGameInfo | None, str, str, datetime]:
    added_objects: list[object] = []

    players = get_players(full_log)
    ratings = get_ratings(full_log)
    time_control = get_time_control(game_id, full_log)

    if not players:
        raise ValueError(f"No players: {game_id}")

    white_ref, black_ref = players

    starting_sip = get_starting_sip(full_log)
    if starting_sip == DEFAULT_STARTING_SIP_V1 or not starting_sip:
        position = Position.default_starting()
        starting_sip = None
    else:
        position = position_from_sip(starting_sip)
        starting_sip = get_sip(position)  # to v2

    move_cnt = 0
    opening_sip = starting_sip
    latest_sip = starting_sip

    ply_events: list[GamePlyEvent] = []
    chat_message_events: list[GameChatMessageEvent] = []
    offer_events: list[GameOfferEvent] = []
    time_added_events: list[GameTimeAddedEvent] = []
    rollback_events: list[GameRollbackEvent] = []

    started_at = get_datetime(full_log) or (datetime.fromisoformat(revived_dt) if revived_dt else None) or datetime.fromtimestamp(0, UTC)
    event_time = started_at
    time_update = GameTimeUpdate(
        updated_at=event_time,
        white_ms=time_control.start_seconds * 1000,
        black_ms=time_control.start_seconds * 1000,
        ticking_side=None,
        reason=GameTimeUpdateReason.INIT,
        game_id=game_id
    ) if time_control else None
    if time_update:
        added_objects.append(time_update)
        time_update = clone_time_update(time_update)

    for line in full_log.splitlines():
        line = line.removesuffix(";")

        if line.startswith("#"):
            code, remainder = line.removeprefix("#").split("|", 1)
            args = remainder.split("/")
            if code == "C":
                event_time += timedelta(seconds=1)
                chat_message_events.append(GameChatMessageEvent(
                    occurred_at=event_time,
                    text=args[1][:255],
                    spectator=False,
                    author_ref=white_ref if args[0] == "w" else black_ref
                ))
            elif code == "E":
                if args[0] == "tad":
                    event_time += timedelta(seconds=1)
                    if not time_update:
                        continue

                    time_update.updated_at = event_time
                    time_update.reason = GameTimeUpdateReason.TIME_ADDED
                    if args[1] == 'w':
                        time_update.white_ms += 15000
                        receiver = PieceColor.WHITE
                    else:
                        time_update.black_ms += 15000
                        receiver = PieceColor.BLACK

                    time_added_events.append(GameTimeAddedEvent(
                        occurred_at=event_time,
                        amount_seconds=15,
                        receiver=receiver,
                        time_update=time_update
                    ))
                    time_update = clone_time_update(time_update)
                    continue

                offer_kind = None
                if args[0][0] == "d" and args[0] != "dcn":
                    offer_kind = OfferKind.DRAW
                elif args[0][0] == "t":
                    offer_kind = OfferKind.TAKEBACK
                if not offer_kind:
                    continue

                offer_action_color = PieceColor.WHITE if len(args) < 2 or args[1] == 'w' else PieceColor.BLACK

                if args[0][1:] == "of":
                    offer_action = OfferAction.CREATE
                    offer_author = offer_action_color
                elif args[0][1:] == "ca":
                    offer_action = OfferAction.CANCEL
                    offer_author = offer_action_color
                elif args[0][1:] == "ac":
                    offer_action = OfferAction.ACCEPT
                    offer_author = offer_action_color.opposite()
                elif args[0][1:] == "de":
                    offer_action = OfferAction.DECLINE
                    offer_author = offer_action_color.opposite()
                else:
                    raise ValueError(f'Unknown event: {line}')

                event_time += timedelta(seconds=1)
                offer_events.append(GameOfferEvent(
                    occurred_at=event_time,
                    action=offer_action,
                    offer_kind=offer_kind,
                    offer_author=offer_author
                ))

                if offer_action == OfferAction.ACCEPT and offer_kind == OfferKind.TAKEBACK:
                    event_time += timedelta(seconds=1)
                    if time_update:
                        time_update.updated_at = event_time
                        time_update.reason = GameTimeUpdateReason.ROLLBACK
                    rollback_events.append(GameRollbackEvent(
                        occurred_at=event_time,
                        ply_cnt_before=move_cnt + 1,
                        ply_cnt_after=move_cnt,
                        requested_by=offer_author,
                        time_update=time_update
                    ))
                    if time_update:
                        time_update = clone_time_update(time_update)
            continue

        parts = line.split("/")
        raw_ply = parts[0]
        ply_num = move_cnt + 1

        if len(raw_ply) < 4:
            raise ValueError(
                f"Invalid ply {ply_num} (raw: {raw_ply})\n"
                f"Game: {game_id}\n"
            )

        ply = Ply(
            departure=HexCoordinates(int(raw_ply[0]), int(raw_ply[1])),
            destination=HexCoordinates(int(raw_ply[2]), int(raw_ply[3]))
        )
        if len(raw_ply) > 4:
            raw_morph_into = raw_ply[4:]
            match raw_morph_into:
                case "Aggressor":
                    ply.morph_into = PieceKind.AGGRESSOR
                case "Liberator":
                    ply.morph_into = PieceKind.LIBERATOR
                case "Progressor":
                    ply.morph_into = PieceKind.PROGRESSOR
                case "Defensor":
                    ply.morph_into = PieceKind.DEFENSOR
                case "Dominator":
                    ply.morph_into = PieceKind.DOMINATOR
                case _:
                    if game_id == 431:  # Cheating
                        break
                    if game_id not in (596, 613):  # Fatum with morphing
                        raise ValueError(
                            f"Invalid morph type ({raw_morph_into}) in ply {ply_num} (raw: {raw_ply})\n"
                            f"Game: {game_id}\n"
                        )

        try:
            ply_output = position.perform_ply(ply, validate=True, allow_progressor_aura=game_id < 100, pre_check_finality=True)
            position = ply_output.new_position
        except PlyImpossibleException as e:
            raise ValueError(
                f"Impossible ply {ply_num} (raw: {raw_ply})\n"
                f"Game: {game_id}\n"
                f"Position: {get_sip(position)}\n"
                f"Finality: {position.get_finality_group().name}"
            ) from e

        move_cnt += 1

        event_time += timedelta(seconds=1)
        if time_update:
            time_update.updated_at = event_time
            time_update.reason = GameTimeUpdateReason.PLY
            time_update.ticking_side = position.color_to_move if move_cnt >= 2 else None
            if len(parts) == 3:
                time_update.white_ms = int(parts[1])
                time_update.black_ms = int(parts[2])

        new_sip = get_sip(position)
        latest_sip = new_sip
        if new_sip in OPENINGS.mapping:
            opening_sip = new_sip

        ply_events.append(GamePlyEvent(
            occurred_at=event_time,
            ply_index=move_cnt - 1,
            from_i=ply.departure.i,
            from_j=ply.departure.j,
            to_i=ply.destination.i,
            to_j=ply.destination.j,
            morph_into=ply.morph_into,
            kind=ply_output.properties.ply_kind,
            moving_color=ply_output.properties.moving_piece.color,
            moved_piece=ply_output.properties.moving_piece.kind,
            target_piece=ply_output.properties.target_piece.kind if ply_output.properties.target_piece else None,
            sip_after=new_sip,
            time_update=time_update
        ))

        if time_update:
            time_update = clone_time_update(time_update)

    last_remainders = get_remainders(full_log)
    event_time += timedelta(seconds=1)
    if time_update:
        time_update.updated_at = event_time
        time_update.reason = GameTimeUpdateReason.GAME_ENDED
        time_update.ticking_side = None
        if last_remainders:
            time_update.white_ms = last_remainders[0]
            time_update.black_ms = last_remainders[1]
    outcome = get_outcome(game_id, full_log, event_time, time_update)

    added_objects.append(
        Game(
            started_at=started_at,
            time_control_kind=TimeControlKind.of(time_control),
            rated=ratings is not None,
            custom_starting_sip=starting_sip,
            external_uploader_ref=None,
            id=game_id,
            white_player_ref=white_ref,
            black_player_ref=black_ref,
            latest_sip=latest_sip,
            opening_sip=opening_sip,
            fischer_time_control=time_control,
            outcome=outcome,
            ply_events=ply_events,
            chat_message_events=chat_message_events,
            offer_events=offer_events,
            time_added_events=time_added_events,
            rollback_events=rollback_events
        )
    )

    rated_info = None
    if ratings is not None:
        exact_started_at = get_datetime(full_log)
        assert exact_started_at
        rated_info = RatedGameInfo(
            game_id=game_id,
            prior_player_elo={
                white_ref: ratings[0][0],
                black_ref: ratings[1][0],
            },
            started_at=exact_started_at
        )

    return added_objects, rated_info, white_ref, black_ref, started_at
