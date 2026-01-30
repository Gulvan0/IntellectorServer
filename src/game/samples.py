from dataclasses import dataclass
from datetime import datetime, timedelta
from math import floor
from random import choice, randint, random, randrange, uniform
from typing import Literal

from board.deserializers.sip import position_from_sip
from board.position import Position
from board.serializers.sip import get_sip
from common.models import UserRefWithNickname
from common.samples import (
    SampleTimeControl,
    bot_user_ref_with_nickname,
    guest_ref_with_nickname,
    string,
    uint,
    user_ref_with_nickname,
    time_control as sample_time_control,
    boolean,
    underscore_str,
    past_datetime,
)
from common.time_control import TimeControlKind
from game.datatypes import OfferAction, OfferKind, OutcomeKind
from game.models.chat import ChatMessageBroadcastedData, GameChatMessageEventPublic
from game.models.main import GamePublic, GameStartedBroadcastedData, GenericEventList
from board.samples import non_default_starting_position, piece_color, playthrough, valid_non_final_sip
from board.piece import PieceColor
from game.models.offer import GameOfferEventPublic, OfferActionBroadcastedData
from game.models.outcome import GameEndedBroadcastedData, GameEndedEloUpdate, GameEndedEloUpdates, GameOutcomePublic
from game.models.ply import GamePlyEventPublic, PlyBroadcastedData
from game.models.rollback import RollbackBroadcastedData
from game.models.time_added import GameTimeAddedEventPublic, TimeAddedBroadcastedData
from game.models.time_control import GameFischerTimeControlPublic
from game.models.time_update import GameTimeUpdatePublic, GameTimeUpdateReason
from pubsub.models.state import GameStateRefresh


@dataclass
class SampleGameState:
    outcome: GameOutcomePublic | None
    events: GenericEventList
    latest_time_update: GameTimeUpdatePublic | None


def sample_time_update(reason: GameTimeUpdateReason) -> GameTimeUpdatePublic:
    return GameTimeUpdatePublic(
        white_ms=randint(1, 7200000),
        black_ms=randint(1, 7200000),
        ticking_side=choice([PieceColor.WHITE, PieceColor.BLACK, None]),
        reason=reason
    )


def ply_broadcasted_data() -> PlyBroadcastedData:
    old_position = non_default_starting_position()
    ply = choice(old_position.available_plys())
    new_sip = get_sip(old_position.perform_ply(ply).new_position)

    return PlyBroadcastedData(
        occurred_at=past_datetime(min_offset_secs=3, max_offset_secs=600),
        ply_index=randint(0, 50),
        from_i=ply.departure.i,
        from_j=ply.departure.j,
        to_i=ply.destination.i,
        to_j=ply.destination.j,
        morph_into=ply.morph_into,
        game_id=uint(),
        sip_after=new_sip
    )


def chat_message_broadcasted_data(is_author_guest: bool | None = None) -> ChatMessageBroadcastedData:
    if is_author_guest is None:
        is_author_guest = boolean()

    return ChatMessageBroadcastedData(
        occurred_at=past_datetime(min_offset_secs=3, max_offset_secs=600),
        text=string(),
        spectator=boolean(),
        author=guest_ref_with_nickname() if is_author_guest else user_ref_with_nickname(),
        game_id=uint()
    )


def offer_action_broadcasted_data() -> OfferActionBroadcastedData:
    return OfferActionBroadcastedData(
        occurred_at=past_datetime(min_offset_secs=3, max_offset_secs=600),
        action=choice(list(OfferAction)),
        offer_kind=choice(list(OfferKind)),
        offer_author=piece_color(),
        game_id=uint()
    )


def time_added_broadcasted_data() -> TimeAddedBroadcastedData:
    return TimeAddedBroadcastedData(
        occurred_at=past_datetime(min_offset_secs=3, max_offset_secs=600),
        amount_seconds=randint(10, 15),
        receiver=piece_color(),
        game_id=uint(),
        time_update=sample_time_update(GameTimeUpdateReason.TIME_ADDED)
    )


