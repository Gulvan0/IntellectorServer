from src.challenge.models import Challenge, ChallengeFischerTimeControlCreate


def time_control_equality_conditions(challenge_time_control: ChallengeFischerTimeControlCreate | None) -> list[bool]:
    if challenge_time_control is None:
        return [Challenge.fischer_time_control == None]
    return [
        Challenge.fischer_time_control != None,
        Challenge.fischer_time_control.start_seconds == challenge_time_control.start_seconds,  # type: ignore
        Challenge.fischer_time_control.increment_seconds == challenge_time_control.increment_seconds,  # type: ignore
    ]
