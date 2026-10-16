"""ZMODEM 单文件收发。带文件名、长度，以及从 ZRPOS 指定的偏移续传。"""

from __future__ import annotations

from uart_ble.book.crc import crc16, crc32
from uart_ble.book.link import Link, TransferError

ZPAD = 0x2A
ZDLE = 0x18
ZHEX = ord("B")
ZBIN32 = ord("C")
ZRQINIT = 0
ZRINIT = 1
ZFILE = 4
ZFIN = 8
ZRPOS = 9
ZDATA = 10
ZEOF = 11
ZCRCE = ord("h")
ZCRCG = ord("i")
CANFDX = 0x01
CANFC32 = 0x20
_ESCAPE = {0x18, 0x10, 0x90, 0x11, 0x91, 0x13, 0x93}
_FRAME_END = {ZCRCE, ZCRCG}


def send(link: Link, name: str, payload: bytes, timeout: float = 3.0) -> None:
    link.write(_hex_header(ZRQINIT, 0))
    _expect(link, ZRINIT, timeout)
    link.write(_bin32_header(ZFILE, 0))
    meta = name.encode("utf-8") + b"\0" + str(len(payload)).encode("ascii") + b"\0"
    link.write(_subpacket(meta, ZCRCE))
    offset = _expect(link, ZRPOS, timeout)
    offset = min(offset, len(payload))
    link.write(_bin32_header(ZDATA, offset))
    cursor = offset
    while cursor < len(payload):
        nxt = min(cursor + 1024, len(payload))
        end = ZCRCE if nxt == len(payload) else ZCRCG
        link.write(_subpacket(payload[cursor:nxt], end))
        cursor = nxt
    if cursor == offset:
        link.write(_subpacket(b"", ZCRCE))
    link.write(_bin32_header(ZEOF, len(payload)))
    _expect(link, ZRINIT, timeout)
    link.write(_hex_header(ZFIN, 0))
    _expect(link, ZFIN, timeout)
    link.write(b"OO")


def recv(link: Link, timeout: float = 3.0) -> tuple[str, bytes]:
    _expect(link, ZRQINIT, timeout)
    link.write(_hex_header(ZRINIT, CANFDX | CANFC32))
    _expect(link, ZFILE, timeout)
    meta, _end = _read_subpacket(link, timeout)
    name, size = _parse_meta(meta)
    link.write(_hex_header(ZRPOS, 0))
    _expect(link, ZDATA, timeout)
    out = bytearray()
    while True:
        chunk, end = _read_subpacket(link, timeout)
        out += chunk
        if end == ZCRCE:
            break
    _expect(link, ZEOF, timeout)
    link.write(_hex_header(ZRINIT, CANFDX | CANFC32))
    _expect(link, ZFIN, timeout)
    link.write(_hex_header(ZFIN, 0))
    link.read(2, timeout)
    return name, bytes(out[:size])


def _parse_meta(meta: bytes) -> tuple[str, int]:
    name, _, rest = meta.partition(b"\0")
    size_text = rest.split(b"\0", 1)[0].split(b" ", 1)[0]
    size = int(size_text) if size_text.isdigit() else len(meta)
    return name.decode("utf-8", "replace"), size


def _hex_header(frame_type: int, pos: int) -> bytes:
    raw = bytes([frame_type]) + (pos & 0xFFFFFFFF).to_bytes(4, "little")
    body = raw + crc16(raw).to_bytes(2, "big")
    text = "".join(f"{byte:02x}" for byte in body)
    return bytes([ZPAD, ZPAD, ZDLE, ZHEX]) + text.encode("ascii") + b"\r\n"


def _bin32_header(frame_type: int, pos: int) -> bytes:
    raw = bytes([frame_type]) + (pos & 0xFFFFFFFF).to_bytes(4, "little")
    body = raw + crc32(raw).to_bytes(4, "little")
    return bytes([ZPAD, ZPAD, ZDLE, ZBIN32]) + _escape(body)


def _subpacket(data: bytes, end: int) -> bytes:
    crc = crc32(data + bytes([end])).to_bytes(4, "little")
    return _escape(data) + bytes([ZDLE, end]) + _escape(crc)


def _escape(data: bytes) -> bytes:
    out = bytearray()
    for byte in data:
        if byte in _ESCAPE:
            out.extend((ZDLE, byte ^ 0x40))
        else:
            out.append(byte)
    return bytes(out)


def _expect(link: Link, frame_type: int, timeout: float) -> int:
    got, pos = _read_header(link, timeout)
    if got != frame_type:
        raise TransferError(f"ZMODEM 期望帧 {frame_type}，收到 {got}")
    return pos


def _read_header(link: Link, timeout: float) -> tuple[int, int]:
    window = bytearray()
    for _ in range(64):
        window += link.read_exact(1, timeout)
        if len(window) >= 2 and window[-2] == ZDLE and window[-1] in (ZHEX, ZBIN32):
            kind = window[-1]
            if kind == ZHEX:
                text = bytearray()
                while len(text) < 14:
                    char = link.read_byte(timeout)
                    if char in (13, 10):
                        continue
                    text.append(char)
                raw = bytes.fromhex(text[:14].decode("ascii"))
                if crc16(raw[:5]) != int.from_bytes(raw[5:7], "big"):
                    raise TransferError("ZMODEM 十六进制头 CRC 错误")
                return raw[0], int.from_bytes(raw[1:5], "little")
            raw = _read_escaped(link, 9, timeout)
            if crc32(raw[:5]) != int.from_bytes(raw[5:9], "little"):
                raise TransferError("ZMODEM 二进制头 CRC 错误")
            return raw[0], int.from_bytes(raw[1:5], "little")
    raise TransferError("ZMODEM 找不到帧头")


def _read_subpacket(link: Link, timeout: float) -> tuple[bytes, int]:
    out = bytearray()
    while True:
        byte = link.read_byte(timeout)
        if byte != ZDLE:
            out.append(byte)
            continue
        nxt = link.read_byte(timeout)
        if nxt in _FRAME_END:
            crc_bytes = _read_escaped(link, 4, timeout)
            if crc32(bytes(out) + bytes([nxt])) != int.from_bytes(crc_bytes, "little"):
                raise TransferError("ZMODEM 数据 CRC 错误")
            return bytes(out), nxt
        out.append(nxt ^ 0x40)


def _read_escaped(link: Link, size: int, timeout: float) -> bytes:
    out = bytearray()
    while len(out) < size:
        byte = link.read_byte(timeout)
        if byte == ZDLE:
            out.append(link.read_byte(timeout) ^ 0x40)
        else:
            out.append(byte)
    return bytes(out)
