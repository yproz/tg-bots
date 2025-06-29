-- Миграция для добавления полей СПП мониторинга
-- Выполнить: docker-compose exec db psql -U pricebot -d pricebot -f /app/migration_add_spp_fields.sql

-- Добавляем новые колонки в таблицу accounts
ALTER TABLE accounts 
ADD COLUMN IF NOT EXISTS topic_id BIGINT;

-- Добавляем новую колонку в таблицу raw_prices
ALTER TABLE raw_prices 
ADD COLUMN IF NOT EXISTS discount_percent NUMERIC;

-- Создаем таблицу parser_tasks
CREATE TABLE IF NOT EXISTS parser_tasks (
    id BIGSERIAL PRIMARY KEY,
    client_id TEXT REFERENCES clients(id),
    account_id INTEGER REFERENCES accounts(id),
    task_id TEXT UNIQUE NOT NULL,
    market TEXT NOT NULL,
    status TEXT NOT NULL,
    report_url TEXT,
    created_at DATE NOT NULL,
    completed_at DATE
);

-- Создаем индексы для оптимизации
CREATE INDEX IF NOT EXISTS idx_parser_tasks_client_id ON parser_tasks(client_id);
CREATE INDEX IF NOT EXISTS idx_parser_tasks_status ON parser_tasks(status);
CREATE INDEX IF NOT EXISTS idx_raw_prices_discount ON raw_prices(discount_percent);

-- Проверяем результат
SELECT 
    'accounts' as table_name,
    column_name,
    data_type
FROM information_schema.columns 
WHERE table_name = 'accounts' AND column_name IN ('topic_id')
UNION ALL
SELECT 
    'raw_prices' as table_name,
    column_name,
    data_type
FROM information_schema.columns 
WHERE table_name = 'raw_prices' AND column_name IN ('discount_percent')
UNION ALL
SELECT 
    'parser_tasks' as table_name,
    'table_created' as column_name,
    'exists' as data_type
WHERE EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'parser_tasks'); 