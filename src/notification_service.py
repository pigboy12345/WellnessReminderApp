import datetime as dt
import logging
import os
from typing import Callable, Optional

from windows_toasts import ( # type: ignore
    InteractableWindowsToaster,
    Toast,
    ToastButton,
    ToastDisplayImage,
    ToastImagePosition,
    ToastActivatedEventArgs,
)

from src.media_popup import show_media_popup
from src.models import Reminder

logger = logging.getLogger("WellnessReminder")

COMPLETED = "Completed"
DISMISS = "Dismiss"
SNOOZE = "Snooze"

# Media extensions that should render in the popup instead of the toast.
_MEDIA_EXTS = {".gif", ".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v", ".wmv"}


class NotificationService:
    def __init__(
        self,
        app_name: str,
        logo_path: str,
        snooze_minutes: int = 10,
        media_popup_enabled: bool = True,
        media_max_width: int = 420,
        media_timeout_seconds: int = 0,
        gif_max_loops: int = 0,
    ):
        self.toaster = InteractableWindowsToaster(app_name)
        self.logo_path = logo_path if (logo_path and os.path.exists(logo_path)) else None
        self.snooze_minutes = snooze_minutes
        self.media_popup_enabled = media_popup_enabled
        self.media_max_width = media_max_width
        self.media_timeout_seconds = media_timeout_seconds
        self.gif_max_loops = gif_max_loops
        if logo_path and not self.logo_path:
            logger.warning("Logo image not found at '%s' - notifications will show without it.", logo_path)

    def _is_media_path(self, path: str) -> bool:
        """Return True if a path points to a GIF/video (local or URL)."""
        if not path:
            return False
        ext = os.path.splitext(path.split("?")[0])[1].lower()
        return ext in _MEDIA_EXTS or path.startswith(("http://", "https://"))

    def _icon_path_exists(self, path: str) -> bool:
        """Check if an icon path is valid - either a local file or a URL."""
        if not path:
            return False
        if path.startswith(("http://", "https://")):
            return True
        return os.path.exists(path)

    def show(self, reminder: Reminder, on_action: Optional[Callable[[Reminder, str], None]] = None) -> bool:
        now_str = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        body = f"{reminder.message}\nCategory: {reminder.category}   |   Time: {now_str}"

        # If the reminder uses a GIF/video media file (local or URL), show the
        # custom media popup instead of the toast (Windows toasts can't play
        # animated/video content).
        if self.media_popup_enabled and reminder.icon and self._is_media_path(reminder.icon):
            def _popup_action(action: str):
                if on_action:
                    try:
                        on_action(reminder, action)
                    except Exception:
                        logger.exception("Error handling media popup action for ReminderId=%s", reminder.id)

            return show_media_popup(
                title=reminder.title,
                message=body,
                media_path=reminder.icon,
                snooze_minutes=self.snooze_minutes,
                max_width=self.media_max_width,
                timeout_seconds=self.media_timeout_seconds,
                gif_max_loops=self.gif_max_loops,
                on_action=_popup_action,
            )

        toast = Toast([reminder.title, body])

        image_path = reminder.icon if (reminder.icon and self._icon_path_exists(reminder.icon)) else self.logo_path
        logo_image_path = self.logo_path if (self.logo_path and self._icon_path_exists(self.logo_path)) else None
        if image_path:
            toast.AddImage(ToastDisplayImage.fromPath(image_path, position=ToastImagePosition.Hero))
            toast.AddImage(ToastDisplayImage.fromPath(logo_image_path, position=ToastImagePosition.AppLogo)) # type: ignore

        toast.AddAction(ToastButton(COMPLETED, COMPLETED))
        toast.AddAction(ToastButton(DISMISS, DISMISS))
        toast.AddAction(ToastButton(f"Snooze {self.snooze_minutes} min", SNOOZE))

        def _on_activated(event_args: ToastActivatedEventArgs):
            action = event_args.arguments or DISMISS
            logger.info("Toast action received for ReminderId=%s: %s", reminder.id, action)
            if on_action:
                try:
                    on_action(reminder, action)
                except Exception:
                    logger.exception("Error handling toast action for ReminderId=%s", reminder.id)

        toast.on_activated = _on_activated

        try:
            self.toaster.show_toast(toast)
            logger.info("Toast displayed for ReminderId=%s (%s)", reminder.id, reminder.title)
            return True
        except Exception:
            logger.exception("Failed to display toast for ReminderId=%s", reminder.id)
            return False
