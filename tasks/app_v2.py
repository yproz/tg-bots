"""
Celery задачи для работы с парсером v2
"""
import logging
import html
from celery import Celery
from services.parser_service_v2 import ParserServiceV2
import os
import requests
import io
import xlsxwriter
import pytz
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

def safe_error_message(error) -> str:
    """Безопасно экранирует HTML в сообщениях об ошибках"""
    return html.escape(str(error))

# Создаем Celery приложение
app = Celery('pricebot_v2')
app.config_from_object('celeryconfig')

parser_service = ParserServiceV2()

# Московское время
MSK_TZ = pytz.timezone('Europe/Moscow')

@app.task
def send_parser_order_v2(client_id: str, account_id: int, batch_size: int = 1000, test_mode: bool = False):
    """
    Отправка заказа в парсер v2
    """
    logger.info(f"Отправка заказа в парсер v2 для клиента {client_id}, аккаунт {account_id}")
    
    try:
        from services.order_processor import send_order_refactored
        result = send_order_refactored(client_id, account_id, batch_size, test_mode)
        success = result.success
        if success:
            logger.info(f"Заказ успешно отправлен для клиента {client_id}, создано заказов: {result.orders_created}")
        else:
            logger.error(f"Ошибка отправки заказа для клиента {client_id}: {result.error_message}")
        return success
    except Exception as e:
        logger.exception(f"Ошибка в задаче send_parser_order_v2: {e}")
        return False

@app.task
def check_reports_v2(client_id: str):
    """
    Проверка отчетов от парсера v2
    """
    logger.info(f"Проверка отчетов v2 для клиента {client_id}")
    
    try:
        from services.report_checker import check_reports_refactored
        base_url = "https://parser.market/wp-json/client-api/v1"
        success = check_reports_refactored(base_url, client_id)
        if success:
            logger.info(f"Отчеты успешно обработаны для клиента {client_id}")
        else:
            logger.info(f"Нет новых отчетов для клиента {client_id}")
        return success
    except Exception as e:
        logger.exception(f"Ошибка в задаче check_reports_v2: {e}")
        return False

@app.task
def collect_all_accounts_v2():
    """
    Сбор цен по всем аккаунтам v2
    """
    logger.info("Запуск сбора цен по всем аккаунтам v2")
    
    try:
        from db.session import get_sync_session
        from db.models import Client, Account
        
        session = get_sync_session()
        
        # Получаем всех клиентов с API ключами парсера
        clients = session.query(Client).filter(Client.parser_api_key.isnot(None)).all()
        
        total_orders = 0
        
        for client in clients:
            # Получаем аккаунты клиента
            accounts = session.query(Account).filter(Account.client_id == client.id).all()
            
            for account in accounts:
                logger.info(f"Отправка заказа для клиента {client.id}, аккаунт {account.id}")
                
                # Отправляем заказ
                success = send_parser_order_v2.delay(client.id, account.id)
                if success:
                    total_orders += 1
                    
        session.close()
        
        logger.info(f"Отправлено {total_orders} заказов")
        
        return total_orders > 0
        
    except Exception as e:
        logger.exception(f"Ошибка в задаче collect_all_accounts_v2: {e}")
        return False

@app.task
def check_all_reports_v2():
    """
    Проверка отчетов по всем клиентам v2
    """
    logger.info("Запуск проверки отчетов по всем клиентам v2")
    
    try:
        from db.session import get_sync_session
        from db.models import Client
        
        session = get_sync_session()
        
        # Получаем всех клиентов с API ключами парсера
        clients = session.query(Client).filter(Client.parser_api_key.isnot(None)).all()
        
        total_updated = 0
        
        for client in clients:
            logger.info(f"Проверка отчетов для клиента {client.id}")
            
            # Проверяем отчеты
            success = check_reports_v2.delay(client.id)
            if success:
                total_updated += 1
                
        session.close()
        
        logger.info(f"Обновлено {total_updated} клиентов")
        return total_updated > 0
        
    except Exception as e:
        logger.exception(f"Ошибка в задаче check_all_reports_v2: {e}")
        return False

@app.task
def send_daily_summary_v2(client_id: Optional[str] = None, force_send: bool = False):
    """
    Wrapper для рефакторенной версии send_daily_summary_refactored.
    """
    from services.daily_summary_service import send_daily_summary_refactored
    return send_daily_summary_refactored(client_id, force_send)

@app.task
def send_excel_report_v2(client_id: str, date_str: str, marketplace: Optional[str] = None):
    """
    Wrapper для рефакторенной версии send_excel_report_v2_refactored.
    """
    from tasks.refactored_reports import send_excel_report_v2_refactored
    return send_excel_report_v2_refactored(client_id, date_str, marketplace) 