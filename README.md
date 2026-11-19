# ParcelFlow — система автоматизации учёта и отслеживания посылок

Программная реализация по отчёту к лабораторным работам №1–5 («Объектное моделирование
интеллектуальных систем», вариант 15, тема: *Система автоматизации учета и отслеживания посылок
в логистических компаниях*).

## Запуск

Требуется **Python 3.8+** с Tkinter (входит в стандартную поставку Python для Windows/macOS;
в Linux: `sudo apt install python3-tk`). Внешние библиотеки **не нужны**.

```bash
cd parcelflow
python main.py
```

При первом запуске создаётся база `parcelflow.db` (SQLite) с демонстрационными данными.
Чтобы вернуть данные к исходным, удалите файл `parcelflow.db`.

### Тестовые учётные записи

| Роль          | Логин       | Пароль      | Первый экран после входа |
|---------------|-------------|-------------|--------------------------|
| Администратор | `admin`     | `admin`     | Настройки (пользователи и права) |
| Оператор      | `operator1` | `operator1` | Главная |
| Курьер        | `courier1`  | `courier1`  | Мои посылки |
| Клиент        | `client1`   | `client1`   | Мои посылки |

Также есть курьеры `courier2`–`courier4` (пароль = логин).

## Структура проекта

```
main.py                    # <<main>> Main.main()
parcelflow/
  injector.py              # <<injector>> ApplicationInjector
  ui.py                    # <<UI>> LogisticsUI (все экраны по макетам ЛР5)
  services.py              # ParcelService, TrackingService, UserService, NotificationService
  repositories.py          # ParcelRepository, UserRepository (+ Database, SQLite)
  entities.py              # <<data>> BaseEntity, Parcel, TrackingRecord, Notification, User + роли
  mobile.py                # Направление 1: мобильное приложение
  maps.py                  # Направление 2: картографические сервисы
  analytics.py             # Направление 3: интеллектуальная аналитика
  seed.py                  # демонстрационные данные
```

Слои соответствуют диаграмме классов (ЛР4): `Main → ApplicationInjector → LogisticsUI →
Services → Repositories → Entities`. Все подсистемы взаимодействуют через общую базу данных.

---

## Описание классов и методов

### Точка входа и внедрение зависимостей

| Класс | Метод | Описание |
|-------|-------|----------|
| `Main` `<<main>>` | `main()` | Создаёт приложение через инжектор, подключает модули-расширения и запускает главный цикл. |
| `ApplicationInjector` `<<injector>>` | `createApplication()` | Создаёт (`<<create>>`) БД, репозитории, сервисы и `LogisticsUI`; при пустой БД заполняет демо-данными. |
| | `createServices()` | Создание репозиториев и сервисов и связывание их зависимостей. |

### Пользовательский интерфейс — `LogisticsUI` `<<UI>>`

Методы из диаграммы классов:

| Метод | Описание |
|-------|----------|
| `registerParcel()` | Регистрация посылки оператором: валидация формы → `ParcelService.registerParcel` → запись «Зарегистрирована» в историю (`TrackingService.addTrackingRecord`) → уведомление. Автоматически назначается наименее загруженный курьер, клиент определяется по ФИО получателя. |
| `trackParcel(parcelNumber)` | Отслеживание: проверка прав и наличия посылки; при отсутствии — ошибка «Посылка не найдена» (BPMN: «отслеживание завершено с ошибкой»). |
| `changeParcelStatus(parcelNumber, status, description)` | Смена статуса по sequence-диаграмме: проверка прав → `isStatusAllowed` → `updateParcelStatus` → `addTrackingRecord` (история + время) → уведомление клиенту. Недопустимый статус — ветка `[else] displayError("Invalid status")`. |
| `showParcelInfo(parcel)` | Карточка посылки и «История перемещения» (временная шкала, ещё не пройденные этапы выделены серым). |
| `showError(message)` | Диалог ошибки. |

Методы-переходы диаграммы состояний: `enterSystem()`, `logout()`, `openMain()`, `openParcels()`,
`openNewParcel()`, `openTracking()`, `openCouriers()`, `openReports()`, `openSettings()`,
`openMyParcels()`, `openDeliveryHistory()`, `openNotifications()`.
`registerExtension(title, roles, launcher, perParcel)` подключает модули-расширения без изменения базовой системы.

