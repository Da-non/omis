import unittest
from datetime import date, datetime, timedelta

from parcelflow.entities import (ROLE_ADMIN, ROLE_CLIENT, ROLE_COURIER, ROLE_OPERATOR,
                                 USER_CLASSES, Client, Notification, ParcelStatus, TrackingRecord)
from parcelflow.repositories import Database, ParcelRepository, UserRepository

from .helpers import make_parcel


class DatabaseTests(unittest.TestCase):
    def test_is_empty_until_user_added(self):
        db = Database(":memory:")
        self.assertTrue(db.isEmpty())
        UserRepository(db).save(Client(name="A", login="a", password="x"))
        self.assertFalse(db.isEmpty())

    def test_default_path_is_memory(self):
        self.assertTrue(Database().isEmpty())


class ParcelRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.repo = ParcelRepository(self.db)

    def test_save_assigns_id_and_roundtrips(self):
        parcel = make_parcel(number="BY1", senderPhone="+375 1", recipientPhone="+375 2",
                             clientId=4, courierId=6, status=ParcelStatus.SENT)
        self.repo.save(parcel)
        self.assertGreater(parcel.id, 0)
        loaded = self.repo.findByNumber("BY1")
        self.assertEqual(loaded.id, parcel.id)
        self.assertEqual(loaded.sender, parcel.sender)
        self.assertEqual(loaded.senderPhone, "+375 1")
        self.assertEqual(loaded.recipientPhone, "+375 2")
        self.assertEqual(loaded.clientId, 4)
        self.assertEqual(loaded.courierId, 6)
        self.assertEqual(loaded.status, ParcelStatus.SENT)
        self.assertEqual(loaded.departureDate, parcel.departureDate)
        self.assertEqual(loaded.estimatedDeliveryDate, parcel.estimatedDeliveryDate)

    def test_find_missing_returns_none(self):
        self.assertIsNone(self.repo.findByNumber("NOPE"))

    def test_records_saved_with_parcel(self):
        ts = datetime(2026, 1, 2, 3, 4, 5)
        parcel = make_parcel(number="BY2", records=[
            TrackingRecord(status=ParcelStatus.REGISTERED, timestamp=ts, description="a"),
            TrackingRecord(status=ParcelStatus.ACCEPTED, timestamp=ts + timedelta(hours=1))])
        self.repo.save(parcel)
        self.assertTrue(all(r.id > 0 for r in parcel.records))
        loaded = self.repo.findByNumber("BY2")
        self.assertEqual([r.status for r in loaded.records],
                         [ParcelStatus.REGISTERED, ParcelStatus.ACCEPTED])
        self.assertEqual(loaded.records[0].timestamp, ts)
        self.assertEqual(loaded.records[0].description, "a")

    def test_update_changes_fields_and_adds_only_new_records(self):
        parcel = make_parcel(number="BY3", records=[TrackingRecord(description="first")])
        self.repo.save(parcel)
        parcel.status = ParcelStatus.DELAYED
        parcel.courierId = 9
        parcel.records.append(TrackingRecord(status=ParcelStatus.DELAYED, description="late"))
        self.repo.update(parcel)
        self.repo.update(parcel)  # повторное сохранение не дублирует историю
        loaded = self.repo.findByNumber("BY3")
        self.assertEqual(loaded.status, ParcelStatus.DELAYED)
        self.assertEqual(loaded.courierId, 9)
        self.assertEqual(len(loaded.records), 2)

    def test_find_all_ordered_by_id(self):
        for n in ("BY10", "BY11", "BY12"):
            self.repo.save(make_parcel(number=n))
        self.assertEqual([p.number for p in self.repo.findAll()], ["BY10", "BY11", "BY12"])

    def test_null_columns_become_defaults(self):
        self.db.conn.execute(
            "INSERT INTO parcels(number,departure,estimated,status) VALUES(?,?,?,?)",
            ("BYNULL", "2026-01-01", "2026-01-03", "REGISTERED"))
        loaded = self.repo.findByNumber("BYNULL")
        self.assertEqual(loaded.sender, "")
        self.assertEqual(loaded.senderPhone, "")
        self.assertEqual(loaded.recipient, "")
        self.assertEqual(loaded.deliveryAddress, "")
        self.assertEqual(loaded.route, "")
        self.assertEqual(loaded.clientId, 0)
        self.assertEqual(loaded.courierId, 0)
        self.assertEqual(loaded.departureDate, date(2026, 1, 1))

    def test_record_with_null_description(self):
        parcel = make_parcel(number="BY4")
        self.repo.save(parcel)
        self.db.conn.execute("INSERT INTO tracking(parcel_id,status,ts,description) VALUES(?,?,?,NULL)",
                             (parcel.id, "SENT", "2026-01-01T10:00:00"))
        self.assertEqual(self.repo.findByNumber("BY4").records[0].description, "")


class UserRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.repo = UserRepository(self.db)

    def _user(self, login="u1", role_cls=Client, **kw):
        user = role_cls(name=kw.pop("name", "Имя"), contactInfo="+375", login=login, password="h", **kw)
        self.repo.save(user)
        return user

    def test_save_find_by_id_and_login(self):
        user = self._user()
        self.assertGreater(user.id, 0)
        by_id = self.repo.findById(user.id)
        by_login = self.repo.findByLogin("u1")
        self.assertEqual(by_id.login, "u1")
        self.assertEqual(by_login.id, user.id)
        self.assertEqual(by_id.contactInfo, "+375")
        self.assertTrue(by_id.active)

    def test_missing_user_returns_none(self):
        self.assertIsNone(self.repo.findById(404))
        self.assertIsNone(self.repo.findByLogin("ghost"))

    def test_roundtrip_keeps_concrete_class(self):
        for i, (role, cls) in enumerate(USER_CLASSES.items()):
            saved = self._user(login=f"l{i}", role_cls=cls)
            loaded = self.repo.findById(saved.id)
            self.assertIsInstance(loaded, cls)
            self.assertEqual(loaded.role, role)

    def test_update(self):
        user = self._user()
        user.name, user.active, user.password = "Новое", False, "h2"
        self.repo.update(user)
        loaded = self.repo.findById(user.id)
        self.assertEqual((loaded.name, loaded.active, loaded.password), ("Новое", False, "h2"))

    def test_find_all_has_no_notifications_loaded(self):
        user = self._user()
        self.repo.addNotification(user.id, Notification(message="m"))
        users = self.repo.findAll()
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0].notifications, [])
        self.assertEqual(len(self.repo.findById(user.id).notifications), 1)

    def test_notifications_add_find_and_order(self):
        user = self._user()
        early = Notification(message="old", parcelNumber="BY1", sentAt=datetime(2026, 1, 1))
        late = Notification(message="new", parcelNumber="BY2", sentAt=datetime(2026, 2, 1), isRead=True)
        self.repo.addNotification(user.id, early)
        self.repo.addNotification(user.id, late)
        self.assertGreater(early.id, 0)
        self.assertEqual(late.userId, user.id)
        found = self.repo.findNotifications(user.id)
        self.assertEqual([n.message for n in found], ["new", "old"])
        self.assertTrue(found[0].isRead)
        self.assertFalse(found[1].isRead)
        self.assertEqual(found[1].parcelNumber, "BY1")

    def test_notification_without_sent_at_gets_now(self):
        user = self._user()
        self.repo.addNotification(user.id, Notification(message="x"))
        self.assertIsInstance(self.repo.findNotifications(user.id)[0].sentAt, datetime)

    def test_mark_all_read_only_for_user(self):
        a, b = self._user("a"), self._user("b")
        self.repo.addNotification(a.id, Notification(message="1"))
        self.repo.addNotification(b.id, Notification(message="2"))
        self.repo.markAllRead(a.id)
        self.assertTrue(all(n.isRead for n in self.repo.findNotifications(a.id)))
        self.assertFalse(any(n.isRead for n in self.repo.findNotifications(b.id)))

    def test_delete_removes_user_and_notifications(self):
        user = self._user()
        self.repo.addNotification(user.id, Notification(message="1"))
        self.repo.delete(user.id)
        self.assertIsNone(self.repo.findById(user.id))
        self.assertEqual(self.repo.findNotifications(user.id), [])

    def test_roles_constants_are_known(self):
        self.assertEqual({ROLE_ADMIN, ROLE_OPERATOR, ROLE_COURIER, ROLE_CLIENT}, set(USER_CLASSES))


if __name__ == "__main__":
    unittest.main()
