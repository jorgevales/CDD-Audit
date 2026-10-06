"""Load genuine, locally licensed Aptos faces without changing Windows settings."""

import ctypes
import hashlib
import os
from pathlib import Path
from tkinter import font as tkfont

FONT_HASHES = {
    "Aptos.ttf": "01bbd2d3bd483045e1dbf4f106935cb86478b937f8d334258ad12eea60554a05",
    "Aptos-Bold.ttf": "ae318584be8737164e24842e0b27ab180ee6761c1bedd799f5a29c93a8a4e65c",
}


def font_directory():
    base = os.environ.get("LOCALAPPDATA")
    return Path(base) / "CDDAuditRemediation" / "fonts" / "Aptos-4.40" if base else None


def private_font_api():
    gdi = ctypes.WinDLL("gdi32", use_last_error=True)
    for name in ("AddFontResourceExW", "RemoveFontResourceExW"):
        function = getattr(gdi, name)
        function.argtypes = (ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p)
        function.restype = ctypes.c_int
    return gdi


def load_ui_font(root):
    root.private_fonts = []
    families = set(tkfont.families(root))
    if "Aptos" not in families and os.name == "nt":
        directory = font_directory()
        try:
            if directory is not None:
                # Validate both faces before loading either; no shared writable font cache.
                paths = [directory / name for name in FONT_HASHES]
                if all(hashlib.sha256(path.read_bytes()).hexdigest() == FONT_HASHES[path.name]
                       for path in paths):
                    api = private_font_api()
                    for path in paths:
                        if not api.AddFontResourceExW(str(path), 0x10, None):
                            raise OSError("Windows could not load the private font")
                        root.private_fonts.append(path)
                    families = set(tkfont.families(root))
        except (OSError, AttributeError):
            release_ui_fonts(root)
    if "Aptos" in families:
        # Check the actual selected face, not just a requested family name.
        if tkfont.Font(root=root, family="Aptos", size=11).actual("family") == "Aptos":
            return "Aptos", ""
    fallback = next((name for name in ("Segoe UI Variable Text", "Segoe UI", "Arial")
                     if name in families), "TkDefaultFont")
    return fallback, "Aptos unavailable. Double-click Install Aptos.cmd and reopen. Using the Windows font for now."


def release_ui_fonts(root):
    paths = getattr(root, "private_fonts", [])
    if paths:
        try:
            api = private_font_api()
            for path in paths:
                api.RemoveFontResourceExW(str(path), 0x10, None)
        except (OSError, AttributeError):
            pass
        paths.clear()
