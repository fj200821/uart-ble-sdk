"""命令行：查看端口、读身份、按 profile 把模块收成透传适配器。"""

from __future__ import annotations

import argparse
import sys

import uart_ble.profiles  # noqa: F401  注册内置 profile
from uart_ble.book.link import TransferError
from uart_ble.registry import profile_ids
from uart_ble.session import open_session
from uart_ble.types import UartBleError


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="uart-ble")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("profiles", help="列出已注册的适配器")
    sub.add_parser("ports", help="列出本机串口")

    info = sub.add_parser("info", help="识别串口上的适配器并打印身份")
    _add_port_args(info)

    scan = sub.add_parser("scan", help="startScan，扫一轮附近广播")
    _add_port_args(scan)

    setup = sub.add_parser("setup", help="startAdvertising，可选带本地名")
    _add_port_args(setup)
    setup.add_argument("--name", default=None, help="广播名，不超过该 profile 的长度限制")

    send = sub.add_parser("send-book", help="在已经透传的串口上发送一本书")
    _add_port_args(send)
    send.add_argument("file")
    send.add_argument("--protocol", default="ymodem", choices=("xmodem", "ymodem", "zmodem"))

    recv = sub.add_parser("recv-book", help="在已经透传的串口上接收一本书")
    _add_port_args(recv)
    recv.add_argument("dest")
    recv.add_argument("--protocol", default="ymodem", choices=("xmodem", "ymodem", "zmodem"))
    recv.add_argument("--name", default="book.bin", help="XMODEM 没有文件名，用这个名字保存")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "profiles":
            for item in profile_ids():
                print(item)
            return 0
        if args.cmd == "ports":
            return _ports()
        if args.cmd == "info":
            return _info(args)
        if args.cmd == "scan":
            return _scan(args)
        if args.cmd == "setup":
            return _setup(args)
        if args.cmd == "send-book":
            return _send_book(args)
        if args.cmd == "recv-book":
            return _recv_book(args)
    except (UartBleError, TransferError, ValueError, OSError) as exc:
        print(f"error: {exc}")
        return 1
    return 2


def _add_port_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=None)
    parser.add_argument(
        "--profile",
        default=None,
        help="xy-dg02、raw，或 define_profile 注册的 id；省略则自动探测",
    )


def _ports() -> int:
    from serial.tools import list_ports

    found = list(list_ports.comports())
    if not found:
        print("没有串口")
        return 1
    for item in found:
        print(f"{item.device}\t{item.description}")
    return 0


def _info(args) -> int:
    with open_session(args.port, baud=args.baud, profile=args.profile) as session:
        _print_identity(session)
    return 0


def _scan(args) -> int:
    with open_session(args.port, baud=args.baud, profile=args.profile) as session:
        found = session.start_scan()
    if not found:
        print("没有扫到广播")
        return 0
    for item in found:
        name = item.local_name or "-"
        print(f"{item.address}\trssi={item.rssi}\tname={name}")
    return 0


def _send_book(args) -> int:
    with open_session(args.port, baud=args.baud, profile=args.profile or "raw") as session:
        session.send_book(args.file, args.protocol)
    print(args.file)
    return 0


def _recv_book(args) -> int:
    with open_session(args.port, baud=args.baud, profile=args.profile or "raw") as session:
        saved = session.recv_book(args.dest, args.protocol, args.name)
    print(saved)
    return 0


def _setup(args) -> int:
    with open_session(args.port, baud=args.baud, profile=args.profile) as session:
        session.start_advertising(local_name=args.name)
        _print_identity(session)
    return 0


def _print_identity(session) -> None:
    ident = session.identity
    adv = "开" if ident.advertising else "关"
    if ident.advertising is None:
        adv = "未知"
    baud = str(ident.baudrate) if ident.baudrate else "未知"
    print(f"profile: {ident.profile_id}")
    print(f"version: {ident.version}")
    print(f"name: {session.name}")
    print(f"address: {session.address}")
    print(f"baudrate: {baud} (code {ident.baud_code})")
    print(f"advertising: {adv}")
    print(f"service: {ident.service_uuid}")
    print(f"notify characteristic: {ident.notify_characteristic_uuid}")
    print(f"write characteristic: {ident.write_characteristic_uuid}")
    print(f"connection: {session.connection_status.value}")


if __name__ == "__main__":
    raise SystemExit(main())
