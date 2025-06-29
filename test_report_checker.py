# test_report_checker.py
"""
Unit тесты для рефакторенного модуля проверки отчетов.
Проверяют корректность разбиения функции check_reports.
"""

import pytest
import json
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
from services.report_checker import (
    OrderStatus,
    ReportItem,
    validate_client_and_get_orders,
    fetch_parser_reports,
    parse_parser_response,
    find_order_status,
    download_and_parse_report,
    extract_report_items,
    calculate_final_price,
    update_results_prices,
    check_reports_refactored
)


class TestOrderStatus:
    """Тесты для dataclass OrderStatus."""
    
    def test_order_status_creation(self):
        """Тестирует создание OrderStatus."""
        status = OrderStatus(
            task_id="test_task",
            status="completed",
            report_url="http://example.com/report.json"
        )
        
        assert status.task_id == "test_task"
        assert status.status == "completed"
        assert status.report_url == "http://example.com/report.json"
        assert status.found is False  # default value
    
    def test_order_status_defaults(self):
        """Тестирует значения по умолчанию."""
        status = OrderStatus(task_id="test", status="pending", report_url=None)
        
        assert status.found is False
        assert status.report_url is None


class TestReportItem:
    """Тесты для dataclass ReportItem."""
    
    def test_report_item_creation(self):
        """Тестирует создание ReportItem."""
        item = ReportItem(
            product_code="ABC123",
            final_price=99.99,
            offers=[{"Price": "99.99", "PromoPrice": ""}]
        )
        
        assert item.product_code == "ABC123"
        assert item.final_price == 99.99
        assert len(item.offers) == 1


class TestValidateClientAndGetOrders:
    """Тесты для валидации клиента и получения заказов."""
    
    @patch('services.report_checker.Client')
    @patch('services.report_checker.Order')
    def test_validate_success(self, mock_order, mock_client):
        """Тестирует успешную валидацию."""
        # Arrange
        mock_session = Mock()
        mock_client_obj = Mock()
        mock_orders = [Mock(), Mock()]
        
        mock_session.query.return_value.filter.return_value.first.return_value = mock_client_obj
        mock_session.query.return_value.filter.return_value.all.return_value = mock_orders
        
        # Act
        client, orders = validate_client_and_get_orders(mock_session, "client123")
        
        # Assert
        assert client == mock_client_obj
        assert orders == mock_orders
    
    @patch('services.report_checker.Client')
    def test_validate_client_not_found(self, mock_client):
        """Тестирует случай отсутствующего клиента."""
        # Arrange
        mock_session = Mock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        
        # Act
        client, orders = validate_client_and_get_orders(mock_session, "nonexistent")
        
        # Assert
        assert client is None
        assert orders == []
    
    @patch('services.report_checker.Client')
    @patch('services.report_checker.Order')
    def test_validate_no_orders(self, mock_order, mock_client):
        """Тестирует случай отсутствия заказов."""
        # Arrange
        mock_session = Mock()
        mock_client_obj = Mock()
        
        mock_session.query.return_value.filter.return_value.first.return_value = mock_client_obj
        mock_session.query.return_value.filter.return_value.all.return_value = []
        
        # Act
        client, orders = validate_client_and_get_orders(mock_session, "client123")
        
        # Assert
        assert client == mock_client_obj
        assert orders == []


class TestFetchParserReports:
    """Тесты для получения отчетов от парсера."""
    
    @patch('services.report_checker.requests.post')
    def test_fetch_success(self, mock_post):
        """Тестирует успешное получение отчетов."""
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": ["test_data"]}
        mock_post.return_value = mock_response
        
        # Act
        result = fetch_parser_reports("http://api.example.com", "test_key")
        
        # Assert
        assert result == {"data": ["test_data"]}
        mock_post.assert_called_once()
    
    @patch('services.report_checker.requests.post')
    def test_fetch_failure(self, mock_post):
        """Тестирует неуспешный запрос."""
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_post.return_value = mock_response
        
        # Act
        result = fetch_parser_reports("http://api.example.com", "bad_key")
        
        # Assert
        assert result is None


