# test_excel_processor.py
"""
Unit тесты для модуля services/excel_processor.py
Покрывают рефакторенную функцию sync_load_excel.
"""

import pytest
import pandas as pd
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
from services.excel_processor import (
    ValidationError,
    ProcessingResult,
    read_excel_file,
    validate_excel_columns,
    check_for_duplicates,
    validate_row_data,
    find_account_id,
    upsert_product,
    process_single_row,
    process_excel_rows,
    sync_load_excel_refactored,
    validate_excel_file_exists,
    get_file_info,
    REQUIRED_COLUMNS,
    ALLOWED_MARKETS
)


class TestExcelFileOperations:
    """Тесты операций с Excel файлами."""

    def test_read_excel_file_success(self):
        """Тест успешного чтения Excel файла."""
        # Создаем временный Excel файл
        test_data = pd.DataFrame({
            'client_id': ['TEST'],
            'market': ['ozon'],
            'account_id': ['test_acc'],
            'product_code': ['12345'],
            'product_name': ['Test Product'],
            'product_link': ['http://test.com']
        })
        
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp:
            test_data.to_excel(tmp.name, index=False)
            tmp_path = tmp.name

        try:
            result_df = read_excel_file(tmp_path)
            assert len(result_df) == 1
            assert result_df.iloc[0]['client_id'] == 'TEST'
        finally:
            os.unlink(tmp_path)

    def test_read_excel_file_invalid_path(self):
        """Тест чтения несуществующего файла."""
        with pytest.raises(ValueError, match="Ошибка чтения файла"):
            read_excel_file("/invalid/path/file.xlsx")

    def test_validate_excel_file_exists_true(self):
        """Тест проверки существования файла - существует."""
        with tempfile.NamedTemporaryFile() as tmp:
            assert validate_excel_file_exists(tmp.name) is True

    def test_validate_excel_file_exists_false(self):
        """Тест проверки существования файла - не существует."""
        assert validate_excel_file_exists("/invalid/path") is False

    def test_get_file_info_exists(self):
        """Тест получения информации о существующем файле."""
        with tempfile.NamedTemporaryFile(suffix='.xlsx') as tmp:
            info = get_file_info(tmp.name)
            assert info['exists'] is True
            assert 'size' in info
            assert 'modified' in info
            assert info['extension'] == '.xlsx'

    def test_get_file_info_not_exists(self):
        """Тест получения информации о несуществующем файле."""
        info = get_file_info("/invalid/path")
        assert info['exists'] is False


