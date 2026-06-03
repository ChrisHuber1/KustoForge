import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import QApplication, QMainWindow, QStatusBar
from PySide6.QtGui import QPalette, QColor, QIcon
from PySide6.QtCore import Qt
from ui_builder import QueryBuilderWidget


def apply_dark_theme(app):
    app.setStyle("Fusion")
    p = QPalette()

    DARK_BG   = QColor(30, 30, 30)
    DARKER_BG = QColor(22, 22, 22)
    MID_DARK  = QColor(45, 45, 45)
    LIGHT_TXT = QColor(212, 212, 212)
    DIM_TXT   = QColor(140, 140, 140)
    HIGHLIGHT = QColor(0, 100, 180)

    p.setColor(QPalette.Window, DARK_BG)
    p.setColor(QPalette.WindowText, LIGHT_TXT)
    p.setColor(QPalette.Base, DARKER_BG)
    p.setColor(QPalette.AlternateBase, MID_DARK)
    p.setColor(QPalette.Text, LIGHT_TXT)
    p.setColor(QPalette.Button, MID_DARK)
    p.setColor(QPalette.ButtonText, LIGHT_TXT)
    p.setColor(QPalette.Highlight, HIGHLIGHT)
    p.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    p.setColor(QPalette.Disabled, QPalette.Text, DIM_TXT)
    p.setColor(QPalette.Disabled, QPalette.ButtonText, DIM_TXT)
    p.setColor(QPalette.ToolTipBase, MID_DARK)
    p.setColor(QPalette.ToolTipText, LIGHT_TXT)
    p.setColor(QPalette.PlaceholderText, DIM_TXT)
    p.setColor(QPalette.Link, QColor(0, 120, 212))

    app.setPalette(p)

    app.setStyleSheet("""
        QGroupBox {
            border: 1px solid #3d3d3d;
            border-radius: 4px;
            margin-top: 12px;
            padding: 16px 8px 8px 8px;
            font-weight: bold;
            font-size: 12px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 6px;
            color: #0078d4;
        }
        QPushButton {
            padding: 5px 14px;
            border-radius: 3px;
            border: 1px solid #3d3d3d;
            min-height: 24px;
        }
        QPushButton:hover {
            background-color: #0078d4;
            border-color: #0078d4;
        }
        QPushButton:pressed {
            background-color: #005a9e;
        }
        QPushButton#copyButton {
            background-color: #0078d4;
            color: white;
            font-weight: bold;
            font-size: 13px;
            padding: 10px 28px;
            border: none;
            border-radius: 4px;
        }
        QPushButton#copyButton:hover {
            background-color: #1a8ae8;
        }
        QPushButton#addFilterBtn {
            background-color: #0e639c;
            color: white;
            font-weight: bold;
            border: none;
        }
        QPushButton#addFilterBtn:hover {
            background-color: #1177bb;
        }
        QPushButton#clearButton {
            background-color: #3d3d3d;
            color: #cccccc;
            font-weight: bold;
            font-size: 13px;
            padding: 10px 28px;
            border: 1px solid #555555;
            border-radius: 4px;
        }
        QPushButton#clearButton:hover {
            background-color: #555555;
            border-color: #0078d4;
        }
        QPushButton#removeFilterBtn {
            background-color: #5a1d1d;
            color: #f48771;
            font-weight: bold;
            border: none;
            padding: 5px 10px;
        }
        QPushButton#removeFilterBtn:hover {
            background-color: #8b2020;
        }
        QPlainTextEdit#queryPreview {
            font-family: Consolas, 'Courier New', monospace;
            font-size: 13px;
            border: 1px solid #0078d4;
            border-radius: 4px;
            padding: 10px;
            background-color: #1e1e1e;
        }
        QComboBox {
            padding: 4px 8px;
            border: 1px solid #3d3d3d;
            border-radius: 3px;
            min-height: 22px;
        }
        QComboBox:hover {
            border-color: #0078d4;
        }
        QComboBox QAbstractItemView {
            background-color: #2d2d2d;
            border: 1px solid #3d3d3d;
            selection-background-color: #0078d4;
        }
        QLineEdit {
            padding: 4px 8px;
            border: 1px solid #3d3d3d;
            border-radius: 3px;
            min-height: 22px;
        }
        QLineEdit:focus {
            border-color: #0078d4;
        }
        QSpinBox {
            padding: 4px 8px;
            border: 1px solid #3d3d3d;
            border-radius: 3px;
            min-height: 22px;
        }
        QListWidget {
            border: 1px solid #3d3d3d;
            border-radius: 3px;
            outline: none;
        }
        QListWidget::item {
            padding: 6px 10px;
            margin: 1px 0;
        }
        QListWidget::item:selected {
            background-color: #0078d4;
        }
        QListWidget#projectList::item {
            padding: 3px 8px;
        }
        QSplitter::handle {
            background-color: #3d3d3d;
            width: 2px;
        }
        QScrollArea {
            border: none;
        }
        QCheckBox::indicator {
            width: 16px;
            height: 16px;
        }
    """)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("KustoForge - KQL Query Builder")
        self.setMinimumSize(1100, 700)
        self.resize(1300, 800)

        self.builder = QueryBuilderWidget(self)
        self.setCentralWidget(self.builder)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

        self.builder.status_message.connect(self._show_status)

    def _show_status(self, msg):
        self.status_bar.showMessage(msg, 3000)


def main():
    app = QApplication(sys.argv)
    apply_dark_theme(app)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
