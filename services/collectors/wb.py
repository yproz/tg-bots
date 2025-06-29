import logging
import requests
import json
import time
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)
api_logger = logging.getLogger("api")

def get_initial_market_prices_wb(product_codes, account_config, test_mode=False):
    """
    Выполняет запрос к Wildberries API для получения цен по списку vendorCodes (product_codes).
    Если test_mode=True, возвращает фиктивные цены для тестирования.
    """
    if test_mode:
        logger.info("TEST MODE: Возвращаем фиктивные цены для WB")
        return {str(code): 9999 for code in product_codes}
    
    wb_api_key = account_config.get("wb_api_key")
    if not wb_api_key:
        logger.error("Параметры Wildberries (wb_api_key) отсутствуют в account_config")
        return {}

    wb_url = "https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter"
    headers = {
        "Authorization": wb_api_key
    }
    # WB API не позволяет фильтровать сразу по vendorCode – поэтому будем перебором
    vendor_codes_needed = set(str(code) for code in product_codes)
    wb_prices = {}
    offset = 0
    limit = 1000  # Максимальное значение согласно документации
    logger.info("Начало запроса к WB API для vendorCodes: %s", list(vendor_codes_needed))
    
    while vendor_codes_needed:
        params = {
            "limit": limit,
            "offset": offset
        }
        logger.info("WB API запрос: URL: %s, Params: %s", wb_url, json.dumps(params))
        try:
            response = requests.get(wb_url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            api_logger.info("WB API Response (offset %s): %s", offset, json.dumps(data, indent=2))
        except Exception as e:
            logger.exception(f"Ошибка при запросе WB API на offset {offset}: {e}")
            break
        
        list_goods = data.get("data", {}).get("listGoods", [])
        if not list_goods:
            logger.info("WB API: Нет данных на offset %s", offset)
            break
        
        for item in list_goods:
            vendor_code = item.get("vendorCode", "").strip()
            if vendor_code in vendor_codes_needed:
                sizes = item.get("sizes", [])
                if sizes:
                    # Берем первую запись, можно доработать логику выбора нужного размера
                    size = sizes[0]
                    price = int(size.get("discountedPrice", 0))
                    wb_prices[vendor_code] = price
                    logger.info("Найдена цена для vendorCode %s: %s", vendor_code, price)
                    vendor_codes_needed.remove(vendor_code)
        if len(list_goods) < limit:
            logger.info("Достигнут конец списка товаров WB")
            break
        offset += limit
        time.sleep(0.1)
    
    logger.info("Завершено получение цен с WB. Обработано товаров: %s", offset)
    return wb_prices

def get_initial_market_price(market, product_code, account_config=None, test_mode=False):
    if market.lower() == "wb":
        prices = get_initial_market_prices_wb([product_code], account_config, test_mode)
        return prices.get(str(product_code), 0.0)
    else:
        return 0.0

class WildberriesCollector:
    """Коллектор цен с Wildberries API"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://discounts-prices-api.wildberries.ru"
        
    def get_product_prices(self, vendor_codes: List[str]) -> List[Dict[str, Any]]:
        """Получить цены товаров по vendor_code"""
        account_config = {
            "wb_api_key": self.api_key
        }
        
        prices_dict = get_initial_market_prices_wb(vendor_codes, account_config)
        
        prices = []
        for vendor_code, price in prices_dict.items():
            price_info = {
                "vendor_code": vendor_code,
                "price": price,
                "currency": "RUB",
                "marketplace": "wildberries",
                "collected_at": datetime.now().isoformat()
            }
            prices.append(price_info)
            
        return prices
        
    def test_connection(self) -> bool:
        """Тест подключения к API"""
        try:
            account_config = {
                "wb_api_key": self.api_key
            }
            # Тестируем на одном товаре
            test_prices = get_initial_market_prices_wb(["test"], account_config)
            return True
        except Exception as e:
            logger.error(f"Wildberries connection test failed: {e}")
            return False 