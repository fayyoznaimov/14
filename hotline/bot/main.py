import os, re, asyncio, datetime, csv, io
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, FSInputFile, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest

from db import (
    init_db, wait_db,
    set_user_category, get_user_category,
    set_user_lang, get_user_lang,
    is_blocked, block_user, unblock_user, list_blocked,
    list_users, list_complaints, insert_complaint, get_by_ticket, set_status,
    last_submit_time, touch_rate_limit, stats_counts
)

# --- ENV ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")
MOD_CHAT_ID = int(os.getenv("MOD_CHAT_ID", "0"))
RATE_LIMIT_SECONDS = int(os.getenv("RATE_LIMIT_SECONDS", "30"))
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "changeme")
ADMIN_IDS = set(int(x.strip()) for x in os.getenv("ADMIN_IDS","").split(",") if x.strip().isdigit())

# S3 params (optional)
S3_ENDPOINT = os.getenv("S3_ENDPOINT")
S3_BUCKET   = os.getenv("S3_BUCKET")
S3_REGION   = os.getenv("S3_REGION")
S3_ACCESS   = os.getenv("S3_ACCESS_KEY")
S3_SECRET   = os.getenv("S3_SECRET_KEY")
S3_USE_SSL  = os.getenv("S3_USE_SSL","true").lower() == "true"

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# --- i18n ---
T = {
    "ru": {
        "menu": "Выберите действие:",
        "btn_complaint": "🟥 Жалоба",
        "btn_suggestion": "🟩 Предложение",
        "btn_my": "📜 Мои обращения",
        "btn_about": "ℹ️ О сервисе",
        "category_set": "Категория установлена: <b>{name}</b>.\nТеперь отправьте текст или медиа.",
        "complaint_name": "жалоба",
        "suggestion_name": "предложение",
        "link_block": "🚫 Ссылки и теги запрещены. Удалите ссылку и отправьте текст повторно.",
        "blocked": "⛔ Вы заблокированы. Обращения от вас не принимаются.",
        "select_category": "Выберите тип обращения:",
        "saved": "✅ Обращение сохранено. Номер: <b>{ticket}</b>\nСпасибо!",
        "my_empty": "У вас пока нет обращений.",
        "my_list": "📜 Ваши обращения:",
        "about": "ℹ️ Сервис приёма жалоб и предложений.\nКаждое обращение получает номер и отправляется на рассмотрение. Пожалуйста, не отправляйте ссылки.",
        "users_empty": "Список пользователей пуст.",
        "complaints_empty": "Жалоб нет.",
        "suggestions_empty": "Предложений нет.",
        "blocked_empty": "Список блокировок пуст.",
        "blocked_list_title": "⛔ Заблокированные (стр. {page}):",
        "users_title": "👥 Пользователи (стр. {page}):",
        "complaints_title": "📥 Жалобы (стр. {page}):",
        "suggestions_title": "💡 Предложения (стр. {page}):",
        "cant_block_admin": "Нельзя блокировать администратора.",
        "block_usage": "Ответьте /block на сообщение пользователя или /block <user_id> [причина]",
        "unblock_usage": "Ответьте /unblock на сообщение пользователя или /unblock <user_id>",
        "blocked_ok": "Пользователь <code>{uid}</code> заблокирован. Причина: {reason}",
        "unblocked_ok": "Пользователь <code>{uid}</code> разблокирован.",
        "rate_limited": "⏳ Пожалуйста, подождите {sec} сек. между отправками.",
        "stats": "📊 Статистика:\nВсего: {total}\nСегодня: {today}\n7 дней: {week}\n30 дней: {month}\nЖалоб: {complaints}\nПредложений: {suggestions}",
        "status_ok": "Статус заявки <b>{ticket}</b> установлен: <b>{status}</b>.",
        "status_notify": "ℹ️ По вашей заявке <b>{ticket}</b> установлен статус: <b>{status}</b>.",
        "status_usage": "Использование: /setstatus <TICKET> <new|in_progress|done>",
        "export_usage": "Использование: /export complaints|suggestions|users",
        "export_done": "Экспорт готов, отправляю файл…"
    },
    "uz": {
        "menu": "Amalni tanlang:",
        "btn_complaint": "🟥 Shikoyat",
        "btn_suggestion": "🟩 Taklif",
        "btn_my": "📜 Mening murojaatlarim",
        "btn_about": "ℹ️ Xizmat haqida",
        "category_set": "Toifa o‘rnatildi: <b>{name}</b>.\nEndi matn yoki media yuboring.",
        "complaint_name": "shikoyat",
        "suggestion_name": "taklif",
        "link_block": "🚫 Havolalar taqiqlangan. Havolasiz yuboring.",
        "blocked": "⛔ Siz bloklangansiz. Murojaatlar qabul qilinmaydi.",
        "select_category": "Murojaat turini tanlang:",
        "saved": "✅ Murojaat saqlandi. Raqam: <b>{ticket}</b>\nRahmat!",
        "my_empty": "Hali murojaatlaringiz yo‘q.",
        "my_list": "📜 Sizning murojaatlaringiz:",
        "about": "ℹ️ Shikoyat va takliflarni qabul qilish xizmati. Har bir murojaatga raqam beriladi va ko‘rib chiqiladi.",
        "users_empty": "Foydalanuvchilar ro‘yxati bo‘sh.",
        "complaints_empty": "Shikoyatlar yo‘q.",
        "suggestions_empty": "Takliflar yo‘q.",
        "blocked_empty": "Bloklanganlar ro‘yxati bo‘sh.",
        "blocked_list_title": "⛔ Bloklanganlar (sah. {page}):",
        "users_title": "👥 Foydalanuvchilar (sah. {page}):",
        "complaints_title": "📥 Shikoyatlar (sah. {page}):",
        "suggestions_title": "💡 Takliflar (sah. {page}):",
        "cant_block_admin": "Administratorni bloklab bo‘lmaydi.",
        "block_usage": "Javobda /block yoki /block <user_id> [sabab]",
        "unblock_usage": "Javobda /unblock yoki /unblock <user_id>",
        "blocked_ok": "Foydalanuvchi <code>{uid}</code> bloklandi. Sabab: {reason}",
        "unblocked_ok": "Foydalanuvchi <code>{uid}</code> blokdan chiqarildi.",
        "rate_limited": "⏳ Yuborishlar orasida {sec} soniya kuting.",
        "stats": "📊 Statistika:\nJami: {total}\nBugun: {today}\n7 kun: {week}\n30 kun: {month}\nShikoyatlar: {complaints}\nTakliflar: {suggestions}",
        "status_ok": "Ariza holati <b>{ticket}</b>: <b>{status}</b> ga o‘rnatildi.",
        "status_notify": "ℹ️ Sizning <b>{ticket}</b> arizangiz holati: <b>{status}</b>.",
        "status_usage": "Foydalanish: /setstatus <TICKET> <new|in_progress|done>",
        "export_usage": "Foydalanish: /export complaints|suggestions|users",
        "export_done": "Eksport tayyor, fayl yuborilmoqda…"
    }
}

