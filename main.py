"""
Wellness Reminder Application
------------------------------
Meant to be run once daily (e.g. 09:30 AM via Windows Task Scheduler).
Loads today's reminders from WellnessReminders.xlsx, schedules each with
APScheduler for its exact schedulingTime, shows an actionable Windows toast
when each fires, writes every outcome to SQL Server (WellnessReminderHistory),
then exits automatically once all reminders (including any snoozes) are done.
"""
import datetime as dt
import threading
import time

from apscheduler.schedulers.background import BackgroundScheduler

from config import Config
from src.logger_setup import setup_logging
from src.excel_reader import load_todays_reminders
from src.db_service import DBService
from src.notification_service import NotificationService, COMPLETED, DISMISS, SNOOZE
from src.models import Reminder


class ReminderRunner:
    def __init__(self):
        self.cfg = Config()
        self.logger = setup_logging(self.cfg.log_file, self.cfg.log_level)
        self.db = DBService(self.cfg.build_connection_string(), self.cfg.db_command_timeout)
        self.notifier = NotificationService(
            app_name="Wellness Reminder",
            logo_path=self.cfg.logo_path,
            snooze_minutes=self.cfg.snooze_minutes,
            media_popup_enabled=self.cfg.media_popup_enabled,
            media_max_width=self.cfg.media_max_width,
            media_timeout_seconds=self.cfg.media_timeout_seconds,
            gif_max_loops=self.cfg.gif_max_loops,
        )
        self.scheduler = BackgroundScheduler()
        self._pending = 0
        self._lock = threading.Lock()
        self._all_done = threading.Event()

    # ---- job bookkeeping so the process can exit once everything is done ----
    def _job_added(self, n: int = 1):
        with self._lock:
            self._pending += n

    def _job_finished(self):
        with self._lock:
            self._pending -= 1
            done = self._pending <= 0
        if done:
            self._all_done.set()

    def _log_history(self, reminder: Reminder, status: str, error_message: str = None, when: dt.datetime = None):  # type: ignore
        when = when or dt.datetime.now()
        self.db.insert_history(reminder.id, when, status, reminder.title, reminder.category, error_message)

    # ---- toast button handling ----
    def _handle_action(self, reminder: Reminder, action: str):
        if action == COMPLETED:
            reminder.status = "Completed"
            self._log_history(reminder, "Completed")

        elif action == SNOOZE:
            if reminder.snooze_count >= self.cfg.max_snoozes:
                self.logger.info("ReminderId=%s hit max snoozes (%d); treating as dismissed.",
                                  reminder.id, self.cfg.max_snoozes)
                reminder.status = "Dismissed"
                self._log_history(reminder, "Dismissed", "Max snoozes reached")
            else:
                reminder.snooze_count += 1
                reminder.status = "Snoozed"
                self._log_history(reminder, "Snoozed")
                run_at = dt.datetime.now() + dt.timedelta(minutes=self.cfg.snooze_minutes)
                self._job_added()
                self.scheduler.add_job(
                    self._trigger_reminder, "date", run_date=run_at, args=[reminder],
                    id=f"{reminder.id}-snooze{reminder.snooze_count}",
                )
                self.logger.info("ReminderId=%s snoozed until %s", reminder.id, run_at)

        else:  # DISMISS or unrecognized action
            reminder.status = "Dismissed"
            self._log_history(reminder, "Dismissed")

    # ---- APScheduler job body ----
    def _trigger_reminder(self, reminder: Reminder):
        try:
            shown = self.notifier.show(reminder, on_action=self._handle_action)
            status = "Triggered" if shown else "Failed"
            error = None if shown else "Toast display failed"
            reminder.status = status
            self._log_history(reminder, status, error)  # type: ignore
        except Exception as exc:
            self.logger.exception("Unexpected error triggering ReminderId=%s", reminder.id)
            self._log_history(reminder, "Failed", str(exc))
        finally:
            self._job_finished()

    def run(self):
        self.logger.info("=== Wellness Reminder run started ===")
        reminders, invalid_rows = load_todays_reminders(self.cfg.excel_file)

        if invalid_rows:
            self.logger.warning("%d invalid row(s) skipped - see warnings above for details.", len(invalid_rows))

        if not reminders:
            self.logger.info("No enabled reminders found for today. Exiting.")
            return

        now = dt.datetime.now()
        today = now.date()

        to_schedule = []
        for r in reminders:
            scheduled_dt = dt.datetime.combine(today, r.scheduling_time)
            if scheduled_dt <= now:
                r.status = "Skipped"
                self._log_history(r, "Skipped", "Scheduled time already passed at startup", when=now)
                self.logger.info("ReminderId=%s skipped (scheduled %s already passed).", r.id, scheduled_dt)
            else:
                to_schedule.append((scheduled_dt, r))

        if not to_schedule:
            self.logger.info("No remaining reminders to schedule today. Exiting.")
            return

        self.scheduler.start()
        for scheduled_dt, r in to_schedule:
            self._job_added()
            self.scheduler.add_job(
                self._trigger_reminder, "date", run_date=scheduled_dt, args=[r], id=r.id,
            )
            self.logger.info("Scheduled ReminderId=%s at %s", r.id, scheduled_dt)

        self.logger.info("Waiting for %d scheduled reminder(s) to complete...", len(to_schedule))
        self._all_done.wait()
        time.sleep(2)  # small grace period for any last toast callback to land
        self.scheduler.shutdown(wait=False)
        self.logger.info("=== Wellness Reminder run completed ===")


def main():
    runner = ReminderRunner()
    runner.run()


if __name__ == "__main__":
    main()
