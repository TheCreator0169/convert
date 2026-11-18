"""Entry point. `--cli [format] files...` converts without a window; `--cli` alone lists formats."""
import sys
from pathlib import Path

from . import settings
from .formats import OUTPUTS


def cli(argv):
    if getattr(sys, "frozen", False):  # a windowed exe has no console: attach the parent's so output shows
        import ctypes
        if ctypes.windll.kernel32.AttachConsole(-1):
            sys.stdout = open("CONOUT$", "w", encoding="utf-8")
            sys.stderr = sys.stdout
    if not argv:
        for t, fmts in OUTPUTS.items():
            print(f"{t}: " + " ".join(fmts))
        return 0
    fmt_id, files = argv[0], argv[1:]
    from .converter import convert_file
    st = settings.load()
    code = 0
    for f in files:
        try:
            notes = []
            for out in convert_file(f, fmt_id, st["options"], st["trash_originals"], notes=notes):
                print(f"{f} -> {out}")
            for n in notes:
                print(f"warning: {n}", file=sys.stderr)
        except Exception as e:  # report each file, keep going
            settings.setup_logging().exception("failed %s", Path(f).name)
            print(f"{f}: {e}", file=sys.stderr)
            code = 1
    return code


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    settings.setup_logging()
    if argv and argv[0] == "--cli":
        return cli(argv[1:])
    if argv and argv[0] in ("--install-menu", "--uninstall-menu"):
        from . import shell_integration
        (shell_integration.install if argv[0] == "--install-menu" else shell_integration.uninstall)()
        return 0
    from . import ui
    return ui.run([a for a in argv if Path(a).is_file()])


if __name__ == "__main__":
    sys.exit(main())
