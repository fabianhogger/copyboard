# Copyboard — Specification

The source of truth for **what** Copyboard does and **why**. For **how** it is built, see
[ARCHITECTURE.md](ARCHITECTURE.md). For progress, see [TASKS.md](TASKS.md).

## Problem

The OS clipboard only remembers the *last* copied item. During a task you copy many things in
sequence — a screenshot, some text for a chat, a file path, a URL — and everything but the last is
lost, and you can't remember what the earlier items were.

## Goal

A small **cross-platform** (Windows, Linux, macOS) background app that watches the clipboard and shows
a live view of your recent clippings, so you can glance back and re-copy any of them.

## Functional requirements

1. **Capture** every clipboard change while the app runs and classify each into one kind
   (priority order: image → url → path → json → markdown → command → text):
   - **Image** — a bitmap copied to the clipboard (e.g. a screenshot).
   - **URL** — text that is a URL (`http`, `https`, `ftp`, …).
   - **Path** — text that is a filesystem path (Windows drive/UNC or POSIX), by syntax.
   - **JSON** — text that parses as a JSON object or array.
   - **Markdown** — text carrying Markdown structure (headings, lists, code fences, links…).
   - **Command** — text whose first line looks like a shell / CLI command.
   - **Text** — arbitrary copied text (the fallback).
2. **Live view** — a window listing recent clippings, newest first, each showing a preview
   (text snippet, URL, path, or image thumbnail) and its capture time.
3. **Re-copy** — clicking a clipping puts it back on the system clipboard.
4. **Delete** — a clipping can be removed from the view.
5. **Retention** — the view keeps only recent clippings, bounded by **both**:
   - a maximum **count** (default **30**), and
   - a maximum **age** (default **20 minutes**).
   Both limits are configurable.
6. **Background behavior** — the app lives in the **system tray** and captures continuously. A
   **global hotkey** (default **Ctrl+Shift+H**) and clicking the tray icon show/hide the viewer.

## Configuration

Settings load from **`config.json`** at the repo root (`copyboard/config_loading.py`). Missing or
partial files fall back to defaults (`copyboard/config.py`). Fields:

```json
{
  "retention": { "max_items": 30, "max_age_minutes": 20 },
  "hotkey": { "toggle_viewer_hotkey": "ctrl+shift+h" }
}
```

## Storage model

- The **history index is in-memory** and clears when the app exits.
- The "vault" is simply the **OS temp directory**:
  - **Images** are written there (via the stdlib `tempfile` module) and referenced by path, so RAM
    stays small.
  - **Path/file** clippings reference the **existing OS file** — nothing is copied.
  - **Text/URL** clippings stay in memory.
  - There is no managed folder and no explicit cleanup — the OS owns temp.

## Non-goals (out of scope)

- Disk persistence / history surviving a restart.
- A web front-end (the architecture keeps this possible later, but it is not built now).
- A settings *UI* (config is edited directly in `config.json`).
- Image-size caps / advanced de-duplication.

## Known platform caveats

- The `pynput` global hotkey needs **X11** on Linux (not native Wayland) and **Accessibility
  permission** on macOS. If the hotkey can't bind, the app still runs — use the tray icon to open the
  viewer.
