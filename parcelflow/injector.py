"""<<injector>> ApplicationInjector — внедрение зависимостей (<<create>> для всех
репозиториев, сервисов и пользовательского интерфейса)."""
from __future__ import annotations

import os
import tkinter as tk

from .repositories import Database, ParcelRepository, UserRepository
from .seed import seedDatabase
from .services import NotificationService, ParcelService, TrackingService, UserService
from .ui import LogisticsUI

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "parcelflow.db")


class ApplicationInjector:
    def __init__(self, dbPath: str = DB_PATH):
        self.dbPath = dbPath

    def createServices(self) -> None:
        self.database = Database(self.dbPath)
        self.parcelRepository = ParcelRepository(self.database)
        self.userRepository = UserRepository(self.database)
        self.notificationService = NotificationService(self.parcelRepository, self.userRepository)
        self.parcelService = ParcelService(self.parcelRepository)
        self.trackingService = TrackingService(self.parcelRepository, self.notificationService)
        self.userService = UserService(self.userRepository)
        if self.database.isEmpty():
            seedDatabase(self.userService, self.userRepository, self.parcelRepository)

    def createApplication(self) -> LogisticsUI:
        self.createServices()
        self.root = tk.Tk()
        return LogisticsUI(self.root, self.parcelService, self.trackingService,
                           self.userService, self.notificationService)
