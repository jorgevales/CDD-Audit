"""Shared visual tokens for the native Windows interface."""

from tkinter import ttk

COLORS = {
    "blue": "#194FB5", "blue_hover": "#123D91", "rail": "#123579",
    "rail_active": "#2453A2", "rail_text": "#C9D9F5", "paper": "#FFFFFF",
    "background": "#F3F5F8", "ink": "#202B3C", "muted": "#586579",
    "border": "#D8DFE9", "success": "#16734B", "error": "#B2333A",
    "warning": "#916013", "soft_blue": "#EAF0FC",
}


def apply_theme(root) -> None:
    root.configure(background=COLORS["background"])
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", font=("Segoe UI", 10), background=COLORS["paper"],
                    foreground=COLORS["ink"])
    style.configure("TFrame", background=COLORS["paper"])
    style.configure("Background.TFrame", background=COLORS["background"])
    style.configure("TLabel", background=COLORS["paper"])
    style.configure("Title.TLabel", font=("Segoe UI", 22, "bold"))
    style.configure("Section.TLabel", font=("Segoe UI", 12, "bold"))
    style.configure("Field.TLabel", font=("Segoe UI", 10, "bold"))
    style.configure("Muted.TLabel", foreground=COLORS["muted"])
    style.configure("Small.TLabel", font=("Segoe UI", 9), foreground=COLORS["muted"])
    style.configure("TButton", padding=(14, 9), background=COLORS["paper"],
                    bordercolor=COLORS["border"], focusthickness=2, focuscolor=COLORS["blue"])
    style.map("TButton", background=[("active", COLORS["soft_blue"])],
              foreground=[("disabled", "#8590A1")])
    style.configure("Primary.TButton", background=COLORS["blue"], foreground="white",
                    bordercolor=COLORS["blue"], font=("Segoe UI", 10, "bold"))
    style.map("Primary.TButton", background=[("disabled", "#DFE5EE"),
              ("active", COLORS["blue_hover"])], foreground=[("disabled", "#677488")])
    style.configure("TEntry", padding=8, fieldbackground=COLORS["paper"],
                    bordercolor=COLORS["border"], lightcolor=COLORS["border"],
                    darkcolor=COLORS["border"])
    style.map("TEntry", bordercolor=[("focus", COLORS["blue"])])
    style.configure("TSpinbox", padding=7, arrowsize=14, fieldbackground=COLORS["paper"])
    style.configure("TCombobox", padding=7, arrowsize=14)
    style.map("TCombobox", fieldbackground=[("readonly", COLORS["paper"])],
              selectbackground=[("readonly", COLORS["paper"])],
              selectforeground=[("readonly", COLORS["ink"])])
    style.configure("TCheckbutton", padding=(0, 5), background=COLORS["paper"])
    style.configure("Treeview", rowheight=36, borderwidth=0, background=COLORS["paper"],
                    fieldbackground=COLORS["paper"])
    style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"),
                    background=COLORS["background"], padding=(10, 10))
    style.map("Treeview", background=[("selected", COLORS["soft_blue"])],
              foreground=[("selected", COLORS["ink"])])
    style.configure("Horizontal.TProgressbar", background=COLORS["blue"],
                    troughcolor=COLORS["soft_blue"], borderwidth=0, thickness=5)
