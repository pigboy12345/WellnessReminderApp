import datetime as dt
import getpass
import logging
import socket

import pyodbc # type: ignore

logger = logging.getLogger("WellnessReminder")

INSERT_SQL = """
INSERT INTO GP_Custom.dbo.WellnessReminderHistory
    (ReminderId, Title, Category, TriggeredDateTime, Status, MachineName, UserName, ErrorMessage)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""


class DBService:
    def __init__(self, connection_string: str, command_timeout: int = 0):
        self.connection_string = connection_string
        self.command_timeout = command_timeout

    def _connect(self):
        conn = pyodbc.connect(self.connection_string, autocommit=True)
        if self.command_timeout is not None:
            conn.timeout = self.command_timeout  # 0 = no timeout, matches your original string
        return conn

    def insert_history(self, reminder_id: str, triggered_dt: dt.datetime,
                        status: str, title: str = "", category: str = "",
                        error_message: str = None) -> bool: # type: ignore
        composite_id = triggered_dt.strftime("%Y%m%d") + str(reminder_id)
        machine_name = socket.gethostname()
        user_name = getpass.getuser()
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    INSERT_SQL,
                    composite_id,
                    title,
                    category,
                    triggered_dt,
                    status,
                    machine_name,
                    user_name,
                    error_message,
                )
            logger.info("History logged: ReminderId=%s Title=%s Status=%s MachineName=%s UserName=%s",
                        composite_id, title, status, machine_name, user_name)
            return True
        except Exception as exc:
            logger.error("Failed to write history for ReminderId=%s (Status=%s): %s",
                         composite_id, status, exc)
            return False
