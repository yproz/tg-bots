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
        success = parser_service.send_order(client_id, account_id, batch_size, test_mode)
        if success:
            logger.info(f"Заказ успешно отправлен для клиента {client_id}")
        else:
            logger.error(f"Ошибка отправки заказа для клиента {client_id}")
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
        success = parser_service.check_reports(client_id)
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
def send_daily_summary_v2(client_id: Optional[str] = None):
    """
    Отправка ежедневного отчета по всем клиентам v2 или для конкретного клиента
    Отправляет отдельные сообщения для каждого маркетплейса
    """
    logger.info(f"Запуск отправки ежедневного отчета v2 для клиента: {client_id or 'всех'}")
    
    try:
        from db.session import get_sync_session
        from db.models import Client, Result
        from datetime import datetime, timedelta
        from sqlalchemy import text
        import redis
        
        # Подключение к Redis для проверки уже отправленных отчетов
        redis_client = redis.Redis(host='redis', port=6379, db=0)
        
        session = get_sync_session()
        
        # Получаем клиентов - либо конкретного, либо всех
        if client_id:
            clients = session.query(Client).filter(Client.id == client_id).all()
        else:
            clients = session.query(Client).all()
        
        today = datetime.now().date()
        today_str = today.strftime('%Y-%m-%d')
        
        total_sent = 0
        
        for client in clients:
            if not client.group_chat_id:
                logger.warning(f"Клиент {client.id} не имеет group_chat_id, пропускаем")
                continue
            
            # Проверяем, отправлялся ли уже отчет сегодня для этого клиента
            redis_key = f"daily_summary_sent:{client.id}:{today_str}"
            if redis_client.get(redis_key):
                logger.info(f"Отчет для клиента {client.id} уже отправлялся сегодня, пропускаем")
                continue
                
            # Получаем данные отдельно для каждого маркетплейса
            marketplaces = ['ozon', 'wb']
            
            for marketplace in marketplaces:
                # Получаем последний срез данных за сегодня для конкретного маркетплейса
                today_results = session.execute(text("""
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
                    "client_id": client.id,
                    "marketplace": marketplace,
                    "today_start": today,
                    "today_end": today + timedelta(days=1)
                }).fetchall()
                
                if not today_results:
                    logger.info(f"Нет данных для клиента {client.id} на {marketplace}, пропускаем")
                    continue
                
                # Получаем время последнего среза за сегодня
                today_timestamp = max(r.timestamp for r in today_results)
                
                # Получаем предыдущий срез данных для этого клиента и маркетплейса
                previous_results = session.execute(text("""
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
                    "client_id": client.id,
                    "marketplace": marketplace,
                    "today_timestamp": today_timestamp
                }).fetchall()
                
                # Получаем время предыдущего среза
                previous_timestamp = max(r.timestamp for r in previous_results) if previous_results else None
                
                # Определяем название маркетплейса
                marketplace_name = "Ozon" if marketplace == "ozon" else "Wildberries"
                marketplace_emoji = "🟠" if marketplace == "ozon" else "🟣"
                
                # Формируем сообщение для конкретного маркетплейса
                message = f"{marketplace_emoji} <b>Отчет СПП мониторинга - {marketplace_name}</b>\n\n"
                message += f"<b>Клиент:</b> {safe_error_message(client.name)} (ID: {safe_error_message(client.id)})\n"
                message += f"<b>Дата:</b> {today.strftime('%d.%m.%Y')}\n"
                
                # Конвертируем время в московское
                today_timestamp_msk = today_timestamp.replace(tzinfo=pytz.UTC).astimezone(MSK_TZ)
                message += f"<b>Текущий срез:</b> {today_timestamp_msk.strftime('%d.%m.%Y %H:%M')} МСК\n"
                
                if previous_timestamp:
                    previous_timestamp_msk = previous_timestamp.replace(tzinfo=pytz.UTC).astimezone(MSK_TZ)
                    message += f"<b>Сравнение с:</b> {previous_timestamp_msk.strftime('%d.%m.%Y %H:%M')} МСК\n\n"
                else:
                    message += f"<b>Сравнение с:</b> Нет предыдущих данных\n\n"
                
                # Статистика для конкретного маркетплейса
                total_tracked = len(today_results)
                increased = 0
                decreased = 0
                unchanged = 0
                new_products = 0
                
                # Создаем словарь для быстрого поиска предыдущих данных
                previous_data = {r.product_code: r for r in previous_results}
                
                # Сравниваем размеры скидок (СПП)
                for today_result in today_results:
                    # Рассчитываем текущую скидку
                    today_market_price = today_result.market_price or 0
                    today_showcase_price = today_result.showcase_price or 0
                    today_discount = 0
                    if today_market_price > 0 and today_showcase_price > 0:
                        today_discount = (today_market_price - today_showcase_price) / today_market_price
                    
                    # Находим предыдущий результат для сравнения скидки
                    prev_result = previous_data.get(today_result.product_code)
                    
                    if prev_result is None:
                        new_products += 1
                    else:
                        # Рассчитываем предыдущую скидку
                        prev_market_price = prev_result.market_price or 0
                        prev_showcase_price = prev_result.showcase_price or 0
                        prev_discount = 0
                        if prev_market_price > 0 and prev_showcase_price > 0:
                            prev_discount = (prev_market_price - prev_showcase_price) / prev_market_price
                        
                        # Сравниваем скидки с округлением до 2 знаков
                        today_discount_rounded = round(today_discount, 2)
                        prev_discount_rounded = round(prev_discount, 2)
                        
                        if today_discount_rounded > prev_discount_rounded:
                            increased += 1  # Скидка увеличилась = СПП выросла
                        elif today_discount_rounded < prev_discount_rounded:
                            decreased += 1  # Скидка уменьшилась = СПП снизилась
                        else:
                            unchanged += 1
                
                message += f"📈 <b>Статистика:</b>\n"
                message += f"• Всего отслеживается: {total_tracked}\n"
                message += f"• СПП выросла (скидка увеличилась): {increased}\n"
                message += f"• СПП снизилась (скидка уменьшилась): {decreased}\n"
                message += f"• СПП без изменений: {unchanged}\n"
                message += f"• Новые товары: {new_products}\n\n"
                
                # Отправляем в Telegram
                bot_token = os.getenv("BOT_TOKEN")
                if not bot_token:
                    logger.error("BOT_TOKEN не найден в переменных окружения")
                    continue
                    
                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                payload = {
                    "chat_id": client.group_chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                    "reply_markup": {
                        "inline_keyboard": [[
                            {
                                "text": f"📥 Подробный отчет {marketplace_name} (EXCEL)",
                                "callback_data": f"excel_report|{client.id}|{today.strftime('%Y-%m-%d')}|{marketplace}"
                            }
                        ]]
                    }
                }
                
                try:
                    response = requests.post(url, json=payload, timeout=10)
                    if response.status_code == 200:
                        logger.info(f"Отчет {marketplace_name} отправлен для клиента {client.id}")
                        total_sent += 1
                    else:
                        logger.error(f"Ошибка отправки отчета {marketplace_name} для клиента {client.id}: {response.text}")
                except Exception as e:
                    logger.error(f"Ошибка отправки отчета {marketplace_name} для клиента {client.id}: {e}")
            
            # Отмечаем, что отчет для этого клиента уже отправлен сегодня (срок действия 24 часа)
            redis_client.setex(redis_key, 86400, "sent")  # 86400 секунд = 24 часа
                
        session.close()
        
        logger.info(f"Отправлено отчетов: {total_sent}")
        return total_sent > 0
        
    except Exception as e:
        logger.exception(f"Ошибка в задаче send_daily_summary_v2: {e}")
        return False

