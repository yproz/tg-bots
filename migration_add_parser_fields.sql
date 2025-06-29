-- Миграция для добавления полей парсера в таблицу clients
-- Выполнить: docker-compose exec db psql -U postgres -d pricebot -f /app/migration_add_parser_fields.sql

-- Добавляем новые колонки в таблицу clients
ALTER TABLE clients 
ADD COLUMN IF NOT EXISTS parser_api_key TEXT,
ADD COLUMN IF NOT EXISTS omni_url TEXT,
ADD COLUMN IF NOT EXISTS omni_api_key TEXT;

-- Обновляем существующего клиента SEB с данными из конфига
UPDATE clients 
SET 
    parser_api_key = 'WKLculgyZrUuldii7Oq0yNmIKdE=',
    omni_url = 'https://ocs.omnicrm.ru/api/v1/shops/b3990cd9-193c-423c-b757-f974ed58b3f9',
    omni_api_key = 'fe576fbfa9244716f0941850e89cb56b'
WHERE id = 'SEB';

-- Проверяем результат
SELECT id, name, parser_api_key IS NOT NULL as has_parser_key, omni_url IS NOT NULL as has_omni_url 
FROM clients; 