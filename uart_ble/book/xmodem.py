"""XMODEM-CRC。128 字节一块，没有文件名。"""

from __future__ import annotations

from uart_ble.book.crc import crc16
from uart_ble.book.link import Link, TransferError

SOH = 0x01
EOT = 0x04
ACK = 0x06
NAK = 0x15
CAN = 0x18
CRC_REQ = ord("C")
BLOCK = 128
PAD = 0x1A


def send(link: Link, payload: bytes, timeout: float = 3.0) -> None:
    _wait_crc_request(link, timeout)
    seq = 1
    offset = 0
    while offset < len(payload) or (offset == 0 and not payload):
        if not payload:
            break
        chunk = payload[offset : offset + BLOCK]
        offset += BLOCK
        _send_block(link, seq, chunk, timeout)
        seq = (seq + 1) & 0xFF
    link.write(bytes([EOT]))
    if link.read_byte(timeout) != ACK:
        raise TransferError("XMODEM 结束未被确认")


def recv(link: Link, timeout: float = 3.0) -> bytes:
    link.write(bytes([CRC_REQ]))
    out = bytearray()
    expect = 1
    while True:
        head = link.read_byte(timeout)
        if head == EOT:
            link.write(bytes([ACK]))
            return bytes(out)
        if head == CAN:
            raise TransferError("XMODEM 被取消")
        if head != SOH:
            link.write(bytes([NAK]))
            continue
        seq = link.read_byte(timeout)
        complement = link.read_byte(timeout)
        data = link.read_exact(BLOCK, timeout)
        crc_bytes = link.read_exact(2, timeout)
        ok = (seq ^ 0xFF) == complement and int.from_bytes(crc_bytes, "big") == crc16(data)
        if ok and seq == expect:
            out += data
            expect = (expect + 1) & 0xFF
            link.write(bytes([ACK]))
        elif ok and seq == ((expect - 1) & 0xFF):
            link.write(bytes([ACK]))
        else:
            link.write(bytes([NAK]))


def _wait_crc_request(link: Link, timeout: float) -> None:
    deadline_byte = link.read_byte(timeout)
    if deadline_byte != CRC_REQ:
        raise TransferError("对端没有请求 CRC 模式")


def _send_block(link: Link, seq: int, chunk: bytes, timeout: float) -> None:
    block = chunk.ljust(BLOCK, bytes([PAD]))
    frame = bytes([SOH, seq, seq ^ 0xFF]) + block + crc16(block).to_bytes(2, "big")
    for _ in range(10):
        link.write(frame)
        reply = link.read_byte(timeout)
        if reply == ACK:
            return
        if reply == CAN:
            raise TransferError("XMODEM 被取消")
    raise TransferError("XMODEM 块重试耗尽")
