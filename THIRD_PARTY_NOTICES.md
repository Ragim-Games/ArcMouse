# Third-party notices

The Windows build bundles Python, Tcl/Tk, pySerial, and the PyInstaller bootloader. ArcMouse itself is licensed under the MIT license in `LICENSE`.

| Component | License / source |
|---|---|
| Python and its bundled standard library components | [Python license](https://docs.python.org/3/license.html); the build includes the installed distribution's LICENSE.txt |
| Tcl/Tk | BSD-style licenses; the build copies the installed libraries' license.terms files |
| pySerial | BSD license; retained from the official pyserial 3.5 source distribution because its wheel omits the license file |
| PyInstaller bootloader | GPL with the bootloader exception; copied from the installed PyInstaller distribution |

The portable ZIP includes these notices in its `licenses` directory. The same license files are embedded inside the single-file EXE. The PyInstaller bootloader exception allows distributing the bundled application under its own license.
