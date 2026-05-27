"""
pipboy_app.py
-------------
Entry point for the Pip-Boy Health PyQt6 companion app.

Requirements:
    pip install PyQt6

Run:
    python pipboy_app.py

Make sure pipboy_auth.py is in the same folder and you have
run it at least once to create ~/.pipboy_token.json
"""

import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore    import Qt
from ui.style        import APP_STYLE
from ui.main_window  import PipBoyWindow


def main():
    # High-DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication(sys.argv)
    app.setApplicationName("Pip-Boy Health")
    app.setApplicationDisplayName("Pip-Boy Health")
    app.setOrganizationName("Vault-Tec")

    # Apply global stylesheet
    app.setStyleSheet(APP_STYLE)

    # Don't quit when last window closes (lives in tray)
    app.setQuitOnLastWindowClosed(False)

    window = PipBoyWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
