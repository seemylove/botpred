import asyncio
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

BOT_TOKEN = "8725996418:AAHNw01xWp6i7IR6ZAbYS4xcSf6S0LP7-u8"

ADMIN_IDS = [
    8568804971,
    8593132522,
    8340996170,
]

CHANNEL_ID = "@findugagark"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# ─────────────── Очередь заявок ───────────────
# pending_id -> {
#   user_id, username, full_name, mode,
#   content: {kind, text, file_id, caption},
#   created_at, admin_msg
# }
pending_offers: dict[int, dict] = {}
pending_counter = 0


def next_pending_id() -> int:
    global pending_counter
    pending_counter += 1
    return pending_counter


# ─────────────── Состояния ───────────────
class SearchForm(StatesGroup):
    waiting_for_text = State()
    choosing_anonymity = State()


# ─────────────── Хелпер: клавиатура главного меню ───────────────
def main_menu_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔎 Отправить заявку", callback_data="send_offer")]
        ]
    )


# ─────────────── /start ───────────────
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()

    text = (
        "👋 <b>Привет, {name}!</b>\n\n"
        "🔎 Это бот <b>поиска людей и вещей</b>.\n"
        "Если ты <b>потерял что-то</b> или <b>ищешь кого-то</b> — "
        "отправь заявку, и она уйдёт администрации.\n\n"
        "📝 <b>Как это работает:</b>\n"
        "1. Нажми кнопку ниже\n"
        "2. Опиши, что или кого ты ищешь\n"
        "3. Выбери: с юзером или анонимно\n"
        "4. Заявка уйдёт на модерацию\n\n"
        "💡 <i>Чем подробнее опишешь — тем больше шансов найти!</i>"
    ).format(name=message.from_user.full_name)

    await message.answer(text, parse_mode="HTML", reply_markup=main_menu_kb())


# ─────────────── Нажатие "Отправить заявку" ───────────────
@dp.callback_query(F.data == "send_offer")
async def on_send_offer(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    cancel_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_offer")]
        ]
    )

    await callback.message.edit_text(
        "✍️ <b>Опиши свою заявку</b>\n\n"
        "Что именно ты <b>потерял</b> или <b>кого ищешь</b>?\n\n"
        "📎 Можно отправить <b>текст</b>, <b>фото</b> или <b>видео</b> с подписью.\n\n"
        "💡 <i>Укажи приметы, место и время — это сильно поможет.</i>",
        parse_mode="HTML",
        reply_markup=cancel_kb
    )

    await state.set_state(SearchForm.waiting_for_text)


# ─────────────── Нажатие "Отменить" ───────────────
@dp.callback_query(F.data == "cancel_offer")
async def on_cancel_offer(callback: CallbackQuery, state: FSMContext):
    await callback.answer("Отменено")

    await state.clear()

    await callback.message.edit_text(
        "❌ <b>Отправка отменена</b>\n\n"
        "Если передумаешь — жми кнопку ниже 👇",
        parse_mode="HTML",
        reply_markup=main_menu_kb()
    )


# ─────────────── Приём текста заявки ───────────────
@dp.message(SearchForm.waiting_for_text, F.text | F.photo | F.video)
async def receive_offer(message: Message, state: FSMContext):
    # Сохраняем контент, чтобы потом отправить в канал без "Переслано"
    content = {
        "kind": None,
        "text": None,
        "file_id": None,
        "caption": None,
    }

    if message.text:
        content["kind"] = "text"
        content["text"] = message.text
    elif message.photo:
        content["kind"] = "photo"
        content["file_id"] = message.photo[-1].file_id
        content["caption"] = message.caption or ""
    elif message.video:
        content["kind"] = "video"
        content["file_id"] = message.video.file_id
        content["caption"] = message.caption or ""

    await state.update_data(content=content)
    await state.set_state(SearchForm.choosing_anonymity)

    choice_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📤 Отправить с юзером",
                    callback_data="user_choice:named"
                ),
                InlineKeyboardButton(
                    text="🕵️ Отправить анонимно",
                    callback_data="user_choice:anon"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data="cancel_offer"
                ),
            ],
        ]
    )

    await message.answer(
        "🔒 <b>Как отправить заявку?</b>\n\n"
        "📤 <b>С юзером</b> — в канале увидят твой @username\n"
        "🕵️ <b>Анонимно</b> — авторство скрыто\n\n"
        "<i>Выбери вариант ниже:</i>",
        parse_mode="HTML",
        reply_markup=choice_kb
    )


