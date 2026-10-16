"""内置 profile。导入本包即完成注册。"""

from uart_ble.profile import AtProfile
from uart_ble.profiles.raw import RAW_SPEC
from uart_ble.profiles.xy_dg02 import XY_DG02_SPEC
from uart_ble.registry import register_profile

XY_DG02: AtProfile = register_profile(AtProfile(XY_DG02_SPEC))
RAW: AtProfile = register_profile(AtProfile(RAW_SPEC))

__all__ = ["RAW", "XY_DG02"]
