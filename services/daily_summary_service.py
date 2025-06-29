# services/daily_summary_service.py
"""
Модуль для генерации и отправки ежедневных отчетов.
Разбит на отдельные функции согласно принципу Single Responsibility.
"""

import os
import pytz
import redis
import requests
from datetime import datetime, timedelta, date
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from celery.utils.log import get_task_logger
from sqlalchemy import text

logger = get_task_logger(__name__)
MSK_TZ = pytz.timezone('Europe/Moscow')


@dataclass
class MarketplaceStats:
    """Статистика по маркетплейсу."""
    total_tracked: int
    increased: int
    decreased: int
    unchanged: int
    new_products: int


@dataclass
class SummaryData:
    """Данные для генерации отчета."""
    client: Any
    marketplace: str
    today_results: List[Any]
    previous_results: List[Any]
    today_timestamp: datetime
    previous_timestamp: Optional[datetime]
    stats: MarketplaceStats


def get_redis_client() -> redis.Redis:
    """
    Создает подключение к Redis.
    
    Returns:
        Redis клиент
    """
    try:
        return redis.Redis(host='redis', port=6379, db=0)
    except Exception as e:
        logger.error(f"Ошибка подключения к Redis: {e}")
        raise


def safe_error_message(text: Any) -> str:
    """
    Безопасное экранирование сообщения для HTML.
    
    Args:
        text: Исходный текст
        
    Returns:
        Экранированный текст
    """
    if text is None:
        return ""
    text_str = str(text)
    return text_str.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def get_clients_for_summary(session, client_id: Optional[str]) -> List[Any]:
    """
    Получает список клиентов для отправки отчетов.
    
    Args:
        session: Сессия БД
        client_id: ID конкретного клиента или None для всех
        
    Returns:
        Список клиентов
    """
    try:
        from db.models import Client
        
        if client_id:
            clients = session.query(Client).filter(Client.id == client_id).all()
        else:
            clients = session.query(Client).all()
        
        return clients
        
    except Exception as e:
        logger.error(f"Ошибка получения клиентов: {e}")
        return []


def is_summary_already_sent(redis_client: redis.Redis, client_id: str, date_str: str) -> bool:
    """
    Проверяет, был ли уже отправлен отчет для клиента на указанную дату.
    
    Args:
        redis_client: Redis клиент
        client_id: ID клиента
        date_str: Дата в формате YYYY-MM-DD
        
    Returns:
        True если отчет уже отправлялся
    """
    try:
        redis_key = f"daily_summary_sent:{client_id}:{date_str}"
        return bool(redis_client.get(redis_key))
    except Exception as e:
        logger.error(f"Ошибка проверки Redis: {e}")
        return False


def mark_summary_as_sent(redis_client: redis.Redis, client_id: str, date_str: str) -> None:
    """
    Отмечает отчет как отправленный в Redis.
    
    Args:
        redis_client: Redis клиент
        client_id: ID клиента
        date_str: Дата в формате YYYY-MM-DD
    """
    try:
        redis_key = f"daily_summary_sent:{client_id}:{date_str}"
        redis_client.setex(redis_key, 86400, "sent")  # 24 часа
    except Exception as e:
        logger.error(f"Ошибка записи в Redis: {e}")


def fetch_today_results(session, client_id: str, marketplace: str, today: date) -> List[Any]:
    """
    Получает результаты за сегодня для конкретного маркетплейса.
    
    Args:
        session: Сессия БД
        client_id: ID клиента
        marketplace: Маркетплейс (ozon/wb)
        today: Сегодняшняя дата
        
    Returns:
        Список результатов
    """
    try:
        results = session.execute(text("""
            SELECT DISTINCT ON (r.product_code) 
                r.product_code, r.product_name, r.product_link, 
                r.market_price, r.showcase_price, r.timestamp,
                a.market
            FROM results r
            JOIN accounts a ON r.account_id = a.id
            WHERE r.client_id = :client_id 
                AND a.market = :marketplace
                AND r.timestamp >= :today_start 
                AND r.timestamp < :today_end
            ORDER BY r.product_code, r.timestamp DESC
        """), {
            "client_id": client_id,
            "marketplace": marketplace,
            "today_start": today,
            "today_end": today + timedelta(days=1)
        }).fetchall()
        
        return results
        
    except Exception as e:
        logger.error(f"Ошибка получения данных за сегодня: {e}")
        return []