WELCOME = {
    "ru": "👋 <b>Здравствуйте!</b>\nЭто бот для приёма жалоб и предложений.\nИспользуйте кнопки ниже или выберите тип обращения и отправьте текст.",
    "uz": "👋 <b>Assalomu alaykum!</b>\nBu bot shikoyat va takliflarni qabul qiladi.\nQuyidagi tugmalardan foydalaning yoki toifani tanlab matn yuboring."
}

URL_RE = re.compile(r"(https?://|www\.|t\.me/|telegram\.me/|@[a-zA-Z0-9_]{4,}|://)", re.IGNORECASE)

def kb_lang():
    kb = InlineKeyboardBuilder()
    kb.button(text="🇷🇺 Русский", callback_data="lang:ru")
    kb.button(text="🇺🇿 O‘zbek",   callback_data="lang:uz")
    kb.adjust(2)
    return kb.as_markup()

def kb_menu(lang="ru"):
    kb = InlineKeyboardBuilder()
    kb.button(text=T[lang]["btn_complaint"],  callback_data="menu:complaint")
    kb.button(text=T[lang]["btn_suggestion"], callback_data="menu:suggestion")
    kb.button(text=T[lang]["btn_my"],         callback_data="menu:my")
    kb.button(text=T[lang]["btn_about"],      callback_data="menu:about")
    kb.adjust(2,2)
    return kb.as_markup()

