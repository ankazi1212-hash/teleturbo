from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Optional

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext

from telethon.errors import SessionPasswordNeededError

from .client import TGClient
from .downloader import DownloadQueue, DownloadItem, DownloadStatus
from .config import Config

CHECKED = "\u2611"
UNCHECKED = "\u2610"

LIGHT = {
    "header_bg": "#2b5278",
    "header_fg": "#ffffff",
    "sidebar_bg": "#17212b",
    "sidebar_hover": "#1e2c3a",
    "sidebar_active_bg": "#242f3d",
    "sidebar_accent": "#3390ec",
    "sidebar_fg": "#ffffff",
    "sidebar_fg_muted": "#8e9aa9",
    "content_bg": "#e8edf2",
    "card_bg": "#ffffff",
    "accent": "#3390ec",
    "accent_hover": "#2b7ad0",
    "text_primary": "#222222",
    "text_secondary": "#556472",
    "text_muted": "#8e9aa9",
    "input_border": "#ccd4db",
    "border": "#dae1e7",
    "status_bg": "#15202b",
    "status_fg": "#7a8a9a",
    "success": "#4cae4f",
    "danger": "#e53935",
    "warning": "#f5a623",
}

DARK = {
    "header_bg": "#1a2332",
    "header_fg": "#f0f6fc",
    "sidebar_bg": "#0f1419",
    "sidebar_hover": "#151d27",
    "sidebar_active_bg": "#1a2332",
    "sidebar_accent": "#3390ec",
    "sidebar_fg": "#f0f6fc",
    "sidebar_fg_muted": "#b0bac5",
    "content_bg": "#0b0e11",
    "card_bg": "#151d27",
    "accent": "#3390ec",
    "accent_hover": "#2b7ad0",
    "text_primary": "#f0f6fc",
    "text_secondary": "#b0bac5",
    "text_muted": "#8b949e",
    "input_border": "#3d4a5c",
    "border": "#263040",
    "status_bg": "#070a0d",
    "status_fg": "#b0bac5",
    "success": "#4cae4f",
    "danger": "#e53935",
    "warning": "#f5a623",
}

C = {**DARK}  # copy, not alias — so C.update(LIGHT) doesn't corrupt DARK
SIDEBAR_W = 230


