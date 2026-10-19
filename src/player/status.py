from collections.abc import Collection
from typing import TYPE_CHECKING

from common.datatypes import UserStatus
from common.models import UserActivity
from player.methods import get_ws_activity, promote_to_playing
from player.models import PlayerStatusState
from pubsub.models.channel import PlayerStatusEventChannel
from pubsub.outgoing_event.update import PlayerStatusChanged
from utils.async_orm_session import AsyncSession


if TYPE_CHECKING:
    from net.state import MutableState


async def get_player_status_states(session: AsyncSession, state: MutableState, player_logins: Collection[str]) -> dict[str, PlayerStatusState]:
    activities: dict[str, UserActivity] = {}
    for login in player_logins:
        activity = get_ws_activity(state, login)
        if activity:
            activities[login] = activity

    await promote_to_playing(session, activities)

    result: dict[str, PlayerStatusState] = {}
    for login in player_logins:
        activity = activities.get(login)
        if activity:
            result[login] = PlayerStatusState(status=activity.status, last_active_unixsecs=activity.last_active_unixsecs)
        else:
            # no connection left: the latest activity is the one seen while it was there
            published = state.published_player_statuses.get(login)
            result[login] = PlayerStatusState(status=UserStatus.OFFLINE, last_active_unixsecs=published.last_active_unixsecs if published else None)
    return result


async def track_player_statuses(session: AsyncSession, state: MutableState, player_logins: Collection[str]) -> dict[str, PlayerStatusState]:
    """The players' current statuses; a change made to one of them before the next check gets published too"""
    status_states = await get_player_status_states(session, state, player_logins)
    for login, status_state in status_states.items():
        state.published_player_statuses.setdefault(login, status_state)
    return status_states


async def publish_player_status_changes(session: AsyncSession, state: MutableState) -> None:
    """Broadcasts the status of every player someone is subscribed to, if it changed since the previous call"""
    watched_logins = {channel.watched_ref for channel in state.ws_subscribers.get_subscribed_channels(PlayerStatusEventChannel)}
    published = state.published_player_statuses

    for login in published.keys() - watched_logins:
        del published[login]

    for login, status_state in (await get_player_status_states(session, state, watched_logins)).items():
        previous = published.get(login)
        published[login] = status_state
        if previous and previous.status != status_state.status:
            state.concurrent_tasks.plan(state.ws_subscribers.broadcast(
                PlayerStatusChanged(status_state, PlayerStatusEventChannel(watched_ref=login))
            ))
