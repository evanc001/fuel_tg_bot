from __future__ import annotations

import asyncio
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import logging
import os
import tempfile
import threading
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from src.dopgen.data_loaders import (
    load_aliases,
    load_clients_encrypted,
    load_locations,
    load_products,
)
from src.dopgen.render import build_context, build_output_filename, choose_template, render_docx
from src.dopgen.ru_dates import format_pay_date, parse_ddmmyyyy
from src.dopgen.state import (
    COMPANY_INPUT,
    COMPANY_SELECT,
    CONFIRM,
    DELIVERY_DATE,
    DELIVERY_TYPE,
    LOCATION_INPUT,
    LOCATION_SELECT,
    PAY_DATE,
    PAYMENT_TYPE,
    PRODUCT_INPUT,
    PRODUCT_SELECT,
    START,
    UNLOAD_ADDRESS,
)
from src.dopgen.utils import normalize_text, sanitize_filename, search_catalog


logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
# Avoid leaking bot token in request URLs in platform logs.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
TEMPLATES_DIR = BASE_DIR / "templates"


MENU_BUTTON = "Создать допсоглашение"


def _catalogs(context: ContextTypes.DEFAULT_TYPE) -> dict:
    return context.application.bot_data["catalogs"]


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/health"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"ok")
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def _start_health_server() -> ThreadingHTTPServer | None:
    port = (os.getenv("PORT") or "").strip()
    if not port:
        return None

    server = ThreadingHTTPServer(("0.0.0.0", int(port)), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Health server started on port %s", port)
    return server


def _make_select_keyboard(prefix: str, items: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = []
    for key, label in items:
        text = f"{key} — {label}"
        if len(text) > 60:
            text = text[:57] + "..."
        rows.append([InlineKeyboardButton(text=text, callback_data=f"{prefix}:{key}")])
    return InlineKeyboardMarkup(rows)


def _find_company_matches(query: str, aliases: dict[str, str], clients: dict[str, dict]) -> list[str]:
    normalized = normalize_text(query)
    alias_target = aliases.get(normalized)
    if alias_target:
        normalized = normalize_text(alias_target)

    exact = [key for key in clients if normalize_text(key) == normalized]
    if exact:
        return exact

    matches = []
    for key, payload in clients.items():
        company_name = normalize_text(str(payload.get("company_name", "")))
        if normalized and normalized in company_name:
            matches.append(key)
    return matches


def _parse_company_and_dop_input(text: str) -> tuple[str, str]:
    parts = [p.strip() for p in (text or "").split(",", 1)]
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError("Введите: компания, номер допсоглашения. Пример: сиб, 12")
    return parts[0], parts[1]


def _parse_product_tons_price_input(text: str) -> tuple[str, int, int]:
    parts = [p.strip() for p in (text or "").split(",")]
    if len(parts) != 3:
        raise ValueError("Введите: продукт, тонны, цена. Пример: дтл, 25, 62500")
    product_query = parts[0]
    if not product_query:
        raise ValueError("Ключ/название продукта не может быть пустым.")
    try:
        tons = int(parts[1])
        price = int(parts[2])
    except ValueError as exc:
        raise ValueError("Тонны и цена должны быть целыми числами.") from exc
    if tons <= 0:
        raise ValueError("Количество тонн должно быть больше 0.")
    if price <= 0:
        raise ValueError("Цена должна быть больше 0.")
    return product_query, tons, price


async def _ask_payment_type_message(target_message) -> None:
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Предоплата", callback_data="payment:prepayment")],
            [InlineKeyboardButton("Отсрочка", callback_data="payment:deferment")],
        ]
    )
    await target_message.reply_text("Выберите тип оплаты:", reply_markup=keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    keyboard = ReplyKeyboardMarkup([[MENU_BUTTON]], resize_keyboard=True)
    await update.message.reply_text(
        "Нажмите кнопку, чтобы начать формирование допсоглашения.",
        reply_markup=keyboard,
    )
    return START


async def start_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if text != MENU_BUTTON:
        await update.message.reply_text("Используйте кнопку 'Создать допсоглашение'.")
        return START

    await update.message.reply_text(
        "компания, № доп. согл",
        reply_markup=ReplyKeyboardRemove(),
    )
    return COMPANY_INPUT


async def company_search_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    catalogs = _catalogs(context)
    try:
        company_query, dop_num_value = _parse_company_and_dop_input(update.message.text or "")
    except ValueError as exc:
        await update.message.reply_text(str(exc))
        return COMPANY_INPUT

    matches = _find_company_matches(company_query, catalogs["aliases"], catalogs["clients"])

    if not matches:
        await update.message.reply_text(
            "Компания не найдена. Повторите шаг в формате: компания, номер допсоглашения."
        )
        return COMPANY_INPUT

    if len(matches) == 1:
        key = matches[0]
        context.user_data["company_key"] = key
        context.user_data["client_data"] = catalogs["clients"][key]
        context.user_data["dop_num"] = dop_num_value
        await _ask_payment_type_message(update.message)
        return PAYMENT_TYPE

    items = [(key, str(catalogs["clients"][key].get("company_name", ""))) for key in matches[:10]]
    context.user_data["pending_dop_num"] = dop_num_value
    await update.message.reply_text(
        "Найдено несколько компаний. Выберите нужную:",
        reply_markup=_make_select_keyboard("company", items),
    )
    return COMPANY_SELECT


async def company_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if not query.data or not query.data.startswith("company:"):
        await query.edit_message_text("Некорректный выбор. Введите компанию заново.")
        return COMPANY_INPUT

    key = query.data.split(":", 1)[1]
    catalogs = _catalogs(context)
    if key not in catalogs["clients"]:
        await query.edit_message_text("Компания не найдена. Введите компанию заново.")
        return COMPANY_INPUT

    context.user_data["company_key"] = key
    context.user_data["client_data"] = catalogs["clients"][key]
    dop_num_value = (context.user_data.pop("pending_dop_num", "") or "").strip()
    if not dop_num_value:
        await query.edit_message_text(
            "Не удалось получить номер допсоглашения. Повторите ввод: компания, номер."
        )
        return COMPANY_INPUT
    context.user_data["dop_num"] = dop_num_value
    await query.edit_message_text(f"Выбрано: {key}")
    await _ask_payment_type_message(query.message)
    return PAYMENT_TYPE


async def payment_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if not query.data or not query.data.startswith("payment:"):
        await query.edit_message_text("Некорректный выбор типа оплаты.")
        return PAYMENT_TYPE

    value = query.data.split(":", 1)[1]
    if value not in {"prepayment", "deferment"}:
        await query.edit_message_text("Некорректный выбор типа оплаты.")
        return PAYMENT_TYPE

    context.user_data["payment_type"] = value
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Самовывоз", callback_data="delivery:pickup")],
            [InlineKeyboardButton("Доставка", callback_data="delivery:delivery")],
        ]
    )
    await query.edit_message_text("Выберите тип поставки:", reply_markup=keyboard)
    return DELIVERY_TYPE


