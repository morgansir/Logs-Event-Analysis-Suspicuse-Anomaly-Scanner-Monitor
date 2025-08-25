import sys
import threading
import time
import csv
import os
from datetime import datetime, timedelta
import platform  # Import platform to check OS
import re  # Import regular expression module

# --- Conditional Imports and OS-Specific Setup ---
IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"

# Common imports
try:
    import pyqtgraph as pg  # مكتبة الرسوم البيانية
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.pdfgen import canvas
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle, Paragraph
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    import arabic_reshaper
    from bidi.algorithm import get_display

    import pandas as pd

    # Register font for PDF (handle potential missing font)
    try:
        # Attempt to use Arial Unicode MS for better Arabic/multilingual support
        # On Linux, this might need a different font path or font name
        # For cross-platform, a more robust font handling might be needed,
        # but for now, let's try a common approach.
        # Consider 'NotoSansArabic-Regular.ttf' for Linux if 'arial.ttf' is not found
        pdfmetrics.registerFont(TTFont('ArialUnicodeMS', 'arial.ttf'))
    except Exception:
        print("تحذير: لم يتم العثور على خط 'arial.ttf'. قد تظهر النصوص العربية بشكل غير صحيح في ملفات PDF.")
        # Fallback to Helvetica if Arial Unicode MS is not found
        pdfmetrics.registerFont(TTFont('ArialUnicodeMS', 'Helvetica'))

except ImportError as e:
    print(f"خطأ في استيراد المكتبات الأساسية: {e}")
    print(
        "يرجى التأكد من تثبيت المكتبات المطلوبة: 'pip install PyQt6 pyqtgraph reportlab arabic_reshaper python-bidi pandas openpyxl'")
    sys.exit(1)

# OS-specific imports
if IS_WINDOWS:
    try:
        import win32evtlog
        import win32evtlogutil
        import win32con
        import pywintypes
        import win32api
        import win32security
    except ImportError:
        print("مكتبات Windows (pywin32) غير مثبتة. يرجى تشغيل: 'pip install pywin32'")
        sys.exit(1)
elif IS_LINUX:
    try:
        from systemd import journal  # For structured log access on systemd systems
        # For basic file reading fallback, no special imports needed initially
        # We might need to parse syslog format, which can be complex.
        # For now, let's prioritize systemd.journal.
    except ImportError:
        print("مكتبة systemd.journal غير مثبتة. يرجى تشغيل: 'pip install python-systemd'")
        print("سيتم استخدام قارئ سجلات بسيط يعتمد على الملفات كبديل، ولكنه قد لا يكون شاملاً.")
        journal = None  # Indicate that systemd.journal is not available

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QGroupBox, QLabel, QLineEdit, QPushButton, QComboBox, QTableView,
    QMessageBox, QStatusBar, QProgressBar, QMenu, QDialog,
    QGridLayout, QHeaderView, QAbstractItemView, QFileDialog, QTextEdit, QCheckBox, QFrame,
    QListWidget, QListWidgetItem, QRadioButton, QButtonGroup, QInputDialog
)
from PyQt6.QtCore import (
    Qt, QAbstractTableModel, QModelIndex, QVariant, QSettings, QThread, pyqtSignal, QSize
)
from PyQt6.QtGui import QFont, QIcon, QColor, QPixmap, QAction, QCursor


# ==============================================================================

class SettingsManager:
    """
    فئة لإدارة إعدادات التطبيق وتوفير آلية للترجمة.
    """

    def __init__(self):
        self.settings = QSettings("LogAnalyzerPro", "App")
        self.translations = {
            'en': {
                "Log Analyzer": "Log Analyzer", "Inputs": "Inputs", "Outputs": "Outputs",
                "Log Sources": "Log Sources", "Keywords to include": "Keywords to include",
                "Keywords to exclude": "Keywords to exclude", "Time Range (hours)": "Time Range (hours)",
                "Severity Levels": "Severity Levels", "Event IDs": "Event IDs",
                "Analyze Logs": "Analyze Logs", "File": "File", "Export Results": "Export Results",
                "Export Selected Results": "Export Selected Results", "Settings": "Settings",
                "Theme": "Theme", "Language": "Language", "Exit": "Exit",
                "Dark": "Dark", "Light": "Light", "English": "English", "Arabic": "Arabic",
                "Analyze": "Analyze", "Status": "Status:", "Ready": "Ready.",
                "Analyzing logs...": "Analyzing logs...",
                "Analysis complete. Found {} matching events.": "Analysis complete. Found {} matching events.",
                "Error": "Error", "Warning": "Warning", "Information": "Information", "Success": "Success",
                "Failure": "Failure", "AuditSuccess": "AuditSuccess", "AuditFailure": "AuditFailure",
                "No matching events found.": "No matching events found.",
                "Events loaded successfully.": "Events loaded successfully.",
                "Export to CSV": "Export to CSV", "Save results as": "Save results as",
                "CSV Files (*.csv)": "CSV Files (*.csv)", "Export successful.": "Export successful.",
                "Failed to export results.": "Failed to export results.", "Settings Dialog": "Settings Dialog",
                "Choose a theme:": "Choose a theme:", "Choose a language:": "Choose a language:",
                "Apply": "Apply", "Close": "Close", "Log Name": "Log Name", "Event ID": "Event ID",
                "Event Source": "Event Source", "Creation Time": "Creation Time", "Matched Keyword": "Matched Keyword",
                "Time since analysis start": "Time since analysis start", "Severity Level": "Severity Level",
                "Message": "Message", "Analysis Status": "Analysis Status",
                "Please specify at least one Log Source.": "Please specify at least one Log Source.",
                "Event ID must be a comma-separated list of numbers.": "Event ID must be a comma-separated list of numbers.",
                "Time Range must be a positive number.": "Time Range must be a positive number.",
                "No logs found for the given criteria.": "No logs found for the given criteria.",
                "No rows selected to export.": "No rows selected to export.", "Show Full Details": "Show Full Details",
                "Isolate Log": "Isolate Log", "Export Selected Record": "Export Selected Record",
                "High": "High", "Medium": "Medium", "Low": "Low", "Log Details": "Log Details",
                "Security log access denied. Please run as Administrator.": "Security log access denied. Please run as Administrator.",
                "Error reading log '{}': {}": "Error reading log '{}': {}",
                "An unexpected error occurred: {}": "An unexpected error occurred: {}",
                "Failed to open log '{}': {}": "Failed to open log '{}': {}",
                "Load from file...": "Load from file...", "Select a keyword file": "Select a keyword file",
                "Text Files (*.txt)": "Text Files (*.txt)", "Error loading file.": "Error loading file.",
                "The file is empty.": "The file is empty.",
                "Restart Application": "Please restart the application for all language changes to take effect.",
                "Failed to retrieve log details. Please try again.": "Failed to retrieve log details. Please try again.",
                "Error: Failed to format event message.": "Error: Failed to format event message.",
                "Add": "Add", "Delete": "Delete",
                "Keyword Match Mode": "Keyword Match Mode",
                "Exact Match": "Exact Match",
                "Starts With": "Starts With",
                "Contains": "Contains",
                "Add Keywords": "Add Keywords",
                "Delete Keywords": "Delete Keywords",
                "Add Log Source": "Add Log Source",
                "Remove Log Source": "Remove Log Source",
                "already exists.": "already exists.",
                "Event Severity Distribution": "Event Severity Distribution",  # New
                "Count (events)": "Count (events)",  # New
                "Log Analyzer Report": "Log Analyzer Report",  # New
                "Show Reports": "Show Reports",  # New
                "Reports": "Reports",  # New
                "Export to PDF": "Export to PDF",  # New
                "Export to XLSX": "Export to XLSX",  # New
                "Failed Logins Details": "Failed Logins Details",  # New
                "Successful Logins Details": "Successful Logins Details",  # New
                "High Severity Details": "High Severity Details",  # New
                "Medium Severity Details": "Medium Severity Details",  # New
                "Low Severity Details": "Low Severity Details",  # New
                "Error Details": "Error Details",  # New
                "Warning Details": "Warning Details",  # New
                "Audit Success Details": "Audit Success Details",  # New
                "Audit Failure Details": "Audit Failure Details",  # New
                "No logs found for this category.": "No logs found for this category.",  # New
                "No keywords selected to delete.": "No keywords selected to delete.",  # New
                "Systemd Journal (Linux)": "Systemd Journal (Linux)",  # New
                "Common Log Files (Linux)": "Common Log Files (Linux)",  # New
                "Please run as root or with appropriate permissions to access logs.": "Please run as root or with appropriate permissions to access logs.",
                # New
                "Failed to read log file '{}': {}": "Failed to read log file '{}': {}",  # New
                "Unsupported log source type for Linux.": "Unsupported log source type for Linux.",  # New
                "Log file '{}' not found or not readable.": "Log file '{}' not found or not readable.",  # New
            },
            'ar': {
                "Log Analyzer": "محلل السجلات", "Inputs": "المدخلات", "Outputs": "المخرجات",
                "Log Sources": "مصادر السجلات", "Keywords to include": "كلمات رئيسية للمطابقة",
                "Keywords to exclude": "كلمات رئيسية للاستثناء", "Time Range (hours)": "النطاق الزمني (ساعة)",
                "Severity Levels": "مستويات الخطورة", "Event IDs": "معرفات الأحداث",
                "Analyze Logs": "تحليل السجلات", "File": "ملف", "Export Results": "تصدير النتائج",
                "Export Selected Results": "تصدير النتائج المحددة", "Settings": "إعدادات",
                "Theme": "المظهر", "Language": "اللغة", "Exit": "خروج",
                "Dark": "مظلم", "Light": "فاتح", "English": "الإنجليزية", "Arabic": "العربية",
                "Analyze": "تحليل", "Status": "الحالة:", "Ready": "جاهز.",
                "Analyzing logs...": "جاري تحليل السجلات...",
                "Analysis complete. Found {} matching events.": "اكتمل التحليل. تم العثور على {} حدث مطابق.",
                "Error": "خطأ", "Warning": "تحذير", "Information": "معلومات", "Success": "نجاح",
                "Failure": "فشل", "AuditSuccess": "نجاح التدقيق", "AuditFailure": "فشل التدقيق",
                "No matching events found.": "لم يتم العثور على أحداث مطابقة.",
                "Events loaded successfully.": "تم تحميل الأحداث بنجاح.",
                "Export to CSV": "تصدير إلى CSV", "Save results as": "حفظ النتائج باسم",
                "CSV Files (*.csv)": "ملفات CSV (*.csv)", "Export successful.": "تم التصدير بنجاح.",
                "Failed to export results.": "فشل تصدير النتائج.", "Settings Dialog": "نافذة الإعدادات",
                "Choose a theme:": "اختر مظهرًا:", "Choose a language:": "اختر لغة:",
                "Apply": "تطبيق", "Close": "إغلاق", "Log Name": "اسم السجل", "Event ID": "معرف الحدث",
                "Event Source": "مصدر الحدث", "Creation Time": "وقت الإنشاء",
                "Matched Keyword": "الكلمة المفتاحية المطابقة",
                "Time since analysis start": "الوقت منذ بداية التحليل", "Severity Level": "مستوى الخطورة",
                "Message": "الرسالة", "Analysis Status": "حالة التحليل",
                "Please specify at least one Log Source.": "الرجاء تحديد مصدر سجل واحد على الأقل.",
                "Event ID must be a comma-separated list of numbers.": "يجب أن تكون معرفات الأحداث قائمة بأرقام مفصولة بفواصل.",
                "Time Range must be a positive number.": "يجب أن يكون النطاق الزمني رقمًا موجبًا.",
                "No logs found for the given criteria.": "لم يتم العثور على سجلات للمعايير المحددة.",
                "No rows selected to export.": "لم يتم تحديد أي صفوف للتصدير.",
                "Show Full Details": "عرض السجل الكامل", "Isolate Log": "عزل السجل",
                "Export Selected Record": "تصدير السجل المحدد",
                "High": "مرتفع", "Medium": "متوسط", "منخفض": "منخفض", "Log Details": "تفاصيل السجل",
                "Security log access denied. Please run as Administrator.": "تم رفض الوصول إلى سجل الأمان. يرجى التشغيل كمسؤول.",
                "Error reading log '{}': {}": "خطأ في قراءة السجل '{}': {}",
                "An unexpected error occurred: {}": "حدث خطأ غير متوقع: {}",
                "Failed to open log '{}': {}": "فشل فتح السجل '{}': {}",
                "Load from file...": "تحميل من ملف...", "Select a keyword file": "اختر ملف كلمات مفتاحية",
                "Text Files (*.txt)": "ملفات نصية (*.txt)", "Error loading file.": "خطأ في تحميل الملف.",
                "The file is empty.": "الملف فارغ.",
                "Restart Application": "يرجى إعادة تشغيل التطبيق لتطبيق جميع تغييرات اللغة.",
                "Failed to retrieve log details. Please try again.": "فشل استرداد تفاصيل السجل. يرجى المحاولة مرة أخرى.",
                "Error: Failed to format event message.": "خطأ: فشل في تنسيق رسالة الحدث.",
                "Add": "إضافة", "Delete": "حذف",
                "Keyword Match Mode": "وضعية مطابقة الكلمات الرئيسية",
                "Exact Match": "مطابقة تامة",
                "Starts With": "بداية الكلمة",
                "Contains": "مطابقة عامة",
                "Add Keywords": "إضافة كلمات",
                "Delete Keywords": "حذف كلمات",
                "Add Log Source": "إضافة مصدر سجل",
                "Remove Log Source": "حذف مصدر سجل",
                "already exists.": "موجود بالفعل.",
                "Event Severity Distribution": "توزيع خطورة الأحداث",  # New
                "Count (events)": "العدد (أحداث)",  # New
                "Log Analyzer Report": "تقرير محلل السجلات",  # New
                "Show Reports": "عرض التقارير",  # New
                "Reports": "التقارير",  # New
                "Export to PDF": "تصدير إلى PDF",  # New
                "Export to XLSX": "تصدير إلى XLSX",  # New
                "Failed Logins Details": "تفاصيل تسجيلات الدخول الفاشلة",  # New
                "Successful Logins Details": "تفاصيل تسجيلات الدخول الناجحة",  # New
                "High Severity Details": "تفاصيل الخطورة العالية",  # New
                "Medium Severity Details": "تفاصيل الخطورة المتوسطة",  # New
                "Low Severity Details": "تفاصيل الخطورة المنخفضة",  # New
                "Error Details": "تفاصيل الأخطاء",  # New
                "Warning Details": "تفاصيل التحذيرات",  # New
                "Audit Success Details": "تفاصيل نجاح التدقيق",  # New
                "Audit Failure Details": "تفاصيل فشل التدقيق",  # New
                "No logs found for this category.": "لم يتم العثور على سجلات لهذه الفئة.",  # New
                "No keywords selected to delete.": "لم يتم تحديد أي كلمات مفتاحية للحذف.",  # New
                "Systemd Journal (Linux)": "سجل النظام (لينكس)",  # New
                "Common Log Files (Linux)": "ملفات السجلات الشائعة (لينكس)",  # New
                "Please run as root or with appropriate permissions to access logs.": "يرجى التشغيل كمسؤول (root) أو بصلاحيات مناسبة للوصول إلى السجلات.",
                # New
                "Failed to read log file '{}': {}": "فشل في قراءة ملف السجل '{}': {}",  # New
                "Unsupported log source type for Linux.": "نوع مصدر السجل غير مدعوم لنظام لينكس.",  # New
                "Log file '{}' not found or not readable.": "ملف السجل '{}' غير موجود أو غير قابل للقراءة.",  # New
            }
        }
        self.load_settings()

    def load_settings(self):
        self.language = self.settings.value("language", "ar")
        self.theme = self.settings.value("theme", "Dark")

    def save_settings(self, language, theme):
        self.settings.setValue("language", language)
        self.settings.setValue("theme", theme)
        self.language = language
        self.theme = theme

    def get_translation(self, text):
        return self.translations.get(self.language, {}).get(text, text)

    def apply_theme(self, app):
        if self.theme == "Dark":
            style = """
                QWidget { background-color: #212121; color: #e0e0e0; border-radius: 5px; }
                QMainWindow, QDialog { background-color: #121212; }
                QGroupBox { background-color: #1e1e1e; border: 1px solid #333; border-radius: 8px; margin-top: 20px; padding: 10px; }
                QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top center; padding: 0 10px; color: #88aaff; }
                QLineEdit, QComboBox, QPushButton, QListWidget { background-color: #333; color: #e0e0e0; border: 1px solid #555; padding: 5px; }
                QPushButton { background-color: #444; border-radius: 5px; }
                QPushButton:hover { background-color: #555; }
                QHeaderView::section { background-color: #333; color: #e0e0e0; padding: 5px; border: 1px solid #555; }
                QTableView { gridline-color: #444; }
                QStatusBar { background-color: #1e1e1e; color: #e0e0e0; }
                QMenu { background-color: #333; color: #e0e0e0; }
                QMenu::item:selected { background-color: #555; }
                QProgressBar { text-align: center; background-color: #333; color: #e0e0e0; border-radius: 5px; border: 1px solid #555; }
                QProgressBar::chunk { background-color: #88aaff; }
                QComboBox::drop-down { border: none; }
                QFrame { border: 1px solid #555; } /* Added for stat frames */
            """
        else:
            style = """
                QWidget { background-color: #f0f0f0; color: #333333; border-radius: 5px; }
                QMainWindow, QDialog { background-color: #ffffff; }
                QGroupBox { background-color: #e8e8e8; border: 1px solid #ccc; border-radius: 8px; margin-top: 20px; padding: 10px; }
                QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top center; padding: 0 10px; color: #007bff; }
                QLineEdit, QComboBox, QPushButton, QListWidget { background-color: #ffffff; color: #333333; border: 1px solid #ccc; padding: 5px; }
                QPushButton { background-color: #e0e0e0; border-radius: 5px; }
                QPushButton:hover { background-color: #d0d0d0; }
                QHeaderView::section { background-color: #e8e8e8; color: #333333; padding: 5px; border: 1px solid #ccc; }
                QTableView { gridline-color: #e0e0e0; }
                QStatusBar { background-color: #e8e8e8; color: #333333; }
                QMenu { background-color: #f8f8f8; color: #333333; }
                QMenu::item:selected { background-color: #e0e0e0; }
                QProgressBar { text-align: center; background-color: #f0f0f0; color: #333333; border-radius: 5px; border: 1px solid #ccc; }
                QProgressBar::chunk { background-color: #007bff; }
                QComboBox::drop-down { border: none; }
                QFrame { border: 1px solid #ccc; } /* Added for stat frames */
            """
        app.setStyleSheet(style)


