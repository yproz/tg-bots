"""
Модуль для генерации Excel отчетов.
Разбит на отдельные функции согласно принципу Single Responsibility.
"""

import io
from datetime import datetime, timedelta, date
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None

try:
    from db.models import Client, Result
    from sqlalchemy import text
    from sqlalchemy.orm import Session
except ImportError:
    # Для случаев когда модуль импортируется без полного контекста
    pass


@dataclass
class ReportData:
    """Данные для генерации отчета."""
    current_results: List[Any]
    previous_data: Dict[str, Dict[str, Any]]
    client: Client
    date: datetime.date
    marketplace: Optional[str]


@dataclass
class ReportStats:
    """Статистика изменений в отчете."""
    increased: int = 0
    decreased: int = 0
    unchanged: int = 0
    new_products: int = 0


def validate_report_params(client_id: str, date_str: str, session) -> Tuple[Optional[Any], Optional[date]]:
    """
    Валидирует параметры для генерации отчета.
    
    Args:
        client_id: ID клиента
        date_str: Дата в формате YYYY-MM-DD
        session: Сессия БД
        
    Returns:
        Tuple[Client, date] или (None, None) при ошибке
    """
    # Проверяем клиента
    client = session.query(Client).filter(Client.id == client_id).first()
    if not client or not client.group_chat_id:
        return None, None
    
    # Проверяем дату
    try:
        date = datetime.strptime(date_str, "%Y-%m-%d").date()
        return client, date
    except ValueError:
        return None, None


def fetch_current_results(session: Session, client_id: str, date: datetime.date, marketplace: Optional[str]) -> List[Any]:
    """
    Получает текущие результаты за указанную дату.
    
    Args:
        session: Сессия БД
        client_id: ID клиента
        date: Дата для поиска
        marketplace: Фильтр по маркетплейсу (ozon/wb) или None
        
    Returns:
        Список результатов
    """
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
    
    params = {
        "client_id": client_id,
        "date_start": date,
        "date_end": date + timedelta(days=1)
    }
    
    if marketplace:
        base_sql += " AND a.market = :marketplace"
        params["marketplace"] = marketplace
    
    base_sql += " ORDER BY r.product_code, r.timestamp DESC"
    
    return session.execute(text(base_sql), params).fetchall()


def fetch_previous_results(session: Session, client_id: str, current_timestamp: datetime, marketplace: Optional[str]) -> Dict[str, Dict[str, Any]]:
    """
    Получает предыдущие результаты для сравнения.
    
    Args:
        session: Сессия БД
        client_id: ID клиента
        current_timestamp: Время текущего среза
        marketplace: Фильтр по маркетплейсу или None
        
    Returns:
        Словарь {product_code: {showcase_price, market_price, timestamp}}
    """
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
    
    # Создаем словарь для быстрого поиска
    previous_data = {}
    for r in previous_results:
        previous_data[r.product_code] = {
            'showcase_price': r.showcase_price,
            'market_price': r.market_price,
            'timestamp': r.timestamp
        }
    
    return previous_data


def create_excel_workbook() -> Tuple[xlsxwriter.Workbook, io.BytesIO]:
    """
    Создает Excel workbook в памяти.
    
    Returns:
        Tuple[workbook, output_buffer]
    """
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    return workbook, output


def setup_excel_formats(workbook: xlsxwriter.Workbook) -> Dict[str, Any]:
    """
    Настраивает форматы для Excel файла.
    
    Args:
        workbook: Excel workbook
        
    Returns:
        Словарь с форматами
    """
    return {
        'header': workbook.add_format({
            'bold': True,
            'bg_color': '#D3D3D3',
            'border': 1,
            'text_wrap': True,
            'align': 'center'
        }),
        'data': workbook.add_format({'border': 1}),
        'percent': workbook.add_format({'border': 1, 'num_format': '0.00%'}),
        'price': workbook.add_format({'border': 1, 'num_format': '#,##0.00'}),
        'date': workbook.add_format({'border': 1, 'num_format': 'dd.mm.yyyy hh:mm'})
    }


def get_report_headers(marketplace: Optional[str]) -> List[str]:
    """
    Возвращает заголовки для отчета в зависимости от фильтра маркетплейса.
    
    Args:
        marketplace: Фильтр по маркетплейсу или None
        
    Returns:
        Список заголовков
    """
    base_headers = [
        "Артикул", "Название", "Ссылка", "Цена маркетплейса", 
        "Цена на витрине", "Размер скидки (%)", "Время замера",
        "Цена на витрине прошл", "Размер скидки (%) прошл", "Время замера прошл"
    ]
    
    if not marketplace:
        base_headers.append("Маркетплейс")
    
    return base_headers