def kb_pinned(lang: str = "ru") -> ReplyKeyboardMarkup:
    labels = {
        "ru": ["🟥 Жалоба", "🟩 Предложение", "📜 Мои", "ℹ️ О сервисе", "🌐 Язык"],
        "uz": ["🟥 Shikoyat", "🟩 Taklif", "📜 Mening", "ℹ️ Xizmat haqida", "🌐 Til"]
    }[lang]
    row1 = [KeyboardButton(text=labels[0]), KeyboardButton(text=labels[1])]
    row2 = [KeyboardButton(text=labels[2]), KeyboardButton(text=labels[3])]
    row3 = [KeyboardButton(text=labels[4])]
    return ReplyKeyboardMarkup(keyboard=[row1,row2,row3], resize_keyboard=True, is_persistent=True, input_field_placeholder="Напишите текст…")

async def safe_edit_text(msg, text, reply_markup=None):
    try:
        await msg.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return
        raise

def is_admin(message: Message) -> bool:
    return message.from_user and message.from_user.id in ADMIN_IDS

def lang_of(message: Message) -> str:
    l = get_user_lang(message.from_user.id)
    return l if l in ("ru","uz") else "ru"

def s3_enabled() -> bool:
    return all([S3_ENDPOINT, S3_BUCKET, S3_ACCESS, S3_SECRET])

async def tg_file_to_s3(file_id: str, key_prefix: str) -> str | None:
    if not s3_enabled():
        return None
    try:
        from io import BytesIO
        import boto3
        file = await bot.get_file(file_id)
        buf = BytesIO()
        await bot.download_file(file.file_path, buf)
        buf.seek(0)
        key = f"{key_prefix}/{file_id}"
        s3 = boto3.client("s3", endpoint_url=S3_ENDPOINT, aws_access_key_id=S3_ACCESS, aws_secret_access_key=S3_SECRET, region_name=S3_REGION)
        s3.upload_fileobj(buf, S3_BUCKET, key, ExtraArgs={"ACL": "public-read"})
        return f"{S3_ENDPOINT.rstrip('/')}/{S3_BUCKET}/{key}"
    except Exception:
        return None

# ===== Onboarding / Language =====
@dp.message(CommandStart())
async def start(message: Message):
    l = get_user_lang(message.from_user.id)
    if l not in ("ru","uz"):
        await say(message, "👋 Assalomu alaykum! / Здравствуйте!\nIltimos, tilni tanlang / Пожалуйста, выберите язык:", reply_markup=kb_lang())
    else:
        pinned = kb_admin_pinned(l) if is_admin(message) else kb_pinned(l)
        await say(message, WELCOME[l], reply_markup=pinned)
        await say(message, T[l]["menu"])

@dp.message(Command("lang"))
async def cmd_lang(message: Message):
    await say(message, "🇷🇺 Русский | 🇺🇿 O‘zbek", reply_markup=kb_lang())

@dp.callback_query(F.data.startswith("lang:"))
async def on_lang(cb: CallbackQuery):
    lang = cb.data.split(":",1)[1]
    if lang not in ("ru","uz"): lang = "ru"
    set_user_lang(cb.from_user.id, lang)
    await cb.message.answer(WELCOME[lang], reply_markup=kb_pinned(lang))
    await cb.message.answer(T[lang]["menu"])
    await cb.answer()

# ===== Menu (inline) =====
@dp.callback_query(F.data.startswith("menu:"))
async def on_menu(cb: CallbackQuery):
    lang = get_user_lang(cb.from_user.id) or "ru"
    action = cb.data.split(":",1)[1]
    if action == "complaint":
        set_user_category(cb.from_user.id, "complaint")
        await cb.message.answer(T[lang]["category_set"].format(name=T[lang]["complaint_name"]))
    elif action == "suggestion":
        set_user_category(cb.from_user.id, "suggestion")
        await cb.message.answer(T[lang]["category_set"].format(name=T[lang]["suggestion_name"]))
    elif action == "my":
        rows = list_complaints(None, limit=10, offset=0, by_user=cb.from_user.id)
        if not rows:
            await cb.message.answer(T[lang]["my_empty"])
        else:
            lines = [T[lang]["my_list"], "— — —"]
            for r in rows:
                _id, ticket, uid, un, fn, cat, textval, ftype, status, created = r
                preview = (textval or "").replace("\n"," ")
                if len(preview) > 100: preview = preview[:97] + "…"
                cn = T[lang]["complaint_name"] if cat=="complaint" else T[lang]["suggestion_name"]
                lines.append(f"• <b>{ticket}</b> | {cn} | {status} | {created:%Y-%m-%d %H:%M}\n— {preview}")
            await cb.message.answer("\n".join(lines))
    elif action == "about":
        await cb.message.answer(T[lang]["about"])
    await cb.answer()

