#!/usr/bin/env python3
"""Roboss — Roblox automation, Linux port.

Original: AutoIt (Windows) by Matt Brassey. This is a functional port to Linux
using tkinter for the GUI and xdotool for window activation and key/text
injection under X11.

Requires: xdotool (`sudo apt install xdotool`), an X11 session.
Wayland is not supported for key injection (xdotool needs X11 / XWayland).
"""

import os
import random
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk

WIN_TITLE = "Roblox"          # substring matched against window titles
ASSET_DIR = os.path.dirname(os.path.abspath(__file__))
ROBOSS_JPG = os.path.join(ASSET_DIR, "Roboss.jpg")

# --- Wisdom -----------------------------------------------------------------
# Ported verbatim from Roboss.au3 $arr. Index 15 was absent in the original
# (a gap in the AutoIt array); we keep the same set of sayings.
WISDOM = [
    "Live as if you were to die tomorrow. Learn as if you were to live forever.",
    "Unless you try to do something beyond what you have already mastered, you will never grow.",
    "Buddha was asked, “What have you gained from meditation?” He replied, “Nothing!” However, Buddha said, let me tell you what I lost: Anger, Anxiety, Depression, Insecurity, Fear of Death.",
    "The best teachers are those who show you where to look, but don’t tell you what to see.",
    "Be kind, for everyone you meet is fighting a hard battle.",
    "Because the people who are crazy enough to think they can change the world, are the ones who do.",
    "Do the difficult things while they are easy and do the great things while they are small. A journey of a thousand miles must begin with a single step.",
    "In a time of deceit, telling the truth is a revolutionary act.",
    "Logic will get you from A to B. Imagination will take you everywhere.",
    "Everything that irritates us about others can lead us to an understanding of ourselves.",
    "I’m not in this world to live up to your expectations and you’re not in this world to live up to mine.",
    "Do not pray for an easy life. Pray for the strength to endure a difficult one.",
    "Never let school interfere with your education.",
    "The beautiful thing about fear is that when you run to it, it runs away.",
    "We can’t solve problems by using the same kind of thinking we used when we created them.",
    "Modern technologies are 99 percent bravery, and 1 percent investment.",
    "Bitcoin is the most stellar and most useful system of mutual trust ever devised.",
    "Cryptocurrency is freedom, Banking is slavery.",
    "We're moving from a centralized understanding of the world to a decentralized understanding of the world.",
    "This Bitcoin currency is a voluntary decentralized currency, anonymous. It can't be shut down by anyone; there are no central servers.",
    "Absorb what is useful, discard what is useless and add what is specifically your own.",
    "The more we value things, the less we value ourselves.",
    "The successful warrior is the average man, with laser-like focus.",
    "In the middle of chaos lies opportunity.",
    "The key to immortality is first living a life worth remembering.",
    "When the mind is calm, how quickly, how smoothly, how beautifully you will perceive everything.",
    "Be kind to others, so that you may learn the secret art of being kind to yourself.",
    "Little stones that are pelted into the lake of consciousness should not throw the whole lake into commotion.",
    "I will not let anyone walk through my mind with their dirty feet.",
    "To believe in something, and not to live it, is dishonest.",
    "Truth never damages a cause that is just.",
    "Whenever you are confronted with an opponent. Conquer him with love.",
    "Strength does not come from physical capacity. It comes from an indomitable will.",
    "My Life is My Message.",
    "Love is the strongest force the world possesses and yet it is the humblest imaginable.",
    "A coward is incapable of exhibiting love, it is the prerogative of the brave.",
    "Speak only if it improves upon the silence.",
    "No one saves us but ourselves. No one can and no one may. We ourselves must walk the path.",
    "Live quietly in the moment and see the beauty of all before you. The future will take care of itself.",
    "The Way is not in the sky; the Way is in the heart.",
    "Peace comes from within. Do not seek it without.",
    "You will not be punished for your anger, you will be punished by your anger.",
    "The mind is everything. What you think you become.",
    "Better than worshiping gods is obedience to the laws of righteousness.",
    "A jug fills drop by drop.",
    "All wrong-doing arises because of mind. If mind is transformed can wrong-doing remain?",
    "Even death is not to be feared by one who has lived wisely.",
    "The journey of a thousand miles begins with one step.",
    "Great acts are made up of small deeds.",
    "He who conquers others is strong, He who conquers himself is mighty.",
    "It does not matter how slowly you go as long as you do not stop.",
    "Everything has beauty, but not everyone sees it.",
    "Wherever you go, go with all your heart.",
    "Better a diamond with a flaw than a pebble without.",
    "The object of the superior man is truth.",
    "Cryptocurrency is such a powerful concept that it can almost overturn governments.",
]


