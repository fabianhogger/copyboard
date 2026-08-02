# Copyboard — Tasks

Phase/step checklist. See [PLAN.md](PLAN.md) for full detail, [SPEC.md](SPEC.md) for scope,
[ARCHITECTURE.md](ARCHITECTURE.md) for design.

## Phase 0 — Scaffolding, docs & tooling gate
- [x] 0.1 Create `copyboard/` package + `tests/` tree; retire `copyboard.py` sketch and `main.py`.
- [x] 0.2 Configure `pyproject.toml` (deps via uv, ruff, mypy `disallow_untyped_defs` incl. tests, `project.scripts`).
- [x] 0.3 Write project docs: `SPEC.md`, `ARCHITECTURE.md`, `TASKS.md`.
- [x] 0.4 Write identical `CLAUDE.md` / `AGENTS.md` / `GEMINI.md`.
- [x] 0.5 `uv sync`; confirm `ruff` / `mypy` / `pytest` green on the skeleton.

## Phase 1 — Domain core (Qt-free, fully unit-tested)
- [x] 1.1 `domain/content.py` — `RawClipboardData`, `ImagePayload`, `ClipboardPayload`.
- [x] 1.2 `domain/clipping.py` — `Clipping` ABC + `TextualClipping` + 7 kinds (text/url/path/image/command/json/markdown).
- [x] 1.3 `domain/ports.py` — `Clock`, `ClipboardSource`, `ClipboardSink`, `ClippingVault`.
- [x] 1.4 `config.py` (`RetentionPolicy` 30 / 20 min, `HotkeyConfig` ctrl+shift+h, `AppConfig`) + `config_loading.py` (reads `config.json`).
- [x] 1.5 `domain/clippingclassifier.py` — `ClippingClassifier` + Url/Path/Json/Markdown/Command detectors.
- [x] 1.6 `domain/clippinghistory.py` — `ClippingHistory`.
- [x] 1.7 Tests: classifier (FakeVault), history count+time pruning (FakeClock), previews, config loading — 20 passing.

## Phase 2 — Application service (Qt-free)
- [x] 2.1 `application/events.py` — event types + `ObserverRegistry` + `HistoryObserver`.
- [x] 2.2 `application/copyboardservice.py` — `CopyboardService`.
- [x] 2.3 `adapters/systemclock.py` — `SystemClock`; `adapters/tempdirvault.py` — `TempDirVault`.
- [x] 2.4 Tests with fakes + a `TempDirVault` temp-file test — 26 passing total.

## Phase 3 — Qt clipboard adapters
- [x] 3.1 `adapters/qt/qtclipboard.py` — `QtClipboardSource` (+ `ClipboardEchoGuard`), `QtClipboardSink`; PNG-by-default, configurable image format.
- [ ] 3.2 Manual check: copying produces the right clipping kinds (covered by Phase 5 E2E).

## Phase 4 — Qt viewer UI
- [ ] 4.1 `adapters/ui/clippingwidget.py` — per-kind rendering + re-copy/delete.
- [ ] 4.2 `adapters/ui/mainwindow.py` — list, subscribes to events, `QTimer` prune.
- [ ] 4.3 GUI-thread observer marshaling (Qt signal).

## Phase 5 — Tray, hotkey, entry point
- [x] 5.1 `adapters/ui/trayicon.py` — `TrayIcon` (+ programmatic icon).
- [x] 5.2 `adapters/pynputhotkeybinder.py` — `PynputHotkeyBinder` (Ctrl+Shift+H) via `HotkeyBinder`.
- [x] 5.3 `__main__.py` — composition root + `main()` (pynput→Qt queued-signal bridge).
- [x] 5.4 Headless boot smoke passed; interactive copy check is for the user on a real desktop.

## Phase 6 — Polish & final quality gate
- [x] 6.1 `README.md` written; docs + this checklist reconciled.
- [x] 6.2 Full `ruff` / `mypy` / `pytest` green across src + tests (42 files, 34 tests).
- [x] 6.3 Backlog notes (below).

## Backlog
- Disk persistence (history surviving restart) — currently in-memory only.
- A web front-end reusing the pure core (the hexagonal seam makes it possible).
- A settings UI (config is edited directly in `config.json`).
- Image-size caps / thumbnail caching; de-duplication of consecutive identical clippings.
- Wayland global-hotkey support (pynput needs X11); macOS Accessibility onboarding.
