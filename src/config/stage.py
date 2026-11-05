import os


STAGES = ("test", "prod")


def current_stage() -> str:
    """Has no default: on the production server, falling back to the test stage would log passwords and open a plain HTTP port"""
    stage = os.getenv("STAGE", "").lower()
    if stage not in STAGES:
        raise RuntimeError(f"The STAGE environment variable must be one of {STAGES}, got {os.getenv('STAGE')!r}")
    return stage


def is_test_stage() -> bool:
    return current_stage() == "test"
