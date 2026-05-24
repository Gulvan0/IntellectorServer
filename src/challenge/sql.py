from sqlmodel import and_

from challenge.models import Challenge, ChallengeFischerTimeControl, ChallengeFischerTimeControlCreate


def time_control_equality_conditions(challenge_time_control: ChallengeFischerTimeControlCreate | None) -> list:
    if challenge_time_control is None:
        return [Challenge.fischer_time_control == None]
    return [
        Challenge.fischer_time_control.has(and_(  # type: ignore
            ChallengeFischerTimeControl.start_seconds == challenge_time_control.start_seconds,
            ChallengeFischerTimeControl.increment_seconds == challenge_time_control.increment_seconds,
        ))
    ]
