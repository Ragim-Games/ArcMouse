"""Native, dependency-free workflow studio. No browser or web server required."""
from __future__ import annotations

import copy
import json
import multiprocessing as mp
from pathlib import Path
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import __version__, win32
from .model import DEFAULTS, WorkflowError, demo, load, number, ports, validate
from .supervisor import supervisor_main

BG = "#0c111c"
PANEL = "#131b29"
CARD = "#1b2638"
LINE = "#2a374c"
TEXT = "#e7eef9"
MUTED = "#91a1b9"
ACCENT = "#5ee2bd"
BLUE = "#7ba7ff"
RED = "#ff8194"
LABELS = {"start": "시작", "move": "곡선 이동", "click": "마우스 클릭", "wait": "대기",
          "set": "변수 설정", "if": "조건 분기", "repeat": "반복", "script": "Python", "end": "종료"}
COLORS = {"start": ACCENT, "end": MUTED, "move": BLUE, "click": ACCENT,
          "wait": "#f1cb81", "set": "#bba2ff", "if": "#f1cb81", "repeat": BLUE, "script": "#bba2ff"}
FIELDS = {"x": "X 좌표 / 수식", "y": "Y 좌표 / 수식", "duration_ms": "이동 시간 (ms)",
          "noise_px": "좌표 표준편차 (물리 px)", "button": "마우스 버튼", "interval_ms": "클릭 전 간격 (ms)",
          "jitter_ms": "간격 표준편차 (ms)", "ms": "대기 시간 (ms)", "name": "변수 이름",
          "value": "값 / 수식", "condition": "조건식", "count": "반복 횟수 / 수식", "code": "Python 코드"}
PORT_LABELS = {"next": "다음", "true": "참", "false": "거짓", "body": "반복 본문", "done": "반복 완료"}


