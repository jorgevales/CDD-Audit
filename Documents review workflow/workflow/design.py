"""Shared visual tokens for the native Windows interface."""

import getpass
import os
import tkinter as tk
from tkinter import font as tkfont, ttk

from .fonts import load_ui_font
from .rounded import apply_rounded_controls

COLORS = {
    "blue": "#102D59", "blue_hover": "#193E72", "paper": "#FFFFFF",
    "background": "#F5F7FB", "ink": "#10233F", "muted": "#637189",
    "border": "#DFE5EF", "success": "#148361", "error": "#B2333A",
    "warning": "#966818", "soft_blue": "#E6EDF7", "header_text": "#D1DCEF",
}

GLYPHS = {"folder": "\ue8b7", "file": "\ue8a5", "settings": "\ue713",
          "check": "\ue73e", "play": "\ue768", "user": "\ue77b", "save": "\ue74e",
          "back": "\ue72b", "next": "\ue72a", "help": "\ue946", "warning": "\ue7ba",
          "search": "\ue721", "logs": "\ue9d9", "master": "\ue9f9", "stop": "\ue71a"}


def detected_user() -> str:
    if os.name == "nt":
        try:
            import ctypes
            size = ctypes.c_ulong(256)
            buffer = ctypes.create_unicode_buffer(size.value)
            if ctypes.windll.secur32.GetUserNameExW(3, buffer, ctypes.byref(size)) and buffer.value:
                return buffer.value
        except (AttributeError, OSError):
            pass
    try:
        return getpass.getuser()
    except (OSError, KeyError):
        return "Current user"


def apply_theme(root) -> None:
    root.configure(background=COLORS["background"])
    families = set(tkfont.families(root))
    root.ui_font, root.font_warning = load_ui_font(root)
    for name in tkfont.names(root):
        tkfont.nametofont(name, root=root).configure(family=root.ui_font)
    root.option_add("*TCombobox*Listbox.font", (root.ui_font, 11))
    root.icon_font = next((name for name in ("Segoe Fluent Icons", "Segoe MDL2 Assets") if name in families), root.ui_font)
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", font=(root.ui_font, 11), background=COLORS["background"],
                    foreground=COLORS["ink"])
    style.configure("TFrame", background=COLORS["background"])
    style.configure("Card.TFrame", background=COLORS["paper"])
    style.configure("Background.TFrame", background=COLORS["background"])
    style.configure("TLabel", background=COLORS["background"])
    style.configure("Title.TLabel", font=(root.ui_font, 25, "bold"))
    style.configure("Section.TLabel", font=(root.ui_font, 13, "bold"))
    style.configure("Field.TLabel", font=(root.ui_font, 11, "bold"), background=COLORS["paper"])
    style.configure("Card.TLabel", background=COLORS["paper"])
    style.configure("Metric.TLabel", font=(root.ui_font, 22, "bold"), background=COLORS["paper"])
    style.configure("CardSmall.TLabel", font=(root.ui_font, 9), background=COLORS["paper"], foreground=COLORS["muted"])
    style.configure("Muted.TLabel", foreground=COLORS["muted"])
    style.configure("Small.TLabel", font=(root.ui_font, 9), foreground=COLORS["muted"])
    style.configure("TButton", padding=(16, 5), background=COLORS["paper"],
                    bordercolor=COLORS["border"], focusthickness=2, focuscolor=COLORS["blue"])
    style.map("TButton", background=[("active", COLORS["soft_blue"])],
              foreground=[("disabled", "#8590A1")])
    style.configure("Primary.TButton", background=COLORS["blue"], foreground="white",
                    bordercolor=COLORS["blue"], font=(root.ui_font, 11, "bold"))
    style.map("Primary.TButton", background=[("disabled", "#DFE5EE"),
              ("active", COLORS["blue_hover"])], foreground=[("disabled", "#677488")])
    style.configure("TEntry", padding=(8, 5), fieldbackground=COLORS["paper"],
                    bordercolor=COLORS["border"], lightcolor=COLORS["border"],
                    darkcolor=COLORS["border"])
    style.map("TEntry", bordercolor=[("focus", COLORS["blue"])])
    style.configure("TSpinbox", padding=(8, 3), arrowsize=14, fieldbackground=COLORS["paper"])
    style.configure("TCombobox", padding=(8, 3), arrowsize=14)
    style.map("TCombobox", fieldbackground=[("readonly", COLORS["paper"])],
              selectbackground=[("readonly", COLORS["paper"])],
              selectforeground=[("readonly", COLORS["ink"])])
    style.configure("TCheckbutton", padding=(0, 5), background=COLORS["paper"])
    style.configure("Treeview", rowheight=36, borderwidth=0, background=COLORS["paper"],
                    fieldbackground=COLORS["paper"])
    style.configure("Treeview.Heading", font=(root.ui_font, 10, "bold"),
                    background=COLORS["background"], padding=(10, 10))
    style.map("Treeview", background=[("selected", COLORS["soft_blue"])],
              foreground=[("selected", COLORS["ink"])])
    style.configure("Horizontal.TProgressbar", background=COLORS["blue"],
                    troughcolor=COLORS["background"], borderwidth=0, thickness=3)
    apply_rounded_controls(root, style, COLORS)


