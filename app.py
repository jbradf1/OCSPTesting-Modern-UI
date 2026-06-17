import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, scrolledtext
from typing import List
import os
import sys
import io
from datetime import datetime

from ocsp_tester.runner import TestRunner, TestInputs
from ocsp_tester.exporters import export_results_json, export_results_csv
from ocsp_tester.config import ConfigManager, OCSPConfig
from ocsp_tester.monitor import OCSPMonitor


# ======================================================================
# Theme  ---  flip DARK_MODE to switch between the dark and light palette
# ======================================================================
DARK_MODE = True
FONT_UI = "Segoe UI"      # Windows default; Tk substitutes a sans-serif elsewhere
FONT_MONO = "Consolas"

_DARK = {
    "bg": "#15171c", "surface": "#1c1f26", "surface_alt": "#21252e",
    "field": "#262b35", "border": "#333a46",
    "text": "#e7e9ee", "muted": "#98a0ad",
    "accent": "#4c8dff", "accent_hover": "#6aa0ff",
    "success": "#46c267", "warning": "#e3b341",
    "danger": "#f1656a", "danger_hover": "#f47e82", "danger_bg": "#2a1f23",
    "info": "#6cb6ff",
}
_LIGHT = {
    "bg": "#eef1f5", "surface": "#ffffff", "surface_alt": "#f5f7fa",
    "field": "#ffffff", "border": "#d9dee5",
    "text": "#1c2430", "muted": "#6b7480",
    "accent": "#2f6fed", "accent_hover": "#2861d8",
    "success": "#1f9d52", "warning": "#b07d00",
    "danger": "#d64550", "danger_hover": "#c23842", "danger_bg": "#fdecec",
    "info": "#2f6fed",
}
PAL = _DARK if DARK_MODE else _LIGHT


class ConsoleRedirector:
    """Redirect stdout/stderr to a text widget"""
    def __init__(self, text_widget):
        self.text_widget = text_widget
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr

    def write(self, text):
        try:
            # Insert text into the widget
            self.text_widget.insert(tk.END, text)
            self.text_widget.see(tk.END)
            # Also write to original stdout for debugging
            self.original_stdout.write(text)
        except Exception:
            # If GUI is not available, just write to original stdout
            self.original_stdout.write(text)

    def flush(self):
        try:
            self.original_stdout.flush()
        except Exception:
            pass

    def restore(self):
        """Restore original stdout/stderr"""
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr


class OCSPTesterGUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("OCSP Server Test Suite")
        self.geometry("1280x860")
        self.minsize(1040, 720)

        # Apply the modern ttk styling before anything is built
        self._setup_styles()

        # Create menu bar
        self._create_menu_bar()

        # Initialize configuration manager
        self.config_manager = ConfigManager()
        self.config = self.config_manager.load_config()

        self.var_ocsp_url = tk.StringVar(value=self.config.ocsp_url)
        self.var_issuer_path = tk.StringVar(value=self.config.issuer_path)
        self.var_good_cert = tk.StringVar(value=self.config.good_cert)
        self.var_revoked_cert = tk.StringVar(value=self.config.revoked_cert)
        self.var_unknown_ca_cert = tk.StringVar(value=self.config.unknown_ca_cert)

        # Serial number variable for OCSP/CRL Monitor tab only
        self.var_cert_serial = tk.StringVar(value="")

        # Optional client signing for sigRequired/auth tests
        self.var_client_cert = tk.StringVar(value=self.config.client_cert)
        self.var_client_key = tk.StringVar(value=self.config.client_key)

        self.var_latency_samples = tk.IntVar(value=self.config.latency_samples)
        self.var_enable_load = tk.BooleanVar(value=self.config.enable_load_test)
        self.var_load_concurrency = tk.IntVar(value=self.config.load_concurrency)
        self.var_load_requests = tk.IntVar(value=self.config.load_requests)

        # Monitoring variables
        self.var_crl_override_url = tk.StringVar(value=self.config.crl_override_url)
        self.var_check_validity = tk.BooleanVar(value=self.config.check_validity)
        self.var_follow_log = tk.BooleanVar(value=self.config.follow_log)
        self.var_show_info = tk.BooleanVar(value=self.config.show_info)
        self.var_show_warn = tk.BooleanVar(value=self.config.show_warn)
        self.var_show_cmd = tk.BooleanVar(value=self.config.show_cmd)
        self.var_show_stderr = tk.BooleanVar(value=self.config.show_stderr)
        self.var_show_status = tk.BooleanVar(value=self.config.show_status)
        self.var_show_debug = tk.BooleanVar(value=self.config.show_debug)

        # Trust anchor configuration variables
        self.var_trust_anchor = tk.StringVar(value=self.config.trust_anchor_path)
        self.var_trust_anchor_type = tk.StringVar(value=self.config.trust_anchor_type)
        self.var_require_explicit_policy = tk.BooleanVar(value=self.config.require_explicit_policy)
        self.var_inhibit_policy_mapping = tk.BooleanVar(value=self.config.inhibit_policy_mapping)

        # Advanced testing options
        self.var_test_cryptographic_preferences = tk.BooleanVar(value=self.config.test_cryptographic_preferences)
        self.var_test_non_issued_certificates = tk.BooleanVar(value=self.config.test_non_issued_certificates)

        # OCSP response validation settings
        self.var_max_age_hours = tk.IntVar(value=self.config.max_age_hours)

        self.runner = TestRunner()
        self.results = []
        self.monitor = None  # Will be initialized after UI is built

        self._build_ui()

        # Initialize monitor after UI is built
        self.monitor = OCSPMonitor(log_callback=self._log_monitor, config=self.config)

        # Configure advanced testing options from config
        self.monitor.test_cryptographic_preferences = self.config.test_cryptographic_preferences
        self.monitor.test_non_issued_certificates = self.config.test_non_issued_certificates

        # Ensure debug logging is enabled by default
        self.var_show_debug.set(True)
        self._log_monitor("[DEBUG] Debug logging enabled by default\n")

        # Add some initial console output to demonstrate terminal capture
        # This will be captured by the Console Log tab
        print("=" * 60)
        print("OCSP Server Test Suite - Console Log")
        print("=" * 60)
        print(f"Application started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Python version: {sys.version}")
        print(f"Working directory: {os.getcwd()}")
        print("=" * 60)
        print("This console log captures all stdout/stderr output")
        print("including print statements, error messages, and")
        print("any other terminal output from the application.")
        print("=" * 60)

        # Set up cleanup when window is closed
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

    # ------------------------------------------------------------------
    # Styling
    # ------------------------------------------------------------------
    def _setup_styles(self) -> None:
        """Configure a cohesive, modern ttk theme from the PAL palette."""
        P = PAL
        self.configure(bg=P["bg"])
        st = ttk.Style(self)
        st.theme_use("clam")  # 'clam' honours custom colors on every platform

        # --- base ---
        st.configure(".", background=P["bg"], foreground=P["text"],
                     fieldbackground=P["field"], bordercolor=P["border"],
                     font=(FONT_UI, 10))

        # --- frames ---
        st.configure("TFrame", background=P["bg"])
        st.configure("Card.TFrame", background=P["surface"])
        st.configure("Sidebar.TFrame", background=P["surface_alt"])

        # --- labels ---
        st.configure("TLabel", background=P["surface"], foreground=P["text"])
        st.configure("Muted.TLabel", background=P["surface"], foreground=P["muted"],
                     font=(FONT_UI, 9))
        st.configure("Mono.TLabel", background=P["surface"], foreground=P["info"],
                     font=(FONT_MONO, 10))
        st.configure("Title.TLabel", background=P["bg"], foreground=P["text"],
                     font=(FONT_UI, 18, "bold"))
        st.configure("Subtitle.TLabel", background=P["bg"], foreground=P["muted"],
                     font=(FONT_UI, 10))
        st.configure("SidebarTitle.TLabel", background=P["surface_alt"],
                     foreground=P["text"], font=(FONT_UI, 15, "bold"))
        st.configure("SidebarSub.TLabel", background=P["surface_alt"],
                     foreground=P["muted"], font=(FONT_UI, 9))

        # --- cards (labelframes) ---
        st.configure("Card.TLabelframe", background=P["surface"],
                     bordercolor=P["border"], lightcolor=P["border"],
                     darkcolor=P["border"], relief="solid", borderwidth=1)
        st.configure("Card.TLabelframe.Label", background=P["surface"],
                     foreground=P["accent"], font=(FONT_UI, 11, "bold"))

        # --- buttons ---
        st.configure("Accent.TButton", background=P["accent"], foreground="#ffffff",
                     borderwidth=0, relief="flat", padding=(16, 9),
                     font=(FONT_UI, 10, "bold"))
        st.map("Accent.TButton",
               background=[("disabled", P["muted"]), ("active", P["accent_hover"])],
               foreground=[("disabled", "#dddddd")])

        st.configure("Secondary.TButton", background=P["surface_alt"],
                     foreground=P["text"], borderwidth=1, relief="flat",
                     bordercolor=P["border"], padding=(13, 8))
        st.map("Secondary.TButton", background=[("active", P["border"])])

        st.configure("Ghost.TButton", background=P["surface"], foreground=P["accent"],
                     borderwidth=1, relief="flat", bordercolor=P["border"],
                     padding=(11, 6))
        st.map("Ghost.TButton", background=[("active", P["surface_alt"])])

        st.configure("Danger.TButton", background=P["danger"], foreground="#ffffff",
                     borderwidth=0, relief="flat", padding=(13, 8),
                     font=(FONT_UI, 10, "bold"))
        st.map("Danger.TButton", background=[("active", P["danger_hover"])])

        # --- sidebar nav buttons ---
        st.configure("Nav.TButton", background=P["surface_alt"], foreground=P["text"],
                     borderwidth=0, relief="flat", anchor="w", padding=(16, 11),
                     font=(FONT_UI, 10))
        st.map("Nav.TButton", background=[("active", P["border"])])
        st.configure("NavActive.TButton", background=P["accent"], foreground="#ffffff",
                     borderwidth=0, relief="flat", anchor="w", padding=(16, 11),
                     font=(FONT_UI, 10, "bold"))
        st.map("NavActive.TButton", background=[("active", P["accent_hover"])])

        # --- inputs ---
        st.configure("TEntry", fieldbackground=P["field"], foreground=P["text"],
                     bordercolor=P["border"], lightcolor=P["border"],
                     darkcolor=P["border"], insertcolor=P["text"], padding=5)
        st.map("TEntry", bordercolor=[("focus", P["accent"])],
               lightcolor=[("focus", P["accent"])])
        st.configure("TSpinbox", fieldbackground=P["field"], foreground=P["text"],
                     bordercolor=P["border"], lightcolor=P["border"],
                     darkcolor=P["border"], arrowcolor=P["muted"], padding=4)
        st.map("TSpinbox", bordercolor=[("focus", P["accent"])])

        # --- checkbuttons / radiobuttons (on card surface) ---
        for cls in ("TCheckbutton", "TRadiobutton"):
            st.configure(cls, background=P["surface"], foreground=P["text"],
                         focuscolor=P["surface"], font=(FONT_UI, 10))
            st.map(cls, background=[("active", P["surface"])],
                   foreground=[("disabled", P["muted"])])

        # --- treeview ---
        st.configure("Modern.Treeview", background=P["field"],
                     fieldbackground=P["field"], foreground=P["text"],
                     bordercolor=P["border"], borderwidth=0, rowheight=28,
                     font=(FONT_UI, 10))
        st.map("Modern.Treeview", background=[("selected", P["accent"])],
               foreground=[("selected", "#ffffff")])
        st.configure("Modern.Treeview.Heading", background=P["surface_alt"],
                     foreground=P["muted"], relief="flat", padding=(10, 7),
                     font=(FONT_UI, 10, "bold"))
        st.map("Modern.Treeview.Heading", background=[("active", P["border"])])

        # --- progressbar / scrollbar / separator ---
        st.configure("Accent.Horizontal.TProgressbar", background=P["accent"],
                     troughcolor=P["surface_alt"], bordercolor=P["surface_alt"],
                     lightcolor=P["accent"], darkcolor=P["accent"])
        st.configure("TScrollbar", background=P["surface_alt"], troughcolor=P["bg"],
                     bordercolor=P["bg"], arrowcolor=P["muted"], relief="flat")
        st.map("TScrollbar", background=[("active", P["border"])])
        st.configure("TSeparator", background=P["border"])

    # ------------------------------------------------------------------
    # Small UI helpers
    # ------------------------------------------------------------------
    def _card(self, parent, title, expand=False):
        """A titled surface 'card' to group related controls."""
        c = ttk.Labelframe(parent, text=f"  {title}  ", style="Card.TLabelframe",
                           padding=16)
        c.pack(fill="both" if expand else "x", expand=expand, pady=(0, 16))
        return c

    def _view_header(self, parent, title, subtitle):
        ttk.Label(parent, text=title, style="Title.TLabel").pack(anchor="w")
        ttk.Label(parent, text=subtitle, style="Subtitle.TLabel").pack(
            anchor="w", pady=(2, 18))

    def _form_row(self, parent, row, label, var, browse=False):
        """A label + full-width entry (+ optional Browse) on a card grid."""
        ttk.Label(parent, text=label, style="TLabel").grid(
            row=row, column=0, sticky="w", padx=(0, 14), pady=7)
        entry = ttk.Entry(parent, textvariable=var)
        if browse:
            entry.grid(row=row, column=1, sticky="ew", pady=7)
            ttk.Button(parent, text="Browse\u2026", style="Ghost.TButton",
                       command=lambda: self._browse(var)).grid(
                row=row, column=2, sticky="w", padx=(10, 0), pady=7)
        else:
            entry.grid(row=row, column=1, columnspan=2, sticky="ew", pady=7)
        return entry

    def _style_text(self, widget):
        """Apply the dark console styling to a Text / ScrolledText widget."""
        widget.configure(bg=PAL["field"], fg=PAL["text"], insertbackground=PAL["text"],
                         relief="flat", borderwidth=0, font=(FONT_MONO, 10),
                         padx=12, pady=10, selectbackground=PAL["accent"],
                         selectforeground="#ffffff")

    def _select_view(self, key: str) -> None:
        self._views[key].tkraise()
        for k, btn in self._nav_buttons.items():
            btn.configure(style="NavActive.TButton" if k == key else "Nav.TButton")

    @staticmethod
    def _status_tag(status: str) -> str:
        return {"PASS": "pass", "FAIL": "fail", "WARN": "warn",
                "SKIP": "skip", "ERROR": "error", "INFO": "info"}.get(status, "")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def _on_closing(self):
        """Handle window closing"""
        if hasattr(self, 'console_redirector'):
            self.console_redirector.restore()
        self.destroy()

    def __del__(self):
        """Cleanup when GUI is destroyed"""
        if hasattr(self, 'console_redirector'):
            self.console_redirector.restore()

    # ------------------------------------------------------------------
    # Top-level layout: sidebar + switchable content views
    # ------------------------------------------------------------------
    def _make_scrollable(self, parent):
        """Put a vertically scrolling canvas inside *parent* and return the
        inner frame to add content to. Used for tall, form-heavy views so the
        controls below the fold (Run, results, details) stay reachable."""
        canvas = tk.Canvas(parent, bg=PAL["bg"], highlightthickness=0, bd=0)
        vbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vbar.set)
        vbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        interior = ttk.Frame(canvas)
        window_id = canvas.create_window((0, 0), window=interior, anchor="nw")

        def _on_interior_configure(_event):
            # Content changed size -> update the scrollable region.
            canvas.configure(scrollregion=canvas.bbox("all"))
        interior.bind("<Configure>", _on_interior_configure)

        def _on_canvas_configure(event):
            # Stretch the inner frame to the canvas width so inputs fill it.
            canvas.itemconfigure(window_id, width=event.width)
        canvas.bind("<Configure>", _on_canvas_configure)

        # Mouse-wheel scrolling, but only while the pointer is over this view.
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-event.delta / 120), "units")
        canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))

        return interior

    def _build_ui(self) -> None:
        container = ttk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True)
        container.columnconfigure(1, weight=1)
        container.rowconfigure(0, weight=1)

        sidebar = ttk.Frame(container, style="Sidebar.TFrame", width=240)
        sidebar.grid(row=0, column=0, sticky="ns")
        sidebar.grid_propagate(False)
        self._build_sidebar(sidebar)

        content = ttk.Frame(container)
        content.grid(row=0, column=1, sticky="nsew")
        content.rowconfigure(0, weight=1)
        content.columnconfigure(0, weight=1)

        # Monitor and console are dominated by a log that should fill the
        # window, so they don't scroll. The testing view is a long form, so it
        # lives inside a vertical scroll container.
        self.monitor_frame = ttk.Frame(content, padding=24)
        self.console_log_frame = ttk.Frame(content, padding=24)

        test_outer = ttk.Frame(content)
        test_interior = self._make_scrollable(test_outer)
        self.test_frame = ttk.Frame(test_interior, padding=24)
        self.test_frame.pack(fill="both", expand=True)

        self._views = {
            "monitor": self.monitor_frame,
            "testing": test_outer,
            "console": self.console_log_frame,
        }
        for f in self._views.values():
            f.grid(row=0, column=0, sticky="nsew")

        self._build_monitoring_ui()
        self._build_testing_ui()
        self._build_console_log_ui()
        self._select_view("monitor")

    def _build_sidebar(self, sidebar) -> None:
        ttk.Label(sidebar, text="OCSP Suite", style="SidebarTitle.TLabel").pack(
            anchor="w", padx=20, pady=(26, 2))
        ttk.Label(sidebar, text="Test \u00b7 Monitor \u00b7 Validate",
                  style="SidebarSub.TLabel").pack(anchor="w", padx=20, pady=(0, 26))

        self._nav_buttons = {}
        for key, label in (("monitor", "OCSP / CRL Monitor"),
                           ("testing", "Conformance Testing"),
                           ("console", "Console Log")):
            btn = ttk.Button(sidebar, text=label, style="Nav.TButton",
                             command=lambda k=key: self._select_view(k))
            btn.pack(fill="x", padx=12, pady=2)
            self._nav_buttons[key] = btn

    # ------------------------------------------------------------------
    # Menu bar
    # ------------------------------------------------------------------
    def _create_menu_bar(self) -> None:
        """Create the menu bar with File and Help menus"""
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)

        # Config submenu
        config_menu = tk.Menu(file_menu, tearoff=0)
        file_menu.add_cascade(label="Config", menu=config_menu)
        config_menu.add_command(label="Save Config", command=self._save_config)
        config_menu.add_command(label="Load Config", command=self._load_config)

        # Export submenu
        export_menu = tk.Menu(file_menu, tearoff=0)
        file_menu.add_cascade(label="Export", menu=export_menu)
        export_menu.add_command(label="Export as JSON", command=self._export_json)
        export_menu.add_command(label="Export as CSV", command=self._export_csv)

        # Separator
        file_menu.add_separator()

        # Exit
        file_menu.add_command(label="Exit", command=self.quit)

        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self._show_about)

        # Tint the drop-down menus to match the theme (native menubars on
        # Windows are OS-drawn and may ignore this, which is fine).
        for m in (file_menu, config_menu, export_menu, help_menu):
            m.configure(background=PAL["surface"], foreground=PAL["text"],
                        activebackground=PAL["accent"], activeforeground="#ffffff",
                        borderwidth=0)

    # ------------------------------------------------------------------
    # Conformance Testing view
    # ------------------------------------------------------------------
    def _build_testing_ui(self) -> None:
        f = self.test_frame
        self._view_header(
            f, "Conformance Testing",
            "Configure inputs and run the OCSP / CRL conformance test suite.")

        # --- Endpoints & certificates ---
        card = self._card(f, "Endpoints & Certificates")
        card.columnconfigure(1, weight=1)
        self._form_row(card, 0, "OCSP URL", self.var_ocsp_url)
        self._form_row(card, 1, "CRL Override URL", self.var_crl_override_url)
        self._form_row(card, 2, "Issuer CA", self.var_issuer_path, browse=True)
        self._form_row(card, 3, "Known GOOD cert", self.var_good_cert, browse=True)
        self._form_row(card, 4, "Known REVOKED cert", self.var_revoked_cert, browse=True)
        self._form_row(card, 5, "Unknown-CA cert (optional)", self.var_unknown_ca_cert, browse=True)
        self._form_row(card, 6, "Client cert (optional)", self.var_client_cert, browse=True)
        self._form_row(card, 7, "Client key (optional)", self.var_client_key, browse=True)
        self._form_row(card, 8, "Trust Anchor (optional)", self.var_trust_anchor, browse=True)

        # --- Two columns: trust anchor config + test categories ---
        row = ttk.Frame(f)
        row.pack(fill="x", pady=(0, 16))
        row.columnconfigure(0, weight=1, uniform="cols")
        row.columnconfigure(1, weight=1, uniform="cols")

        ta = ttk.Labelframe(row, text="  Trust Anchor Configuration  ",
                            style="Card.TLabelframe", padding=16)
        ta.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        ta.columnconfigure(1, weight=1)

        ttk.Label(ta, text="Type", style="TLabel").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=6)
        typ = ttk.Frame(ta, style="Card.TFrame")
        typ.grid(row=0, column=1, sticky="w", pady=6)
        ttk.Radiobutton(typ, text="Root CA", variable=self.var_trust_anchor_type, value="root").pack(side="left", padx=(0, 12))
        ttk.Radiobutton(typ, text="Bridge CA", variable=self.var_trust_anchor_type, value="bridge").pack(side="left", padx=(0, 12))
        ttk.Radiobutton(typ, text="Intermediate CA", variable=self.var_trust_anchor_type, value="intermediate").pack(side="left")

        ttk.Label(ta, text="Validation", style="TLabel").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=6)
        val = ttk.Frame(ta, style="Card.TFrame")
        val.grid(row=1, column=1, sticky="w", pady=6)
        ttk.Checkbutton(val, text="Require explicit policy", variable=self.var_require_explicit_policy).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(val, text="Inhibit policy mapping", variable=self.var_inhibit_policy_mapping).pack(side="left")

        ttk.Label(ta, text="Advanced", style="TLabel").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=6)
        adv = ttk.Frame(ta, style="Card.TFrame")
        adv.grid(row=2, column=1, sticky="w", pady=6)
        ttk.Checkbutton(adv, text="Cryptographic Preferences", variable=self.var_test_cryptographic_preferences).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(adv, text="Non-Issued Certificates", variable=self.var_test_non_issued_certificates).pack(side="left")

        ttk.Label(ta, text="OCSP Max Age", style="TLabel").grid(row=3, column=0, sticky="w", padx=(0, 12), pady=6)
        age = ttk.Frame(ta, style="Card.TFrame")
        age.grid(row=3, column=1, sticky="w", pady=6)
        ttk.Spinbox(age, from_=1, to=168, width=6, textvariable=self.var_max_age_hours).pack(side="left")
        ttk.Label(age, text="hours (1\u2013168, default 24)", style="Muted.TLabel").pack(side="left", padx=(8, 0))

        tc = ttk.Labelframe(row, text="  Test Categories  ",
                            style="Card.TLabelframe", padding=16)
        tc.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        self.var_enable_ocsp_tests = tk.BooleanVar(value=True)
        self.var_enable_crl_tests = tk.BooleanVar(value=True)
        self.var_enable_path_validation_tests = tk.BooleanVar(value=True)
        self.var_enable_ikev2_tests = tk.BooleanVar(value=False)
        self.var_enable_federal_bridge_tests = tk.BooleanVar(value=False)
        self.var_enable_performance_tests = tk.BooleanVar(value=False)

        ttk.Checkbutton(tc, text="OCSP Tests", variable=self.var_enable_ocsp_tests).grid(row=0, column=0, sticky="w", padx=5, pady=4)
        ttk.Checkbutton(tc, text="CRL Tests", variable=self.var_enable_crl_tests).grid(row=0, column=1, sticky="w", padx=5, pady=4)
        ttk.Checkbutton(tc, text="Path Validation Tests", variable=self.var_enable_path_validation_tests).grid(row=1, column=0, sticky="w", padx=5, pady=4)
        ttk.Checkbutton(tc, text="IKEv2 Tests", variable=self.var_enable_ikev2_tests).grid(row=1, column=1, sticky="w", padx=5, pady=4)
        ttk.Checkbutton(tc, text="Federal Bridge Tests", variable=self.var_enable_federal_bridge_tests).grid(row=2, column=0, sticky="w", padx=5, pady=4)
        ttk.Checkbutton(tc, text="Performance Tests", variable=self.var_enable_performance_tests).grid(row=2, column=1, sticky="w", padx=5, pady=4)

        select_frame = ttk.Frame(tc, style="Card.TFrame")
        select_frame.grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Button(select_frame, text="Select All", style="Ghost.TButton", command=self._select_all_test_categories).pack(side="left", padx=(0, 6))
        ttk.Button(select_frame, text="Select None", style="Ghost.TButton", command=self._select_none_test_categories).pack(side="left", padx=(0, 6))
        ttk.Button(select_frame, text="Default", style="Ghost.TButton", command=self._select_default_test_categories).pack(side="left")

        # --- Performance ---
        perf = self._card(f, "Performance")
        ttk.Label(perf, text="Latency samples", style="TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(perf, textvariable=self.var_latency_samples, width=8).grid(row=0, column=1, sticky="w", padx=(0, 18), pady=4)
        ttk.Checkbutton(perf, text="Enable load test", variable=self.var_enable_load).grid(row=0, column=2, sticky="w", padx=(0, 18), pady=4)
        ttk.Label(perf, text="Concurrency", style="TLabel").grid(row=0, column=3, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(perf, textvariable=self.var_load_concurrency, width=8).grid(row=0, column=4, sticky="w", padx=(0, 18), pady=4)
        ttk.Label(perf, text="Total requests", style="TLabel").grid(row=0, column=5, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(perf, textvariable=self.var_load_requests, width=8).grid(row=0, column=6, sticky="w", pady=4)

        # --- Run / progress ---
        act = self._card(f, "Run")
        self.run_tests_btn = ttk.Button(act, text="Run Tests", style="Accent.TButton", command=self._run_tests)
        self.run_tests_btn.pack(side="left")
        self.progress_var = tk.StringVar(value="Ready")
        self.progress_label = ttk.Label(act, textvariable=self.progress_var, style="TLabel")
        self.progress_label.pack(side="left", padx=14)
        self.progress_bar = ttk.Progressbar(act, mode='indeterminate', style="Accent.Horizontal.TProgressbar")
        self.progress_bar.pack(side="left", padx=(8, 0), fill="x", expand=True)

        # --- Results table ---
        res = self._card(f, "Test Results", expand=True)
        tree_wrap = ttk.Frame(res, style="Card.TFrame")
        tree_wrap.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(tree_wrap, columns=("category", "name", "status", "message"),
                                 show="headings", style="Modern.Treeview", height=12)
        self.tree.heading("category", text="Category", command=lambda: self._sort_tree("category"))
        self.tree.heading("name", text="Test", command=lambda: self._sort_tree("name"))
        self.tree.heading("status", text="Status", command=lambda: self._sort_tree("status"))
        self.tree.heading("message", text="Message", command=lambda: self._sort_tree("message"))
        self.tree.column("category", width=160, anchor="w")
        self.tree.column("status", width=90, anchor="w")
        vscroll = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vscroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vscroll.pack(side="right", fill="y")

        # Status colors
        self.tree.tag_configure("pass", foreground=PAL["success"])
        self.tree.tag_configure("fail", foreground=PAL["danger"], background=PAL["danger_bg"])
        self.tree.tag_configure("warn", foreground=PAL["warning"])
        self.tree.tag_configure("skip", foreground=PAL["muted"])
        self.tree.tag_configure("error", foreground=PAL["danger"], background=PAL["danger_bg"])
        self.tree.tag_configure("info", foreground=PAL["info"])

        # Initialize sorting state
        self.tree_sort_column = None
        self.tree_sort_reverse = False

        # --- Details ---
        det = self._card(f, "Selected Test Details")
        self.details = tk.Text(det, height=10)
        self._style_text(self.details)
        self.details.pack(fill="both", expand=False)

        self.tree.bind("<<TreeviewSelect>>", self._on_select)

    # ------------------------------------------------------------------
    # OCSP / CRL Monitor view
    # ------------------------------------------------------------------
    def _build_monitoring_ui(self) -> None:
        f = self.monitor_frame
        self._view_header(
            f, "OCSP / CRL Monitor",
            "Run live OCSP and CRL status checks against a certificate.")

        # --- Certificate & issuer ---
        card = self._card(f, "Certificate & Issuer")
        card.columnconfigure(1, weight=1)
        self._form_row(card, 0, "Issuer Certificate", self.var_issuer_path, browse=True)
        self._form_row(card, 1, "Certificate File", self.var_good_cert, browse=True)

        ttk.Label(card, text="OR Serial Number", style="TLabel").grid(row=2, column=0, sticky="w", padx=(0, 14), pady=7)
        serial_wrap = ttk.Frame(card, style="Card.TFrame")
        serial_wrap.grid(row=2, column=1, columnspan=2, sticky="ew", pady=7)
        serial_wrap.columnconfigure(0, weight=1)
        ttk.Entry(serial_wrap, textvariable=self.var_cert_serial).grid(row=0, column=0, sticky="ew")
        ttk.Label(serial_wrap, text="hex 0x123  or  decimal 123", style="Muted.TLabel").grid(row=0, column=1, padx=(10, 0))

        # --- Endpoints ---
        urls = self._card(f, "Endpoints")
        urls.columnconfigure(1, weight=1)
        self._form_row(urls, 0, "OCSP URL", self.var_ocsp_url)
        self._form_row(urls, 1, "CRL Override URL", self.var_crl_override_url)

        # --- Options ---
        opts = self._card(f, "Options")
        ttk.Checkbutton(opts, text="Check certificate validity period", variable=self.var_check_validity).pack(anchor="w")

        # --- Actions ---
        actions = self._card(f, "Actions")
        ttk.Button(actions, text="Run OCSP Check", style="Accent.TButton", command=self._run_ocsp_monitor).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Run CRL Check", style="Accent.TButton", command=self._run_crl_monitor).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Show Test Results", style="Secondary.TButton", command=self._show_test_results_in_monitor).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Clear Log", style="Secondary.TButton", command=self._clear_monitor_log).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Clear Response", style="Secondary.TButton", command=self._clear_response).pack(side="left")

        # --- Log filters ---
        filt = self._card(f, "Log Filters")
        ttk.Checkbutton(filt, text="Follow log", variable=self.var_follow_log).pack(side="left", padx=(0, 14))
        for label, var in (("[INFO]", self.var_show_info), ("[WARN]", self.var_show_warn),
                           ("[DEBUG]", self.var_show_debug), ("[CMD]", self.var_show_cmd),
                           ("[STDERR]", self.var_show_stderr), ("[STATUS]", self.var_show_status)):
            ttk.Checkbutton(filt, text=label, variable=var).pack(side="left", padx=(0, 10))
        ttk.Button(filt, text="Enable All Debug", style="Ghost.TButton", command=self._enable_all_debug).pack(side="left", padx=(10, 0))

        # --- Latest response summaries ---
        self.ocsp_summary = tk.StringVar(value="")
        self.crl_summary = tk.StringVar(value="")
        resp = self._card(f, "Latest Response")
        ttk.Label(resp, textvariable=self.ocsp_summary, style="Mono.TLabel", justify="left").pack(anchor="w")
        ttk.Label(resp, textvariable=self.crl_summary, style="Mono.TLabel", justify="left").pack(anchor="w", pady=(6, 0))

        # --- Output log ---
        log = self._card(f, "Monitor Log", expand=True)
        self.monitor_output = scrolledtext.ScrolledText(log, height=16)
        self._style_text(self.monitor_output)
        self.monitor_output.pack(fill="both", expand=True)

    # ------------------------------------------------------------------
    # Console Log view
    # ------------------------------------------------------------------
    def _build_console_log_ui(self) -> None:
        """Build the console log UI"""
        f = self.console_log_frame
        self._view_header(
            f, "Console Log",
            "Captures all stdout / stderr output from the application.")

        card = self._card(f, "Output", expand=True)
        self.console_log_output = scrolledtext.ScrolledText(card, height=24)
        self._style_text(self.console_log_output)
        self.console_log_output.pack(fill="both", expand=True)

        # Set up stdout/stderr redirection after GUI is built
        self.console_redirector = ConsoleRedirector(self.console_log_output)
        # Store original stdout/stderr for restoration if needed
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        sys.stdout = self.console_redirector
        sys.stderr = self.console_redirector

    # ==================================================================
    # Everything below is unchanged application logic
    # ==================================================================
    def _browse(self, var: tk.StringVar) -> None:
        path = filedialog.askopenfilename(filetypes=[("Certificates", "*.pem *.cer *.crt *.der"), ("All files", "*.*")])
        if path:
            var.set(path)

    def _collect_inputs(self) -> TestInputs:
        # Update config with current checkbox values before creating TestInputs
        self.config.test_cryptographic_preferences = bool(self.var_test_cryptographic_preferences.get())
        self.config.test_non_issued_certificates = bool(self.var_test_non_issued_certificates.get())
        self.config.max_age_hours = int(self.var_max_age_hours.get())

        return TestInputs(
            ocsp_url=self.var_ocsp_url.get().strip(),
            issuer_path=self.var_issuer_path.get().strip(),
            known_good_cert_path=self.var_good_cert.get().strip() or None,
            known_revoked_cert_path=self.var_revoked_cert.get().strip() or None,
            unknown_ca_cert_path=self.var_unknown_ca_cert.get().strip() or None,
            client_sign_cert_path=self.var_client_cert.get().strip() or None,
            client_sign_key_path=self.var_client_key.get().strip() or None,
            latency_samples=max(1, int(self.var_latency_samples.get() or 1)),
            enable_load_test=bool(self.var_enable_load.get()),
            load_concurrency=max(1, int(self.var_load_concurrency.get() or 1)),
            load_requests=max(1, int(self.var_load_requests.get() or 1)),
            crl_override_url=self.var_crl_override_url.get().strip() or None,
            trust_anchor_path=self.var_trust_anchor.get().strip() or None,
            trust_anchor_type=self.var_trust_anchor_type.get(),
            require_explicit_policy=bool(self.var_require_explicit_policy.get()),
            inhibit_policy_mapping=bool(self.var_inhibit_policy_mapping.get()),
            config=self.config
        )

    def _run_tests(self) -> None:
        inputs = self._collect_inputs()
        if not inputs.ocsp_url or not inputs.issuer_path:
            messagebox.showerror("Input error", "OCSP URL and Issuer CA are required.")
            return

        # Check if any test categories are selected
        if not any([
            self.var_enable_ocsp_tests.get(),
            self.var_enable_crl_tests.get(),
            self.var_enable_path_validation_tests.get(),
            self.var_enable_ikev2_tests.get(),
            self.var_enable_federal_bridge_tests.get(),
            self.var_enable_performance_tests.get()
        ]):
            messagebox.showerror("Input error", "Please select at least one test category to run.")
            return

        # Clear previous results and show progress
        self.tree.delete(*self.tree.get_children())
        self.details.delete("1.0", tk.END)

        # Update UI to show tests are running
        self.run_tests_btn.config(state='disabled', text='Running...')
        self.progress_var.set("Running tests...")
        self.progress_bar.start()

        # Start test execution in background thread
        threading.Thread(target=self._run_tests_thread, args=(inputs,), daemon=True).start()

        # Show debug reminder
        if not self.var_show_debug.get():
            messagebox.showinfo("Debug Logging", "Debug logging is currently disabled. Enable [DEBUG] checkbox in the OCSP/CRL Monitor tab to see detailed test execution information.")

    def _run_tests_thread(self, inputs: TestInputs) -> None:
        try:
            # Update progress with detailed steps
            self.progress_var.set("Initializing tests...")
            self._log_monitor(f"[INFO] Starting test execution at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            self._log_monitor(f"[INFO] OCSP URL: {inputs.ocsp_url}\n")
            self._log_monitor(f"[INFO] Issuer path: {inputs.issuer_path}\n")

            # Enable debug logging for test execution
            self._log_monitor("[DEBUG] Debug logging enabled for test execution\n")
            self._log_monitor(f"[DEBUG] Test configuration: latency_samples={inputs.latency_samples}, load_test={inputs.enable_load_test}\n")
            self._log_monitor(f"[DEBUG] Certificate paths - Good: {inputs.known_good_cert_path}, Revoked: {inputs.known_revoked_cert_path}\n")

            # Test runner instantiation
            self.progress_var.set("Creating test runner...")
            self._log_monitor("[INFO] Creating TestRunner instance...\n")
            self._log_monitor("[DEBUG] TestRunner initialization starting...\n")
            runner = TestRunner(log_callback=self._log_monitor)
            self._log_monitor("[DEBUG] TestRunner initialization completed\n")
            self._log_monitor("[INFO] TestRunner created successfully\n")

            # Run the tests with timeout protection
            self.progress_var.set("Executing tests...")
            self._log_monitor("[INFO] Starting test execution...\n")
            self._log_monitor("[DEBUG] Test execution thread starting...\n")

            # Windows-compatible timeout mechanism
            import threading
            import time

            # Add timeout protection using threading
            timeout_occurred = threading.Event()
            test_results = None
            test_exception = None

            def run_tests_with_timeout():
                nonlocal test_results, test_exception
                try:
                    self._log_monitor("[DEBUG] TestRunner.run_all() called\n")
                    # Pass selected test categories to the runner
                    test_categories = {
                        'ocsp_tests': self.var_enable_ocsp_tests.get(),
                        'crl_tests': self.var_enable_crl_tests.get(),
                        'path_validation_tests': self.var_enable_path_validation_tests.get(),
                        'ikev2_tests': self.var_enable_ikev2_tests.get(),
                        'federal_bridge_tests': self.var_enable_federal_bridge_tests.get(),
                        'performance_tests': self.var_enable_performance_tests.get()
                    }
                    self._log_monitor(f"[DEBUG] Test categories enabled: {test_categories}\n")
                    test_results = runner.run_all(inputs, test_categories=test_categories)
                    self._log_monitor(f"[DEBUG] TestRunner.run_all() completed with {len(test_results)} results\n")
                except Exception as e:
                    test_exception = e
                    self._log_monitor(f"[DEBUG] TestRunner.run_all() failed with exception: {str(e)}\n")

            # Start test execution in a separate thread
            test_thread = threading.Thread(target=run_tests_with_timeout, daemon=True)
            test_thread.start()

            self._log_monitor("[DEBUG] Test execution thread started, waiting for completion...\n")

            # Wait for completion with timeout (5 minutes)
            test_thread.join(timeout=300)  # 5 minutes

            if test_thread.is_alive():
                self._log_monitor("[DEBUG] Test execution thread timed out after 5 minutes\n")
                # Test is still running, timeout occurred
                self._log_monitor("[ERROR] Test execution timed out after 5 minutes\n")
                raise Exception("Test execution timed out")
            else:
                self._log_monitor("[DEBUG] Test execution thread completed successfully\n")

            if test_exception:
                self._log_monitor(f"[DEBUG] Test execution failed with exception: {str(test_exception)}\n")
                raise test_exception

            self._log_monitor(f"[DEBUG] Results processing starting...\n")
            self._log_monitor(f"[DEBUG] Total test results received: {len(test_results)}\n")

            self.results = test_results
            self._log_monitor(f"[INFO] Test execution completed successfully - {len(self.results)} results\n")

            # Update progress
            self.progress_var.set("Processing results...")
            self._log_monitor("[INFO] Processing test results...\n")

            # Populate the tree with results
            for i, r in enumerate(self.results):
                self.tree.insert("", tk.END, iid=r.id,
                                 values=(r.category, r.name, r.status.value, r.message),
                                 tags=(self._status_tag(r.status.value),))
                if i % 5 == 0:  # Update progress every 5 tests
                    self.progress_var.set(f"Processing results... ({i+1}/{len(self.results)})")

            # Update progress
            self.progress_var.set("Updating monitoring window...")
            self._log_monitor("[INFO] Updating monitoring window...\n")

            # Automatically show test results in monitoring window
            self._show_test_results_in_monitor()

            # Also log to monitoring window that tests completed
            self._log_monitor(f"\n[INFO] Test execution completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            self._log_monitor(f"[INFO] Total tests executed: {len(self.results)}\n")

            # Count results by status
            status_counts = {}
            for result in self.results:
                status = result.status.value
                status_counts[status] = status_counts.get(status, 0) + 1

            self._log_monitor(f"[INFO] Test results summary: {status_counts}\n")
            self._log_monitor("="*80 + "\n")

            # Update progress to show completion
            self.progress_var.set(f"Completed - {len(self.results)} tests run")

        except Exception as exc:
            self.progress_var.set("Error occurred")
            self._log_monitor(f"[ERROR] Test execution failed: {str(exc)}\n")
            self._log_monitor(f"[ERROR] Error type: {type(exc).__name__}\n")
            import traceback
            self._log_monitor(f"[ERROR] Traceback: {traceback.format_exc()}\n")
            messagebox.showerror("Execution error", str(exc))
        finally:
            # Re-enable UI elements
            self.run_tests_btn.config(state='normal', text='Run Tests')
            self.progress_bar.stop()

    def _on_select(self, _event=None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        rid = sel[0]
        match = next((r for r in self.results if r.id == rid), None)
        self.details.delete("1.0", tk.END)
        if match:
            self.details.insert(tk.END, f"ID: {match.id}\n")
            self.details.insert(tk.END, f"Category: {match.category}\n")
            self.details.insert(tk.END, f"Name: {match.name}\n")
            self.details.insert(tk.END, f"Status: {match.status.value}\n")
            self.details.insert(tk.END, f"Message: {match.message}\n\n")

            # Enhanced details display for Path Validation tests
            if "Path Validation" in match.category:
                self.details.insert(tk.END, "=== DETAILED TEST INFORMATION ===\n\n")

            def format_details(data, indent_level=0):
                """Recursively format nested details with proper indentation"""
                indent = "  " * indent_level
                for k, v in data.items():
                    if isinstance(v, dict):
                        self.details.insert(tk.END, f"{indent}{k}:\n")
                        format_details(v, indent_level + 1)
                    elif isinstance(v, list):
                        self.details.insert(tk.END, f"{indent}{k}:\n")
                        for item in v:
                            if isinstance(item, dict):
                                format_details(item, indent_level + 1)
                            else:
                                self.details.insert(tk.END, f"{indent}  - {item}\n")
                    else:
                        self.details.insert(tk.END, f"{indent}{k}: {v}\n")
                if indent_level == 0:
                    self.details.insert(tk.END, "\n")

            format_details(match.details)

    def _sort_tree(self, column: str) -> None:
        """Sort the tree by the specified column"""
        # Determine if we're sorting the same column (toggle reverse) or a new column
        if self.tree_sort_column == column:
            self.tree_sort_reverse = not self.tree_sort_reverse
        else:
            self.tree_sort_column = column
            self.tree_sort_reverse = False

        # Get all items from the tree
        items = []
        for item in self.tree.get_children():
            values = self.tree.item(item)['values']
            items.append((item, values))

        # Define column mapping for sorting
        column_map = {
            "category": 0,
            "name": 1,
            "status": 2,
            "message": 3
        }

        # Sort the items
        col_index = column_map.get(column, 0)

        # Custom sorting for status column (PASS, FAIL, WARN, SKIP, ERROR)
        if column == "status":
            status_order = {"PASS": 0, "FAIL": 1, "WARN": 2, "SKIP": 3, "ERROR": 4}
            items.sort(key=lambda x: status_order.get(x[1][col_index], 5), reverse=self.tree_sort_reverse)
        else:
            # Regular string sorting for other columns
            items.sort(key=lambda x: x[1][col_index].lower() if x[1][col_index] else "", reverse=self.tree_sort_reverse)

        # Clear the tree and re-insert sorted items
        for item in self.tree.get_children():
            self.tree.delete(item)

        for item_id, values in items:
            self.tree.insert("", tk.END, iid=item_id, values=values,
                             tags=(self._status_tag(values[2]),))

        # Update column headers to show sort direction
        for col in ["category", "name", "status", "message"]:
            if col == column:
                arrow = " \u2193" if self.tree_sort_reverse else " \u2191"
                self.tree.heading(col, text=self.tree.heading(col)['text'].replace(" \u2191", "").replace(" \u2193", "") + arrow)
            else:
                # Remove arrows from other columns
                self.tree.heading(col, text=self.tree.heading(col)['text'].replace(" \u2191", "").replace(" \u2193", ""))

    def _export_json(self) -> None:
        if not self.results:
            messagebox.showinfo("Export", "No results to export yet.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not path:
            return
        export_results_json(self.results, path)
        messagebox.showinfo("Export", f"Saved to {path}")

    def _export_csv(self) -> None:
        if not self.results:
            messagebox.showinfo("Export", "No results to export yet.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        export_results_csv(self.results, path)
        messagebox.showinfo("Export", f"Saved to {path}")

    def _show_about(self) -> None:
        """Show about dialog"""
        about_text = """OCSP Server Test Suite
        
A comprehensive testing application for OCSP (Online Certificate Status Protocol) servers with both GUI and monitoring capabilities.

Features:
• Comprehensive OCSP Testing
• CRL Monitoring  
• Certificate Validation
• Export Capabilities (JSON/CSV)
• Advanced Testing Options

Version: 2.1.0
License: MIT License

Copyright (c) 2025 OCSP Testing Tool"""

        messagebox.showinfo("About OCSP Server Test Suite", about_text)

    def _save_config(self) -> None:
        """Save current configuration to file"""
        try:
            # Update config with current values
            self.config.ocsp_url = self.var_ocsp_url.get().strip()
            self.config.issuer_path = self.var_issuer_path.get().strip()
            self.config.good_cert = self.var_good_cert.get().strip()
            # Persist optional serial number used in monitor OCSP checks
            self.config.cert_serial = self.var_cert_serial.get().strip()
            self.config.revoked_cert = self.var_revoked_cert.get().strip()
            self.config.unknown_ca_cert = self.var_unknown_ca_cert.get().strip()
            self.config.client_cert = self.var_client_cert.get().strip()
            self.config.client_key = self.var_client_key.get().strip()
            self.config.latency_samples = max(1, int(self.var_latency_samples.get() or 1))
            self.config.enable_load_test = bool(self.var_enable_load.get())
            self.config.load_concurrency = max(1, int(self.var_load_concurrency.get() or 1))
            self.config.load_requests = max(1, int(self.var_load_requests.get() or 1))

            # Update monitoring settings
            self.config.crl_override_url = self.var_crl_override_url.get().strip()
            self.config.check_validity = bool(self.var_check_validity.get())
            self.config.follow_log = bool(self.var_follow_log.get())
            self.config.show_info = bool(self.var_show_info.get())
            self.config.show_warn = bool(self.var_show_warn.get())
            self.config.show_debug = bool(self.var_show_debug.get())
            self.config.show_cmd = bool(self.var_show_cmd.get())
            self.config.show_stderr = bool(self.var_show_stderr.get())
            self.config.show_status = bool(self.var_show_status.get())

            # Update trust anchor settings
            self.config.trust_anchor_path = self.var_trust_anchor.get().strip()
            self.config.trust_anchor_type = self.var_trust_anchor_type.get()
            self.config.require_explicit_policy = bool(self.var_require_explicit_policy.get())
            self.config.inhibit_policy_mapping = bool(self.var_inhibit_policy_mapping.get())

            # Update advanced testing settings
            self.config.test_cryptographic_preferences = bool(self.var_test_cryptographic_preferences.get())
            self.config.test_non_issued_certificates = bool(self.var_test_non_issued_certificates.get())

            # Update OCSP response validation settings
            self.config.max_age_hours = int(self.var_max_age_hours.get())

            if self.config_manager.save_config(self.config):
                messagebox.showinfo("Config", "Configuration saved successfully!")
            else:
                messagebox.showerror("Config", "Failed to save configuration.")
        except Exception as exc:
            messagebox.showerror("Config", f"Error saving configuration: {exc}")

    def _load_config(self) -> None:
        """Load configuration from file"""
        try:
            self.config = self.config_manager.load_config()

            # Update UI with loaded values
            self.var_ocsp_url.set(self.config.ocsp_url)
            self.var_issuer_path.set(self.config.issuer_path)
            self.var_good_cert.set(self.config.good_cert)
            # Restore optional serial number if present
            self.var_cert_serial.set(getattr(self.config, 'cert_serial', ""))
            self.var_revoked_cert.set(self.config.revoked_cert)
            self.var_unknown_ca_cert.set(self.config.unknown_ca_cert)
            self.var_client_cert.set(self.config.client_cert)
            self.var_client_key.set(self.config.client_key)
            self.var_latency_samples.set(self.config.latency_samples)
            self.var_enable_load.set(self.config.enable_load_test)
            self.var_load_concurrency.set(self.config.load_concurrency)
            self.var_load_requests.set(self.config.load_requests)

            # Update monitoring variables
            self.var_crl_override_url.set(self.config.crl_override_url)
            self.var_check_validity.set(self.config.check_validity)
            self.var_follow_log.set(self.config.follow_log)
            self.var_show_info.set(self.config.show_info)
            self.var_show_warn.set(self.config.show_warn)
            self.var_show_debug.set(self.config.show_debug)
            self.var_show_cmd.set(self.config.show_cmd)
            self.var_show_stderr.set(self.config.show_stderr)
            self.var_show_status.set(self.config.show_status)

            # Update trust anchor variables
            self.var_trust_anchor.set(self.config.trust_anchor_path)
            self.var_trust_anchor_type.set(self.config.trust_anchor_type)
            self.var_require_explicit_policy.set(self.config.require_explicit_policy)
            self.var_inhibit_policy_mapping.set(self.config.inhibit_policy_mapping)

            # Update advanced testing variables
            self.var_test_cryptographic_preferences.set(self.config.test_cryptographic_preferences)
            self.var_test_non_issued_certificates.set(self.config.test_non_issued_certificates)

            # Update OCSP response validation variables
            self.var_max_age_hours.set(self.config.max_age_hours)

            messagebox.showinfo("Config", "Configuration loaded successfully!")
        except Exception as exc:
            messagebox.showerror("Config", f"Error loading configuration: {exc}")

    def _log_monitor(self, text: str) -> None:
        """Log callback for monitoring"""
        if ("[INFO]" in text and not self.var_show_info.get()) or \
           ("[WARN]" in text and not self.var_show_warn.get()) or \
           ("[DEBUG]" in text and not self.var_show_debug.get()) or \
           ("[CMD]" in text and not self.var_show_cmd.get()) or \
           ("[STDERR]" in text and not self.var_show_stderr.get()) or \
           ("[STATUS]" in text and not self.var_show_status.get()):
            return

        # Write to monitoring output
        self.monitor_output.insert(tk.END, text)
        if self.var_follow_log.get():
            self.monitor_output.see(tk.END)

        # Also print to stdout so it appears in console log
        print(text, end='')

    def _parse_serial_number(self, serial_str: str) -> str:
        """Parse serial number string and convert hex to decimal if needed"""
        if not serial_str or not serial_str.strip():
            return ""

        serial_str = serial_str.strip()

        # Handle hex format (0x prefix)
        if serial_str.startswith('0x') or serial_str.startswith('0X'):
            try:
                # Convert hex to decimal
                decimal_value = int(serial_str, 16)
                return str(decimal_value)
            except ValueError:
                self._log_monitor(f"[WARN] Invalid hex serial number: {serial_str}\n")
                return serial_str

        # Handle negative decimal
        if serial_str.startswith('-'):
            try:
                int(serial_str)  # Validate it's a valid integer
                return serial_str
            except ValueError:
                self._log_monitor(f"[WARN] Invalid negative serial number: {serial_str}\n")
                return serial_str

        # Handle positive decimal
        try:
            int(serial_str)  # Validate it's a valid integer
            return serial_str
        except ValueError:
            self._log_monitor(f"[WARN] Invalid serial number format: {serial_str}\n")
            return serial_str

    def _clear_monitor_log(self) -> None:
        """Clear monitoring log"""
        self.monitor_output.delete(1.0, tk.END)
        self.console_log_output.delete(1.0, tk.END)

    def _clear_response(self) -> None:
        """Clear OCSP/CRL response summaries"""
        self.ocsp_summary.set("")
        self.crl_summary.set("")
        self._log_monitor("[INFO] Response summaries cleared\n")

    def _enable_all_debug(self) -> None:
        """Enable all debug logging options"""
        self.var_show_debug.set(True)
        self.var_show_info.set(True)
        self.var_show_warn.set(True)
        self.var_show_cmd.set(True)
        self.var_show_stderr.set(True)
        self.var_show_status.set(True)
        self._log_monitor("[DEBUG] All debug logging options enabled\n")

    def _select_all_test_categories(self) -> None:
        """Select all test categories"""
        self.var_enable_ocsp_tests.set(True)
        self.var_enable_crl_tests.set(True)
        self.var_enable_path_validation_tests.set(True)
        self.var_enable_ikev2_tests.set(True)
        self.var_enable_federal_bridge_tests.set(True)
        self.var_enable_performance_tests.set(True)

    def _select_none_test_categories(self) -> None:
        """Select no test categories"""
        self.var_enable_ocsp_tests.set(False)
        self.var_enable_crl_tests.set(False)
        self.var_enable_path_validation_tests.set(False)
        self.var_enable_ikev2_tests.set(False)
        self.var_enable_federal_bridge_tests.set(False)
        self.var_enable_performance_tests.set(False)

    def _select_default_test_categories(self) -> None:
        """Select default test categories"""
        self.var_enable_ocsp_tests.set(True)
        self.var_enable_crl_tests.set(True)
        self.var_enable_path_validation_tests.set(True)
        self.var_enable_ikev2_tests.set(False)
        self.var_enable_federal_bridge_tests.set(False)
        self.var_enable_performance_tests.set(False)

    def _show_test_results_in_monitor(self) -> None:
        """Display latest test results in monitoring window"""
        if not hasattr(self, 'results') or not self.results:
            self._log_monitor("[INFO] No test results available. Run tests first.\n")
            return

        self._log_monitor("\n" + "="*80 + "\n")
        self._log_monitor("LATEST TEST RESULTS\n")
        self._log_monitor("="*80 + "\n\n")

        # Group results by category
        categories = {}
        for result in self.results:
            if result.category not in categories:
                categories[result.category] = []
            categories[result.category].append(result)

        # Display results by category
        for category, results in categories.items():
            self._log_monitor(f"[{category.upper()} TESTS]\n")
            self._log_monitor("-" * 40 + "\n")

            for result in results:
                status_icon = "✅" if result.status.value == "PASS" else "❌" if result.status.value == "FAIL" else "⚠️" if result.status.value == "WARN" else "⏭️" if result.status.value == "SKIP" else "🔍" if result.status.value == "INFO" else "❌"
                self._log_monitor(f"{status_icon} {result.name}\n")
                self._log_monitor(f"   Status: {result.status.value}\n")
                self._log_monitor(f"   Message: {result.message}\n")

                if result.details:
                    self._log_monitor("   Details:\n")
                    for key, value in result.details.items():
                        if isinstance(value, dict):
                            self._log_monitor(f"     {key}:\n")
                            for sub_key, sub_value in value.items():
                                if isinstance(sub_value, (list, dict)):
                                    self._log_monitor(f"       {sub_key}: {sub_value}\n")
                                else:
                                    self._log_monitor(f"       {sub_key}: {sub_value}\n")
                        elif isinstance(value, list):
                            self._log_monitor(f"     {key}:\n")
                            for item in value:
                                self._log_monitor(f"       - {item}\n")
                        else:
                            self._log_monitor(f"     {key}: {value}\n")

                self._log_monitor(f"   Duration: {result.duration_ms}ms\n")
                self._log_monitor("\n")

            self._log_monitor("\n")

        self._log_monitor("="*80 + "\n")
        self._log_monitor(f"Total Tests: {len(self.results)}\n")

        # Count by status
        status_counts = {}
        for result in self.results:
            status = result.status.value
            status_counts[status] = status_counts.get(status, 0) + 1

        self._log_monitor("Status Summary:\n")
        for status, count in status_counts.items():
            self._log_monitor(f"  {status}: {count}\n")

        self._log_monitor("="*80 + "\n\n")

    def _run_ocsp_monitor(self) -> None:
        """Run OCSP monitoring check"""
        cert = self.var_good_cert.get()
        cert_serial = self.var_cert_serial.get()
        issuer = self.var_issuer_path.get()
        url = self.var_ocsp_url.get()

        # Check if either certificate file or serial number is provided
        if not cert and not cert_serial:
            messagebox.showerror("Input Error", "Please provide either a certificate file or serial number.")
            return

        if not issuer:
            messagebox.showerror("Input Error", "Please select an issuer certificate file.")
            return

        # Parse serial number if provided
        if cert_serial:
            cert_serial = self._parse_serial_number(cert_serial)
            if not cert_serial:
                messagebox.showerror("Input Error", "Invalid serial number format.")
                return

        # Update monitor settings
        self.monitor.check_validity = self.var_check_validity.get()

        # If no OCSP URL provided, it will be extracted from the certificate's AIA extension
        threading.Thread(target=self._ocsp_monitor_thread, args=(cert, cert_serial, issuer, url), daemon=True).start()

    def _run_crl_monitor(self) -> None:
        """Run CRL monitoring check"""
        cert = self.var_good_cert.get()
        issuer = self.var_issuer_path.get()
        crl_url = self.var_crl_override_url.get()

        if not cert or not issuer:
            messagebox.showerror("Input Error", "Please select both a certificate and issuer file.")
            return

        # Update monitor settings
        self.monitor.check_validity = self.var_check_validity.get()

        threading.Thread(target=self._crl_monitor_thread, args=(cert, issuer, crl_url), daemon=True).start()

    def _ocsp_monitor_thread(self, cert: str, cert_serial: str, issuer: str, url: str) -> None:
        """OCSP monitoring thread"""
        try:
            results = self.monitor.run_ocsp_check(cert, issuer, url, cert_serial)
            if "summary" in results:
                self.ocsp_summary.set(results["summary"])
        except Exception as exc:
            self._log_monitor(f"[ERROR] OCSP Monitor Exception: {exc}\n")

    def _crl_monitor_thread(self, cert: str, issuer: str, crl_url: str) -> None:
        """CRL monitoring thread"""
        try:
            results = self.monitor.run_crl_check(cert, issuer, crl_url)
            if "summary" in results:
                self.crl_summary.set(results["summary"])
        except Exception as exc:
            self._log_monitor(f"[ERROR] CRL Monitor Exception: {exc}\n")


if __name__ == "__main__":
    os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")
    app = OCSPTesterGUI()
    app.mainloop()