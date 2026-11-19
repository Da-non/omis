import hashlib
import re
import unittest
from datetime import date, timedelta
from unittest import mock

from parcelflow.entities import (ROLE_ADMIN, ROLE_CLIENT, ROLE_COURIER, ROLE_OPERATOR, Client,
                                 Courier, Operator, ParcelStatus as S)
from parcelflow.services import FINAL_STATUSES, PERMISSIONS, ParcelService, UserService

from .helpers import Env, make_parcel


class ParcelServiceTests(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.service = self.env.parcelService

    def test_register_assigns_number_and_status(self):
        parcel = self.service.registerParcel(make_parcel(status=S.DELIVERED))
        self.assertRegex(parcel.number, r"^BY\d{9}$")
        self.assertEqual(parcel.status, S.REGISTERED)
        self.assertEqual(self.service.findParcel(parcel.number).id, parcel.id)

    def test_register_validation_errors(self):
        cases = [
            (dict(sender="  "), "отправителе"),
            (dict(recipient=""), "получателе"),
            (dict(deliveryAddress=" "), "адрес"),
            (dict(departureDate=date(2026, 5, 10), estimatedDeliveryDate=date(2026, 5, 9)), "раньше"),
        ]
        for kwargs, fragment in cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError) as ctx:
                    self.service.registerParcel(make_parcel(**kwargs))
                self.assertIn(fragment, str(ctx.exception))
        self.assertEqual(self.service.findAll(), [])

    def test_same_day_delivery_is_allowed(self):
        today = date.today()
        parcel = self.service.registerParcel(make_parcel(departureDate=today, estimatedDeliveryDate=today))
        self.assertTrue(parcel.number)

    def test_generated_numbers_are_unique(self):
        numbers = {self.service.registerParcel(make_parcel()).number for _ in range(30)}
        self.assertEqual(len(numbers), 30)

    def test_generate_number_retries_on_collision(self):
        repo = mock.Mock()
        repo.findByNumber.side_effect = [make_parcel(), make_parcel(), None]
        number = ParcelService(repo)._generateNumber()
        self.assertTrue(re.fullmatch(r"BY\d{9}", number))
        self.assertEqual(repo.findByNumber.call_count, 3)

    def test_find_parcel_missing(self):
        self.assertIsNone(self.service.findParcel("BY000000000"))

    def test_update_status(self):
        parcel = self.service.registerParcel(make_parcel())
        self.service.updateParcelStatus(parcel.number, S.SENT)
        self.assertEqual(self.service.findParcel(parcel.number).status, S.SENT)

    def test_update_status_unknown_parcel(self):
        with self.assertRaises(ValueError):
            self.service.updateParcelStatus("BY404", S.SENT)

    def test_pending_and_final_statuses(self):
        a = self.service.registerParcel(make_parcel())
        b = self.service.registerParcel(make_parcel())
        c = self.service.registerParcel(make_parcel())
        self.service.updateParcelStatus(b.number, S.DELIVERED)
        self.service.updateParcelStatus(c.number, S.NOT_DELIVERED)
        pending = self.service.getPendingParcels()
        self.assertEqual([p.number for p in pending], [a.number])
        self.assertEqual(set(FINAL_STATUSES), {S.DELIVERED, S.NOT_DELIVERED})

    def test_find_by_client_and_courier(self):
        a = self.service.registerParcel(make_parcel(clientId=1, courierId=10))
        self.service.registerParcel(make_parcel(clientId=2, courierId=11))
        self.assertEqual([p.number for p in self.service.findByClient(1)], [a.number])
        self.assertEqual([p.number for p in self.service.findByCourier(10)], [a.number])
        self.assertEqual(self.service.findByClient(99), [])


class StatusTransitionTests(unittest.TestCase):
    allowed = staticmethod(ParcelService.isStatusAllowed)

    def test_same_status_not_allowed(self):
        for s in S:
            with self.subTest(status=s):
                self.assertFalse(self.allowed(s, s))

    def test_nothing_after_delivered(self):
        for s in S:
            self.assertFalse(self.allowed(S.DELIVERED, s))

    def test_delayed_from_anywhere_except_not_delivered(self):
        for cur in (S.REGISTERED, S.ACCEPTED, S.SENT, S.IN_TRANSIT, S.ARRIVED):
            self.assertTrue(self.allowed(cur, S.DELAYED))
        self.assertFalse(self.allowed(S.NOT_DELIVERED, S.DELAYED))

    def test_not_delivered_only_after_dispatch(self):
        for cur in (S.SENT, S.IN_TRANSIT, S.ARRIVED, S.DELAYED):
            self.assertTrue(self.allowed(cur, S.NOT_DELIVERED))
        for cur in (S.REGISTERED, S.ACCEPTED):
            self.assertFalse(self.allowed(cur, S.NOT_DELIVERED))

    def test_delivered_is_reachable(self):
        for cur in (S.REGISTERED, S.IN_TRANSIT, S.DELAYED, S.NOT_DELIVERED):
            self.assertTrue(self.allowed(cur, S.DELIVERED))

    def test_recovery_from_delayed_and_not_delivered(self):
        self.assertTrue(self.allowed(S.DELAYED, S.ACCEPTED))
        self.assertTrue(self.allowed(S.NOT_DELIVERED, S.IN_TRANSIT))

    def test_forward_ok_backward_not(self):
        self.assertTrue(self.allowed(S.REGISTERED, S.ACCEPTED))
        self.assertTrue(self.allowed(S.ACCEPTED, S.ARRIVED))  # можно пропустить этапы
        self.assertFalse(self.allowed(S.SENT, S.ACCEPTED))
        self.assertFalse(self.allowed(S.ARRIVED, S.REGISTERED))


