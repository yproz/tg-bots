# Настройка секретов в GitLab CI/CD

## ⚠️ КРИТИЧЕСКИ ВАЖНО

**Все ключи из файла `env.example` были скомпрометированы и находятся в публичной истории git!**

Немедленно требуется:
1. Отозвать все старые ключи в соответствующих сервисах
2. Создать новые ключи
3. Настроить их в GitLab CI Variables

## Скомпрометированные ключи (ОТОЗВАТЬ!)

- **Telegram BOT_TOKEN**: `7810372208:AAHxJv97Mh3aHZDbgOsApwkVEHFi4si7K-0`
- **OZON_API_KEY_SEB**: `f5799144-b8e1-45ad-aaea-5ec570ad241c`
- **OZON_API_KEY_DF**: `268c6e82-ff66-4944-aa16-9665f153c07d`
- **PARSER_API_KEY**: `WKLculgyZrUuldii7Oq0yNmIKdE=`

## Настройка GitLab CI Variables

1. Перейдите в GitLab проект: https://gitlab.com/y.prozoroff/spp-monitoring-bot
2. Settings → CI/CD → Variables
3. Добавьте следующие переменные (Protected ✓, Masked ✓):

### Обязательные секреты

- `BOT_TOKEN` - Новый Telegram Bot Token
- `PARSER_API_KEY_SEB` - API ключ парсера для SEB
- `PARSER_API_KEY_DF` - API ключ парсера для DF
- `OZON_API_KEY_SEB` - Ozon API Key для SEB
- `OZON_API_KEY_DF` - Ozon API Key для DF
- `WB_API_KEY_SEB` - Wildberries API Key для SEB
- `WB_API_KEY_DF` - Wildberries API Key для DF

### Не секретные (Protected ✓)

- `OZON_CLIENT_ID_SEB` - Ozon Client ID для SEB
- `OZON_CLIENT_ID_DF` - Ozon Client ID для DF

## Действия по восстановлению безопасности

1. **Telegram Bot**: @BotFather → `/revoke` → `/newtoken`
2. **Ozon API**: Seller API → отозвать старые → создать новые
3. **Parser API**: связаться с поставщиком → отозвать → получить новые
4. **Wildberries**: личный кабинет → создать новые API ключи
