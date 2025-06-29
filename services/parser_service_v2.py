"""
Сервис для работы с парсером.market API v2
Реализация согласно правильному примеру
"""
import logging
import requests
import json
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import text

from db.models import Client, Account, Product, Order, Result
from services.collectors.ozon import get_initial_market_prices_ozon
from services.collectors.wb import get_initial_market_prices_wb

logger = logging.getLogger(__name__)

class ParserServiceV2:
    """Сервис для работы с парсером.market API"""
    
    def __init__(self):
        self.base_url = "https://parser.market/wp-json/client-api/v1"
        
    def send_order(self, client_id: str, account_id: int, batch_size: int = 1000, test_mode: bool = False) -> bool:
        """
        Отправка заказа в парсер с получением цен из API маркетплейсов
        """
        logger.info(f"Запуск отправки задания на сбор данных для клиента {client_id}, аккаунт {account_id}")
        
        try:
            # Получаем данные клиента и аккаунта
            from db.session import get_sync_session
            session = get_sync_session()
            
            client = session.query(Client).filter(Client.id == client_id).first()
            if not client:
                logger.error(f"Клиент {client_id} не найден")
                return False
                
            account = session.query(Account).filter(Account.id == account_id).first()
            if not account:
                logger.error(f"Аккаунт {account_id} не найден")
                return False
                
            # Получаем товары для аккаунта
            products = session.query(Product).filter(
                Product.client_id == client_id,
                Product.account_id == account_id
            ).all()
            
            if not products:
                logger.error(f"Для клиента {client_id} с аккаунтом {account_id} отсутствуют товары")
                return False
                
            logger.info(f"Найдено {len(products)} товаров для обработки")
            
            # Подготавливаем данные для отправки
            orders_inserted = 0
            batch = []
            product_codes_batch = []
            current_product_id = None
            
            for index, product in enumerate(products):
                current_product_id = product.id
                
                # Проверяем соответствие ссылки маркетплейсу
                valid_link = None
                if product.product_link:
                    link_lower = product.product_link.lower()
                    if account.market.lower() == "wb" and ("wildberries.ru" in link_lower or "wb.ru" in link_lower):
                        valid_link = product.product_link
                        logger.debug(f"Используем WB ссылку для товара {product.product_code}: {valid_link}")
                    elif account.market.lower() == "ozon" and "ozon.ru" in link_lower:
                        valid_link = product.product_link
                        logger.debug(f"Используем Ozon ссылку для товара {product.product_code}: {valid_link}")
                    else:
                        # Ссылка не соответствует маркетплейсу - не используем её
                        logger.warning(f"Ссылка товара {product.product_code} не соответствует маркетплейсу {account.market}: {product.product_link}")
                        valid_link = None
                else:
                    logger.debug(f"У товара {product.product_code} нет ссылки")
                
                batch.append({
                    "code": product.product_code,
                    "name": product.product_name,
                    "linkset": [valid_link] if valid_link else [],
                    "account_id": account.account_id
                })
                product_codes_batch.append(product.product_code)
                
                # Отправляем батч когда достигли размера или это последний товар
                if len(batch) == batch_size or index == len(products) - 1:
                    # Получаем цены из API маркетплейса
                    if account.market.lower() == "ozon":
                        account_config = {
                            'ozon_client_id': account.ozon_client_id,
                            'ozon_api_key': account.api_key
                        }
                        prices = get_initial_market_prices_ozon(product_codes_batch, account_config, test_mode)
                    elif account.market.lower() == "wb":
                        account_config = {
                            'wb_api_key': account.api_key
                        }
                        prices = get_initial_market_prices_wb(product_codes_batch, account_config, test_mode)
                    else:
                        prices = {}
                        
                    # Создаем task_id с ID клиента и буквой маркетплейса для уникальности
                    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                    market_letter = "O" if account.market.lower() == "ozon" else "W"
                    task_id = f"{client_id}{market_letter}{timestamp}"
                    
                    # Отправляем в парсер
                    payload = {
                        "apikey": client.parser_api_key,
                        "regionid": account.region,
                        "market": account.market,
                        "userlabel": task_id,
                        "products": batch
                    }
                    
                    logger.info(f"Отправка батча с task_id {task_id}")
                    logger.debug(f"Send Order Payload: {json.dumps(payload, indent=2)}")
                    
                    if test_mode:
                        logger.info("TEST MODE: Не отправляем запрос в парсинговый сервис.")
                        response_status = 200
                        response_text = "TEST MODE: Симулированный ответ"
                    else:
                        response = requests.post(f'{self.base_url}/send-order', json=payload, timeout=30)
                        response_status = response.status_code
                        response_text = response.text
                        
                    if response_status == 200:
                        logger.info(f"Батч успешно отправлен, task_id: {task_id}")
                        now = datetime.now()
                        
                        # Сохраняем заказ
                        order = Order(
                            client_id=client_id,
                            task_id=task_id,
                            region=account.region,
                            market=account.market,
                            status='pending',
                            report_url=None,
                            created_at=now,
                            updated_at=now
                        )
                        session.add(order)
                        
                        # Сохраняем результаты с ценами из API маркетплейса
                        for prod in batch:
                            market_price = prices.get(str(prod["code"]), 0.0)
                            result = Result(
                                client_id=client_id,
                                task_id=task_id,
                                product_id=current_product_id,
                                account_id=account_id,
                                product_code=prod["code"],
                                product_name=prod["name"],
                                product_link=prod["linkset"][0] if prod["linkset"] else None,
                                market_price=market_price,
                                showcase_price=None,  # Будет обновлено из отчета парсера
                                timestamp=now
                            )
                            session.add(result)
                            
                        orders_inserted += 1
                    else:
                        logger.error(f"Ошибка отправки батча: {response_text}")
                        
                    # Очищаем батч
                    batch = []
                    product_codes_batch = []
                    time.sleep(1)  # Пауза между батчами
                    
            session.commit()
            session.close()
            
            logger.info(f"Отправка завершена, создано заданий: {orders_inserted}")
            return orders_inserted > 0
            
        except Exception as e:
            logger.exception(f"Ошибка в send_order: {e}")
            return False
            
    def check_reports(self, client_id: str) -> bool:
        """
        Проверка готовности отчётов от парсера
        """
        logger.info(f"Запуск проверки готовности отчётов для клиента {client_id}")
        
        try:
            from db.session import get_sync_session
            session = get_sync_session()
            
            # Получаем клиента
            client = session.query(Client).filter(Client.id == client_id).first()
            if not client:
                logger.error(f"Клиент {client_id} не найден")
                return False
                
            # Получаем pending заказы
            orders = session.query(Order).filter(
                Order.client_id == client_id,
                Order.status == 'pending'
            ).all()
            
            if not orders:
                logger.info("Нет заданий для проверки")
                return True
                
            # Запрашиваем статусы от парсера
            response = requests.post(
                f'{self.base_url}/get-last50',
                json={"apikey": client.parser_api_key, "limit": 50},
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error(f"Ошибка получения статусов заданий: {response.text}")
                return False
                
            json_response = response.json()
            logger.debug(f"Ответ API: {json.dumps(json_response, indent=2)}")
            
            # Парсим ответ
            data = None
            if isinstance(json_response, list):
                for elem in json_response:
                    if isinstance(elem, dict) and "data" in elem:
                        data = elem["data"]
                        break
            if data is None:
                data = json_response
                
            updated_orders = 0
            
            for order in orders:
                task_id = order.task_id
                found = False
                report_url = None
                status = None
                
                # Ищем задачу в ответе парсера
                for task_group in data:
                    local_task_id = None
                    local_report_url = None
                    local_status = None
                    
                    if isinstance(task_group, list):
                        for item in task_group:
                            if isinstance(item, dict):
                                if 'userlabel' in item:
                                    local_task_id = item['userlabel']
                                elif 'report_json' in item:
                                    local_report_url = item['report_json']
                                elif 'status' in item:
                                    local_status = item['status']
                                    
                        if local_task_id == task_id:
                            found = True
                            status = local_status
                            report_url = local_report_url
                            break
                            
                if found and status == 'completed' and report_url:
                    logger.info(f"Задание {task_id} завершено, обрабатываем отчёт")
                    
                    # Скачиваем и обрабатываем отчет
                    json_data = self._download_and_parse_json(report_url)
                    if json_data:
                        # Обновляем цены в results
                        for item in json_data.get("data", []):
                            product_code = item.get("code")
                            offers = item.get("offers", [])
                            
                            if offers:
                                offer = offers[0]
                                promo_price = offer.get("PromoPrice", "")
                                
                                if promo_price in [0, "0", "", None]:
                                    price = offer.get("Price", "")
                                    if price in [None, "", "0", 0]:
                                        logger.info(f"Пропускаем товар {product_code}: отсутствует валидная цена")
                                        continue
                                    else:
                                        final_price = price
                                else:
                                    final_price = promo_price
                                    
                                logger.info(f"Для товара {product_code} рассчитана итоговая цена: {final_price}")
                                
                                # Обновляем showcase_price в results
                                session.execute(
                                    text("""
                                        UPDATE results
                                        SET showcase_price = :price
                                        WHERE client_id = :client_id AND task_id = :task_id AND product_code = :product_code
                                    """),
                                    {
                                        "price": final_price,
                                        "client_id": client_id,
                                        "task_id": task_id,
                                        "product_code": product_code
                                    }
                                )
                                
                        # Обновляем статус заказа
                        now = datetime.now()
                        order.status = 'completed'
                        order.report_url = report_url
                        order.updated_at = now
                        updated_orders += 1
                        
                        # Отправляем отчет сразу после обновления данных
                        logger.info(f"Данные обновлены для клиента {client_id}, запускаем отправку отчета")
                        from services.daily_summary_service import send_daily_summary_refactored
                        send_daily_summary_refactored(client_id, force_send=True)
                        
            session.commit()
            session.close()
            
            logger.info(f"Проверка завершена, обновлено заданий: {updated_orders}")
            return updated_orders > 0
            
        except Exception as e:
            logger.exception(f"Ошибка в check_reports: {e}")
            return False
            
    def _download_and_parse_json(self, url: str) -> Optional[Dict]:
        """
        Скачивание и парсинг JSON отчета
        """
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Ошибка скачивания или парсинга JSON: {e}")
            return None 