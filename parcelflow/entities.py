"""Слой сущностей (<<data>>): BaseEntity, Parcel, TrackingRecord, Notification,
User и его наследники Client, Operator, Courier, Administrator."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import List, Optional


class ParcelStatus(Enum):
    """Статусы посылки (ЛР1 + экраны ЛР5: «Задержана», «Не вручена»)."""
    REGISTERED = "Зарегистрирована"
    ACCEPTED = "Принята на склад"
    SENT = "Отправлена"
    IN_TRANSIT = "В пути"
    ARRIVED = "Доставлена в пункт назначения"
    DELIVERED = "Вручена получателю"
    DELAYED = "Задержана"
    NOT_DELIVERED = "Не вручена"

    @property
    def phrase(self) -> str:
        """Фраза для текста уведомления: «Посылка BY... <фраза>»."""
        return {
            ParcelStatus.REGISTERED: "зарегистрирована",
            ParcelStatus.ACCEPTED: "принята на склад",
            ParcelStatus.SENT: "отправлена",
            ParcelStatus.IN_TRANSIT: "находится в пути",
            ParcelStatus.ARRIVED: "доставлена в пункт назначения",
            ParcelStatus.DELIVERED: "вручена получателю",
            ParcelStatus.DELAYED: "задержана",
            ParcelStatus.NOT_DELIVERED: "не вручена получателю",
        }[self]


# Последовательность основных этапов доставки
STATUS_FLOW = [
    ParcelStatus.REGISTERED,
    ParcelStatus.ACCEPTED,
    ParcelStatus.SENT,
    ParcelStatus.IN_TRANSIT,
    ParcelStatus.ARRIVED,
    ParcelStatus.DELIVERED,
]

ROLE_CLIENT = "Клиент"
ROLE_OPERATOR = "Оператор"
ROLE_COURIER = "Курьер"
ROLE_ADMIN = "Администратор"


@dataclass
class BaseEntity(ABC):
    """<<abstract>> BaseEntity — общий идентификатор id : Long."""
    id: int = 0

    @abstractmethod
    def entityName(self) -> str:
        ...


@dataclass
class TrackingRecord:
    """<<data>> TrackingRecord — запись истории перемещения."""
    id: int = 0
    status: ParcelStatus = ParcelStatus.REGISTERED
    timestamp: datetime = field(default_factory=datetime.now)
    description: str = ""


@dataclass
class Notification(BaseEntity):
    """<<data>> Notification — уведомление пользователю (композиция в User)."""
    message: str = ""
    sentAt: Optional[datetime] = None
    userId: int = 0
    parcelNumber: str = ""
    isRead: bool = False

    def entityName(self) -> str:
        return "Notification"


@dataclass
class Parcel(BaseEntity):
    """<<data>> Parcel — посылка. records — композиция с TrackingRecord (0..*).

    Дополнительные служебные поля (для экранов ЛР5): route, телефоны,
    clientId (получатель-клиент) и courierId (назначенный курьер)."""
    number: str = ""
    sender: str = ""
    recipient: str = ""
    deliveryAddress: str = ""
    departureDate: date = field(default_factory=date.today)
    estimatedDeliveryDate: date = field(default_factory=date.today)
    status: ParcelStatus = ParcelStatus.REGISTERED
    records: List[TrackingRecord] = field(default_factory=list)
    route: str = ""
    senderPhone: str = ""
    recipientPhone: str = ""
    clientId: int = 0
    courierId: int = 0

    def entityName(self) -> str:
        return "Parcel"


@dataclass
class User(BaseEntity):
    """<<abstract>> User — name, contactInfo (+ login/password для входа).
    notifications — композиция с Notification (0..*)."""
    name: str = ""
    contactInfo: str = ""
    login: str = ""
    password: str = ""
    active: bool = True
    notifications: List[Notification] = field(default_factory=list)

    @property
    @abstractmethod
    def role(self) -> str:
        ...

    def entityName(self) -> str:
        return "User"


@dataclass
class Client(User):
    @property
    def role(self) -> str:
        return ROLE_CLIENT

    def viewMyParcels(self, parcelService) -> list:
        """Клиент просматривает свои отправления."""
        return parcelService.findByClient(self.id)


@dataclass
class Operator(User):
    @property
    def role(self) -> str:
        return ROLE_OPERATOR

    def manageUsers(self, userService, userId: int, operation: str) -> bool:
        return userService.manageUser(userId, operation)


@dataclass
class Courier(User):
    @property
    def role(self) -> str:
        return ROLE_COURIER

    def markAsDelivered(self, parcelService, parcelNumber: str) -> None:
        """Курьер отмечает вручение посылки."""
        parcelService.updateParcelStatus(parcelNumber, ParcelStatus.DELIVERED)


@dataclass
class Administrator(User):
    @property
    def role(self) -> str:
        return ROLE_ADMIN

    def manageUsers(self, userService, userId: int, operation: str) -> bool:
        return userService.manageUser(userId, operation)


USER_CLASSES = {
    ROLE_CLIENT: Client,
    ROLE_OPERATOR: Operator,
    ROLE_COURIER: Courier,
    ROLE_ADMIN: Administrator,
}