class Tooltip:
    def __init__(self, widget, text):
        self.widget, self.text, self.window, self.job = widget, text, None, None
        widget.bind("<Enter>", self.schedule, add=True)
        widget.bind("<FocusIn>", self.schedule, add=True)
        widget.bind("<Leave>", self.hide, add=True)
        widget.bind("<FocusOut>", self.hide, add=True)
        widget.bind("<Destroy>", self.hide, add=True)

    def schedule(self, _=None):
        self.hide()
        self.job = self.widget.after(450, self.show)

    def show(self):
        self.job = None
        self.window = tk.Toplevel(self.widget)
        self.window.overrideredirect(True)
        self.window.configure(bg=COLORS["blue"])
        tk.Label(self.window, text=self.text, bg=COLORS["blue"], fg="white",
                 font=(self.widget.winfo_toplevel().ui_font, 10), wraplength=300,
                 padx=12, pady=8).pack()
        self.window.update_idletasks()
        x = min(self.widget.winfo_rootx(), self.widget.winfo_screenwidth() - self.window.winfo_reqwidth() - 12)
        y = min(self.widget.winfo_rooty() + self.widget.winfo_height() + 6,
                self.widget.winfo_screenheight() - self.window.winfo_reqheight() - 12)
        self.window.geometry(f"+{max(0, x)}+{max(0, y)}")

    def hide(self, _=None):
        if self.job:
            self.widget.after_cancel(self.job)
            self.job = None
        if self.window:
            self.window.destroy()
            self.window = None


def icon_button(parent, root, name, command, label, background=None):
    button = ttk.Button(parent, text=GLYPHS[name], command=command,
                        style="Icon.TButton" if background else "IconCard.TButton",
                        cursor="hand2", takefocus=True)
    Tooltip(button, label)
    return button


class Surface(tk.Canvas):
    def __init__(self, parent, padding=28):
        super().__init__(parent, bg=COLORS["background"], highlightthickness=0, height=140)
        self.padding = padding
        self.inner = ttk.Frame(self, style="Card.TFrame")
        self.window = self.create_window(padding, padding, anchor="nw", window=self.inner)
        self.bind("<Configure>", self.resize)
        self.inner.bind("<Configure>", self.fit)

    def fit(self, _=None):
        height = self.inner.winfo_reqheight() + 2 * self.padding
        if self.winfo_reqheight() != height:
            self.configure(height=height)

    def resize(self, event):
        w, h, r = event.width - 1, event.height - 1, 16
        self.delete("surface")
        self.create_polygon(r, 1, w-r, 1, w, 1, w, r, w, h-r, w, h,
                            w-r, h, r, h, 1, h, 1, h-r, 1, r, 1, 1,
                            smooth=True, fill=COLORS["paper"], outline=COLORS["border"], tags="surface")
        self.tag_lower("surface")
        self.itemconfigure(self.window, width=max(1, w - 2 * self.padding))


