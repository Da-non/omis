"""<<main>> Main — точка входа приложения ParcelFlow."""
from parcelflow.injector import ApplicationInjector


class Main:
    @staticmethod
    def main() -> None:
        injector = ApplicationInjector()
        app = injector.createApplication()
        app.run()


if __name__ == "__main__":
    Main.main()