# Copyboard — Clipboard History Viewer

## Context

**Problem.** The OS clipboard only remembers the *last* copied item. During a task you copy many
things in sequence — a screenshot, some text for ChatGPT, a file path, a URL — and all but the last
are lost, and you can't remember what they were.

**Goal.** A small **cross-platform** (Windows, Linux, macOS) background app that watches the
clipboard and shows a live view of the recent clippings (text, URLs, paths, images), so you can
glance back and re-copy any of them.

**Decisions (from planning Q&A):**
- **Platform:** OS-agnostic — runs on Windows, Linux, and macOS. Every adapter uses a cross-platform
  mechanism (Qt clipboard + tray, stdlib `tempfile`, `pynput` global hotkey); no platform-specific
  native code.
- **UI:** PySide6 (Qt), but behind a **strictly layered architecture** — the core must be UI-agnostic
  so the app can later be re-fronted as a web app by swapping only the adapter layer.
- **Storage:** In-memory history index (clears on exit). The "vault" is the **OS temp directory**:
  clipboard *images* are written there and referenced by path (keeps RAM small); *path/file* clippings
  reference the existing OS file (no copy); *text/url* stay in memory. No managed folder, no explicit
  cleanup — the OS owns temp. Temp location resolved via the stdlib `tempfile` module
  (cross-platform), not a hardcoded path.
- **Retention:** Both count *and* time, configurable — keep the last `N` items (default 30) **and**
  drop anything older than `T` (default 20 min).
- **Behavior:** Runs in the system tray, capturing continuously; a global hotkey / tray click opens
  the viewer. Click an item to re-copy it; delete items you don't want.

