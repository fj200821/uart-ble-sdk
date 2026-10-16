"""字节通道。真机用串口，测试用内存通道，会话层不区分。"""

from __future__ import annotations

from typing import Callable, Protocol


class ByteTransport(Protocol):
    def write(self, data: bytes) -> None: ...

    def read(self, max_bytes: int) -> bytes: ...

    def close(self) -> None: ...

    def reconfigure(self, baud: int) -> None: ...


class SerialTransport:
    def __init__(self, port: str, baud: int, timeout: float = 0.05) -> None:
        import serial

        self._ser = serial.Serial(
            port,
            baud,
            timeout=timeout,
            write_timeout=1.0,
        )

    @property
    def baud(self) -> int:
        return int(self._ser.baudrate)

    def write(self, data: bytes) -> None:
        self._ser.write(data)
        self._ser.flush()

    def read(self, max_bytes: int) -> bytes:
        chunk = self._ser.read(max_bytes)
        return bytes(chunk)

    def reconfigure(self, baud: int) -> None:
        self._ser.baudrate = int(baud)

    def close(self) -> None:
        self._ser.close()


Reply = Callable[[bytes, "MemoryTransport"], bytes]


class MemoryTransport:
    """按写出去的请求回放响应，供 profile 单测使用。"""

    def __init__(self, on_write: Reply | None = None, baud: int = 115200) -> None:
        self.baud = baud
        self.tx = bytearray()
        self._rx = bytearray()
        self._on_write = on_write
        self.closed = False

    def push_rx(self, data: bytes) -> None:
        self._rx += data

    def write(self, data: bytes) -> None:
        self.tx += data
        if self._on_write is None:
            return
        reply = self._on_write(bytes(data), self)
        if reply:
            self._rx += reply

    def read(self, max_bytes: int) -> bytes:
        if not self._rx:
            return b""
        chunk = bytes(self._rx[:max_bytes])
        del self._rx[:max_bytes]
        return chunk

    def reconfigure(self, baud: int) -> None:
        self.baud = int(baud)

    def close(self) -> None:
        self.closed = True
