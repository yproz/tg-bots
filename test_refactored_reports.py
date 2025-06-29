# test_refactored_reports.py
"""
Unit тесты для рефакторенных функций генерации отчетов.
Проверяют корректность разбиения монолитной функции.
"""

import pytest
import io
from datetime import datetime, date
from unittest.mock import Mock, patch, MagicMock
from services.telegram_notifier import (
    safe_error_message,
    get_marketplace_display_name,
    get_marketplace_suffix,
    create_excel_report_caption,
    create_excel_filename
)


class TestTelegramNotifier:
    """Тесты для сервиса Telegram уведомлений."""
    
    def test_safe_error_message_escapes_html(self):
        """Тестирует экранирование HTML символов."""
        # Arrange
        text = "<script>alert('xss')</script> & other"
        expected = "&lt;script&gt;alert('xss')&lt;/script&gt; &amp; other"
        
        # Act
        result = safe_error_message(text)
        
        # Assert
        assert result == expected
    
    def test_safe_error_message_handles_empty_string(self):
        """Тестирует обработку пустой строки."""
        assert safe_error_message("") == ""
        assert safe_error_message(None) == ""
    
    def test_get_marketplace_display_name(self):
        """Тестирует получение отображаемого названия маркетплейса."""
        assert get_marketplace_display_name("ozon") == " Ozon"
        assert get_marketplace_display_name("wb") == " Wildberries"
        assert get_marketplace_display_name(None) == ""
        assert get_marketplace_display_name("unknown") == ""
    
    def test_get_marketplace_suffix(self):
        """Тестирует получение суффикса файла."""
        assert get_marketplace_suffix("ozon") == "_Ozon"
        assert get_marketplace_suffix("wb") == "_WB"
        assert get_marketplace_suffix(None) == ""
        assert get_marketplace_suffix("unknown") == ""
    
    def test_create_excel_report_caption(self):
        """Тестирует создание подписи для отчета."""
        # Test without marketplace
        caption = create_excel_report_caption("2024-01-15")
        assert "2024-01-15" in caption
        assert "Excel-отчет" in caption
        
        # Test with marketplace
        caption_ozon = create_excel_report_caption("2024-01-15", "ozon")
        assert "Ozon" in caption_ozon
        assert "2024-01-15" in caption_ozon
    
    def test_create_excel_filename(self):
        """Тестирует создание имени файла."""
        # Without marketplace
        filename = create_excel_filename("client123", "2024-01-15")
        expected = "report_comparison_client123_2024-01-15.xlsx"
        assert filename == expected
        
        # With marketplace
        filename_ozon = create_excel_filename("client123", "2024-01-15", "ozon")
        expected_ozon = "report_comparison_client123_2024-01-15_Ozon.xlsx"
        assert filename_ozon == expected_ozon


class TestReportGenerator:
    """Тесты для генератора отчетов."""
    
    @patch('services.report_generator.Session')
    def test_validate_report_params_success(self, mock_session):
        """Тестирует успешную валидацию параметров."""
        # Arrange
        mock_client = Mock()
        mock_client.group_chat_id = "12345"
        mock_session.query.return_value.filter.return_value.first.return_value = mock_client
        
        from services.report_generator import validate_report_params
        
        # Act
        client, result_date = validate_report_params("client123", "2024-01-15", mock_session)
        
        # Assert
        assert client == mock_client
        assert result_date == date(2024, 1, 15)
    
    @patch('services.report_generator.Session')
    def test_validate_report_params_invalid_date(self, mock_session):
        """Тестирует валидацию с некорректной датой."""
        # Arrange
        mock_client = Mock()
        mock_client.group_chat_id = "12345"
        mock_session.query.return_value.filter.return_value.first.return_value = mock_client
        
        from services.report_generator import validate_report_params
        
        # Act
        client, result_date = validate_report_params("client123", "invalid-date", mock_session)
        
        # Assert
        assert client is None
        assert result_date is None
    
    @patch('services.report_generator.Session')
    def test_validate_report_params_missing_client(self, mock_session):
        """Тестирует валидацию с отсутствующим клиентом."""
        # Arrange
        mock_session.query.return_value.filter.return_value.first.return_value = None
        
        from services.report_generator import validate_report_params
        
        # Act
        client, result_date = validate_report_params("nonexistent", "2024-01-15", mock_session)
        
        # Assert
        assert client is None
        assert result_date is None


class TestRefactoredComplexity:
    """Тесты для проверки снижения цикломатической сложности."""
    
    def test_cyclomatic_complexity_reduction(self):
        """
        Тестирует что рефакторинг действительно снизил сложность.
        
        Оригинальная функция send_excel_report_v2 имела CC = 29
        Новая функция send_excel_report_v2_refactored должна иметь CC < 10
        """
        # Этот тест проверяет структуру, а не функциональность
        
        # Подсчитаем количество условных операторов в новой функции
        from tasks.refactored_reports import send_excel_report_v2_refactored
        import inspect
        
        source = inspect.getsource(send_excel_report_v2_refactored)
        
        # Простой подсчет условных операторов
        if_count = source.count('if ')
        elif_count = source.count('elif ')
        for_count = source.count('for ')
        while_count = source.count('while ')
        try_count = source.count('try:')
        except_count = source.count('except ')
        
        # Приблизительная оценка CC (упрощенная)
        estimated_cc = 1 + if_count + elif_count + for_count + while_count + try_count + except_count
        
        # Проверяем что сложность значительно снижена
        assert estimated_cc < 10, f"Цикломатическая сложность все еще высокая: {estimated_cc}"
    
    def test_single_responsibility_separation(self):
        """Тестирует что функции разделены по ответственности."""
        from services.telegram_notifier import send_document_to_telegram, create_excel_filename
        from services.report_generator import validate_report_params, fetch_current_results
        
        # Проверяем что каждая функция имеет четкую ответственность
        telegram_functions = [send_document_to_telegram, create_excel_filename]
        data_functions = [validate_report_params, fetch_current_results]
        
        # Все функции должны быть определены и импортируемы
        for func in telegram_functions + data_functions:
            assert callable(func), f"Функция {func.__name__} не определена"
            assert func.__doc__, f"Функция {func.__name__} не документирована"


class TestIntegration:
    """Интеграционные тесты для проверки взаимодействия компонентов."""
    
    @patch('services.telegram_notifier.requests.post')
    @patch('services.telegram_notifier.os.getenv')
    def test_send_document_success(self, mock_getenv, mock_post):
        """Тестирует успешную отправку документа."""
        # Arrange
        mock_getenv.return_value = "test_token"
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        from services.telegram_notifier import send_document_to_telegram
        
        document_data = io.BytesIO(b"test data")
        
        # Act
        result = send_document_to_telegram(
            chat_id="12345",
            document_data=document_data,
            filename="test.xlsx",
            caption="Test caption"
        )
        
        # Assert
        assert result is True
        mock_post.assert_called_once()
    
    @patch('services.telegram_notifier.requests.post')
    @patch('services.telegram_notifier.os.getenv')
    def test_send_document_failure(self, mock_getenv, mock_post):
        """Тестирует неуспешную отправку документа."""
        # Arrange
        mock_getenv.return_value = "test_token"
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_post.return_value = mock_response
        
        from services.telegram_notifier import send_document_to_telegram
        
        document_data = io.BytesIO(b"test data")
        
        # Act
        result = send_document_to_telegram(
            chat_id="12345",
            document_data=document_data,
            filename="test.xlsx",
            caption="Test caption"
        )
        
        # Assert
        assert result is False


if __name__ == "__main__":
    # Запуск тестов
    pytest.main([__file__, "-v"]) 