@app.task
def send_excel_report_v2(client_id: str, date_str: str, marketplace: Optional[str] = None):
    """
    Формирует и отправляет Excel-отчет по товарам с сравнением двух периодов для клиента client_id
    Если указан marketplace, создает отчет только для этого маркетплейса
    """
    from db.session import get_sync_session
    from db.models import Client, Result
    from datetime import datetime, timedelta
    from sqlalchemy import text

    logger.info(f"Формирование Excel-отчета для клиента {client_id} за {date_str}, маркетплейс: {marketplace or 'все'}")
    session = get_sync_session()
    client = session.query(Client).filter(Client.id == client_id).first()
    if not client or not client.group_chat_id:
        logger.error(f"Клиент {client_id} не найден или не задан group_chat_id")
        return False

    try:
        date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception as e:
        logger.error(f"Неверный формат даты: {date_str}")
        return False

    # Базовый SQL запрос
    base_sql = """
        SELECT DISTINCT ON (r.product_code) 
            r.product_code, r.product_name, r.product_link, 
            r.market_price, r.showcase_price, r.timestamp,
            a.market
        FROM results r
        JOIN accounts a ON r.account_id = a.id
        WHERE r.client_id = :client_id 
            AND r.timestamp >= :date_start 
            AND r.timestamp < :date_end
    """
    
    # Добавляем фильтр по маркетплейсу если указан
    params = {
        "client_id": client_id,
        "date_start": date,
        "date_end": date + timedelta(days=1)
    }
    
    if marketplace:
        base_sql += " AND a.market = :marketplace"
        params["marketplace"] = marketplace
    
    base_sql += " ORDER BY r.product_code, r.timestamp DESC"

    # Получаем последний срез данных за дату
    current_results = session.execute(text(base_sql), params).fetchall()

    if not current_results:
        logger.info(f"Нет данных для клиента {client_id} за {date_str}, маркетплейс: {marketplace or 'все'}")
        return False

    # Получаем время текущего среза
    current_timestamp = max(r.timestamp for r in current_results)

    # Получаем предыдущий срез данных
    prev_sql = """
        SELECT DISTINCT ON (r.product_code) 
            r.product_code, r.product_name, r.product_link, 
            r.market_price, r.showcase_price, r.timestamp,
            a.market
        FROM results r
        JOIN accounts a ON r.account_id = a.id
        WHERE r.client_id = :client_id 
            AND r.timestamp < :current_timestamp
    """
    
    prev_params = {
        "client_id": client_id,
        "current_timestamp": current_timestamp
    }
    
    if marketplace:
        prev_sql += " AND a.market = :marketplace"
        prev_params["marketplace"] = marketplace
    
    prev_sql += " ORDER BY r.product_code, r.timestamp DESC"

    previous_results = session.execute(text(prev_sql), prev_params).fetchall()

    # Создаем словарь предыдущих данных для быстрого поиска
    previous_data = {}
    for r in previous_results:
        previous_data[r.product_code] = {
            'showcase_price': r.showcase_price,
            'market_price': r.market_price,
            'timestamp': r.timestamp
        }

    # Определяем название маркетплейса для файла
    marketplace_name = ""
    if marketplace == "ozon":
        marketplace_name = "_Ozon"
    elif marketplace == "wb":
        marketplace_name = "_WB"
    
    # Формируем Excel в памяти
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    worksheet_name = f"Отчет{marketplace_name}" if marketplace_name else "Отчет"
    worksheet = workbook.add_worksheet(worksheet_name)

    # Форматы для заголовков и данных
    header_format = workbook.add_format({
        'bold': True,
        'bg_color': '#D3D3D3',
        'border': 1,
        'text_wrap': True,
        'align': 'center'
    })
    
    data_format = workbook.add_format({
        'border': 1
    })
    
    percent_format = workbook.add_format({
        'border': 1,
        'num_format': '0.00%'
    })

    price_format = workbook.add_format({
        'border': 1,
        'num_format': '#,##0.00'
    })

    date_format = workbook.add_format({
        'border': 1,
        'num_format': 'dd.mm.yyyy hh:mm'
    })

    # Заголовки (убираем колонку Маркетплейс если фильтруем по одному)
    if marketplace:
        headers = [
            "Артикул", 
            "Название", 
            "Ссылка", 
            "Цена маркетплейса", 
            "Цена на витрине", 
            "Размер скидки (%)", 
            "Время замера",
            "Цена на витрине прошл",
            "Размер скидки (%) прошл", 
            "Время замера прошл"
        ]
    else:
        headers = [
            "Артикул", 
            "Название", 
            "Ссылка", 
            "Цена маркетплейса", 
            "Цена на витрине", 
            "Размер скидки (%)", 
            "Время замера",
            "Цена на витрине прошл",
            "Размер скидки (%) прошл", 
            "Время замера прошл",
            "Маркетплейс"
        ]
    
    for col, h in enumerate(headers):
        worksheet.write(0, col, h, header_format)

    # Данные
    stats_increased = 0
    stats_decreased = 0
    stats_unchanged = 0
    stats_new_products = 0

    for row, r in enumerate(current_results, start=1):
        worksheet.write(row, 0, r.product_code, data_format)
        worksheet.write(row, 1, r.product_name, data_format)
        worksheet.write(row, 2, r.product_link or "", data_format)
        worksheet.write(row, 3, r.market_price or 0, price_format)
        worksheet.write(row, 4, r.showcase_price or 0, price_format)
        
        # Рассчитываем текущий размер скидки
        current_discount_percent = 0
        if r.market_price and r.showcase_price and r.market_price > 0:
            current_discount_percent = (r.market_price - r.showcase_price) / r.market_price
        worksheet.write(row, 5, current_discount_percent, percent_format)
        
        worksheet.write(row, 6, r.timestamp, date_format)

        # Данные предыдущего периода
        prev_data = previous_data.get(r.product_code)
        if prev_data:
            prev_showcase_price = prev_data['showcase_price'] or 0
            prev_market_price = prev_data['market_price'] or 0
            prev_timestamp = prev_data['timestamp']
            
            worksheet.write(row, 7, prev_showcase_price, price_format)
            
            # Рассчитываем предыдущий размер скидки
            prev_discount_percent = 0
            if prev_market_price and prev_showcase_price and prev_market_price > 0:
                prev_discount_percent = (prev_market_price - prev_showcase_price) / prev_market_price
            worksheet.write(row, 8, prev_discount_percent, percent_format)
            
            worksheet.write(row, 9, prev_timestamp, date_format)

            # Статистика изменений СПП (сравниваем размеры скидок)
            current_market_price = r.market_price or 0
            current_showcase_price = r.showcase_price or 0
            current_discount = 0
            if current_market_price > 0 and current_showcase_price > 0:
                current_discount = (current_market_price - current_showcase_price) / current_market_price
            
            prev_discount = 0
            if prev_market_price > 0 and prev_showcase_price > 0:
                prev_discount = (prev_market_price - prev_showcase_price) / prev_market_price
            
            # Сравниваем скидки с округлением до 2 знаков
            current_discount_rounded = round(current_discount, 2)
            prev_discount_rounded = round(prev_discount, 2)
            
            if current_discount_rounded > prev_discount_rounded:
                stats_increased += 1
            elif current_discount_rounded < prev_discount_rounded:
                stats_decreased += 1
            else:
                stats_unchanged += 1
        else:
            # Нет предыдущих данных - новый товар
            worksheet.write(row, 7, "", data_format)
            worksheet.write(row, 8, "", data_format)
            worksheet.write(row, 9, "", data_format)
            stats_new_products += 1

        # Добавляем маркетплейс только если не фильтруем по одному
        if not marketplace:
            market_display = "Ozon" if r.market == "ozon" else "Wildberries"
            worksheet.write(row, 10, market_display, data_format)

    # Автоширина столбцов
    if marketplace:
        column_widths = [15, 40, 30, 20, 20, 15, 20, 20, 18, 20]
    else:
        column_widths = [15, 40, 30, 20, 20, 15, 20, 20, 18, 20, 15]
    
    for col, width in enumerate(column_widths):
        worksheet.set_column(col, col, width)

    workbook.close()
    output.seek(0)

    # Отправляем файл в Telegram
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        logger.error("BOT_TOKEN не найден в переменных окружения")
        return False
    
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    
    # Формируем название файла
    file_suffix = marketplace_name if marketplace_name else ""
    filename = f"report_comparison_{client_id}_{date_str}{file_suffix}.xlsx"
    
    # Краткое сообщение без дублирования
    marketplace_display = ""
    if marketplace == "ozon":
        marketplace_display = " Ozon"
    elif marketplace == "wb": 
        marketplace_display = " Wildberries"
    
    caption = f"📊 <b>Подробный Excel-отчет{marketplace_display} за {safe_error_message(date_str)}</b>"
    
    files = {
        'document': (filename, output.read(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    }
    data = {
        'chat_id': client.group_chat_id,
        'caption': caption,
        'parse_mode': 'HTML'
    }
    try:
        response = requests.post(url, data=data, files=files, timeout=30)
        if response.status_code == 200:
            logger.info(f"Excel-отчет{marketplace_display} отправлен для клиента {client_id}")
            return True
        else:
            logger.error(f"Ошибка отправки Excel-отчета: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Ошибка отправки Excel-отчета: {e}")
        return False
    finally:
        session.close() 