"""Помощники для UI-тестов: поиск виджетов, «клики», выбор строк таблицы."""
from parcelflow.ui import FlatButton

from . import fake_tk
from .fake_tk import walk


def find_buttons(root, text=None):
    return [w for w in walk(root) if isinstance(w, FlatButton)
            and (text is None or w.options.get("text") == text)]


def find_trees(root):
    return [w for w in walk(root) if isinstance(w, fake_tk.Treeview)]


def find_entries(root):
    return [w for w in walk(root) if isinstance(w, fake_tk.Entry)]


def find_combos(root):
    return [w for w in walk(root) if isinstance(w, fake_tk.Combobox)]


def find_labels(root, text=None):
    return [w for w in walk(root) if isinstance(w, fake_tk.Label) and not isinstance(w, FlatButton)
            and (text is None or w.options.get("text") == text)]


def label_texts(root):
    return [str(w.options.get("text")) for w in find_labels(root)]


def click(widget):
    widget.bindings["<Button-1>"](None)


def answer(**values):
    """Обработчик модального окна: «пользователь» вводит значения и жмёт OK."""
    def handler(dlg):
        for key, value in values.items():
            dlg.vars[key].set(value)
        dlg._ok()
    return handler


def cancel(dlg):
    """Обработчик модального окна: «пользователь» жмёт «Отмена»."""
    click(find_buttons(dlg, "Отмена")[0])