settings_manager = SettingsManager()


class LogDataModel(QAbstractTableModel):
    def __init__(self, data=None):
        super(LogDataModel, self).__init__()
        self._data = data or []
        self._headers = self.get_translated_headers()
        self._severity_colors = {
            "High": QColor(255, 69, 58), "Medium": QColor(255, 159, 10), "Low": QColor(48, 209, 88),
            "Error": QColor(255, 69, 58), "Warning": QColor(255, 159, 10), "Information": QColor(48, 209, 88),
            "Success": QColor(48, 209, 88), "Failure": QColor(255, 69, 58),  # Added for Linux syslog
            "AuditSuccess": QColor(48, 209, 88), "AuditFailure": QColor(255, 69, 58),
            "مرتفع": QColor(255, 69, 58), "متوسط": QColor(255, 159, 10), "منخفض": QColor(48, 209, 88),
            "خطأ": QColor(255, 69, 58), "تحذير": QColor(255, 159, 10), "معلومات": QColor(48, 209, 88),
            "نجاح": QColor(48, 209, 88), "فشل": QColor(255, 69, 58),  # Added for Linux syslog
            "نجاح التدقيق": QColor(48, 209, 88), "فشل التدقيق": QColor(255, 69, 58),
        }

    def get_translated_headers(self):
        return [
            settings_manager.get_translation("Log Name"), settings_manager.get_translation("Event ID"),
            settings_manager.get_translation("Event Source"), settings_manager.get_translation("Creation Time"),
            settings_manager.get_translation("Matched Keyword"),
            settings_manager.get_translation("Time since analysis start"),
            settings_manager.get_translation("Severity Level"), settings_manager.get_translation("Message")
        ]

    def set_data(self, data):
        self.beginResetModel()
        self._data = data
        self.endResetModel()

    def rowCount(self, parent=None):
        return len(self._data)

    def columnCount(self, parent=None):
        return len(self._headers)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return QVariant()
        row, col = index.row(), index.column()
        if row < len(self._data) and col < len(self._data[row]):
            value = self._data[row][col]
            if col == self._headers.index(settings_manager.get_translation("Severity Level")):
                if role == Qt.ItemDataRole.BackgroundRole:
                    severity_text = self.data(index, role=Qt.ItemDataRole.DisplayRole)
                    return QVariant(self._severity_colors.get(severity_text, QColor(255, 255, 255)))
                if role == Qt.ItemDataRole.ForegroundRole:
                    return QVariant(QColor(0, 0, 0))
            if role == Qt.ItemDataRole.DisplayRole:
                if isinstance(value, datetime):
                    return value.strftime("%Y-%m-%d %H:%M:%S")
                if isinstance(value, timedelta):
                    total_seconds = int(value.total_seconds())
                    hours, remainder = divmod(total_seconds, 3600)
                    minutes, seconds = divmod(remainder, 60)
                    return f"{hours}h {minutes}m {seconds}s"
                return str(value)
        return QVariant()

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            if section < len(self._headers):
                return self._headers[section]
        return QVariant()

    def update_headers(self):
        self._headers = self.get_translated_headers()
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, len(self._headers) - 1)

    def sort(self, column, order):
        self.layoutAboutToBeChanged.emit()
        reverse = order == Qt.SortOrder.DescendingOrder
        self._data.sort(key=lambda item: item[column], reverse=reverse)
        self.layoutChanged.emit()


# --- Log Reader Classes (OS-Agnostic Interface) ---

class BaseLogReader:
    def __init__(self, log_source, time_limit):
        self.log_source = log_source
        self.time_limit = time_limit
        self._is_running = True

    def stop(self):
        self._is_running = False

    def read_events(self, progress_callback, error_callback):
        raise NotImplementedError("Subclasses must implement read_events")

    def get_total_records(self):
        return 0  # Default, can be overridden


class WindowsLogReader(BaseLogReader):
    def __init__(self, log_source, time_limit):
        super().__init__(log_source, time_limit)
        self.log_handle = None

    def get_total_records(self):
        try:
            hand = win32evtlog.OpenEventLog(None, self.log_source)
            total = win32evtlog.GetNumberOfEventLogRecords(hand)
            win32evtlog.CloseEventLog(hand)
            return total
        except pywintypes.error as e:
            if e.winerror == 5 and self.log_source.lower() == 'security':
                raise Exception(
                    settings_manager.get_translation("Security log access denied. Please run as Administrator."))
            else:
                raise Exception(
                    settings_manager.get_translation("Error reading log '{}': {}").format(self.log_source, e))
        except Exception as e:
            raise Exception(settings_manager.get_translation("An unexpected error occurred: {}").format(e))

    def read_events(self, progress_callback, error_callback):
        events_read = []
        try:
            if self.log_source.lower() == 'security':
                try:
                    h_proc = win32api.GetCurrentProcess()
                    h_token = win32security.OpenProcessToken(h_proc,
                                                             win32con.TOKEN_ADJUST_PRIVILEGES | win32con.TOKEN_QUERY)
                    privilege_id = win32security.LookupPrivilegeValue(None, "SeSecurityPrivilege")
                    win32security.AdjustTokenPrivileges(h_token, False,
                                                        [(privilege_id, win32con.SE_PRIVILEGE_ENABLED)])
                except Exception:
                    pass  # Best effort, will fail later if permissions are truly missing

            self.log_handle = win32evtlog.OpenEventLog(None, self.log_source)
            flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
            events = 1
            while events and self._is_running:
                events = win32evtlog.ReadEventLog(self.log_handle, flags, 0, 1000)
                if not events:
                    break
                for event in events:
                    if not self._is_running:
                        break
                    event_time = event.TimeGenerated.replace(tzinfo=None)
                    if event_time < self.time_limit:
                        progress_callback()  # Still count towards progress even if skipped
                        continue  # Skip events older than time limit

                    try:
                        msg = win32evtlogutil.SafeFormatMessage(event, self.log_source)
                        message = msg.replace("\r\n", " ").strip()
                    except (pywintypes.error, Exception):
                        message = settings_manager.get_translation("Error: Failed to format event message.")

                    events_read.append({
                        'log_name': self.log_source,
                        'event_id': event.EventID & 0xFFFF,
                        'source_name': event.SourceName,
                        'creation_time': event_time,
                        'event_type': event.EventType,  # Windows specific type
                        'message': message
                    })
                    progress_callback()
        except pywintypes.error as e:
            error_callback(settings_manager.get_translation("Error reading log '{}': {}").format(self.log_source, e))
        except Exception as e:
            error_callback(settings_manager.get_translation("An unexpected error occurred: {}").format(e))
        finally:
            if self.log_handle:
                win32evtlog.CloseEventLog(self.log_handle)
                self.log_handle = None
        return events_read


