"""Colours and the one stylesheet. No colour literal anywhere else."""
PALETTE = {"bg": "#1b1d22", "panel": "#252830", "border": "#343844", "text": "#e8eaf0", "muted": "#9aa1b2",
           "tile": "#2f3340", "accent": "#4c8dff", "accent_text": "#ffffff", "error": "#ff6b6b", "ok": "#4cd08a"}


def stylesheet(p=PALETTE, chevron="", chevron_up=""):
    """`chevron`, `chevron_up`: paths (forward slashes) of the select and spin-box arrow images; empty keeps Qt's own arrows."""
    arrow = f"image: url({chevron}); width: 10px; height: 10px;" if chevron else ""
    arrow_up = f"image: url({chevron_up}); width: 10px; height: 10px;" if chevron_up else ""
    return f"""
    QWidget {{ background: {p['bg']}; color: {p['text']}; font-family: 'Segoe UI'; font-size: 13px; }}
    QListWidget, QComboBox, QSpinBox, QGroupBox {{ background: {p['panel']}; border: 1px solid {p['border']};
        border-radius: 6px; padding: 4px; }}
    QListWidget#drop {{ border: 1px dashed {p['border']}; }}
    QListWidget#drop[drag="true"] {{ border: 2px dashed {p['accent']}; }}
    QListWidget#drop QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
    QListWidget#drop QScrollBar::handle:vertical {{ background: {p['border']}; border-radius: 4px; min-height: 24px; }}
    QListWidget#drop QScrollBar::add-line:vertical, QListWidget#drop QScrollBar::sub-line:vertical {{ height: 0; }}
    QListWidget#drop QScrollBar::add-page:vertical, QListWidget#drop QScrollBar::sub-page:vertical {{ background: transparent; }}
    QLabel#update {{ color: {p['accent']}; font-size: 13px; }}
    QLabel#version {{ color: {p['muted']}; font-size: 12px; }}
    QLabel#hint {{ background: transparent; color: {p['muted']}; }}
    QComboBox, QSpinBox {{ border-radius: 8px; padding: 0 12px; min-height: 34px; }}
    QComboBox:hover, QComboBox:on, QSpinBox:hover, QSpinBox:focus {{ border-color: {p['accent']}; }}
    QComboBox[empty="true"] {{ color: {p['muted']}; }}
    QComboBox::drop-down {{ border: none; width: 28px; subcontrol-origin: padding; subcontrol-position: center right; }}
    QComboBox::down-arrow {{ {arrow} }}
    QComboBox QAbstractItemView {{ background: {p['panel']}; border: 1px solid {p['border']}; border-radius: 8px;
        outline: 0; padding: 2px; selection-background-color: {p['accent']}; selection-color: {p['accent_text']}; }}
    QComboBox QAbstractItemView::item {{ min-height: 32px; padding-left: 8px; }}
    QSpinBox::up-button, QSpinBox::down-button {{ background: transparent; border: none; width: 22px; }}
    QSpinBox::up-arrow {{ {arrow_up} }}
    QSpinBox::down-arrow {{ {arrow} }}
    QGroupBox QComboBox, QGroupBox QSpinBox {{ background: {p['bg']}; }}
    QGroupBox QLabel, QGroupBox QCheckBox {{ background: transparent; }}
    QGroupBox {{ margin-top: 10px; padding-top: 12px; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 10px; color: {p['muted']}; }}
    QPushButton {{ background: {p['panel']}; border: 1px solid {p['border']}; border-radius: 6px; padding: 7px 16px; }}
    QPushButton:disabled {{ color: {p['muted']}; }}
    QPushButton#primary {{ background: {p['accent']}; color: {p['accent_text']}; border: none; font-weight: 600; }}
    QPushButton#primary:disabled {{ background: {p['border']}; color: {p['muted']}; }}
    QMenu {{ background: {p['panel']}; border: 1px solid {p['border']}; border-radius: 6px; padding: 4px; color: {p['text']}; }}
    QMenu::item {{ background: transparent; padding: 7px 16px; }}
    QMenu::item:selected {{ background: {p['border']}; }}
    QMenu::item:disabled {{ color: {p['muted']}; }}
    QProgressBar {{ background: {p['panel']}; border: none; border-radius: 4px; height: 8px; text-align: center; }}
    QProgressBar::chunk {{ background: {p['accent']}; border-radius: 4px; }}
    QLabel#muted {{ color: {p['muted']}; }}
    QLabel#error {{ color: {p['error']}; }}
    QLabel#ok {{ color: {p['ok']}; }}
    """