async def delivery_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if not query.data or not query.data.startswith("delivery:"):
        await query.edit_message_text("Некорректный выбор типа поставки.")
        return DELIVERY_TYPE

    value = query.data.split(":", 1)[1]
    if value not in {"pickup", "delivery"}:
        await query.edit_message_text("Некорректный выбор типа поставки.")
        return DELIVERY_TYPE

    context.user_data["delivery_type"] = value
    context.user_data["current_date"] = date.today()
    await query.edit_message_text("дата поставки:")
    return DELIVERY_DATE


async def delivery_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text or ""
    try:
        context.user_data["delivery_date"] = parse_ddmmyyyy(text)
    except ValueError:
        await update.message.reply_text("Неверная дата. Используйте формат ДД.ММ или ДД.ММ.ГГГГ.")
        return DELIVERY_DATE

    if context.user_data.get("payment_type") == "deferment":
        await update.message.reply_text("дата оплаты:")
        return PAY_DATE

    context.user_data["pay_date"] = context.user_data["current_date"]
    await update.message.reply_text("продукт, количество, цена:")
    return PRODUCT_INPUT


async def pay_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text or ""
    try:
        context.user_data["pay_date"] = parse_ddmmyyyy(text)
    except ValueError:
        await update.message.reply_text("Неверная дата. Используйте формат ДД.ММ или ДД.ММ.ГГГГ.")
        return PAY_DATE

    await update.message.reply_text("продукт, количество, цена:")
    return PRODUCT_INPUT


async def product_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    catalogs = _catalogs(context)
    try:
        product_query, tons_value, price_value = _parse_product_tons_price_input(update.message.text or "")
    except ValueError as exc:
        await update.message.reply_text(str(exc))
        return PRODUCT_INPUT

    matches = search_catalog(product_query, catalogs["products"], limit=10)

    if not matches:
        await update.message.reply_text("Продукт не найден. Введите ключ/название ещё раз.")
        return PRODUCT_INPUT

    if len(matches) == 1:
        context.user_data["product_key"] = matches[0][0]
        context.user_data["tons"] = tons_value
        context.user_data["price"] = price_value
        await update.message.reply_text("базис погрузки:")
        return LOCATION_INPUT

    context.user_data["pending_tons"] = tons_value
    context.user_data["pending_price"] = price_value

    await update.message.reply_text(
        "Найдено несколько продуктов. Выберите нужный:",
        reply_markup=_make_select_keyboard("product", matches),
    )
    return PRODUCT_SELECT


