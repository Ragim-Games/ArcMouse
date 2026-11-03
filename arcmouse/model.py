"""Flat click settings, ordered point actions, and configurable hotkeys."""
import json
import math
from pathlib import Path

MIN_DELAY_MS = 5.0
MAX_ACTIONS = 200
DEFAULTS = {"mode":"cursor", "interval_ms":100.0, "button":"left", "count":0,
            "actions":[], "start_hotkey":"F6", "stop_hotkey":"F7", "dry_run":False,
            "backend":"software", "port":"COM3"}
EMERGENCY = "Ctrl+Alt+Shift+K"


class SettingsError(ValueError):
    pass


def number(value, low=0, high=1e9):
    if isinstance(value,bool): raise SettingsError("숫자를 입력하세요.")
    try: result=float(value)
    except (ValueError,TypeError,OverflowError) as exc: raise SettingsError("숫자를 입력하세요.") from exc
    if not math.isfinite(result) or not low<=result<=high:
        raise SettingsError(f"{low:g}~{high:g} 범위로 입력하세요.")
    return result


def hotkey(value):
    if not isinstance(value,str): raise SettingsError("단축키 형식 오류")
    parts=[p.strip().upper() for p in value.split("+")]
    if not parts or any(not p for p in parts): raise SettingsError("예: F6 또는 Ctrl+Alt+S")
    aliases={"CONTROL":"CTRL","CTL":"CTRL","OPTION":"ALT"}
    mods=[aliases.get(p,p) for p in parts[:-1]]
    if len(set(mods))!=len(mods) or any(m not in ("CTRL","ALT","SHIFT") for m in mods):
        raise SettingsError("Ctrl, Alt, Shift와 키 하나를 조합하세요.")
    key=parts[-1]
    names={"SPACE":32,"ENTER":13,"ESC":27,"ESCAPE":27,"HOME":36,"END":35,"INSERT":45,"DELETE":46,
           "PAGEUP":33,"PAGEDOWN":34}
    if key.startswith("F") and key[1:].isdigit() and 1<=int(key[1:])<=24:
        if int(key[1:])==12: raise SettingsError("F12는 Windows 예약 키입니다. F6/F7 등 다른 키를 선택하세요.")
        vk=111+int(key[1:])
        key=f"F{int(key[1:])}"
    elif len(key)==1 and key.isascii() and key.isalnum():
        if not any(m in mods for m in ("CTRL","ALT")):
            raise SettingsError("문자·숫자 키에는 Ctrl 또는 Alt를 함께 지정하세요.")
        vk=ord(key)
    elif key in names:
        vk=names[key]
        if key=="ESCAPE": key="ESC"
    else: raise SettingsError("지원하는 단축키를 입력하세요. 예: F6, Ctrl+Alt+S")
    flags=sum({"ALT":1,"CTRL":2,"SHIFT":4}[m] for m in mods)
    canonical="+".join([label for token,label in (("CTRL","Ctrl"),("ALT","Alt"),("SHIFT","Shift")) if token in mods]+[key])
    return flags,vk,canonical


def hotkey_pair(start,stop):
    a,b=hotkey(start),hotkey(stop)
    if a[:2]==b[:2]: raise SettingsError("시작과 중단 단축키는 다르게 지정하세요.")
    emergency=hotkey(EMERGENCY)
    if a[:2]==emergency[:2] or b[:2]==emergency[:2]:
        raise SettingsError("Ctrl+Alt+Shift+K는 비상 정지용으로 남겨두세요.")
    return a,b


def action(source):
    if not isinstance(source,dict): raise SettingsError("지점 형식 오류")
    allowed={"type","x","y","end_x","end_y","duration_ms","wait_ms","button"}
    if set(source)-allowed: raise SettingsError("알 수 없는 지점 설정")
    result={"type":"click","duration_ms":500,"wait_ms":100,"button":"left",**source}
    if result["type"] not in ("click","hold","slide"): raise SettingsError("클릭/홀드/슬라이드를 선택하세요.")
    if result["button"] not in ("left","right","middle"): raise SettingsError("마우스 버튼 오류")
    for key in ("x","y")+(("end_x","end_y") if result["type"]=="slide" else ()):
        if key not in result: raise SettingsError("먼저 화면에서 지점을 지정하세요.")
        result[key]=int(round(number(result[key],-100000,100000)))
    result["duration_ms"]=number(result["duration_ms"],5,60000)
    result["wait_ms"]=max(MIN_DELAY_MS,number(result["wait_ms"],0,3600000))
    return result


def validate_settings(source, require_actions=True):
    if not isinstance(source,dict) or set(source)-set(DEFAULTS): raise SettingsError("클릭 설정 형식 오류")
    result={**DEFAULTS,**source}
    result["interval_ms"]=max(MIN_DELAY_MS,number(result["interval_ms"],0,60000))
    count=number(result["count"],0,10000000)
    if int(count)!=count: raise SettingsError("반복 횟수는 정수로 입력하세요.")
    result["count"]=int(count)
    if result["button"] not in ("left","right","middle"): raise SettingsError("마우스 버튼 오류")
    if result["mode"] not in ("cursor","points"): raise SettingsError("모드 오류")
    if type(result["dry_run"]) is not bool: raise SettingsError("테스트 옵션 형식 오류")
    if not isinstance(result["actions"],list) or len(result["actions"])>MAX_ACTIONS:
        raise SettingsError(f"지점은 최대 {MAX_ACTIONS}개입니다.")
    result["actions"]=[action(a) for a in result["actions"]]
    if require_actions and result["mode"]=="points" and not result["actions"]:
        raise SettingsError("실행할 지점을 먼저 추가하세요.")
    a,b=hotkey_pair(result["start_hotkey"],result["stop_hotkey"])
    result["start_hotkey"],result["stop_hotkey"]=a[2],b[2]
    if result["backend"] not in ("software","hardware"): raise SettingsError("입력 방식 오류")
    if not isinstance(result["port"],str) or (result["backend"]=="hardware" and not result["port"].strip()):
        raise SettingsError("USB 포트를 입력하세요.")
    return result


def save_profile(path,settings):
    data={"version":3,"settings":validate_settings(settings,require_actions=False)}
    destination=Path(path)
    temporary=destination.with_suffix(destination.suffix+".tmp")
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    temporary.replace(destination)


def load_profile(path):
    path=Path(path)
    if path.stat().st_size>1_000_000: raise SettingsError("파일은 1 MB 이하여야 합니다.")
    data=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data,dict) or data.get("version")!=3: raise SettingsError("지원하지 않는 설정 파일입니다.")
    return validate_settings(data.get("settings"),require_actions=False)