# --- X11 automation backend (xdotool wrapper) -------------------------------
class Roblox:
    """Window activation and input injection for the Roblox window via xdotool.

    On Windows the original used WinActivate/WinWaitActive/Send. The X11
    equivalents: `xdotool search --name` + `windowactivate` to focus, then
    `key` / `type` to inject input into the focused window.
    """

    def __init__(self, title=WIN_TITLE):
        self.title = title
        self._win = None

    @staticmethod
    def available():
        return shutil.which("xdotool") is not None

    def _find(self):
        try:
            out = subprocess.run(
                ["xdotool", "search", "--name", self.title],
                capture_output=True, text=True, timeout=5,
            )
        except (subprocess.SubprocessError, OSError):
            return None
        ids = out.stdout.split()
        return ids[0] if ids else None

    def activate(self):
        """Focus the Roblox window. Returns True if it is active afterward."""
        self._win = self._find()
        if not self._win:
            return False
        try:
            subprocess.run(["xdotool", "windowactivate", "--sync", self._win],
                           capture_output=True, timeout=5)
        except (subprocess.SubprocessError, OSError):
            return False
        return True

    def key(self, keyspec):
        """Send a key chord, e.g. 'Pause', 'Return', 'F12'."""
        try:
            subprocess.run(["xdotool", "key", "--clearmodifiers", keyspec],
                           capture_output=True, timeout=5)
        except (subprocess.SubprocessError, OSError):
            pass

    def type(self, text, delay_ms=30):
        """Type literal text with per-keystroke delay (mimics SendKeyDelay)."""
        try:
            subprocess.run(
                ["xdotool", "type", "--clearmodifiers", "--delay", str(delay_ms), text],
                capture_output=True, timeout=30,
            )
        except (subprocess.SubprocessError, OSError):
            pass


