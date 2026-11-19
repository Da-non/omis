"""Тесты UI: экраны оператора и администратора."""
import csv
import os
import tempfile
from datetime import date
from unittest import mock

from parcelflow.entities import ROLE_ADMIN, ROLE_CLIENT, ROLE_COURIER, ROLE_OPERATOR, ParcelStatus as S
from parcelflow.services import FINAL_STATUSES, UserService

from . import fake_tk
from .helpers import make_parcel
from .test_ui_core import UITestCase
from .ui_helpers import (answer, cancel, click, find_buttons, find_combos, find_entries,
                         find_labels, find_trees, label_texts)


class MainAndParcelsTests(UITestCase):
    def test_main_screen_for_operator(self):
        self.login("operator1")
        parcels = self.env.parcelService.findAll()
        texts = label_texts(self.ui.content)
        self.assertIn("Всего посылок", texts)
        self.assertIn(str(len(parcels)), texts)
        rows = self.tree().get_children()
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0], max(parcels, key=lambda p: p.id).number)
        self.assertTrue(self.has_button("Добавить посылку"))

    def test_main_screen_for_admin_has_no_add_button(self):
        self.login("admin")
        self.ui.openMain()
        self.assertFalse(self.has_button("Добавить посылку"))

    def test_details_requires_selection(self):
        self.login("operator1")
        click(self.button("Подробнее"))
        self.assertEqual(self.errors, ["Выберите строку в таблице"])
        self.assertEqual(self.ui.currentState, "openMain")

    def test_details_opens_tracking(self):
        self.login("operator1")
        tree = self.tree()
        self.select(tree, tree.get_children()[0])
        click(self.button("Подробнее"))
        self.assertEqual(self.ui.currentState, "openTracking")
        self.assertIn("Информация о посылке", label_texts(self.ui.content))

    def test_add_button_opens_form(self):
        self.login("operator1")
        click(self.button("Добавить посылку"))
        self.assertEqual(self.ui.currentState, "openNewParcel")

    def test_parcels_list_for_operator_and_admin(self):
        self.login("operator1")
        self.ui.openParcels()
        self.assertEqual(len(self.tree().get_children()), len(self.env.parcelService.findAll()))
        self.assertTrue(self.has_button("Изменить статус"))
        self.assertTrue(self.has_button("Добавить посылку"))
        self.ui.showLogin()
        self.login("admin")
        self.ui.openParcels()
        self.assertFalse(self.has_button("Изменить статус"))
        self.assertFalse(self.has_button("Добавить посылку"))

    def test_parcels_list_rows_are_coloured_by_status(self):
        self.login("operator1")
        self.ui.openParcels()
        tree = self.tree()
        item = tree.items["BY321987654"]
        self.assertEqual(item["tags"], ("st_DELAYED",))
        self.assertEqual(item["values"][-1], S.DELAYED.value)


class ChangeStatusDialogTests(UITestCase):
    def setUp(self):
        super().setUp()
        self.login("operator1")
        self.ui.openParcels()

    def test_requires_selection(self):
        click(self.button("Изменить статус"))
        self.assertEqual(self.errors, ["Выберите строку в таблице"])

    def test_final_parcel_cannot_change(self):
        self.select(self.tree(), "BY987654321")  # вручена
        click(self.button("Изменить статус"))
        self.assertIn("невозможно", self.errors[0])

    def test_change_status_success(self):
        self.select(self.tree(), "BY421985673")  # зарегистрирована
        fake_tk.state.dialog_handler = answer(status=S.ACCEPTED.value, description="принята")
        click(self.button("Изменить статус"))
        parcel = self.env.parcelService.findParcel("BY421985673")
        self.assertEqual(parcel.status, S.ACCEPTED)
        self.assertEqual(parcel.records[-1].description, "принята")
        self.assertIn("Клиент получит уведомление", self.infos[0])
        self.assertEqual(self.tree().items["BY421985673"]["values"][-1], S.ACCEPTED.value)

    def test_dialog_offers_only_allowed_statuses(self):
        self.select(self.tree(), "BY421985673")
        offered = []

        def handler(dlg):
            offered.extend(find_combos(dlg)[0].options["values"])
            self.assertEqual(dlg.vars["status"].get(), offered[0])  # по умолчанию — первый допустимый
            cancel(dlg)

        fake_tk.state.dialog_handler = handler
        click(self.button("Изменить статус"))
        self.assertNotIn(S.REGISTERED.value, offered)
        self.assertNotIn(S.NOT_DELIVERED.value, offered)
        self.assertIn(S.DELAYED.value, offered)

    def test_cancel_changes_nothing(self):
        self.select(self.tree(), "BY421985673")
        fake_tk.state.dialog_handler = cancel
        click(self.button("Изменить статус"))
        self.assertEqual(self.env.parcelService.findParcel("BY421985673").status, S.REGISTERED)
        self.assertEqual(self.infos, [])

    def test_failed_change_does_not_refresh(self):
        self.select(self.tree(), "BY421985673")
        fake_tk.state.dialog_handler = answer(status=S.ACCEPTED.value)
        with mock.patch.object(self.ui, "changeParcelStatus", return_value=False), \
                mock.patch.object(self.ui, "_refresh") as refresh:
            click(self.button("Изменить статус"))
        refresh.assert_not_called()