### Сервисы (бизнес-логика)

**`ParcelService`** — подсистема управления посылками
- `registerParcel(parcel)` — проверка данных, генерация уникального номера `BY#########`, статус «Зарегистрирована», сохранение.
- `findParcel(parcelNumber)` — поиск по номеру.
- `updateParcelStatus(parcelNumber, status)` — обновление статуса.
- вспомогательные: `isStatusAllowed(current, new)`, `findAll()`, `getPendingParcels()`, `findByClient(id)`, `findByCourier(id)`.

**`TrackingService`** — подсистема отслеживания
- `getCurrentStatus(parcelNumber) : ParcelStatus`
- `getMovementHistory(parcelNumber) : List<TrackingRecord>`
- `addTrackingRecord(parcelNumber, status, description)` — сохраняет статус с временем изменения и вызывает `NotificationService`.

**`UserService`** — подсистема управления пользователями
- `authenticate(login, password) : User` — вход (пароли хранятся в виде SHA-256, заблокированные не входят).
- `checkAccess(userId, operation) : boolean` — матрица прав по ролям.
- `manageUser(userId, operation)` — `activate`, `deactivate`, `delete`, `role:<роль>`, `password:<пароль>`.
- вспомогательные: `createUser`, `getUsers`, `getUsersByRole`, `findById`, `findClientByName`.

**`NotificationService`** — подсистема уведомлений
- `createNotification(parcelNumber, message) : Notification`
- `sendNotification(notification)` — ставит время отправки и сохраняет у клиента.
- вспомогательные: `getNotifications(userId)`, `markAllRead(userId)`.

### Репозитории

- **`ParcelRepository`**: `save(parcel)`, `findByNumber(parcelNumber)`, `update(parcel)`, `findAll()`.
- **`UserRepository`**: `save(user)`, `findById(userId)`, `findByLogin(login)`, `update(user)`, `findAll()`, `delete(userId)`, а также операции с уведомлениями пользователя (композиция `User → Notification`): `addNotification`, `findNotifications`, `markAllRead`.

### Сущности `<<data>>`

- `BaseEntity` `<<abstract>>` — общий идентификатор `id`.
- `Parcel` — `number, sender, recipient, deliveryAddress, departureDate, estimatedDeliveryDate, status`; композиция с `TrackingRecord` (поле `records`, 0..*).
- `TrackingRecord` — `id, status, timestamp, description`.
- `Notification` — `id, message, sentAt`.
- `User` `<<abstract>>` — `name, contactInfo` (+ `login, password, active`); композиция с `Notification` (`notifications`, 0..*).
  - `Client.viewMyParcels()`, `Courier.markAsDelivered()`, `Administrator.manageUsers()`, `Operator.manageUsers()`.
- `ParcelStatus` — Зарегистрирована, Принята на склад, Отправлена, В пути, Доставлена в пункт назначения, Вручена получателю, а также Задержана и Не вручена (из макетов и BPMN).

### Направление 1 — Мобильное приложение (`mobile.py`)
`MobileApplicationInjector.createMobileApplication()` создаёт `MobileUI` и `MobileController`.
- `MobileUI` `<<UI>>`: `showParcelStatus(number)`, `showDeliveryTasks()`, `submitStatusChange(number, status)`, `showMessage(message)` — окно формата смартфона (вкладка задач — только у курьера).
- `MobileController`: `trackParcel(number)`, `getDeliveryTasks(courierId)`, `changeParcelStatus(number, status)`; использует существующие `ParcelService` и `TrackingService`.