def rollback_broadcasted_data() -> RollbackBroadcastedData:
    ply_cnt_before = randint(1, 60)
    return RollbackBroadcastedData(
        occurred_at=past_datetime(min_offset_secs=3, max_offset_secs=600),
        ply_cnt_before=ply_cnt_before,
        ply_cnt_after=max(0, ply_cnt_before - randint(1, 2)),
        requested_by=piece_color(),
        game_id=uint(),
        time_update=sample_time_update(GameTimeUpdateReason.ROLLBACK),
        updated_sip=valid_non_final_sip()
    )


def game_state(
    white_player: UserRefWithNickname | None = None,
    black_player: UserRefWithNickname | None = None,
    started_at: datetime | None = None,
    time_control: SampleTimeControl | None = None,
    starting_position: Position | None = None,
    finished: bool | None = None,
) -> SampleGameState:
    if not white_player:
        white_player = user_ref_with_nickname()
    if not black_player:
        black_player = user_ref_with_nickname()
    if not started_at:
        started_at = past_datetime(min_offset_days=3, max_offset_days=120)
    if not time_control:
        time_control = sample_time_control()
    if not starting_position:
        starting_position = non_default_starting_position()
    if finished is None:
        finished = boolean()

    first_ply_color = starting_position.color_to_move
    plys = playthrough(starting_position)
    current_time = started_at
    if time_control.kind != TimeControlKind.CORRESPONDENCE:
        time_update = GameTimeUpdatePublic(
            updated_at=started_at,
            white_ms=time_control.start_seconds * 1000,
            black_ms=time_control.start_seconds * 1000,
            ticking_side=None,
            reason=GameTimeUpdateReason.INIT
        )
    else:
        time_update = None

    chat_message_after_ply_index = randrange(0, len(plys))
    cancelled_offer_after_ply_index = randrange(0, len(plys))
    time_added_after_ply_index = randrange(0, len(plys)) if time_control.kind != TimeControlKind.CORRESPONDENCE else -1

    events: GenericEventList = []
    for ply_index, ply in enumerate(plys):
        if time_control.kind != TimeControlKind.CORRESPONDENCE:
            ms_spent = randint(10, time_control.start_seconds * 100)  # 10% of initial time
        else:
            ms_spent = randint(1000, 10000)

        if time_update:
            ply_color = first_ply_color if ply_index % 2 == 0 else first_ply_color.opposite()
            if ply_index >= 1:
                time_update.ticking_side = ply_color.opposite()

            if ply_index >= 2:
                wasted_time_share = ply_index * 0.1 * uniform(0.5, 1.5)
                if ply_color == PieceColor.WHITE:
                    ms_spent = floor(time_update.white_ms * wasted_time_share)
                    time_update.white_ms -= ms_spent - time_control.increment_seconds * 1000
                else:
                    ms_spent = floor(time_update.black_ms * wasted_time_share)
                    time_update.black_ms -= ms_spent - time_control.increment_seconds * 1000

        current_time += timedelta(milliseconds=ms_spent)

        if time_update:
            time_update.reason = GameTimeUpdateReason.PLY
            time_update.updated_at = current_time

        events.append(GamePlyEventPublic(
            occurred_at=current_time,
            ply_index=ply_index,
            from_i=ply.departure.i,
            from_j=ply.departure.j,
            to_i=ply.destination.i,
            to_j=ply.destination.j,
            morph_into=ply.morph_into,
            time_update=time_update
        ))

        if time_update:
            time_update = time_update.model_copy()

        if ply_index == chat_message_after_ply_index:
            current_time += timedelta(seconds=0.5 + random() * 3)
            events.append(GameChatMessageEventPublic(
                occurred_at=current_time,
                author=white_player if boolean() else black_player,
                text=string(),
                spectator=False
            ))

            current_time += timedelta(seconds=0.5 + random())
            events.append(GameChatMessageEventPublic(
                occurred_at=current_time,
                author=user_ref_with_nickname(),
                text=string(),
                spectator=True
            ))

        if ply_index == cancelled_offer_after_ply_index:
            offer_author = piece_color()

            current_time += timedelta(seconds=0.5 + random() * 3)
            events.append(GameOfferEventPublic(
                occurred_at=current_time,
                action=OfferAction.CREATE,
                offer_kind=OfferKind.TAKEBACK,
                offer_author=offer_author
            ))

            current_time += timedelta(seconds=0.5 + random())
            events.append(GameOfferEventPublic(
                occurred_at=current_time,
                action=choice([OfferAction.CANCEL, OfferAction.DECLINE]),
                offer_kind=OfferKind.TAKEBACK,
                offer_author=offer_author
            ))

        if ply_index == time_added_after_ply_index and time_update:
            current_time += timedelta(seconds=0.5 + random() * 3)

            receiver = piece_color()
            amount_seconds = randint(10, 15)

            secs_passed = (current_time - time_update.updated_at).total_seconds()
            ms_passed = floor(secs_passed * 1000)

            time_update.updated_at = current_time
            time_update.reason = GameTimeUpdateReason.TIME_ADDED

            if receiver == PieceColor.WHITE:
                time_update.white_ms += amount_seconds * 1000
            else:
                time_update.black_ms += amount_seconds * 1000

            if time_update.ticking_side == PieceColor.WHITE:
                time_update.white_ms -= ms_passed
            elif time_update.ticking_side == PieceColor.BLACK:
                time_update.black_ms -= ms_passed

            events.append(GameTimeAddedEventPublic(
                occurred_at=current_time,
                amount_seconds=amount_seconds,
                receiver=receiver,
                time_update=time_update
            ))

            time_update = time_update.model_copy()

    outcome = None
    if finished:
        current_time += timedelta(seconds=0.5 + random() * 3)

        if time_update:
            time_update.updated_at = current_time
            time_update.reason = GameTimeUpdateReason.GAME_ENDED
            time_update.ticking_side = None

            secs_passed = (current_time - time_update.updated_at).total_seconds()
            ms_passed = floor(secs_passed * 1000)

            if time_update.ticking_side == PieceColor.WHITE:
                time_update.white_ms -= ms_passed
            elif time_update.ticking_side == PieceColor.BLACK:
                time_update.black_ms -= ms_passed

        outcome = GameOutcomePublic(
            game_ended_at=current_time,
            kind=choice([OutcomeKind.RESIGN, OutcomeKind.ABANDON]),
            winner=piece_color(),
            time_update=time_update
        )

    return SampleGameState(
        outcome=outcome,
        events=events,
        latest_time_update=time_update
    )