class ChangeParcelStatusTests(UITestCase):
    def test_client_has_no_rights(self):
        self.login("client1")
        self.assertFalse(self.ui.changeParcelStatus("BY123456789", S.SENT))
        self.assertIn("Недостаточно прав", self.errors[0])

    def test_delivery_right_is_checked_for_final_statuses(self):
        self.login("client1")
        self.assertFalse(self.ui.changeParcelStatus("BY123456789", S.DELIVERED))
        self.assertIn("Недостаточно прав", self.errors[0])

    def test_unknown_parcel(self):
        self.login("operator1")
        self.assertFalse(self.ui.changeParcelStatus("BY404", S.SENT))
        self.assertEqual(self.errors, ["Посылка не найдена"])

    def test_courier_cannot_touch_foreign_parcel(self):
        self.login("courier2")
        self.assertFalse(self.ui.changeParcelStatus("BY123456789", S.DELIVERED))
        self.assertIn("не назначена вам", self.errors[0])

    def test_invalid_transition(self):
        self.login("operator1")
        self.assertFalse(self.ui.changeParcelStatus("BY421985673", S.REGISTERED))
        self.assertEqual(self.errors, ["Недопустимый статус"])

    def test_success_with_default_description_and_notification(self):
        self.login("operator1")
        client = self.env.userService.getUsersByRole(ROLE_CLIENT)[0]
        before = len(self.env.notificationService.getNotifications(client.id))
        self.assertTrue(self.ui.changeParcelStatus("BY123456789", S.DELAYED))
        parcel = self.env.parcelService.findParcel("BY123456789")
        self.assertEqual(parcel.status, S.DELAYED)
        self.assertEqual(parcel.records[-1].description, "Статус изменён: Глёза Е.Д.")
        self.assertEqual(len(self.env.notificationService.getNotifications(client.id)), before + 1)