# --- Core automation engine -------------------------------------------------
class Engine:
    """Background worker thread reproducing RunnerFunc/awake/sayings/dance/record.

    Threading model differs from the original AutoIt single-loop design: the
    GUI runs on the main thread and the automation loop runs on a daemon
    thread, coordinated by a threading.Event stop flag.
    """

    def __init__(self, app):
        self.app = app
        self.rbx = Roblox()
        self._stop = threading.Event()
        self._thread = None

        # feature toggles
        self.wisdom = False
        self.dance = False
        self.record_want = False   # user asked to record
        self.recording = False     # F12 toggled on

        # slow-counters (anti-detection cadence), same names as original
        self.awake_slowly = 0
        self.speak_slowly = 0
        self.dance_slowly = 0
        self.quiet = 0
        self.cycles = 0
        self.last_saying = 18

    # --- lifecycle ---
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        if self.running():
            return
        self._stop.clear()
        self.cycles = 0
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _sleep(self, seconds):
        """Interruptible sleep; returns False if a stop was requested."""
        return not self._stop.wait(seconds)

    # --- main loop ---
    def _run(self):
        # begin recording once at start if requested
        if self.record_want:
            self._record_start()

        while not self._stop.is_set():
            self._awake()
            if self._stop.is_set():
                break
            if self.dance:
                self.app.set_dancing(True)
                self._dance()
            if self.wisdom:
                self.app.set_speaking(True)
                self._sayings()
                if self.quiet >= random.randint(195, 205):
                    self._quiet()
            self.cycles += 1
            self.app.set_cycles(self.cycles)

        self._on_stopped()

    # --- behaviors (ports of the AutoIt funcs) ---
    def _awake(self):
        # original slept 3000ms then poked the window
        if not self._sleep(3.0):
            return
        if self.awake_slowly == 0:
            if self.rbx.activate():
                self.rbx.key("Pause")   # {BREAK} on Windows == Pause/Break key
        self.awake_slowly += 1
        if self.awake_slowly >= random.randint(20, 27):
            self.awake_slowly = 0

    def _sayings(self):
        self.quiet += 1
        idx = random.randint(0, len(WISDOM) - 1)
        if idx == self.last_saying:
            idx = random.randint(0, len(WISDOM) - 1)
        saying = WISDOM[idx]
        self.last_saying = idx
        if self.speak_slowly == 0:
            if self.rbx.activate():
                # Roblox chat: '/' opens chat, then the text, then Enter
                self.rbx.type("/" + saying, delay_ms=30)
                self.rbx.key("Return")
        self.speak_slowly += 1
        if self.speak_slowly >= random.randint(36, 42):
            self.speak_slowly = 0

    def _dance(self):
        if self.dance_slowly == 0:
            if self.rbx.activate():
                self.rbx.key("Pause")
                self.rbx.type("//e dance", delay_ms=30)
                self.rbx.key("Return")
        self.dance_slowly += 1
        if self.dance_slowly >= random.randint(50, 70):
            self.dance_slowly = 0

    def _stop_dance(self):
        if self.rbx.activate():
            for k in ("Up", "Down", "Up", "Down"):
                self.rbx.key(k)
        self.dance = False
        self.dance_slowly = 0

    def _record_start(self):
        if self.rbx.activate():
            self.rbx.key("F12")
            self.recording = True
            self.app.set_recording(True)

    def _record_stop(self):
        if self.recording and self.rbx.activate():
            self.rbx.key("F12")
        self.recording = False
        self.app.set_recording(False)

    def _quiet(self):
        # respectfully stop speaking after ~200 cycles, re-enable the button
        self.wisdom = False
        self.speak_slowly = 0
        self.quiet = 0
        self.app.set_speaking(False)
        self.app.enable_wisdom_btn()

    def _on_stopped(self):
        # runs on the worker thread as it exits; marshal UI back to main thread
        self._stop_dance()
        if self.recording:
            self._record_stop()
        self.awake_slowly = 0
        self.speak_slowly = 0
        self.wisdom = False
        self.recording = False
        self.record_want = False
        self.app.on_engine_stopped()


