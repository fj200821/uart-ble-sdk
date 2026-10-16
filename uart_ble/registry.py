"""profile 注册表。新模块调用 define_profile 即可被自动探测。"""

from __future__ import annotations

from uart_ble.profile import AtProfile, AtProfileSpec
from uart_ble.types import AdapterNotFound

_PROFILES: dict[str, AtProfile] = {}


def register_profile(profile: AtProfile) -> AtProfile:
    _PROFILES[profile.profile_id] = profile
    return profile


def define_profile(spec: AtProfileSpec) -> AtProfile:
    return register_profile(AtProfile(spec))


def unregister_profile(profile_id: str) -> None:
    _PROFILES.pop(profile_id, None)


def get_profile(profile_id: str) -> AtProfile:
    try:
        return _PROFILES[profile_id]
    except KeyError as exc:
        raise AdapterNotFound(f"未注册的适配器 {profile_id}") from exc


def profile_ids() -> list[str]:
    return list(_PROFILES)


def at_profiles() -> list[AtProfile]:
    """会应答探测指令的 profile。纯透传不参与自动识别。"""
    return [item for item in _PROFILES.values() if item.probe_bytes()]