class NewParcelTests(UITestCase):
    VALID = {"sender": "Сидоров П.П.", "sender_phone": "+375 29 111-22-33",
             "recipient": "Иванов И.А.", "recipient_phone": "+375 29 999-88-77",
             "address": "г. Гродно, ул. Ленина, 1"}

    def setUp(self):
        super().setUp()
        self.login("operator1")
        self.ui.openNewParcel()

    def fill(self, **override):
        values = dict(self.VALID, **override)
        for key, value in values.items():
            self.ui.formVars[key].set(value)

    def count(self):
        return len(self.env.parcelService.findAll())

    def test_form_defaults(self):
        self.assertEqual(self.ui.formVars["departure"].get(), date.today().isoformat())
        self.assertEqual(self.ui.formVars["sender_phone"].get(), "+375 29 ")
        self.assertEqual(len(find_entries(self.ui.content)), 7)

    def test_cancel_returns_to_list(self):
        click(self.button("Отмена"))
        self.assertEqual(self.ui.currentState, "openParcels")

    def test_register_success(self):
        before = self.count()
        self.fill()
        click(self.button("Сохранить"))
        self.assertEqual(self.count(), before + 1)
        parcel = self.env.parcelService.findAll()[-1]
        client = self.env.userService.getUsersByRole(ROLE_CLIENT)[0]
        self.assertEqual(parcel.route, "Минск-Гродно")
        self.assertEqual(parcel.clientId, client.id)
        self.assertEqual(parcel.status, S.REGISTERED)
        self.assertEqual(len(parcel.records), 1)
        self.assertIn(self.env.userService.findById(parcel.courierId).role, (ROLE_COURIER,))
        self.assertIn(parcel.number, self.infos[0])
        self.assertEqual(self.ui.currentState, "openParcels")
        self.assertEqual(len(self.env.notificationService.getNotifications(client.id)), 5)

    def test_unknown_recipient_has_no_client(self):
        self.fill(recipient="Неизвестный Н.Н.")
        self.ui.registerParcel()
        self.assertEqual(self.env.parcelService.findAll()[-1].clientId, 0)

    def test_required_fields(self):
        for key, label in (("sender", "ФИО отправителя"), ("recipient", "ФИО получателя"),
                           ("address", "Адрес доставки")):
            with self.subTest(field=key):
                self.errors.clear()
                before = self.count()
                self.fill(**{key: "   "})
                self.ui.registerParcel()
                self.assertIn(label, self.errors[0])
                self.assertEqual(self.count(), before)
                self.assertEqual(self.ui.currentState, "openNewParcel")

    def test_phone_validation(self):
        for key in ("sender_phone", "recipient_phone"):
            with self.subTest(field=key):
                self.errors.clear()
                self.fill(**{key: "abc"})
                self.ui.registerParcel()
                self.assertIn("Некорректное значение", self.errors[0])

    def test_date_validation(self):
        self.fill()
        self.ui.formVars["departure"].set("вчера")
        self.ui.registerParcel()
        self.assertIn("Дата должна быть", self.errors[0])

    def test_estimated_before_departure_rejected_by_service(self):
        self.fill()
        self.ui.formVars["departure"].set("2026-05-10")
        self.ui.formVars["estimated"].set("10.05.2025")
        before = self.count()
        self.ui.registerParcel()
        self.assertIn("раньше", self.errors[0])
        self.assertEqual(self.count(), before)


class TrackingTests(UITestCase):
    def setUp(self):
        super().setUp()
        self.login("operator1")
        self.ui.openTracking()

    def search(self, number):
        self.ui.trackVar.set(number)
        click(self.button("Найти"))

    def dots(self):
        return find_labels(self.ui.trackResult, "●")

    def test_found_parcel_shows_info_and_timeline(self):
        self.search("BY123456789")
        texts = label_texts(self.ui.trackResult)
        self.assertIn("BY123456789", texts)
        self.assertIn("В пути", texts)
        self.assertIn("Минск-Брест", texts)
        dots = self.dots()
        self.assertEqual(len(dots), 6)  # 4 пройденных этапа + 2 предстоящих
        self.assertEqual(sum(d.options["fg"] == ui_blue() for d in dots), 4)

    def test_lowercase_number_is_normalised(self):
        self.search(" by123456789 ")
        self.assertIn("BY123456789", label_texts(self.ui.trackResult))

    def test_delivered_parcel_has_no_future_steps(self):
        self.search("BY987654321")
        self.assertEqual(len(self.dots()), 6)
        self.assertTrue(all(d.options["fg"] == ui_blue() for d in self.dots()))

    def test_delayed_parcel_timeline(self):
        self.search("BY321987654")
        self.assertEqual(len(self.dots()), 7)  # 5 записей + «Прибыла» и «Вручена»

    def test_parcel_without_history_shows_full_plan(self):
        parcel = self.env.parcelService.registerParcel(make_parcel())
        self.search(parcel.number)
        dots = self.dots()
        self.assertEqual(len(dots), 6)
        self.assertTrue(all(d.options["fg"] != ui_blue() for d in dots))

    def test_empty_number(self):
        self.search("   ")
        self.assertEqual(self.errors, ["Введите номер отправления"])

    def test_unknown_number(self):
        self.search("by000")
        self.assertEqual(self.errors, ["Посылка с номером BY000 не найдена"])

    def test_enter_key_starts_search(self):
        self.ui.trackVar.set("BY123456789")
        find_entries(self.ui.content)[0].bindings["<Return>"](None)
        self.assertIn("BY123456789", label_texts(self.ui.trackResult))

    def test_track_from_other_screen_switches_to_tracking(self):
        self.ui.openMain()
        self.ui.trackParcel("BY123456789")
        self.assertEqual(self.ui.currentState, "openTracking")
        self.assertIn("Информация о посылке", label_texts(self.ui.trackResult))

    def test_open_tracking_with_prefill(self):
        self.ui.openTracking("BY987654321")
        self.assertEqual(self.ui.trackVar.get(), "BY987654321")
        self.assertIn("Вручена получателю", label_texts(self.ui.trackResult))

    def test_blocked_user_has_no_rights(self):
        operator = self.ui.currentUser
        self.env.userService.manageUser(operator.id, "deactivate")
        self.ui.trackParcel("BY123456789")
        self.assertIn("Недостаточно прав", self.errors[0])

    def test_per_parcel_extension_buttons(self):
        launcher, other = mock.Mock(), mock.Mock()
        self.ui.registerExtension("Карта", [ROLE_OPERATOR], launcher, perParcel=True)
        self.ui.registerExtension("Аналитика", [ROLE_OPERATOR], other, perParcel=False)
        self.ui.registerExtension("Чужое", [ROLE_ADMIN], other, perParcel=True)
        self.search("BY123456789")
        self.assertEqual(len(find_buttons(self.ui.trackResult)), 1)
        click(find_buttons(self.ui.trackResult, "Карта")[0])
        launcher.assert_called_once_with(self.ui.currentUser, "BY123456789")
        other.assert_not_called()


