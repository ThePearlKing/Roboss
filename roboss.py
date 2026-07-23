#!/usr/bin/env python3
"""Roboss — Roblox automation, Linux port.

Original: AutoIt (Windows) by Matt Brassey. This is a functional port to Linux
using tkinter for the GUI and xdotool for window activation and key/text
injection under X11.

Requires: xdotool (`sudo apt install xdotool`), an X11 session.
Wayland is not supported for key injection (xdotool needs X11 / XWayland).
"""

import json
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request

WIN_TITLE = "Roblox"          # substring matched against window titles

# Window matchers tried in order. Sober (VinegarHQ) is the Roblox client on
# Linux; its window is titled "Sober" with WM_CLASS org.vinegarhq.Sober, so a
# plain --name "Roblox" search never finds it. Match its class first, then fall
# back to name matches for the web player / other clients.
#   (xdotool search flag, pattern)
WIN_MATCHERS = [
    ("--class", "org.vinegarhq.Sober"),   # Sober (Roblox on Linux)
    ("--class", "Sober"),
    ("--name", "Roblox"),                 # web player, Grapejuice/wine, etc.
    ("--name", "Sober"),
]
ASSET_DIR = os.path.dirname(os.path.abspath(__file__))
ROBOSS_JPG = os.path.join(ASSET_DIR, "Roboss.jpg")
SACA_PNG = os.path.join(ASSET_DIR, "sacabambaspis_transparent.png")

# where saved robobaspis configs live (one JSON per robobaspis)
CONFIG_DIR = os.path.join(ASSET_DIR, "robobaspis")
DEFAULT_OLLAMA_URL = "http://localhost:11434"

# max_steps at or beyond this (or <= 0) means "run forever" and shows the ∞ icon
INF_STEPS = 100000


def steps_infinite(value):
    try:
        v = int(float(value))
    except (ValueError, TypeError):
        return False
    return v <= 0 or v >= INF_STEPS

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

    def __init__(self, title=WIN_TITLE, matchers=WIN_MATCHERS):
        self.title = title
        self.matchers = matchers
        self._win = None

    @staticmethod
    def available():
        return shutil.which("xdotool") is not None

    def _search(self, flag, pattern, only_visible=True):
        cmd = ["xdotool", "search"]
        if only_visible:
            cmd.append("--onlyvisible")
        cmd += [flag, pattern]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        except (subprocess.SubprocessError, OSError):
            return []
        return out.stdout.split()

    def _find(self):
        # Try each matcher, visible windows first; fall back to any window.
        for only_visible in (True, False):
            for flag, pattern in self.matchers:
                ids = self._search(flag, pattern, only_visible)
                if ids:
                    return ids[-1]   # topmost/last is the real toplevel
        return None

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

    def keys(self, keyseq, delay_ms=30):
        """Send several key presses rapidly in ONE xdotool call (low overhead)."""
        keyseq = [k for k in keyseq if k]
        if not keyseq:
            return
        try:
            subprocess.run(
                ["xdotool", "key", "--clearmodifiers", "--delay",
                 str(int(delay_ms))] + list(keyseq),
                capture_output=True, timeout=20)
        except (subprocess.SubprocessError, OSError, ValueError):
            pass

    def reset_character(self, gap=0.4):
        """Roblox reset: Escape, then R, then Enter — with a gap between each
        so they are not registered simultaneously."""
        for k in ("Escape", "r", "Return"):
            self.key(k)
            time.sleep(gap)

    def hold_key(self, keyspec, seconds):
        """Hold a key down for `seconds` (WASD movement etc.)."""
        seconds = max(0.05, min(float(seconds), 6.0))
        try:
            subprocess.run(["xdotool", "keydown", keyspec],
                           capture_output=True, timeout=5)
            time.sleep(seconds)
        except (subprocess.SubprocessError, OSError):
            pass
        finally:
            try:
                subprocess.run(["xdotool", "keyup", keyspec],
                               capture_output=True, timeout=5)
            except (subprocess.SubprocessError, OSError):
                pass

    def click(self, button=1):
        """Click a mouse button at the current pointer position."""
        try:
            subprocess.run(["xdotool", "click", str(button)],
                           capture_output=True, timeout=5)
        except (subprocess.SubprocessError, OSError):
            pass

    def click_at(self, x, y, button=1):
        """Move the pointer to absolute screen (x, y) and click."""
        try:
            subprocess.run(["xdotool", "mousemove", "--sync",
                            str(int(x)), str(int(y))],
                           capture_output=True, timeout=5)
            subprocess.run(["xdotool", "click", str(button)],
                           capture_output=True, timeout=5)
        except (subprocess.SubprocessError, OSError, ValueError):
            pass

    def geometry(self):
        """Absolute (x, y, w, h) of the Roblox window, or None."""
        win = self._win or self._find()
        if not win:
            return None
        try:
            out = subprocess.run(
                ["xdotool", "getwindowgeometry", "--shell", win],
                capture_output=True, text=True, timeout=5).stdout
        except (subprocess.SubprocessError, OSError):
            return None
        g = {}
        for line in out.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                g[k.strip()] = v.strip()
        try:
            return int(g["X"]), int(g["Y"]), int(g["WIDTH"]), int(g["HEIGHT"])
        except (KeyError, ValueError):
            return None

    def capture_image(self):
        """Return a full-resolution PIL image of ONLY the Roblox window's own
        pixels (overlapping windows are not captured), or None.

        Prefers Xlib get_image on the window id; falls back to a full-screen
        grab cropped to the window rect."""
        win = self._win or self._find()
        if win:
            try:
                from Xlib import X, display as _display
                from PIL import Image
                d = _display.Display()
                try:
                    wobj = d.create_resource_object("window", int(win))
                    g = wobj.get_geometry()
                    raw = wobj.get_image(0, 0, g.width, g.height,
                                         X.ZPixmap, 0xffffffff)
                    img = Image.frombytes("RGB", (g.width, g.height),
                                          raw.data, "raw", "BGRX")
                finally:
                    d.close()
                return img
            except Exception:
                pass
        geo = self.geometry()
        if not geo:
            return None
        x, y, w, h = geo
        full = "/tmp/.roboss_full.png"
        try:
            subprocess.run(["gnome-screenshot", "-f", full],
                           capture_output=True, timeout=10)
            from PIL import Image
            img = Image.open(full).crop((x, y, x + w, y + h)).copy()
            os.remove(full)
            return img
        except Exception:
            return None

    def screenshot(self, path, max_w=1000, region=None):
        """Save a PNG of the Roblox window (optionally a sub-REGION) to `path`,
        downscaled to <= max_w wide. Returns (win_w, win_h) or None.

        `region` is a (x0, y0, x1, y1) box in window percentages (0-100); when
        given, only that area is captured — cropped from the FULL-resolution
        grab so small details stay sharp (a zoom/magnify). Callers report
        positions as full-window percentages, so the crop is transparent."""
        img = self.capture_image()
        if img is None:
            return None
        win_w, win_h = img.width, img.height
        if region:
            x0, y0, x1, y1 = region
            box = (round(win_w * x0 / 100), round(win_h * y0 / 100),
                   round(win_w * x1 / 100), round(win_h * y1 / 100))
            if box[2] > box[0] and box[3] > box[1]:
                img = img.crop(box)
        if img.width > max_w:
            img = img.resize((max_w, round(img.height * max_w / img.width)))
        try:
            img.save(path)
        except OSError:
            return None
        return win_w, win_h

    def click_pct(self, xpct, ypct, button=1):
        """Click at a position given as percentages (0-100) of the window,
        mapped to absolute screen coordinates."""
        geo = self.geometry()
        if not geo:
            return
        x, y, w, h = geo
        sx = x + max(0.0, min(float(xpct), 100.0)) / 100.0 * w
        sy = y + max(0.0, min(float(ypct), 100.0)) / 100.0 * h
        self.click_at(sx, sy, button)

    def drag_right(self, dx, dy=0, steps=24, duration=0.45):
        """Rotate the camera with a smooth right-mouse drag (Roblox camera pan).

        The drag is split into many small relative moves with a short sleep
        between each so the camera glides instead of teleporting. Fractional
        per-step remainders are carried so the total travel is exact.
        """
        try:
            subprocess.run(["xdotool", "mousedown", "3"],
                           capture_output=True, timeout=5)
            per = max(duration / steps, 0.0)
            acc_x = acc_y = 0.0
            done_x = done_y = 0
            for i in range(1, steps + 1):
                acc_x = dx * i / steps
                acc_y = dy * i / steps
                mx = round(acc_x) - done_x
                my = round(acc_y) - done_y
                done_x += mx
                done_y += my
                if mx or my:
                    subprocess.run(
                        ["xdotool", "mousemove_relative", "--sync", "--",
                         str(mx), str(my)], capture_output=True, timeout=5)
                if per:
                    time.sleep(per)
            subprocess.run(["xdotool", "mouseup", "3"],
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
        self.jump = False
        self.camera = False
        self.record_want = False   # user asked to record
        self.recording = False     # F12 toggled on

        # slow-counters (anti-detection cadence), same names as original
        self.awake_slowly = 0
        self.speak_slowly = 0
        self.dance_slowly = 0
        self.jump_slowly = 0
        self.camera_slowly = 0
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
            if self.jump:
                self.app.set_jumping(True)
                self._jump()
            if self.camera:
                self.app.set_camera(True)
                self._camera()
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

    def _jump(self):
        # jump once every ~13-20 loop passes (each pass ~3s), so roughly once a
        # minute, jittered to look organic. space = jump in Roblox.
        if self.jump_slowly == 0:
            if self.rbx.activate():
                self.rbx.key("space")
        self.jump_slowly += 1
        if self.jump_slowly >= random.randint(13, 20):
            self.jump_slowly = 0

    def _camera(self):
        # tilt the camera a tiny bit every ~15-25 passes (~45-75s) with a small
        # right-mouse drag, jittered in direction/amount to look organic.
        if self.camera_slowly == 0:
            if self.rbx.activate():
                dx = random.choice((-1, 1)) * random.randint(20, 45)
                dy = random.randint(-8, 8)
                self.rbx.drag_right(dx, dy)
        self.camera_slowly += 1
        if self.camera_slowly >= random.randint(15, 25):
            self.camera_slowly = 0

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
        self.jump_slowly = 0
        self.camera_slowly = 0
        self.wisdom = False
        self.jump = False
        self.camera = False
        self.recording = False
        self.record_want = False
        self.app.on_engine_stopped()


# --- Ollama LLM client ------------------------------------------------------
class Ollama:
    """Minimal client for a local Ollama server (stdlib urllib, no deps)."""

    def __init__(self, url=DEFAULT_OLLAMA_URL):
        self.url = url.rstrip("/")

    def _post(self, path, payload, timeout=120):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.url + path, data=data,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def list_models(self, timeout=5):
        try:
            req = urllib.request.Request(self.url + "/api/tags")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
            return [m["name"] for m in data.get("models", [])]
        except (urllib.error.URLError, OSError, ValueError, KeyError):
            return []

    def reachable(self):
        return bool(self.list_models())

    def chat(self, model, messages, temperature=0.7, timeout=120):
        """Non-streaming chat completion. Returns the assistant text."""
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "think": False,               # qwen3 etc.: skip <think> when supported
            "options": {"temperature": float(temperature)},
        }
        out = self._post("/api/chat", payload, timeout=timeout)
        return out.get("message", {}).get("content", "")

    def vision(self, model, prompt, image_path, timeout=120):
        """Ask a vision model about an image. Returns the description text."""
        import base64
        with open(image_path, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode("ascii")
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt, "images": [b64]}],
            "stream": False,
            "keep_alive": "10m",           # keep the vision model warm between looks
            "options": {
                "temperature": 0.2,
                "num_ctx": 4096,           # smaller image fits; less to process
                "num_predict": 220,        # cap the description length for speed
            },
        }
        out = self._post("/api/chat", payload, timeout=timeout)
        return out.get("message", {}).get("content", "")


