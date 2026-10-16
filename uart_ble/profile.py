"""适配器 profile。换模块时新增一份 AtProfileSpec，会话层不用改。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from uart_ble.types import Event, EventKind, Link, PeerRole, UnsupportedCommand


@dataclass(frozen=True)
class CommandDef:
    """一条 AT。template 里用 {value} 占位，不要写回车。"""

    template: str
    response_prefix: str | None = None
    accepts_ok: bool = False
    multiline: bool = False
    end_line: str | None = None


@dataclass(frozen=True)
class EventDef:
    """fullmatch 整行。命名组 raw_type、mac 会变成 Link。"""

    pattern: str
    kind: EventKind


@dataclass(frozen=True)
class AtProfileSpec:
    profile_id: str
    display_name: str
    default_baud: int
    probe_command: str
    probe_prefix: str
    commands: dict[str, CommandDef]
    events: tuple[EventDef, ...] = ()
    identity_ops: tuple[str, ...] = ()
    baud_codes: dict[int, str] = field(default_factory=dict)
    # 对端类型值等于它时，认为对端是主机（手机）。各模块手册可能相反，写在自己的 spec 里。
    central_type: int = 0
    allowed_while_linked: frozenset[str] = frozenset({"disconnect"})
    line_ending: str = "\r\n"
    name_limit: int = 0


class AtProfile:
    def __init__(self, spec: AtProfileSpec) -> None:
        self.spec = spec
        self.profile_id = spec.profile_id
        self.default_baud = spec.default_baud
        self._events = tuple(
            (re.compile(item.pattern), item.kind) for item in spec.events
        )

    def probe_bytes(self) -> bytes:
        if not self.spec.probe_command:
            return b""
        return (self.spec.probe_command + self.spec.line_ending).encode("ascii")

    def matches_probe(self, text: str) -> bool:
        return bool(self.spec.probe_prefix) and self.spec.probe_prefix in text

    def command_def(self, op: str) -> CommandDef:
        command = self.spec.commands.get(op)
        if command is None:
            raise UnsupportedCommand(f"{self.profile_id} 没有指令 {op}")
        return command

    def render(self, op: str, **kwargs: object) -> bytes:
        command = self.command_def(op)
        values = {key: str(val) for key, val in kwargs.items()}
        if op == "set_baudrate" and "value" in values:
            values["value"] = self.baud_code(kwargs.get("value"))
        if op == "write_name":
            self._check_name(values.get("value", ""))
        for key, val in values.items():
            if "\r" in val or "\n" in val:
                raise UnsupportedCommand(f"{op} 的参数不能换行")
        line = command.template
        for key, val in values.items():
            line = line.replace("{" + key + "}", val)
        if "{" in line or "}" in line:
            raise UnsupportedCommand(f"{op} 还缺参数")
        return (line + self.spec.line_ending).encode("utf-8")

    def baud_code(self, value: object) -> str:
        if isinstance(value, int) and value > 15:
            code = self.spec.baud_codes.get(value)
            if code is None:
                raise UnsupportedCommand(f"{self.profile_id} 不支持波特率 {value}")
            return code
        return str(value)

    def baud_from_code(self, code: str) -> int | None:
        wanted = str(code).strip()
        for rate, mapped in self.spec.baud_codes.items():
            if mapped == wanted:
                return rate
        return None

    def classify(self, line: str) -> Event | None:
        text = line.strip()
        for pattern, kind in self._events:
            match = pattern.fullmatch(text)
            if match is None:
                continue
            link = None
            groups = match.groupdict()
            if "raw_type" in groups and "address" in groups:
                raw = int(groups["raw_type"])
                role = (
                    PeerRole.CENTRAL
                    if raw == self.spec.central_type
                    else PeerRole.PERIPHERAL
                )
                link = Link(role=role, address=groups["address"].upper(), raw_type=raw)
            return Event(kind=kind, text=text, link=link)
        return None

    def _check_name(self, value: str) -> None:
        limit = self.spec.name_limit
        if limit and len(value.encode("utf-8")) > limit:
            raise UnsupportedCommand(f"名称超过 {limit} 字节")
