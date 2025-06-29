"""
Сервис для отправки уведомлений через Telegram API.
Выделен из основной бизнес логики для лучшей тестируемости.
"""

import os
import requests
import io
from typing import Optional, Dict, Any
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


def safe_error_message(text: str) -> str:
    """
    Безопасное экранирование сообщения для HTML.
    
    Args:
        text: Исходный текст
        
    Returns:
        Экранированный текст
    """
    if not text:
        return ""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def get_marketplace_display_name(marketplace: Optional[str]) -> str:
    """
    Возвращает отображаемое название маркетплейса.
    
    Args:
        marketplace: Код маркетплейса (ozon/wb)
        
    Returns:
        Отображаемое название
    """
    if marketplace == "ozon":
        return " Ozon"
    elif marketplace == "wb":
        return " Wildberries"
    return ""


def get_marketplace_suffix(marketplace: Optional[str]) -> str:
    """
    Возвращает суффикс для имени файла.
    
    Args:
        marketplace: Код маркетплейса (ozon/wb)
        
    Returns:
        Суффикс для файла
    """
    if marketplace == "ozon":
        return "_Ozon"
    elif marketplace == "wb":
        return "_WB"
    return ""


def send_document_to_telegram(
    chat_id: str,
    document_data: io.BytesIO,
    filename: str,
    caption: str,
    bot_token: Optional[str] = None
) -> bool:
    """
    Отправляет документ в Telegram чат.
    
    Args:
        chat_id: ID чата
        document_data: Данные документа
        filename: Имя файла
        caption: Подпись к документу
        bot_token: Токен бота (если не передан, берется из env)
        
    Returns:
        True если успешно отправлено, False при ошибке
    """
    if not bot_token:
        bot_token = os.getenv("BOT_TOKEN")
    
    if not bot_token:
        logger.error("BOT_TOKEN не найден в переменных окружения")
        return False
    
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    
    files = {
        'document': (
            filename, 
            document_data.read(), 
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    }
    
    data = {
        'chat_id': chat_id,
        'caption': caption,
        'parse_mode': 'HTML'
    }
    
    try:
        response = requests.post(url, data=data, files=files, timeout=30)
        if response.status_code == 200:
            logger.info(f"Документ {filename} отправлен в чат {chat_id}")
            return True
        else:
            logger.error(f"Ошибка отправки документа: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Ошибка отправки документа: {e}")
        return False


def send_text_message_to_telegram(
    chat_id: str,
    text: str,
    parse_mode: str = "HTML",
    bot_token: Optional[str] = None
) -> bool:
    """
    Отправляет текстовое сообщение в Telegram чат.
    
    Args:
        chat_id: ID чата
        text: Текст сообщения
        parse_mode: Режим парсинга (HTML/Markdown)
        bot_token: Токен бота
        
    Returns:
        True если успешно отправлено
    """
    if not bot_token:
        bot_token = os.getenv("BOT_TOKEN")
    
    if not bot_token:
        logger.error("BOT_TOKEN не найден в переменных окружения")
        return False
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    data = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': parse_mode
    }
    
    try:
        response = requests.post(url, data=data, timeout=30)
        if response.status_code == 200:
            logger.info(f"Сообщение отправлено в чат {chat_id}")
            return True
        else:
            logger.error(f"Ошибка отправки сообщения: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения: {e}")
        return False


def create_excel_report_caption(date_str: str, marketplace: Optional[str] = None) -> str:
    """
    Создает подпись для Excel отчета.
    
    Args:
        date_str: Дата отчета
        marketplace: Маркетплейс (опционально)
        
    Returns:
        Подпись для отчета
    """
    marketplace_display = get_marketplace_display_name(marketplace)
    safe_date = safe_error_message(date_str)
    
    return f"📊 <b>Подробный Excel-отчет{marketplace_display} за {safe_date}</b>"


def create_excel_filename(client_id: str, date_str: str, marketplace: Optional[str] = None) -> str:
    """
    Создает имя файла для Excel отчета.
    
    Args:
        client_id: ID клиента
        date_str: Дата отчета
        marketplace: Маркетплейс (опционально)
        
    Returns:
        Имя файла
    """
    file_suffix = get_marketplace_suffix(marketplace)
    return f"report_comparison_{client_id}_{date_str}{file_suffix}.xlsx" 