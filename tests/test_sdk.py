"""用内存串口验证分帧、XY-DG02 指令表，以及后注册的另一种适配器。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from uart_ble.framer import Framer, Payload
from uart_ble.profile import AtProfileSpec, CommandDef
from uart_ble.profiles import RAW, XY_DG02
from uart_ble.registry import define_profile, profile_ids, unregister_profile
from uart_ble.session import UartBleSession, attach
from uart_ble.transport import MemoryTransport
from uart_ble.types import (
    CommandFailed,
    ConnectionStatus,
    EventKind,
    LinkBusy,
    PeerRole,
    UnsupportedCommand,
)


def _xy_reply(data: bytes, _transport: MemoryTransport) -> bytes:
    table = {
        b"AT+VER?\r\n": b"+VER:V1.2.1\r\n",
        b"AT+MAC?\r\n": b"+MAC:C955CFF917FF\r\n",
        b"AT+NAME?\r\n": b"+NAME:XY-DG02\r\n",
        b"AT+UART?\r\n": b"+UART:5\r\n",
        b"AT+ADV?\r\n": b"+ADV:1\r\n",
        b"AT+UUIDS?\r\n": b"+UUIDS:FFF0\r\n",
        b"AT+UUIDN?\r\n": b"+UUIDN:FFF1\r\n",
        b"AT+UUIDW?\r\n": b"+UUIDW:FFF2\r\n",
        b"AT+NAME=DEMO\r\n": b"OK\r\n",
        b"AT+ADV=1\r\n": b"OK\r\n",
        b"AT+UART=6\r\n": b"OK\r\n",
        b"AT+DISCONN=1\r\n": b"+DISCONN:0,AABBCCDDEEFF\r\n",
        b"AT+SCAN=1\r\n": (
            b"+SCAN:\r\n"
            b"001B10F4DA0B 1 -35 NBEE\r\n"
            b"C955CFF917FF 0 -82\r\n"
            b"+SCAN END\r\n"
        ),
        b"AT+SCAN=0\r\n": b"OK\r\n",
        b"AT+NOPE\r\n": b"ERROR\r\n",
    }
    return table.get(data, b"ERROR\r\n")


class FramerTest(unittest.TestCase):
    def test_event_splits_from_payload(self) -> None:
        framer = Framer(XY_DG02.classify)
        items = framer.feed(b"abc+CONNECTED:0,AABBCCDDEEFF\r\nxyz")
        self.assertIsInstance(items[0], Payload)
        self.assertEqual(items[0].data, b"abc")
        self.assertEqual(items[1].kind, EventKind.CONNECTED)
        self.assertEqual(items[1].link.address, "AABBCCDDEEFF")
        self.assertEqual(items[1].link.role, PeerRole.CENTRAL)
        self.assertEqual(items[2].data, b"xyz")

    def test_partial_event_is_held(self) -> None:
        framer = Framer(XY_DG02.classify)
        self.assertEqual(framer.feed(b"+CONNECTED:0,AA"), [])
        items = framer.feed(b"BBCCDDEEFF\r\n")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].kind, EventKind.CONNECTED)

    def test_cr_is_not_split_off_the_line(self) -> None:
        framer = Framer(XY_DG02.classify)
        self.assertEqual(framer.feed(b"hello\r"), [Payload(b"hello")])
        items = framer.feed(b"\n")
        self.assertEqual(items, [Payload(b"\r\n")])


class XyDg02SessionTest(unittest.TestCase):
    def _session(self) -> tuple[UartBleSession, MemoryTransport]:
        transport = MemoryTransport(_xy_reply)
        return UartBleSession(transport, XY_DG02), transport

    def test_identity(self) -> None:
        session, _transport = self._session()
        ident = session.refresh_identity()
        self.assertEqual(ident.profile_id, "xy-dg02")
        self.assertEqual(ident.version, "V1.2.1")
        self.assertEqual(ident.address, "C955CFF917FF")
        self.assertEqual(session.name, "XY-DG02")
        self.assertEqual(ident.baudrate, 115200)
        self.assertTrue(ident.advertising)
        self.assertEqual(session.connection_status, ConnectionStatus.DISCONNECTED)
        services = session.discover_services()
        self.assertEqual(services.service_uuid, "FFF0")
        self.assertEqual(services.notify_characteristic_uuid, "FFF1")
        self.assertEqual(services.write_characteristic_uuid, "FFF2")

    def test_start_advertising_sends_name_and_adv(self) -> None:
        session, transport = self._session()
        session.start_advertising(local_name="DEMO")
        sent = bytes(transport.tx)
        self.assertIn(b"AT+NAME=DEMO\r\n", sent)
        self.assertIn(b"AT+ADV=1\r\n", sent)
        self.assertEqual(session.name, "XY-DG02")
        self.assertTrue(session.identity.advertising)

    def test_set_baudrate_reopens_host_uart(self) -> None:
        session, transport = self._session()
        session.set_baudrate(230400)
        self.assertIn(b"AT+UART=6\r\n", bytes(transport.tx))
        self.assertEqual(transport.baud, 230400)

    def test_error_raises(self) -> None:
        session, _transport = self._session()
        with self.assertRaises(CommandFailed):
            session.command("write_name", value="")

    def test_connected_blocks_at_but_allows_disconnect(self) -> None:
        session, _transport = self._session()
        _transport.push_rx(b"+CONNECTED:0,AABBCCDDEEFF\r\n")
        events = session.poll(0.05)
        self.assertEqual(events[0].link.role, PeerRole.CENTRAL)
        self.assertEqual(session.connection_status, ConnectionStatus.CONNECTED)
        with self.assertRaises(LinkBusy):
            session.start_advertising(local_name="DEMO")
        session.disconnect()
        self.assertEqual(session.connection_status, ConnectionStatus.DISCONNECTED)

    def test_start_scan_reads_advertisements(self) -> None:
        session, _transport = self._session()
        found = session.start_scan(timeout=0.5)
        self.assertEqual(len(found), 2)
        self.assertEqual(found[0].address, "001B10F4DA0B")
        self.assertEqual(found[0].rssi, -35)
        self.assertEqual(found[0].local_name, "NBEE")
        self.assertEqual(found[0].address_type, 1)
        self.assertEqual(found[1].local_name, "")
        session.stop_scan()

    def test_characteristic_bytes(self) -> None:
        session, transport = self._session()
        transport.push_rx(b"hello")
        self.assertEqual(session.read_characteristic(timeout=0.05), b"hello")
        session.write_characteristic(b"ping")
        self.assertTrue(bytes(transport.tx).endswith(b"ping"))


class OtherAdapterTest(unittest.TestCase):
    def tearDown(self) -> None:
        unregister_profile("acme")

    def test_define_profile_is_probed(self) -> None:
        define_profile(
            AtProfileSpec(
                profile_id="acme",
                display_name="ACME",
                default_baud=9600,
                probe_command="AT+ID?",
                probe_prefix="+ID:ACME",
                commands={
                    "read_version": CommandDef("AT+ID?", response_prefix="+ID:"),
                    "write_name": CommandDef("AT+N={value}", accepts_ok=True),
                    "start_advertising": CommandDef("AT+A=1", accepts_ok=True),
                },
                identity_ops=("read_version",),
            )
        )
        self.assertIn("acme", profile_ids())

        def reply(data: bytes, _transport: MemoryTransport) -> bytes:
            if data == b"AT+VER?\r\n":
                return b""
            if data == b"AT+ID?\r\n":
                return b"+ID:ACME-1\r\n"
            if data.startswith(b"AT+N=") or data.startswith(b"AT+A="):
                return b"OK\r\n"
            return b"ERROR\r\n"

        transport = MemoryTransport(reply, baud=9600)
        from uart_ble.registry import at_profiles

        session = attach(transport, at_profiles(), timeout=0.08)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.profile.profile_id, "acme")
        ident = session.refresh_identity()
        self.assertEqual(ident.version, "ACME-1")
        session.start_advertising(local_name="BOX")
        self.assertIn(b"AT+N=BOX\r\n", bytes(transport.tx))
        self.assertIn(b"AT+A=1\r\n", bytes(transport.tx))

    def test_raw_has_no_at(self) -> None:
        session = UartBleSession(MemoryTransport(), RAW)
        with self.assertRaises(UnsupportedCommand):
            session.command("read_name")
        session.transport.push_rx(b"+VER:NO\r\n")
        self.assertEqual(session.read_characteristic(timeout=0.05), b"+VER:NO\r\n")


if __name__ == "__main__":
    unittest.main()