class NotificationServiceTests(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.service = self.env.notificationService
        self.client = self.env.userService.createUser(ROLE_CLIENT, "Клиент", "", "cl", "pass")
        self.parcel = self.env.parcelService.registerParcel(make_parcel(clientId=self.client.id))

    def test_create_uses_clients_id(self):
        n = self.service.createNotification(self.parcel.number, "msg")
        self.assertEqual((n.userId, n.parcelNumber, n.message), (self.client.id, self.parcel.number, "msg"))

    def test_create_for_unknown_parcel_has_no_user(self):
        self.assertEqual(self.service.createNotification("BY404", "msg").userId, 0)

    def test_send_stores_for_user_and_sets_time(self):
        n = self.service.createNotification(self.parcel.number, "msg")
        self.service.sendNotification(n)
        self.assertIsNotNone(n.sentAt)
        self.assertEqual([x.message for x in self.service.getNotifications(self.client.id)], ["msg"])

    def test_send_without_user_is_not_stored(self):
        n = self.service.createNotification("BY404", "msg")
        self.service.sendNotification(n)
        self.assertIsNotNone(n.sentAt)
        self.assertEqual(self.service.getNotifications(0), [])

    def test_mark_all_read(self):
        self.service.sendNotification(self.service.createNotification(self.parcel.number, "m"))
        self.service.markAllRead(self.client.id)
        self.assertTrue(all(n.isRead for n in self.service.getNotifications(self.client.id)))


class TrackingServiceTests(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.service = self.env.trackingService
        self.client = self.env.userService.createUser(ROLE_CLIENT, "Клиент", "", "cl", "pass")
        self.parcel = self.env.parcelService.registerParcel(make_parcel(clientId=self.client.id))

    def test_current_status(self):
        self.assertEqual(self.service.getCurrentStatus(self.parcel.number), S.REGISTERED)

    def test_add_record_updates_status_history_and_notifies(self):
        rec = self.service.addTrackingRecord(self.parcel.number, S.SENT, "уехала")
        self.assertEqual(rec.description, "уехала")
        self.assertEqual(self.service.getCurrentStatus(self.parcel.number), S.SENT)
        history = self.service.getMovementHistory(self.parcel.number)
        self.assertEqual([r.status for r in history], [S.SENT])
        notes = self.env.notificationService.getNotifications(self.client.id)
        self.assertEqual(notes[0].message, f"Посылка {self.parcel.number} отправлена")

    def test_default_description_is_status_text(self):
        rec = self.service.addTrackingRecord(self.parcel.number, S.ACCEPTED)
        self.assertEqual(rec.description, S.ACCEPTED.value)

    def test_history_is_a_copy(self):
        self.service.addTrackingRecord(self.parcel.number, S.SENT)
        self.service.getMovementHistory(self.parcel.number).clear()
        self.assertEqual(len(self.service.getMovementHistory(self.parcel.number)), 1)

    def test_unknown_parcel_raises_everywhere(self):
        with self.assertRaises(ValueError):
            self.service.getCurrentStatus("BY404")
        with self.assertRaises(ValueError):
            self.service.getMovementHistory("BY404")
        with self.assertRaises(ValueError):
            self.service.addTrackingRecord("BY404", S.SENT)


class UserServiceTests(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.service = self.env.userService

    def _create(self, role=ROLE_CLIENT, login="user", name="Иванов И.А.", password="secret"):
        return self.service.createUser(role, name, "+375", login, password)

    # --- пароли и вход ---
    def test_hash_password_is_sha256(self):
        self.assertEqual(UserService.hashPassword("abc"), hashlib.sha256(b"abc").hexdigest())

    def test_authenticate_success_strips_login(self):
        created = self._create()
        user = self.service.authenticate("  user ", "secret")
        self.assertEqual(user.id, created.id)

    def test_authenticate_failures(self):
        user = self._create()
        self.assertIsNone(self.service.authenticate("user", "wrong"))
        self.assertIsNone(self.service.authenticate("ghost", "secret"))
        self.service.manageUser(user.id, "deactivate")
        self.assertIsNone(self.service.authenticate("user", "secret"))

    # --- права доступа ---
    def test_check_access(self):
        admin = self._create(ROLE_ADMIN, "adm")
        client = self._create(ROLE_CLIENT, "cl")
        self.assertTrue(self.service.checkAccess(admin.id, "manage_users"))
        self.assertFalse(self.service.checkAccess(client.id, "manage_users"))
        self.assertTrue(self.service.checkAccess(client.id, "view_notifications"))
        self.assertFalse(self.service.checkAccess(999, "manage_users"))

    def test_inactive_user_has_no_access(self):
        admin = self._create(ROLE_ADMIN, "adm")
        self.service.manageUser(admin.id, "deactivate")
        self.assertFalse(self.service.checkAccess(admin.id, "manage_users"))

    def test_permissions_table_covers_all_roles(self):
        self.assertEqual(set(PERMISSIONS), {ROLE_ADMIN, ROLE_OPERATOR, ROLE_COURIER, ROLE_CLIENT})
        self.assertIn("register_parcel", PERMISSIONS[ROLE_OPERATOR])
        self.assertNotIn("register_parcel", PERMISSIONS[ROLE_ADMIN])

    # --- manageUser ---
    def test_activate_deactivate(self):
        user = self._create()
        self.assertTrue(self.service.manageUser(user.id, "deactivate"))
        self.assertFalse(self.service.findById(user.id).active)
        self.assertTrue(self.service.manageUser(user.id, "activate"))
        self.assertTrue(self.service.findById(user.id).active)

    def test_delete(self):
        user = self._create()
        self.assertTrue(self.service.manageUser(user.id, "delete"))
        self.assertIsNone(self.service.findById(user.id))

    def test_change_role_changes_class_and_keeps_data(self):
        user = self._create(name="Смирнов П.Л.")
        self.service.manageUser(user.id, "role:" + ROLE_COURIER)
        changed = self.service.findById(user.id)
        self.assertIsInstance(changed, Courier)
        self.assertEqual((changed.name, changed.login), ("Смирнов П.Л.", "user"))

    def test_change_role_unknown(self):
        user = self._create()
        with self.assertRaises(ValueError):
            self.service.manageUser(user.id, "role:Президент")

    def test_change_password(self):
        user = self._create()
        self.service.manageUser(user.id, "password:newpass")
        self.assertIsNotNone(self.service.authenticate("user", "newpass"))
        self.assertIsNone(self.service.authenticate("user", "secret"))

    def test_password_too_short(self):
        user = self._create()
        with self.assertRaises(ValueError):
            self.service.manageUser(user.id, "password:ab")

    def test_unknown_operation_and_user(self):
        user = self._create()
        with self.assertRaises(ValueError):
            self.service.manageUser(user.id, "explode")
        with self.assertRaises(ValueError):
            self.service.manageUser(12345, "activate")

    # --- createUser ---
    def test_create_user_hashes_password_and_trims(self):
        user = self.service.createUser(ROLE_OPERATOR, "  Оператор ", " +375 ", " op ", "pwd")
        self.assertIsInstance(user, Operator)
        self.assertEqual((user.name, user.contactInfo, user.login), ("Оператор", "+375", "op"))
        self.assertEqual(user.password, UserService.hashPassword("pwd"))

    def test_create_user_errors(self):
        self._create(login="taken")
        cases = [
            (("Неизвестная", "A", "", "l", "p"), "роль"),
            ((ROLE_CLIENT, " ", "", "l", "p"), "Заполните"),
            ((ROLE_CLIENT, "A", "", " ", "p"), "Заполните"),
            ((ROLE_CLIENT, "A", "", "l", ""), "Заполните"),
            ((ROLE_CLIENT, "A", "", "taken", "p"), "уже существует"),
        ]
        for args, fragment in cases:
            with self.subTest(args=args):
                with self.assertRaises(ValueError) as ctx:
                    self.service.createUser(*args)
                self.assertIn(fragment, str(ctx.exception))

    # --- выборки ---
    def test_get_users_and_by_role(self):
        self._create(ROLE_CLIENT, "c1")
        self._create(ROLE_COURIER, "k1")
        self._create(ROLE_COURIER, "k2")
        self.assertEqual(len(self.service.getUsers()), 3)
        self.assertEqual(len(self.service.getUsersByRole(ROLE_COURIER)), 2)
        self.assertEqual(self.service.getUsersByRole(ROLE_ADMIN), [])

    # --- поиск клиента по ФИО ---
    def test_find_client_by_name(self):
        client = self._create(ROLE_CLIENT, "c1", "Иванов И.А.")
        self._create(ROLE_OPERATOR, "o1", "Петров П.П.")
        self.assertEqual(self.service.findClientByName("Иванов Иван Алексеевич").id, client.id)
        self.assertEqual(self.service.findClientByName("иванов и.а.").id, client.id)
        self.assertIsNone(self.service.findClientByName("Сидоров С.С."))
        self.assertIsNone(self.service.findClientByName("Петров П.П."))  # оператор — не клиент

    def test_same_name_rules(self):
        same = UserService._sameName
        self.assertTrue(same("Иванов И.А.", "Иванов Иван"))
        self.assertTrue(same("Иванов", "Иванов И."))
        self.assertTrue(same("Иванов И. А.", "иванов и а"))
        self.assertFalse(same("Иванов И.А.", "Иванов П.А."))
        self.assertFalse(same("Иванов И.А.", "Петров И.А."))
        self.assertFalse(same("", "Иванов"))
        self.assertFalse(same("Иванов", "   "))


if __name__ == "__main__":
    unittest.main()
