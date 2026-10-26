# Бот записи в барбершоп

Telegram-бот для записи клиентов на услуги: выбор услуги, дня и времени, подтверждение, напоминание и панель мастера.

**Стек:** Python 3.11+, aiogram 3, SQLite.

## Что умеет

**Клиент**
- `/start` и меню «📅 Записаться» / «🗂 Мои записи»
- Пошаговая запись: услуга → день → свободное время → телефон (кнопкой или текстом) → подтверждение
- Кнопки «назад» на каждом шаге
- Просмотр и отмена своих записей
- Напоминание за 2 часа до визита

**Мастер (`/admin`)**
- Записи на любой день недели вперёд с именами и телефонами
- Отмена записи в один клик, клиент получает уведомление
- Уведомления о новых записях и отменах

**Надёжность**
- Одно время нельзя занять дважды, даже при одновременном нажатии: это гарантирует уникальный индекс в базе (`db.py`)
- Прошедшее время не показывается и не бронируется
- Нельзя отменить чужую запись подделанной кнопкой
- Ошибка в напоминаниях не роняет бота

## Структура

```
bot.py           точка входа, сборка диспетчера
config.py        настройки из .env
db.py            база: услуги, записи, напоминания
slots.py         расчёт свободного времени (чистые функции)
keyboards.py     кнопки и CallbackData
reminders.py     фоновая задача напоминаний
handlers/
  client.py      сценарий клиента (FSM)
  admin.py       панель мастера
tests/           тесты логики
deploy/          unit-файл systemd
```

## Запуск у себя

1. Создай бота у [@BotFather](https://t.me/BotFather), скопируй токен.
2. Узнай свой Telegram ID у [@userinfobot](https://t.me/userinfobot).
3. В папке проекта:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # на Windows: copy .env.example .env
```

4. Впиши в `.env` токен и свой ID в `ADMIN_IDS`.
5. `python bot.py` (на Windows можно двойным кликом по `run_bot.bat`) — открой бота в Telegram и нажми /start. Для панели мастера — `/admin`.

Тесты: `python -m unittest -v`

## Деплой на VPS (Ubuntu), чтобы бот работал 24/7

```bash
# на сервере под root
apt update && apt install -y python3-venv git
adduser --disabled-password --gecos "" bot
su - bot
git clone <твой-репозиторий> barber_bot && cd barber_bot
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
nano .env          # заполнить как локально
exit

# обратно под root
cp /home/bot/barber_bot/deploy/barber-bot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now barber-bot
systemctl status barber-bot        # должно быть active (running)
journalctl -u barber-bot -f        # живые логи
```

`Restart=always` перезапустит бота, если он упадёт, а `enable` запустит его после перезагрузки сервера.

Обновление: `su - bot -c "cd barber_bot && git pull"` и `systemctl restart barber-bot`.

## Как адаптировать под клиента

- **Услуги и цены**: список `DEFAULT_SERVICES` в `db.py` (применяется к новой базе) или правка таблицы `services`.
- **График**: `WORK_START`, `WORK_END`, `SLOT_MINUTES` в `.env`.
- **Тексты**: в `handlers/client.py`.

## Идеи для развития (хорошие задачи на прокачку)

- Несколько мастеров: таблица `masters`, выбор мастера первым шагом, уникальный индекс по `(master_id, start_at)`
- Разная длительность услуг: хранить `duration` и проверять пересечения интервалов
- Выходные дни и перерывы
- Предоплата через ЮKassa или Telegram Stars
- Добавление услуг из панели мастера
- Переход на PostgreSQL и Docker
