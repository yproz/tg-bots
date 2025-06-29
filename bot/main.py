import asyncio, logging, os, tempfile, contextlib, html
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from db.session import create_tables, async_session_factory, sync_session_factory
from db.models import Account, Client
from services import excel_loader
import datetime as dt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME", "pricebot")
if not BOT_TOKEN:
    raise RuntimeError("Переменная окружения BOT_TOKEN не задана")

from aiogram.client.default import DefaultBotProperties
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

router = dp


def safe_error_message(error) -> str:
    """Безопасно экранирует HTML в сообщениях об ошибках"""
    return html.escape(str(error))


# -------------------------- HELP / START --------------------------
@dp.message(F.text.in_({"start", "/start"}))
async def cmd_start(m: Message):
    await m.answer(
        "👋 <b>СПП Мониторинг Бот</b>\n\n"
        "Команды:\n"
        "• /add_client — мастер добавления клиента\n"
        "• /add_account — мастер добавления магазина\n"
        "• /set_topic <account_id> — сохранить topic_id текущего треда\n"
        "• /get_template — XLSX‑шаблон для загрузки товаров\n"
        "• пришлите файл XLSX для импорта товаров\n"
        "• /snapshot YYYY-MM-DD — CSV‑срез СПП\n"
        "• /collect_now — запустить сбор цен сейчас\n"
        "\n<i>Бот отслеживает изменения СПП (Совместных инвестиций) на маркетплейсах</i>",
        parse_mode="HTML"
    )


# ----------------------- ADD CLIENT (WIZARD) ------------------------------
class AddClient(StatesGroup):
    client_id = State()
    name = State()
    chat_id = State()
    parser_api_key = State()

@dp.message(Command("add_client"))
async def add_client_start(m: Message, state: FSMContext):
    await m.answer("🆕 Создаём клиента для СПП мониторинга.\nВведите client_id (латиница/цифры):")
    await state.set_state(AddClient.client_id)

@dp.message(AddClient.client_id)
async def add_client_id(m: Message, state: FSMContext):
    await state.update_data(client_id=m.text.strip())
    await m.answer("Введите название клиента (например «SEB»):")
    await state.set_state(AddClient.name)

@dp.message(AddClient.name)
async def add_client_name(m: Message, state: FSMContext):
    await state.update_data(name=m.text.strip())
    await m.answer("Введите chat_id группы для отчётов (можно 0, настроите позже):")
    await state.set_state(AddClient.chat_id)

@dp.message(AddClient.chat_id)
async def add_client_chat(m: Message, state: FSMContext):
    await state.update_data(chat_id=int(m.text.strip()))
    await m.answer("Введите API ключ парсера (можно оставить пустым, настроите позже):")
    await state.set_state(AddClient.parser_api_key)

@dp.message(AddClient.parser_api_key)
async def add_client_finish(m: Message, state: FSMContext):
    parser_key = m.text.strip() if m.text.strip() else None
    await state.update_data(parser_api_key=parser_key)
    data = await state.get_data()

    # Используем sync-сессию для избежания конфликтов event loop
    def sync_insert():
        with sync_session_factory() as s:
            stmt = (
                insert(Client)
                .values(
                    id=data["client_id"], 
                    name=data["name"], 
                    group_chat_id=data["chat_id"],
                    parser_api_key=data["parser_api_key"]
                )
                .on_conflict_do_update(
                    index_elements=["id"],
                    set_={
                        "name": data["name"],
                        "group_chat_id": data["chat_id"],
                        "parser_api_key": data["parser_api_key"]
                    }
                )
            )
            s.execute(stmt)
            s.commit()
    import concurrent.futures
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, sync_insert)

    await m.answer(f"✅ Клиент <b>{safe_error_message(data['client_id'])}</b> добавлен для СПП мониторинга.", parse_mode="HTML")
    await state.clear()


# ----------------------- ADD ACCOUNT (WIZARD) ------------------------------
class AddAccount(StatesGroup):
    market = State()
    client_id = State()
    account_id = State()
    ozon_client_id = State()
    api_key = State()
    region = State()

@dp.message(Command("add_account"))
async def add_account_start(m: Message, state: FSMContext):
    await m.answer("🛠 Добавление аккаунта для СПП мониторинга.\n"
                   "Укажите marketplace (ozon / wb):")
    await state.set_state(AddAccount.market)

@dp.message(AddAccount.market)
async def add_account_market(m: Message, state: FSMContext):
    market = m.text.strip().lower()
    if market not in {"ozon", "wb"}:
        await m.answer("Введите именно ozon или wb.")
        return
    await state.update_data(market=market)
    await m.answer("Введите client_id (ключ клиента в нашей системе):")
    await state.set_state(AddAccount.client_id)

@dp.message(AddAccount.client_id)
async def add_account_client(m: Message, state: FSMContext):
    await state.update_data(client_id=m.text.strip())
    await m.answer("Введите account_id (короткое имя магазина):")
    await state.set_state(AddAccount.account_id)

