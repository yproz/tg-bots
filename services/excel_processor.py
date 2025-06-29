# services/excel_processor.py
"""
Модуль для обработки Excel файлов с товарами.
Разбит на отдельные функции согласно принципу Single Responsibility.
"""

import os
import pandas as pd
from typing import List, Dict, Tuple, Optional, Set, Any
from dataclasses import dataclass
from sqlalchemy import create_engine, text
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)

# Константы
REQUIRED_COLUMNS = ["client_id", "market", "account_id", "product_code", "product_name", "product_link"]
ALLOWED_MARKETS = ["ozon", "wb"]


@dataclass
class ValidationError:
    """Ошибка валидации строки."""
    row_number: int
    error_message: str
    row_data: List[str]


@dataclass
class ProcessingResult:
    """Результат обработки Excel файла."""
    success_count: int
    errors: List[str]
    error_rows: List[List[str]]


def create_sync_engine() -> Any:
    """
    Создает синхронный engine для работы с БД.
    
    Returns:
        SQLAlchemy Engine
    """
    try:
        database_url = os.getenv('DATABASE_URL', 'postgresql+asyncpg://pricebot:pricebot@db/pricebot')
        sync_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
        
        return create_engine(sync_url)
        
    except Exception as e:
        logger.error(f"Ошибка создания database engine: {e}")
        raise


def read_excel_file(file_path: str) -> pd.DataFrame:
    """
    Читает Excel файл и возвращает DataFrame.
    
    Args:
        file_path: Путь к Excel файлу
        
    Returns:
        DataFrame с данными
        
    Raises:
        ValueError: При ошибке чтения файла
    """
    try:
        df = pd.read_excel(file_path, dtype=str).fillna("")
        logger.info(f"Успешно прочитан Excel файл: {len(df)} строк")
        return df
        
    except Exception as e:
        error_msg = f"Ошибка чтения файла: {str(e)}"
        logger.error(error_msg)
        raise ValueError(error_msg)


def validate_excel_columns(df: pd.DataFrame) -> None:
    """
    Валидирует наличие необходимых колонок в DataFrame.
    
    Args:
        df: DataFrame для валидации
        
    Raises:
        ValueError: При отсутствии необходимых колонок
    """
    missing_columns = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    
    if missing_columns:
        error_msg = f"В файле отсутствуют колонки: {missing_columns}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    logger.info("Все необходимые колонки присутствуют")


def check_for_duplicates(df: pd.DataFrame) -> Set[Tuple[str, str]]:
    """
    Проверяет наличие дубликатов product_code в файле.
    
    Args:
        df: DataFrame для проверки
        
    Returns:
        Set дубликатов (client_id, product_code)
    """
    seen_products = {}
    duplicates = set()
    
    for idx, row in df.iterrows():
        row_data = {k: str(v).strip() for k, v in row.items()}
        
        if row_data["client_id"] and row_data["product_code"]:
            key = (row_data["client_id"], row_data["product_code"])
            
            if key in seen_products:
                duplicates.add(key)
                logger.warning(f"Найден дубликат: {key} в строке {idx + 2}")
            else:
                seen_products[key] = idx + 2
    
    if duplicates:
        logger.warning(f"Обнаружено {len(duplicates)} дубликатов в файле")
    
    return duplicates


def validate_row_data(row_data: Dict[str, str], row_number: int) -> Optional[str]:
    """
    Валидирует данные строки.
    
    Args:
        row_data: Данные строки
        row_number: Номер строки в Excel
        
    Returns:
        Сообщение об ошибке или None если валидация прошла
    """
    # Проверка обязательных полей
    if not row_data["client_id"]:
        return f"Строка {row_number}: пустой client_id"
    
    if not row_data["market"]:
        return f"Строка {row_number}: пустой market"
    
    if row_data["market"] not in ALLOWED_MARKETS:
        return f"Строка {row_number}: неверный market '{row_data['market']}' (должен быть {' или '.join(ALLOWED_MARKETS)})"
    
    if not row_data["account_id"]:
        return f"Строка {row_number}: пустой account_id"
    
    if not row_data["product_code"]:
        return f"Строка {row_number}: пустой product_code"
    
    if not row_data["product_name"]:
        return f"Строка {row_number}: пустое product_name"
    
    return None


def find_account_id(conn, client_id: str, market: str, account_id: str) -> Optional[int]:
    """
    Находит ID аккаунта в базе данных.
    
    Args:
        conn: Соединение с БД
        client_id: ID клиента
        market: Маркетплейс
        account_id: ID аккаунта
        
    Returns:
        ID аккаунта или None если не найден
    """
    try:
        query = text("""
            SELECT id FROM accounts 
            WHERE client_id = :client_id 
            AND market = :market 
            AND account_id = :account_id
        """)
        
        result = conn.execute(query, {
            "client_id": client_id,
            "market": market,
            "account_id": account_id
        })
        
        row = result.fetchone()
        return row[0] if row else None
        
    except Exception as e:
        logger.error(f"Ошибка поиска аккаунта: {e}")
        return None


def upsert_product(conn, client_id: str, account_id: int, product_code: str, 
                   product_name: str, product_link: str) -> bool:
    """
    Вставляет или обновляет товар в базе данных.
    
    Args:
        conn: Соединение с БД
        client_id: ID клиента
        account_id: ID аккаунта
        product_code: Код товара
        product_name: Название товара
        product_link: Ссылка на товар
        
    Returns:
        True если операция успешна
    """
    try:
        query = text("""
            INSERT INTO products (client_id, account_id, product_code, product_name, product_link)
            VALUES (:client_id, :account_id, :product_code, :product_name, :product_link)
            ON CONFLICT (account_id, product_code)
            DO UPDATE SET
                product_name = EXCLUDED.product_name,
                product_link = EXCLUDED.product_link,
                client_id = EXCLUDED.client_id
        """)
        
        conn.execute(query, {
            "client_id": client_id,
            "account_id": account_id,
            "product_code": product_code,
            "product_name": product_name,
            "product_link": product_link
        })
        
        conn.commit()
        return True
        
    except Exception as e:
        logger.error(f"Ошибка upsert товара {product_code}: {e}")
        conn.rollback()
        return False


