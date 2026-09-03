#!/usr/bin/env python3
"""
Video Toast Player - Display videos as a toast notification
Auto-repeats and auto-closes after 20 seconds
Positioned in top-right corner at 1/4 screen size
FIXED: Proper video playback speed
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import cv2
import threading
import time
from PIL import Image, ImageTk
import os
import sys
from pathlib import Path


class VideoToastPlayer:
   def __init__(self, root):
       self.root = root
       self.root.title("Video Toast")
       
       # Get screen dimensions
       screen_width = self.root.winfo_screenwidth()
       screen_height = self.root.winfo_screenheight()
       
       # Calculate 1/4 screen size (50% width, 50% height)
       self.toast_width = screen_width // 3
       self.toast_height = screen_height // 2
       
       # Position in top-right corner
       x_pos = screen_width - self.toast_width
       y_pos = 0
       
       # Set geometry: WIDTHxHEIGHT+X+Y
       self.root.geometry(f"{self.toast_width}x{self.toast_height}+{x_pos}+{y_pos}")
       self.root.resizable(False, False)  # Fixed size
       self.root.attributes('-topmost', True)  # Always on top
       
       # Video properties
       self.cap = None
       self.is_playing = False
       self.is_paused = False
       self.video_path = None
       self.frame_count = 0
       self.current_frame = 0
       self.fps = 30  # Default FPS
       self.auto_close_time = 20  # Auto-close after 20 seconds
       self.auto_close_timer = None
       self.play_thread = None
       self.stop_flag = False
       
       # Store references for rendering
       self.photo_image = None
       self.last_frame = None
       
       # Set window styling
       self.root.configure(bg='#000000')
       
       # Bind keyboard shortcuts
       self.root.bind('<space>', lambda e: self.toggle_play_pause())
       self.root.bind('<q>', lambda e: self.on_closing())
       self.root.bind('<Escape>', lambda e: self.on_closing())
       
       # Create minimal UI
       self.create_ui()
       
       # Start responsiveness check
       self.update_on_resize()
   
   def create_ui(self):
       """Create minimal UI - just video display"""
       
       # Configure grid for full screen
       self.root.grid_rowconfigure(0, weight=1)
       self.root.grid_columnconfigure(0, weight=1)
       
       # Full-screen video frame
       self.video_frame = tk.Frame(self.root, bg='#000000')
       self.video_frame.grid(row=0, column=0, sticky='nsew', padx=0, pady=0)
       self.video_frame.grid_propagate(True)
       
       # Video label
       self.video_label = tk.Label(
           self.video_frame,
           text="🎬 Loading video...",
           font=("Segoe UI", 16, "bold"),
           bg='#000000',
           fg='#666666'
       )
       self.video_label.pack(expand=True, fill=tk.BOTH)
   
   def update_on_resize(self):
       """Periodic check for resize to update video display"""
       if self.last_frame is not None:
           self.redraw_video_frame()
       
       self.root.after(250, self.update_on_resize)
   
   def redraw_video_frame(self):
       """Redraw current video frame at current window size"""
       if self.last_frame is None:
           return
       
       frame = self.last_frame.copy()
       label_width = self.video_frame.winfo_width()
       label_height = self.video_frame.winfo_height()
       
       if label_width > 1 and label_height > 1:
           h, w = frame.shape[:2]
           aspect = w / h
           
           if label_width / label_height > aspect:
               new_h = label_height
               new_w = int(new_h * aspect)
           else:
               new_w = label_width
               new_h = int(new_w / aspect)
           
           frame = cv2.resize(frame, (new_w, new_h))
           frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
           img = Image.fromarray(frame_rgb)
           self.photo_image = ImageTk.PhotoImage(img)
           self.video_label.config(image=self.photo_image)
   
   def load_video(self, source=None):
       """Load video from path or URL and auto-play with auto-repeat"""
       if source is None:
           return
       
       source = str(source).strip()
       
       if not source:
           self.video_label.config(text="📹 No video source")
           return
       
       self.stop_video()
       self.video_label.config(text="⏳ Loading video...")
       self.root.update()
       
       # Store video path for replay
       self.video_path = source
       
       # Cancel previous auto-close timer if exists
       if self.auto_close_timer:
           self.root.after_cancel(self.auto_close_timer)
       
       try:
           self.cap = cv2.VideoCapture(source)
           
           # Add delay to let stream load properly
           self.root.after(500, self._validate_and_play)
           
       except Exception as e:
           self.video_label.config(text=f"❌ Error: {str(e)[:30]}")
           self.cap = None
   
   def _validate_and_play(self):
       """Validate video and start playback"""
       if self.cap is None:
           self.video_label.config(text="❌ Video failed to load")
           return
       
       try:
           if not self.cap.isOpened():
               raise ValueError("Could not open video source")
           
           self.frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
           self.fps = self.cap.get(cv2.CAP_PROP_FPS)
           
           # Validate FPS
           if self.fps <= 0 or self.fps > 120:
               self.fps = 30  # Default to 30 if invalid
           
           self.current_frame = 0
           
           if self.frame_count == 0:
               raise ValueError("Invalid video file or incomplete stream")
           
           self.display_frame()
           
           # Auto-play
           self.root.after(100, self.play_video)
           
           # Set auto-close timer (20 seconds)
           self.auto_close_timer = self.root.after(self.auto_close_time * 1000, self.on_closing)
           
       except Exception as e:
           self.video_label.config(text=f"❌ Invalid video")
           self.cap = None
   
   def play_video(self):
       """Play the loaded video"""
       if self.cap is None:
           return
       
       self.is_playing = True
       self.is_paused = False
       
       if self.play_thread is None or not self.play_thread.is_alive():
           self.stop_flag = False
           self.play_thread = threading.Thread(target=self._play_thread, daemon=True)
           self.play_thread.start()
   
   def _play_thread(self):
       """Thread function for video playback with safe recovery on OpenCV failures."""
       try:
           while self.is_playing and not self.stop_flag:
               if self.cap is None:
                   self.is_playing = False
                   break

               if not self.is_paused:
                   try:
                       ret, frame = self.cap.read() # type: ignore
                   except Exception:
                       self.root.after(0, self.on_closing)
                       return

                   if not ret:
                       try:
                           if not self.stop_flag:
                               self.cap.release() # type: ignore
                               self.root.after(100, self._reload_and_replay)
                               break
                       except Exception as exc:
                           print(f"Error during replay: {exc}")
                           self.is_playing = False
                           break
                       continue

                   self.current_frame += 1
                   self.last_frame = frame
                   self.root.after(0, self._update_display, frame)

                   if self.fps > 0:
                       frame_delay = 1.0 / self.fps
                   else:
                       frame_delay = 1.0 / 30

                   time.sleep(frame_delay)
               else:
                   time.sleep(0.1)
       except Exception:
           self.is_playing = False
           self.is_paused = True
           self.stop_flag = True
           if self.cap is not None:
               try:
                   self.cap.release()
               except Exception:
                   pass
           self.video_label.config(text="❌ Video playback stopped")
   def _reload_and_replay(self):
       """Reload video for the next loop"""
       if self.stop_flag or self.video_path is None:
           return
       
       try:
           self.cap = cv2.VideoCapture(self.video_path)
           
           if not self.cap.isOpened():
               self.video_label.config(text="❌ Video replay failed")
               return
           
           # Re-validate FPS
           self.fps = self.cap.get(cv2.CAP_PROP_FPS)
           if self.fps <= 0 or self.fps > 120:
               self.fps = 30
           
           self.current_frame = 0
           self.is_playing = True
           self.is_paused = False
           
           # Continue playing
           if self.play_thread is None or not self.play_thread.is_alive():
               self.play_thread = threading.Thread(target=self._play_thread, daemon=True)
               self.play_thread.start()
       except Exception as e:
           print(f"Error reloading video: {e}")
           self.video_label.config(text="❌ Replay error")
   
   def _update_display(self, frame):
       """Update the video display with new frame"""
       if self.stop_flag:
           return
       
       label_width = self.video_frame.winfo_width()
       label_height = self.video_frame.winfo_height()
       
       if label_width > 1 and label_height > 1:
           h, w = frame.shape[:2]
           aspect = w / h
           
           if label_width / label_height > aspect:
               new_h = label_height
               new_w = int(new_h * aspect)
           else:
               new_w = label_width
               new_h = int(new_w / aspect)
           
           frame = cv2.resize(frame, (new_w, new_h))
       
       frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
       img = Image.fromarray(frame_rgb)
       self.photo_image = ImageTk.PhotoImage(img)
       
       self.video_label.config(image=self.photo_image)
   
   def pause_video(self):
       """Pause the video"""
       self.is_paused = True
   
   def toggle_play_pause(self):
       """Toggle between play and pause"""
       if self.cap is None:
           return
       
       if self.is_playing and not self.is_paused:
           self.pause_video()
       else:
           self.play_video()
   
   def stop_video(self):
       """Stop video playback"""
       self.stop_flag = True
       self.is_playing = False
       self.is_paused = False
       
       if self.cap:
           self.cap.release()
           self.cap = None
       
       self.current_frame = 0
       self.last_frame = None
   
   def display_frame(self):
       """Display the first frame of the video"""
       if self.cap is None:
           return
       
       ret, frame = self.cap.read()
       if ret:
           self.last_frame = frame
           self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
           self._update_display(frame)
   
   def on_closing(self):
       """Handle window closing"""
       # Cancel auto-close timer
       if self.auto_close_timer:
           self.root.after_cancel(self.auto_close_timer)
       
       self.stop_video()
       self.root.destroy()


def main():
   """Main entry point"""
   root = tk.Tk()
   app = VideoToastPlayer(root)
   
   # Get video source from command line arguments
   video_source = None
   if len(sys.argv) > 1:
       video_source = sys.argv[1]
   else:
       # Try to get from environment variable
       video_source = os.environ.get('VIDEO_SOURCE')
   
   # If we have a video source, load and play it
   if video_source:
       root.after(500, lambda: app.load_video(video_source))
   
   root.protocol("WM_DELETE_WINDOW", app.on_closing)
   root.mainloop()


if __name__ == "__main__":
   main()