class TestParseParserResponse:
    """Тесты для парсинга ответа парсера."""
    
    def test_parse_list_with_data(self):
        """Тестирует парсинг списка с данными."""
        # Arrange
        response = [{"other": "value"}, {"data": "target_data"}]
        
        # Act
        result = parse_parser_response(response)
        
        # Assert
        assert result == "target_data"
    
    def test_parse_direct_data(self):
        """Тестирует парсинг прямых данных."""
        # Arrange
        response = {"direct": "data"}
        
        # Act
        result = parse_parser_response(response)
        
        # Assert
        assert result == {"direct": "data"}


class TestFindOrderStatus:
    """Тесты для поиска статуса заказа."""
    
    def test_find_existing_order(self):
        """Тестирует поиск существующего заказа."""
        # Arrange
        data = [
            [
                {"userlabel": "task123"},
                {"status": "completed"},
                {"report_json": "http://example.com/report.json"}
            ]
        ]
        
        # Act
        status = find_order_status(data, "task123")
        
        # Assert
        assert status.found is True
        assert status.task_id == "task123"
        assert status.status == "completed"
        assert status.report_url == "http://example.com/report.json"
    
    def test_find_nonexistent_order(self):
        """Тестирует поиск несуществующего заказа."""
        # Arrange
        data = [
            [
                {"userlabel": "other_task"},
                {"status": "completed"}
            ]
        ]
        
        # Act
        status = find_order_status(data, "task123")
        
        # Assert
        assert status.found is False
        assert status.task_id == "task123"


class TestCalculateFinalPrice:
    """Тесты для вычисления итоговой цены."""
    
    def test_promo_price_available(self):
        """Тестирует использование промо цены."""
        # Arrange
        offer = {"PromoPrice": "89.99", "Price": "99.99"}
        
        # Act
        price = calculate_final_price(offer)
        
        # Assert
        assert price == 89.99
    
    def test_regular_price_only(self):
        """Тестирует использование обычной цены."""
        # Arrange
        offer = {"PromoPrice": "", "Price": "99.99"}
        
        # Act
        price = calculate_final_price(offer)
        
        # Assert
        assert price == 99.99
    
    def test_no_valid_price(self):
        """Тестирует отсутствие валидной цены."""
        # Arrange
        offer = {"PromoPrice": "", "Price": ""}
        
        # Act
        price = calculate_final_price(offer)
        
        # Assert
        assert price is None
    
    def test_invalid_price_format(self):
        """Тестирует некорректный формат цены."""
        # Arrange
        offer = {"PromoPrice": "invalid", "Price": "also_invalid"}
        
        # Act
        price = calculate_final_price(offer)
        
        # Assert
        assert price is None


class TestExtractReportItems:
    """Тесты для извлечения данных из отчета."""
    
    def test_extract_valid_items(self):
        """Тестирует извлечение валидных товаров."""
        # Arrange
        json_data = {
            "data": [
                {
                    "code": "ABC123",
                    "offers": [{"Price": "99.99", "PromoPrice": ""}]
                },
                {
                    "code": "DEF456", 
                    "offers": [{"Price": "", "PromoPrice": "89.99"}]
                }
            ]
        }
        
        # Act
        items = extract_report_items(json_data)
        
        # Assert
        assert len(items) == 2
        assert items[0].product_code == "ABC123"
        assert items[0].final_price == 99.99
        assert items[1].product_code == "DEF456"
        assert items[1].final_price == 89.99
    
    def test_extract_skip_invalid_items(self):
        """Тестирует пропуск товаров без валидных цен."""
        # Arrange
        json_data = {
            "data": [
                {
                    "code": "ABC123",
                    "offers": []  # Нет предложений
                },
                {
                    "code": "DEF456",
                    "offers": [{"Price": "", "PromoPrice": ""}]  # Нет цен
                }
            ]
        }
        
        # Act
        items = extract_report_items(json_data)
        
        # Assert
        assert len(items) == 0


