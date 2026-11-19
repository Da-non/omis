"""<<UI>> LogisticsUI — пользовательский интерфейс системы ParcelFlow (Tkinter).

Экраны и переходы соответствуют макетам (ЛР5) и диаграмме состояний:
Вход в систему -> (выбор интерфейса по роли) -> экраны роли -> logout() -> Вход в систему."""
from __future__ import annotations

import csv
import re
import tkinter as tk
from datetime import date, datetime, timedelta
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Dict, List, Optional

from .entities import (ROLE_ADMIN, ROLE_CLIENT, ROLE_COURIER, ROLE_OPERATOR, STATUS_FLOW,
                       USER_CLASSES, Parcel, ParcelStatus as S, User)
from .services import (FINAL_STATUSES, NotificationService, ParcelService,
                       TrackingService, UserService)

BG, NAVY, BLUE, WHITE = "#eaf0fb", "#172a52", "#3b7bf5", "#ffffff"
MUTED, BORDER = "#6b7a99", "#d5deef"
GREEN, ORANGE, RED = "#1f8a3b", "#c2570c", "#c62828"
STATUS_COLORS = {S.REGISTERED: "#d7e5fd", S.ACCEPTED: "#d7e5fd", S.SENT: "#fdf0c8",
                 S.IN_TRANSIT: "#fdf0c8", S.ARRIVED: "#d6f5dd", S.DELIVERED: "#d6f5dd",
                 S.DELAYED: "#fbd9d9", S.NOT_DELIVERED: "#fbd9d9"}
MONTHS = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]
FONT = ("Arial", 10)
FONT_B = ("Arial", 10, "bold")

# Меню по ролям: (основные пункты, нижний пункт). Имена методов = переходы диаграммы состояний.
NAV = {
    ROLE_ADMIN: ([("Главная", "openMain"), ("Посылки", "openParcels"), ("Отчёты", "openReports")],
                 ("Настройки", "openSettings")),
    ROLE_OPERATOR: ([("Главная", "openMain"), ("Посылки", "openParcels"),
                     ("Отслеживание", "openTracking"), ("Курьеры", "openCouriers"),
                     ("Отчёты", "openReports")], ("Настройки", "openSettings")),
    ROLE_COURIER: ([("Мои посылки", "openMyParcels"), ("История доставок", "openDeliveryHistory")],
                   ("Выйти", "logout")),
    ROLE_CLIENT: ([("Мои посылки", "openMyParcels"), ("Отслеживание", "openTracking"),
                   ("Уведомления", "openNotifications")], ("Выйти", "logout")),
}
INITIAL_STATE = {ROLE_ADMIN: "openSettings", ROLE_OPERATOR: "openMain",
                 ROLE_COURIER: "openMyParcels", ROLE_CLIENT: "openMyParcels"}


class FlatButton(tk.Label):
    """Кнопка-метка (одинаково выглядит на всех ОС)."""

    def __init__(self, parent, text, command, bg=BLUE, fg=WHITE, padx=14, pady=7, **kw):
        super().__init__(parent, text=text, bg=bg, fg=fg, cursor="hand2", padx=padx, pady=pady,
                         font=FONT_B, **kw)
        self.command = command
        self.bind("<Button-1>", lambda e: self.command())


class FormDialog(tk.Toplevel):
    """Модальная форма ввода. fields: dict(key,label,type=entry|password|combo,values,default)."""

    def __init__(self, parent, title, fields, submitText="Сохранить"):
        super().__init__(parent)
        self.title(title)
        self.configure(bg=WHITE, padx=20, pady=16)
        self.resizable(False, False)
        self.result: Optional[dict] = None
        self.vars: Dict[str, tk.StringVar] = {}
        for f in fields:
            tk.Label(self, text=f["label"], bg=WHITE, fg=MUTED, font=("Arial", 9)).pack(anchor="w")
            var = tk.StringVar(value=f.get("default", ""))
            self.vars[f["key"]] = var
            if f.get("type") == "combo":
                w = ttk.Combobox(self, textvariable=var, values=f["values"], state="readonly", width=34)
            else:
                w = tk.Entry(self, textvariable=var, width=36, show="*" if f.get("type") == "password" else "",
                             relief="flat", highlightthickness=1, highlightbackground=BORDER,
                             highlightcolor=BLUE)
            w.pack(fill="x", pady=(0, 8), ipady=3)
        row = tk.Frame(self, bg=WHITE)
        row.pack(fill="x", pady=(6, 0))
        FlatButton(row, submitText, self._ok).pack(side="right")
        FlatButton(row, "Отмена", self.destroy, bg=WHITE, fg=BLUE).pack(side="right", padx=6)
        self.transient(parent)
        self.grab_set()

    def _ok(self):
        self.result = {k: v.get() for k, v in self.vars.items()}
        self.destroy()


def parseDate(text: str) -> date:
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            pass
    raise ValueError("Дата должна быть в формате ГГГГ-ММ-ДД (или ДД.ММ.ГГГГ)")


