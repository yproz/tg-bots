-- Миграция для добавления таблиц orders и results
-- Создаем таблицу orders
CREATE TABLE IF NOT EXISTS orders (
    id BIGSERIAL PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES clients(id),
    task_id TEXT NOT NULL UNIQUE,
    region TEXT NOT NULL,
    market TEXT NOT NULL,
    status TEXT NOT NULL,
    report_url TEXT,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

-- Создаем таблицу results
CREATE TABLE IF NOT EXISTS results (
    id BIGSERIAL PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES clients(id),
    task_id TEXT NOT NULL,
    product_id INTEGER NOT NULL REFERENCES products(id),
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    product_code TEXT NOT NULL,
    product_name TEXT NOT NULL,
    product_link TEXT,
    market_price NUMERIC,
    showcase_price NUMERIC,
    timestamp TIMESTAMP NOT NULL,
    UNIQUE(client_id, task_id, product_code)
);

-- Создаем индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_orders_client_status ON orders(client_id, status);
CREATE INDEX IF NOT EXISTS idx_orders_task_id ON orders(task_id);
CREATE INDEX IF NOT EXISTS idx_results_client_task ON results(client_id, task_id);
CREATE INDEX IF NOT EXISTS idx_results_product_code ON results(product_code); 