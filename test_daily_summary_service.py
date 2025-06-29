# test_daily_summary_service.py
"""
Unit тесты для рефакторенного модуля ежедневных отчетов.
Проверяют корректность разбиения функции send_daily_summary_v2.
"""

import pytest
from datetime import datetime, date, timedelta
from unittest.mock import Mock, patch, MagicMock
from services.daily_summary_service import (
    MarketplaceStats,
    SummaryData,
    get_redis_client,
    safe_error_message,
    get_clients_for_summary,
    is_summary_already_sent,
    mark_summary_as_sent,
    fetch_today_results,
    fetch_previous_results,
    calculate_discount_percent,
    calculate_marketplace_stats,
    get_marketplace_display_info,
    format_summary_message,
    create_inline_keyboard,
    send_telegram_message,
    generate_summary_for_marketplace,
    send_daily_summary_refactored,
    process_marketplace_summary
)


class TestMarketplaceStats:
    """Тесты для dataclass MarketplaceStats."""
    
    def test_marketplace_stats_creation(self):
        """Тестирует создание MarketplaceStats."""
        stats = MarketplaceStats(
            total_tracked=100,
            increased=25,
            decreased=15,
            unchanged=55,
            new_products=5
        )
        
        assert stats.total_tracked == 100
        assert stats.increased == 25
        assert stats.decreased == 15
        assert stats.unchanged == 55
        assert stats.new_products == 5


class TestSummaryData:
    """Тесты для dataclass SummaryData."""
    
    def test_summary_data_creation(self):
        """Тестирует создание SummaryData."""
        client = Mock()
        today_results = [Mock(), Mock()]
        previous_results = [Mock()]
        today_timestamp = datetime.now()
        previous_timestamp = datetime.now() - timedelta(days=1)
        stats = MarketplaceStats(10, 2, 3, 4, 1)
        
        data = SummaryData(
            client=client,
            marketplace="ozon",
            today_results=today_results,
            previous_results=previous_results,
            today_timestamp=today_timestamp,
            previous_timestamp=previous_timestamp,
            stats=stats
        )
        
        assert data.client == client
        assert data.marketplace == "ozon"
        assert len(data.today_results) == 2
        assert len(data.previous_results) == 1
        assert data.stats.total_tracked == 10


class TestSafeErrorMessage:
    """Тесты для safe_error_message."""
    
    def test_safe_error_message_html_escaping(self):
        """Тестирует экранирование HTML символов."""
        message = safe_error_message("<script>alert('xss')</script>")
        assert "&lt;script&gt;" in message
        assert "&lt;/script&gt;" in message
    
    def test_safe_error_message_none(self):
        """Тестирует обработку None."""
        message = safe_error_message(None)
        assert message == ""
    
    def test_safe_error_message_number(self):
        """Тестирует обработку чисел."""
        message = safe_error_message(123)
        assert message == "123"


class TestGetClientsForSummary:
    """Тесты для получения клиентов."""
    
    @patch('services.daily_summary_service.Client')
    def test_get_specific_client(self, mock_client):
        """Тестирует получение конкретного клиента."""
        mock_session = Mock()
        mock_clients = [Mock()]
        mock_session.query.return_value.filter.return_value.all.return_value = mock_clients
        
        result = get_clients_for_summary(mock_session, "client123")
        
        assert result == mock_clients
        mock_session.query.assert_called_once()
    
    @patch('services.daily_summary_service.Client')
    def test_get_all_clients(self, mock_client):
        """Тестирует получение всех клиентов."""
        mock_session = Mock()
        mock_clients = [Mock(), Mock()]
        mock_session.query.return_value.all.return_value = mock_clients
        
        result = get_clients_for_summary(mock_session, None)
        
        assert result == mock_clients
        mock_session.query.assert_called_once()


class TestRedisFunctions:
    """Тесты для функций работы с Redis."""
    
    def test_is_summary_already_sent_true(self):
        """Тестирует проверку уже отправленного отчета."""
        mock_redis = Mock()
        mock_redis.get.return_value = b'sent'
        
        result = is_summary_already_sent(mock_redis, "client123", "2024-01-01")
        
        assert result is True
        mock_redis.get.assert_called_once_with("daily_summary_sent:client123:2024-01-01")
    
    def test_is_summary_already_sent_false(self):
        """Тестирует проверку неотправленного отчета."""
        mock_redis = Mock()
        mock_redis.get.return_value = None
        
        result = is_summary_already_sent(mock_redis, "client123", "2024-01-01")
        
        assert result is False
    
    def test_mark_summary_as_sent(self):
        """Тестирует отметку отчета как отправленного."""
        mock_redis = Mock()
        
        mark_summary_as_sent(mock_redis, "client123", "2024-01-01")
        
        mock_redis.setex.assert_called_once_with(
            "daily_summary_sent:client123:2024-01-01", 
            86400, 
            "sent"
        )


