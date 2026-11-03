"""Screen point picker and draggable numbered markers, hidden during execution."""
import tkinter as tk
from . import win32

win32.bind(win32.user,"SetWindowPos",win32.W.BOOL,win32.W.HWND,win32.W.HWND,
           win32.C.c_int,win32.C.c_int,win32.C.c_int,win32.C.c_int,win32.W.UINT)


def place(window,x,y,width,height):
    window.update_idletasks()
    hwnd=win32.user.GetAncestor(window.winfo_id(),2)
    win32.user.SetWindowPos(hwnd,win32.W.HWND(-1),int(x),int(y),int(width),int(height),0x10)


class PointPicker:
    def __init__(self,root,kind,done,cancel):
        self.root,self.kind,self.done,self.cancel=root,kind,done,cancel
        self.start=None
        self.closed=False
        root.withdraw()
        self.window=tk.Toplevel(root)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost",True)
        self.window.attributes("-alpha",.28)
        self.window.configure(bg="#0a6456")
        left,top,width,height=win32.screen_bounds()
        self.left,self.top=left,top
        self.window.geometry(f"{width}x{height}+0+0")
        self.canvas=tk.Canvas(self.window,bg="#0a6456",highlightthickness=0,cursor="crosshair")
        self.canvas.pack(fill="both",expand=True)
        hint="Drag from the start point to the end point" if kind=="slide" else "Click to choose a point"
        self.canvas.create_text(-left+40,-top+42,text=hint+"  ·  Esc to cancel",anchor="w",fill="white",font=("Segoe UI",20,"bold"))
        self.canvas.bind("<ButtonPress-1>",self.press)
        self.canvas.bind("<B1-Motion>",self.motion)
        self.canvas.bind("<ButtonRelease-1>",self.release)
        self.window.bind("<Escape>",lambda _:self.abort())
        place(self.window,left,top,width,height)
        self.window.focus_force()
        self.window.grab_set()

    def press(self,event):
        self.start=(event.x_root,event.y_root)

    def motion(self,event):
        if self.start and self.kind=="slide":
            self.canvas.delete("path")
            self.canvas.create_line(self.start[0]-self.left,self.start[1]-self.top,
                                    event.x_root-self.left,event.y_root-self.top,
                                    fill="white",width=4,arrow="last",tags="path")

    def release(self,event):
        if not self.start:return
        item={"type":self.kind,"x":self.start[0],"y":self.start[1],
              "duration_ms":500,"wait_ms":100,"button":"left"}
        if self.kind=="slide":item.update(end_x=event.x_root,end_y=event.y_root)
        self.finish()
        self.done(item)

    def finish(self):
        if self.closed:return
        self.closed=True
        self.window.grab_release()
        self.window.destroy()
        self.root.deiconify()

    def abort(self):
        self.finish()
        self.cancel()


class Markers:
    def __init__(self,root,changed):
        self.root,self.changed=root,changed
        self.windows=[]

    def hide(self):
        for window in self.windows:
            if window.winfo_exists():window.destroy()
        self.windows=[]

    def show(self,actions):
        self.hide()
        for index,item in enumerate(actions):
            self.add(index,item["x"],item["y"],False,item["type"]=="slide")
            if item["type"]=="slide":self.add(index,item["end_x"],item["end_y"],True,True)

    def add(self,index,x,y,endpoint,slide):
        window=tk.Toplevel(self.root)
        window.overrideredirect(True)
        window.attributes("-topmost",True)
        transparent="#ff00ff"
        window.attributes("-transparentcolor",transparent)
        window.configure(bg=transparent)
        window.geometry("48x48+0+0")
        canvas=tk.Canvas(window,bg=transparent,highlightthickness=0,cursor="fleur")
        canvas.pack(fill="both",expand=True)
        canvas.create_oval(3,3,45,45,fill="#527fce" if endpoint else "#16856e",outline="white",width=2)
        label=str(index+1)+("B" if endpoint else "A" if slide else "")
        canvas.create_text(24,24,text=label,fill="white",font=("Segoe UI",12,"bold"))
        drag={}
        def down(event):drag.update(dx=event.x,dy=event.y)
        def motion(event):
            if drag:place(window,event.x_root-drag["dx"],event.y_root-drag["dy"],48,48)
        def up(event):
            if drag:
                self.changed(index,endpoint,event.x_root-drag["dx"]+24,event.y_root-drag["dy"]+24)
                drag.clear()
        canvas.bind("<ButtonPress-1>",down)
        canvas.bind("<B1-Motion>",motion)
        canvas.bind("<ButtonRelease-1>",up)
        place(window,x-24,y-24,48,48)
        self.windows.append(window)
