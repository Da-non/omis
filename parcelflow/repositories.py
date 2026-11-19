"""Слой доступа к данным: ParcelRepository и UserRepository.
Все подсистемы работают через общую базу данных (SQLite)."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime
from typing import List, Optional

from .entities import (USER_CLASSES, Notification, Parcel, ParcelStatus,
                       TrackingRecord, User)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT NOT NULL, name TEXT NOT NULL,
    contact TEXT, login TEXT UNIQUE NOT NULL, password TEXT NOT NULL, active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS parcels(
    id INTEGER PRIMARY KEY AUTOINCREMENT, number TEXT UNIQUE NOT NULL, sender TEXT,
    sender_phone TEXT, recipient TEXT, recipient_phone TEXT, address TEXT, route TEXT,
    departure TEXT, estimated TEXT, status TEXT, client_id INTEGER DEFAULT 0,
    courier_id INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS tracking(
    id INTEGER PRIMARY KEY AUTOINCREMENT, parcel_id INTEGER NOT NULL,
    status TEXT, ts TEXT, description TEXT);
CREATE TABLE IF NOT EXISTS notifications(
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, parcel_number TEXT,
    message TEXT, sent_at TEXT, is_read INTEGER DEFAULT 0);
"""


class Database:
    """Общая база данных системы (пользователи, посылки, история, уведомления)."""

    def __init__(self, path: str = ":memory:"):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def isEmpty(self) -> bool:
        return self.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0


class ParcelRepository:
    def __init__(self, db: Database):
        self.db = db

    # ---- операции из диаграммы классов ----
    def save(self, parcel: Parcel) -> None:
        cur = self.db.conn.execute(
            "INSERT INTO parcels(number,sender,sender_phone,recipient,recipient_phone,address,"
            "route,departure,estimated,status,client_id,courier_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            self._params(parcel))
        parcel.id = cur.lastrowid
        self._saveRecords(parcel)
        self.db.conn.commit()

    def findByNumber(self, parcelNumber: str) -> Optional[Parcel]:
        row = self.db.conn.execute(
            "SELECT * FROM parcels WHERE number=?", (parcelNumber,)).fetchone()
        return self._toParcel(row) if row else None

    def update(self, parcel: Parcel) -> None:
        p = self._params(parcel)
        self.db.conn.execute(
            "UPDATE parcels SET number=?,sender=?,sender_phone=?,recipient=?,recipient_phone=?,"
            "address=?,route=?,departure=?,estimated=?,status=?,client_id=?,courier_id=? WHERE id=?",
            p + (parcel.id,))
        self._saveRecords(parcel)
        self.db.conn.commit()

    # ---- вспомогательные операции ----
    def findAll(self) -> List[Parcel]:
        rows = self.db.conn.execute("SELECT * FROM parcels ORDER BY id").fetchall()
        return [self._toParcel(r) for r in rows]

    @staticmethod
    def _params(p: Parcel) -> tuple:
        return (p.number, p.sender, p.senderPhone, p.recipient, p.recipientPhone,
                p.deliveryAddress, p.route, p.departureDate.isoformat(),
                p.estimatedDeliveryDate.isoformat(), p.status.name, p.clientId, p.courierId)

    def _saveRecords(self, parcel: Parcel) -> None:
        for r in parcel.records:
            if r.id == 0:
                cur = self.db.conn.execute(
                    "INSERT INTO tracking(parcel_id,status,ts,description) VALUES(?,?,?,?)",
                    (parcel.id, r.status.name, r.timestamp.isoformat(), r.description))
                r.id = cur.lastrowid

    def _toParcel(self, row) -> Parcel:
        recs = self.db.conn.execute(
            "SELECT * FROM tracking WHERE parcel_id=? ORDER BY ts, id", (row["id"],)).fetchall()
        return Parcel(
            id=row["id"], number=row["number"], sender=row["sender"] or "",
            senderPhone=row["sender_phone"] or "", recipient=row["recipient"] or "",
            recipientPhone=row["recipient_phone"] or "", deliveryAddress=row["address"] or "",
            route=row["route"] or "", departureDate=date.fromisoformat(row["departure"]),
            estimatedDeliveryDate=date.fromisoformat(row["estimated"]),
            status=ParcelStatus[row["status"]], clientId=row["client_id"] or 0,
            courierId=row["courier_id"] or 0,
            records=[TrackingRecord(id=r["id"], status=ParcelStatus[r["status"]],
                                    timestamp=datetime.fromisoformat(r["ts"]),
                                    description=r["description"] or "") for r in recs])


class UserRepository:
    def __init__(self, db: Database):
        self.db = db

    # ---- операции из диаграммы классов ----
    def save(self, user: User) -> None:
        cur = self.db.conn.execute(
            "INSERT INTO users(role,name,contact,login,password,active) VALUES(?,?,?,?,?,?)",
            (user.role, user.name, user.contactInfo, user.login, user.password, int(user.active)))
        user.id = cur.lastrowid
        self.db.conn.commit()

    def findById(self, userId: int) -> Optional[User]:
        row = self.db.conn.execute("SELECT * FROM users WHERE id=?", (userId,)).fetchone()
        return self._toUser(row) if row else None

    def findByLogin(self, login: str) -> Optional[User]:
        row = self.db.conn.execute("SELECT * FROM users WHERE login=?", (login,)).fetchone()
        return self._toUser(row) if row else None

    def update(self, user: User) -> None:
        self.db.conn.execute(
            "UPDATE users SET role=?,name=?,contact=?,login=?,password=?,active=? WHERE id=?",
            (user.role, user.name, user.contactInfo, user.login, user.password,
             int(user.active), user.id))
        self.db.conn.commit()

    # ---- вспомогательные операции ----
    def findAll(self) -> List[User]:
        rows = self.db.conn.execute("SELECT * FROM users ORDER BY id").fetchall()
        return [self._toUser(r, withNotifications=False) for r in rows]

    def delete(self, userId: int) -> None:
        self.db.conn.execute("DELETE FROM users WHERE id=?", (userId,))
        self.db.conn.execute("DELETE FROM notifications WHERE user_id=?", (userId,))
        self.db.conn.commit()

    # ---- уведомления (композиция User -> Notification) ----
    def addNotification(self, userId: int, n: Notification) -> None:
        cur = self.db.conn.execute(
            "INSERT INTO notifications(user_id,parcel_number,message,sent_at,is_read) VALUES(?,?,?,?,?)",
            (userId, n.parcelNumber, n.message,
             (n.sentAt or datetime.now()).isoformat(), int(n.isRead)))
        n.id = cur.lastrowid
        n.userId = userId
        self.db.conn.commit()

    def findNotifications(self, userId: int) -> List[Notification]:
        rows = self.db.conn.execute(
            "SELECT * FROM notifications WHERE user_id=? ORDER BY sent_at DESC, id DESC",
            (userId,)).fetchall()
        return [Notification(id=r["id"], message=r["message"], userId=r["user_id"],
                             parcelNumber=r["parcel_number"] or "",
                             sentAt=datetime.fromisoformat(r["sent_at"]),
                             isRead=bool(r["is_read"])) for r in rows]

    def markAllRead(self, userId: int) -> None:
        self.db.conn.execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (userId,))
        self.db.conn.commit()

    def _toUser(self, row, withNotifications: bool = True) -> User:
        user = USER_CLASSES[row["role"]](
            id=row["id"], name=row["name"], contactInfo=row["contact"] or "",
            login=row["login"], password=row["password"], active=bool(row["active"]))
        if withNotifications:
            user.notifications = self.findNotifications(user.id)
        return user
