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
    if isinstance(value,bool): raise SettingsError("Enter a number.")
    try: result=float(value)
    except (ValueError,TypeError,OverflowError) as exc: raise SettingsError("Enter a number.") from exc
    if not math.isfinite(result) or not low<=result<=high:
        raise SettingsError(f"Enter a value between {low:g} and {high:g}.")
    return result


def hotkey(value):
    if not isinstance(value,str): raise SettingsError("Invalid hotkey format.")
    parts=[p.strip().upper() for p in value.split("+")]
    if not parts or any(not p for p in parts): raise SettingsError("Example: F6 or Ctrl+Alt+S.")
    aliases={"CONTROL":"CTRL","CTL":"CTRL","OPTION":"ALT"}
    mods=[aliases.get(p,p) for p in parts[:-1]]
    if len(set(mods))!=len(mods) or any(m not in ("CTRL","ALT","SHIFT") for m in mods):
        raise SettingsError("Combine Ctrl, Alt, or Shift with one key.")
    key=parts[-1]
    names={"SPACE":32,"ENTER":13,"ESC":27,"ESCAPE":27,"HOME":36,"END":35,"INSERT":45,"DELETE":46,
           "PAGEUP":33,"PAGEDOWN":34}
    if key.startswith("F") and key[1:].isdigit() and 1<=int(key[1:])<=24:
        if int(key[1:])==12: raise SettingsError("F12 is reserved by Windows. Choose another key, such as F6 or F7.")
        vk=111+int(key[1:])
        key=f"F{int(key[1:])}"
    elif len(key)==1 and key.isascii() and key.isalnum():
        if not any(m in mods for m in ("CTRL","ALT")):
            raise SettingsError("Combine letter or number keys with Ctrl or Alt.")
        vk=ord(key)
    elif key in names:
        vk=names[key]
        if key=="ESCAPE": key="ESC"
    else: raise SettingsError("Enter a supported hotkey, such as F6 or Ctrl+Alt+S.")
    flags=sum({"ALT":1,"CTRL":2,"SHIFT":4}[m] for m in mods)
    canonical="+".join([label for token,label in (("CTRL","Ctrl"),("ALT","Alt"),("SHIFT","Shift")) if token in mods]+[key])
    return flags,vk,canonical


def hotkey_pair(start,stop):
    a,b=hotkey(start),hotkey(stop)
    if a[:2]==b[:2]: raise SettingsError("Choose different hotkeys for Start and Stop.")
    emergency=hotkey(EMERGENCY)
    if a[:2]==emergency[:2] or b[:2]==emergency[:2]:
        raise SettingsError("Ctrl+Alt+Shift+K is reserved for emergency stop.")
    return a,b


def action(source):
    if not isinstance(source,dict): raise SettingsError("Invalid point format.")
    allowed={"type","x","y","end_x","end_y","duration_ms","wait_ms","button"}
    if set(source)-allowed: raise SettingsError("Unknown point setting.")
    result={"type":"click","duration_ms":500,"wait_ms":100,"button":"left",**source}
    if result["type"] not in ("click","hold","slide"): raise SettingsError("Choose Click, Hold, or Slide.")
    if result["button"] not in ("left","right","middle"): raise SettingsError("Invalid mouse button.")
    for key in ("x","y")+(("end_x","end_y") if result["type"]=="slide" else ()):
        if key not in result: raise SettingsError("Pick a point on the screen first.")
        result[key]=int(round(number(result[key],-100000,100000)))
    result["duration_ms"]=number(result["duration_ms"],5,60000)
    result["wait_ms"]=max(MIN_DELAY_MS,number(result["wait_ms"],0,3600000))
    return result


def validate_settings(source, require_actions=True):
    if not isinstance(source,dict) or set(source)-set(DEFAULTS): raise SettingsError("Invalid click settings.")
    result={**DEFAULTS,**source}
    result["interval_ms"]=max(MIN_DELAY_MS,number(result["interval_ms"],0,60000))
    count=number(result["count"],0,10000000)
    if int(count)!=count: raise SettingsError("Repeat count must be a whole number.")
    result["count"]=int(count)
    if result["button"] not in ("left","right","middle"): raise SettingsError("Invalid mouse button.")
    if result["mode"] not in ("cursor","points"): raise SettingsError("Invalid mode.")
    if type(result["dry_run"]) is not bool: raise SettingsError("Invalid dry-run option.")
    if not isinstance(result["actions"],list) or len(result["actions"])>MAX_ACTIONS:
        raise SettingsError(f"You can add up to {MAX_ACTIONS} points.")
    result["actions"]=[action(a) for a in result["actions"]]
    if require_actions and result["mode"]=="points" and not result["actions"]:
        raise SettingsError("Add at least one point before starting.")
    a,b=hotkey_pair(result["start_hotkey"],result["stop_hotkey"])
    result["start_hotkey"],result["stop_hotkey"]=a[2],b[2]
    if result["backend"] not in ("software","hardware"): raise SettingsError("Invalid input method.")
    if not isinstance(result["port"],str) or (result["backend"]=="hardware" and not result["port"].strip()):
        raise SettingsError("Enter a USB serial port.")
    return result


def save_profile(path,settings):
    data={"version":3,"settings":validate_settings(settings,require_actions=False)}
    destination=Path(path)
    temporary=destination.with_suffix(destination.suffix+".tmp")
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    temporary.replace(destination)


def load_profile(path):
    path=Path(path)
    if path.stat().st_size>1_000_000: raise SettingsError("The profile must be no larger than 1 MB.")
    data=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data,dict) or data.get("version")!=3: raise SettingsError("Unsupported profile format.")
    return validate_settings(data.get("settings"),require_actions=False)
