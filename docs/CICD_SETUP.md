# Настройка GitHub Actions Pipeline

## 🚀 Обзор Pipeline

GitHub Actions Workflow состоит из 4 джобов:
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

### 3. Build Job
- **Docker**: Сборка образа приложения
- **Registry**: Отправка в GitHub Container Registry (ghcr.io)
- **Tags**: `$GITHUB_SHA` + `latest`

### 4. Deploy Job
- **production**: Автодеплой ветки `main` (environment protection)

## 🔧 Настройка GitHub Secrets

### Обязательные секреты для CI/CD

Перейдите в **Settings → Secrets and variables → Actions** и добавьте:

#### Деплой переменные (Protected ✓)
| Переменная | Описание | Пример |
|------------|----------|--------|
| `SSH_PRIVATE_KEY` | SSH ключ для деплоя | `-----BEGIN OPENSSH PRIVATE KEY-----` |
| `DEPLOY_HOST` | IP/домен сервера | `89.169.152.79` |
| `DEPLOY_USER` | Пользователь на сервере | `price-robot-vm` |
| `DEPLOY_PATH` | Путь к проекту на сервере | `/home/price-robot-vm/pricebot` |

#### Секреты приложения (Environment secrets)
См. файл `docs/GITHUB_SECRETS_SETUP.md` для полного списка.

## 🔀 Правила запуска

### Lint + Test + Build
Запускаются при:
- Pull Request в любую ветку
- Push в ветки `main`, `dev`

### Deploy
- **production**: Автоматически для ветки `main` (с environment protection)

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
3. Создайте PR в `dev`
4. GitHub Actions проверит качество кода
5. После approve → merge в `dev`

### Релиз
1. Создайте PR из `dev` в `main`
2. После review → merge в `main`
3. Автоматический deploy на production
