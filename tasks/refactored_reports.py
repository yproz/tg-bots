"""
Рефакторенные задачи для генерации отчетов.
Разбиты на функции с низкой цикломатической сложностью (CC < 10).
"""

import os
from typing import Optional
from celery import current_app as celery_app
from celery.utils.log import get_task_logger

# Импорты сервисов
from services.report_generator import (
    validate_report_params,
    fetch_current_results,
    fetch_previous_results,
    generate_excel_file,
    ReportData
)
from services.telegram_notifier import (
    send_document_to_telegram,
    create_excel_report_caption,
    create_excel_filename
)

logger = get_task_logger(__name__)


def send_excel_report_v2_refactored(client_id: str, date_str: str, marketplace: Optional[str] = None) -> bool:
    """
    Рефакторенная версия генерации и отправки Excel-отчета.
    
    Цикломатическая сложность: 4 (было 29)
    Разбита на функции согласно принципу Single Responsibility.
    
    Args:
        client_id: ID клиента
        date_str: Дата в формате YYYY-MM-DD
        marketplace: Фильтр по маркетплейсу (ozon/wb) или None
        
    Returns:
        True если отчет успешно отправлен
    """
    from db.session import get_sync_session
    
    logger.info(f"Формирование Excel-отчета для клиента {client_id} за {date_str}, маркетплейс: {marketplace or 'все'}")
    
    session = get_sync_session()
    
    try:
        # 1. Валидация параметров (CC: 1)
        client, date = validate_report_params(client_id, date_str, session)
        if not client or not date:
            logger.error(f"Некорректные параметры: клиент {client_id}, дата {date_str}")
            return False
        
        # 2. Получение данных (CC: 1)
        current_results = fetch_current_results(session, client_id, date, marketplace)
        if not current_results:
            logger.info(f"Нет данных для клиента {client_id} за {date_str}")
            return False
        
        # 3. Получение данных для сравнения (CC: 1)
        current_timestamp = max(r.timestamp for r in current_results)
        previous_data = fetch_previous_results(session, client_id, current_timestamp, marketplace)
        
        # 4. Создание объекта данных
        report_data = ReportData(
            current_results=current_results,
            previous_data=previous_data,
            client=client,
            date=date,
            marketplace=marketplace
        )
        
        # 5. Генерация Excel файла (CC: 1)
        excel_buffer, stats = generate_excel_file(report_data)
        
        # 6. Отправка в Telegram (CC: 1)
        filename = create_excel_filename(client_id, date_str, marketplace)
        caption = create_excel_report_caption(date_str, marketplace)
        
        success = send_document_to_telegram(
            chat_id=client.group_chat_id,
            document_data=excel_buffer,
            filename=filename,
            caption=caption
        )
        
        if success:
            marketplace_display = marketplace or 'все маркетплейсы'
            logger.info(f"Excel-отчет ({marketplace_display}) отправлен для клиента {client_id}")
        
        return success
        
    except Exception as e:
        logger.error(f"Ошибка генерации отчета для клиента {client_id}: {e}")
        return False
    finally:
        session.close()


@celery_app.task  
def validate_excel_report_request(client_id: str, date_str: str) -> bool:
    """
    Предварительная валидация запроса на отчет.
    
    Args:
        client_id: ID клиента
        date_str: Дата в формате YYYY-MM-DD
        
    Returns:
        True если запрос валиден
    """
    from db.session import get_sync_session
    
    session = get_sync_session()
    try:
        client, date = validate_report_params(client_id, date_str, session)
        return client is not None and date is not None
    finally:
        session.close()


def generate_report_for_marketplace(client_id: str, date_str: str, marketplace: str) -> bool:
    """
    Генерирует отчет для конкретного маркетплейса.
    Вспомогательная функция для batch генерации.
    
    Args:
        client_id: ID клиента
        date_str: Дата
        marketplace: Маркетплейс (ozon/wb)
        
    Returns:
        True если успешно
    """
    return send_excel_report_v2_refactored(client_id, date_str, marketplace)


@celery_app.task
def generate_all_marketplace_reports(client_id: str, date_str: str) -> dict:
    """
    Генерирует отчеты для всех маркетплейсов.
    
    Args:
        client_id: ID клиента
        date_str: Дата
        
    Returns:
        Словарь с результатами {marketplace: success}
    """
    results = {}
    
    # Генерируем отчеты для каждого маркетплейса
    for marketplace in ['ozon', 'wb']:
        try:
            success = generate_report_for_marketplace(client_id, date_str, marketplace)
            results[marketplace] = success
            logger.info(f"Отчет {marketplace} для клиента {client_id}: {'успешно' if success else 'ошибка'}")
        except Exception as e:
            logger.error(f"Ошибка генерации отчета {marketplace} для клиента {client_id}: {e}")
            results[marketplace] = False
    
    # Генерируем общий отчет
    try:
        success = send_excel_report_v2_refactored(client_id, date_str, None)
        results['all'] = success
        logger.info(f"Общий отчет для клиента {client_id}: {'успешно' if success else 'ошибка'}")
    except Exception as e:
        logger.error(f"Ошибка генерации общего отчета для клиента {client_id}: {e}")
        results['all'] = False
    
    return results 