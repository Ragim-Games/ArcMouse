"""Small native UI components for the light theme."""
import tkinter as tk
from tkinter import font as tkfont

BG = "#f5f7fa"
WHITE = "#ffffff"
INK = "#243448"
MUTED = "#778596"
LINE = "#e6ebf0"
GREEN = "#16856e"
MINT = "#e7f6f0"


def rounded(canvas, x1, y1, x2, y2, radius=12, **kwargs):
    r = min(radius, (x2-x1)/2, (y2-y1)/2)
    return canvas.create_polygon(
        x1+r,y1, x2-r,y1, x2,y1, x2,y1+r, x2,y2-r,
        x2,y2, x2-r,y2, x1+r,y2, x1,y2, x1,y2-r,
        x1,y1+r, x1,y1, smooth=True, splinesteps=24, **kwargs)


class Surface(tk.Canvas):
    """Rounded panel with a real frame inside; native controls remain editable."""
    def __init__(self, parent, height=100, width=200, padding=16, color=WHITE, **kwargs):
        super().__init__(parent, bg=parent.cget("bg"), height=height, width=width,
                         bd=0, highlightthickness=0, **kwargs)
        self.padding, self.color = padding, color
        self.body = tk.Frame(self, bg=color)
        self.bind("<Configure>", self._layout)

    def _layout(self, event):
        self.delete("surface")
        rounded(self, 1, 3, event.width-1, event.height-1, 14,
                fill="#ecf0f3", outline="", tags="surface")
        rounded(self, 1, 1, event.width-1, event.height-3, 14,
                fill=self.color, outline=LINE, width=1, tags="surface")
        p = self.padding
        self.body.place(x=p, y=p, width=max(1,event.width-p*2), height=max(1,event.height-p*2-2))


class Button(tk.Canvas):
    def __init__(self, parent, text, command, variant="normal", width=None, height=36, **kwargs):
        self.text, self.command, self.variant = text, command, variant
        self.status, self.hover, self.focused = "normal", False, False
        self.label_font = tkfont.Font(family="Malgun Gothic", size=9, weight="bold" if variant=="primary" else "normal")
        width = width or self.label_font.measure(text)+28
        super().__init__(parent, width=width, height=height, bg=parent.cget("bg"),
                         highlightthickness=0, bd=0, cursor="hand2", takefocus=1, **kwargs)
        self.bind("<Configure>",lambda _:self.redraw())
        self.bind("<Enter>",lambda _:self._hover(True))
        self.bind("<Leave>",lambda _:self._hover(False))
        self.bind("<ButtonRelease-1>",self._release)
        self.bind("<Return>",lambda _:self.invoke())
        self.bind("<space>",lambda _:self.invoke())
        self.bind("<FocusIn>",lambda _:self._focus(True))
        self.bind("<FocusOut>",lambda _:self._focus(False))

    def _hover(self,value):
        self.hover=value
        self.redraw()

    def _focus(self,value):
        self.focused=value
        self.redraw()

    def _release(self,event):
        if 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height():
            self.invoke()

    def invoke(self):
        if self.status != "disabled":
            self.command()

    def configure(self, cnf=None, **kwargs):
        if "state" in kwargs:
            self.status=kwargs.pop("state")
            super().configure(takefocus=self.status!="disabled",cursor="" if self.status=="disabled" else "hand2")
        if "text" in kwargs:
            self.text=kwargs.pop("text")
        if cnf is not None or kwargs:
            result=super().configure(cnf,**kwargs)
        else:
            result=None
        self.redraw()
        return result

    config=configure

    def redraw(self):
        self.delete("all")
        w,h=self.winfo_width(),self.winfo_height()
        if w < 2: return
        fill,fg,border={
            "normal":(WHITE,INK,LINE),
            "primary":(GREEN,WHITE,GREEN),
            "danger":("#fff2f2","#c64f5e","#f7dfe2"),
            "quiet":(self.cget("bg"),MUTED,self.cget("bg")),
            "selected":(MINT,GREEN,MINT),
        }[self.variant]
        if self.status=="disabled":
            fill,fg,border="#eef1f4","#a2acb7",LINE
        elif self.hover:
            fill={"normal":"#f3f7f8","primary":"#106d5a","danger":"#ffe7e9",
                  "quiet":"#edf3f5","selected":"#d9f0e6"}[self.variant]
        rounded(self,1,1,w-1,h-1,9,fill=fill,outline=GREEN if self.focused else border,width=1)
        self.create_text(w/2,h/2,text=self.text,fill=fg,font=self.label_font)


class Toggle(tk.Canvas):
    def __init__(self,parent,variable,text="모의 실행"):
        self.variable,self.text,self.status=variable,text,"normal"
        self.switch_x=max(86,tkfont.Font(family="Malgun Gothic",size=9).measure(text)+12)
        super().__init__(parent,width=self.switch_x+44,height=34,bg=parent.cget("bg"),bd=0,
                         highlightthickness=0,cursor="hand2",takefocus=1)
        self.trace=variable.trace_add("write",lambda *_:self.redraw())
        self.bind("<Configure>",lambda _:self.redraw())
        self.bind("<ButtonRelease-1>",lambda _:self.toggle())
        self.bind("<space>",lambda _:self.toggle())
        self.bind("<Return>",lambda _:self.toggle())
        self.bind("<FocusIn>",lambda _:self.redraw(True))
        self.bind("<FocusOut>",lambda _:self.redraw())

    def toggle(self):
        if self.status!="disabled": self.variable.set(not self.variable.get())

    def configure(self,cnf=None,**kwargs):
        if "state" in kwargs:
            self.status=kwargs.pop("state")
            super().configure(takefocus=self.status!="disabled")
        if cnf is not None or kwargs: super().configure(cnf,**kwargs)
        self.redraw()

    config=configure

    def redraw(self,focused=False):
        self.delete("all")
        active=self.variable.get()
        self.create_text(0,17,text=self.text,anchor="w",fill=MUTED if self.status=="disabled" else INK,font=("Malgun Gothic",9))
        rounded(self,self.switch_x,7,self.switch_x+38,27,10,fill=("#36b990" if active else "#c7d0da"),outline=GREEN if focused else "")
        x=self.switch_x+(26 if active else 12)
        self.create_oval(x-8,9,x+8,25,fill=WHITE,outline="")