def game_started_data(
    players: tuple[UserRefWithNickname | None, UserRefWithNickname] | None = None,
    time_control: SampleTimeControl | None = None,
    rated: bool | None = None,
    custom_starting_sip: str | Literal['AUTO'] | None = 'AUTO',
    external_uploader_login: str | Literal['GENERATE'] | None = None,
    started_at: datetime | None = None
) -> tuple[GameStartedBroadcastedData, Position]:
    if not players:
        players = (user_ref_with_nickname(), user_ref_with_nickname())
    elif not players[0]:
        players = (user_ref_with_nickname(), players[1])

    if not time_control:
        time_control = sample_time_control(exclude_correspondence=True)

    if rated is None:
        rated = boolean()

    if custom_starting_sip == 'AUTO' and not rated:
        starting_position = non_default_starting_position()
        custom_starting_sip = get_sip(starting_position)
    elif custom_starting_sip and custom_starting_sip != 'AUTO':
        starting_position = position_from_sip(custom_starting_sip)
    else:
        starting_position = Position.default_starting()
        custom_starting_sip = None

    if external_uploader_login == 'GENERATE':
        external_uploader_ref = underscore_str()
    elif external_uploader_login:
        external_uploader_ref = external_uploader_login
    else:
        external_uploader_ref = None

    if not started_at:
        started_at = past_datetime(min_offset_days=3, max_offset_days=200)

    return (
        GameStartedBroadcastedData(
            started_at=started_at,
            white_player=players[0],
            black_player=players[1],
            time_control_kind=time_control.kind,
            rated=rated,
            custom_starting_sip=custom_starting_sip,
            external_uploader_ref=external_uploader_ref,
            id=uint(),
            fischer_time_control=GameFischerTimeControlPublic(
                start_seconds=time_control.start_seconds,
                increment_seconds=time_control.increment_seconds
            ) if time_control.kind != TimeControlKind.CORRESPONDENCE else None,
        ),
        starting_position
    )