class Stepper(tk.Canvas):
    def __init__(self, parent, root, command):
        super().__init__(parent, height=64, bg=COLORS["background"], highlightthickness=0,
                         takefocus=True, cursor="hand2")
        self.root, self.command, self.step, self.selected = root, command, 0, 0
        self.enabled = True
        self.complete = set()
        self.bind("<Configure>", lambda _: self.draw())
        self.bind("<Button-1>", self.click)
        self.bind("<Left>", lambda _: self.move(-1))
        self.bind("<Right>", lambda _: self.move(1))
        self.bind("<Return>", lambda _: self.activate())
        self.bind("<space>", lambda _: self.activate())
        self.bind("<FocusIn>", lambda _: self.draw())
        self.bind("<FocusOut>", lambda _: self.draw())

    def move(self, change):
        self.selected = max(0, min(5, self.selected + change))
        self.draw()

    def activate(self):
        if self.enabled:
            self.command(self.selected)

    def click(self, event):
        self.selected = min(5, max(0, int(event.x / max(1, self.winfo_width() / 6))))
        self.focus_set()
        self.activate()

    def draw(self):
        self.delete("all")
        unit = self.winfo_width() / 6
        for index, title in enumerate(("Sources", "Outputs", "Review", "Preferences", "Checks", "Run")):
            x = unit * (index + 0.5)
            if index < 5:
                passed = index in self.complete and (index + 1 in self.complete or index + 1 == self.step)
                self.create_line(x + 14, 17, x + unit - 14, 17, fill=COLORS["blue"] if passed else COLORS["border"], width=1)
            active = index == self.step or index in self.complete
            fill = COLORS["blue"] if active else COLORS["background"]
            self.create_oval(x-13, 4, x+13, 30, fill=fill, outline=COLORS["blue"] if active else COLORS["border"])
            done = index in self.complete and index != self.step
            self.create_text(x, 17, text=GLYPHS["check"] if done else str(index+1),
                             font=(self.root.icon_font if done else self.root.ui_font, 10, "bold"),
                             fill="white" if active else COLORS["muted"])
            self.create_text(x, 45, text=title, font=(self.root.ui_font, 9), fill=COLORS["blue"] if active else COLORS["muted"])
            if self.focus_get() == self and index == self.selected:
                self.create_rectangle(x-17, 1, x+17, 33, outline=COLORS["blue"], dash=(2, 2))


def blend(color, background, amount):
    a, b = color.lstrip("#"), background.lstrip("#")
    return "#" + "".join(f"{round(int(a[i:i+2], 16) * amount + int(b[i:i+2], 16) * (1-amount)):02x}" for i in (0, 2, 4))


class ContentFade:
    """Fade page colors while leaving the header and top progress stable."""
    def __init__(self, root):
        self.root, self.job, self.records = root, None, []
        self.style = ttk.Style(root)
        self.styles = {}

    def capture(self, parents):
        records = []
        def visit(widget):
            if isinstance(widget, ttk.Widget):
                original = widget.cget("style") or widget.winfo_class()
                clone = self.styles.setdefault(widget, f"Fade{len(self.styles)}.{original}")
                colors = {key: self.style.lookup(original, key) for key in
                          ("foreground", "background", "fieldbackground", "bordercolor")}
                colors = {key: value for key, value in colors.items() if isinstance(value, str) and re_color(value)}
                records.append((widget, original, clone, colors))
            elif isinstance(widget, (tk.Label, tk.Button)):
                colors = {key: widget.cget(key) for key in ("foreground", "background")}
                records.append((widget, None, None, colors))
            elif isinstance(widget, tk.Canvas):
                for item in widget.find_all():
                    kind = widget.type(item)
                    if kind in {"oval", "polygon", "rectangle", "line", "text"}:
                        keys = ("fill",) if kind in {"line", "text"} else ("fill", "outline")
                        colors = {key: widget.itemcget(item, key) for key in keys}
                        colors = {key: value for key, value in colors.items() if re_color(value)}
                        records.append((widget, ("canvas", item), None, colors))
            for child in widget.winfo_children():
                visit(child)
        for parent in parents:
            visit(parent)
        return records

    def paint(self, amount):
        for widget, original, clone, colors in self.records:
            tinted = {key: blend(value, COLORS["background"], amount) for key, value in colors.items()}
            if isinstance(original, tuple):
                if widget.type(original[1]):
                    widget.itemconfigure(original[1], **tinted)
            elif original:
                self.style.configure(clone, **tinted)
                self.style.map(clone, foreground=[], background=[])
                widget.configure(style=clone)
            else:
                widget.configure(**tinted)

    def restore(self):
        for widget, original, _, colors in self.records:
            if widget.winfo_exists():
                if isinstance(original, tuple):
                    if widget.type(original[1]):
                        widget.itemconfigure(original[1], **colors)
                else:
                    widget.configure(style=original) if original else widget.configure(**colors)
        self.records = []

    def cancel(self):
        if self.job:
            self.root.after_cancel(self.job)
            self.job = None
        self.restore()

    def play(self, parents, swap, incoming, finish):
        self.cancel()
        self.records = self.capture(parents)
        def tick(frame):
            self.job = None
            if frame == 5:
                self.restore()
                swap()
                self.records = self.capture(incoming())
            amount = 1 - frame / 5 if frame <= 5 else (frame - 5) / 5
            self.paint(amount)
            if frame < 10:
                self.job = self.root.after(16, lambda: tick(frame + 1))
            else:
                self.restore()
                finish()
        tick(0)


