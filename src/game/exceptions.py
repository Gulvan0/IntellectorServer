from dataclasses import dataclass
from datetime import datetime

from board.piece import PieceColor


@dataclass
class TimeoutReachedException(Exception):
    winner: PieceColor
    reached_at: datetime


@dataclass
class PlyInvalidException(Exception):
    current_sip: str


@dataclass
class SinkException(Exception):
    message: str
    status_code: int | None = None
