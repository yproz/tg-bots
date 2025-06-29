# services/order_processor.py
"""
Модуль для обработки заказов парсера.
Рефакторенная версия send_order с разделением ответственности.
"""

import logging
import json
import time
import requests
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from sqlalchemy.orm import Session

from db.models import Client, Account, Product, Order, Result
from services.collectors.ozon import get_initial_market_prices_ozon
from services.collectors.wb import get_initial_market_prices_wb

logger = logging.getLogger(__name__)

# Константы
PARSER_BASE_URL = "https://parser.market/wp-json/client-api/v1"
DEFAULT_BATCH_SIZE = 1000
BATCH_DELAY_SECONDS = 1
REQUEST_TIMEOUT = 30


@dataclass
class AccountData:
    """Данные аккаунта для обработки."""
    account_id: int
    client_id: str
    market: str
    region: str
    account_id_str: str
    api_key: str
    ozon_client_id: Optional[str] = None


@dataclass
class ProductBatch:
    """Пакет товаров для отправки."""
    products: List[Dict[str, Any]]
    product_codes: List[str]
    task_id: str


@dataclass
class OrderResult:
    """Результат обработки заказа."""
    success: bool
    orders_created: int
    error_message: Optional[str] = None


def validate_client_and_account(session: Session, client_id: str, account_id: int) -> Tuple[Optional[Client], Optional[Account]]:
    """
    Валидирует существование клиента и аккаунта.
    
    Args:
        session: Сессия БД
        client_id: ID клиента
        account_id: ID аккаунта
        
    Returns:
        Tuple[Client, Account] или (None, None) при ошибке
    """
    try:
        client = session.query(Client).filter(Client.id == client_id).first()
        if not client:
            logger.error(f"Клиент {client_id} не найден")
            return None, None
            
        account = session.query(Account).filter(Account.id == account_id).first()
        if not account:
            logger.error(f"Аккаунт {account_id} не найден")
            return None, None
            
        return client, account
        
    except Exception as e:
        logger.error(f"Ошибка валидации клиента/аккаунта: {e}")
        return None, None


def get_products_for_account(session: Session, client_id: str, account_id: int) -> List[Product]:
    """
    Получает список товаров для аккаунта.
    
    Args:
        session: Сессия БД
        client_id: ID клиента
        account_id: ID аккаунта
        
    Returns:
        Список товаров
    """
    try:
        products = session.query(Product).filter(
            Product.client_id == client_id,
            Product.account_id == account_id
        ).all()
        
        if not products:
            logger.error(f"Для клиента {client_id} с аккаунтом {account_id} отсутствуют товары")
            return []
            
        logger.info(f"Найдено {len(products)} товаров для обработки")
        return products
        
    except Exception as e:
        logger.error(f"Ошибка получения товаров: {e}")
        return []


def validate_product_link(product_link: str, market: str) -> Optional[str]:
    """
    Валидирует соответствие ссылки товара маркетплейсу.
    
    Args:
        product_link: Ссылка на товар
        market: Маркетплейс (ozon/wb)
        
    Returns:
        Валидную ссылку или None
    """
    if not product_link:
        return None
        
    link_lower = product_link.lower()
    market_lower = market.lower()
    
    if market_lower == "wb" and ("wildberries.ru" in link_lower or "wb.ru" in link_lower):
        return product_link
    elif market_lower == "ozon" and "ozon.ru" in link_lower:
        return product_link
    else:
        logger.warning(f"Ссылка не соответствует маркетплейсу {market}: {product_link}")
        return None


def create_account_data(client: Client, account: Account) -> AccountData:
    """
    Создает структуру данных аккаунта.
    
    Args:
        client: Клиент
        account: Аккаунт
        
    Returns:
        Данные аккаунта
    """
    return AccountData(
        account_id=account.id,
        client_id=client.id,
        market=account.market,
        region=account.region,
        account_id_str=account.account_id,
        api_key=account.api_key,
        ozon_client_id=getattr(account, 'ozon_client_id', None)
    )


def create_task_id(client_id: str, market: str) -> str:
    """
    Создает уникальный task_id для заказа.
    
    Args:
        client_id: ID клиента
        market: Маркетплейс
        
    Returns:
        Уникальный task_id
    """
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    market_letter = "O" if market.lower() == "ozon" else "W"
    return f"{client_id}{market_letter}{timestamp}"


