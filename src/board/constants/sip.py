from board.position import Position
from board.serializers.sip import get_sip, get_v1_sip


DEFAULT_STARTING_SIP = get_sip(Position.default_starting())
DEFAULT_STARTING_SIP_V1 = get_v1_sip(Position.default_starting())