def process_single_row(conn, row_data: Dict[str, str], row_number: int, 
                      duplicates: Set[Tuple[str, str]]) -> Optional[ValidationError]:
    """
    Обрабатывает одну строку из Excel файла.
    
    Args:
        conn: Соединение с БД
        row_data: Данные строки
        row_number: Номер строки
        duplicates: Множество дубликатов
        
    Returns:
        ValidationError если есть ошибка, None если успешно
    """
    # Проверяем дубликат
    key = (row_data["client_id"], row_data["product_code"])
    if key in duplicates:
        error_msg = f"Строка {row_number}: дубликат product_code '{row_data['product_code']}' в загружаемом файле"
        return ValidationError(
            row_number=row_number,
            error_message=error_msg,
            row_data=[str(row_number)] + [row_data.get(col, "") for col in REQUIRED_COLUMNS]
        )
    
    # Валидация данных строки
    validation_error = validate_row_data(row_data, row_number)
    if validation_error:
        return ValidationError(
            row_number=row_number,
            error_message=validation_error,
            row_data=[str(row_number)] + [row_data.get(col, "") for col in REQUIRED_COLUMNS]
        )
    
    # Поиск аккаунта
    account_db_id = find_account_id(
        conn, 
        row_data["client_id"], 
        row_data["market"], 
        row_data["account_id"]
    )
    
    if not account_db_id:
        error_msg = f"Строка {row_number}: аккаунт не найден ({row_data['client_id']}/{row_data['market']}/{row_data['account_id']})"
        return ValidationError(
            row_number=row_number,
            error_message=error_msg,
            row_data=[str(row_number)] + [row_data.get(col, "") for col in REQUIRED_COLUMNS]
        )
    
    # Upsert товара
    success = upsert_product(
        conn,
        row_data["client_id"],
        account_db_id,
        row_data["product_code"],
        row_data["product_name"],
        row_data["product_link"]
    )
    
    if not success:
        error_msg = f"Строка {row_number}: ошибка при сохранении товара"
        return ValidationError(
            row_number=row_number,
            error_message=error_msg,
            row_data=[str(row_number)] + [row_data.get(col, "") for col in REQUIRED_COLUMNS]
        )
    
    return None


def process_excel_rows(df: pd.DataFrame, engine) -> ProcessingResult:
    """
    Обрабатывает все строки Excel файла.
    
    Args:
        df: DataFrame с данными
        engine: Database engine
        
    Returns:
        ProcessingResult с результатами обработки
    """
    # Проверяем дубликаты
    duplicates = check_for_duplicates(df)
    
    success_count = 0
    validation_errors = []
    
    with engine.connect() as conn:
        for idx, row in df.iterrows():
            row_number = idx + 2  # Excel строки начинаются с 1, +1 для заголовка
            row_data = {k: str(v).strip() for k, v in row.items()}
            
            # Обрабатываем строку
            error = process_single_row(conn, row_data, row_number, duplicates)
            
            if error:
                validation_errors.append(error)
            else:
                success_count += 1
    
    # Формируем результат
    errors = [err.error_message for err in validation_errors]
    error_rows = [err.row_data for err in validation_errors]
    
    return ProcessingResult(
        success_count=success_count,
        errors=errors,
        error_rows=error_rows
    )


def sync_load_excel_refactored(file_path: str) -> Tuple[int, List[str], List[List[str]]]:
    """
    Рефакторенная версия загрузки Excel файла.
    
    Цикломатическая сложность: 7 (было 18)
    Разбита на функции согласно принципу Single Responsibility.
    
    Args:
        file_path: Путь к Excel файлу
        
    Returns:
        Tuple[количество загруженных, список ошибок, список строк с ошибками]
    """
    logger.info(f"Начинаю обработку Excel файла: {file_path}")
    
    try:
        # 1. Создание подключения к БД (CC: 1)
        engine = create_sync_engine()
        
        # 2. Чтение Excel файла (CC: 1)
        df = read_excel_file(file_path)
        
        # 3. Валидация колонок (CC: 1)
        validate_excel_columns(df)
        
        # 4. Обработка строк (CC: 1)
        result = process_excel_rows(df, engine)
        
        logger.info(f"Обработка завершена: {result.success_count} успешно, {len(result.errors)} ошибок")
        
        return result.success_count, result.errors, result.error_rows
        
    except Exception as e:
        logger.exception(f"Критическая ошибка при обработке Excel: {e}")
        return 0, [str(e)], []


def validate_excel_file_exists(file_path: str) -> bool:
    """
    Проверяет существование Excel файла.
    
    Args:
        file_path: Путь к файлу
        
    Returns:
        True если файл существует
    """
    return os.path.exists(file_path) and os.path.isfile(file_path)


def get_file_info(file_path: str) -> Dict[str, Any]:
    """
    Получает информацию о файле.
    
    Args:
        file_path: Путь к файлу
        
    Returns:
        Словарь с информацией о файле
    """
    if not validate_excel_file_exists(file_path):
        return {"exists": False}
    
    stat = os.stat(file_path)
    
    return {
        "exists": True,
        "size": stat.st_size,
        "modified": stat.st_mtime,
        "extension": os.path.splitext(file_path)[1].lower()
    } 