# ===== Pinned buttons mapping =====
def _btn_map(lang: str):
    return {
        "ru": {
            "🟥 жалоба": "complaint",
            "🟩 предложение": "suggestion",
            "📜 мои": "my",
            "ℹ️ о сервисе": "about",
            "🌐 язык": "lang",
        },
        "uz": {
            "🟥 shikoyat": "complaint",
            "🟩 taklif": "suggestion",
            "📜 mening": "my",
            "ℹ️ xizmat haqida": "about",
            "🌐 til": "lang",
        }
    }[lang]

@dp.message(Command("menu"))
async def cmd_menu(message: Message):
    l = lang_of(message)
    await say(message, WELCOME[l], reply_markup=kb_pinned(l))
    await say(message, T[l]["menu"])

@dp.message(Command("complaint"))
async def cmd_complaint(message: Message):
    l = lang_of(message)
    set_user_category(message.from_user.id, "complaint")
    await say(message, T[l]["category_set"].format(name=T[l]["complaint_name"]))

@dp.message(Command("suggestion"))
async def cmd_suggestion(message: Message):
    l = lang_of(message)
    set_user_category(message.from_user.id, "suggestion")
    await say(message, T[l]["category_set"].format(name=T[l]["suggestion_name"]))

@dp.message(Command("my"))
async def cmd_my(message: Message):
    l = lang_of(message)
    rows = list_complaints(None, limit=10, offset=0, by_user=message.from_user.id)
    if not rows:
        await say(message, T[l]["my_empty"])
    else:
        lines = [T[l]["my_list"], "— — —"]
        for r in rows:
            _id, ticket, uid, un, fn, cat, textval, ftype, status, created = r
            preview = (textval or "").replace("\n"," ")
            if len(preview) > 100: preview = preview[:97] + "…"
            cn = T[l]["complaint_name"] if cat=="complaint" else T[l]["suggestion_name"]
            lines.append(f"• <b>{ticket}</b> | {cn} | {status} | {created:%Y-%m-%d %H:%M}\n— {preview}")
        await say(message, "\n".join(lines))

@dp.message(Command("about"))
async def cmd_about(message: Message):
    l = lang_of(message)
    await say(message, T[l]["about"])

@dp.message(F.text)
async def handle_buttons_or_text(message: Message):
    l = lang_of(message)
    txt = (message.text or "").strip().lower()
    m = _btn_map(l)

    if txt in m:
        action = m[txt]
        if action == "complaint":  await cmd_complaint(message);  return
        if action == "suggestion": await cmd_suggestion(message); return
        if action == "my":         await cmd_my(message);         return
        if action == "about":      await cmd_about(message);      return
        if action == "lang":       await cmd_lang(message);       return

    # Иначе — это обычный текст обращения
    await handle_payload(message, message.text)

# ===== Admin: lists, block, status, export, stats =====
def _extract_target_uid(message: Message) -> int | None:
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user.id
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) >= 2:
        try: return int(parts[1])
        except ValueError: return None
    return None

@dp.message(Command("users"))
async def cmd_users(message: Message):
    if not is_admin(message): return
    l = lang_of(message)
    args = (message.text or "").split()
    page = int(args[1]) if len(args)>1 and args[1].isdigit() else 1
    rows = list_users(limit=50, offset=(page-1)*50)
    if not rows: await say(message, T[l]["users_empty"]); return
    lines = [T[l]["users_title"].format(page=page)]
    for uid, username, full_name, last, total in rows:
        un = f"@{username}" if username else "-"
        fn = full_name or "-"
        lines.append(f"• <code>{uid}</code> | {un} | {fn} | msg: {total}")
    await say(message, "\n".join(lines))

