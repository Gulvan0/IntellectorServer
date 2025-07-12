import requests  # type: ignore


def post_vk_message(chat_id: int, text: str, token: str) -> int | None:
    try:
        return requests.post(
            'https://api.vk.com/method/messages.send',
            params=dict(
                random_id=0,
                peer_ids=chat_id,
                message=text,
                access_token=token,
                v="5.199"
            )
        ).json().get("conversation_message_id")
    except Exception:
        return None


def delete_vk_message(message_id: int, chat_id: int, token: str) -> None:
    try:
        requests.post(
            'https://api.vk.com/method/messages.delete',
            params=dict(
                cmids=message_id,
                delete_for_all=1,
                peer_id=chat_id,
                access_token=token,
                v="5.199"
            )
        )
    except Exception:
        pass


def post_discord_webhook(url: str, text: str) -> None:
    try:
        requests.post(
            url,
            json=dict(content=text)
        )
    except Exception:
        pass
