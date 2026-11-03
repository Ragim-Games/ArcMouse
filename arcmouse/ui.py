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
from .design import Button, Surface, Toggle, rounded

BG = "#f5f7fa"
PANEL = "#ffffff"
CARD = "#f7f9fb"
LINE = "#e6ebf0"
TEXT = "#243448"
MUTED = "#778596"
ACCENT = "#16856e"
BLUE = "#587dce"
RED = "#c64f5e"
LABELS = {"start": "시작", "move": "곡선 이동", "click": "마우스 클릭", "wait": "대기",
          "set": "변수 설정", "if": "조건 분기", "repeat": "반복", "script": "Python", "end": "종료"}
COLORS = {"start": ACCENT, "end": MUTED, "move": BLUE, "click": ACCENT,
          "wait": "#af8134", "set": "#8b6ac2", "if": "#af8134", "repeat": BLUE, "script": "#8b6ac2"}
TINTS = {"start": "#e9f7f0", "end": "#eef1f5", "move": "#eef3ff", "click": "#e9f7f0",
         "wait": "#fff6e6", "set": "#f3edfc", "if": "#fff6e6", "repeat": "#eef3ff", "script": "#f3edfc"}
ICONS = {"start": "▷", "move": "↗", "click": "⌖", "wait": "◷", "set": "x", "if": "◇", "repeat": "↻", "script": "{ }", "end": "□"}
NODE_W, NODE_H = 206, 90
FIELDS = {"x": "X 좌표 / 수식", "y": "Y 좌표 / 수식", "duration_ms": "이동 시간 (ms)",
          "noise_px": "좌표 표준편차 (물리 px)", "button": "마우스 버튼", "interval_ms": "클릭 전 간격 (ms)",
          "jitter_ms": "간격 표준편차 (ms)", "ms": "대기 시간 (ms)", "name": "변수 이름",
          "value": "값 / 수식", "condition": "조건식", "count": "반복 횟수 / 수식", "code": "Python 코드"}
PORT_LABELS = {"next": "다음", "true": "참", "false": "거짓", "body": "반복 본문", "done": "반복 완료"}