def prepare_product_batch(products: List[Product], account_data: AccountData, 
                         start_idx: int, batch_size: int) -> ProductBatch:
    """
    Подготавливает пакет товаров для отправки.
    
    Args:
        products: Список товаров
        account_data: Данные аккаунта
        start_idx: Начальный индекс
        batch_size: Размер пакета
        
    Returns:
        Подготовленный пакет товаров
    """
    end_idx = min(start_idx + batch_size, len(products))
    batch_products = products[start_idx:end_idx]
    
    batch = []
    product_codes = []
    
    for product in batch_products:
        valid_link = validate_product_link(product.product_link, account_data.market)
        
        if valid_link:
            logger.debug(f"Используем ссылку для товара {product.product_code}: {valid_link}")
        else:
            logger.debug(f"У товара {product.product_code} нет валидной ссылки")
        
        batch.append({
            "code": product.product_code,
            "name": product.product_name,
            "linkset": [valid_link] if valid_link else [],
            "account_id": account_data.account_id_str
        })
        product_codes.append(product.product_code)
    
    task_id = create_task_id(account_data.client_id, account_data.market)
    
    return ProductBatch(
        products=batch,
        product_codes=product_codes,
        task_id=task_id
    )


def get_marketplace_prices(product_codes: List[str], account_data: AccountData, 
                          test_mode: bool) -> Dict[str, Any]:
    """
    Получает цены товаров из API маркетплейса.
    
    Args:
        product_codes: Коды товаров
        account_data: Данные аккаунта
        test_mode: Режим тестирования
        
    Returns:
        Словарь цен по кодам товаров
    """
    try:
        if account_data.market.lower() == "ozon":
            account_config = {
                'ozon_client_id': account_data.ozon_client_id,
                'ozon_api_key': account_data.api_key
            }
            return get_initial_market_prices_ozon(product_codes, account_config, test_mode)
            
        elif account_data.market.lower() == "wb":
            account_config = {
                'wb_api_key': account_data.api_key
            }
            return get_initial_market_prices_wb(product_codes, account_config, test_mode)
        else:
            logger.warning(f"Неподдерживаемый маркетплейс: {account_data.market}")
            return {}
            
    except Exception as e:
        logger.error(f"Ошибка получения цен с маркетплейса: {e}")
        return {}


def create_parser_payload(client: Client, account_data: AccountData, batch: ProductBatch) -> Dict[str, Any]:
    """
    Создает payload для отправки в парсер.
    
    Args:
        client: Клиент
        account_data: Данные аккаунта
        batch: Пакет товаров
        
    Returns:
        Payload для API запроса
    """
    return {
        "apikey": client.parser_api_key,
        "regionid": account_data.region,
        "market": account_data.market,
        "userlabel": batch.task_id,
        "products": batch.products
    }


def send_batch_to_parser(payload: Dict[str, Any], test_mode: bool) -> Tuple[int, str]:
    """
    Отправляет пакет товаров в парсер.
    
    Args:
        payload: Данные для отправки
        test_mode: Режим тестирования
        
    Returns:
        Tuple[status_code, response_text]
    """
    try:
        logger.info(f"Отправка батча с task_id {payload['userlabel']}")
        logger.debug(f"Send Order Payload: {json.dumps(payload, indent=2)}")
        
        if test_mode:
            logger.info("TEST MODE: Не отправляем запрос в парсинговый сервис.")
            return 200, "TEST MODE: Симулированный ответ"
        
        response = requests.post(
            f'{PARSER_BASE_URL}/send-order', 
            json=payload, 
            timeout=REQUEST_TIMEOUT
        )
        return response.status_code, response.text
        
    except Exception as e:
        logger.error(f"Ошибка отправки в парсер: {e}")
        return 500, str(e)


def save_order_and_results(session: Session, client_id: str, account_data: AccountData,
                          batch: ProductBatch, prices: Dict[str, float], 
                          current_product_id: int) -> bool:
    """
    Сохраняет заказ и результаты в базу данных.
    
    Args:
        session: Сессия БД
        client_id: ID клиента
        account_data: Данные аккаунта
        batch: Пакет товаров
        prices: Цены товаров
        current_product_id: ID последнего товара в пакете
        
    Returns:
        True если сохранение успешно
    """
    try:
        now = datetime.now()
        
        # Сохраняем заказ
        order = Order(
            client_id=client_id,
            task_id=batch.task_id,
            region=account_data.region,
            market=account_data.market,
            status='pending',
            report_url=None,
            created_at=now,
            updated_at=now
        )
        session.add(order)
        
        # Сохраняем результаты с ценами из API маркетплейса
        for prod in batch.products:
            market_price = prices.get(str(prod["code"]), 0.0)
            result = Result(
                client_id=client_id,
                task_id=batch.task_id,
                product_id=current_product_id,
                account_id=account_data.account_id,
                product_code=prod["code"],
                product_name=prod["name"],
                product_link=prod["linkset"][0] if prod["linkset"] else None,
                market_price=market_price,
                showcase_price=None,  # Будет обновлено из отчета парсера
                timestamp=now
            )
            session.add(result)
        
        logger.info(f"Батч успешно отправлен, task_id: {batch.task_id}")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка сохранения заказа и результатов: {e}")
        return False