class TestDatabaseFunctions:
    """Тесты для функций работы с БД."""
    
    def test_fetch_today_results(self):
        """Тестирует получение сегодняшних результатов."""
        mock_session = Mock()
        mock_results = [Mock(), Mock()]
        mock_session.execute.return_value.fetchall.return_value = mock_results
        
        today = date(2024, 1, 1)
        result = fetch_today_results(mock_session, "client123", "ozon", today)
        
        assert result == mock_results
        mock_session.execute.assert_called_once()
    
    def test_fetch_previous_results(self):
        """Тестирует получение предыдущих результатов."""
        mock_session = Mock()
        mock_results = [Mock()]
        mock_session.execute.return_value.fetchall.return_value = mock_results
        
        timestamp = datetime(2024, 1, 1, 12, 0, 0)
        result = fetch_previous_results(mock_session, "client123", "ozon", timestamp)
        
        assert result == mock_results
        mock_session.execute.assert_called_once()


class TestCalculateDiscountPercent:
    """Тесты для расчета процента скидки."""
    
    def test_calculate_discount_percent_normal(self):
        """Тестирует нормальный расчет скидки."""
        discount = calculate_discount_percent(100.0, 80.0)
        assert discount == 0.2  # 20% скидка
    
    def test_calculate_discount_percent_zero_market_price(self):
        """Тестирует обработку нулевой цены маркетплейса."""
        discount = calculate_discount_percent(0.0, 80.0)
        assert discount == 0.0
    
    def test_calculate_discount_percent_zero_showcase_price(self):
        """Тестирует обработку нулевой цены витрины."""
        discount = calculate_discount_percent(100.0, 0.0)
        assert discount == 0.0
    
    def test_calculate_discount_percent_none_values(self):
        """Тестирует обработку None значений."""
        discount = calculate_discount_percent(None, None)
        assert discount == 0.0


class TestCalculateMarketplaceStats:
    """Тесты для расчета статистики маркетплейса."""
    
    def test_calculate_marketplace_stats_with_changes(self):
        """Тестирует расчет статистики с изменениями."""
        # Создаем mock результаты
        today_result1 = Mock()
        today_result1.product_code = "ABC123"
        today_result1.market_price = 100.0
        today_result1.showcase_price = 80.0  # 20% скидка
        
        today_result2 = Mock()
        today_result2.product_code = "DEF456"
        today_result2.market_price = 200.0
        today_result2.showcase_price = 180.0  # 10% скидка
        
        today_result3 = Mock()
        today_result3.product_code = "GHI789"
        today_result3.market_price = 300.0
        today_result3.showcase_price = 270.0  # 10% скидка (новый товар)
        
        previous_result1 = Mock()
        previous_result1.product_code = "ABC123"
        previous_result1.market_price = 100.0
        previous_result1.showcase_price = 90.0  # 10% скидка (была меньше)
        
        previous_result2 = Mock()
        previous_result2.product_code = "DEF456"
        previous_result2.market_price = 200.0
        previous_result2.showcase_price = 160.0  # 20% скидка (была больше)
        
        today_results = [today_result1, today_result2, today_result3]
        previous_results = [previous_result1, previous_result2]
        
        stats = calculate_marketplace_stats(today_results, previous_results)
        
        assert stats.total_tracked == 3
        assert stats.increased == 1  # ABC123: 10% -> 20%
        assert stats.decreased == 1  # DEF456: 20% -> 10%
        assert stats.unchanged == 0
        assert stats.new_products == 1  # GHI789
    
    def test_calculate_marketplace_stats_no_previous_data(self):
        """Тестирует статистику без предыдущих данных."""
        today_results = [Mock(), Mock()]
        previous_results = []
        
        stats = calculate_marketplace_stats(today_results, previous_results)
        
        assert stats.total_tracked == 2
        assert stats.new_products == 2
        assert stats.increased == 0
        assert stats.decreased == 0
        assert stats.unchanged == 0


