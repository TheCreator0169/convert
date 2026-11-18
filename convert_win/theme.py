"""Colours and the one stylesheet. No colour literal anywhere else."""
PALETTE = {"bg": "#1b1d22", "panel": "#252830", "border": "#343844", "text": "#e8eaf0", "muted": "#9aa1b2",
           "accent": "#4c8dff", "accent_text": "#ffffff", "error": "#ff6b6b", "ok": "#4cd08a"}


def stylesheet(p=PALETTE):
    return f"""
    QWidget {{ background: {p['bg']}; color: {p['text']}; font-family: 'Segoe UI'; font-size: 13px; }}
    QListWidget, QComboBox, QSpinBox, QGroupBox {{ background: {p['panel']}; border: 1px solid {p['border']};
        border-radius: 6px; padding: 4px; }}
    QGroupBox {{ margin-top: 10px; padding-top: 12px; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 10px; color: {p['muted']}; }}
    QPushButton {{ background: {p['panel']}; border: 1px solid {p['border']}; border-radius: 6px; padding: 7px 16px; }}
    QPushButton:disabled {{ color: {p['muted']}; }}
    QPushButton#primary {{ background: {p['accent']}; color: {p['accent_text']}; border: none; font-weight: 600; }}
    QPushButton#primary:disabled {{ background: {p['border']}; color: {p['muted']}; }}
    QProgressBar {{ background: {p['panel']}; border: none; border-radius: 4px; height: 8px; text-align: center; }}
    QProgressBar::chunk {{ background: {p['accent']}; border-radius: 4px; }}
    QLabel#muted {{ color: {p['muted']}; }}
    QLabel#error {{ color: {p['error']}; }}
    QLabel#ok {{ color: {p['ok']}; }}
    """
