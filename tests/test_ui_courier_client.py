"""Тесты UI: экраны курьера и клиента."""
from datetime import date

from parcelflow.entities import ROLE_CLIENT, ParcelStatus as S
from parcelflow.services import FINAL_STATUSES

from . import fake_tk
from .test_ui_core import UITestCase
from .ui_helpers import answer, cancel, click, find_entries, label_texts


class CourierParcelsTests(UITestCase):
    def setUp(self):
        super().setUp()
        self.login("courier1")
        self.courier = self.ui.currentUser

    def active(self):
        return [p for p in self.env.parcelService.findByCourier(self.courier.id)
                if p.status not in FINAL_STATUSES]

    def test_lists_only_active_parcels_of_this_courier(self):
        rows = set(self.tree().get_children())
        self.assertEqual(rows, {p.number for p in self.active()})
        self.assertIn("BY123456789", rows)
        self.assertNotIn("BY987654321", rows)  # чужая и уже вручена
        self.assertIn(str(len(self.active())), label_texts(self.ui.content))

    def test_address_filter(self):
        flt = find_entries(self.ui.content)[0].options["textvariable"]
        flt.set("МИНСК")
        expected = {p.number for p in self.active() if "минск" in p.deliveryAddress.lower()}
        self.assertEqual(set(self.tree().get_children()), expected)
        flt.set("")
        self.assertEqual(len(self.tree().get_children()), len(self.active()))

    def test_details_opens_tracking(self):
        self.select(self.tree(), "BY123456789")
        click(self.button("Подробнее"))
        self.assertEqual(self.ui.currentState, "openTracking")

    def test_deliver_requires_selection(self):
        click(self.button("Вручена получателю"))
        self.assertEqual(self.errors, ["Выберите строку в таблице"])

    def test_deliver_marks_parcel_and_notifies_client(self):
        client = self.env.userService.getUsersByRole(ROLE_CLIENT)[0]
        before = len(self.env.notificationService.getNotifications(client.id))
        self.select(self.tree(), "BY123456789")
        click(self.button("Вручена получателю"))
        parcel = self.env.parcelService.findParcel("BY123456789")
        self.assertEqual(parcel.status, S.DELIVERED)
        self.assertIn("Курьер: Смирнов П.Л.", parcel.records[-1].description)
        self.assertNotIn("BY123456789", self.tree().get_children())
        self.assertEqual(len(self.env.notificationService.getNotifications(client.id)), before + 1)
        self.assertIn("1", label_texts(self.ui.content))  # «Доставлено сегодня» вырос

    def test_refuse_with_reason(self):
        self.select(self.tree(), "BY123456789")
        fake_tk.state.dialog_handler = answer(reason="Адресат отказался")
        click(self.button("Не вручена (отказ)"))
        parcel = self.env.parcelService.findParcel("BY123456789")
        self.assertEqual(parcel.status, S.NOT_DELIVERED)
        self.assertEqual(parcel.records[-1].description, "Отказ/не вручено: Адресат отказался")

    def test_refuse_requires_selection(self):
        click(self.button("Не вручена (отказ)"))
        self.assertEqual(self.errors, ["Выберите строку в таблице"])

    def test_refuse_cancel(self):
        self.select(self.tree(), "BY123456789")
        fake_tk.state.dialog_handler = cancel
        click(self.button("Не вручена (отказ)"))
        self.assertEqual(self.env.parcelService.findParcel("BY123456789").status, S.IN_TRANSIT)

    def test_refuse_not_allowed_for_registered_parcel(self):
        self.select(self.tree(), "BY421985673")  # только зарегистрирована
        fake_tk.state.dialog_handler = answer(reason="тест")
        click(self.button("Не вручена (отказ)"))
        self.assertEqual(self.errors, ["Недопустимый статус"])
        self.assertEqual(self.env.parcelService.findParcel("BY421985673").status, S.REGISTERED)


class DeliveryHistoryTests(UITestCase):
    def test_shows_finished_deliveries_only(self):
        self.login("courier2")
        self.ui.openDeliveryHistory()
        rows = set(self.tree().get_children())
        self.assertTrue({"BY987654321", "BY123987654"} <= rows)
        for number in rows:
            self.assertIn(self.env.parcelService.findParcel(number).status, FINAL_STATUSES)
        values = self.tree().items["BY987654321"]["values"]
        self.assertEqual(values[3], S.DELIVERED.value)
        self.assertRegex(values[4], r"^\d{2}\.\d{2}\.\d{4}, \d{2}:\d{2}$")

    def test_courier_navigation_reaches_history(self):
        self.login("courier2")
        click(self.ui.navButtons["openDeliveryHistory"])
        self.assertEqual(self.ui.currentState, "openDeliveryHistory")


class ClientTests(UITestCase):
    def setUp(self):
        super().setUp()
        self.login("client1")

    def test_my_parcels(self):
        self.assertEqual(self.ui.currentState, "openMyParcels")
        self.assertEqual(len(self.tree().get_children()), 4)
        texts = label_texts(self.ui.content)
        self.assertIn("4", texts)   # всего
        self.assertIn("2", texts)   # в пути и доставлено
        values = self.tree().items["BY123456789"]["values"]
        self.assertEqual(values[1], "Минск-Брест")
        self.assertEqual(values[3], S.IN_TRANSIT.value)

    def test_details_arrow_opens_tracking(self):
        self.select(self.tree(), "BY123456789")
        click(self.button("Подробнее →"))
        self.assertEqual(self.ui.currentState, "openTracking")
        self.assertIn("BY123456789", label_texts(self.ui.trackResult))

    def test_details_requires_selection(self):
        click(self.button("Подробнее →"))
        self.assertEqual(self.errors, ["Выберите строку в таблице"])

    def test_notifications_list(self):
        self.ui.openNotifications()
        tree = self.tree()
        self.assertEqual(len(tree.get_children()), 4)
        self.assertIn("Новых уведомлений: 2", label_texts(self.ui.content))
        marks = sorted(v["values"][0] for v in tree.items.values())
        self.assertEqual(marks, ["", "", "●", "●"])

    def test_open_notification_goes_to_tracking(self):
        self.ui.openNotifications()
        first = self.tree().get_children()[0]
        self.select(self.tree(), first)
        click(self.button("Открыть →"))
        self.assertEqual(self.ui.currentState, "openTracking")

    def test_open_notification_requires_selection(self):
        self.ui.openNotifications()
        click(self.button("Открыть →"))
        self.assertEqual(self.errors, ["Выберите строку в таблице"])

    def test_mark_all_read(self):
        self.ui.openNotifications()
        click(self.button("Отметить все прочитанными"))
        self.assertIn("Новых уведомлений: 0", label_texts(self.ui.content))
        self.assertTrue(all(n.isRead for n in
                            self.env.notificationService.getNotifications(self.ui.currentUser.id)))

    def test_client_menu_navigation(self):
        click(self.ui.navButtons["openNotifications"])
        self.assertEqual(self.ui.currentState, "openNotifications")
        click(self.ui.navButtons["openTracking"])
        self.assertEqual(self.ui.currentState, "openTracking")
        click(self.ui.navButtons["logout"])
        self.assertEqual(self.ui.currentState, "login")
