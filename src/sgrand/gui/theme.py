"""Original visual theme and packaged icon helpers for the desktop app."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QIcon, QPalette

ASSET_DIRECTORY = Path(__file__).with_name("assets")


def icon(name: str) -> QIcon:
    """Return an original SVG icon bundled with SGRand."""
    return QIcon(str(ASSET_DIRECTORY / f"{name}.svg"))


def dark_palette() -> QPalette:
    """Provide dark defaults for native Qt surfaces not fully controlled by QSS."""
    palette = QPalette()
    colors = {
        QPalette.ColorRole.Window: "#0d1420",
        QPalette.ColorRole.WindowText: "#e8edf5",
        QPalette.ColorRole.Base: "#101a28",
        QPalette.ColorRole.AlternateBase: "#162132",
        QPalette.ColorRole.ToolTipBase: "#172235",
        QPalette.ColorRole.ToolTipText: "#ffffff",
        QPalette.ColorRole.Text: "#e8edf5",
        QPalette.ColorRole.Button: "#1b283b",
        QPalette.ColorRole.ButtonText: "#e8edf5",
        QPalette.ColorRole.BrightText: "#ffffff",
        QPalette.ColorRole.Link: "#f2c94c",
        QPalette.ColorRole.Highlight: "#d9485f",
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.PlaceholderText: "#718096",
    }
    for role, color in colors.items():
        palette.setColor(role, QColor(color))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#718096"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#718096"))
    return palette


APP_STYLESHEET = """
QMainWindow, QWizard, QDialog {
    background: #0d1420;
}
QWizardPage {
    background: #111b2a;
}
QWidget {
    color: #e8edf5;
    font-size: 10pt;
}
QLabel#heroTitle {
    color: #ffffff;
    font-size: 20pt;
    font-weight: 800;
}
QLabel#heroSubtitle {
    color: #9eacc0;
    font-size: 10pt;
}
QLabel[role="description"] {
    color: #aeb9ca;
    padding: 2px 0 8px 0;
}
QGroupBox {
    background: #162132;
    border: 1px solid #2b3b52;
    border-radius: 10px;
    font-weight: 700;
    margin-top: 14px;
    padding: 14px 10px 10px 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 13px;
    padding: 0 6px;
    color: #f3f6fa;
}
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTableWidget {
    color: #eef2f8;
    background: #101a28;
    border: 1px solid #394b65;
    border-radius: 6px;
    padding: 5px 7px;
    selection-background-color: #d9485f;
    selection-color: #ffffff;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus,
QTableWidget:focus {
    border: 2px solid #d9485f;
}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled,
QPlainTextEdit:disabled, QTableWidget:disabled {
    color: #718096;
    background: #1b2636;
    border-color: #2a384d;
}
QComboBox::drop-down {
    border: 0;
    width: 24px;
}
QComboBox QAbstractItemView {
    color: #eef2f8;
    background: #162132;
    border: 1px solid #394b65;
    selection-color: #ffffff;
    selection-background-color: #d9485f;
    outline: 0;
}
QCheckBox {
    spacing: 7px;
}
QCheckBox::indicator, QGroupBox::indicator {
    width: 17px;
    height: 17px;
}
QCheckBox::indicator:unchecked, QGroupBox::indicator:unchecked {
    background: #101a28;
    border: 1px solid #60728b;
    border-radius: 4px;
}
QCheckBox::indicator:checked, QGroupBox::indicator:checked {
    background: #d9485f;
    border: 1px solid #bc344c;
    border-radius: 4px;
    image: url("__CHECK_ICON__");
}
QPushButton {
    color: #e8edf5;
    background: #1b283b;
    border: 1px solid #3a4b64;
    border-radius: 7px;
    min-height: 30px;
    padding: 3px 12px;
    font-weight: 600;
}
QPushButton:hover {
    color: #ffffff;
    background: #2b3542;
    border-color: #f2c94c;
}
QPushButton:pressed {
    background: #3a3c36;
}
QPushButton:disabled {
    color: #68778c;
    background: #182231;
    border-color: #26354a;
}
QPushButton[kind="primary"] {
    color: #ffffff;
    background: #d9485f;
    border-color: #bd344b;
    font-weight: 800;
}
QPushButton[kind="primary"]:hover {
    background: #e6536a;
}
QPushButton[kind="gold"] {
    color: #111927;
    background: #f2c94c;
    border-color: #d7ad2f;
    font-weight: 800;
}
QPushButton[kind="gold"]:hover {
    color: #111927;
    background: #ffda62;
}
QTabWidget::pane {
    background: #111b2a;
    border: 1px solid #2b3b52;
    border-radius: 8px;
    top: -1px;
}
QTabBar::tab {
    background: #172335;
    color: #aab6c8;
    border: 1px solid #2b3b52;
    border-bottom: 0;
    border-top-left-radius: 7px;
    border-top-right-radius: 7px;
    padding: 8px 12px;
    margin-right: 2px;
    font-weight: 600;
}
QTabBar::tab:hover {
    color: #f2c94c;
    background: #222f43;
}
QTabBar::tab:selected {
    color: #ffffff;
    background: #202d41;
    border-top: 3px solid #d9485f;
    padding-top: 6px;
}
QHeaderView::section {
    color: #dce4ef;
    background: #202d40;
    border: 0;
    border-right: 1px solid #34445c;
    border-bottom: 1px solid #34445c;
    padding: 6px;
    font-weight: 700;
}
QProgressBar {
    background: #1b2738;
    border: 0;
    border-radius: 7px;
    min-height: 14px;
    text-align: center;
    color: #e8edf5;
    font-weight: 700;
}
QProgressBar::chunk {
    background: #f2c94c;
    border-radius: 7px;
}
QStatusBar {
    color: #9eacc0;
    background: #101925;
}
QToolTip {
    color: #ffffff;
    background: #172235;
    border: 1px solid #f2c94c;
    border-radius: 5px;
    padding: 7px;
}
QMenuBar, QMenu {
    color: #e8edf5;
    background: #111b2a;
}
QMenuBar::item:selected, QMenu::item:selected {
    background: #26344a;
    color: #f2c94c;
}
QScrollArea {
    background: transparent;
}
QScrollArea > QWidget > QWidget {
    background: transparent;
}
QScrollBar:vertical {
    background: #111b2a;
    width: 12px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #465871;
    min-height: 28px;
    border-radius: 6px;
}
QScrollBar::handle:vertical:hover {
    background: #60738f;
}
QScrollBar:horizontal {
    background: #111b2a;
    height: 12px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #465871;
    min-width: 28px;
    border-radius: 6px;
}
QScrollBar::handle:horizontal:hover {
    background: #60738f;
}
QScrollBar::add-line, QScrollBar::sub-line,
QScrollBar::add-page, QScrollBar::sub-page {
    background: transparent;
    border: 0;
}
"""

APP_STYLESHEET = APP_STYLESHEET.replace(
    "__CHECK_ICON__", (ASSET_DIRECTORY / "check.svg").as_posix()
)
