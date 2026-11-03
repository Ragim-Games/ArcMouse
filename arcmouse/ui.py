"""A single-screen auto clicker. No editor, graph, or scripting UI."""
import multiprocessing as mp
import os
import time
import tkinter as tk
from tkinter import ttk

from . import __version__, win32
from .design import BG, WHITE, INK, MUTED, LINE, GREEN, Button, Surface, Toggle, rounded
from .model import DEFAULTS, validate_settings
from .supervisor import supervisor_main

AUTO_TARGET = "시작할 때 활성화된 창"
BUTTONS = {"왼쪽 버튼": "left", "오른쪽 버튼": "right", "가운데 버튼": "middle"}


class AutoClicker:
    def __init__(self, root, *, start_services=True):
        self.root = root
        self.services_started = start_services
        self.busy, self.ready, self.capturing = False, False, False
        self.targets, self.inputs = [], []
        self.extra_dialog = None
        self.target_text = tk.StringVar(value=AUTO_TARGET)
        self.interval = tk.StringVar(value="100")
        self.button_name = tk.StringVar(value="왼쪽 버튼")
        self.repeat_mode = tk.StringVar(value="중지할 때까지")
        self.count = tk.StringVar(value="100")
        self.fixed = tk.BooleanVar(value=False)
        self.x, self.y = tk.StringVar(value="0"), tk.StringVar(value="0")
        self.state = tk.StringVar(value="안전 감시 준비 중…")
        self.clicks = tk.StringVar(value="0회")
        self.extra = dict(DEFAULTS)
        self.last_supervisor = time.monotonic()
        self.last_heartbeat = 0
        self.countdown_until = 0
        root.title(f"ArcMouse {__version__}")
        root.configure(bg=BG)
        root.geometry("600x680")
        root.minsize(570, 670)
        self.style()
        self.layout()
        self.refresh_targets()
        if start_services:
            ctx = mp.get_context("spawn")
            self.pipe, child = ctx.Pipe()
            self.supervisor = ctx.Process(target=supervisor_main, args=(child,), name="ArcMouse-Safety")
            self.supervisor.start()
            child.close()
            root.after(40, self.poll)
        else:
            self.state.set("미리보기 · 실제 입력 꺼짐")
            self.start_button.configure(state="disabled")
        root.protocol("WM_DELETE_WINDOW", self.close)

    def style(self):
        self.root.option_add("*Font", ("Malgun Gothic", 10))
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TEntry", fieldbackground=WHITE, foreground=INK, padding=8,
                        bordercolor=LINE, lightcolor=LINE, darkcolor=LINE, insertcolor=INK)
        style.configure("TCombobox", fieldbackground=WHITE, foreground=INK, background=WHITE,
                        padding=8, bordercolor=LINE, lightcolor=LINE, darkcolor=LINE, arrowcolor=MUTED)
        style.map("TCombobox", fieldbackground=[("readonly", WHITE), ("disabled", BG)],
                  foreground=[("readonly", INK), ("disabled", MUTED)])
        style.map("TEntry", fieldbackground=[("disabled", BG)], foreground=[("disabled", MUTED)])
        self.root.option_add("*TCombobox*Listbox.background", WHITE)
        self.root.option_add("*TCombobox*Listbox.foreground", INK)

    def label(self, parent, text="", size=10, color=INK, bold=False, **kw):
        return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=color, bd=0,
                        font=("Malgun Gothic", size, "bold" if bold else "normal"), **kw)

    def entry(self, parent, variable, width=10):
        widget = ttk.Entry(parent, textvariable=variable, width=width)
        self.inputs.append((widget, "normal"))
        return widget

    def combo(self, parent, variable, values, width=15):
        widget = ttk.Combobox(parent, textvariable=variable, values=values, state="readonly", width=width)
        self.inputs.append((widget, "readonly"))
        return widget

    def layout(self):
        header = tk.Frame(self.root, bg=WHITE, padx=24, pady=10)
        header.pack(fill="x")
        logo = tk.Canvas(header, width=27, height=28, bg=WHITE, highlightthickness=0)
        logo.pack(side="left", padx=(0,8))
        logo.create_line(3,16,10,23,22,7,fill="#42baa0",width=4,capstyle="round",joinstyle="round")
        logo.create_line(3,7,10,14,15,7,fill="#92d8cb",width=4,capstyle="round",joinstyle="round")
        self.label(header,"ArcMouse",18,bold=True).pack(side="left")
        self.extra_button = Button(header,"추가 설정",self.settings,variant="quiet")
        self.extra_button.pack(side="right")
        tk.Frame(self.root,bg=LINE,height=1).pack(fill="x")

        content = tk.Frame(self.root,bg=BG,padx=24,pady=14)
        content.pack(fill="both",expand=True)
        self.label(content,"간단하게, 자동 클릭.",21,bold=True).pack(anchor="w")
        self.label(content,"간격을 정하고 시작을 누르세요.",9,MUTED).pack(anchor="w",pady=(5,12))

        card = Surface(content,height=235,padding=18)
        card.pack(fill="x")
        form = card.body
        self.label(form,"대상 창",9,bold=True).pack(anchor="w",pady=(0,6))
        target_row = tk.Frame(form,bg=WHITE)
        target_row.pack(fill="x",pady=(0,13))
        self.refresh_button = Button(target_row,"↻",self.refresh_targets,width=36,height=36)
        self.refresh_button.pack(side="right",padx=(8,0))
        self.target_combo = self.combo(target_row,self.target_text,(),width=30)
        self.target_combo.pack(fill="x",expand=True)

        row = tk.Frame(form,bg=WHITE)
        row.pack(fill="x",pady=(0,14))
        for col in range(2): row.columnconfigure(col,weight=1,uniform="main")
        interval_box = tk.Frame(row,bg=WHITE)
        interval_box.grid(row=0,column=0,sticky="ew",padx=(0,18))
        self.label(interval_box,"클릭 간격",9,bold=True).pack(anchor="w",pady=(0,6))
        interval_row = tk.Frame(interval_box,bg=WHITE)
        interval_row.pack(fill="x")
        self.label(interval_row,"ms",9,MUTED).pack(side="right",padx=(8,0))
        self.entry(interval_row,self.interval).pack(fill="x",expand=True)
        button_box = tk.Frame(row,bg=WHITE)
        button_box.grid(row=0,column=1,sticky="ew")
        self.label(button_box,"마우스 버튼",9,bold=True).pack(anchor="w",pady=(0,6))
        self.combo(button_box,self.button_name,tuple(BUTTONS)).pack(fill="x")

        row = tk.Frame(form,bg=WHITE)
        row.pack(fill="x")
        self.label(row,"반복",9,bold=True).pack(side="left",padx=(0,18))
        mode = self.combo(row,self.repeat_mode,("중지할 때까지","횟수 지정"),width=15)
        mode.pack(side="left",fill="x",expand=True)
        mode.bind("<<ComboboxSelected>>",lambda _:self.update_count())
        self.count_entry = self.entry(row,self.count,width=6)
        self.count_entry.pack(side="left",padx=(10,6))
        self.label(row,"회",9,MUTED).pack(side="left")
        self.update_count()

        self.location_card = Surface(content,height=65,padding=14)
        self.location_card.pack(fill="x",pady=(12,0))
        location = self.location_card.body
        row = tk.Frame(location,bg=WHITE)
        row.pack(fill="x")
        self.fixed_toggle = Toggle(row,self.fixed,text="위치 지정")
        self.fixed_toggle.pack(side="left")
        self.label(row,"꺼두면 현재 커서 위치를 클릭합니다.",8,MUTED).pack(side="right",pady=8)
        self.position_fields = tk.Frame(location,bg=WHITE)
        self.label(self.position_fields,"X",9,MUTED).pack(side="left",padx=(0,5))
        self.entry(self.position_fields,self.x,width=7).pack(side="left")
        self.label(self.position_fields,"Y",9,MUTED).pack(side="left",padx=(12,5))
        self.entry(self.position_fields,self.y,width=7).pack(side="left")
        self.capture_button = Button(self.position_fields,"위치 가져오기",self.capture,width=128)
        self.capture_button.pack(side="right")
        self.fixed.trace_add("write",lambda *_:self.update_position())

        status = tk.Frame(content,bg=BG)
        status.pack(fill="x",pady=(12,10))
        self.status_label = self.label(status,textvariable=self.state,size=9,color=MUTED,anchor="w",justify="left",wraplength=400)
        self.status_label.pack(side="left",fill="x",expand=True)
        self.label(status,textvariable=self.clicks,size=16,bold=True,color=GREEN).pack(side="right",padx=(10,0))
        actions = tk.Frame(content,bg=BG)
        actions.pack(fill="x")
        self.start_button = Button(actions,"▶  클릭 시작",self.run,variant="primary",height=46)
        self.start_button.pack(side="left",fill="x",expand=True,padx=(0,10))
        self.stop_button = Button(actions,"■  중지",self.stop,variant="danger",width=112,height=46)
        self.stop_button.pack(side="right")
        self.label(content,"3초 안에 클릭할 창으로 전환하세요. 연속 실행은 최대 30분입니다.",8,MUTED).pack(pady=(10,0))
        self.label(content,"비상 정지  F12  /  Ctrl + Alt + Shift + K",9,GREEN,bold=True).pack(pady=(7,0))

    def update_count(self):
        self.count_entry.configure(state="normal" if not self.busy and self.repeat_mode.get()=="횟수 지정" else "disabled")

    def update_position(self):
        if self.fixed.get():
            self.location_card.configure(height=111)
            self.position_fields.pack(fill="x",pady=(9,0))
            if self.root.winfo_height()<700: self.root.geometry("600x710")
        else:
            self.position_fields.pack_forget()
            self.location_card.configure(height=65)

    def refresh_targets(self):
        if self.busy: return
        self.targets = win32.windows()
        self.target_combo["values"] = [AUTO_TARGET]+[f"{t['title'][:48]} · {t['pid']}" for t in self.targets]
        self.target_text.set(AUTO_TARGET)

    def selected_target(self):
        index = self.target_combo.current()
        if index==0: return None
        if index<1 or index>len(self.targets): raise ValueError("대상 창을 선택하세요.")
        return dict(self.targets[index-1])

    def collect_settings(self):
        result = dict(self.extra)
        result.update(interval_ms=self.interval.get(),button=BUTTONS[self.button_name.get()],
                      count=self.count.get() if self.repeat_mode.get()=="횟수 지정" else 0,
                      fixed_position=self.fixed.get(),x=self.x.get() if self.fixed.get() else 0,
                      y=self.y.get() if self.fixed.get() else 0)
        result=validate_settings(result)
        if self.repeat_mode.get()=="횟수 지정" and result["count"]==0:
            raise ValueError("반복 횟수는 1회 이상으로 입력하세요.")
        return result

    def set_busy(self,busy):
        self.busy=busy
        for widget,normal in self.inputs: widget.configure(state="disabled" if busy else normal)
        for widget in (self.fixed_toggle,self.extra_button,self.refresh_button,self.capture_button):
            widget.configure(state="disabled" if busy else "normal")
        self.update_count()
        self.start_button.configure(state="normal" if self.ready and not busy and not self.capturing else "disabled")

    def run(self):
        if not self.services_started or not self.ready or self.busy or self.capturing: return
        try:
            settings=self.collect_settings()
            target=self.selected_target()
            self.pipe.send({"type":"start","settings":settings,"target":target,"client_pid":os.getpid()})
            self.clicks.set("0회")
            self.active_dry=settings["dry_run"]
            self.countdown_until=time.monotonic()+3
            self.set_busy(True)
            self.state.set("3초 후 시작 · 클릭할 창으로 전환하세요")
        except Exception as exc:
            self.state.set(str(exc))

    def stop(self):
        if not self.services_started: return
        try: self.pipe.send({"type":"stop"})
        except (EOFError,BrokenPipeError,OSError): pass

    def capture(self):
        if self.busy or self.capturing: return
        try: selected=self.selected_target()
        except Exception as exc:
            self.state.set(str(exc))
            return
        self.capturing=True
        self.start_button.configure(state="disabled")
        self.capture_button.configure(state="disabled")
        self.state.set("3초 안에 클릭할 위치로 커서를 옮기세요")
        def finish():
            guard=None
            try:
                target=selected or win32.foreground_target(os.getpid())
                guard=win32.TargetGuard(target)
                point=win32.cursor()
                guard.check_point(point)
                ox,oy,w,h,scale=guard.geometry()
                x,y=point[0]-ox,point[1]-oy
                if self.extra["coordinates"]=="ratio": x,y=x/max(1,w-1),y/max(1,h-1)
                else: x,y=x/scale,y/scale
                self.x.set(f"{x:.4f}")
                self.y.set(f"{y:.4f}")
                # Pin the captured coordinates to their actual window.
                match=next((i for i,t in enumerate(self.targets) if t["hwnd"]==target["hwnd"] and t["created"]==target["created"]),None)
                if match is None:
                    target.setdefault("title","선택한 창")
                    self.targets.append(target)
                    self.target_combo["values"]=[AUTO_TARGET]+[f"{t['title'][:48]} · {t['pid']}" for t in self.targets]
                    match=len(self.targets)-1
                self.target_combo.current(match+1)
                self.state.set("위치를 가져왔습니다")
            except Exception as exc: self.state.set(str(exc))
            finally:
                if guard: guard.close()
                self.capturing=False
                self.capture_button.configure(state="normal")
                self.set_busy(False)
        self.root.after(3000,finish)

    def settings(self):
        if self.busy or self.capturing: return
        if self.extra_dialog and self.extra_dialog.winfo_exists():
            self.extra_dialog.lift()
            return
        dialog=tk.Toplevel(self.root)
        self.extra_dialog=dialog
        dialog.title("ArcMouse · 추가 설정")
        dialog.configure(bg=WHITE,padx=24,pady=20)
        dialog.geometry("520x610")
        dialog.transient(self.root)
        dialog.grab_set()
        self.label(dialog,"필요할 때만 설정하세요",16,bold=True).pack(anchor="w",pady=(0,16))
        values={k:tk.StringVar(value=str(self.extra[k])) for k in ("jitter_ms","noise_px","duration_ms","port","device")}
        fields=(("클릭 간격 변동 (ms)","jitter_ms"),("좌표 변동 (px)","noise_px"),("곡선 이동 시간 (ms)","duration_ms"))
        for title,key in fields:
            row=tk.Frame(dialog,bg=WHITE)
            row.pack(fill="x",pady=5)
            self.label(row,title,9).pack(side="left")
            ttk.Entry(row,textvariable=values[key],width=12).pack(side="right")
        self.label(dialog,"좌표 변동·곡선 이동은 위치 지정이 켜졌을 때 적용됩니다.",8,MUTED).pack(anchor="w",pady=(4,12))
        coordinates=tk.StringVar(value="창 기준 좌표" if self.extra["coordinates"]=="dip" else "창 크기 비율 (0~1)")
        ttk.Combobox(dialog,textvariable=coordinates,values=("창 기준 좌표","창 크기 비율 (0~1)"),state="readonly").pack(fill="x")
        self.label(dialog,"좌표 기준을 바꾸면 X/Y를 다시 지정하세요.",8,MUTED).pack(anchor="w",pady=(5,16))
        backend=tk.StringVar(value="일반 마우스 입력" if self.extra["backend"]=="software" else "USB 보드 (Leonardo / Pico)")
        ttk.Combobox(dialog,textvariable=backend,values=("일반 마우스 입력","USB 보드 (Leonardo / Pico)"),state="readonly").pack(fill="x")
        self.label(dialog,"USB 포트 / MCU 장치",9,MUTED).pack(anchor="w",pady=(12,5))
        ttk.Entry(dialog,textvariable=values["port"]).pack(fill="x",pady=(0,6))
        ttk.Combobox(dialog,textvariable=values["device"],values=win32.mouse_devices(),state="readonly").pack(fill="x")
        self.label(dialog,"USB 보드를 쓸 때만 지정하세요. 실제 마우스를 제외하면\n그 마우스의 움직임으로 자동 일시정지가 작동하지 않습니다.",8,"#c64f5e",justify="left").pack(anchor="w",pady=(7,12))
        dry=tk.BooleanVar(value=self.extra["dry_run"])
        Toggle(dialog,dry,text="입력 없이 테스트").pack(anchor="w")
        error=tk.StringVar()
        self.label(dialog,textvariable=error,size=8,color="#c64f5e",wraplength=470).pack(fill="x",pady=5)
        def apply():
            try:
                result={**self.extra,**{k:v.get() for k,v in values.items()},"dry_run":dry.get(),
                        "coordinates":"dip" if coordinates.get()=="창 기준 좌표" else "ratio",
                        "backend":"software" if backend.get()=="일반 마우스 입력" else "hardware"}
                self.extra=validate_settings(result)
                self.state.set("테스트 모드 · 실제 입력 꺼짐" if dry.get() else "대기 중")
                dialog.destroy()
            except Exception as exc: error.set(str(exc))
        Button(dialog,"저장",apply,variant="primary",height=38).pack(fill="x",side="bottom",pady=(8,0))

    def poll(self):
        try:
            now=time.monotonic()
            if now-self.last_heartbeat>=0.25:
                self.pipe.send({"type":"heartbeat"})
                self.last_heartbeat=now
            for _ in range(64):
                if not self.pipe.poll(): break
                event=self.pipe.recv()
                kind=event["type"]
                self.last_supervisor=now
                if kind=="ready":
                    self.ready=True
                    self.state.set("대기 중")
                    self.set_busy(False)
                elif kind=="countdown":
                    self.countdown_until=now+3
                elif kind=="running":
                    self.countdown_until=0
                    self.state.set("테스트 중 · 실제 입력 꺼짐" if self.active_dry else "클릭 중")
                elif kind=="paused":
                    self.countdown_until=0
                    self.state.set("사용자 입력 감지 · 잠시 대기")
                elif kind=="progress": self.clicks.set(f"{event['clicks']:,}회")
                elif kind in ("completed","stopped","error","fatal"):
                    self.countdown_until=0
                    if kind=="fatal": self.ready=False
                    self.state.set(event.get("message",event.get("reason","완료했습니다")))
                    self.set_busy(False)
                    if kind in ("error","fatal"): self.alert(self.state.get())
                elif kind=="idle": self.set_busy(False)
            if self.busy and self.countdown_until>now:
                seconds=max(1,int(self.countdown_until-now+0.999))
                self.state.set(f"{seconds}초 후 시작 · 클릭할 창으로 전환하세요")
            if now-self.last_supervisor>1.5 or not self.supervisor.is_alive():
                self.ready=False
                self.set_busy(False)
                self.state.set("안전 감시 연결이 끊겼습니다. 앱을 다시 실행하세요.")
                if self.supervisor.is_alive(): self.supervisor.terminate()
                return
        except (EOFError,BrokenPipeError,OSError):
            self.ready=False
            self.set_busy(False)
            self.state.set("안전 감시가 종료됐습니다. 앱을 다시 실행하세요.")
            return
        self.root.after(40,self.poll)

    def alert(self,message):
        dialog=tk.Toplevel(self.root)
        dialog.title("ArcMouse · 클릭 중단")
        dialog.configure(bg=WHITE,padx=22,pady=20)
        self.label(dialog,"클릭을 중단했습니다",14,"#c64f5e",True).pack(anchor="w")
        self.label(dialog,message,9,wraplength=380,justify="left").pack(anchor="w",pady=16)
        Button(dialog,"확인",dialog.destroy).pack(anchor="e")

    def close(self):
        if self.services_started:
            try:
                self.pipe.send({"type":"shutdown"})
                self.supervisor.join(1)
                if self.supervisor.is_alive():
                    self.supervisor.terminate()
                    self.supervisor.join(0.5)
            except (EOFError,BrokenPipeError,OSError): pass
            self.pipe.close()
        self.root.destroy()


def main():
    win32.dpi_aware()
    root=tk.Tk()
    AutoClicker(root)
    root.mainloop()
