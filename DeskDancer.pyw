"""DeskDancer.pyw  v1.3.0 — запуск двойным кликом (без консоли).

3D-девушки танцуют на рабочем столе под музыку, в такт.
Библиотеки (PySide6, numpy, soundcard) ставятся сами при первом запуске.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from deskdancer import main  # noqa: E402

if __name__ == "__main__":
    main()
