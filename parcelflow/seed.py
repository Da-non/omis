"""Начальное наполнение базы демонстрационными данными (данные из макетов ЛР5)."""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from .entities import (ROLE_ADMIN, ROLE_CLIENT, ROLE_COURIER, ROLE_OPERATOR, STATUS_FLOW,
                       Notification, Parcel, ParcelStatus as S, TrackingRecord)

OFFSET_H = {S.REGISTERED: 0, S.ACCEPTED: 6, S.SENT: 14, S.IN_TRANSIT: 20, S.DELAYED: 30,
            S.ARRIVED: 40, S.DELIVERED: 50, S.NOT_DELIVERED: 45}
CITIES = ["Минск", "Брест", "Витебск", "Гомель", "Гродно", "Могилёв"]
NAMES = ["Петров А.В.", "Алексеев М.С.", "Сергеев С.С.", "Козлов Д.Н.", "Пупкин А.А.",
         "Волков И.П.", "Морозова Н.А.", "Белов К.Л.", "Орлова Т.С.", "Зайцев В.Д."]


def _records(dep: datetime, status: S, scale: float = 1.0):
    if status in (S.DELAYED, S.NOT_DELIVERED):
        seq = STATUS_FLOW[:4] + [status]
    else:
        seq = STATUS_FLOW[:STATUS_FLOW.index(status) + 1]
    return [TrackingRecord(status=s, timestamp=min(dep + timedelta(hours=OFFSET_H[s] * scale), datetime.now()),
                           description=s.value) for s in seq]


def seedDatabase(userService, userRepository, parcelRepository) -> None:
    users = [
        (ROLE_ADMIN, "Кузьмич Д.С.", "admin@parcelflow.by", "admin", "admin"),
        (ROLE_OPERATOR, "Глёза Е.Д.", "+375 29 000-00-01", "operator1", "operator1"),
        (ROLE_COURIER, "Смирнов П.Л.", "+375 29 111-22-33", "courier1", "courier1"),
        (ROLE_COURIER, "Новик А.С.", "+375 33 222-33-44", "courier2", "courier2"),
        (ROLE_COURIER, "Лис Е.В.", "+375 44 333-44-55", "courier3", "courier3"),
        (ROLE_COURIER, "Громов Т.И.", "+375 29 444-55-66", "courier4", "courier4"),
        (ROLE_CLIENT, "Иванов И.А.", "+375 29 123-45-67", "client1", "client1"),
    ]
    created = {u[3]: userService.createUser(*u) for u in users}
    client = created["client1"]
    couriers = [created[f"courier{i}"] for i in range(1, 5)]
    now = datetime.now()

    def add(number, sender, recipient, address, route, dep, status, courier, clientId=0,
            est_days=2, scale=1.0):
        parcel = Parcel(number=number, sender=sender, recipient=recipient, deliveryAddress=address,
                        route=route, departureDate=dep.date(),
                        estimatedDeliveryDate=(dep + timedelta(days=est_days)).date(), status=status,
                        records=_records(dep, status, scale), courierId=courier.id, clientId=clientId,
                        senderPhone="+375 29 000-00-00", recipientPhone="+375 29 111-11-11")
        parcelRepository.save(parcel)
        return parcel

    demo = [
        add("BY123456789", "Козлов Д.Н.", "Иванов И.А.", "г. Брест, ул. Московская, 12", "Минск-Брест",
            now - timedelta(hours=30), S.IN_TRANSIT, couriers[0], client.id),
        add("BY555120930", "Петров А.В.", "Иванов И.А.", "г. Минск, ул. Мясникова, 5", "Гомель-Минск",
            now - timedelta(hours=26), S.IN_TRANSIT, couriers[0], client.id),
        add("BY987654321", "Волков И.П.", "Иванов И.А.", "г. Брест, ул. Ленина, 10", "Витебск-Брест",
            now - timedelta(days=4), S.DELIVERED, couriers[1], client.id),
        add("BY123987654", "Пупкин А.А.", "Иванов И.А.", "г. Брест, ул. Советская, 3", "Минск-Брест",
            now - timedelta(days=5), S.DELIVERED, couriers[1], client.id),
        add("BY321987654", "Алексеев М.С.", "Орлова Т.С.", "г. Минск, пр. Независимости, 40", "Брест-Минск",
            now - timedelta(days=3), S.DELAYED, couriers[0], est_days=2),
        add("BY421985673", "Сергеев С.С.", "Белов К.Л.", "г. Минск, ул. Притыцкого, 8", "Брест-Минск",
            now - timedelta(hours=3), S.REGISTERED, couriers[0]),
    ]
    for p in demo[:4]:  # уведомления клиента
        last = p.records[-1]
        userRepository.addNotification(client.id, Notification(
            message=f"Посылка {p.number} {last.status.phrase}", parcelNumber=p.number,
            sentAt=last.timestamp, isRead=p.status == S.DELIVERED))

    rnd = random.Random(7)  # архив для отчётов (статистика по месяцам)
    for i in range(110):
        a, b = rnd.sample(CITIES, 2)
        roll = rnd.random()
        if roll < 0.9:
            status, dep = S.DELIVERED, now - timedelta(days=rnd.uniform(6, 180))
        elif roll < 0.95:
            status, dep = S.IN_TRANSIT, now - timedelta(hours=rnd.uniform(24, 40))
        else:
            status, dep = S.DELAYED, now - timedelta(days=rnd.uniform(3, 5))
        add(f"BY{700000000 + i * 137:09d}", rnd.choice(NAMES), rnd.choice(NAMES),
            f"г. {b}, ул. Центральная, {rnd.randint(1, 80)}", f"{a}-{b}", dep, status,
            rnd.choice(couriers), est_days=rnd.randint(2, 4), scale=rnd.uniform(0.8, 2.0))