async def product_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if not query.data or not query.data.startswith("product:"):
        await query.edit_message_text("Некорректный выбор. Введите продукт заново.")
        return PRODUCT_INPUT

    key = query.data.split(":", 1)[1]
    catalogs = _catalogs(context)
    if key not in catalogs["products"]:
        await query.edit_message_text("Ключ продукта не найден. Введите продукт заново.")
        return PRODUCT_INPUT

    context.user_data["product_key"] = key
    tons_value = context.user_data.pop("pending_tons", None)
    price_value = context.user_data.pop("pending_price", None)
    if not isinstance(tons_value, int) or not isinstance(price_value, int):
        await query.edit_message_text("Не удалось получить тонны/цену. Повторите шаг 2/5.")
        return PRODUCT_INPUT
    context.user_data["tons"] = tons_value
    context.user_data["price"] = price_value
    await query.edit_message_text(f"Выбрано: {key}")
    await query.message.reply_text("базис погрузки:")
    return LOCATION_INPUT


async def location_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    catalogs = _catalogs(context)
    query = update.message.text or ""
    matches = search_catalog(query, catalogs["locations"], limit=10)

    if not matches:
        await update.message.reply_text("Локация не найдена. Введите ключ/название ещё раз.")
        return LOCATION_INPUT

    if len(matches) == 1:
        context.user_data["location_key"] = matches[0][0]
        if context.user_data.get("delivery_type") == "delivery":
            await update.message.reply_text("адрес слива:")
            return UNLOAD_ADDRESS
        return await show_confirm(update, context)

    await update.message.reply_text(
        "Найдено несколько локаций. Выберите нужную:",
        reply_markup=_make_select_keyboard("location", matches),
    )
    return LOCATION_SELECT


async def location_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if not query.data or not query.data.startswith("location:"):
        await query.edit_message_text("Некорректный выбор. Введите локацию заново.")
        return LOCATION_INPUT

    key = query.data.split(":", 1)[1]
    catalogs = _catalogs(context)
    if key not in catalogs["locations"]:
        await query.edit_message_text("Ключ локации не найден. Введите локацию заново.")
        return LOCATION_INPUT

    context.user_data["location_key"] = key
    await query.edit_message_text(f"Выбрано: {key}")

    if context.user_data.get("delivery_type") == "delivery":
        await query.message.reply_text("адрес слива:")
        return UNLOAD_ADDRESS

    summary_text = _build_summary_text(context)
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Сгенерировать", callback_data="confirm:generate")],
            [InlineKeyboardButton("Отмена", callback_data="confirm:cancel")],
        ]
    )
    await query.message.reply_text(summary_text, reply_markup=keyboard)
    return CONFIRM


async def unload_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    value = (update.message.text or "").strip()
    if not value:
        await update.message.reply_text("Адрес доставки не может быть пустым.")
        return UNLOAD_ADDRESS

    context.user_data["unload_address"] = value
    return await show_confirm(update, context)


def _build_summary_text(context: ContextTypes.DEFAULT_TYPE) -> str:
    catalogs = _catalogs(context)
    user_data = context.user_data
    company_key = user_data["company_key"]
    client_data = user_data["client_data"]

    summary_lines = [
        "Проверьте данные:",
        f"Компания: {company_key} ({client_data.get('company_name', '')})",
        f"Номер допсоглашения: {user_data['dop_num']}",
        f"Оплата: {'предоплата' if user_data['payment_type'] == 'prepayment' else 'отсрочка'}",
        f"Поставка: {'самовывоз' if user_data['delivery_type'] == 'pickup' else 'доставка'}",
        f"Дата допсоглашения: {format_pay_date(user_data['current_date'])}",
        f"Дата поставки: {format_pay_date(user_data['delivery_date'])}",
        f"Дата оплаты: {format_pay_date(user_data['pay_date'])}",
        f"Продукт: {user_data['product_key']} ({catalogs['products'][user_data['product_key']]})",
        f"Тонн: {user_data['tons']}",
        f"Цена: {user_data['price']}",
        f"Локация: {user_data['location_key']} ({catalogs['locations'][user_data['location_key']]})",
    ]

    if user_data.get("delivery_type") == "delivery":
        summary_lines.append(f"Адрес доставки: {user_data.get('unload_address', '')}")

    return "\n".join(summary_lines)