def calculate_discount_percent(market_price: Optional[float], showcase_price: Optional[float]) -> float:
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


def write_excel_data(worksheet: Any, current_results: List[Any], 
                    previous_data: Dict[str, Dict[str, Any]], formats: Dict[str, Any],
                    marketplace: Optional[str]) -> ReportStats:
    """
    Записывает данные в Excel worksheet и собирает статистику.
    
    Args:
        worksheet: Excel worksheet
        current_results: Текущие результаты
        previous_data: Предыдущие данные
        formats: Форматы для ячеек
        marketplace: Фильтр по маркетплейсу
        
    Returns:
        Статистика изменений
    """
    stats = ReportStats()
    
    for row, r in enumerate(current_results, start=1):
        # Основные данные товара
        worksheet.write(row, 0, r.product_code, formats['data'])
        worksheet.write(row, 1, r.product_name, formats['data'])
        worksheet.write(row, 2, r.product_link or "", formats['data'])
        worksheet.write(row, 3, r.market_price or 0, formats['price'])
        worksheet.write(row, 4, r.showcase_price or 0, formats['price'])
        
        # Текущий размер скидки
        current_discount = calculate_discount_percent(r.market_price, r.showcase_price)
        worksheet.write(row, 5, current_discount, formats['percent'])
        worksheet.write(row, 6, r.timestamp, formats['date'])

        # Предыдущие данные
        prev_data = previous_data.get(r.product_code)
        if prev_data:
            prev_showcase_price = prev_data['showcase_price'] or 0
            prev_market_price = prev_data['market_price'] or 0
            prev_timestamp = prev_data['timestamp']
            
            worksheet.write(row, 7, prev_showcase_price, formats['price'])
            
            # Предыдущий размер скидки
            prev_discount = calculate_discount_percent(prev_market_price, prev_showcase_price)
            worksheet.write(row, 8, prev_discount, formats['percent'])
            worksheet.write(row, 9, prev_timestamp, formats['date'])

            # Обновляем статистику
            current_discount_rounded = round(current_discount, 2)
            prev_discount_rounded = round(prev_discount, 2)
            
            if current_discount_rounded > prev_discount_rounded:
                stats.increased += 1
            elif current_discount_rounded < prev_discount_rounded:
                stats.decreased += 1
            else:
                stats.unchanged += 1
        else:
            # Новый товар
            worksheet.write(row, 7, "", formats['data'])
            worksheet.write(row, 8, "", formats['data'])
            worksheet.write(row, 9, "", formats['data'])
            stats.new_products += 1

        # Маркетплейс (если не фильтруем)
        if not marketplace:
            market_display = "Ozon" if r.market == "ozon" else "Wildberries"
            worksheet.write(row, 10, market_display, formats['data'])
    
    return stats


def setup_column_widths(worksheet: Any, marketplace: Optional[str]) -> None:
    """
    Настраивает ширину столбцов.
    
    Args:
        worksheet: Excel worksheet
        marketplace: Фильтр по маркетплейсу
    """
    if marketplace:
        column_widths = [15, 40, 30, 20, 20, 15, 20, 20, 18, 20]
    else:
        column_widths = [15, 40, 30, 20, 20, 15, 20, 20, 18, 20, 15]
    
    for col, width in enumerate(column_widths):
        worksheet.set_column(col, col, width)


def generate_excel_file(report_data: ReportData) -> Tuple[io.BytesIO, ReportStats]:
    """
    Основная функция генерации Excel файла.
    
    Args:
        report_data: Данные для отчета
        
    Returns:
        Tuple[excel_buffer, stats]
    """
    workbook, output = create_excel_workbook()
    
    # Определяем название листа
    marketplace_name = ""
    if report_data.marketplace == "ozon":
        marketplace_name = "_Ozon"
    elif report_data.marketplace == "wb":
        marketplace_name = "_WB"
    
    worksheet_name = f"Отчет{marketplace_name}" if marketplace_name else "Отчет"
    worksheet = workbook.add_worksheet(worksheet_name)
    
    # Настройка форматов
    formats = setup_excel_formats(workbook)
    
    # Заголовки
    headers = get_report_headers(report_data.marketplace)
    for col, header in enumerate(headers):
        worksheet.write(0, col, header, formats['header'])
    
    # Данные и статистика
    stats = write_excel_data(
        worksheet, 
        report_data.current_results, 
        report_data.previous_data,
        formats,
        report_data.marketplace
    )
    
    # Настройка ширины столбцов
    setup_column_widths(worksheet, report_data.marketplace)
    
    workbook.close()
    output.seek(0)
    
    return output, stats 