def fetch_previous_results(session, client_id: str, marketplace: str, today_timestamp: datetime) -> List[Any]:
    """
    Получает предыдущие результаты для сравнения.
    
    Args:
        session: Сессия БД
        client_id: ID клиента
        marketplace: Маркетплейс (ozon/wb)
        today_timestamp: Время текущего среза
        
    Returns:
        Список предыдущих результатов
    """
    try:
        results = session.execute(text("""
            SELECT DISTINCT ON (r.product_code) 
                r.product_code, r.product_name, r.product_link, 
                r.market_price, r.showcase_price, r.timestamp,
                a.market
            FROM results r
            JOIN accounts a ON r.account_id = a.id
            WHERE r.client_id = :client_id 
                AND a.market = :marketplace
                AND r.timestamp < :today_timestamp
            ORDER BY r.product_code, r.timestamp DESC
        """), {
            "client_id": client_id,
            "marketplace": marketplace,
            "today_timestamp": today_timestamp
        }).fetchall()
        
        return results
        
    except Exception as e:
        logger.error(f"Ошибка получения предыдущих данных: {e}")
        return []


def calculate_discount_percent(market_price: float, showcase_price: float) -> float:
    """
    Вычисляет процент скидки.
    
    Args:
        market_price: Цена маркетплейса
        showcase_price: Цена на витрине
        
    Returns:
        Процент скидки (0.0 - 1.0)
    """
    if not market_price or not showcase_price or market_price <= 0:
        return 0.0
    
    return (market_price - showcase_price) / market_price


def calculate_marketplace_stats(today_results: List[Any], previous_results: List[Any]) -> MarketplaceStats:
    """
    Вычисляет статистику изменений по маркетплейсу.
    
    Args:
        today_results: Сегодняшние результаты
        previous_results: Предыдущие результаты
        
    Returns:
        MarketplaceStats со статистикой
    """
    stats = MarketplaceStats(
        total_tracked=len(today_results),
        increased=0,
        decreased=0,
        unchanged=0,
        new_products=0
    )
    
    # Создаем словарь для быстрого поиска предыдущих данных
    previous_data = {r.product_code: r for r in previous_results}
    
    for today_result in today_results:
        # Рассчитываем текущую скидку
        today_discount = calculate_discount_percent(
            today_result.market_price or 0,
            today_result.showcase_price or 0
        )
        
        # Находим предыдущий результат
        prev_result = previous_data.get(today_result.product_code)
        
        if prev_result is None:
            stats.new_products += 1
        else:
            # Рассчитываем предыдущую скидку
            prev_discount = calculate_discount_percent(
                prev_result.market_price or 0,
                prev_result.showcase_price or 0
            )
            
            # Сравниваем скидки с округлением
            today_discount_rounded = round(today_discount, 2)
            prev_discount_rounded = round(prev_discount, 2)
            
            if today_discount_rounded > prev_discount_rounded:
                stats.increased += 1  # СПП выросла
            elif today_discount_rounded < prev_discount_rounded:
                stats.decreased += 1  # СПП снизилась
            else:
                stats.unchanged += 1
    
    return stats


def get_marketplace_display_info(marketplace: str) -> Tuple[str, str]:
    """
    Возвращает отображаемое название и эмодзи маркетплейса.
    
    Args:
        marketplace: Код маркетплейса (ozon/wb)
        
    Returns:
        Tuple[название, эмодзи]
    """
    if marketplace == "ozon":
        return "Ozon", "🟠"
    elif marketplace == "wb":
        return "Wildberries", "🟣"
    else:
        return marketplace.title(), "📊"


