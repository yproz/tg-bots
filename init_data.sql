-- Инициализация данных для клиента SEB
INSERT INTO clients (id, name, group_chat_id, parser_api_key, omni_url, omni_api_key) 
VALUES (
    'SEB', 
    'SEB', 
    123456789,  -- замените на реальный chat_id
    'WKLculgyZrUuldii7Oq0yNmIKdE=',
    'https://ocs.omnicrm.ru/api/v1/shops/b3990cd9-193c-423c-b757-f974ed58b3f9',
    'fe576fbfa9244716f0941850e89cb56b'
) ON CONFLICT (id) DO UPDATE SET
    parser_api_key = EXCLUDED.parser_api_key,
    omni_url = EXCLUDED.omni_url,
    omni_api_key = EXCLUDED.omni_api_key;

-- Создаем аккаунт Ozon для SEB
INSERT INTO accounts (client_id, market, account_id, api_key, region, ozon_client_id, market_price, showcase_price)
VALUES (
    'SEB',
    'ozon',
    'fm',
    'a5fe0991-d12c-4942-9bf6-ceb5b33ef50b',
    'Москва',
    '2229598',
    'custom:ozon_current_price_nsk',
    'custom:ozon_promo_price_nsk'
) ON CONFLICT (client_id, market, account_id) DO UPDATE SET
    api_key = EXCLUDED.api_key,
    region = EXCLUDED.region,
    ozon_client_id = EXCLUDED.ozon_client_id,
    market_price = EXCLUDED.market_price,
    showcase_price = EXCLUDED.showcase_price;

-- Проверяем результат
SELECT 
    c.id, 
    c.name, 
    c.parser_api_key IS NOT NULL as has_parser_key,
    c.omni_url IS NOT NULL as has_omni_url,
    a.account_id,
    a.market
FROM clients c
LEFT JOIN accounts a ON c.id = a.client_id; 