class TestGetMarketplaceDisplayInfo:
    """Тесты для получения информации о маркетплейсе."""
    
    def test_get_ozon_info(self):
        """Тестирует информацию для Ozon."""
        name, emoji = get_marketplace_display_info("ozon")
        assert name == "Ozon"
        assert emoji == "🟠"
    
    def test_get_wb_info(self):
        """Тестирует информацию для Wildberries."""
        name, emoji = get_marketplace_display_info("wb")
        assert name == "Wildberries"
        assert emoji == "🟣"
    
    def test_get_unknown_marketplace_info(self):
        """Тестирует информацию для неизвестного маркетплейса."""
        name, emoji = get_marketplace_display_info("unknown")
        assert name == "Unknown"
        assert emoji == "📊"


class TestFormatSummaryMessage:
    """Тесты для форматирования сообщения."""
    
    def test_format_summary_message_ozon(self):
        """Тестирует форматирование сообщения для Ozon."""
        client = Mock()
        client.name = "Test Client"
        client.id = "client123"
        
        stats = MarketplaceStats(100, 10, 5, 80, 5)
        today_timestamp = datetime(2024, 1, 1, 12, 0, 0)
        
        summary_data = SummaryData(
            client=client,
            marketplace="ozon",
            today_results=[],
            previous_results=[],
            today_timestamp=today_timestamp,
            previous_timestamp=None,
            stats=stats
        )
        
        today = date(2024, 1, 1)
        message = format_summary_message(summary_data, today)
        
        assert "🟠" in message  # Ozon emoji
        assert "Ozon" in message
        assert "Test Client" in message
        assert "client123" in message
        assert "100" in message  # total_tracked
        assert "10" in message   # increased
        assert "5" in message    # decreased and new_products
        assert "80" in message   # unchanged


class TestCreateInlineKeyboard:
    """Тесты для создания inline клавиатуры."""
    
    def test_create_inline_keyboard_ozon(self):
        """Тестирует создание клавиатуры для Ozon."""
        today = date(2024, 1, 1)
        keyboard = create_inline_keyboard("client123", today, "ozon")
        
        assert "inline_keyboard" in keyboard
        button = keyboard["inline_keyboard"][0][0]
        assert "Ozon" in button["text"]
        assert "EXCEL" in button["text"]
        assert "excel_report|client123|2024-01-01|ozon" == button["callback_data"]


class TestSendTelegramMessage:
    """Тесты для отправки сообщений в Telegram."""
    
    @patch('services.daily_summary_service.os.getenv')
    @patch('services.daily_summary_service.requests.post')
    def test_send_telegram_message_success(self, mock_post, mock_getenv):
        """Тестирует успешную отправку сообщения."""
        mock_getenv.return_value = "test_token"
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        result = send_telegram_message("chat123", "Test message", {})
        
        assert result is True
        mock_post.assert_called_once()
    
    @patch('services.daily_summary_service.os.getenv')
    def test_send_telegram_message_no_token(self, mock_getenv):
        """Тестирует отправку без токена."""
        mock_getenv.return_value = None
        
        result = send_telegram_message("chat123", "Test message", {})
        
        assert result is False
    
    @patch('services.daily_summary_service.os.getenv')
    @patch('services.daily_summary_service.requests.post')
    def test_send_telegram_message_api_error(self, mock_post, mock_getenv):
        """Тестирует обработку ошибки API."""
        mock_getenv.return_value = "test_token"
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_post.return_value = mock_response
        
        result = send_telegram_message("chat123", "Test message", {})
        
        assert result is False


