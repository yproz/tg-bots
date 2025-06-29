#!/usr/bin/env python3
"""
Тест для локального воспроизведения ошибки с загрузкой Excel файлов
"""
import asyncio
import os
import sys
import tempfile
import pandas as pd
import html
from pathlib import Path

# Добавляем корневую директорию в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent))

def safe_error_message(error) -> str:
    """Безопасно экранирует HTML в сообщениях об ошибках"""
    return html.escape(str(error))

async def test_excel_upload_with_errors():
    """Тестируем загрузку Excel файла с ошибками"""
    print("🔍 Тестируем загрузку Excel файла с ошибками...")
    
    try:
        from services import excel_loader
        from db.session import create_tables
        
        # Создаем таблицы
        await create_tables()
        
        # Создаем тестовый Excel файл с ошибками
        test_data = [
            {
                "client_id": "TEST",
                "market": "ozon",
                "account_id": "test_account",
                "product_code": "TEST001",
                "product_name": "Товар с <class='error'>ошибкой HTML</class>",
                "product_link": "https://example.com/test001"
            },
            {
                "client_id": "",  # Пустой client_id - ошибка
                "market": "wb",
                "account_id": "test_account",
                "product_code": "TEST002",
                "product_name": "Товар с пустым клиентом",
                "product_link": "https://example.com/test002"
            },
            {
                "client_id": "TEST",
                "market": "invalid_market",  # Неверный market - ошибка
                "account_id": "test_account",
                "product_code": "TEST003",
                "product_name": "Товар с неверным маркетом",
                "product_link": "https://example.com/test003"
            }
        ]
        
        # Создаем временный Excel файл
        df = pd.DataFrame(test_data)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            df.to_excel(tmp.name, index=False)
            test_file_path = tmp.name
        
        print(f"Создан тестовый файл: {test_file_path}")
        
        # Тестируем загрузку
        ok, errors, error_file_path = await excel_loader.load_excel(test_file_path)
        
        print(f"Результат загрузки: {ok} успешных, {len(errors)} ошибок")
        
        # Формируем сообщение как в боте
        if ok > 0:
            message = f"✅ Успешно загружено <b>{ok}</b> товаров"
            if errors:
                message += f"\n⚠️ Ошибок: <b>{len(errors)}</b>"
        else:
            message = f"❌ Не удалось загрузить товары"
        
        if errors:
            message += "\n\n<i>Первые ошибки:</i>\n"
            for i, error in enumerate(errors[:5]):
                message += f"• {error}\n"
            if len(errors) > 5:
                message += f"• ... и ещё {len(errors) - 5} ошибок"
        
        print("Сообщение для отправки в Telegram:")
        print(message)
        
        # Проверяем, есть ли проблемные HTML теги
        print("\n🔍 Анализ HTML тегов в сообщении:")
        if "<class=" in message:
            print("❌ Найден проблемный тег <class=")
        if "class=" in message:
            print("❌ Найден атрибут class=")
        
        # Тестируем экранирование
        print("\n🔍 Тестируем экранирование ошибок:")
        for error in errors:
            escaped = safe_error_message(error)
            print(f"Оригинал: {error}")
            print(f"Экранированный: {escaped}")
            print()
        
        # Очищаем временные файлы
        os.unlink(test_file_path)
        if error_file_path and os.path.exists(error_file_path):
            os.unlink(error_file_path)
            
        return True
        
    except Exception as e:
        print(f"❌ Ошибка в тесте: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_html_escaping():
    """Тестируем экранирование HTML"""
    print("🔍 Тестируем экранирование HTML...")
    
    test_strings = [
        "Обычная строка",
        "Строка с <b>жирным</b> текстом",
        "Строка с <class='error'>классом</class>",
        "Строка с <div class='container'>контейнером</div>",
        "Строка с & амперсандом",
        "Строка с \"кавычками\"",
        "Строка с 'одинарными кавычками'",
    ]
    
    for test_str in test_strings:
        escaped = safe_error_message(test_str)
        print(f"Оригинал: {test_str}")
        print(f"Экранированный: {escaped}")
        print()

async def main():
    """Основная функция тестирования"""
    print("🚀 Запуск тестов загрузки Excel файлов...")
    print("=" * 60)
    
    # Тест экранирования HTML
    await test_html_escaping()
    
    print("=" * 60)
    
    # Тест загрузки Excel с ошибками
    await test_excel_upload_with_errors()
    
    print("=" * 60)
    print("✅ Тестирование завершено")

if __name__ == "__main__":
    asyncio.run(main()) 