class TestDataValidation:
    """Тесты валидации данных."""

    def test_validate_excel_columns_success(self):
        """Тест успешной валидации колонок."""
        df = pd.DataFrame(columns=REQUIRED_COLUMNS)
        # Не должно бросать исключение
        validate_excel_columns(df)

    def test_validate_excel_columns_missing(self):
        """Тест валидации с отсутствующими колонками."""
        df = pd.DataFrame(columns=['client_id', 'market'])  # Не хватает колонок
        
        with pytest.raises(ValueError, match="отсутствуют колонки"):
            validate_excel_columns(df)

    def test_check_for_duplicates_no_duplicates(self):
        """Тест проверки дубликатов - нет дубликатов."""
        df = pd.DataFrame({
            'client_id': ['CLIENT1', 'CLIENT1'],
            'product_code': ['PROD1', 'PROD2'],
            'market': ['ozon', 'ozon'],
            'account_id': ['acc1', 'acc1'],
            'product_name': ['Product 1', 'Product 2'],
            'product_link': ['link1', 'link2']
        })
        
        duplicates = check_for_duplicates(df)
        assert len(duplicates) == 0

    def test_check_for_duplicates_with_duplicates(self):
        """Тест проверки дубликатов - есть дубликаты."""
        df = pd.DataFrame({
            'client_id': ['CLIENT1', 'CLIENT1'],
            'product_code': ['PROD1', 'PROD1'],  # Дубликат
            'market': ['ozon', 'ozon'],
            'account_id': ['acc1', 'acc1'],
            'product_name': ['Product 1', 'Product 1'],
            'product_link': ['link1', 'link1']
        })
        
        duplicates = check_for_duplicates(df)
        assert len(duplicates) == 1
        assert ('CLIENT1', 'PROD1') in duplicates

    def test_validate_row_data_success(self):
        """Тест успешной валидации строки."""
        row_data = {
            'client_id': 'CLIENT1',
            'market': 'ozon',
            'account_id': 'acc1',
            'product_code': 'PROD1',
            'product_name': 'Product 1',
            'product_link': 'http://link1.com'
        }
        
        result = validate_row_data(row_data, 2)
        assert result is None

    def test_validate_row_data_empty_client_id(self):
        """Тест валидации с пустым client_id."""
        row_data = {
            'client_id': '',
            'market': 'ozon',
            'account_id': 'acc1',
            'product_code': 'PROD1',
            'product_name': 'Product 1',
            'product_link': 'http://link1.com'
        }
        
        result = validate_row_data(row_data, 2)
        assert result is not None and "пустой client_id" in result

    def test_validate_row_data_invalid_market(self):
        """Тест валидации с неверным market."""
        row_data = {
            'client_id': 'CLIENT1',
            'market': 'invalid_market',
            'account_id': 'acc1',
            'product_code': 'PROD1',
            'product_name': 'Product 1',
            'product_link': 'http://link1.com'
        }
        
        result = validate_row_data(row_data, 2)
        assert result is not None and "неверный market" in result

    @pytest.mark.parametrize("field_name", [
        'market', 'account_id', 'product_code', 'product_name'
    ])
    def test_validate_row_data_empty_required_fields(self, field_name):
        """Тест валидации с пустыми обязательными полями."""
        row_data = {
            'client_id': 'CLIENT1',
            'market': 'ozon',
            'account_id': 'acc1',
            'product_code': 'PROD1',
            'product_name': 'Product 1',
            'product_link': 'http://link1.com'
        }
        row_data[field_name] = ''  # Делаем поле пустым
        
        result = validate_row_data(row_data, 2)
        assert result is not None and (f"пустой {field_name}" in result or f"пустое {field_name}" in result)


class TestDatabaseOperations:
    """Тесты операций с базой данных."""

    def test_find_account_id_success(self):
        """Тест успешного поиска аккаунта."""
        mock_conn = Mock()
        mock_result = Mock()
        mock_result.fetchone.return_value = [123]
        mock_conn.execute.return_value = mock_result
        
        result = find_account_id(mock_conn, 'CLIENT1', 'ozon', 'acc1')
        
        assert result == 123
        mock_conn.execute.assert_called_once()

    def test_find_account_id_not_found(self):
        """Тест поиска несуществующего аккаунта."""
        mock_conn = Mock()
        mock_result = Mock()
        mock_result.fetchone.return_value = None
        mock_conn.execute.return_value = mock_result
        
        result = find_account_id(mock_conn, 'CLIENT1', 'ozon', 'acc1')
        
        assert result is None

    def test_find_account_id_exception(self):
        """Тест обработки исключения при поиске аккаунта."""
        mock_conn = Mock()
        mock_conn.execute.side_effect = Exception("DB Error")
        
        result = find_account_id(mock_conn, 'CLIENT1', 'ozon', 'acc1')
        
        assert result is None

    def test_upsert_product_success(self):
        """Тест успешного upsert товара."""
        mock_conn = Mock()
        
        result = upsert_product(
            mock_conn, 'CLIENT1', 123, 'PROD1', 
            'Product 1', 'http://link1.com'
        )
        
        assert result is True
        mock_conn.execute.assert_called_once()
        mock_conn.commit.assert_called_once()

    def test_upsert_product_exception(self):
        """Тест обработки исключения при upsert товара."""
        mock_conn = Mock()
        mock_conn.execute.side_effect = Exception("DB Error")
        
        result = upsert_product(
            mock_conn, 'CLIENT1', 123, 'PROD1', 
            'Product 1', 'http://link1.com'
        )
        
        assert result is False
        mock_conn.rollback.assert_called_once()


