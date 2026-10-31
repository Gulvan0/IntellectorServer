from dataclasses import dataclass


@dataclass(frozen=True)
class BotFamily:
    ref_prefix: str
    # member code -> display name
    members: dict[str, str]
    min_strength: int
    max_strength: int


HXCONDA = BotFamily(
    ref_prefix="hxconda",
    members={
        "std": "Haxaconda Standard",
        "trl": "Haxaconda Trailblazer",
        "vrz": "Haxaconda Vrezh",
        "frt": "Haxaconda Fortress",
        "unc": "Haxaconda Unchained",
    },
    min_strength=1,
    max_strength=9,
)

# only the flagship plays at the full strength
FULL_STRENGTH_MEMBERS = {"std"}

LEGACY_ANACONDA_NAME = "Anaconda"


def registered_bot_display_name(bot_name: str) -> str | None:
    """`<member display name> <strength>` for `bot_name` (a bot ref without its `+`) of a registered bot, None otherwise.
    Bot names have the form `hxconda_<member code>_<strength>`"""
    parts = bot_name.split("_")
    if len(parts) != 3 or parts[0] != HXCONDA.ref_prefix or parts[1] not in HXCONDA.members or not parts[2].isdigit():
        return None
    strength = int(parts[2])
    if str(strength) != parts[2] or not HXCONDA.min_strength <= strength <= HXCONDA.max_strength:
        return None
    if strength == HXCONDA.max_strength and parts[1] not in FULL_STRENGTH_MEMBERS:
        return None
    return f"{HXCONDA.members[parts[1]]} {strength}"
