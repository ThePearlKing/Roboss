## Roboss (Linux port)

Roblox automation application. This is a **Linux port** of the original Windows
[Roboss](https://github.com/MBrassey/Roboss) by Matt Brassey, which was written
in AutoIt. The port reimplements the same behavior in Python using **tkinter**
for the GUI and **xdotool** for X11 window activation and input injection.

![licensebadge](https://img.shields.io/badge/license-CC0_1.0_Universal-blue)

### Requirements

- Linux with an **X11** session (`echo $XDG_SESSION_TYPE` → `x11`).
  Wayland is not supported for key injection — `xdotool` needs X11/XWayland.
- Python 3.8+ with tkinter (`sudo apt install python3-tk`)
- `xdotool` (`sudo apt install xdotool`)

Optional: install `python3-pil` / Pillow to render the `Roboss.jpg` mascot in
the window. Without it the GUI still works; the image is just skipped (tkinter's
built-in `PhotoImage` can't decode JPEG).

### Run

```bash
python3 roboss.py
```

The window must match the title `Roblox`. Launch your Roblox client (e.g. via
[Sober](https://sober.vinegarhq.org/) or the web player) before starting.

### What it does

- **awake()** — periodically focuses the Roblox window and sends the Break
  (`Pause`) key to keep the character from going idle. Delay between pokes is
  randomized to look organic.
- **sayings()** — opens chat (`/`), types a wise message, presses Enter.
  Randomized cadence; stops after ~200 cycles and re-enables the button.
- **dance()** — sends `/e dance`. Re-triggers at randomized intervals until Stop.
- **record()** — presses `F12` to toggle Roblox recording on start/stop.

### Usage

Click any options on the left (SpeakWisdom / Dance / Record), then click
**Start!** on the right. Click **Stop** to halt everything. Options can be added
while running, but individual options can't be stopped without a full Stop.

### Port notes

| Original (AutoIt / Windows) | Port (Python / Linux)                    |
|-----------------------------|------------------------------------------|
| `GUICreate` + `GUICtrl*`    | `tkinter`                                |
| `WinActivate`/`WinWaitActive` | `xdotool search --name` + `windowactivate --sync` |
| `Send("{BREAK}")`           | `xdotool key Pause`                      |
| `Send("...")` text          | `xdotool type --delay 30`                |
| `Send("{ENTER}")` / `{F12}` | `xdotool key Return` / `xdotool key F12` |
| single `While 1` event loop | GUI main thread + daemon worker thread   |

Behavior (randomized anti-idle cadence, the 56 sayings, the 200-cycle quiet
window) is preserved from `Roboss.au3`, kept in this repo for reference.

### Disclaimer

Roboss is a hobby proof-of-concept, ported for use on Linux. Distributed for
free as an experimental open source application.

### License

Published under the **CC0 1.0 Universal** license (see `LICENSE`).
