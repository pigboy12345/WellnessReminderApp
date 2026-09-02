import datetime as dt
import unittest
from unittest.mock import MagicMock, patch

from src.db_service import DBService


class DBServiceHistoryInsertTest(unittest.TestCase):
    @patch("src.db_service.socket.gethostname", return_value="WORKSTATION-01")
    @patch("src.db_service.getpass.getuser", return_value="jdoe")
    @patch("src.db_service.pyodbc.connect")
    def test_insert_history_uses_current_table_columns(self, mock_connect, mock_getuser, mock_gethostname):
        conn = MagicMock()
        conn.__enter__.return_value = conn
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        mock_connect.return_value = conn

        service = DBService("DRIVER={SQL Server};SERVER=server;DATABASE=db;")
        triggered_dt = dt.datetime(2026, 9, 2, 10, 30, 0)

        result = service.insert_history(
            "ABC123",
            triggered_dt,
            "Triggered",
            title="Hydration",
            category="Wellness",
            error_message="Optional note",
        )

        self.assertTrue(result)
        cursor.execute.assert_called_once()
        sql, *args = cursor.execute.call_args[0]

        self.assertIn("MachineName", sql)
        self.assertIn("UserName", sql)
        self.assertEqual(args, [
            "20260902ABC123",
            "Hydration",
            "Wellness",
            triggered_dt,
            "Triggered",
            "WORKSTATION-01",
            "jdoe",
            "Optional note",
        ])


if __name__ == "__main__":
    unittest.main()
