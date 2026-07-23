# Roboss

A Linux port of [Roboss](https://github.com/MBrassey/Roboss) — a Roblox
automation toy by Matt Brassey, originally written in AutoIt for Windows. This
version reimplements it in Python with a **tkinter** GUI and drives the game
through **xdotool** (X11 window activation + key/mouse injection).

It has two modes:

- **Normal** — the classic Roboss: anti-idle, chat "wisdom", dance, jump, camera
  wiggle, and recording.
- **Roboboss** — an autonomous agent that connects a *robobaspis* to a local
  [Ollama](https://ollama.com) LLM and lets it **see the screen and play on its
  own** — move, click buttons, read menus and money, use tools, and run routines
  it programs itself. It can target Roblox **or any other window** on your
  computer.

![license](https://img.shields.io/badge/license-CC0_1.0_Universal-blue)

---

## Requirements

- Linux with an **X11** session (`echo $XDG_SESSION_TYPE` → `x11`). Wayland is
  not supported for input injection (xdotool needs X11/XWayland).
- **Python 3.8+** with tkinter — `sudo apt install python3-tk`
- **xdotool** — `sudo apt install xdotool`

Optional (Normal mode works without these):

- **Pillow** — renders the mascot and captures screenshots for the agent
  `sudo apt install python3-pil`
- **python-xlib** — fast, occlusion-free window capture + the global stop hotkey
  `sudo apt install python3-xlib`
- **wmctrl** — lists open windows for the target picker
  `sudo apt install wmctrl`

For **Roboboss** mode you also need a running Ollama server with a text model and
a vision model:

```bash
ollama serve                 # if not already running
ollama pull qwen3            # the "brain" (any chat model works)
ollama pull qwen2.5vl:3b     # the "eyes" (any vision model works)
```

## Run

```bash
python3 roboss.py
```

Launch your Roblox client first — this port targets **[Sober](https://sober.vinegarhq.org/)**
(the VinegarHQ Roblox client) by matching its window, and also matches a window
titled `Roblox` (web player, Wine, etc.).

---

## Normal mode

Pick options on the left, then hit **Start!**; **Stop** halts everything.

- **SpeakWisdom** — opens chat and types a rotating set of quotes.
- **Dance** — sends `/e dance` on a randomized cadence.
- **Jump** — taps space every ~40–60 s.
- **Camera** — smoothly tilts the camera a little every ~45–75 s.
- **Record** — toggles Roblox recording with `F12`.

Cadence is randomized to look organic. The two small circle icons under the logo:
**⇄** switches to Roboboss mode, and **⇧** pins the window on top of the game so
you can watch it while the game keeps focus.

---

## Roboboss mode

Switch with the **⇄** icon. A *robobaspis* (Sacabambaspis avatar) reasons with a
local LLM and acts on the target window one step at a time. It's dark when idle
and lights up while thinking/acting, with a speech bubble showing what it's
"saying".

### Controls

- **Left** — the robobaspis, its connection/state, and your saved robobaspis
  (Save / Load / Delete / New; stored as JSON in `robobaspis/`, git-ignored).
- **Top right — settings:** name, **model**, **👁 vision model**, **target
  window**, personality, goal/prompt, temperature, and max steps (with a rainbow
  **∞** that appears when steps are infinite — set `-1`).
- **Bottom right:** **Start / Pause / Stop**, a **message box** to feed the
  running agent new info without stopping it, and the live thoughts/actions log.
- **Global stop hotkey: `Ctrl+Alt+S`** — stops the agent from anywhere, even
  while the game has focus.

### Any window, not just Roblox

The **Target window** picker (↻ to refresh) lists your open windows. Point a
robobaspis at Roblox, a browser, an editor — anything. Roblox-specific actions
(move/look/jump/reset/say) are used only when the target is a game; for other
apps the agent sticks to see + click + keys.

### How it sees and acts

The agent is blind between look-ups and uses a **`see`** action on demand:
it captures **only the target window's own pixels** (so overlapping windows,
including Roboss itself, are never in frame) and asks the vision model to
describe buttons, key prompts, tools, money, and surroundings — reporting
positions as percentages. For small things it can **zoom** into a region
(`hotbar`, `bottom-center`, `top-left`, …, or an explicit box).

Clicking uses **`click_object`**, which finds a named target and clicks its
center with a **coarse-to-fine zoom** (locate roughly, then re-look at a tight
crop centered on the guess) so a weak model's error shrinks to a few pixels. All
coordinate mapping is done in code. **`click_here`** does a true blind click at
the current mouse position without moving it.

For fast routines the agent can **program its own `sequence`** — a list of steps
with `repeat`, `shuffle`, randomized `[min,max]` argument ranges, and an optional
pacing `gap`. A sequence focuses the window once and runs back-to-back, so combos
are one LLM call instead of many.

**Action set:** `see`, `click_object`, `click_here`, `click`, `move`, `look`,
`jump`, `reset`, `key`, `keys`, `say`, `wait`, `sequence`, `done`.

---

## Port notes

| Original (AutoIt / Windows)   | Port (Python / Linux)                              |
|-------------------------------|----------------------------------------------------|
| `GUICreate` + `GUICtrl*`      | `tkinter`                                           |
| `WinActivate`/`WinWaitActive` | `xdotool search` + `windowactivate --sync`          |
| `Send("{BREAK}")`             | `xdotool key Pause`                                 |
| `Send("...")` / `{ENTER}`     | `xdotool type` / `xdotool key Return`               |
| single `While 1` loop         | GUI main thread + daemon worker/agent threads       |
| —                             | Ollama vision/chat agent, Xlib capture, X hotkey    |

Screenshots for the agent are grabbed via Xlib `get_image` on the target window
(fast and occlusion-free), falling back to a full-screen grab if Xlib is absent.

## Disclaimer

Roboss is a hobby proof-of-concept. Automating Roblox may violate its terms of
service; use it on your own account at your own risk. Distributed for free as an
experimental open-source project.

## License

Published under the **CC0 1.0 Universal** license (see `LICENSE`).
