import datetime as dt
import logging
import os
import subprocess
import sys
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
from src.videoToast import VideoToastPlayer

logger = logging.getLogger("WellnessReminder")

COMPLETED = "Completed"
DISMISS = "Dismiss"
SNOOZE = "Snooze"

# Media extensions that should render in a dedicated media player instead of
# the standard Windows toast hero image when they cannot be displayed natively.
_VIDEO_EXTS = {".gif", ".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v", ".wmv"}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}


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
        return ext in _VIDEO_EXTS or path.startswith(("http://", "https://"))

    def _is_image_path(self, path: str) -> bool:
        """Return True when the value is a normal image file (native toast support)."""
        if not path:
            return False
        ext = os.path.splitext(path.split("?")[0])[1].lower()
        return ext in _IMAGE_EXTS and not path.startswith(("http://", "https://"))

    def _show_video_toast(self, media_path: str) -> bool:
        """Attempt to show a separate video toast only when the media is actually playable."""
        if not media_path or not self.media_popup_enabled:
            return False

        try:
            import cv2
            cap = cv2.VideoCapture(media_path)
            is_valid = cap.isOpened() if cap else False
            if cap is not None:
                cap.release()
            if not is_valid:
                logger.info("Skipping video toast for unsupported media source: %s", media_path)
                return False
        except Exception:
            logger.info("Skipping video toast: unsupported or unreadable media source: %s", media_path)
            return False

        try:
            launcher = """
import sys
import tkinter as tk
from src.videoToast import VideoToastPlayer

root = tk.Tk()
player = VideoToastPlayer(root)
root.protocol(\"WM_DELETE_WINDOW\", player.on_closing)
root.after(500, lambda: player.load_video(sys.argv[1]))
root.mainloop()
"""
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.Popen(
                [sys.executable, "-c", launcher, media_path],
                creationflags=creation_flags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
            return True
        except Exception:
            logger.exception("Could not initialize video toast for media path: %s", media_path)
            return False

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

        native_toast_shown = False
        toast = Toast([reminder.title, body])

        if reminder.icon and self._is_image_path(reminder.icon):
            image_path = reminder.icon if self._icon_path_exists(reminder.icon) else self.logo_path
            logo_image_path = self.logo_path if (self.logo_path and self._icon_path_exists(self.logo_path)) else None
            if image_path:
                toast.AddImage(ToastDisplayImage.fromPath(image_path, position=ToastImagePosition.Hero))
                toast.AddImage(ToastDisplayImage.fromPath(logo_image_path, position=ToastImagePosition.AppLogo)) # type: ignore
        elif self.logo_path and self._icon_path_exists(self.logo_path):
            toast.AddImage(ToastDisplayImage.fromPath(self.logo_path, position=ToastImagePosition.AppLogo)) # type: ignore

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
            native_toast_shown = True
            logger.info("Toast displayed for ReminderId=%s (%s)", reminder.id, reminder.title)
        except Exception:
            logger.exception("Failed to display toast for ReminderId=%s", reminder.id)
            return False

        if self.media_popup_enabled and reminder.icon and self._is_media_path(reminder.icon):
            try:
                # self._show_video_toast(reminder.icon) # for pop-up video toast
                logger.info("Video toast displayed for ReminderId=%s", reminder.id)
            except Exception:
                logger.exception("Video toast fallback failed for ReminderId=%s", reminder.id)

        return native_toast_shown