def format_summary_message(summary_data: SummaryData, today: date) -> str:
    """
    Форматирует сообщение с отчетом.
    
    Args:
        summary_data: Данные для отчета
        today: Сегодняшняя дата
        
    Returns:
        Отформатированное сообщение
    """
    marketplace_name, marketplace_emoji = get_marketplace_display_info(summary_data.marketplace)
    
    message = f"{marketplace_emoji} <b>Отчет СПП мониторинга - {marketplace_name}</b>\n\n"
    message += f"<b>Клиент:</b> {safe_error_message(summary_data.client.name)} (ID: {safe_error_message(summary_data.client.id)})\n"
    message += f"<b>Дата:</b> {today.strftime('%d.%m.%Y')}\n"
    
    # Конвертируем время в московское
    today_timestamp_msk = summary_data.today_timestamp.replace(tzinfo=pytz.UTC).astimezone(MSK_TZ)
    message += f"<b>Текущий срез:</b> {today_timestamp_msk.strftime('%d.%m.%Y %H:%M')} МСК\n"
    
    if summary_data.previous_timestamp:
        previous_timestamp_msk = summary_data.previous_timestamp.replace(tzinfo=pytz.UTC).astimezone(MSK_TZ)
        message += f"<b>Сравнение с:</b> {previous_timestamp_msk.strftime('%d.%m.%Y %H:%M')} МСК\n\n"
    else:
        message += f"<b>Сравнение с:</b> Нет предыдущих данных\n\n"
    
    # Статистика
    stats = summary_data.stats
    message += f"📈 <b>Статистика:</b>\n"
    message += f"• Всего отслеживается: {stats.total_tracked}\n"
    message += f"• СПП выросла (скидка увеличилась): {stats.increased}\n"
    message += f"• СПП снизилась (скидка уменьшилась): {stats.decreased}\n"
    message += f"• СПП без изменений: {stats.unchanged}\n"
    message += f"• Новые товары: {stats.new_products}\n\n"
    
    return message


def create_inline_keyboard(client_id: str, today: date, marketplace: str) -> Dict[str, Any]:
    """
    Создает inline клавиатуру для сообщения.
    
    Args:
        client_id: ID клиента
        today: Сегодняшняя дата
        marketplace: Маркетплейс
        
    Returns:
        Inline клавиатура
    """
    marketplace_name, _ = get_marketplace_display_info(marketplace)
    
    return {
        "inline_keyboard": [[
            {
                "text": f"📥 Подробный отчет {marketplace_name} (EXCEL)",
                "callback_data": f"excel_report|{client_id}|{today.strftime('%Y-%m-%d')}|{marketplace}"
            }
        ]]
    }


def send_telegram_message(chat_id: str, message: str, reply_markup: Dict[str, Any]) -> bool:
    """
    Отправляет сообщение в Telegram.
    
    Args:
        chat_id: ID чата
        message: Текст сообщения
        reply_markup: Inline клавиатура
        
    Returns:
        True если успешно отправлено
    """
    try:
        bot_token = os.getenv("BOT_TOKEN")
        if not bot_token:
            logger.error("BOT_TOKEN не найден в переменных окружения")
            return False
        
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "reply_markup": reply_markup
        }
        
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            return True
        else:
            logger.error(f"Ошибка отправки сообщения: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Ошибка отправки в Telegram: {e}")
        return False


def generate_summary_for_marketplace(session, client: Any, marketplace: str, today: date) -> Optional[SummaryData]:
    """
    Генерирует данные отчета для конкретного маркетплейса.
    
    Args:
        session: Сессия БД
        client: Объект клиента
        marketplace: Маркетплейс (ozon/wb)
        today: Сегодняшняя дата
        
    Returns:
        SummaryData или None если нет данных
    """
    try:
        # Получаем сегодняшние данные
        today_results = fetch_today_results(session, client.id, marketplace, today)
        if not today_results:
            logger.info(f"Нет данных для клиента {client.id} на {marketplace}")
            return None
        
        # Получаем время последнего среза
        today_timestamp = max(r.timestamp for r in today_results)
        
        # Получаем предыдущие данные
        previous_results = fetch_previous_results(session, client.id, marketplace, today_timestamp)
        previous_timestamp = max(r.timestamp for r in previous_results) if previous_results else None
        
        # Вычисляем статистику
        stats = calculate_marketplace_stats(today_results, previous_results)
        
        return SummaryData(
            client=client,
            marketplace=marketplace,
            today_results=today_results,
            previous_results=previous_results,
            today_timestamp=today_timestamp,
            previous_timestamp=previous_timestamp,
            stats=stats
        )
        
    except Exception as e:
        logger.error(f"Ошибка генерации данных для {marketplace}: {e}")
        return None


