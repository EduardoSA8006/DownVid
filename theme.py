from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

DARK_QSS = """
QWidget {
    background-color: #15171a;
    color: #e2e2e2;
    font-size: 14px;
}

QMenuBar, QMenu {
    background-color: #1b1f24;
    color: #e2e2e2;
}
QMenu::item:selected {
    background: #2a3138;
}

QToolTip {
    background-color: #2a3138;
    color: #e2e2e2;
    border: 1px solid #3a424a;
}

QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: #1b1f24;
    color: #e2e2e2;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 6px;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #58a6ff;
}

QPushButton {
    background-color: #238636;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 8px 12px;
}
QPushButton:hover {
    background-color: #2ea043;
}
QPushButton:disabled {
    background-color: #2a3138;
    color: #888;
}

QTableWidget, QTreeWidget, QListWidget {
    background-color: #0d1117;
    alternate-background-color: #0f141a;
    gridline-color: #30363d;
    border: 1px solid #30363d;
    border-radius: 8px;
}
QHeaderView::section {
    background-color: #161b22;
    color: #e2e2e2;
    padding: 6px;
    border: 1px solid #30363d;
}
QTableWidget::item:selected, QTreeWidget::item:selected, QListWidget::item:selected {
    background-color: #1f6feb;
}

QProgressBar {
    background-color: #1b1f24;
    border: 1px solid #30363d;
    border-radius: 6px;
    text-align: center;
    color: #e2e2e2;
}
QProgressBar::chunk {
    background-color: #2ea043;
    border-radius: 6px;
}

QTabBar::tab {
    background: #161b22;
    color: #e2e2e2;
    padding: 8px 12px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}
QTabBar::tab:selected {
    background: #1f2937;
}
"""

def apply_dark_theme(app: QApplication):
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#15171a"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#e2e2e2"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#0d1117"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#0f141a"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#2a3138"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#e2e2e2"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#e2e2e2"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#1b1f24"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#e2e2e2"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#ff6666"))
    palette.setColor(QPalette.ColorRole.Link, QColor("#58a6ff"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#1f6feb"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)
    app.setStyleSheet(DARK_QSS)