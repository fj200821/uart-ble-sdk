"""UART BLE 适配器 SDK。

对外动词对齐 Android / iOS / Windows：start_advertising、disconnect、
write_characteristic、read_characteristic。模块 AT 只写在 profile 里。

    from uart_ble import define_profile, open_session
    from uart_ble.profile import AtProfileSpec, CommandDef

    define_profile(AtProfileSpec(
        profile_id="acme",
        display_name="ACME",
        default_baud=9600,
        probe_command="AT+ID?",
        probe_prefix="+ID:",
        commands={
            "read_version": CommandDef("AT+ID?", response_prefix="+ID:"),
            "write_name": CommandDef("AT+N={value}", accepts_ok=True),
            "start_advertising": CommandDef("AT+A=1", accepts_ok=True),
        },
        identity_ops=("read_version",),
    ))
    with open_session("COM100") as session:
        session.start_advertising(local_name="UART-BLE")
        session.write_characteristic(b"hello")
"""

from uart_ble.profile import AtProfile, AtProfileSpec, CommandDef, EventDef
from uart_ble.profiles import RAW, XY_DG02
from uart_ble.registry import define_profile, get_profile, profile_ids
from uart_ble.session import UartBleSession, open_session
from uart_ble.types import (
    AdapterIdentity,
    AdapterNotFound,
    Advertisement,
    CommandFailed,
    CommandTimeout,
    ConnectionStatus,
    Event,
    EventKind,
    LinkBusy,
    PeerRole,
    UnsupportedCommand,
    UartBleError,
)

__all__ = [
    "RAW",
    "XY_DG02",
    "AdapterIdentity",
    "AdapterNotFound",
    "Advertisement",
    "AtProfile",
    "AtProfileSpec",
    "CommandDef",
    "CommandFailed",
    "CommandTimeout",
    "ConnectionStatus",
    "Event",
    "EventDef",
    "EventKind",
    "LinkBusy",
    "PeerRole",
    "UnsupportedCommand",
    "UartBleError",
    "UartBleSession",
    "define_profile",
    "get_profile",
    "open_session",
    "profile_ids",
]
