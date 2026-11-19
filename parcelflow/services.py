"""Слой бизнес-логики: ParcelService, TrackingService, UserService, NotificationService."""
from __future__ import annotations

import hashlib
import random
from datetime import datetime
from typing import List, Optional

from .entities import (ROLE_ADMIN, ROLE_CLIENT, ROLE_COURIER, ROLE_OPERATOR,
                       STATUS_FLOW, USER_CLASSES, Notification, Parcel,
                       ParcelStatus, TrackingRecord, User)
from .repositories import ParcelRepository, UserRepository

FINAL_STATUSES = (ParcelStatus.DELIVERED, ParcelStatus.NOT_DELIVERED)


class ParcelService:
    """Подсистема управления посылками (создание, изменение, поиск)."""

    def __init__(self, parcelRepository: ParcelRepository):
        self.parcelRepository = parcelRepository

    def registerParcel(self, parcel: Parcel) -> Parcel:
        """Проверяет данные, присваивает уникальный номер и статус «Зарегистрирована»."""
        if not parcel.sender.strip():
            raise ValueError("Не указана информация об отправителе")
        if not parcel.recipient.strip():
            raise ValueError("Не указана информация о получателе")
        if not parcel.deliveryAddress.strip():
            raise ValueError("Не указан адрес доставки")
        if parcel.estimatedDeliveryDate < parcel.departureDate:
            raise ValueError("Предполагаемая дата доставки раньше даты отправления")
        parcel.number = self._generateNumber()
        parcel.status = ParcelStatus.REGISTERED
        self.parcelRepository.save(parcel)
        return parcel

    def findParcel(self, parcelNumber: str) -> Optional[Parcel]:
        return self.parcelRepository.findByNumber(parcelNumber)

    def updateParcelStatus(self, parcelNumber: str, status: ParcelStatus) -> None:
        parcel = self.parcelRepository.findByNumber(parcelNumber)
        if parcel is None:
            raise ValueError(f"Посылка {parcelNumber} не найдена")
        parcel.status = status
        self.parcelRepository.update(parcel)

    # ---- вспомогательные операции ----
    @staticmethod
    def isStatusAllowed(current: ParcelStatus, new: ParcelStatus) -> bool:
        """Допустимость перехода между статусами (isStatusAllowed из sequence-диаграммы)."""
        if new == current or current == ParcelStatus.DELIVERED:
            return False
        if new == ParcelStatus.DELAYED:
            return current != ParcelStatus.NOT_DELIVERED
        if new == ParcelStatus.NOT_DELIVERED:
            return current in (ParcelStatus.SENT, ParcelStatus.IN_TRANSIT,
                               ParcelStatus.ARRIVED, ParcelStatus.DELAYED)
        if new == ParcelStatus.DELIVERED:
            return True
        if current in (ParcelStatus.DELAYED, ParcelStatus.NOT_DELIVERED):
            return True
        return STATUS_FLOW.index(new) > STATUS_FLOW.index(current)

    def findAll(self) -> List[Parcel]:
        return self.parcelRepository.findAll()

    def getPendingParcels(self) -> List[Parcel]:
        return [p for p in self.findAll() if p.status not in FINAL_STATUSES]

    def findByClient(self, clientId: int) -> List[Parcel]:
        return [p for p in self.findAll() if p.clientId == clientId]

    def findByCourier(self, courierId: int) -> List[Parcel]:
        return [p for p in self.findAll() if p.courierId == courierId]

    def _generateNumber(self) -> str:
        while True:
            number = "BY" + "".join(random.choice("0123456789") for _ in range(9))
            if self.parcelRepository.findByNumber(number) is None:
                return number


class NotificationService:
    """Подсистема уведомлений."""

    def __init__(self, parcelRepository: ParcelRepository, userRepository: UserRepository):
        self.parcelRepository = parcelRepository
        self.userRepository = userRepository

    def createNotification(self, parcelNumber: str, message: str) -> Notification:
        parcel = self.parcelRepository.findByNumber(parcelNumber)
        return Notification(message=message, parcelNumber=parcelNumber,
                            userId=parcel.clientId if parcel else 0)

    def sendNotification(self, notification: Notification) -> None:
        notification.sentAt = datetime.now()
        if notification.userId:
            self.userRepository.addNotification(notification.userId, notification)

    # ---- вспомогательные операции ----
    def getNotifications(self, userId: int) -> List[Notification]:
        return self.userRepository.findNotifications(userId)

    def markAllRead(self, userId: int) -> None:
        self.userRepository.markAllRead(userId)