class TestRowProcessing:
    """Тесты обработки строк."""

    def test_process_single_row_duplicate(self):
        """Тест обработки строки с дубликатом."""
        mock_conn = Mock()
        row_data = {
            'client_id': 'CLIENT1',
            'product_code': 'PROD1',
            'market': 'ozon',
            'account_id': 'acc1',
            'product_name': 'Product 1',
            'product_link': 'http://link1.com'
        }
        duplicates = {('CLIENT1', 'PROD1')}
        
        result = process_single_row(mock_conn, row_data, 2, duplicates)
        
        assert isinstance(result, ValidationError)
        assert "дубликат product_code" in result.error_message

    def test_process_single_row_validation_error(self):
        """Тест обработки строки с ошибкой валидации."""
        mock_conn = Mock()
        row_data = {
            'client_id': '',  # Пустой client_id
            'product_code': 'PROD1',
            'market': 'ozon',
            'account_id': 'acc1',
            'product_name': 'Product 1',
            'product_link': 'http://link1.com'
        }
        duplicates = set()
        
        result = process_single_row(mock_conn, row_data, 2, duplicates)
        
        assert isinstance(result, ValidationError)
        assert "пустой client_id" in result.error_message

    def test_process_single_row_account_not_found(self):
        """Тест обработки строки с несуществующим аккаунтом."""
        mock_conn = Mock()
        mock_result = Mock()
        mock_result.fetchone.return_value = None
        mock_conn.execute.return_value = mock_result
        
        row_data = {
            'client_id': 'CLIENT1',
            'product_code': 'PROD1',
            'market': 'ozon',
            'account_id': 'acc1',
            'product_name': 'Product 1',
            'product_link': 'http://link1.com'
        }
        duplicates = set()
        
        result = process_single_row(mock_conn, row_data, 2, duplicates)
        
        assert isinstance(result, ValidationError)
        assert "аккаунт не найден" in result.error_message

    def test_process_single_row_upsert_failed(self):
        """Тест обработки строки с ошибкой upsert."""
        mock_conn = Mock()
        # Настраиваем успешный поиск аккаунта
        mock_result = Mock()
        mock_result.fetchone.return_value = [123]
        mock_conn.execute.return_value = mock_result
        
        # Настраиваем провал upsert
        mock_conn.execute.side_effect = [mock_result, Exception("Upsert failed")]
        
        row_data = {
            'client_id': 'CLIENT1',
            'product_code': 'PROD1',
            'market': 'ozon',
            'account_id': 'acc1',
            'product_name': 'Product 1',
            'product_link': 'http://link1.com'
        }
        duplicates = set()
        
        result = process_single_row(mock_conn, row_data, 2, duplicates)
        
        assert isinstance(result, ValidationError)
        assert "ошибка при сохранении товара" in result.error_message

    def test_process_single_row_success(self):
        """Тест успешной обработки строки."""
        mock_conn = Mock()
        # Настраиваем успешный поиск аккаунта
        mock_result = Mock()
        mock_result.fetchone.return_value = [123]
        mock_conn.execute.return_value = mock_result
        
        row_data = {
            'client_id': 'CLIENT1',
            'product_code': 'PROD1',
            'market': 'ozon',
            'account_id': 'acc1',
            'product_name': 'Product 1',
            'product_link': 'http://link1.com'
        }
        duplicates = set()
        
        result = process_single_row(mock_conn, row_data, 2, duplicates)
        
        assert result is None  # Успех


