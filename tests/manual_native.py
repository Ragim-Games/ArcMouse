"""Opt-in native integration: injects only over this script's blank test window.
Run on an idle Windows desktop: python tests/manual_native.py --run
"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import multiprocessing as mp
import time
import tkinter as tk
from arcmouse import win32
from arcmouse.model import validate_settings
from arcmouse.supervisor import supervisor_main


def main():
    if '--run' not in sys.argv: raise SystemExit('Opt in with --run on an idle Windows desktop.')
    win32.dpi_aware()
    root=tk.Tk();root.title('ArcMouse native input test — blank pad');root.geometry('640x360+120+120');root.attributes('-topmost',True)
    pad=tk.Canvas(root,bg='white',highlightthickness=0);pad.pack(fill='both',expand=True)
    pad.create_text(320,45,text='ArcMouse: controlled click / hold / slide verification',fill='#16856e')
    root.update();root.focus_force();root.update()
    hwnd=win32.user.GetAncestor(root.winfo_id(),2)
    received=[]
    for name,sequence in [('down','<ButtonPress-1>'),('up','<ButtonRelease-1>'),('drag','<B1-Motion>')]:
        pad.bind(sequence,lambda e,n=name:received.append((n,e.x_root,e.y_root,time.monotonic())))
    ctx=mp.get_context('spawn');parent,child=ctx.Pipe();held=ctx.Value('I',0,lock=False)
    supervisor=ctx.Process(target=supervisor_main,args=(child,held));supervisor.start();child.close()
    events=[];last_ping=0;armed=False;direct_mouse_down=False
    def pump():
        nonlocal last_ping
        root.update()
        now=time.monotonic()
        if now-last_ping>.1:parent.send({'type':'heartbeat'});last_ping=now
        while parent.poll():events.append(parent.recv())
        if armed and win32.user.GetForegroundWindow()!=hwnd:
            parent.send({'type':'stop'});raise AssertionError('Test window lost focus; stopped input')
        errors=[e for e in events if e['type'] in ('error','fatal','hotkey_error')]
        if errors:raise AssertionError(errors)
        time.sleep(.005)
    def until(condition,timeout=5):
        end=time.monotonic()+timeout
        while not condition():
            if time.monotonic()>end:raise AssertionError('timeout: '+str(events[-6:]))
            pump()
    def take(kind):
        for i,e in enumerate(events):
            if e['type']==kind:return events.pop(i)
        return None
    def key(vk):
        assert win32.user.GetForegroundWindow()==hwnd,'Focus guard'
        win32.send_inputs(win32.INPUT(type=1,ki=win32.KEYBDINPUT(vk,0,0,0,win32.MARKER)),win32.INPUT(type=1,ki=win32.KEYBDINPUT(vk,0,2,0,win32.MARKER)))
    def start(settings):
        nonlocal armed
        events.clear();received.clear();root.focus_force();root.update()
        assert win32.user.GetForegroundWindow()==hwnd
        armed=True;key(0x85) # F22
        until(lambda:any(e['type']=='hotkey_start' for e in events))
        event=take('hotkey_start');parent.send({'type':'start','epoch':event['epoch'],'settings':validate_settings(settings)})
    try:
        until(lambda:any(e['type']=='ready' for e in events))
        parent.send({'type':'hotkeys','start':'F22','stop':'F23'})
        until(lambda:any(e['type']=='hotkeys' for e in events))
        x,y=pad.winfo_rootx()+180,pad.winfo_rooty()+160
        assert win32.user.GetAncestor(win32.user.WindowFromPoint(win32.W.POINT(x,y)),2)==hwnd
        win32.SoftwareMouse().move(x,y);root.update()
        common={'start_hotkey':'F22','stop_hotkey':'F23'}
        start({**common,'count':3,'interval_ms':40})
        until(lambda:any(e['type']=='idle' for e in events));armed=False
        assert [e[0] for e in received if e[0]!='drag']==['down','up']*3,received
        print('PASS actual current-cursor clicks: 3; native F22 start')
        actions=[{'type':'click','x':x,'y':y,'wait_ms':70},{'type':'hold','x':x+70,'y':y,'duration_ms':90,'wait_ms':70},{'type':'slide','x':x,'y':y+50,'end_x':x+150,'end_y':y+50,'duration_ms':150,'wait_ms':20}]
        start({**common,'mode':'points','actions':actions,'count':1})
        until(lambda:any(e['type']=='idle' for e in events));armed=False
        edges=[e for e in received if e[0]!='drag']
        assert [e[0] for e in edges]==['down','up']*3,received
        assert edges[3][-1]-edges[2][-1]>=.07,edges
        assert edges[2][-1]-edges[1][-1]>=.05,edges
        assert any(e[0]=='drag' for e in received),received
        assert abs(edges[-1][1]-(x+150))<=2 and abs(edges[-1][2]-(y+50))<=2,edges
        print('PASS actual ordered click/hold/slide, post-action wait, held drag endpoint')
        start({**common,'mode':'points','actions':[{'type':'hold','x':x,'y':y,'duration_ms':60000,'wait_ms':5}],'count':1})
        until(lambda:any(e[0]=='down' for e in received));t=time.monotonic();key(0x86) # F23
        until(lambda:any(e['type']=='stopped' for e in events));until(lambda:any(e[0]=='up' for e in received));armed=False
        elapsed=time.monotonic()-t;assert elapsed<.5,elapsed;assert held.value==0
        print(f'PASS native F23 stop during 60-second hold; release in {elapsed*1000:.0f} ms')
        from arcmouse.overlay import PointPicker, Markers
        owner=tk.Toplevel(root);owner.geometry('20x20+10000+10000');root.update()
        picked=[]
        picker=PointPicker(owner,'slide',picked.append,lambda:None)
        root.update()
        overlay_hwnd=win32.user.GetAncestor(picker.window.winfo_id(),2)
        assert win32.user.GetAncestor(win32.user.WindowFromPoint(win32.W.POINT(x,y)),2)==overlay_hwnd
        mouse=win32.SoftwareMouse();mouse.move(x,y);root.update();direct_mouse_down=True;mouse.press('left');root.update()
        mouse.move(x+100,y+40);root.update();mouse.release('left');direct_mouse_down=False
        until(lambda:bool(picked))
        item=picked[0]
        assert abs(item['x']-x)<=2 and abs(item['end_x']-x-100)<=2,item
        assert abs(item['end_y']-y-40)<=2,item
        changed=[];markers=Markers(owner,lambda *args:changed.append(args));markers.show([item]);root.update()
        marker_hwnd=win32.user.GetAncestor(markers.windows[0].winfo_id(),2)
        assert win32.user.GetAncestor(win32.user.WindowFromPoint(win32.W.POINT(x,y)),2)==marker_hwnd
        mouse.move(x,y);root.update();direct_mouse_down=True;mouse.press('left');root.update();mouse.move(x+30,y+20);root.update();mouse.release('left');direct_mouse_down=False
        until(lambda:bool(changed))
        assert abs(changed[0][2]-x-30)<=2 and abs(changed[0][3]-y-20)<=2,changed
        markers.hide();owner.destroy()
        print('PASS actual screen picker slide and draggable numbered point')

    finally:
        try:parent.send({'type':'shutdown'})
        except (OSError,EOFError):pass
        supervisor.join(2)
        if supervisor.is_alive():supervisor.terminate();supervisor.join(1)
        if held.value or direct_mouse_down:win32.release_buttons(held.value | (1 if direct_mouse_down else 0))
        parent.close();root.destroy()

if __name__=='__main__':main()
