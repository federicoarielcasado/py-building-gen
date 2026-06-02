"""Entry point de la aplicación py-building-gen."""

import sys

from PyQt6.QtWidgets import QApplication

from ui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("py-building-gen")
    app.setApplicationVersion("0.1.0")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
