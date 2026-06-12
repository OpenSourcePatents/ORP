# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The ORP application icon: a programmatic QPainter lettermark, no binary assets.

A rounded square in the palette's VERIFIED_SOURCE blue carrying the white letters
"ORP", rendered at several pixel sizes so the icon stays legible from a 16 px
taskbar entry up to a 256 px about box, and readable on both light and dark chrome
(solid mid-blue with white text works on either).
"""

from __future__ import annotations

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap

from orp.gui.app_state import LEVEL_COLOR_HEX

__all__ = ["orp_icon", "ICON_SIZES"]

#: Rendered pixel sizes (16/32 for window chrome and taskbar, up the scale to 256).
ICON_SIZES: tuple[int, ...] = (16, 32, 64, 128, 256)

#: Background: the palette's VERIFIED_SOURCE blue — consistent with the existing
#: five-color provenance code and acceptable on light and dark themes alike.
_BACKGROUND = LEVEL_COLOR_HEX["VERIFIED_SOURCE"]


def _render(size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        radius = max(2, round(size * 0.22))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(_BACKGROUND))
        painter.drawRoundedRect(0, 0, size, size, radius, radius)

        font = QFont()
        font.setBold(True)
        # Three capitals across the square: ~42% of the height keeps "ORP" inside
        # the rounded bounds and still legible at 16 px (pixel-size floor of 6).
        font.setPixelSize(max(6, round(size * 0.42)))
        painter.setFont(font)
        painter.setPen(QColor("white"))
        painter.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, "ORP")
    finally:
        painter.end()
    return pixmap


def orp_icon() -> QIcon:
    """The application QIcon with pixmaps rendered at every size in ICON_SIZES.

    Requires a QGuiApplication to exist (QPixmap rendering needs one); both launch
    paths create the application object before calling this.
    """
    icon = QIcon()
    for size in ICON_SIZES:
        icon.addPixmap(_render(size))
    return icon
