from fastapi import HTTPException

from board.constants.sip import DEFAULT_STARTING_SIP
from board.deserializers.sip import position_from_sip


def validated_starting_sip(sip: str | None) -> str | None:
    """The custom starting position to store: none for the default one. Answers 422 to an invalid one"""
    if not sip or sip == DEFAULT_STARTING_SIP:
        return None
    try:
        is_valid = position_from_sip(sip).is_valid_starting()
    except ValueError:
        is_valid = False
    if not is_valid:
        raise HTTPException(status_code=422, detail="Invalid starting situation")
    return sip
