"""把任意收发函数收成按字节读的链路。传书协议只依赖这个。"""

from __future__ import annotations

import queue
import time
from typing import Callable


class TransferError(Exception):
    pass


class Link:
    def __init__(self, read: Callable[[int, float], bytes], write: Callable[[bytes], None]) -> None:
        self._read = read
        self._write = write
        self.buf = bytearray()

    def write(self, data: bytes) -> None:
        if data:
            self._write(data)

    def read(self, size: int, timeout: float) -> bytes:
        deadline = time.monotonic() + timeout
        while len(self.buf) < size:
            left = deadline - time.monotonic()
            if left <= 0:
                break
            chunk = self._read(size - len(self.buf), min(0.2, left))
            if chunk:
                self.buf += chunk
            else:
                time.sleep(0.002)
        take = min(size, len(self.buf))
        out = bytes(self.buf[:take])
        del self.buf[:take]
        return out

    def read_exact(self, size: int, timeout: float) -> bytes:
        data = self.read(size, timeout)
        if len(data) != size:
            raise TransferError("链路超时")
        return data

    def read_byte(self, timeout: float) -> int:
        return self.read_exact(1, timeout)[0]


class MemoryPipe:
    """测试用双向管道的一端。"""

    def __init__(self, incoming: queue.Queue[bytes], outgoing: queue.Queue[bytes]) -> None:
        self._in = incoming
        self._out = outgoing
        self._buf = bytearray()

    def write(self, data: bytes) -> None:
        if data:
            self._out.put(data)

    def read(self, size: int, timeout: float) -> bytes:
        deadline = time.monotonic() + timeout
        while len(self._buf) < size:
            left = deadline - time.monotonic()
            if left <= 0:
                break
            try:
                self._buf += self._in.get(timeout=min(0.05, left))
            except queue.Empty:
                break
        take = min(size, len(self._buf))
        out = bytes(self._buf[:take])
        del self._buf[:take]
        return out


def pair() -> tuple[MemoryPipe, MemoryPipe]:
    left: queue.Queue[bytes] = queue.Queue()
    right: queue.Queue[bytes] = queue.Queue()
    return MemoryPipe(right, left), MemoryPipe(left, right)
