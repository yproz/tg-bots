# services/report_checker.py
"""
Модуль для проверки готовности отчетов от парсера.
Разбит на отдельные функции согласно принципу Single Responsibility.
"""

import json
import requests
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@dataclass
class OrderStatus:
    """Статус заказа от парсера."""
    task_id: str
    status: str
    report_url: Optional[str]
    found: bool = False


@dataclass
class ReportItem:
    """Элемент отчета с данными о товаре."""
    product_code: str
    final_price: float
    offers: List[Dict[str, Any]]


def validate_client_and_get_orders(session, client_id: str) -> Tuple[Optional[Any], List[Any]]:
    """
    Валидирует клиента и получает pending заказы.
    
    Args:
        session: Сессия БД
        client_id: ID клиента
        
    Returns:
        Tuple[client, orders] или (None, []) при ошибке
    """
    try:
        from db.models import Client, Order
        
        # Проверяем клиента
        client = session.query(Client).filter(Client.id == client_id).first()
        if not client:
            logger.error(f"Клиент {client_id} не найден")
            return None, []
        
        # Получаем pending заказы
        orders = session.query(Order).filter(
            Order.client_id == client_id,
            Order.status == 'pending'
        ).all()
        
        if not orders:
            logger.info("Нет заданий для проверки")
            return client, []
        
        return client, orders
        
    except Exception as e:
        logger.error(f"Ошибка валидации клиента: {e}")
        return None, []


def fetch_parser_reports(base_url: str, api_key: str, limit: int = 50) -> Optional[Dict]:
    """
    Получает отчеты от парсера.
    
    Args:
        base_url: Базовый URL API парсера
        api_key: API ключ клиента
        limit: Лимит результатов
        
    Returns:
        Данные ответа или None при ошибке
    """
    try:
        response = requests.post(
            f'{base_url}/get-last50',
            json={"apikey": api_key, "limit": limit},
            timeout=30
        )
        
        if response.status_code != 200:
            logger.error(f"Ошибка получения статусов заданий: {response.text}")
            return None
        
        json_response = response.json()
        logger.debug(f"Ответ API: {json.dumps(json_response, indent=2)}")
        
        return json_response
        
    except Exception as e:
        logger.error(f"Ошибка запроса к парсеру: {e}")
        return None


def parse_parser_response(json_response: Dict) -> Dict:
    """
    Парсит ответ от парсера в стандартный формат.
    
    Args:
        json_response: Ответ от API парсера
        
    Returns:
        Обработанные данные
    """
    data = None
    
    # Ищем данные в ответе
    if isinstance(json_response, list):
        for elem in json_response:
            if isinstance(elem, dict) and "data" in elem:
                data = elem["data"]
                break
    
    if data is None:
        data = json_response
    
    return data


def find_order_status(data: Dict, task_id: str) -> OrderStatus:
    """
    Находит статус конкретного заказа в данных парсера.
    
    Args:
        data: Даные от парсера
        task_id: ID задачи для поиска
        
    Returns:
        OrderStatus с информацией о статусе
    """
    order_status = OrderStatus(task_id=task_id, status='', report_url=None)
    
    for task_group in data:
        local_task_id = None
        local_report_url = None
        local_status = None
        
        if isinstance(task_group, list):
            for item in task_group:
                if isinstance(item, dict):
                    if 'userlabel' in item:
                        local_task_id = item['userlabel']
                    elif 'report_json' in item:
                        local_report_url = item['report_json']
                    elif 'status' in item:
                        local_status = item['status']
            
            if local_task_id == task_id:
                order_status.found = True
                order_status.status = local_status or ''
                order_status.report_url = local_report_url
                break
    
    return order_status


