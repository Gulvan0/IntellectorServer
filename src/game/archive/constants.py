"""Caps on a game archive formula (mirrored by hand in the client's `client.logic.games.FormulaCaps`), and other request limits"""

FORMULA_VERSION = 1

MAX_DEPTH = 8  # recursive layers (AND/OR/NOT), the root AND included
MAX_LEAVES = 50
MAX_NODES = 100  # leaves and recursive conditions
MAX_VALUES_PER_LEAF = 100
MAX_COSTLY_LEAVES = 10  # `opening` and `starting_position`
MAX_FORMULA_BYTES = 8 * 1024

MAX_PAGE_SIZE = 50
MAX_SORT_LEVELS = 3

SAVED_FILTER_NAME_PATTERN = r"^[\w ]{1,32}$"  # Python's \w is Unicode-aware, matching the client's [\p{L}\p{N}_ ] closely enough

GAME_ID_PLACEHOLDER = "{game_id}"
GAME_URL_TEMPLATE_PATTERN = r"^https?://\S*\{game_id\}\S*$"
