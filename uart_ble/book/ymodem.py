"""YMODEM。第 0 块带文件名和长度，数据块 1024 字节。"""

from __future__ import annotations

from uart_ble.book.crc import crc16
from uart_ble.book.link import Link, TransferError

SOH = 0x01
STX = 0x02
EOT = 0x04
ACK = 0x06
NAK = 0x15
CAN = 0x18
CRC_REQ = ord("C")
PAD = 0x1A


def send(link: Link, name: str, payload: bytes, timeout: float = 3.0) -> None:
    if link.read_byte(timeout) != CRC_REQ:
        raise TransferError("YMODEM 对端没有请求 CRC")
    _block(link, 0, _header(name, len(payload)), 128, timeout)
    if link.read_byte(timeout) != CRC_REQ:
        raise TransferError("YMODEM 对端没有开始收数据")
    seq = 1
    offset = 0
    while offset < len(payload):
        _block(link, seq, payload[offset : offset + 1024], 1024, timeout)
        seq = (seq + 1) & 0xFF
        offset += 1024
    link.write(bytes([EOT]))
    if link.read_byte(timeout) == NAK:
        link.write(bytes([EOT]))
    if link.read_byte(timeout) != ACK:
        raise TransferError("YMODEM 结束未被确认")
    if link.read_byte(timeout) != CRC_REQ:
        raise TransferError("YMODEM 没有进入批结束")
    _block(link, 0, b"\0" * 128, 128, timeout)


def recv(link: Link, timeout: float = 3.0) -> tuple[str, bytes]:
    link.write(bytes([CRC_REQ]))
    header = _read_block(link, 128, timeout)
    if not header:
        raise TransferError("YMODEM 缺少文件头")
    name, size = _parse_header(header)
    link.write(bytes([CRC_REQ]))
    if size == 0:
        _finish(link, timeout)
        return name, b""
    out = bytearray()
    while len(out) < size:
        piece = _read_block(link, 1024, timeout)
        if piece is None:
            break
        out += piece
    body = bytes(out[:size])
    _finish(link, timeout)
    return name, body


def _header(name: str, size: int) -> bytes:
    raw = name.encode("utf-8") + b"\0" + str(size).encode("ascii") + b"\0"
    return raw.ljust(128, b"\0")[:128]


def _parse_header(block: bytes) -> tuple[str, int]:
    name, _, rest = block.partition(b"\0")
    size_text = rest.split(b"\0", 1)[0].split(b" ", 1)[0]
    size = int(size_text) if size_text.isdigit() else 0
    return name.decode("utf-8", "replace"), size


def _block(link: Link, seq: int, data: bytes, size: int, timeout: float) -> None:
    body = data.ljust(size, bytes([PAD]))[:size]
    head = STX if size == 1024 else SOH
    frame = bytes([head, seq & 0xFF, (seq ^ 0xFF) & 0xFF]) + body + crc16(body).to_bytes(2, "big")
    for _ in range(10):
        link.write(frame)
        if link.read_byte(timeout) == ACK:
            return
    raise TransferError("YMODEM 块重试耗尽")


def _read_block(link: Link, fallback: int, timeout: float) -> bytes | None:
    head = link.read_byte(timeout)
    if head == EOT:
        link.buf[:0] = bytes([EOT])
        return None
    size = 1024 if head == STX else 128 if head == SOH else fallback
    if head not in (SOH, STX):
        raise TransferError("YMODEM 块头无效")
    link.read_exact(2, timeout)
    data = link.read_exact(size, timeout)
    crc_bytes = link.read_exact(2, timeout)
    if int.from_bytes(crc_bytes, "big") != crc16(data):
        link.write(bytes([NAK]))
        raise TransferError("YMODEM CRC 错误")
    link.write(bytes([ACK]))
    return data


def _finish(link: Link, timeout: float) -> None:
    if link.read_byte(timeout) != EOT:
        raise TransferError("YMODEM 没有结束符")
    link.write(bytes([NAK]))
    if link.read_byte(timeout) != EOT:
        raise TransferError("YMODEM 第二次结束符缺失")
    link.write(bytes([ACK]))
    link.write(bytes([CRC_REQ]))
    closing = _read_block(link, 128, timeout)
    if closing is None:
        raise TransferError("YMODEM 批结束缺失")
