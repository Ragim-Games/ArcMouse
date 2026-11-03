# Building the Windows executable

Use 64-bit Windows and 64-bit Python 3.15 with Tkinter. The release workflow uses the same Python minor version.

```powershell
python -m venv .venv-build
.venv-build/Scripts/python.exe -m pip install -r requirements-build.txt
.venv-build/Scripts/python.exe scripts/build_windows.py
```

Outputs are written under `dist/release`:

- `ArcMouse-<version>-windows-x64.exe`
- `ArcMouse-<version>-windows-x64.zip`
- `SHA256SUMS.txt`

The ZIP includes the executable, README, MIT license, third-party notices, and dependency licenses. The single-file EXE bundles its Python runtime, Tcl/Tk, and pySerial. It uses an application icon, English version metadata, an as-invoker manifest, and per-monitor DPI awareness. No administrator privileges or Python installation are required to launch it.

The EXE extracts its bundled runtime to a temporary directory when it starts. The early `multiprocessing.freeze_support()` call is required for the supervisor and input worker to launch correctly. See the [PyInstaller multiprocessing documentation](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#multi-processing) and [build options](https://pyinstaller.org/en/stable/usage.html).

## Verify the packaged app

Run on a Windows desktop where F22 and F23 are available for the temporary test bindings:

```powershell
$report = Join-Path $PWD 'build/self-test.json'
$app = Start-Process -FilePath (Resolve-Path 'dist/ArcMouse.exe') -ArgumentList @('--self-test', "`"$report`"") -WindowStyle Hidden -PassThru
$app.WaitForExit(60000)
Get-Content -LiteralPath $report
```

The report must contain `"ok": true` and `"frozen": true`. The check constructs the UI, registers temporary hotkeys in the supervisor, starts packaged child processes, runs finite cursor and click/hold/slide dry runs, cancels a long hold, and verifies supervisor shutdown. No mouse input is generated. The standard automated tests remain separate:

```powershell
.venv-build/Scripts/python.exe -m unittest discover -s tests -v
```

## Publish

Update `arcmouse.__version__`, add English release notes at `docs/releases/v<version>.md`, and push the matching `v<version>` tag. The **Windows EXE** workflow builds, tests, and uploads the executable, ZIP, and checksums to a GitHub release. A manual workflow run produces downloadable build artifacts without publishing a release. A failed build or packaged self-test blocks release publication.

Executables are currently unsigned. No certificate, installer, automatic update service, or machine-wide installation is added.
