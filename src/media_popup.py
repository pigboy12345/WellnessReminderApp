"""Lightweight toast-like media popup for wellness reminders.

Renders a single media file (static image, animated GIF, or short video)
from a local path or an http(s) URL, alongside the reminder title and
message, plus the same action buttons as the Windows toast
(Complete / Snooze / Dismiss). The popup replaces the toast whenever the
reminder's ``icon/image`` column contains a media path.

Because Windows toast notifications cannot play GIFs or videos natively,
this module provides a small Tkinter window that runs in its own thread and
its own Tk event loop, so it does not block the APScheduler callbacks.
"""
import logging
import os
import tempfile
import threading
import urllib.request
from typing import Callable, Optional

import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk

logger = logging.getLogger("WellnessReminder")

# Action strings must match the toast actions in notification_service.py
COMPLETED = "Completed"
DISMISS = "Dismiss"
SNOOZE = "Snooze"

_GIF_EXTS = {".gif"}
_VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v", ".wmv"}


def _download_to_temp(url: str) -> str:
    """Download a media URL to a temp file and return the local path."""
    fd, tmp_path = tempfile.mkstemp(suffix=os.path.splitext(url)[1] or ".bin")
    os.close(fd)
    try:
        with urllib.request.urlopen(url, timeout=30) as resp, open(tmp_path, "wb") as fh:  # noqa: S310
            fh.write(resp.read())
        return tmp_path
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def _resolve_media_path(path: str) -> str:
    """Return a local file path for a media reference (local path or URL)."""
    if path.startswith(("http://", "https://")):
        return _download_to_temp(path)
    return path