class TrackingService:
    """Подсистема отслеживания: текущий статус и история перемещения."""

    def __init__(self, parcelRepository: ParcelRepository, notificationService: NotificationService):
        self.parcelRepository = parcelRepository
        self.notificationService = notificationService

    def getCurrentStatus(self, parcelNumber: str) -> ParcelStatus:
        parcel = self._require(parcelNumber)
        return parcel.status

    def getMovementHistory(self, parcelNumber: str) -> List[TrackingRecord]:
        return list(self._require(parcelNumber).records)

    def addTrackingRecord(self, parcelNumber: str, status: ParcelStatus,
                          description: str = "") -> TrackingRecord:
        """Сохраняет новое состояние и время изменения, затем формирует уведомление."""
        parcel = self._require(parcelNumber)
        record = TrackingRecord(status=status, timestamp=datetime.now(),
                                description=description or status.value)
        parcel.records.append(record)
        parcel.status = status
        self.parcelRepository.update(parcel)
        notification = self.notificationService.createNotification(
            parcelNumber, f"Посылка {parcelNumber} {status.phrase}")
        self.notificationService.sendNotification(notification)
        return record

    def _require(self, parcelNumber: str) -> Parcel:
        parcel = self.parcelRepository.findByNumber(parcelNumber)
        if parcel is None:
            raise ValueError(f"Посылка {parcelNumber} не найдена")
        return parcel


PERMISSIONS = {
    ROLE_ADMIN: {"view_all_parcels", "view_reports", "manage_users", "track_parcel"},
    ROLE_OPERATOR: {"register_parcel", "change_status", "deliver_parcel", "track_parcel",
                    "view_all_parcels", "view_reports", "view_couriers", "manage_couriers"},
    ROLE_COURIER: {"view_own_parcels", "deliver_parcel", "track_parcel"},
    ROLE_CLIENT: {"view_own_parcels", "track_parcel", "view_notifications"},
}


class UserService:
    """Подсистема управления пользователями: вход, роли, права доступа."""

    def __init__(self, userRepository: UserRepository):
        self.userRepository = userRepository

    @staticmethod
    def hashPassword(password: str) -> str:
        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    def authenticate(self, login: str, password: str) -> Optional[User]:
        user = self.userRepository.findByLogin(login.strip())
        if user and user.active and user.password == self.hashPassword(password):
            return user
        return None

    def checkAccess(self, userId: int, operation: str) -> bool:
        user = self.userRepository.findById(userId)
        return bool(user and user.active and operation in PERMISSIONS.get(user.role, set()))

    def manageUser(self, userId: int, operation: str) -> bool:
        """operation: activate | deactivate | delete | role:<роль> | password:<пароль>."""
        user = self.userRepository.findById(userId)
        if user is None:
            raise ValueError("Пользователь не найден")
        if operation == "activate":
            user.active = True
        elif operation == "deactivate":
            user.active = False
        elif operation == "delete":
            self.userRepository.delete(userId)
            return True
        elif operation.startswith("role:"):
            role = operation.split(":", 1)[1]
            if role not in USER_CLASSES:
                raise ValueError("Неизвестная роль")
            old = user
            user = USER_CLASSES[role](id=old.id, name=old.name, contactInfo=old.contactInfo,
                                      login=old.login, password=old.password, active=old.active)
        elif operation.startswith("password:"):
            pwd = operation.split(":", 1)[1]
            if len(pwd) < 3:
                raise ValueError("Пароль слишком короткий")
            user.password = self.hashPassword(pwd)
        else:
            raise ValueError(f"Неизвестная операция: {operation}")
        self.userRepository.update(user)
        return True

    # ---- вспомогательные операции ----
    def createUser(self, role: str, name: str, contactInfo: str, login: str, password: str) -> User:
        if role not in USER_CLASSES:
            raise ValueError("Неизвестная роль")
        if not name.strip() or not login.strip() or not password:
            raise ValueError("Заполните ФИО, логин и пароль")
        if self.userRepository.findByLogin(login.strip()):
            raise ValueError("Пользователь с таким логином уже существует")
        user = USER_CLASSES[role](name=name.strip(), contactInfo=contactInfo.strip(),
                                  login=login.strip(), password=self.hashPassword(password))
        self.userRepository.save(user)
        return user

    def getUsers(self) -> List[User]:
        return self.userRepository.findAll()

    def getUsersByRole(self, role: str) -> List[User]:
        return [u for u in self.getUsers() if u.role == role]

    def findById(self, userId: int) -> Optional[User]:
        return self.userRepository.findById(userId)

    def findClientByName(self, fullName: str) -> Optional[User]:
        for client in self.getUsersByRole(ROLE_CLIENT):
            if self._sameName(client.name, fullName):
                return client
        return None

    @staticmethod
    def _sameName(a: str, b: str) -> bool:
        ta, tb = a.lower().replace(".", " ").split(), b.lower().replace(".", " ").split()
        if not ta or not tb or ta[0] != tb[0]:
            return False
        return len(ta) < 2 or len(tb) < 2 or ta[1][0] == tb[1][0]
