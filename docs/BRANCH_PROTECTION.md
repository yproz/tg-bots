# Настройка защиты ветки main

## 🔒 Обзор

Ветка `main` должна быть защищена от прямых push и содержать только проверенный код, прошедший ревью.

## 📋 Настройка в GitHub

### 1. Защита ветки main

Перейдите в **Settings → Branches → Add rule**:

#### Основные настройки:
- **Branch name pattern**: `main`
- **Restrict pushes that create files**: ✅ (запрещаем прямые push)
- **Require a pull request before merging**: ✅
- **Require status checks to pass before merging**: ✅
- **Require conversation resolution before merging**: ✅
- **Require review from CODEOWNERS**: ✅ (если есть CODEOWNERS)

### 2. Pull Request правила

В том же разделе **Branch protection rules** настройте:

#### Pull request approvals:
- **Require pull request reviews before merging**: ✅
- **Required number of reviewers**: 1
- **Dismiss stale reviews when new commits are pushed**: ✅
- **Require review from CODEOWNERS**: ✅

#### Status checks:
- **Require status checks to pass before merging**: ✅
- **Require branches to be up to date before merging**: ✅
- **Status checks**: добавьте `lint`, `test`, `build`

#### Additional settings:
- **Allow squash merging**: ✅
- **Allow merge commits**: ❌ (для чистой истории)
- **Allow rebase merging**: ✅

## 🔄 Workflow после настройки

### Разработка:
1. Создайте feature branch: `git checkout -b feature/new-feature`
2. Внесите изменения и коммиты
3. Создайте PR в GitHub: `dev ← feature/new-feature`
4. Дождитесь прохождения GitHub Actions
5. Запросите ревью от коллег
6. После approval → merge в `dev`

### Релиз:
1. Создайте PR: `main ← dev`
2. Обязательное ревью и тестирование
3. Проверьте, что все GitHub Actions прошли
4. Merge в `main` только после полного approval
5. Автоматический деплой на production (environment protection)

## 🚫 Запрещенные действия

### Нельзя:
- `git push origin main` (прямой push)
- `git push --force origin main` (force push)
- Коммиты с debug/print/console.log
- Коммиты с секретными ключами
- Merge без ревью
- Merge при падающих тестах

### Можно:
- Push в feature branches
- Создание PR с любой ветки
- Merge после успешного ревью
- Squash merge для чистой истории

## 🔧 Автоматизация

### Pre-commit hooks (опционально)

```bash
pip install pre-commit
pre-commit install
```

## 📊 Мониторинг

### Проверка настроек:
1. Попробуйте push в main - должен быть заблокирован
2. Создайте PR без ревью - merge должен быть недоступен
3. Создайте PR с падающими тестами - merge заблокирован

### Команды для проверки:
```bash
# Проверка защиты main
git push origin main
# Ожидаемый результат: remote: error: GH006: Protected branch update failed for refs/heads/main

# Проверка текущих настроек
git remote show origin
git branch -r
```