# --- robobaspis config persistence ------------------------------------------
DEFAULT_CONFIG = {
    "name": "baspis",
    "model": "qwen3:latest",
    "vision_model": "qwen2.5vl:3b",
    "url": DEFAULT_OLLAMA_URL,
    "personality": ("You are a curious, playful Sacabambaspis fish robot. "
                    "You like to explore and interact with the world."),
    "goal": "Wander around, look at your surroundings, and jump now and then.",
    "temperature": 0.7,
    "max_steps": 40,
    # which window this baspis drives. Empty target_match => auto Roblox/Sober.
    "target_label": "Roblox / Sober (auto)",
    "target_by": "name",       # "name" or "class"
    "target_match": "",        # substring; empty = use the Roblox/Sober matchers
}

AUTO_TARGET_LABEL = "Roblox / Sober (auto)"


def target_matchers(cfg):
    """Build xdotool search matchers for a baspis's chosen target window."""
    match = (cfg.get("target_match") or "").strip()
    if not match:
        return WIN_MATCHERS                       # auto Roblox/Sober
    flag = "--class" if cfg.get("target_by") == "class" else "--name"
    return [(flag, match)]


def list_windows():
    """Return [(title, wm_class, id)] of normal top-level windows (for the
    target picker), skipping panels/docks and our own Roboss window."""
    if shutil.which("wmctrl") is None:
        return []
    try:
        out = subprocess.run(["wmctrl", "-lx"], capture_output=True,
                             text=True, timeout=5).stdout
    except (subprocess.SubprocessError, OSError):
        return []
    wins = []
    for line in out.splitlines():
        parts = line.split(None, 4)
        if len(parts) < 4:
            continue
        wid, desktop, wmclass, host = parts[:4]
        title = parts[4].strip() if len(parts) >= 5 else ""
        if desktop == "-1":              # panels, docks, desktop
            continue
        if title == "Roboss":            # skip ourselves
            continue
        wins.append((title, wmclass, wid))
    return wins


def _safe_name(name):
    keep = "".join(c if c.isalnum() or c in "-_ " else "" for c in name).strip()
    return (keep or "baspis").replace(" ", "_")


def list_configs():
    try:
        names = [f[:-5] for f in os.listdir(CONFIG_DIR) if f.endswith(".json")]
    except OSError:
        return []
    return sorted(names)


def save_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    name = _safe_name(cfg.get("name", "baspis"))
    cfg = dict(cfg)
    cfg["name"] = name
    with open(os.path.join(CONFIG_DIR, name + ".json"), "w") as f:
        json.dump(cfg, f, indent=2)
    return name


def load_config(name):
    with open(os.path.join(CONFIG_DIR, _safe_name(name) + ".json")) as f:
        cfg = json.load(f)
    merged = dict(DEFAULT_CONFIG)
    merged.update(cfg)
    return merged


def delete_config(name):
    try:
        os.remove(os.path.join(CONFIG_DIR, _safe_name(name) + ".json"))
        return True
    except OSError:
        return False


# --- Autonomous agent (LLM -> Roblox actions) -------------------------------
SYSTEM_TMPL = """You are {name}, a Sacabambaspis robot that autonomously \
controls an application window on Linux by looking at it and sending mouse/key \
input. The window you are controlling is: {target}. You act by emitting ONE \
action at a time as a single JSON object; after each action you get an \
acknowledgement, then you emit the next one.

Personality / instructions:
{personality}

Your current goal:
{goal}

You are blind BETWEEN look-ups: use the "see" action to capture the window and \
get a description whenever it matters. USE "see" BEFORE clicking a button/menu, \
using a tool, answering an on-screen prompt, or reading numbers. Respond with \
EXACTLY ONE JSON object and NOTHING else -- no prose, no markdown, no fences.

CLICKING -- to press an on-screen BUTTON, MENU, or ICON, prefer "click_object" \
with a short description of the target (e.g. {{"action":"click_object","args":\
{{"target":"the chest button","region":"bottom-center"}}}}). It finds the target \
and clicks its exact center for you -- this is far more accurate than guessing \
coordinates. For a small target, also pass a "region" to zoom in for precision. \
Only use raw "click" with xpct/ypct if you already have exact coordinates. Do \
NOT hunt for a keyboard shortcut for buttons -- buttons are clicked. Only use \
"key" when the screen literally shows a key prompt.

BLIND CLICK -- if the human tells you NOT to move the mouse (e.g. "blind click", \
"don't move, just click", "click where my cursor is"), you MUST use \
"click_here" (clicks the current mouse position and never moves the pointer). \
Do NOT use click_object/click/coordinates in that case -- obey exactly.

SMALL THINGS: if you are hunting a small object/icon (a little chest, item, \
collectible, or tool slot) and the full view is too coarse, ZOOM by setting \
see's "region" to the part to inspect. region is one of: top, bottom, left, \
right, center, top-left, top-right, bottom-left, bottom-right, bottom-center, \
hotbar, or an explicit [x0,y0,x1,y1] box in %. Positions are STILL reported as \
percentages of the full window. "see" also describes your surroundings and \
roughly where you are.

IMPORTANT -- you are blind after you act. Clicking, opening/closing a menu, \
moving, or resetting CHANGES the screen, so your last look is stale. After any \
such action your NEXT action should usually be "see" to observe the result \
(e.g. confirm a menu opened and read inside it). NEVER answer about a menu or \
screen from memory -- "see" first, THEN report. To answer what is in a menu: \
see (find the button) -> click it -> see again (read the opened menu) -> answer.

Within one unchanged screen, one "see" already lists everything, so don't "see" \
twice in a row without acting. Pass the (x%, y%) it reports straight to "click" \
as xpct/ypct. Don't guess positions.

You may get a "PLAYER MESSAGE" from the human at any time -- treat it as new \
instructions/information and adapt.

If the target is a ROBLOX game: "move" walks (WASD), "look" turns the camera, \
tool/hotbar slots are small at the very bottom-CENTER (use region "hotbar" to \
read them), "say" opens chat, and "reset" (Escape,R,Enter) KILLS and respawns \
your character -- use it only to get unstuck. For non-game apps, prefer see + \
click + key and ignore move/look/jump/reset.

Schema (the optional "text" is spoken aloud in your speech bubble):
{{"thought": "<short reasoning>", "text": "<optional words to say>", "action": "<name>", "args": {{ ... }}}}

For a COMPLICATED multi-step routine (a movement pattern, repeated jumps, a \
little dance, grinding the same steps) you may PROGRAM IT YOURSELF in one \
"sequence" action instead of emitting each step: give a "steps" list of actions, \
an optional "repeat" count, "shuffle": true to randomize order, and any numeric \
arg may be a [min,max] range that is randomized each run. Example: \
{{"action":"sequence","args":{{"repeat":3,"steps":[{{"action":"move","args":\
{{"direction":"forward","seconds":[0.5,1.5]}}}},{{"action":"jump"}},{{"action":\
"look","args":{{"direction":"left","amount":[20,60]}}}}]}}}}. Use sequences ONLY \
for such routines; for a single step just emit that one action, and never bury \
"see"/"click_object" reactions inside a long blind sequence.

FAST / TIMING: for fast-paced combos put them in ONE "sequence" -- it focuses \
the window once and runs steps back-to-back with no delay (much faster than \
separate actions). For a rapid burst of key presses use "keys" (all sent in one \
go). Add "gap" seconds to a sequence only if you WANT it slower/paced.

Available actions:
- sequence     args: {{"steps":[<action>,...], "repeat":<int>, "shuffle":<bool>, "gap":<seconds, 0=fastest>}}  # program a routine (numeric args may be [min,max])
- keys         args: {{"keys":["w","a","s","d"], "delay":<ms>}}                  # fast burst of key presses in one call
- see          args: {{"query": "<what to look for>", "region": "<optional zoom area>"}}
- click_object args: {{"target": "<what to click>", "region": "<optional zoom area>"}}  # locate + click its center (accurate)
- click_here   args: {{}}                                                       # click the CURRENT mouse spot without moving (blind click)
- click        args: {{"xpct": <0-100>, "ypct": <0-100>}}                       # click exact % position (only if you have precise coords)
- move   args: {{"direction": "forward|back|left|right", "seconds": <0.2-3>}}   # game movement (WASD)
- look   args: {{"direction": "left|right|up|down", "amount": <10-120>}}        # turn game camera
- jump   args: {{}}
- reset  args: {{}}   # ROBLOX ONLY -- DEATH+RESPAWN (Escape,R,Enter); kills your character to get unstuck. NOT a settings/app reset.
- key    args: {{"key": "<single key, e.g. e, f, 1, space, ctrl+s>"}}           # press a key / shortcut
- say    args: {{"text": "<chat message>"}}                                     # game chat
- wait   args: {{"seconds": <0.2-5>}}
- done   args: {{}}                                                             # goal complete, stop

Emit only one JSON object."""


