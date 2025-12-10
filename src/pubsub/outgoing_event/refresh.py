from src.player.models import StartedPlayerGamesStateRefresh
from src.pubsub.models.channel import StartedPlayerGamesEventChannel
from src.pubsub.outgoing_event.base import RefreshEvent


class StartedPlayerGamesRefresh(RefreshEvent[StartedPlayerGamesStateRefresh, StartedPlayerGamesEventChannel]):
    @classmethod
    def payload_example(cls) -> StartedPlayerGamesStateRefresh:
        return StartedPlayerGamesStateRefresh(
            player_ref="watched_player_login",
            current_games=[]  # TODO: Fill the list with game samples
        )

# TODO: Add the remaining ones + a new one ("subscribers") - respective channel should be added too
