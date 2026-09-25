import os

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from figureforge.__init__ import ASSETS_DIR, __version__


class WelcomeDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Welcome to figureforge {__version__}")
        self.setWindowIcon(QIcon(os.path.join(ASSETS_DIR, "logo.ico")))
        layout = QVBoxLayout()

        logo = QLabel()
        logo.setPixmap(QPixmap(os.path.join(ASSETS_DIR, "logo_color_text.png")))
        logo.setScaledContents(True)
        logo.setFixedSize(QSize(100, 100))

        layout.addWidget(logo, alignment=Qt.AlignCenter)

        description = QLabel("figureforge is a GUI tool for creating and editing matplotlib figures.")
        layout.addWidget(description, alignment=Qt.AlignLeft)

        documentation_link = QLabel(
            'For more information, please visit the <a href="https://github.com/nogula/figureforge/wiki">documentation</a>.'
        )
        documentation_link.setOpenExternalLinks(True)
        layout.addWidget(documentation_link, alignment=Qt.AlignLeft)
        layout.addSpacing(10)
        self.display_at_startup = QCheckBox("Display this dialog at startup")
        self.display_at_startup.setChecked(True)
        layout.addWidget(self.display_at_startup)
        self.check_for_updates = QCheckBox("Check for updates at startup")
        self.check_for_updates.setChecked(True)
        layout.addWidget(self.check_for_updates)

        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        bottom_row.addWidget(close_button)

        layout.addLayout(bottom_row)

        self.setLayout(layout)
        self.exec()
