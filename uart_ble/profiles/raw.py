"""已经配好的透传模块：没有 AT，串口字节原样进出。"""

from __future__ import annotations

from uart_ble.profile import AtProfileSpec

RAW_SPEC = AtProfileSpec(
    profile_id="raw",
    display_name="raw",
    default_baud=115200,
    probe_command="",
    probe_prefix="",
    commands={},
)