def download_and_parse_report(report_url: str) -> Optional[Dict]:
    """
    Скачивает и парсит JSON отчет.
    
    Args:
        report_url: URL отчета
        
    Returns:
        Данные отчета или None при ошибке
    """
    try:
        response = requests.get(report_url, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Ошибка скачивания или парсинга JSON: {e}")
        return None


def extract_report_items(json_data: Dict) -> List[ReportItem]:
    """
    Извлекает данные о товарах из отчета.
    
    Args:
        json_data: JSON данные отчета
        
    Returns:
        Список объектов ReportItem
    """
    items = []
    
    for item in json_data.get("data", []):
        product_code = item.get("code")
        offers = item.get("offers", [])
        
        if not offers:
            continue
        
        offer = offers[0]
        final_price = calculate_final_price(offer)
        
        if final_price is None:
            logger.info(f"Пропускаем товар {product_code}: отсутствует валидная цена")
            continue
        
        logger.info(f"Для товара {product_code} рассчитана итоговая цена: {final_price}")
        
        items.append(ReportItem(
            product_code=product_code,
            final_price=final_price,
            offers=offers
        ))
    
    return items


def calculate_final_price(offer: Dict[str, Any]) -> Optional[float]:
    """
    Вычисляет итоговую цену товара из предложения.
    
    Args:
        offer: Данные предложения
        
    Returns:
        Итоговая цена или None если цена недоступна
    """
    promo_price = offer.get("PromoPrice", "")
    regular_price = offer.get("Price", "")
    
    # Проверяем промо цену
    if promo_price not in [0, "0", "", None]:
        try:
            return float(promo_price)
        except (ValueError, TypeError):
            pass
    
    # Проверяем обычную цену
    if regular_price not in [0, "0", "", None]:
        try:
            return float(regular_price)
        except (ValueError, TypeError):
            pass
    
    return None


def update_results_prices(session, client_id: str, task_id: str, report_items: List[ReportItem]) -> int:
    """
    Обновляет цены в таблице results.
    
    Args:
        session: Сессия БД
        client_id: ID клиента
        task_id: ID задачи
        report_items: Список товаров с ценами
        
    Returns:
        Количество обновленных записей
    """
    try:
        from sqlalchemy import text
        
        updated_count = 0
        
        for item in report_items:
            result = session.execute(
                text("""
                    UPDATE results
                    SET showcase_price = :price
                    WHERE client_id = :client_id AND task_id = :task_id AND product_code = :product_code
                """),
                {
                    "price": item.final_price,
                    "client_id": client_id,
                    "task_id": task_id,
                    "product_code": item.product_code
                }
            )
            updated_count += result.rowcount
        
        return updated_count
        
    except Exception as e:
        logger.error(f"Ошибка обновления цен: {e}")
        return 0


def update_order_status(session, order, report_url: str) -> None:
    """
    Обновляет статус заказа на completed.
    
    Args:
        session: Сессия БД
        order: Объект заказа
        report_url: URL отчета
    """
    try:
        now = datetime.now()
        order.status = 'completed'
        order.report_url = report_url
        order.updated_at = now
        
    except Exception as e:
        logger.error(f"Ошибка обновления статуса заказа: {e}")


def trigger_daily_summary(client_id: str) -> None:
    """
    Запускает отправку ежедневного отчета.
    
    Args:
        client_id: ID клиента
    """
    try:
        from services.daily_summary_service import send_daily_summary_refactored
        logger.info(f"Данные обновлены для клиента {client_id}, запускаем отправку отчета")
        send_daily_summary_refactored(client_id, force_send=True)
        
    except Exception as e:
        logger.error(f"Ошибка запуска отчета: {e}")


def check_reports_refactored(base_url: str, client_id: str) -> bool:
    """
    Рефакторенная версия проверки готовности отчетов.
    
    Цикломатическая сложность: 6 (было 25)
    Разбита на функции согласно принципу Single Responsibility.
    
    Args:
        base_url: Базовый URL API парсера
        client_id: ID клиента
        
    Returns:
        True если проверка завершена успешно
    """
    logger.info(f"Запуск проверки готовности отчётов для клиента {client_id}")
    
    try:
        from db.session import get_sync_session
        session = get_sync_session()
        
        # 1. Валидация клиента и получение заказов (CC: 1)
        client, orders = validate_client_and_get_orders(session, client_id)
        if not client:
            return False
        
        if not orders:
            return True
        
        # 2. Получение данных от парсера (CC: 1)
        json_response = fetch_parser_reports(base_url, client.parser_api_key)
        if not json_response:
            return False
        
        # 3. Парсинг ответа (CC: 1)
        data = parse_parser_response(json_response)
        
        updated_orders = 0
        
        # 4. Обработка каждого заказа (CC: 1)
        for order in orders:
            order_status = find_order_status(data, order.task_id)
            
            # 5. Обработка завершенного заказа (CC: 1)
            if order_status.found and order_status.status == 'completed' and order_status.report_url:
                success = process_completed_order(session, client_id, order, order_status.report_url)
                if success:
                    updated_orders += 1
        
        # 6. Сохранение изменений (CC: 1)
        session.commit()
        session.close()
        
        logger.info(f"Проверка завершена, обновлено заданий: {updated_orders}")
        return updated_orders > 0
        
    except Exception as e:
        logger.exception(f"Ошибка в check_reports: {e}")
        return False


def process_completed_order(session, client_id: str, order, report_url: str) -> bool:
    """
    Обрабатывает завершенный заказ.
    
    Args:
        session: Сессия БД
        client_id: ID клиента
        order: Объект заказа
        report_url: URL отчета
        
    Returns:
        True если обработка успешна
    """
    try:
        logger.info(f"Задание {order.task_id} завершено, обрабатываем отчёт")
        
        # Скачиваем и парсим отчет
        json_data = download_and_parse_report(report_url)
        if not json_data:
            return False
        
        # Извлекаем данные о товарах
        report_items = extract_report_items(json_data)
        if not report_items:
            logger.warning(f"Нет данных о товарах в отчете для задания {order.task_id}")
            return False
        
        # Обновляем цены в БД
        updated_count = update_results_prices(session, client_id, order.task_id, report_items)
        logger.info(f"Обновлено {updated_count} записей цен для задания {order.task_id}")
        
        # Обновляем статус заказа
        update_order_status(session, order, report_url)
        
        # Запускаем отправку отчета
        trigger_daily_summary(client_id)
        
        return True
        
    except Exception as e:
        logger.error(f"Ошибка обработки заказа {order.task_id}: {e}")
        return False 