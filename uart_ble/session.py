"""会话：探测模块、发 AT、在透传和主动上报之间分路。"""

from __future__ import annotations

import re
import time

from uart_ble.framer import Framer, Payload
from uart_ble.profile import AtProfile
from uart_ble.transport import ByteTransport, SerialTransport
from uart_ble.types import (
    AdapterIdentity,
    AdapterNotFound,
    Advertisement,
    CommandFailed,
    CommandResult,
    CommandTimeout,
    ConnectionStatus,
    Event,
    EventKind,
    LinkBusy,
    UartBleError,
)

_ADVERTISEMENT_LINE = re.compile(
    r"^(?P<address>[0-9A-Fa-f]{12})\s+"
    r"(?P<address_type>\d+)\s+"
    r"(?P<rssi>-?\d+)"
    r"(?:\s+(?P<local_name>.*))?$"
)


class UartBleSession:
    def __init__(self, transport: ByteTransport, profile: AtProfile) -> None:
        self.transport = transport
        self.profile = profile
        self.identity = AdapterIdentity(profile_id=profile.profile_id)
        self.links: dict[str, object] = {}
        self._framer = Framer(profile.classify)
        self._payload = bytearray()
        self._events: list[Event] = []
        self._lines: list[str] = []
        self._waiting = False
        self._last_rx = time.monotonic()
        self._idle_s = 0.04

    def close(self) -> None:
        self.transport.close()

    def __enter__(self) -> "UartBleSession":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    @property
    def name(self) -> str:
        """GAP 设备名。对应 Android getName / iOS CBPeripheral.name / Windows Name。"""
        return self.identity.name

    @property
    def address(self) -> str:
        """设备地址。对应 Android getAddress / Windows BluetoothAddress。"""
        return self.identity.address

    @property
    def connection_status(self) -> ConnectionStatus:
        """对应 Android STATE_CONNECTED 与 Windows BluetoothConnectionStatus。"""
        if self.links:
            return ConnectionStatus.CONNECTED
        return ConnectionStatus.DISCONNECTED

    @property
    def is_connected(self) -> bool:
        return self.connection_status is ConnectionStatus.CONNECTED

    def start_advertising(self, local_name: str | None = None) -> AdapterIdentity:
        """开始广播。对应 startAdvertising；local_name 即广播本地名。"""
        if local_name is not None:
            self.command("write_name", value=local_name)
        self.command("start_advertising")
        return self.refresh_identity()

    def stop_advertising(self) -> None:
        """停止广播。对应 stopAdvertising。"""
        self.command("stop_advertising")

    def disconnect(self) -> None:
        """断开当前 BLE 连接。对应 disconnect / cancelPeripheralConnection。"""
        self.command("disconnect", value="1")

    def start_scan(self, timeout: float = 7.5) -> list[Advertisement]:
        """扫描附近广播。对应 startScan / scanForPeripherals。XY-DG02 约 6 秒后结束。"""
        result = self.command("start_scan", timeout=timeout)
        return _advertisements(result.lines)

    def stop_scan(self) -> None:
        """停止扫描。对应 stopScan。"""
        self.command("stop_scan", timeout=1.0)

    def discover_services(self) -> AdapterIdentity:
        """读取服务和特征值 UUID。对应 discoverServices。"""
        for op in (
            "read_service",
            "read_notify_characteristic",
            "read_write_characteristic",
        ):
            try:
                result = self.command(op, timeout=0.6)
            except UartBleError:
                continue
            self._assign(self.identity, op, result.value)
        return self.identity

    def write_characteristic(self, value: bytes) -> None:
        """写入对端将收到的特征值。对应 writeCharacteristic / writeValue。"""
        self.transport.write(value)

    def read_characteristic(self, max_bytes: int = 4096, timeout: float = 0.2) -> bytes:
        """读出对端写入、从串口吐出的数据。对应 readCharacteristic / readValue。"""
        return self._read_payload(max_bytes, timeout)

    def send_book(self, file: str, protocol: str = "ymodem") -> None:
        """在已连接的透传链路上发送一本书。protocol 为 xmodem、ymodem 或 zmodem。"""
        self._require_transparent()
        from uart_ble.book import send_book
        from uart_ble.book.link import Link

        send_book(Link(self.read_characteristic, self.write_characteristic), file, protocol)

    def recv_book(self, dest_dir: str, protocol: str = "ymodem", name: str = "book.bin") -> str:
        """在已连接的透传链路上接收一本书，返回保存路径。"""
        self._require_transparent()
        from uart_ble.book import recv_book
        from uart_ble.book.link import Link

        path = recv_book(
            Link(self.read_characteristic, self.write_characteristic),
            dest_dir,
            protocol,
            name,
        )
        return str(path)

    def _require_transparent(self) -> None:
        if self.profile.spec.probe_command and not self.is_connected:
            raise UartBleError("传书要等 BLE 连上，串口才是透传")

    def set_baudrate(self, baudrate: int) -> None:
        """串口速率。对应 pySerial 的 baudrate，不是 BLE 概念。"""
        self.command("set_baudrate", value=baudrate)

    def _read_payload(self, max_bytes: int = 4096, timeout: float = 0.2) -> bytes:
        deadline = time.monotonic() + timeout
        while not self._payload and time.monotonic() < deadline:
            self._pump_once()
            time.sleep(0.005)
        chunk = bytes(self._payload[:max_bytes])
        del self._payload[:max_bytes]
        return chunk

    def poll(self, timeout: float = 0.0) -> list[Event]:
        deadline = time.monotonic() + max(timeout, 0.0)
        while True:
            self._pump_once()
            if self._events or time.monotonic() >= deadline:
                break
            time.sleep(0.005)
        events = self._events
        self._events = []
        return events

    def command(self, op: str, timeout: float = 0.8, **kwargs: object) -> CommandResult:
        if self.links and op not in self.profile.spec.allowed_while_linked:
            raise LinkBusy(f"{op} 在已连接时会被当成透传数据")
        command = self.profile.command_def(op)
        payload = self.profile.render(op, **kwargs)
        self._lines.clear()
        self._waiting = True
        matched: list[str] = []
        try:
            self.transport.write(payload)
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                got = self._pump_once()
                done, failed, matched = self._consume(command, matched)
                if failed:
                    raise CommandFailed(op + ": " + " | ".join(matched))
                if done:
                    result = CommandResult(op=op, lines=list(matched), ok=True)
                    self._apply_result(op, result, kwargs)
                    return result
                if not got:
                    time.sleep(0.005)
            raise CommandTimeout(op)
        finally:
            self._waiting = False
            self._flush_pending_lines()

    def refresh_identity(self) -> AdapterIdentity:
        ident = AdapterIdentity(profile_id=self.profile.profile_id)
        for op in self.profile.spec.identity_ops:
            try:
                result = self.command(op, timeout=0.6)
            except UartBleError:
                continue
            self._assign(ident, op, result.value)
        self.identity = ident
        return ident

    def _apply_result(self, op: str, result: CommandResult, kwargs: dict) -> None:
        self._assign(self.identity, op, result.value)
        if op == "write_name":
            self.identity.name = str(kwargs.get("value", ""))
        elif op == "start_advertising":
            self.identity.advertising = True
        elif op == "stop_advertising":
            self.identity.advertising = False
        if op == "set_baudrate" and result.ok:
            code = self.profile.baud_code(kwargs.get("value", ""))
            baud = self.profile.baud_from_code(code)
            if baud is not None:
                self.transport.reconfigure(baud)
                self.identity.baudrate = baud
                self.identity.baud_code = code

    def _assign(self, ident: AdapterIdentity, op: str, value: str) -> None:
        if op == "read_version":
            ident.version = value
        elif op == "read_address":
            ident.address = value.upper()
        elif op == "read_name":
            ident.name = value
        elif op == "read_baudrate":
            ident.baud_code = value.strip()
            ident.baudrate = self.profile.baud_from_code(value.strip())
        elif op == "read_advertising":
            ident.advertising = value.strip() == "1"
        elif op == "read_service":
            ident.service_uuid = value
        elif op == "read_notify_characteristic":
            ident.notify_characteristic_uuid = value
        elif op == "read_write_characteristic":
            ident.write_characteristic_uuid = value

    def _consume(self, command, matched: list[str]):
        done = False
        failed = False
        while self._lines:
            line = self._lines.pop(0)
            if line.upper().startswith("ERROR"):
                matched.append(line)
                failed = True
                break
            if command.accepts_ok and line.startswith("OK"):
                matched.append(line)
                done = True
                break
            if command.end_line and line.startswith(command.end_line):
                matched.append(line)
                done = True
                break
            prefix = command.response_prefix
            if prefix and line.startswith(prefix):
                matched.append(line)
                if not command.multiline:
                    done = True
                    break
                continue
            if command.multiline and line:
                matched.append(line)
                continue
            if line.startswith("+") or line == "":
                continue
            self._payload += (line + "\r\n").encode("utf-8")
        return done, failed, matched

    def _flush_pending_lines(self) -> None:
        for line in self._lines:
            if line.startswith("+") or line.startswith("OK") or line.upper().startswith("ERROR"):
                continue
            if line:
                self._payload += (line + "\r\n").encode("utf-8")
        self._lines.clear()

    def _pump_once(self) -> bool:
        data = self.transport.read(512)
        now = time.monotonic()
        if data:
            self._last_rx = now
            for item in self._framer.feed(data):
                self._dispatch(item)
            return True
        if not self._waiting and now - self._last_rx >= self._idle_s:
            for item in self._framer.flush():
                self._dispatch(item)
        return False

    def _dispatch(self, item) -> None:
        if isinstance(item, Payload):
            if self._waiting and item.data.endswith(b"\n"):
                self._lines.append(item.data.decode("utf-8", "replace").strip("\r\n"))
                return
            self._payload += item.data
            return
        event: Event = item
        self._apply_event(event)
        self._events.append(event)
        if self._waiting:
            self._lines.append(event.text)

    def _apply_event(self, event: Event) -> None:
        if event.kind is EventKind.CONNECTED and event.link is not None:
            self.links[event.link.address] = event.link
        elif event.kind is EventKind.DISCONNECTED:
            if event.link is None:
                self.links.clear()
            else:
                self.links.pop(event.link.address, None)


