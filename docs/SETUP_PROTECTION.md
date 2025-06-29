# Пошаговая настройка защиты ветки main

## 🚀 Быстро настроить

### 1. Откройте GitLab проект
https://gitlab.com/y.prozoroff/spp-monitoring-bot

### 2. Защитите ветку main
**Settings** → **Repository** → **Protected branches**

```
Branch: main
Allowed to merge: Maintainers  
Allowed to push: No one ❌
Allowed to force push: No one ❌
Code owner approval required: ✅
```

Нажмите **Protect**.

### 3. Настройте Merge Request правила  
**Settings** → **General** → **Merge requests**

#### Approvals:
```
Approval rules: 1 approval required
Prevent approval by author: ✅
Remove approvals when commits added: ✅  
```

#### Merge options:
```
Merge only if pipeline succeeds: ✅
Merge only if all discussions resolved: ✅
Enable squash commits: ✅
```

Нажмите **Save changes**.

### 4. Проверьте защиту
Попробуйте выполнить:
```bash
git push origin main
```

Должна появиться ошибка:
```
remote: GitLab: You are not allowed to push code to protected branches on this project.
```

## ✅ Готово!

Теперь в ветку `main` можно вносить изменения только через Merge Request с обязательным ревью.

### Workflow:
1. Создаете feature branch от `dev`
2. Вносите изменения 
3. Создаете MR: `dev ← feature/my-feature`
4. После CI/CD и ревью → merge в `dev`
5. Для релиза: MR `main ← dev` с обязательным ревью

## 📋 Дополнительно (опционально)

### Pre-commit hooks (локально)
```bash
pip install pre-commit
pre-commit install
```

Теперь код будет проверяться автоматически перед каждым коммитом.
