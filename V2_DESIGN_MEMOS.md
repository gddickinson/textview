# v2.1+ design memos

Each remaining moonshot summarized: what it costs, what it unlocks, what
controllers it touches, where the design risk lies. Order is rough
"easiest payoff first" — none of these have been started.

---

## A. Quick-open palette (`Ctrl+P`)

**What it is:** companion to the existing `Ctrl+K` action palette, but
fuzzy-finds *files* under the active project root. VS Code / Sublime style.

**Cost:** ~80 lines. Reuses the `_fuzzy_score` ranker from `command_palette.py`.

**Unlocks:** opening any file in a project without dragging the tree open.

**Touches:** new `src/quick_open.py`; one action in `actions.py`; reads
`ProjectPanel._model.rootPath()` for the index source.

**Risks:** glob-walking large project trees on every keystroke is slow.
Mitigation: build the file list once on dialog open and cache; or use
`os.scandir` with a 5k-entry cap.

**Recommendation:** ship first. Highest payoff per line of code.

---

## B. Real PTY terminal (Mac/Linux)

**What it is:** replace today's "subprocess runner" with a true terminal —
`pty.openpty()` + a [`pyte`](https://pypi.org/project/pyte/)-driven
character grid. Handles `vim`, `htop`, `less`, ANSI cursor positioning,
shell prompts. The current `Runner` becomes a degraded path for non-PTY
languages.

**Cost:** ~300 lines new (`src/pty_terminal.py`). pyte is small (~300 KB)
and pure Python. Does not work on Windows — needs `pywinpty`/ConPTY shim
(another ~150 lines, deferred).

**Unlocks:** running interactive REPLs (ipython, node, psql) without
losing prompts. Unblocks "drop into shell" workflows. The LLM agent can
use the terminal too via the existing `run_command` tool.

**Touches:** new file; `RunController` gets a "use PTY" toggle; output
rendering is custom (paint cells from pyte's screen) so the existing
`AnsiParser` for the simple runner still applies for non-PTY commands.

**Risks:**
- **Sizing**: the PTY needs to be told the terminal size; we re-send on
  resize. Standard but fiddly.
- **Color cube**: pyte gives us a 256-color screen; mapping to QColor is
  straightforward.
- **Performance**: for big output (e.g. `find /`) we may need to throttle
  paints (60 fps cap; coalesce updates).

**Recommendation:** worthwhile if running interactive shells matters. If
the user just wants `python script.py` output, the current runner already
covers it — skip.

---

## C. Inline LLM suggestions (Copilot ghost text)

**What it is:** as the user types in `CodeViewer`, after a 400 ms idle a
small completions request goes to Claude/Ollama with the surrounding
buffer; the response is rendered as grey ghost text after the cursor;
`Tab` accepts, `Esc`/any-keystroke rejects.

**Cost:** ~400-500 lines. Real complexity is in the rendering and the
debounce/cancel:
- Ghost-text overlay: extra `QPainter` pass on the viewport drawing the
  proposed text in a faded foreground; cursor positioning math.
- Debounce: `QTimer` per buffer; cancel pending request on each keystroke.
- API: dedicated provider method, not the chat-stream one — a
  *non-streaming* one-shot completion, smaller token budget, no system
  prompt.

**Unlocks:** the headline AI-pair feature people expect now. Differentiates
from "chat-only" tools.

**Touches:** `CodeViewer.paintEvent` (new overlay), new
`src/llm/completions.py` provider mode, settings (`inline_suggestions:
bool`, debounce ms, max suggestion length).

**Risks:**
- **Quality without context**: we'd send only the local file. For best
  results we'd want neighboring files in the project — adds size.
- **Cost**: every keystroke pause is a paid API call. Mitigations:
  per-day budget cap; only fire on word/line-end transitions; Ollama
  default for local-free option.
- **Race conditions**: multiple in-flight requests, only the latest
  matters. Track a generation counter.

**Recommendation:** big lift, big payoff. Phase it: ship "ghost text
on demand" (Cmd+. triggers a single suggestion) before the auto-debounce
loop.

---

## D. Diff viewer

**What it is:** a sixth viewer mode (`MODE_DIFF`) that shows a unified
diff between two files (or current vs git HEAD). Uses Python's `difflib`
or shells out to `git diff` for git-tracked files. Renders red/green
hunks with line numbers in the existing `CodeViewer` (custom
`QSyntaxHighlighter`).

**Cost:** ~250 lines. New `src/diff_view.py`; a small "Compare with…"
dialog; integration with git via `subprocess`.

**Unlocks:** see what changed since last commit; review pull requests
locally; compare two arbitrary files.

**Touches:** new file; `actions.py` gets `Compare with file… / Compare
with HEAD`; `viewer.py` gets `MODE_DIFF` and a `show_diff()` shortcut.

**Risks:** rendering performance on huge diffs (10k+ lines). Use
`QSyntaxHighlighter` so coloring is incremental.

**Recommendation:** uncontroversial mid-size feature. Bundle with the
project panel — right-click a file → "Compare with…".

---

## E. Multi-window

**What it is:** drag a tab out into its own `MainWindow`. Windows share
the same `SettingsManager` and `keyring` but have independent viewers,
edit state, terminals, chats.

**Cost:** ~200-300 lines refactor across every controller currently
holding a `self.window` reference. Most can stay; some (recent files,
bookmarks) want one shared instance, others (edit, run) want per-window.

**Unlocks:** side-by-side editing — open a doc on one monitor, code on
another.

**Touches:** every controller; introduces a `WindowGroup` /
`Application` registry. `tab_bar` gains "detach tab to new window".

**Risks:**
- **State sharing**: lots of fiddly decisions per controller.
- **Settings application**: `SettingsManager.changed` must reach all
  windows — single signal hub.
- **Hooks fire on which window?** Probably on the active one. Need a
  policy.

**Recommendation:** valuable but expensive. Defer until clear demand
from the user.

---

## F. Plugin API

**What it is:** standardize the existing scripting hooks into a real
plugin system. Plugins live in `~/.config/TextView/plugins/<name>/`
with a `plugin.toml` manifest describing entry points, menu
contributions, dependencies, semver constraint. Loaded at startup via
the same hook machinery, with a richer event surface.

**Cost:** ~200 lines new in `src/plugins.py`; existing `hooks.py`
keeps working as a thin lightweight option.

**Unlocks:** third-party ecosystem. Plugins can add custom viewer modes,
LLM tools, language formatters, etc.

**Touches:** new file; small additions to controllers exposing public
methods plugins should rely on.

**Risks:**
- **Stable API surface**: the moment plugins ship, our internals
  freeze. Bigger commitment than feature size suggests.
- **Security**: third-party plugins are arbitrary Python — same trust
  model as the existing hooks dir, but more visible. Need a "Plugins"
  preferences page that lists what each one declared and lets the user
  disable any.

**Recommendation:** worthwhile only if there's interest from external
contributors. Until then, the hooks dir does 90% of what plugins would.

---

## Recommended order

1. **A — Quick-open palette** (Ctrl+P): cheapest, biggest user win.
2. **D — Diff viewer**: clean self-contained mid-size feature.
3. **C — Inline LLM suggestions** (phase 1 = on-demand only): the
   killer feature, but de-risked.
4. **B — PTY terminal**: only if interactive shells matter.
5. **E / F — Multi-window / plugin API**: defer.

Each can be picked off independently — no inter-dependencies. The user
can interrupt to redirect at any wake-up.
