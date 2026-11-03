"""Launch from source: python main.py"""
import multiprocessing
import sys


if __name__ == "__main__":
    multiprocessing.freeze_support()
    if sys.platform != "win32":
        raise SystemExit("ArcMouse desktop requires Windows 10/11. Portable core tests work on other systems.")
    from arcmouse.ui import main
    main()
