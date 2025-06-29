# СПП Мониторинг Бот

Система для отслеживания изменений СПП (Совместных инвестиций) на маркетплейсах Ozon и Wildberries через Telegram бот.

## 🎯 Основные функции

- **Сбор цен через парсер API** — автоматический сбор цен с маркетплейсов
- **Сравнение с прошлым периодом** — анализ изменений СПП
- **Отчеты в Telegram** — ежедневные сводки с кнопками для подробных отчетов
- **Загрузка товаров через Excel** — удобный импорт списков товаров
- **Мультиклиентская поддержка** — работа с несколькими клиентами одновременно

## 📊 Формат отчетов

### Ежедневная сводка
```
📊 СПП Мониторинг: SEB
📅 15.01.2025

🔻 5 товаров снизили СПП
🔺 3 товара повысили СПП
➖ 12 товаров без изменений

📈 Всего отслеживается: 22 товара

Нажмите кнопку ниже для подробного отчета
```

### Подробный Excel отчет
| Артикул | Название | Цена на витрине | Цена из маркетплейса | % скидки |
|---------|----------|-----------------|---------------------|----------|
| 1101001001 | Футболка мужская | 899 | 1299 | 30.8 |
| 1101001020 | Джинсы классические | 1499 | 1999 | 25.0 |

## 🏗 Архитектура

```
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│ Telegram Bot  │    │ Celery Beat   │    │ Celery Worker │
│  (aiogram 3)  │    │ (Scheduler)   │    │ (Tasks, v2)   │
└───────────────┘    └───────────────┘    └───────────────┘
        │                    │                    │
        ▼                    ▼                    ▼
┌─────────────────┐    ┌────────────┐    ┌─────────────────┐
│   PostgreSQL    │    │   Redis    │    │  Parser API     │
│ (SQLAlchemy v2) │    │ (Broker)   │    │  (Market Data)  │
└─────────────────┘    └────────────┘    └─────────────────┘
```

- Все задачи и логика реализованы в `tasks/app_v2.py` и `services/parser_service_v2.py`.
- Отчеты отправляются **только после появления новых данных от парсера** (записи showcase_price в БД).
- Регулярная проверка готовности отчетов — каждые 3 минуты (Celery Beat).

## 🚀 Быстрый старт

### 1. Клонирование и настройка

```bash
# Клонируем репозиторий
git clone git@github.com:yproz/tg-bots.git
cd tg-bots

# Копируем пример конфигурации
cp env.example .env

# Редактируем переменные окружения
nano .env
```

### 2. Подключение к Production VM

```bash
# Настройка SSH alias (выполнить один раз)
echo "Host pricebot-vm
    HostName 89.169.152.79
    User price-robot-vm
    IdentityFile /Users/yuprozorov/ssh-key
    IdentitiesOnly yes" >> ~/.ssh/config

# Подключение к серверу
ssh pricebot-vm

# Проверка статуса контейнеров на сервере
cd pricebot && docker-compose ps
```

### 3. Переменные окружения (.env)

```env
# Telegram Bot
BOT_TOKEN=your_telegram_bot_token
BOT_USERNAME=your_bot_username

# База данных
DATABASE_URL=postgresql+asyncpg://pricebot:password@db:5432/pricebot

# Redis
CELERY_BROKER=redis://redis:6379/0
CELERY_BACKEND=redis://redis:6379/0

# Парсер API (настраивается для каждого клиента)
PARSER_API_KEY=your_parser_api_key
```

### 4. Запуск через Docker

```bash
# Создаем и запускаем контейнеры
docker-compose up -d

# Проверяем статус
docker-compose ps

# Смотрим логи
docker-compose logs -f bot
```

### 5. Настройка клиентов и аккаунтов

Через Telegram бот:

1. `/add_client` — добавление клиента
2. `/add_account` — добавление аккаунта маркетплейса
3. `/get_template` — получение шаблона Excel
4. Загрузить Excel с товарами

## 📋 Команды бота

### Основные команды
- `/start` — приветствие и список команд
- `/add_client` — мастер добавления клиента
- `/add_account` — мастер добавления аккаунта
- `/get_template` — получение шаблона Excel для товаров
- `/collect_now` — запуск сбора цен прямо сейчас

### Управление товарами
- Отправьте Excel файл с товарами для импорта
- Формат: `client_id | market | account_id | product_code | product_name | product_link`

### Отчеты
- `/snapshot YYYY-MM-DD` — генерация отчета за дату
- Ежедневные сводки отправляются автоматически **после появления новых данных**

## ⏰ Расписание задач

- **Каждые 3 минуты** — Проверка готовности отчетов от парсера (Celery Beat)
- **Отправка отчетов** — Сразу после записи showcase_price в БД (по факту появления новых данных)

## 🗄 Структура базы данных

### Основные таблицы
- `clients` — клиенты системы
- `accounts` — аккаунты маркетплейсов
- `products` — товары для мониторинга
- `orders` — заказы на сбор данных (task_id, статус, ссылка на отчет)
- `results` — результаты по товарам (цены, скидки, showcase_price)

### Ключевые поля
- `parser_api_key` — ключ для работы с парсером
- `discount_percent` — процент скидки СПП
- `group_chat_id` — ID чата для уведомлений

## 🔧 Разработка

