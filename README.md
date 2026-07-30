# Copyboard

A cross-platform system-tray app that keeps a live, scrollable history of everything you copy — text, URLs, paths, images, JSON, Markdown, shell commands — so you can glance back and re-copy anything, not just the last item.

## Features

**Automatic capture**  
Every clipboard change is recorded in the background. The app runs silently in the system tray; there is nothing to configure before it starts working.

**Smart content classification**  
Each clipping is automatically classified so you can tell what you're looking at at a glance:

| Kind | Detected when |
|------|--------------|
| URL | `http://`, `https://`, `ftp://`, `ftps://` with a valid host |
| Path | Windows drive (`C:\`), UNC (`\\server\share`), POSIX absolute (`/foo`), or home-relative (`~/…`) |
| JSON | Parses as a valid JSON object `{}` or array `[]` |
| Markdown | Contains headings, fenced code blocks, blockquotes, inline links, bold text, or two or more list items |
| Command | First word is a known CLI tool (`git`, `docker`, `kubectl`, `npm`, `uv`, `ssh`, `curl`, …) or line starts with `$`, `>`, `#`, `PS ` |
| Image | Bitmap copied from any app; stored in a temp file and shown as a thumbnail |
| Text | Everything else |

**Viewer window**  
A scrollable list (newest first) with a timestamp and preview for each item. Images render as 160 × 90 thumbnails. Each row has:
- **Copy** — puts the item back on the system clipboard
- **Delete** — removes it from history immediately
- **Drag** — drag any item directly into another app (text, URLs, paths, or image files)

**Global hotkey**  
Press **Ctrl+Shift+H** (configurable) from any application to show or raise the viewer. Press again while the viewer is in the foreground to hide it.

**Stack paste mode (LIFO)**

Enable **Stack paste: On/Off** in the viewer or **Stack paste mode (LIFO)** in the tray menu to paste
through history newest-first. Both controls stay synchronized. Copyboard
preloads the newest clipping; after each normal **Ctrl+V** (Windows/Linux) or **Cmd+V** (macOS), that
clipping is removed from history and the next-newest clipping is loaded. The final paste clears the
clipboard. Turning the mode off leaves the current clipboard and remaining history untouched.

**System-tray icon**  
Click the tray icon to toggle the viewer. Right-click for the menu:
- Show / hide viewer
- Stack paste mode (LIFO)
- Toggle light / dark theme
- Edit config… (opens `config.json` in your default editor)
- Quit Copyboard

**Live theme toggle**  
Switch themes from the tray menu — no restart needed. Colors use flat, neutral boxes without
gradients; dark is the default.

**Retention policy**  
Both limits apply together: the history keeps at most `max_items` clippings **and** drops anything older than `max_age_minutes`. Pruning runs every second in the background.

**No echo duplicates**  
When you re-copy a clipping, the resulting clipboard change is suppressed so it doesn't create a new duplicate entry.

**Detaches from the terminal**  
Launching `uv run copyboard` immediately returns your shell prompt; the app continues running in the background.

## Install & run

Requires [uv](https://docs.astral.sh/uv/) and Python 3.10+.

```
uv sync            # create .venv and install dependencies
uv run copyboard   # launch the tray app (detaches from terminal automatically)
```

## Configuration

Settings load from `config.json` at the repo root. Missing or partial files fall back to defaults.

```json
{
  "retention": {
    "max_items": 30,
    "max_age_minutes": 20
  },
  "hotkey": {
    "toggle_viewer_hotkey": "ctrl+shift+h"
  },
  "theme": "dark"
}
```

| Setting | Default | Description |
|---------|---------|-------------|
| `retention.max_items` | `30` | Maximum number of clippings to keep |
| `retention.max_age_minutes` | `20` | Drop clippings older than this many minutes |
| `hotkey.toggle_viewer_hotkey` | `ctrl+shift+h` | Global show/hide hotkey |
| `theme` | `dark` | `dark`, `light`, or `system` (follow the OS) |

You can open the config file directly from the tray menu via **Edit config…**

## Platform notes

| Platform | Notes |
|----------|-------|
| Linux | The global hotkey requires **X11**. On native Wayland, the hotkey won't bind, but the tray icon still works. |
| macOS | `pynput` needs **Accessibility permission** (System Settings → Privacy → Accessibility). Without it the hotkey is skipped, but the app runs normally. |
| Windows | Works out of the box. |

If the hotkey fails to bind, the app still runs — use the tray icon to open the viewer.

## Development

Stack paste advances only for keyboard paste shortcuts. Context-menu paste, middle-click paste, and
mouse buttons mapped to Paste are not observed. Its keyboard listener has the same X11 requirement on
Linux and Accessibility-permission requirement on macOS as the viewer hotkey.

```
uv run ruff check .     # lint
uv run ruff format .    # format
uv run mypy .           # type-check (src + tests, disallow_untyped_defs)
uv run pytest           # run the test suite
```

Docs: [SPEC.md](SPEC.md) (scope) · [ARCHITECTURE.md](ARCHITECTURE.md) (design) · [TASKS.md](TASKS.md) (progress) · [PLAN.md](PLAN.md) (phased plan)
