"""共享类型。业务代码只看这些对象，不看某个模块的 AT 原文。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PeerRole(Enum):
    """对端角色。对应 iOS CBCentral / CBPeripheral。"""

    CENTRAL = "central"
    PERIPHERAL = "peripheral"
    UNKNOWN = "unknown"


class ConnectionStatus(Enum):
    """连接状态。对应 Android STATE_CONNECTED / Windows BluetoothConnectionStatus。"""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"


@dataclass(frozen=True)
class Advertisement:
    """一次扫描看到的广播。对应 Android ScanResult / iOS didDiscover / Windows Received。"""

    address: str
    rssi: int
    local_name: str = ""
    address_type: int = 0


@dataclass(frozen=True)
class Link:
    role: PeerRole
    address: str
    raw_type: int


class EventKind(Enum):
    """连接回调。对应 onConnectionStateChange / didConnect / ConnectionStatusChanged。"""

    READY = "ready"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    CONNECT_TIMEOUT = "connect_timeout"


@dataclass(frozen=True)
class Event:
    kind: EventKind
    text: str
    link: Link | None = None


@dataclass
class AdapterIdentity:
    """一块适配器当前读到的身份。字段为空表示这份 profile 没有对应查询。"""

    profile_id: str
    version: str = ""
    address: str = ""
    name: str = ""
    baud_code: str = ""
    baudrate: int | None = None
    advertising: bool | None = None
    service_uuid: str = ""
    notify_characteristic_uuid: str = ""
    write_characteristic_uuid: str = ""


@dataclass
class CommandResult:
    op: str
    lines: list[str]
    ok: bool

    @property
    def value(self) -> str:
        for line in reversed(self.lines):
            if ":" in line:
                return line.split(":", 1)[1].strip()
        return ""


class UartBleError(Exception):
    pass


class AdapterNotFound(UartBleError):
    pass


class UnsupportedCommand(UartBleError):
    pass


class CommandFailed(UartBleError):
    pass


class CommandTimeout(UartBleError):
    pass


class LinkBusy(UartBleError):
    """链路已建立，串口处于透传，这条 AT 不能再发。"""