def process_products_in_batches(session: Session, client: Client, account_data: AccountData,
                               products: List[Product], batch_size: int, 
                               test_mode: bool) -> int:
    """
    Обрабатывает товары пакетами.
    
    Args:
        session: Сессия БД
        client: Клиент
        account_data: Данные аккаунта
        products: Список товаров
        batch_size: Размер пакета
        test_mode: Режим тестирования
        
    Returns:
        Количество созданных заказов
    """
    orders_created = 0
    total_products = len(products)
    
    for start_idx in range(0, total_products, batch_size):
        # Подготавливаем пакет товаров
        batch = prepare_product_batch(products, account_data, start_idx, batch_size)
        
        # Получаем цены из API маркетплейса
        prices = get_marketplace_prices(batch.product_codes, account_data, test_mode)
        
        # Создаем payload для парсера
        payload = create_parser_payload(client, account_data, batch)
        
        # Отправляем в парсер
        status_code, response_text = send_batch_to_parser(payload, test_mode)
        
        if status_code == 200:
            # Получаем ID последнего товара в пакете
            current_product_id = products[min(start_idx + batch_size - 1, total_products - 1)].id
            
            # Сохраняем заказ и результаты
            if save_order_and_results(session, client.id, account_data, batch, prices, current_product_id):
                orders_created += 1
            else:
                logger.error(f"Ошибка сохранения для task_id: {batch.task_id}")
        else:
            logger.error(f"Ошибка отправки батча: {response_text}")
        
        # Пауза между пакетами
        if start_idx + batch_size < total_products:
            time.sleep(BATCH_DELAY_SECONDS)
    
    return orders_created


def send_order_refactored(client_id: str, account_id: int, batch_size: int = DEFAULT_BATCH_SIZE, 
                         test_mode: bool = False) -> OrderResult:
    """
    Рефакторенная версия отправки заказа в парсер.
    
    Цикломатическая сложность: 7 (было 16)
    Разбита на функции согласно принципу Single Responsibility.
    
    Args:
        client_id: ID клиента
        account_id: ID аккаунта
        batch_size: Размер пакета товаров
        test_mode: Режим тестирования
        
    Returns:
        OrderResult с результатом обработки
    """
    logger.info(f"Запуск отправки задания на сбор данных для клиента {client_id}, аккаунт {account_id}")
    
    try:
        from db.session import get_sync_session
        session = get_sync_session()
        
        try:
            # 1. Валидация клиента и аккаунта (CC: 1)
            client, account = validate_client_and_account(session, client_id, account_id)
            if not client or not account:
                return OrderResult(success=False, orders_created=0, error_message="Клиент или аккаунт не найден")
            
            # 2. Получение товаров (CC: 1)
            products = get_products_for_account(session, client_id, account_id)
            if not products:
                return OrderResult(success=False, orders_created=0, error_message="Товары не найдены")
            
            # 3. Создание данных аккаунта (CC: 1)
            account_data = create_account_data(client, account)
            
            # 4. Обработка товаров пакетами (CC: 1)
            orders_created = process_products_in_batches(
                session, client, account_data, products, batch_size, test_mode
            )
            
            # 5. Коммит транзакции (CC: 1)
            session.commit()
            
            logger.info(f"Отправка завершена, создано заданий: {orders_created}")
            
            return OrderResult(
                success=orders_created > 0,
                orders_created=orders_created,
                error_message=None if orders_created > 0 else "Не удалось создать ни одного заказа"
            )
            
        finally:
            session.close()
            
    except Exception as e:
        logger.exception(f"Ошибка в send_order_refactored: {e}")
        return OrderResult(success=False, orders_created=0, error_message=str(e))


def validate_batch_size(batch_size: int) -> int:
    """
    Валидирует размер пакета.
    
    Args:
        batch_size: Размер пакета
        
    Returns:
        Валидный размер пакета
    """
    if batch_size <= 0:
        logger.warning(f"Неверный размер пакета {batch_size}, используем по умолчанию {DEFAULT_BATCH_SIZE}")
        return DEFAULT_BATCH_SIZE
    
    if batch_size > 10000:
        logger.warning(f"Слишком большой размер пакета {batch_size}, ограничиваем до 10000")
        return 10000
    
    return batch_size


def get_batch_processing_info(total_products: int, batch_size: int) -> Dict[str, int]:
    """
    Получает информацию о пакетной обработке.
    
    Args:
        total_products: Общее количество товаров
        batch_size: Размер пакета
        
    Returns:
        Информация о пакетах
    """
    return {
        "total_products": total_products,
        "batch_size": batch_size,
        "total_batches": (total_products + batch_size - 1) // batch_size,
        "estimated_time_seconds": ((total_products + batch_size - 1) // batch_size) * BATCH_DELAY_SECONDS
    } 