# ─────────────── Юзер выбрал анонимность ───────────────
@dp.callback_query(F.data.startswith("user_choice:"), SearchForm.choosing_anonymity)
async def on_user_choice(callback: CallbackQuery, state: FSMContext):
    mode = callback.data.split(":")[1]  # "named" или "anon"
    data = await state.get_data()
    await state.clear()

    user = callback.from_user

    # Уникальный номер заявки
    pending_id = next_pending_id()

    # Сохраняем в очередь
    pending_offers[pending_id] = {
        "user_id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "mode": mode,
        "content": data["content"],
        "created_at": datetime.now(),
        "admin_msg": {},
    }

    mode_label = "📤 С юзером" if mode == "named" else "🕵️ Анонимно"

    header = (
        f"📩 <b>Новая заявка #{pending_id}</b>\n\n"
        f"👤 <b>От:</b> {user.full_name}\n"
        f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
        f"🔗 <b>Юзернейм:</b> @{user.username if user.username else '—'}\n"
        f"🔒 <b>Режим:</b> {mode_label}\n"
        f"─────────────────────"
    )

    moderation_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Опубликовать",
                    callback_data=f"approve:{pending_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=f"reject:{pending_id}"
                ),
            ]
        ]
    )

    sent = 0
    content = data["content"]

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, header, parse_mode="HTML")

            if content["kind"] == "text":
                sent_msg = await bot.send_message(
                    admin_id,
                    content["text"],
                    reply_markup=moderation_kb
                )
            elif content["kind"] == "photo":
                sent_msg = await bot.send_photo(
                    admin_id,
                    content["file_id"],
                    caption=content["caption"] or None,
                    reply_markup=moderation_kb
                )
            elif content["kind"] == "video":
                sent_msg = await bot.send_video(
                    admin_id,
                    content["file_id"],
                    caption=content["caption"] or None,
                    reply_markup=moderation_kb
                )

            pending_offers[pending_id]["admin_msg"][admin_id] = sent_msg.message_id
            sent += 1
        except Exception as e:
            logging.warning(f"Не удалось отправить админу {admin_id}: {e}")

    try:
        await callback.message.edit_text(
            callback.message.html_text + "\n\n<i>(выбор сделан)</i>",
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.edit_reply_markup(reply_markup=None)

    if sent > 0:
        await callback.message.answer(
            "✅ <b>Заявка отправлена на модерацию!</b>\n\n"
            "Как только её рассмотрят — ты получишь уведомление.\n"
            "Удачи в поиске 🍀",
            parse_mode="HTML"
        )
    else:
        await callback.message.answer("😔 Не удалось доставить заявку. Попробуй позже.")

    await callback.answer("Отправлено")


# ─────────────── Модерация: Отклонить ───────────────
@dp.callback_query(F.data.startswith("reject:"))
async def on_reject(callback: CallbackQuery):
    pending_id = int(callback.data.split(":")[1])

    offer = pending_offers.pop(pending_id, None)

    if not offer:
        await callback.answer("Заявка уже обработана", show_alert=True)
        await callback.message.edit_reply_markup(reply_markup=None)
        return

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.reply(
        f"❌ <b>Заявка #{pending_id} отклонена</b>",
        parse_mode="HTML"
    )

    try:
        await bot.send_message(
            offer["user_id"],
            "😔 <b>Твоя заявка отклонена</b>\n\n"
            "Возможно, она не соответствует правилам. "
            "Попробуй описать подробнее или отправь заново.",
            parse_mode="HTML",
            reply_markup=main_menu_kb()
        )
    except Exception as e:
        logging.warning(f"Не смог уведомить {offer['user_id']}: {e}")

    await callback.answer("Отклонено")


# ─────────────── Модерация: Опубликовать ───────────────
@dp.callback_query(F.data.startswith("approve:"))
async def on_approve(callback: CallbackQuery):
    pending_id = int(callback.data.split(":")[1])

    offer = pending_offers.pop(pending_id, None)

    if not offer:
        await callback.answer("Заявка уже обработана", show_alert=True)
        await callback.message.edit_reply_markup(reply_markup=None)
        return

    user_id = offer["user_id"]
    mode = offer["mode"]

    if mode == "named":
        try:
            author = await bot.get_chat(user_id)
        except Exception:
            author = None

        if author and author.username:
            author_suffix = f"\n\n👤 <b>Автор:</b> @{author.username}"
        elif author:
            author_suffix = (
                f"\n\n👤 <b>Автор:</b> "
                f"<a href='tg://user?id={user_id}'>{author.full_name}</a>"
            )
        else:
            author_suffix = (
                f"\n\n👤 <b>Автор:</b> "
                f"<a href='tg://user?id={user_id}'>профиль</a>"
            )
    else:
        author_suffix = ""

    await publish_offer_to_channel(offer["content"], author_suffix)

    await callback.message.edit_reply_markup(reply_markup=None)
    label = (
        f"✅ <b>Заявка #{pending_id} опубликована с автором</b>"
        if mode == "named"
        else f"✅ <b>Заявка #{pending_id} опубликована анонимно</b>"
    )
    await callback.message.reply(label, parse_mode="HTML")

    notify_text = (
        "🎉 <b>Твоя заявка опубликована!</b>\n\nОна уже в канале — скоро тебе ответят."
        if mode == "named"
        else "🎉 <b>Твоя заявка опубликована анонимно!</b>\n\nЗаявка уже в канале."
    )

    try:
        await bot.send_message(user_id, notify_text, parse_mode="HTML")
    except Exception as e:
        logging.warning(f"Не смог уведомить {user_id}: {e}")

    await callback.answer("Опубликовано")


# ─────────────── Публикация в канал ───────────────
async def publish_offer_to_channel(content: dict, author_suffix: str = ""):
    kind = content["kind"]

    if kind == "text":
        new_text = content["text"] + author_suffix
        await bot.send_message(CHANNEL_ID, new_text, parse_mode="HTML")

    elif kind == "photo":
        new_caption = (content["caption"] + author_suffix).strip() or None
        await bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=content["file_id"],
            caption=new_caption,
            parse_mode="HTML"
        )

    elif kind == "video":
        new_caption = (content["caption"] + author_suffix).strip() or None
        await bot.send_video(
            chat_id=CHANNEL_ID,
            video=content["file_id"],
            caption=new_caption,
            parse_mode="HTML"
        )


