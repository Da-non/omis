import os
import runpy
import tempfile
import unittest
from unittest import mock

import main as main_module
from parcelflow import injector
from parcelflow.injector import DB_PATH, ApplicationInjector
from parcelflow.ui import LogisticsUI

from . import fake_tk

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class InjectorTests(unittest.TestCase):
    def setUp(self):
        fake_tk.state.reset()

    def test_default_db_path(self):
        self.assertEqual(os.path.basename(DB_PATH), "parcelflow.db")
        self.assertEqual(ApplicationInjector().dbPath, DB_PATH)
        self.assertEqual(ApplicationInjector(":memory:").dbPath, ":memory:")

    def test_create_services_wires_and_seeds_empty_db(self):
        inj = ApplicationInjector(":memory:")
        inj.createServices()
        self.assertIs(inj.trackingService.notificationService, inj.notificationService)
        self.assertIs(inj.parcelService.parcelRepository, inj.parcelRepository)
        self.assertIs(inj.userService.userRepository, inj.userRepository)
        self.assertFalse(inj.database.isEmpty())
        self.assertEqual(len(inj.userService.getUsers()), 7)

    def test_existing_db_is_not_seeded_again(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "test.db")
            first = ApplicationInjector(path)
            first.createServices()
            before = len(first.parcelService.findAll())
            first.database.conn.close()
            second = ApplicationInjector(path)
            second.createServices()  # повторное наполнение упало бы на дубликате логина
            self.assertEqual(len(second.parcelService.findAll()), before)
            second.database.conn.close()

    def test_create_application_builds_ui(self):
        inj = ApplicationInjector(":memory:")
        app = inj.createApplication()
        self.assertIsInstance(app, LogisticsUI)
        self.assertIs(app.root, inj.root)
        self.assertIs(app.userService, inj.userService)
        self.assertEqual(app.currentState, "login")


class MainTests(unittest.TestCase):
    def test_main_creates_and_runs_application(self):
        with mock.patch.object(main_module, "ApplicationInjector") as injector_cls:
            main_module.Main.main()
        injector_cls.return_value.createApplication.assert_called_once_with()
        injector_cls.return_value.createApplication.return_value.run.assert_called_once_with()

    def test_script_entry_point(self):
        with mock.patch.object(injector, "ApplicationInjector") as injector_cls:
            runpy.run_path(os.path.join(PROJECT_ROOT, "main.py"), run_name="__main__")
        injector_cls.return_value.createApplication.return_value.run.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
