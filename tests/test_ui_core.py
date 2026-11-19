"""Тесты UI: вспомогательные классы, вход/выход, оболочка, навигация."""
import unittest
from datetime import date, datetime
from unittest import mock

from parcelflow import ui as ui_module
from parcelflow.entities import (ROLE_ADMIN, ROLE_CLIENT, ROLE_COURIER, ROLE_OPERATOR,
                                 ParcelStatus as S)
from parcelflow.ui import (BLUE, INITIAL_STATE, NAV, NAVY, FlatButton, FormDialog,
                           LogisticsUI, parseDate)

from . import fake_tk
from .helpers import Env, make_parcel
from .ui_helpers import (answer, cancel, click, find_buttons, find_combos, find_entries,
                         find_labels, find_trees, label_texts)


class UITestCase(unittest.TestCase):
    """База: свежая БД с демо-данными, поддельное окно и вход под нужным пользователем."""
    seed = True

    def setUp(self):
        fake_tk.state.reset()
        self.env = Env(seed=self.seed)
        self.root = fake_tk.Tk()
        self.ui = LogisticsUI(self.root, self.env.parcelService, self.env.trackingService,
                              self.env.userService, self.env.notificationService)

    def login(self, login, password=None):
        self.ui.loginVar.set(login)
        self.ui.passVar.set(password or login)
        self.ui.enterSystem()
        self.assertIsNotNone(self.ui.currentUser, f"не удалось войти как {login}")

    def tree(self, index=0):
        return find_trees(self.ui.content)[index]

    def button(self, text):
        found = find_buttons(self.ui.content, text)
        self.assertEqual(len(found), 1, f"кнопка «{text}»: найдено {len(found)}")
        return found[0]

    def has_button(self, text):
        return bool(find_buttons(self.ui.content, text))

    @staticmethod
    def select(tree, iid):
        tree.selection_set(iid)

    @property
    def errors(self):
        return fake_tk.state.errors

    @property
    def infos(self):
        return fake_tk.state.infos