class LinuxJournalLogReader(BaseLogReader):
    def __init__(self, log_source, time_limit):
        super().__init__(log_source, time_limit)
        self.reader = None

    def get_total_records(self):
        # systemd.journal doesn't provide a direct count easily without iterating.
        # Return a placeholder or estimate.
        return 100000  # Arbitrary large number for progress bar estimation

    def read_events(self, progress_callback, error_callback):
        events_read = []
        try:
            if not journal:
                error_callback("systemd.journal library not available. Cannot read journal logs.")
                return []

            self.reader = journal.Reader()
            # Seek to the beginning of the time range
            self.reader.seek_realtime(self.time_limit)

            # Map journal priorities to our severity levels
            # LOG_EMERG (0), LOG_ALERT (1), LOG_CRIT (2), LOG_ERR (3), LOG_WARNING (4),
            # LOG_NOTICE (5), LOG_INFO (6), LOG_DEBUG (7)
            priority_map = {
                0: settings_manager.get_translation("High"),  # EMERG
                1: settings_manager.get_translation("High"),  # ALERT
                2: settings_manager.get_translation("High"),  # CRIT
                3: settings_manager.get_translation("Error"),  # ERR
                4: settings_manager.get_translation("Warning"),  # WARNING
                5: settings_manager.get_translation("Information"),  # NOTICE
                6: settings_manager.get_translation("Information"),  # INFO
                7: settings_manager.get_translation("Low"),  # DEBUG
            }

            for entry in self.reader:
                if not self._is_running:
                    break

                # Journal entries have __REALTIME_TIMESTAMP in microseconds
                entry_time_us = int(entry.get('__REALTIME_TIMESTAMP', 0))
                if entry_time_us == 0:
                    progress_callback()
                    continue  # Skip entries without a timestamp

                entry_time = datetime.fromtimestamp(entry_time_us / 1000000)

                if entry_time < self.time_limit:
                    progress_callback()
                    continue  # Should already be handled by seek_realtime, but double check

                message = entry.get('MESSAGE', 'N/A')
                event_id = entry.get('_AUDIT_ID', entry.get('CODE', 'N/A'))  # Try to get an ID
                source_name = entry.get('_COMM', entry.get('_EXE', 'N/A'))  # Command or executable

                # Determine severity based on PRIORITY
                priority = entry.get('PRIORITY', 6)  # Default to INFO if not set
                severity_level = priority_map.get(priority, settings_manager.get_translation("Information"))

                events_read.append({
                    'log_name': "Systemd Journal",
                    'event_id': event_id,
                    'source_name': source_name,
                    'creation_time': entry_time,
                    'event_type': severity_level,  # Using mapped severity as event_type for consistency
                    'message': message
                })
                progress_callback()

        except PermissionError:
            error_callback(
                settings_manager.get_translation("Please run as root or with appropriate permissions to access logs."))
        except Exception as e:
            error_callback(settings_manager.get_translation("Error reading log '{}': {}").format(self.log_source, e))
        finally:
            if self.reader:
                self.reader.close()
                self.reader = None
        return events_read


class LinuxFileLogReader(BaseLogReader):
    def __init__(self, log_source, time_limit):
        super().__init__(log_source, time_limit)

    def get_total_records(self):
        # Cannot reliably get total records for a file without reading it all.
        # Return a placeholder or estimate.
        return 10000  # Arbitrary large number for progress bar estimation

    def read_events(self, progress_callback, error_callback):
        events_read = []
        try:
            if not os.path.exists(self.log_source) or not os.access(self.log_source, os.R_OK):
                error_callback(settings_manager.get_translation("Log file '{}' not found or not readable.").format(
                    self.log_source))
                return []

            with open(self.log_source, 'r', errors='ignore') as f:
                for line in f:
                    if not self._is_running:
                        break
                    # Basic syslog parsing (very simplified)
                    # Example format: "Aug 20 01:05:39 hostname program: message"
                    try:
                        parts = line.strip().split(' ', 5)  # Split by space, max 5 times
                        if len(parts) < 5:
                            progress_callback()
                            continue  # Not a standard syslog line

                        # Attempt to parse timestamp (e.g., "Aug 20 01:05:39")
                        # This is highly dependent on the year, which is often missing in syslog
                        # For simplicity, assume current year if not present.
                        try:
                            timestamp_str = f"{parts[0]} {parts[1]} {parts[2]}"
                            # Add current year to parse correctly
                            current_year = datetime.now().year
                            creation_time = datetime.strptime(f"{timestamp_str} {current_year}", "%b %d %H:%M:%S %Y")
                            # Adjust year if the month/day combination implies previous year
                            if creation_time > datetime.now() and creation_time.month > datetime.now().month:
                                creation_time = creation_time.replace(year=current_year - 1)
                        except ValueError:
                            creation_time = datetime.now()  # Fallback if parsing fails

                        if creation_time < self.time_limit:
                            progress_callback()
                            continue

                        source_name = parts[3].rstrip(':') if len(parts) > 3 else 'N/A'
                        message = parts[5] if len(parts) > 5 else line.strip()

                        # Basic severity inference (very crude)
                        severity_level = settings_manager.get_translation("Information")
                        message_lower = message.lower()
                        if "error" in message_lower or "fail" in message_lower or "denied" in message_lower:
                            severity_level = settings_manager.get_translation("Error")
                        elif "warn" in message_lower:
                            severity_level = settings_manager.get_translation("Warning")
                        elif "success" in message_lower or "accepted" in message_lower:
                            severity_level = settings_manager.get_translation("Success")
                        elif "failure" in message_lower or "failed" in message_lower:
                            severity_level = settings_manager.get_translation("Failure")

                        events_read.append({
                            'log_name': self.log_source,
                            'event_id': 'N/A',  # File logs often don't have explicit event IDs
                            'source_name': source_name,
                            'creation_time': creation_time,
                            'event_type': severity_level,
                            'message': message
                        })
                        progress_callback()

                    except Exception as e:
                        # Skip lines that can't be parsed, but log the error
                        # error_callback(f"Failed to parse log line in '{self.log_source}': {line.strip()} - {e}")
                        pass  # Suppress line-level parsing errors for cleaner output

        except PermissionError:
            error_callback(
                settings_manager.get_translation("Please run as root or with appropriate permissions to access logs."))
        except Exception as e:
            error_callback(
                settings_manager.get_translation("Failed to read log file '{}': {}").format(self.log_source, e))
        return events_read


