from src.rules.position import Position
from src.rules.serializers.sip import get_sip, get_v1_sip


DEFAULT_STARTING_SIP = get_sip(Position.default_starting())
DEFAULT_STARTING_SIP_V1 = get_v1_sip(Position.default_starting())
