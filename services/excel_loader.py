import pandas as pd
import tempfile
import os
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import asyncio

# Требуемый набор колонок Excel для СПП мониторинга
COLS = ["client_id", "market", "account_id", "product_code", "product_name", "product_link"]

TEMPLATE_PATH = "/tmp/products_template.xlsx"

async def create_error_file(error_rows, errors):
    """Создает Excel файл с ошибками."""
    if not error_rows:
        return None
    
    error_df = pd.DataFrame(error_rows, columns=["Строка"] + COLS)
    error_file = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    error_df.to_excel(error_file.name, index=False)
    return error_file.name

async def generate_template():
    """Создаёт файл-шаблон XLSX с примерами данных для СПП мониторинга."""
    # Создаем примеры данных
    example_data = [
        {
            "client_id": "SEB",
            "market": "ozon", 
            "account_id": "fm",
            "product_code": "1101001001",
            "product_name": "Футболка мужская хлопок",
            "product_link": "https://www.ozon.ru/product/1101001001"
        },
        {
            "client_id": "SEB",
            "market": "ozon",
            "account_id": "fm", 
            "product_code": "1101001020",
            "product_name": "Джинсы классические",
            "product_link": "https://www.ozon.ru/product/1101001020"
        },
        {
            "client_id": "SEB",
            "market": "wb",
            "account_id": "fm",
            "product_code": "2000069940", 
            "product_name": "Кроссовки спортивные",
            "product_link": "https://www.wildberries.ru/catalog/2000069940"
        }
    ]
    
    df = pd.DataFrame(example_data)
    df.to_excel(TEMPLATE_PATH, index=False)
    return TEMPLATE_PATH

def sync_load_excel(path: str):
    """Синхронная версия загрузки Excel с использованием только SQL запросов."""
    import os
    
    # Получаем DATABASE_URL из переменных окружения и конвертируем в синхронный
    database_url = os.getenv('DATABASE_URL', 'postgresql+asyncpg://pricebot:pricebot@db/pricebot')
    sync_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    
    # Создаем синхронный engine
    engine = create_engine(sync_url)
    
    try:
        df = pd.read_excel(path, dtype=str).fillna("")
    except Exception as e:
        raise ValueError(f"Ошибка чтения файла: {str(e)}")
    
    missing = [c for c in COLS if c not in df.columns]
    if missing:
        raise ValueError(f"В файле отсутствуют колонки: {missing}")

    ok, errors = 0, []
    error_rows = []

    # Предварительно проверяем все product_code на дубликаты в файле
    seen_products = {}
    for idx, row in df.iterrows():
        row_data = {k: str(v).strip() for k, v in row.items()}
        if row_data["client_id"] and row_data["product_code"]:
            key = (row_data["client_id"], row_data["product_code"])
            if key in seen_products:
                row_num = idx + 2
                error_msg = f"Строка {row_num}: дубликат product_code '{row_data['product_code']}' в загружаемом файле"
                errors.append(error_msg)
                error_rows.append([row_num] + [row_data.get(col, "") for col in COLS])
                continue
            seen_products[key] = True

    # Обрабатываем записи синхронно с использованием только SQL
    with engine.connect() as conn:
        for idx, row in df.iterrows():
            row_num = idx + 2  # Excel строки начинаются с 1, +1 для заголовка
            row_data = {k: str(v).strip() for k, v in row.items()}
            
            # Пропускаем строки с уже найденными дубликатами
            key = (row_data["client_id"], row_data["product_code"])
            if key in seen_products and seen_products[key] is not True:
                continue
                
            # Валидация обязательных полей
            if not row_data["client_id"]:
                error_msg = f"Строка {row_num}: пустой client_id"
                errors.append(error_msg)
                error_rows.append([row_num] + [row_data.get(col, "") for col in COLS])
                continue
                
            if not row_data["market"]:
                error_msg = f"Строка {row_num}: пустой market"
                errors.append(error_msg)
                error_rows.append([row_num] + [row_data.get(col, "") for col in COLS])
                continue
                
            if row_data["market"] not in ["ozon", "wb"]:
                error_msg = f"Строка {row_num}: неверный market '{row_data['market']}' (должен быть ozon или wb)"
                errors.append(error_msg)
                error_rows.append([row_num] + [row_data.get(col, "") for col in COLS])
                continue
                
            if not row_data["account_id"]:
                error_msg = f"Строка {row_num}: пустой account_id"
                errors.append(error_msg)
                error_rows.append([row_num] + [row_data.get(col, "") for col in COLS])
                continue
                
            if not row_data["product_code"]:
                error_msg = f"Строка {row_num}: пустой product_code"
                errors.append(error_msg)
                error_rows.append([row_num] + [row_data.get(col, "") for col in COLS])
                continue
                
            if not row_data["product_name"]:
                error_msg = f"Строка {row_num}: пустое product_name"
                errors.append(error_msg)
                error_rows.append([row_num] + [row_data.get(col, "") for col in COLS])
                continue
            
            try:
                # Найдём account.id с помощью прямого SQL запроса
                acc_query = text("""
                    SELECT id FROM accounts 
                    WHERE client_id = :client_id 
                    AND market = :market 
                    AND account_id = :account_id
                """)
                
                result = conn.execute(acc_query, {
                    "client_id": row_data["client_id"],
                    "market": row_data["market"],
                    "account_id": row_data["account_id"]
                })
                acc_row = result.fetchone()
                
                if not acc_row:
                    error_msg = f"Строка {row_num}: аккаунт не найден ({row_data['client_id']}/{row_data['market']}/{row_data['account_id']})"
                    errors.append(error_msg)
                    error_rows.append([row_num] + [row_data.get(col, "") for col in COLS])
                    continue
                
                acc_id = acc_row[0]
                
                # Используем PostgreSQL-специфичный upsert с прямым SQL
                upsert_query = text("""
                    INSERT INTO products (client_id, account_id, product_code, product_name, product_link)
                    VALUES (:client_id, :account_id, :product_code, :product_name, :product_link)
                    ON CONFLICT (account_id, product_code)
                    DO UPDATE SET
                        product_name = EXCLUDED.product_name,
                        product_link = EXCLUDED.product_link,
                        client_id = EXCLUDED.client_id
                """)
                
                conn.execute(upsert_query, {
                    "client_id": row_data["client_id"],
                    "account_id": acc_id,
                    "product_code": row_data["product_code"],
                    "product_name": row_data["product_name"],
                    "product_link": row_data["product_link"]
                })
                
                conn.commit()
                ok += 1
                
            except Exception as e:
                conn.rollback()
                error_msg = f"Строка {row_num}: ошибка при сохранении: {str(e)}"
                errors.append(error_msg)
                error_rows.append([row_num] + [row_data.get(col, "") for col in COLS])
    
    return ok, errors, error_rows

async def load_excel(path: str):
    """Парсит Excel и пишет новые товары в таблицу products.

    Возвращает кортеж: (кол-во вставленных, список ошибок, путь к файлу с ошибками)
    """
    # Запускаем синхронную версию в отдельном потоке
    loop = asyncio.get_event_loop()
    ok, errors, error_rows = await loop.run_in_executor(None, sync_load_excel, path)
    
    # Создаем файл с ошибками если есть
    error_file_path = None
    if error_rows:
        error_file_path = await create_error_file(error_rows, errors)
    
    return ok, errors, error_file_path 