def extract_json(text):
    """Pull the first balanced JSON object out of an LLM reply."""
    if not text:
        return None
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"```(?:json)?", "", text)
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except ValueError:
                    return None
    return None


class Agent:
    """Background LLM control loop: think -> act on the Roblox window -> repeat."""

    MOVE_KEYS = {"forward": "w", "back": "s", "left": "a", "right": "d"}

    def __init__(self, app, cfg):
        self.app = app
        self.cfg = cfg
        self.rbx = Roblox(matchers=target_matchers(cfg))
        self.ollama = Ollama(cfg.get("url", DEFAULT_OLLAMA_URL))
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._inbox = []                 # pending player messages
        self._inbox_lock = threading.Lock()
        self._thread = None

    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def paused(self):
        return self._pause.is_set()

    def toggle_pause(self):
        """Pause/resume without losing state. Returns the new paused flag."""
        if self._pause.is_set():
            self._pause.clear()
        else:
            self._pause.set()
        return self._pause.is_set()

    def tell(self, text):
        """Queue a message to be delivered to the agent before its next step,
        without stopping it."""
        text = (text or "").strip()
        if text:
            with self._inbox_lock:
                self._inbox.append(text)

    def _drain_inbox(self):
        with self._inbox_lock:
            msgs, self._inbox = self._inbox, []
        return msgs

    def start(self):
        if self.running():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        cfg = self.cfg
        self.app.agent_active(True)
        try:
            system = SYSTEM_TMPL.format(
                name=cfg.get("name", "baspis"),
                personality=cfg.get("personality", ""),
                goal=cfg.get("goal", ""),
                target=cfg.get("target_label") or "a Roblox game (Sober)")
            messages = [{"role": "system", "content": system},
                        {"role": "user",
                         "content": "Begin. Emit your first action as one JSON object."}]
            max_steps = int(cfg.get("max_steps", 40))
            infinite = steps_infinite(max_steps)      # -1/0/huge => run forever
            steps_label = "∞" if infinite else str(max_steps)
            limit = 10 ** 9 if infinite else max_steps
            for step in range(1, limit + 1):
                if self._stop.is_set():
                    break
                # honour pause without dropping state
                announced = False
                while self._pause.is_set() and not self._stop.is_set():
                    if not announced:
                        self.app.agent_status(paused=True)
                        announced = True
                    self._stop.wait(0.2)
                if self._stop.is_set():
                    break
                # deliver any pending player messages before thinking
                for msg in self._drain_inbox():
                    self.app.agent_log("  ✉ player: %s" % msg)
                    messages.append({"role": "user",
                                     "content": "PLAYER MESSAGE: " + msg})
                self.app.agent_status(thinking=True)
                try:
                    reply = self.ollama.chat(
                        cfg["model"], messages,
                        temperature=cfg.get("temperature", 0.7))
                except (urllib.error.URLError, OSError, ValueError) as e:
                    self.app.agent_log("! ollama error: %s" % e)
                    break
                self.app.agent_status(thinking=False)
                if self._stop.is_set():
                    break

                action = extract_json(reply)
                if not action:
                    # still surface whatever the model said, so it "talks"
                    self.app.baspis_say(self._bubble_text({}, reply))
                    self.app.agent_log("! could not parse action; retrying")
                    messages.append({"role": "assistant", "content": reply})
                    messages.append({"role": "user", "content":
                        "That was not a single JSON object. Reply with exactly "
                        "one JSON action object."})
                    continue

                name = str(action.get("action", "")).lower()
                args = action.get("args") or {}
                thought = action.get("thought", "")
                self.app.baspis_say(self._bubble_text(action, reply))
                self.app.agent_log("[%d] %s -> %s %s" % (
                    step, thought, name, json.dumps(args)))
                self.app.agent_status(acting=True)

                if name == "done":
                    self.app.agent_log("* goal complete")
                    break
                result = self._do(name, args)
                self.app.agent_status(acting=False)

                messages.append({"role": "assistant", "content": reply})
                messages.append({"role": "user", "content":
                    "%s Step %d/%s done. Emit the next single JSON action, or "
                    "\"done\" if the goal is complete." % (result, step, steps_label)})
                # keep context bounded on long/infinite runs (drop old turns)
                if len(messages) > 40:
                    messages = [messages[0]] + messages[-24:]
            else:
                if not infinite:
                    self.app.agent_log("* reached max steps")
        finally:
            self.app.agent_active(False)
            self.app.on_agent_stopped()

    @staticmethod
    def _bubble_text(action, reply):
        """Pick the best line to show in the speech bubble, model-agnostically.

        Works whether the model puts words in "text", "say", "message",
        "thought", or "speech", or just returns plain prose (e.g. llama3)."""
        args = action.get("args") or {}
        for src in (action, args):
            for key in ("text", "say", "speech", "message", "thought"):
                v = src.get(key)
                if isinstance(v, str) and v.strip():
                    return v.strip()
        # plain-text fallback: first non-empty, non-JSON line of the raw reply
        cleaned = re.sub(r"<think>.*?</think>", "", reply or "", flags=re.DOTALL)
        for line in cleaned.splitlines():
            line = line.strip().strip("`")
            if line and not line.startswith("{") and not line.startswith("["):
                return line
        return "…"

    def _do(self, name, args, activate=True):
        """Execute one parsed action on the Roblox window. Returns a result str.

        `activate=False` skips the (slow) window-focus step -- used inside a
        sequence, which focuses once up front so fast routines aren't delayed by
        re-focusing on every step."""
        if name in ("sequence", "macro", "program"):
            return self._sequence(args)     # runs many sub-actions
        if activate and not self.rbx.activate():
            return "Could not focus the Roblox window (is it open?)."
        try:
            if name in ("keys", "combo", "tap"):
                ks = args.get("keys") or args.get("key") or []
                if isinstance(ks, str):
                    ks = ks.split()
                ks = [str(k).strip()[:20] for k in ks if str(k).strip()][:40]
                self.rbx.keys(ks, args.get("delay", 30))
                return "Pressed keys: %s" % " ".join(ks)
            if name == "see":
                return self._see(str(args.get("query", "")), args.get("region"))
            if name == "move":
                key = self.MOVE_KEYS.get(str(args.get("direction", "")).lower())
                if not key:
                    return "Unknown move direction."
                self.rbx.hold_key(key, args.get("seconds", 1.0))
                return "Moved %s." % args.get("direction")
            if name == "look":
                amt = max(5, min(int(args.get("amount", 40)), 200))
                d = str(args.get("direction", "")).lower()
                dx, dy = 0, 0
                if d == "left":
                    dx = -amt
                elif d == "right":
                    dx = amt
                elif d == "up":
                    dy = -amt
                elif d == "down":
                    dy = amt
                self.rbx.drag_right(dx, dy)
                return "Looked %s." % d
            if name == "jump":
                self.rbx.key("space")
                return "Jumped."
            if name == "reset":
                self.rbx.reset_character()
                return "Reset character (Escape, R, Enter)."
            if name == "key":
                k = str(args.get("key", "")).strip()[:20]
                if k:
                    self.rbx.key(k)
                return "Pressed %s." % k
            if name in ("click_object", "click_target", "find_and_click"):
                return self._click_object(str(args.get("target", "")),
                                          args.get("region"))
            if name in ("click_here", "blind_click", "clickhere"):
                self.rbx.click()      # click current pointer spot; never moves it
                return ("Blind-clicked at the current mouse position (mouse not "
                        "moved). The screen may have changed -- 'see' to check.")
            if name == "click":
                changed = " The screen may have changed -- use 'see' to observe the result."
                if "xpct" in args and "ypct" in args:
                    self.rbx.click_pct(args["xpct"], args["ypct"])
                    return ("Clicked at (%s%%, %s%%)." % (args["xpct"], args["ypct"])) + changed
                if "x" in args and "y" in args:
                    self.rbx.click_at(args["x"], args["y"])
                    return ("Clicked at (%s, %s)." % (args["x"], args["y"])) + changed
                self.rbx.click()
                return "Clicked." + changed
            if name == "say":
                text = str(args.get("text", ""))[:200]
                if text:
                    self.rbx.type("/" + text, delay_ms=20)
                    self.rbx.key("Return")
                return "Said it."
            if name == "wait":
                self._stop.wait(max(0.1, min(float(args.get("seconds", 1)), 8)))
                return "Waited."
            return "Unknown action '%s'." % name
        except (ValueError, TypeError) as e:
            return "Bad args: %s" % e

    # named zoom regions -> (x0, y0, x1, y1) in window percentages
    REGIONS = {
        "full": (0, 0, 100, 100),
        "top": (0, 0, 100, 55), "bottom": (0, 45, 100, 100),
        "left": (0, 0, 55, 100), "right": (45, 0, 100, 100),
        "center": (25, 25, 75, 75), "middle": (25, 25, 75, 75),
        "top-left": (0, 0, 55, 55), "top-right": (45, 0, 100, 55),
        "bottom-left": (0, 45, 55, 100), "bottom-right": (45, 45, 100, 100),
        "bottom-center": (25, 86, 75, 100), "bottom-middle": (25, 86, 75, 100),
        # Roblox tool/hotbar slots are small, centered horizontally and at the
        # very bottom vertically:
        "hotbar": (25, 88, 75, 100), "toolbar": (25, 88, 75, 100),
        "tools": (25, 88, 75, 100),
    }

    VISION_PROMPT = (
        "This is a screenshot of a Roblox game.{zoom} The player asks: {query}\n"
        "Answer concisely and factually about what is ACTUALLY visible. Include, "
        "when relevant:\n"
        "- Any on-screen key prompts (e.g. 'Press E to ...').\n"
        "- Buttons, menu items, icons, and SMALL objects (chests, items, "
        "collectibles, tool slots) -- look carefully, do not skip small ones. "
        "Give each a short label and its position as PERCENTAGES of the FULL "
        "game window, written as (x%, y%) where 0%,0% is top-left and "
        "100%,100% is bottom-right.\n"
        "- Money/cash/coins or other numbers, read exactly.\n"
        "- Your surroundings / where the character is: nearby objects, terrain, "
        "NPCs, landmarks, and roughly where you are in the world.\n"
        "If something is not visible, say so. Do not invent things.")

    def _resolve_region(self, region):
        """Return (bbox_or_None, label). Accepts a name or [x0,y0,x1,y1]%."""
        if region is None:
            return None, ""
        if isinstance(region, str):
            box = self.REGIONS.get(region.strip().lower())
            return (box if box and box != (0, 0, 100, 100) else None), region
        if isinstance(region, (list, tuple)) and len(region) == 4:
            try:
                box = tuple(max(0, min(float(v), 100)) for v in region)
                return box, "%s" % (box,)
            except (ValueError, TypeError):
                return None, ""
        return None, ""

    def _see(self, query, region=None):
        """Screenshot the window (optionally a zoomed region) and describe it."""
        model = self.cfg.get("vision_model") or DEFAULT_CONFIG["vision_model"]
        if model not in self.ollama.list_models():
            return ("Cannot see: vision model '%s' not installed "
                    "(try: ollama pull %s)." % (model, model))
        box, label = self._resolve_region(region)
        path = os.path.join(ASSET_DIR, ".baspis_view.png")
        wh = self.rbx.screenshot(path, region=box)
        if not wh:
            return "Could not capture the screen."
        zoom = (" This is a ZOOMED-IN crop of the '%s' area of the window; still "
                "report positions as percentages of the FULL window." % label
                if box else "")
        self.app.agent_status(seeing=True)
        try:
            desc = self.ollama.vision(
                model,
                self.VISION_PROMPT.format(
                    zoom=zoom, query=query or "Describe the screen and surroundings."),
                path)
        except (urllib.error.URLError, OSError, ValueError) as e:
            return "Vision error: %s" % e
        finally:
            self.app.agent_status(seeing=False)
            try:
                os.remove(path)
            except OSError:
                pass
        self.app.agent_log("  👁 %s" % desc.strip().replace("\n", " ")[:300])
        return "Saw the screen: " + desc.strip()

    LOCATE_PROMPT = (
        "Look at this image of an app/game window.{zoom} Find: {target}\n"
        "Reply with ONLY a JSON object and nothing else:\n"
        '{{"found": true or false, "x": <0-100>, "y": <0-100>}}\n'
        "where x,y are the CENTER of that target as a PERCENT of THIS image "
        "(x: 0=left,100=right; y: 0=top,100=bottom). If it is not visible, set "
        "found=false.")

    def _locate(self, model, target, box):
        """One vision localization pass. `box` = window-% crop (or None=full).
        Returns (win_x%, win_y%) or None if not found/failed."""
        path = os.path.join(ASSET_DIR, ".baspis_view.png")
        if not self.rbx.screenshot(path, region=box):
            return None
        zoom = " This is a tight zoomed-in crop; the target should be near the center." if box else ""
        try:
            reply = self.ollama.vision(
                model, self.LOCATE_PROMPT.format(zoom=zoom, target=target), path)
        except (urllib.error.URLError, OSError, ValueError):
            return None
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        obj = extract_json(reply) or {}
        if not obj.get("found"):
            return None
        try:
            ix, iy = float(obj["x"]), float(obj["y"])
        except (KeyError, ValueError, TypeError):
            return None
        if box:
            x0, y0, x1, y1 = box
            return x0 + ix / 100.0 * (x1 - x0), y0 + iy / 100.0 * (y1 - y0)
        return ix, iy

    def _click_object(self, target, region=None):
        """Locate a named target and click its exact center, using a
        COARSE-TO-FINE zoom: find it roughly, then re-look at a tight crop
        centered on the guess so the same model error shrinks to a few pixels.
        All crop->window mapping is done in code, not by the model."""
        if not target.strip():
            return "click_object needs a 'target' description."
        model = self.cfg.get("vision_model") or DEFAULT_CONFIG["vision_model"]
        if model not in self.ollama.list_models():
            return "Cannot see: vision model '%s' not installed." % model
        box, _label = self._resolve_region(region)
        self.app.agent_status(seeing=True)
        wx = wy = None
        try:
            # pass 0 = full (or given region); passes 1..2 = tight refine crops
            half = [(20.0, 16.0), (10.0, 9.0)]     # crop half-size per refine
            cur = box
            for i in range(3):
                loc = self._locate(model, target, cur)
                if loc is None:
                    break                          # keep the last good estimate
                wx, wy = loc
                if i >= len(half):
                    break
                hw, hh = half[i]
                nb = (max(0.0, wx - hw), max(0.0, wy - hh),
                      min(100.0, wx + hw), min(100.0, wy + hh))
                cur_w = 100.0 if cur is None else (cur[2] - cur[0])
                if (nb[2] - nb[0]) >= cur_w - 1:   # not actually zooming in
                    break
                cur = nb
        finally:
            self.app.agent_status(seeing=False)
        if wx is None:
            return ("Could not find '%s' on screen. Try a region zoom "
                    "(e.g. hotbar / bottom-center) or 'see' first." % target)
        self.rbx.click_pct(wx, wy)
        self.app.agent_log("  🎯 clicked '%s' at (%.1f%%, %.1f%%)" % (target, wx, wy))
        return ("Clicked '%s' at (%.1f%%, %.1f%%). The screen may have changed "
                "-- 'see' to confirm." % (target, wx, wy))

    @staticmethod
    def _resolve_random(args):
        """Resolve randomized args: any value that is a [min, max] number pair
        becomes a random value in that range (ints stay ints)."""
        if not isinstance(args, dict):
            return args
        out = {}
        for k, v in args.items():
            if (isinstance(v, list) and len(v) == 2
                    and all(isinstance(n, (int, float)) and not isinstance(n, bool)
                            for n in v)):
                lo, hi = min(v), max(v)
                if isinstance(v[0], int) and isinstance(v[1], int):
                    out[k] = random.randint(int(lo), int(hi))
                else:
                    out[k] = round(random.uniform(lo, hi), 2)
            else:
                out[k] = v
        return out

    def _sequence(self, args):
        """Run a self-programmed series of actions (a macro).

        args: {"steps": [ {action, args}, ... ], "repeat": <int>,
               "shuffle": <bool>}. Numeric step args may be [min,max] ranges,
               resolved to a random value each time -- so the baspis can build
               its own randomized routines. Not nestable; capped for safety."""
        steps = args.get("steps") or args.get("actions") or []
        if not isinstance(steps, list) or not steps:
            return "sequence needs a non-empty 'steps' list."
        try:
            repeat = max(1, min(int(args.get("repeat", 1)), 50))
        except (ValueError, TypeError):
            repeat = 1
        shuffle = bool(args.get("shuffle"))
        try:
            gap = max(0.0, min(float(args.get("gap", 0)), 2.0))   # pause between steps
        except (ValueError, TypeError):
            gap = 0.0
        # focus the window ONCE so fast routines aren't delayed by re-focusing
        # on every step
        self.rbx.activate()
        done = 0
        for _r in range(repeat):
            order = list(steps)
            if shuffle:
                random.shuffle(order)
            for st in order:
                if self._stop.is_set() or done >= 200:
                    break
                while self._pause.is_set() and not self._stop.is_set():
                    self._stop.wait(0.2)
                if not isinstance(st, dict):
                    continue
                sname = str(st.get("action", "")).lower()
                if sname in ("sequence", "macro", "program", "done", ""):
                    continue           # no nesting / no-ops inside a macro
                sargs = self._resolve_random(st.get("args") or {})
                res = self._do(sname, sargs, activate=False)
                done += 1
                self.app.agent_log("   • %s %s -> %s" % (
                    sname, json.dumps(sargs), res[:60]))
                if gap:
                    self._stop.wait(gap)
            if self._stop.is_set() or done >= 200:
                break
        return ("Ran a %d-action sequence (repeat=%d%s). The screen likely "
                "changed -- 'see' to observe the result."
                % (done, repeat, ", shuffled" if shuffle else ""))


