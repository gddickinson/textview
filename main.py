"""TextView entry point.

Usage:
    python main.py                                  # GUI, welcome screen
    python main.py path/to/file                     # GUI, opens file
    python main.py FILE --headless --screenshot OUT.png
    python main.py FILE --headless --screenshot-pdf-pages DIR --dpi 150
"""
import argparse
import os
import sys
from pathlib import Path


def _bootstrap_qt_plugin_path():
    """Point Qt at PyQt6's bundled plugins.

    Some environments (notably conda installs of PyQt6) ship Qt plugins inside
    the package but don't register the path with the Qt loader, so the cocoa
    platform plugin isn't found and the app aborts at startup. Setting
    QT_QPA_PLATFORM_PLUGIN_PATH before any Qt import side-steps that.
    """
    import PyQt6
    plugins = Path(PyQt6.__file__).parent / "Qt6" / "plugins"
    if plugins.is_dir():
        os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", str(plugins / "platforms"))
        os.environ.setdefault("QT_PLUGIN_PATH", str(plugins))


def _parse_args():
    p = argparse.ArgumentParser(
        prog="textview",
        description="A modular GUI for viewing text, code, markup, and document files.",
    )
    p.add_argument("file", nargs="?", help="File to open on launch.")
    p.add_argument(
        "--headless", action="store_true",
        help="Use the offscreen Qt platform — no window is shown. "
             "Combine with --screenshot or --screenshot-pdf-pages to extract images and exit.",
    )
    p.add_argument(
        "--screenshot", metavar="OUT",
        help="Render a single screenshot of the viewer (or first PDF page) "
             "to OUT and exit.",
    )
    p.add_argument(
        "--screenshot-pdf-pages", metavar="DIR",
        help="Render every page of a loaded PDF as an image into DIR and exit.",
    )
    p.add_argument(
        "--dpi", type=int, default=150,
        help="DPI used for PDF rasterization (default: 150).",
    )
    p.add_argument(
        "--control-port", type=int, default=0,
        help="If non-zero, start a JSON-RPC control server on TCP "
             "127.0.0.1:<PORT> so external processes can drive the GUI. "
             "Use 0 to disable (default).",
    )
    return p.parse_args()


def _run_headless_screenshots(window, args) -> int:
    """Take whatever screenshots were requested and return an exit code."""
    from src.exporter import (
        screenshot_widget, render_pdf_page, render_pdf_pages,
    )

    is_pdf = window._current_format == "pdf" and window._pdf.doc is not None

    if args.screenshot_pdf_pages:
        if not is_pdf:
            print("--screenshot-pdf-pages requires a PDF file.", file=sys.stderr)
            return 2
        paths = render_pdf_pages(window._pdf, args.screenshot_pdf_pages, dpi=args.dpi)
        print(f"Saved {len(paths)} page(s) to {args.screenshot_pdf_pages}")
        for p in paths:
            print(f"  {p}")

    if args.screenshot:
        if is_pdf:
            ok = render_pdf_page(window._pdf, 0, args.screenshot, dpi=args.dpi)
        else:
            ok = screenshot_widget(window.viewer.active_widget(), args.screenshot)
        print(f"{'Saved' if ok else 'FAILED'} screenshot → {args.screenshot}")
        if not ok:
            return 1

    return 0


def main():
    args = _parse_args()

    if args.headless or args.screenshot or args.screenshot_pdf_pages:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    _bootstrap_qt_plugin_path()

    from PyQt6.QtWidgets import QApplication
    from src.app import MainWindow

    app = QApplication([sys.argv[0]])
    app.setApplicationName("TextView")
    app.setOrganizationName("ClaudeText")
    app.setApplicationDisplayName("TextView")

    window = MainWindow()
    window.restore_workspace()

    if args.control_port:
        from src.control_server import ControlServer
        window._control_server = ControlServer(window, parent=window)
        actual = window._control_server.listen(args.control_port)
        if actual > 0:
            print(f"Control server listening on 127.0.0.1:{actual}", flush=True)
        else:
            print(f"Control server failed to bind port {args.control_port}",
                  file=sys.stderr, flush=True)

    if args.file:
        if args.file.startswith(("http://", "https://", "about:")):
            window.open_url(args.file)
        else:
            candidate = Path(args.file)
            if candidate.is_file():
                window.open_file(str(candidate))
            else:
                print(f"File not found: {args.file}", file=sys.stderr)
                return 2
    elif not args.headless and not args.screenshot and not args.screenshot_pdf_pages:
        # No file argument — restore the tabs from the previous session.
        window.restore_tabs()

    if args.screenshot or args.screenshot_pdf_pages:
        # Headless extraction path — no window, no event loop, just write
        # files and exit.
        return _run_headless_screenshots(window, args)

    if args.headless:
        # Headless without a screenshot is a no-op; report status and exit.
        print("Headless launch OK. (No --screenshot / --screenshot-pdf-pages given.)")
        return 0

    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
