"""XMODEM CRC-16 与 ZMODEM CRC-32。"""

from __future__ import annotations

import binascii


def crc16(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def crc32(data: bytes) -> int:
    return binascii.crc32(data) & 0xFFFFFFFF