@dp.message(AddAccount.account_id)
async def add_account_accid(m: Message, state: FSMContext):
    await state.update_data(account_id=m.text.strip())
    data = await state.get_data()
    if data["market"] == "ozon":
        await m.answer("Введите Ozon Client-ID (число из кабинета):")
        await state.set_state(AddAccount.ozon_client_id)
    else:  # wb
        await m.answer("Введите WB API-key (токен):")
        await state.set_state(AddAccount.api_key)

@dp.message(AddAccount.ozon_client_id)
async def add_account_ozon_cid(m: Message, state: FSMContext):
    await state.update_data(ozon_client_id=m.text.strip())
    await m.answer("Введите Ozon API-key:")
    await state.set_state(AddAccount.api_key)

@dp.message(AddAccount.api_key)
async def add_account_apikey(m: Message, state: FSMContext):
    await state.update_data(api_key=m.text.strip())
    await m.answer("Введите регион (например Москва):")
    await state.set_state(AddAccount.region)

@dp.message(AddAccount.region)
async def add_account_finish(m: Message, state: FSMContext):
    await state.update_data(region=m.text.strip())
    data = await state.get_data()

    # Используем sync-сессию для избежания конфликтов event loop
    def sync_insert():
        with sync_session_factory() as session:
            # гарантируем, что клиент существует
            stmt_cli = (
                insert(Client)
                .values(id=data["client_id"], name=data["client_id"], group_chat_id=0)
                .on_conflict_do_nothing(index_elements=["id"])
            )
            session.execute(stmt_cli)

            # вставляем аккаунт
            stmt_acc = (
                insert(Account)
                .values(
                    client_id=data["client_id"],
                    market=data["market"],
                    account_id=data["account_id"],
                    api_key=data["api_key"],
                    region=data["region"],
                    ozon_client_id=data.get("ozon_client_id"),
                )
                .on_conflict_do_update(
                    index_elements=["client_id", "market", "account_id"],
                    set_={
                        "api_key": data["api_key"],
                        "region": data["region"],
                        "ozon_client_id": data.get("ozon_client_id"),
                    }
                )
            )
            session.execute(stmt_acc)
            session.commit()
    
    import concurrent.futures
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, sync_insert)

    await m.answer("✅ Аккаунт сохранён для СПП мониторинга.")
    await state.clear()


# ----------------------- SET TOPIC ------------------------------
@dp.message(F.text.startswith("/set_topic"))
async def set_topic(m: Message):
    """Сохраняет topic_id текущего треда для аккаунта."""
    parts = m.text.split()
    if len(parts) != 2:
        await m.answer("Формат: /set_topic <account_id>", parse_mode="HTML")
        return
    
    account_id = parts[1].strip()
    topic_id = m.message_thread_id if m.is_topic_message else None
    
    if not topic_id:
        await m.answer("❌ Эта команда должна быть выполнена в треде (topic).")
        return
    
    # Используем sync-сессию для избежания конфликтов event loop
    def sync_update():
        with sync_session_factory() as session:
            # Находим аккаунт
            stmt = select(Account).where(Account.account_id == account_id)
            result = session.execute(stmt)
            account = result.scalar_one_or_none()
            
            if not account:
                return False
            
            # Обновляем topic_id
            stmt_update = (
                update(Account)
                .where(Account.account_id == account_id)
                .values(topic_id=topic_id)
            )
            session.execute(stmt_update)
            session.commit()
            return True
    
    import concurrent.futures
    loop = asyncio.get_running_loop()
    account_found = await loop.run_in_executor(None, sync_update)
    
    if not account_found:
        await m.answer(f"❌ Аккаунт с account_id '{safe_error_message(account_id)}' не найден.")
        return
    
    await m.answer(f"✅ Topic ID {safe_error_message(topic_id)} сохранён для аккаунта {safe_error_message(account_id)}")


# ----------------------- GET TEMPLATE ------------------------------
@dp.message(F.text.in_({"get_template", "/get_template"})) #!ВАЖНО
async def get_template(m: Message):
    """Отправляет шаблон Excel для загрузки товаров."""
    try:
        template_path = await excel_loader.generate_template()
        await m.answer_document(
            FSInputFile(template_path),
            caption="📋 <b>Шаблон для загрузки товаров</b>\n\n"
                   "Заполните файл и отправьте обратно для импорта товаров в систему СПП мониторинга.\n\n"
                   "<i>Колонки:</i>\n"
                   "• client_id - ID клиента\n"
                   "• market - маркетплейс (ozon/wb)\n"
                   "• account_id - ID аккаунта\n"
                   "• product_code - артикул товара\n"
                   "• product_name - название товара\n"
                   "• product_link - ссылка на товар",
            parse_mode="HTML"
        )
    except Exception as e:
        await m.answer(f"❌ Ошибка создания шаблона: {safe_error_message(e)}")