### Структура проекта
```
pricebot/
├── .gitlab/            # GitLab конфигурация
│   └── CODEOWNERS      # Автоназначение ревьюеров
├── bot/                # Telegram бот
│   └── main.py         # Основной файл бота
├── db/                 # База данных
│   ├── models.py       # SQLAlchemy модели
│   └── session.py      # Настройки сессий
├── docs/               # Документация
│   ├── ARCHITECTURE.md      # Архитектура системы
│   ├── BRANCH_PROTECTION.md # Защита веток
│   ├── CICD_SETUP.md       # Настройка CI/CD
│   ├── GITLAB_SECRETS_SETUP.md # Настройка секретов
│   └── SETUP_PROTECTION.md  # Быстрая настройка защиты
├── services/           # Бизнес-логика
│   ├── collectors/     # Коллекторы данных
│   │   ├── ozon.py     # Ozon API
│   │   └── wb.py       # Wildberries API
│   ├── parser_service_v2.py # Работа с парсером
│   └── excel_loader.py      # Импорт товаров
├── tasks/              # Celery задачи
│   └── app_v2.py       # Все задачи (актуальная версия)
├── .flake8             # Конфигурация flake8
├── .gitlab-ci.yml      # CI/CD pipeline
├── .pre-commit-config.yaml # Pre-commit hooks
├── docker-compose.yml  # Docker конфигурация (prod)
├── docker-compose.local.yml # Docker конфигурация (dev)
├── pyproject.toml      # Конфигурация инструментов
├── requirements.txt    # Зависимости (prod)
├── requirements-dev.txt # Зависимости (dev)
└── TASKS.md           # Чек-лист синхронизации
```

### Локальная разработка

```bash
# Установка зависимостей
pip install -r requirements.txt

# Запуск базы данных
docker-compose up db redis -d

# Запуск бота
python -m bot.main

# Запуск Celery worker
celery -A tasks.app_v2 worker --loglevel=info

# Запуск Celery beat
celery -A tasks.app_v2 beat --loglevel=info
```

## 🚀 CI/CD Pipeline

Проект использует GitHub Actions для автоматизации тестирования, сборки и деплоя.

### Стадии Pipeline

1. **lint** - Проверка качества кода (flake8, black, isort, mypy)
2. **test** - Запуск тестов с PostgreSQL + Redis
3. **build** - Сборка Docker образа в GitHub Container Registry
4. **deploy** - Деплой на production сервер (environment protection)

### Настройка CI/CD

```bash
# Конфигурация линтеров
pip install -r requirements-dev.txt

# Локальная проверка кода
black .
isort .
flake8 .
mypy bot/ services/ db/ tasks/

# Запуск тестов
pytest test_basic.py test_excel_upload.py -v
```

### Workflow разработки

1. **Feature branch**: Создайте ветку от `dev`
2. **Изменения**: Внесите изменения и коммиты  
3. **Pull Request**: Создайте PR в GitHub
4. **CI/CD**: Дождитесь прохождения GitHub Actions
5. **Code Review**: Запросите ревью (обязательно)
6. **Merge**: После approval → merge в `dev`

### Релиз в production

1. **Release PR**: Создайте PR `main ← dev`
2. **Testing**: Проведите дополнительное тестирование
3. **Approval**: Получите обязательное ревью
4. **Deploy**: Автоматический деплой с environment protection

> **Важно**: Ветка `main` защищена от прямых push. Все изменения только через PR с ревью.

## 📦 Деплой

### Автоматический деплой

После merge в `main`:
1. GitHub Actions собирает Docker образ
2. Автоматический деплой с environment protection
3. Обновление контейнеров на сервере

### Ручной деплой на сервере

```bash
# Подключение к серверу
ssh pricebot-vm

# Обновление кода
cd pricebot
git pull origin main

# Обновление контейнеров
docker-compose pull
docker-compose up -d

# Проверка статуса
docker-compose ps
```

### Откат изменений

```bash
# Откат к предыдущему коммиту
git reset --hard HEAD~1
docker-compose up -d

# Или откат к конкретному коммиту
git reset --hard <commit-hash>
docker-compose up -d
```

## 📝 Миграции

```bash
# Применение миграций
docker-compose exec db psql -U pricebot -d pricebot -f /app/migration_add_orders_results.sql
```

## 🐛 Отладка

### Логи
```bash
# Логи бота
docker-compose logs -f bot

# Логи Celery
docker-compose logs -f worker

# Логи базы данных
docker-compose logs -f db
```

### Тестирование
```bash
# Запуск тестов
python test_basic.py
```

## 🧹 Очистка служебных файлов

Для освобождения места можно безопасно удалить все папки `__pycache__`:
```bash
find . -name "__pycache__" -type d -exec rm -r {} +
```

## 📞 Поддержка

При возникновении проблем:

1. Проверьте логи контейнеров
2. Убедитесь в правильности настроек API ключей
3. Проверьте подключение к базе данных
4. Обратитесь к документации парсера API

## 🔄 Обновления

Для обновления системы:

```bash
# Остановка контейнеров
docker-compose down

# Обновление кода
git pull

# Пересборка и запуск
docker-compose up -d --build
```

## 📚 Документация

- [📋 Чек-лист синхронизации](TASKS.md) - Пошаговый план настройки проекта
- [🏗 Архитектура системы](docs/ARCHITECTURE.md) - Детальное описание компонентов
- [🚀 Настройка CI/CD](docs/CICD_SETUP.md) - Конфигурация GitLab Pipeline
- [🔒 Защита веток](docs/BRANCH_PROTECTION.md) - Настройка защиты main ветки
- [🔐 Управление секретами](docs/GITLAB_SECRETS_SETUP.md) - Работа с API ключами
- [⚡ Быстрая настройка](docs/SETUP_PROTECTION.md) - Пошаговая инструкция

## 🔗 Полезные ссылки

- [GitHub Repository](https://github.com/yproz/tg-bots)
- [Production Server](ssh://pricebot-vm) - `ssh pricebot-vm`
- [GitHub Actions](https://github.com/yproz/tg-bots/actions)
- [Container Registry](https://github.com/yproz/tg-bots/pkgs/container/tg-bots)

## 📄 Лицензия

Проект разработан для внутреннего использования. 