def _advertisements(lines: list[str]) -> list[Advertisement]:
    found: list[Advertisement] = []
    for line in lines:
        match = _ADVERTISEMENT_LINE.match(line.strip())
        if match is None:
            continue
        name = match.group("local_name") or ""
        found.append(
            Advertisement(
                address=match.group("address").upper(),
                rssi=int(match.group("rssi")),
                local_name=name.strip(),
                address_type=int(match.group("address_type")),
            )
        )
    return found


def attach(
    transport: ByteTransport,
    profiles: list[AtProfile],
    timeout: float = 0.4,
) -> UartBleSession | None:
    """在已经打开的通道上试探。命中后通道归会话所有。"""
    transport.read(256)
    for profile in profiles:
        probe = profile.probe_bytes()
        if not probe:
            continue
        transport.write(probe)
        deadline = time.monotonic() + timeout
        buf = bytearray()
        while time.monotonic() < deadline:
            chunk = transport.read(256)
            if chunk:
                buf += chunk
                text = bytes(buf).decode("utf-8", "replace")
                if profile.matches_probe(text):
                    return UartBleSession(transport, profile)
            else:
                time.sleep(0.005)
        transport.read(256)
    return None


def open_session(
    port: str,
    *,
    baud: int | None = None,
    profile: str | None = None,
    timeout: float = 0.45,
) -> UartBleSession:
    """打开串口并识别适配器。profile 为空时按注册表逐个探测。"""
    from uart_ble.registry import at_profiles, get_profile

    if profile == "raw":
        chosen = get_profile("raw")
        transport = SerialTransport(port, baud or chosen.default_baud)
        return UartBleSession(transport, chosen)

    if profile:
        candidates = [get_profile(profile)]
    else:
        candidates = at_profiles()
    if not candidates:
        raise AdapterNotFound("没有可探测的适配器 profile")

    bauds: list[int] = []
    if baud is not None:
        bauds.append(baud)
    else:
        for item in candidates:
            if item.default_baud not in bauds:
                bauds.append(item.default_baud)
            for rate in item.spec.baud_codes:
                if rate not in bauds:
                    bauds.append(rate)

    last_error = ""
    for rate in bauds:
        try:
            transport = SerialTransport(port, rate)
        except Exception as exc:
            raise UartBleError(f"无法打开 {port}: {exc}") from exc
        try:
            session = attach(transport, candidates, timeout)
        except Exception as exc:
            transport.close()
            last_error = str(exc)
            continue
        if session is None:
            transport.close()
            continue
        session.refresh_identity()
        return session
    detail = f"：{last_error}" if last_error else ""
    raise AdapterNotFound(f"{port} 上没有适配器应答{detail}")
