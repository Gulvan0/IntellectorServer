import aiohttp


async def post_vk_message(chat_id: int, text: str, token: str) -> int | None:
    try:
        async with aiohttp.ClientSession() as session:
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
                response_json: dict = await response.json()
                return response_json.get("conversation_message_id")
    except Exception:
        return None


async def delete_vk_message(message_id: int, chat_id: int, token: str) -> None:
    try:
        async with aiohttp.ClientSession() as session:
            response = await session.post(
                'https://api.vk.ru/method/messages.delete',
                params=dict(
                    cmids=message_id,
                    delete_for_all=1,
                    peer_id=chat_id,
                    access_token=token,
                    v="5.199"
                )
            )
            await response.release()
    except Exception:
        pass


async def post_discord_webhook(url: str, text: str) -> None:
    try:
        async with aiohttp.ClientSession() as session:
            response = await session.post(
                url,
                json=dict(content=text)
            )
            await response.release()
    except Exception:
        pass
