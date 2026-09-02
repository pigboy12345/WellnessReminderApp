import configparser
import os
import sys
from dotenv import load_dotenv # type: ignore


def _base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


class Config:
    def __init__(self, config_path: str = None): # type: ignore
        self.base_dir = _base_dir()
        self.config_path = config_path or os.path.join(self.base_dir, "config.ini")

        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        # Load .env file from the base directory (sensitive credentials)
        dotenv_path = os.path.join(self.base_dir, ".env")
        load_dotenv(dotenv_path)

        parser = configparser.ConfigParser()
        parser.read(self.config_path, encoding="utf-8")

        # --- Excel ---
        self.excel_file = self._resolve_path(
            parser.get("Excel", "FilePath", fallback="WellnessReminders.xlsx")
        )

        # --- Database ---
        # Non-sensitive settings still come from config.ini
        self.db_driver = parser.get("Database", "Driver", fallback="ODBC Driver 17 for SQL Server")
        self.db_server = parser.get("Database", "Server", fallback="")
        self.db_name = parser.get("Database", "Database", fallback="").strip()
        self.db_encrypt = parser.get("Database", "Encrypt", fallback="no")
        self.db_trust_cert = parser.get("Database", "TrustServerCertificate", fallback="yes")
        self.db_app_name = parser.get("Database", "Application Name", fallback="WellnessReminderApp")
        self.db_command_timeout = parser.getint("Database", "CommandTimeout", fallback=0)

        # Sensitive credentials loaded from .env (with fallback to config.ini for backward compatibility)
        self.db_uid = os.getenv("DB_UID") or parser.get("Database", "UID", fallback="")
        self.db_pwd = os.getenv("DB_PWD") or parser.get("Database", "PWD", fallback="")

        # --- Notification ---
        self.logo_path = self._resolve_path(parser.get("Notification", "LogoPath", fallback="logo.png"))
        self.snooze_minutes = parser.getint("Notification", "SnoozeMinutes", fallback=10)
        self.max_snoozes = parser.getint("Notification", "MaxSnoozes", fallback=3)

        # Media popup settings (used when a reminder's icon/image is a GIF/video)
        self.media_popup_enabled = parser.getboolean("Notification", "MediaPopupEnabled", fallback=True)
        self.media_max_width = parser.getint("Notification", "MediaMaxWidth", fallback=420)
        self.media_timeout_seconds = parser.getint("Notification", "MediaTimeoutSeconds", fallback=0)
        self.gif_max_loops = parser.getint("Notification", "GifMaxLoops", fallback=0)

        # --- Logging ---
        self.log_file = self._resolve_path(parser.get("Logging", "LogFile", fallback="wellness_reminder.log"))
        self.log_level = parser.get("Logging", "LogLevel", fallback="INFO")

    def _resolve_path(self, path: str) -> str:
        if os.path.isabs(path):
            return path
        return os.path.join(self.base_dir, path)

    def build_connection_string(self) -> str:
        parts = [
            f"Driver={{{self.db_driver}}}",
            f"Server={self.db_server}",
        ]
        if self.db_name:
            parts.append(f"Database={self.db_name}")
        parts += [
            f"UID={self.db_uid}",
            f"PWD={self.db_pwd}",
            f"Encrypt={self.db_encrypt}",
            f"TrustServerCertificate={self.db_trust_cert}",
            f"APP={self.db_app_name}",
        ]
        return ";".join(parts) + ";"
