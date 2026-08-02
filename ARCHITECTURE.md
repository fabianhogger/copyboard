# Copyboard — Architecture

**How** Copyboard is built. For **what/why**, see [SPEC.md](SPEC.md).

## Pattern: Hexagonal (Ports & Adapters)

Copyboard follows **Hexagonal Architecture** (a.k.a. Ports & Adapters / Clean / Onion), governed by
the **Dependency Inversion Principle**: the domain never depends on Qt or OS details; both depend on
abstractions the domain owns.

- **Core** — `copyboard/domain/` + `copyboard/application/`. Pure business rules. Imports nothing
  technological (no PySide6, no OS I/O).
- **Ports** — `Protocol` interfaces the core defines and depends on:
  - *outbound*: `Clock`, `ClipboardSource`, `ClipboardSink`, `ClippingVault`
  - *notification*: `HistoryObserver` (implemented by the UI)
- **Adapters** — `copyboard/adapters/`. One concrete class per technology: `SystemClock`,
  `TempDirVault`, `PynputHotkeyBinder`, `QtClipboardSource`/`QtClipboardSink`, and the Qt UI/tray.
  Adapters depend on the core; the core never imports an adapter.
- **Composition root** — `copyboard/__main__.py`. The only place that names concrete classes and wires
  adapters into the service. Dependencies point **inward**.

### The dependency rule (enforced)

`domain/` and `application/` must **never** `import PySide6` (or any adapter). This is what makes the
core reusable behind a different front-end (e.g. a future web UI reuses the core untouched and provides
web implementations of the ports) and fully unit-testable with fakes (`FakeClock`, `FakeVault`,
`FakeClipboardSource`) — no Qt, no real filesystem/clipboard in tests.

## Layers & package layout

**File-naming convention:** a file dominated by one class is named after that class, lowercased with
no separators (`ClippingHistory` → `clippinghistory.py`). Files holding several co-equal classes keep
a conceptual name (`content.py`, `ports.py`, `config.py`).

```
copyboard/
  __main__.py                 # composition root + Qt bootstrap
  config.py                   # RetentionPolicy, HotkeyConfig, AppConfig (pure)
  config_loading.py           # load_app_config_from_json — reads config.json (I/O)
  domain/                     # pure business rules, no Qt / no I/O
    content.py                # RawClipboardData, ImagePayload, ClipboardPayload (value objects)
    clipping.py               # Clipping (ABC) + TextualClipping + 7 kind subclasses
    clippingclassifier.py     # ClippingClassifier + Url/Path/Json/Markdown/Command detectors
    clippinghistory.py        # ClippingHistory (count + time bounded)
    ports.py                  # Clock, ClipboardSource, ClipboardSink, ClippingVault
  application/                # orchestration, depends only on domain
    events.py                 # ClippingAdded / ClippingRemoved / HistoryPruned, ObserverRegistry, HistoryObserver
    copyboardservice.py       # CopyboardService
  adapters/                   # the only place Qt / OS APIs live
    systemclock.py            # SystemClock
    tempdirvault.py           # TempDirVault (stdlib tempfile)
    pynputhotkeybinder.py     # PynputHotkeyBinder (cross-platform global hotkey)
    qt/qtclipboard.py         # QtClipboardSource, QtClipboardSink
    ui/mainwindow.py          # MainWindow
    ui/clippingwidget.py      # ClippingWidget + per-kind renderers
    ui/trayicon.py            # TrayIcon
```

## Key classes & responsibilities

- **`Clipping`** (ABC) — `id`, `created_at`, `size_bytes`, abstract `kind`, plus pure helpers
  `build_preview_text()` and `to_clipboard_payload()` (so re-copy stays UI-free). The text-based kinds
  share an intermediate **`TextualClipping`** base; concrete kinds: `TextClipping`, `UrlClipping`,
  `CommandClipping`, `JsonClipping`, `MarkdownClipping`, plus `PathClipping` (references an existing OS
  file) and `ImageClipping` (holds the temp-file `Path`; thumbnailing happens in the UI by reading it).
- **`RawClipboardData`** / **`ImagePayload`** / **`ClipboardPayload`** — neutral value objects crossing
  the port boundary.
- **`ClippingVault`** (port) — `store_image_bytes(data, suffix) -> Path`. **`TempDirVault`** writes to
  the OS temp dir via stdlib `tempfile` (cross-platform); no cleanup (OS owns temp).
- **`ClippingClassifier`** — injected `ClippingVault` + `Clock`. `classify_clipboard_content(raw)`
  applies ordered rules image → url → path → json → markdown → command → text via small detector
  classes (`UrlDetector`, `PathDetector`, `JsonDetector`, `MarkdownDetector`, `CommandDetector`).
- **`AppConfig`** (pure, `config.py`) loaded by `load_app_config_from_json()` (`config_loading.py`)
  from `config.json`, with tolerant fallback to defaults.
- **`ClippingHistory`** — `add_clipping`, `remove_clipping_by_id`, `list_clippings_newest_first`,
  `enforce_retention(now)`; obeys `RetentionPolicy` (`max_items`, `max_age`).
- **`CopyboardService`** (application core) — `handle_new_clipboard_content(raw)` → classify → add →
  enforce retention → notify; `recopy_clipping_by_id`, `delete_clipping_by_id`,
  `remove_expired_clippings()` (driven by a UI timer). Notifies `HistoryObserver`s.
- **Qt adapters** — `QtClipboardSource` (connects `QClipboard.dataChanged`, guards the re-copy feedback
  loop), `QtClipboardSink`, `MainWindow`, `ClippingWidget`, `TrayIcon`.
- **`HotkeyBinder`** (UI-layer interface) + **`PynputHotkeyBinder`** — cross-platform global hotkey via
  `pynput`, running a listener thread; its callback is marshaled onto the Qt GUI thread by a queued
  signal. Lives outside the domain (an interaction concern, not business logic).

## Supporting patterns

**Observer** (service → UI change notifications), **Strategy/polymorphism** (the `Clipping` hierarchy +
classifier rules), **Value Objects** (`RawClipboardData`, `ImagePayload`), and **constructor Dependency
Injection** for all ports.
