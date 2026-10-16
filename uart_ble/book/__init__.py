"""在已经接通的透传链路上传一本书。

XMODEM 只有正文。YMODEM 和 ZMODEM 带文件名与长度。
两边都要先进入透传：手机或另一块模组已经连上，串口不再解释 AT。
"""

from __future__ import annotations

from pathlib import Path

from uart_ble.book.link import Link
from uart_ble.book import xmodem, ymodem, zmodem

PROTOCOLS = ("xmodem", "ymodem", "zmodem")


def send_book(link: Link, file: str | Path, protocol: str = "ymodem") -> None:
    kind = _protocol(protocol)
    path = Path(file)
    payload = path.read_bytes()
    if kind == "xmodem":
        xmodem.send(link, payload)
    elif kind == "ymodem":
        ymodem.send(link, path.name, payload)
    else:
        zmodem.send(link, path.name, payload)


def recv_book(
    link: Link,
    dest_dir: str | Path,
    protocol: str = "ymodem",
    name: str = "book.bin",
) -> Path:
    directory = Path(dest_dir)
    directory.mkdir(parents=True, exist_ok=True)
    kind = _protocol(protocol)
    if kind == "xmodem":
        filename, payload = name, xmodem.recv(link)
    elif kind == "ymodem":
        filename, payload = ymodem.recv(link)
    else:
        filename, payload = zmodem.recv(link)
    safe = Path(filename).name or name
    target = directory / safe
    target.write_bytes(payload)
    return target


def _protocol(name: str) -> str:
    kind = name.strip().lower()
    if kind not in PROTOCOLS:
        raise ValueError(f"协议必须是 {', '.join(PROTOCOLS)}")
    return kind