class TeleTurboGUI:
    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        self.root = tk.Tk()
        self.root.title("TeleTurbo")
        self.root.geometry("1100x720")
        self.root.minsize(900, 560)
        self.root.configure(bg=C["content_bg"])

        self.config = Config()
        self.client: Optional[TGClient] = None
        self.download_queue: Optional[DownloadQueue] = None
        self._dialogs_data: list = []
        self._video_cache: dict[int, list] = {}
        self._download_items_by_group: dict[str, list] = {}
        self._authorized = False
        self._update_throttle: dict[int, float] = {}
        self._sidebar_buttons: list = []
        self._content_frames: list = []
        self._active_section = 0
        self._dl_item_ids: set[str] = set()

        self.is_dark = getattr(self.config, 'dark_mode', True)
        C.clear()
        C.update(DARK if self.is_dark else LIGHT)

        self._configure_styles()
        self._build_ui()
        self._setup_protocols()
        self._load_config_to_ui()

        self.root.bind("<Control-l>", lambda e: self._show_section(0))
        self.root.bind("<Control-g>", lambda e: self._show_section(1))
        self.root.bind("<Control-d>", lambda e: self._show_section(2))
        self.root.bind("<Delete>", lambda e: self._on_remove_selected())
        self.root.bind("<space>", self._on_space_key)

    def _configure_styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Treeview", background=C["card_bg"], fieldbackground=C["card_bg"],
                        foreground=C["text_primary"], rowheight=36, borderwidth=0,
                        font=("Segoe UI", 10))
        style.configure("Treeview.Heading", background=C["content_bg"],
                        foreground=C["text_secondary"], font=("Segoe UI", 9, "bold"),
                        borderwidth=0, relief="flat")
        style.map("Treeview.Heading", background=[("active", C["border"])])
        style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        style.configure("Vertical.TScrollbar", background=C["card_bg"],
                        troughcolor=C["content_bg"], bordercolor=C["border"],
                        arrowcolor=C["text_secondary"], relief="flat", borderwidth=0)
        style.configure("TEntry", fieldbackground=C["card_bg"], borderwidth=0,
                        foreground=C["text_primary"], font=("Segoe UI", 10))
        style.configure("TButton", background=C["accent"], foreground="#ffffff",
                        font=("Segoe UI", 10), borderwidth=0, focusthickness=0)
        style.map("TButton", background=[("active", C["accent_hover"]),
                                          ("disabled", "#b0c4de")])
        style.configure("TLabel", background=C["card_bg"], foreground=C["text_primary"],
                        font=("Segoe UI", 10))
        style.configure("TLabelframe", background=C["card_bg"], borderwidth=0)
        style.configure("TLabelframe.Label", background=C["card_bg"],
                        foreground=C["text_secondary"], font=("Segoe UI", 9, "bold"))

    # ----------------------------------------------------------------
    # Master UI
    # ----------------------------------------------------------------
    def _build_ui(self):
        self._build_header()
        self.body = tk.Frame(self.root, bg=C["content_bg"])
        self.body.pack(fill=tk.BOTH, expand=True)
        self._build_sidebar()
        self._build_content()
        self._build_status_bar()

    def _build_header(self):
        h = tk.Frame(self.root, bg=C["header_bg"], height=48)
        h.pack(fill=tk.X)
        h.pack_propagate(False)
        tk.Label(h, text="TeleTurbo", font=("Segoe UI", 15, "bold"),
                 bg=C["header_bg"], fg=C["header_fg"]).pack(side=tk.LEFT, padx=(18, 0), pady=10)
        tk.Label(h, text="Telegram Video Downloader", font=("Segoe UI", 10),
                 bg=C["header_bg"], fg=C["header_fg"]).pack(side=tk.LEFT, padx=(10, 0), pady=10)

    def _build_status_bar(self):
        s = tk.Frame(self.root, bg=C["status_bg"], height=28)
        s.pack(fill=tk.X, side=tk.BOTTOM)
        s.pack_propagate(False)
        self.status_var = tk.StringVar(value="Ready")
        self.status_icon_var = tk.StringVar(value="\u25CF")
        tk.Label(s, textvariable=self.status_icon_var, font=("Segoe UI", 8),
                 bg=C["status_bg"], fg=C["success"]).pack(side=tk.LEFT, padx=(10, 2))
        tk.Label(s, textvariable=self.status_var, font=("Segoe UI", 9),
                 bg=C["status_bg"], fg=C["status_fg"]).pack(side=tk.LEFT, padx=(0, 10))

    # ----------------------------------------------------------------
    # Sidebar
    # ----------------------------------------------------------------
    def _build_sidebar(self):
        sb = tk.Frame(self.body, bg=C["sidebar_bg"], width=SIDEBAR_W)
        sb.pack(side=tk.LEFT, fill=tk.Y)
        sb.pack_propagate(False)

        nav_items = [
            ("\u2691", "Login"),
            ("\u2709", "Groups"),
            ("\u2913", "Downloads"),
        ]

        for idx, (icon, label) in enumerate(nav_items):
            self._sidebar_buttons.append(self._make_nav_item(sb, icon, label, idx))

        tk.Frame(sb, bg=C["sidebar_bg"]).pack(fill=tk.BOTH, expand=True)

        self.theme_btn = tk.Label(sb, text="\u263E", font=("Segoe UI", 16),
                                   bg=C["sidebar_bg"], fg=C["sidebar_fg_muted"],
                                   cursor="hand2")
        self.theme_btn.pack(side=tk.BOTTOM, pady=(0, 2))
        self.theme_btn.bind("<Button-1>", lambda e: self._toggle_theme())
        ver = tk.Label(sb, text="v1.0", font=("Segoe UI", 8),
                       bg=C["sidebar_bg"], fg=C["sidebar_fg_muted"])
        ver.pack(side=tk.BOTTOM, pady=(0, 10))

        self._set_nav_active(0)

    def _make_nav_item(self, parent, icon, label, idx):
        f = tk.Frame(parent, bg=C["sidebar_bg"], cursor="hand2", height=46)
        f.pack(fill=tk.X)
        f.pack_propagate(False)

        accent = tk.Frame(f, width=3, bg=C["sidebar_bg"])
        accent.pack(side=tk.LEFT, fill=tk.Y)

        icon_lbl = tk.Label(f, text=icon, font=("Segoe UI", 16),
                            bg=C["sidebar_bg"], fg=C["sidebar_fg"])
        icon_lbl.pack(side=tk.LEFT, padx=(18, 10), pady=10)

        text_lbl = tk.Label(f, text=label, font=("Segoe UI", 13),
                            bg=C["sidebar_bg"], fg=C["sidebar_fg"],
                            anchor=tk.W)
        text_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=10)

        data = {"frame": f, "accent": accent, "icon": icon_lbl, "text": text_lbl, "idx": idx}
        for w in (f, icon_lbl, text_lbl, accent):
            w.bind("<Button-1>", lambda e, i=idx: self._show_section(i))
            w.bind("<Enter>", lambda e, d=data: self._nav_hover(d, True))
            w.bind("<Leave>", lambda e, d=data: self._nav_hover(d, False))
        return data

    def _nav_hover(self, data, enter):
        if data["idx"] == self._active_section:
            return
        bg = C["sidebar_hover"] if enter else C["sidebar_bg"]
        data["frame"].configure(bg=bg)
        data["icon"].configure(bg=bg)
        data["text"].configure(bg=bg)

    def _set_nav_active(self, idx):
        for d in self._sidebar_buttons:
            active = d["idx"] == idx
            bg = C["sidebar_active_bg"] if active else C["sidebar_bg"]
            abg = C["sidebar_accent"] if active else C["sidebar_bg"]
            d["frame"].configure(bg=bg)
            d["accent"].configure(bg=abg)
            d["icon"].configure(bg=bg)
            d["text"].configure(bg=bg, fg=C["sidebar_fg"])
        self._active_section = idx

    def _show_section(self, idx):
        for f in self._content_frames:
            f.pack_forget()
        self._content_frames[idx].pack(fill=tk.BOTH, expand=True)
        self._set_nav_active(idx)

    # ----------------------------------------------------------------
    # Content area
    # ----------------------------------------------------------------
    def _build_content(self):
        c = tk.Frame(self.body, bg=C["content_bg"])
        c.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.content_login = tk.Frame(c, bg=C["content_bg"])
        self.content_groups = tk.Frame(c, bg=C["content_bg"])
        self.content_downloads = tk.Frame(c, bg=C["content_bg"])
        self._content_frames = [self.content_login, self.content_groups, self.content_downloads]

        self._build_login_section()
        self._build_groups_section()
        self._build_downloads_section()
        self._show_section(0)

    # ----------------------------------------------------------------
    # Cards helper
    # ----------------------------------------------------------------
    def _card(self, parent, **kw):
        f = tk.Frame(parent, bg=C["card_bd"] if "bd" in kw else C["card_bg"],
                     highlightbackground=C["input_border"],
                     highlightthickness=1, highlightcolor=C["input_border"])
        if "pad" in kw:
            padding = int(kw["pad"])
            f.pack(fill=kw.get("fill", tk.X), padx=padding, pady=padding)
        return f

    # ================================================================
    # LOGIN SECTION
    # ================================================================
    def _build_login_section(self):
        p = self.content_login

        # Scrollable area
        canvas = tk.Canvas(p, bg=C["content_bg"], highlightthickness=0)
        vsb = ttk.Scrollbar(p, orient=tk.VERTICAL, command=canvas.yview)
        scroll_f = tk.Frame(canvas, bg=C["content_bg"])
        scroll_f.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_f, anchor="nw", width=canvas.winfo_width())
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        def _resize_canvas(e):
            canvas.itemconfig(1, width=e.width)
        canvas.bind("<Configure>", _resize_canvas)

        f = scroll_f

        # Card: API
        card1 = tk.Frame(f, bg=C["card_bg"], highlightbackground=C["border"],
                         highlightthickness=1)
        card1.pack(fill=tk.X, padx=24, pady=(24, 8))

        tk.Label(card1, text="API Configuration", font=("Segoe UI", 13, "bold"),
                 bg=C["card_bg"], fg=C["text_primary"]).pack(anchor=tk.W, padx=18, pady=(14, 4))
        tk.Label(card1, text="Get your credentials from my.telegram.org/apps",
                 font=("Segoe UI", 9), bg=C["card_bg"], fg=C["text_muted"]
                 ).pack(anchor=tk.W, padx=18, pady=(0, 10))

        row = tk.Frame(card1, bg=C["card_bg"])
        row.pack(fill=tk.X, padx=18, pady=(0, 6))
        tk.Label(row, text="API ID", font=("Segoe UI", 10), bg=C["card_bg"],
                 fg=C["text_primary"], width=10, anchor=tk.W).pack(side=tk.LEFT)
        self.api_id_var = tk.StringVar()
        e1 = tk.Entry(row, textvariable=self.api_id_var, font=("Segoe UI", 10),
                       bg=C["card_bg"], fg=C["text_primary"], bd=0,
                       highlightbackground=C["input_border"], highlightthickness=1,
                       highlightcolor=C["accent"], width=25)
        e1.pack(side=tk.LEFT, padx=(0, 20), ipady=4, ipadx=4)

        tk.Label(row, text="API Hash", font=("Segoe UI", 10), bg=C["card_bg"],
                 fg=C["text_primary"], width=10, anchor=tk.W).pack(side=tk.LEFT)
        self.api_hash_var = tk.StringVar()
        e2 = tk.Entry(row, textvariable=self.api_hash_var, font=("Segoe UI", 10),
                       bg=C["card_bg"], fg=C["text_primary"], bd=0,
                       highlightbackground=C["input_border"], highlightthickness=1,
                       highlightcolor=C["accent"], width=35)
        e2.pack(side=tk.LEFT, ipady=4, ipadx=4)

        btn_save = tk.Button(card1, text="Save", font=("Segoe UI", 10),
                              bg=C["accent"], fg="#ffffff", bd=0, padx=20, pady=4,
                              activebackground=C["accent_hover"], activeforeground="#ffffff",
                              cursor="hand2", command=self._on_save_config)
        btn_save.pack(anchor=tk.W, padx=18, pady=(10, 14))

        # Card: Auth
        card2 = tk.Frame(f, bg=C["card_bg"], highlightbackground=C["border"],
                         highlightthickness=1)
        card2.pack(fill=tk.X, padx=24, pady=8)

        tk.Label(card2, text="Authentication", font=("Segoe UI", 13, "bold"),
                 bg=C["card_bg"], fg=C["text_primary"]).pack(anchor=tk.W, padx=18, pady=(14, 8))

        def _labeled_entry(parent, label, var, width=28, show=None):
            r = tk.Frame(parent, bg=C["card_bg"])
            r.pack(fill=tk.X, padx=18, pady=3)
            tk.Label(r, text=label, font=("Segoe UI", 10), bg=C["card_bg"],
                     fg=C["text_primary"], width=12, anchor=tk.W).pack(side=tk.LEFT)
            e = tk.Entry(r, textvariable=var, font=("Segoe UI", 10),
                          bg=C["card_bg"], fg=C["text_primary"], bd=0,
                          highlightbackground=C["input_border"], highlightthickness=1,
                          highlightcolor=C["accent"], width=width, show=show)
            e.pack(side=tk.LEFT, ipady=4, ipadx=4)
            return e

        self.phone_var = tk.StringVar()
        _labeled_entry(card2, "Phone", self.phone_var)
        self.code_var = tk.StringVar()
        _labeled_entry(card2, "Code", self.code_var, 12)
        self.password_var = tk.StringVar()
        _labeled_entry(card2, "2FA Password", self.password_var, 20, show="*")

        btn_frame = tk.Frame(card2, bg=C["card_bg"])
        btn_frame.pack(fill=tk.X, padx=18, pady=(10, 14))
        self.btn_send_code = tk.Button(btn_frame, text="Send Code",
                                        font=("Segoe UI", 10),
                                        bg=C["accent"], fg="#ffffff", bd=0, padx=22, pady=4,
                                        activebackground=C["accent_hover"],
                                        activeforeground="#ffffff", cursor="hand2",
                                        command=self._on_send_code)
        self.btn_send_code.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_sign_in = tk.Button(btn_frame, text="Sign In",
                                      font=("Segoe UI", 10),
                                      bg=C["accent"], fg="#ffffff", bd=0, padx=22, pady=4,
                                      activebackground=C["accent_hover"],
                                      activeforeground="#ffffff", cursor="hand2",
                                      command=self._on_sign_in)
        self.btn_sign_in.pack(side=tk.LEFT, padx=8)
        self.btn_disconnect = tk.Button(btn_frame, text="Disconnect",
                                         font=("Segoe UI", 10),
                                         bg=C["danger"], fg="#ffffff", bd=0, padx=22, pady=4,
                                         activebackground="#c62828", activeforeground="#ffffff",
                                         cursor="hand2", command=self._on_disconnect,
                                         state=tk.DISABLED)
        self.btn_disconnect.pack(side=tk.LEFT, padx=8)

        # Log card
        card3 = tk.Frame(f, bg=C["card_bg"], highlightbackground=C["border"],
                         highlightthickness=1)
        card3.pack(fill=tk.BOTH, expand=True, padx=24, pady=(8, 24))

        tk.Label(card3, text="Log", font=("Segoe UI", 11, "bold"),
                 bg=C["card_bg"], fg=C["text_primary"]).pack(anchor=tk.W, padx=18, pady=(10, 4))

        self.log_text = tk.Text(card3, height=8, state=tk.DISABLED, wrap=tk.WORD,
                                 bg=C["content_bg"], fg=C["text_secondary"],
                                 font=("Consolas", 10), bd=0,
                                 highlightbackground=C["border"], highlightthickness=1)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=18, pady=(2, 14))

    # ================================================================
    # GROUPS SECTION
    # ================================================================
    def _build_groups_section(self):
        p = self.content_groups

        # Toolbar card
        tbar = tk.Frame(p, bg=C["card_bg"], highlightbackground=C["border"],
                        highlightthickness=1)
        tbar.pack(fill=tk.X, padx=24, pady=(24, 0))

        inner = tk.Frame(tbar, bg=C["card_bg"])
        inner.pack(fill=tk.X, padx=16, pady=12)

        tk.Label(inner, text="\u26B2 Groups & Channels", font=("Segoe UI", 13, "bold"),
                 bg=C["card_bg"], fg=C["text_primary"]).pack(anchor=tk.W, pady=(0, 10))

        r1 = tk.Frame(inner, bg=C["card_bg"])
        r1.pack(fill=tk.X)
        tk.Label(r1, text="Search", font=("Segoe UI", 10), bg=C["card_bg"],
                 fg=C["text_primary"]).pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace("w", lambda *_: self._on_search())
        tk.Entry(r1, textvariable=self.search_var, font=("Segoe UI", 10),
                 bg=C["card_bg"], fg=C["text_primary"], bd=0,
                 highlightbackground=C["input_border"], highlightthickness=1,
                 highlightcolor=C["accent"], width=28
                 ).pack(side=tk.LEFT, padx=(8, 12), ipady=4, ipadx=4)
        tk.Label(r1, text="Limit", font=("Segoe UI", 10), bg=C["card_bg"],
                 fg=C["text_primary"]).pack(side=tk.LEFT)
        self.limit_var = tk.StringVar(value="200")
        tk.Spinbox(r1, from_=10, to=2000, textvariable=self.limit_var,
                   font=("Segoe UI", 10), bd=0, bg=C["card_bg"], width=6,
                   highlightbackground=C["input_border"], highlightthickness=1
                   ).pack(side=tk.LEFT, padx=(4, 0), ipady=3)

        r2 = tk.Frame(inner, bg=C["card_bg"])
        r2.pack(fill=tk.X, pady=(8, 0))
        self.btn_refresh = tk.Button(r2, text="\u21BB Refresh", font=("Segoe UI", 10),
                                      bg=C["accent"], fg="#ffffff", bd=0, padx=18, pady=4,
                                      activebackground=C["accent_hover"],
                                      activeforeground="#ffffff", cursor="hand2",
                                      command=self._on_refresh_dialogs)
        self.btn_refresh.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_fetch = tk.Button(r2, text="\u2913 Fetch Videos", font=("Segoe UI", 10),
                                    bg=C["accent"], fg="#ffffff", bd=0, padx=18, pady=4,
                                    activebackground=C["accent_hover"],
                                    activeforeground="#ffffff", cursor="hand2",
                                    command=self._on_fetch_videos, state=tk.DISABLED)
        self.btn_fetch.pack(side=tk.LEFT, padx=8)

        # Dialogs tree card
        card = tk.Frame(p, bg=C["card_bg"], highlightbackground=C["border"],
                        highlightthickness=1)
        card.pack(fill=tk.BOTH, expand=True, padx=24, pady=(12, 24))

        tframe = tk.Frame(card, bg=C["card_bg"])
        tframe.pack(fill=tk.BOTH, expand=True, padx=16, pady=12)

        cols = ("check", "title", "type", "protected", "unread")
        self.dialog_tree = ttk.Treeview(tframe, columns=cols, show="headings",
                                        selectmode="none")
        self.dialog_tree.heading("check", text="")
        self.dialog_tree.heading("title", text="Title")
        self.dialog_tree.heading("type", text="Type")
        self.dialog_tree.heading("protected", text="Protected")
        self.dialog_tree.heading("unread", text="Unread")
        self.dialog_tree.column("check", width=40, anchor=tk.CENTER, minwidth=30)
        self.dialog_tree.column("title", width=400, minwidth=150)
        self.dialog_tree.column("type", width=100, anchor=tk.CENTER, minwidth=60)
        self.dialog_tree.column("protected", width=85, anchor=tk.CENTER, minwidth=60)
        self.dialog_tree.column("unread", width=70, anchor=tk.CENTER, minwidth=50)
        self.dialog_tree.bind("<ButtonRelease-1>", self._on_dialog_click)

        vsb = ttk.Scrollbar(tframe, orient=tk.VERTICAL, command=self.dialog_tree.yview)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.dialog_tree.configure(yscrollcommand=vsb.set)
        self.dialog_tree.pack(fill=tk.BOTH, expand=True)

        self.scan_status_var = tk.StringVar(value="Ready")
        tk.Label(card, textvariable=self.scan_status_var, font=("Segoe UI", 9),
                 bg=C["card_bg"], fg=C["text_muted"]).pack(anchor=tk.W, padx=18, pady=(0, 10))

    # ================================================================
    # DOWNLOADS SECTION
    # ================================================================
    def _format_duration(self, secs: int) -> str:
        m, s = divmod(secs, 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

    def _format_size(self, bytes_: int) -> str:
        if bytes_ < 1024:
            return f"{bytes_} B"
        kb = bytes_ / 1024
        if kb < 1024:
            return f"{kb:.0f} KB"
        mb = kb / 1024
        if mb < 1024:
            return f"{mb:.1f} MB"
        return f"{mb/1024:.2f} GB"

    def _format_speed(self, bytes_per_sec: float) -> str:
        if bytes_per_sec < 1024:
            return f"{bytes_per_sec:.0f} B/s"
        kb = bytes_per_sec / 1024
        if kb < 1024:
            return f"{kb:.0f} KB/s"
        mb = kb / 1024
        return f"{mb:.1f} MB/s"

    def _build_downloads_section(self):
        p = self.content_downloads
        self._thumb_cache: dict[int, tk.PhotoImage] = {}
        self._thumb_future = None
        self._selected_dl_item = None

        # Toolbar card
        tbar = tk.Frame(p, bg=C["card_bg"], highlightbackground=C["border"],
                        highlightthickness=1)
        tbar.pack(fill=tk.X, padx=24, pady=(24, 0))
        inner = tk.Frame(tbar, bg=C["card_bg"])
        inner.pack(fill=tk.X, padx=16, pady=12)

        tk.Label(inner, text="\u2913 Downloads", font=("Segoe UI", 13, "bold"),
                 bg=C["card_bg"], fg=C["text_primary"]).pack(anchor=tk.W, pady=(0, 10))

        r1 = tk.Frame(inner, bg=C["card_bg"])
        r1.pack(fill=tk.X)
        tk.Label(r1, text="Save to", font=("Segoe UI", 10), bg=C["card_bg"],
                 fg=C["text_primary"]).pack(side=tk.LEFT)
        self.download_dir_var = tk.StringVar(value="downloads")
        tk.Entry(r1, textvariable=self.download_dir_var, font=("Segoe UI", 10),
                 bg=C["card_bg"], fg=C["text_primary"], bd=0,
                 highlightbackground=C["input_border"], highlightthickness=1,
                 highlightcolor=C["accent"], width=40
                 ).pack(side=tk.LEFT, padx=(8, 6), ipady=4, ipadx=4)
        tk.Button(r1, text="\u2026", font=("Segoe UI", 12), bg=C["accent"],
                  fg="#ffffff", bd=0, padx=10, pady=2, cursor="hand2",
                  activebackground=C["accent_hover"],
                  command=self._on_browse_dir).pack(side=tk.LEFT)
        tk.Label(r1, text="  Workers", font=("Segoe UI", 10), bg=C["card_bg"],
                 fg=C["text_primary"]).pack(side=tk.LEFT, padx=(16, 0))
        self.concurrent_var = tk.StringVar(value="3")
        tk.Spinbox(r1, from_=1, to=10, textvariable=self.concurrent_var,
                   font=("Segoe UI", 10), bd=0, bg=C["card_bg"], width=4,
                   highlightbackground=C["input_border"], highlightthickness=1
                   ).pack(side=tk.LEFT, padx=(4, 0), ipady=3)

        r2 = tk.Frame(inner, bg=C["card_bg"])
        r2.pack(fill=tk.X, pady=(8, 0))
        self.btn_start = tk.Button(r2, text="\u25B6 Start Checked", font=("Segoe UI", 10),
                                    bg=C["success"], fg="#ffffff", bd=0, padx=18, pady=4,
                                    activebackground="#3d9140", activeforeground="#ffffff",
                                    cursor="hand2", command=self._on_start_all,
                                    state=tk.DISABLED)
        self.btn_start.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_pause = tk.Button(r2, text="\u23F8 Pause", font=("Segoe UI", 10),
                                    bg=C["warning"], fg="#ffffff", bd=0, padx=18, pady=4,
                                    activebackground="#d4951e", activeforeground="#ffffff",
                                    cursor="hand2", command=self._on_pause,
                                    state=tk.DISABLED)
        self.btn_pause.pack(side=tk.LEFT, padx=8)
        self.btn_cancel_all = tk.Button(r2, text="\u2716 Cancel All", font=("Segoe UI", 10),
                                         bg=C["danger"], fg="#ffffff", bd=0, padx=18, pady=4,
                                         activebackground="#c62828", activeforeground="#ffffff",
                                         cursor="hand2", command=self._on_cancel_all,
                                         state=tk.DISABLED)
        self.btn_cancel_all.pack(side=tk.LEFT, padx=8)

        # Link import row
        r3 = tk.Frame(inner, bg=C["card_bg"])
        r3.pack(fill=tk.X, pady=(6, 0))
        tk.Label(r3, text="\u2197 Link", font=("Segoe UI", 10), bg=C["card_bg"],
                 fg=C["text_primary"]).pack(side=tk.LEFT)
        self.link_var = tk.StringVar()
        tk.Entry(r3, textvariable=self.link_var, font=("Segoe UI", 10),
                 bg=C["card_bg"], fg=C["text_primary"], bd=0,
                 highlightbackground=C["input_border"], highlightthickness=1,
                 highlightcolor=C["accent"], width=50
                 ).pack(side=tk.LEFT, padx=(8, 6), ipady=4, ipadx=4)
        self.btn_fetch_link = tk.Button(r3, text="Fetch", font=("Segoe UI", 10),
                                         bg=C["accent"], fg="#ffffff", bd=0, padx=16, pady=4,
                                         activebackground=C["accent_hover"],
                                         activeforeground="#ffffff", cursor="hand2",
                                         command=self._on_fetch_link)
        self.btn_fetch_link.pack(side=tk.LEFT)
        self.link_status = tk.Label(r3, text="", font=("Segoe UI", 9), bg=C["card_bg"],
                                     fg=C["text_muted"])
        self.link_status.pack(side=tk.LEFT, padx=(10, 0))

        # Filter tabs
        filter_frame = tk.Frame(p, bg=C["content_bg"])
        filter_frame.pack(fill=tk.X, padx=24, pady=(8, 0))

        self.dl_filter_var = tk.StringVar(value="all")
        self.dl_filter_tabs: list[tuple[str, tk.Label]] = []
        for key, label in [("all", "All"), ("downloading", "Downloading"),
                           ("completed", "Completed"), ("failed", "Failed")]:
            tab = tk.Label(filter_frame, text=f"  {label}  ",
                          font=("Segoe UI", 10),
                          bg=C["content_bg"], fg=C["text_secondary"],
                          cursor="hand2", padx=8, pady=4)
            tab.pack(side=tk.LEFT, padx=(0, 4))
            tab.bind("<Button-1>", lambda e, k=key: self._set_dl_filter(k))
            tab.bind("<Enter>", lambda e, k=key: self._filter_tab_hover(k, True))
            tab.bind("<Leave>", lambda e, k=key: self._filter_tab_hover(k, False))
            self.dl_filter_tabs.append((key, tab))
        self._update_filter_tabs()

        # Main area: tree (left) + preview (right)
        main = tk.Frame(p, bg=C["content_bg"])
        main.pack(fill=tk.BOTH, expand=True, padx=24, pady=(12, 8))

        # ---- Tree card (left) ----
        tree_card = tk.Frame(main, bg=C["card_bg"], highlightbackground=C["border"],
                             highlightthickness=1)
        tree_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        tframe = tk.Frame(tree_card, bg=C["card_bg"])
        tframe.pack(fill=tk.BOTH, expand=True, padx=14, pady=12)

        dl_cols = ("sel", "group", "filename", "speed", "size", "status")
        self.dl_tree = ttk.Treeview(tframe, columns=dl_cols, show="headings",
                                    selectmode="extended")
        self.dl_tree.heading("sel", text="")
        self.dl_tree.heading("group", text="Group")
        self.dl_tree.heading("filename", text="Filename")
        self.dl_tree.heading("speed", text="Speed")
        self.dl_tree.heading("size", text="Size")
        self.dl_tree.heading("status", text="Status")
        self.dl_tree.column("sel", width=38, anchor=tk.CENTER, minwidth=30)
        self.dl_tree.column("group", width=160, minwidth=80)
        self.dl_tree.column("filename", width=220, minwidth=120)
        self.dl_tree.column("speed", width=85, anchor=tk.CENTER, minwidth=60)
        self.dl_tree.column("size", width=80, anchor=tk.CENTER, minwidth=55)
        self.dl_tree.column("status", width=120, anchor=tk.CENTER, minwidth=80)
        self.dl_tree.bind("<ButtonRelease-1>", self._on_dl_click)
        self.dl_tree.bind("<<TreeviewSelect>>", self._on_dl_select)
        self.dl_tree.bind("<Delete>", lambda e: self._on_remove_selected())

        vsb = ttk.Scrollbar(tframe, orient=tk.VERTICAL, command=self.dl_tree.yview)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.dl_tree.configure(yscrollcommand=vsb.set)
        self.dl_tree.pack(fill=tk.BOTH, expand=True)

        # Context menu
        self.dl_context = tk.Menu(self.root, tearoff=0, bg=C["sidebar_bg"],
                                  fg=C["sidebar_fg"],
                                  activebackground=C["sidebar_hover"],
                                  activeforeground=C["sidebar_fg"])
        self.dl_context.add_command(label="\u25B6 Start", command=self._ctx_start)
        self.dl_context.add_command(label="\u23F8 Pause", command=self._ctx_pause)
        self.dl_context.add_separator()
        self.dl_context.add_command(label="\u2716 Remove", command=self._on_remove_selected)
        self.dl_context.add_command(label="\uD83D\uDCC2 Open Folder", command=self._ctx_open_folder)
        self.dl_tree.bind("<Button-3>", self._on_dl_context)

        # ---- Preview card (right) ----
        preview_card = tk.Frame(main, bg=C["card_bg"], highlightbackground=C["border"],
                                highlightthickness=1, width=340)
        preview_card.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(14, 0))
        preview_card.pack_propagate(False)

        # Thumbnail area
        thumb_frame = tk.Frame(preview_card, bg="#0d1117", height=200)
        thumb_frame.pack(fill=tk.X)
        thumb_frame.pack_propagate(False)
        self.thumb_label = tk.Label(thumb_frame, bg="#0d1117",
                                     fg="#444", font=("Segoe UI", 28),
                                     text="\u25B6")
        self.thumb_label.pack(fill=tk.BOTH, expand=True)

        # Info area
        info_frame = tk.Frame(preview_card, bg=C["card_bg"])
        info_frame.pack(fill=tk.X, padx=16, pady=(10, 6))

        self.preview_widgets = {}
        fields = [
            ("file", "File"),
            ("group", "Group"),
            ("duration", "Duration"),
            ("size", "Size"),
            ("eta", "Est. Time"),
            ("date", "Date"),
        ]
        for key, label in fields:
            r = tk.Frame(info_frame, bg=C["card_bg"])
            r.pack(fill=tk.X, pady=2)
            tk.Label(r, text=label, font=("Segoe UI", 9, "bold"),
                     bg=C["card_bg"], fg=C["text_secondary"],
                     width=9, anchor=tk.W).pack(side=tk.LEFT)
            lbl = tk.Label(r, text="-", font=("Segoe UI", 9),
                           bg=C["card_bg"], fg=C["text_primary"],
                           anchor=tk.W)
            lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.preview_widgets[key] = lbl

        # Select toggle button
        sep = tk.Frame(preview_card, bg=C["border"], height=1)
        sep.pack(fill=tk.X, padx=16, pady=4)
        self.preview_sel_btn = tk.Button(preview_card,
                                          text="\u2611 Selected for download",
                                          font=("Segoe UI", 10),
                                          bg=C["accent"], fg="#ffffff", bd=0,
                                          padx=12, pady=6, cursor="hand2",
                                          activebackground=C["accent_hover"],
                                          activeforeground="#ffffff",
                                          command=self._toggle_preview_select)
        self.preview_sel_btn.pack(fill=tk.X, padx=16, pady=6)

        # Bottom area with actions + progress
        bot = tk.Frame(p, bg=C["card_bg"], highlightbackground=C["border"],
                       highlightthickness=1)
        bot.pack(fill=tk.X, padx=24, pady=(0, 24))

        bot_inner = tk.Frame(bot, bg=C["card_bg"])
        bot_inner.pack(fill=tk.X, padx=16, pady=(6, 10))

        tk.Button(bot_inner, text="Remove Selected", font=("Segoe UI", 9),
                  bg=C["content_bg"], fg=C["text_primary"], bd=0, padx=12, pady=3,
                  activebackground=C["border"], cursor="hand2",
                  command=self._on_remove_selected).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(bot_inner, text="Clear Finished", font=("Segoe UI", 9),
                  bg=C["content_bg"], fg=C["text_primary"], bd=0, padx=12, pady=3,
                  activebackground=C["border"], cursor="hand2",
                  command=self._on_clear_completed).pack(side=tk.LEFT)

        self.dl_status_var = tk.StringVar(value="0 items")
        tk.Label(bot_inner, textvariable=self.dl_status_var,
                 font=("Segoe UI", 9, "bold"), bg=C["card_bg"],
                 fg=C["text_secondary"]).pack(side=tk.RIGHT)

        self.dl_progress = ttk.Progressbar(p, mode="determinate", length=0)
        self.dl_progress.pack(fill=tk.X, padx=24, pady=(0, 24), ipady=4)

    # ----------------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------------
    def _async(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def _async_cb(self, coro, callback):
        def _done(f):
            try:
                r = f.result()
                self.root.after(0, lambda r=r: callback(r, None))
            except Exception as e:
                self.root.after(0, lambda e=e: callback(None, e))
        fut = self._async(coro)
        fut.add_done_callback(_done)

    def _run_async(self, coro):
        def _done(f):
            try:
                f.result()
            except Exception as e:
                self.root.after(0, lambda e=e: self._log(f"Error: {e}"))
        fut = self._async(coro)
        fut.add_done_callback(_done)

    def _log(self, msg: str):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def run(self):
        self.root.mainloop()

    def _setup_protocols(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        if self.download_queue:
            self.download_queue.cancel_all()
        if self.client:
            self._async(self.client.disconnect())
        self.root.destroy()

    def _load_config_to_ui(self):
        if self.config.api_id:
            self.api_id_var.set(str(self.config.api_id))
        if self.config.api_hash:
            self.api_hash_var.set(self.config.api_hash)
        if self.config.phone:
            self.phone_var.set(self.config.phone)
        self.download_dir_var.set(self.config.download_dir)
        self.concurrent_var.set(str(self.config.max_concurrent))
        self.limit_var.set(str(self.config.max_messages_per_group))
        self.root.after(500, self._try_auto_login)

    def _try_auto_login(self):
        phone = self.config.phone.strip()
        if not phone or not self.config.api_id or not self.config.api_hash:
            return
        from pathlib import Path
        session_file = Path(f"sessions/session_{phone}.session")
        if not session_file.exists():
            return
        self._log(f"Found saved session for {phone}, connecting...")
        self.status_var.set("Auto-login...")
        self.status_icon_var.set("\u25CF")
        self.client = TGClient(f"session_{phone}", self.config.api_id,
                                self.config.api_hash, loop=self.loop)
        def cb(result, error):
            if error or not result:
                self._log("Saved session expired, login manually.")
                self.client = None
                self.status_var.set("Session expired")
                self.status_icon_var.set("\u25CB")
                return
            self._authorized = True
            self._log("Authenticated from saved session!")
            self.status_var.set(f"Authenticated as {phone}")
            self.status_icon_var.set("\u25CF")
            self.btn_disconnect.configure(state=tk.NORMAL)
            self.btn_send_code.configure(state=tk.DISABLED)
            self.btn_fetch.configure(state=tk.NORMAL)
            self._show_section(1)
            self._on_refresh_dialogs()
        self._async_cb(self._do_auto_login(), cb)

    async def _do_auto_login(self):
        await self.client.connect()
        if await self.client.is_authorized():
            return True
        await self.client.disconnect()
        self.client = None
        return False

    # ----------------------------------------------------------------
    # Theme
    # ----------------------------------------------------------------
    def _toggle_theme(self, event=None):
        old = {k: C[k] for k in C}
        self.is_dark = not self.is_dark
        C.clear()
        C.update(DARK if self.is_dark else LIGHT)
        self.config.dark_mode = self.is_dark
        self.config.save()
        self._apply_theme(old)

    def _apply_theme(self, old_colors=None):
        self._configure_styles()
        new = dict(C)
        if old_colors:
            self._recolor_widget(self.root, old_colors, new)
            # Fix context menu colors (not part of widget tree)
            if hasattr(self, 'dl_context'):
                self.dl_context.configure(
                    bg=C["sidebar_bg"], fg=C["sidebar_fg"],
                    activebackground=C["sidebar_hover"],
                    activeforeground=C["sidebar_fg"])
            # Refresh filter tab highlight
            if hasattr(self, 'dl_filter_tabs'):
                self._update_filter_tabs()
                self._update_dl_status()

    def _recolor_widget(self, w, old_colors, new_colors):
        color_map = {}
        for key in old_colors:
            if old_colors[key] != new_colors[key]:
                color_map[old_colors[key]] = new_colors[key]
        if not color_map:
            return
        try:
            updates = {}
            for opt in ("bg", "fg", "activebackground", "activeforeground",
                        "highlightbackground", "highlightcolor",
                        "selectbackground", "inactiveselectbackground"):
                try:
                    v = str(w.cget(opt))
                    if v in color_map:
                        updates[opt] = color_map[v]
                except tk.TclError:
                    pass
            if updates:
                w.configure(**updates)
        except Exception:
            pass
        try:
            for child in w.winfo_children():
                self._recolor_widget(child, old_colors, new_colors)
        except Exception:
            pass

    # ----------------------------------------------------------------
    # Login handlers
    # ----------------------------------------------------------------
    def _on_save_config(self):
        try:
            self.config.api_id = int(self.api_id_var.get().strip())
        except ValueError:
            messagebox.showerror("Error", "API ID must be a number")
            return
        self.config.api_hash = self.api_hash_var.get().strip()
        if not self.config.api_hash:
            messagebox.showerror("Error", "API Hash is required")
            return
        self.config.phone = self.phone_var.get().strip()
        self.config.download_dir = self.download_dir_var.get().strip() or "downloads"
        try:
            self.config.max_concurrent = int(self.concurrent_var.get().strip())
        except ValueError:
            self.config.max_concurrent = 3
        try:
            self.config.max_messages_per_group = int(self.limit_var.get().strip())
        except ValueError:
            self.config.max_messages_per_group = 200
        self.config.save()
        self._log("Configuration saved.")

    def _on_send_code(self):
        phone = self.phone_var.get().strip()
        if not phone:
            messagebox.showwarning("Warning", "Enter phone number")
            return
        try:
            api_id = int(self.api_id_var.get().strip())
            api_hash = self.api_hash_var.get().strip()
        except ValueError:
            messagebox.showerror("Error", "Valid API ID and Hash required")
            return
        if self.client:
            self._async(self.client.disconnect())
        self._log(f"Connecting to Telegram as {phone} ...")
        self.client = TGClient(f"session_{phone}", api_id, api_hash, loop=self.loop)
        self.btn_send_code.configure(state=tk.DISABLED)

        def connected(result, error):
            if error:
                self.btn_send_code.configure(state=tk.NORMAL)
                self._log(f"Connection failed: {error}")
                self.client = None
                self.status_var.set("Disconnected")
                return
            self._async_cb(self.client.is_authorized(), self._on_check_auth)
        self._async_cb(self.client.connect(), connected)

    def _on_check_auth(self, result, error):
        self.btn_send_code.configure(state=tk.NORMAL)
        if error:
            self._log(f"Auth check failed: {error}")
            return
        if result:
            self._on_auth_success()
            self._log("Already authenticated (saved session).")
        else:
            self._async_cb(self.client.send_code_request(self.phone_var.get().strip()),
                           self._on_code_sent)

    def _on_code_sent(self, result, error):
        if error:
            self._log(f"Send code failed: {error}")
            self.client = None
            self.status_var.set("Connection failed")
            return
        self._log("Code sent! Check your Telegram.")
        self.status_var.set("Code sent")

    def _on_auth_success(self):
        self._authorized = True
        self._log("Authenticated successfully!")
        self.status_var.set(f"Authenticated as {self.phone_var.get().strip()}")
        self.status_icon_var.set("\u25CF")
        self.btn_disconnect.configure(state=tk.NORMAL)
        self.btn_send_code.configure(state=tk.DISABLED)
        self.btn_fetch.configure(state=tk.NORMAL)
        # Save phone to config for auto-login next launch
        self.config.phone = self.phone_var.get().strip()
        self.config.save()
        self._show_section(1)
        self._on_refresh_dialogs()

    def _on_sign_in(self):
        code = self.code_var.get().strip()
        if not code:
            messagebox.showwarning("Warning", "Enter the code")
            return
        phone = self.phone_var.get().strip()
        password = self.password_var.get().strip() or None
        self.btn_sign_in.configure(state=tk.DISABLED)
        self._log("Signing in ...")

        async def _do():
            await self.client.sign_in(phone, code, password)
            return await self.client.is_authorized()

        def cb(result, error):
            self.btn_sign_in.configure(state=tk.NORMAL)
            if error:
                if isinstance(error, SessionPasswordNeededError):
                    self._log("2FA password required. Enter it above and try again.")
                    self.status_var.set("2FA required")
                    return
                self._log(f"Sign in failed: {error}")
                return
            if result:
                self._on_auth_success()
            else:
                self._log("Authorization failed.")
        self._async_cb(_do(), cb)

    def _on_disconnect(self):
        phone = self.phone_var.get().strip()
        if self.client:
            self._async(self.client.disconnect())
            self.client = None
        self._authorized = False
        self._log("Disconnected.")
        self.status_var.set("Disconnected")
        self.status_icon_var.set("\u25CB")
        self.btn_disconnect.configure(state=tk.DISABLED)
        self.btn_send_code.configure(state=tk.NORMAL)
        self.btn_fetch.configure(state=tk.DISABLED)
        self._clear_dialog_tree()
        self._dialogs_data = []
        # Clear cached sessions
        from pathlib import Path
        for f in Path("sessions").glob(f"session_{phone}.session*"):
            try:
                f.unlink()
                self._log(f"Removed session file: {f.name}")
            except OSError:
                pass

    # ----------------------------------------------------------------
    # Groups handlers
    # ----------------------------------------------------------------
    def _clear_dialog_tree(self):
        for item in self.dialog_tree.get_children():
            self.dialog_tree.delete(item)

    def _on_search(self):
        query = self.search_var.get().lower().strip()
        self._clear_dialog_tree()
        for d in self._dialogs_data:
            if query and query not in d["title"].lower():
                continue
            check = CHECKED if d.get("_checked") else UNCHECKED
            prot = "\u26D4" if d["protected"] else ""
            self.dialog_tree.insert("", tk.END, iid=str(d["id"]), values=(
                check, d["title"], d["type"], prot, d["unread"],
            ))

    def _on_dialog_click(self, event):
        item = self.dialog_tree.identify_row(event.y)
        if not item:
            return
        col = self.dialog_tree.identify_column(event.x)
        if col != "#1":
            return
        values = list(self.dialog_tree.item(item, "values"))
        iid = int(item)
        for d in self._dialogs_data:
            if d["id"] == iid:
                d["_checked"] = not d.get("_checked", False)
                values[0] = CHECKED if d["_checked"] else UNCHECKED
                break
        self.dialog_tree.item(item, values=values)
        self._update_fetch_button()

    def _update_fetch_button(self):
        has_checked = any(d.get("_checked") for d in self._dialogs_data)
        self.btn_fetch.configure(state=tk.NORMAL if has_checked else tk.DISABLED)

    def _on_refresh_dialogs(self):
        if not self.client:
            return
        self._log("Loading dialogs ...")
        self.btn_refresh.configure(state=tk.DISABLED)
        self.scan_status_var.set("Loading dialogs...")

        def cb(result, error):
            self.btn_refresh.configure(state=tk.NORMAL)
            if error:
                self._log(f"Load dialogs failed: {error}")
                self.scan_status_var.set("Error loading dialogs")
                return
            self._dialogs_data = result
            for d in self._dialogs_data:
                d["_checked"] = False
            self._on_search()
            self._update_fetch_button()
            self._log(f"Loaded {len(result)} dialogs.")
            self.scan_status_var.set(f"{len(result)} dialogs loaded")
        self._async_cb(self.client.get_dialogs(), cb)

    def _on_fetch_videos(self):
        checked = [d for d in self._dialogs_data if d.get("_checked")]
        if not checked:
            messagebox.showwarning("Warning", "Select at least one group/channel first")
            return
        try:
            limit = int(self.limit_var.get().strip())
        except ValueError:
            limit = 200
        self._log(f"Scanning {len(checked)} groups for videos (limit={limit})...")
        self.btn_fetch.configure(state=tk.DISABLED)
        self.scan_status_var.set("Scanning...")
        self._video_cache.clear()
        self._download_items_by_group.clear()

        async def _scan_all():
            total = []
            for i, d in enumerate(checked):
                self.root.after(0, lambda: self.scan_status_var.set(
                    f"Scanning {i+1}/{len(checked)}: {d['title']}"))
                try:
                    msgs = await self.client.get_video_messages(d["entity"], limit=limit)
                except Exception as e:
                    self.root.after(0, lambda e=e, t=d["title"]: self._log(f"Error scanning {t}: {e}"))
                    continue
                items = []
                for msg in msgs:
                    fname = self.client.get_video_filename(msg)
                    fsize = msg.video.size if msg.video else 0
                    dur = self.client.get_video_duration(msg)
                    item = DownloadItem(
                        chat_title=d["title"],
                        message=msg,
                        save_dir=self.download_dir_var.get().strip() or "downloads",
                        filename=fname,
                        file_size=fsize,
                        duration=dur,
                    )
                    items.append(item)
                if items:
                    self._download_items_by_group[d["title"]] = items
                    total.extend(items)
                self.root.after(0, lambda t=d["title"], n=len(items): self._log(
                    f"  {t}: {n} videos found"))
            return total

        def cb(result, error):
            self.btn_fetch.configure(state=tk.NORMAL)
            self.scan_status_var.set("Ready")
            if error:
                self._log(f"Scan failed: {error}")
                return
            if not result:
                self._log("No videos found.")
                return
            self._log(f"Total: {len(result)} videos queued.")
            self._add_items_to_download_tab(result)
            self._show_section(2)

        self._async_cb(_scan_all(), cb)

    # ----------------------------------------------------------------
    # Downloads handlers
    # ----------------------------------------------------------------
    def _find_dl_item(self, cid: str):
        for item_list in self._download_items_by_group.values():
            for it in item_list:
                if str(id(it)) == cid:
                    return it
        return None

    def _clear_preview(self):
        self._selected_dl_item = None
        self.thumb_label.configure(image="", text="\u25B6")
        for key in self.preview_widgets:
            self.preview_widgets[key].configure(text="-")
        self.preview_sel_btn.configure(text="\u2611 Selected", bg=C["accent"])

    def _show_preview(self, item: DownloadItem):
        self._selected_dl_item = item
        dt = item.message.date.strftime("%Y-%m-%d %H:%M") if item.message.date else "-"
        eta_text = self._format_eta(item.eta) if item.eta > 0 else "-"
        info = {
            "file": item.filename,
            "group": item.chat_title,
            "duration": self._format_duration(item.duration) if item.duration else "-",
            "size": self._format_size(item.file_size) if item.file_size else "-",
            "eta": eta_text,
            "date": dt,
        }
        for key, val in info.items():
            self.preview_widgets[key].configure(text=val)
        self._update_preview_sel_btn()
        self._load_thumbnail(item)

    def _update_preview_sel_btn(self):
        if not self._selected_dl_item:
            return
        cid = str(id(self._selected_dl_item))
        if not self.dl_tree.exists(cid):
            return
        checked = self.dl_tree.item(cid, "values")[0] == CHECKED
        txt = "\u2611 Selected for download" if checked else "\u2610 Not selected"
        bg = C["accent"] if checked else C["text_muted"]
        self.preview_sel_btn.configure(text=txt, bg=bg)

    def _toggle_preview_select(self):
        if not self._selected_dl_item:
            return
        cid = str(id(self._selected_dl_item))
        if not self.dl_tree.exists(cid):
            return
        vals = list(self.dl_tree.item(cid, "values"))
        vals[0] = UNCHECKED if vals[0] == CHECKED else CHECKED
        self.dl_tree.item(cid, values=vals)
        self._update_preview_sel_btn()

    def _load_thumbnail(self, item: DownloadItem):
        self.thumb_label.configure(image="", text="\u23F3")
        if self._thumb_future:
            self._thumb_future.cancel()
        self._thumb_future = self._async(self._do_load_thumb(item))

    async def _do_load_thumb(self, item: DownloadItem):
        cache_dir = Path("cache/thumbnails")
        cache_dir.mkdir(parents=True, exist_ok=True)
        msg_id = item.message.id
        thumb_path = cache_dir / f"{msg_id}.jpg"
        chat_id = getattr(item.message.chat_id if hasattr(item.message, 'chat_id') else item.message.peer_id, 'channel_id', msg_id)
        safe_path = cache_dir / f"{chat_id}_{msg_id}.jpg"
        if not safe_path.exists():
            try:
                result = await self.client.download_thumbnail(item.message, str(safe_path))
                if not result or not safe_path.exists():
                    raise FileNotFoundError
            except Exception:
                self.root.after(0, lambda: self.thumb_label.configure(
                    image="", text="\u25B6", font=("Segoe UI", 28)))
                return
        try:
            from PIL import Image, ImageTk
            img = Image.open(str(safe_path))
            w, h = img.size
            ratio = min(320 / w, 190 / h)
            new_w, new_h = int(w * ratio), int(h * ratio)
            img = img.resize((new_w, new_h), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self._thumb_cache[msg_id] = photo
            self.root.after(0, lambda: self.thumb_label.configure(
                image=photo, text=""))
        except Exception:
            self.root.after(0, lambda: self.thumb_label.configure(
                image="", text="\u25B6", font=("Segoe UI", 28)))

    def _add_items_to_download_tab(self, items):
        for item in items:
            cid = str(id(item))
            self._dl_item_ids.add(cid)
            size_str = self._format_size(item.file_size) if item.file_size else "-"
            self.dl_tree.insert("", tk.END, iid=cid, values=(
                CHECKED, item.chat_title, item.filename,
                "-", size_str, item.status.value,
            ))
        self._update_dl_status()
        self.btn_start.configure(state=tk.NORMAL)
        self._apply_dl_filter()

    def _on_browse_dir(self):
        d = filedialog.askdirectory(initialdir=self.download_dir_var.get() or ".")
        if d:
            self.download_dir_var.set(d)

    def _on_fetch_link(self):
        link = self.link_var.get().strip()
        if not link:
            messagebox.showwarning("Warning", "Paste a Telegram video link first")
            return
        self.link_status.configure(text="Fetching...", fg=C["text_muted"])
        self.btn_fetch_link.configure(state=tk.DISABLED)
        self._async_cb(self.client.get_message_from_link(link), self._on_link_fetched)

    def _on_link_fetched(self, msg, error):
        self.btn_fetch_link.configure(state=tk.NORMAL)
        if error or not msg:
            self.link_status.configure(text="Invalid link or not found", fg=C["danger"])
            return
        if not self.client._is_video(msg):
            self.link_status.configure(text="Not a video", fg=C["warning"])
            return
        fname = self.client.get_video_filename(msg)
        fsize = msg.video.size if msg.video else 0
        dur = self.client.get_video_duration(msg)
        item = DownloadItem(
            chat_title=self.link_var.get().strip()[:40],
            message=msg,
            save_dir=self.download_dir_var.get().strip() or "downloads",
            filename=fname,
            file_size=fsize,
            duration=dur,
        )
        key = f"link_{len(self._download_items_by_group)}"
        self._download_items_by_group[key] = [item]
        self._add_items_to_download_tab([item])
        self.link_status.configure(text=f"Added: {fname}", fg=C["success"])
        self.link_var.set("")

    def _on_dl_click(self, event):
        row = self.dl_tree.identify_row(event.y)
        col = self.dl_tree.identify_column(event.x)
        if not row or col != "#1":
            return
        vals = list(self.dl_tree.item(row, "values"))
        vals[0] = UNCHECKED if vals[0] == CHECKED else CHECKED
        self.dl_tree.item(row, values=vals)
        if self._selected_dl_item and str(id(self._selected_dl_item)) == row:
            self._update_preview_sel_btn()

    def _on_dl_select(self, event):
        sel = self.dl_tree.selection()
        if not sel:
            self._clear_preview()
            return
        item = self._find_dl_item(sel[0])
        if not item:
            self._clear_preview()
            return
        self._show_preview(item)

    def _on_start_all(self):
        if not self.client or not self._authorized:
            messagebox.showwarning("Warning", "Login first")
            return
        children = self.dl_tree.get_children()
        if not children:
            messagebox.showwarning("Warning", "No items. Fetch videos first.")
            return
        items = []
        for cid in children:
            vals = self.dl_tree.item(cid, "values")
            if vals[0] != CHECKED:
                continue
            if vals[5] in ("Queued", "Failed"):
                it = self._find_dl_item(cid)
                if it:
                    it.status = DownloadStatus.QUEUED
                    items.append(it)
        if not items:
            messagebox.showinfo("Info", "No checked/queued items to download")
            return
        self.download_queue = DownloadQueue(
            self.client,
            max_concurrent=int(self.concurrent_var.get().strip() or 3),
        )
        self.download_queue.set_on_update(self._on_dl_update)
        self.download_queue.add_items(items)
        self._log(f"Starting download of {len(items)} checked items...")
        self.btn_start.configure(state=tk.DISABLED)
        self.btn_pause.configure(state=tk.NORMAL, text="\u23F8 Pause")
        self.btn_cancel_all.configure(state=tk.NORMAL)
        self._run_async(self.download_queue.process())

    def _on_pause(self):
        if not self.download_queue:
            return
        paused = self.download_queue.toggle_pause()
        self.btn_pause.configure(text="\u25B6 Resume" if paused else "\u23F8 Pause")
        self._log("Download " + ("paused" if paused else "resumed"))

    def _on_cancel_all(self):
        if self.download_queue:
            self.download_queue.cancel_all()
            self._log("All downloads cancelled.")
        self.btn_start.configure(state=tk.NORMAL)
        self.btn_pause.configure(state=tk.DISABLED)
        self.btn_cancel_all.configure(state=tk.DISABLED)
        self._update_dl_status()

    def _on_remove_selected(self):
        selected = self.dl_tree.selection()
        for cid in selected:
            self.dl_tree.delete(cid)
            self._dl_item_ids.discard(cid)
            for item_list in self._download_items_by_group.values():
                item_list[:] = [it for it in item_list if str(id(it)) != cid]
        if not self.dl_tree.get_children():
            self.btn_start.configure(state=tk.DISABLED)
            self._clear_preview()
        self._update_dl_status()

    def _on_clear_completed(self):
        for cid in self.dl_tree.get_children():
            vals = self.dl_tree.item(cid, "values")
            if vals[5] in ("Completed", "Skipped (exists)", "Cancelled"):
                self.dl_tree.delete(cid)
                self._dl_item_ids.discard(cid)
                for item_list in self._download_items_by_group.values():
                    item_list[:] = [it for it in item_list if str(id(it)) != cid]
        if not self.dl_tree.get_children():
            self.btn_start.configure(state=tk.DISABLED)
            self._clear_preview()
        self._update_dl_status()

    def _on_dl_update(self, item):
        now = time.monotonic()
        item_id = id(item)
        last = self._update_throttle.get(item_id, 0)
        if now - last < 0.15 and item.status in (DownloadStatus.DOWNLOADING, DownloadStatus.QUEUED):
            return
        self._update_throttle[item_id] = now
        self.root.after(0, self._update_dl_item, item)

    def _update_dl_item(self, item):
        cid = str(id(item))
        if not self.dl_tree.exists(cid):
            return
        vals = list(self.dl_tree.item(cid, "values"))
        if item.status == DownloadStatus.DOWNLOADING:
            n = min(8, int(item.progress * 8 / 100))
            bar = "\u2588" * n + "\u2591" * (8 - n)
            vals[3] = self._format_speed(item.speed) if item.speed > 0 else "..."
            vals[5] = f"{bar} {item.progress:.0f}%"
        elif item.status == DownloadStatus.COMPLETED:
            vals[3] = "-"
            vals[5] = "Completed"
            self._toast(f"Done: {item.filename}")
        else:
            vals[3] = "-"
            vals[5] = item.status.value
        self.dl_tree.item(cid, values=vals)
        if self._selected_dl_item and str(id(self._selected_dl_item)) == cid:
            self._update_preview_eta(item)
        self._update_dl_status()
        if item.status in (DownloadStatus.COMPLETED, DownloadStatus.FAILED,
                           DownloadStatus.CANCELLED, DownloadStatus.SKIPPED):
            all_done = all(
                self.dl_tree.item(c, "values")[5] in (
                    "Completed", "Failed", "Cancelled", "Skipped (exists)"
                )
                for c in self._dl_item_ids
                if self.dl_tree.exists(c)
            )
            if all_done and self._dl_item_ids:
                self.root.after(500, self._on_all_done)

    def _on_all_done(self):
        if getattr(self, "_all_done_flag", False):
            return
        self._all_done_flag = True
        self.btn_start.configure(state=tk.NORMAL)
        self.btn_pause.configure(state=tk.DISABLED)
        self.btn_cancel_all.configure(state=tk.DISABLED)
        self._log("All downloads finished.")
        self._toast("All downloads completed!")
        self.root.after(2000, lambda: setattr(self, "_all_done_flag", False))

    def _update_dl_status(self):
        all_children = []
        for cid in self._dl_item_ids:
            if self.dl_tree.exists(cid):
                all_children.append(cid)
        total = len(all_children)
        if total == 0:
            self.dl_status_var.set("0 items")
            self.dl_progress["value"] = 0
            return
        counts = {"all": 0, "downloading": 0, "completed": 0, "failed": 0}
        checked = 0
        total_pct = 0.0
        for cid in all_children:
            vals = self.dl_tree.item(cid, "values")
            counts["all"] += 1
            if vals[0] == CHECKED:
                checked += 1
            s = vals[5]
            if s.endswith("%") or s == "Downloading":
                counts["downloading"] += 1
                total_pct += float(s.rstrip("%")) if s.endswith("%") else 0
            elif s in ("Completed", "Skipped (exists)"):
                counts["completed"] += 1
                total_pct += 100
            elif s in ("Failed", "Cancelled"):
                counts["failed"] += 1
        avg = total_pct / total if total > 0 else 0
        self.dl_status_var.set(f"{avg:.0f}% overall  ({checked} checked, {total} items)")
        self.dl_progress["value"] = avg
        # Update filter tab labels with counts
        label_map = {"all": "All", "downloading": "Downloading",
                     "completed": "Completed", "failed": "Failed"}
        for key, tab in self.dl_filter_tabs:
            c = counts.get(key, 0)
            tab.configure(text=f"  {label_map[key]} ({c})  ")

    # ----------------------------------------------------------------
    # Toast notification
    # ----------------------------------------------------------------
    def _toast(self, message, duration=3000):
        toast = tk.Frame(self.root, bg=C["card_bg"],
                         highlightbackground=C["border"],
                         highlightthickness=1)
        tk.Label(toast, text=message, bg=C["card_bg"], fg=C["text_primary"],
                 font=("Segoe UI", 10), padx=16, pady=8).pack()
        toast.place(relx=1.0, rely=1.0, anchor=tk.SE, x=-20, y=-50)
        self.root.after(duration, toast.destroy)

    def _format_eta(self, secs: float) -> str:
        if secs <= 0:
            return ""
        m, s = divmod(int(secs), 60)
        h, m = divmod(m, 60)
        if h:
            return f"~{h}h{m:02d}m"
        if m:
            return f"~{m}m{s:02d}s"
        return f"~{s}s"

    # ----------------------------------------------------------------
    # Filter tabs
    # ----------------------------------------------------------------
    def _set_dl_filter(self, key):
        self.dl_filter_var.set(key)
        self._update_filter_tabs()
        self._apply_dl_filter()

    def _update_filter_tabs(self):
        current = self.dl_filter_var.get()
        for key, tab in self.dl_filter_tabs:
            bg = C["sidebar_accent"] if key == current else C["content_bg"]
            fg = C["sidebar_fg"] if key == current else C["text_secondary"]
            tab.configure(bg=bg, fg=fg)

    def _filter_tab_hover(self, key, enter):
        current = self.dl_filter_var.get()
        if key == current:
            return
        for k, tab in self.dl_filter_tabs:
            if k == key:
                tab.configure(bg=C["sidebar_hover"] if enter else C["content_bg"])
                break

    def _apply_dl_filter(self):
        current = self.dl_filter_var.get()
        # Detach all
        for cid in self._dl_item_ids:
            if self.dl_tree.exists(cid):
                try:
                    self.dl_tree.detach(cid)
                except tk.TclError:
                    pass
        # Re-attach matching
        for cid in self._dl_item_ids:
            if not self.dl_tree.exists(cid):
                continue
            vals = self.dl_tree.item(cid, "values")
            show = self._status_matches_filter(vals[5], current)
            if show:
                try:
                    self.dl_tree.reattach(cid, "", tk.END)
                except tk.TclError:
                    pass

    def _status_matches_filter(self, status, filter_key):
        if filter_key == "all":
            return True
        if filter_key == "downloading":
            return status.endswith("%") or status == "Downloading"
        if filter_key == "completed":
            return status in ("Completed", "Skipped (exists)")
        if filter_key == "failed":
            return status in ("Failed", "Cancelled")
        return True

    def _update_preview_eta(self, item):
        if not self._selected_dl_item or str(id(self._selected_dl_item)) != str(id(item)):
            return
        eta_text = self._format_eta(item.eta) if item.eta > 0 else "-"
        self.preview_widgets["eta"].configure(text=eta_text)

    # ----------------------------------------------------------------
    # Context menu
    # ----------------------------------------------------------------
    def _on_dl_context(self, event):
        row = self.dl_tree.identify_row(event.y)
        if not row:
            return
        self.dl_tree.selection_set(row)
        vals = self.dl_tree.item(row, "values")
        status = vals[5]
        # Enable/disable menu items based on status
        self.dl_context.entryconfig(0, state=tk.NORMAL if status in ("Queued", "Failed") else tk.DISABLED)
        self.dl_context.entryconfig(1, state=tk.NORMAL if status.endswith("%") else tk.DISABLED)
        self.dl_context.tk_popup(event.x_root, event.y_root)

    def _ctx_start(self):
        sel = self.dl_tree.selection()
        if not sel:
            return
        items = []
        for cid in sel:
            vals = list(self.dl_tree.item(cid, "values"))
            if vals[5] not in ("Queued", "Failed"):
                continue
            if vals[0] != CHECKED:
                vals[0] = CHECKED
                self.dl_tree.item(cid, values=vals)
            it = self._find_dl_item(cid)
            if it:
                it.status = DownloadStatus.QUEUED
                items.append(it)
        if items:
            if not self.download_queue:
                self.download_queue = DownloadQueue(
                    self.client,
                    max_concurrent=int(self.concurrent_var.get().strip() or 3),
                )
                self.download_queue.set_on_update(self._on_dl_update)
            self.download_queue.add_items(items)
            self._log(f"Starting {len(items)} items...")
            self.btn_start.configure(state=tk.DISABLED)
            self.btn_pause.configure(state=tk.NORMAL, text="\u23F8 Pause")
            self.btn_cancel_all.configure(state=tk.NORMAL)
            self._run_async(self.download_queue.process())

    def _ctx_pause(self):
        sel = self.dl_tree.selection()
        if not sel:
            return
        for cid in sel:
            it = self._find_dl_item(cid)
            if it and it.status == DownloadStatus.DOWNLOADING:
                self.download_queue.cancel(it) if self.download_queue else None

    def _ctx_open_folder(self):
        sel = self.dl_tree.selection()
        if not sel:
            return
        for cid in sel:
            it = self._find_dl_item(cid)
            if it and it.full_path.exists():
                import subprocess
                subprocess.Popen(["explorer", "/select,", str(it.full_path)])
                break

    # ----------------------------------------------------------------
    # Keyboard shortcuts
    # ----------------------------------------------------------------
    def _on_space_key(self, event):
        if self._active_section == 2:  # Downloads
            sel = self.dl_tree.selection()
            if sel:
                for row in sel:
                    vals = list(self.dl_tree.item(row, "values"))
                    vals[0] = UNCHECKED if vals[0] == CHECKED else CHECKED
                    self.dl_tree.item(row, values=vals)
                if self._selected_dl_item and str(id(self._selected_dl_item)) == sel[0]:
                    self._update_preview_sel_btn()
            return "break"
        elif self._active_section == 1:  # Groups
            item = self.dialog_tree.focus()
            if item:
                vals = list(self.dialog_tree.item(item, "values"))
                vals[0] = UNCHECKED if vals[0] == CHECKED else CHECKED
                self.dialog_tree.item(item, values=vals)
            return "break"
