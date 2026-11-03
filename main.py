"""Launch from source: python main.py"""
import multiprocessing
import sys


if __name__ == "__main__":
    multiprocessing.freeze_support()
    if sys.platform != "win32":
        raise SystemExit("ArcMouse desktop requires Windows 10/11. Portable core tests work on other systems.")
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        from arcmouse.diagnostics import self_test
        raise SystemExit(self_test(sys.argv[2]))
    from arcmouse.ui import main
    main()
