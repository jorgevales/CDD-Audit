"""Antialiased nine-slice borders, retaining native ttk control behaviour."""

import base64
import math
import struct
import tkinter as tk
import zlib


def rounded_image(root, fill, outline, radius=8, background="#F5F7FB"):
    size = radius * 2 + 4
    colors = [tuple(bytes.fromhex(value.lstrip("#"))) for value in (fill, outline)]
    backdrop = tuple(bytes.fromhex(background.lstrip("#")))
    rows = bytearray()
    for y in range(size):
        rows.append(0)
        for x in range(size):
            outer = inner = 0
            for dy in (0.125, 0.375, 0.625, 0.875):
                for dx in (0.125, 0.375, 0.625, 0.875):
                    px, py = x + dx, y + dy
                    cx = min(max(px, radius), size - radius)
                    cy = min(max(py, radius), size - radius)
                    distance = math.hypot(px - cx, py - cy)
                    outer += distance <= radius
                    inner += distance <= radius - 1 and 1 <= px <= size - 1 and 1 <= py <= size - 1
            if outer:
                rgb = [round((colors[0][i] * inner + colors[1][i] * (outer - inner)
                              + backdrop[i] * (16 - outer)) / 16)
                       for i in range(3)]
                rows.extend((*rgb, 255))
            else:
                rows.extend((*backdrop, 255))
    def chunk(kind, data):
        return struct.pack("!I", len(data)) + kind + data + struct.pack("!I", zlib.crc32(kind + data))
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack("!2I5B", size, size, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(bytes(rows))) + chunk(b"IEND", b""))
    return tk.PhotoImage(master=root, data=base64.b64encode(png))


def apply_rounded_controls(root, style, colors):
    root.rounded_images = []
    def element(name, fill, border, variants, background=None):
        backdrop = background or colors["background"]
        normal = rounded_image(root, fill, border, background=backdrop)
        root.rounded_images.append(normal)
        states = []
        for state, state_fill, state_border in variants:
            image = rounded_image(root, state_fill, state_border, background=backdrop)
            root.rounded_images.append(image)
            states.append((state, image))
        style.element_create(name, "image", normal, *states, border=9, sticky="nsew")
    element("Rounded.Button", colors["paper"], colors["border"], [
        ("disabled", colors["background"], colors["border"]),
        ("focus", colors["soft_blue"], colors["blue"]),
        ("active", colors["soft_blue"], colors["blue"]),
    ])
    element("Rounded.IconCard", colors["paper"], colors["border"], [
        ("disabled", colors["paper"], colors["border"]),
        ("focus", colors["soft_blue"], colors["blue"]),
        ("active", colors["soft_blue"], colors["blue"]),
    ], background=colors["paper"])
    element("Rounded.Primary", colors["blue"], colors["blue"], [
        ("disabled", "#DFE5EE", "#DFE5EE"),
        ("focus", colors["blue_hover"], "#7494BD"),
        ("active", colors["blue_hover"], colors["blue_hover"]),
    ])
    element("Rounded.Field", colors["paper"], colors["border"], [
        ("disabled", colors["background"], colors["border"]),
        ("focus", colors["paper"], colors["blue"]),
    ], background=colors["paper"])
    for name, border in (("TButton", "Rounded.Button"), ("Primary.TButton", "Rounded.Primary")):
        style.layout(name, [(border, {"sticky": "nsew", "children": [
            ("Button.padding", {"sticky": "nsew", "children": [
                ("Button.label", {"sticky": "nsew"})]})]})])
    for name, field in (("TEntry", "Entry.field"), ("TSpinbox", "Spinbox.field"),
                        ("TCombobox", "Combobox.field")):
        def replace(layout):
            return [("Rounded.Field" if key == field else key,
                     dict(options, **({"children": replace(options["children"])}
                                      if "children" in options else {}))) for key, options in layout]
        style.layout(name, replace(style.layout(name)))
    style.layout("IconCard.TButton", [("Rounded.IconCard", {"sticky": "nsew", "children": [
        ("Button.padding", {"sticky": "nsew", "children": [("Button.label", {"sticky": "nsew"})]})]})])
    style.configure("Icon.TButton", padding=(5, 3), width=3,
                    font=(root.icon_font, 19), foreground=colors["blue"])
    style.configure("IconCard.TButton", padding=(5, 3), width=3,
                    font=(root.icon_font, 19), foreground=colors["blue"])
