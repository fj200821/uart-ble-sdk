"""新一 XY-DG02（ASR5601）串口透传 BLE。

指令与出厂参数来自《XY-DG02 用户使用手册》V1.1.5，并在 COM100 上核对过
AT+VER / AT+MAC / AT+NAME / AT+UART / AT+ADV / UUID / TXPOWER。

角色取值跟开机文案和 AT+DEV? 一致：0 表示对端是主机，1 表示对端是从机。
手册「断开连接」那一页把 0/1 写反了，这里不采用那一页。
"""

from __future__ import annotations

from uart_ble.profile import AtProfileSpec, CommandDef, EventDef
from uart_ble.types import EventKind

_BAUD = {
    9600: "0",
    14400: "1",
    19200: "2",
    38400: "3",
    57600: "4",
    115200: "5",
    230400: "6",
}

_LINK_CONNECTED = (
    r"\+CONNECTED:\s*(?P<raw_type>\d+)\s*,\s*(?P<address>[0-9A-Fa-f]+)"
)
_LINK_DISCONNECTED = (
    r"\+DISCONN:\s*(?P<raw_type>\d+)\s*,\s*(?P<address>[0-9A-Fa-f]+)"
)


def _query(template: str, prefix: str) -> CommandDef:
    return CommandDef(template, response_prefix=prefix)


def _set(template: str) -> CommandDef:
    return CommandDef(template, accepts_ok=True)


XY_DG02_SPEC = AtProfileSpec(
    profile_id="xy-dg02",
    display_name="XY-DG02",
    default_baud=115200,
    probe_command="AT+VER?",
    probe_prefix="+VER:",
    name_limit=20,
    central_type=0,
    baud_codes=_BAUD,
    identity_ops=(
        "read_version",
        "read_address",
        "read_name",
        "read_baudrate",
        "read_advertising",
        "read_service",
        "read_notify_characteristic",
        "read_write_characteristic",
    ),
    commands={
        "read_version": _query("AT+VER?", "+VER:"),
        "read_address": _query("AT+MAC?", "+MAC:"),
        "write_address": _set("AT+MAC={value}"),
        "read_name": _query("AT+NAME?", "+NAME:"),
        "write_name": _set("AT+NAME={value}"),
        "read_advertising": _query("AT+ADV?", "+ADV:"),
        "start_advertising": _set("AT+ADV=1"),
        "stop_advertising": _set("AT+ADV=0"),
        "start_scan": CommandDef(
            "AT+SCAN=1",
            response_prefix="+SCAN:",
            multiline=True,
            end_line="+SCAN END",
        ),
        "stop_scan": CommandDef("AT+SCAN=0", accepts_ok=True, response_prefix="+SCAN END"),
        "read_baudrate": _query("AT+UART?", "+UART:"),
        "set_baudrate": _set("AT+UART={value}"),
        "read_service": _query("AT+UUIDS?", "+UUIDS:"),
        "write_service": _set("AT+UUIDS={value}"),
        "read_notify_characteristic": _query("AT+UUIDN?", "+UUIDN:"),
        "write_notify_characteristic": _set("AT+UUIDN={value}"),
        "read_write_characteristic": _query("AT+UUIDW?", "+UUIDW:"),
        "write_write_characteristic": _set("AT+UUIDW={value}"),
        "read_interval": _query("AT+AINTVL?", "+AINTVL:"),
        "write_interval": _set("AT+AINTVL={value}"),
        "read_tx_power": _query("AT+TXPOWER?", "+TXPOWER:"),
        "write_tx_power": _set("AT+TXPOWER={value}"),
        "read_connected_devices": _query("AT+DEV?", "+DEV:"),
        "read_manufacturer_data": _query("AT+AMDATA?", "+AMDATA:"),
        "write_manufacturer_data": _set("AT+AMDATA={value}"),
        "disconnect": CommandDef("AT+DISCONN={value}", response_prefix="+DISCONN:"),
        "reboot": _set("AT+REBOOT={value}"),
        "factory_reset": _set("AT+RESET={value}"),
    },
    events=(
        EventDef(r"\+READY", EventKind.READY),
        EventDef(_LINK_CONNECTED, EventKind.CONNECTED),
        EventDef(_LINK_DISCONNECTED, EventKind.DISCONNECTED),
        EventDef(r"\+CONNECT TIMEOUT", EventKind.CONNECT_TIMEOUT),
    ),
)
