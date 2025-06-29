#!/usr/bin/env python3
"""
Простой тест для проверки основных компонентов PriceBot
"""
import asyncio
import os
import sys
from pathlib import Path

# Добавляем корневую директорию в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent))

async def test_database():
    """Тест подключения к базе данных"""
    print("🔍 Тестируем подключение к базе данных...")
    try:
        from db.session import async_session_factory, create_tables
        from db.models import Client, Account, Product
        
        # Создаем таблицы
        await create_tables()
        print("✅ Таблицы созданы/проверены")
        
        # Тестируем сессию
        async with async_session_factory() as session:
            # Проверяем, что можем выполнить простой запрос
            from sqlalchemy import select
            result = await session.execute(select(Client))
            clients = result.scalars().all()
            print(f"✅ Подключение к БД работает, клиентов: {len(clients)}")
            
    except Exception as e:
        print(f"❌ Ошибка БД: {e}")
        return False
    return True

async def test_collectors():
    """Тест сборщиков цен"""
    print("🔍 Тестируем сборщики цен...")
    try:
        from services.collectors.ozon import fetch_prices_ozon
        from services.collectors.wb import fetch_prices_wb
        
        # Тестируем с пустыми данными
        mock_account = {
            "account_id": "test",
            "ozon_client_id": "123",
            "api_key": "test_key"
        }
        mock_products = []
        
        result_ozon = await fetch_prices_ozon(mock_account, mock_products)
        result_wb = await fetch_prices_wb(mock_account, mock_products)
        
        print("✅ Сборщики цен работают")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка сборщиков: {e}")
        return False

async def test_excel_loader():
    """Тест загрузчика Excel"""
    print("🔍 Тестируем загрузчик Excel...")
    try:
        from services import excel_loader
        
        # Тестируем генерацию шаблона
        template_path = await excel_loader.generate_template()
        if os.path.exists(template_path):
            print("✅ Генерация шаблона работает")
            return True
        else:
            print("❌ Шаблон не создан")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка Excel loader: {e}")
        return False



async def main():
    """Основная функция тестирования"""
    print("🚀 Запуск тестов PriceBot...")
    print("=" * 50)
    
    tests = [
        test_database,
        test_collectors,
        test_excel_loader
    ]
    
    results = []
    for test in tests:
        try:
            result = await test()
            results.append(result)
        except Exception as e:
            print(f"❌ Критическая ошибка в тесте: {e}")
            results.append(False)
        print()
    
    # Итоговый результат
    passed = sum(results)
    total = len(results)
    
    print("=" * 50)
    print(f"📊 Результаты: {passed}/{total} тестов прошли")
    
    if passed == total:
        print("🎉 Все тесты прошли успешно!")
        return 0
    else:
        print("⚠️  Некоторые тесты не прошли")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code) 