# ─────────────── /queue — список всех необработанных заявок ───────────────
@dp.message(Command("queue"))
async def cmd_queue(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    if not pending_offers:
        await message.answer(
            "📭 <b>Очередь пуста</b>\n\nВсе заявки обработаны.",
            parse_mode="HTML"
        )
        return

    lines = ["📋 <b>Очередь модерации</b>\n"]
    for pid, offer in sorted(pending_offers.items()):
        mode_label = "📤 с юзером" if offer["mode"] == "named" else "🕵️ анонимно"
        time_str = offer["created_at"].strftime("%H:%M")
        username = f"@{offer['username']}" if offer["username"] else "—"

        lines.append(
            f"<b>#{pid}</b> · {mode_label} · <i>{time_str}</i>\n"
            f"   👤 {offer['full_name']} ({username})"
        )

    lines.append(f"\n<b>Всего:</b> {len(pending_offers)}")
    lines.append("\nЧтобы открыть заявку — <code>/pending N</code>")

    await message.answer("\n".join(lines), parse_mode="HTML")


# ─────────────── /pending N — открыть конкретную заявку ───────────────
@dp.message(Command("pending"))
async def cmd_pending(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer(
            "⚠️ Использование: <code>/pending 5</code>\n"
            "Номер заявки можно узнать через /queue",
            parse_mode="HTML"
        )
        return

    pending_id = int(args[1])
    offer = pending_offers.get(pending_id)

    if not offer:
        await message.answer(
            f"❌ Заявка <b>#{pending_id}</b> не найдена или уже обработана.",
            parse_mode="HTML"
        )
        return

    mode_label = "📤 С юзером" if offer["mode"] == "named" else "🕵️ Анонимно"

    header = (
        f"📩 <b>Заявка #{pending_id}</b>\n\n"
        f"👤 <b>От:</b> {offer['full_name']}\n"
        f"🆔 <b>ID:</b> <code>{offer['user_id']}</code>\n"
        f"🔗 <b>Юзернейм:</b> @{offer['username'] if offer['username'] else '—'}\n"
        f"🔒 <b>Режим:</b> {mode_label}\n"
        f"─────────────────────"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Опубликовать",
                    callback_data=f"approve:{pending_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=f"reject:{pending_id}"
                ),
            ]
        ]
    )

    await message.answer(header, parse_mode="HTML")

    content = offer["content"]
    if content["kind"] == "text":
        await message.answer(content["text"], reply_markup=kb)
    elif content["kind"] == "photo":
        await message.answer_photo(
            content["file_id"],
            caption=content["caption"] or None,
            reply_markup=kb
        )
    elif content["kind"] == "video":
        await message.answer_video(
            content["file_id"],
            caption=content["caption"] or None,
            reply_markup=kb
        )


