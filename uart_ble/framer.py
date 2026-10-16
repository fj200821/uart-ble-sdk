"""把字节流拆成「透传载荷」和「模块主动上报的一行」。

以 ``+`` 开头、且能被当前 profile 识别的一行是事件。
其余字节原样交给透传，包括二进制里偶然出现的换行。
"""

from __future__ import annotations

from dataclasses import dataclass

from uart_ble.types import Event

# 已知主动上报都是短行。更长的 "+..." 视为透传，避免二进制被一直卡住。
_HOLD_LIMIT = 80


@dataclass(frozen=True)
class Payload:
    data: bytes


FrameItem = Event | Payload


class Framer:
    def __init__(self, classify) -> None:
        self._buf = bytearray()
        self._classify = classify

    def feed(self, data: bytes) -> list[FrameItem]:
        if data:
            self._buf += data
        return self._drain(flush=False)

    def flush(self) -> list[FrameItem]:
        return self._drain(flush=True)

    def _drain(self, flush: bool) -> list[FrameItem]:
        out: list[FrameItem] = []
        while True:
            nl = self._buf.find(b"\n")
            if nl < 0:
                break
            raw = bytes(self._buf[: nl + 1])
            del self._buf[: nl + 1]
            out.extend(self._split_line(raw))
        if not self._buf:
            return out
        plus = self._buf.find(b"+")
        if plus > 0:
            out.append(Payload(bytes(self._buf[:plus])))
            del self._buf[:plus]
        if flush or len(self._buf) > _HOLD_LIMIT:
            out.append(Payload(bytes(self._buf)))
            self._buf.clear()
            return out
        if self._buf.startswith(b"+") or self._buf == b"\r":
            return out
        if self._buf.endswith(b"\r"):
            head = bytes(self._buf[:-1])
            self._buf = bytearray(b"\r")
            if head:
                out.append(Payload(head))
            return out
        out.append(Payload(bytes(self._buf)))
        self._buf.clear()
        return out

    def _split_line(self, raw: bytes) -> list[FrameItem]:
        body = raw[:-1]
        if body.endswith(b"\r"):
            body = body[:-1]
        for index, char in enumerate(body):
            if char != 0x2B:
                continue
            event = self._classify(body[index:].decode("utf-8", "replace"))
            if event is None:
                continue
            out: list[FrameItem] = []
            if index:
                out.append(Payload(body[:index]))
            out.append(event)
            return out
        return [Payload(raw)] if raw else []