**Hard constraints (from the user):**
- Every function/method **fully typed**. `mypy` must pass with `--disallow-untyped-defs`
  (interpreting the user's `--no-untuped-defs`) on **both `copyboard/` and `tests/`**.
- `ruff check` clean on source and tests.
- A **rich class hierarchy** — many small, single-purpose classes — for a clear codebase.
- **Descriptive, intention-revealing names** for every function, method, and class — across the whole
  codebase, not just tests. Prefer `check_if_clipboard_has_image()` over `check()`,
  `looks_like_filesystem_path()` over `is_path()`. A name should state what it does/answers without
  needing the body. Short idioms are allowed only where context makes intent unambiguous (e.g.
  `Clock.now()`).
- Create **`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`** with **identical** contents.
- Create project docs **`SPEC.md`, `ARCHITECTURE.md`, `TASKS.md`**.
- **The user handles all git commits.** I will not run `git commit` / `git add`.
- **Tooling: `uv`** for env + dependency management (repo already has uv scaffolding); ruff, mypy,
  pytest run via `uv run …`. `typing-extensions` available for typing backports.

## Documentation set

Two categories of markdown, kept in sync:

- **Agent instruction files — `CLAUDE.md` / `AGENTS.md` / `GEMINI.md` (identical content).** Short,
  operational: hexagonal/ports-&-adapters layering + dependency constraint, the typing/ruff/mypy bar,
  the class-per-concept convention, the **descriptive-naming rule**, `uv run …` commands, and "the user
  does all git commits." Each links to `SPEC.md` / `ARCHITECTURE.md` / `TASKS.md` for detail rather than
  duplicating them.
- **Project docs:**
  - **`SPEC.md`** — the *what/why*: problem statement, functional requirements (capture text/url/path/image,
    live view, re-copy, delete), retention rules (count + time, defaults 30 / 20 min), the storage model
    (in-memory index + OS-temp-dir vault for images, path clippings reference existing files), tray +
    hotkey behavior, non-goals/out-of-scope. The source of truth for scope.
  - **`ARCHITECTURE.md`** — the *how*: names the pattern (Hexagonal / Ports & Adapters, Dependency
    Inversion), the layered design + dependency rule, the package layout, the ports/adapters seam (and
    how it enables a future web front-end), and the key classes with their responsibilities. Mirrors the
    "Architecture pattern" and "Key classes" sections below.
  - **`TASKS.md`** — the phase/step checklist (Phases 0–6 below) as trackable checkboxes, updated as work
    progresses.

## Architecture pattern: Hexagonal (Ports & Adapters)

This is **Hexagonal Architecture** (a.k.a. Ports & Adapters / Clean / Onion), governed by the
**Dependency Inversion Principle**: the domain never depends on Qt/OS details; both depend on
abstractions the domain owns.

- **Core** (`domain/` + `application/`) — pure business rules; imports nothing technological.
- **Ports** — `Protocol` interfaces the core defines: *outbound* `Clock`, `ClipboardSource`,
  `ClipboardSink`, `ClippingVault`; *notification* `HistoryObserver` (the UI implements it).
- **Adapters** — one concrete class per technology: `SystemClock`, `QtClipboardSource`/`QtClipboardSink`,
  `TempDirVault`, `PynputHotkeyBinder`, Qt UI/tray. Adapters depend on the core; the core never imports
  an adapter.
- **Composition root** (`__main__.py`) — the only place that names concrete classes and wires adapters
  into the service. Dependencies point *inward*.

Payoffs: (1) a web front-end later = new adapters + composition root, core reused untouched;
(2) the core is fully unit-testable with `FakeClock` / `FakeVault` / `FakeClipboardSource` — no Qt, no
real filesystem/clipboard. Supporting patterns: **Observer** (service→UI), **Strategy/polymorphism**
(the `Clipping` hierarchy + classifier rules), **Value Objects** (`RawClipboardData`, `ImagePayload`),
**constructor Dependency Injection** for ports.

## The layering rule (the backbone of this design)

```
domain/  ── pure Python, no Qt, no I/O ....... models, history, classifier, config, PORTS
application/ ── pure Python, depends only on domain ... CopyboardService, events
adapters/ ── the only place Qt / OS APIs live
    clock.py            SystemClock            (implements domain Clock port)
    vault.py            TempDirVault           (stdlib tempfile, cross-platform)
    hotkey.py           PynputHotkeyBinder     (cross-platform global hotkey)
    qt/                 QtClipboardSource/Sink
    ui/                 MainWindow, item widgets, tray icon
__main__.py ── composition root: wires adapters into the service, starts Qt
```

**Dependency rule:** `domain/` and `application/` must **never** `import PySide6`. The service talks to
the outside world only through **ports** (Protocols) — `Clock`, `ClipboardSource`, `ClipboardSink`,
`HistoryObserver`. A web version reuses `domain/` + `application/` unchanged and provides web
implementations of those ports plus a browser front-end. This is also what makes the core fully
unit-testable with fakes (no Qt needed in tests).

## Package layout (target)

```
copyboard/
  __init__.py
  __main__.py                 # main(): composition root + Qt bootstrap
  config.py                   # RetentionPolicy, HotkeyConfig, AppConfig
  domain/
    content.py                # RawClipboardData, ImagePayload  (value objects)
    clipping.py               # Clipping (ABC) + Text/Url/Path/Image subclasses
    classifier.py             # ClippingClassifier, UrlDetector, PathDetector
    history.py                # ClippingHistory (count + time bounded)
    ports.py                  # Clock, ClipboardSource, ClipboardSink, ClippingVault, HistoryObserver
  application/
    events.py                 # ClippingAdded / ClippingRemoved / HistoryPruned, ObserverRegistry
    service.py                # CopyboardService
  adapters/
    clock.py                  # SystemClock
    vault.py                  # TempDirVault (writes image blobs to OS temp dir via stdlib tempfile)
    hotkey.py                 # PynputHotkeyBinder (cross-platform global hotkey)
    qt/
      qt_clipboard.py         # QtClipboardSource, QtClipboardSink
    ui/
      main_window.py          # MainWindow
      clipping_widget.py      # ClippingWidget + per-kind renderers
      tray.py                 # TrayIcon
tests/
  domain/  application/       # fakes: FakeClock, FakeClipboardSource, RecordingObserver
```
The existing `copyboard.py` sketch and `main.py` are replaced by this package (the sketch's
`Clipping`/`ClippingsDequeue`/`Display` map onto `domain/clipping.py`, `domain/history.py`, and
`adapters/ui/`). `ClippingsDequeue(deque)` becomes `ClippingHistory` (composition, not `deque`
subclassing, because time-pruning needs to scan).

## Key classes & responsibilities

(Method names below follow the descriptive-naming rule — intention-revealing, not terse.)

- **`Clipping` (ABC)** — `id`, `created_at: datetime`, `size_bytes: int`, abstract `kind`, plus pure
  helpers `build_preview_text() -> str` and `to_clipboard_payload()` (so re-copy stays UI-free).
  Subclasses: **`TextClipping`, `UrlClipping`, `PathClipping`** (references an existing OS file),
  **`ImageClipping`** (holds the **temp-file `Path`** written by the vault, not raw bytes; thumbnailing
  happens in the UI layer by reading that path).
- **`RawClipboardData`** — neutral snapshot of the OS clipboard (`text: str | None`, `image: ImagePayload | None`).
- **`ClippingVault` (port)** — `store_image_bytes(data: bytes, suffix: str) -> Path`. The domain depends
  only on this interface. **`TempDirVault`** (adapter) implements it by writing to the OS temp dir
  via stdlib `tempfile` (cross-platform) and returning the path — no cleanup (OS owns temp).
- **`ClippingClassifier`** — depends on the `ClippingVault` port (injected). `classify_clipboard_content(raw)`
  applies ordered rules image → url → path → text, using `UrlDetector.looks_like_url(text)` and
  `PathDetector.looks_like_filesystem_path(text)` (drive-letter / UNC / existing path). For images it
  asks the vault to persist bytes → `ImageClipping(path=…)`; else it builds an in-memory clipping.
  Testable with a `FakeVault`.
- **`ClippingHistory`** — `add_clipping`, `remove_clipping_by_id(id)`, `list_clippings_newest_first()`,
  `enforce_retention(now)`; obeys `RetentionPolicy` (`max_items`, `max_age: timedelta`).
- **Ports (Protocols)** — `Clock.now()`, `ClipboardSource.read_current_content()` (+ change signal),
  `ClipboardSink.copy_clipping_to_system_clipboard(clipping)`, `HistoryObserver.on_history_changed(event)`.
- **`CopyboardService`** — the application core: `handle_new_clipboard_content(raw)` → classify → add →
  enforce retention → notify; `recopy_clipping_by_id(id)` (via sink), `delete_clipping_by_id(id)`,
  `remove_expired_clippings()` (time-based prune driven by a UI timer).
- **Qt adapters** — `QtClipboardSource` (connects `QClipboard.dataChanged`, guards against the
  re-copy feedback loop), `QtClipboardSink`, `MainWindow`, `ClippingWidget`, `TrayIcon` (all Qt,
  cross-platform).
- **`HotkeyBinder` (UI-layer interface) + `PynputHotkeyBinder`** — a cross-platform global hotkey via
  `pynput` (Windows / macOS / X11). Runs a listener thread; its callback is marshaled onto the Qt GUI
  thread by a queued signal to toggle the window. Lives outside the domain (an interaction concern, not
  business logic).

## Dependencies & tooling (uv)

- Managed with **uv**: `uv add PySide6 pynput typing-extensions`; `uv add --dev ruff mypy pytest`;
  `uv sync` to materialize `.venv`. Everything runs through `uv run` (e.g. `uv run pytest`).
- Runtime: **PySide6** (QClipboard reads text *and* images natively → no Pillow needed), **pynput**
  (cross-platform global hotkey), **typing-extensions** for typing backports if useful. The vault uses
  the stdlib `tempfile` module — no dependency.
- Dev: **ruff, mypy, pytest** (PySide6 ships type stubs).
- `pyproject.toml` gains `dependencies`, a `[dependency-groups] dev` group (uv's dev deps),
  `[tool.ruff]`, `[tool.mypy]` (`disallow_untyped_defs = true`, covering `tests/`), and
  `[project.scripts] copyboard = "copyboard.__main__:main"`.

---

## PHASES & STEPS

### PHASE 0 — Scaffolding, docs & tooling gate
- **0.1** Create the `copyboard/` package + `tests/` tree; retire `copyboard.py` sketch and `main.py`.
- **0.2** Set up deps via uv (`uv add PySide6 typing-extensions`, `uv add --dev ruff mypy pytest`) and
  configure `pyproject.toml`: `[tool.ruff]`, `[tool.mypy]` (disallow untyped defs, include tests),
  `[project.scripts]`.
- **0.3** Write project docs: **`SPEC.md`** (scope/requirements), **`ARCHITECTURE.md`** (layering,
  ports/adapters, classes), **`TASKS.md`** (Phases 0–6 as checkboxes).
- **0.4** Write `CLAUDE.md`, `AGENTS.md`, `GEMINI.md` — **identical** content (layering rule, typing/
  ruff/mypy bar, class-per-concept convention, `uv run …` commands, "user does the commits"), each
  pointing to the three project docs.
- **0.5** `uv sync`, then confirm `uv run ruff check`, `uv run mypy .`, `uv run pytest` all run green on
  the empty skeleton.

### PHASE 1 — Domain core (Qt-free, fully unit-tested)
- **1.1** `domain/content.py` — `RawClipboardData`, `ImagePayload`.
- **1.2** `domain/clipping.py` — `Clipping` ABC + four subclasses (`ImageClipping` holds a temp `Path`).
- **1.3** `domain/ports.py` — `Clock`, `ClipboardSource`, `ClipboardSink`, `ClippingVault`, `HistoryObserver`.
- **1.4** `config.py` — `RetentionPolicy` (30 items / 20 min defaults), `HotkeyConfig`, `AppConfig`.
- **1.5** `domain/clippingclassifier.py` — `ClippingClassifier` (injected `ClippingVault` + `Clock`) with Url/Path/Json/Markdown/Command detectors.
- **1.6** `domain/clippinghistory.py` — `ClippingHistory`.
- **1.7** Tests: classifier rules (with `FakeVault`), history count+time pruning (with `FakeClock`),
  model previews. ruff + mypy clean.

### PHASE 2 — Application service (Qt-free)
- **2.1** `application/events.py` — event types + `ObserverRegistry`.
- **2.2** `application/service.py` — `CopyboardService` (add/recopy/delete/tick + notifications).
- **2.3** `adapters/clock.py` — `SystemClock`; `adapters/vault.py` — `TempDirVault` (writes image blobs
  to the OS temp dir via `tempfile` / `QStandardPaths.TempLocation`).
- **2.4** Tests with `FakeClipboardSource`, `FakeClipboardSink`, `FakeVault`, `RecordingObserver`,
  `FakeClock`; a `TempDirVault` test that asserts a temp file is created and readable.

### PHASE 3 — Qt clipboard adapters
- **3.1** `adapters/qt/qt_clipboard.py` — `QtClipboardSource` (dataChanged → RawClipboardData, feedback-loop
  guard) and `QtClipboardSink` (write text/image back).
- **3.2** Manual check: copying things in Windows produces the right clipping kinds.

### PHASE 4 — Qt viewer UI
- **4.1** `adapters/ui/clipping_widget.py` — per-kind rendering (text/url/path previews, image thumbnail
  via `QPixmap`) with re-copy + delete buttons.
- **4.2** `adapters/ui/main_window.py` — scrollable list, subscribes to service events, `QTimer` tick
  drives time-based pruning + refresh.
- **4.3** Observer that marshals service events onto the GUI thread (Qt signal).

### PHASE 5 — Tray, hotkey, entry point
- **5.1** `adapters/ui/tray.py` — `TrayIcon` (show/hide viewer, quit).
- **5.2** `adapters/pynputhotkeybinder.py` — `PynputHotkeyBinder` (default **Ctrl+Shift+H**, configurable)
  implementing the `HotkeyBinder` interface via `pynput`; its callback toggles the window through a
  queued Qt signal (thread-safe, cross-platform).
- **5.3** `__main__.py` — composition root: build `AppConfig`, `CopyboardService`, adapters, tray,
  window, hotkey; `main()` entry point.
- **5.4** End-to-end manual verification on Windows.

### PHASE 6 — Polish & final quality gate
- **6.1** `README.md` usage; confirm `SPEC.md` / `ARCHITECTURE.md` / `TASKS.md` and the three agent
  files are current (all `TASKS.md` boxes checked).
- **6.2** Full `uv run ruff check`, `uv run mypy .`, `uv run pytest` green across src + tests.
- **6.3** Backlog notes (config file, thumbnail/image-size caps, persistence, cross-platform clipboard adapter).

## Verification

- **Core (automated, no display needed):** `uv run pytest` — classifier picks correct kinds;
  `ClippingHistory` drops by count and by age using `FakeClock`; `CopyboardService` adds/recopies/deletes
  and notifies observers via fakes.
- **Quality gate:** `uv run ruff check` and `uv run mypy .` clean over `copyboard/` **and** `tests/`.
- **Layering guard:** grep confirms no `PySide6` import under `domain/` or `application/`.
- **End-to-end (manual, any OS):** launch `uv run copyboard`; copy text, a URL, a file path, and a
  screenshot in turn → each appears in the viewer with the right rendering, and the screenshot's bytes
  land as a temp file that the thumbnail reads; click re-copy → item lands back on the clipboard; wait
  past the age window / exceed 30 items → old ones disappear; the global hotkey and tray icon show/hide
  the window.

## Out of scope (backlog)
Disk persistence, a web front-end (the layering makes it possible later), configurable-via-file
settings UI, image-size caps. Known platform caveats: `pynput` global hotkeys need X11 (not native
Wayland) on Linux and Accessibility permission on macOS — the app still runs without the hotkey.