def ui_blue():
    from parcelflow.ui import BLUE
    return BLUE


class CouriersTests(UITestCase):
    def setUp(self):
        super().setUp()
        self.login("operator1")
        self.ui.openCouriers()

    def active_of(self, courier):
        return [p for p in self.env.parcelService.findByCourier(courier.id) if p.status not in FINAL_STATUSES]

    def test_table_and_stats(self):
        couriers = self.env.userService.getUsersByRole(ROLE_COURIER)
        self.assertEqual(len(self.tree().get_children()), len(couriers))
        busy = sum(1 for c in couriers if self.active_of(c))
        texts = label_texts(self.ui.content)
        self.assertIn(str(len(couriers)), texts)
        self.assertIn(str(busy), texts)
        courier1 = couriers[0]
        values = self.tree().items[str(courier1.id)]["values"]
        self.assertEqual(values[2], len(self.active_of(courier1)))
        self.assertEqual(values[3], "На маршруте")

    def test_details_requires_selection(self):
        click(self.button("Подробнее"))
        self.assertEqual(self.errors, ["Выберите строку в таблице"])

    def test_details_lists_active_parcels(self):
        courier1 = self.env.userService.getUsersByRole(ROLE_COURIER)[0]
        self.select(self.tree(), str(courier1.id))
        click(self.button("Подробнее"))
        self.assertIn("BY123456789 — г. Брест, ул. Московская, 12", self.infos[0])

    def test_add_courier_and_details_for_idle_courier(self):
        fake_tk.state.dialog_handler = answer(name="Новый К.К.", phone="+375 29 5",
                                              login="courier9", password="pw1234")
        click(self.button("Добавить курьера"))
        couriers = self.env.userService.getUsersByRole(ROLE_COURIER)
        self.assertEqual(len(couriers), 5)
        self.assertEqual(len(self.tree().get_children()), 5)
        new = couriers[-1]
        self.assertEqual(self.tree().items[str(new.id)]["values"][3], "Свободен")
        self.select(self.tree(), str(new.id))
        click(self.button("Подробнее"))
        self.assertTrue(self.infos[0].endswith("нет"))

    def test_add_courier_duplicate_login(self):
        fake_tk.state.dialog_handler = answer(name="Ещё Е.Е.", phone="", login="courier1", password="pw1234")
        click(self.button("Добавить курьера"))
        self.assertIn("уже существует", self.errors[0])
        self.assertEqual(len(self.env.userService.getUsersByRole(ROLE_COURIER)), 4)

    def test_add_courier_cancel(self):
        fake_tk.state.dialog_handler = cancel
        click(self.button("Добавить курьера"))
        self.assertEqual(len(self.env.userService.getUsersByRole(ROLE_COURIER)), 4)

    def test_admin_cannot_add_couriers(self):
        self.ui.showLogin()
        self.login("admin")
        self.ui.openCouriers()
        self.assertFalse(self.has_button("Добавить курьера"))


class FixedDate(date):
    @classmethod
    def today(cls):
        return cls(2027, 2, 10)


