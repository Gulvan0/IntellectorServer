import asyncio
from datetime import UTC, datetime
from typing import Iterable

from sqlmodel import desc, select

from challenge.models import ChallengePublic
from common.user_ref import UserReference
from config.models import IntegrationParams
from game.models.main import GameSummaryPublic
from notification.integration import delete_vk_message, post_discord_webhook, post_vk_message
from notification.models import GameStartedNotification, NewPublicChallengeNotification, NotificationApp
from notification.texts import get_discord_new_challenge_message, get_vk_new_challenge_message, get_vk_new_game_message
from utils.async_orm_session import AsyncSession


async def nth_last_notification_send_times(ns: Iterable[int], app: NotificationApp, session: AsyncSession) -> dict[int, datetime]:
    max_n = max(ns)
    results = await asyncio.gather(
        session.exec(
            select(
                NewPublicChallengeNotification.sent_at
            ).where(
                NewPublicChallengeNotification.app == app
            ).order_by(
                desc(NewPublicChallengeNotification.sent_at)
            ).limit(max_n)
        ),
        session.exec(
            select(
                GameStartedNotification.sent_at
            ).where(
                GameStartedNotification.app == app
            ).order_by(
                desc(GameStartedNotification.sent_at)
            ).limit(max_n)
        ),
    )

    send_times = sorted(sent_at for result in results for sent_at in result)
    return {
        n: send_times[n - 1] if len(send_times) >= n else send_times[-1]
        for n in ns
    }


async def vk_antispam_limit_reached(integrations_config: IntegrationParams, session: AsyncSession) -> bool:
    now_dt = datetime.now(UTC)

    antispam_windows = integrations_config.vk.antispam_windows
    oldest_send_times = await nth_last_notification_send_times(
        map(lambda x: x.max_messages, antispam_windows),
        NotificationApp.VK,
        session
    )
    for antispam_window in antispam_windows:
        oldest_send_time = oldest_send_times.get(antispam_window.max_messages)
        if oldest_send_time and (now_dt - oldest_send_time).seconds < antispam_window.window_size_seconds:
            return True

    return False


async def send_new_public_challenge_notifications(
    public_challenge: ChallengePublic,
    integrations_config: IntegrationParams,
    session: AsyncSession
) -> None:
    if await vk_antispam_limit_reached(integrations_config, session):
        return

    vk_chat_id = integrations_config.vk.community_chat_id
    vk_announcement_text = get_vk_new_challenge_message(public_challenge)
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

    discord_announcement_text = get_discord_new_challenge_message(public_challenge)
    await post_discord_webhook(integrations_config.discord.webhook_url, discord_announcement_text)


async def delete_new_public_challenge_notifications(challenge_id: int, session: AsyncSession, vk_token: str) -> None:
    challenge_notifications = await session.exec(select(
        NewPublicChallengeNotification
    ).where(
        NewPublicChallengeNotification.challenge_id == challenge_id,
        NewPublicChallengeNotification.is_permanent == False  # noqa
    ))
    for notification in challenge_notifications:
        if notification.app == NotificationApp.VK:
            await delete_vk_message(
                message_id=notification.message_id,
                chat_id=notification.chat_id,
                token=vk_token
            )
        await session.delete(notification)
    await session.commit()


async def send_game_started_notifications(
    white_player_ref: str,
    black_player_ref: str,
    public_game: GameSummaryPublic,
    integrations_config: IntegrationParams,
    session: AsyncSession
) -> None:
    if await vk_antispam_limit_reached(integrations_config, session):
        return

    white_player = UserReference(white_player_ref)
    black_player = UserReference(black_player_ref)
    if white_player.is_bot() or black_player.is_bot() or (white_player.is_guest() and black_player.is_guest()):
        return

    vk_chat_id = integrations_config.vk.community_chat_id
    vk_announcement_text = get_vk_new_game_message(public_game)
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
            await delete_vk_message(
                message_id=notification.message_id,
                chat_id=notification.chat_id,
                token=vk_token
            )
        await session.delete(notification)
    await session.commit()
