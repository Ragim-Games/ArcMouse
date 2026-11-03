import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

@unittest.skipUnless(sys.platform=='win32','Windows UI')
class UITests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from arcmouse.ui import AutoClicker
        self.root=tk.Tk();self.root.withdraw()
        self.app=AutoClicker(self.root,start_services=False)
        self.app.extra['dry_run']=True
    def tearDown(self):
        self.app.services_started=False;self.app.close()
    def add(self,kind,x=10):
        with patch('arcmouse.ui.PointPicker') as picker:
            self.app.pick(kind)
            item={'type':kind,'x':x,'y':20}
            if kind=='slide':item.update(end_x=100,end_y=200)
            # Picker's completion path, with overlays disabled for unattended CI.
            with patch.object(self.app.markers,'show'):
                picker.call_args.args[2](item)
    def test_edit_reorder_delete_and_collect(self):
        a=self.app;a.switch_mode('points')
        self.add('click');self.add('hold',30);self.add('slide',50)
        a.refresh_list(1);a.wait_value.set('321');a.duration_value.set('765');a.apply_point()
        a.reorder(-1)
        self.assertEqual(a.actions[0]['type'],'hold');self.assertEqual(a.actions[0]['wait_ms'],321)
        self.assertEqual(a.actions[0]['duration_ms'],765)
        a.delete_point();a.repeat_mode.set('Fixed count');a.count.set('2')
        s=a.collect_settings();self.assertEqual([x['type'] for x in s['actions']],['click','slide']);self.assertEqual(s['count'],2)
    def test_run_hides_markers_and_sends_current_settings(self):
        a=self.app;a.switch_mode('points');self.add('hold');a.wait_value.set('456')
        a.services_started=True;a.ready=True;a.registered=('F6','F7');a.pipe=Mock()
        with patch.object(a.markers,'hide') as hide:a.run(epoch=9);hide.assert_called()
        command=a.pipe.send.call_args.args[0]
        self.assertEqual(command['epoch'],9);self.assertEqual(command['settings']['actions'][0]['wait_ms'],456);self.assertTrue(a.busy)
    def test_hotkey_cannot_run_during_file_dialog_or_picker(self):
        a=self.app;a.services_started=True;a.ready=True;a.pipe=Mock();a.registered=('F6','F7')
        a.dialog_open=True;a.run();a.dialog_open=False;a.picking=True;a.run();a.picking=False
        a.pipe.send.assert_not_called()
    def test_profile_ui_roundtrip(self):
        a=self.app;a.switch_mode('points');self.add('slide');a.wait_value.set('789')
        with tempfile.TemporaryDirectory() as folder:
            path=str(Path(folder)/'saved.json')
            with patch('arcmouse.ui.filedialog.asksaveasfilename',return_value=path):a.save()
            a.actions=[];a.selected=None
            with patch('arcmouse.ui.filedialog.askopenfilename',return_value=path),patch.object(a.markers,'show'):a.open()
        self.assertEqual(a.actions[0]['wait_ms'],789);self.assertEqual(a.actions[0]['type'],'slide');self.assertFalse(a.dialog_open)

if __name__=='__main__':unittest.main()