def game(
    players: tuple[UserRefWithNickname | None, UserRefWithNickname] | None = None,
    time_control: SampleTimeControl | None = None,
    rated: bool | None = None,
    custom_starting_sip: str | Literal['AUTO'] | None = 'AUTO',
    external_uploader_login: str | Literal['GENERATE'] | None = None,
    finished: bool | None = None,
    started_at: datetime | None = None
) -> GamePublic:
    startup_data, starting_position = game_started_data(players, time_control, rated, custom_starting_sip, external_uploader_login, started_at)

    if finished is None:
        finished = boolean()

    state = game_state(
        white_player=startup_data.white_player,
        black_player=startup_data.black_player,
        started_at=startup_data.started_at,
        time_control=SampleTimeControl(
            startup_data.time_control_kind,
            startup_data.fischer_time_control.start_seconds if startup_data.fischer_time_control else 0,
            startup_data.fischer_time_control.increment_seconds if startup_data.fischer_time_control else 0
        ),
        starting_position=starting_position,
        finished=finished
    )

    return GamePublic(
        started_at=startup_data.started_at,
        white_player=startup_data.white_player,
        black_player=startup_data.black_player,
        time_control_kind=startup_data.time_control_kind,
        rated=startup_data.rated,
        custom_starting_sip=startup_data.custom_starting_sip,
        external_uploader_ref=startup_data.external_uploader_ref,
        id=startup_data.id,
        fischer_time_control=startup_data.fischer_time_control,
        outcome=state.outcome,
        events=state.events,
        latest_time_update=state.latest_time_update
    )


def minimal_representative_games(common_player: UserRefWithNickname | None = None) -> list[GamePublic]:
    bot_game_player = common_player or user_ref_with_nickname()
    return [
        game(
            players=(bot_game_player, bot_user_ref_with_nickname()),
            time_control=sample_time_control(TimeControlKind.CORRESPONDENCE),
            rated=False,
            custom_starting_sip='AUTO',
            external_uploader_login=bot_game_player.user_ref,
            finished=True
        ),
        game(
            players=(None, common_player) if common_player else None,
            time_control=sample_time_control(TimeControlKind.RAPID),
            rated=True,
            custom_starting_sip=None,
            finished=False
        ),
    ]


def game_state_refreshes(count: int = 3) -> list[GameStateRefresh]:
    result = []
    for i in range(count):
        state = game_state(finished=i != 1 and (i == 0 or boolean()))  # First game is guaranteed to be finished, second one - in-progress
        result.append(GameStateRefresh(
            game_id=uint(),
            refresh_reason=choice(['invalid_move', 'sub']),
            outcome=state.outcome,
            events=state.events,
            latest_time_update=state.latest_time_update
        ))
    return result


def game_started_data_samples() -> list[GameStartedBroadcastedData]:
    return [
        game_started_data(
            players=(None, bot_user_ref_with_nickname()),
            rated=False,
            custom_starting_sip='AUTO',
            external_uploader_login='GENERATE'
        )[0],
        game_started_data(rated=True)[0],
    ]


def game_ended_data_samples(count: int = 3) -> list[GameEndedBroadcastedData]:
    result = []

    for i in range(count):
        outcome_kind = OutcomeKind(choice(list(OutcomeKind)))
        result.append(GameEndedBroadcastedData(
            kind=outcome_kind,
            winner=None if outcome_kind.drawish else choice([PieceColor.WHITE, PieceColor.BLACK]),
            game_id=uint(),
            time_update=sample_time_update(GameTimeUpdateReason.GAME_ENDED),
            elo=GameEndedEloUpdates(
                white=GameEndedEloUpdate(new_value=randint(100, 2500), delta=randint(-50, 50)),
                black=GameEndedEloUpdate(new_value=randint(100, 2500), delta=randint(-50, 50)),
            ) if i != 1 else None
        ))

    return result
