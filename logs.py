# !/usr/bin/env python
# -*- coding: utf-8 -*-
"""
تم تحسين هذه الأداة لتقليل وقت بدء التشغيل بعد تحويلها إلى exe.
ننصح باستخدام PyInstaller مع خيارات:
    --onedir
    --runtime-tmpdir "C:\Temp"   (أو مسار مناسب على نظامك)
كما قمنا بتأجيل تحميل بعض المكتبات الثقيلة (lazy-loading) لتأخير تحميلها حتى الحاجة.
"""

import sys, os, sqlite3, threading, queue, getpass, re, json, csv, locale, platform, time, math, subprocess, \
    tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox, simpledialog, filedialog
from datetime import datetime, timedelta
import logging

# --- Core Dependencies ---
import psutil
import pandas as pd
import numpy as np
from PIL import Image, ImageTk

# تأجيل تحميل مكتبات رسم المخططات المكتبية (lazy-loading)
# سيتم تحميل matplotlib عند الحاجة في دالة lazy_imports()

# --- Machine Learning ---
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler  # Added for data scaling

# --- محاولة تأجيل تحميل مكتبة ReportLab---
# سيتم التأكد من توفرها عند الحاجة في دالة _export_to_pdf
REPORTLAB_AVAILABLE = False
try:
    import reportlab

    REPORTLAB_AVAILABLE = True
except ImportError:
    print("Warning: reportlab not found. PDF export will be disabled. Install with: pip install reportlab")

# --- Windows Specific ---
IS_WINDOWS = (platform.system() == "Windows")
if IS_WINDOWS:
    try:
        import win32evtlog, pywintypes

        WINDOWS_EVENT_TYPES = {
            win32evtlog.EVENTLOG_ERROR_TYPE: "High",
            win32evtlog.EVENTLOG_WARNING_TYPE: "Medium",
            win32evtlog.EVENTLOG_INFORMATION_TYPE: "Normal",
            win32evtlog.EVENTLOG_AUDIT_SUCCESS: "Normal",
            win32evtlog.EVENTLOG_AUDIT_FAILURE: "High",
        }

    except ImportError:
        messagebox.showerror("Error",
                             "Module 'pywin32' not found. Please install it (`pip install pywin32`) for Windows event log functionality.")
        sys.exit(1)

# --- Logging Configuration ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] (%(threadName)s) %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')

# --- Locale Setting ---
try:
    locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, 'en_US')
    except locale.Error:
        logging.warning("Could not set locale to en_US.UTF-8 or en_US. Using default locale.")


# --- تحديد مسار قاعدة البيانات ليكون في موقع قابل للكتابة ---
def get_database_path():
    if IS_WINDOWS:
        base_dir = os.path.join(os.getenv('APPDATA'), 'LogAnalyzer')
    else:
        base_dir = os.path.join(os.path.expanduser('~'), '.loganalyzer')
    if not os.path.exists(base_dir):
        os.makedirs(base_dir, exist_ok=True)
    return os.path.join(base_dir, 'logs_v2.db')


DATABASE_FILE = get_database_path()

# --- Constants ---
MAX_LOG_EVENTS_PER_TYPE = 500  # لكل نوع سجل، سيتم تصفية الأحداث غير الهامة
REALTIME_SCAN_INTERVAL_SECONDS = 2.5
ANOMALY_CONTAMINATION = 0.05
DEFAULT_KEYWORDS = ["error", "fail", "warning", "critical", "exception", "denied", "attack", "malware"]
KEYWORDS_FILE = "keywords.json"
EXCEPTIONS_FILE = "exceptions.json"  # ملف تخزين الاستثناءات بتنسيق JSON


# ==============================================================================
# Log Analyzer Class
# ==============================================================================