# --- Global stop hotkey -----------------------------------------------------
class Hotkey:
    """A system-wide X hotkey (default Ctrl+Alt+S) that fires a callback from a
    background thread, even when Roblox (not Roboss) has focus."""

    def __init__(self, callback, key="s", ctrl=True, alt=True):
        self.callback = callback
        self.key = key
        self.ctrl = ctrl
        self.alt = alt
        self.combo = ("Ctrl+" if ctrl else "") + ("Alt+" if alt else "") + key.upper()
        self._run = False
        self._d = None

    def start(self):
        try:
            from Xlib import X, display, XK
        except Exception:
            return False
        try:
            self._d = display.Display()
            self._X = X
            root = self._d.screen().root
            self._root = root
            self._keycode = self._d.keysym_to_keycode(XK.string_to_keysym(self.key))
            mod = 0
            if self.ctrl:
                mod |= X.ControlMask
            if self.alt:
                mod |= X.Mod1Mask
            self._mod = mod
            # grab with lock-key variants so CapsLock/NumLock don't block it
            for extra in (0, X.LockMask, X.Mod2Mask, X.LockMask | X.Mod2Mask):
                root.grab_key(self._keycode, mod | extra, True,
                              X.GrabModeAsync, X.GrabModeAsync)
            self._d.sync()
        except Exception:
            return False
        self._run = True
        threading.Thread(target=self._loop, daemon=True).start()
        return True

    def _loop(self):
        X = self._X
        while self._run:
            try:
                ev = self._d.next_event()
            except Exception:
                break
            if ev.type == X.KeyPress and ev.detail == self._keycode:
                try:
                    self.callback()
                except Exception:
                    pass

    def stop(self):
        self._run = False
        try:
            self._root.ungrab_key(self._keycode, self._mod)
            self._d.close()
        except Exception:
            pass


