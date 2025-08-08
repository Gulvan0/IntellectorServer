from sqlmodel import Session
from models.player import Player
from utils.datatypes import UserReference


def prettify_player_reference(player_ref: UserReference, session: Session) -> str:
    if player_ref.is_guest():
        return f"Guest {player_ref.guest_id}"
    elif player_ref.is_bot():
        return f"{player_ref.bot_name} (bot)"
    else:
        player = session.get(Player, player_ref.login)
        return player.nickname if player else player_ref.login
