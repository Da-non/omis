"""Тесты ParcelFlow. Подмена tkinter ставится до импорта parcelflow.ui —
поэтому тесты работают без дисплея (в том числе в CI)."""
from . import fake_tk

fake_tk.install()
