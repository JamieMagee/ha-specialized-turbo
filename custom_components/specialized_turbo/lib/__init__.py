"""Embedded protocol library from specialized-turbo."""

from .protocol import (  # noqa: F401
    # UUIDs
    SERVICE_DATA_NOTIFY,
    SERVICE_DATA_REQUEST,
    SERVICE_DATA_WRITE,
    CHAR_NOTIFY,
    CHAR_REQUEST_READ,
    CHAR_REQUEST_WRITE,
    CHAR_WRITE,
    NORDIC_COMPANY_ID,
    ADVERTISING_MAGIC,
    # Enums
    Sender,
    BatteryChannel,
    MotorChannel,
    BikeSettingsChannel,
    AssistLevel,
    # Parsing
    parse_message,
    ParsedMessage,
    FieldDefinition,
    get_field_def,
    all_field_defs,
    build_request,
    is_specialized_advertisement,
)
from .models import (  # noqa: F401
    BatteryState,
    MotorState,
    BikeSettings,
    TelemetrySnapshot,
)