class MediaPopup:
    """A single media popup window."""

    def __init__(
        self,
        title: str,
        message: str,
        media_path: str,
        snooze_minutes: int = 10,
        max_width: int = 420,
        timeout_seconds: int = 0,
        gif_max_loops: int = 0,
        on_action: Optional[Callable[[str], None]] = None,
    ):
        self.title = title
        self.message = message
        self.media_path = media_path
        self.snooze_minutes = snooze_minutes
        self.max_width = max_width
        self.timeout_seconds = timeout_seconds
        self.gif_max_loops = gif_max_loops
        self.on_action = on_action

        self._root = tk.Tk()
        self._root.withdraw()
        self._root.overrideredirect(True)  # borderless, toast-like
        self._root.attributes("-topmost", True)
        try:
            self._root.attributes("-alpha", 0.98)
        except tk.TclError:
            pass

        self._frames = []          # list of PhotoImage for GIF / static preview
        self._frame_index = 0
        self._loop_count = 0
        self._video_reader = None
        self._video_delay = 40     # ms
        self._video_temp = None
        self._after_id = None
        self._auto_close_id = None
        self._closed = False

        self._build_ui()
        self._place_window()
        self._root.deiconify()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        self._root.configure(bg="#1f1f1f")
        self._root.protocol("WM_DELETE_WINDOW", self.close)

        # Outer frame with a subtle border
        outer = tk.Frame(self._root, bg="#2d2d2d", bd=1, relief="solid")
        outer.pack(fill="both", expand=True)

        # Header row: title on left, close button on right
        header = tk.Frame(outer, bg="#2d2d2d")
        header.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(
            header, text=self.title, bg="#2d2d2d", fg="#ffffff",
            font=("Segoe UI", 13, "bold"), wraplength=self.max_width - 40,
            justify="left",
        ).pack(side="left", fill="x", expand=True)
        tk.Button(
            header, text="✕", command=self.close, bg="#2d2d2d", fg="#ffffff",
            relief="flat", bd=0, cursor="hand2", activebackground="#3a3a3a",
            activeforeground="#ffffff", font=("Segoe UI", 10, "bold"),
        ).pack(side="right")

        # Media area
        self._media_frame = tk.Frame(outer, bg="#1f1f1f")
        self._media_frame.pack(fill="both", expand=True, padx=12, pady=4)
        self._media_label = tk.Label(self._media_frame, bg="#1f1f1f")
        self._media_label.pack(fill="both", expand=True)

        # Message / category
        tk.Label(
            outer, text=self.message, bg="#2d2d2d", fg="#d4d4d4",
            font=("Segoe UI", 10), wraplength=self.max_width - 40, justify="left",
        ).pack(fill="x", padx=12, pady=(4, 8))

        # Action buttons
        actions = tk.Frame(outer, bg="#2d2d2d")
        actions.pack(fill="x", padx=12, pady=(0, 10))
        ttk.Button(actions, text="Complete", command=lambda: self._finish(COMPLETED)).pack(
            side="left", padx=(0, 6))
        ttk.Button(
            actions, text=f"Snooze {self.snooze_minutes} min", command=lambda: self._finish(SNOOZE)
        ).pack(side="left", padx=6)
        ttk.Button(actions, text="Dismiss", command=lambda: self._finish(DISMISS)).pack(
            side="right", padx=(6, 0))

    def _place_window(self):
        self._root.update_idletasks()
        w = self._root.winfo_width()
        h = self._root.winfo_height()
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        x = sw - w - 24
        y = 24
        self._root.geometry(f"{w}x{h}+{x}+{y}")

    # ------------------------------------------------------------- media
    def _load_media(self):
        """Load the media into the label. Called once the window is up."""
        path = _resolve_media_path(self.media_path)
        self._video_temp = path
        ext = os.path.splitext(path)[1].lower()

        if ext in _VIDEO_EXTS:
            self._load_video(path)
        elif ext in _GIF_EXTS:
            self._load_gif(path)
        else:
            self._load_static(path)

    def _scale_image(self, img: Image.Image) -> Image.Image:
        w, h = img.size
        if w <= self.max_width:
            return img
        ratio = self.max_width / float(w)
        return img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS) # type: ignore

    def _load_static(self, path: str):
        try:
            img = Image.open(path)
            img = self._scale_image(img)
            self._frames.append(ImageTk.PhotoImage(img))
            self._media_label.configure(image=self._frames[0])
        except Exception:
            logger.exception("Failed to load static image '%s'", path)
            self._show_placeholder()

    def _load_gif(self, path: str):
        try:
            base = Image.open(path)
            frames = []
            for frame in range(getattr(base, "n_frames", 1)):
                base.seek(frame)
                f = base.convert("RGBA")
                frames.append(self._scale_image(f))
            if not frames:
                return self._show_placeholder()
            self._frames = [ImageTk.PhotoImage(f) for f in frames]
            self._loop_count = 0
            self._animate_gif()
        except Exception:
            logger.exception("Failed to load GIF '%s'", path)
            self._show_placeholder()

    def _animate_gif(self):
        if self._closed:
            return
        self._media_label.configure(image=self._frames[self._frame_index])
        self._frame_index = (self._frame_index + 1) % len(self._frames)
        if self._frame_index == 0:
            self._loop_count += 1
            if self.gif_max_loops and self._loop_count >= self.gif_max_loops:
                return
        try:
            self._after_id = self._root.after(80, self._animate_gif)
        except tk.TclError:
            pass

    def _load_video(self, path: str):
        try:
            import imageio  # noqa: F401  (ensures ffmpeg plugin is registered)
            import imageio_ffmpeg  # noqa: F401  (triggers ffmpeg availability)

            self._video_reader = imageio.get_reader(path, "ffmpeg") # type: ignore
            self._play_next_video_frame()
        except Exception:
            logger.exception("Failed to load video '%s'", path)
            self._show_placeholder()

    def _play_next_video_frame(self):
        if self._closed:
            return
        try:
            frame = self._video_reader.get_next_data() # type: ignore
            img = Image.fromarray(frame).convert("RGB") # type: ignore
            img = self._scale_image(img)
            photo = ImageTk.PhotoImage(img)
            self._frames = [photo]
            self._media_label.configure(image=photo)
            self._after_id = self._root.after(self._video_delay, self._play_next_video_frame)
        except StopIteration:
            # Loop video: reopen the reader
            try:
                self._video_reader.close() # type: ignore
                import imageio
                self._video_reader = imageio.get_reader(self._video_temp, "ffmpeg") # type: ignore
                self._play_next_video_frame()
            except Exception:
                logger.exception("Video loop failed")
        except Exception:
            logger.exception("Video frame error")

    def _show_placeholder(self):
        self._media_label.configure(
            text="[Media unavailable]", bg="#1f1f1f", fg="#888888",
            font=("Segoe UI", 10, "italic"),
        )

    # ------------------------------------------------------------- actions
    def _finish(self, action: str):
        try:
            if self.on_action:
                self.on_action(action)
        except Exception:
            logger.exception("Error handling media popup action %s", action)
        finally:
            self.close()

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._after_id:
            try:
                self._root.after_cancel(self._after_id)
            except Exception:
                pass
        if self._auto_close_id:
            try:
                self._root.after_cancel(self._auto_close_id)
            except Exception:
                pass
        if self._video_reader is not None:
            try:
                self._video_reader.close()
            except Exception:
                pass
        try:
            self._root.destroy()
        except Exception:
            pass

    # ------------------------------------------------------------- run
    def run(self):
        try:
            self._load_media()
            if self.timeout_seconds > 0:
                self._auto_close_id = self._root.after(
                    self.timeout_seconds * 1000, self.close)
            self._root.mainloop()
        except Exception:
            logger.exception("Media popup crashed")
            self.close()


def _run_popup(
    title: str,
    message: str,
    media_path: str,
    snooze_minutes: int,
    max_width: int,
    timeout_seconds: int,
    gif_max_loops: int,
    on_action: Optional[Callable[[str], None]],
):
    """Run a popup in a fresh Tk root (called from a background thread)."""
    popup = MediaPopup(
        title=title,
        message=message,
        media_path=media_path,
        snooze_minutes=snooze_minutes,
        max_width=max_width,
        timeout_seconds=timeout_seconds,
        gif_max_loops=gif_max_loops,
        on_action=on_action,
    )
    popup.run()


def show_media_popup(
    title: str,
    message: str,
    media_path: str,
    snooze_minutes: int = 10,
    max_width: int = 420,
    timeout_seconds: int = 0,
    gif_max_loops: int = 0,
    on_action: Optional[Callable[[str], None]] = None,
) -> bool:
    """Launch the media popup in a background thread. Returns True."""
    try:
        t = threading.Thread(
            target=_run_popup,
            kwargs={
                "title": title,
                "message": message,
                "media_path": media_path,
                "snooze_minutes": snooze_minutes,
                "max_width": max_width,
                "timeout_seconds": timeout_seconds,
                "gif_max_loops": gif_max_loops,
                "on_action": on_action,
            },
            daemon=True,
        )
        t.start()
        logger.info("Media popup launched for reminder '%s' (media: %s)", title, media_path)
        return True
    except Exception:
        logger.exception("Failed to launch media popup for reminder '%s'", title)
        return False