# --- GUI --------------------------------------------------------------------
class App:
    def __init__(self, root):
        self.root = root
        self.engine = Engine(self)
        root.title("Roboss")
        root.configure(bg="#000000")
        root.geometry("360x230")
        root.resizable(False, False)

        btn = dict(width=12, bg="#222222", fg="#ffffff",
                   activebackground="#444444", activeforeground="#ffffff",
                   relief="raised", bd=2)

        self.wise_btn = tk.Button(root, text="SpeakWisdom", command=self.on_wisdom, **btn)
        self.wise_btn.place(x=10, y=10)
        self.dance_btn = tk.Button(root, text="Dance", command=self.on_dance, **btn)
        self.dance_btn.place(x=10, y=50)
        self.record_btn = tk.Button(root, text="Record", command=self.on_record, **btn)
        self.record_btn.place(x=10, y=90)

        self.run_btn = tk.Button(root, text="Start!", command=self.on_start, **btn)
        self.run_btn.place(x=170, y=10)
        self.stop_btn = tk.Button(root, text="Stop", command=self.on_stop, **btn)
        self.stop_btn.place(x=170, y=10)
        self.stop_btn.place_forget()

        lbl = dict(bg="#000000", fg="#ff0000", anchor="w")
        self.recording_lbl = tk.Label(root, text="Recording: No", **lbl)
        self.recording_lbl.place(x=170, y=55)
        self.speaking_lbl = tk.Label(root, text="Speaking: No", **lbl)
        self.speaking_lbl.place(x=10, y=140)
        self.dancing_lbl = tk.Label(root, text="Dancing: No", **lbl)
        self.dancing_lbl.place(x=10, y=162)
        self.cycles_lbl = tk.Label(root, text="RunCycles: 0", **lbl)
        self.cycles_lbl.place(x=10, y=184)

        # optional mascot image (Roboss.jpg), like the original GUICtrlCreatePic.
        # tkinter's built-in PhotoImage can't decode JPEG, so prefer Pillow.
        self._img = self._load_mascot()
        if self._img is not None:
            tk.Label(root, image=self._img, bg="#000000").place(x=250, y=95)

        if not Roblox.available():
            self.status = tk.Label(
                root, text="xdotool not found — install it",
                bg="#000000", fg="#ffaa00", anchor="w")
            self.status.place(x=170, y=185)

        root.protocol("WM_DELETE_WINDOW", self.on_exit)

    def _load_mascot(self):
        if not os.path.exists(ROBOSS_JPG):
            return None
        try:
            from PIL import Image, ImageTk
            img = Image.open(ROBOSS_JPG)
            img.thumbnail((93, 124))
            return ImageTk.PhotoImage(img)
        except Exception:
            pass
        try:
            return tk.PhotoImage(file=ROBOSS_JPG)  # works for PNG/GIF only
        except tk.TclError:
            return None

    # --- thread-safe UI setters (called from worker thread) ---
    def set_speaking(self, on):
        self.root.after(0, lambda: self.speaking_lbl.config(
            text="Speaking: " + ("Yes" if on else "No")))

    def set_dancing(self, on):
        self.root.after(0, lambda: self.dancing_lbl.config(
            text="Dancing: " + ("Yes" if on else "No")))

    def set_recording(self, on):
        self.root.after(0, lambda: self.recording_lbl.config(
            text="Recording: " + ("Yes" if on else "No")))

    def set_cycles(self, n):
        self.root.after(0, lambda: self.cycles_lbl.config(text="RunCycles: " + str(n)))

    def enable_wisdom_btn(self):
        self.root.after(0, lambda: self.wise_btn.config(state="normal"))

    # --- button handlers ---
    def on_wisdom(self):
        self.engine.wisdom = True
        self.wise_btn.config(state="disabled")

    def on_dance(self):
        self.engine.dance = True
        self.dance_btn.config(state="disabled")

    def on_record(self):
        self.engine.record_want = True
        self.record_btn.config(state="disabled")

    def on_start(self):
        self.run_btn.place_forget()
        self.stop_btn.place(x=170, y=10)
        self.engine.start()

    def on_stop(self):
        self.engine.stop()

    def on_engine_stopped(self):
        # marshalled to main thread
        def finish():
            self.stop_btn.place_forget()
            self.run_btn.place(x=170, y=10)
            self.wise_btn.config(state="normal")
            self.dance_btn.config(state="normal")
            self.record_btn.config(state="normal")
            self.set_speaking(False)
            self.set_dancing(False)
            self.set_recording(False)
            self.cycles_lbl.config(text="RunCycles: 0")
        self.root.after(0, finish)

    def on_exit(self):
        self.engine.stop()
        self.root.after(200, self.root.destroy)


def main():
    if sys.platform.startswith("win"):
        print("This is the Linux port. On Windows, use the original Roboss.au3/.exe.")
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
