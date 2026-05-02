from challenge.datatypes import ChallengeAcceptorColor
from challenge.models import ChallengePublic
from common.time_control import FischerTimeControlEntity
from game.models.main import GameSummaryPublic


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


def get_discord_new_challenge_message(challenge: ChallengePublic) -> str:
    bracket = "Rated" if challenge.rated else "Unrated"
    time_control = format_time_control(challenge.fischer_time_control) or "Correspondence"
    match challenge.acceptor_color:
        case ChallengeAcceptorColor.WHITE:
            color = "White"
        case ChallengeAcceptorColor.BLACK:
            color = "Black"
        case ChallengeAcceptorColor.RANDOM:
            color = "Random"
    start_pos = "Custom" if challenge.custom_starting_sip else "Default"

    return DISCORD_NEW_CHALLENGE_MESSAGE_TEMPLATE.format(
        pretty_caller_ref=challenge.caller.nickname,
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


def get_vk_new_challenge_message(challenge: ChallengePublic) -> str:
    bracket = "На рейтинг" if challenge.rated else "Без рейтинга"
    time_control = format_time_control(challenge.fischer_time_control) or "По переписке"
    match challenge.acceptor_color:
        case ChallengeAcceptorColor.WHITE:
            color = "Белыми"
        case ChallengeAcceptorColor.BLACK:
            color = "Черными"
        case ChallengeAcceptorColor.RANDOM:
            color = "Случайно"
    start_pos = "Особая" if challenge.custom_starting_sip else "Стандартная"

    return VK_NEW_CHALLENGE_MESSAGE_TEMPLATE.format(
        pretty_caller_ref=challenge.caller.nickname,
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


def get_vk_new_game_message(game: GameSummaryPublic) -> str:
    time_control = format_time_control(game.fischer_time_control) or "По переписке"

    return VK_NEW_GAME_MESSAGE_TEMPLATE.format(
        pretty_white_ref=game.white_player.nickname,
        pretty_black_ref=game.black_player.nickname,
        time_control=time_control,
        game_id=game.id
    )
