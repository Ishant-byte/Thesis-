from __future__ import annotations

import random
import tkinter as tk
from tkinter import ttk

class AnimatedBackground(tk.Canvas):
    def __init__(self, master, theme: dict, **kwargs):
        super().__init__(master, highlightthickness=0, bd=0, **kwargs)
        self.theme = theme
        self.particles = []
        self.running = False

    def start(self):
        if self.running:
            return
        self.running = True
        self._init_particles()
        self._tick()

    def stop(self):
        self.running = False

    def _init_particles(self):
        self.delete("all")
        w = max(600, self.winfo_width())
        h = max(400, self.winfo_height())
        self.particles = []
        for _ in range(40):
            x = random.randint(0, w)
            y = random.randint(0, h)
            r = random.randint(2, 6)
            dx = random.uniform(-0.6, 0.6)
            dy = random.uniform(-0.6, 0.6)
            self.particles.append([x,y,r,dx,dy])

    def _draw_gradient(self, w, h):
        # simple vertical gradient by drawing rectangles
        self.delete("grad")
        steps = 40
        c0 = self.theme["bg0"]
        c1 = self.theme["bg1"]
        def hex_to_rgb(c):
            c=c.lstrip("#")
            return tuple(int(c[i:i+2],16) for i in (0,2,4))
        def rgb_to_hex(rgb):
            return "#%02x%02x%02x"%rgb
        r0,g0,b0 = hex_to_rgb(c0)
        r1,g1,b1 = hex_to_rgb(c1)
        for i in range(steps):
            t = i/(steps-1)
            r = int(r0 + (r1-r0)*t)
            g = int(g0 + (g1-g0)*t)
            b = int(b0 + (b1-b0)*t)
            y0 = int(h*i/steps)
            y1 = int(h*(i+1)/steps)
            self.create_rectangle(0,y0,w,y1, fill=rgb_to_hex((r,g,b)), outline="", tags="grad")

    def _tick(self):
        if not self.running:
            return
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 10 or h < 10:
            self.after(50, self._tick)
            return
        self._draw_gradient(w,h)
        self.delete("p")
        for p in self.particles:
            p[0] += p[3]
            p[1] += p[4]
            if p[0] < 0: p[0] = w
            if p[0] > w: p[0] = 0
            if p[1] < 0: p[1] = h
            if p[1] > h: p[1] = 0
            x,y,r = p[0],p[1],p[2]
            self.create_oval(x-r,y-r,x+r,y+r, fill=self.theme["accent2"], outline="", tags="p")
        self.after(40, self._tick)

def style_button(btn: tk.Widget, theme: dict):
    def on_enter(e):
        btn.configure(bg=theme["accent2"])
    def on_leave(e):
        btn.configure(bg=theme["accent"])
    btn.bind("<Enter>", on_enter)
    btn.bind("<Leave>", on_leave)

def make_label(master, text, theme, size=12, bold=False):
    font = ("Segoe UI", size, "bold" if bold else "normal")
    return tk.Label(master, text=text, fg=theme["text"], bg=theme.get("panel", theme["bg0"]), font=font)

def make_entry(master, theme, show=None):
    e = tk.Entry(master, fg=theme["text"], bg=theme["bg0"], insertbackground=theme["text"], relief="flat", highlightthickness=1, highlightbackground=theme["accent"], highlightcolor=theme["accent2"], show=show)
    return e

def make_button(master, text, theme, command):
    b = tk.Button(master, text=text, command=command, fg=theme["text"], bg=theme["accent"], activebackground=theme["accent2"], activeforeground=theme["text"], relief="flat", padx=14, pady=8, font=("Segoe UI", 11, "bold"))
    style_button(b, theme)
    return b


class ScrollableFrame(tk.Frame):
    """A simple scrollable container for long forms.

    Tkinter has no native scrollable Frame; this wraps a Frame in a Canvas.
    """

    def __init__(self, master, bg: str, width: int | None = None, height: int | None = None):
        super().__init__(master, bg=bg)

        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.vsb = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)

        self.vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        if width:
            self.canvas.configure(width=width)
        if height:
            self.canvas.configure(height=height)

        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.inner.bind("<Configure>", self._on_configure)
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        # Mouse wheel scroll support
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)  # Windows
        self.canvas.bind_all("<Button-4>", self._on_mousewheel)    # Linux
        self.canvas.bind_all("<Button-5>", self._on_mousewheel)

    def _on_configure(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_resize(self, event):
        # Keep inner frame width synced to canvas width
        self.canvas.itemconfigure(self._win, width=event.width)

    def _on_mousewheel(self, event):
        # Only scroll when pointer is over this widget
        try:
            x, y = self.winfo_pointerxy()
            w = self.winfo_containing(x, y)
            if w is None:
                return
            if not str(w).startswith(str(self.canvas)) and not str(w).startswith(str(self.inner)):
                return
        except Exception:
            return

        if event.num == 4:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.canvas.yview_scroll(1, "units")
        else:
            # Windows delta is 120 per notch
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