class ParseDateTests(unittest.TestCase):
    def test_iso_and_dotted_formats(self):
        self.assertEqual(parseDate("2026-03-05"), date(2026, 3, 5))
        self.assertEqual(parseDate("05.03.2026"), date(2026, 3, 5))
        self.assertEqual(parseDate("  2026-03-05 "), date(2026, 3, 5))

    def test_invalid_raises(self):
        for text in ("", "завтра", "2026/03/05", "31.02.2026"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    parseDate(text)


class FlatButtonTests(unittest.TestCase):
    def test_click_calls_command(self):
        calls = []
        btn = FlatButton(fake_tk.Frame(), "Ок", lambda: calls.append(1))
        click(btn)
        self.assertEqual(calls, [1])
        self.assertEqual(btn.options["text"], "Ок")
        self.assertEqual(btn.options["bg"], BLUE)


class FormDialogTests(unittest.TestCase):
    FIELDS = [{"key": "a", "label": "A", "default": "x"},
              {"key": "p", "label": "P", "type": "password"},
              {"key": "c", "label": "C", "type": "combo", "values": ["1", "2"], "default": "2"}]

    def setUp(self):
        fake_tk.state.reset()
        self.dlg = FormDialog(fake_tk.Tk(), "Заголовок", self.FIELDS, "Применить")

    def test_widgets_follow_field_types(self):
        self.assertEqual(self.dlg.title(), "Заголовок")
        entries = find_entries(self.dlg)
        self.assertEqual([e.options["show"] for e in entries], ["", "*"])
        self.assertEqual(find_combos(self.dlg)[0].options["values"], ["1", "2"])
        self.assertEqual(len(find_buttons(self.dlg, "Применить")), 1)

    def test_ok_collects_values_and_closes(self):
        self.dlg.vars["a"].set("новое")
        click(find_buttons(self.dlg, "Применить")[0])
        self.assertEqual(self.dlg.result, {"a": "новое", "p": "", "c": "2"})
        self.assertTrue(self.dlg.destroyed)

    def test_cancel_leaves_result_empty(self):
        click(find_buttons(self.dlg, "Отмена")[0])
        self.assertIsNone(self.dlg.result)
        self.assertTrue(self.dlg.destroyed)


class NavigationTableTests(unittest.TestCase):
    def test_every_menu_item_is_a_method(self):
        for role, (items, bottom) in NAV.items():
            for _, method in items + [bottom]:
                self.assertTrue(callable(getattr(LogisticsUI, method)), (role, method))
        for role, method in INITIAL_STATE.items():
            self.assertTrue(callable(getattr(LogisticsUI, method)), (role, method))


class StartupAndLoginTests(UITestCase):
    def test_init_state(self):
        self.assertEqual(self.ui.currentState, "login")
        self.assertIsNone(self.ui.currentUser)
        self.assertEqual(self.ui.extensions, {})
        self.assertIn("ParcelFlow", self.root.title())

    def test_run_starts_mainloop(self):
        self.ui.run()
        self.assertTrue(fake_tk.state.mainloop_called)

    def test_register_extension(self):
        launcher = mock.Mock()
        self.ui.registerExtension("Карта", [ROLE_OPERATOR], launcher, perParcel=True)
        self.assertEqual(self.ui.extensions["Карта"],
                         {"roles": [ROLE_OPERATOR], "launcher": launcher, "perParcel": True})

    def test_wrong_credentials(self):
        self.ui.loginVar.set("admin")
        self.ui.passVar.set("nope")
        self.ui.enterSystem()
        self.assertIsNone(self.ui.currentUser)
        self.assertEqual(self.ui.passVar.get(), "")
        self.assertIn("Неверные данные", self.errors[0])

    def test_blocked_user_cannot_login(self):
        client = self.env.userService.getUsersByRole(ROLE_CLIENT)[0]
        self.env.userService.manageUser(client.id, "deactivate")
        self.ui.loginVar.set("client1")
        self.ui.passVar.set("client1")
        self.ui.enterSystem()
        self.assertIsNone(self.ui.currentUser)
        self.assertEqual(len(self.errors), 1)

    def test_login_screen_forgot_password_and_enter_key(self):
        click(find_labels(self.root, "Забыли пароль?")[0])
        self.assertIn("администратору", self.infos[0])
        entries = find_entries(self.root)
        self.assertEqual(len(entries), 2)
        self.ui.loginVar.set("ghost")
        entries[1].bindings["<Return>"](None)
        self.assertEqual(len(self.errors), 1)

    def test_each_role_lands_on_its_initial_screen(self):
        titles = {ROLE_ADMIN: "Настройки", ROLE_OPERATOR: "Главная",
                  ROLE_COURIER: "Мои посылки", ROLE_CLIENT: "Мои посылки"}
        logins = {ROLE_ADMIN: "admin", ROLE_OPERATOR: "operator1",
                  ROLE_COURIER: "courier1", ROLE_CLIENT: "client1"}
        for role, login in logins.items():
            with self.subTest(role=role):
                self.ui.showLogin()
                self.login(login)
                self.assertEqual(self.ui.currentUser.role, role)
                self.assertEqual(self.ui.currentState, INITIAL_STATE[role])
                self.assertEqual(self.ui.titleLabel.options["text"], titles[role])

    def test_logout_returns_to_login(self):
        self.login("admin")
        self.ui.logout()
        self.assertEqual(self.ui.currentState, "login")
        self.assertIsNone(self.ui.currentUser)
        self.assertEqual(self.ui.navButtons, {})


class ShellTests(UITestCase):
    def test_menu_matches_role(self):
        self.login("operator1")
        expected = {method for _, method in NAV[ROLE_OPERATOR][0]} | {"openSettings"}
        self.assertEqual(set(self.ui.navButtons), expected)

    def test_active_menu_item_is_highlighted(self):
        self.login("operator1")
        self.ui.openParcels()
        colors = {k: b.options["bg"] for k, b in self.ui.navButtons.items()}
        self.assertEqual(colors["openParcels"], BLUE)
        self.assertEqual(colors["openMain"], NAVY)

    def test_nav_button_click_opens_screen(self):
        self.login("operator1")
        click(self.ui.navButtons["openCouriers"])
        self.assertEqual(self.ui.currentState, "openCouriers")
        self.assertEqual(self.ui.titleLabel.options["text"], "Курьеры")

    def test_header_has_user_info_and_logout(self):
        self.login("courier1")
        self.assertTrue(any("Смирнов П.Л." in t for t in label_texts(self.root)))
        click(find_buttons(self.root, "Выйти")[0])
        self.assertEqual(self.ui.currentState, "login")

    def test_extensions_appear_only_for_their_roles(self):
        launcher = mock.Mock()
        self.ui.registerExtension("Карта", [ROLE_OPERATOR], launcher)
        self.login("operator1")
        self.assertIn("ДОПОЛНИТЕЛЬНО", label_texts(self.root))
        click(find_buttons(self.root, "Карта")[0])
        launcher.assert_called_once_with(self.ui.currentUser, None)
        self.ui.showLogin()
        self.login("admin")
        self.assertNotIn("ДОПОЛНИТЕЛЬНО", label_texts(self.root))
        self.assertEqual(find_buttons(self.root, "Карта"), [])

    def test_refresh_rebuilds_current_screen(self):
        self.login("operator1")
        calls = []
        self.ui._open("Тест", "openTest", lambda parent, *a: calls.append(a), 1, 2, highlight="openMain")
        self.ui._refresh()
        self.assertEqual(calls, [(1, 2), (1, 2)])
        self.assertEqual(self.ui.navButtons["openMain"].options["bg"], BLUE)

    def test_open_screens_by_role(self):
        self.login("operator1")
        for method, state in [("openMain", "openMain"), ("openParcels", "openParcels"),
                              ("openTracking", "openTracking"), ("openCouriers", "openCouriers"),
                              ("openReports", "openReports"), ("openSettings", "openSettings"),
                              ("openNewParcel", "openNewParcel")]:
            with self.subTest(method=method):
                getattr(self.ui, method)()
                self.assertEqual(self.ui.currentState, state)

    def test_new_parcel_needs_permission(self):
        self.login("admin")
        self.ui.openNewParcel()
        self.assertEqual(self.ui.currentState, "openSettings")
        self.assertIn("Недостаточно прав", self.errors[0])

    def test_new_parcel_highlights_parcels_menu(self):
        self.login("operator1")
        self.ui.openNewParcel()
        self.assertEqual(self.ui.navButtons["openParcels"].options["bg"], BLUE)


class HelperMethodTests(UITestCase):
    def test_fmt(self):
        self.assertEqual(LogisticsUI._fmt(datetime(2026, 3, 5, 14, 7)), "05.03.2026, 14:07")
        self.assertEqual(LogisticsUI._fmt(date(2026, 3, 5)), "05.03.2026")

    def test_city_is_route(self):
        self.assertEqual(LogisticsUI._city(make_parcel(route="Минск-Брест")), "Минск-Брест")

    def test_city_from_address(self):
        city = LogisticsUI._cityFromAddress
        self.assertEqual(city("г. Брест, ул. Ленина, 1"), "Брест")
        self.assertEqual(city("город Витебск, пр. Мира"), "Витебск")
        self.assertEqual(city("Гродно, ул. Советская"), "Гродно")
        self.assertEqual(city("г., ул. Ленина"), "Минск")
        self.assertEqual(city(""), "Минск")

    def test_can_requires_login_and_permission(self):
        self.assertFalse(self.ui._can("track_parcel"))
        self.login("client1")
        self.assertTrue(self.ui._can("track_parcel"))
        self.assertFalse(self.ui._can("register_parcel"))

    def test_messages(self):
        self.ui.showError("беда")
        self.ui.showMessage("ок")
        self.assertEqual(self.errors, ["беда"])
        self.assertEqual(self.infos, ["ок"])

    def test_selected_requires_selection(self):
        tree = fake_tk.Treeview(fake_tk.Frame())
        self.assertIsNone(self.ui._selected(tree))
        self.assertEqual(self.errors, ["Выберите строку в таблице"])
        tree.insert("", "end", iid="r1", values=())
        tree.selection_set("r1")
        self.assertEqual(self.ui._selected(tree), "r1")

    def test_least_loaded_courier(self):
        self.login("operator1")
        couriers = self.env.userService.getUsersByRole(ROLE_COURIER)

        def load(c):
            return sum(p.status not in ui_module.FINAL_STATUSES for p in self.env.parcelService.findByCourier(c.id))

        self.assertEqual(self.ui._leastLoadedCourier(), min(couriers, key=load).id)

    def test_parcel_values(self):
        parcel = make_parcel(number="BY1", status=S.SENT)
        short = self.ui._parcelValues(parcel)
        full = self.ui._parcelValues(parcel, full=True)
        self.assertEqual(short, ("BY1", "Иванов И.А.", "Минск-Брест", S.SENT.value))
        self.assertEqual(len(full), 6)
        self.assertEqual(full[-1], S.SENT.value)


class NoCouriersTests(UITestCase):
    seed = False

    def test_least_loaded_courier_without_couriers(self):
        self.env.userService.createUser(ROLE_OPERATOR, "Оп", "", "op", "op")
        self.login("op")
        self.assertEqual(self.ui._leastLoadedCourier(), 0)


if __name__ == "__main__":
    unittest.main()
