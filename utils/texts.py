from typing import TYPE_CHECKING, assert_never

from utils.datatypes import ChallengeAcceptorColor, FischerTimeControlEntity, UserReference

if TYPE_CHECKING:
    from models import ChallengePublic, GamePublic


def format_time_control(time_control: FischerTimeControlEntity | None) -> str | None:
    if not time_control:
        return None
    if time_control.start_seconds % 60 == 0:
        formatted_start_secs = str(time_control.start_seconds // 60)
    elif time_control.start_seconds > 60:
        formatted_start_secs = f"{time_control.start_seconds // 60}m{time_control.start_seconds % 60}s"
    else:
        formatted_start_secs = f"{time_control.start_seconds % 60}s"
    return f"{formatted_start_secs}+{time_control.increment_seconds}"


DISCORD_NEW_CHALLENGE_MESSAGE_TEMPLATE = """
New open challenge by **{pretty_caller_ref}**
*{bracket}*
Time control: {time_control}
Color: {color}
Starting position: {start_pos}
https://intellector.info/game/?p=join/{challenge_id}
"""


def get_discord_new_challenge_message(challenge: ChallengePublic, pretty_caller_ref: str | None = None) -> str:
    if not pretty_caller_ref:
        callee = UserReference(challenge.caller_ref)
        if callee.is_guest():
            pretty_caller_ref = f"Guest {callee.guest_id}"
        else:
            pretty_caller_ref = callee.login

    bracket = "Rated" if challenge.rated else "Unrated"
    time_control = format_time_control(challenge.fischer_time_control) or "Correspondence"
    match challenge.acceptor_color:
        case ChallengeAcceptorColor.WHITE:
            color = "White"
        case ChallengeAcceptorColor.BLACK:
            color = "Black"
        case ChallengeAcceptorColor.RANDOM:
            color = "Random"
        case _:
            assert_never(challenge.acceptor_color)
    start_pos = "Custom" if challenge.custom_starting_sip else "Default"

    return DISCORD_NEW_CHALLENGE_MESSAGE_TEMPLATE.format(
        pretty_caller_ref=pretty_caller_ref,
        bracket=bracket,
        time_control=time_control,
        color=color,
        start_pos=start_pos,
        challenge_id=challenge.id
    )


VK_NEW_CHALLENGE_MESSAGE_TEMPLATE = """
🗣 Открытый вызов от {pretty_caller_ref}
{bracket}
Контроль: {time_control}
Цвет: {color}
Начальная позиция: {start_pos}
https://intellector.info/game/?p=join/{challenge_id}
"""


def get_vk_new_challenge_message(challenge: ChallengePublic, pretty_caller_ref: str | None = None) -> str:
    if not pretty_caller_ref:
        callee = UserReference(challenge.caller_ref)
        if callee.is_guest():
            pretty_caller_ref = f"гостя {callee.guest_id}"
        else:
            pretty_caller_ref = callee.login

    bracket = "На рейтинг" if challenge.rated else "Без рейтинга"
    time_control = format_time_control(challenge.fischer_time_control) or "По переписке"
    match challenge.acceptor_color:
        case ChallengeAcceptorColor.WHITE:
            color = "Белыми"
        case ChallengeAcceptorColor.BLACK:
            color = "Черными"
        case ChallengeAcceptorColor.RANDOM:
            color = "Случайно"
        case _:
            assert_never(challenge.acceptor_color)
    start_pos = "Особая" if challenge.custom_starting_sip else "Стандартная"

    return VK_NEW_CHALLENGE_MESSAGE_TEMPLATE.format(
        pretty_caller_ref=pretty_caller_ref,
        bracket=bracket,
        time_control=time_control,
        color=color,
        start_pos=start_pos,
        challenge_id=challenge.id
    )


VK_NEW_GAME_MESSAGE_TEMPLATE = """
🔥 Игра началась!
{pretty_white_ref} против {pretty_black_ref}
Контроль: {time_control}
https://intellector.info/game/?p=live/{game_id}
"""


def get_vk_new_game_message(game: GamePublic, pretty_white_ref: str | None, pretty_black_ref: str | None) -> str:
    if not pretty_white_ref:
        white = UserReference(game.white_player_ref)
        if white.is_guest():
            pretty_white_ref = f"Гость {white.guest_id}"
        else:
            pretty_white_ref = white.login

    if not pretty_black_ref:
        black = UserReference(game.black_player_ref)
        if black.is_guest():
            pretty_black_ref = f"гостя {black.guest_id}"
        else:
            pretty_black_ref = black.login

    time_control = format_time_control(game.fischer_time_control) or "По переписке"

    return VK_NEW_GAME_MESSAGE_TEMPLATE.format(
        pretty_white_ref=pretty_white_ref,
        pretty_black_ref=pretty_black_ref,
        time_control=time_control,
        game_id=game.id
    )