class Studio:
    def __init__(self, root, *, start_services=True):
        self.root = root
        root.title(f"ArcMouse · Workflow Studio {__version__}")
        root.configure(bg=BG)
        width, height = min(1420, root.winfo_screenwidth()-60), min(920, root.winfo_screenheight()-80)
        root.geometry(f"{width}x{height}")
        root.minsize(1100, 660)
        self.flow = demo()
        self.path = None
        self.selected = None
        self.zoom = 1.0
        self.auto_fit = True
        self.fit_pending = None
        self.step_count = tk.StringVar(value="0")
        self.click_count = tk.StringVar(value="0")
        self.block_count = tk.StringVar(value="8")
        self.document_title = tk.StringVar(value=self.flow["name"])
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
        self.services_started = start_services
        if start_services:
            ctx = mp.get_context("spawn")
            self.pipe, child = ctx.Pipe()
            self.supervisor = ctx.Process(target=supervisor_main, args=(child,), name="ArcMouse-Safety")
            self.supervisor.start()
            child.close()
            root.after(50, self.poll)
        else:
            self.state.set("화면 미리보기 · 입력 엔진 비활성")
            self.run_button.configure(state="disabled")
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<Control-s>", lambda _: self.save())
        root.bind("<Control-o>", lambda _: self.open())
        root.after(100, self.fit_view)
        self.log("준비 · 모의 실행은 마우스 입력을 보내지 않습니다. 대상 창을 선택하세요.")

    def _style(self):
        self.root.option_add("*Font", ("Malgun Gothic", 9))
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=PANEL, background=PANEL, foreground=TEXT,
                        bordercolor=LINE, lightcolor=LINE, darkcolor=LINE, arrowcolor=MUTED, padding=7)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL), ("disabled", CARD)],
                  foreground=[("readonly", TEXT), ("disabled", MUTED)],
                  bordercolor=[("focus", ACCENT)])
        style.configure("TEntry", fieldbackground=PANEL, foreground=TEXT, bordercolor=LINE,
                        lightcolor=LINE, darkcolor=LINE, padding=7, insertcolor=TEXT)
        for direction in ("Vertical", "Horizontal"):
            style.configure(f"{direction}.TScrollbar", background="#d8e0e6", troughcolor=BG,
                            bordercolor=BG, lightcolor=BG, darkcolor=BG, arrowcolor=MUTED,
                            arrowsize=10, width=10, gripcount=0)
            style.map(f"{direction}.TScrollbar", background=[("active", "#b9c8d1")])
        self.root.option_add("*TCombobox*Listbox.background", PANEL)
        self.root.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", "#e7f6f0")
        self.root.option_add("*TCombobox*Listbox.selectForeground", ACCENT)

    def label(self, parent, text="", color=TEXT, size=10, bold=False, **kw):
        return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=color, bd=0,
                        font=("Malgun Gothic", size, "bold" if bold else "normal"), **kw)

    def button(self, parent, text, command, primary=False, danger=False, **kw):
        return Button(parent,text,command,variant="primary" if primary else ("danger" if danger else "normal"),**kw)

    def _layout(self):
        sidebar = tk.Frame(self.root,bg=PANEL,width=186)
        sidebar.pack(side="left",fill="y")
        sidebar.pack_propagate(False)
        tk.Frame(self.root,bg=LINE,width=1).pack(side="left",fill="y")
        brand = tk.Frame(sidebar,bg=PANEL)
        brand.pack(fill="x",padx=22,pady=(24,26))
        logo = tk.Canvas(brand,width=27,height=28,bg=PANEL,highlightthickness=0)
        logo.pack(side="left",padx=(0,8))
        logo.create_line(3,16,10,23,22,7,fill="#42baa0",width=4,capstyle="round",joinstyle="round")
        logo.create_line(3,7,10,14,15,7,fill="#92d8cb",width=4,capstyle="round",joinstyle="round")
        self.label(brand,"ArcMouse",size=15,bold=True).pack(side="left")
        nav = tk.Frame(sidebar,bg=PANEL,padx=14)
        nav.pack(fill="x")
        Button(nav,"◈   워크플로 편집기",self.show_editor,variant="selected").pack(fill="x",pady=(0,5))
        Button(nav,"↗   워크플로 열기",self.open,variant="quiet").pack(fill="x",pady=2)
        Button(nav,"⚙   실행 설정",self.settings,variant="quiet").pack(fill="x",pady=2)
        tk.Frame(sidebar,bg=LINE,height=1).pack(fill="x",padx=22,pady=(17,14))
        self.label(sidebar,"블록 라이브러리",MUTED,8,bold=True).pack(anchor="w",padx=24)
        self.label(sidebar,"끌어서 흐름에 추가하세요",MUTED,8).pack(anchor="w",padx=24,pady=(5,10))

        sidebar_bottom = tk.Frame(sidebar,bg=PANEL,padx=14,pady=14)
        sidebar_bottom.pack(side="bottom",fill="x")
        self.button(sidebar_bottom,"＋  새 워크플로",self.new).pack(fill="x",pady=(0,7))
        Button(sidebar_bottom,"예제 불러오기",self.example,variant="quiet",height=30).pack(fill="x")
        self.label(sidebar_bottom,"LOCAL WORKSPACE  ·  0.1",MUTED,7).pack(pady=(16,0))

        palette_shell = tk.Frame(sidebar,bg=PANEL,padx=14)
        palette_shell.pack(fill="both",expand=True)
        palette_canvas = tk.Canvas(palette_shell,bg=PANEL,highlightthickness=0)
        palette_scroll = ttk.Scrollbar(palette_shell,orient="vertical",command=palette_canvas.yview)
        palette_scroll.pack(side="right",fill="y")
        palette_canvas.pack(fill="both",expand=True)
        palette_canvas.configure(yscrollcommand=palette_scroll.set)
        palette = tk.Frame(palette_canvas,bg=PANEL)
        palette_id = palette_canvas.create_window(0,0,window=palette,anchor="nw")
        palette.bind("<Configure>",lambda _:palette_canvas.configure(scrollregion=palette_canvas.bbox("all")))
        palette_canvas.bind("<Configure>",lambda e:palette_canvas.itemconfigure(palette_id,width=e.width))
        for kind in ("move","click","wait","set","if","repeat","script","start","end"):
            item = tk.Canvas(palette,height=37,bg=PANEL,highlightthickness=0,cursor="hand2")
            item.pack(fill="x",pady=2)
            rounded(item,4,5,31,32,7,fill=TINTS[kind],outline="")
            item.create_text(18,18,text=ICONS[kind],fill=COLORS[kind],font=("Segoe UI",12))
            item.create_text(43,18,text=LABELS[kind],fill=TEXT,anchor="w",font=("Malgun Gothic",9))
            item.bind("<Enter>",lambda e:e.widget.configure(bg=CARD))
            item.bind("<Leave>",lambda e:e.widget.configure(bg=PANEL))
            item.bind("<ButtonRelease-1>",lambda event,k=kind:self.drop_palette(event,k))
            item.bind("<MouseWheel>",lambda e:palette_canvas.yview_scroll(-int(e.delta/120),"units"))

        page = tk.Frame(self.root,bg=BG)
        page.pack(fill="both",expand=True)
        header = tk.Frame(page,bg=PANEL,height=65,padx=24)
        header.pack(fill="x")
        header.pack_propagate(False)
        self.label(header,"워크스페이스",MUTED,9).pack(side="left")
        self.label(header,"  /  ","#c0c9d2",10).pack(side="left")
        self.label(header,"편집기",TEXT,9,bold=True).pack(side="left")
        self.button(header,"■  중지",self.stop,danger=True,width=82).pack(side="right",pady=14)
        self.run_button = self.button(header,"▶  실행",self.run,primary=True,width=96)
        self.run_button.pack(side="right",padx=(12,8),pady=14)
        self.button(header,"저장",self.save,width=66).pack(side="right",pady=14)
        tk.Frame(page,bg=LINE,height=1).pack(fill="x")

        footer = tk.Frame(page,bg=BG,height=30,padx=24)
        footer.pack(side="bottom",fill="x")
        footer.pack_propagate(False)
        self.label(footer,"●",ACCENT,8).pack(side="left",padx=(0,6))
        self.label(footer,textvariable=self.state,color=MUTED,size=8).pack(side="left")
        self.label(footer,"비상 정지   Ctrl + Alt + Shift + K",MUTED,8).pack(side="right")

        content = tk.Frame(page,bg=BG,padx=22)
        content.pack(fill="both",expand=True)
        title_row = tk.Frame(content,bg=BG)
        title_row.pack(fill="x",pady=(20,14))
        title_left = tk.Frame(title_row,bg=BG)
        title_left.pack(side="left")
        self.label(title_left,"워크플로 스튜디오",size=21,bold=True).pack(anchor="w")
        self.label(title_left,"반복하는 작업을, 나만의 흐름으로.",MUTED,9).pack(anchor="w",pady=(4,0))
        badge = tk.Frame(title_row,bg="#e7f6f0",padx=12,pady=6)
        badge.pack(side="right",anchor="center")
        self.label(badge,"●  로컬 워크스페이스",ACCENT,8).pack()

        metrics = tk.Frame(content,bg=BG)
        metrics.pack(fill="x",pady=(0,12))
        for column,(title,variable,note,tint,symbol) in enumerate((
            ("워크플로 블록",self.block_count,"개의 블록", "#eef3ff","◇"),
            ("실행한 단계",self.step_count,"이번 세션", "#f3edfc","↗"),
            ("마우스 클릭",self.click_count,"이번 세션", "#e9f7f0","⌖"))):
            metrics.columnconfigure(column,weight=1,uniform="metric")
            surface = Surface(metrics,height=83,padding=15)
            surface.grid(row=0,column=column,sticky="ew",padx=(0,10) if column<2 else 0)
            row = tk.Frame(surface.body,bg=PANEL)
            row.pack(fill="x")
            self.label(row,title,MUTED,8).pack(side="left")
            self.label(row,symbol,ACCENT,12).pack(side="right")
            row = tk.Frame(surface.body,bg=PANEL)
            row.pack(fill="x",pady=(4,0))
            self.label(row,textvariable=variable,size=20,bold=True).pack(side="left")
            self.label(row,note,MUTED,8).pack(side="left",padx=9,pady=(9,0))

        target_card = Surface(content,height=63,padding=12)
        target_card.pack(fill="x",pady=(0,12))
        def responsive(event):
            if event.widget is not self.root: return
            compact=event.height<800
            if compact and metrics.winfo_manager(): metrics.pack_forget()
            elif not compact and not metrics.winfo_manager(): metrics.pack(fill="x",pady=(0,12),before=target_card)
        self.root.bind("<Configure>",responsive,add="+")
        bar = target_card.body
        self.label(bar,"대상 창",TEXT,9,bold=True).pack(side="left",padx=(6,12))
        self.dry_check = Toggle(bar,self.dry)
        self.dry_check.pack(side="right",padx=(12,2))
        self.button(bar,"↻",self.refresh_targets,width=36).pack(side="right",padx=(8,0))
        self.target_combo = ttk.Combobox(bar,textvariable=self.target_text,state="readonly",width=24)
        self.target_combo.pack(side="left",fill="x",expand=True,pady=1)

        body = tk.Frame(content,bg=BG)
        body.pack(fill="both",expand=True)
        inspector_surface = Surface(body,width=278,padding=14)
        inspector_surface.pack(side="right",fill="y",padx=(12,0))
        self.inspector_shell = inspector_surface.body
        inspector_header = tk.Frame(self.inspector_shell,bg=PANEL)
        inspector_header.pack(fill="x",pady=(2,12))
        self.label(inspector_header,"블록 속성",size=10,bold=True).pack(side="left")
        self.label(inspector_header,"편집",MUTED,8).pack(side="right")
        tk.Frame(self.inspector_shell,bg=LINE,height=1).pack(fill="x",pady=(0,14))
        inspector_actions = tk.Frame(self.inspector_shell,bg=PANEL)
        inspector_actions.pack(side="bottom",fill="x",pady=(10,0))
        self.button(inspector_actions,"적용",self.apply,primary=True,width=140).pack(side="left",fill="x",expand=True)
        self.button(inspector_actions,"삭제",self.delete,danger=True,width=58).pack(side="right",padx=(7,0))
        self.inspector_canvas = tk.Canvas(self.inspector_shell,bg=PANEL,highlightthickness=0)
        sb = ttk.Scrollbar(self.inspector_shell,orient="vertical",command=self.inspector_canvas.yview)
        sb.pack(side="right",fill="y")
        self.inspector_canvas.pack(fill="both",expand=True)
        self.inspector_canvas.configure(yscrollcommand=sb.set)
        self.inspector = tk.Frame(self.inspector_canvas,bg=PANEL,padx=2)
        self.inspector_id = self.inspector_canvas.create_window(0,0,window=self.inspector,anchor="nw")
        self.inspector.bind("<Configure>",lambda _:self.inspector_canvas.configure(scrollregion=self.inspector_canvas.bbox("all")))
        self.inspector_canvas.bind("<Configure>",lambda e:self.inspector_canvas.itemconfigure(self.inspector_id,width=e.width))

        workspace = Surface(body,padding=12)
        workspace.pack(fill="both",expand=True)
        heading = tk.Frame(workspace.body,bg=PANEL)
        heading.pack(fill="x",pady=(0,10))
        self.label(heading,textvariable=self.document_title,size=10,bold=True).pack(side="left",padx=5)
        self.button(heading,"맞춤",self.fit_view,width=48,height=29).pack(side="right")
        self.button(heading,"＋",lambda:self.zoom_view(1.15),width=28,height=29).pack(side="right",padx=3)
        self.zoom_label = self.label(heading,"100%",MUTED,8,width=5)
        self.zoom_label.pack(side="right")
        self.button(heading,"−",lambda:self.zoom_view(1/1.15),width=28,height=29).pack(side="right",padx=3)
        self.label(workspace.body,"블록을 연결해 흐름을 만드세요.  ·  색상 포트 → 다음 블록",MUTED,8).pack(anchor="w",padx=5,pady=(0,8))
        canvas_shell = tk.Frame(workspace.body,bg=CARD)
        canvas_shell.pack(fill="both",expand=True)
        self.canvas = tk.Canvas(canvas_shell,bg="#fafcfd",highlightthickness=0)
        vertical = ttk.Scrollbar(canvas_shell,orient="vertical",command=self.canvas.yview)
        horizontal = ttk.Scrollbar(canvas_shell,orient="horizontal",command=self.canvas.xview)
        horizontal.pack(side="bottom",fill="x")
        vertical.pack(side="right",fill="y")
        self.canvas.pack(fill="both",expand=True)
        self.canvas.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set,scrollregion=(0,0,1600,1400))
        self.canvas.bind("<ButtonPress-1>",self.press)
        self.canvas.bind("<B1-Motion>",self.motion)
        self.canvas.bind("<ButtonRelease-1>",self.release)
        self.canvas.bind("<MouseWheel>",lambda e:self.canvas.yview_scroll(-int(e.delta/120),"units"))
        self.canvas.bind("<Shift-MouseWheel>",lambda e:self.canvas.xview_scroll(-int(e.delta/120),"units"))
        self.canvas.bind("<Control-MouseWheel>",lambda e:self.zoom_view(1.1 if e.delta>0 else 1/1.1))
        self.canvas.bind("<ButtonPress-2>",lambda e:self.canvas.scan_mark(e.x,e.y))
        self.canvas.bind("<B2-Motion>",lambda e:self.canvas.scan_dragto(e.x,e.y,gain=1))
        self.canvas.bind("<Delete>",lambda _:self.delete())
        self.canvas.bind("<Configure>",self.schedule_fit)

        log_surface = Surface(content,height=71,padding=12)
        log_surface.pack(fill="x",pady=(12,0))
        self.label(log_surface.body,"실행 기록",size=8,bold=True).pack(side="left",anchor="n",padx=(2,18),pady=2)
        self.logs = tk.Text(log_surface.body,height=2,bg=PANEL,fg=MUTED,relief="flat",bd=0,
                            font=("Malgun Gothic",8),state="disabled",wrap="word",highlightthickness=0)
        self.logs.pack(fill="both",expand=True)

    def show_editor(self):
        self.canvas.focus_set()

    def zoom_view(self, factor):
        self.auto_fit=False
        old=self.zoom
        cx=(self.canvas.canvasx(0)+self.canvas.winfo_width()/2)/old
        cy=(self.canvas.canvasy(0)+self.canvas.winfo_height()/2)/old
        self.zoom=max(0.4,min(1.6,self.zoom*factor))
        self.canvas.delete("grid")
        self.draw()
        self.canvas.xview_moveto(max(0,cx*self.zoom-self.canvas.winfo_width()/2)/(1600*self.zoom))
        self.canvas.yview_moveto(max(0,cy*self.zoom-self.canvas.winfo_height()/2)/(1400*self.zoom))

    def fit_view(self):
        if not self.flow["nodes"]: return
        self.auto_fit=True
        width=max(n["x"]+NODE_W+70 for n in self.flow["nodes"])
        height=max(n["y"]+NODE_H+40 for n in self.flow["nodes"])
        self.zoom=max(0.4,min(1.1,self.canvas.winfo_width()/width,self.canvas.winfo_height()/height))
        self.canvas.delete("grid")
        self.draw()
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)

    def schedule_fit(self,event=None):
        if self.auto_fit:
            if self.fit_pending is not None:
                self.root.after_cancel(self.fit_pending)
            self.fit_pending=self.root.after(150,self.fit_view)

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
        c=self.canvas
        c.delete("flow")
        self.block_count.set(str(len(self.flow["nodes"])))
        self.document_title.set(self.flow.get("name","워크플로"))
        self.zoom_label.configure(text=f"{round(self.zoom*100)}%")
        c.configure(scrollregion=(0,0,1600*self.zoom,1400*self.zoom))
        if not c.find_withtag("grid"):
            spacing=max(18,int(30*self.zoom))
            for x in range(15,int(1600*self.zoom),spacing):
                for y in range(15,int(1400*self.zoom),spacing):
                    c.create_oval(x,y,x+1,y+1,fill="#dfe7ec",outline="",tags="grid")
        by_id={n["id"]:n for n in self.flow["nodes"]}
        incoming={key:[] for key in by_id}
        for node in self.flow["nodes"]:
            for port in ports(node["type"]):
                target=by_id.get(node["edges"].get(port))
                if not target: continue
                x1,y1=self.port_point(node,port)
                if abs(target["y"]-node["y"])<4:
                    x2=target["x"] if target["x"]>node["x"] else target["x"]+NODE_W
                    y2=target["y"]+NODE_H/2
                    points=(x1,y1,x2,y2)
                else:
                    x2=target["x"]+NODE_W/2
                    y2=target["y"] if target["y"]>node["y"] else target["y"]+NODE_H
                    mid=(y1+y2)/2
                    # Small rounded elbows in the whitespace between rows.
                    points=(x1,y1,x1,mid,x2,mid,x2,y2)
                incoming[target["id"]].append((x2,y2))
                color="#70b8a8" if node["id"]==self.highlight else "#bdcdd6"
                c.create_line(*points,fill=color,width=1.5,smooth=True,splinesteps=24,
                              arrow="last",arrowshape=(7,8,3),tags="flow")
        for node in self.flow["nodes"]:
            key,kind,x,y=node["id"],node["type"],node["x"],node["y"]
            color=COLORS[kind]
            selected=key==self.selected
            active=key==self.highlight
            tag=(f"node:{key}","flow")
            if selected or active:
                rounded(c,x-4,y-4,x+NODE_W+4,y+NODE_H+4,15,fill="#e1f3ed",outline="",tags=tag)
            rounded(c,x,y+3,x+NODE_W,y+NODE_H+3,12,fill="#e8edf1",outline="",tags=tag)
            rounded(c,x,y,x+NODE_W,y+NODE_H,12,fill=PANEL,
                    outline=ACCENT if selected or active else "#dfe7ed",width=1.5 if selected or active else 1,tags=tag)
            rounded(c,x+14,y+13,x+44,y+43,8,fill=TINTS[kind],outline="",tags=tag)
            c.create_text(x+29,y+28,text=ICONS[kind],fill=color,font=("Segoe UI",max(8,round(14*self.zoom))),tags=tag)
            c.create_text(x+55,y+28,text=LABELS[kind],anchor="w",fill=TEXT,
                          font=("Malgun Gothic",max(8,round(11*self.zoom)),"bold"),tags=tag)
            c.create_text(x+NODE_W-19,y+25,text="⋮",fill="#b1bcc7",font=("Segoe UI",max(8,round(12*self.zoom))),tags=tag)
            c.create_text(x+16,y+65,text=self.summary(node),anchor="w",fill=MUTED,
                          font=("Malgun Gothic",max(7,round(9*self.zoom))),tags=tag)
            for ix,iy in incoming[key]:
                c.create_oval(ix-4,iy-4,ix+4,iy+4,fill=PANEL,outline="#c6d4dc",width=1.5,tags=tag)
            available=ports(kind)
            for i,port in enumerate(available):
                px,py=self.port_point(node,port)
                c.create_oval(px-5,py-5,px+5,py+5,fill=PANEL,outline=color,width=1.7,
                              tags=(f"port:{key}:{port}","flow"))
                if len(available)>1:
                    label_x=px+36 if px==x+NODE_W else px
                    label_y=py-14 if px==x+NODE_W else py+16
                    short_label={"body":"본문","done":"완료","true":"참","false":"거짓"}[port]
                    c.create_text(label_x,label_y,text=short_label,fill=MUTED,
                                  font=("Malgun Gothic",max(7,round(8*self.zoom))),tags="flow")
        c.scale("flow",0,0,self.zoom,self.zoom)

    def port_point(self,node,port):
        target=self.node(node["edges"].get(port))
        available=ports(node["type"])
        x=node["x"]+NODE_W*(available.index(port)+1)/(len(available)+1)
        y=node["y"]+NODE_H
        if target:
            if abs(target["y"]-node["y"])<4:
                x=node["x"]+NODE_W if target["x"]>node["x"] else node["x"]
                y=node["y"]+NODE_H/2
            elif target["y"]<node["y"]:
                y=node["y"]
        return x,y

    def hit(self, x, y):
        for node in reversed(self.flow["nodes"]):
            if node["x"] <= x <= node["x"]+NODE_W and node["y"]-5 <= y <= node["y"]+NODE_H:
                return node
        return None

    def press(self, event):
        if self.busy:
            return
        self.canvas.focus_set()
        x, y = self.canvas.canvasx(event.x)/self.zoom, self.canvas.canvasy(event.y)/self.zoom
        items = self.canvas.find_overlapping(x*self.zoom-7,y*self.zoom-7,x*self.zoom+7,y*self.zoom+7)
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
        x, y = self.canvas.canvasx(event.x)/self.zoom, self.canvas.canvasy(event.y)/self.zoom
        if self.connecting:
            self.canvas.delete("wire")
            self.canvas.create_line(self.connecting[2]*self.zoom,self.connecting[3]*self.zoom,x*self.zoom,y*self.zoom,fill=ACCENT,width=2,dash=(4,3),tags="wire")
        elif self.drag:
            key, dx, dy = self.drag
            node = self.node(key)
            node["x"], node["y"] = max(15,min(1380,x-dx)), max(15,min(1280,y-dy))
            self.dirty = True
            self.draw()

    def release(self, event):
        self.canvas.delete("wire")
        if self.connecting:
            target = self.hit(self.canvas.canvasx(event.x)/self.zoom, self.canvas.canvasy(event.y)/self.zoom)
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
            x,y = self.canvas.canvasx(px)/self.zoom, self.canvas.canvasy(py)/self.zoom
        else:
            x,y = self.canvas.canvasx(40)/self.zoom, self.canvas.canvasy(40)/self.zoom
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
        for child in self.inspector.winfo_children(): child.destroy()
        self.editors,self.edge_editors={},{}
        self.inspector_canvas.yview_moveto(0)
        node=self.node(self.selected)
        if not node:
            self.label(self.inspector,"편집할 블록을 선택하세요.",MUTED,9).pack(anchor="w",pady=10)
            return
        kind=node["type"]
        title=tk.Frame(self.inspector,bg=PANEL)
        title.pack(fill="x",pady=(0,5))
        icon=tk.Canvas(title,width=40,height=40,bg=PANEL,highlightthickness=0)
        icon.pack(side="left",padx=(0,10))
        rounded(icon,1,1,39,39,10,fill=TINTS[kind],outline="")
        icon.create_text(20,20,text=ICONS[kind],fill=COLORS[kind],font=("Segoe UI",18))
        self.label(title,LABELS[kind],size=14,bold=True).pack(side="left")
        descriptions={"move":"자연스러운 곡선으로 커서를 이동합니다.","click":"지정한 간격으로 마우스를 클릭합니다.",
                      "wait":"다음 동작 전 잠시 기다립니다.","set":"값을 저장하고 다음 단계에서 사용합니다.",
                      "if":"조건에 따라 두 경로로 나눕니다.","repeat":"정한 횟수만큼 본문을 반복합니다.",
                      "script":"Python으로 흐름을 확장합니다.","start":"워크플로가 시작되는 지점입니다.","end":"모든 작업을 마칩니다."}
        self.label(self.inspector,descriptions[kind],MUTED,8,wraplength=220,justify="left").pack(anchor="w",pady=(3,16))

        def field(parent,name,value):
            self.label(parent,FIELDS.get(name,name),MUTED,8).pack(anchor="w",pady=(0,6))
            if name=="code":
                widget=tk.Text(parent,height=9,bg=CARD,fg=TEXT,insertbackground=TEXT,relief="flat",wrap="none",
                               highlightthickness=1,highlightbackground=LINE,highlightcolor=ACCENT,
                               padx=8,pady=8,font=("Consolas",9))
                widget.insert("1.0",value)
            elif name=="button":
                widget=ttk.Combobox(parent,values=("left","right","middle"),state="readonly",width=12)
                widget.set(value)
            else:
                widget=ttk.Entry(parent,width=8)
                widget.insert(0,str(value))
            widget.pack(fill="x")
            self.editors[name]=widget

        if kind=="move":
            row=tk.Frame(self.inspector,bg=PANEL)
            row.pack(fill="x",pady=(0,12))
            for i,name in enumerate(("x","y")):
                row.columnconfigure(i,weight=1,uniform="coordinates")
                cell=tk.Frame(row,bg=PANEL)
                cell.grid(row=0,column=i,sticky="ew",padx=(0,8) if i==0 else 0)
                field(cell,name,node["params"][name])
        for name,value in node["params"].items():
            if kind=="move" and name in ("x","y"): continue
            cell=tk.Frame(self.inspector,bg=PANEL)
            cell.pack(fill="x",pady=(0,12))
            field(cell,name,value)
        if kind=="move":
            self.button(self.inspector,"⌖  커서 좌표 가져오기",self.capture,height=34).pack(fill="x",pady=(0,5))
            self.label(self.inspector,"누른 뒤 3초 안에 위치를 지정하세요.",MUTED,8).pack(anchor="w",pady=(0,10))
        if kind=="repeat":
            self.label(self.inspector,"본문의 마지막 블록을 이 반복 블록에\n다시 연결하세요.",MUTED,8,justify="left").pack(anchor="w",pady=(0,10))
        if kind=="script":
            self.label(self.inspector,"신뢰하는 코드만 설정에서 허용하세요.\nPython은 로컬 사용자 권한으로 실행됩니다.",RED,8,justify="left").pack(anchor="w",pady=(0,10))
        if ports(kind):
            tk.Frame(self.inspector,bg=LINE,height=1).pack(fill="x",pady=(6,12))
            self.label(self.inspector,"다음 흐름",size=9,bold=True).pack(anchor="w",pady=(0,10))
        destinations=[""]+[n["id"] for n in self.flow["nodes"]]
        for port in ports(kind):
            self.label(self.inspector,PORT_LABELS[port]+" →",MUTED,8).pack(anchor="w",pady=(0,5))
            widget=ttk.Combobox(self.inspector,values=destinations,state="readonly",width=12)
            widget.set(node["edges"].get(port,""))
            widget.pack(fill="x",pady=(0,12))
            self.edge_editors[port]=widget
        # Scroll the panel even when the pointer is over an Entry or label.
        def bind_scroll(widget):
            widget.bind("<MouseWheel>",self.scroll_inspector)
            for child in widget.winfo_children(): bind_scroll(child)
        bind_scroll(self.inspector)

    def scroll_inspector(self,event):
        self.inspector_canvas.yview_scroll(-int(event.delta/120),"units")
        return "break"

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
        self.root.after_idle(self.fit_view)

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
        self.target_text.set("실행할 프로그램 창을 선택하세요")

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
        if self.busy: return
        dialog=tk.Toplevel(self.root)
        dialog.title("ArcMouse · 실행 설정")
        dialog.configure(bg=BG)
        dialog.geometry("650x660")
        dialog.minsize(560,500)
        dialog.transient(self.root)
        heading=tk.Frame(dialog,bg=PANEL,padx=24,pady=20)
        heading.pack(fill="x")
        self.label(heading,"실행 설정",size=18,bold=True).pack(anchor="w")
        self.label(heading,"입력 방식과 워크플로 실행 환경을 설정하세요.",MUTED,9).pack(anchor="w",pady=(4,0))
        footer=tk.Frame(dialog,bg=PANEL,padx=24,pady=14)
        footer.pack(side="bottom",fill="x")
        self.button(footer,"완료",dialog.destroy,primary=True,width=100).pack(side="right")
        self.label(footer,"최소 5 ms 지연 · 사용자 입력 시 0.5초 양보",MUTED,8).pack(side="left")
        scroll=tk.Canvas(dialog,bg=BG,highlightthickness=0)
        scrollbar=ttk.Scrollbar(dialog,orient="vertical",command=scroll.yview)
        scrollbar.pack(side="right",fill="y")
        scroll.pack(fill="both",expand=True)
        scroll.configure(yscrollcommand=scrollbar.set)
        body=tk.Frame(scroll,bg=BG,padx=24,pady=18)
        window=scroll.create_window(0,0,window=body,anchor="nw")
        body.bind("<Configure>",lambda _:scroll.configure(scrollregion=scroll.bbox("all")))
        scroll.bind("<Configure>",lambda e:scroll.itemconfigure(window,width=e.width))

        def section(title,description):
            frame=tk.Frame(body,bg=PANEL,padx=18,pady=16,highlightbackground=LINE,highlightthickness=1)
            frame.pack(fill="x",pady=(0,14))
            self.label(frame,title,size=11,bold=True).pack(anchor="w")
            self.label(frame,description,MUTED,8,wraplength=510,justify="left").pack(anchor="w",pady=(5,12))
            return frame

        def radio(frame,text,variable,value):
            tk.Radiobutton(frame,text=text,variable=variable,value=value,bg=PANEL,fg=TEXT,
                selectcolor="#e7f6f0",activebackground=PANEL,activeforeground=ACCENT,
                anchor="w",highlightthickness=0,pady=5).pack(fill="x")

        frame=section("입력 방식","추가 장치 없이 시작하거나, 연결한 USB 보드를 사용할 수 있습니다.")
        radio(frame,"Windows 마우스 입력",self.backend,"software")
        radio(frame,"USB HID · Leonardo / Pico",self.backend,"hardware")
        self.label(frame,"MCU 시리얼 포트",MUTED,8).pack(anchor="w",pady=(12,6))
        ttk.Entry(frame,textvariable=self.port).pack(fill="x")
        self.label(frame,"입력 감지에서 제외할 MCU 장치",MUTED,8).pack(anchor="w",pady=(12,6))
        ttk.Combobox(frame,textvariable=self.device,values=win32.mouse_devices(),state="readonly").pack(fill="x")
        self.label(frame,"MCU 연결 전후 목록을 비교하세요. 실제 마우스를 선택하면 그 마우스의 움직임으로 자동 일시정지가 작동하지 않습니다.",
                   RED,8,wraplength=510,justify="left").pack(anchor="w",pady=(10,0))

        frame=section("좌표 기준","좌표 모드를 바꾸어도 기존 숫자는 자동으로 변환되지 않습니다.")
        radio(frame,"창 내부 DIP · 화면 배율 자동 보정",self.coordinates,"dip")
        radio(frame,"창 내부 비율 · X/Y 각각 0~1",self.coordinates,"ratio")

        frame=section("Python 스크립트","신뢰하는 워크플로에만 실행 권한을 허용하세요.")
        tk.Checkbutton(frame,text="이 세션에서 신뢰한 Python 코드 실행 허용",variable=self.allow_scripts,
                       bg=PANEL,fg=TEXT,selectcolor="#e7f6f0",activebackground=PANEL,
                       activeforeground=ACCENT,highlightthickness=0).pack(anchor="w")
        self.label(frame,"Python은 보안 샌드박스가 아닙니다. 파일과 네트워크에 접근할 수 있으며, 모의 실행에서도 api 외부의 Python 동작은 실제로 실행됩니다.",
                   RED,8,wraplength=510,justify="left").pack(anchor="w",pady=(10,0))
        self.label(body,"항상 적용: 30분 / 100,000 노드 한도 · 대상 창 유실 또는 포커스 변경 시 중지",MUTED,8,wraplength=550,justify="left").pack(anchor="w")
        def bind_scroll(widget):
            widget.bind("<MouseWheel>",lambda e:(scroll.yview_scroll(-int(e.delta/120),"units"),"break")[1])
            for child in widget.winfo_children(): bind_scroll(child)
        bind_scroll(body)

    def run(self):
        if not self.services_started: return
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
        if not self.services_started: return
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
                    self.step_count.set(f"{event['steps']:,}")
                    self.click_count.set(f"{event['clicks']:,}")
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
        if not self.services_started:
            self.root.destroy()
            return
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