class LogAnalyzerThread(QThread):
    finished_signal = pyqtSignal(list, int, dict)
    progress_signal = pyqtSignal(int, int)
    status_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(self, log_sources, keywords_include, keywords_include_mode, keywords_exclude, time_range,
                 severity_levels, event_ids):
        super().__init__()
        self.log_sources = log_sources  # List of log sources
        self.keywords_include = [k.lower() for k in keywords_include]
        self.keywords_include_mode = keywords_include_mode  # 'exact', 'startswith', 'contains'
        self.keywords_exclude = [k.lower() for k in keywords_exclude]
        self.time_range = time_range
        self.severity_levels = severity_levels
        self._is_running = True
        self.custom_severity_map = {
            # Windows specific mappings
            ('System', 6008): 'High', ('System', 41): 'High', ('System', 7036): 'Medium',
            ('Application', 1000): 'Medium', ('Security', 4625): 'High', ('Security', 4720): 'High',
            ('Security', 4726): 'High', ('Security', 4732): 'High', ('Security', 4740): 'High',
            ('Security', 4672): 'High', ('Security', 1102): 'High', ('Security', 4624): 'Medium',
            ('Security', 4722): 'Medium', ('Security', 4725): 'Medium', ('Security', 4724): 'Medium',
        }
        # Windows Event Log Types
        if IS_WINDOWS:
            self.win_event_type_map = {
                win32evtlog.EVENTLOG_ERROR_TYPE: settings_manager.get_translation("Error"),
                win32evtlog.EVENTLOG_WARNING_TYPE: settings_manager.get_translation("Warning"),
                win32evtlog.EVENTLOG_INFORMATION_TYPE: settings_manager.get_translation("Information"),
                win32evtlog.EVENTLOG_AUDIT_SUCCESS: settings_manager.get_translation("AuditSuccess"),
                win32evtlog.EVENTLOG_AUDIT_FAILURE: settings_manager.get_translation("AuditFailure"),
            }

        # Parse event_ids once
        self.event_ids = []
        if event_ids:
            try:
                self.event_ids = [int(i) for i in event_ids if str(i).strip().isdigit()]
            except ValueError:
                # This should ideally be caught in main window, but as a safeguard
                self.error_signal.emit(
                    settings_manager.get_translation("Event ID must be a comma-separated list of numbers."))

    def get_severity_level(self, log_source_name, event_type_or_priority, event_id_val=None):
        # Check custom mappings first (primarily for Windows)
        if IS_WINDOWS and event_id_val is not None:
            custom_level = self.custom_severity_map.get((log_source_name, event_id_val))
            if custom_level:
                return settings_manager.get_translation(custom_level)

        if IS_WINDOWS:
            # Map Windows event types
            return self.win_event_type_map.get(event_type_or_priority, settings_manager.get_translation('Low'))
        elif IS_LINUX:
            # For Linux, event_type_or_priority is already the mapped severity string from the reader
            return event_type_or_priority
        return settings_manager.get_translation('Information')  # Default fallback

    def matches_include_keywords(self, message_lower):
        # إذا لم يتم تحديد كلمات، نعتبر كل الرسائل مطابقة
        if not self.keywords_include:
            return True, ""

        for keyword in self.keywords_include:
            if self.keywords_include_mode == 'exact':
                # Use regex with word boundaries for exact word match
                # \b matches a word boundary. re.escape handles special characters in keyword.
                pattern = r'\b{}\b'.format(re.escape(keyword))
                if re.search(pattern, message_lower):
                    return True, keyword
            elif self.keywords_include_mode == 'startswith':
                # Check if any word in the message starts with the keyword
                # \b matches a word boundary, \w* matches zero or more word characters (letters, numbers, underscore)
                pattern = r'\b{}\w*'.format(re.escape(keyword))
                if re.search(pattern, message_lower):
                    return True, keyword
            else:  # 'contains'
                if keyword in message_lower:
                    return True, keyword
        return False, ""

    def run(self):
        start_time_limit = datetime.now() - timedelta(hours=self.time_range)
        all_results = []
        overall_stats = {
            'failed_logins': 0,
            'successful_logins': 0,
            'severity_counts': {
                settings_manager.get_translation("High"): 0,
                settings_manager.get_translation("Medium"): 0,
                settings_manager.get_translation("Low"): 0,
                settings_manager.get_translation("Error"): 0,
                settings_manager.get_translation("Warning"): 0,
                settings_manager.get_translation("Information"): 0,
            },
            'events_by_category': {
                'failed_logins': [],
                'successful_logins': [],
                settings_manager.get_translation("High"): [],
                settings_manager.get_translation("Medium"): [],
                settings_manager.get_translation("Low"): [],
                settings_manager.get_translation("Error"): [],
                settings_manager.get_translation("Warning"): [],
                settings_manager.get_translation("Information"): [],
            }
        }
        if IS_WINDOWS:
            overall_stats['severity_counts'][settings_manager.get_translation("AuditSuccess")] = 0
            overall_stats['severity_counts'][settings_manager.get_translation("AuditFailure")] = 0
            overall_stats['events_by_category'][settings_manager.get_translation("AuditSuccess")] = []
            overall_stats['events_by_category'][settings_manager.get_translation("AuditFailure")] = []
        elif IS_LINUX:
            overall_stats['severity_counts'][settings_manager.get_translation("Success")] = 0
            overall_stats['severity_counts'][settings_manager.get_translation("Failure")] = 0
            overall_stats['events_by_category'][settings_manager.get_translation("Success")] = []
            overall_stats['events_by_category'][settings_manager.get_translation("Failure")] = []

        total_records_to_process = 0
        log_readers = []

        # Determine total records and initialize readers
        for log_source in self.log_sources:
            if not self._is_running:
                break
            try:
                reader = None
                if IS_WINDOWS:
                    reader = WindowsLogReader(log_source, start_time_limit)
                elif IS_LINUX:
                    if log_source == settings_manager.get_translation("Systemd Journal (Linux)"):
                        reader = LinuxJournalLogReader(log_source, start_time_limit)
                    elif log_source == settings_manager.get_translation("Common Log Files (Linux)"):
                        # This is a placeholder, user should select specific files
                        self.error_signal.emit(settings_manager.get_translation(
                            "Please select specific log files or 'Systemd Journal (Linux)'. 'Common Log Files (Linux)' is a category, not a source."))
                        continue
                    elif os.path.exists(log_source) and os.path.isfile(log_source):  # Assume it's a file path
                        reader = LinuxFileLogReader(log_source, start_time_limit)
                    else:
                        self.error_signal.emit(
                            settings_manager.get_translation("Log file '{}' not found or not readable.").format(
                                log_source))
                        continue  # Skip this log source

                if reader:
                    log_readers.append(reader)
                    total_records_to_process += reader.get_total_records()
            except Exception as e:
                self.error_signal.emit(str(e))
                continue

        if not log_readers and self._is_running:
            self.finished_signal.emit([], 0, overall_stats)
            return

        processed_records_count = 0

        def update_progress_callback():
            nonlocal processed_records_count
            processed_records_count += 1
            self.progress_signal.emit(processed_records_count, total_records_to_process)

        for reader in log_readers:
            if not self._is_running:
                break

            self.status_signal.emit(f"{settings_manager.get_translation('Analyzing logs...')} ({reader.log_source})")

            try:
                events_from_reader = reader.read_events(update_progress_callback, self.error_signal.emit)
            except Exception as e:
                self.error_signal.emit(str(e))
                continue

            for event_data_raw in events_from_reader:
                if not self._is_running:
                    break

                log_name = event_data_raw['log_name']
                event_id_val = event_data_raw['event_id']
                source_name = event_data_raw['source_name']
                creation_time = event_data_raw['creation_time']
                message = event_data_raw['message']
                event_type_or_priority = event_data_raw['event_type']  # This is the raw type/priority from OS

                # Apply severity mapping
                severity_level = self.get_severity_level(log_name, event_type_or_priority, event_id_val)

                # Keyword filtering
                message_lower = message.lower()
                matched_keyword = ""
                is_match, matched_keyword = self.matches_include_keywords(message_lower)

                if is_match and self.keywords_exclude:
                    for keyword in self.keywords_exclude:
                        if keyword in message_lower:
                            is_match = False
                            break

                if not is_match:
                    continue

                # Event ID filtering (only if event_id_val is a number)
                if self.event_ids and isinstance(event_id_val, (int, float)):
                    if event_id_val not in self.event_ids:
                        continue

                # Severity level filtering
                desired_severities = self.severity_levels
                if desired_severities:
                    # Create a set of *actual* severities to allow based on user selection
                    allowed_actual_severities = set()
                    if settings_manager.get_translation("Error") in desired_severities:
                        allowed_actual_severities.add(settings_manager.get_translation("Error"))
                    if settings_manager.get_translation("Warning") in desired_severities:
                        allowed_actual_severities.add(settings_manager.get_translation("Warning"))
                    if settings_manager.get_translation("Information") in desired_severities:
                        allowed_actual_severities.add(settings_manager.get_translation("Information"))
                        allowed_actual_severities.add(settings_manager.get_translation("Low"))
                        allowed_actual_severities.add(settings_manager.get_translation("Medium"))
                        allowed_actual_severities.add(settings_manager.get_translation("High"))

                    if IS_WINDOWS:
                        if settings_manager.get_translation("AuditSuccess") in desired_severities:
                            allowed_actual_severities.add(settings_manager.get_translation("AuditSuccess"))
                        if settings_manager.get_translation("AuditFailure") in desired_severities:
                            allowed_actual_severities.add(settings_manager.get_translation("AuditFailure"))
                    elif IS_LINUX:
                        if settings_manager.get_translation("Success") in desired_severities:
                            allowed_actual_severities.add(settings_manager.get_translation("Success"))
                        if settings_manager.get_translation("Failure") in desired_severities:
                            allowed_actual_severities.add(settings_manager.get_translation("Failure"))

                    if severity_level not in allowed_actual_severities:
                        continue  # Skip if severity not allowed

                # Construct the final event data for display
                event_data_for_display = [
                    log_name, event_id_val, source_name, creation_time,
                    matched_keyword, datetime.now() - creation_time,
                    severity_level, message
                ]

                # Update overall stats
                if severity_level in overall_stats['severity_counts']:
                    overall_stats['severity_counts'][severity_level] += 1
                    overall_stats['events_by_category'][severity_level].append(event_data_for_display)

                # Specific login event tracking (Windows Event IDs and Linux keyword-based)
                if IS_WINDOWS:
                    if log_name.lower() == 'security':
                        if event_id_val == 4625:  # Failed login
                            overall_stats['failed_logins'] += 1
                            overall_stats['events_by_category']['failed_logins'].append(event_data_for_display)
                        elif event_id_val == 4624:  # Successful login
                            overall_stats['successful_logins'] += 1
                            overall_stats['events_by_category']['successful_logins'].append(event_data_for_display)
                elif IS_LINUX:
                    if "failed password" in message_lower or "authentication failure" in message_lower or "failed to authenticate" in message_lower:
                        overall_stats['failed_logins'] += 1
                        overall_stats['events_by_category']['failed_logins'].append(event_data_for_display)
                    elif "accepted password" in message_lower or "authentication success" in message_lower or "logged in" in message_lower:
                        overall_stats['successful_logins'] += 1
                        overall_stats['events_by_category']['successful_logins'].append(event_data_for_display)

                all_results.append(event_data_for_display)

        for reader in log_readers:
            reader.stop()  # Ensure all readers are stopped

        self.finished_signal.emit(all_results, len(all_results), overall_stats)

    def stop(self):
        self._is_running = False


class StatsDetailsDialog(QDialog):
    def __init__(self, parent=None, data=None, title=None):
        super().__init__(parent)
        self.setWindowTitle(title or settings_manager.get_translation("Log Details"))
        self.resize(900, 600)
        layout = QVBoxLayout(self)
        self.table_view = QTableView()
        self.table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self.show_context_menu)
        self.model = LogDataModel(data)
        self.table_view.setModel(self.model)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_view.setSortingEnabled(True)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(self.table_view)

        btn_layout = QHBoxLayout()
        export_pdf_btn = QPushButton(settings_manager.get_translation("Export to PDF"))
        export_pdf_btn.clicked.connect(self.export_all_to_pdf)
        export_xlsx_btn = QPushButton(settings_manager.get_translation("Export to XLSX"))
        export_xlsx_btn.clicked.connect(self.export_all_to_xlsx)
        btn_layout.addWidget(export_pdf_btn)
        btn_layout.addWidget(export_xlsx_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        close_btn = QPushButton(settings_manager.get_translation("Close"))
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

    def show_context_menu(self, position):
        menu = QMenu(self)
        show_details_action = QAction(settings_manager.get_translation("Show Full Details"), self)
        show_details_action.triggered.connect(self.show_full_record)
        menu.addAction(show_details_action)

        export_pdf_action = QAction(settings_manager.get_translation("Export Selected Record") + " (PDF)", self)
        export_pdf_action.triggered.connect(self.export_selected_record_pdf)
        menu.addAction(export_pdf_action)

        export_xlsx_action = QAction(settings_manager.get_translation("Export Selected Record") + " (XLSX)", self)
        export_xlsx_action.triggered.connect(self.export_selected_record_xlsx)
        menu.addAction(export_xlsx_action)

        menu.exec(self.table_view.viewport().mapToGlobal(position))

    def show_full_record(self):
        selected_rows = self.table_view.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, settings_manager.get_translation("Warning"),
                                settings_manager.get_translation("No rows selected to export."))
            return
        try:
            row_data = self.model._data[selected_rows[0].row()]
            headers = self.model.get_translated_headers()
            log_details_dict = dict(zip(headers, row_data))
            dialog = LogDetailsDialog(self, log_data=log_details_dict)
            dialog.exec()
        except IndexError:
            QMessageBox.critical(self, settings_manager.get_translation("Error"),
                                 settings_manager.get_translation("Failed to retrieve log details. Please try again."))

    def export_selected_record_pdf(self):
        selected_rows = self.table_view.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, settings_manager.get_translation("Warning"),
                                settings_manager.get_translation("No rows selected to export."))
            return
        selected_data = [self.model._data[index.row()] for index in selected_rows]
        self._export_pdf(selected_data)

    def export_selected_record_xlsx(self):
        selected_rows = self.table_view.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, settings_manager.get_translation("Warning"),
                                settings_manager.get_translation("No rows selected to export."))
            return
        selected_data = [self.model._data[index.row()] for index in selected_rows]
        self._export_xlsx(selected_data)

    def export_all_to_pdf(self):
        self._export_pdf(self.model._data)

    def export_all_to_xlsx(self):
        self._export_xlsx(self.model._data)

    def _export_pdf(self, data_to_export):
        file_path, _ = QFileDialog.getSaveFileName(self, settings_manager.get_translation("Export to PDF"),
                                                   "report.pdf", "PDF Files (*.pdf)")
        if not file_path:
            return
        try:
            c = canvas.Canvas(file_path, pagesize=letter)
            width, height = letter
            styles = getSampleStyleSheet()
            styleN = styles["Normal"]
            styleN.fontName = "ArialUnicodeMS"
            c.setFont("ArialUnicodeMS", 16)
            header_text = settings_manager.get_translation("Log Analyzer Report")
            reshaped_header = arabic_reshaper.reshape(header_text)
            bidi_header = get_display(reshaped_header)
            c.drawRightString(width - 30, height - 40, bidi_header)
            y_position = height - 70
            for row in data_to_export:
                record_lines = []
                for header, cell in zip(self.model.get_translated_headers(), row):
                    if isinstance(cell, datetime):
                        cell_str = cell.strftime("%Y-%m-%d %H:%M:%S")
                    elif isinstance(cell, timedelta):
                        total_seconds = int(cell.total_seconds())
                        hours, remainder = divmod(total_seconds, 3600)
                        minutes, seconds = divmod(remainder, 60)
                        cell_str = f"{hours}h {minutes}m {seconds}s"
                    else:
                        cell_str = str(cell)

                    reshaped_header = arabic_reshaper.reshape(header)
                    bidi_header = get_display(reshaped_header)

                    reshaped_cell = arabic_reshaper.reshape(cell_str)
                    bidi_cell = get_display(reshaped_cell)

                    line = f'<b>{bidi_header}:</b> {bidi_cell}'
                    record_lines.append(line)

                record_text = "<br/>".join(record_lines)
                para = Paragraph(record_text, styleN)
                available_width = width - 60
                w, h_taken = para.wrapOn(c, available_width, y_position)

                if y_position - h_taken < 50:
                    c.showPage()
                    c.setFont("ArialUnicodeMS", 12)
                    y_position = height - 50

                para.drawOn(c, 30, y_position - h_taken)
                y_position -= (h_taken + 20)
                c.line(30, y_position + 10, width - 30, y_position + 10)

                if y_position < 50:
                    c.showPage()
                    c.setFont("ArialUnicodeMS", 12)
                    y_position = height - 50

            c.save()
            QMessageBox.information(self, settings_manager.get_translation("Success"),
                                    settings_manager.get_translation("Export successful."))
        except Exception as e:
            QMessageBox.critical(self, settings_manager.get_translation("Error"),
                                 f"{settings_manager.get_translation('Failed to export results.')}\n{str(e)}")

    def _export_xlsx(self, data_to_export):
        file_path, _ = QFileDialog.getSaveFileName(self, settings_manager.get_translation("Export to XLSX"),
                                                   "report.xlsx", "Excel Files (*.xlsx)")
        if not file_path:
            return
        try:
            headers = self.model.get_translated_headers()
            rows = []
            for row in data_to_export:
                formatted_row = []
                for cell in row:
                    if isinstance(cell, datetime):
                        formatted_row.append(cell.strftime("%Y-%m-%d %H:%M:%S"))
                    elif isinstance(cell, timedelta):
                        total_seconds = int(cell.total_seconds())
                        hours, remainder = divmod(total_seconds, 3600)
                        minutes, seconds = divmod(remainder, 60)
                        formatted_row.append(f"{hours}h {minutes}m {seconds}s")
                    else:
                        formatted_row.append(str(cell))
                rows.append(formatted_row)
            df = pd.DataFrame(rows, columns=headers)
            df.to_excel(file_path, index=False)
            QMessageBox.information(self, settings_manager.get_translation("Success"),
                                    settings_manager.get_translation("Export successful."))
        except Exception as e:
            QMessageBox.critical(self, settings_manager.get_translation("Error"),
                                 f"{settings_manager.get_translation('Failed to export results.')}\n{str(e)}")


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.setWindowTitle(settings_manager.get_translation("Settings Dialog"))
        self.setGeometry(200, 200, 300, 150)
        layout = QVBoxLayout(self)
        theme_group = QGroupBox(settings_manager.get_translation("Choose a theme:"))
        theme_layout = QHBoxLayout()
        self.dark_radio = QCheckBox(settings_manager.get_translation("Dark"))
        self.light_radio = QCheckBox(settings_manager.get_translation("Light"))
        theme_layout.addWidget(self.dark_radio)
        theme_layout.addWidget(self.light_radio)
        theme_group.setLayout(theme_layout)
        layout.addWidget(theme_group)
        lang_group = QGroupBox(settings_manager.get_translation("Choose a language:"))
        lang_layout = QHBoxLayout()
        self.english_radio = QCheckBox(settings_manager.get_translation("English"))
        self.arabic_radio = QCheckBox(settings_manager.get_translation("Arabic"))
        lang_layout.addWidget(self.english_radio)
        lang_layout.addWidget(self.arabic_radio)
        lang_group.setLayout(lang_layout)
        layout.addWidget(lang_group)
        btn_layout = QHBoxLayout()
        self.apply_btn = QPushButton(settings_manager.get_translation("Apply"))
        self.close_btn = QPushButton(settings_manager.get_translation("Close"))
        btn_layout.addWidget(self.apply_btn)
        btn_layout.addWidget(self.close_btn)
        layout.addLayout(btn_layout)
        if settings_manager.theme == "Dark":
            self.dark_radio.setChecked(True)
        else:
            self.light_radio.setChecked(True)
        if settings_manager.language == "en":
            self.english_radio.setChecked(True)
        else:
            self.arabic_radio.setChecked(True)
        self.apply_btn.clicked.connect(self.apply_settings)
        self.close_btn.clicked.connect(self.close)

    def apply_settings(self):
        selected_theme = "Dark" if self.dark_radio.isChecked() else "Light"
        selected_language = "en" if self.english_radio.isChecked() else "ar"
        if selected_theme != settings_manager.theme or selected_language != settings_manager.language:
            settings_manager.save_settings(selected_language, selected_theme)
            settings_manager.apply_theme(QApplication.instance())
            self.parent_window.retranslateUi()
            if selected_language == 'ar':
                self.parent_window.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
                self.parent_window.time_range_input.setAlignment(Qt.AlignmentFlag.AlignRight)
            else:
                self.parent_window.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
                self.parent_window.time_range_input.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.close()