# --- GUI --------------------------------------------------------------------
class App:
    NORMAL_GEO = "360x210"
    ROBOBOSS_GEO = "900x820"

    def __init__(self, root):
        self.root = root
        self.engine = Engine(self)
        self.agent = None
        self.mode = "normal"
        self.pinned = False
        self._pins = []          # pin toggle canvases to keep in sync
        root.title("Roboss")
        root.configure(bg="#000000")
        root.geometry(self.NORMAL_GEO)
        root.resizable(False, False)

        self.normal_frame = tk.Frame(root, bg="#000000")
        self.roboboss_frame = tk.Frame(root, bg="#0a0a0f")
        self._build_normal(self.normal_frame)
        self._build_roboboss(self.roboboss_frame)
        self.normal_frame.pack(fill="both", expand=True)

        # global stop hotkey (works even while the game is focused)
        self.hotkey = Hotkey(self._hotkey_stop)
        if self.hotkey.start():
            self.stop_hint_lbl.config(text="stop hotkey: %s" % self.hotkey.combo)

        root.protocol("WM_DELETE_WINDOW", self.on_exit)

    def _hotkey_stop(self):
        # fires on the hotkey thread; marshal to the Tk main thread
        self.root.after(0, self._do_hotkey_stop)

    def _do_hotkey_stop(self):
        stopped = False
        if self.agent and self.agent.running():
            self.agent.stop()
            stopped = True
        if self.engine.running():
            self.engine.stop()
            stopped = True
        if stopped:
            self.agent_log("* STOP hotkey (%s) pressed" % self.hotkey.combo)

    # ================= NORMAL MODE =================
    def _build_normal(self, f):
        btn = dict(width=12, bg="#222222", fg="#ffffff",
                   activebackground="#444444", activeforeground="#ffffff",
                   relief="raised", bd=2)

        self.wise_btn = tk.Button(f, text="SpeakWisdom", command=self.on_wisdom, **btn)
        self.wise_btn.place(x=10, y=10)
        self.dance_btn = tk.Button(f, text="Dance", command=self.on_dance, **btn)
        self.dance_btn.place(x=10, y=50)
        self.record_btn = tk.Button(f, text="Record", command=self.on_record, **btn)
        self.record_btn.place(x=10, y=90)
        self.jump_btn = tk.Button(f, text="Jump", command=self.on_jump, **btn)
        self.jump_btn.place(x=10, y=130)
        self.camera_btn = tk.Button(f, text="Camera", command=self.on_camera, **btn)
        self.camera_btn.place(x=10, y=170)

        self.run_btn = tk.Button(f, text="Start!", command=self.on_start, **btn)
        self.run_btn.place(x=170, y=10)
        self.stop_btn = tk.Button(f, text="Stop", command=self.on_stop, **btn)
        self.stop_btn.place(x=170, y=10)
        self.stop_btn.place_forget()

        # status labels stacked in the right column to keep the window short
        lbl = dict(bg="#000000", fg="#ff0000", anchor="w")
        self.recording_lbl = tk.Label(f, text="Recording: No", **lbl)
        self.recording_lbl.place(x=175, y=50)
        self.speaking_lbl = tk.Label(f, text="Speaking: No", **lbl)
        self.speaking_lbl.place(x=175, y=72)
        self.dancing_lbl = tk.Label(f, text="Dancing: No", **lbl)
        self.dancing_lbl.place(x=175, y=94)
        self.jumping_lbl = tk.Label(f, text="Jumping: No", **lbl)
        self.jumping_lbl.place(x=175, y=116)
        self.camera_lbl = tk.Label(f, text="Camera: No", **lbl)
        self.camera_lbl.place(x=175, y=138)
        self.cycles_lbl = tk.Label(f, text="RunCycles: 0", **lbl)
        self.cycles_lbl.place(x=175, y=160)

        # mascot image (Roboss.jpg); tkinter can't decode JPEG so prefer Pillow.
        self._img = self._load_mascot()
        if self._img is not None:
            tk.Label(f, image=self._img, bg="#000000").place(x=272, y=48)

        # mode switcher — a little circle icon tucked under the logo
        icon = self._icon_btn(f, "⇄", self.toggle_mode, bg="#000000")
        icon.place(x=298, y=168)
        # pin: keep Roboss floating above Roblox/Sober
        self._pin_icon(f, bg="#000000").place(x=262, y=168)

        if not Roblox.available():
            tk.Label(f, text="xdotool not found — install it",
                     bg="#000000", fg="#ffaa00", anchor="w").place(x=10, y=192)

    def _icon_btn(self, parent, symbol, command, fg="#66e0ff", bg="#000000", d=30):
        """A small round icon button drawn on a Canvas."""
        c = tk.Canvas(parent, width=d, height=d, bg=bg, highlightthickness=0,
                      cursor="hand2")
        oval = c.create_oval(2, 2, d - 2, d - 2, outline=fg, fill="#141420",
                             width=2)
        c.create_text(d / 2, d / 2 - 1, text=symbol, fill=fg,
                      font=("TkDefaultFont", int(d * 0.42), "bold"))
        c.bind("<Button-1>", lambda e: command())
        c.bind("<Enter>", lambda e: c.itemconfig(oval, fill="#22224a"))
        c.bind("<Leave>", lambda e: c.itemconfig(oval, fill="#141420"))
        return c

    def _pin_icon(self, parent, bg="#000000", d=30):
        """Round toggle that pins Roboss above other windows (on-top)."""
        c = tk.Canvas(parent, width=d, height=d, bg=bg, highlightthickness=0,
                      cursor="hand2")
        c.oval = c.create_oval(2, 2, d - 2, d - 2, outline="#55557a",
                               fill="#141420", width=2)
        c.txt = c.create_text(d / 2, d / 2 - 1, text="⇧", fill="#889",
                              font=("TkDefaultFont", int(d * 0.44), "bold"))
        c.bind("<Button-1>", lambda e: self.toggle_pin())
        self._pins.append(c)
        return c

    def toggle_pin(self):
        """Toggle always-on-top so you can watch Roboss while Sober keeps focus."""
        self.pinned = not self.pinned
        self.root.attributes("-topmost", self.pinned)
        self._apply_above(self.pinned)     # WM reinforcement (best effort)
        on, off = "#33ffcc", "#889"
        edge_on, edge_off = "#33ffcc", "#55557a"
        for c in self._pins:
            c.itemconfig(c.txt, fill=on if self.pinned else off)
            c.itemconfig(c.oval, outline=edge_on if self.pinned else edge_off)

    def _apply_above(self, on):
        """Also set _NET_WM_STATE_ABOVE via wmctrl (some WMs ignore -topmost)."""
        if shutil.which("wmctrl") is None:
            return
        op = "add,above" if on else "remove,above"
        wid = hex(self.root.winfo_id())
        try:
            subprocess.run(["wmctrl", "-i", "-r", wid, "-b", op],
                           capture_output=True, timeout=3)
        except (subprocess.SubprocessError, OSError):
            pass

    def _load_mascot(self):
        if not os.path.exists(ROBOSS_JPG):
            return None
        try:
            from PIL import Image, ImageTk
            img = Image.open(ROBOSS_JPG)
            img.thumbnail((78, 104))
            return ImageTk.PhotoImage(img)
        except Exception:
            pass
        try:
            import base64
            import io
            from PIL import Image
            img = Image.open(ROBOSS_JPG)
            img.thumbnail((78, 104))
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="PNG")
            return tk.PhotoImage(data=base64.b64encode(buf.getvalue()))
        except Exception:
            pass
        try:
            return tk.PhotoImage(file=ROBOSS_JPG)
        except tk.TclError:
            return None

    # ================= ROBOBOSS MODE =================
    def _build_roboboss(self, f):
        self._saca_dark, self._saca_lit = self._load_saca()

        ent = dict(bg="#15151f", fg="#e6e6f0", insertbackground="#e6e6f0",
                   relief="flat", highlightbackground="#26263a",
                   highlightthickness=1)
        lab = dict(bg="#0a0a0f", fg="#7a7a99", anchor="w")
        hdr = dict(bg="#0a0a0f", fg="#66e0ff",
                   font=("TkDefaultFont", 10, "bold"), anchor="w")
        card = dict(bg="#101018", bd=0, highlightbackground="#20203a",
                    highlightthickness=1)

        body = tk.Frame(f, bg="#0a0a0f")
        body.pack(fill="both", expand=True, padx=12, pady=12)
        body.grid_columnconfigure(0, minsize=280)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        # ============ LEFT: the robobaspis ============
        left = tk.Frame(body, **card)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        tk.Label(left, text="◈ ROBOBASPIS", bg="#101018", fg="#66e0ff",
                 font=("TkDefaultFont", 13, "bold")).pack(anchor="w",
                                                          padx=12, pady=(12, 4))

        # speech bubble — what the baspis is thinking / saying
        self.bubble = tk.Label(
            left, text="…", bg="#e8f4ff", fg="#0a0a0f", wraplength=232,
            justify="left", anchor="w", padx=8, pady=5, bd=0,
            font=("TkDefaultFont", 9))
        self.bubble.pack(padx=12, pady=(2, 0), fill="x")
        self.bubble_tail = tk.Label(left, text="▾", bg="#101018", fg="#e8f4ff",
                                    font=("TkDefaultFont", 12))
        self.bubble_tail.pack(anchor="w", padx=26)

        # glowing portrait
        self.baspis_wrap = tk.Frame(left, bg="#0c0c12", bd=0,
                                    highlightbackground="#1a1a26",
                                    highlightthickness=3)
        self.baspis_wrap.pack(padx=12, pady=4)
        self.baspis_lbl = tk.Label(self.baspis_wrap, bg="#0c0c12")
        if self._saca_dark is not None:
            self.baspis_lbl.config(image=self._saca_dark)
        else:
            self.baspis_lbl.config(text="(sacabambaspis)", fg="#334",
                                   width=26, height=9)
        self.baspis_lbl.pack()

        self.name_head = tk.Label(left, text=DEFAULT_CONFIG["name"],
                                  bg="#101018", fg="#e6e6f0",
                                  font=("TkDefaultFont", 12, "bold"))
        self.name_head.pack(anchor="w", padx=12, pady=(6, 0))
        self.conn_lbl = tk.Label(left, text="Connection: --", bg="#101018",
                                 fg="#7a7a99", anchor="w")
        self.conn_lbl.pack(fill="x", padx=12)
        self.state_lbl = tk.Label(left, text="State: idle", bg="#101018",
                                  fg="#66e0ff", anchor="w")
        self.state_lbl.pack(fill="x", padx=12)

        tk.Label(left, text="Saved robobaspis", bg="#101018", fg="#7a7a99",
                 anchor="w").pack(fill="x", padx=12, pady=(10, 0))
        listrow = tk.Frame(left, bg="#101018")
        listrow.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.saved_list = tk.Listbox(
            listrow, height=5, bg="#15151f", fg="#e6e6f0", relief="flat",
            highlightbackground="#26263a", highlightthickness=1,
            selectbackground="#2a2a55", exportselection=False)
        self.saved_list.pack(side="left", fill="both", expand=True)
        self.saved_list.bind("<Double-Button-1>", lambda e: self.rb_load())
        lbtns = tk.Frame(listrow, bg="#101018")
        lbtns.pack(side="left", fill="y", padx=(6, 0))
        sbtn = dict(width=7, bg="#1a1a28", fg="#cfe8ff",
                    activebackground="#2a2a48", relief="ridge", bd=1)
        tk.Button(lbtns, text="Save", command=self.rb_save,
                  **dict(sbtn, bg="#1a2a3a")).pack(pady=1)
        tk.Button(lbtns, text="Load", command=self.rb_load, **sbtn).pack(pady=1)
        tk.Button(lbtns, text="Delete", command=self.rb_delete, **sbtn).pack(pady=1)
        tk.Button(lbtns, text="New", command=self.rb_new, **sbtn).pack(pady=1)

        # ============ RIGHT: settings (top) + controls/log (bottom) ============
        right = tk.Frame(body, bg="#0a0a0f")
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        # ---- TOP RIGHT: settings ----
        settings = tk.Frame(right, **card)
        settings.grid(row=0, column=0, sticky="new")
        pad = dict(padx=12)
        tk.Label(settings, text="⚙ SETTINGS", **dict(hdr, bg="#101018")).pack(
            anchor="w", padx=12, pady=(10, 6))

        self.name_var = tk.StringVar(value=DEFAULT_CONFIG["name"])
        self.name_var.trace_add(
            "write", lambda *a: self.name_head.config(text=self.name_var.get() or "baspis"))
        tk.Label(settings, text="Name", bg="#101018", fg="#7a7a99",
                 anchor="w").pack(fill="x", **pad)
        tk.Entry(settings, textvariable=self.name_var, **ent).pack(fill="x", **pad)

        tk.Label(settings, text="Model", bg="#101018", fg="#7a7a99",
                 anchor="w").pack(fill="x", pady=(6, 0), **pad)
        mr = tk.Frame(settings, bg="#101018")
        mr.pack(fill="x", **pad)
        self.model_var = tk.StringVar(value=DEFAULT_CONFIG["model"])
        self.model_menu = tk.OptionMenu(mr, self.model_var, DEFAULT_CONFIG["model"])
        self.model_menu.config(bg="#15151f", fg="#e6e6f0", relief="flat",
                               highlightthickness=1, activebackground="#2a2a48",
                               width=16)
        self.model_menu["menu"].config(bg="#15151f", fg="#e6e6f0")
        self.model_menu.pack(side="left")
        tk.Button(mr, text="↻", command=self.rb_refresh_models, width=3,
                  bg="#1a1a28", fg="#cfe8ff", relief="ridge", bd=1
                  ).pack(side="left", padx=4)
        tk.Label(mr, text="server", bg="#101018", fg="#7a7a99").pack(side="left")
        self.url_var = tk.StringVar(value=DEFAULT_CONFIG["url"])
        tk.Entry(mr, textvariable=self.url_var, **ent).pack(
            side="left", fill="x", expand=True, padx=(4, 0))

        # vision model (for the "see" action)
        vr = tk.Frame(settings, bg="#101018")
        vr.pack(fill="x", pady=(4, 0), **pad)
        tk.Label(vr, text="👁 Vision", bg="#101018", fg="#7a7a99").pack(side="left")
        self.vision_var = tk.StringVar(value=DEFAULT_CONFIG["vision_model"])
        self.vision_menu = tk.OptionMenu(vr, self.vision_var,
                                         DEFAULT_CONFIG["vision_model"])
        self.vision_menu.config(bg="#15151f", fg="#e6e6f0", relief="flat",
                                highlightthickness=1, activebackground="#2a2a48",
                                width=16)
        self.vision_menu["menu"].config(bg="#15151f", fg="#e6e6f0")
        self.vision_menu.pack(side="left", padx=(4, 0))

        # target window (which app this baspis drives — Roblox or anything else)
        tk.Label(settings, text="Target window", bg="#101018", fg="#7a7a99",
                 anchor="w").pack(fill="x", pady=(6, 0), **pad)
        tr = tk.Frame(settings, bg="#101018")
        tr.pack(fill="x", **pad)
        self._targets = {AUTO_TARGET_LABEL: (AUTO_TARGET_LABEL, "name", "")}
        self.target_var = tk.StringVar(value=DEFAULT_CONFIG["target_label"])
        self.target_menu = tk.OptionMenu(tr, self.target_var, AUTO_TARGET_LABEL)
        self.target_menu.config(bg="#15151f", fg="#e6e6f0", relief="flat",
                                highlightthickness=1, activebackground="#2a2a48",
                                width=24, anchor="w")
        self.target_menu["menu"].config(bg="#15151f", fg="#e6e6f0")
        self.target_menu.pack(side="left", fill="x", expand=True)
        tk.Button(tr, text="↻", command=self.rb_refresh_targets, width=3,
                  bg="#1a1a28", fg="#cfe8ff", relief="ridge", bd=1
                  ).pack(side="left", padx=4)

        tk.Label(settings, text="Personality", bg="#101018", fg="#7a7a99",
                 anchor="w").pack(fill="x", pady=(6, 0), **pad)
        self.pers_txt = tk.Text(settings, height=2, wrap="word", **ent)
        self.pers_txt.pack(fill="x", **pad)
        self.pers_txt.insert("1.0", DEFAULT_CONFIG["personality"])

        tk.Label(settings, text="Goal / prompt", bg="#101018", fg="#7a7a99",
                 anchor="w").pack(fill="x", pady=(6, 0), **pad)
        self.goal_txt = tk.Text(settings, height=2, wrap="word", **ent)
        self.goal_txt.pack(fill="x", **pad)
        self.goal_txt.insert("1.0", DEFAULT_CONFIG["goal"])

        prow = tk.Frame(settings, bg="#101018")
        prow.pack(fill="x", pady=(6, 12), **pad)
        tk.Label(prow, text="Temp", bg="#101018", fg="#7a7a99").pack(side="left")
        self.temp_var = tk.StringVar(value=str(DEFAULT_CONFIG["temperature"]))
        tk.Entry(prow, textvariable=self.temp_var, width=5, **ent).pack(
            side="left", padx=(2, 10))
        tk.Label(prow, text="Max steps", bg="#101018", fg="#7a7a99").pack(side="left")
        self.steps_var = tk.StringVar(value=str(DEFAULT_CONFIG["max_steps"]))
        tk.Entry(prow, textvariable=self.steps_var, width=5, **ent).pack(
            side="left", padx=2)
        # rainbow ∞ indicator — appears only when max steps is infinite
        # (-1, 0, or a huge number)
        self.inf_lbl = tk.Label(prow, text="∞", bg="#101018", fg="#ff0000",
                                font=("TkDefaultFont", 11, "bold"))
        self._inf_shown = False
        self._rainbow_hue = 0
        self._animate_rainbow()
        self.steps_var.trace_add("write", lambda *a: self._update_inf_icon())
        self._update_inf_icon()

        # ---- BOTTOM RIGHT: controls + mode select + log ----
        bottom = tk.Frame(right, **card)
        bottom.grid(row=1, column=0, sticky="nsew", pady=(12, 0))

        ctl = tk.Frame(bottom, bg="#101018")
        ctl.pack(fill="x", padx=12, pady=(10, 6))
        self.agent_btn = tk.Button(
            ctl, text="▶ Start Robobaspis", command=self.rb_start,
            bg="#123", fg="#7CFFB0", activebackground="#1c3a2a",
            relief="raised", bd=2, font=("TkDefaultFont", 10, "bold"))
        self.agent_btn.pack(side="left")
        self.agent_pause_btn = tk.Button(
            ctl, text="⏸ Pause", command=self.rb_pause,
            bg="#2a2410", fg="#ffd166", activebackground="#3a3418",
            relief="raised", bd=2)
        self.agent_pause_btn.pack(side="left", padx=6)
        self.agent_pause_btn.config(state="disabled")
        self.agent_stop_btn = tk.Button(
            ctl, text="■ Stop", command=self.rb_stop,
            bg="#311", fg="#ff8888", activebackground="#4a1c1c",
            relief="raised", bd=2)
        self.agent_stop_btn.pack(side="left", padx=(0, 6))
        self.agent_stop_btn.config(state="disabled")
        self.stop_hint_lbl = tk.Label(ctl, text="", bg="#101018", fg="#7a7a99",
                                      font=("TkDefaultFont", 8))
        self.stop_hint_lbl.pack(side="left", padx=(2, 0))
        # mode select + pin-on-top — little circle icons, bottom right
        self._icon_btn(ctl, "⇄", self.toggle_mode, bg="#101018").pack(side="right")
        self._pin_icon(ctl, bg="#101018").pack(side="right", padx=(0, 6))

        # live message box — send info to the running baspis without stopping it
        msgrow = tk.Frame(bottom, bg="#101018")
        msgrow.pack(fill="x", padx=12, pady=(0, 6))
        self.msg_var = tk.StringVar()
        msg_entry = tk.Entry(msgrow, textvariable=self.msg_var, bg="#15151f",
                             fg="#e6e6f0", insertbackground="#e6e6f0",
                             relief="flat", highlightbackground="#26263a",
                             highlightthickness=1)
        msg_entry.pack(side="left", fill="x", expand=True)
        msg_entry.bind("<Return>", lambda e: self.rb_send())
        tk.Button(msgrow, text="✉ Send", command=self.rb_send, bg="#1a2a3a",
                  fg="#cfe8ff", activebackground="#22344a", relief="ridge",
                  bd=1).pack(side="left", padx=(6, 0))

        tk.Label(bottom, text="Thoughts / actions", bg="#101018", fg="#7a7a99",
                 anchor="w").pack(fill="x", padx=12)
        logwrap = tk.Frame(bottom, bg="#101018")
        logwrap.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        sb = tk.Scrollbar(logwrap)
        sb.pack(side="right", fill="y")
        self.log_txt = tk.Text(logwrap, height=6, bg="#08080c", fg="#9fe6c0",
                               relief="flat", highlightbackground="#1a1a26",
                               highlightthickness=1, wrap="word",
                               yscrollcommand=sb.set, state="disabled")
        self.log_txt.pack(side="left", fill="both", expand=True)
        sb.config(command=self.log_txt.yview)

        self.rb_refresh_list()

    def _load_saca(self):
        """Return (dark_photo, lit_photo) tk images, or (None, None)."""
        if not os.path.exists(SACA_PNG):
            return None, None
        try:
            import base64
            import io
            from PIL import Image, ImageEnhance

            def to_photo(factor):
                img = Image.open(SACA_PNG).convert("RGBA")
                img.thumbnail((240, 190))
                r, g, b, a = img.split()
                rgb = Image.merge("RGB", (r, g, b))
                rgb = ImageEnhance.Brightness(rgb).enhance(factor)
                r2, g2, b2 = rgb.split()
                out = Image.merge("RGBA", (r2, g2, b2, a))
                buf = io.BytesIO()
                out.save(buf, format="PNG")
                return tk.PhotoImage(data=base64.b64encode(buf.getvalue()))

            return to_photo(0.30), to_photo(1.12)
        except Exception:
            return None, None

    # --- mode switch ---
    def toggle_mode(self):
        if self.mode == "normal":
            self.normal_frame.pack_forget()
            self.root.resizable(True, True)
            self.root.geometry(self.ROBOBOSS_GEO)
            self.roboboss_frame.pack(fill="both", expand=True)
            self.mode = "roboboss"
            self.rb_refresh_models()
            self.rb_refresh_targets()
            self.rb_refresh_list()
        else:
            if self.agent and self.agent.running():
                self.agent.stop()
            self.roboboss_frame.pack_forget()
            self.root.geometry(self.NORMAL_GEO)
            self.root.resizable(False, False)
            self.normal_frame.pack(fill="both", expand=True)
            self.mode = "normal"

    # ================= thread-safe UI setters (normal engine) =================
    def set_speaking(self, on):
        self.root.after(0, lambda: self.speaking_lbl.config(
            text="Speaking: " + ("Yes" if on else "No")))

    def set_dancing(self, on):
        self.root.after(0, lambda: self.dancing_lbl.config(
            text="Dancing: " + ("Yes" if on else "No")))

    def set_jumping(self, on):
        self.root.after(0, lambda: self.jumping_lbl.config(
            text="Jumping: " + ("Yes" if on else "No")))

    def set_camera(self, on):
        self.root.after(0, lambda: self.camera_lbl.config(
            text="Camera: " + ("Yes" if on else "No")))

    def set_recording(self, on):
        self.root.after(0, lambda: self.recording_lbl.config(
            text="Recording: " + ("Yes" if on else "No")))

    def set_cycles(self, n):
        self.root.after(0, lambda: self.cycles_lbl.config(text="RunCycles: " + str(n)))

    def enable_wisdom_btn(self):
        self.root.after(0, lambda: self.wise_btn.config(state="normal"))

    # --- normal button handlers ---
    def on_wisdom(self):
        self.engine.wisdom = True
        self.wise_btn.config(state="disabled")

    def on_dance(self):
        self.engine.dance = True
        self.dance_btn.config(state="disabled")

    def on_jump(self):
        self.engine.jump = True
        self.jump_btn.config(state="disabled")

    def on_camera(self):
        self.engine.camera = True
        self.camera_btn.config(state="disabled")

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
        def finish():
            self.stop_btn.place_forget()
            self.run_btn.place(x=170, y=10)
            self.wise_btn.config(state="normal")
            self.dance_btn.config(state="normal")
            self.jump_btn.config(state="normal")
            self.camera_btn.config(state="normal")
            self.record_btn.config(state="normal")
            self.set_speaking(False)
            self.set_dancing(False)
            self.set_jumping(False)
            self.set_camera(False)
            self.set_recording(False)
            self.cycles_lbl.config(text="RunCycles: 0")
        self.root.after(0, finish)

    # ================= ROBOBOSS handlers =================
    def _rebuild_target_menu(self):
        menu = self.target_menu["menu"]
        menu.delete(0, "end")
        for disp in self._targets:
            menu.add_command(label=disp,
                             command=lambda v=disp: self.target_var.set(v))

    def rb_refresh_targets(self):
        """Repopulate the target-window menu from the open windows."""
        keep = self.target_var.get()
        self._targets = {AUTO_TARGET_LABEL: (AUTO_TARGET_LABEL, "name", "")}
        for title, wmclass, _wid in list_windows():
            # match by WM_CLASS (stable across title changes); label by title
            cls = wmclass.split(".")[-1] if wmclass else wmclass
            label = title or cls or "window"
            disp = label if len(label) <= 40 else label[:39] + "…"
            while disp in self._targets:       # de-dupe display strings
                disp += " "
            self._targets[disp] = (label, "class", cls)
        self._rebuild_target_menu()
        if keep not in self._targets:
            self.target_var.set(AUTO_TARGET_LABEL)

    def rb_refresh_models(self):
        models = Ollama(self.url_var.get()).list_models()
        if not models:
            self.conn_lbl.config(text="Connection: no server", fg="#ff8888")
            return
        hints = ("vl", "llava", "vision", "moondream", "bakllava", "minicpm")
        vision_models = [m for m in models if any(h in m.lower() for h in hints)]
        for menu, var, pref in (
                (self.model_menu["menu"], self.model_var, models),
                (self.vision_menu["menu"], self.vision_var,
                 vision_models or models)):
            menu.delete(0, "end")
            for m in models:
                menu.add_command(label=m,
                                 command=lambda v=m, vr=var: vr.set(v))
            if var.get() not in models:
                var.set(pref[0])
        self.conn_lbl.config(text="Connection: %d models" % len(models),
                             fg="#7CFFB0")

    def rb_refresh_list(self):
        self.saved_list.delete(0, "end")
        for n in list_configs():
            self.saved_list.insert("end", n)

    def _selected_name(self):
        sel = self.saved_list.curselection()
        return self.saved_list.get(sel[0]) if sel else None

    def rb_load(self):
        name = self._selected_name()
        if not name:
            return
        try:
            cfg = load_config(name)
        except (OSError, ValueError) as e:
            self.agent_log("! load failed: %s" % e)
            return
        self.name_var.set(cfg["name"])
        self.model_var.set(cfg["model"])
        self.vision_var.set(cfg.get("vision_model", DEFAULT_CONFIG["vision_model"]))
        self.url_var.set(cfg["url"])
        # target window
        tmatch = cfg.get("target_match", "")
        if not tmatch:
            self.target_var.set(AUTO_TARGET_LABEL)
        else:
            tlabel = cfg.get("target_label", tmatch)
            disp = tlabel if len(tlabel) <= 40 else tlabel[:39] + "…"
            self._targets[disp] = (tlabel, cfg.get("target_by", "class"), tmatch)
            self._rebuild_target_menu()
            self.target_var.set(disp)
        self.temp_var.set(str(cfg["temperature"]))
        self.steps_var.set(str(cfg["max_steps"]))
        self.pers_txt.delete("1.0", "end")
        self.pers_txt.insert("1.0", cfg["personality"])
        self.goal_txt.delete("1.0", "end")
        self.goal_txt.insert("1.0", cfg["goal"])
        self.agent_log("* loaded '%s'" % cfg["name"])

    def rb_delete(self):
        name = self._selected_name()
        if name and delete_config(name):
            self.rb_refresh_list()
            self.agent_log("* deleted '%s'" % name)

    def rb_new(self):
        self.name_var.set(DEFAULT_CONFIG["name"])
        self.temp_var.set(str(DEFAULT_CONFIG["temperature"]))
        self.steps_var.set(str(DEFAULT_CONFIG["max_steps"]))
        self.pers_txt.delete("1.0", "end")
        self.pers_txt.insert("1.0", DEFAULT_CONFIG["personality"])
        self.goal_txt.delete("1.0", "end")
        self.goal_txt.insert("1.0", DEFAULT_CONFIG["goal"])

    def rb_gather(self):
        def fnum(v, default, cast):
            try:
                return cast(v)
            except (ValueError, TypeError):
                return default
        label, by, match = self._targets.get(
            self.target_var.get(), (AUTO_TARGET_LABEL, "name", ""))
        return {
            "name": self.name_var.get().strip() or "baspis",
            "model": self.model_var.get(),
            "vision_model": self.vision_var.get(),
            "url": self.url_var.get().strip() or DEFAULT_OLLAMA_URL,
            "personality": self.pers_txt.get("1.0", "end").strip(),
            "goal": self.goal_txt.get("1.0", "end").strip(),
            "temperature": fnum(self.temp_var.get(), 0.7, float),
            "max_steps": fnum(self.steps_var.get(), 40, int),
            "target_label": label,
            "target_by": by,
            "target_match": match,
        }

    def rb_save(self):
        name = save_config(self.rb_gather())
        self.rb_refresh_list()
        self.agent_log("* saved '%s'" % name)

    def rb_start(self):
        if self.agent and self.agent.running():
            return
        if not Roblox.available():
            self.agent_log("! xdotool not found — cannot control Roblox")
            return
        cfg = self.rb_gather()
        oll = Ollama(cfg["url"])
        if not oll.reachable():
            self.agent_log("! ollama not reachable at %s" % cfg["url"])
            self.conn_lbl.config(text="Connection: no server", fg="#ff8888")
            return
        self._clear_log()
        self.agent_log("* '%s' waking up (model %s)" % (cfg["name"], cfg["model"]))
        self.agent = Agent(self, cfg)
        self.agent_btn.config(state="disabled")
        self.agent_stop_btn.config(state="normal")
        self.agent_pause_btn.config(state="normal", text="⏸ Pause")
        self.agent.start()

    def rb_stop(self):
        if self.agent:
            self.agent.stop()
        self.agent_stop_btn.config(state="disabled")
        self.agent_pause_btn.config(state="disabled", text="⏸ Pause")

    def rb_pause(self):
        if not (self.agent and self.agent.running()):
            return
        paused = self.agent.toggle_pause()
        self.agent_pause_btn.config(text="▶ Resume" if paused else "⏸ Pause")
        self.agent_log("* paused" if paused else "* resumed")

    def rb_send(self):
        text = self.msg_var.get().strip()
        if not text:
            return
        if self.agent and self.agent.running():
            self.agent.tell(text)
            self.msg_var.set("")
            self.agent_log("  ✉ you: %s (queued)" % text)
        else:
            self.agent_log("! no robobaspis running to message")

    # --- agent callbacks (called from agent thread) ---
    def agent_active(self, on):
        def apply():
            if on and self._saca_lit is not None:
                self.baspis_lbl.config(image=self._saca_lit)
                self.baspis_wrap.config(highlightbackground="#33ffcc",
                                        bg="#12201e")
            elif self._saca_dark is not None:
                self.baspis_lbl.config(image=self._saca_dark)
                self.baspis_wrap.config(highlightbackground="#1a1a26",
                                        bg="#101018")
        self.root.after(0, apply)

    def agent_status(self, thinking=None, acting=None, seeing=None, paused=None):
        def apply():
            if paused:
                self.state_lbl.config(text="State: ⏸ paused", fg="#ffd166")
            elif seeing:
                self.state_lbl.config(text="State: 👁 looking...", fg="#c792ff")
            elif seeing is False and thinking is None and acting is None:
                self.state_lbl.config(text="State: acting", fg="#7CFFB0")
            elif thinking:
                self.state_lbl.config(text="State: thinking...", fg="#ffd166")
            elif acting:
                self.state_lbl.config(text="State: acting", fg="#7CFFB0")
            elif thinking is False and acting is None:
                self.state_lbl.config(text="State: idle", fg="#66e0ff")
        self.root.after(0, apply)

    def agent_log(self, msg):
        def apply():
            self.log_txt.config(state="normal")
            self.log_txt.insert("end", msg + "\n")
            self.log_txt.see("end")
            self.log_txt.config(state="disabled")
        self.root.after(0, apply)

    def _update_inf_icon(self):
        """Show the ∞ icon only when the max-steps value means infinite."""
        inf = steps_infinite(self.steps_var.get())
        if inf and not self._inf_shown:
            self.inf_lbl.pack(side="left", padx=(4, 0))
            self._inf_shown = True
        elif not inf and self._inf_shown:
            self.inf_lbl.pack_forget()
            self._inf_shown = False

    def _animate_rainbow(self):
        """Continuously cycle the ∞ icon through rainbow colors."""
        import colorsys
        self._rainbow_hue = (self._rainbow_hue + 6) % 360
        r, g, b = colorsys.hsv_to_rgb(self._rainbow_hue / 360.0, 0.9, 1.0)
        try:
            self.inf_lbl.config(fg="#%02x%02x%02x" % (int(r * 255), int(g * 255),
                                                      int(b * 255)))
            self.root.after(60, self._animate_rainbow)
        except tk.TclError:
            pass       # window closed

    def baspis_say(self, text):
        """Show text in the baspis speech bubble."""
        text = (text or "").strip() or "…"
        if len(text) > 220:
            text = text[:217] + "…"
        self.root.after(0, lambda: self.bubble.config(text=text))

    def _clear_log(self):
        self.log_txt.config(state="normal")
        self.log_txt.delete("1.0", "end")
        self.log_txt.config(state="disabled")

    def on_agent_stopped(self):
        def finish():
            self.agent_btn.config(state="normal")
            self.agent_stop_btn.config(state="disabled")
            self.agent_pause_btn.config(state="disabled", text="⏸ Pause")
            self.state_lbl.config(text="State: idle", fg="#66e0ff")
            self.agent_log("* robobaspis stopped")
        self.root.after(0, finish)

    def on_exit(self):
        self.engine.stop()
        if self.agent:
            self.agent.stop()
        if getattr(self, "hotkey", None):
            self.hotkey.stop()
        self.root.after(200, self.root.destroy)


def main():
    if sys.platform.startswith("win"):
        print("This is the Linux port. On Windows, use the original Roboss.au3/.exe.")
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
