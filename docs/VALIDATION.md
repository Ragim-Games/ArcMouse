# Validation status · 0.3.1

Environment: Windows, Python 3.15.0 (64-bit), Tk 9.0. Date: 2026-11-03.

## English interface update

- All **34 automated tests passed** after the English conversion. Coverage includes settings and hotkey validation, action order and repetition, post-action delays, hold cancellation, release after a failed slide, dry runs, profile persistence, UI editing and reordering, blocking Start during dialogs, hotkey rollback and swapping, Win32 ABI sizes, real Job Object termination, and serial acknowledgement and watchdog behavior.
- Python source compilation passed.
- All application-owned labels, status messages, validation errors, point-picker instructions, and profile dialog titles were converted to English. The README, architecture guide, hardware guide, and this validation record are in English.
- Current cursor, Point sequence, and Settings were rendered using the actual Tk UI and visually checked for clipping. Both README screenshots were replaced with English captures. Their Start buttons are intentionally disabled because the input engine was off during capture.
- Profile format version 3 and action identifiers are unchanged. Display labels are not stored in profiles, so existing 0.3 profiles remain compatible.
- Repository text files were scanned for remaining Korean text. Firmware comments, CI configuration, and licensing were already in English.

Windows-provided file dialog controls and system error descriptions can follow the Windows display language. ArcMouse does not change the user's OS language.

## Previous native input validation (0.3.0)

The following results were recorded before the interface translation. Native input injection was not repeated for the language-only update.

- Actual app startup, default F6/F7 registration, UI–supervisor–worker communication, and finite dry-run completion passed.
- `tests/manual_native.py --run` verified actual **SendInput and RegisterHotKey** in a dedicated blank window: three current-cursor clicks, a click → hold → slide sequence, post-action waits, and drag endpoint events.
- F22/F23 were registered as test Start/Stop keys. Stopping a 60-second hold released the button in approximately **19 ms** in the latest recorded run. This is a measurement from one environment, not a worst-case latency guarantee.
- The full-screen picker accepted a slide's start and end points, and dragging a numbered marker updated its position.

The native test sends input to its own blank window and overlays. It checks window ownership and focus before starting and stops if focus is lost during execution. Automated tests do not inject desktop clicks. Native input testing required a normal Windows environment because the sandbox rejected global hotkey registration.

## Not yet validated

- Physical Leonardo/Pico compilation, upload, connection, watchdog behavior, and stop button.
- Every DPI and multi-monitor combination, exclusive input application, and elevated application.
- Sustained load, maximum click rate, and CPU/latency distributions across hardware.
- GitHub CI results must be checked separately from these local results.

## Reproduce

```powershell
python -m compileall -q arcmouse main.py firmware/pico
python -m unittest discover -s tests -v
python tests/manual_native.py --run
```

The last command uses real input and should run on an idle Windows desktop. For a manual UI check, verify F6/F7 in Current cursor mode, edit and apply hotkeys, then add points, drag markers, edit timing, save, open, start, and stop a sequence.