# ----------------------- UPLOAD PRODUCTS ------------------------------
@dp.message(F.document.mime_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
async def upload_products(m: Message):
    """Обрабатывает загруженный Excel файл с товарами."""
    try:
        # Скачиваем файл
        file_info = await bot.get_file(m.document.file_id)
        file_path = file_info.file_path
        
        # Создаем временный файл
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            await bot.download_file(file_path, tmp.name)
            tmp_path = tmp.name
        
        # Загружаем данные
        ok, errors, error_file_path = await excel_loader.load_excel(tmp_path)
        
        # Удаляем временный файл
        os.unlink(tmp_path)
        
        # Формируем ответ
        if ok > 0:
            message = f"✅ Успешно загружено <b>{ok}</b> товаров"
            if errors:
                message += f"\n⚠️ Ошибок: <b>{len(errors)}</b>"
        else:
            message = f"❌ Не удалось загрузить товары"
            if errors:
                message += f"\n⚠️ Ошибок: <b>{len(errors)}</b>"
        
        await m.answer(message, parse_mode="HTML")
        
        # Отправляем файл с ошибками, если есть
        if errors:
            # Создаем txt файл с ошибками
            errors_text = f"Отчет об ошибках загрузки товаров\n"
            errors_text += f"Дата: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            errors_text += f"Успешно загружено: {ok} товаров\n"
            errors_text += f"Ошибок: {len(errors)}\n"
            errors_text += "=" * 50 + "\n\n"
            
            for i, error in enumerate(errors, 1):
                errors_text += f"{i}. {error}\n"
            
            # Создаем временный файл
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=".txt", encoding='utf-8') as tmp_errors:
                tmp_errors.write(errors_text)
                errors_file_path = tmp_errors.name
            
            await m.answer_document(
                FSInputFile(errors_file_path),
                caption="📋 Файл с ошибками загрузки товаров",
                parse_mode="HTML"
            )
            os.unlink(errors_file_path)
        
        # Удаляем старый Excel файл с ошибками, если был создан
        if error_file_path and os.path.exists(error_file_path):
            os.unlink(error_file_path)
            
    except Exception as e:
        await m.answer(f"❌ Ошибка обработки файла: {safe_error_message(e)}")


# ----------------------- SNAPSHOT ------------------------------
@dp.message(F.text.startswith("/snapshot"))
async def snapshot(m: Message):
    """Генерирует CSV срез СПП за указанную дату."""
    parts = m.text.split()
    if len(parts) != 2:
        await m.answer("Формат: /snapshot YYYY-MM-DD")
        return
    
    try:
        date_str = parts[1]
        date = dt.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        await m.answer("❌ Неверный формат даты. Используйте YYYY-MM-DD")
        return
    
    # Пока что возвращаем заглушку
    await m.answer(f"📊 Генерация отчета СПП за {safe_error_message(date_str)}...\n\n<i>Функция в разработке</i>", parse_mode="HTML")


# ----------------------- COLLECT NOW ------------------------------
@dp.message(Command("collect_now"))
async def collect_now(m: Message):
    """Запускает сбор цен прямо сейчас."""
    try:
        from tasks.app_v2 import collect_all_accounts_v2
        # Запускаем задачу через Celery
        task = collect_all_accounts_v2.delay()
        await m.answer(f"🚀 Запущен сбор цен СПП v2\n\nTask ID: <code>{safe_error_message(task.id)}</code>", parse_mode="HTML")
    except Exception as e:
        await m.answer(f"❌ Ошибка запуска сбора: {safe_error_message(e)}")


# ----------------------- CALLBACK HANDLERS ------------------------------
@dp.callback_query(F.data.startswith("excel_report|"))
async def handle_excel_report_callback(callback: CallbackQuery):
    """Обрабатывает нажатие на кнопку Excel-отчета и вызывает celery-задачу"""
    try:
        data = callback.data.split("|")
        if len(data) < 3:
            await callback.answer("Некорректные данные для отчета", show_alert=True)
            return
        
        client_id, date_str = data[1], data[2]
        marketplace = data[3] if len(data) > 3 else None
        
        from tasks.app_v2 import send_excel_report_v2
        send_excel_report_v2.delay(client_id, date_str, marketplace)
        
        marketplace_name = ""
        if marketplace == "ozon":
            marketplace_name = " Ozon"
        elif marketplace == "wb":
            marketplace_name = " Wildberries"
        
        await callback.answer(f"Формируем и отправляем Excel-отчет{marketplace_name}...", show_alert=True)
    except Exception as e:
        await callback.answer(f"Ошибка: {safe_error_message(e)}", show_alert=True)


# ----------------------- STARTUP ------------------------------
async def on_startup():
    await create_tables()
    logging.info("Bot started")

def main():
    asyncio.run(on_startup())
    asyncio.run(dp.start_polling(bot))


if __name__ == "__main__":
    main()

router = dp