@dp.message(Command("complaints"))
async def cmd_complaints(message: Message):
    if not is_admin(message): return
    l = lang_of(message)
    args = (message.text or "").split()
    page = int(args[1]) if len(args)>1 and args[1].isdigit() else 1
    rows = list_complaints("complaint", limit=30, offset=(page-1)*30)
    if not rows: await say(message, T[l]["complaints_empty"]); return
    lines = [T[l]["complaints_title"].format(page=page)]
    for r in rows:
        _id, ticket, uid, un, fn, cat, textval, ftype, status, created = r
        preview = (textval or "").replace("\n"," ")
        if len(preview) > 120: preview = preview[:117] + "…"
        un = f"@{un}" if un else "-"
        lines.append(f"{ticket} | <code>{uid}</code> {un} | {status} | {created:%Y-%m-%d %H:%M}\n— {preview}")
    await say(message, "\n".join(lines))

@dp.message(Command("suggestions"))
async def cmd_suggestions(message: Message):
    if not is_admin(message): return
    l = lang_of(message)
    args = (message.text or "").split()
    page = int(args[1]) if len(args)>1 and args[1].isdigit() else 1
    rows = list_complaints("suggestion", limit=30, offset=(page-1)*30)
    if not rows: await say(message, T[l]["suggestions_empty"]); return
    lines = [T[l]["suggestions_title"].format(page=page)]
    for r in rows:
        _id, ticket, uid, un, fn, cat, textval, ftype, status, created = r
        preview = (textval or "").replace("\n"," ")
        if len(preview) > 120: preview = preview[:117] + "…"
        un = f"@{un}" if un else "-"
        lines.append(f"{ticket} | <code>{uid}</code> {un} | {status} | {created:%Y-%m-%d %H:%M}\n— {preview}")
    await say(message, "\n".join(lines))

@dp.message(Command("blocked"))
async def cmd_blocked(message: Message):
    if not is_admin(message): return
    l = lang_of(message)
    args = (message.text or "").split()
    page = int(args[1]) if len(args)>1 and args[1].isdigit() else 1
    rows = list_blocked(limit=50, offset=(page-1)*50)
    if not rows: await say(message, T[l]["blocked_empty"]); return
    lines = [T[l]["blocked_list_title"].format(page=page)]
    for uid, reason, ts in rows:
        r = reason or "-"
        lines.append(f"• <code>{uid}</code> | {r} | {ts:%Y-%m-%d %H:%M}")
    await say(message, "\n".join(lines))

@dp.message(Command("block"))
async def cmd_block(message: Message):
    if not is_admin(message): return
    l = lang_of(message)
    uid = _extract_target_uid(message)
    reason = None
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) == 3: reason = parts[2]
    if not uid: await message.reply(T[l]["block_usage"]); return
    if uid in ADMIN_IDS: await message.reply(T[l]["cant_block_admin"]); return
    block_user(uid, reason)
    await message.reply(T[l]["blocked_ok"].format(uid=uid, reason=reason or "-"))

@dp.message(Command("unblock"))
async def cmd_unblock(message: Message):
    if not is_admin(message): return
    l = lang_of(message)
    uid = _extract_target_uid(message)
    if not uid: await message.reply(T[l]["unblock_usage"]); return
    unblock_user(uid)
    await message.reply(T[l]["unblocked_ok"].format(uid=uid))

@dp.message(Command("setstatus"))
async def cmd_setstatus(message: Message):
    if not is_admin(message): return
    l = lang_of(message)
    parts = (message.text or "").split()
    if len(parts) != 3 or parts[2] not in ("new","in_progress","done"):
        await message.reply(T[l]["status_usage"]); return
    ticket, status = parts[1], parts[2]
    row = get_by_ticket(ticket)
    if not row:
        await message.reply("Ticket not found"); return
    _id, _ticket, uid, _st = row
    set_status(ticket, status)
    await message.reply(T[l]["status_ok"].format(ticket=ticket, status=status))
    try:
        await bot.send_message(uid, T[l]["status_notify"].format(ticket=ticket, status=status))
    except Exception:
        pass