class Studio:
    def __init__(self, root):
        self.root = root
        root.title(f"ArcMouse · Workflow Studio {__version__}")
        root.configure(bg=BG)
        width, height = min(1420, root.winfo_screenwidth()-60), min(920, root.winfo_screenheight()-80)
        root.geometry(f"{width}x{height}")
        root.minsize(1080, 680)
        self.flow = demo()
        self.path = None
        self.selected = None
        self.editors, self.edge_editors = {}, {}
        self.drag = self.connecting = None
        self.highlight = None
        self.busy, self.ready = False, False
        self.dirty = False
        self.dry = tk.BooleanVar(value=True)
        self.allow_scripts = tk.BooleanVar(value=False)
        self.backend = tk.StringVar(value="software")
        self.coordinates = tk.StringVar(value="dip")
        self.port = tk.StringVar(value="COM3")
        self.device = tk.StringVar(value="")
        self.state = tk.StringVar(value="안전 감시 시작 중")
        self.stats = tk.StringVar(value="0 STEPS    ·    0 CLICKS")
        self.target_text = tk.StringVar()
        self.targets = []
        self.last_supervisor = time.monotonic()
        self.last_heartbeat = 0
        self._style()
        self._layout()
        self.refresh_targets()
        self.draw()
        self.select("move")
        ctx = mp.get_context("spawn")
        self.pipe, child = ctx.Pipe()
        self.supervisor = ctx.Process(target=supervisor_main, args=(child,), name="ArcMouse-Safety")
        self.supervisor.start()
        child.close()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<Control-s>", lambda _: self.save())
        root.bind("<Control-o>", lambda _: self.open())
        root.after(50, self.poll)
        self.log("준비 · 모의 실행은 마우스 입력을 보내지 않습니다. 대상 창을 선택하세요.")

    def _style(self):
        self.root.option_add("*Font", ("Malgun Gothic", 10))
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=CARD, background=LINE, foreground=TEXT,
                        bordercolor=LINE, arrowcolor=TEXT, padding=5)
        style.map("TCombobox", fieldbackground=[("readonly", CARD)], foreground=[("readonly", TEXT)])
        style.configure("Vertical.TScrollbar", background=LINE, troughcolor=BG, bordercolor=BG, arrowcolor=MUTED)
        style.configure("Horizontal.TScrollbar", background=LINE, troughcolor=BG, bordercolor=BG, arrowcolor=MUTED)
        self.root.option_add("*TCombobox*Listbox.background", CARD)
        self.root.option_add("*TCombobox*Listbox.foreground", TEXT)

    def label(self, parent, text="", color=TEXT, size=10, bold=False, **kw):
        return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=color,
                        font=("Malgun Gothic", size, "bold" if bold else "normal"), **kw)

    def button(self, parent, text, command, primary=False, danger=False, **kw):
        return tk.Button(parent, text=text, command=command, relief="flat", bd=0, padx=13, pady=8,
                         bg=ACCENT if primary else ("#382130" if danger else CARD),
                         fg=BG if primary else (RED if danger else TEXT), cursor="hand2",
                         activebackground="#83edd0" if primary else LINE, activeforeground=BG if primary else TEXT,
                         disabledforeground="#58657a", **kw)

    def _layout(self):
        top = tk.Frame(self.root, bg=BG)
        top.pack(fill="x", padx=24, pady=(20, 14))
        self.label(top, "◈", ACCENT, 25, True).pack(side="left", padx=(0, 10))
        branding = tk.Frame(top, bg=BG)
        branding.pack(side="left")
        self.label(branding, "ArcMouse", size=21, bold=True).pack(anchor="w")
        self.label(branding, "WORKFLOW STUDIO   /   0.1", MUTED, 8).pack(anchor="w")
        self.button(top, "■  비상 정지", self.stop, danger=True).pack(side="right", padx=(8, 0))
        self.run_button = self.button(top, "▶  실행", self.run, primary=True)
        self.run_button.pack(side="right", padx=(16, 0))
        self.button(top, "설정", self.settings).pack(side="right", padx=4)
        self.button(top, "저장", self.save).pack(side="right", padx=4)
        self.button(top, "열기", self.open).pack(side="right", padx=4)

        bar = tk.Frame(self.root, bg=PANEL, padx=14, pady=11)
        bar.pack(fill="x", padx=24)
        self.label(bar, "TARGET", MUTED, 8, True).pack(side="left", padx=(0, 12))
        self.target_combo = ttk.Combobox(bar, textvariable=self.target_text, state="readonly", width=48)
        self.target_combo.pack(side="left", fill="x", expand=True)
        self.button(bar, "↻", self.refresh_targets).pack(side="left", padx=8)
        self.dry_check = tk.Checkbutton(bar, text="모의 실행", variable=self.dry, bg=PANEL, fg=ACCENT,
                       activebackground=PANEL, activeforeground=ACCENT, selectcolor=CARD)
        self.dry_check.pack(side="left", padx=12)
        self.label(bar, "STOP  Ctrl + Alt + Shift + K", MUTED, 9).pack(side="right", padx=6)

        status = tk.Frame(self.root, bg=BG)
        status.pack(fill="x", padx=26, pady=12)
        self.label(status, "●", ACCENT).pack(side="left", padx=(0, 8))
        self.label(status, textvariable=self.state, color=MUTED, size=9).pack(side="left")
        self.label(status, textvariable=self.stats, color=MUTED, size=9).pack(side="right")

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=24)
        palette_shell = tk.Frame(body, bg=PANEL, width=155, padx=10, pady=12)
        palette_shell.pack(side="left", fill="y", padx=(0, 12))
        palette_shell.pack_propagate(False)
        self.label(palette_shell, "블록 라이브러리", size=10, bold=True).pack(anchor="w", pady=(0, 4))
        self.label(palette_shell, "클릭 / 드래그 / 스크롤", MUTED, 8).pack(anchor="w", pady=(0, 10))
        self.button(palette_shell, "새 워크플로", self.new).pack(side="bottom", fill="x", pady=(6, 0))
        self.button(palette_shell, "예제 불러오기", self.example).pack(side="bottom", fill="x", pady=(6, 0))
        palette_canvas = tk.Canvas(palette_shell,bg=PANEL,highlightthickness=0)
        palette_scroll = ttk.Scrollbar(palette_shell,orient="vertical",command=palette_canvas.yview)
        palette_scroll.pack(side="right",fill="y")
        palette_canvas.pack(fill="both",expand=True)
        palette_canvas.configure(yscrollcommand=palette_scroll.set)
        palette = tk.Frame(palette_canvas,bg=PANEL)
        palette_id = palette_canvas.create_window(0,0,window=palette,anchor="nw")
        palette.bind("<Configure>",lambda _:palette_canvas.configure(scrollregion=palette_canvas.bbox("all")))
        palette_canvas.bind("<Configure>",lambda e:palette_canvas.itemconfigure(palette_id,width=e.width))
        for kind in ("move", "click", "wait", "set", "if", "repeat", "script", "end", "start"):
            item = self.label(palette, " ● " + LABELS[kind], COLORS[kind], 9, anchor="w", cursor="hand2", pady=7)
            item.configure(bg=CARD)
            item.pack(fill="x", pady=3)
            item.bind("<ButtonRelease-1>", lambda event, k=kind: self.drop_palette(event, k))
            item.bind("<MouseWheel>",lambda e:palette_canvas.yview_scroll(-int(e.delta/120),"units"))

        inspector_shell = tk.Frame(body, bg=PANEL, width=290)
        inspector_shell.pack(side="right", fill="y", padx=(12, 0))
        inspector_shell.pack_propagate(False)
        self.label(inspector_shell, "속성", size=12, bold=True).pack(anchor="w", padx=18, pady=(16, 10))
        self.inspector_canvas = tk.Canvas(inspector_shell, bg=PANEL, highlightthickness=0)
        sb = ttk.Scrollbar(inspector_shell, orient="vertical", command=self.inspector_canvas.yview)
        sb.pack(side="right", fill="y")
        self.inspector_canvas.pack(fill="both", expand=True)
        self.inspector_canvas.configure(yscrollcommand=sb.set)
        self.inspector = tk.Frame(self.inspector_canvas, bg=PANEL, padx=14)
        self.inspector_id = self.inspector_canvas.create_window(0, 0, window=self.inspector, anchor="nw")
        self.inspector.bind("<Configure>", lambda _: self.inspector_canvas.configure(scrollregion=self.inspector_canvas.bbox("all")))
        self.inspector_canvas.bind("<Configure>", lambda e: self.inspector_canvas.itemconfigure(self.inspector_id, width=e.width))

        workspace = tk.Frame(body, bg=BG)
        workspace.pack(fill="both", expand=True)
        heading = tk.Frame(workspace, bg=BG)
        heading.pack(fill="x", pady=(0, 8))
        self.label(heading, "워크플로", size=12, bold=True).pack(side="left")
        self.label(heading, "하단 포트 → 다음 블록으로 연결", MUTED, 8).pack(side="right")
        self.canvas = tk.Canvas(workspace, bg="#0f1623", highlightthickness=1, highlightbackground=LINE)
        vertical = ttk.Scrollbar(workspace, orient="vertical", command=self.canvas.yview)
        horizontal = ttk.Scrollbar(workspace, orient="horizontal", command=self.canvas.xview)
        horizontal.pack(side="bottom", fill="x")
        vertical.pack(side="right", fill="y")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set, scrollregion=(0, 0, 1600, 1400))
        self.canvas.bind("<ButtonPress-1>", self.press)
        self.canvas.bind("<B1-Motion>", self.motion)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        self.canvas.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(-int(e.delta / 120), "units"))
        self.canvas.bind("<Shift-MouseWheel>", lambda e: self.canvas.xview_scroll(-int(e.delta / 120), "units"))
        self.canvas.bind("<ButtonPress-2>", lambda e: self.canvas.scan_mark(e.x, e.y))
        self.canvas.bind("<B2-Motion>", lambda e: self.canvas.scan_dragto(e.x, e.y, gain=1))
        self.canvas.bind("<Delete>", lambda _: self.delete())

        bottom = tk.Frame(self.root, bg=BG)
        bottom.pack(fill="x", padx=24, pady=(12, 16))
        self.label(bottom, "실행 기록", MUTED, 9).pack(anchor="w", pady=(0, 5))
        self.logs = tk.Text(bottom, height=3, bg=PANEL, fg=MUTED, relief="flat", padx=10, pady=7,
                            font=("Consolas", 9), state="disabled", wrap="word")
        self.logs.pack(fill="x")

    def node(self, key):
        return next((n for n in self.flow["nodes"] if n["id"] == key), None)

    def summary(self, node):
        p, k = node["params"], node["type"]
        result = {"move": lambda: f"X {p['x']}   Y {p['y']}  ·  {p['duration_ms']:g} ms",
                  "click": lambda: f"{p['button']}  ·  {p['interval_ms']:g} ± {p['jitter_ms']:g} ms",
                  "wait": lambda: f"{p['ms']:g} ms", "set": lambda: f"{p['name']} = {p['value']}",
                  "if": lambda: p["condition"], "repeat": lambda: f"{p['count']} 회 반복",
                  "script": lambda: "신뢰한 Python 코드", "start": lambda: "워크플로 진입점", "end": lambda: "안전하게 완료"}
        return str(result[k]())[:30]

    def draw(self):
        c = self.canvas
        c.delete("flow")
        if not c.find_withtag("grid"):
            for x in range(20, 1600, 28):
                for y in range(20, 1400, 28):
                    c.create_oval(x, y, x+1, y+1, fill="#263044", outline="", tags="grid")
        for node in self.flow["nodes"]:
            available = ports(node["type"])
            for i, port in enumerate(available):
                target = self.node(node["edges"].get(port))
                if not target:
                    continue
                x1, y1 = node["x"] + 190*(i+1)/(len(available)+1), node["y"]+80
                x2, y2 = target["x"]+95, target["y"]
                if y2 > y1:
                    points = (x1,y1,x1,y1+35,x2,y2-35,x2,y2)
                else:
                    side = max(x1,x2)+135
                    points = (x1,y1,x1,y1+30,side,y1+30,side,y2-35,x2,y2-35,x2,y2)
                c.create_line(*points, fill="#526784", width=2, smooth=True, arrow="last", arrowshape=(9,11,4), tags="flow")
        for node in self.flow["nodes"]:
            key, kind, x, y = node["id"], node["type"], node["x"], node["y"]
            color = COLORS[kind]
            border = ACCENT if key == self.highlight else (BLUE if key == self.selected else LINE)
            tag = f"node:{key}"
            c.create_rectangle(x, y, x+190, y+80, fill=CARD, outline=border, width=2, tags=(tag,"flow"))
            c.create_rectangle(x, y+1, x+4, y+79, fill=color, outline="", tags=(tag,"flow"))
            c.create_text(x+16,y+22,text=LABELS[kind],anchor="w",fill=TEXT,font=("Malgun Gothic",11,"bold"),tags=(tag,"flow"))
            c.create_text(x+16,y+51,text=self.summary(node),anchor="w",fill=MUTED,font=("Malgun Gothic",8),tags=(tag,"flow"))
            c.create_oval(x+90,y-5,x+100,y+5,fill=LINE,outline=BG,tags=(tag,"flow"))
            available = ports(kind)
            for i, port in enumerate(available):
                px, py = x+190*(i+1)/(len(available)+1), y+80
                c.create_oval(px-6,py-6,px+6,py+6,fill=color,outline=BG,width=2,tags=(f"port:{key}:{port}","flow"))
                if len(available) > 1:
                    c.create_text(px,py+15,text=PORT_LABELS[port],fill=MUTED,font=("Malgun Gothic",7),tags="flow")

    def hit(self, x, y):
        for node in reversed(self.flow["nodes"]):
            if node["x"] <= x <= node["x"]+190 and node["y"]-5 <= y <= node["y"]+80:
                return node
        return None

    def press(self, event):
        if self.busy:
            return
        self.canvas.focus_set()
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        items = self.canvas.find_overlapping(x-6,y-6,x+6,y+6)
        for item in reversed(items):
            for tag in self.canvas.gettags(item):
                if tag.startswith("port:"):
                    _, key, port = tag.split(":", 2)
                    self.connecting = (key, port, x, y)
                    return
        node = self.hit(x,y)
        if node and self.select(node["id"]):
            self.drag = (node["id"], x-node["x"], y-node["y"])

    def motion(self, event):
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        if self.connecting:
            self.canvas.delete("wire")
            self.canvas.create_line(self.connecting[2],self.connecting[3],x,y,fill=ACCENT,width=2,dash=(4,3),tags="wire")
        elif self.drag:
            key, dx, dy = self.drag
            node = self.node(key)
            node["x"], node["y"] = max(15,min(1380,x-dx)), max(15,min(1280,y-dy))
            self.dirty = True
            self.draw()

    def release(self, event):
        self.canvas.delete("wire")
        if self.connecting:
            target = self.hit(self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
            key, port, _, _ = self.connecting
            if target:
                self.node(key)["edges"][port] = target["id"]
                self.dirty = True
                self.log(f"연결 · {key}.{port} → {target['id']}")
                if self.selected == key:
                    self.populate_inspector()
            self.connecting = None
        self.drag = None
        self.draw()

    def drop_palette(self, event, kind):
        if self.busy or not self.apply(silent=True):
            return
        if kind == "start" and any(n["type"] == "start" for n in self.flow["nodes"]):
            self.log("시작 노드는 하나만 사용할 수 있습니다.")
            return
        px, py = event.x_root-self.canvas.winfo_rootx(), event.y_root-self.canvas.winfo_rooty()
        if 0 <= px <= self.canvas.winfo_width() and 0 <= py <= self.canvas.winfo_height():
            x,y = self.canvas.canvasx(px), self.canvas.canvasy(py)
        else:
            x,y = self.canvas.canvasx(40), self.canvas.canvasy(40)
        index = 1
        while self.node(f"{kind}{index}"):
            index += 1
        key = f"{kind}{index}"
        self.flow["nodes"].append({"id":key,"type":kind,"x":x,"y":y,"params":copy.deepcopy(DEFAULTS[kind]),"edges":{}})
        self.dirty = True
        self.select(key)

    def select(self, key):
        if self.selected and self.selected != key and not self.apply(silent=True):
            return False
        self.selected = key
        self.populate_inspector()
        self.draw()
        return True

    def populate_inspector(self):
        for child in self.inspector.winfo_children():
            child.destroy()
        self.editors, self.edge_editors = {}, {}
        node = self.node(self.selected)
        if not node:
            self.label(self.inspector, "블록을 선택하세요.", MUTED).pack(anchor="w")
            return
        self.label(self.inspector, LABELS[node["type"]], COLORS[node["type"]], 14, True).pack(anchor="w")
        self.label(self.inspector, node["id"], MUTED, 8).pack(anchor="w", pady=(2,12))
        for name, value in node["params"].items():
            self.label(self.inspector, FIELDS.get(name,name), MUTED, 9).pack(anchor="w", pady=(8,4))
            if name == "code":
                widget = tk.Text(self.inspector,height=10,bg=BG,fg=TEXT,insertbackground=TEXT,relief="flat",wrap="none",font=("Consolas",9))
                widget.insert("1.0",value)
            elif name == "button":
                widget = ttk.Combobox(self.inspector,values=("left","right","middle"),state="readonly")
                widget.set(value)
            else:
                widget = tk.Entry(self.inspector,bg=BG,fg=TEXT,insertbackground=TEXT,relief="flat",borderwidth=0)
                widget.insert(0,str(value))
            widget.pack(fill="x",ipady=5)
            self.editors[name] = widget
        if node["type"] == "move":
            self.button(self.inspector,"3초 후 커서 좌표 가져오기",self.capture).pack(fill="x",pady=(12,0))
        if node["type"] == "repeat":
            self.label(self.inspector,"본문의 마지막 블록을 이 반복 블록에\n다시 연결하세요.",MUTED,8,justify="left").pack(anchor="w",pady=(12,0))
        if node["type"] == "script":
            self.label(self.inspector,"로컬 Python 권한으로 실행됩니다.\n신뢰하는 코드만 설정에서 허용하세요.",RED,8,justify="left").pack(anchor="w",pady=(12,0))
        destinations = [""] + [n["id"] for n in self.flow["nodes"]]
        for port in ports(node["type"]):
            self.label(self.inspector,PORT_LABELS[port]+" →",MUTED,9).pack(anchor="w",pady=(12,4))
            widget = ttk.Combobox(self.inspector,values=destinations,state="readonly")
            widget.set(node["edges"].get(port,""))
            widget.pack(fill="x")
            self.edge_editors[port] = widget
        self.button(self.inspector,"속성 적용",self.apply,primary=True).pack(fill="x",pady=(18,6))
        self.button(self.inspector,"블록 삭제",self.delete,danger=True).pack(fill="x",pady=(0,18))

    def apply(self, silent=False):
        node = self.node(self.selected)
        if not node or self.busy:
            return True
        try:
            params = {}
            numeric = {"duration_ms":(5,60000),"noise_px":(0,100),"interval_ms":(0,60000),
                       "jitter_ms":(0,10000),"ms":(0,3600000)}
            for name, widget in self.editors.items():
                value = widget.get("1.0","end-1c") if isinstance(widget,tk.Text) else widget.get()
                params[name] = number(value,*numeric[name]) if name in numeric else value
            edges = {p:w.get() for p,w in self.edge_editors.items() if w.get()}
            if params != node["params"] or edges != node["edges"]:
                self.dirty = True
                node["params"],node["edges"] = params,edges
            self.draw()
            if not silent:
                self.log("속성을 적용했습니다.")
            return True
        except (ValueError,TypeError) as exc:
            messagebox.showerror("속성 오류",str(exc),parent=self.root)
            return False

    def delete(self):
        if self.busy or not self.selected:
            return
        key = self.selected
        self.flow["nodes"] = [n for n in self.flow["nodes"] if n["id"] != key]
        for n in self.flow["nodes"]:
            n["edges"] = {p:t for p,t in n["edges"].items() if t != key}
        self.selected = None
        self.dirty = True
        self.populate_inspector()
        self.draw()

    def discard(self):
        return not self.dirty or messagebox.askyesno("워크플로 바꾸기","저장하지 않은 변경 내용을 버릴까요?",parent=self.root)

    def new(self):
        if self.busy or not self.discard():
            return
        self.flow = {"version":1,"name":"새 워크플로","nodes":[
            {"id":"start","type":"start","x":80,"y":70,"params":{},"edges":{"next":"end"}},
            {"id":"end","type":"end","x":80,"y":230,"params":{},"edges":{}}]}
        self.reset_document()

    def example(self):
        if not self.busy and self.discard():
            self.flow = demo()
            self.reset_document()

    def reset_document(self):
        self.selected,self.path,self.dirty = None,None,False
        self.allow_scripts.set(False)
        self.populate_inspector()
        self.draw()

    def open(self):
        if self.busy or not self.discard():
            return
        path = filedialog.askopenfilename(filetypes=[("ArcMouse workflow","*.json")],parent=self.root)
        if path:
            try:
                self.flow = load(path)
                self.reset_document()
                self.path = path
                self.log(f"불러옴 · {Path(path).name}")
            except Exception as exc:
                messagebox.showerror("파일 오류",str(exc),parent=self.root)

    def save(self):
        if not self.apply(silent=True):
            return
        path = self.path or filedialog.asksaveasfilename(defaultextension=".json",initialfile="workflow.json",
                 filetypes=[("ArcMouse workflow","*.json")],parent=self.root)
        if path:
            try:
                destination = Path(path)
                temporary = destination.with_suffix(destination.suffix+".tmp")
                temporary.write_text(json.dumps(self.flow,ensure_ascii=False,indent=2),encoding="utf-8")
                temporary.replace(destination)
                self.path,self.dirty = path,False
                self.log(f"저장됨 · {destination.name}")
            except OSError as exc:
                messagebox.showerror("저장 오류",str(exc),parent=self.root)

    def refresh_targets(self):
        if self.busy:
            return
        self.targets = win32.windows()
        self.target_combo["values"] = [f"{t['title'][:65]}  ·  PID {t['pid']}" for t in self.targets]
        self.target_text.set("")

    def target(self):
        index = self.target_combo.current()
        if index < 0 or index >= len(self.targets):
            raise WorkflowError("상단에서 대상 창을 선택하세요.")
        return self.targets[index]

    def capture(self):
        try:
            target = self.target()
        except Exception as exc:
            messagebox.showerror("좌표 가져오기",str(exc),parent=self.root)
            return
        key = self.selected
        self.log("3초 안에 대상 창을 활성화하고 원하는 위치에 커서를 놓으세요.")

        def finish():
            guard = None
            try:
                guard = win32.TargetGuard(target)
                point = win32.cursor()
                guard.check_point(point)
                ox,oy,w,h,scale = guard.geometry()
                x,y = point[0]-ox,point[1]-oy
                if self.coordinates.get() == "ratio":
                    x,y = x/max(1,w-1),y/max(1,h-1)
                else:
                    x,y = x/scale,y/scale
                node = self.node(key)
                if node and not self.busy:
                    node["params"].update(x=f"{x:.4f}",y=f"{y:.4f}")
                    if self.selected == key:
                        self.populate_inspector()
                    self.dirty = True
                    self.draw()
                    self.log(f"좌표 · X {x:.2f}, Y {y:.2f}")
            except Exception as exc:
                self.log(f"좌표 실패 · {exc}")
            finally:
                if guard:
                    guard.close()
        self.root.after(3000,finish)

    def settings(self):
        if self.busy:
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("ArcMouse · 실행 설정")
        dialog.configure(bg=PANEL,padx=24,pady=24)
        dialog.geometry("650x600")
        dialog.transient(self.root)
        self.label(dialog,"실행 설정",size=18,bold=True).pack(anchor="w",pady=(0,18))
        for text,value in (("Windows SendInput · 추가 설치 없음","software"),("USB HID · Leonardo / Pico","hardware")):
            tk.Radiobutton(dialog,text=text,variable=self.backend,value=value,bg=PANEL,fg=TEXT,selectcolor=BG,
                           activebackground=PANEL,activeforeground=TEXT).pack(anchor="w",pady=4)
        self.label(dialog,"MCU 시리얼 포트",MUTED,9).pack(anchor="w",pady=(15,4))
        ttk.Entry(dialog,textvariable=self.port).pack(fill="x")
        self.label(dialog,"사용자 입력 감지에서 제외할 MCU HID 경로",MUTED,9).pack(anchor="w",pady=(12,4))
        device_combo = ttk.Combobox(dialog,textvariable=self.device,values=win32.mouse_devices(),state="readonly")
        device_combo.pack(fill="x")
        self.label(dialog,"MCU 연결 전/후 목록을 비교하세요. 실제 마우스를 선택하면\n그 마우스의 움직임으로 자동 일시정지가 작동하지 않습니다.",RED,9,justify="left").pack(anchor="w",pady=8)
        self.label(dialog,"좌표 체계 (기존 좌표는 자동 변환되지 않습니다)",MUTED,9).pack(anchor="w",pady=(12,4))
        for text,value in (("창 내부 DIP · 96 DPI 기준, 배율 자동 보정","dip"),("창 내부 비율 · X/Y 각각 0~1, 창 크기 변경에 대응","ratio")):
            tk.Radiobutton(dialog,text=text,variable=self.coordinates,value=value,bg=PANEL,fg=TEXT,selectcolor=BG,
                           activebackground=PANEL,activeforeground=TEXT).pack(anchor="w",pady=3)
        tk.Checkbutton(dialog,text="이 세션에서 신뢰하는 Python 스크립트 실행 허용",variable=self.allow_scripts,
                       bg=PANEL,fg=TEXT,selectcolor=BG,activebackground=PANEL,activeforeground=TEXT).pack(anchor="w",pady=(18,3))
        self.label(dialog,"Python은 보안 샌드박스가 아닙니다. 파일/네트워크 접근이 가능하며,\n모의 실행에서도 api 외부 Python 동작은 실제로 실행됩니다.",RED,9,justify="left").pack(anchor="w")
        self.label(dialog,"항상 적용: 5 ms 하한 · 사용자 입력 후 0.5초 대기\n최대 30분 / 100,000 노드 · 포커스/대상 유실 시 중지",MUTED,9,justify="left").pack(anchor="w",pady=15)
        self.button(dialog,"완료",dialog.destroy,primary=True).pack(anchor="e")

    def run(self):
        if self.busy or not self.ready or not self.apply(silent=True):
            return
        try:
            validate(self.flow)
            target = self.target()
            if any(n["type"] == "script" for n in self.flow["nodes"]) and not self.allow_scripts.get():
                raise WorkflowError("Python 블록이 있습니다. 신뢰하는 코드인지 확인한 뒤 설정에서 허용하세요.")
            settings = {"dry_run":self.dry.get(),"allow_scripts":self.allow_scripts.get(),
                        "coordinates":self.coordinates.get(),"backend":self.backend.get(),
                        "port":self.port.get(),"device":self.device.get()}
            self.pipe.send({"type":"start","flow":copy.deepcopy(self.flow),"settings":settings,"target":target})
            self.busy = True
            self.dry_check.configure(state="disabled")
            self.target_combo.configure(state="disabled")
            self.run_button.configure(state="disabled")
            self.log("3초 안에 대상 창으로 전환하세요. " + ("모의 실행" if self.dry.get() else "실제 입력"))
        except Exception as exc:
            messagebox.showerror("실행할 수 없습니다",str(exc),parent=self.root)

    def stop(self):
        try:
            self.pipe.send({"type":"stop"})
        except (EOFError,BrokenPipeError):
            pass

    def log(self, message):
        self.logs.configure(state="normal")
        self.logs.insert("end",time.strftime("%H:%M:%S")+"  "+str(message)+"\n")
        if int(self.logs.index("end-1c").split(".")[0]) > 300:
            self.logs.delete("1.0","80.0")
        self.logs.see("end")
        self.logs.configure(state="disabled")

    def poll(self):
        try:
            now = time.monotonic()
            if now-self.last_heartbeat >= 0.25:
                self.pipe.send({"type":"heartbeat"})
                self.last_heartbeat = now
            for _ in range(64):
                if not self.pipe.poll():
                    break
                event = self.pipe.recv()
                kind = event["type"]
                self.last_supervisor = now
                if kind == "ready":
                    self.ready = True
                    self.state.set("준비 완료 · 안전 감시 활성")
                elif kind == "countdown":
                    self.state.set("3초 후 시작 · 대상 창으로 전환하세요")
                elif kind == "running":
                    self.state.set("실행 중" + (" · 모의 실행" if self.dry.get() else " · 실제 입력"))
                elif kind == "paused":
                    self.state.set(event["reason"])
                elif kind == "progress":
                    self.stats.set(f"{event['steps']:,} STEPS    ·    {event['clicks']:,} CLICKS")
                    if self.highlight != event["node"]:
                        self.highlight = event["node"]
                        self.draw()
                elif kind == "log":
                    self.log(event["message"])
                elif kind in ("completed","stopped","error","fatal"):
                    self.busy = False
                    self.dry_check.configure(state="normal")
                    self.target_combo.configure(state="readonly")
                    self.highlight = None
                    message = event.get("message",event.get("reason","워크플로 완료"))
                    self.state.set(message)
                    self.log(message)
                    self.draw()
                    if kind == "fatal":
                        self.ready = False
                    self.run_button.configure(state="normal" if self.ready else "disabled")
                    if kind in ("error","fatal"):
                        # Non-modal alert: GUI heartbeat must continue while the user reads it.
                        self.alert(message)
                elif kind == "idle":
                    self.busy = False
            if now-self.last_supervisor > 1.5 or not self.supervisor.is_alive():
                self.ready = False
                self.busy = False
                self.run_button.configure(state="disabled")
                self.state.set("안전 감시 연결 유실 · 앱을 다시 실행하세요")
                if self.supervisor.is_alive():
                    self.supervisor.terminate()  # Closing its Job handle kills any active worker.
                return
        except (EOFError,BrokenPipeError,OSError):
            self.ready = False
            self.run_button.configure(state="disabled")
            self.state.set("안전 감시 종료 · 앱을 다시 실행하세요")
            return
        self.root.after(40,self.poll)

    def alert(self,message):
        dialog = tk.Toplevel(self.root)
        dialog.title("ArcMouse · 입력 중단")
        dialog.configure(bg=PANEL,padx=24,pady=24)
        self.label(dialog,"입력을 중단했습니다",RED,14,True).pack(anchor="w")
        self.label(dialog,message,wraplength=450,justify="left").pack(anchor="w",pady=18)
        self.button(dialog,"확인",dialog.destroy).pack(anchor="e")

    def close(self):
        self.stop()
        if not self.discard():
            return
        try:
            self.pipe.send({"type":"shutdown"})
            self.supervisor.join(1)
            if self.supervisor.is_alive():
                self.supervisor.terminate()
                self.supervisor.join(0.5)
        except (EOFError,BrokenPipeError,OSError):
            pass
        self.pipe.close()
        self.root.destroy()


def main():
    win32.dpi_aware()
    root = tk.Tk()
    Studio(root)
    root.mainloop()