class LogAnalyzer:
    """
    أداة تحليل سجلات متقدمة بعدة أوضاع فحص، مراقبة عمليات النظام وقتياً،
    واكتشاف الشذوذ مع إمكانية تصدير البيانات.
    بالإضافة إلى إدارة الاستثناءات عبر تبويب خاص.
    """

    def __init__(self):
        # تأجيل التحميل لبعض المكتبات الثقيلة لتسريع بدء التشغيل

        self.lazy_imports()

        self.root = tk.Tk()
        self.root.title("Log Analyzer Pro - التحليل الاحترافي للسجلات")
        self.root.geometry("1440x900")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # --- Fonts (أحجام أصغر لتحسين العرض) ---
        available_fonts = tkfont.families()
        if "Open Sans" in available_fonts:
            self.body_font = ("Open Sans", 10)
        else:
            self.body_font = ("Arial", 10)
        if "Inter" in available_fonts:
            self.header_font = ("Inter", 12, "bold")
        else:
            self.header_font = ("Arial", 12, "bold")
        self.base_font = self.body_font

        # --- State Variables ---
        self.dark_mode = False
        self.scan_active = threading.Event()
        self.realtime_scan_active = threading.Event()
        self.scan_thread = None
        self.realtime_thread = None
        self.realtime_pid_map = {}
        self.frequency_counter = {}
        self.anomaly_detector = None
        self.unique_records = {}
        # تحميل قائمة الاستثناءات من ملف JSON إذا وُجد، وإلا تبدأ كقائمة فارغة
        self.exceptions = self._load_exceptions()

        # --- Configuration ---
        self.log_types = self._get_available_log_types()
        self.keywords = self._load_keywords()
        self.realtime_interval = REALTIME_SCAN_INTERVAL_SECONDS

        # --- Threading & Queue ---
        self.queue = queue.Queue()
        self.db_lock = threading.Lock()

        # --- UI Setup ---
        self.style = ttk.Style()
        self._setup_styles()

        # --- Database ---
        self.db_conn = self._init_database()
        if not self.db_conn:
            messagebox.showerror("Database Error", f"Failed to initialize database '{DATABASE_FILE}'. Exiting.")
            sys.exit(1)

        # بدء تدريب نموذج الشذوذ في خيط منفصل لتسريع بدء التشغيل وعدم تعليق واجهة المستخدم
        threading.Thread(target=self._init_anomaly_detector, daemon=True).start()

        # --- Build UI ---
        self.notebook = ttk.Notebook(self.root, style="TNotebook")
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.tab_welcome = ttk.Frame(self.notebook)
        self.tab_general = ttk.Frame(self.notebook)
        self.tab_keyword = ttk.Frame(self.notebook)
        self.tab_event = ttk.Frame(self.notebook)
        self.tab_realtime = ttk.Frame(self.notebook)
        self.tab_exceptions = ttk.Frame(self.notebook)  # تبويب إدارة الاستثناءات الجديد
        self.notebook.add(self.tab_welcome, text=" ✨ الشاشة الترحيبية ")
        self.notebook.add(self.tab_general, text=" 🛡️ الفحص العام ")
        self.notebook.add(self.tab_keyword, text=" 🔑 الفحص بالكلمات ")
        self.notebook.add(self.tab_event, text=" 🗓️ فحص الأحداث ")
        self.notebook.add(self.tab_realtime, text=" ⏱️ الفحص في الوقت الحقيقي ")
        self.notebook.add(self.tab_exceptions, text="   إدارة الاستثناءات   ")
        self._init_welcome_ui()
        self._init_general_ui()
        self._init_keyword_ui()
        self._init_event_ui()
        self._init_realtime_ui()
        self._init_exceptions_ui()  # تهيئة تبويب إدارة الاستثناءات

        self._init_event_log_ui()
        self.root.after(100, self._process_queue)
        self.log_event_entry("INFO", "Log Analyzer Pro initialized successfully.")

    def lazy_imports(self):
        """
        تأجيل تحميل المكتبات الثقيلة مثل matplotlib عند بدء التشغيل لتسريع الإقلاع.
        يمكن استدعاء هذه الدالة قبل إنشاء نافذة الواجهة.
        """
        try:
            import matplotlib
            matplotlib.use("TkAgg")
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
            # تخزين المراجع في attributes للكائن إذا دعت الحاجة لاحقاً
            self.Figure = Figure
            self.FigureCanvasTkAgg = FigureCanvasTkAgg
            self.NavigationToolbar2Tk = NavigationToolbar2Tk
            logging.info("Matplotlib loaded lazily.")
        except Exception as e:
            logging.warning(f"Lazy load of matplotlib failed: {e}")

    def _get_available_log_types(self):
        if IS_WINDOWS:
            return ['Application', 'System', 'Security']

        else:
            return {
                "System": "/var/log/syslog",
                "Auth": "/var/log/auth.log",
                "Kern": "/var/log/kern.log",
            }

    def _init_database(self):
        try:
            conn = sqlite3.connect(DATABASE_FILE, check_same_thread=False, timeout=10)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS log_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_type TEXT NOT NULL,
                    pid INTEGER,
                    source TEXT,
                    suspicious TEXT,
                    username TEXT,
                    creation_date TEXT,
                    frequency INTEGER,
                    cpu_percent REAL,
                    memory_percent REAL,
                    event_details TEXT,
                    path TEXT,
                    log_name TEXT,
                    severity TEXT,
                    trigger TEXT,
                    detection_date TEXT,
                    age TEXT
                )
            ''')
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_scan_type ON log_entries (scan_type);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_creation_date ON log_entries (creation_date);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_source ON log_entries (source);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_severity ON log_entries (severity);")
            # إنشاء جدول جديد لاستيراد قواعد SIGMA (YAML)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sigma_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rule_name TEXT NOT NULL,
                    rule_data TEXT NOT NULL
                )
            ''')
            conn.commit()
            logging.info(f"Database '{DATABASE_FILE}' initialized successfully.")
            return conn
        except sqlite3.Error as e:
            logging.error(f"Database initialization failed: {e}")
            messagebox.showerror("Database Error", f"Failed to initialize database: {e}")
            return None

    def _load_keywords(self):
        if os.path.exists(KEYWORDS_FILE):
            try:
                with open(KEYWORDS_FILE, 'r', encoding='utf-8') as f:
                    loaded_keywords = json.load(f)
                    if isinstance(loaded_keywords, list) and all(isinstance(k, str) for k in loaded_keywords):
                        logging.info(f"Loaded {len(loaded_keywords)} keywords from {KEYWORDS_FILE}.")
                        return loaded_keywords
                    else:
                        logging.warning(f"Invalid format in {KEYWORDS_FILE}. Using default keywords.")
            except (json.JSONDecodeError, IOError) as e:
                logging.error(f"Error loading keywords from {KEYWORDS_FILE}: {e}. Using default keywords.")
        else:
            logging.info(f"{KEYWORDS_FILE} not found. Using default keywords.")
        try:
            with open(KEYWORDS_FILE, 'w', encoding='utf-8') as f:
                json.dump(DEFAULT_KEYWORDS, f, ensure_ascii=False, indent=2)
            logging.info(f"Saved default keywords to {KEYWORDS_FILE}.")
        except IOError as e:
            logging.error(f"Error saving default keywords to {KEYWORDS_FILE}: {e}")
        return DEFAULT_KEYWORDS[:]

    def _save_keywords(self):
        try:
            with open(KEYWORDS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.keywords, f, ensure_ascii=False, indent=2)
            logging.info(f"Keywords saved to {KEYWORDS_FILE}.")
        except IOError as e:
            logging.error(f"Error saving keywords to {KEYWORDS_FILE}: {e}")
            self.queue.put(('error', f"Failed to save keywords: {e}"))

    def _load_exceptions(self):
        if os.path.exists(EXCEPTIONS_FILE):
            try:
                with open(EXCEPTIONS_FILE, 'r', encoding='utf-8') as f:
                    loaded_exceptions = json.load(f)
                    if isinstance(loaded_exceptions, list) and all(isinstance(ex, str) for ex in loaded_exceptions):
                        logging.info(f"Loaded {len(loaded_exceptions)} exceptions from {EXCEPTIONS_FILE}.")
                        return loaded_exceptions
                    else:
                        logging.warning(f"Invalid format in {EXCEPTIONS_FILE}. Starting with an empty list.")
            except (json.JSONDecodeError, IOError) as e:
                logging.error(f"Error loading exceptions from {EXCEPTIONS_FILE}: {e}. Starting with an empty list.")
        else:
            logging.info(f"{EXCEPTIONS_FILE} not found. Starting with an empty exceptions list.")
        return []

    def _save_exceptions(self):
        try:

            with open(EXCEPTIONS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.exceptions, f, ensure_ascii=False, indent=2)
            logging.info(f"Exceptions saved to {EXCEPTIONS_FILE}.")
        except IOError as e:
            logging.error(f"Error saving exceptions to {EXCEPTIONS_FILE}: {e}")
            self.queue.put(('error', f"Failed to save exceptions: {e}"))

    def _init_anomaly_detector(self):
        logging.info("بدء تدريب نموذج كشف الشذوذ في الخلفية...")
        samples = []
        try:
            for proc in psutil.process_iter(attrs=['cpu_percent', 'memory_percent', 'create_time']):
                try:
                    proc.cpu_percent(interval=None)
                    time.sleep(0.005)
                    info = proc.info
                    cpu = proc.cpu_percent(interval=None)
                    mem = info.get('memory_percent', 0.0)
                    uptime = time.time() - info.get('create_time', time.time()) if info.get('create_time') else 0
                    if cpu is not None and mem is not None:
                        samples.append([cpu, mem, max(0, uptime)])
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
                except Exception as proc_e:
                    logging.warning(f"لم أستطع الحصول على الإحصائيات للعملية {info.get('pid', 'N/A')}: {proc_e}")
            if len(samples) > 10:
                X = np.array(samples)
                scaler = StandardScaler()
                X_scaled = scaler.fit_transform(X)
                self.anomaly_detector = IsolationForest(contamination=ANOMALY_CONTAMINATION, random_state=42)
                self.anomaly_detector.fit(X_scaled)
                logging.info(f"تم تدريب نموذج الشذوذ باستخدام {len(samples)} عينة من العمليات.")
            else:
                logging.warning("عدد العينات غير كافٍ لتدريب نموذج الشذوذ بشكل فعال. استخدام إعدادات افتراضية.")
                self.anomaly_detector = IsolationForest(contamination=ANOMALY_CONTAMINATION, random_state=42)
                self.anomaly_detector.fit(np.array([[0, 0, 0]]))
        except Exception as e:
            logging.error(f"فشل تدريب نموذج كشف الشذوذ: {e}")
            self.queue.put(('error', f"فشل تدريب نموذج كشف الشذوذ: {e}"))
            self.anomaly_detector = IsolationForest(contamination=ANOMALY_CONTAMINATION, random_state=42)
            self.anomaly_detector.fit(np.array([[0, 0, 0]]))

    def _setup_styles(self):
        self.colors = {
            'light': {
                'bg': "#F5F5F5",
                'fg': "#424242",
                'accent': "#1E88E5",

                'secondary': "#90CAF9",
                'progress_trough': "#E0E0E0",
                'progress_bar': "#1E88E5",
                'notebook_bg': "#E3F2FD",
                'tree_even': '#FFFFFF',
                'tree_odd': '#F5F5F5',
                'btn_text': 'white',
                'header_bg': "#1E88E5",
                'header_fg': "white",
                'status_fg': "#424242",
                'critical': "#E53935",
                'warning': "#FFB300",
                'normal': "#43A047",
                'anomaly': '#9C27B0'
            },
            'dark': {
                'bg': "#424242",
                'fg': "#F5F5F5",
                'accent': "#1E88E5",
                'secondary': "#1565C0",
                'progress_trough': "#616161",
                'progress_bar': "#1E88E5",
                'notebook_bg': "#37474F",
                'tree_even': '#455A64',
                'tree_odd': '#37474F',
                'btn_text': 'white',
                'header_bg': "#1E88E5",
                'header_fg': "white",
                'status_fg': "#F5F5F5",
                'critical': "#E53935",
                'warning': "#FFB300",
                'normal': "#43A047",
                'anomaly': '#9C27B0'
            }
        }
        self.current_colors = self.colors['light'] if not self.dark_mode else self.colors['dark']
        self.root.configure(bg=self.current_colors['bg'])
        self.style.theme_use('clam')
        self.style.configure('.',
                             background=self.current_colors['bg'],
                             foreground=self.current_colors['fg'],
                             font=self.body_font)
        self.style.configure("TNotebook", background=self.current_colors['bg'], borderwidth=0)
        self.style.configure("TNotebook.Tab", padding=[10, 6], font=(self.body_font[0], 10, "bold"),
                             foreground=self.current_colors['fg'])
        self.style.map("TNotebook.Tab",
                       background=[("selected", self.current_colors['accent']),
                                   ("!selected", self.current_colors['notebook_bg'])],
                       foreground=[("selected", self.current_colors['btn_text']),
                                   ("!selected", self.current_colors['fg'])])
        self.style.configure('Start.TButton', background="#4CAF50", foreground="white", padding=[8, 4],

                             font=(self.body_font[0], 10, 'bold'))
        self.style.map('Start.TButton', background=[('active', "#45a049")])
        self.style.configure('Stop.TButton', background="#F44336", foreground="white", padding=[8, 4],
                             font=(self.body_font[0], 10, 'bold'))
        self.style.map('Stop.TButton', background=[('active', "#E53935")])
        self.style.configure('Refresh.TButton', background="#1E88E5", foreground="white", padding=[8, 4],
                             font=(self.body_font[0], 10, 'bold'))
        self.style.map('Refresh.TButton', background=[('active', "#1565C0")])
        self.style.configure('Export.TButton', background="#FF9800", foreground="white", padding=[8, 4],
                             font=(self.body_font[0], 10, 'bold'))
        self.style.map('Export.TButton', background=[('active', "#FB8C00")])
        self.style.configure('Delete.TButton', background="#9C27B0", foreground="white", padding=[8, 4],
                             font=(self.body_font[0], 10, 'bold'))
        self.style.map('Delete.TButton', background=[('active', "#8E24AA")])
        self.style.configure('TButton', padding=[8, 4], relief='flat', font=(self.body_font[0], 10, 'bold'),
                             foreground=self.current_colors['btn_text'], background=self.current_colors['accent'],
                             borderwidth=0)
        self.style.map('TButton', background=[('active', self.current_colors['secondary']),
                                              ('hover', self.current_colors['secondary'])],
                       foreground=[('active', self.current_colors['btn_text']),
                                   ('hover', self.current_colors['btn_text'])])
        self.style.configure('Header.TLabel', font=self.header_font,
                             background=self.current_colors['header_bg'], foreground=self.current_colors['header_fg'],
                             padding=6, anchor=tk.CENTER)
        self.style.configure('Status.TLabel', font=(self.body_font[0], 8),
                             background=self.current_colors['bg'], foreground=self.current_colors['status_fg'],
                             padding=4)
        self.style.configure('Progress.TLabel', font=(self.body_font[0], 8, 'bold'),
                             background=self.current_colors['bg'], foreground=self.current_colors['fg'])
        self.style.configure('Treeview', rowheight=25,
                             background=self.current_colors['bg'],
                             fieldbackground=self.current_colors['bg'],
                             foreground=self.current_colors['fg'],
                             font=(self.body_font[0], 9))
        self.style.configure('Treeview.Heading', font=(self.body_font[0], 9, 'bold'), padding=4)
        self.style.map('Treeview',
                       background=[('selected', self.current_colors['accent'])],
                       foreground=[('selected', self.current_colors['btn_text'])])
        self.style.configure('evenrow.Treeview', background=self.current_colors['tree_even'])
        self.style.configure('oddrow.Treeview', background=self.current_colors['tree_odd'])
        self.style.map('evenrow.Treeview', foreground=[('!selected', self.current_colors['fg'])])
        self.style.map('oddrow.Treeview', foreground=[('!selected', self.current_colors['fg'])])
        self.style.configure('severity_High.Treeview', foreground=self.current_colors['critical'])
        self.style.configure('severity_Medium.Treeview', foreground=self.current_colors['warning'])
        self.style.configure('severity_Normal.Treeview', foreground=self.current_colors['normal'])
        self.style.configure('suspicious_True.Treeview', foreground=self.current_colors['critical'])
        self.style.configure('suspicious_False.Treeview', foreground=self.current_colors['normal'])
        self.style.configure('anomaly_Yes.Treeview', foreground=self.current_colors['anomaly'],
                             font=(self.body_font[0], 9, 'bold'))
        self.style.configure('Custom.Horizontal.TProgressbar',
                             troughcolor=self.current_colors['progress_trough'],

                             background=self.current_colors['progress_bar'],
                             thickness=15)
        self.style.configure('TCheckbutton', font=(self.body_font[0], 9),
                             background=self.current_colors['bg'], foreground=self.current_colors['fg'])
        self.style.map('TCheckbutton',
                       indicatorbackground=[('selected', self.current_colors['accent']),
                                            ('!selected', self.current_colors['bg'])],
                       indicatorforeground=[('selected', self.current_colors['btn_text']),
                                            ('!selected', self.current_colors['fg'])])
        if hasattr(self, 'keywords_listbox'):
            self.keywords_listbox.configure(bg=self.current_colors['tree_odd'], fg=self.current_colors['fg'],
                                            selectbackground=self.current_colors['accent'],
                                            selectforeground=self.current_colors['btn_text'])
        if hasattr(self, 'event_log'):
            self.event_log.configure(bg=self.current_colors['tree_odd'], fg=self.current_colors['fg'])

    def _create_gradient_image(self, width, height, color1, color2):
        def hex_to_rgb(hex_color):
            hex_color = hex_color.lstrip('#')
            return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))

        rgb1 = hex_to_rgb(color1)
        rgb2 = hex_to_rgb(color2)
        image = Image.new("RGB", (width, height), color1)
        for x in range(width):
            factor = x / max(1, width - 1)
            r = int(rgb1[0] + (rgb2[0] - rgb1[0]) * factor)
            g = int(rgb1[1] + (rgb2[1] - rgb1[1]) * factor)
            b = int(rgb1[2] + (rgb2[2] - rgb1[2]) * factor)
            for y in range(height):
                image.putpixel((x, y), (r, g, b))
        return ImageTk.PhotoImage(image)

    def _init_shared_toolbar(self, parent_frame, scan_type):
        toolbar_frame = ttk.Frame(parent_frame)
        toolbar_frame.pack(fill=tk.X, pady=(10, 5), padx=10)
        btn_padx = 4
        btn_pady = 2
        if scan_type == 'exceptions':
            theme_btn = ttk.Button(toolbar_frame, text="☀️/🌙 تغيير الواجهة", command=self.toggle_theme, width=18)
            theme_btn.pack(side=tk.RIGHT, padx=btn_padx, pady=btn_pady)
            return
        start_cmd = None
        start_text = "🔍 ابدأ الفحص"
        if scan_type == 'general':
            start_cmd = self.start_general_scan
        elif scan_type == 'keyword':
            start_cmd = self.start_keyword_scan
        elif scan_type == 'event':
            start_cmd = self.start_event_scan
        elif scan_type == 'realtime':

            start_text = "▶ بدء الفحص الحقيقي"
            start_cmd = self.start_realtime_scan
        if start_cmd:
            start_btn = ttk.Button(toolbar_frame, text=start_text, command=start_cmd, style="Start.TButton", width=15)
            start_btn.pack(side=tk.LEFT, padx=btn_padx, pady=btn_pady)
        stop_cmd = self.stop_scan if scan_type != 'realtime' else self.stop_realtime_scan
        stop_text = "⏹️ إيقاف الفحص" if scan_type != 'realtime' else "⏹️ إيقاف الفحص الحقيقي"
        stop_btn = ttk.Button(toolbar_frame, text=stop_text, command=stop_cmd, style="Stop.TButton", width=15)
        stop_btn.pack(side=tk.LEFT, padx=btn_padx, pady=btn_pady)
        if scan_type != 'realtime':
            refresh_btn = ttk.Button(toolbar_frame, text="🔄 تحديث البيانات",
                                     command=lambda: self.refresh_data(scan_type), style="Refresh.TButton", width=15)
            refresh_btn.pack(side=tk.LEFT, padx=btn_padx, pady=btn_pady)
        kill_cmd = self.kill_selected_process_or_event if scan_type != 'realtime' else self.kill_realtime_process
        kill_text = "⛔ إنهاء العملية/الحدث" if scan_type != 'realtime' else "⛔ إنهاء العملية المحددة"
        kill_btn = ttk.Button(toolbar_frame, text=kill_text, command=kill_cmd, style="Export.TButton", width=15)
        kill_btn.pack(side=tk.LEFT, padx=btn_padx, pady=btn_pady)
        export_cmd = lambda: self.export_results(scan_type)
        export_btn = ttk.Button(toolbar_frame, text="💾 تصدير النتائج", command=export_cmd, style="Export.TButton",
                                width=15)
        export_btn.pack(side=tk.LEFT, padx=btn_padx, pady=btn_pady)
        if scan_type == 'realtime':
            clear_btn = ttk.Button(toolbar_frame, text="🗑️ حذف جميع السجلات", command=self.delete_all_records,
                                   style="Delete.TButton", width=18)
            clear_btn.pack(side=tk.LEFT, padx=btn_padx, pady=btn_pady)
        elif scan_type not in ['realtime', 'exceptions']:
            delete_btn = ttk.Button(toolbar_frame, text="🗑️ حذف السجلات", command=self.delete_all_records,
                                    style="Delete.TButton", width=15)
            delete_btn.pack(side=tk.LEFT, padx=btn_padx, pady=btn_pady)

    def _init_event_log_ui(self):
        self.event_log_frame = ttk.LabelFrame(self.root, text=" سجل أحداث البرنامج ", padding=5)
        self.event_log_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=10, pady=(0, 10))
        self.event_log = tk.Text(self.event_log_frame, height=7, state='disabled', wrap='word',
                                 font=(self.body_font[0], 8), borderwidth=1, relief=tk.SUNKEN,
                                 bg=self.current_colors['tree_odd'], fg=self.current_colors['fg'])
        self.event_log.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        scrollbar = ttk.Scrollbar(self.event_log_frame, orient=tk.VERTICAL, command=self.event_log.yview)
        self.event_log.config(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _init_welcome_ui(self):
        self.welcome_frame = ttk.Frame(self.tab_welcome)
        self.welcome_frame.pack(fill=tk.BOTH, expand=True)
        center_frame = ttk.Frame(self.welcome_frame)
        center_frame.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        title = ttk.Label(center_frame, text="Log Analyzer Pro",
                          font=self.header_font, style='Header.TLabel')

        title.pack(pady=(0, 20))
        desc = ttk.Label(center_frame,
                         text="الأداة الاحترافية لتحليل السجلات، فحص الأحداث، ومراقبة النظام.",
                         font=self.body_font, wraplength=500, justify=tk.CENTER)
        desc.pack(pady=10)
        desc2 = ttk.Label(center_frame,
                          text="استخدم التبويبات أعلاه لبدء الفحص أو المراقبة.",
                          font=(self.body_font[0], 10), foreground=self.current_colors['secondary'])
        desc2.pack(pady=10)
        info_label = ttk.Label(self.welcome_frame,
                               text=f"Platform: {platform.system()} | Python: {platform.python_version()}",
                               style='Status.TLabel', relief=tk.SUNKEN, anchor=tk.W)
        info_label.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=5)

    def _init_general_ui(self):
        main_frame = self.tab_general
        self._init_shared_toolbar(main_frame, 'general')
        progress_frame = ttk.Frame(main_frame)
        progress_frame.pack(fill=tk.X, padx=10, pady=(0, 5))
        self.general_progress_var = tk.DoubleVar(value=0.0)
        self.general_progress = ttk.Progressbar(progress_frame, variable=self.general_progress_var,
                                                style='Custom.Horizontal.TProgressbar', maximum=100)
        self.general_progress.pack(fill=tk.X, side=tk.LEFT, expand=True, padx=(0, 10))
        self.general_progress_label = ttk.Label(progress_frame, text="0%", style='Progress.TLabel')
        self.general_progress_label.pack(side=tk.LEFT)
        self._init_treeview(main_frame, 'general')

    def _init_keyword_ui(self):
        main_frame = self.tab_keyword
        self._init_shared_toolbar(main_frame, 'keyword')
        progress_frame = ttk.Frame(main_frame)
        progress_frame.pack(fill=tk.X, padx=10, pady=(0, 5))
        self.keyword_progress_var = tk.DoubleVar(value=0.0)
        self.keyword_progress = ttk.Progressbar(progress_frame, variable=self.keyword_progress_var,
                                                style='Custom.Horizontal.TProgressbar', maximum=100)
        self.keyword_progress.pack(fill=tk.X, side=tk.LEFT, expand=True, padx=(0, 10))
        self.keyword_progress_label = ttk.Label(progress_frame, text="0%", style='Progress.TLabel')
        self.keyword_progress_label.pack(side=tk.LEFT)
        options_frame = ttk.LabelFrame(main_frame, text=" إدارة الكلمات المفتاحية المشبوهة ", padding=10)
        options_frame.pack(fill=tk.X, pady=5, padx=10)
        self.keywords_listbox = tk.Listbox(options_frame, height=6, font=self.body_font, width=40,
                                           exportselection=False, borderwidth=1, relief=tk.SUNKEN)
        self.keywords_listbox.pack(side=tk.LEFT, padx=(0, 10), fill=tk.BOTH, expand=True)
        self._refresh_keyword_listbox()
        kw_manage_frame = ttk.Frame(options_frame)
        kw_manage_frame.pack(side=tk.LEFT, padx=5, fill=tk.Y, anchor=tk.N)
        btn_config = [
            ("إضافة", self.add_keyword, "#43A047", "#388E3C"),
            ("تعديل", self.edit_keyword, "#1E88E5", "#1565C0"),
            ("حذف", self.remove_keyword, "#E53935", "#C62828")
        ]

        for text, cmd, _, _ in btn_config:
            btn = ttk.Button(kw_manage_frame, text=text, command=cmd, width=10)
            btn.pack(pady=4, fill=tk.X)
        # زر استيراد قواعد SIGMA من ملفات YAML
        btn_import_sigma = ttk.Button(kw_manage_frame, text="استيراد من ملف", command=self.import_sigma_rules, width=15)
        btn_import_sigma.pack(pady=4, fill=tk.X)
        self._init_treeview(main_frame, 'keyword')

    def _init_event_ui(self):
        main_frame = self.tab_event
        self._init_shared_toolbar(main_frame, 'event')
        progress_frame = ttk.Frame(main_frame)
        progress_frame.pack(fill=tk.X, padx=10, pady=(0, 5))
        self.event_progress_var = tk.DoubleVar(value=0.0)
        self.event_progress = ttk.Progressbar(progress_frame, variable=self.event_progress_var,
                                              style='Custom.Horizontal.TProgressbar', maximum=100)
        self.event_progress.pack(fill=tk.X, side=tk.LEFT, expand=True, padx=(0, 10))
        self.event_progress_label = ttk.Label(progress_frame, text="0%", style='Progress.TLabel')
        self.event_progress_label.pack(side=tk.LEFT)
        options_frame = ttk.LabelFrame(main_frame, text=" اختر أنواع سجلات الأحداث للفحص ", padding=10)
        options_frame.pack(fill=tk.X, pady=5, padx=10)
        self.event_type_vars = {}
        checkbox_frame = ttk.Frame(options_frame)
        checkbox_frame.pack()
        available_types = self.log_types if IS_WINDOWS else list(self.log_types.keys())
        cols = 4
        for i, log_type in enumerate(available_types):
            var = tk.BooleanVar(value=True)
            cb = ttk.Checkbutton(checkbox_frame, text=log_type, variable=var)
            cb.grid(row=i // cols, column=i % cols, padx=10, pady=2, sticky='w')
            self.event_type_vars[log_type] = var
        self._init_treeview(main_frame, 'event')

    def _init_realtime_ui(self):
        main_frame = self.tab_realtime
        self._init_shared_toolbar(main_frame, 'realtime')
        self._init_treeview(main_frame, 'realtime')

    def _init_exceptions_ui(self):
        main_frame = self.tab_exceptions
        self._init_shared_toolbar(main_frame, 'exceptions')
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, padx=10, pady=10)
        start_ex_btn = ttk.Button(control_frame, text="▶ تشغيل الإدارة", command=self.start_exception_management,
                                  width=25)
        start_ex_btn.pack(side=tk.LEFT, padx=5)
        stop_ex_btn = ttk.Button(control_frame, text="■ إيقاف الإدارة", command=self.stop_exception_management,
                                 width=25)
        stop_ex_btn.pack(side=tk.LEFT, padx=5)
        self.exception_status_label = ttk.Label(control_frame, text="متوقف", font=(self.body_font[0], 10, 'bold'))

        self.exception_status_label.pack(side=tk.LEFT, padx=20)
        options_frame = ttk.LabelFrame(main_frame, text=" إدارة الاستثناءات ", padding=10)
        options_frame.pack(fill=tk.X, pady=5, padx=10)
        self.exceptions_listbox = tk.Listbox(options_frame, height=6, font=self.body_font, width=40,
                                             exportselection=False, borderwidth=1, relief=tk.SUNKEN)
        self.exceptions_listbox.pack(side=tk.LEFT, padx=(0, 10), fill=tk.BOTH, expand=True)
        btns_frame = ttk.Frame(options_frame)
        btns_frame.pack(side=tk.LEFT, padx=(10, 0), fill=tk.Y, anchor=tk.N)
        add_ex_btn = ttk.Button(btns_frame, text="إضافة", command=self.add_exception, width=10)
        add_ex_btn.pack(pady=4, fill=tk.X)
        edit_ex_btn = ttk.Button(btns_frame, text="تعديل", command=self.edit_exception, width=10)
        edit_ex_btn.pack(pady=4, fill=tk.X)
        delete_ex_btn = ttk.Button(btns_frame, text="حذف", command=self.remove_exception, width=10)
        delete_ex_btn.pack(pady=4, fill=tk.X)
        self._refresh_exceptions_listbox()

    def _init_treeview(self, parent_frame, scan_type):
        tree_frame = ttk.Frame(parent_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        if scan_type == 'realtime':
            columns = (
            "id", "pid", "suspicious", "username", "trigger", "detection_date", "cpu_percent", "memory_percent",
            "event_details", "path", "severity", "anomaly", "log_name", "age")
        else:
            columns = ("id", "source", "suspicious", "username", "creation_date", "frequency",
                       "event_details", "path", "log_name", "severity", "trigger", "detection_date", "age")
        tree = ttk.Treeview(tree_frame, columns=columns, show='headings', selectmode='browse')
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        if scan_type == 'realtime':
            col_settings = {
                "id": ("ID", 60),
                "pid": ("PID", 70),
                "suspicious": ("مشبوه", 80),
                "username": ("اسم المستخدم", 100),
                "trigger": ("من يستخدم", 100),
                "detection_date": ("وقت الكشف", 150),
                "cpu_percent": ("CPU %", 70),
                "memory_percent": ("Mem %", 70),
                "event_details": ("تفاصيل العملية", 200),
                "path": ("مسار التشغيل", 300),
                "severity": ("شدة", 90),
                "anomaly": ("شذوذ؟", 80),
                "log_name": ("النوع", 80),
                "age": ("مدة التشغيل", 120)
            }
        else:
            col_settings = {
                "id": ("ID", 40),
                "source": ("المصدر", 100),

                "suspicious": ("مشبوه", 70),
                "username": ("اسم المستخدم", 100),
                "creation_date": ("وقت الحدث", 130),
                "frequency": ("التكرار", 70),
                "event_details": ("التفاصيل", 250),
                "path": ("المسار", 200),
                "log_name": ("النوع", 80),
                "severity": ("الشدة", 70),
                "trigger": ("من يستخدم", 100),
                "detection_date": ("وقت الكشف", 130),
                "age": ("العمر", 100)
            }
        for col, (text, width) in col_settings.items():
            anchor = tk.W if col in ['event_details', 'path', 'source'] else tk.CENTER
            tree.heading(col, text=text, anchor=anchor)
            tree.column(col, width=width, anchor=anchor, stretch=tk.NO if width < 100 else tk.YES)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        status_bar = ttk.Label(parent_frame, text="Records: 0 | Ready", style='Status.TLabel', relief=tk.SUNKEN,
                               anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(0, 5))
        setattr(self, f"{scan_type}_tree", tree)
        setattr(self, f"{scan_type}_status_bar", status_bar)

    def _scan_event_logs(self, scan_type, log_types_to_scan, keywords=None):
        logging.info(f"Starting '{scan_type}' scan for types: {log_types_to_scan}")
        total_processed = 0
        max_total_events = MAX_LOG_EVENTS_PER_TYPE * len(log_types_to_scan)
        progress_queue_msg = f'progress_{scan_type}'
        update_queue_msg = f'update_{scan_type}_table'
        self.frequency_counter.clear()
        self.unique_records.clear()
        try:
            for log_type in log_types_to_scan:
                if not self.scan_active.is_set():
                    logging.info(f"'{scan_type}' scan stopped by user.")
                    break
                events_in_type = 0
                logging.debug(f"Scanning log type: {log_type}")
                if IS_WINDOWS:
                    MAX_RETRIES = 2
                    retry_count = 0
                    handle = None
                    while retry_count <= MAX_RETRIES:
                        try:
                            if handle:
                                try:
                                    win32evtlog.CloseEventLog(handle)
                                except Exception:
                                    pass

                            handle = win32evtlog.OpenEventLog(None, log_type)
                            flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
                            logging.debug(f"Successfully opened handle for {log_type}")
                            while self.scan_active.is_set() and events_in_type < MAX_LOG_EVENTS_PER_TYPE:
                                try:
                                    if not handle:
                                        logging.warning(f"Handle for {log_type} became invalid. Breaking read loop.")
                                        break
                                    events_batch = win32evtlog.ReadEventLog(handle, flags, 0, 8192)
                                    if not events_batch:
                                        logging.debug(f"No more events found in {log_type}.")
                                        break
                                    for event in events_batch:
                                        if not self.scan_active.is_set():
                                            break
                                        if events_in_type >= MAX_LOG_EVENTS_PER_TYPE:
                                            break
                                        processed_data = self._process_windows_event(event, log_type)
                                        if not processed_data:
                                            continue
                                        if self.exceptions:
                                            if any(exc.lower() in processed_data.get('event_details', '').lower() or
                                                   exc.lower() in processed_data.get('source', '').lower() for exc in
                                                   self.exceptions):
                                                continue
                                        if scan_type == 'keyword':
                                            event_text = processed_data.get('event_details', "").lower()
                                            if not any(kw.lower() in event_text for kw in self.keywords):
                                                continue
                                        else:
                                            if log_type != "Security" and processed_data.get('severity') == "Normal":
                                                continue
                                        unique_key = (processed_data.get('source'), processed_data.get('creation_date'),
                                                      processed_data.get('event_details'))
                                        if unique_key in self.unique_records:
                                            continue
                                        self.unique_records[unique_key] = True
                                        self.queue.put((update_queue_msg, processed_data))
                                        events_in_type += 1
                                        total_processed += 1
                                        progress = min(100, (total_processed / max_total_events) * 100)
                                        self.queue.put((progress_queue_msg, progress))
                                        time.sleep(0.05)
                                        if events_in_type >= 500:
                                            break
                                    if not events_batch:
                                        break
                                except pywintypes.error as read_err:
                                    if read_err.winerror == 6:
                                        logging.warning(
                                            f"ReadEventLog failed for {log_type} with invalid handle (Error 6).Retry{retry_count + 1} / {MAX_RETRIES}.")
                                        break
                                    else:
                                        logging.error(
                                            f"Windows API Error during ReadEventLog for '{log_type}': {read_err}")
                                        self.queue.put(('error', f"Error reading '{log_type}': {read_err}"))
                                        events_in_type = MAX_LOG_EVENTS_PER_TYPE
                                        break
                                except Exception as read_loop_e:
                                    logging.exception(
                                        f"Unexpected error during event read loop for {log_type}: {read_loop_e}")
                                    events_in_type = MAX_LOG_EVENTS_PER_TYPE
                                    break
                            if retry_count <= MAX_RETRIES and 'read_err' in locals() and read_err.winerror == 6:
                                retry_count += 1
                                time.sleep(0.5)
                                continue
                            else:
                                break
                        except pywintypes.error as open_err:
                            if open_err.winerror == 5:
                                err_msg = f"Access Denied opening '{log_type}' log. Try running as Administrator."
                                logging.error(err_msg)
                                self.queue.put(('error', err_msg))
                            else:
                                err_msg = f"Windows API Error opening '{log_type}': {open_err}"
                                logging.error(err_msg)
                                self.queue.put(('error', err_msg))
                            break
                        except Exception as outer_e:
                            logging.exception(f"Unexpected error processing log type {log_type}: {outer_e}")
                            self.queue.put(('error', f"Critical error processing '{log_type}': {outer_e}"))
                            break
                        finally:
                            if handle:
                                try:
                                    win32evtlog.CloseEventLog(handle)
                                    logging.debug(f"Closed handle for {log_type}")
                                    handle = None
                                except Exception as close_e:
                                    logging.error(f"Error closing event log handle for {log_type}: {close_e}")
                                    handle = None
                else:
                    log_file_path = self.log_types.get(log_type)
                    if not log_file_path or not os.path.exists(log_file_path):
                        logging.warning(f"Log file for '{log_type}' not found or not configured: {log_file_path}")
                        continue
                    try:
                        cmd = ['tail', '-n', str(MAX_LOG_EVENTS_PER_TYPE), log_file_path]
                        result = subprocess.run(cmd, capture_output=True, text=True, check=False, errors='ignore')
                        if result.returncode != 0:
                            if "Permission denied" in result.stderr:

                                err_msg = f"Permission denied reading '{log_file_path}'. Check file permissions."
                                logging.error(err_msg)
                                self.queue.put(('error', err_msg))
                            else:
                                logging.error(f"Error running tail for {log_file_path}: {result.stderr}")
                                self.queue.put(('error', f"Could not read '{log_file_path}'."))
                            continue
                        lines = result.stdout.strip().splitlines()
                        for line in reversed(lines):
                            if not self.scan_active.is_set():
                                break
                            if not line:
                                continue
                            processed_data = self._process_linux_log_line(line, log_type, log_file_path)
                            if not processed_data:
                                continue
                            if self.exceptions:
                                if any(exc.lower() in processed_data.get('event_details', '').lower() or
                                       exc.lower() in processed_data.get('source', '').lower() for exc in
                                       self.exceptions):
                                    continue
                            if scan_type == 'keyword':
                                event_text = processed_data.get('event_details', "").lower()
                                if not any(kw.lower() in event_text for kw in self.keywords):
                                    continue
                            else:
                                if log_type != "Security" and processed_data.get('severity') == "Normal":
                                    continue
                            unique_key = (processed_data.get('source'), processed_data.get('creation_date'),
                                          processed_data.get('event_details'))
                            if unique_key in self.unique_records:
                                continue
                            self.unique_records[unique_key] = True
                            self.queue.put((update_queue_msg, processed_data))
                            events_in_type += 1
                            total_processed += 1
                            progress = min(100, (total_processed / max_total_events) * 100)
                            self.queue.put((progress_queue_msg, progress))
                            time.sleep(0.05)
                            if events_in_type >= 500:
                                break
                    except FileNotFoundError:
                        logging.error(f"'tail' command not found. Cannot efficiently read {log_file_path}.")
                        self.queue.put(('error', "'tail' command not found. Linux log reading limited."))
                    except Exception as e:
                        logging.exception(f"Error reading Linux log '{log_file_path}': {e}")
                        self.queue.put(('error', f"Error reading '{log_file_path}': {e}"))
            self.queue.put((progress_queue_msg, 100))
            logging.info(f"'{scan_type}' scan finished. Processed approximately {total_processed} events.")
        except Exception as e:
            logging.exception(f"Critical error during '{scan_type}' scan: {e}")
            self.queue.put(('error', f"Critical scan error: {e}"))

        finally:
            self.scan_active.clear()
            self.queue.put((f'status_{scan_type}', "Scan Complete"))

    def _process_windows_event(self, event, log_type):
        try:
            event_id = event.EventID & 0xFFFF
            time_generated = event.TimeGenerated.Format('%Y-%m-%d %H:%M:%S')
            computer_name = event.ComputerName
            source_name = event.SourceName
            event_type = event.EventType
            inserts = event.StringInserts if event.StringInserts else []
            inserts_str = [str(i) if i is not None else '' for i in inserts]
            full_message = " | ".join(inserts_str)
            severity = WINDOWS_EVENT_TYPES.get(event_type, "Normal")
            username = computer_name
            for item in inserts_str:
                if re.match(r"S-\d(-\d+)+", item) or "Account Name:" in item or "User:" in item:
                    parts = item.split(':')
                    if len(parts) > 1:
                        potential_user = parts[-1].strip()
                        if potential_user and potential_user != computer_name:
                            username = potential_user
                            break
                elif '\\' in item and not os.path.exists(item):
                    username = item
                    break
            path = "N/A"
            for item in inserts_str:
                if isinstance(item, str):
                    if re.search(r'\.(exe|dll|sys|bat|cmd|ps1)\b', item, re.IGNORECASE):
                        path = item
                        break
                    if ('\\' in item or '/' in item) and os.path.splitext(item)[1]:
                        path = item
            freq_key = (source_name, event_id, time_generated.split()[0])
            frequency = self.frequency_counter.get(freq_key, 0) + 1
            self.frequency_counter[freq_key] = frequency
            age = self._calculate_age(time_generated)
            suspicious = "✔" if severity == "High" or (severity == "Medium" and frequency > 5) else "✖"
            current_user = getpass.getuser()
            trigger_val = "مستخدم" if username == current_user else "نظام"
            return {
                'scan_type': None,
                'pid': None,
                'source': source_name,
                'suspicious': suspicious,
                'username': username,
                'creation_date': time_generated,
                'frequency': frequency,
                'cpu_percent': None,

                'memory_percent': None,
                'event_details': f"EvtID:{event_id} - {full_message}",
                'path': path,
                'log_name': log_type,
                'severity': severity,
                'trigger': trigger_val,
                'detection_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'age': age
            }
        except Exception as e:
            logging.error(f"Error processing Windows event: {e} - Event Data: {vars(event)}")
            return None

    def _process_linux_log_line(self, line, log_type, file_path):
        try:
            pattern = re.compile(r"(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+(\S+)\s+([^$$:]+)(?:\[(\d+)$$)?:\s+(.*)")
            match = pattern.match(line)
            timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            hostname = platform.node()
            process_name = "Unknown"
            pid = None
            message = line
            if match:
                ts_part, hostname, process_name, pid_str, message = match.groups()
                process_name = process_name.strip()
                try:
                    current_year = datetime.now().year
                    dt_obj = datetime.strptime(f"{current_year} {ts_part}", '%Y %b %d %H:%M:%S')
                    if dt_obj > datetime.now() + timedelta(days=1):
                        dt_obj = datetime.strptime(f"{current_year - 1} {ts_part}", '%Y %b %d %H:%M:%S')
                    timestamp_str = dt_obj.strftime('%Y-%m-%d %H:%M:%S')
                except ValueError:
                    logging.warning(f"Could not parse timestamp '{ts_part}'. Using current time.")
                if pid_str:
                    try:
                        pid = int(pid_str)
                    except ValueError:
                        pid = None
            else:
                parts = line.split(':', 4)
                if len(parts) > 3:
                    process_name = parts[2].split('[')[0].strip()
                    message = parts[-1].strip()
            severity = "Normal"
            msg_lower = message.lower()
            if any(k in msg_lower for k in ["error", "critical", "fail", "fatal", "denied", "attack"]):
                severity = "High"
            elif any(k in msg_lower for k in ["warning", "warn", "refused"]):
                severity = "Medium"
            path_match = re.search(r'(/[^ \t\n\r\f\v:]+)', message)

            path = path_match.group(1) if path_match else "N/A"
            freq_key = (process_name, timestamp_str.split()[0])
            frequency = self.frequency_counter.get(freq_key, 0) + 1
            self.frequency_counter[freq_key] = frequency
            age = self._calculate_age(timestamp_str)
            suspicious = "✔" if severity != "Normal" else "✖"
            current_user = getpass.getuser()
            trigger_val = "مستخدم" if hostname == current_user else "نظام"
            return {
                'scan_type': None,
                'pid': pid,
                'source': process_name,
                'suspicious': suspicious,
                'username': "N/A",
                'creation_date': timestamp_str,
                'frequency': frequency,
                'cpu_percent': None,
                'memory_percent': None,
                'event_details': message,
                'path': path,
                'log_name': log_type,
                'severity': severity,
                'trigger': trigger_val,
                'detection_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'age': age
            }
        except Exception as e:
            logging.error(f"Error processing Linux line: {e} - Line: {line[:100]}...")
            return None

    def _run_realtime_scan(self):
        logging.info("Starting Realtime Scan thread.")
        self.realtime_pid_map.clear()
        psutil.cpu_percent(interval=None)
        while self.realtime_scan_active.is_set():
            try:
                current_pids_on_system = set()
                actions = []
                time.sleep(self.realtime_interval / 2.0)
                for proc in psutil.process_iter(attrs=[
                    'pid', 'name', 'username', 'cpu_percent', 'memory_percent',
                    'create_time', 'exe', 'status'
                ]):
                    if not self.realtime_scan_active.is_set():
                        break
                    try:
                        info = proc.info
                        pid = info.get('pid')
                        if pid is None or info.get('status') == psutil.STATUS_ZOMBIE:
                            continue
                        current_pids_on_system.add(pid)

                        cpu = info.get('cpu_percent', 0.0)
                        mem = info.get('memory_percent', 0.0)
                        create_time = info.get('create_time')
                        uptime_str = "N/A"
                        uptime_seconds = 0
                        if create_time:
                            uptime_seconds = time.time() - create_time
                            uptime_str = str(timedelta(seconds=int(uptime_seconds)))
                        anomaly_str = "N/A"
                        if self.anomaly_detector and cpu is not None and mem is not None:
                            try:
                                features = np.array([[cpu, mem, max(0, uptime_seconds)]])
                                features = np.clip(features, 0, 1000)
                                prediction = self.anomaly_detector.predict(features)
                                anomaly_str = "Yes" if prediction[0] == -1 else "No"
                            except Exception as ad_err:
                                logging.warning(f"Anomaly prediction failed for PID {pid}: {ad_err}")
                        severity = self._determine_process_severity(cpu, mem)
                        suspicious = "✔" if severity != "Normal" or anomaly_str == "Yes" else "✖"
                        process_name = info.get('name', 'Unknown')
                        path = info.get('exe', process_name)
                        username = info.get('username', 'N/A')
                        detection_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        current_user = getpass.getuser()
                        trigger_val = "مستخدم" if username == current_user else "نظام"
                        data_tuple = (
                            f"rt_{pid}",
                            pid,
                            suspicious,
                            username,
                            trigger_val,
                            detection_time,
                            f"{cpu:.1f}" if cpu is not None else "N/A",
                            f"{mem:.1f}" if mem is not None else "N/A",
                            process_name,
                            path,
                            severity,
                            anomaly_str,
                            "Realtime",
                            uptime_str
                        )
                        if pid in self.realtime_pid_map:
                            item_id = self.realtime_pid_map[pid]
                            actions.append({'action': 'update', 'item_id': item_id, 'values': data_tuple})
                        else:
                            item_id = f"rt_{pid}"
                            self.realtime_pid_map[pid] = item_id
                            actions.append({'action': 'add', 'item_id': item_id, 'values': data_tuple})
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        current_pids_on_system.discard(pid)
                        if pid in self.realtime_pid_map:
                            actions.append({'action': 'remove', 'item_id': self.realtime_pid_map[pid]})
                            del self.realtime_pid_map[pid]
                        continue
                    except Exception as proc_err:
                        logging.error(f"Error processing process PID {info.get('pid', 'N/A')}: {proc_err}")
                        continue
                if not self.realtime_scan_active.is_set():
                    break
                terminated_pids = set(self.realtime_pid_map.keys()) - current_pids_on_system
                for pid in terminated_pids:
                    if pid in self.realtime_pid_map:
                        actions.append({'action': 'remove', 'item_id': self.realtime_pid_map[pid]})
                        del self.realtime_pid_map[pid]
                if actions:
                    self.queue.put(('update_realtime_table_batch', actions))
                self.queue.put(('status_realtime', f"Tracking {len(self.realtime_pid_map)} Processes"))
                time.sleep(self.realtime_interval / 2.0)
            except Exception as loop_err:
                logging.exception("Error in realtime scan loop:")
                self.queue.put(('error', f"Realtime scan error: {loop_err}"))
                time.sleep(self.realtime_interval)
        logging.info("Realtime Scan thread finished.")
        self.realtime_pid_map.clear()
        self.queue.put(('status_realtime', "Realtime Scan Stopped"))

    def _calculate_age(self, timestamp_str):
        try:
            event_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
            delta = datetime.now() - event_time
            if delta.days > 0:
                return f"{delta.days} days"
            elif delta.total_seconds() > 3600:
                return f"{delta.seconds // 3600} hours"
            elif delta.total_seconds() > 60:
                return f"{delta.seconds // 60} mins"
            else:
                return f"{max(0, delta.seconds)} secs"
        except (ValueError, TypeError):
            return "Unknown"

    def _determine_process_severity(self, cpu, memory):
        cpu = cpu if cpu is not None else 0.0
        memory = memory if memory is not None else 0.0
        if cpu > 85 or memory > 80:
            return "High"
        elif cpu > 50 or memory > 50:
            return "Medium"
        else:
            return "Normal"

    def _get_treeview_for_scan_type(self, scan_type):

        return getattr(self, f"{scan_type}_tree", None)

    def _get_status_bar_for_scan_type(self, scan_type):
        return getattr(self, f"{scan_type}_status_bar", None)

    def _get_selected_item_data(self, scan_type):
        tree = self._get_treeview_for_scan_type(scan_type)
        if not tree: return None
        selection = tree.selection()
        if not selection:
            return None
        item_id = selection[0]
        item_values = tree.item(item_id, 'values')
        item_columns = tree['columns']
        if not item_values or len(item_values) != len(item_columns):
            logging.warning(f"Could not retrieve valid data for selected item {item_id} in {scan_type} tree.")
            return None
        return dict(zip(item_columns, item_values))

    def _process_queue(self):
        try:
            while True:
                msg_type, data = self.queue.get_nowait()
                if msg_type.startswith('progress_'):
                    scan_type = msg_type.split('_')[1]
                    progress_var = getattr(self, f"{scan_type}_progress_var", None)
                    progress_label = getattr(self, f"{scan_type}_progress_label", None)
                    if progress_var and progress_label:
                        progress_val = min(100.0, float(data))
                        progress_var.set(progress_val)
                        progress_label.config(text=f"{int(progress_val)}%")
                elif msg_type.startswith('update_') and msg_type.endswith('_table'):
                    scan_type = msg_type.split('_')[1]
                    tree = self._get_treeview_for_scan_type(scan_type)
                    status_bar = self._get_status_bar_for_scan_type(scan_type)
                    if tree and status_bar and isinstance(data, dict):
                        self._insert_or_update_tree_item(tree, status_bar, data, scan_type)
                elif msg_type == 'update_realtime_table_batch':
                    self._update_realtime_table_batch(data)
                elif msg_type.startswith('status_'):
                    scan_type = msg_type.split('_')[1]
                    status_bar = self._get_status_bar_for_scan_type(scan_type)
                    tree = self._get_treeview_for_scan_type(scan_type)
                    if status_bar and tree:
                        count = len(tree.get_children())
                        status_bar.config(text=f"Records: {count} | {data}")
                elif msg_type == 'error':
                    messagebox.showerror("Error", str(data))
                    self.log_event_entry("ERROR", str(data))
                elif msg_type == 'info':
                    messagebox.showinfo("Information", str(data))

                    self.log_event_entry("INFO", str(data))
                elif msg_type == 'refresh_keywords':
                    self._refresh_keyword_listbox()
                else:
                    logging.warning(f"Unknown queue message type: {msg_type}")
                self.queue.task_done()
        except queue.Empty:
            pass
        except Exception as e:
            logging.exception("Error processing queue:")
            self.log_event_entry("CRITICAL", f"Queue processing error: {e}")
        finally:
            self.root.after(150, self._process_queue)

    def _apply_tree_tags(self, tree, item_id, values_dict):
        tags = []
        all_items = tree.get_children('')
        try:
            item_index = all_items.index(item_id)
        except ValueError:
            item_index = 0
        tags.append('evenrow' if item_index % 2 == 0 else 'oddrow')
        severity = values_dict.get('severity', 'Normal')
        tags.append(f'severity_{severity}')
        suspicious = values_dict.get('suspicious', '✖')
        tags.append('suspicious_True' if suspicious == '✔' else 'suspicious_False')
        if 'anomaly' in values_dict:
            anomaly = values_dict.get('anomaly', 'N/A')
            if anomaly == 'Yes':
                tags.append('anomaly_Yes')
        tree.item(item_id, tags=tuple(tags))

    def update_seq_numbers(self, tree):
        for idx, item_id in enumerate(tree.get_children()):
            values = list(tree.item(item_id, 'values'))
            if values:
                values[0] = str(idx + 1)
            tree.item(item_id, values=tuple(values))

    def _insert_or_update_tree_item(self, tree, status_bar, data_dict, scan_type):
        try:
            data_dict['scan_type'] = scan_type.capitalize()
            if scan_type != 'realtime':
                db_id = self._save_to_db(data_dict)
                if db_id is None:
                    logging.error("Failed to save record to database, skipping UI update.")
                    return
                item_id_str = str(db_id)
            else:
                item_id_str = data_dict.get('id', f"rt_{data_dict.get('pid', 'unknown')}")
            ordered_values = []

            for col in tree['columns']:
                if col in ['cpu_percent', 'memory_percent'] and data_dict.get(col) is not None:
                    try:
                        ordered_values.append(f"{float(data_dict.get(col)):.1f}")
                    except (ValueError, TypeError):
                        ordered_values.append(data_dict.get(col, 'N/A'))
                else:
                    ordered_values.append(data_dict.get(col, 'N/A'))
            if tree.exists(item_id_str):
                tree.item(item_id_str, values=tuple(ordered_values))
                logging.debug(f"Updated item {item_id_str} in {scan_type} tree.")
            else:
                tree.insert("", 0, iid=item_id_str, values=tuple(ordered_values))
                logging.debug(f"Inserted item {item_id_str} into {scan_type} tree.")
            values_for_tags = dict(zip(tree['columns'], ordered_values))
            self._apply_tree_tags(tree, item_id_str, values_for_tags)
            count = len(tree.get_children())
            current_status = status_bar.cget("text").split('|')[-1].strip()
            status_bar.config(text=f"Records: {count} | {current_status}")
            self.update_seq_numbers(tree)
        except tk.TclError as e:
            if "item" in str(e) and "not found" in str(e):
                logging.warning(f"Item {item_id_str} disappeared before update/tagging in {scan_type} tree.")
            else:
                logging.exception(f"TclError updating {scan_type} tree:")
                self.queue.put(('error', f"UI Update Error: {e}"))
        except Exception as e:
            logging.exception(f"Error updating {scan_type} tree:")
            self.queue.put(('error', f"Failed to update UI table: {e}"))

    def _update_realtime_table_batch(self, actions):
        tree = self.realtime_tree
        status_bar = self.realtime_status_bar
        if not tree or not status_bar:
            return
        try:
            tree.update_idletasks()
            items_to_remove = [a['item_id'] for a in actions if a['action'] == 'remove' and tree.exists(a['item_id'])]
            items_to_update = {a['item_id']: a['values'] for a in actions if
                               a['action'] == 'update' and tree.exists(a['item_id'])}
            items_to_add = [(a['item_id'], a['values']) for a in actions if
a['action'] == 'add' and not tree.exists(a['item_id'])]
            if items_to_remove:
                tree.delete(*items_to_remove)
                logging.debug(f"Removed {len(items_to_remove)} items from realtime tree.")
            for item_id, values_tuple in items_to_update.items():
                tree.item(item_id, values=values_tuple)
                values_dict = dict(zip(tree['columns'], values_tuple))
                self._apply_tree_tags(tree, item_id, values_dict)
            if items_to_update:
                logging.debug(f"Updated {len(items_to_update)} items in realtime tree.")

            for item_id, values_tuple in reversed(items_to_add):
                tree.insert("", 0, iid=item_id, values=values_tuple)
                values_dict = dict(zip(tree['columns'], values_tuple))
                self._apply_tree_tags(tree, item_id, values_dict)
            if items_to_add:
                logging.debug(f"Added {len(items_to_add)} items to realtime tree.")
            self.update_seq_numbers(tree)
        except tk.TclError as e:
            if "item" in str(e) and "not found" in str(e):
                logging.warning(f"Item disappeared during realtime batch update: {e}")
            else:
                logging.exception("TclError during realtime batch update:")
                self.queue.put(('error', f"Realtime UI Update Error: {e}"))
        except Exception as e:
            logging.exception("Error during realtime batch update:")
            self.queue.put(('error', f"Realtime UI Update Error: {e}"))

    def log_event_entry(self, level, message):
        if not hasattr(self, 'event_log'):
            return
        timestamp = datetime.now().strftime('%H:%M:%S')
        formatted_message = f"[{timestamp}] [{level}] {message}\n"
        if level in ("ERROR", "CRITICAL"):
            logging.error(message)
        elif level == "WARNING":
            logging.warning(message)
        else:
            logging.info(message)

        def update_widget():
            if self.event_log:
                current_state = self.event_log.cget('state')
                self.event_log.config(state='normal')
                self.event_log.insert(tk.END, formatted_message)
                self.event_log.config(state=current_state)
                self.event_log.see(tk.END)

        self.root.after(0, update_widget)

    def start_general_scan(self):
        if self.scan_active.is_set():
            messagebox.showwarning("Scan Active", "A log scan is already running. Please wait or stop it.")
            return
        self.scan_active.set()
        self._clear_tree_and_status('general')
        self.log_event_entry("INFO", "Starting General Scan...")
        self.scan_thread = threading.Thread(
            target=self._scan_event_logs,
            args=('general', self.log_types if IS_WINDOWS else list(self.log_types.keys())),
            daemon=True, name="GeneralScanThread"
        )
        self.scan_thread.start()

    def start_keyword_scan(self):
        if self.scan_active.is_set():
            messagebox.showwarning("Scan Active", "A log scan is already running. Please wait or stop it.")
            return
        if not self.keywords:
            messagebox.showwarning("No Keywords", "Please add keywords before starting a keyword scan.")
            return
        self.scan_active.set()
        self._clear_tree_and_status('keyword')
        self.log_event_entry("INFO", f"Starting Keyword Scan for: {', '.join(self.keywords)}...")
        self.scan_thread = threading.Thread(
            target=self._scan_event_logs,
            args=('keyword', self.log_types if IS_WINDOWS else list(self.log_types.keys()), self.keywords),
            daemon=True, name="KeywordScanThread"
        )
        self.scan_thread.start()

    def start_event_scan(self):
        if self.scan_active.is_set():
            messagebox.showwarning("Scan Active", "A log scan is already running. Please wait or stop it.")
            return
        selected_types = [log_type for log_type, var in self.event_type_vars.items() if var.get()]
        if not selected_types:
            messagebox.showwarning("No Selection", "Please select at least one event log type to scan.")
            return
        self.scan_active.set()
        self._clear_tree_and_status('event')
        self.log_event_entry("INFO", f"Starting Event Scan for types: {', '.join(selected_types)}...")
        self.scan_thread = threading.Thread(
            target=self._scan_event_logs,
            args=('event', selected_types),
            daemon=True, name="EventScanThread"
        )
        self.scan_thread.start()

    def start_realtime_scan(self):
        if self.realtime_scan_active.is_set():
            messagebox.showwarning("Scan Active", "The Realtime Scan is already running.")
            return
        self.realtime_scan_active.set()
        self._clear_tree_and_status('realtime')
        self.log_event_entry("INFO", "Starting Realtime Scan...")
        self.realtime_thread = threading.Thread(target=self._run_realtime_scan, daemon=True, name="RealtimeScanThread")
        self.realtime_thread.start()

    def stop_scan(self):
        if not self.scan_active.is_set():
            messagebox.showinfo("Not Active", "No log scan is currently running.")
            return

        if messagebox.askyesno("Confirm Stop", "Are you sure you want to stop the current log scan?"):
            self.scan_active.clear()
            self.log_event_entry("INFO", "Log scan stop requested by user.")

    def stop_realtime_scan(self):
        if not self.realtime_scan_active.is_set():
            messagebox.showinfo("Not Active", "Realtime Scan is not currently running.")
            return
        if messagebox.askyesno("Confirm Stop", "Are you sure you want to stop the Realtime Scan?"):
            self.realtime_scan_active.clear()
            self.log_event_entry("INFO", "Realtime scan stop requested by user.")

    def kill_selected_process_or_event(self):
        scan_type = self._get_current_scan_type()
        if not scan_type or scan_type == 'realtime':
            messagebox.showerror("Error", "Invalid tab for this action.")
            return
        selected_data = self._get_selected_item_data(scan_type)
        if not selected_data:
            messagebox.showwarning("Selection Required", "Please select a log entry first.")
            return
        pid_str = selected_data.get('pid')
        process_path = selected_data.get('path', 'N/A')
        event_details = selected_data.get('event_details', '')
        source = selected_data.get('source', 'Unknown')
        pid_to_kill = None
        if pid_str and pid_str != 'N/A':
            try:
                pid_to_kill = int(pid_str)
            except ValueError:
                pass
        if pid_to_kill is None:
            pid_match = re.search(r'\d+', event_details)
            if pid_match:
                try:
                    pid_to_kill = int(pid_match.group(0))
                except ValueError:
                    pass
        if pid_to_kill is None and process_path != 'N/A' and os.path.exists(process_path):
            process_name = os.path.basename(process_path)
            try:
                for proc in psutil.process_iter(['pid', 'name', 'exe']):
                    if proc.info['name'] == process_name and proc.info['exe'] == process_path:
                        pid_to_kill = proc.info['pid']
                        logging.info(f"Found matching PID {pid_to_kill} by path {process_path}")
                        break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            except Exception as e:
                logging.error(f"Error searching for process by path {process_path}: {e}")
        if pid_to_kill is None:
            if source.lower().endswith(('.exe', '.dll', '.sys')):

                process_name = source
                try:
                    for proc in psutil.process_iter(['pid', 'name']):
                        if proc.info['name'] == process_name:
                            pid_to_kill = proc.info['pid']
                            logging.info(f"Found matching PID {pid_to_kill} by source name {source}")
                            break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                except Exception as e:
                    logging.error(f"Error searching for process by source {source}: {e}")
        if pid_to_kill is None:
            messagebox.showerror("Error",
                                 f"Could not determine a valid Process ID (PID) to terminate for the selected entry (Path: {process_path}, Source: {source}).")
            return
        try:
            if not psutil.pid_exists(pid_to_kill):
                messagebox.showinfo("Process Not Found", f"Process with PID {pid_to_kill} does not exist anymore.")
                return
            proc = psutil.Process(pid_to_kill)
            proc_name = proc.name()
            if messagebox.askyesno("Confirm Kill",
                                   f"Are you sure you want to terminate process '{proc_name}' (PID: {pid_to_kill}) associated with the selected log entry?"):
                proc.terminate()
                try:
                    proc.wait(timeout=1)
                except psutil.TimeoutExpired:
                    logging.warning(f"Process {pid_to_kill} did not terminate gracefully, forcing kill.")
                    proc.kill()
                messagebox.showinfo("Success", f"Process '{proc_name}' (PID: {pid_to_kill}) terminated.")
                self.log_event_entry("INFO",
                                     f"Terminated process '{proc_name}' (PID: {pid_to_kill}) based on log selection.")
        except psutil.NoSuchProcess:
            messagebox.showinfo("Process Gone",
                                f"Process with PID {pid_to_kill} terminated before action could be completed.")
        except psutil.AccessDenied:
            messagebox.showerror("Access Denied",
                                 f"Permission denied trying to terminate process PID {pid_to_kill}. Try running as Administrator.")
            self.log_event_entry("ERROR", f"Access denied terminating PID {pid_to_kill}.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to terminate process PID {pid_to_kill}: {e}")
            self.log_event_entry("ERROR", f"Error terminating PID {pid_to_kill}: {e}")

    def kill_realtime_process(self):
        scan_type = 'realtime'
        selected_data = self._get_selected_item_data(scan_type)
        if not selected_data:
            messagebox.showwarning("Selection Required", "Please select a process in the Realtime Scan list first.")
            return
        pid_str = selected_data.get('pid')
        process_name = selected_data.get('event_details', 'Unknown Process')

        if not pid_str or pid_str == 'N/A':
            messagebox.showerror("Error", "Invalid PID selected.")
            return
        try:
            pid_to_kill = int(pid_str)
        except ValueError:
            messagebox.showerror("Error", f"Invalid PID format: {pid_str}")
            return
        try:
            if not psutil.pid_exists(pid_to_kill):
                messagebox.showinfo("Process Not Found",
                                    f"Process '{process_name}' (PID: {pid_to_kill}) does not exist anymore.")
                tree = self._get_treeview_for_scan_type(scan_type)
                item_id = selected_data.get('id')
                if tree and item_id and tree.exists(item_id):
                    tree.delete(item_id)
                if pid_to_kill in self.realtime_pid_map:
                    del self.realtime_pid_map[pid_to_kill]
                return
            proc = psutil.Process(pid_to_kill)
            process_name = proc.name()
            if messagebox.askyesno("Confirm Kill",
                                   f"Are you sure you want to terminate process '{process_name}' (PID: {pid_to_kill})?"):
                proc.terminate()
                try:
                    proc.wait(timeout=1)
                except psutil.TimeoutExpired:
                    logging.warning(f"Realtime process {pid_to_kill} did not terminate gracefully, forcing kill.")
                    proc.kill()
                messagebox.showinfo("Success", f"Process '{process_name}' (PID: {pid_to_kill}) terminated.")
                self.log_event_entry("INFO", f"Terminated realtime process '{process_name}' (PID: {pid_to_kill}).")
                tree = self._get_treeview_for_scan_type(scan_type)
                item_id = selected_data.get('id')
                if tree and item_id and tree.exists(item_id):
                    tree.delete(item_id)
                if pid_to_kill in self.realtime_pid_map:
                    del self.realtime_pid_map[pid_to_kill]
        except psutil.NoSuchProcess:
            messagebox.showinfo("Process Gone",
                                f"Process '{process_name}' (PID: {pid_to_kill}) terminated before action could be completed.")
            tree = self._get_treeview_for_scan_type(scan_type)
            item_id = selected_data.get('id')
            if tree and item_id and tree.exists(item_id):
                tree.delete(item_id)
            if pid_to_kill in self.realtime_pid_map:
                del self.realtime_pid_map[pid_to_kill]
        except psutil.AccessDenied:
            messagebox.showerror("Access Denied",
                                 f"Permission denied trying to terminate process PID {pid_to_kill}. Try running as Administrator.")
            self.log_event_entry("ERROR", f"Access denied terminating realtime PID {pid_to_kill}.")
        except Exception as e:

            messagebox.showerror("Error", f"Failed to terminate process PID {pid_to_kill}: {e}")
            self.log_event_entry("ERROR", f"Error terminating realtime PID {pid_to_kill}: {e}")

    def refresh_data(self, scan_type):
        if scan_type == 'realtime':
            messagebox.showinfo("Info", "Realtime Scan updates automatically. No manual refresh needed.")
            return
        tree = self._get_treeview_for_scan_type(scan_type)
        status_bar = self._get_status_bar_for_scan_type(scan_type)
        if not tree or not status_bar:
            messagebox.showerror("Error", "Could not find UI elements for the current tab.")
            return
        logging.info(f"Refreshing data for '{scan_type}' tab from database.")
        self._clear_tree_and_status(scan_type, "Refreshing...")
        try:
            with self.db_lock:
                cursor = self.db_conn.cursor()
                cursor.execute("SELECT * FROM log_entries ORDER BY id ASC")
                records = cursor.fetchall()
            if not records:
                status_bar.config(text="Records: 0 | No data found in database.")
                messagebox.showinfo("Refreshed", f"No records found in the database.")
                return
            db_cols = [desc[0] for desc in cursor.description]
            tree_cols = tree['columns']
            tree.update_idletasks()
            for record in records:
                record_dict = dict(zip(db_cols, record))
                item_id = str(record_dict['id'])
                if tree.exists(item_id):
                    continue
                ordered_values = [record_dict.get(col, 'N/A') for col in tree_cols]
                tree.insert("", 'end', iid=item_id, values=tuple(ordered_values))
                self._apply_tree_tags(tree, item_id, record_dict)
            count = len(tree.get_children())
            status_bar.config(text=f"Records: {count} | Refresh Complete")
            logging.info(f"Successfully refreshed '{scan_type}' tab with {count} records.")
            self.update_seq_numbers(tree)
        except sqlite3.Error as e:
            logging.error(f"Database error during refresh: {e}")
            messagebox.showerror("Database Error", f"Failed to refresh data: {e}")
            status_bar.config(text="Records: 0 | Error refreshing data")
        except Exception as e:
            logging.exception(f"Unexpected error during refresh:")
            messagebox.showerror("Error", f"An unexpected error occurred during refresh: {e}")
            status_bar.config(text="Records: 0 | Error refreshing data")

    def delete_all_records(self):
        if not messagebox.askyesno("Confirm Deletion",
                                   f"⚠️ WARNING! ⚠️\n\nAre you absolutely sure you want to delete ALL records from the database?\n\nThis action cannot be undone!"):
            return

        logging.warning("Attempting to delete all records.")
        try:
            with self.db_lock:
                cursor = self.db_conn.cursor()
                cursor.execute("DELETE FROM log_entries")
                deleted_count = cursor.rowcount
                self.db_conn.commit()
            for t in ['general', 'keyword', 'event']:
                self._clear_tree_and_status(t, "All records deleted.")
            messagebox.showinfo("Deletion Complete", f"Successfully deleted {deleted_count} records from the database.")
            self.log_event_entry("WARNING", f"Deleted {deleted_count} records.")
        except sqlite3.Error as e:
            logging.error(f"Database error deleting records: {e}")
            messagebox.showerror("Database Error", f"Failed to delete records: {e}")
        except Exception as e:
            logging.exception(f"Unexpected error deleting records:")
            messagebox.showerror("Error", f"An unexpected error occurred during deletion: {e}")

    def export_results(self, scan_type):
        tree = self._get_treeview_for_scan_type(scan_type)
        if not tree:
            return
        records = []
        columns = list(tree['columns'])
        if scan_type == 'realtime':
            if not self.realtime_tree.get_children():
                messagebox.showinfo("No Data", "There is no data in the Realtime Scan tab to export.")
                return
            for item_id in self.realtime_tree.get_children():
                records.append(list(self.realtime_tree.item(item_id)['values']))
            export_source = "Realtime Scan View"
        else:
            try:
                with self.db_lock:
                    cursor = self.db_conn.cursor()
                    cursor.execute(f"SELECT {', '.join(columns)} FROM log_entries ORDER BY id ASC")
                    records = cursor.fetchall()
                if not records:
                    messagebox.showinfo("No Data", "No records found in the database to export.")
                    return
                export_source = "Database"
            except sqlite3.Error as e:
                messagebox.showerror("Database Error", f"Failed to fetch data for export: {e}")
                logging.error(f"DB error fetching data for export: {e}")
                return
        filetypes = [("Excel File", "*.xlsx"), ("CSV File", "*.csv"),
                     ("JSON File", "*.json"), ("HTML File", "*.html")]
        if REPORTLAB_AVAILABLE:
            filetypes.append(("PDF File", "*.pdf"))
        default_filename = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        save_path = filedialog.asksaveasfilename(
            title="Export Results",
            defaultextension=".xlsx",
            filetypes=filetypes,
            initialfile=default_filename
        )
        if not save_path:
            return
        logging.info(f"Exporting {len(records)} records from {export_source} to {save_path}")
        try:
            df = pd.DataFrame(records, columns=columns)
            file_ext = os.path.splitext(save_path)[1].lower()
            if file_ext == ".xlsx":
                df.to_excel(save_path, index=False, engine='openpyxl')
            elif file_ext == ".csv":
                df.to_csv(save_path, index=False, encoding='utf-8-sig')
            elif file_ext == ".json":
                df.to_json(save_path, orient='records', indent=4, force_ascii=False)
            elif file_ext == ".html":
                html_content = f"<html><head><title>Export</title></head><body>"
                html_content += f"<h1>Export - {datetime.now()}</h1>"
                html_content += df.to_html(index=False, border=1, classes='table table-striped', justify='center')
                html_content += "</body></html>"
                with open(save_path, "w", encoding='utf-8') as f:
                    f.write(html_content)
            elif file_ext == ".pdf" and REPORTLAB_AVAILABLE:
                self._export_to_pdf(df, save_path, "Scan Results")
            else:
                messagebox.showerror("Unsupported Format", f"File format '{file_ext}' is not supported for export.")
                return
            messagebox.showinfo("Export Successful", f"Successfully exported {len(records)} records to:\n{save_path}")
            self.log_event_entry("INFO", f"Exported results to {save_path}")
        except Exception as e:
            logging.exception(f"Error during export to {save_path}:")
            messagebox.showerror("Export Error", f"Failed to export data: {e}")
            self.log_event_entry("ERROR", f"Export failed: {e}")

    def _export_to_pdf(self, dataframe, filename, title):
        # تأجيل تحميل مكتبة reportlab داخل دالة التصدير
        try:
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
            from reportlab.lib import colors as rl_colors
            from reportlab.lib.pagesizes import letter, landscape
            from reportlab.lib.styles import getSampleStyleSheet
        except ImportError:
            messagebox.showerror("Error", "reportlab is not available.")
            return
        doc = SimpleDocTemplate(filename, pagesize=landscape(letter))
        styles = getSampleStyleSheet()

        elements = []
        elements.append(Paragraph(title, styles['h1']))
        elements.append(Paragraph(f"Exported on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
        data = [dataframe.columns.to_list()] + dataframe.astype(str).values.tolist()
        table = Table(data, repeatRows=1)
        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), rl_colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), rl_colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), rl_colors.aliceblue),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, rl_colors.black),
        ])
        table.setStyle(style)
        num_cols = len(dataframe.columns)
        page_width, page_height = landscape(letter)
        available_width = page_width - doc.leftMargin - doc.rightMargin
        col_widths = [available_width / num_cols] * num_cols
        try:
            details_idx = dataframe.columns.get_loc('event_details')
            path_idx = dataframe.columns.get_loc('path')
            reduction_factor = 0.85
            extra_width = (available_width * (1 - reduction_factor)) / 2
            col_widths = [w * reduction_factor for w in col_widths]
            col_widths[details_idx] += extra_width
            col_widths[path_idx] += extra_width
        except KeyError:
            pass
        table._argW = col_widths
        elements.append(table)
        doc.build(elements)

    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self.log_event_entry("INFO", f"Switching to {'Dark' if self.dark_mode else 'Light'} theme.")
        self._setup_styles()
        self.root.configure(bg=self.current_colors['bg'])
        self.keywords_listbox.configure(bg=self.current_colors['tree_odd'], fg=self.current_colors['fg'],
                                        selectbackground=self.current_colors['accent'],
                                        selectforeground=self.current_colors['btn_text'])
        self.event_log.configure(bg=self.current_colors['tree_odd'], fg=self.current_colors['fg'])
        for scan_type in ['general', 'keyword', 'event', 'realtime']:
            tree = self._get_treeview_for_scan_type(scan_type)
            if tree:
                for item_id in tree.get_children():

                    try:
                        values = tree.item(item_id)['values']
                        values_dict = dict(zip(tree['columns'], values))
                        self._apply_tree_tags(tree, item_id, values_dict)
                    except Exception as e:
                        logging.warning(f"Error reapplying tags during theme change for {item_id}: {e}")
        messagebox.showinfo("Theme Changed", f"Switched to {'Dark' if self.dark_mode else 'Light'} theme.")

    def add_keyword(self):
        new_kw = simpledialog.askstring("Add Keyword", "Enter new suspicious keyword:", parent=self.root)
        if new_kw:
            new_kw = new_kw.strip().lower()
            if new_kw and new_kw not in self.keywords:
                self.keywords.append(new_kw)
                self._save_keywords()
                self.queue.put(('refresh_keywords', None))
                self.log_event_entry("INFO", f"Added keyword: '{new_kw}'")
            elif new_kw in self.keywords:
                messagebox.showwarning("Duplicate", f"Keyword '{new_kw}' already exists.")
            else:
                messagebox.showwarning("Invalid", "Please enter a valid keyword.")

    def edit_keyword(self):
        selection = self.keywords_listbox.curselection()
        if not selection:
            messagebox.showwarning("Selection Required", "Please select a keyword to edit.")
            return
        index = selection[0]
        current_kw = self.keywords_listbox.get(index)
        new_kw = simpledialog.askstring("Edit Keyword", "Edit the keyword:", initialvalue=current_kw, parent=self.root)
        if new_kw:
            new_kw = new_kw.strip().lower()
            if new_kw and new_kw != current_kw:
                if new_kw in self.keywords:
                    messagebox.showwarning("Duplicate", f"Keyword '{new_kw}' already exists in the list.")
                    return
                self.keywords[index] = new_kw
                self._save_keywords()
                self.queue.put(('refresh_keywords', None))
                self.log_event_entry("INFO", f"Edited keyword: '{current_kw}' -> '{new_kw}'")
            elif not new_kw:
                messagebox.showwarning("Invalid", "Please enter a valid keyword.")

    def remove_keyword(self):
        selection = self.keywords_listbox.curselection()
        if not selection:
            messagebox.showwarning("Selection Required", "Please select a keyword to remove.")
            return
        index = selection[0]
        kw_to_remove = self.keywords_listbox.get(index)

        if messagebox.askyesno("Confirm Removal", f"Are you sure you want to remove the keyword '{kw_to_remove}'?"):
            if kw_to_remove in self.keywords:
                self.keywords.pop(index)
                self._save_keywords()
                self.queue.put(('refresh_keywords', None))
                self.log_event_entry("INFO", f"Removed keyword: '{kw_to_remove}'")
            else:
                messagebox.showerror("Error", "Keyword not found in internal list.")
                self.queue.put(('refresh_keywords', None))

    def _refresh_keyword_listbox(self):
        if hasattr(self, 'keywords_listbox'):
            self.keywords_listbox.delete(0, tk.END)
            for kw in sorted(self.keywords):
                self.keywords_listbox.insert(tk.END, kw)
            self.keywords_listbox.configure(bg=self.current_colors['tree_odd'], fg=self.current_colors['fg'],
                                            selectbackground=self.current_colors['accent'],
                                            selectforeground=self.current_colors['btn_text'])

    # New Improvement: Import SIGMA Rules from YAML Files and store them in SQLite database
    def import_sigma_rules(self):
        try:
            import yaml  # تأكد من تثبيت PyYAML باستخدام pip install PyYAML
        except ImportError:
            messagebox.showerror("المكتبة المفقودة",
                                 "لم يتم تثبيت مكتبة PyYAML. قم بتثبيتها باستخدام: pip install PyYAML")
            return
        # Allow user to select one or multiple YAML files
        files = filedialog.askopenfilenames(title="اختر ملفات YAML", filetypes=[("YAML Files", "*.yaml *.yml")])
        if not files:
            return
        imported_count = 0
        with self.db_lock:
            cursor = self.db_conn.cursor()
            for file_path in files:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        rule_data = yaml.safe_load(f)
                    if rule_data:
                        # Use the filename as the rule name
                        rule_name = os.path.basename(file_path)
                        # Convert the rule data to JSON string for storage in the database
                        rule_json = json.dumps(rule_data, ensure_ascii=False, indent=2)
                        cursor.execute("INSERT INTO sigma_rules (rule_name, rule_data) VALUES (?, ?)",
                                       (rule_name, rule_json))
                        imported_count += 1
                except Exception as e:
                    logging.error(f"Error importing Sigma rule from {file_path}: {e}")
            self.db_conn.commit()
        messagebox.showinfo("Import Completed", f"تم استيراد {imported_count} قاعدة SIGMA.")

        self.log_event_entry("INFO", f"Imported {imported_count} Sigma rules from YAML files.")

    def add_exception(self):
        new_ex = simpledialog.askstring("إضافة استثناء", "أدخل اسم أو نشاط النظام للاستثناء:", parent=self.root)
        if new_ex:
            new_ex = new_ex.strip()
            if new_ex and new_ex not in self.exceptions:
                self.exceptions.append(new_ex)
                self._save_exceptions()
                self._refresh_exceptions_listbox()
                self.log_event_entry("INFO", f"تمت إضافة الاستثناء: '{new_ex}'")
            elif new_ex in self.exceptions:
                messagebox.showwarning("مكرر", f"الاستثناء '{new_ex}' موجود بالفعل.")
            else:
                messagebox.showwarning("غير صالح", "يرجى إدخال استثناء صالح.")

    def edit_exception(self):
        selection = self.exceptions_listbox.curselection()
        if not selection:
            messagebox.showwarning("يتطلب تحديد", "يرجى تحديد استثناء لتعديله.")
            return
        index = selection[0]
        current_ex = self.exceptions_listbox.get(index)
        new_ex = simpledialog.askstring("تعديل الاستثناء", "عدل اسم أو نشاط النظام للاستثناء:", initialvalue=current_ex,
                                        parent=self.root)
        if new_ex:
            new_ex = new_ex.strip()
            if new_ex and new_ex != current_ex:
                if new_ex in self.exceptions:
                    messagebox.showwarning("مكرر", f"الاستثناء '{new_ex}' موجود بالفعل.")
                    return
                self.exceptions[index] = new_ex
                self._save_exceptions()
                self._refresh_exceptions_listbox()
                self.log_event_entry("INFO", f"تم تعديل الاستثناء: '{current_ex}' -> '{new_ex}'")
            elif not new_ex:
                messagebox.showwarning("غير صالح", "يرجى إدخال استثناء صالح.")

    def remove_exception(self):
        selection = self.exceptions_listbox.curselection()
        if not selection:
            messagebox.showwarning("يتطلب تحديد", "يرجى تحديد استثناء لحذفه.")
            return
        index = selection[0]
        ex_to_remove = self.exceptions_listbox.get(index)
        if messagebox.askyesno("تأكيد الحذف", f"هل انت متأكد من حذف الاستثناء '{ex_to_remove}'؟"):
            if ex_to_remove in self.exceptions:
                self.exceptions.pop(index)
                self._save_exceptions()
                self._refresh_exceptions_listbox()
                self.log_event_entry("INFO", f"تم حذف الاستثناء: '{ex_to_remove}'")

            else:
                messagebox.showerror("خطأ", "لم يتم العثور على الاستثناء في القائمة الداخلية.")

    def _refresh_exceptions_listbox(self):
        if hasattr(self, 'exceptions_listbox'):
            self.exceptions_listbox.delete(0, tk.END)
            for ex in self.exceptions:
                self.exceptions_listbox.insert(tk.END, ex)
            self.exceptions_listbox.configure(bg=self.current_colors['tree_odd'], fg=self.current_colors['fg'],
                                              selectbackground=self.current_colors['accent'],
                                              selectforeground=self.current_colors['btn_text'])

    def start_exception_management(self):
        messagebox.showinfo("تشغيل", "تم تفعيل إدارة الاستثناءات في جميع الفحوصات.")
        self.log_event_entry("INFO", "تم تشغيل إدارة الاستثناءات.")
        if hasattr(self, 'exception_status_label'):
            self.exception_status_label.config(text="نشط", foreground="green")

    def stop_exception_management(self):
        messagebox.showinfo("إيقاف", "تم إيقاف إدارة الاستثناءات في جميع الفحوصات.")
        self.log_event_entry("INFO", "تم إيقاف إدارة الاستثناءات.")
        if hasattr(self, 'exception_status_label'):
            self.exception_status_label.config(text="متوقف", foreground="red")

    def _clear_tree_and_status(self, scan_type, status_text="Ready"):
        tree = self._get_treeview_for_scan_type(scan_type)
        status_bar = self._get_status_bar_for_scan_type(scan_type)
        if tree:
            try:
                tree.delete(*tree.get_children())
            except tk.TclError as e:
                logging.warning(f"TclError clearing tree {scan_type}: {e}")
            except Exception as e:
                logging.error(f"Error clearing tree {scan_type}: {e}")
        if status_bar:
            status_bar.config(text=f"Records: 0 | {status_text}")
        if scan_type != 'realtime':
            progress_var = getattr(self, f"{scan_type}_progress_var", None)
            progress_label = getattr(self, f"{scan_type}_progress_label", None)
            if progress_var: progress_var.set(0.0)
            if progress_label: progress_label.config(text="0%")
        self.unique_records.clear()

    def _get_current_scan_type(self):
        try:
            current_tab_index = self.notebook.index(self.notebook.select())
            tab_map = {1: 'general', 2: 'keyword', 3: 'event', 4: 'realtime', 5: 'exceptions'}
            return tab_map.get(current_tab_index)
        except Exception:
            return None

    def _save_to_db(self, data_dict):
        required_cols = [
            'scan_type', 'pid', 'source', 'suspicious', 'username', 'creation_date',
            'frequency', 'cpu_percent', 'memory_percent', 'event_details', 'path',
            'log_name', 'severity', 'trigger', 'detection_date', 'age'
        ]
        values = [data_dict.get(col) for col in required_cols]
        sql = f'''
            INSERT INTO log_entries ({', '.join(required_cols)})
            VALUES ({', '.join(['?'] * len(required_cols))})
        '''
        try:
            with self.db_lock:
                cursor = self.db_conn.cursor()
                cursor.execute(sql, values)
                self.db_conn.commit()
                last_id = cursor.lastrowid
                logging.debug(f"Saved record ID {last_id} to database.")
                return last_id
        except sqlite3.Error as e:
            logging.error(f"Database save error: {e} - Data: {data_dict}")
            self.queue.put(('error', f"Database Error: {e}"))
            return None
        except Exception as e:
            logging.exception(f"Unexpected error saving to DB:")
            self.queue.put(('error', f"Unexpected DB save Error: {e}"))
            return None

    def on_close(self):
        logging.info("Close requested. Shutting down...")
        self.scan_active.clear()
        self.realtime_scan_active.clear()
        if self.db_conn:
            try:
                self.db_conn.close()
                logging.info("Database connection closed.")
            except sqlite3.Error as e:
                logging.error(f"Error closing database: {e}")
        self.root.destroy()
        logging.info("Application closed.")


if __name__ == '__main__':
    try:
        analyzer = LogAnalyzer()
        analyzer.root.mainloop()
    except Exception as e:
        logging.exception("Critical error starting application:")
        tk_root = tk.Tk()
        tk_root.withdraw()
        messagebox.showerror("Fatal Error", f"Failed to start Log Analyzer Pro:\n\n{e}", parent=None)
        sys.exit(1)
