class ReportsTests(UITestCase):
    def setUp(self):
        super().setUp()
        self.login("operator1")

    def canvas(self):
        return [w for w in fake_tk.walk(self.ui.content) if isinstance(w, fake_tk.Canvas)][0]

    def test_statistics_cards(self):
        self.ui.openReports()
        parcels = self.env.parcelService.findAll()
        delivered = sum(p.status == S.DELIVERED for p in parcels)
        delayed = sum(p.status == S.DELAYED for p in parcels)
        texts = label_texts(self.ui.content)
        self.assertIn(str(delivered), texts)
        self.assertIn(str(delayed), texts)
        self.assertTrue(any(t.endswith(" дня") and "," in t for t in texts))

    def test_chart_is_drawn_on_configure(self):
        self.ui.openReports()
        canvas = self.canvas()
        canvas.bindings["<Configure>"]()
        self.assertEqual(len(canvas.rects), 6)
        self.assertEqual(len(canvas.texts), 12)
        counts = [int(kw["text"]) for _, kw in canvas.texts[0::2]]  # подписи над столбцами
        delivered_recently = sum(
            r.status == S.DELIVERED and (r.timestamp.year, r.timestamp.month) in
            {(date.today().year - (date.today().month - i <= 0), (date.today().month - i - 1) % 12 + 1)
             for i in range(6)}
            for p in self.env.parcelService.findAll() for r in p.records)
        self.assertEqual(sum(counts), delivered_recently)
        self.assertGreater(sum(counts), 0)

    def test_months_wrap_over_new_year(self):
        with mock.patch("parcelflow.ui.date", FixedDate):
            self.ui.openReports()
        canvas = self.canvas()
        canvas.bindings["<Configure>"]()
        labels = [kw["text"] for _, kw in canvas.texts[1::2]]
        self.assertEqual(labels, ["Сен", "Окт", "Ноя", "Дек", "Янв", "Фев"])

    def test_delivered_parcel_without_delivery_record_is_skipped(self):
        parcel = self.env.parcelService.registerParcel(make_parcel())
        self.env.parcelService.updateParcelStatus(parcel.number, S.DELIVERED)
        self.ui.openReports()
        self.assertIn("Доставлено за период", label_texts(self.ui.content))

    def test_export_writes_csv(self):
        self.ui.openReports()
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "report.csv")
            fake_tk.state.save_path = path
            click(self.button("Экспорт"))
            with open(path, encoding="utf-8-sig", newline="") as f:
                rows = list(csv.reader(f, delimiter=";"))
        parcels = self.env.parcelService.findAll()
        self.assertEqual(len(rows), len(parcels) + 1)
        self.assertEqual(rows[0][0], "Номер")
        self.assertEqual(rows[1][0], parcels[0].number)
        self.assertIn("Отчёт сохранён", self.infos[0])

    def test_export_cancelled(self):
        self.ui.openReports()
        fake_tk.state.save_path = ""
        click(self.button("Экспорт"))
        self.assertEqual(self.infos, [])


class EmptyReportsTests(UITestCase):
    seed = False

    def test_no_data(self):
        self.env.userService.createUser(ROLE_OPERATOR, "Оп", "", "op", "op")
        self.login("op")
        self.ui.openReports()
        self.assertIn("—", label_texts(self.ui.content))
        canvas = [w for w in fake_tk.walk(self.ui.content) if isinstance(w, fake_tk.Canvas)][0]
        canvas.bindings["<Configure>"]()
        self.assertEqual(len(canvas.rects), 6)


