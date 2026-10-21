# Мониторинг очереди на границе — Telegram-бот

Платный разовый сервис: пользователь покупает наблюдение за одним пунктом
пропуска (легковой/грузовой, выезд из РБ) на одну ночь. Бот опрашивает
https://gpk.gov.by/situation-at-the-border/ каждые 2 часа и присылает
сообщение, когда число машин в зоне ожидания электронной очереди достигло
заданного порога.

Полный план и обоснование решений — в [`docs/implementation-plan.md`](docs/implementation-plan.md).

## Стек

Python 3.12, aiogram 3.x, PostgreSQL (SQLAlchemy + alembic), APScheduler,
httpx + BeautifulSoup/lxml, деплой на Railway.

## Структура

```
app/
  bot/         aiogram: визард покупки, оплата, админ-команды, уведомления
  scraper/     HTTP-клиент и парсер HTML-страницы ГПК
  domain/      правило срабатывания подписки, сохранение снапшота, обработка подписок
  db/          SQLAlchemy модели и сессия
  logging/     append-only event_log + форматирование /trace для админа
  scheduler/   APScheduler job (опрос раз в 2 часа)
  config.py    настройки из переменных окружения
  main.py      точка входа: бот (long polling) + планировщик в одном процессе
migrations/    alembic
scripts/       seed_crossing_points.py — наполнение справочника пунктов
tests/         pytest: парсер, правило evaluate_subscription
docs/          implementation-plan.md
```

## Локальный запуск

1. Скопировать `.env.example` → `.env`, заполнить `BOT_TOKEN`, `ADMIN_TELEGRAM_IDS`,
   `DATABASE_URL` (локальный Postgres). `PAYMENT_PROVIDER_TOKEN` сейчас пустой —
   оплата временно отключена по решению заказчика: визард сразу активирует
   наблюдение без оплаты («тестовый режим»). Платёжный код (`Payment`,
   Telegram Invoices, `on_pre_checkout`/`on_successful_payment`) не удалён —
   достаточно заполнить `PAYMENT_PROVIDER_TOKEN`, чтобы вернуть платный режим.
2. Установить зависимости: `pip install -e ".[dev]"`.
3. Применить миграции: `alembic upgrade head`.
4. Наполнить справочник пунктов: `python -m scripts.seed_crossing_points`.
5. Запустить: `python -m app.main`.

## Тесты

```
pytest tests/ -q
```

Покрыты: разбор HTML ГПК (`app/scraper/parser.py`) — электронная очередь,
обычное число, прочерк, неработающий сопредельный пункт, отсутствие таблиц;
правило оценки подписки (`app/domain/rules.py`) — порог, отсутствие данных,
нечисловое значение, истёкшее окно.

## Админ-команды в боте

Доступны только telegram_id из `ADMIN_TELEGRAM_IDS`:

- `/trace <subscription_id>` — полная цепочка: оплата → параметры → каждая
  проверка → отправка → закрытие.
- `/trace_user <telegram_id>` — все подписки пользователя.
- `/last_errors [N]` — последние ошибки (парсинг, доставка, оплата).
- `/status` — последний снапшот, число активных наблюдений, включены ли платежи.
- `/force_fetch` — внеочередной опрос ГПК и обработка подписок (для отладки).

## Деплой на Railway

`Dockerfile` выполняет `alembic upgrade head` → `seed_crossing_points` → `app.main`
при каждом старте контейнера. Нужны переменные окружения: `BOT_TOKEN`,
`ADMIN_TELEGRAM_IDS`, `DATABASE_URL` (подставляется Railway Postgres plugin
автоматически), `PAYMENT_PROVIDER_TOKEN` после подключения провайдера
(bePaid/WebPay — см. план, §7, риск "сроки зависят от договора").

## Известные ограничения MVP

- Опрос раз в 2 часа — не ловит точный момент появления очереди внутри окна
  (ограничение источника данных, отражено в тексте уведомления).
- Канал оповещения — только Telegram; WhatsApp/Viber не реализованы.
- Продаются только пункты с электронной очередью (`is_active_for_sale=True`
  в `app/scraper/crossing_points.py`).