class LogisticsUI:
    """Пользовательский интерфейс. Методы из диаграммы классов: registerParcel, trackParcel,
    changeParcelStatus, showParcelInfo, showError."""

    def __init__(self, root: tk.Tk, parcelService: ParcelService, trackingService: TrackingService,
                 userService: UserService, notificationService: NotificationService):
        self.root = root
        self.parcelService = parcelService      # ассоциации «parcelService»,
        self.trackingService = trackingService  # «trackingService»,
        self.userService = userService          # «userService»
        self.notificationService = notificationService
        self.currentUser: Optional[User] = None
        self.currentState = "login"
        self.extensions: Dict[str, dict] = {}   # подключаемые модули (карта, аналитика, мобильное)
        self.navButtons: Dict[str, FlatButton] = {}
        root.title("ParcelFlow — система автоматизации учёта и отслеживания посылок")
        root.geometry("1180x720")
        root.minsize(1000, 640)
        root.configure(bg=BG)
        self._setupStyles()
        self.showLogin()

    def run(self) -> None:
        self.root.mainloop()

    def registerExtension(self, title: str, roles: List[str], launcher: Callable, perParcel: bool = False):
        """launcher(user, parcelNumber|None) — открывает окно подключаемого модуля."""
        self.extensions[title] = {"roles": roles, "launcher": launcher, "perParcel": perParcel}

    # ------------------------------------------------------------------ стили и помощники
    def _setupStyles(self):
        st = ttk.Style(self.root)
        st.theme_use("clam")
        st.configure("Treeview", rowheight=28, font=FONT, background=WHITE, fieldbackground=WHITE,
                     bordercolor=BORDER, borderwidth=0)
        st.configure("Treeview.Heading", font=FONT_B, background="#edf2fb", foreground=MUTED,
                     relief="flat", padding=6)
        st.map("Treeview", background=[("selected", "#cfe0ff")], foreground=[("selected", NAVY)])

    def _clear(self, widget):
        for w in widget.winfo_children():
            w.destroy()

    def _card(self, parent, title=None, subtitle=None, expand=False, fill="x", pady=(0, 14)):
        outer = tk.Frame(parent, bg=WHITE, highlightthickness=1, highlightbackground=BORDER)
        outer.pack(fill=fill, expand=expand, pady=pady)
        inner = tk.Frame(outer, bg=WHITE, padx=16, pady=12)
        inner.pack(fill="both", expand=True)
        if title:
            tk.Label(inner, text=title, bg=WHITE, fg=NAVY, font=("Arial", 13, "bold")).pack(anchor="w")
        if subtitle:
            tk.Label(inner, text=subtitle, bg=WHITE, fg=MUTED, font=("Arial", 9)).pack(anchor="w", pady=(0, 8))
        return inner

    def _statCards(self, parent, items):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(0, 14))
        for i, (title, value, color) in enumerate(items):
            row.columnconfigure(i, weight=1, uniform="c")
            box = tk.Frame(row, bg=WHITE, highlightthickness=1, highlightbackground=BORDER, padx=16, pady=10)
            box.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 8, 0))
            tk.Label(box, text=title, bg=WHITE, fg=MUTED, font=("Arial", 9)).pack(anchor="w")
            tk.Label(box, text=str(value), bg=WHITE, fg=color, font=("Arial", 22, "bold")).pack(anchor="w")

    def _table(self, parent, columns, widths, height=10):
        frame = tk.Frame(parent, bg=WHITE)
        frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=height, selectmode="browse")
        for c, w in zip(columns, widths):
            tree.heading(c, text=c)
            tree.column(c, width=w, anchor="w")
        sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        for s, color in STATUS_COLORS.items():
            tree.tag_configure("st_" + s.name, background=color)
        return tree

    def _entry(self, parent, var, width=30, show=""):
        return tk.Entry(parent, textvariable=var, width=width, show=show, font=FONT, relief="flat",
                        highlightthickness=1, highlightbackground=BORDER, highlightcolor=BLUE)

    def _selected(self, tree) -> Optional[str]:
        sel = tree.selection()
        if not sel:
            self.showError("Выберите строку в таблице")
            return None
        return sel[0]

    def _can(self, operation: str) -> bool:
        return bool(self.currentUser and self.userService.checkAccess(self.currentUser.id, operation))

    @staticmethod
    def _fmt(dt) -> str:
        return dt.strftime("%d.%m.%Y, %H:%M") if isinstance(dt, datetime) else dt.strftime("%d.%m.%Y")

    @staticmethod
    def _city(parcel: Parcel) -> str:
        return parcel.route

    def showError(self, message: str) -> None:
        messagebox.showerror("Ошибка", message, parent=self.root)

    def showMessage(self, message: str) -> None:
        messagebox.showinfo("ParcelFlow", message, parent=self.root)

    # ------------------------------------------------------------------ вход в систему
    def showLogin(self) -> None:
        self.currentUser = None
        self.currentState = "login"
        self.navButtons = {}
        self._clear(self.root)
        self.root.columnconfigure(0, weight=1, uniform="half")
        self.root.columnconfigure(1, weight=1, uniform="half")
        self.root.rowconfigure(0, weight=1)
        left = tk.Frame(self.root, bg=NAVY)
        left.grid(row=0, column=0, sticky="nsew")
        tk.Label(left, text="ParcelFlow", bg=NAVY, fg=WHITE, font=("Arial", 30, "bold")).place(relx=0.12, rely=0.42)
        tk.Label(left, text="Система автоматизации учёта и\nотслеживания посылок в логистической\nкомпании",
                 bg=NAVY, fg="#b9c6e6", font=("Arial", 12), justify="left").place(relx=0.12, rely=0.52)
        right = tk.Frame(self.root, bg=BG)
        right.grid(row=0, column=1, sticky="nsew")
        card = tk.Frame(right, bg=WHITE, highlightthickness=1, highlightbackground=BORDER, padx=26, pady=22)
        card.place(relx=0.5, rely=0.5, anchor="center")
        tk.Label(card, text="Вход в систему", bg=WHITE, fg=NAVY, font=("Arial", 18, "bold")).pack(anchor="w")
        tk.Label(card, text="Введите данные учётной записи. Доступные функции\nзависят от вашей роли.",
                 bg=WHITE, fg=MUTED, justify="left", font=("Arial", 9)).pack(anchor="w", pady=(0, 12))
        self.loginVar, self.passVar = tk.StringVar(), tk.StringVar()
        tk.Label(card, text="Логин", bg=WHITE, fg=MUTED, font=("Arial", 9)).pack(anchor="w")
        e1 = self._entry(card, self.loginVar, 34)
        e1.pack(fill="x", ipady=5, pady=(0, 8))
        tk.Label(card, text="Пароль", bg=WHITE, fg=MUTED, font=("Arial", 9)).pack(anchor="w")
        e2 = self._entry(card, self.passVar, 34, show="*")
        e2.pack(fill="x", ipady=5, pady=(0, 6))
        forgot = tk.Label(card, text="Забыли пароль?", bg=WHITE, fg=BLUE, cursor="hand2", font=("Arial", 9))
        forgot.pack(anchor="w")
        forgot.bind("<Button-1>", lambda e: self.showMessage("Для восстановления пароля обратитесь к администратору системы."))
        FlatButton(card, "Войти", self.enterSystem, pady=9).pack(fill="x", pady=14)
        tk.Label(card, text="Нет доступа? Обратитесь к администратору системы", bg=WHITE, fg=MUTED,
                 font=("Arial", 9)).pack()
        tk.Label(card, text="Демо: admin/admin · operator1/operator1 · courier1/courier1 · client1/client1",
                 bg=WHITE, fg=MUTED, font=("Arial", 8)).pack(pady=(10, 0))
        e1.focus_set()
        for e in (e1, e2):
            e.bind("<Return>", lambda ev: self.enterSystem())

    def enterSystem(self) -> None:
        """Переход: Вход в систему -> [authenticate] -> интерфейс роли (псевдосостояние выбора)."""
        user = self.userService.authenticate(self.loginVar.get(), self.passVar.get())
        if user is None:
            self.showError("Неверные данные: проверьте логин и пароль (или учётная запись заблокирована).")
            self.passVar.set("")
            return
        self.currentUser = user
        self._buildShell()
        getattr(self, INITIAL_STATE[user.role])()

    def logout(self) -> None:
        self.showLogin()

    # ------------------------------------------------------------------ оболочка (меню + шапка)
    def _buildShell(self) -> None:
        self._clear(self.root)
        for c in (0, 1):
            self.root.columnconfigure(c, weight=0, uniform="")
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)
        user = self.currentUser
        side = tk.Frame(self.root, bg=NAVY, width=210)
        side.grid(row=0, column=0, sticky="ns")
        side.pack_propagate(False)
        tk.Label(side, text="ParcelFlow", bg=NAVY, fg=WHITE, font=("Arial", 16, "bold"), pady=22).pack(fill="x")
        main_items, bottom = NAV[user.role]
        self.navButtons = {}
        for title, method in main_items:
            btn = FlatButton(side, title, getattr(self, method), bg=NAVY, anchor="w", padx=18)
            btn.pack(fill="x", padx=10, pady=2)
            self.navButtons[method] = btn
        exts = [(t, e) for t, e in self.extensions.items() if user.role in e["roles"]]
        if exts:
            tk.Label(side, text="ДОПОЛНИТЕЛЬНО", bg=NAVY, fg="#7f8fb5", font=("Arial", 8, "bold"),
                     anchor="w", padx=20).pack(fill="x", pady=(22, 2))
            for title, ext in exts:
                FlatButton(side, title, lambda e=ext: e["launcher"](self.currentUser, None), bg=NAVY,
                           anchor="w", padx=18).pack(fill="x", padx=10, pady=2)
        btn = FlatButton(side, bottom[0], getattr(self, bottom[1]), bg=NAVY, anchor="w", padx=18)
        btn.pack(side="bottom", fill="x", padx=10, pady=14)
        self.navButtons[bottom[1]] = btn
        body = tk.Frame(self.root, bg=BG)
        body.grid(row=0, column=1, sticky="nsew")
        header = tk.Frame(body, bg=WHITE, height=56)
        header.pack(fill="x")
        header.pack_propagate(False)
        self.titleLabel = tk.Label(header, text="", bg=WHITE, fg=NAVY, font=("Arial", 16, "bold"), padx=20)
        self.titleLabel.pack(side="left")
        FlatButton(header, "Выйти", self.logout, bg=WHITE, fg=BLUE).pack(side="right", padx=10)
        tk.Label(header, text=f"{user.name} · {user.role}", bg=WHITE, fg=NAVY, font=FONT_B).pack(side="right", padx=6)
        self.content = tk.Frame(body, bg=BG, padx=22, pady=18)
        self.content.pack(fill="both", expand=True)

    def _open(self, title, state, builder, *args, highlight=None):
        self.currentState = state
        self._current = (title, state, builder, args, highlight)
        for key, btn in self.navButtons.items():
            active = key == (highlight or state)
            btn.config(bg=BLUE if active else NAVY)
        self.titleLabel.config(text=title)
        self._clear(self.content)
        builder(self.content, *args)

    def _refresh(self) -> None:
        title, state, builder, args, highlight = self._current
        self._open(title, state, builder, *args, highlight=highlight)

    # ------------------------------------------------------------------ переходы (диаграмма состояний)
    def openMain(self):
        self._open("Главная", "openMain", self._buildMain)

    def openParcels(self):
        self._open("Посылки", "openParcels", self._buildParcels)

    def openNewParcel(self):
        if not self._can("register_parcel"):
            self.showError("Недостаточно прав для регистрации посылок")
            return
        self._open("Новая посылка", "openNewParcel", self._buildNewParcel, highlight="openParcels")

    def openTracking(self, parcelNumber: str = ""):
        self._open("Отслеживание", "openTracking", self._buildTracking, parcelNumber)
        if parcelNumber:
            self.trackParcel(parcelNumber)

    def openCouriers(self):
        self._open("Курьеры", "openCouriers", self._buildCouriers)

    def openReports(self):
        self._open("Отчёты", "openReports", self._buildReports)

    def openSettings(self):
        if self.currentUser.role == ROLE_ADMIN:
            self._open("Настройки", "openSettings", self._buildSettingsAdmin)
        else:
            self._open("Настройки", "openSettings", self._buildProfile)

    def openMyParcels(self):
        builder = self._buildCourierParcels if self.currentUser.role == ROLE_COURIER else self._buildClientParcels
        self._open("Мои посылки", "openMyParcels", builder)

    def openDeliveryHistory(self):
        self._open("История доставок", "openDeliveryHistory", self._buildDeliveryHistory)

    def openNotifications(self):
        self._open("Уведомления", "openNotifications", self._buildNotifications)

    # ------------------------------------------------------------------ операции из диаграммы классов
    def registerParcel(self) -> None:
        """Регистрация новой посылки оператором (BPMN «Регистрация посылки»)."""
        v = {k: var.get().strip() for k, var in self.formVars.items()}
        phone = re.compile(r"^\+?[0-9\s\-()]{7,}$")
        try:
            for key, label in (("sender", "ФИО отправителя"), ("recipient", "ФИО получателя"),
                               ("address", "Адрес доставки")):
                if not v[key]:
                    raise ValueError(f"Поле «{label}» обязательно")
            for key, label in (("sender_phone", "Телефон отправителя"), ("recipient_phone", "Телефон получателя")):
                if not phone.match(v[key]):
                    raise ValueError(f"Некорректное значение: «{label}»")
            dep, est = parseDate(v["departure"]), parseDate(v["estimated"])
            city = self._cityFromAddress(v["address"])
            client = self.userService.findClientByName(v["recipient"])
            parcel = Parcel(sender=v["sender"], senderPhone=v["sender_phone"], recipient=v["recipient"],
                            recipientPhone=v["recipient_phone"], deliveryAddress=v["address"],
                            departureDate=dep, estimatedDeliveryDate=est, route=f"Минск-{city}",
                            clientId=client.id if client else 0, courierId=self._leastLoadedCourier())
            parcel = self.parcelService.registerParcel(parcel)
            self.trackingService.addTrackingRecord(parcel.number, S.REGISTERED, "Посылка зарегистрирована оператором")
        except ValueError as exc:
            self.showError(str(exc))
            return
        self.showMessage(f"Посылка создана. Номер: {parcel.number}\nСтатус: «{S.REGISTERED.value}»")
        self.openParcels()

    def trackParcel(self, parcelNumber: str) -> None:
        """Отслеживание (BPMN «Отслеживание посылки»): проверка наличия -> вывод информации."""
        if not self._can("track_parcel"):
            self.showError("Недостаточно прав для отслеживания посылок")
            return
        number = parcelNumber.strip().upper()
        if not number:
            self.showError("Введите номер отправления")
            return
        parcel = self.parcelService.findParcel(number)
        if parcel is None:
            self.showError(f"Посылка с номером {number} не найдена")
            return
        if self.currentState != "openTracking":
            self.openTracking(number)
            return
        self.showParcelInfo(parcel)

    def changeParcelStatus(self, parcelNumber: str, status: S, description: str = "") -> bool:
        """Изменение статуса (sequence-диаграмма): isStatusAllowed -> updateStatus ->
        addTrackingRecord (история) -> уведомление клиенту."""
        user = self.currentUser
        operation = "deliver_parcel" if status in FINAL_STATUSES else "change_status"
        if not self._can(operation):
            self.showError("Недостаточно прав для изменения статуса")
            return False
        parcel = self.parcelService.findParcel(parcelNumber)
        if parcel is None:
            self.showError("Посылка не найдена")
            return False
        if user.role == ROLE_COURIER and parcel.courierId != user.id:
            self.showError("Эта посылка не назначена вам")
            return False
        if not self.parcelService.isStatusAllowed(parcel.status, status):
            self.showError("Недопустимый статус")  # ветка [else] -> displayError("Invalid status")
            return False
        self.parcelService.updateParcelStatus(parcelNumber, status)
        self.trackingService.addTrackingRecord(parcelNumber, status, description or f"Статус изменён: {user.name}")
        self.showMessage(f"Статус посылки {parcelNumber} изменён: «{status.value}».\nКлиент получит уведомление.")
        return True

    def showParcelInfo(self, parcel: Parcel) -> None:
        """Карточка посылки + история перемещения (раздел «Отслеживание»)."""
        self._clear(self.trackResult)
        self.trackResult.columnconfigure((0, 1), weight=1, uniform="t")
        left = self._card(self.trackResult, "Информация о посылке", parcel.number, fill="both", pady=0)
        left.master.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        grid = tk.Frame(left, bg=WHITE)
        grid.pack(fill="x")
        fields = [("Отправитель", parcel.sender), ("Получатель", parcel.recipient),
                  ("Маршрут", parcel.route), ("Адрес доставки", parcel.deliveryAddress),
                  ("Дата отправления", self._fmt(parcel.departureDate)),
                  ("Ожидаемая доставка", self._fmt(parcel.estimatedDeliveryDate))]
        for i, (k, val) in enumerate(fields):
            cell = tk.Frame(grid, bg=WHITE)
            cell.grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 24), pady=6)
            tk.Label(cell, text=k, bg=WHITE, fg=MUTED, font=("Arial", 9)).pack(anchor="w")
            tk.Label(cell, text=val, bg=WHITE, fg=NAVY, font=FONT_B, wraplength=220, justify="left").pack(anchor="w")
        tk.Label(left, text=parcel.status.value, bg=STATUS_COLORS[parcel.status], fg=NAVY,
                 font=FONT_B, padx=10, pady=3).pack(anchor="w", pady=(10, 4))
        row = tk.Frame(left, bg=WHITE)
        row.pack(anchor="w", pady=(8, 0))
        for title, ext in self.extensions.items():
            if ext["perParcel"] and self.currentUser.role in ext["roles"]:
                FlatButton(row, title, lambda e=ext: e["launcher"](self.currentUser, parcel.number),
                           bg=WHITE, fg=BLUE).pack(side="left", padx=(0, 6))
        right = self._card(self.trackResult, "История перемещения", fill="both", pady=0)
        right.master.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        history = self.trackingService.getMovementHistory(parcel.number)
        for rec in history:
            self._timelineRow(right, rec.status.value, self._fmt(rec.timestamp), True)
        reached = [STATUS_FLOW.index(r.status) for r in history if r.status in STATUS_FLOW]
        last = max(reached) if reached else -1
        if parcel.status not in FINAL_STATUSES:
            for s in STATUS_FLOW[last + 1:]:
                self._timelineRow(right, s.value, "—", False)

    def _timelineRow(self, parent, title, when, done):
        row = tk.Frame(parent, bg=WHITE)
        row.pack(fill="x", pady=4)
        tk.Label(row, text="●", bg=WHITE, fg=BLUE if done else "#c4cde0", font=("Arial", 12)).pack(side="left")
        col = tk.Frame(row, bg=WHITE)
        col.pack(side="left", padx=8)
        tk.Label(col, text=title, bg=WHITE, fg=NAVY if done else MUTED, font=FONT_B if done else FONT).pack(anchor="w")
        tk.Label(col, text=when, bg=WHITE, fg=MUTED, font=("Arial", 8)).pack(anchor="w")

    # ------------------------------------------------------------------ экраны: оператор / администратор
    def _parcelValues(self, p: Parcel, full=False):
        base = (p.number, p.sender, p.recipient, p.route) if full else (p.number, p.recipient, p.route)
        return base + ((self._fmt(p.estimatedDeliveryDate),) if full else ()) + (p.status.value,)

    def _fillParcels(self, tree, parcels, full=False):
        tree.delete(*tree.get_children())
        for p in parcels:
            tree.insert("", "end", iid=p.number, values=self._parcelValues(p, full), tags=("st_" + p.status.name,))

    def _buildMain(self, parent):
        parcels = self.parcelService.findAll()
        inWay = sum(p.status in (S.SENT, S.IN_TRANSIT) for p in parcels)
        done = sum(p.status == S.DELIVERED for p in parcels)
        delayed = sum(p.status == S.DELAYED for p in parcels)
        tk.Label(parent, text="Обзор отправлений", bg=BG, fg=NAVY, font=("Arial", 13, "bold")).pack(anchor="w", pady=(0, 6))
        self._statCards(parent, [("Всего посылок", len(parcels), NAVY), ("В пути", inWay, ORANGE),
                                 ("Доставлено", done, GREEN), ("Задержано", delayed, RED)])
        card = self._card(parent, "Последние отправления", "Недавно зарегистрированные посылки", expand=True, fill="both")
        tree = self._table(card, ("Номер", "Получатель", "Маршрут", "Статус"), (160, 200, 200, 200), 6)
        self._fillParcels(tree, sorted(parcels, key=lambda p: p.id, reverse=True)[:5])
        row = tk.Frame(card, bg=WHITE)
        row.pack(fill="x", pady=(10, 0))
        FlatButton(row, "Подробнее", lambda: self._details(tree), bg=WHITE, fg=BLUE).pack(side="left")
        if self._can("register_parcel"):
            FlatButton(row, "Добавить посылку", self.openNewParcel).pack(side="right")

    def _details(self, tree):
        number = self._selected(tree)
        if number:
            self.openTracking(number)

    def _buildParcels(self, parent):
        card = self._card(parent, "Список отправлений", "Все посылки в системе", expand=True, fill="both")
        tree = self._table(card, ("Номер", "Отправитель", "Получатель", "Маршрут", "Ожидаемая доставка", "Статус"),
                           (130, 150, 150, 150, 140, 190), 14)
        self._fillParcels(tree, self.parcelService.findAll(), full=True)
        row = tk.Frame(card, bg=WHITE)
        row.pack(fill="x", pady=(10, 0))
        FlatButton(row, "Подробнее", lambda: self._details(tree), bg=WHITE, fg=BLUE).pack(side="left")
        if self._can("change_status"):
            FlatButton(row, "Изменить статус", lambda: self._askStatus(tree), bg=WHITE, fg=BLUE).pack(side="left", padx=8)
        if self._can("register_parcel"):
            FlatButton(row, "Добавить посылку", self.openNewParcel).pack(side="right")

    def _askStatus(self, tree):
        number = self._selected(tree)
        if not number:
            return
        parcel = self.parcelService.findParcel(number)
        allowed = [s for s in S if self.parcelService.isStatusAllowed(parcel.status, s)]
        if not allowed:
            self.showError("Для этой посылки изменение статуса невозможно")
            return
        dlg = FormDialog(self.root, f"Изменение статуса {number}", [
            {"key": "status", "label": "Новый статус", "type": "combo",
             "values": [s.value for s in allowed], "default": allowed[0].value},
            {"key": "description", "label": "Комментарий (необязательно)"}], "Применить")
        self.root.wait_window(dlg)
        if dlg.result:
            status = next(s for s in S if s.value == dlg.result["status"])
            if self.changeParcelStatus(number, status, dlg.result["description"]):
                self._refresh()

    def _buildNewParcel(self, parent):
        card = self._card(parent, "Регистрация отправления", "Начальный статус будет установлен автоматически: «Зарегистрирована»")
        today = date.today()
        defaults = {"sender": "", "sender_phone": "+375 29 ", "recipient": "", "recipient_phone": "+375 29 ",
                    "address": "", "departure": today.isoformat(), "estimated": (today + timedelta(days=2)).isoformat()}
        self.formVars = {k: tk.StringVar(value=v) for k, v in defaults.items()}
        layout = [("ФИО отправителя", "sender", 0, 0), ("Телефон отправителя", "sender_phone", 0, 1),
                  ("ФИО получателя", "recipient", 0, 2), ("Телефон получателя", "recipient_phone", 0, 3),
                  ("Адрес доставки (Город, улица, дом, квартира)", "address", 1, 0),
                  ("Дата отправления (ГГГГ-ММ-ДД)", "departure", 2, 0),
                  ("Предполагаемая дата доставки (ГГГГ-ММ-ДД)", "estimated", 2, 1)]
        grid = tk.Frame(card, bg=WHITE)
        grid.pack(fill="x")
        for label, key, r, c in layout:
            cell = tk.Frame(grid, bg=WHITE)
            span = 4 if key == "address" else 1
            cell.grid(row=r, column=c, columnspan=span, sticky="ew", padx=(0, 10), pady=6)
            tk.Label(cell, text=label, bg=WHITE, fg=MUTED, font=("Arial", 9)).pack(anchor="w")
            self._entry(cell, self.formVars[key], 24).pack(fill="x", ipady=4)
        for c in range(4):
            grid.columnconfigure(c, weight=1, uniform="f")
        row = tk.Frame(card, bg=WHITE)
        row.pack(fill="x", pady=(14, 0))
        FlatButton(row, "Сохранить", self.registerParcel).pack(side="right")
        FlatButton(row, "Отмена", self.openParcels, bg=WHITE, fg=BLUE).pack(side="right", padx=8)

    def _buildTracking(self, parent, prefill=""):
        bar = self._card(parent)
        tk.Label(bar, text="Номер отправления", bg=WHITE, fg=MUTED, font=("Arial", 9)).pack(anchor="w")
        row = tk.Frame(bar, bg=WHITE)
        row.pack(fill="x")
        self.trackVar = tk.StringVar(value=prefill)
        e = self._entry(row, self.trackVar, 40)
        e.pack(side="left", fill="x", expand=True, ipady=5)
        e.bind("<Return>", lambda ev: self.trackParcel(self.trackVar.get()))
        FlatButton(row, "Найти", lambda: self.trackParcel(self.trackVar.get())).pack(side="left", padx=(8, 0))
        self.trackResult = tk.Frame(parent, bg=BG)
        self.trackResult.pack(fill="both", expand=True)

    def _buildCouriers(self, parent):
        couriers = self.userService.getUsersByRole(ROLE_COURIER)
        load = {c.id: [p for p in self.parcelService.findByCourier(c.id) if p.status not in FINAL_STATUSES]
                for c in couriers}
        busy = sum(1 for c in couriers if load[c.id])
        self._statCards(parent, [("Всего курьеров", len(couriers), NAVY), ("На маршруте", busy, ORANGE),
                                 ("Свободны", len(couriers) - busy, GREEN)])
        card = self._card(parent, "Список курьеров", "Назначение посылок и контроль доставки", expand=True, fill="both")
        tree = self._table(card, ("ФИО", "Телефон", "Активных посылок", "Статус"), (220, 180, 160, 160), 8)
        for c in couriers:
            tree.insert("", "end", iid=str(c.id), values=(c.name, c.contactInfo, len(load[c.id]),
                                                           "На маршруте" if load[c.id] else "Свободен"))
        row = tk.Frame(card, bg=WHITE)
        row.pack(fill="x", pady=(10, 0))

        def details():
            cid = self._selected(tree)
            if cid:
                nums = [p.number + " — " + p.deliveryAddress for p in load[int(cid)]]
                self.showMessage("Активные посылки курьера:\n\n" + ("\n".join(nums) if nums else "нет"))

        def add():
            dlg = FormDialog(self.root, "Добавить курьера", [
                {"key": "name", "label": "ФИО"}, {"key": "phone", "label": "Телефон", "default": "+375 "},
                {"key": "login", "label": "Логин"}, {"key": "password", "label": "Пароль", "type": "password"}])
            self.root.wait_window(dlg)
            if dlg.result:
                r = dlg.result
                try:
                    self.userService.createUser(ROLE_COURIER, r["name"], r["phone"], r["login"], r["password"])
                except ValueError as exc:
                    self.showError(str(exc))
                    return
                self._refresh()

        FlatButton(row, "Подробнее", details, bg=WHITE, fg=BLUE).pack(side="left")
        if self._can("manage_couriers"):
            FlatButton(row, "Добавить курьера", add).pack(side="right")

    def _buildReports(self, parent):
        parcels = self.parcelService.findAll()
        delivered = [p for p in parcels if p.status == S.DELIVERED]
        days = []
        for p in delivered:
            rec = [r for r in p.records if r.status == S.DELIVERED]
            if rec:
                days.append(max((rec[-1].timestamp.date() - p.departureDate).days, 0))
        avg = f"{sum(days) / len(days):.1f}".replace(".", ",") + " дня" if days else "—"
        self._statCards(parent, [("Доставлено за период", len(delivered), GREEN), ("Средний срок доставки", avg, NAVY),
                                 ("Задержано", sum(p.status == S.DELAYED for p in parcels), RED)])
        card = self._card(parent, "Доставленные посылки по месяцам", "Динамика работы компании", expand=True, fill="both")
        FlatButton(card, "Экспорт", lambda: self._export(parcels), bg=WHITE, fg=BLUE).place(relx=1.0, y=0, anchor="ne")
        today = date.today()
        months = []
        y, m = today.year, today.month
        for _ in range(6):
            months.append((y, m))
            m -= 1
            if m == 0:
                y, m = y - 1, 12
        months.reverse()
        counts = [0] * 6
        for p in delivered:
            for r in p.records:
                if r.status == S.DELIVERED and (r.timestamp.year, r.timestamp.month) in months:
                    counts[months.index((r.timestamp.year, r.timestamp.month))] += 1
        canvas = tk.Canvas(card, bg=WHITE, height=260, highlightthickness=0)
        canvas.pack(fill="both", expand=True, pady=(10, 0))

        def draw(event=None):
            canvas.delete("all")
            w, h = canvas.winfo_width(), canvas.winfo_height()
            top = max(counts) or 1
            slot = max(w, 300) / 6
            for i, cnt in enumerate(counts):
                bh = (h - 50) * cnt / top
                x0 = i * slot + slot * 0.2
                canvas.create_rectangle(x0, h - 30 - bh, x0 + slot * 0.6, h - 30, fill=BLUE, outline="")
                canvas.create_text(x0 + slot * 0.3, h - 36 - bh, text=str(cnt), fill=NAVY, font=FONT_B)
                canvas.create_text(x0 + slot * 0.3, h - 14, text=MONTHS[months[i][1] - 1], fill=MUTED, font=("Arial", 9))

        canvas.bind("<Configure>", draw)

    def _export(self, parcels):
        path = filedialog.asksaveasfilename(parent=self.root, defaultextension=".csv", initialfile="parcels_report.csv",
                                            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["Номер", "Отправитель", "Получатель", "Маршрут", "Адрес", "Дата отправления", "Ожидаемая доставка", "Статус"])
            for p in parcels:
                w.writerow([p.number, p.sender, p.recipient, p.route, p.deliveryAddress, p.departureDate,
                            p.estimatedDeliveryDate, p.status.value])
        self.showMessage(f"Отчёт сохранён: {path}")

    def _buildSettingsAdmin(self, parent):
        card = self._card(parent, "Пользователи и права доступа", "Управление учётными записями и ролями", expand=True, fill="both")
        bar = tk.Frame(card, bg=WHITE)
        bar.pack(fill="x", pady=(0, 8))
        search, role = tk.StringVar(), tk.StringVar(value="Все роли")
        tk.Label(bar, text="Поиск (ФИО или логин):", bg=WHITE, fg=MUTED).pack(side="left")
        self._entry(bar, search, 28).pack(side="left", padx=6, ipady=3)
        ttk.Combobox(bar, textvariable=role, state="readonly", width=16,
                     values=["Все роли"] + list(USER_CLASSES)).pack(side="left", padx=6)
        tree = self._table(card, ("ФИО", "Логин", "Роль", "Статус"), (260, 180, 180, 140), 12)

        def fill(*_):
            tree.delete(*tree.get_children())
            q = search.get().lower()
            for u in self.userService.getUsers():
                if (q in u.name.lower() or q in u.login.lower()) and role.get() in ("Все роли", u.role):
                    tree.insert("", "end", iid=str(u.id), values=(u.name, u.login, u.role,
                                                                  "Активен" if u.active else "Заблокирован"))

        search.trace_add("write", fill)
        role.trace_add("write", fill)
        fill()

        def add():
            dlg = FormDialog(self.root, "Добавить пользователя", [
                {"key": "name", "label": "ФИО"}, {"key": "login", "label": "Логин"},
                {"key": "password", "label": "Пароль", "type": "password"},
                {"key": "phone", "label": "Контактная информация"},
                {"key": "role", "label": "Роль", "type": "combo", "values": list(USER_CLASSES), "default": ROLE_CLIENT}])
            self.root.wait_window(dlg)
            if dlg.result:
                r = dlg.result
                try:
                    self.userService.createUser(r["role"], r["name"], r["phone"], r["login"], r["password"])
                except ValueError as exc:
                    self.showError(str(exc))
                    return
                fill()

        def rights():
            uid = self._selected(tree)
            if not uid:
                return
            u = self.userService.findById(int(uid))
            dlg = FormDialog(self.root, f"Права: {u.name}", [
                {"key": "role", "label": "Роль", "type": "combo", "values": list(USER_CLASSES), "default": u.role},
                {"key": "active", "label": "Статус", "type": "combo", "values": ["Активен", "Заблокирован"],
                 "default": "Активен" if u.active else "Заблокирован"},
                {"key": "password", "label": "Новый пароль (оставьте пустым, чтобы не менять)", "type": "password"}])
            self.root.wait_window(dlg)
            if not dlg.result:
                return
            r = dlg.result
            try:
                if u.id == self.currentUser.id and (r["role"] != u.role or r["active"] != "Активен"):
                    raise ValueError("Нельзя изменить собственную роль или заблокировать себя")
                if r["role"] != u.role:
                    self.userService.manageUser(u.id, "role:" + r["role"])
                self.userService.manageUser(u.id, "activate" if r["active"] == "Активен" else "deactivate")
                if r["password"]:
                    self.userService.manageUser(u.id, "password:" + r["password"])
            except ValueError as exc:
                self.showError(str(exc))
            fill()

        def delete():
            uid = self._selected(tree)
            if uid and int(uid) == self.currentUser.id:
                self.showError("Нельзя удалить собственную учётную запись")
            elif uid and messagebox.askyesno("Удаление", "Удалить выбранного пользователя?", parent=self.root):
                self.userService.manageUser(int(uid), "delete")
                fill()

        row = tk.Frame(card, bg=WHITE)
        row.pack(fill="x", pady=(10, 0))
        FlatButton(row, "Изменить права →", rights, bg=WHITE, fg=BLUE).pack(side="left")
        FlatButton(row, "Удалить", delete, bg=WHITE, fg=RED).pack(side="left", padx=8)
        FlatButton(row, "Добавить пользователя", add).pack(side="right")

    def _buildProfile(self, parent):
        u = self.currentUser
        card = self._card(parent, "Профиль пользователя", "Сведения об учётной записи")
        for k, val in (("ФИО", u.name), ("Логин", u.login), ("Роль", u.role), ("Контакты", u.contactInfo)):
            row = tk.Frame(card, bg=WHITE)
            row.pack(fill="x", pady=4)
            tk.Label(row, text=k, width=12, anchor="w", bg=WHITE, fg=MUTED).pack(side="left")
            tk.Label(row, text=val, bg=WHITE, fg=NAVY, font=FONT_B).pack(side="left")

    # ------------------------------------------------------------------ экраны: курьер
    def _buildCourierParcels(self, parent):
        mine = self.parcelService.findByCourier(self.currentUser.id)
        active = [p for p in mine if p.status not in FINAL_STATUSES]
        today = date.today()
        deliveredToday = sum(1 for p in mine for r in p.records
                             if r.status == S.DELIVERED and r.timestamp.date() == today)
        self._statCards(parent, [("К доставке", len(active), ORANGE), ("Доставлено сегодня", deliveredToday, GREEN)])
        card = self._card(parent, "Посылки для доставки", "Отметьте вручение после доставки получателю", expand=True, fill="both")
        bar = tk.Frame(card, bg=WHITE)
        bar.pack(fill="x", pady=(0, 6))
        flt = tk.StringVar()
        tk.Label(bar, text="Фильтр по адресу:", bg=WHITE, fg=MUTED).pack(side="left")
        self._entry(bar, flt, 30).pack(side="left", padx=6, ipady=3)
        tree = self._table(card, ("Номер", "Получатель", "Адрес доставки", "Статус"), (150, 180, 330, 190), 10)

        def fill(*_):
            tree.delete(*tree.get_children())
            for p in active:
                if flt.get().lower() in p.deliveryAddress.lower():
                    tree.insert("", "end", iid=p.number, tags=("st_" + p.status.name,),
                                values=(p.number, p.recipient, p.deliveryAddress, p.status.value))

        flt.trace_add("write", fill)
        fill()

        def deliver():
            n = self._selected(tree)
            if n and self.changeParcelStatus(n, S.DELIVERED, f"Вручено получателю. Курьер: {self.currentUser.name}"):
                self._refresh()

        def refuse():
            n = self._selected(tree)
            if not n:
                return
            dlg = FormDialog(self.root, "Оформить отказ от получения", [{"key": "reason", "label": "Причина"}], "Оформить")
            self.root.wait_window(dlg)
            if dlg.result and self.changeParcelStatus(n, S.NOT_DELIVERED, "Отказ/не вручено: " + dlg.result["reason"]):
                self._refresh()

        row = tk.Frame(card, bg=WHITE)
        row.pack(fill="x", pady=(10, 0))
        FlatButton(row, "Подробнее", lambda: self._details(tree), bg=WHITE, fg=BLUE).pack(side="left")
        FlatButton(row, "Не вручена (отказ)", refuse, bg=WHITE, fg=RED).pack(side="left", padx=8)
        FlatButton(row, "Вручена получателю", deliver).pack(side="right")

    def _buildDeliveryHistory(self, parent):
        card = self._card(parent, "Завершённые доставки", "Вручённые и невручённые посылки", expand=True, fill="both")
        tree = self._table(card, ("Номер", "Получатель", "Адрес доставки", "Результат", "Дата"), (140, 160, 300, 160, 150), 14)
        for p in self.parcelService.findByCourier(self.currentUser.id):
            if p.status in FINAL_STATUSES:
                tree.insert("", "end", iid=p.number, tags=("st_" + p.status.name,),
                            values=(p.number, p.recipient, p.deliveryAddress, p.status.value, self._fmt(p.records[-1].timestamp)))

    # ------------------------------------------------------------------ экраны: клиент
    def _buildClientParcels(self, parent):
        mine = self.currentUser.viewMyParcels(self.parcelService)
        self._statCards(parent, [("Всего посылок", len(mine), NAVY),
                                 ("В пути", sum(p.status in (S.SENT, S.IN_TRANSIT) for p in mine), ORANGE),
                                 ("Доставлено", sum(p.status == S.DELIVERED for p in mine), GREEN)])
        card = self._card(parent, "Мои отправления", "Нажмите «Подробнее», чтобы увидеть историю перемещения", expand=True, fill="both")
        tree = self._table(card, ("Номер", "Маршрут", "Ожидаемая доставка", "Статус"), (160, 200, 180, 200), 10)
        for p in mine:
            tree.insert("", "end", iid=p.number, tags=("st_" + p.status.name,),
                        values=(p.number, p.route, self._fmt(p.estimatedDeliveryDate), p.status.value))
        FlatButton(card, "Подробнее →", lambda: self._details(tree), bg=WHITE, fg=BLUE).pack(anchor="w", pady=(10, 0))

    def _buildNotifications(self, parent):
        items = self.notificationService.getNotifications(self.currentUser.id)
        unread = sum(not n.isRead for n in items)
        card = self._card(parent, "Изменения статусов", f"Новых уведомлений: {unread}", expand=True, fill="both")
        tree = self._table(card, ("Нов.", "Уведомление", "Время"), (50, 500, 180), 12)
        for n in items:
            tree.insert("", "end", iid=str(n.id), values=("" if n.isRead else "●", n.message, self._fmt(n.sentAt)))
        by_id = {str(n.id): n for n in items}

        def open_selected():
            nid = self._selected(tree)
            if nid:
                self.openTracking(by_id[nid].parcelNumber)

        def mark():
            self.notificationService.markAllRead(self.currentUser.id)
            self._refresh()

        row = tk.Frame(card, bg=WHITE)
        row.pack(fill="x", pady=(10, 0))
        FlatButton(row, "Открыть →", open_selected, bg=WHITE, fg=BLUE).pack(side="left")
        FlatButton(row, "Отметить все прочитанными", mark, bg=WHITE, fg=BLUE).pack(side="right")

    # ------------------------------------------------------------------ служебные
    def _leastLoadedCourier(self) -> int:
        couriers = self.userService.getUsersByRole(ROLE_COURIER)
        if not couriers:
            return 0
        def load(c):
            return sum(p.status not in FINAL_STATUSES for p in self.parcelService.findByCourier(c.id))
        return min(couriers, key=load).id

    @staticmethod
    def _cityFromAddress(address: str) -> str:
        first = address.split(",")[0].strip()
        first = re.sub(r"^(г\.|город)\s*", "", first, flags=re.I).strip()
        return first or "Минск"