def re_color(value):
    return len(value) == 7 and value.startswith("#") and all(c in "0123456789abcdefABCDEF" for c in value[1:])


def compact_confirm(root, title, message, action="Continue", details="", required_text=None, cancel_label="Cancel"):
    dialog = tk.Toplevel(root)
    dialog.title(title)
    dialog.transient(root)
    dialog.resizable(False, False)
    dialog.configure(bg=COLORS["background"])
    result = [False]
    body = ttk.Frame(dialog, padding=28)
    body.pack(fill="both", expand=True)
    tk.Label(body, text=GLYPHS["warning"], font=(root.icon_font, 28),
             bg=COLORS["background"], fg=COLORS["blue"]).pack(pady=(0, 12))
    ttk.Label(body, text=title, style="Section.TLabel", anchor="center").pack(fill="x")
    ttk.Label(body, text=message, wraplength=390, justify="center", style="Muted.TLabel").pack(pady=14)
    if details:
        detail_text = tk.Text(body, height=5, width=48, wrap="word", font=(root.ui_font, 9),
                              bg=COLORS["paper"], fg=COLORS["muted"], relief="flat", padx=10, pady=8)
        detail_text.insert("1.0", details)
        detail_text.configure(state="disabled")
        def reveal():
            if detail_text.winfo_manager():
                detail_text.pack_forget()
            else:
                detail_text.pack(before=actions, fill="x", pady=(0, 12))
            center()
        ttk.Button(body, text="View files", command=reveal).pack(pady=(0, 8))
    variable = tk.StringVar()
    if required_text:
        ttk.Label(body, text=f"Type {required_text} to confirm", style="Small.TLabel").pack(pady=(0, 6))
        entry = ttk.Entry(body, textvariable=variable, justify="center")
        entry.pack(fill="x", pady=(0, 16))
    actions = ttk.Frame(body)
    actions.pack(fill="x", pady=(6, 0))
    def accept():
        if not required_text or variable.get() == required_text:
            result[0] = True
            dialog.destroy()
    if cancel_label:
        ttk.Button(actions, text=cancel_label, command=dialog.destroy).pack(side="left")
    primary = ttk.Button(actions, text=action, style="Primary.TButton", command=accept,
                         state="disabled" if required_text else "normal")
    primary.pack(side="right")
    variable.trace_add("write", lambda *_: primary.configure(state="normal" if variable.get() == required_text else "disabled"))
    dialog.bind("<Escape>", lambda _: dialog.destroy())
    dialog.bind("<Return>", lambda _: accept())
    def center():
        dialog.update_idletasks()
        width, height = dialog.winfo_reqwidth(), dialog.winfo_reqheight()
        dialog.geometry(f"{width}x{height}+{root.winfo_rootx() + (root.winfo_width()-width)//2}+{root.winfo_rooty() + (root.winfo_height()-height)//2}")
    center()
    dialog.grab_set()
    (entry if required_text else primary).focus_set()
    root.wait_window(dialog)
    return result[0]
