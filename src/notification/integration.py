import logging
from typing import Any
import aiohttp

from config.models import ProxyParams


logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=5)


async def post_vk_message(chat_id: int, text: str, token: str) -> int | None:
    """The sent message's id, or None (logged) if VK didn't confirm sending it"""
    try:
        async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
            async with session.post(
                'https://api.vk.ru/method/messages.send',
                params=dict(
                    random_id=0,
                    peer_ids=chat_id,
                    message=text,
                    access_token=token,
                    v="5.199"
                )
            ) as response:
                response_json: dict[str, Any] = await response.json(content_type=None)
    except TimeoutError:
        logger.warning("VK message sending timed out (chat %s)", chat_id)
        return None
    except Exception:
        logger.warning("VK message sending failed (chat %s)", chat_id, exc_info=True)
        return None

    if "error" in response_json:
        logger.warning("VK rejected message sending (chat %s): %s", chat_id, response_json["error"])
        return None

    # with peer_ids, the response is a list of per-peer results
    results = response_json.get("response")
    first = results[0] if isinstance(results, list) and results else None
    message_id = first.get("conversation_message_id") if isinstance(first, dict) else None
    if message_id is None:
        logger.warning("VK answered without a message id (chat %s): %s", chat_id, response_json)
    return message_id


async def delete_vk_message(message_id: int, chat_id: int, token: str) -> bool:
    """True only if VK confirmed the deletion. Failures are logged"""
    try:
        async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
            async with session.post(
                'https://api.vk.ru/method/messages.delete',
                params=dict(
                    cmids=message_id,
                    delete_for_all=1,
                    peer_id=chat_id,
                    access_token=token,
                    v="5.199"
                )
            ) as response:
                response_json: dict[str, Any] = await response.json(content_type=None)
    except TimeoutError:
        logger.warning("VK message deletion timed out (chat %s, message %s)", chat_id, message_id)
        return False
    except Exception:
        logger.warning("VK message deletion failed (chat %s, message %s)", chat_id, message_id, exc_info=True)
        return False

    error = response_json.get("error")
    if error:
        logger.warning("VK rejected message deletion (chat %s, message %s): %s", chat_id, message_id, error)
        return False

    # messages.delete answers with {"response": {"<cmid>": 1}}: a 0 means that nothing was deleted
    deleted = response_json.get("response")
    if isinstance(deleted, dict) and not all(deleted.values()):
        logger.warning("VK did not delete the message (chat %s, message %s): %s", chat_id, message_id, response_json)
        return False
    return True


async def _post_via_proxy(proxy: ProxyParams, method: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """The worker answers in VK's format: {"response": ...} or {"error": ...}. None (logged) if the call failed"""
    try:
        async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
            async with session.post(
                f"{proxy.url.rstrip('/')}/method/{method}",
                params=dict(v="5.199", access_token=proxy.key),
                json=payload
            ) as response:
                response_json: dict[str, Any] = await response.json(content_type=None)
    except TimeoutError:
        logger.warning("Proxy request timed out (%s)", method)
        return None
    except Exception:
        logger.warning("Proxy request failed (%s)", method, exc_info=True)
        return None

    if "error" in response_json:
        logger.warning("Proxy rejected the request (%s): %s", method, response_json["error"])
        return None
    return response_json


async def post_discord_webhook(proxy: ProxyParams, text: str) -> bool:
    """True only if Discord accepted the message. Failures are logged"""
    return await _post_via_proxy(proxy, "wall.post", dict(content=text)) is not None


async def post_telegram_message(proxy: ProxyParams, chat_id: int, text: str) -> int | None:
    """The sent message's id, or None (logged) if Telegram didn't confirm sending it. The worker has no default chat, so chat_id is always sent"""
    response_json = await _post_via_proxy(proxy, "messages.send", dict(chat_id=chat_id, text=text))
    if response_json is None:
        return None
    message_id = (response_json.get("response") or {}).get("message_id")
    if message_id is None:
        logger.warning("Telegram answered without a message id (chat %s): %s", chat_id, response_json)
    return message_id