class AdminSettingsTests(UITestCase):
    def setUp(self):
        super().setUp()
        self.login("admin")  # стартовый экран администратора — «Настройки»
        self.admin = self.ui.currentUser

    def user(self, login):
        return self.env.userRepo.findByLogin(login)

    def test_lists_all_users(self):
        tree = self.tree()
        self.assertEqual(len(tree.get_children()), 7)
        self.assertEqual(tree.items[str(self.admin.id)]["values"], ("Кузьмич Д.С.", "admin", ROLE_ADMIN, "Активен"))

    def test_search_and_role_filters(self):
        search = find_entries(self.ui.content)[0].options["textvariable"]
        role = find_combos(self.ui.content)[0].options["textvariable"]
        search.set("cour")
        self.assertEqual(len(self.tree().get_children()), 4)
        role.set(ROLE_CLIENT)
        self.assertEqual(len(self.tree().get_children()), 0)
        search.set("")
        self.assertEqual(len(self.tree().get_children()), 1)
        role.set("Все роли")
        self.assertEqual(len(self.tree().get_children()), 7)

    def test_blocked_user_marked(self):
        self.env.userService.manageUser(self.user("client1").id, "deactivate")
        self.ui.openSettings()
        self.assertEqual(self.tree().items[str(self.user("client1").id)]["values"][3], "Заблокирован")

    def test_add_user(self):
        fake_tk.state.dialog_handler = answer(name="Новый О.О.", login="op2", password="pass1",
                                              phone="+375", role=ROLE_OPERATOR)
        click(self.button("Добавить пользователя"))
        self.assertEqual(self.user("op2").role, ROLE_OPERATOR)
        self.assertEqual(len(self.tree().get_children()), 8)

    def test_add_user_validation_error(self):
        fake_tk.state.dialog_handler = answer(name="", login="x", password="p", phone="", role=ROLE_CLIENT)
        click(self.button("Добавить пользователя"))
        self.assertIn("Заполните", self.errors[0])
        self.assertEqual(len(self.tree().get_children()), 7)

    def test_add_user_cancel(self):
        fake_tk.state.dialog_handler = cancel
        click(self.button("Добавить пользователя"))
        self.assertEqual(len(self.env.userService.getUsers()), 7)

    def test_rights_requires_selection(self):
        click(self.button("Изменить права →"))
        self.assertEqual(self.errors, ["Выберите строку в таблице"])

    def test_rights_change_role_status_and_password(self):
        client = self.user("client1")
        self.select(self.tree(), str(client.id))
        fake_tk.state.dialog_handler = answer(role=ROLE_COURIER, active="Заблокирован", password="newpass")
        click(self.button("Изменить права →"))
        changed = self.env.userService.findById(client.id)
        self.assertEqual(changed.role, ROLE_COURIER)
        self.assertFalse(changed.active)
        self.assertEqual(changed.password, UserService.hashPassword("newpass"))
        self.assertEqual(self.errors, [])

    def test_rights_unblock_keeps_role(self):
        client = self.user("client1")
        self.env.userService.manageUser(client.id, "deactivate")
        self.ui.openSettings()
        self.select(self.tree(), str(client.id))
        fake_tk.state.dialog_handler = answer(role=ROLE_CLIENT, active="Активен", password="")
        click(self.button("Изменить права →"))
        self.assertTrue(self.env.userService.findById(client.id).active)

    def test_rights_cannot_demote_or_block_self(self):
        self.select(self.tree(), str(self.admin.id))
        fake_tk.state.dialog_handler = answer(role=ROLE_OPERATOR, active="Активен", password="")
        click(self.button("Изменить права →"))
        self.assertIn("Нельзя изменить собственную роль", self.errors[0])
        self.assertEqual(self.env.userService.findById(self.admin.id).role, ROLE_ADMIN)

    def test_rights_short_password_reports_error(self):
        client = self.user("client1")
        self.select(self.tree(), str(client.id))
        fake_tk.state.dialog_handler = answer(role=ROLE_CLIENT, active="Активен", password="ab")
        click(self.button("Изменить права →"))
        self.assertIn("слишком короткий", self.errors[0])

    def test_rights_cancel(self):
        client = self.user("client1")
        self.select(self.tree(), str(client.id))
        fake_tk.state.dialog_handler = cancel
        click(self.button("Изменить права →"))
        self.assertEqual(self.env.userService.findById(client.id).role, ROLE_CLIENT)

    def test_delete_requires_selection(self):
        click(self.button("Удалить"))
        self.assertEqual(self.errors, ["Выберите строку в таблице"])
        self.assertEqual(len(self.env.userService.getUsers()), 7)

    def test_cannot_delete_self(self):
        self.select(self.tree(), str(self.admin.id))
        click(self.button("Удалить"))
        self.assertIn("собственную учётную запись", self.errors[0])
        self.assertEqual(len(self.env.userService.getUsers()), 7)

    def test_delete_confirmed_and_declined(self):
        client = self.user("client1")
        self.select(self.tree(), str(client.id))
        fake_tk.state.yesno = False
        click(self.button("Удалить"))
        self.assertEqual(len(self.env.userService.getUsers()), 7)
        fake_tk.state.yesno = True
        click(self.button("Удалить"))
        self.assertEqual(len(self.env.userService.getUsers()), 6)
        self.assertEqual(len(self.tree().get_children()), 6)


class ProfileTests(UITestCase):
    def test_operator_sees_profile(self):
        self.login("operator1")
        self.ui.openSettings()
        texts = label_texts(self.ui.content)
        for expected in ("Глёза Е.Д.", "operator1", ROLE_OPERATOR, "+375 29 000-00-01"):
            self.assertIn(expected, texts)
