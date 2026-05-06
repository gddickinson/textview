# TextView — project Claude instructions

A PyQt6 GUI for viewing text, code, markup, and document files with live
display configuration. Modular: every module is under 500 lines and focused
on a single concern.

Always check `@INTERFACE.md` first for orientation before opening any source
file. Update `INTERFACE.md` whenever a module is added, removed, or its
responsibilities shift.

Update `SESSION_LOG.md` with significant progress.

## Run

```
python3 main.py                # opens with welcome screen
python3 main.py path/to/file   # opens that file
```

Drag-and-drop files onto the window to open them.

@INTERFACE.md
