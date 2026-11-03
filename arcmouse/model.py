"""Validated click settings and bounded movement math. No workflow interpreter."""
import math
import random

MIN_DELAY_MS = 5.0
DEFAULTS = {
    "interval_ms": 100.0, "button": "left", "count": 0,
    "fixed_position": False, "x": 0.0, "y": 0.0,
    "duration_ms": 200.0, "noise_px": 0.0, "jitter_ms": 0.0,
    "coordinates": "dip", "dry_run": False,
    "backend": "software", "port": "COM3", "device": "",
}


class SettingsError(ValueError):
    pass


def number(value, low=-1e9, high=1e9):
    if isinstance(value, bool):
        raise SettingsError("숫자 필드에 true/false를 사용할 수 없습니다.")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise SettingsError(f"올바른 숫자가 아닙니다: {value!r}") from exc
    if not math.isfinite(result) or not low <= result <= high:
        raise SettingsError(f"숫자 범위는 {low:g} ~ {high:g}입니다.")
    return result


def validate_settings(source):
    if not isinstance(source, dict) or set(source)-set(DEFAULTS):
        raise SettingsError("클릭 설정 형식이 올바르지 않습니다.")
    result = {**DEFAULTS, **source}
    for key in ("fixed_position", "dry_run"):
        if type(result[key]) is not bool:
            raise SettingsError(f"{key}: 켜짐/꺼짐 값이 필요합니다.")
    for key, low, high in (
        ("interval_ms", 0, 60_000), ("jitter_ms", 0, 10_000),
        ("duration_ms", 5, 60_000), ("noise_px", 0, 100),
        ("count", 0, 10_000_000), ("x", 0, 100_000), ("y", 0, 100_000),
    ):
        try:
            result[key] = number(result[key], low, high)
        except SettingsError as exc:
            labels={"interval_ms":"클릭 간격", "count":"반복 횟수", "x":"X 좌표", "y":"Y 좌표",
                    "jitter_ms":"간격 변동", "duration_ms":"이동 시간", "noise_px":"좌표 변동"}
            raise SettingsError(f"{labels[key]}: {exc}") from exc
    if result["count"] != int(result["count"]):
        raise SettingsError("반복 횟수는 정수로 입력하세요.")
    result["count"] = int(result["count"])
    result["interval_ms"] = max(MIN_DELAY_MS, result["interval_ms"])
    if result["button"] not in ("left", "right", "middle"):
        raise SettingsError("왼쪽/오른쪽/가운데 버튼을 선택하세요.")
    if result["coordinates"] not in ("dip", "ratio"):
        raise SettingsError("지원하지 않는 좌표 모드입니다.")
    if result["fixed_position"] and result["coordinates"] == "ratio":
        if result["x"] > 1 or result["y"] > 1:
            raise SettingsError("비율 좌표는 0~1로 입력하세요.")
    if result["backend"] not in ("software", "hardware"):
        raise SettingsError("지원하지 않는 입력 방식입니다.")
    if not all(isinstance(result[k], str) for k in ("port", "device")):
        raise SettingsError("장치/포트 이름 형식 오류")
    if result["backend"] == "hardware" and not result["dry_run"]:
        if not result["port"].strip() or not result["device"].strip():
            raise SettingsError("추가 설정에서 USB 포트와 MCU 장치를 선택하세요.")
    return result


def safe_interval(mean, deviation, rng=None):
    rng = rng or random
    mean, deviation = number(mean, 0, 60_000), number(deviation, 0, 10_000)
    # Truncated Gaussian avoids very long tails and always enforces the floor.
    offset = max(-3 * deviation, min(3 * deviation, rng.gauss(0, deviation)))
    return max(MIN_DELAY_MS, mean + offset)


def bezier(start, end, steps=40, bend=0.18):
    x0, y0 = start
    x3, y3 = end
    dx, dy = x3 - x0, y3 - y0
    x1, y1 = x0 + dx / 3 - dy * bend, y0 + dy / 3 + dx * bend
    x2, y2 = x0 + dx * 2 / 3 - dy * bend, y0 + dy * 2 / 3 + dx * bend
    for i in range(1, steps + 1):
        t = i / steps
        t = t * t * (3 - 2 * t)
        u = 1 - t
        yield (u**3*x0 + 3*u*u*t*x1 + 3*u*t*t*x2 + t**3*x3,
               u**3*y0 + 3*u*u*t*y1 + 3*u*t*t*y2 + t**3*y3)
