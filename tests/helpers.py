"""Общие помощники: окружение с БД в памяти и быстрые конструкторы данных."""
from datetime import date, timedelta

from parcelflow.entities import Parcel
from parcelflow.repositories import Database, ParcelRepository, UserRepository
from parcelflow.seed import seedDatabase
from parcelflow.services import (NotificationService, ParcelService,
                                 TrackingService, UserService)


class Env:
    """Полный набор репозиториев и сервисов поверх SQLite в памяти."""

    def __init__(self, seed: bool = False):
        self.db = Database(":memory:")
        self.parcelRepo = ParcelRepository(self.db)
        self.userRepo = UserRepository(self.db)
        self.notificationService = NotificationService(self.parcelRepo, self.userRepo)
        self.parcelService = ParcelService(self.parcelRepo)
        self.trackingService = TrackingService(self.parcelRepo, self.notificationService)
        self.userService = UserService(self.userRepo)
        if seed:
            seedDatabase(self.userService, self.userRepo, self.parcelRepo)


def make_parcel(**kw) -> Parcel:
    today = date.today()
    data = dict(sender="Петров А.В.", recipient="Иванов И.А.",
                deliveryAddress="г. Брест, ул. Ленина, 1",
                departureDate=today, estimatedDeliveryDate=today + timedelta(days=2),
                route="Минск-Брест")
    data.update(kw)
    return Parcel(**data)