@dp.message(Command("export"))
async def cmd_export(message: Message):
    if not is_admin(message): return
    l = lang_of(message)
    parts = (message.text or "").split()
    if len(parts) != 2 or parts[1] not in ("complaints","suggestions","users"):
        await message.reply(T[l]["export_usage"]); return
    what = parts[1]
    await message.reply(T[l]["export_done"])
    buf = io.StringIO()
    writer = csv.writer(buf)
    filename = f"{what}_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    if what == "users":
        rows = list_users(limit=100000, offset=0)
        writer.writerow(["user_id","username","full_name","last_activity","total_messages"])
        for uid, username, full_name, last, total in rows:
            writer.writerow([uid, username or "", full_name or "", last, total])
    else:
        cat = "complaint" if what=="complaints" else "suggestion"
        rows = list_complaints(cat, limit=100000, offset=0)
        writer.writerow(["ticket_no","user_id","username","full_name","category","status","created_at","message_text","file_type"])
        for r in rows:
            _id, ticket, uid, un, fn, category, textval, ftype, status, created = r
            writer.writerow([ticket, uid, un or "", fn or "", category, status, created, (textval or "").replace("\n"," "), ftype or ""])
    data = buf.getvalue().encode("utf-8")
    from tempfile import NamedTemporaryFile
    with NamedTemporaryFile("wb", delete=False, suffix=".csv") as f:
        f.write(data)
        temp_path = f.name
    await message.answer_document(FSInputFile(temp_path, filename=filename))

# ===== Submissions =====
async def handle_payload(message: Message, text_value: str, file_type=None, file_id=None):
    l = lang_of(message)

    if is_blocked(message.from_user.id):
        await message.reply(T[l]["blocked"]); return

    if text_value and URL_RE.search(text_value):
        await message.reply(T[l]["link_block"]); return

    category = get_user_category(message.from_user.id)
    if category not in ("complaint", "suggestion"):
        await message.reply(T[l]["select_category"], reply_markup=kb_menu(l)); return

    now = datetime.datetime.utcnow()
    last = last_submit_time(message.from_user.id)
    if last:
        delta = (now - last).total_seconds()
        if delta < RATE_LIMIT_SECONDS:
            await message.reply(T[l]["rate_limited"].format(sec=int(RATE_LIMIT_SECONDS - delta))); return

    file_url = None
    if file_id and file_type in ("photo","document","voice","video"):
        file_url = await tg_file_to_s3(file_id, key_prefix=f"{message.from_user.id}/{now.strftime('%Y%m%d')}")

    ticket = insert_complaint(
        user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=f"{message.from_user.full_name}",
        category=category,
        message_text=text_value or "",
        file_type=file_type,
        file_id=file_id,
        file_url=file_url
    )
    touch_rate_limit(message.from_user.id, now)

    await message.reply(T[l]["saved"].format(ticket=ticket))
    if MOD_CHAT_ID != 0:
        try:
            await message.send_copy(chat_id=MOD_CHAT_ID)
        except Exception:
            await bot.send_message(MOD_CHAT_ID, f"New {category} {ticket}:\n{text_value or ''}")

@dp.message(F.photo)
async def handle_photo(message: Message):
    file_id = message.photo[-1].file_id
    caption = message.caption or ""
    await handle_payload(message, caption, file_type="photo", file_id=file_id)

@dp.message(F.document)
async def handle_doc(message: Message):
    name = message.document.file_name or ""
    caption = message.caption or name
    await handle_payload(message, caption, file_type="document", file_id=message.document.file_id)

@dp.message(F.voice)
async def handle_voice(message: Message):
    await handle_payload(message, "voice", file_type="voice", file_id=message.voice.file_id)

@dp.message(F.video)
async def handle_video(message: Message):
    caption = message.caption or "video"
    await handle_payload(message, caption, file_type="video", file_id=message.video.file_id)

async def on_startup():
    wait_db()
    init_db()

def main():
    asyncio.run(on_startup())
    dp.run_polling(bot)

if __name__ == "__main__":
    main()


# ===== Admin Quick Buttons (reply keyboard) =====
@dp.message(F.text.in_({"📥 Жалобы", "📥 Shikoyatlar"}))
async def goto_complaints(message: Message):
    if not is_admin(message): return
    # mimic /complaints
    await cmd_complaints(message)

@dp.message(F.text.in_({"💡 Предложения", "💡 Takliflar"}))
async def goto_suggestions(message: Message):
    if not is_admin(message): return
    await cmd_suggestions(message)

@dp.message(F.text.in_({"👥 Пользователи", "👥 Foydalanuvchilar"}))
async def goto_users(message: Message):
    if not is_admin(message): return
    await cmd_users(message)

@dp.message(F.text.in_({"📊 Статистика", "📊 Statistika"}))
async def goto_stats(message: Message):
    if not is_admin(message): return
    await cmd_stats(message)
