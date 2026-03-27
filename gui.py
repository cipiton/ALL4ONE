from __future__ import annotations

from engine.app_paths import get_app_root
from ui.main_window import MainWindow


def main() -> int:
    app = MainWindow(get_app_root(__file__))
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