class LogDetailsDialog(QDialog):
    def __init__(self, parent=None, log_data=None):
        super().__init__(parent)
        self.setWindowTitle(settings_manager.get_translation("Log Details"))
        self.setGeometry(100, 100, 600, 400)
        layout = QVBoxLayout(self)
        details_text = QTextEdit()
        details_text.setReadOnly(True)
        details_str = ""
        if log_data:
            for header, value in log_data.items():
                if isinstance(value, timedelta):
                    total_seconds = int(value.total_seconds())
                    hours, remainder = divmod(total_seconds, 3600)
                    minutes, seconds = divmod(remainder, 60)
                    value_str = f"{hours}h {minutes}m {seconds}s"
                elif isinstance(value, datetime):
                    value_str = value.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    value_str = str(value)
                details_str += f"<b>{header}:</b> {value_str}<br>"
        details_text.setHtml(details_str)
        layout.addWidget(details_text)
        close_btn = QPushButton(settings_manager.get_translation("Close"))
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(settings_manager.get_translation("Log Analyzer"))
        self.resize(1200, 800)
        self.setMinimumSize(1000, 700)
        icon_path = "icons/logo.png"  # Assuming an icons folder exists
        if not QPixmap(icon_path).isNull():
            self.setWindowIcon(QIcon(QPixmap(icon_path)))
        self.log_analyzer_thread = None
        self.current_analysis_stats = {}  # لتخزين إحصائيات التحليل الحالية
        self.create_menu()
        self.create_status_bar()
        self.setup_ui()
        self.setup_connections()
        self.load_persistent_lists()

    def create_menu(self):
        self.menu_bar = self.menuBar()
        self.retranslateMenu()

    def retranslateMenu(self):
        self.menu_bar.clear()
        file_menu = self.menu_bar.addMenu(settings_manager.get_translation("File"))
        self.export_action = QAction(settings_manager.get_translation("Export Results"), self)
        self.export_action.triggered.connect(self.export_all_results)
        file_menu.addAction(self.export_action)
        self.export_selected_action = QAction(settings_manager.get_translation("Export Selected Results"), self)
        self.export_selected_action.triggered.connect(self.export_selected_results)
        file_menu.addAction(self.export_selected_action)
        self.exit_action = QAction(settings_manager.get_translation("Exit"), self)
        self.exit_action.triggered.connect(self.close)
        file_menu.addAction(self.exit_action)

        settings_menu = self.menu_bar.addMenu(settings_manager.get_translation("Settings"))
        self.settings_action = QAction(settings_manager.get_translation("Settings"), self)
        self.settings_action.triggered.connect(self.show_settings_dialog)
        settings_menu.addAction(self.settings_action)
        self.reports_action = QAction(settings_manager.get_translation("Show Reports"), self)
        self.reports_action.triggered.connect(self.show_reports_dialog)
        self.menu_bar.addAction(self.reports_action)

    def show_reports_dialog(self):
        data = self.log_model._data
        headers = self.log_model.get_translated_headers()
        dialog = StatsDetailsDialog(self, data=data, title=settings_manager.get_translation("Reports"))
        dialog.exec()

    def create_status_bar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel(
            f"{settings_manager.get_translation('Status')} {settings_manager.get_translation('Ready')}")
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setVisible(False)
        self.status_bar.addWidget(self.status_label, 1)
        self.status_bar.addWidget(self.progress_bar)

    def _get_all_event_logs(self):
        log_names = []
        if IS_WINDOWS:
            key_path = r'SYSTEM\CurrentControlSet\Services\EventLog'
            try:
                hkey = win32api.RegOpenKey(win32con.HKEY_LOCAL_MACHINE, key_path, 0, win32con.KEY_READ)
                num_subkeys = win32api.RegQueryInfoKey(hkey)[0]

                for i in range(num_subkeys):
                    log_name = win32api.RegEnumKey(hkey, i)
                    log_handle = 0
                    try:
                        log_handle = win32evtlog.OpenEventLog(None, log_name)
                        if log_handle:
                            log_names.append(log_name)
                    except pywintypes.error:
                        pass
                    finally:
                        if log_handle:
                            win32evtlog.CloseEventLog(log_handle)

                win32api.RegCloseKey(hkey)

                if not log_names:
                    raise ValueError("No logs found dynamically")

            except Exception as e:
                print(f"خطأ أثناء القراءة الديناميكية للسجلات: {e}. العودة إلى القائمة الافتراضية.")
                return ["Application", "Security", "System"]
        elif IS_LINUX:
            # For Linux, provide common log sources. User can add more.
            # Systemd Journal is a special case that reads from the journal.
            log_names.append(settings_manager.get_translation("Systemd Journal (Linux)"))
            # Common log files (can be expanded)
            common_files = [
                "/var/log/syslog",
                "/var/log/auth.log",
                "/var/log/kern.log",
                "/var/log/daemon.log",
                "/var/log/messages",  # Common on RHEL/CentOS
                "/var/log/secure",  # Common on RHEL/CentOS for security
            ]
            for f in common_files:
                if os.path.exists(f):
                    log_names.append(f)

            # Add a placeholder for user to add custom paths
            # log_names.append(settings_manager.get_translation("Common Log Files (Linux)")) # This is just a label/hint

        log_names.sort()
        return log_names

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        v_splitter = QSplitter(Qt.Orientation.Vertical)

        top_splitter = QSplitter(Qt.Orientation.Horizontal)
        top_splitter.setHandleWidth(5)
        top_splitter.setChildrenCollapsible(False)

        self.input_group = QGroupBox(settings_manager.get_translation("Inputs"))
        input_layout = QGridLayout(self.input_group)

        # مصادر السجلات مع أزرار الإضافة والحذف على الجانب بحجم صغير
        self.log_sources_label = QLabel(settings_manager.get_translation("Log Sources"))
        self.log_sources_list_widget = QListWidget()
        self.log_sources_list_widget.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)

        all_logs = self._get_all_event_logs()
        self.log_sources_list_widget.addItems(all_logs)

        # Pre-select common logs based on OS
        if IS_WINDOWS:
            for log_name in ["Application", "System"]:
                items = self.log_sources_list_widget.findItems(log_name, Qt.MatchFlag.MatchFixedString)
                if items:
                    for item in items:
                        item.setSelected(True)
            # For Security log, don't auto-select due to permissions
        elif IS_LINUX:
            # Auto-select Systemd Journal if available
            journal_item = self.log_sources_list_widget.findItems(
                settings_manager.get_translation("Systemd Journal (Linux)"), Qt.MatchFlag.MatchFixedString)
            if journal_item:
                journal_item[0].setSelected(True)
            # Auto-select common log files if they exist
            for log_file in ["/var/log/syslog", "/var/log/auth.log"]:
                items = self.log_sources_list_widget.findItems(log_file, Qt.MatchFlag.MatchFixedString)
                if items:
                    for item in items:
                        item.setSelected(True)

        self.add_log_source_btn = QPushButton("+")
        self.add_log_source_btn.setFixedSize(25, 25)
        self.remove_log_source_btn = QPushButton("-")
        self.remove_log_source_btn.setFixedSize(25, 25)

        log_sources_btn_layout = QVBoxLayout()
        log_sources_btn_layout.addWidget(self.add_log_source_btn)
        log_sources_btn_layout.addWidget(self.remove_log_source_btn)
        log_sources_btn_layout.addStretch()

        input_layout.addWidget(self.log_sources_label, 0, 3)
        input_layout.addWidget(self.log_sources_list_widget, 1, 3, 1, 1)
        input_layout.addLayout(log_sources_btn_layout, 1, 5, 1, 1)

        # الكلمات الرئيسية للمطابقة (include) مع QListWidget وأزرار إضافة وحذف على الجانب بحجم صغير
        self.keywords_include_label = QLabel(settings_manager.get_translation("Keywords to include"))
        self.keywords_include_list_widget = QListWidget()
        self.keywords_include_list_widget.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.keywords_include_input = QLineEdit()
        self.add_keyword_include_btn = QPushButton("+")
        self.add_keyword_include_btn.setFixedSize(25, 25)
        self.del_keyword_include_btn = QPushButton("-")
        self.del_keyword_include_btn.setFixedSize(25, 25)

        keywords_include_btn_layout = QVBoxLayout()
        keywords_include_btn_layout.addWidget(self.add_keyword_include_btn)
        keywords_include_btn_layout.addWidget(self.del_keyword_include_btn)
        keywords_include_btn_layout.addStretch()

        input_layout.addWidget(self.keywords_include_label, 0, 0)
        input_layout.addWidget(self.keywords_include_list_widget, 1, 1)
        input_layout.addLayout(keywords_include_btn_layout, 1, 2)
        input_layout.addWidget(self.keywords_include_input, 0, 1)

        # وضعية مطابقة الكلمات الرئيسية (Exact, Starts With, Contains)
        self.keyword_match_mode_label = QLabel(settings_manager.get_translation("Keyword Match Mode"))
        self.exact_match_radio = QRadioButton(settings_manager.get_translation("Exact Match"))
        self.startswith_radio = QRadioButton(settings_manager.get_translation("Starts With"))
        self.contains_radio = QRadioButton(settings_manager.get_translation("Contains"))
        self.contains_radio.setChecked(True)  # الوضع الافتراضي

        self.keyword_match_mode_group = QButtonGroup()
        self.keyword_match_mode_group.addButton(self.exact_match_radio)
        self.keyword_match_mode_group.addButton(self.startswith_radio)
        self.keyword_match_mode_group.addButton(self.contains_radio)

        keyword_match_mode_layout = QHBoxLayout()
        keyword_match_mode_layout.addWidget(self.exact_match_radio)
        keyword_match_mode_layout.addWidget(self.startswith_radio)
        keyword_match_mode_layout.addWidget(self.contains_radio)
        keyword_match_mode_layout.addStretch()

        input_layout.addWidget(self.keyword_match_mode_label, 8, 0)
        input_layout.addLayout(keyword_match_mode_layout, 8, 1, 1, 2)

        # الكلمات الرئيسية للاستثناء كما في الكود الأصلي (QComboBox)
        self.keywords_exclude_label = QLabel(settings_manager.get_translation("Keywords to exclude"))
        self.keywords_exclude_combo = QComboBox()
        self.keywords_exclude_combo.setEditable(True)
        self.add_keyword_exclude_btn = QPushButton("+")
        self.add_keyword_exclude_btn.setFixedSize(25, 25)
        self.del_keyword_exclude_btn = QPushButton("-")
        self.del_keyword_exclude_btn.setFixedSize(25, 25)

        keywords_exclude_btn_layout = QHBoxLayout()
        keywords_exclude_btn_layout.addWidget(self.add_keyword_exclude_btn)
        keywords_exclude_btn_layout.addWidget(self.del_keyword_exclude_btn)
        keywords_exclude_btn_layout.addStretch()

        input_layout.addWidget(self.keywords_exclude_label, 5, 0)
        input_layout.addWidget(self.keywords_exclude_combo, 5, 1)
        input_layout.addLayout(keywords_exclude_btn_layout, 5, 2)

        # باقي الواجهة كما هي
        self.event_ids_label = QLabel(settings_manager.get_translation("Event IDs"))
        self.event_ids_combo = QComboBox()
        self.event_ids_combo.setEditable(True)
        self.event_ids_combo.setObjectName("eventIdsCombo")
        input_layout.addWidget(self.event_ids_label, 6, 0)
        input_layout.addWidget(self.event_ids_combo, 6, 1, 1, 1)

        self.severity_levels_label = QLabel(settings_manager.get_translation("Severity Levels"))
        input_layout.addWidget(self.severity_levels_label, 9, 0)
        levels_layout = QHBoxLayout()
        self.error_checkbox = QCheckBox(settings_manager.get_translation("Error"))
        self.error_checkbox.setChecked(True)
        self.warning_checkbox = QCheckBox(settings_manager.get_translation("Warning"))
        self.warning_checkbox.setChecked(True)
        self.information_checkbox = QCheckBox(settings_manager.get_translation("Information"))
        self.information_checkbox.setChecked(True)

        # Conditional checkboxes for AuditSuccess/Failure (Windows) and general Success/Failure (Linux)
        if IS_WINDOWS:
            self.audit_success_checkbox = QCheckBox(settings_manager.get_translation("AuditSuccess"))
            self.audit_success_checkbox.setChecked(True)
            self.audit_failure_checkbox = QCheckBox(settings_manager.get_translation("AuditFailure"))
            self.audit_failure_checkbox.setChecked(True)
            levels_layout.addWidget(self.audit_success_checkbox)
            levels_layout.addWidget(self.audit_failure_checkbox)
        elif IS_LINUX:
            self.success_checkbox = QCheckBox(settings_manager.get_translation("Success"))
            self.success_checkbox.setChecked(True)
            self.failure_checkbox = QCheckBox(settings_manager.get_translation("Failure"))
            self.failure_checkbox.setChecked(True)
            levels_layout.addWidget(self.success_checkbox)
            levels_layout.addWidget(self.failure_checkbox)

        levels_layout.addWidget(self.error_checkbox)
        levels_layout.addWidget(self.warning_checkbox)
        levels_layout.addWidget(self.information_checkbox)
        levels_layout.addStretch()
        input_layout.addLayout(levels_layout, 9, 1, 2, 2)

        self.time_range_label = QLabel(settings_manager.get_translation("Time Range (hours)"))
        self.time_range_input = QLineEdit("24")
        self.time_range_input.setFixedWidth(self.time_range_input.sizeHint().width() // 2)
        input_layout.addWidget(self.time_range_label, 6, 3)
        input_layout.addWidget(self.time_range_input, 7, 3, 1, 1)

        buttons_layout = QHBoxLayout()
        self.analyze_button = QPushButton(settings_manager.get_translation("Analyze"))
        analyze_btn_style = "font-weight: bold; font-size: 16px; padding: 10px;"
        if settings_manager.theme == "Light":
            analyze_btn_style += "background-color: #007bff; color: white;"
        else:
            analyze_btn_style += "background-color: #88aaff; color: black;"
        self.analyze_button.setStyleSheet(analyze_btn_style)
        buttons_layout.addWidget(self.analyze_button)
        input_layout.addLayout(buttons_layout, 9, 3, 2, 2)
        self.analyze_button.setFixedSize(170, 40)

        self.input_group.setLayout(input_layout)
        self.input_group.setFixedSize(800, 350)  # ارتفاع كما في الكود الأصلي

        # تصغير عرض واجهة الرسم البياني وإضافتها ضمن واجهة المدخلات (يمينها)
        self.graph_group = QGroupBox(settings_manager.get_translation("Event Severity Distribution"))
        graph_layout = QVBoxLayout(self.graph_group)
        pg.setConfigOption('background', None)
        pg.setConfigOption('foreground', 'k' if settings_manager.theme == "Light" else 'w')
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.getAxis('left').setLabel(settings_manager.get_translation("Count (events)"), units='')
        self.plot_widget.getAxis('bottom').setTicks([])
        graph_layout.addWidget(self.plot_widget)
        self.graph_group.setLayout(graph_layout)
        self.graph_group.setFixedSize(700, 350)  # عرض أصغر وارتفاع مطابق لواجهة المدخلات

        top_splitter.addWidget(self.input_group)
        top_splitter.addWidget(self.graph_group)
        top_splitter.setSizes([750, 350])
        top_splitter.setChildrenCollapsible(False)

        self.output_group = QGroupBox(settings_manager.get_translation("Outputs"))
        output_layout = QVBoxLayout(self.output_group)
        self.log_model = LogDataModel()
        self.log_table = QTableView()
        self.log_table.setModel(self.log_model)
        self.log_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.log_table.setSortingEnabled(True)
        self.log_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.log_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.log_table.customContextMenuRequested.connect(self.show_context_menu)
        output_layout.addWidget(self.log_table)
        self.output_group.setLayout(output_layout)

        v_splitter.addWidget(top_splitter)
        v_splitter.addWidget(self.output_group)
        v_splitter.setSizes([400, 500])
        v_splitter.setChildrenCollapsible(False)

        main_layout.addWidget(v_splitter)

        self.stats_group = QGroupBox()
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(5)
        self.stats_widgets = {}

        # تعريف مفاتيح الإحصائيات لسهولة الوصول إليها وتحديثها
        self.stat_keys = [
            ('failed_logins', settings_manager.get_translation("Failure")),
            ('successful_logins', settings_manager.get_translation("Success")),
            (settings_manager.get_translation("High"), settings_manager.get_translation("High")),
            (settings_manager.get_translation("Medium"), settings_manager.get_translation("Medium")),
            (settings_manager.get_translation("Low"), settings_manager.get_translation("Low")),
            (settings_manager.get_translation("Error"), settings_manager.get_translation("Error")),
            (settings_manager.get_translation("Warning"), settings_manager.get_translation("Warning")),
        ]
        if IS_WINDOWS:
            self.stat_keys.extend([
                (settings_manager.get_translation("AuditSuccess"), settings_manager.get_translation("AuditSuccess")),
                (settings_manager.get_translation("AuditFailure"), settings_manager.get_translation("AuditFailure")),
            ])
        elif IS_LINUX:
            self.stat_keys.extend([
                (settings_manager.get_translation("Success"), settings_manager.get_translation("Success")),
                (settings_manager.get_translation("Failure"), settings_manager.get_translation("Failure")),
            ])

        def create_stat_widget(label_text, key):
            frame = QFrame()
            frame.setFrameShape(QFrame.Shape.StyledPanel)
            # تحديث الألوان لتتناسب مع الثيم
            if settings_manager.theme == "Dark":
                frame.setStyleSheet("background-color: #333; border-radius: 5px; padding: 0px;")
            else:
                frame.setStyleSheet("background-color: #e0e0e0; border-radius: 5px; padding: 0px;")

            layout = QVBoxLayout(frame)
            label = QLabel(label_text)
            label.setStyleSheet("font-weight: bold; font-size: 8pt;")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            count_label = QLabel("0")
            count_label.setStyleSheet("font-size: 9pt; font-weight: bold;")
            count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)
            layout.addWidget(count_label)
            # ربط النقر بوظيفة عرض التفاصيل
            frame.mousePressEvent = lambda ev, k=key: self.show_stat_details(k)
            return frame, count_label

        for key, label_text in self.stat_keys:
            widget, count_lbl = create_stat_widget(label_text, key)
            stats_layout.addWidget(widget)
            self.stats_widgets[key] = (widget, count_lbl)

        stats_layout.addStretch()
        self.stats_group.setLayout(stats_layout)
        main_layout.addWidget(self.stats_group)

    # الاتصالات
    def setup_connections(self):
        self.analyze_button.clicked.connect(self.start_analysis)

        # مصادر السجلات
        self.add_log_source_btn.clicked.connect(self.add_log_source)
        self.remove_log_source_btn.clicked.connect(self.remove_log_source)

        # كلمات include
        self.add_keyword_include_btn.clicked.connect(self.add_keywords_include)
        # ربط حقل الإدخال بوظيفة الإضافة عند الضغط على Enter
        self.keywords_include_input.returnPressed.connect(self.add_keywords_include)
        self.del_keyword_include_btn.clicked.connect(self.del_keywords_include)
        # ربط حقل الإدخال بوظيفة التصفية الديناميكية
        self.keywords_include_input.textChanged.connect(self.filter_keywords_include_list)

        # كلمات exclude (QComboBox)
        self.add_keyword_exclude_btn.clicked.connect(self.add_keywords_exclude)
        self.del_keyword_exclude_btn.clicked.connect(self.del_keywords_exclude)

    def add_log_source(self):
        text, ok = QInputDialog.getText(self, settings_manager.get_translation("Add Log Source"),
                                        settings_manager.get_translation("Add Log Source"))
        if ok and text.strip():
            text = text.strip()
            existing_items = [self.log_sources_list_widget.item(i).text() for i in
                              range(self.log_sources_list_widget.count())]
            if text not in existing_items:
                item = QListWidgetItem(text)
                item.setSelected(True)
                self.log_sources_list_widget.addItem(item)
            else:
                QMessageBox.information(self, settings_manager.get_translation("Information"),
                                        f"'{text}' {settings_manager.get_translation('already exists.')}")

    def remove_log_source(self):
        selected_items = self.log_sources_list_widget.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, settings_manager.get_translation("Warning"),
                                settings_manager.get_translation("Please specify at least one Log Source."))
            return
        for item in selected_items:
            self.log_sources_list_widget.takeItem(self.log_sources_list_widget.row(item))

    def add_keywords_include(self):
        text = self.keywords_include_input.text().strip()
        if not text:
            return
        keywords = [k.strip() for k in text.split(',') if k.strip()]

        # الحصول على جميع الكلمات الموجودة حالياً في القائمة (مرئية أو مخفية)
        existing_keywords_in_list = set()
        for i in range(self.keywords_include_list_widget.count()):
            existing_keywords_in_list.add(self.keywords_include_list_widget.item(i).text().lower())

        added_any = False
        for kw in keywords:
            if kw.lower() not in existing_keywords_in_list:
                # إضافة الكلمة الجديدة في أعلى القائمة (index 0)
                self.keywords_include_list_widget.insertItem(0, kw)
                added_any = True
                # تحديث مجموعة الكلمات الموجودة لتجنب تكرار الإضافة في نفس العملية
                existing_keywords_in_list.add(kw.lower())

        if added_any:
            self.keywords_include_input.clear()
            self.save_persistent_lists()
            # إعادة تصفية القائمة بعد الإضافة لضمان ظهور الكلمات الجديدة بشكل صحيح
            self.filter_keywords_include_list(self.keywords_include_input.text())

    def del_keywords_include(self):
        selected_items = self.keywords_include_list_widget.selectedItems()
        if not selected_items:
            # رسالة تحذير أكثر دقة
            QMessageBox.warning(self, settings_manager.get_translation("Warning"),
                                settings_manager.get_translation("No keywords selected to delete."))
            return

        # حذف العناصر المحددة من القائمة
        for item in selected_items:
            self.keywords_include_list_widget.takeItem(self.keywords_include_list_widget.row(item))

        self.save_persistent_lists()
        # إعادة تصفية القائمة بعد الحذف
        self.filter_keywords_include_list(self.keywords_include_input.text())

    def filter_keywords_include_list(self, text):
        """
        تصفية قائمة الكلمات المفتاحية (include) بناءً على النص المدخل.
        """
        filter_text = text.strip().lower()
        for i in range(self.keywords_include_list_widget.count()):
            item = self.keywords_include_list_widget.item(i)
            item_text = item.text().lower()
            if not filter_text or item_text.startswith(filter_text):
                item.setHidden(False)
            else:
                item.setHidden(True)

    def add_keywords_exclude(self):
        text = self.keywords_exclude_combo.currentText().strip()
        if not text:
            return
        keywords = [k.strip() for k in text.split(',') if k.strip()]
        existing_keywords = [self.keywords_exclude_combo.itemText(i) for i in
                             range(self.keywords_exclude_combo.count())]
        added_any = False
        for kw in keywords:
            if kw not in existing_keywords:
                self.keywords_exclude_combo.addItem(kw)
                added_any = True
        if added_any:
            self.keywords_exclude_combo.setCurrentText("")
            self.save_persistent_lists()

    def del_keywords_exclude(self):
        current_index = self.keywords_exclude_combo.currentIndex()
        if current_index == -1:
            QMessageBox.warning(self, settings_manager.get_translation("Warning"),
                                settings_manager.get_translation(
                                    "No rows selected to export."))  # يمكن تحسين هذه الرسالة أيضاً
            return
        self.keywords_exclude_combo.removeItem(current_index)
        self.save_persistent_lists()

    def load_persistent_lists(self):
        include_keys = settings_manager.settings.value("include_keywords", [], type=list)
        exclude_keys = settings_manager.settings.value("exclude_keywords", [], type=list)
        event_ids = settings_manager.settings.value("event_ids", [], type=list)
        keyword_match_mode = settings_manager.settings.value("keyword_match_mode", "contains")

        # إضافة الكلمات المفتاحية للمطابقة (include)
        # بما أننا نضيف دائماً في الأعلى، فإن ترتيب القائمة المحفوظة سيعكس ذلك
        self.keywords_include_list_widget.addItems(include_keys)

        self.keywords_exclude_combo.addItems(exclude_keys)
        self.event_ids_combo.addItems(event_ids)

        if keyword_match_mode == 'exact':
            self.exact_match_radio.setChecked(True)
        elif keyword_match_mode == 'startswith':
            self.startswith_radio.setChecked(True)
        else:
            self.contains_radio.setChecked(True)

    def save_persistent_lists(self):
        # قراءة الكلمات المفتاحية من QListWidget بالترتيب الحالي (الأحدث في الأعلى)
        include_keys = [self.keywords_include_list_widget.item(i).text() for i in
                        range(self.keywords_include_list_widget.count())]
        exclude_keys = [self.keywords_exclude_combo.itemText(i) for i in range(self.keywords_exclude_combo.count())]
        event_ids = [self.event_ids_combo.itemText(i) for i in range(self.event_ids_combo.count())]

        if self.exact_match_radio.isChecked():
            keyword_match_mode = 'exact'
        elif self.startswith_radio.isChecked():
            keyword_match_mode = 'startswith'
        else:
            keyword_match_mode = 'contains'

        settings_manager.settings.setValue("include_keywords", include_keys)
        settings_manager.settings.setValue("exclude_keywords", exclude_keys)
        settings_manager.settings.setValue("event_ids", event_ids)
        settings_manager.settings.setValue("keyword_match_mode", keyword_match_mode)

    def start_analysis(self):
        selected_log_sources = [item.text() for item in self.log_sources_list_widget.selectedItems()]
        if not selected_log_sources:
            self.show_message_box(settings_manager.get_translation("Error"),
                                  settings_manager.get_translation("Please specify at least one Log Source."))
            return

        # --- NEW LOGIC FOR KEYWORDS TO INCLUDE ---
        selected_include_items = self.keywords_include_list_widget.selectedItems()
        if selected_include_items:
            # If items are selected, use only them
            keywords_include = [item.text().strip() for item in selected_include_items if item.text().strip()]
        else:
            # If no items are selected, use all items in the list (visible or hidden)
            keywords_include = [self.keywords_include_list_widget.item(i).text().strip() for i in
                                range(self.keywords_include_list_widget.count()) if
                                self.keywords_include_list_widget.item(i).text().strip()]
        # --- END NEW LOGIC ---

        keywords_exclude = [self.keywords_exclude_combo.itemText(i).strip() for i in
                            range(self.keywords_exclude_combo.count()) if
                            self.keywords_exclude_combo.itemText(i).strip()]

        try:
            time_range = int(self.time_range_input.text())
            if time_range <= 0:
                raise ValueError
        except ValueError:
            self.show_message_box(settings_manager.get_translation("Error"),
                                  settings_manager.get_translation("Time Range must be a positive number."))
            return

        severity_levels = []
        if self.error_checkbox.isChecked():
            severity_levels.append(settings_manager.get_translation("Error"))
        if self.warning_checkbox.isChecked():
            severity_levels.append(settings_manager.get_translation("Warning"))
        if self.information_checkbox.isChecked():
            severity_levels.append(settings_manager.get_translation("Information"))

        if IS_WINDOWS:
            if self.audit_success_checkbox.isChecked():
                severity_levels.append(settings_manager.get_translation("AuditSuccess"))
            if self.audit_failure_checkbox.isChecked():
                severity_levels.append(settings_manager.get_translation("AuditFailure"))
        elif IS_LINUX:
            if self.success_checkbox.isChecked():
                severity_levels.append(settings_manager.get_translation("Success"))
            if self.failure_checkbox.isChecked():
                severity_levels.append(settings_manager.get_translation("Failure"))

        event_ids = []
        all_ids_text = [self.event_ids_combo.itemText(i).strip() for i in range(self.event_ids_combo.count())]
        current_text = self.event_ids_combo.currentText().strip()
        if current_text:
            all_ids_text.append(current_text)
        combined_ids = ",".join(all_ids_text).strip()
        if combined_ids:
            try:
                event_ids = [int(i.strip()) for i in combined_ids.split(",") if i.strip()]
            except ValueError:
                self.show_message_box(settings_manager.get_translation("Error"), settings_manager.get_translation(
                    "Event ID must be a comma-separated list of numbers."))
                return
        else:
            event_ids = []

        if self.exact_match_radio.isChecked():
            keyword_match_mode = 'exact'
        elif self.startswith_radio.isChecked():
            keyword_match_mode = 'startswith'
        else:
            keyword_match_mode = 'contains'

        self.log_model.set_data([])
        self.status_label.setText(
            f"{settings_manager.get_translation('Status')} {settings_manager.get_translation('Analyzing logs...')} ({', '.join(selected_log_sources)})")
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.analyze_button.setEnabled(False)

        if self.log_analyzer_thread and self.log_analyzer_thread.isRunning():
            self.log_analyzer_thread.stop()
            self.log_analyzer_thread.wait()

        self.log_analyzer_thread = LogAnalyzerThread(selected_log_sources, keywords_include, keyword_match_mode,
                                                     keywords_exclude,
                                                     time_range, severity_levels, event_ids)
        self.log_analyzer_thread.finished_signal.connect(self.on_analysis_finished)
        self.log_analyzer_thread.progress_signal.connect(self.update_progress)
        self.log_analyzer_thread.status_signal.connect(self.update_status_bar)
        self.log_analyzer_thread.error_signal.connect(self.on_thread_error)
        self.log_analyzer_thread.start()

    def on_analysis_finished(self, results, count, stats):
        self.log_model.set_data(results)
        self.status_label.setText(
            f"{settings_manager.get_translation('Status')} {settings_manager.get_translation('Analysis complete. Found {} matching events.').format(count)}")
        self.progress_bar.setVisible(False)
        self.analyze_button.setEnabled(True)
        if not results:
            self.show_message_box(settings_manager.get_translation("Information"),
                                  settings_manager.get_translation("No matching events found."))
        self.update_graph(results)
        self.update_stats_display(stats)
        self.current_analysis_stats = stats  # تخزين الإحصائيات الحالية

    def update_graph(self, results):
        severity_col_index = self.log_model.get_translated_headers().index(
            settings_manager.get_translation("Severity Level"))
        counts = {
            settings_manager.get_translation("High"): 0,
            settings_manager.get_translation("Medium"): 0,
            settings_manager.get_translation("Low"): 0,
            settings_manager.get_translation("Error"): 0,
            settings_manager.get_translation("Warning"): 0,
            settings_manager.get_translation("Information"): 0,
        }
        if IS_WINDOWS:
            counts[settings_manager.get_translation("AuditSuccess")] = 0
            counts[settings_manager.get_translation("AuditFailure")] = 0
        elif IS_LINUX:
            counts[settings_manager.get_translation("Success")] = 0
            counts[settings_manager.get_translation("Failure")] = 0

        for row in results:
            severity = row[severity_col_index]
            if severity in counts:
                counts[severity] += 1
            else:
                # إذا كانت هناك مستويات خطورة غير متوقعة، يمكن إضافتها إلى "Low" أو تجاهلها
                counts[settings_manager.get_translation("Information")] += 1  # Default to Information for unknown

        active_counts = {k: v for k, v in counts.items() if v > 0}
        self.plot_widget.clear()
        if not active_counts:
            return
        labels = list(active_counts.keys())
        values = list(active_counts.values())
        ticks = [list(enumerate(labels))]
        self.plot_widget.getAxis('bottom').setTicks(ticks)
        colors = {
            settings_manager.get_translation("High"): '#FF453A',
            settings_manager.get_translation("Medium"): '#FF9F0A',
            settings_manager.get_translation("Low"): '#30D158',
            settings_manager.get_translation("Error"): '#FF453A',
            settings_manager.get_translation("Warning"): '#FF9F0A',
            settings_manager.get_translation("Information"): '#30D158',
            settings_manager.get_translation("AuditSuccess"): '#30D158',
            settings_manager.get_translation("AuditFailure"): '#FF453A',
            settings_manager.get_translation("Success"): '#30D158',  # Linux
            settings_manager.get_translation("Failure"): '#FF453A',  # Linux
        }
        brushes = [colors.get(label, '#FFFFFF') for label in labels]
        self.bar_graph_item = pg.BarGraphItem(x=range(len(values)), height=values, width=0.6, brushes=brushes)
        self.plot_widget.addItem(self.bar_graph_item)

    def update_progress(self, current, total):
        if total > 0:
            self.progress_bar.setValue(int((current / total) * 100))
        else:
            self.progress_bar.setValue(0)

    def update_status_bar(self, message):
        self.status_label.setText(f"{settings_manager.get_translation('Status')} {message}")

    def on_thread_error(self, message):
        self.show_message_box(settings_manager.get_translation("Error"), message)
        self.status_label.setText(
            f"{settings_manager.get_translation('Status')} {settings_manager.get_translation('Ready')}")
        self.progress_bar.setVisible(False)
        self.analyze_button.setEnabled(True)
        self.log_model.set_data([])

    def show_message_box(self, title, message):
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.exec()

    def show_settings_dialog(self):
        dialog = SettingsDialog(self)
        dialog.exec()

    def show_context_menu(self, position):
        menu = QMenu(self)
        show_details_action = QAction(settings_manager.get_translation("Show Full Details"), self)
        show_details_action.triggered.connect(self.show_full_details)
        menu.addAction(show_details_action)
        isolate_action = QAction(settings_manager.get_translation("Isolate Log"), self)
        isolate_action.triggered.connect(self.isolate_log)
        menu.addAction(isolate_action)
        export_record_action = QAction(settings_manager.get_translation("Export Selected Record") + " (PDF)", self)
        export_record_action.triggered.connect(self.export_selected_results_pdf)
        menu.addAction(export_record_action)
        export_record_xlsx_action = QAction(settings_manager.get_translation("Export Selected Record") + " (XLSX)",
                                            self)
        export_record_xlsx_action.triggered.connect(self.export_selected_results_xlsx)
        menu.addAction(export_record_xlsx_action)
        menu.exec(self.log_table.viewport().mapToGlobal(position))

    def show_full_details(self):
        selected_rows = self.log_table.selectionModel().selectedRows()
        if not selected_rows:
            self.show_message_box(settings_manager.get_translation("Warning"),
                                  settings_manager.get_translation("No rows selected to export."))
            return
        try:
            row_data = self.log_model._data[selected_rows[0].row()]
            headers = self.log_model.get_translated_headers()
            log_details_dict = dict(zip(headers, row_data))
            dialog = LogDetailsDialog(self, log_data=log_details_dict)
            dialog.exec()
        except IndexError:
            self.show_message_box(settings_manager.get_translation("Error"),
                                  settings_manager.get_translation("Failed to retrieve log details. Please try again."))
            return

    def isolate_log(self):
        selected_rows = self.log_table.selectionModel().selectedRows()
        if not selected_rows:
            self.show_message_box(settings_manager.get_translation("Warning"),
                                  settings_manager.get_translation("No rows selected to export."))
            return
        selected_row_data = self.log_model._data[selected_rows[0].row()]
        self.log_model.set_data([selected_row_data])

    def export_all_results(self):
        self.export_results(self.log_model._data)

    def export_selected_results_pdf(self):
        selected_rows = self.log_table.selectionModel().selectedRows()
        if not selected_rows:
            self.show_message_box(settings_manager.get_translation("Warning"),
                                  settings_manager.get_translation("No rows selected to export."))
            return
        selected_data = [self.log_model._data[index.row()] for index in selected_rows]
        self._export_pdf(selected_data)

    def export_selected_results_xlsx(self):
        selected_rows = self.log_table.selectionModel().selectedRows()
        if not selected_rows:
            self.show_message_box(settings_manager.get_translation("Warning"),
                                  settings_manager.get_translation("No rows selected to export."))
            return
        selected_data = [self.log_model._data[index.row()] for index in selected_rows]
        self._export_xlsx(selected_data)

    def export_selected_results(self):
        self.export_selected_results_pdf()  # Default to PDF for selected export

    def export_results(self, data_to_export):
        if not data_to_export:
            self.show_message_box(settings_manager.get_translation("Information"),
                                  settings_manager.get_translation("No logs found for the given criteria."))
            return
        file_path, _ = QFileDialog.getSaveFileName(self, settings_manager.get_translation("Export to CSV"),
                                                   "results.csv", settings_manager.get_translation("CSV Files (*.csv)"))
        if file_path:
            try:
                with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f, quoting=csv.QUOTE_ALL)
                    headers = self.log_model.get_translated_headers()
                    writer.writerow(headers)

                    creation_time_col_idx = headers.index(settings_manager.get_translation("Creation Time"))
                    time_since_analysis_col_idx = headers.index(
                        settings_manager.get_translation("Time since analysis start"))

                    for row_data in data_to_export:
                        formatted_row = list(row_data)

                        if isinstance(formatted_row[creation_time_col_idx], datetime):
                            formatted_row[creation_time_col_idx] = formatted_row[creation_time_col_idx].strftime(
                                "%Y-%m-%d %H:%M:%S")

                        if isinstance(formatted_row[time_since_analysis_col_idx], timedelta):
                            total_seconds = int(formatted_row[time_since_analysis_col_idx].total_seconds())
                            hours, remainder = divmod(total_seconds, 3600)
                            minutes, seconds = divmod(remainder, 60)
                            formatted_row[time_since_analysis_col_idx] = f"{hours}h {minutes}m {seconds}s"

                        writer.writerow(formatted_row)

                self.show_message_box(settings_manager.get_translation("Success"),
                                      settings_manager.get_translation("Export successful."))
            except Exception as e:
                self.show_message_box(settings_manager.get_translation("Error"),
                                      f"{settings_manager.get_translation('Failed to export results.')}\n{str(e)}")

    def _export_pdf(self, data_to_export):
        dialog = StatsDetailsDialog(self, data=data_to_export, title=settings_manager.get_translation("Reports"))
        dialog._export_pdf(data_to_export)

    def _export_xlsx(self, data_to_export):
        dialog = StatsDetailsDialog(self, data=data_to_export, title=settings_manager.get_translation("Reports"))
        dialog._export_xlsx(data_to_export)

    def closeEvent(self, event):
        self.save_persistent_lists()
        if self.log_analyzer_thread and self.log_analyzer_thread.isRunning():
            self.log_analyzer_thread.stop()
            self.log_analyzer_thread.wait()
        event.accept()

    def retranslateUi(self):
        self.setWindowTitle(settings_manager.get_translation("Log Analyzer"))
        self.input_group.setTitle(settings_manager.get_translation("Inputs"))
        self.log_sources_label.setText(settings_manager.get_translation("Log Sources"))
        self.keywords_include_label.setText(settings_manager.get_translation("Keywords to include"))
        self.keywords_exclude_label.setText(settings_manager.get_translation("Keywords to exclude"))
        self.event_ids_label.setText(settings_manager.get_translation("Event IDs"))
        self.time_range_label.setText(settings_manager.get_translation("Time Range (hours)"))
        self.severity_levels_label.setText(settings_manager.get_translation("Severity Levels"))
        self.error_checkbox.setText(settings_manager.get_translation("Error"))
        self.warning_checkbox.setText(settings_manager.get_translation("Warning"))
        self.information_checkbox.setText(settings_manager.get_translation("Information"))

        if IS_WINDOWS:
            self.audit_success_checkbox.setText(settings_manager.get_translation("AuditSuccess"))
            self.audit_failure_checkbox.setText(settings_manager.get_translation("AuditFailure"))
        elif IS_LINUX:
            self.success_checkbox.setText(settings_manager.get_translation("Success"))
            self.failure_checkbox.setText(settings_manager.get_translation("Failure"))

        self.analyze_button.setText(settings_manager.get_translation("Analyze"))
        self.graph_group.setTitle(settings_manager.get_translation("Event Severity Distribution"))
        self.output_group.setTitle(settings_manager.get_translation("Outputs"))
        self.keyword_match_mode_label.setText(settings_manager.get_translation("Keyword Match Mode"))
        self.exact_match_radio.setText(settings_manager.get_translation("Exact Match"))
        self.startswith_radio.setText(settings_manager.get_translation("Starts With"))
        self.contains_radio.setText(settings_manager.get_translation("Contains"))
        self.add_keyword_include_btn.setText("+")
        self.del_keyword_include_btn.setText("-")
        self.add_keyword_exclude_btn.setText("+")
        self.del_keyword_exclude_btn.setText("-")
        self.add_log_source_btn.setText("+")
        self.remove_log_source_btn.setText("-")
        self.retranslateMenu()
        self.log_model.update_headers()
        self.status_label.setText(
            f"{settings_manager.get_translation('Status')} {settings_manager.get_translation('Ready')}")
        if settings_manager.theme == "Light":
            self.analyze_button.setStyleSheet(
                "background-color: #007bff; color: white; font-weight: bold; font-size: 16px; padding: 5px;")
        else:
            self.analyze_button.setStyleSheet(
                "background-color: #88aaff; color: black; font-weight: bold; font-size: 16px; padding: 10px;")

        # Update stat labels and reset counts
        # Re-create stat_keys based on current OS to ensure correct labels are used
        self.stat_keys = [
            ('failed_logins', settings_manager.get_translation("Failure")),
            ('successful_logins', settings_manager.get_translation("Success")),
            (settings_manager.get_translation("High"), settings_manager.get_translation("High")),
            (settings_manager.get_translation("Medium"), settings_manager.get_translation("Medium")),
            (settings_manager.get_translation("Low"), settings_manager.get_translation("Low")),
            (settings_manager.get_translation("Error"), settings_manager.get_translation("Error")),
            (settings_manager.get_translation("Warning"), settings_manager.get_translation("Warning")),
        ]
        if IS_WINDOWS:
            self.stat_keys.extend([
                (settings_manager.get_translation("AuditSuccess"), settings_manager.get_translation("AuditSuccess")),
                (settings_manager.get_translation("AuditFailure"), settings_manager.get_translation("AuditFailure")),
            ])
        elif IS_LINUX:
            self.stat_keys.extend([
                (settings_manager.get_translation("Success"), settings_manager.get_translation("Success")),
                (settings_manager.get_translation("Failure"), settings_manager.get_translation("Failure")),
            ])

        # Clear existing stats widgets and re-add them to ensure correct order and labels
        for i in reversed(range(self.stats_group.layout().count())):
            widget_to_remove = self.stats_group.layout().itemAt(i).widget()
            if widget_to_remove:
                widget_to_remove.setParent(None)

        self.stats_widgets = {}  # Reset the dictionary

        for key, label_text in self.stat_keys:
            widget, count_lbl = self._create_stat_widget_internal(label_text, key)  # Use a helper for re-creation
            self.stats_group.layout().addWidget(widget)
            self.stats_widgets[key] = (widget, count_lbl)

        # Ensure the stretch is at the end
        self.stats_group.layout().addStretch()

    def _create_stat_widget_internal(self, label_text, key):
        # Helper function to create a single stat widget, used during retranslateUi
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        if settings_manager.theme == "Dark":
            frame.setStyleSheet("background-color: #333; border-radius: 5px; padding: 0px;")
        else:
            frame.setStyleSheet("background-color: #e0e0e0; border-radius: 5px; padding: 0px;")

        layout = QVBoxLayout(frame)
        label = QLabel(label_text)
        label.setStyleSheet("font-weight: bold; font-size: 8pt;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        count_label = QLabel("0")
        count_label.setStyleSheet("font-size: 9pt; font-weight: bold;")
        count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        layout.addWidget(count_label)
        frame.mousePressEvent = lambda ev, k=key: self.show_stat_details(k)
        return frame, count_label

    def update_stats_display(self, stats):
        """
        تحديث الأرقام المعروضة في مربعات الإحصائيات.
        """
        for key, _ in self.stat_keys:
            count_label = self.stats_widgets[key][1]  # الحصول على QLabel الخاص بالعداد
            if key in ['failed_logins', 'successful_logins']:
                count = stats[key]
            elif key in stats['severity_counts']:
                count = stats['severity_counts'][key]
            else:
                count = 0  # في حال عدم وجود بيانات لهذه الفئة
            count_label.setText(str(count))

    def show_stat_details(self, stat_key):
        """
        عرض تفاصيل السجلات لفئة إحصائية معينة عند النقر على مربع الإحصائية.
        """
        if not hasattr(self, 'current_analysis_stats') or not self.current_analysis_stats:
            self.show_message_box(settings_manager.get_translation("Information"),
                                  settings_manager.get_translation("No logs found for the given criteria."))
            return

        data_to_display = self.current_analysis_stats['events_by_category'].get(stat_key, [])
        if not data_to_display:
            self.show_message_box(settings_manager.get_translation("Information"),
                                  settings_manager.get_translation("No logs found for this category."))
            return

        # تحديد عنوان النافذة بناءً على مفتاح الإحصائية
        title_map = {
            'failed_logins': settings_manager.get_translation("Failed Logins Details"),
            'successful_logins': settings_manager.get_translation("Successful Logins Details"),
            settings_manager.get_translation("High"): settings_manager.get_translation("High Severity Details"),
            settings_manager.get_translation("Medium"): settings_manager.get_translation("Medium Severity Details"),
            settings_manager.get_translation("Low"): settings_manager.get_translation("Low Severity Details"),
            settings_manager.get_translation("Error"): settings_manager.get_translation("Error Details"),
            settings_manager.get_translation("Warning"): settings_manager.get_translation("Warning Details"),
        }
        if IS_WINDOWS:
            title_map.update({
                settings_manager.get_translation("AuditSuccess"): settings_manager.get_translation(
                    "Audit Success Details"),
                settings_manager.get_translation("AuditFailure"): settings_manager.get_translation(
                    "Audit Failure Details"),
            })
        elif IS_LINUX:
            title_map.update({
                settings_manager.get_translation("Success"): settings_manager.get_translation(
                    "Successful Logins Details"),  # Re-using for general success
                settings_manager.get_translation("Failure"): settings_manager.get_translation("Failed Logins Details"),
                # Re-using for general failure
            })

        dialog_title = title_map.get(stat_key, settings_manager.get_translation("Log Details"))

        dialog = StatsDetailsDialog(self, data=data_to_display, title=dialog_title)
        dialog.exec()


def main():
    app = QApplication(sys.argv)
    settings_manager.apply_theme(app)
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    main_window = MainWindow()
    if settings_manager.language == 'ar':
        main_window.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        main_window.time_range_input.setAlignment(Qt.AlignmentFlag.AlignRight)
    else:
        main_window.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        main_window.time_range_input.setAlignment(Qt.AlignmentFlag.AlignLeft)
    main_window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()