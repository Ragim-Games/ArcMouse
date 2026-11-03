"""Simple cursor clicking plus an optional ordered point list."""
import multiprocessing as mp
import time
import tkinter as tk
from tkinter import ttk, filedialog
from . import __version__,win32
from .design import BG,WHITE,INK,MUTED,LINE,GREEN,Button,Surface,Toggle
from .model import DEFAULTS,MAX_ACTIONS,action,hotkey_pair,validate_settings,save_profile,load_profile
from .overlay import PointPicker,Markers
from .supervisor import supervisor_main

BUTTONS={"Left":"left","Right":"right","Middle":"middle"}
NAMES={"click":"Click","hold":"Hold","slide":"Slide"}


class AutoClicker:
    def __init__(self,root,*,start_services=True):
        self.root,self.services_started=root,start_services
        self.busy,self.ready,self.picking=False,False,False
        self.mode="cursor"
        self.actions=[]
        self.selected=None
        self.inputs=[]
        self.registered=None
        self.extra={"backend":"software","port":"COM3","dry_run":False}
        self.interval=tk.StringVar(value="100")
        self.button_name=tk.StringVar(value="Left")
        self.repeat_mode=tk.StringVar(value="Until stopped")
        self.count=tk.StringVar(value="1")
        self.start_key=tk.StringVar(value="F6")
        self.stop_key=tk.StringVar(value="F7")
        self.state=tk.StringVar(value="Preparing hotkeys…")
        self.stats=tk.StringVar(value="Actions: 0")
        self.key_status=tk.StringVar(value="F6 to start · F7 to stop")
        self.wait_value=tk.StringVar(value="100")
        self.duration_value=tk.StringVar(value="500")
        self.point_button=tk.StringVar(value="Left")
        self.show_markers=tk.BooleanVar(value=False)
        self.extra_dialog=None
        self.dialog_open=False
        self.minimized_for_run=False
        self.last_supervisor=time.monotonic()
        self.last_heartbeat=0
        root.title(f"ArcMouse {__version__}")
        root.configure(bg=BG)
        root.geometry("650x560")
        root.minsize(620,550)
        self.style()
        self.layout()
        self.markers=Markers(root,self.marker_changed)
        ctx=mp.get_context("spawn")
        self.held=ctx.Value("I",0,lock=False)
        if start_services:
            self.pipe,child=ctx.Pipe()
            self.supervisor=ctx.Process(target=supervisor_main,args=(child,self.held),name="ArcMouse-Hotkeys")
            self.supervisor.start()
            child.close()
            root.after(40,self.poll)
        else:
            self.state.set("Preview · Input engine off")
            self.start_button.configure(state="disabled")
        root.protocol("WM_DELETE_WINDOW",self.close)

    def style(self):
        self.root.option_add("*Font",("Segoe UI",9))
        st=ttk.Style();st.theme_use("clam")
        for name in ("TEntry","TCombobox"):
            st.configure(name,fieldbackground=WHITE,foreground=INK,background=WHITE,padding=7,
                         bordercolor=LINE,lightcolor=LINE,darkcolor=LINE,arrowcolor=MUTED,insertcolor=INK)
            st.map(name,fieldbackground=[("readonly",WHITE),("disabled",BG)],foreground=[("readonly",INK),("disabled",MUTED)])
        st.configure("Treeview",background=WHITE,fieldbackground=WHITE,foreground=INK,rowheight=33,borderwidth=0,font=("Segoe UI",9))
        st.configure("Treeview.Heading",background=BG,foreground=MUTED,relief="flat",font=("Segoe UI",8))
        st.map("Treeview",background=[("selected","#e7f6f0")],foreground=[("selected",GREEN)])
        self.root.option_add("*TCombobox*Listbox.background",WHITE)
        self.root.option_add("*TCombobox*Listbox.foreground",INK)

    def label(self,parent,text="",size=9,color=INK,bold=False,**kw):
        return tk.Label(parent,text=text,bg=parent.cget("bg"),fg=color,bd=0,
                        font=("Segoe UI",size,"bold" if bold else "normal"),**kw)

    def entry(self,parent,var,width=10):
        w=ttk.Entry(parent,textvariable=var,width=width);self.inputs.append((w,"normal"));return w

    def combo(self,parent,var,values,width=12,editable=False):
        state="normal" if editable else "readonly"
        w=ttk.Combobox(parent,textvariable=var,values=values,width=width,state=state)
        self.inputs.append((w,state));return w

    def layout(self):
        header=tk.Frame(self.root,bg=WHITE,padx=20,pady=10);header.pack(fill="x")
        self.label(header,"◈",23,GREEN,True).pack(side="left",padx=(0,8))
        self.label(header,"ArcMouse",18,bold=True).pack(side="left")
        self.settings_button=Button(header,"Settings",self.settings,variant="quiet",width=78)
        self.settings_button.pack(side="right")
        self.save_button=Button(header,"Save",self.save,variant="quiet",width=50);self.save_button.pack(side="right")
        self.open_button=Button(header,"Open",self.open,variant="quiet",width=50);self.open_button.pack(side="right")
        tk.Frame(self.root,bg=LINE,height=1).pack(fill="x")
        content=tk.Frame(self.root,bg=BG,padx=20,pady=14);content.pack(fill="both",expand=True)
        tabs=tk.Frame(content,bg=BG);tabs.pack(fill="x",pady=(0,12))
        self.cursor_tab=Button(tabs,"Current cursor",lambda:self.switch_mode("cursor"),variant="selected",width=125)
        self.cursor_tab.pack(side="left",padx=(0,6))
        self.points_tab=Button(tabs,"Point sequence",lambda:self.switch_mode("points"),width=125)
        self.points_tab.pack(side="left")
        self.label(tabs,"No target window required",8,MUTED).pack(side="right",padx=2)

        self.simple_card=Surface(content,height=106,padding=16);self.simple_card.pack(fill="x",pady=(0,10))
        row=self.simple_card.body
        row.columnconfigure(0,weight=1,uniform="simple");row.columnconfigure(1,weight=1,uniform="simple")
        for col,title in enumerate(("Click interval (ms)","Mouse button")):
            box=tk.Frame(row,bg=WHITE);box.grid(row=0,column=col,sticky="ew",padx=(0,14) if col==0 else 0)
            self.label(box,title,bold=True).pack(anchor="w",pady=(0,8))
            if col==0:self.entry(box,self.interval).pack(fill="x")
            else:self.combo(box,self.button_name,tuple(BUTTONS)).pack(fill="x")

        self.points_card=Surface(content,height=280,padding=12)
        panel=self.points_card.body
        toolbar=tk.Frame(panel,bg=WHITE);toolbar.pack(fill="x",pady=(0,10))
        self.point_tools=[]
        for kind in ("click","hold","slide"):
            w=Button(toolbar,"＋ "+NAMES[kind],lambda k=kind:self.pick(k),height=32)
            w.pack(side="left",padx=(0,5));self.point_tools.append(w)
        self.marker_toggle=Toggle(toolbar,self.show_markers,text="Show markers")
        self.marker_toggle.pack(side="right")
        self.show_markers.trace_add("write",lambda *_:self.update_markers())
        editor=tk.Frame(panel,bg=WHITE,width=205);editor.pack(side="right",fill="y",padx=(14,0));editor.pack_propagate(False)
        self.point_title=self.label(editor,"Add a point",11,bold=True);self.point_title.pack(anchor="w",pady=(0,8))
        self.label(editor,"Wait after action (ms)",8,MUTED).pack(anchor="w",pady=(0,4))
        self.entry(editor,self.wait_value).pack(fill="x")
        self.duration_label=self.label(editor,"Hold / slide duration (ms)",8,MUTED)
        self.duration_label.pack(anchor="w",pady=(8,4))
        self.duration_entry=self.entry(editor,self.duration_value);self.duration_entry.pack(fill="x")
        row=tk.Frame(editor,bg=WHITE);row.pack(fill="x",pady=(9,0))
        self.combo(row,self.point_button,tuple(BUTTONS),width=7).pack(side="left",fill="x",expand=True)
        apply=Button(row,"Apply",self.apply_point,variant="primary",width=56,height=32)
        apply.pack(side="right",padx=(6,0));self.point_tools.append(apply)
        listbox=tk.Frame(panel,bg=WHITE);listbox.pack(fill="both",expand=True)
        self.tree=ttk.Treeview(listbox,columns=("type","wait","duration"),show="tree headings",height=4,selectmode="browse")
        self.tree.heading("#0",text="Order");self.tree.column("#0",width=40,stretch=False)
        self.tree.heading("type",text="Action");self.tree.column("type",width=100)
        self.tree.heading("wait",text="Wait after");self.tree.column("wait",width=70,stretch=False)
        self.tree.heading("duration",text="Duration");self.tree.column("duration",width=75,stretch=False)
        scroll=ttk.Scrollbar(listbox,orient="vertical",command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set);scroll.pack(side="right",fill="y");self.tree.pack(fill="both",expand=True)
        self.tree.bind("<<TreeviewSelect>>",self.select_point)
        controls=tk.Frame(listbox,bg=WHITE);controls.pack(fill="x",pady=(8,0))
        for title,command in (("↑",lambda:self.reorder(-1)),("↓",lambda:self.reorder(1)),("Pick again",self.repick),("Delete",self.delete_point)):
            w=Button(controls,title,command,height=28);w.pack(side="left",padx=(0,5));self.point_tools.append(w)

        self.repeat_row=tk.Frame(content,bg=BG);self.repeat_row.pack(fill="x",pady=(0,12))
        self.repeat_label=self.label(self.repeat_row,"Repeat",bold=True);self.repeat_label.pack(side="left",padx=(0,12))
        self.repeat_combo=self.combo(self.repeat_row,self.repeat_mode,("Until stopped","Fixed count"),width=14)
        self.repeat_combo.pack(side="left",fill="x",expand=True)
        self.repeat_combo.bind("<<ComboboxSelected>>",lambda _:self.update_count())
        self.count_entry=self.entry(self.repeat_row,self.count,width=7);self.count_entry.pack(side="left",padx=(10,6))
        self.label(self.repeat_row,"times").pack(side="left");self.update_count()

        keys=Surface(content,height=108,padding=12);keys.pack(fill="x",pady=(0,10))
        row=tk.Frame(keys.body,bg=WHITE);row.pack(fill="x")
        presets=tuple(f"F{i}" for i in range(1,12))+("Ctrl+Alt+S","Ctrl+Alt+D")
        self.label(row,"Start",bold=True).pack(side="left",padx=(0,7))
        self.combo(row,self.start_key,presets,width=11,editable=True).pack(side="left",fill="x",expand=True)
        self.label(row,"Stop",bold=True).pack(side="left",padx=(14,7))
        self.combo(row,self.stop_key,presets,width=11,editable=True).pack(side="left",fill="x",expand=True)
        self.key_button=Button(row,"Apply",self.apply_hotkeys,width=56);self.key_button.pack(side="left",padx=(10,0))
        self.label(keys.body,textvariable=self.key_status,size=8,color=MUTED,anchor="w").pack(fill="x",pady=(10,0))
        status=tk.Frame(content,bg=BG);status.pack(fill="x",pady=(0,10))
        self.label(status,textvariable=self.state,size=9,color=MUTED,wraplength=510,justify="left").pack(side="left",fill="x",expand=True)
        self.label(status,textvariable=self.stats,size=13,color=GREEN,bold=True).pack(side="right")
        row=tk.Frame(content,bg=BG);row.pack(fill="x")
        self.start_button=Button(row,"▶ Start",self.run,variant="primary",height=44);self.start_button.pack(side="left",fill="x",expand=True,padx=(0,10))
        Button(row,"■ Stop",self.stop,variant="danger",width=120,height=44).pack(side="right")
        self.emergency_note=self.label(content,"Emergency stop  Ctrl + Alt + Shift + K",8,GREEN)
        self.emergency_note.pack(pady=(10,0))

    def switch_mode(self,mode):
        if self.busy or self.picking:return
        if not self.apply_point(silent=True):return
        self.mode=mode
        self.cursor_tab.variant="selected" if mode=="cursor" else "normal";self.cursor_tab.redraw()
        self.points_tab.variant="selected" if mode=="points" else "normal";self.points_tab.redraw()
        if mode=="points":
            self.root.minsize(820,720)
            self.simple_card.pack_forget()
            self.points_card.pack(fill="x",pady=(0,10),before=self.repeat_row)
            self.root.geometry("870x720")
            self.repeat_label.configure(text="Repeat sequence")
        else:
            self.root.minsize(620,550)
            self.points_card.pack_forget()
            self.simple_card.pack(fill="x",pady=(0,10),before=self.repeat_row)
            self.root.geometry("650x560")
            self.repeat_label.configure(text="Repeat")
        self.update_markers()

    def update_count(self):
        self.count_entry.configure(state="normal" if not self.busy and self.repeat_mode.get()=="Fixed count" else "disabled")

    def update_markers(self):
        if not hasattr(self,"markers"):return
        if self.show_markers.get() and self.mode=="points" and not self.busy and not self.picking:self.markers.show(self.actions)
        else:self.markers.hide()

    def marker_changed(self,index,endpoint,x,y):
        if self.busy:return
        if endpoint:self.actions[index].update(end_x=x,end_y=y)
        else:self.actions[index].update(x=x,y=y)
        self.refresh_list(index)

    def refresh_list(self,selected=None):
        self.tree.delete(*self.tree.get_children())
        for i,item in enumerate(self.actions):
            duration="—" if item["type"]=="click" else f"{item['duration_ms']:g} ms"
            self.tree.insert("","end",iid=str(i),text=str(i+1),values=(NAMES[item["type"]],f"{item['wait_ms']:g} ms",duration))
        if selected is not None and 0<=selected<len(self.actions):
            self.tree.selection_set(str(selected));self.tree.see(str(selected));self.selected=selected;self.populate_point()
        else:self.selected=None;self.point_title.configure(text="Select a point")

    def select_point(self,event=None):
        if self.busy:return
        chosen=self.tree.selection()
        if chosen:
            self.selected=int(chosen[0]);self.populate_point()

    def populate_point(self):
        if self.selected is None:return
        item=self.actions[self.selected]
        self.point_title.configure(text=f"{self.selected+1}. {NAMES[item['type']]}")
        self.wait_value.set(f"{item['wait_ms']:g}");self.duration_value.set(f"{item['duration_ms']:g}")
        self.point_button.set(next(k for k,v in BUTTONS.items() if v==item["button"]))
        self.duration_entry.configure(state="disabled" if item["type"]=="click" else "normal")

    def apply_point(self,silent=False):
        if self.selected is None or self.busy:return True
        try:
            item=dict(self.actions[self.selected]);item.update(wait_ms=self.wait_value.get(),duration_ms=self.duration_value.get(),button=BUTTONS[self.point_button.get()])
            self.actions[self.selected]=action(item)
            self.refresh_list(self.selected)
            if not silent:self.state.set("Point timing updated")
            return True
        except Exception as exc:self.state.set(str(exc));return False

    def pick(self,kind,index=None):
        if self.busy or self.picking:return
        if index is None and len(self.actions)>=MAX_ACTIONS:self.state.set(f"You can add up to {MAX_ACTIONS} points");return
        if not self.apply_point(silent=True):return
        self.picking=True;self.markers.hide();self.start_button.configure(state="disabled")
        def done(item):
            self.picking=False
            if index is None:self.actions.append(action(item));selected=len(self.actions)-1
            else:
                previous=self.actions[index]
                item.update(wait_ms=previous["wait_ms"],duration_ms=previous["duration_ms"],button=previous["button"])
                self.actions[index]=action(item);selected=index
            self.refresh_list(selected);self.show_markers.set(True);self.update_markers();self.set_busy(False)
            self.state.set("Point added. Drag its marker to adjust the position.")
        def cancel():self.picking=False;self.set_busy(False);self.update_markers();self.state.set("Point selection canceled")
        self.picker=PointPicker(self.root,kind,done,cancel)

    def repick(self):
        if self.selected is not None:self.pick(self.actions[self.selected]["type"],self.selected)

    def reorder(self,delta):
        if self.busy or self.selected is None or not self.apply_point(silent=True):return
        index=self.selected;other=index+delta
        if 0<=other<len(self.actions):
            self.actions[index],self.actions[other]=self.actions[other],self.actions[index]
            self.refresh_list(other);self.update_markers()

    def delete_point(self):
        if self.busy or self.selected is None:return
        index=self.selected;del self.actions[index];self.selected=None
        self.refresh_list(min(index,len(self.actions)-1) if self.actions else None);self.update_markers()

    def collect_settings(self,require_actions=True):
        if not self.apply_point(silent=True):raise ValueError("Check the point timing values.")
        result={**self.extra,"mode":self.mode,"interval_ms":self.interval.get(),"button":BUTTONS[self.button_name.get()],
                "count":self.count.get() if self.repeat_mode.get()=="Fixed count" else 0,"actions":self.actions,
                "start_hotkey":self.start_key.get(),"stop_hotkey":self.stop_key.get()}
        result=validate_settings(result,require_actions=require_actions)
        if self.repeat_mode.get()=="Fixed count" and result["count"]==0:raise ValueError("Enter a repeat count of at least 1.")
        return result

    def apply_hotkeys(self):
        if self.busy or self.picking:return
        try:
            a,b=hotkey_pair(self.start_key.get(),self.stop_key.get())
            if self.services_started:self.pipe.send({"type":"hotkeys","start":a[2],"stop":b[2]})
            else:self.key_status.set(f"Preview: {a[2]} to start · {b[2]} to stop")
        except Exception as exc:self.state.set(str(exc))

    def set_busy(self,busy):
        self.busy=busy
        for widget,normal in self.inputs:widget.configure(state="disabled" if busy else normal)
        for widget in (self.cursor_tab,self.points_tab,self.key_button,self.settings_button,self.save_button,self.open_button,self.marker_toggle,*self.point_tools):
            widget.configure(state="disabled" if busy else "normal")
        self.update_count()
        if not busy:self.populate_point()
        self.start_button.configure(state="normal" if self.ready and not busy and not self.picking else "disabled")

    def run(self,epoch=None):
        if not self.services_started or not self.ready or self.busy or self.picking or self.dialog_open or (self.extra_dialog and self.extra_dialog.winfo_exists()):return
        try:
            settings=self.collect_settings()
            if (settings["start_hotkey"],settings["stop_hotkey"])!=self.registered:raise ValueError("Apply your new hotkeys before starting.")
            self.markers.hide();self.root.update_idletasks()
            if not settings["dry_run"] and self.root.state()!="iconic":
                self.root.iconify();self.root.update_idletasks();self.minimized_for_run=True
            message={"type":"start","settings":settings}
            if epoch is not None:message["epoch"]=epoch
            self.pipe.send(message);self.active_backend=settings["backend"]
            self.set_busy(True);self.state.set("Starting…");self.stats.set("Actions: 0")
        except Exception as exc:self.state.set(str(exc))

    def stop(self):
        if self.services_started:
            try:self.pipe.send({"type":"stop"})
            except (EOFError,BrokenPipeError,OSError):pass

    def save(self):
        if self.busy or self.picking:return
        self.dialog_open=True
        try:
            settings=self.collect_settings(require_actions=False)
            self.markers.hide()
            path=filedialog.asksaveasfilename(parent=self.root,title="Save ArcMouse profile",defaultextension=".json",initialfile="click-points.json",filetypes=[("ArcMouse settings","*.json")])
            if path:save_profile(path,settings);self.state.set("Profile saved")
        except Exception as exc:self.state.set(str(exc))
        finally:self.dialog_open=False;self.update_markers()

    def open(self):
        if self.busy or self.picking:return
        self.markers.hide()
        self.dialog_open=True
        try:
            path=filedialog.askopenfilename(parent=self.root,title="Open ArcMouse profile",filetypes=[("ArcMouse settings","*.json")])
            if not path:return
            config=load_profile(path);self.selected=None
            self.actions=config["actions"]
            self.interval.set(str(config["interval_ms"]));self.button_name.set(next(k for k,v in BUTTONS.items() if v==config["button"]))
            self.repeat_mode.set("Fixed count" if config["count"] else "Until stopped");self.count.set(str(config["count"] or 1))
            self.start_key.set(config["start_hotkey"]);self.stop_key.set(config["stop_hotkey"])
            self.extra={k:config[k] for k in ("backend","port","dry_run")}
            self.switch_mode(config["mode"]);self.refresh_list(0 if self.actions else None);self.update_count();self.apply_hotkeys()
            self.state.set("Profile loaded")
        except Exception as exc:self.state.set(str(exc))
        finally:self.dialog_open=False;self.update_markers()

    def settings(self):
        if self.busy or self.picking:return
        if self.extra_dialog and self.extra_dialog.winfo_exists():self.extra_dialog.lift();return
        dialog=tk.Toplevel(self.root);self.extra_dialog=dialog
        dialog.title("ArcMouse settings");dialog.configure(bg=WHITE,padx=24,pady=22);dialog.geometry("430x310");dialog.transient(self.root);dialog.grab_set()
        self.label(dialog,"Input method",14,bold=True).pack(anchor="w",pady=(0,15))
        backend=tk.StringVar(value="Windows mouse" if self.extra["backend"]=="software" else "USB board")
        ttk.Combobox(dialog,textvariable=backend,values=("Windows mouse","USB board"),state="readonly").pack(fill="x")
        port=tk.StringVar(value=self.extra["port"])
        self.label(dialog,"USB serial port (hardware mode only)",8,MUTED).pack(anchor="w",pady=(12,5))
        ttk.Entry(dialog,textvariable=port).pack(fill="x")
        dry=tk.BooleanVar(value=self.extra["dry_run"]);Toggle(dialog,dry,text="Dry run (no mouse input)").pack(anchor="w",pady=(12,8))
        def apply():
            self.extra={"backend":"software" if backend.get()=="Windows mouse" else "hardware","port":port.get(),"dry_run":dry.get()}
            self.state.set("Dry run · Mouse input off" if dry.get() else "Ready");dialog.destroy()
        Button(dialog,"Save",apply,variant="primary").pack(fill="x",side="bottom")

    def poll(self):
        try:
            now=time.monotonic()
            if now-self.last_heartbeat>=.25:self.pipe.send({"type":"heartbeat"});self.last_heartbeat=now
            for _ in range(64):
                if not self.pipe.poll():break
                event=self.pipe.recv();kind=event["type"];self.last_supervisor=now
                if kind=="ready":
                    if not event["emergency"]:self.emergency_note.configure(text="Use your configured Stop hotkey to stop")
                    self.apply_hotkeys()
                elif kind=="hotkeys":
                    self.registered=(event["start"],event["stop"]);self.start_key.set(event["start"]);self.stop_key.set(event["stop"])
                    self.ready=True;self.key_status.set(f"Active: {event['start']} to start · {event['stop']} to stop");self.state.set("Ready");self.set_busy(False)
                elif kind=="hotkey_error":self.state.set(event["message"])
                elif kind=="hotkey_start":self.run(epoch=event["epoch"])
                elif kind=="running":self.state.set("Dry run · Mouse input off" if self.extra["dry_run"] else "Running")
                elif kind=="progress":
                    self.stats.set(f"Actions: {event['clicks']:,}")
                    if self.mode=="points" and event["index"]>0:self.state.set(f"Point {event['index']} · Completed cycles: {event['cycles']}")
                elif kind in ("completed","stopped","error","fatal"):
                    if kind=="fatal":self.ready=False
                    self.state.set(event.get("message",event.get("reason","Completed")));self.set_busy(False)
                    if self.minimized_for_run:self.root.deiconify();self.minimized_for_run=False
                elif kind=="idle":self.set_busy(False)
            if now-self.last_supervisor>1.5 or not self.supervisor.is_alive():
                self.disconnect();return
        except (EOFError,BrokenPipeError,OSError):self.disconnect();return
        self.root.after(40,self.poll)

    def disconnect(self):
        if self.held.value and getattr(self,"active_backend","software")=="software":
            try:win32.release_buttons(self.held.value)
            except OSError:pass
            self.held.value=0
        self.ready=False;self.set_busy(False);self.state.set("The safety monitor stopped. Restart ArcMouse.")
        if self.minimized_for_run:self.root.deiconify();self.minimized_for_run=False
        if self.supervisor.is_alive():self.supervisor.terminate()

    def close(self):
        self.markers.hide()
        if self.picking:self.picker.abort()
        if self.services_started:
            try:
                self.pipe.send({"type":"shutdown"});self.supervisor.join(1)
                if self.supervisor.is_alive():self.supervisor.terminate();self.supervisor.join(.5)
                if self.held.value and getattr(self,"active_backend","software")=="software":win32.release_buttons(self.held.value)
            except (EOFError,BrokenPipeError,OSError):pass
            self.pipe.close()
        self.root.destroy()


def main():
    win32.dpi_aware();root=tk.Tk();AutoClicker(root);root.mainloop()