async def show_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    summary_text = _build_summary_text(context)

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Сгенерировать", callback_data="confirm:generate")],
            [InlineKeyboardButton("Отмена", callback_data="confirm:cancel")],
        ]
    )

    await update.message.reply_text(summary_text, reply_markup=keyboard)
    return CONFIRM


async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if not query.data or not query.data.startswith("confirm:"):
        await query.edit_message_text("Некорректная команда подтверждения.")
        return CONFIRM

    action = query.data.split(":", 1)[1]
    if action == "cancel":
        context.user_data.clear()
        await query.edit_message_text("Операция отменена.")
        keyboard = ReplyKeyboardMarkup([[MENU_BUTTON]], resize_keyboard=True)
        await query.message.reply_text(
            "Можете сразу создать новый документ.",
            reply_markup=keyboard,
        )
        return START

    if action != "generate":
        await query.edit_message_text("Некорректная команда подтверждения.")
        return CONFIRM

    catalogs = _catalogs(context)

    try:
        template_rel = choose_template(
            context.user_data["payment_type"],
            context.user_data["delivery_type"],
        )
        template_path = BASE_DIR / template_rel
        if not template_path.exists():
            await query.edit_message_text(f"Шаблон не найден: {template_rel}")
            return CONFIRM

        context_dict = build_context(context.user_data, catalogs)
        filename = sanitize_filename(build_output_filename(context.user_data))

        temp_path = None
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            temp_path = Path(tmp.name)

        render_docx(template_path, context_dict, temp_path)

        with temp_path.open("rb") as fp:
            await query.message.reply_document(document=fp, filename=filename)

        await query.edit_message_text("Готово. DOCX сформирован и отправлен.")
        context.user_data.clear()
        keyboard = ReplyKeyboardMarkup([[MENU_BUTTON]], resize_keyboard=True)
        await query.message.reply_text(
            "Создать ещё один документ?",
            reply_markup=keyboard,
        )
        return START

    except Exception as exc:
        logger.exception("Failed to generate document")
        await query.edit_message_text(f"Ошибка генерации документа: {exc}")
        return CONFIRM

    finally:
        if "temp_path" in locals() and temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    keyboard = ReplyKeyboardMarkup([[MENU_BUTTON]], resize_keyboard=True)
    await update.message.reply_text(
        "Диалог отменён. Можно сразу создать новый документ.",
        reply_markup=keyboard,
    )
    return START


def build_application() -> Application:
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        raise RuntimeError("Environment variable BOT_TOKEN is required.")

    if (
        not os.getenv("CLIENTS_JSON_B64")
        and not os.getenv("CLIENTS_KEY")
        and not os.getenv("CLIENTS_KEY_FILE")
    ):
        raise RuntimeError(
            "Environment variable CLIENTS_JSON_B64 or CLIENTS_KEY or CLIENTS_KEY_FILE is required."
        )

    aliases = load_aliases(DATA_DIR / "aliases.json")
    products = load_products(DATA_DIR / "products.json")
    locations = load_locations(DATA_DIR / "locations.json")
    clients = load_clients_encrypted(DATA_DIR / "clients.enc")

    app = ApplicationBuilder().token(bot_token).build()
    app.bot_data["catalogs"] = {
        "aliases": {normalize_text(k): v for k, v in aliases.items()},
        "products": products,
        "locations": locations,
        "clients": clients,
    }

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            START: [MessageHandler(filters.TEXT & ~filters.COMMAND, start_menu)],
            COMPANY_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, company_search_input)],
            COMPANY_SELECT: [CallbackQueryHandler(company_select, pattern=r"^company:")],
            PAYMENT_TYPE: [CallbackQueryHandler(payment_type, pattern=r"^payment:")],
            DELIVERY_TYPE: [CallbackQueryHandler(delivery_type, pattern=r"^delivery:")],
            DELIVERY_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, delivery_date)],
            PAY_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, pay_date)],
            PRODUCT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, product_input)],
            PRODUCT_SELECT: [CallbackQueryHandler(product_select, pattern=r"^product:")],
            LOCATION_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, location_input)],
            LOCATION_SELECT: [CallbackQueryHandler(location_select, pattern=r"^location:")],
            UNLOAD_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, unload_address)],
            CONFIRM: [CallbackQueryHandler(confirm, pattern=r"^confirm:")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(conv)
    return app


def main() -> None:
    # Python 3.14 no longer creates a default event loop in main thread.
    asyncio.set_event_loop(asyncio.new_event_loop())
    health_server = _start_health_server()
    try:
        app = build_application()
        app.run_polling()
    finally:
        if health_server:
            health_server.shutdown()
            health_server.server_close()


if __name__ == "__main__":
    main()
