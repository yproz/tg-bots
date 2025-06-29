# Настройка CI/CD Pipeline

## 🚀 Обзор Pipeline

Pipeline состоит из 4 стадий:
1. **lint** - Проверка качества кода
2. **test** - Запуск тестов
3. **build** - Сборка Docker образа
4. **deploy** - Деплой на сервера

## 📋 Стадии Pipeline

### 1. Lint Stage
- **flake8**: Проверка стиля Python кода
- **black**: Проверка форматирования  
- **isort**: Проверка сортировки импортов
- **mypy**: Проверка типов (allow_failure)

### 2. Test Stage
- **unit tests**: Запуск pytest с coverage
- **services**: PostgreSQL + Redis для тестов
- **artifacts**: Coverage report в XML

### 3. Build Stage
- **Docker**: Сборка образа приложения
- **Registry**: Отправка в GitLab Container Registry
- **Tags**: `$CI_COMMIT_SHA` + `latest`

### 4. Deploy Stage
- **production**: Автодеплой ветки `main` (manual)

## 🔧 Настройка GitLab Variables

### Обязательные переменные для CI/CD

Перейдите в **Settings → CI/CD → Variables** и добавьте:

#### Деплой переменные (Protected ✓)
| Переменная | Описание | Пример |
|------------|----------|--------|
| `SSH_PRIVATE_KEY` | SSH ключ для деплоя | `-----BEGIN OPENSSH PRIVATE KEY-----` |
| `DEPLOY_HOST` | IP/домен сервера | `89.169.152.79` |
| `DEPLOY_USER` | Пользователь на сервере | `price-robot-vm` |
| `DEPLOY_PATH` | Путь к проекту на сервере | `/home/price-robot-vm/pricebot` |

#### Секреты приложения (Protected ✓, Masked ✓)
См. файл `docs/GITLAB_SECRETS_SETUP.md` для полного списка.

## 🔀 Правила запуска

### Lint + Test + Build
Запускаются при:
- Merge Request в любую ветку
- Push в ветки `main`, `dev`

### Deploy
- **production**: Manual для ветки `main`

## 🐛 Решение проблем

### Ошибки Lint
```bash
# Локальное исправление
pip install -r requirements-dev.txt

# Автоформатирование
black .
isort .

# Проверка
flake8 .
mypy bot/ services/ db/ tasks/
```

### Ошибки тестов
```bash
# Локальный запуск тестов
pytest test_basic.py test_excel_upload.py -v

# С покрытием
pytest --cov=. --cov-report=html
```

## 🔄 Workflow

### Разработка
1. Создайте feature branch от `dev`
2. Внесите изменения
3. Создайте MR в `dev`
4. Pipeline проверит качество кода
5. После approve → merge в `dev`

### Релиз
1. Создайте MR из `dev` в `main`
2. После review → merge в `main`
3. Manual deploy на production
