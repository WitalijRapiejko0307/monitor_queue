# План реализации: сервис мониторинга очереди на границе (Telegram-бот)

Статус: на согласование. Код не начинается до отдельного "ОК" на этот план.

## 1. Назначение и объём первой версии (MVP)

Платный разовый сервис в Telegram: пользователь покупает одно наблюдение за одним
пунктом пропуска (направление "выезд из РБ", легковой/грузовой) на одну ночь, бот
присылает сообщение, когда число машин в зоне ожидания электронной очереди достигло
заданного порога (по умолчанию — появилась, то есть ≥1).

Вне объёма MVP (отложено сознательно, не забыто):
- Каналы WhatsApp/Viber — только Telegram на первом этапе.
- Направление "въезд в РБ" и тип "автобус" — данные собираем, в продаже не участвуют.
- Админ-веб-панель — доступ к логам только через админ-команды бота.
- Повторная подписка/подписка на несколько пунктов одной оплатой.

## 2. Источник данных

- `GET https://gpk.gov.by/situation-at-the-border/`, обычный HTTP, без браузера.
- Парсинг таблиц `#car` и `#truck` (BeautifulSoup/lxml): по каждому пункту —
  значение "выезд из РБ", флаг "электронная очередь" (наличие `(N)*`), флаг
  "пункт не работает" (класс `text-red`), время среза из блока `.ochered_time`.
- Список пунктов для продажи — только с электронной очередью: Григоровщина, Урбаны,
  Котловка, Каменный Лог, Бенякони, Брузги, Берестовица, Козловичи, Брест.
- Опрос: APScheduler, каждые 2 часа в 10 минут после чётного часа (00:10, 02:10, ...,
  минский часовой пояс), плюс ручной триггер админ-командой для отладки.
- Если таблица не распарсилась — снапшот не пишется как "очередь = 0", фиксируется
  отдельное событие ошибки парсинга, админу уходит сообщение.

## 3. Модель данных (PostgreSQL, SQLAlchemy + alembic)

**crossing_points** — справочник пунктов пропуска
- id, slug, name, has_electronic_queue (bool), is_active_for_sale (bool)

**queue_snapshots** — результат одного опроса сайта ГПК
- id, fetched_at (время запроса сервером), source_time (время среза с сайта),
  parse_ok (bool), raw_html_ref (опционально, путь/хэш для отладки)

**queue_values** — значения внутри снапшота, по пункту/направлению/типу
- id, snapshot_id, crossing_point_id, direction (exit_by/entry_by),
  vehicle_type (car/truck/bus), raw_value (строка как на сайте, напр. "(65)*", "-", "0"),
  numeric_value (nullable int), is_electronic_queue_value (bool)

**users** — минимальный профиль
- id, telegram_id, created_at, is_admin (bool, из конфига/колонки)

**payments** — платёжные события
- id, user_id, telegram_payment_charge_id, provider, amount, currency,
  status (invoice_created/succeeded/refunded/failed), created_at, raw_payload (JSON)

**subscriptions** — купленное наблюдение
- id, user_id, payment_id, crossing_point_id, vehicle_type, direction,
  threshold (int, default 1), window_start, window_end, status
  (pending_payment/active/fulfilled/expired/cancelled/error), created_at

**event_log** — неизменяемый журнал (append-only), для `/trace`
- id, created_at, event_type (payment_*, subscription_*, snapshot_fetch,
  rule_check, window_state, notification_sent, notification_failed, parse_error),
  subscription_id (nullable), payment_id (nullable), telegram_id (nullable),
  payload (JSON — что именно произошло: снятое значение, порог, решение, текст сообщения,
  ответ Telegram API)

Хранение: payments и event_log — не короче нескольких месяцев; остальное — по мере роста
можно архивировать отдельно.

## 4. Модули приложения

```
app/
  bot/            # aiogram: хендлеры визарда, админ-команды, Payments callbacks
  scraper/        # httpx-клиент + парсер HTML ГПК -> QueueSnapshot
  scheduler/      # APScheduler job: fetch -> save snapshot -> evaluate subscriptions
  domain/         # правила: evaluate_subscription(snapshot, subscription) -> decision
  db/             # SQLAlchemy models, session, alembic migrations
  logging/        # event_log writer (append-only helper), admin trace formatter
  config.py       # токены, admin telegram_id, провайдер оплаты, таймзона
  main.py         # запуск бота + планировщика в одном процессе
```

Поток выполнения по срабатыванию:
`scheduler job → scraper.fetch_and_parse() → db.save(snapshot, values)
→ for each active subscription: domain.evaluate() → event_log(rule_check)
→ if match: bot.send_notification() → event_log(notification_sent) → subscription.status = fulfilled`

## 5. Telegram-бот: сценарий и платежи

Визард (aiogram FSM): пункт → тип ТС → время выезда → порог → подтверждение → счёт.
После `successful_payment` — создание subscription со статусом `active` и
`window_start = now`, `window_end` = выбранное время выезда.

Платежи: Telegram Bot Payments API, провайдер bePaid или WebPay (белорусский эквайринг,
подтверждается отдельно — нужны ваши реквизиты/договор, это блокер для подключения
реальных платежей, но не блокер для разработки остального на тестовом провайдере/заглушке).

Админ-команды (доступ только по telegram_id из конфига):
- `/trace <subscription_id>`
- `/trace_user <telegram_id>`
- `/last_errors [N]`
- `/status`
- `/force_fetch` — ручной внеочередной опрос ГПК

## 6. Порядок реализации (атомарные шаги)

1. Каркас проекта, конфиг, подключение к Postgres на Railway, миграция справочника
   crossing_points.
2. Scraper + парсер ГПК, юнит-тесты на сохранённом HTML, ручной `/force_fetch` в тестовом
   боте без оплаты — проверяем, что данные снимаются верно на реальном сайте.
3. Модели payments/subscriptions/event_log + миграции.
4. Визард бота без оплаты (заглушка "оплата прошла") — проверяем UX сценария целиком.
5. APScheduler job + domain.evaluate + отправка уведомления — сквозной прогон на тестовой
   подписке.
6. Admin-команды и `/trace`.
7. Подключение реального платёжного провайдера (после получения реквизитов).
8. Деплой на Railway (сервис + Postgres plugin), настройка переменных окружения,
   проверка job по расписанию в проде.

## 7. Риски

- Смена вёрстки HTML на gpk.gov.by — парсер отличает "ошибка парсинга" от "очередь = 0",
  авто-алерт админу.
- Платёжный провайдер: сроки подключения зависят от договора с bePaid/WebPay, вне контроля
  разработки — не блокирует остальные шаги плана.
- Опрос раз в 2 часа не ловит момент появления очереди внутри окна — ограничение источника
  данных, явно описано пользователям в тексте сообщений ("по данным ГПК на HH:MM").
- Один процесс бот+планировщик на старте — при росте нагрузки потребуется разнести на
  два сервиса Railway (уже предусмотрено модульной структурой).

## 8. Критерии приёмки MVP

- Пользователь проходит визард, оплачивает, получает уведомление при выполнении условия
  или сообщение "очередь не собралась" к концу окна.
- Админ видит полную цепочку по `/trace <id>`: оплата → параметры → каждая проверка →
  отправка → закрытие.
- Ошибка парсинга ГПК не путается с "очередь = 0" ни в логике, ни в логах.
- Админ-команды недоступны никому кроме указанного telegram_id.
