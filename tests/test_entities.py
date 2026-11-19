import unittest
from unittest import mock

from parcelflow.entities import (ROLE_ADMIN, ROLE_CLIENT, ROLE_COURIER, ROLE_OPERATOR,
                                 STATUS_FLOW, USER_CLASSES, Administrator, BaseEntity, Client,
                                 Courier, Notification, Operator, Parcel, ParcelStatus,
                                 TrackingRecord, User)


class ParcelStatusTests(unittest.TestCase):
    def test_every_status_has_phrase(self):
        for status in ParcelStatus:
            self.assertTrue(status.phrase)

    def test_specific_phrases(self):
        self.assertEqual(ParcelStatus.IN_TRANSIT.phrase, "находится в пути")
        self.assertEqual(ParcelStatus.NOT_DELIVERED.phrase, "не вручена получателю")

    def test_status_flow_order(self):
        self.assertEqual(STATUS_FLOW[0], ParcelStatus.REGISTERED)
        self.assertEqual(STATUS_FLOW[-1], ParcelStatus.DELIVERED)
        self.assertNotIn(ParcelStatus.DELAYED, STATUS_FLOW)


class DataEntitiesTests(unittest.TestCase):
    def test_tracking_record_defaults(self):
        rec = TrackingRecord()
        self.assertEqual(rec.id, 0)
        self.assertEqual(rec.status, ParcelStatus.REGISTERED)
        self.assertEqual(rec.description, "")
        self.assertIsNotNone(rec.timestamp)

    def test_parcel_defaults_and_entity_name(self):
        parcel = Parcel()
        self.assertEqual(parcel.entityName(), "Parcel")
        self.assertEqual(parcel.status, ParcelStatus.REGISTERED)
        self.assertEqual(parcel.records, [])

    def test_records_are_not_shared_between_parcels(self):
        a, b = Parcel(), Parcel()
        a.records.append(TrackingRecord())
        self.assertEqual(b.records, [])

    def test_notification_entity_name(self):
        n = Notification(message="hi")
        self.assertEqual(n.entityName(), "Notification")
        self.assertFalse(n.isRead)

    def test_abstract_base_cannot_be_instantiated(self):
        with self.assertRaises(TypeError):
            BaseEntity()
        with self.assertRaises(TypeError):
            User()

    def test_abstract_bodies_return_none(self):
        self.assertIsNone(BaseEntity.entityName(Parcel()))
        self.assertIsNone(User.role.fget(Client()))


class UserHierarchyTests(unittest.TestCase):
    def test_roles(self):
        self.assertEqual(Client().role, ROLE_CLIENT)
        self.assertEqual(Operator().role, ROLE_OPERATOR)
        self.assertEqual(Courier().role, ROLE_COURIER)
        self.assertEqual(Administrator().role, ROLE_ADMIN)

    def test_user_entity_name_and_defaults(self):
        user = Client(name="Аня")
        self.assertEqual(user.entityName(), "User")
        self.assertTrue(user.active)
        self.assertEqual(user.notifications, [])

    def test_user_classes_mapping(self):
        self.assertEqual(USER_CLASSES, {ROLE_CLIENT: Client, ROLE_OPERATOR: Operator,
                                        ROLE_COURIER: Courier, ROLE_ADMIN: Administrator})

    def test_client_views_own_parcels(self):
        service = mock.Mock()
        service.findByClient.return_value = ["p1"]
        self.assertEqual(Client(id=5).viewMyParcels(service), ["p1"])
        service.findByClient.assert_called_once_with(5)

    def test_operator_and_admin_manage_users(self):
        service = mock.Mock()
        service.manageUser.return_value = True
        self.assertTrue(Operator().manageUsers(service, 3, "activate"))
        self.assertTrue(Administrator().manageUsers(service, 4, "delete"))
        service.manageUser.assert_has_calls([mock.call(3, "activate"), mock.call(4, "delete")])

    def test_courier_marks_delivered(self):
        service = mock.Mock()
        Courier().markAsDelivered(service, "BY1")
        service.updateParcelStatus.assert_called_once_with("BY1", ParcelStatus.DELIVERED)


if __name__ == "__main__":
    unittest.main()