class TestUpdateResultsPrices:
    """Тесты для обновления цен в результатах."""
    
    @patch('services.report_checker.text')
    def test_update_prices_success(self, mock_text):
        """Тестирует успешное обновление цен."""
        # Arrange
        mock_session = Mock()
        mock_result = Mock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result
        
        report_items = [
            ReportItem("ABC123", 99.99, []),
            ReportItem("DEF456", 89.99, [])
        ]
        
        # Act
        count = update_results_prices(mock_session, "client123", "task456", report_items)
        
        # Assert
        assert count == 2
        assert mock_session.execute.call_count == 2


class TestCheckReportsRefactored:
    """Интеграционные тесты для основной функции."""
    
    @patch('services.report_checker.get_sync_session')
    @patch('services.report_checker.validate_client_and_get_orders')
    @patch('services.report_checker.fetch_parser_reports')
    @patch('services.report_checker.parse_parser_response')
    @patch('services.report_checker.find_order_status')
    @patch('services.report_checker.process_completed_order')
    def test_check_reports_success(self, mock_process, mock_find, mock_parse, 
                                   mock_fetch, mock_validate, mock_session):
        """Тестирует успешную проверку отчетов."""
        # Arrange
        mock_client = Mock()
        mock_client.parser_api_key = "test_key"
        mock_orders = [Mock()]
        mock_orders[0].task_id = "task123"
        
        mock_validate.return_value = (mock_client, mock_orders)
        mock_fetch.return_value = {"data": "test_data"}
        mock_parse.return_value = "parsed_data"
        
        mock_status = OrderStatus("task123", "completed", "http://report.url", True)
        mock_find.return_value = mock_status
        mock_process.return_value = True
        
        # Act
        result = check_reports_refactored("http://api.url", "client123")
        
        # Assert
        assert result is True
        mock_validate.assert_called_once()
        mock_fetch.assert_called_once()
        mock_process.assert_called_once()
    
    @patch('services.report_checker.get_sync_session')
    @patch('services.report_checker.validate_client_and_get_orders')
    def test_check_reports_no_client(self, mock_validate, mock_session):
        """Тестирует случай отсутствия клиента."""
        # Arrange
        mock_validate.return_value = (None, [])
        
        # Act
        result = check_reports_refactored("http://api.url", "nonexistent")
        
        # Assert
        assert result is False


class TestComplexityReduction:
    """Тесты для проверки снижения цикломатической сложности."""
    
    def test_function_separation(self):
        """Тестирует что функции разделены правильно."""
        functions = [
            validate_client_and_get_orders,
            fetch_parser_reports,
            parse_parser_response,
            find_order_status,
            download_and_parse_report,
            extract_report_items,
            calculate_final_price,
            update_results_prices,
            check_reports_refactored
        ]
        
        # Проверяем что все функции определены и документированы
        for func in functions:
            assert callable(func), f"Функция {func.__name__} не определена"
            assert func.__doc__, f"Функция {func.__name__} не документирована"
    
    def test_cyclomatic_complexity_reduction(self):
        """Проверяет снижение цикломатической сложности."""
        import inspect
        
        # Получаем исходный код основной функции
        source = inspect.getsource(check_reports_refactored)
        
        # Простой подсчет условных операторов
        if_count = source.count('if ')
        elif_count = source.count('elif ')
        for_count = source.count('for ')
        while_count = source.count('while ')
        try_count = source.count('try:')
        
        # Приблизительная оценка CC
        estimated_cc = 1 + if_count + elif_count + for_count + while_count + try_count
        
        # Проверяем что сложность значительно снижена (было 25)
        assert estimated_cc < 10, f"Цикломатическая сложность все еще высокая: {estimated_cc}"


if __name__ == "__main__":
    # Запуск тестов
    pytest.main([__file__, "-v"]) 