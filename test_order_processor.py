# test_order_processor.py
"""
Unit тесты для модуля services/order_processor.py
Покрывают рефакторенную функцию send_order.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from services.order_processor import (
    AccountData,
    ProductBatch,
    OrderResult,
    validate_client_and_account,
    get_products_for_account,
    validate_product_link,
    create_account_data,
    create_task_id,
    prepare_product_batch,
    get_marketplace_prices,
    create_parser_payload,
    send_batch_to_parser,
    save_order_and_results,
    process_products_in_batches,
    send_order_refactored,
    validate_batch_size,
    get_batch_processing_info,
    DEFAULT_BATCH_SIZE,
    PARSER_BASE_URL
)


class TestDataModels:
    """Тесты структур данных."""

    def test_account_data_creation(self):
        """Тест создания AccountData."""
        account_data = AccountData(
            account_id=123,
            client_id="CLIENT1",
            market="ozon",
            region="77",
            account_id_str="acc123",
            api_key="key123"
        )
        
        assert account_data.account_id == 123
        assert account_data.client_id == "CLIENT1"
        assert account_data.market == "ozon"
        assert account_data.ozon_client_id is None

    def test_product_batch_creation(self):
        """Тест создания ProductBatch."""
        products = [{"code": "123", "name": "Product 1"}]
        batch = ProductBatch(
            products=products,
            product_codes=["123"],
            task_id="CLIENTE_O20240101123456"
        )
        
        assert len(batch.products) == 1
        assert batch.product_codes == ["123"]
        assert "CLIENTE_O" in batch.task_id

    def test_order_result_success(self):
        """Тест успешного OrderResult."""
        result = OrderResult(success=True, orders_created=5)
        
        assert result.success is True
        assert result.orders_created == 5
        assert result.error_message is None

    def test_order_result_failure(self):
        """Тест неуспешного OrderResult."""
        result = OrderResult(
            success=False, 
            orders_created=0, 
            error_message="Test error"
        )
        
        assert result.success is False
        assert result.orders_created == 0
        assert result.error_message == "Test error"


class TestValidation:
    """Тесты валидации."""

    def test_validate_client_and_account_success(self):
        """Тест успешной валидации клиента и аккаунта."""
        mock_session = Mock()
        mock_client = Mock()
        mock_client.id = "CLIENT1"
        mock_account = Mock()
        mock_account.id = 123
        
        mock_session.query.return_value.filter.return_value.first.side_effect = [
            mock_client, mock_account
        ]
        
        client, account = validate_client_and_account(mock_session, "CLIENT1", 123)
        
        assert client == mock_client
        assert account == mock_account

    def test_validate_client_and_account_client_not_found(self):
        """Тест валидации с несуществующим клиентом."""
        mock_session = Mock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        
        client, account = validate_client_and_account(mock_session, "CLIENT1", 123)
        
        assert client is None
        assert account is None

    def test_validate_client_and_account_exception(self):
        """Тест обработки исключения при валидации."""
        mock_session = Mock()
        mock_session.query.side_effect = Exception("DB Error")
        
        client, account = validate_client_and_account(mock_session, "CLIENT1", 123)
        
        assert client is None
        assert account is None

    def test_validate_product_link_wb_valid(self):
        """Тест валидации валидной WB ссылки."""
        link = "https://www.wildberries.ru/catalog/123456"
        result = validate_product_link(link, "wb")
        
        assert result == link

    def test_validate_product_link_ozon_valid(self):
        """Тест валидации валидной Ozon ссылки."""
        link = "https://www.ozon.ru/product/123456"
        result = validate_product_link(link, "ozon")
        
        assert result == link

    def test_validate_product_link_invalid_market(self):
        """Тест валидации ссылки с неверным маркетплейсом."""
        link = "https://www.wildberries.ru/catalog/123456"
        result = validate_product_link(link, "ozon")
        
        assert result is None

    def test_validate_product_link_empty(self):
        """Тест валидации пустой ссылки."""
        result = validate_product_link("", "ozon")
        
        assert result is None

    def test_validate_batch_size_valid(self):
        """Тест валидации корректного размера пакета."""
        result = validate_batch_size(500)
        
        assert result == 500

    def test_validate_batch_size_zero(self):
        """Тест валидации нулевого размера пакета."""
        result = validate_batch_size(0)
        
        assert result == DEFAULT_BATCH_SIZE

    def test_validate_batch_size_too_large(self):
        """Тест валидации слишком большого размера пакета."""
        result = validate_batch_size(15000)
        
        assert result == 10000


class TestProductProcessing:
    """Тесты обработки товаров."""

    def test_get_products_for_account_success(self):
        """Тест успешного получения товаров."""
        mock_session = Mock()
        mock_products = [Mock(), Mock(), Mock()]
        mock_session.query.return_value.filter.return_value.all.return_value = mock_products
        
        products = get_products_for_account(mock_session, "CLIENT1", 123)
        
        assert len(products) == 3
        assert products == mock_products

    def test_get_products_for_account_no_products(self):
        """Тест получения товаров - товары не найдены."""
        mock_session = Mock()
        mock_session.query.return_value.filter.return_value.all.return_value = []
        
        products = get_products_for_account(mock_session, "CLIENT1", 123)
        
        assert len(products) == 0

    def test_get_products_for_account_exception(self):
        """Тест обработки исключения при получении товаров."""
        mock_session = Mock()
        mock_session.query.side_effect = Exception("DB Error")
        
        products = get_products_for_account(mock_session, "CLIENT1", 123)
        
        assert len(products) == 0

    def test_prepare_product_batch(self):
        """Тест подготовки пакета товаров."""
        mock_products = []
        for i in range(3):
            product = Mock()
            product.product_code = f"PROD{i}"
            product.product_name = f"Product {i}"
            product.product_link = f"https://www.ozon.ru/product/{i}"
            mock_products.append(product)
        
        account_data = AccountData(
            account_id=123,
            client_id="CLIENT1",
            market="ozon",
            region="77",
            account_id_str="acc123",
            api_key="key123"
        )
        
        batch = prepare_product_batch(mock_products, account_data, 0, 2)
        
        assert len(batch.products) == 2
        assert len(batch.product_codes) == 2
        assert batch.product_codes == ["PROD0", "PROD1"]
        assert "CLIENT1" in batch.task_id

    def test_create_task_id_ozon(self):
        """Тест создания task_id для Ozon."""
        task_id = create_task_id("CLIENT1", "ozon")
        
        assert task_id.startswith("CLIENT1O")
        assert len(task_id) == len("CLIENT1O20240101123456")

    def test_create_task_id_wb(self):
        """Тест создания task_id для WB."""
        task_id = create_task_id("CLIENT1", "wb")
        
        assert task_id.startswith("CLIENT1W")
        assert len(task_id) == len("CLIENT1W20240101123456")


class TestAccountData:
    """Тесты работы с данными аккаунта."""

    def test_create_account_data(self):
        """Тест создания данных аккаунта."""
        mock_client = Mock()
        mock_client.id = "CLIENT1"
        
        mock_account = Mock()
        mock_account.id = 123
        mock_account.market = "ozon"
        mock_account.region = "77"
        mock_account.account_id = "acc123"
        mock_account.api_key = "key123"
        mock_account.ozon_client_id = "ozon_client_123"
        
        account_data = create_account_data(mock_client, mock_account)
        
        assert account_data.client_id == "CLIENT1"
        assert account_data.account_id == 123
        assert account_data.market == "ozon"
        assert account_data.ozon_client_id == "ozon_client_123"


class TestMarketplaceIntegration:
    """Тесты интеграции с маркетплейсами."""

    @patch('services.order_processor.get_initial_market_prices_ozon')
    def test_get_marketplace_prices_ozon(self, mock_ozon_prices):
        """Тест получения цен с Ozon."""
        mock_ozon_prices.return_value = {"123": 100.0, "456": 200.0}
        
        account_data = AccountData(
            account_id=123,
            client_id="CLIENT1",
            market="ozon",
            region="77",
            account_id_str="acc123",
            api_key="ozon_key",
            ozon_client_id="ozon_client_123"
        )
        
        prices = get_marketplace_prices(["123", "456"], account_data, False)
        
        assert prices == {"123": 100.0, "456": 200.0}
        mock_ozon_prices.assert_called_once()

    @patch('services.order_processor.get_initial_market_prices_wb')
    def test_get_marketplace_prices_wb(self, mock_wb_prices):
        """Тест получения цен с WB."""
        mock_wb_prices.return_value = {"789": 50.0}
        
        account_data = AccountData(
            account_id=123,
            client_id="CLIENT1",
            market="wb",
            region="77",
            account_id_str="acc123",
            api_key="wb_key"
        )
        
        prices = get_marketplace_prices(["789"], account_data, False)
        
        assert prices == {"789": 50.0}
        mock_wb_prices.assert_called_once()

    def test_get_marketplace_prices_unsupported_market(self):
        """Тест получения цен с неподдерживаемого маркетплейса."""
        account_data = AccountData(
            account_id=123,
            client_id="CLIENT1",
            market="unsupported",
            region="77",
            account_id_str="acc123",
            api_key="key123"
        )
        
        prices = get_marketplace_prices(["123"], account_data, False)
        
        assert prices == {}

    @patch('services.order_processor.get_initial_market_prices_ozon')
    def test_get_marketplace_prices_exception(self, mock_ozon_prices):
        """Тест обработки исключения при получении цен."""
        mock_ozon_prices.side_effect = Exception("API Error")
        
        account_data = AccountData(
            account_id=123,
            client_id="CLIENT1",
            market="ozon",
            region="77",
            account_id_str="acc123",
            api_key="ozon_key"
        )
        
        prices = get_marketplace_prices(["123"], account_data, False)
        
        assert prices == {}


class TestParserIntegration:
    """Тесты интеграции с парсером."""

    def test_create_parser_payload(self):
        """Тест создания payload для парсера."""
        mock_client = Mock()
        mock_client.parser_api_key = "parser_key_123"
        
        account_data = AccountData(
            account_id=123,
            client_id="CLIENT1",
            market="ozon",
            region="77",
            account_id_str="acc123",
            api_key="key123"
        )
        
        batch = ProductBatch(
            products=[{"code": "123", "name": "Product 1"}],
            product_codes=["123"],
            task_id="CLIENT1O20240101123456"
        )
        
        payload = create_parser_payload(mock_client, account_data, batch)
        
        assert payload["apikey"] == "parser_key_123"
        assert payload["regionid"] == "77"
        assert payload["market"] == "ozon"
        assert payload["userlabel"] == "CLIENT1O20240101123456"
        assert len(payload["products"]) == 1

    @patch('services.order_processor.requests.post')
    def test_send_batch_to_parser_success(self, mock_post):
        """Тест успешной отправки в парсер."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "Success"
        mock_post.return_value = mock_response
        
        payload = {"userlabel": "test_task"}
        
        status, text = send_batch_to_parser(payload, False)
        
        assert status == 200
        assert text == "Success"
        mock_post.assert_called_once()

    def test_send_batch_to_parser_test_mode(self):
        """Тест отправки в парсер в тестовом режиме."""
        payload = {"userlabel": "test_task"}
        
        status, text = send_batch_to_parser(payload, True)
        
        assert status == 200
        assert "TEST MODE" in text

    @patch('services.order_processor.requests.post')
    def test_send_batch_to_parser_exception(self, mock_post):
        """Тест обработки исключения при отправке в парсер."""
        mock_post.side_effect = Exception("Network Error")
        
        payload = {"userlabel": "test_task"}
        
        status, text = send_batch_to_parser(payload, False)
        
        assert status == 500
        assert "Network Error" in text


