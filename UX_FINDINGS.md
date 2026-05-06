# UX_FINDINGS.md

Curated findings from the v3.0 I.3 screenshot-driven UX hardening pass.
The auto-generated `UX_REPORT.md` (under `/tmp/textview_ux/`) carries
the raw matrix; this file is the persistent narrative.

The methodology: `python3 -m src.ux_screenshots /tmp/textview_ux`
walks 8 viewer modes × 3 themes (Solarized Dark / Light / Dracula)
plus a "kitchen sink" all-docks shot per theme. 24 PNGs per run.
Every fix below was caught by inspecting one of those PNGs.

---

## Findings

### F1 — Table view ignored theme changes (FIXED, W5)

**Symptom**: switching from Solarized Dark to Light or Dracula left the
table cells in dark Solarized colours against an otherwise correctly
re-themed app shell.

**Diagnosis**: Qt's `QWidget.setStyleSheet` runs an internal
unpolish/polish cycle that pulls properties expressible in stylesheets
back into the palette. We had `color:` and `background-color:` rules on
the `QTableView` selector, so each polish copied those values into the
palette and a subsequent `setColor(Text, …)` was overwritten by the
next refresh.

**Fix** (in `src/view_styler.py::apply_table_theme`): clear stylesheet
to `""` first, set palette via `setColor` for all roles, re-set the
stylesheet **without** `color:` / `background-color:` for the
QTableView selector. Stylesheet keeps only what palette can't express
(`gridline-color`, header bg/fg, header borders, corner-button).

**Verified across 3 themes**: Light → white-on-dark-text with stripes,
Dracula → purple-bg with light text, Solarized Dark unchanged.

### F2 — Bracket-pair highlight had a hardcoded dark colour (FIXED, W6)

**Symptom**: in the JSON-Light shot, the outer `{` (line 1) and `}`
(last line) had jarring near-black blocks behind them. On dark themes
the same code was nearly invisible.

**Diagnosis**: `viewer.py::CodeViewer._bracket_selections` used a
fixed `#3c3f41` for the matching-bracket highlight regardless of
theme.

**Fix**: added `set_bracket_match_color(color)` to `CodeViewer` and
made `view_styler.apply_theme` set it from `theme["selection_bg"]`.
Selection bg is already tuned per theme: subtle on dark, soft blue on
light, lavender on Dracula — exactly the palette range a
bracket-match cue wants.

### F3 — PDF view renders blank in offscreen mode (HARNESS LIMITATION)

**Symptom**: `pdf__*.png` shots are entirely blank in the central
viewer area despite the document being attached.

**Diagnosis**: `QPdfView` paints via a graphics path that
`widget.grab()` doesn't capture without a GL context. The
`createPlatformOpenGLContext` warning at startup hints at the same.
With a real screen the PDF renders fine (verified earlier in the
session via the live GUI).

**Resolution**: not a real bug — documenting as a known limitation of
the headless harness. PDF UX testing has to happen with a live
display, or via `screenshot_pdf_pages` (which rasterises through
`QPdfDocument` directly and bypasses the widget).

### F5 — Custom dialogs ignored the active theme (FIXED, W7)

**Symptom**: opening **Stats** or **Plot** while in Dracula or
Solarized Dark left the dialog rendered in default light Qt chrome
(grey background, white form fields). Stuck out badly against the
themed main window. Captured in
`dialog_stats__Dracula.png` / `dialog_plot__Dracula.png` (pre-fix).

**Diagnosis**: dialogs inherit from `QApplication.palette()` rather
than from any widget we paint in `view_styler.apply_theme`. The
viewer styling never propagated up to the application palette.

**Fix** (`src/view_styler.py`): added `apply_app_palette(theme)`
which builds a `QPalette` from theme colours
(`Window/WindowText/Base/Text/Button/Highlight/ToolTip…`) and calls
`QApplication.instance().setPalette(pal)`. Called once per
`apply_theme()`. Native macOS chrome (file picker, OS-supplied
modals) ignores QApplication palette and keeps system colours, which
is what we want.

**Bonus**: also themed the **matplotlib figure** in `PlotDialog._plot()`
— `figure.patch.set_facecolor(...)`, `ax.set_facecolor(...)`, spines
+ ticks + axis labels coloured from the palette `Text` role. The
chart no longer looks like a glowing white sheet against a Dracula
sidebar.

**Verified**: `dialog_stats__Dracula` is now dark with light text;
`dialog_plot__Dracula` has dark axis chrome with the same blue bar
fill (matplotlib's default cycler). Light + Solarized Dark unchanged.
Code/Markdown/Table views unchanged (already explicitly themed).

### F6 — PivotDialog defaulted Values to a non-numeric column (FIXED, W13)

**Symptom**: opening the pivot dialog showed `Values: name  (non-numeric
— count only)` as the default, even though `age` and `score` are
numeric. Selecting `sum` while a non-numeric column was bound for
Values would silently drop everything.

**Fix**: `PivotDialog.__init__` now scans `model.numeric_columns()`
and pre-selects the first column flagged numeric. Strings remain
selectable (with the explanatory suffix) for `count` use.

### F7 — Placeholder text in dialog filter inputs is hard to read on dark themes (DOCUMENTED, low priority)

**Symptom**: "Type to filter actions…" and "Type to filter files…"
in the command palette and quick-open dialogs render in Qt's default
placeholder grey, which is fine on Light but blends into the
background on Dracula and Solarized Dark.

**Resolution**: low-priority. Fix would be to set
`QPalette.ColorRole.PlaceholderText` to a tonally adjusted version of
the theme's `fg` (e.g. fg with reduced alpha) in `apply_app_palette`.
Tracked but deferred — the user types into the input within seconds,
so the placeholder is only visible briefly.

### F4 — All-docks-shown shot is unreadable at 1280px (KNOWN, accepted)

**Symptom**: `kitchen__*.png` (every dock visible) shrinks each dock
to a sliver and the central viewer becomes a vertical band.

**Resolution**: accepted — the shot is meant to verify *that nothing
collides*, not that the layout is usable. A real user would never
have all 7 docks open at once. The test value is detecting hidden
overlaps; for that purpose 1280px is fine. Future passes can run at
1920×1200 if dense-layout review is needed.

---

## Things still to review (W7 + later)

- **Dracula docks** — verify the chat / metadata / spreadsheet panel
  internals match the theme. Quick scan looks consistent but could
  hide gradient mismatches.
- **Sepia theme** — wasn't in the matrix; prose-readability theme that
  may have different contrast trade-offs.
- **Image / video viewers** — not in the matrix because no sample
  files were loaded. Add a known-good image + tiny video to
  `sample_files/` and extend the matrix.
- **Dialogs** — Stats, Plot, Color picker, Set API key, Goto line,
  Command palette — none captured. Worth a separate dialog matrix.
- **Find/replace bar visible state** — captures of the search bar
  active.
- **Edit mode visual feedback** — currently relies on a dirty `*` in
  the title; double-check it's noticeable.

Run `python3 -m src.ux_screenshots <out_dir>` to regenerate.