class TestGenerateSummaryForMarketplace:
    """Тесты для генерации отчета по маркетплейсу."""
    
    @patch('services.daily_summary_service.fetch_today_results')
    @patch('services.daily_summary_service.fetch_previous_results')
    @patch('services.daily_summary_service.calculate_marketplace_stats')
    def test_generate_summary_success(self, mock_calc_stats, mock_fetch_prev, mock_fetch_today):
        """Тестирует успешную генерацию отчета."""
        mock_session = Mock()
        mock_client = Mock()
        mock_client.id = "client123"
        
        today_results = [Mock()]
        today_results[0].timestamp = datetime(2024, 1, 1, 12, 0, 0)
        mock_fetch_today.return_value = today_results
        
        previous_results = [Mock()]
        previous_results[0].timestamp = datetime(2024, 1, 1, 10, 0, 0)
        mock_fetch_prev.return_value = previous_results
        
        stats = MarketplaceStats(1, 0, 0, 1, 0)
        mock_calc_stats.return_value = stats
        
        today = date(2024, 1, 1)
        result = generate_summary_for_marketplace(mock_session, mock_client, "ozon", today)
        
        assert result is not None
        assert result.client == mock_client
        assert result.marketplace == "ozon"
        assert result.stats == stats
    
    @patch('services.daily_summary_service.fetch_today_results')
    def test_generate_summary_no_data(self, mock_fetch_today):
        """Тестирует генерацию при отсутствии данных."""
        mock_session = Mock()
        mock_client = Mock()
        mock_client.id = "client123"
        
        mock_fetch_today.return_value = []
        
        today = date(2024, 1, 1)
        result = generate_summary_for_marketplace(mock_session, mock_client, "ozon", today)
        
        assert result is None


class TestSendDailySummaryRefactored:
    """Интеграционные тесты для основной функции."""
    
    @patch('services.daily_summary_service.get_sync_session')
    @patch('services.daily_summary_service.get_redis_client')
    @patch('services.daily_summary_service.get_clients_for_summary')
    @patch('services.daily_summary_service.is_summary_already_sent')
    @patch('services.daily_summary_service.process_marketplace_summary')
    @patch('services.daily_summary_service.mark_summary_as_sent')
    def test_send_daily_summary_success(self, mock_mark, mock_process, mock_is_sent, 
                                        mock_get_clients, mock_redis, mock_session):
        """Тестирует успешную отправку отчетов."""
        # Arrange
        mock_client = Mock()
        mock_client.id = "client123"
        mock_client.group_chat_id = "chat123"
        
        mock_get_clients.return_value = [mock_client]
        mock_is_sent.return_value = False
        mock_process.return_value = True
        
        # Act
        result = send_daily_summary_refactored("client123")
        
        # Assert
        assert result == 2  # 2 marketplaces
        mock_process.assert_called()
        mock_mark.assert_called_once()
    
    @patch('services.daily_summary_service.get_sync_session')
    @patch('services.daily_summary_service.get_redis_client')
    @patch('services.daily_summary_service.get_clients_for_summary')
    def test_send_daily_summary_no_clients(self, mock_get_clients, mock_redis, mock_session):
        """Тестирует случай отсутствия клиентов."""
        mock_get_clients.return_value = []
        
        result = send_daily_summary_refactored("nonexistent")
        
        assert result == 0


class TestComplexityReduction:
    """Тесты для проверки снижения цикломатической сложности."""
    
    def test_function_separation(self):
        """Тестирует что функции разделены правильно."""
        functions = [
            get_redis_client,
            safe_error_message,
            get_clients_for_summary,
            is_summary_already_sent,
            mark_summary_as_sent,
            fetch_today_results,
            fetch_previous_results,
            calculate_discount_percent,
            calculate_marketplace_stats,
            get_marketplace_display_info,
            format_summary_message,
            create_inline_keyboard,
            send_telegram_message,
            generate_summary_for_marketplace,
            send_daily_summary_refactored,
            process_marketplace_summary
        ]
        
        # Проверяем что все функции определены и документированы
        for func in functions:
            assert callable(func), f"Функция {func.__name__} не определена"
            assert func.__doc__, f"Функция {func.__name__} не документирована"
    
    def test_cyclomatic_complexity_reduction(self):
        """Проверяет снижение цикломатической сложности."""
        import inspect
        
        # Получаем исходный код основной функции
        source = inspect.getsource(send_daily_summary_refactored)
        
        # Простой подсчет условных операторов
        if_count = source.count('if ')
        elif_count = source.count('elif ')  
        for_count = source.count('for ')
        while_count = source.count('while ')
        try_count = source.count('try:')
        
        # Приблизительная оценка CC
        estimated_cc = 1 + if_count + elif_count + for_count + while_count + try_count
        
        # Проверяем что сложность значительно снижена (было 20)
        assert estimated_cc < 12, f"Цикломатическая сложность все еще высокая: {estimated_cc}"


if __name__ == "__main__":
    # Запуск тестов
    pytest.main([__file__, "-v"]) 