class TestDatabaseOperations:
    """Тесты операций с базой данных."""

    def test_save_order_and_results_success(self):
        """Тест успешного сохранения заказа и результатов."""
        mock_session = Mock()
        
        account_data = AccountData(
            account_id=123,
            client_id="CLIENT1",
            market="ozon",
            region="77",
            account_id_str="acc123",
            api_key="key123"
        )
        
        batch = ProductBatch(
            products=[
                {"code": "123", "name": "Product 1", "linkset": ["http://link1.com"]},
                {"code": "456", "name": "Product 2", "linkset": []}
            ],
            product_codes=["123", "456"],
            task_id="CLIENT1O20240101123456"
        )
        
        prices = {"123": 100.0, "456": 200.0}
        
        result = save_order_and_results(
            mock_session, "CLIENT1", account_data, batch, prices, 999
        )
        
        assert result is True
        assert mock_session.add.call_count == 3  # 1 order + 2 results

    def test_save_order_and_results_exception(self):
        """Тест обработки исключения при сохранении."""
        mock_session = Mock()
        mock_session.add.side_effect = Exception("DB Error")
        
        account_data = AccountData(
            account_id=123,
            client_id="CLIENT1",
            market="ozon",
            region="77",
            account_id_str="acc123",
            api_key="key123"
        )
        
        batch = ProductBatch(
            products=[{"code": "123", "name": "Product 1", "linkset": []}],
            product_codes=["123"],
            task_id="CLIENT1O20240101123456"
        )
        
        result = save_order_and_results(
            mock_session, "CLIENT1", account_data, batch, {}, 999
        )
        
        assert result is False


