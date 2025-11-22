from sqlmodel import select

from src.common.user_ref import UserReference
from src.config.models import IntegrationParams
from src.notification.integration import delete_vk_message, post_discord_webhook, post_vk_message
from src.notification.models import GameStartedNotification, NewPublicChallengeNotification, NotificationApp
from src.notification.texts import get_discord_new_challenge_message, get_vk_new_challenge_message, get_vk_new_game_message

import src.player.methods as player_methods
import src.game.models.main as main_game_models
import src.challenge.models as challenge_models
from src.utils.async_orm_session import AsyncSession


async def send_new_public_challenge_notifications(
    caller: UserReference,
    public_challenge: challenge_models.ChallengePublic,
    integrations_config: IntegrationParams,
    session: AsyncSession
) -> None:
    pretty_caller_ref = await player_methods.prettify_player_reference(caller, session)

    vk_chat_id = integrations_config.vk.community_chat_id
    vk_announcement_text = get_vk_new_challenge_message(public_challenge, pretty_caller_ref)
    vk_message_id = post_vk_message(vk_chat_id, vk_announcement_text, integrations_config.vk.token)

    if vk_message_id:
        notification = NewPublicChallengeNotification(
            app=NotificationApp.VK,
            chat_id=vk_chat_id,
            message_id=vk_message_id,
            is_permanent=False,
            challenge_id=public_challenge.id
        )
        session.add(notification)
        await session.commit()

    discord_announcement_text = get_discord_new_challenge_message(public_challenge, pretty_caller_ref)
    post_discord_webhook(integrations_config.discord.webhook_url, discord_announcement_text)


async def delete_new_public_challenge_notifications(challenge_id: int, session: AsyncSession, vk_token: str) -> None:
    challenge_notifications = await session.exec(select(
        NewPublicChallengeNotification
    ).where(
        NewPublicChallengeNotification.challenge_id == challenge_id,
        NewPublicChallengeNotification.is_permanent == False  # noqa
    ))
    for notification in challenge_notifications:
        if notification.app == NotificationApp.VK:
            delete_vk_message(
                message_id=notification.message_id,
                chat_id=notification.chat_id,
                token=vk_token
            )
        await session.delete(notification)
    await session.commit()


async def send_game_started_notifications(
    white_player_ref: str,
    black_player_ref: str,
    public_game: main_game_models.GamePublic,
    integrations_config: IntegrationParams,
    session: AsyncSession
) -> None:
    white_player = UserReference(white_player_ref)
    black_player = UserReference(black_player_ref)
    if white_player.is_bot() or black_player.is_bot() or (white_player.is_guest() and black_player.is_guest()):
        return

    pretty_white_ref = await player_methods.prettify_player_reference(white_player, session)
    pretty_black_ref = await player_methods.prettify_player_reference(black_player, session)

    vk_chat_id = integrations_config.vk.community_chat_id
    vk_announcement_text = get_vk_new_game_message(public_game, pretty_white_ref, pretty_black_ref)
    vk_message_id = post_vk_message(vk_chat_id, vk_announcement_text, integrations_config.vk.token)

    if vk_message_id:
        notification = GameStartedNotification(
            app=NotificationApp.VK,
            chat_id=vk_chat_id,
            message_id=vk_message_id,
            is_permanent=False,
            game_id=public_game.id
        )
        session.add(notification)
        await session.commit()


async def delete_game_started_notifications(game_id: int, vk_token: str, session: AsyncSession) -> None:
    challenge_notifications = await session.exec(select(
        GameStartedNotification
    ).where(
        GameStartedNotification.game_id == game_id,
        GameStartedNotification.is_permanent == False  # noqa
    ))
    for notification in challenge_notifications:
        if notification.app == NotificationApp.VK:
            delete_vk_message(
                message_id=notification.message_id,
                chat_id=notification.chat_id,
                token=vk_token
            )
        await session.delete(notification)
    await session.commit()
