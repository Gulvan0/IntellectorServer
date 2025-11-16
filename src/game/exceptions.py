from dataclasses import dataclass
from datetime import datetime

from src.rules import PieceColor


@dataclass
class TimeoutReachedException(Exception):
    winner: PieceColor
    reached_at: datetime


class PlyInvalidException(Exception):
    pass
