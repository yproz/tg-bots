# Настройка защиты ветки main

## 🔒 Обзор

Ветка `main` должна быть защищена от прямых push и содержать только проверенный код, прошедший ревью.

## 📋 Настройка в GitLab

### 1. Защита ветки main

Перейдите в **Settings → Repository → Protected branches**:

#### Основные настройки:
- **Branch**: `main`
- **Allowed to merge**: `Maintainers` или `Developers + Maintainers`
- **Allowed to push**: `No one` ❌ (запрещаем прямые push)
- **Allowed to force push**: `No one` ❌
- **Code owner approval required**: `Yes` ✅ (если есть CODEOWNERS)

### 2. Merge Request правила

Перейдите в **Settings → General → Merge requests**:

#### Merge request approvals:
- **Approval rules**: Minimum 1 approval
- **Prevent approval by author**: `Yes` ✅
- **Prevent approval by committers**: `Yes` ✅
- **Remove all approvals when commits are added**: `Yes` ✅

#### Merge options:
- **Enable merge when pipeline succeeds**: `Yes` ✅
- **Only allow merge if pipeline succeeds**: `Yes` ✅
- **Only allow merge if all discussions are resolved**: `Yes` ✅
- **Enable squash commits**: `Yes` ✅
- **Encourage squash commits**: `Yes` ✅

## 🔄 Workflow после настройки

### Разработка:
1. Создайте feature branch: `git checkout -b feature/new-feature`
2. Внесите изменения и коммиты
3. Создайте MR в GitLab: `dev ← feature/new-feature`
4. Дождитесь прохождения CI/CD pipeline
5. Запросите ревью от коллег
6. После approval → merge в `dev`

### Релиз:
1. Создайте MR: `main ← dev`
2. Обязательное ревью и тестирование
3. Проверьте, что все CI/CD stages прошли
4. Merge в `main` только после полного approval
5. Автоматический деплой на production (manual trigger)

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
- Создание MR с любой ветки
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
2. Создайте MR без ревью - merge должен быть недоступен
3. Создайте MR с падающими тестами - merge заблокирован

### Команды для проверки:
```bash
# Проверка защиты main
git push origin main
# Ожидаемый результат: remote: GitLab: You are not allowed to push code to protected branches

# Проверка текущих настроек
git remote show origin
git branch -r
```