### Направление 2 — Карты (`maps.py`)
- `MapProvider` `<<interface>>`: `getLocation`, `calculateRoute`, `getMapData`.
- `ExternalMapAdapter` — реализует `MapProvider` (паттерн «Адаптер»; внешний API имитируется офлайн-справочником городов Беларуси и формулой гаверсинусов).
- `MapService`: `findParcel`, `buildRoute`, `getMapData` (работает только с `MapProvider`).
- `MapController`: `buildDeliveryRoute(parcelNumber)`, `findCourierLocation(courierId)`.
- `MapData` `<<data>>`: `coordinates, route, distance, estimatedDuration`.
- `MapUI` `<<UI>>`: `requestRoute`, `showCourierLocation`, `showMap`, `showMessage` — рисует маршрут и текущее положение посылки/курьера.
- `MapApplicationInjector.createMapApplication()`.

### Направление 3 — Аналитика (`analytics.py`)
- `DeliveryTimePredictor` `<<interface>>`: `predict(parcelData, history)`; реализация `StatisticalPredictor`.
- `DelayDetector.findDelays(parcelData, history)` — признаки задержки (статус, просрочка, нет обновлений > 24 ч).
- `AnalyticsService`: `predictDeliveryTime`, `detectDelays`, `getAnalyticsResults`.
- `AnalyticsController`: `forecastDelivery(parcelNumber)`, `analyzeDelays()`.
- `AnalyticsData` `<<data>>`: `forecastDate, delayDetected, delayDescription, confidence`.
- `AnalyticsUI` `<<UI>>`: `requestDeliveryForecast`, `requestDelayAnalysis`, `showForecast`, `showDelayReport`, `showMessage`.
- `AnalyticsApplicationInjector.createAnalyticsApplication()`.

Расширения доступны в боковом меню в разделе «Дополнительно» и кнопками на экране отслеживания («Карта», «Аналитика»).

---

## Пользовательский интерфейс и переходы между окнами

Реализованы все макеты ЛР5 (тёмно-синее меню слева, голубой фон, синие кнопки). Состояния и переходы — по диаграмме состояний:

- **Вход в систему** → при верных данных открывается интерфейс по роли; при неверных — остаётся на входе (сообщение об ошибке).
- **Администратор:** Настройки (пользователи и права: поиск, фильтр по роли, добавление, смена роли/блокировка/пароль, удаление) · Главная · Посылки · Отчёты.
- **Оператор:** Главная (обзор, последние отправления) · Посылки (список, смена статуса, «Добавить посылку» → **Новая посылка**) · Отслеживание · Курьеры (добавление, активные посылки) · Отчёты (диаграмма по месяцам, экспорт в CSV) · Настройки (профиль).
- **Курьер:** Мои посылки («Вручена получателю», «Не вручена (отказ)», фильтр по адресу) · История доставок.
- **Клиент:** Мои посылки · Отслеживание · Уведомления (непрочитанные отмечены «●», «Открыть →», «Отметить все прочитанными»).
- Из любого состояния доступен переход `logout()` (кнопка «Выйти») в «Вход в систему».

## Соответствие сценариям и диаграммам

- **BPMN:** регистрация посылки (проверка корректности → ID → статус «Зарегистрирована»), отслеживание (найдена / не найдена), изменение статуса (сохранение → уведомление), доставка (вручена / не вручена).
- **Use Case:** все прецеденты реализованы, включая `extend`: «Просмотреть историю перемещения», «Фильтровать по адресам», «Оформить отказ от получения».
- **Права доступа** (`UserService.checkAccess`): клиент — только свои посылки, отслеживание, уведомления; курьер — свои посылки и вручение; оператор — регистрация, смена статусов, курьеры, отчёты; администратор — пользователи и права.

## Допущения

- В `Parcel` добавлены служебные поля `route`, `senderPhone`, `recipientPhone`, `clientId`, `courierId` (нужны для экранов «Маршрут», телефонов в форме и для связи посылки с клиентом и курьером). Маршрут формируется как «Минск–<город из адреса>».
- В `User` добавлены `login`, `password`, `active` — необходимы для экрана входа и блокировки.
- В `MapData` добавлено необязательное поле `currentPosition` для отображения текущего положения на карте; `MapController` дополнительно использует `UserService` для списка курьеров.
- Внешний картографический API имитируется адаптером, поэтому приложение работает без интернета.
- Даты в форме новой посылки вводятся текстом в формате `ГГГГ-ММ-ДД` (или `ДД.ММ.ГГГГ`).
