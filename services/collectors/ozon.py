import aiohttp
import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import json
import requests

logger = logging.getLogger(__name__)
api_logger = logging.getLogger("api")

def get_initial_market_prices_ozon(product_codes, account_config, test_mode=False):
    """
    Выполняет запрос к Ozon API для получения цен по списку offer_id (product_codes).
    Если test_mode=True, возвращает фиктивные цены для тестирования.
    """
    if test_mode:
        logger.info("TEST MODE: Возвращаем фиктивные цены для Ozon")
        return {str(code): 499 for code in product_codes}
    
    ozon_client_id = account_config.get("ozon_client_id")
    ozon_api_key = account_config.get("ozon_api_key")
    if not ozon_client_id or not ozon_api_key:
        logger.error("Параметры Ozon (ozon_client_id, ozon_api_key) отсутствуют в account_config")
        return {}

    ozon_url = "https://api-seller.ozon.ru/v5/product/info/prices"
    payload = {
        "cursor": "",
        "filter": {
            "offer_id": [str(code) for code in product_codes],
            "visibility": "ALL"
        },
        "limit": 1000
    }
    headers = {
        "Client-Id": ozon_client_id,
        "Api-Key": ozon_api_key,
        "Content-Type": "application/json"
    }
    logger.info("Отправка запроса к Ozon API:")
    logger.info("URL: %s", ozon_url)
    logger.info("Headers: %s", json.dumps(headers, indent=2))
    logger.info("Payload: %s", json.dumps(payload, indent=2))
    
    try:
        response = requests.post(ozon_url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        data = response.json()
        api_logger.info("Ozon API Response: %s", json.dumps(data, indent=2))
        prices = {}
        for item in data.get("items", []):
            offer_id = item.get("offer_id")
            if not offer_id:
                continue
                
            # Извлекаем цену: сначала marketing_seller_price, если нет - то price
            price = None
            price_info = item.get("price", {})
            
            # Проверяем marketing_seller_price
            if "marketing_seller_price" in price_info and price_info["marketing_seller_price"] not in [0, "0", "", None]:
                price = price_info["marketing_seller_price"]
            # Если нет marketing_seller_price, берем обычную price
            elif "price" in price_info and price_info["price"] not in [0, "0", "", None]:
                price = price_info["price"]
            
            if price is not None:
                prices[offer_id] = int(float(price))
                logger.debug(f"Цена для {offer_id}: {price} (marketing_seller_price: {price_info.get('marketing_seller_price')}, price: {price_info.get('price')})")
            else:
                logger.warning(f"Нет валидной цены для {offer_id}")
        return prices
    except Exception as e:
        logger.exception(f"Ошибка при запросе цен для offer_id {product_codes}: {e}")
        return {}

def get_initial_market_price(market, product_code, account_config=None, test_mode=False):
    if market.lower() == "ozon":
        prices = get_initial_market_prices_ozon([product_code], account_config, test_mode)
        return prices.get(str(product_code), 0.0)
    else:
        return 0.0

class OzonCollector:
    """Коллектор цен с Ozon API"""
    
    def __init__(self, client_id: str, api_key: str):
        self.client_id = client_id
        self.api_key = api_key
        self.base_url = "https://api-seller.ozon.ru"
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            headers={
                "Client-Id": self.client_id,
                "Api-Key": self.api_key,
                "Content-Type": "application/json"
            }
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            
    async def get_product_prices(self, offer_ids: List[str]) -> List[Dict[str, Any]]:
        """Получить цены товаров по offer_id"""
        if not self.session:
            raise RuntimeError("Session not initialized. Use async context manager.")
            
        url = f"{self.base_url}/v2/product/info/list"
        
        # Правильный payload для Ozon API
        payload = {
            "limit": 1000,  # Обязательный параметр
            "visibility": "ALL",  # Обязательный параметр
            "offer_id": offer_ids,
            "product_id": [],
            "sku": []
        }
        
        logger.info(f"Ozon API request: {url}")
        logger.info(f"Payload: {json.dumps(payload, indent=2)}")
        
        try:
            async with self.session.post(url, json=payload) as response:
                logger.info(f"Ozon API response status: {response.status}")
                
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Ozon API error: {error_text}")
                    return []
                    
                data = await response.json()
                logger.info(f"Ozon API response: {json.dumps(data, indent=2)}")
                
                if not data.get("result", {}).get("items"):
                    logger.warning("Ozon API returned empty items")
                    return []
                    
                prices = []
                for item in data["result"]["items"]:
                    price_info = {
                        "offer_id": item.get("offer_id"),
                        "product_id": item.get("id"),
                        "name": item.get("name", ""),
                        "price": None,
                        "old_price": None,
                        "currency": "RUB",
                        "marketplace": "ozon",
                        "collected_at": datetime.now().isoformat()
                    }
                    
                    # Извлекаем цены из разных возможных мест
                    if "price" in item:
                        price_info["price"] = item["price"].get("price", "")
                    elif "prices" in item:
                        price_info["price"] = item["prices"].get("price", "")
                        
                    if "old_price" in item:
                        price_info["old_price"] = item["old_price"]
                        
                    prices.append(price_info)
                    
                logger.info(f"Extracted {len(prices)} price records from Ozon")
                return prices
                
        except Exception as e:
            logger.error(f"Error fetching Ozon prices: {e}")
            return []
            
    async def test_connection(self) -> bool:
        """Тест подключения к API"""
        try:
            url = f"{self.base_url}/v1/info"
            async with self.session.get(url) as response:
                return response.status == 200
        except Exception as e:
            logger.error(f"Ozon connection test failed: {e}")
            return False 