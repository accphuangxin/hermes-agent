"""Shared ANSI color utilities for Hermes CLI modules."""

import os
import sys


def _enable_windows_ansi() -> bool:
    """Enable Virtual Terminal Processing on Windows cmd.exe / PowerShell.

    Returns True if ANSI sequences will be processed, False if the console
    does not support them (e.g. old Windows, redirected output).
    """
    if sys.platform != "win32":
        return True
    try:
        import ctypes
        import ctypes.wintypes

        kernel32 = ctypes.windll.kernel32
        # Get handle for stdout (STD_OUTPUT_HANDLE = -11)
        handle = kernel32.GetStdHandle(-11)
        if handle == -1:
            return False

        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        mode = ctypes.wintypes.DWORD()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        if mode.value & ENABLE_VIRTUAL_TERMINAL_PROCESSING:
            return True
        return bool(kernel32.SetConsoleMode(handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING))
    except Exception:
        return False


def should_use_color() -> bool:
    """Return True when colored output is appropriate.

    Respects the NO_COLOR environment variable (https://no-color.org/)
    and TERM=dumb, in addition to the existing TTY check.
    """
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    if not sys.stdout.isatty():
        return False
    return _enable_windows_ansi()


class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"


def color(text: str, *codes) -> str:
    """Apply color codes to text (only when color output is appropriate)."""
    if not should_use_color():
        return text
    return "".join(codes) + text + Colors.RESET
