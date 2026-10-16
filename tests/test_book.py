"""XMODEM / YMODEM / ZMODEM 在内存双工链路上对传。"""

from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from uart_ble.book import recv_book, send_book
from uart_ble.book.crc import crc16
from uart_ble.book.link import Link, TransferError, pair
from uart_ble.book import xmodem, ymodem, zmodem
from uart_ble.profiles import RAW, XY_DG02
from uart_ble.session import UartBleSession
from uart_ble.transport import MemoryTransport
from uart_ble.types import UartBleError


def _roundtrip(send, recv):
    left_pipe, right_pipe = pair()
    left = Link(left_pipe.read, left_pipe.write)
    right = Link(right_pipe.read, right_pipe.write)
    box: list = []

    def run_recv() -> None:
        box.append(recv(right))

    worker = threading.Thread(target=run_recv)
    worker.start()
    try:
        send(left)
    finally:
        worker.join(8)
    if worker.is_alive():
        raise TimeoutError("接收端没有结束")
    return box[0]


class BookTransferTest(unittest.TestCase):
    def test_crc16_known_vector(self) -> None:
        self.assertEqual(crc16(b"123456789"), 0x31C3)

    def test_xmodem_roundtrip(self) -> None:
        payload = bytes(range(128))

        def send(link: Link) -> None:
            xmodem.send(link, payload)

        got = _roundtrip(send, xmodem.recv)
        self.assertEqual(got, payload)

    def test_xmodem_pads_short_block(self) -> None:
        payload = b"abc"

        def send(link: Link) -> None:
            xmodem.send(link, payload)

        got = _roundtrip(send, xmodem.recv)
        self.assertEqual(got[:3], payload)
        self.assertEqual(len(got), 128)

    def test_ymodem_keeps_name_size_and_nul(self) -> None:
        payload = b"hello\0book" + bytes([0x1A, 0x00, 0xFF])

        def send(link: Link) -> None:
            ymodem.send(link, "note.txt", payload)

        name, got = _roundtrip(send, ymodem.recv)
        self.assertEqual(name, "note.txt")
        self.assertEqual(got, payload)

    def test_ymodem_empty(self) -> None:
        def send(link: Link) -> None:
            ymodem.send(link, "empty.txt", b"")

        name, got = _roundtrip(send, ymodem.recv)
        self.assertEqual((name, got), ("empty.txt", b""))

    def test_zmodem_escapes_control_bytes(self) -> None:
        payload = bytes([0x00, 0x10, 0x11, 0x13, 0x18, 0x90, 0xFF]) + b"Z" * 1500

        def send(link: Link) -> None:
            zmodem.send(link, "big.bin", payload)

        name, got = _roundtrip(send, zmodem.recv)
        self.assertEqual(name, "big.bin")
        self.assertEqual(got, payload)

    def test_files_roundtrip(self) -> None:
        payload = "第一章\n".encode("utf-8") + b"\0" * 3
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "章.txt"
            source.write_bytes(payload)
            dest = root / "in"
            for protocol in ("xmodem", "ymodem", "zmodem"):
                left_pipe, right_pipe = pair()
                left = Link(left_pipe.read, left_pipe.write)
                right = Link(right_pipe.read, right_pipe.write)
                saved: list[Path] = []

                def run_recv(link=right, kind=protocol) -> None:
                    saved.append(recv_book(link, dest, kind, "fallback.bin"))

                worker = threading.Thread(target=run_recv)
                worker.start()
                try:
                    send_book(left, source, protocol)
                finally:
                    worker.join(8)
                self.assertFalse(worker.is_alive(), protocol)
                body = saved[0].read_bytes()
                if protocol == "xmodem":
                    self.assertEqual(saved[0].name, "fallback.bin")
                    self.assertTrue(body.startswith(payload))
                else:
                    self.assertEqual(saved[0].name, "章.txt")
                    self.assertEqual(body, payload)

    def test_session_refuses_before_link(self) -> None:
        session = UartBleSession(MemoryTransport(), XY_DG02)
        with self.assertRaises(UartBleError):
            session.send_book("missing.bin")

    def test_unknown_protocol(self) -> None:
        left, _right = pair()
        with self.assertRaises(ValueError):
            send_book(Link(left.read, left.write), "missing.bin", "kermit")

    def test_raw_session_can_call_transfer(self) -> None:
        session = UartBleSession(MemoryTransport(), RAW)
        with self.assertRaises(TransferError):
            session.recv_book(tempfile.gettempdir(), "xmodem")


if __name__ == "__main__":
    unittest.main()
