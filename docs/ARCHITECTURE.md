# Architecture · 0.3

The UI provides repeated clicks at the current cursor and a simple ordered list of point actions. There is no target-window search, workflow graph, or script injection layer.

| Module | Responsibility |
|---|---|
| ui.py / design.py | Light UI, timing, repetition, hotkey editing, and profiles |
| overlay.py | Full-screen point selection and draggable numbered markers |
| model.py | Settings validation and normalization, hotkey parsing, JSON persistence |
| supervisor.py | Independent global hotkey monitoring, heartbeats, execution, stopping, and Job Objects |
| engine.py | Current-cursor clicks or ordered click, hold, and slide actions |
| win32.py | SendInput, RegisterHotKey, DPI awareness, virtual desktop bounds, and Job Objects |
| hardware.py | Sequential, acknowledged USB board communication |

The supervisor forwards Start hotkeys to the UI, which validates and sends the latest settings. Execution cannot start while a file dialog, point picker, or settings window is open. Unapplied hotkey changes also prevent execution. If rebinding fails, only newly registered keys are released, preserving the existing Start and Stop bindings. Swapping the two hotkeys reuses their existing registrations.

A worker waits on a gate until its Job Object has been assigned. Current cursor mode waits for the interval, then clicks. Point sequence mode moves to the point, performs the action, then waits for that action's post-action delay. Repeat count means individual clicks in cursor mode and complete sequence cycles in point mode. Slides hold the button while moving along the selected segment with smoothstep acceleration and deceleration.

Waits check cancellation at intervals of at most 10 ms. Waits and movement also check the session deadline. Held-button state is recorded in shared memory. Normal cancellation releases the button in a finally block; the supervisor releases software buttons after forced worker termination. The UI also attempts release if the supervisor is lost. MCU firmware uses its own watchdog if the host exits.

Global stopping is independent of UI responsiveness. If a worker has not exited within 80 ms after cancellation, the supervisor closes its Job Object. Execution stops after 2.5 seconds without a UI heartbeat, and an independent 30-minute session limit also applies. Hotkey start requests carry an epoch so requests issued before a stop cannot restart execution later. Completion is sent to the UI only after the worker has exited, avoiding a race between immediate restart and cleanup.

Profiles are validated JSON using format version 3. They are written to a temporary file and then replaced; imports are limited to 1 MB. Display labels are not serialized, so changing the interface language does not change existing profile keys or action values. Coordinates are virtual desktop pixels read by a DPI-aware process, including negative monitor origins. The app does not track windows or recalculate saved points after layout changes.

Input and stopping cannot be guaranteed during a complete Windows freeze, on the secure desktop, or when UIPI blocks input. The 5 ms floor prevents a busy loop; it is not a guarantee of an exact click rate.
