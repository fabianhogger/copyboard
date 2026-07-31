# Copyboard — A Study Guide

> A deep, build-it-in-your-head walkthrough of a real cross-platform desktop app.
> The goal is not to describe *what* the code is, but to teach you *why every non-obvious
> decision was made* — architecture, data modelling, concurrency, cross-platform quirks, UX, and
> testing — so you could rebuild it (or defend it in a design review) from first principles.

**Audience:** you already know Python and OOP. You want to see how the ideas from a software-design
course — Hexagonal Architecture, the SOLID principles, value objects, the Observer and Strategy
patterns, dependency injection — actually land in a small-but-serious codebase, and how they pay off
when the real world (Windows firing duplicate events, a lying type stub, a terminal that won't let
go) fights back.

**How to read it:** top to bottom the first time. Each part states a *problem*, derives a *decision*,
shows the *code*, and calls out the *trade-off*. Boxes marked **🔬 War story** are real bugs found and
fixed in this project — they are the most instructive parts. Boxes marked **🏋 Exercise** are for you.

---

## Table of contents

0. [The product and the problem](#0-the-product-and-the-problem)
1. [The one architectural idea that matters: Ports & Adapters](#1-the-one-architectural-idea-that-matters-ports--adapters)
2. [The domain model: value objects and the clipping hierarchy](#2-the-domain-model-value-objects-and-the-clipping-hierarchy)
3. [Classification: the Strategy pattern with a priority ladder](#3-classification-the-strategy-pattern-with-a-priority-ladder)
4. [History & retention: choosing a data structure](#4-history--retention-choosing-a-data-structure)
5. [The application service and the Observer pattern](#5-the-application-service-and-the-observer-pattern)
6. [Adapters, part 1: clock, vault, and the storage model](#6-adapters-part-1-clock-vault-and-the-storage-model)
7. [Adapters, part 2: the clipboard, and three subtle bugs](#7-adapters-part-2-the-clipboard-and-three-subtle-bugs)
8. [The UI: window, rows, drag-out, tray, and theme](#8-the-ui-window-rows-drag-out-tray-and-theme)
9. [Concurrency: the global hotkey and the GUI thread](#9-concurrency-the-global-hotkey-and-the-gui-thread)
10. [Process detachment: freeing the terminal](#10-process-detachment-freeing-the-terminal)
11. [Configuration: pure model vs. tolerant loading](#11-configuration-pure-model-vs-tolerant-loading)
12. [The composition root: where it all comes together](#12-the-composition-root-where-it-all-comes-together)
13. [Testing strategy: fakes, offscreen Qt, and honest limits](#13-testing-strategy-fakes-offscreen-qt-and-honest-limits)
14. [Tooling & CI: the quality gate across 12 environments](#14-tooling--ci-the-quality-gate-across-12-environments)
15. [Cross-platform cheat sheet](#15-cross-platform-cheat-sheet)
16. [Architecture Decision Record (summary)](#16-architecture-decision-record-summary)
17. [Exercises & extension challenges](#17-exercises--extension-challenges)
18. [Glossary](#18-glossary)

---

## 0. The product and the problem

**The problem.** The OS clipboard is a single register: it remembers only the *last* thing you
copied. In real work you copy many things in a row — a screenshot, a chat message, a file path, a
URL — and everything but the last is gone.

**The product.** *Copyboard* is a small, cross-platform (Windows / Linux / macOS) background app
that lives in the system tray, watches every clipboard change, classifies each into a *kind*
(image, URL, path, text, …), and shows a live, newest-first list you can glance at and re-copy from.

The functional requirements, distilled:

| # | Requirement | Where it lives |
|---|-------------|----------------|
| 1 | **Capture** each clipboard change and classify it | `QtClipboardSource` → `ClippingClassifier` |
| 2 | **Live view**, newest-first, previews + timestamps | `MainWindow` + `ClippingWidget` |
| 3 | **Re-copy** an item back onto the clipboard | `QtClipboardSink` |
| 4 | **Delete** an item from the view | `CopyboardService.delete_clipping_by_id` |
| 5 | **Retention** bounded by *both* count and age | `ClippingHistory` + `RetentionPolicy` |
| 6 | **Background**: tray + global hotkey | `TrayIcon`, `PynputHotkeyBinder`, `processdetach` |

Everything below is the story of how those six lines become a robust program.

---

## 1. The one architectural idea that matters: Ports & Adapters

If you remember one thing from this guide, remember this section.

### 1.1 The problem with the "obvious" design

The obvious way to write a clipboard app is to let the GUI framework drive everything: a Qt widget
reads `QClipboard`, decides "is this a URL?", stuffs it into a Python list, and repaints itself. It
works — and it is almost impossible to test, impossible to reuse behind a web UI, and it welds your
business rules to a specific version of a specific GUI toolkit forever.

The rules that make Copyboard *Copyboard* — "classify by priority", "keep 30 items or 20 minutes,
whichever is tighter", "re-copying should not create a duplicate entry" — have nothing to do with
Qt. So they should not import Qt.

### 1.2 The pattern

Copyboard uses **Hexagonal Architecture** (a.k.a. *Ports & Adapters*, *Clean*, *Onion*). The
governing law is the **Dependency Inversion Principle**: high-level policy must not depend on
low-level detail; both depend on an abstraction that the policy layer *owns*.

```
                     ┌──────────────────────────────────────────┐
                     │            ADAPTERS (the edge)            │
                     │  Qt, pynput, tempfile, subprocess, JSON   │
                     │                                           │
   OS clipboard ──▶  │  QtClipboardSource ┐         ┌ TrayIcon   │
   keyboard    ──▶   │  PynputHotkeyBinder│         │ MainWindow │  ──▶  screen
                     │  SystemClock       │  ports  │ ClippingWidget    
                     │  TempDirVault      ▼         ▲            │
                     │        ┌───────────────────────────┐     │
                     │        │   APPLICATION (service)    │     │
                     │        │     CopyboardService       │     │
                     │        │  ┌─────────────────────┐   │     │
                     │        │  │   DOMAIN (rules)     │   │     │
                     │        │  │ Clipping hierarchy   │   │     │
                     │        │  │ ClippingClassifier   │   │     │
                     │        │  │ ClippingHistory      │   │     │
                     │        │  │ ports.py (Protocols) │   │     │
                     │        │  └─────────────────────┘   │     │
                     │        └───────────────────────────┘     │
                     └──────────────────────────────────────────┘
                          dependencies point INWARD only
```

- **Core** = `copyboard/domain/` + `copyboard/application/`. Pure rules. Imports nothing
  technological — no `PySide6`, no OS I/O.
- **Ports** = `Protocol` interfaces the core defines and depends on (`Clock`, `ClipboardSource`,
  `ClipboardSink`, `ClippingVault`, and the notification port `HistoryObserver`).
- **Adapters** = `copyboard/adapters/`. Exactly one concrete class per technology.
- **Composition root** = `copyboard/__main__.py`. The *only* file that names concrete adapter
  classes and wires them into the service.

### 1.3 Ports are `Protocol`s (structural typing)

Here is the entire outbound-port file — the seam of the whole app:

```python
# copyboard/domain/ports.py
class Clock(Protocol):
    def now(self) -> datetime: ...

class ClippingVault(Protocol):
    def store_image_bytes(self, data: bytes, suffix: str) -> Path: ...

class ClipboardSource(Protocol):
    def read_current_content(self) -> RawClipboardData: ...

class ClipboardSink(Protocol):
    def copy_clipping_to_system_clipboard(self, clipping: Clipping) -> None: ...
```

**Why `Protocol` and not an abstract base class?** With `typing.Protocol` the conformance is
*structural* ("duck typing checked at compile time"). `SystemClock` never writes
`class SystemClock(Clock)` — it simply has a `now(self) -> datetime` method, and mypy verifies it
satisfies the port wherever one is required. The adapter therefore has *zero import dependency* on
the domain's port definition. Dependencies point inward without even a nominal `import` pointing
outward. That is Dependency Inversion in its purest form.

### 1.4 The rule that is actually enforced

> `domain/` and `application/` must **never** `import PySide6` (or any adapter).

This isn't a guideline in a wiki; it is checked. A one-line grep in review (`rg
'^\s*(from|import)\s+(PySide6|pynput)' copyboard/domain copyboard/application` returns nothing) and,
more importantly, the *test suite proves it*: the core is exercised entirely with in-memory fakes
(`FakeClock`, `FakeVault`, `FakeClipboardSink`). If someone smuggled a Qt import into the domain, the
domain tests would suddenly need a `QApplication` to run — the friction *is* the alarm.

**What this buys you:**
- **Reuse.** A future web front-end reuses `domain/` and `application/` untouched and supplies web
  implementations of the same four ports.
- **Testability.** The interesting logic runs in microseconds with no GUI, no real clipboard, no
  files.
- **Replaceability.** Swap `pynput` for a native hotkey library, or `tempfile` for a real database,
  by writing one new adapter and changing one line in the composition root.

> **🔬 Nuance — push vs. pull at the clipboard port.**
> `ClipboardSource.read_current_content()` is a *pull* API, and `QtClipboardSource` implements it.
> But the live wiring is actually *push*: the adapter subscribes to `QClipboard.dataChanged` and
> calls a listener (`service.handle_new_clipboard_content`). Both exist deliberately — `read_current
> _content()` is the testable, synchronous heart, and the push callback is the event-driven skin
> around it. Recognising when to expose *both* a pull method and a push callback over the same code
> is a genuinely senior instinct.

---

## 2. The domain model: value objects and the clipping hierarchy

### 2.1 Two shapes of clipboard data, not one

A naive model uses one "ClipboardItem" class everywhere. Copyboard instead has **three** value
objects, and the split is the whole point:

```python
# copyboard/domain/content.py
@dataclass(frozen=True, slots=True)
class ImagePayload:
    data: bytes
    image_format: str

@dataclass(frozen=True, slots=True)
class RawClipboardData:          # what comes IN off the clipboard
    text: str | None = None
    image: ImagePayload | None = None

@dataclass(frozen=True, slots=True)
class ClipboardPayload:          # what goes OUT when you re-copy
    text: str | None = None
    image_path: Path | None = None
```

Notice the **asymmetry**, which encodes a real data decision:

- *In*, an image is raw **bytes** (`ImagePayload.data`) — the clipboard hands you an in-memory bitmap
  that has no file on disk yet.
- *Out*, an image is a **`Path`** (`ClipboardPayload.image_path`) — by the time you re-copy, the
  bytes have been spilled to a temp file, and the domain refers to it by path so it never has to hold
  or re-serialize image bytes.

Modelling "input" and "output" as different types (rather than one mutable bag) means the compiler
tells you when you confuse the two, and each stage of the pipeline consumes exactly the shape it
needs.

**Why `frozen=True, slots=True`?** `frozen` makes them immutable value objects — you can't
accidentally mutate a clipping's text after it's classified, and immutability makes equality and
hashing meaningful (crucial in §7 for de-duplication). `slots=True` drops the per-instance `__dict__`
for a smaller memory footprint — appropriate for objects you may create on every keypress.

### 2.2 The `Clipping` hierarchy: polymorphism that keeps the UI dumb

Each captured item becomes a `Clipping`. The base class is abstract and carries only what *every*
kind has:

```python
# copyboard/domain/clipping.py
@dataclass(frozen=True, kw_only=True)
class Clipping(ABC):
    created_at: datetime
    size_bytes: int
    id: str = field(default_factory=lambda: uuid4().hex)

    @property
    @abstractmethod
    def kind(self) -> ClippingKind: ...
    @abstractmethod
    def build_preview_text(self) -> str: ...
    @abstractmethod
    def to_clipboard_payload(self) -> ClipboardPayload: ...
```

Two abstract methods carry the design:

- `build_preview_text()` — a short, one-line human description **for the viewer**, but computed in
  the *domain* with no Qt involved.
- `to_clipboard_payload()` — how to put this item *back* on the clipboard, again as a neutral value
  object, not a Qt call.

This is **"tell, don't ask"**: the UI never inspects a clipping's internals with `if isinstance(...)`
ladders to figure out how to render or re-copy it. It asks the clipping to describe itself. Adding a
new kind never touches the UI's rendering logic or the re-copy logic.

The text-based kinds share an intermediate base so the shared behaviour is written **once**:

```python
@dataclass(frozen=True, kw_only=True)
class TextualClipping(Clipping, ABC):
    text: str
    def build_preview_text(self) -> str:
        return summarize_as_single_line(self.text)
    def to_clipboard_payload(self) -> ClipboardPayload:
        return ClipboardPayload(text=self.text)

class TextClipping(TextualClipping):    # kind == TEXT
class UrlClipping(TextualClipping):     # kind == URL
class CommandClipping(TextualClipping): # kind == COMMAND
class JsonClipping(TextualClipping):    # kind == JSON
class MarkdownClipping(TextualClipping):# kind == MARKDOWN
```

`PathClipping` and `ImageClipping` are *not* textual — they override the two methods differently. A
`PathClipping` references an **existing OS file** and re-copies its path string; an `ImageClipping`
holds the temp-file `Path` and re-copies via `image_path`:

```python
@dataclass(frozen=True, kw_only=True)
class ImageClipping(Clipping):
    path: Path
    image_format: str
    def build_preview_text(self) -> str:
        return f"Image ({self.image_format.upper()}, {self.size_bytes} bytes)"
    def to_clipboard_payload(self) -> ClipboardPayload:
        return ClipboardPayload(image_path=self.path)
```

> **Design note — `kw_only=True`.** Dataclass inheritance has a notorious field-ordering trap: a
> base-class field with a default (like `id`) followed by a subclass field without one is a
> `TypeError`. Making every field keyword-only side-steps ordering entirely *and* forces call sites
> to name fields (`ImageClipping(created_at=..., size_bytes=..., path=...)`), which reads far better
> than positional soup.

> **Design note — the `id`.** Every clipping gets a `uuid4().hex`. The UI addresses clippings by id
> (`recopy_clipping_by_id`, `delete_clipping_by_id`), never by list index. Indices shift the moment
> retention prunes an item; a stable id means a row's "Delete" button always deletes the *right*
> thing even if the list changed underneath it.

### 2.3 The file-naming convention

`ClippingHistory` lives in `clippinghistory.py`; `CopyboardService` in `copyboardservice.py`. A file
dominated by one class is named after it, lowercased, no separators. Files with several co-equal
classes keep a *conceptual* name: `content.py` (three value objects), `ports.py` (four protocols),
`config.py` (three config records). This is a small rule, but consistently applied it means you can
find any class without a search tool.

---

## 3. Classification: the Strategy pattern with a priority ladder

Capturing raw data is easy; deciding *what it is* is the first real piece of logic.

### 3.1 An ordered set of rules

`ClippingClassifier.classify_clipboard_content(raw)` applies rules in a fixed **priority order**:

```
image → url → path → json → markdown → command → text (fallback)
```

Order matters because the categories overlap: `https://example.com` is technically also "text";
`{"a":1}` is JSON *and* text. The first rule that matches wins, so the ladder is arranged
most-specific first, with plain `text` as the catch-all at the bottom.

```python
# copyboard/domain/clippingclassifier.py (shape)
def classify_clipboard_content(self, raw: RawClipboardData) -> Clipping | None:
    if raw.image is not None:
        return self._build_image_clipping(raw.image)
    if raw.text:
        return self._build_text_clipping(raw.text)
    return None

def _build_text_clipping(self, text: str) -> Clipping:
    created_at, size = self._clock.now(), len(text.encode("utf-8"))
    if self._url_detector.looks_like_url(text):       return UrlClipping(...)
    if self._path_detector.looks_like_filesystem_path(text): return PathClipping(...)
    if self._json_detector.looks_like_json(text):     return JsonClipping(...)
    if self._markdown_detector.looks_like_markdown(text): return MarkdownClipping(...)
    if self._command_detector.looks_like_command(text):   return CommandClipping(...)
    return TextClipping(...)
```

### 3.2 One detector = one class = one responsibility

Each rule is its own small class with an intention-revealing method:

```python
class UrlDetector:
    def looks_like_url(self, text: str) -> bool: ...
class PathDetector:
    def looks_like_filesystem_path(self, text: str) -> bool: ...
class JsonDetector:
    def looks_like_json(self, text: str) -> bool: ...
```

This is the **Strategy pattern**. The benefits are concrete, not academic:

- **Testable in isolation.** You can unit-test `PathDetector` against `C:\x`, `\\unc\share`,
  `/home/me`, `~/x`, and `not a path` without constructing the whole classifier.
- **Injectable.** The classifier takes each detector as an optional constructor argument
  (`url_detector: UrlDetector | None = None`), so a test can substitute a fake or a stricter rule.
- **Deterministic & pure.** Detection is *syntactic only* — no filesystem access, no network. A URL
  is "a URL" because it parses with a known scheme and a netloc, not because a server answered. A
  path "looks like a path" by shape (`C:\`, `\\`, `/`, `~/`), and Copyboard never calls
  `os.path.exists` during classification. Purity is what makes the whole domain testable without a
  world to touch.

### 3.3 The naming standard, illustrated

Notice `looks_like_url`, `looks_like_filesystem_path`, `check_if_clipboard_has_image`. The house rule
is **descriptive, intention-revealing names everywhere** — `check_if_clipboard_has_image()` over
`check()`, `looks_like_filesystem_path()` over `is_path()`. Short idioms (`Clock.now()`) are allowed
only where context makes intent unambiguous. Good names are the cheapest documentation you will ever
write.

> **🔧 Product decision — the frontend later hid the kinds.** Originally the viewer printed the kind
> as a label (`URL · 20:59:18`). A UX review decided that was clutter — a user can *see* it's a URL —
> so the label was removed from `ClippingWidget`. Crucially, the *classifiers were kept*: the domain
> still tags items as URL/JSON/Command, the UI just doesn't surface it. Why keep dead-looking code?
> Because the planned next feature is **colour-coding** (URL in an accent colour, commands in red,
> `.py` paths in blue), which needs exactly that classification. The lesson: a *presentation* change
> (`adapters/ui`) should not amputate a *domain* capability. Turn it off at the edge; keep the model
> rich.

---

## 4. History & retention: choosing a data structure

### 4.1 The dual bound

Retention is governed by a policy with **two independent limits that both apply**:

```python
# copyboard/config.py
@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    max_items: int = 30                          # keep at most 30…
    max_age: timedelta = timedelta(minutes=20)   # …AND nothing older than 20 min
```

"Whichever is tighter" is a deliberate product choice: a burst of 100 copies shouldn't blow up
memory (count bound), and a clipping you made an hour ago is stale even if it's the only one (age
bound).

### 4.2 Why a `list`, not a `deque`

The first instinct for "a bounded queue of recent things" is `collections.deque(maxlen=30)`. Copyboard
deliberately uses a plain `list` with composition instead of subclassing `deque`. Here's the
reasoning:

```python
# copyboard/domain/clippinghistory.py
class ClippingHistory:
    def __init__(self, policy: RetentionPolicy) -> None:
        self._policy = policy
        self._clippings: list[Clipping] = []   # oldest-first == time order

    def enforce_retention(self, now: datetime) -> list[Clipping]:
        cutoff = now - self._policy.max_age
        removed = [c for c in self._clippings if c.created_at < cutoff]
        self._clippings = [c for c in self._clippings if c.created_at >= cutoff]
        removed.extend(self._trim_to_count_limit())
        return removed
```

- `deque(maxlen=…)` gives you the *count* bound for free but the **age** bound needs a full scan and
  a partial rebuild — which a `deque`'s API expresses awkwardly. A `list` scan is clear and, at
  ≤30 items, trivially fast.
- **Composition over inheritance.** `ClippingHistory` *has a* list; it is not *a* list. It exposes
  exactly the four operations the app needs (`add`, `remove_by_id`, `list_newest_first`,
  `enforce_retention`) and hides the container. Subclassing `deque` would leak dozens of list-like
  methods that make no sense on a history (`rotate`, `extendleft`, …).
- **`enforce_retention` returns what it removed.** That return value is not decoration — the service
  turns it into a `HistoryPruned` event so the UI can react (§5). A pruning method that silently
  mutated global state would be far harder to observe and test.

Items are stored **oldest-first** (natural insertion order, which is also time order because captures
arrive chronologically), and `list_clippings_newest_first()` returns `reversed()` for display. Store
in the order that makes the logic simple; transform at the boundary that needs a different order.

---

## 5. The application service and the Observer pattern

### 5.1 The service is pure orchestration

`CopyboardService` is the application layer: it *coordinates* the domain and the ports but contains no
business rule of its own and — like the domain — never imports Qt.

```python
# copyboard/application/copyboardservice.py
def handle_new_clipboard_content(self, raw: RawClipboardData) -> None:
    clipping = self._classifier.classify_clipboard_content(raw)
    if clipping is None:
        return
    self._history.add_clipping(clipping)
    self._observers.notify_all(ClippingAdded(clipping))
    self.remove_expired_clippings()
```

Read that as a sentence: *classify → store → announce → prune*. Every collaborator
(`_classifier`, `_history`, `_sink`, `_observers`) is injected through the constructor. That is
**constructor Dependency Injection**, and it's why the service can be tested with fakes and reused
behind any front-end.

### 5.2 Observer: how the UI learns about changes without the core knowing about the UI

The core must update the UI when history changes — but the core is forbidden from importing the UI.
The **Observer pattern** resolves the tension. The *application* defines the interface; the *UI*
(an adapter) implements it:

```python
# copyboard/application/events.py
HistoryChangeEvent = ClippingAdded | ClippingRemoved | HistoryPruned

class HistoryObserver(Protocol):
    def on_history_changed(self, event: HistoryChangeEvent) -> None: ...

class ObserverRegistry:
    def notify_all(self, event: HistoryChangeEvent) -> None:
        for observer in self._observers:
            observer.on_history_changed(event)
```

The three events are a small **tagged union** (`ClippingAdded | ClippingRemoved | HistoryPruned`).
The service emits typed events; observers can pattern-match on them. `MainWindow` is registered as an
observer and reacts by refreshing its list. The core depends only on the `HistoryObserver`
*protocol* — never on `MainWindow`.

> **Why put the observer machinery in `application/`, not `domain/`?** Notification is a
> boundary/coordination concern, not a business rule. The domain doesn't care that anyone is
> watching; the application does. Placing it in the application layer keeps the domain maximally
> pure.

---

## 6. Adapters, part 1: clock, vault, and the storage model

Now we cross the line into the messy real world. Everything from here imports Qt or the OS.

### 6.1 `SystemClock` — the tiniest adapter earns its keep

```python
# copyboard/adapters/systemclock.py
class SystemClock:
    def now(self) -> datetime:
        return datetime.now()
```

Three lines, and worth every one. Because time is a *port*, every time-based rule — "is this clipping
older than 20 minutes?" — is deterministically testable. Tests inject a `FakeClock` they can
`advance(timedelta(...))`; production injects `SystemClock`. Never let untestable `datetime.now()`
calls leak into your business logic; put them behind a `Clock`.

### 6.2 The storage model — a decision, not an afterthought

Copyboard's storage model is deliberately minimal, and each choice is defensible:

| Data | Where it lives | Rationale |
|------|----------------|-----------|
| History **index** | In memory (`list`) | Ephemeral by design; clears on exit (non-goal: persistence). |
| **Images** | OS temp dir, referenced by `Path` | Bitmaps are large; keeping them in RAM would bloat the process. Spill to disk, keep a path. |
| **Path/file** clippings | Reference the *existing* file | Copying a file path shouldn't duplicate the file. Zero-copy. |
| **Text/URL** | In memory | Small; no reason to touch disk. |

The "vault" is just the OS temp directory:

```python
# copyboard/adapters/tempdirvault.py
class TempDirVault:                              # implements ClippingVault
    def store_image_bytes(self, data: bytes, suffix: str) -> Path:
        with tempfile.NamedTemporaryFile(
            prefix=self._filename_prefix, suffix=suffix, delete=False
        ) as temp_file:
            temp_file.write(data)
            return Path(temp_file.name)
```

**Design decisions embedded here:**
- **stdlib `tempfile`** → cross-platform for free (`%TEMP%` on Windows, `/tmp` on Linux/macOS) with
  no path logic of our own.
- **`delete=False`** is required: the whole point is that the file *outlives* this `with` block so
  the `ImageClipping` can reference it later. The context manager only guarantees the handle is
  flushed and closed.
- **No cleanup.** There is deliberately no managed folder and no explicit deletion — the OS owns its
  temp directory and reclaims it. That's a real trade-off (temp files accumulate until the OS cleans
  house) chosen for simplicity, and it's documented as a known limitation rather than hidden.

> **🏋 Exercise.** The "no cleanup" choice is the app's biggest data-hygiene compromise. Design a
> `CleaningVault` decorator that deletes an image file when its `ImageClipping` is pruned. Which
> event would it observe? What new failure mode (dangling path) does it introduce, and where would
> you guard against it? (Hint: `HistoryPruned` carries the removed clippings.)

---

## 7. Adapters, part 2: the clipboard, and three subtle bugs

The clipboard adapter is where the real world fights hardest. Three separate defects lived here; each
teaches something.

### 7.1 The feedback loop, and the echo guard

**The problem.** When the user clicks "Copy" on a row, the sink writes to the system clipboard. That
write fires `QClipboard.dataChanged` — which the source is listening to — so the app would immediately
*re-capture its own write* as a brand-new clipping. An infinite-ish echo.

**The fix** is a one-shot latch shared by the sink and the source:

```python
# copyboard/adapters/clipboardechoguard.py
class ClipboardEchoGuard:
    def arm(self) -> None:
        self._armed = True
    def consume_if_armed(self) -> bool:
        was_armed, self._armed = self._armed, False
        return was_armed
```

The sink `arm()`s the guard immediately before writing; the source `consume_if_armed()`s on the next
change and skips exactly that one event. It's pure Python with no Qt, so it's unit-testable on its
own. This is a classic **re-entrancy guard**, the same idea as a signal-blocker or a "programmatic
change" flag.

### 7.2 War story #1 — Windows fires the change event *several times per copy*

> **🔬 War story.** Users reported that copying a command from `cmd.exe` inserted it **four times**;
> copying from a browser inserted it **twice**. The cause: on Windows, a single copy can raise
> `dataChanged` multiple times (clipboard-chain / delayed-rendering notifications). The one-shot echo
> guard couldn't help — these aren't our own writes; they're redundant notifications of *someone
> else's* one copy.

**The fix** is to remember the last snapshot we emitted and drop consecutive duplicates. Because
`RawClipboardData` is a *frozen dataclass*, value-equality (`==`) is automatic and correct — including
for images, since `ImagePayload` compares its `bytes`. (This is §2.1's immutability paying off.)

```python
# copyboard/adapters/qt/qtclipboard.py
def _handle_clipboard_data_changed(self) -> None:
    content = self.read_current_content()
    if content.is_empty():
        return
    if self._echo_guard.consume_if_armed():   # our own re-copy → remember, skip
        self._last_content = content
        return
    if content == self._last_content:          # a redundant OS fire → skip
        return
    self._last_content = content
    if self._on_new_content is not None:
        self._on_new_content(content)
```

The ordering is careful: **read first**, ignore empties, *then* consult the echo guard, *then* dedupe.
An echo consumes the guard **and** updates `_last_content`, so any follow-up duplicate fires for our
own write are also collapsed. Only *consecutive* identical content is suppressed — copy A, then B,
then A again still records two A's, which is the behaviour you want.

**Where does this fix belong?** In the *adapter*, not the domain. Multi-firing is a Qt/Windows
artifact — the domain should never learn that Windows is chatty. Push platform quirks to the very
edge.

### 7.3 War story #2 — the type stub that lied

> **🔬 War story.** Screenshots (Win+Shift+S) never appeared in the history. There was no crash in the
> log. The image-capture path *silently* did nothing. A unit test written against the encoder
> reproduced it instantly: `QImage.save(buffer, b"PNG")` **raises `ValueError` at runtime** in this
> PySide6 build — even though its own type stub declares the `format` parameter as
> `bytes | bytearray | memoryview | None`. The exception was thrown inside the Qt `dataChanged`
> callback, where it was swallowed, so image capture failed invisibly.

The investigation probed four call variants headlessly and found that `str "PNG"` and `QImageWriter`
work while `bytes` does not. The fix uses `QImageWriter`, whose format parameter genuinely *is* a
`QByteArray`, so the stub and the runtime agree:

```python
# copyboard/adapters/qt/qtclipboard.py
def _encode_image(self, image: QImage) -> ImagePayload:
    byte_array = QByteArray()
    buffer = QBuffer(byte_array)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    # QImageWriter, not QImage.save(): save() rejects a bytes format at runtime despite its stub.
    writer = QImageWriter(buffer, QByteArray(self._image_format.upper().encode("ascii")))
    writer.write(image)
    buffer.close()
    return ImagePayload(data=bytes(byte_array.data()), image_format=self._image_format)
```

**Lessons.** (1) A type checker checks *stubs*, not the library; a green mypy does not prove a call
works. (2) An exception in a GUI event callback often vanishes — treat "it silently does nothing" as a
prime suspect for a swallowed error. (3) The reason a test *caught* this is that the encoder was
extracted into a small, directly callable method instead of being buried in the event handler.
**Testability is a debugging tool, not just a correctness tool.**

### 7.4 The sink

The sink is the mirror image, and it's where the echo guard is *armed*:

```python
def copy_clipping_to_system_clipboard(self, clipping: Clipping) -> None:
    payload = clipping.to_clipboard_payload()
    if payload.image_path is not None:
        image = QImage(str(payload.image_path))
        if image.isNull():
            return
        self._echo_guard.arm()
        self._clipboard.setImage(image)
    elif payload.text is not None:
        self._echo_guard.arm()
        self._clipboard.setText(payload.text)
```

Note it consumes a `ClipboardPayload` — the neutral value object from §2.1 — never the clipping's
internals. Domain decides *what* to copy; the adapter decides *how*.

---

## 8. The UI: window, rows, drag-out, tray, and theme

### 8.1 `MainWindow` — an observer with three responsibilities

`MainWindow` (a `QWidget`) does three things and delegates everything else:

1. **Implements `HistoryObserver`.** On any change it refreshes the list — but with a twist (§9): the
   refresh is bounced through a Qt signal with a **queued connection** so it always runs on the GUI
   thread, no matter which thread produced the change.
2. **Drives time-based retention.** A `QTimer` periodically calls
   `service.remove_expired_clippings()`, so a clipping ages out after 20 minutes *even if nothing new
   is ever copied*. (Age retention can't be event-driven; nothing "happens" when time passes — so a
   timer polls.)
3. **Rebuilds rows** from `service.list_clippings_newest_first()`, one `ClippingWidget` each.

> **🔧 UX decision — bring-to-front vs. toggle.** The naïve hotkey handler is "if visible, hide; else
> show". But if the window is open yet *buried behind another app*, "hide" is the wrong response — the
> user pressed the hotkey precisely *because* they couldn't see it. So:
> ```python
> def toggle_visibility(self) -> None:
>     if self.isVisible() and self.isActiveWindow():
>         self.hide()          # only hide when it's already frontmost
>         return
>     self.bring_to_front()    # otherwise raise + focus it
> ```
> `bring_to_front()` un-minimises, `show()`s, `raise_()`s and `activateWindow()`s. Stealing focus from
> a global hotkey is genuinely OS-dependent (Windows has a foreground-lock), so this is documented as
> a "verify manually" item — an honest boundary of what can be guaranteed in code.

### 8.2 `ClippingWidget` — a row that describes itself, and can be dragged out

Each row shows a **muted timestamp** and either a text preview or an image thumbnail — deliberately
*not* a kind label (§3.3). It renders by *asking* the clipping (`build_preview_text()`), never by
type-switching on it, except the one legitimate branch that needs a different *widget* for images:

```python
def _build_preview_label(self, clipping: Clipping) -> QLabel:
    if isinstance(clipping, ImageClipping):
        return self._build_thumbnail_label(clipping)   # QPixmap scaled to a logical size
    label = QLabel(clipping.build_preview_text())
    label.setWordWrap(True)
    return label
```

**Drag-to-export.** You can drag a row out of the viewer into any app. The implementation is textbook
Qt drag initiation, and the interesting part is *when* a drag starts:

```python
def mousePressEvent(self, event: QMouseEvent) -> None:
    if event.button() == Qt.MouseButton.LeftButton:
        self._drag_start_position = event.position().toPoint()

def mouseMoveEvent(self, event: QMouseEvent) -> None:
    if not event.buttons() & Qt.MouseButton.LeftButton:
        return
    if self._drag_start_position is None:
        return
    moved = (event.position().toPoint() - self._drag_start_position).manhattanLength()
    if moved >= QApplication.startDragDistance():   # not a click, a drag
        self._start_drag()
```

A drag begins only after the pointer moves past the platform's drag threshold — otherwise a plain
click would be misread as a drag. `_start_drag()` nulls the start position first (a re-entrancy guard
so the blocking `drag.exec()` can't spawn a second drag) and exports with `CopyAction` so dragging
never removes the item from history.

> **🔬 War story #3 — drag-and-drop pasted the image twice.** The drag payload originally offered an
> image **two ways at once** — a file URL *and* raw bitmap data — "to satisfy the widest set of drop
> targets". But rich targets (Word, OneNote, several chat apps) happily accept *both* and insert the
> image twice. The fix: offer **exactly one representation per payload**.
> ```python
> # copyboard/adapters/qt/clippingdragdata.py
> def build_drag_mime_data(payload: ClipboardPayload) -> QMimeData:
>     mime = QMimeData()
>     if payload.text is not None:
>         mime.setText(payload.text)
>     elif payload.image_path is not None:
>         mime.setUrls([QUrl.fromLocalFile(str(payload.image_path))])   # one format, one paste
>     return mime
> ```
> Subtlety uncovered by the test: `setUrls()` *also* makes `hasText()` true (Qt synthesises a
> `text/plain` from the URL). That's harmless — a drop target still picks *one* format and inserts
> once — but it's exactly the kind of thing you only learn by asserting on real `QMimeData`.
> **Text/URL/path clippings were never affected**: they carry a single `text/plain` and can't double.

### 8.3 `TrayIcon` — no asset files, four actions

The tray icon is *drawn in code* (a lettered "C" badge via `QPainter`), so the app ships with no image
assets to bundle or lose. Its menu wires four injected callbacks — show/hide, toggle theme, edit
config, quit — and it re-shows the viewer on a single click. Note the pattern: the tray widget knows
*nothing* about the window or the app; it invokes `Callable[[], None]`s handed to it by the
composition root. A view that depends only on callbacks is trivially reusable and testable.

### 8.4 Theme — Fusion + a hand-built palette, toggled live

Theming defaults to **dark** (a product call: "most people want black"). The implementation applies
Qt's cross-platform **Fusion** style plus an explicit `QPalette`, so the look is identical on every OS:

```python
# copyboard/adapters/ui/apptheme.py
def apply_theme(app: QApplication, theme: Theme) -> None:
    if theme is Theme.SYSTEM:            # leave the native palette alone
        return
    app.setStyle("Fusion")
    app.setPalette(_dark_palette() if theme is Theme.DARK else app.style().standardPalette())

class ThemeController:                    # holds the active theme; the tray flips it live
    def toggle(self) -> None:
        self._theme = next_theme(self._theme)
        apply_theme(self._app, self._theme)
```

Two small design touches: `next_theme()` is a **pure function** (`DARK↔LIGHT`, and `SYSTEM→DARK`
first), unit-tested with no `QApplication`; and the *stateful* part (`ThemeController`) is separated
from the *decision* part, so the logic is testable while the application of it stays a thin wrapper.

---

## 9. Concurrency: the global hotkey and the GUI thread

This is the trickiest correctness issue in the app, and it recurs in every GUI program that talks to
the outside world.

**The rule:** in essentially every GUI toolkit, widgets may be touched only from the **one GUI
thread**. Touch a widget from another thread and you get corruption or a crash — often intermittently,
which is the worst kind of bug.

**The tension:** `pynput` (the global-hotkey library) runs its keyboard listener on its **own
background thread**. When you press Ctrl+Shift+H, the callback fires *off* the GUI thread. If it
called `window.toggle_visibility()` directly, it would be mutating a widget from the wrong thread.

**The resolution:** marshal the call onto the GUI thread with a **queued Qt signal**. A Qt signal
connected with `QueuedConnection` posts an event to the receiver's thread's event loop instead of
calling the slot directly:

```python
# copyboard/__main__.py
class _HotkeyToggleBridge(QObject):
    triggered = Signal()

bridge = _HotkeyToggleBridge()
bridge.triggered.connect(window.toggle_visibility, Qt.ConnectionType.QueuedConnection)
hotkey = PynputHotkeyBinder(config.hotkey.toggle_viewer_hotkey, lambda: bridge.triggered.emit())
hotkey.start()
```

The pynput thread only ever calls `bridge.triggered.emit()` — safe to do from any thread. Qt then
delivers the signal to the GUI thread, where `toggle_visibility` runs safely. The bridge is a
deliberately tiny `QObject` whose entire job is to be that thread-safe hand-off point.

The binder itself keeps a clean seam: it converts a friendly combo (`ctrl+shift+h`) into pynput's
`<ctrl>+<shift>+h` format (a small, pure, unit-tested function) and owns the listener lifecycle
(`start`/`stop`). It's an *interaction* concern, so it lives in the adapters — not a business rule, so
it's kept out of the domain.

> The same queued-signal trick appears in `MainWindow`: `on_history_changed` merely `emit()`s a
> signal wired with `QueuedConnection`, so even if a future adapter delivered a change from a worker
> thread, the list refresh still happens on the GUI thread. Build the thread-safety in once, at the
> seam, and stop thinking about it.

---

## 10. Process detachment: freeing the terminal

A tray app launched from a terminal should not *hold that terminal hostage*. Copyboard re-launches
itself as a **detached background process** and lets the original invocation return the shell
immediately.

```python
# copyboard/__main__.py  (top of main)
if should_relaunch_detached(os.environ):
    relaunch_detached()
    return 0            # parent returns the shell; the detached child runs the real app
```

The mechanism (`copyboard/adapters/processdetach.py`) has several platform-aware details, each solving
a specific annoyance:

- **A guard env var breaks the recursion.** The child is spawned with `COPYBOARD_DETACHED=1`;
  `should_relaunch_detached` returns `False` when it sees that flag, so the child falls through and
  runs the app instead of detaching again. (`COPYBOARD_FOREGROUND=1` opts out entirely — used for
  development, debugging, and tests.)
- **`pythonw.exe` on Windows avoids a console flash.** `python.exe` is a *console-subsystem* binary
  that briefly allocates a console window even when detached. The code prefers `pythonw.exe` — the
  GUI-subsystem interpreter with no console at all — when it sits next to the current interpreter.
- **The right OS primitives for "no controlling terminal".** On Windows:
  `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW`. On POSIX: `start_new_session=True`
  (a fresh session, so closing the terminal doesn't SIGHUP the app).
- **Standard streams go to the null device** (`stdin/stdout/stderr=DEVNULL`) so nothing keeps the
  shell attached, and the child is intentionally **not waited on**.

> **🔬 Design story.** This is exactly why, earlier in development, running `uv run copyboard` returned
> "completed with no output" instantly — that's the *parent* exiting after spawning the detached
> child, which is the intended behaviour. During testing you set `COPYBOARD_FOREGROUND=1` to keep the
> app attached so you can see logs and tracebacks.

---

## 11. Configuration: pure model vs. tolerant loading

Configuration is split into two files on purpose, mirroring the core/adapter split:

- **`config.py`** — the *pure* model: `RetentionPolicy`, `HotkeyConfig`, `Theme`, `AppConfig`. Frozen
  dataclasses with sensible defaults, **no file I/O**. Because it does no I/O, it's safe to import from
  the domain (`ClippingHistory` needs `RetentionPolicy`).
- **`config_loading.py`** — the *infrastructure*: `load_app_config_from_json()` does the file reading
  and tolerant parsing.

The loader's guiding principle is **"a hand-edited file must never crash the app"**:

```python
# copyboard/config_loading.py
def load_app_config_from_json(config_path: Path) -> AppConfig:
    if not config_path.is_file():            # missing → all defaults
        return AppConfig()
    raw_text = config_path.read_text(encoding="utf-8")
    if not raw_text.strip():                 # empty → all defaults
        return AppConfig()
    document = json.loads(raw_text)
    if not isinstance(document, dict):       # garbage top-level → all defaults
        return AppConfig()
    return _build_app_config_from_document(document)
```

Every section falls back independently: an unknown `theme` string, a missing `hotkey` block, a
partial `retention` — each degrades to its default rather than raising. The `theme` parse shows the
tolerant enum pattern:

```python
def _build_theme(value: Any, default: Theme) -> Theme:
    if not isinstance(value, str):
        return default
    try:
        return Theme(value.strip().lower())  # "DARK" / " light " both work
    except ValueError:
        return default                        # "chartreuse" → default, no crash
```

There's also `write_default_config_file()`, which seeds a pretty-printed `config.json` — used by the
tray's **"Edit config…"** action so the user always has a real file to open and edit.

> **🔧 UX decision — no settings *UI*.** Configuration is a JSON file, plus a tray shortcut to open it,
> plus a live theme toggle. Building a preferences dialog was an explicit *non-goal* — the smallest
> thing that lets a power user tune retention and hotkey without inventing a whole settings screen.
> (Trade-off: edits to `config.json` apply on next launch, which is documented.)

---

## 12. The composition root: where it all comes together

`main()` in `__main__.py` is the *only* place that names concrete adapters. Read it as the wiring
diagram of the entire app:

```python
def main() -> int:
    if should_relaunch_detached(os.environ):     # 1. free the terminal (§10)
        relaunch_detached(); return 0

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)         # 2. tray app: closing the window ≠ quitting

    config_path = Path(DEFAULT_CONFIG_FILENAME)
    config = load_app_config_from_json(config_path)   # 3. config (§11)
    theme_controller = ThemeController(app, config.theme)  # 4. theme (§8.4)

    clock = SystemClock()                                    # 5. build adapters + core
    classifier = ClippingClassifier(vault=TempDirVault(), clock=clock)
    history = ClippingHistory(config.retention)
    echo_guard = ClipboardEchoGuard()
    clipboard = app.clipboard()
    sink = QtClipboardSink(clipboard, echo_guard)
    service = CopyboardService(classifier=classifier, history=history, clock=clock, sink=sink)

    source = QtClipboardSource(clipboard, echo_guard)        # 6. capture → service (push)
    source.set_new_content_listener(service.handle_new_clipboard_content)

    window = MainWindow(service); window.show()              # 7. views
    tray = TrayIcon(create_default_tray_icon(), window.toggle_visibility,
                    theme_controller.toggle,
                    lambda: _open_config_in_editor(config_path, config), app.quit)
    tray.show()

    bridge = _HotkeyToggleBridge()                           # 8. hotkey → GUI thread (§9)
    bridge.triggered.connect(window.toggle_visibility, Qt.ConnectionType.QueuedConnection)
    hotkey = PynputHotkeyBinder(config.hotkey.toggle_viewer_hotkey, lambda: bridge.triggered.emit())
    hotkey.start()

    try:
        return app.exec()                                    # 9. run the event loop
    finally:
        hotkey.stop()                                        # 10. always stop the listener thread
```

Everything you learned above is one line here. The composition root is where the *shared* mutable
collaborators are created exactly once and handed around: note that **one** `echo_guard` and **one**
`clipboard` are shared between the source and the sink — that shared instance is what makes the
feedback-loop suppression in §7.1 work. Dependency injection isn't a ceremony; it's the thing that
lets two adapters cooperate through an object the composition root controls.

---

## 13. Testing strategy: fakes, offscreen Qt, and honest limits

The whole architecture exists to make testing cheap. It does.

**The core is tested with in-memory fakes.** Because every dependency is a port, tests substitute
tiny fakes and never touch Qt, the real clipboard, or the filesystem:

```python
# tests/fakes.py
class FakeClock:
    def now(self) -> datetime: ...
    def advance(self, delta: timedelta) -> None: ...   # deterministic time travel
class FakeVault:                     # records bytes instead of writing files
    def store_image_bytes(self, data, suffix) -> Path: ...
class FakeClipboardSink:             # records what was re-copied
    def copy_clipping_to_system_clipboard(self, clipping) -> None: ...
```

This is why a retention test can "wait" 20 minutes in a microsecond (`clock.advance(...)`), and why a
classifier test asserts on kinds without a display.

**Qt tests run headless.** A shared fixture forces Qt's **offscreen** platform so UI/adapter tests
need no display, even in CI:

```python
# tests/conftest.py
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

@pytest.fixture(scope="session")
def qt_app() -> Iterator[QApplication]:
    existing = QApplication.instance()
    yield existing if isinstance(existing, QApplication) else QApplication([])
```

**Adapter tests go white-box where it earns its keep.** The dedup test (§7.2) calls the private
`_handle_clipboard_data_changed()` directly to *simulate* Windows firing the event repeatedly, and
asserts the listener receives the content exactly once. The image test (§7.3) sets a real `QImage` on
the offscreen clipboard and reads it back through the public `read_current_content()`. Both were
written to reproduce actual bugs — the discipline is **reproduce first, then fix**.

**Honest limits are written down, not pretended away.** Some behaviours genuinely can't be verified
headlessly — the real `Win+Shift+S` clipboard round-trip, the multi-fire behaviour against a real
console, the hotkey stealing focus from another app, live theme repaint. These live in a `TODO.md`
manual-checklist instead of being faked into a false green. Knowing *what your tests don't cover* is
as senior as the tests themselves.

---

## 14. Tooling & CI: the quality gate across 12 environments

**Every function is fully typed** and mypy runs strict (`disallow_untyped_defs`,
`disallow_incomplete_defs`, `check_untyped_defs`) over **both** `copyboard/` and `tests/`. Unannotated
code fails the gate — tests included. **ruff** lints and formats (`E, F, I, UP, B, SIM, C4, RUF`) over
source and tests. The commands, via `uv`:

```
uv run ruff check .     # lint          uv run mypy .     # type-check (src + tests)
uv run ruff format .    # format        uv run pytest     # tests
```

**CI runs the suite on a 3 × 4 matrix** — Windows, Linux, macOS × Python 3.10 / 3.11 / 3.12 / 3.13 —
plus a single lint/type job. Two non-obvious things had to be solved to make that real:

- **Python floor.** Testing 3.10 means the project must *install* on 3.10, so `requires-python` was
  lowered from `>=3.12` to `>=3.10` (after verifying the code uses no 3.11+/3.12-only runtime
  features), and `ruff target-version` / `mypy python_version` were aligned to `py310`. The lockfile
  resolved PySide6 to an **abi3 stable-ABI wheel** (`cp310-abi3`) — one wheel that runs on 3.10
  through 3.13 — so the whole matrix installs from a single pin.
- **Headless Linux needs a display for `pynput`.** Qt is forced offscreen, but `pynput`'s Linux
  backend connects to an X server *at import time*. So the Linux job installs Qt/X11 system libs plus
  `xvfb` and runs `xvfb-run -a uv run pytest`; Windows and macOS run pytest directly.

```yaml
# .github/workflows/tests.yml (essence)
strategy:
  fail-fast: false                       # one cell failing doesn't cancel the rest
  matrix:
    os: [ubuntu-latest, windows-latest, macos-latest]
    python-version: ["3.10", "3.11", "3.12", "3.13"]
env:
  QT_QPA_PLATFORM: offscreen
```

---

## 15. Cross-platform cheat sheet

The single hardest thing about this app is that it must behave on three OSes. Every place that
required per-platform care, in one table:

| Concern | Windows | Linux | macOS |
|---------|---------|-------|-------|
| **Duplicate clipboard events** | fires 2–4× per copy → dedup in `QtClipboardSource` (§7.2) | typically once | typically once |
| **Image encode** | `QImage.save(bytes)` raises → use `QImageWriter` (§7.3) | same fix, uniform | same fix, uniform |
| **Detach / no console flash** | `pythonw.exe` + `DETACHED_PROCESS`/`CREATE_NO_WINDOW` | `start_new_session=True` | `start_new_session=True` |
| **Global hotkey** | works | needs **X11** (not native Wayland) | needs **Accessibility** permission |
| **Temp dir** | `%TEMP%` via `tempfile` | `/tmp` via `tempfile` | `/tmp` via `tempfile` |
| **Theme** | Fusion + palette (uniform look) | same | same |
| **Headless test display** | not needed | needs `xvfb` for pynput import | not needed |

The recurring strategy: **normalise at the adapter**, so the core never learns any of this exists.

---

## 16. Architecture Decision Record (summary)

A compressed ADR log — the decision, and the one-line reason.

| # | Decision | Why |
|---|----------|-----|
| 1 | Hexagonal / Ports & Adapters | Core reusable + testable; GUI is a replaceable detail. |
| 2 | Ports as `Protocol` (structural) | Adapters need no import of the domain; purest DIP. |
| 3 | Separate `RawClipboardData` (in) vs `ClipboardPayload` (out) | Input and output have genuinely different shapes (bytes vs path). |
| 4 | `Clipping` polymorphism + `TextualClipping` base | New kinds don't touch UI/re-copy logic; shared behaviour once. |
| 5 | Address clippings by `uuid` id, not index | Indices shift under pruning; ids are stable. |
| 6 | Detectors as one-class-each Strategy | Isolated, injectable, purely syntactic, testable. |
| 7 | Keep classifiers even after hiding kinds in UI | Presentation change shouldn't amputate domain capability (future colours). |
| 8 | `list` + composition for history, not `deque` subclass | Age bound needs a scan; expose only 4 operations. |
| 9 | Observer for UI updates | Core notifies without importing the UI. |
| 10 | In-memory index + temp-dir image vault, no cleanup | Ephemeral by design; keep RAM small; OS owns temp. |
| 11 | One-shot echo guard | Suppress re-capturing our own re-copy. |
| 12 | Consecutive-duplicate dedup in the adapter | Absorb Windows' multi-fire without polluting the core. |
| 13 | `QImageWriter` over `QImage.save` | Runtime rejects the bytes format the stub advertises. |
| 14 | Queued Qt signal for the pynput callback | Marshal a background-thread event onto the GUI thread safely. |
| 15 | Detach via re-spawn (+ `pythonw`, guard env) | Free the launching terminal; no console flash. |
| 16 | Single drag representation per payload | Two representations made rich targets paste twice. |
| 17 | Dark theme default via Fusion + palette | Consistent cross-OS look; "most want black". |
| 18 | `requires-python >=3.10` + abi3 wheel | One wheel spans the whole 3.10–3.13 test matrix. |

---

## 17. Exercises & extension challenges

Ordered roughly by difficulty. Each is doable *without* violating the architecture — that constraint
is the exercise.

1. **Pin favourites.** Add a `pinned: bool`… but `Clipping` is frozen. How do you represent "pinned"
   without mutating a value object, and where does the pin state live so retention won't prune a
   pinned item? (Hint: is "pinned" a property of the clipping, or of the history?)
2. **Colour-code kinds.** The classifiers already tag URL/Command/Path. Style `ClippingWidget` per
   kind (accent for URL, red for command, blue for `.py` paths) — with **zero** changes to
   `domain/`. Which layer owns the kind→colour mapping?
3. **De-duplicate across the whole history**, not just consecutively — copying A, B, A should *move*
   the old A to the top rather than add a third entry. Which class changes, and does the change belong
   in the domain or the adapter? (Contrast with the *consecutive* dedup in §7.2, which is an OS
   artifact.)
4. **Persist history to disk** so it survives a restart (a stated non-goal — now make it a goal).
   Define the port first. What's the minimal `HistoryStore` protocol, and how do image temp files
   complicate "reload after restart"?
5. **A web front-end.** Reuse `domain/` + `application/` untouched. What are the web implementations of
   `ClipboardSource`, `ClipboardSink`, and `HistoryObserver`? (This is the ultimate test of whether the
   dependency rule was actually respected — if any Qt leaked into the core, you'll find it here.)
6. **Clean up temp images** (the §6.2 exercise) as a `ClippingVault`/observer decorator, without the
   domain learning that files exist.

---

## 18. Glossary

- **Hexagonal Architecture (Ports & Adapters).** A style where business logic (the core) depends only
  on abstractions (ports) it defines, and all technology (UI, DB, OS) lives in adapters that implement
  those ports. Dependencies point inward.
- **Port.** An interface the core owns and depends on. Here: `Protocol` classes.
- **Adapter.** A concrete implementation of a port using a specific technology (`SystemClock`,
  `QtClipboardSink`).
- **Composition root.** The single place (here `__main__.py`) that instantiates concrete adapters and
  injects them — the only file allowed to know every concrete class.
- **Dependency Inversion Principle (DIP).** Depend on abstractions, not concretions; both high- and
  low-level modules depend on the abstraction.
- **Dependency Injection (DI).** Passing a collaborator in (usually via the constructor) rather than
  constructing it internally — the mechanism that realises DIP.
- **Value object.** A small immutable object defined by its values, with meaningful equality
  (`RawClipboardData`). Frozen dataclasses.
- **Observer pattern.** Subjects notify registered observers of events through an interface, decoupling
  who-changes from who-reacts (`HistoryObserver`).
- **Strategy pattern.** Interchangeable algorithms behind a common shape (the detector classes).
- **Structural typing (`Protocol`).** Conformance by shape (having the right methods), checked
  statically, without a nominal `class X(Port)` declaration.
- **Re-entrancy guard.** A flag that prevents a piece of code from reacting to its own side effect
  (the `ClipboardEchoGuard`; the drag start-position reset).
- **Queued connection.** A Qt signal delivery mode that posts the call to the receiver's thread's event
  loop — the tool for crossing from a worker thread to the GUI thread safely.
- **abi3 wheel.** A Python wheel built against the stable ABI, installable on the tagged CPython
  version *and all later ones* — one file for many Python versions.

---

*This guide describes Copyboard as built. Where the code and this document disagree, the code wins —
and fixing the mismatch is itself a good exercise. Companion docs: [SPEC.md](SPEC.md) (what & why),
[ARCHITECTURE.md](ARCHITECTURE.md) (how, in brief), [TODO.md](TODO.md) (manual-test checklist).*