# ─────────────── /cancel ───────────────
@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    if await state.get_state() is None:
        await message.answer("Нечего отменять 🤷")
        return

    await state.clear()
    await message.answer(
        "❌ <b>Отменено</b>\n\nНачать заново?",
        parse_mode="HTML",
        reply_markup=main_menu_kb()
    )


# ─────────────── Фолбэк: любое сообщение вне сценария ───────────────
@dp.message()
async def fallback_handler(message: Message, state: FSMContext):
    await state.clear()

    await message.answer(
        "🤔 <b>Я тебя не понял</b>\n\n"
        "Похоже, ты написал без команды. Чтобы отправить заявку — "
        "нажми кнопку ниже 👇\n\n"
        "<i>Если давно не пользовался ботом — начни с /start.</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✍️ Написать ещё", callback_data="send_offer")],
                [InlineKeyboardButton(text="🏠 Начать заново", callback_data="restart")],
            ]
        )
    )


# ─────────────── Кнопка "Начать заново" ───────────────
@dp.callback_query(F.data == "restart")
async def on_restart(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    await callback.message.edit_text(
        "🏠 <b>Главное меню</b>\n\n"
        "Жми кнопку, чтобы отправить заявку 👇",
        parse_mode="HTML",
        reply_markup=main_menu_kb()
    )


# ─────────────── Запуск ───────────────
async def main():
    print(f"📋 ADMIN_IDS = {ADMIN_IDS}")
    print(f"📢 CHANNEL_ID = {CHANNEL_ID}")

    for admin_id in ADMIN_IDS:
        try:
            chat = await bot.get_chat(admin_id)
            print(f"✅ Админ {admin_id}: {chat.full_name}")
        except Exception as e:
            print(f"❌ Админ {admin_id} НЕДОСТУПЕН: {e}")

    try:
        chat = await bot.get_chat(CHANNEL_ID)
        print(f"✅ Канал: {chat.title}")
    except Exception as e:
        print(f"❌ Канал {CHANNEL_ID} НЕДОСТУПЕН: {e}")

    print("Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())