class TestBatchProcessing:
    """Тесты пакетной обработки."""

    def test_get_batch_processing_info(self):
        """Тест получения информации о пакетной обработке."""
        info = get_batch_processing_info(1500, 500)
        
        assert info["total_products"] == 1500
        assert info["batch_size"] == 500
        assert info["total_batches"] == 3
        assert info["estimated_time_seconds"] == 3

    def test_get_batch_processing_info_remainder(self):
        """Тест получения информации с остатком."""
        info = get_batch_processing_info(1001, 500)
        
        assert info["total_batches"] == 3  # 500 + 500 + 1


class TestMainFunction:
    """Тесты главной функции."""

    @patch('services.order_processor.get_sync_session')
    @patch('services.order_processor.validate_client_and_account')
    @patch('services.order_processor.get_products_for_account')
    @patch('services.order_processor.process_products_in_batches')
    def test_send_order_refactored_success(
        self, mock_process_batches, mock_get_products, 
        mock_validate, mock_get_session
    ):
        """Тест успешного выполнения главной функции."""
        # Подготовка
        mock_session = Mock()
        mock_get_session.return_value = mock_session
        
        mock_client = Mock()
        mock_account = Mock()
        mock_validate.return_value = (mock_client, mock_account)
        
        mock_products = [Mock(), Mock()]
        mock_get_products.return_value = mock_products
        
        mock_process_batches.return_value = 2
        
        # Тест
        result = send_order_refactored("CLIENT1", 123, 1000, False)
        
        # Проверки
        assert result.success is True
        assert result.orders_created == 2
        assert result.error_message is None
        
        mock_validate.assert_called_once_with(mock_session, "CLIENT1", 123)
        mock_get_products.assert_called_once_with(mock_session, "CLIENT1", 123)
        mock_process_batches.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()

    @patch('services.order_processor.get_sync_session')
    @patch('services.order_processor.validate_client_and_account')
    def test_send_order_refactored_client_not_found(self, mock_validate, mock_get_session):
        """Тест с несуществующим клиентом."""
        mock_session = Mock()
        mock_get_session.return_value = mock_session
        mock_validate.return_value = (None, None)
        
        result = send_order_refactored("CLIENT1", 123)
        
        assert result.success is False
        assert result.orders_created == 0
        assert "не найден" in result.error_message

    @patch('services.order_processor.get_sync_session')
    @patch('services.order_processor.validate_client_and_account')
    @patch('services.order_processor.get_products_for_account')
    def test_send_order_refactored_no_products(
        self, mock_get_products, mock_validate, mock_get_session
    ):
        """Тест без товаров."""
        mock_session = Mock()
        mock_get_session.return_value = mock_session
        
        mock_client = Mock()
        mock_account = Mock()
        mock_validate.return_value = (mock_client, mock_account)
        
        mock_get_products.return_value = []
        
        result = send_order_refactored("CLIENT1", 123)
        
        assert result.success is False
        assert result.orders_created == 0
        assert "не найдены" in result.error_message

    @patch('services.order_processor.get_sync_session')
    def test_send_order_refactored_exception(self, mock_get_session):
        """Тест обработки исключения в главной функции."""
        mock_get_session.side_effect = Exception("Critical error")
        
        result = send_order_refactored("CLIENT1", 123)
        
        assert result.success is False
        assert result.orders_created == 0
        assert "Critical error" in result.error_message


if __name__ == '__main__':
    pytest.main([__file__, '-v']) 