class TestExcelProcessing:
    """Тесты полной обработки Excel."""

    @patch('services.excel_processor.check_for_duplicates')
    @patch('services.excel_processor.process_single_row')
    def test_process_excel_rows_success(self, mock_process_row, mock_check_duplicates):
        """Тест успешной обработки всех строк."""
        # Подготовка
        df = pd.DataFrame({
            'client_id': ['CLIENT1', 'CLIENT2'],
            'product_code': ['PROD1', 'PROD2'],
            'market': ['ozon', 'wb'],
            'account_id': ['acc1', 'acc2'],
            'product_name': ['Product 1', 'Product 2'],
            'product_link': ['link1', 'link2']
        })
        
        mock_engine = Mock()
        mock_conn = Mock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        
        mock_check_duplicates.return_value = set()
        mock_process_row.return_value = None  # Успех для всех строк
        
        # Тест
        result = process_excel_rows(df, mock_engine)
        
        # Проверки
        assert result.success_count == 2
        assert len(result.errors) == 0
        assert len(result.error_rows) == 0
        assert mock_process_row.call_count == 2

    @patch('services.excel_processor.check_for_duplicates')
    @patch('services.excel_processor.process_single_row')
    def test_process_excel_rows_with_errors(self, mock_process_row, mock_check_duplicates):
        """Тест обработки строк с ошибками."""
        # Подготовка
        df = pd.DataFrame({
            'client_id': ['CLIENT1', ''],  # Вторая строка с ошибкой
            'product_code': ['PROD1', 'PROD2'],
            'market': ['ozon', 'wb'],
            'account_id': ['acc1', 'acc2'],
            'product_name': ['Product 1', 'Product 2'],
            'product_link': ['link1', 'link2']
        })
        
        mock_engine = Mock()
        mock_conn = Mock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        
        mock_check_duplicates.return_value = set()
        
        # Первая строка успешна, вторая с ошибкой
        mock_process_row.side_effect = [
            None,  # Успех для первой строки
            ValidationError(3, "Test error", ["3", "CLIENT1", "PROD2", "wb", "acc2", "Product 2", "link2"])
        ]
        
        # Тест
        result = process_excel_rows(df, mock_engine)
        
        # Проверки
        assert result.success_count == 1
        assert len(result.errors) == 1
        assert len(result.error_rows) == 1
        assert "Test error" in result.errors[0]

    @patch('services.excel_processor.create_sync_engine')
    @patch('services.excel_processor.read_excel_file')
    @patch('services.excel_processor.validate_excel_columns')
    @patch('services.excel_processor.process_excel_rows')
    def test_sync_load_excel_refactored_success(
        self, mock_process_rows, mock_validate_cols, 
        mock_read_file, mock_create_engine
    ):
        """Тест успешного выполнения главной функции."""
        # Подготовка
        mock_df = Mock()
        mock_engine = Mock()
        
        mock_create_engine.return_value = mock_engine
        mock_read_file.return_value = mock_df
        mock_validate_cols.return_value = None
        mock_process_rows.return_value = ProcessingResult(
            success_count=5,
            errors=['Error 1'],
            error_rows=[['1', 'data']]
        )
        
        # Тест
        success, errors, error_rows = sync_load_excel_refactored('/test/path.xlsx')
        
        # Проверки
        assert success == 5
        assert len(errors) == 1
        assert len(error_rows) == 1
        
        mock_create_engine.assert_called_once()
        mock_read_file.assert_called_once_with('/test/path.xlsx')
        mock_validate_cols.assert_called_once_with(mock_df)
        mock_process_rows.assert_called_once_with(mock_df, mock_engine)

    @patch('services.excel_processor.create_sync_engine')
    def test_sync_load_excel_refactored_exception(self, mock_create_engine):
        """Тест обработки исключения в главной функции."""
        # Подготовка
        mock_create_engine.side_effect = Exception("Critical error")
        
        # Тест
        success, errors, error_rows = sync_load_excel_refactored('/test/path.xlsx')
        
        # Проверки
        assert success == 0
        assert len(errors) == 1
        assert "Critical error" in errors[0]
        assert len(error_rows) == 0


class TestConstants:
    """Тесты констант модуля."""

    def test_required_columns_complete(self):
        """Тест полноты списка обязательных колонок."""
        expected_columns = [
            'client_id', 'market', 'account_id', 
            'product_code', 'product_name', 'product_link'
        ]
        
        assert REQUIRED_COLUMNS == expected_columns

    def test_allowed_markets_complete(self):
        """Тест списка разрешенных маркетплейсов."""
        expected_markets = ['ozon', 'wb']
        
        assert ALLOWED_MARKETS == expected_markets


if __name__ == '__main__':
    pytest.main([__file__, '-v']) 