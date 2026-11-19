"""Лёгкая подмена tkinter для тестов: окна не создаются, дисплей не нужен.

Виджеты запоминают родителя, детей, параметры и обработчики событий, поэтому
тест может «нажать» кнопку, выбрать строку таблицы или ввести текст в поле.
"""
import sys
import types


class _State:
    """Общее состояние: что показали messagebox/filedialog и как «отвечает» пользователь."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.errors = []            # тексты messagebox.showerror
        self.infos = []             # тексты messagebox.showinfo
        self.yesno = True           # ответ messagebox.askyesno
        self.save_path = ""         # ответ filedialog.asksaveasfilename
        self.dialog_handler = None  # функция(dlg): «пользователь» заполняет модальное окно
        self.mainloop_called = False


state = _State()


class Widget:
    def __init__(self, master=None, **kw):
        self.master = master
        self.options = dict(kw)
        self.bindings = {}
        self._children = []
        self.destroyed = False
        self._title = ""
        if master is not None and "_children" in master.__dict__:
            master._children.append(self)

    # --- геометрия и прочее: ничего не делаем ---
    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *a, **k: None

    def configure(self, **kw):
        self.options.update(kw)

    config = configure

    def bind(self, sequence, func):
        self.bindings[sequence] = func

    def winfo_children(self):
        return list(self._children)

    def destroy(self):
        for child in list(self._children):
            child.destroy()
        self.destroyed = True
        if self.master is not None and self in self.master._children:
            self.master._children.remove(self)

    def title(self, text=None):
        if text is not None:
            self._title = text
        return self._title


class Label(Widget):
    pass


class Frame(Widget):
    pass


class Entry(Widget):
    pass


class Toplevel(Widget):
    pass


class Combobox(Widget):
    pass


class Scrollbar(Widget):
    pass


class Canvas(Widget):
    def __init__(self, master=None, **kw):
        super().__init__(master, **kw)
        self.rects, self.texts = [], []

    def winfo_width(self):
        return 600

    def winfo_height(self):
        return 260

    def delete(self, *args):
        self.rects.clear()
        self.texts.clear()

    def create_rectangle(self, *args, **kw):
        self.rects.append((args, kw))

    def create_text(self, *args, **kw):
        self.texts.append((args, kw))


class Treeview(Widget):
    def __init__(self, master=None, **kw):
        super().__init__(master, **kw)
        self.items = {}
        self._selection = ()

    def insert(self, parent, index, iid=None, **kw):
        if iid is None:
            iid = str(len(self.items) + 1)
        if iid in self.items:  # настоящий Treeview тоже ругается на дубликаты
            raise ValueError(f"Item {iid} already exists")
        self.items[iid] = kw
        return iid

    def delete(self, *iids):
        for iid in iids:
            self.items.pop(iid, None)
        self._selection = tuple(s for s in self._selection if s in self.items)

    def get_children(self, item=""):
        return tuple(self.items)

    def selection(self):
        return self._selection

    def selection_set(self, iid):
        self._selection = (iid,)

    def values(self, iid):
        return tuple(self.items[iid].get("values", ()))


class Tk(Widget):
    def __init__(self):
        super().__init__(None)

    def wait_window(self, window):
        if state.dialog_handler:
            state.dialog_handler(window)

    def mainloop(self):
        state.mainloop_called = True


class StringVar:
    def __init__(self, master=None, value="", name=None):
        self._value = value
        self._callbacks = []

    def get(self):
        return self._value

    def set(self, value):
        self._value = value
        for callback in list(self._callbacks):
            callback("", "", "write")

    def trace_add(self, mode, callback):
        self._callbacks.append(callback)
        return "trace"


class Style:
    def __init__(self, master=None):
        self.calls = []

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *a, **k: self.calls.append((name, a, k))


def _showerror(title, message, **kw):
    state.errors.append(message)


def _showinfo(title, message, **kw):
    state.infos.append(message)


def _askyesno(title, message, **kw):
    return state.yesno


def _asksaveasfilename(**kw):
    return state.save_path


def install():
    """Подменяет tkinter в sys.modules (до импорта parcelflow.ui)."""
    module = types.ModuleType("tkinter")
    module.Tk, module.Label, module.Frame = Tk, Label, Frame
    module.Entry, module.Toplevel, module.Canvas = Entry, Toplevel, Canvas
    module.StringVar = StringVar
    module.ttk = types.SimpleNamespace(Style=Style, Combobox=Combobox,
                                       Treeview=Treeview, Scrollbar=Scrollbar)
    module.messagebox = types.SimpleNamespace(showerror=_showerror, showinfo=_showinfo,
                                              askyesno=_askyesno)
    module.filedialog = types.SimpleNamespace(asksaveasfilename=_asksaveasfilename)
    sys.modules["tkinter"] = module
    sys.modules["tkinter.ttk"] = module.ttk
    sys.modules["tkinter.messagebox"] = module.messagebox
    sys.modules["tkinter.filedialog"] = module.filedialog
    return module


def walk(widget):
    """Все потомки виджета (в глубину)."""
    for child in widget._children:
        yield child
        yield from walk(child)
