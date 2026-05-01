# Delivery Tracker

Production-oriented сервис для отслеживания multi-carrier отправлений с fallback между агрегатором и Playwright-адаптерами, хранением истории статусов и уведомлениями в Telegram.

## Возможности

- Multi-carrier архитектура с единым интерфейсом `CarrierAdapter`
- Приоритет получения статуса: агрегатор -> carrier-specific fallback
- Авто-определение перевозчика по tracking number
- Интеграция с Google Sheets как реестром shipment-ов
- Нормализация статусов к общей доменной модели
- Защита от повторных уведомлений о получении
- История смены статусов в БД
- CLI для добавления отправлений и запуска проверки
- APScheduler для запуска по интервалу

## Структура

```text
delivery_tracker/
  adapters/
  models/
  repositories/
  services/
  config.py
  db.py
  logging_config.py
  scheduler.py
main.py
requirements.txt
.env.example
```

## Запуск

1. Создать виртуальное окружение:

```bash
python -m venv .venv
```

2. Активировать окружение:

```bash
.venv\Scripts\activate
```

3. Установить зависимости:

```bash
pip install -r requirements.txt
playwright install chromium
```

4. Создать `.env` на основе `.env.example` и заполнить:

- `DATABASE_URL`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `AGGREGATOR_API_KEY`
- при использовании Google Sheets: `GOOGLE_SHEETS_ENABLED`, `GOOGLE_SHEETS_SPREADSHEET_ID`, `GOOGLE_SHEETS_CREDENTIALS_FILE`

Если `17TRACK` пока не настроен, оставьте `AGGREGATOR_API_KEY=` пустым. Сервис просто пропустит шаг агрегатора и сразу пойдет в fallback-адаптеры.

5. Добавить отправление:

```bash
python main.py add-shipment --tracking-number RR123456789CY --pickup-location-url https://maps.google.com/?q=35.1856,33.3823 --pickup-code 4821 --recipient-name "Алексей" --recipient-username alexey
```

6. Разовая проверка:

```bash
python main.py run-once
```

7. Запуск планировщика:

```bash
python main.py scheduler
```

## Google Sheets

Сервис может читать shipment-ы из Google Sheets и писать обратно текущие статусы. Для production-сценария лучше использовать service account, а не desktop OAuth quickstart. Google в quickstart отдельно пишет, что упрощенная авторизация подходит для тестов, а для production нужно выбирать подходящий тип credentials. Источник: [Google Sheets Python quickstart](https://developers.google.com/workspace/sheets/api/quickstart/python).

Что нужно сделать:

1. В Google Cloud включить Google Sheets API.
2. Создать service account и скачать JSON credentials.
3. Положить файл, например, как `google-service-account.json` в корень проекта.
4. Открыть Google Sheet и расшарить ее на e-mail service account с правами Editor.
5. Заполнить `.env`:

```env
GOOGLE_SHEETS_ENABLED=true
GOOGLE_SHEETS_SPREADSHEET_ID=your_spreadsheet_id
GOOGLE_SHEETS_WORKSHEET_NAME=Shipments
GOOGLE_SHEETS_CREDENTIALS_FILE=./google-service-account.json
```

Рекомендуемые колонки в строке 1:

```text
tracking_number | carrier | recipient_name | recipient_username | pickup_location_url | pickup_code | active | last_status | last_status_raw | last_checked_at | pickup_notified | sync_state | error_message
```

Достаточно заполнять только:

- `tracking_number`
- `recipient_name`
- `recipient_username`
- опционально `carrier`, `pickup_location_url`, `pickup_code`, `active`

Остальные поля сервис обновляет сам после каждого цикла.

## Пример добавления shipment

```bash
python main.py add-shipment --tracking-number 123456789012 --recipient-name "Мария" --recipient-username maria --pickup-location-url https://maps.google.com/?q=35.1,33.3
```

## Пример логов

```text
2026-04-24 10:00:00,010 | INFO | delivery_tracker.scheduler | Scheduler started with interval=30 minutes
2026-04-24 10:00:00,021 | INFO | delivery_tracker.services.tracker | Tracker cycle started. Shipments to process: 2
2026-04-24 10:00:00,321 | INFO | delivery_tracker.services.tracker | Trying aggregator for RR123456789CY
2026-04-24 10:00:01,004 | WARNING | delivery_tracker.services.tracker | Aggregator failed for RR123456789CY: Aggregator request failed: 401 Unauthorized
2026-04-24 10:00:01,005 | INFO | delivery_tracker.services.tracker | Trying cyprus_post adapter for RR123456789CY
2026-04-24 10:00:06,882 | INFO | delivery_tracker.services.tracker | Status changed for RR123456789CY: IN_TRANSIT -> READY_FOR_PICKUP (Available for collection)
2026-04-24 10:00:07,192 | INFO | delivery_tracker.services.tracker | Pickup notification sent for RR123456789CY
2026-04-24 10:00:08,010 | INFO | delivery_tracker.services.tracker | No status change for 123456789012, still IN_TRANSIT
```

## Как добавить нового carrier

1. Создать новый адаптер в `delivery_tracker/adapters/`
2. Унаследоваться от `CarrierAdapter` или `PlaywrightCarrierAdapter`
3. Добавить детекцию в `delivery_tracker/adapters/detection.py`
4. Зарегистрировать адаптер в `TrackingService.carrier_adapters`

## Замечания по production

- Для production лучше использовать PostgreSQL вместо SQLite
- Для горизонтального масштабирования можно вынести scheduler в отдельный процесс
- Для интеграции с другими агрегаторами достаточно добавить новый adapter и зарегистрировать его как provider
- Переход на другой агрегатор делается через новый клиент в `delivery_tracker/adapters/aggregator_clients.py`, без переписывания `TrackingService`
- По состоянию на апрель 2026 у Cyprus Post на официальном сайте есть публичное сообщение, что web Track & Trace может быть недоступен; адаптер теперь завершает такую ситуацию быстро и с понятной ошибкой вместо долгого таймаута
- Если трек не найден, система пишет warning и не шлет ложное уведомление