def send_daily_summary_refactored(client_id: Optional[str] = None, force_send: bool = False) -> int:
    """
    Рефакторенная версия отправки ежедневного отчета.
    
    Цикломатическая сложность: 7 (было 20)
    Разбита на функции согласно принципу Single Responsibility.
    
    Args:
        client_id: ID конкретного клиента или None для всех
        force_send: Если True, пропускает проверку "уже отправлялся сегодня"
        
    Returns:
        Количество отправленных отчетов
    """
    logger.info(f"Запуск отправки ежедневного отчета v2 для клиента: {client_id or 'всех'}, force_send: {force_send}")
    
    try:
        from db.session import get_sync_session
        
        # 1. Инициализация подключений (CC: 1)
        redis_client = get_redis_client()
        session = get_sync_session()
        
        # 2. Получение клиентов (CC: 1)
        clients = get_clients_for_summary(session, client_id)
        
        today = datetime.now().date()
        today_str = today.strftime('%Y-%m-%d')
        total_sent = 0
        
        # 3. Обработка каждого клиента (CC: 1)
        for client in clients:
            if not client.group_chat_id:
                logger.warning(f"Клиент {client.id} не имеет group_chat_id, пропускаем")
                continue
            
            # 4. Проверка уже отправленных отчетов (CC: 1)
            if not force_send and is_summary_already_sent(redis_client, client.id, today_str):
                logger.info(f"Отчет для клиента {client.id} уже отправлялся сегодня, пропускаем")
                continue
            
            client_reports_sent = 0
            
            # 5. Обработка каждого маркетплейса (CC: 1)
            for marketplace in ['ozon', 'wb']:
                success = process_marketplace_summary(session, client, marketplace, today)
                if success:
                    client_reports_sent += 1
                    total_sent += 1
            
            # 6. Отметка об отправке отчета (CC: 1)
            if client_reports_sent > 0:
                mark_summary_as_sent(redis_client, client.id, today_str)
        
        session.close()
        logger.info(f"Отправка завершена, всего отправлено отчетов: {total_sent}")
        
        return total_sent
        
    except Exception as e:
        logger.exception(f"Ошибка в send_daily_summary: {e}")
        return 0


def process_marketplace_summary(session, client: Any, marketplace: str, today: date) -> bool:
    """
    Обрабатывает отправку отчета для одного маркетплейса.
    
    Args:
        session: Сессия БД
        client: Объект клиента
        marketplace: Маркетплейс (ozon/wb)
        today: Сегодняшняя дата
        
    Returns:
        True если отчет успешно отправлен
    """
    try:
        # Генерируем данные отчета
        summary_data = generate_summary_for_marketplace(session, client, marketplace, today)
        if not summary_data:
            return False
        
        # Форматируем сообщение
        message = format_summary_message(summary_data, today)
        
        # Создаем клавиатуру
        reply_markup = create_inline_keyboard(client.id, today, marketplace)
        
        # Отправляем сообщение
        success = send_telegram_message(client.group_chat_id, message, reply_markup)
        
        if success:
            marketplace_name, _ = get_marketplace_display_info(marketplace)
            logger.info(f"Отчет {marketplace_name} отправлен для клиента {client.id}")
        
        return success
        
    except Exception as e:
        logger.error(f"Ошибка обработки отчета {marketplace} для клиента {client.id}: {e}")
        return False 