import unittest
from datetime import datetime, timedelta

from parcelflow.entities import ROLE_ADMIN, ROLE_CLIENT, ROLE_COURIER, ROLE_OPERATOR, ParcelStatus as S
from parcelflow.seed import OFFSET_H, _records

from .helpers import Env


class RecordsTests(unittest.TestCase):
    dep = datetime(2026, 1, 1, 8, 0)

    def test_regular_status_follows_flow(self):
        recs = _records(self.dep, S.IN_TRANSIT)
        self.assertEqual([r.status for r in recs],
                         [S.REGISTERED, S.ACCEPTED, S.SENT, S.IN_TRANSIT])
        self.assertEqual(recs[1].timestamp, self.dep + timedelta(hours=OFFSET_H[S.ACCEPTED]))

    def test_delayed_and_not_delivered_end_with_that_status(self):
        for status in (S.DELAYED, S.NOT_DELIVERED):
            with self.subTest(status=status):
                recs = _records(self.dep, status)
                self.assertEqual(len(recs), 5)
                self.assertEqual(recs[-1].status, status)

    def test_scale_stretches_time(self):
        recs = _records(self.dep, S.DELIVERED, scale=2.0)
        self.assertEqual(recs[-1].timestamp, self.dep + timedelta(hours=100))

    def test_timestamps_never_in_the_future(self):
        recs = _records(datetime.now(), S.DELIVERED)
        self.assertTrue(all(r.timestamp <= datetime.now() for r in recs))


class SeedDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = Env(seed=True)

    def test_users_created(self):
        users = self.env.userService.getUsers()
        self.assertEqual(len(users), 7)
        self.assertEqual(len(self.env.userService.getUsersByRole(ROLE_COURIER)), 4)
        for role in (ROLE_ADMIN, ROLE_OPERATOR, ROLE_CLIENT):
            self.assertEqual(len(self.env.userService.getUsersByRole(role)), 1)

    def test_demo_logins_work(self):
        for login in ("admin", "operator1", "courier1", "client1"):
            with self.subTest(login=login):
                self.assertIsNotNone(self.env.userService.authenticate(login, login))

    def test_parcels_created_and_unique(self):
        parcels = self.env.parcelService.findAll()
        self.assertEqual(len(parcels), 6 + 110)
        self.assertEqual(len({p.number for p in parcels}), len(parcels))

    def test_demo_parcels_have_expected_status(self):
        service = self.env.parcelService
        self.assertEqual(service.findParcel("BY123456789").status, S.IN_TRANSIT)
        self.assertEqual(service.findParcel("BY987654321").status, S.DELIVERED)
        self.assertEqual(service.findParcel("BY321987654").status, S.DELAYED)
        self.assertEqual(service.findParcel("BY421985673").status, S.REGISTERED)

    def test_client_has_parcels_and_notifications(self):
        client = self.env.userService.authenticate("client1", "client1")
        self.assertEqual(len(self.env.parcelService.findByClient(client.id)), 4)
        notes = self.env.notificationService.getNotifications(client.id)
        self.assertEqual(len(notes), 4)
        self.assertEqual(sum(n.isRead for n in notes), 2)

    def test_every_parcel_has_history_and_courier(self):
        for p in self.env.parcelService.findAll():
            self.assertTrue(p.records, p.number)
            self.assertGreater(p.courierId, 0)


if __name__ == "__main__":
    unittest.main()
