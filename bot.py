import telebot
from telebot import types
import json
import os
import random
import threading
import requests
import time
from datetime import datetime, timedelta

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = "8896941108:AAGtzglNGd2JoNxKKxcr3IjsneBqi_OD5Wc"
ADMIN_ID = 1075018527
CRYPTO_BOT_TOKEN = "617372:AATHO7ftVok1F576SuLMelt32cncAyWMatw"
# ==================================================

bot = telebot.TeleBot(BOT_TOKEN)
DB_FILE = "lucky_db.json"

def load_db():
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, 'w') as f:
            json.dump({
                "settings": {
                    "max_tickets": 100,
                    "winners_count": 3,
                    "ticket_price": 0.5,
                    "commission": 20,
                    "duration_hours": 24
                },
                "temp_settings": {},
                "fast_game": {
                    "max_tickets": 50,
                    "winners_count": 1,
                    "ticket_price": 0.5,
                    "commission": 20,
                    "duration_minutes": 10
                },
                "games": [],
                "fast_games": [],
                "tickets": [],
                "fast_tickets": [],
                "winners": [],
                "pending_payments": {},
                "processed_invoices": [],
                "referrals": {},
                "users": {}
            }, f)
    with open(DB_FILE, 'r') as f:
        return json.load(f)

def save_db(db):
    with open(DB_FILE, 'w') as f:
        json.dump(db, f, indent=2)

def get_active_game(db):
    for game in db["games"]:
        if game["status"] == "active":
            return game
    return None

def get_active_fast_game(db):
    for game in db.get("fast_games", []):
        if game["status"] == "active":
            return game
    return None

def create_game(db):
    settings = db["temp_settings"] if db["temp_settings"] else db["settings"]
    max_t = settings["max_tickets"]
    winners = settings["winners_count"]
    duration = settings["duration_hours"]
    
    game = {
        "id": len(db["games"]) + 1,
        "status": "active",
        "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "end_time": (datetime.now() + timedelta(hours=duration)).strftime("%Y-%m-%d %H:%M:%S"),
        "prize_pool": 0.0,
        "winners_count": winners,
        "max_tickets": max_t,
        "type": "standard"
    }
    db["games"].append(game)
    save_db(db)
    threading.Timer(duration * 3600, finish_game, args=[game["id"]]).start()
    return game

def create_fast_game(db):
    s = db["fast_game"]
    game = {
        "id": len(db.get("fast_games", [])) + 1,
        "status": "active",
        "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "end_time": (datetime.now() + timedelta(minutes=s["duration_minutes"])).strftime("%Y-%m-%d %H:%M:%S"),
        "prize_pool": 0.0,
        "winners_count": s["winners_count"],
        "max_tickets": s["max_tickets"],
        "type": "fast"
    }
    db.setdefault("fast_games", []).append(game)
    save_db(db)
    threading.Timer(s["duration_minutes"] * 60, finish_fast_game, args=[game["id"]]).start()
    return game

def finish_game(game_id):
    db = load_db()
    game = next((g for g in db["games"] if g["id"] == game_id and g["status"] == "active"), None)
    if game:
        process_finish(db, game, "tickets", "games")

def finish_fast_game(game_id):
    db = load_db()
    game = next((g for g in db.get("fast_games", []) if g["id"] == game_id and g["status"] == "active"), None)
    if game:
        process_finish(db, game, "fast_tickets", "fast_games")

def process_finish(db, game, tickets_key, games_key):
    participants = [t for t in db.get(tickets_key, []) if t["game_id"] == game["id"]]
    
    if not participants:
        game["status"] = "finished"
        save_db(db)
        if game["type"] == "fast":
            create_fast_game(db)
        else:
            db["temp_settings"] = {}
            save_db(db)
            create_game(db)
        return
    
    commission = db["settings"]["commission"] / 100
    ticket_price = db["settings"]["ticket_price"]
    prize_pool = len(participants) * ticket_price * (1 - commission)
    winners_count = min(game["winners_count"], len(participants))
    winners = random.sample(participants, winners_count)
    prize_each = prize_pool / winners_count
    
    for w in winners:
        db.setdefault("winners", []).append({
            "game_id": game["id"], "user_id": w["user_id"],
            "username": w.get("username", "Аноним"), "prize": prize_each,
            "type": game["type"]
        })
    
    game["status"] = "finished"
    game["prize_pool"] = prize_pool
    if game["type"] != "fast":
        db["temp_settings"] = {}
    save_db(db)
    
    type_name = "БЫСТРЫЙ" if game["type"] == "fast" else "СТАНДАРТНЫЙ"
    
    for w in winners:
        try:
            bot.send_message(w["user_id"], f"🎉 Ты выиграл *{prize_each:.1f} TON* в {type_name} розыгрыше!", parse_mode="Markdown")
        except:
            pass
    
    for p in participants:
        try:
            bot.send_message(p["user_id"], f"🏆 {type_name} розыгрыш #{game['id']} завершён!\n💰 Банк: *{prize_pool:.1f} TON*", parse_mode="Markdown")
        except:
            pass
    
    if game["type"] == "fast":
        create_fast_game(db)
    else:
        create_game(db)

def format_block(lines_list):
    """Принимает список строк, возвращает красивый блок"""
    width = 26
    result = ["╔" + "═" * width + "╗"]
    for line in lines_list:
        # Убираем Markdown-разметку для подсчёта длины
        clean = line.replace("*", "").replace("_", "").replace("`", "")
        # Считаем длину: ASCII = 1, остальное = 2
        length = sum(2 if ord(c) > 127 else 1 for c in clean)
        pad = max(0, width - length - 1)
        result.append("║ " + line + " " * pad + "║")
    result.append("╚" + "═" * width + "╝")
    return "\n".join(result)

def create_invoice(user_id, game_id, amount, game_type="standard"):
    """Создаёт инвойс в TON через CryptoBot API"""
    url = "https://pay.crypt.bot/api/createInvoice"
    headers = {
        "Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN,
        "Content-Type": "application/json"
    }
    body = {
        "asset": "TON",
        "amount": str(amount),
        "description": f"Lucky Bank {game_type.capitalize()} Ticket",
        "payload": f"{user_id}_{game_id}_{game_type}",
        "allow_comments": False,
        "allow_anonymous": False
    }
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=10)
        return resp.json()
    except:
        return {"ok": False}

def check_invoice(invoice_id):
    """Проверяет статус инвойса"""
    url = f"https://pay.crypt.bot/api/getInvoices?invoice_ids={invoice_id}"
    headers = {"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        return resp.json()
    except:
        return {"ok": False}

# ==================== КОМАНДЫ ====================

@bot.message_handler(commands=['start'])
def start(message):
    db = load_db()
    uid = str(message.from_user.id)
    
    # Сохраняем пользователя
    db["users"][uid] = {"username": message.from_user.username}
    
    # Рефералы
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref"):
        ref_id = args[1].replace("ref", "")
        if ref_id != uid:
            game = get_active_game(db)
            if game:
                db.setdefault("tickets", []).append({
                    "user_id": int(ref_id), "username": db.get("users", {}).get(ref_id, {}).get("username"),
                    "game_id": game["id"]
                })
                save_db(db)
                try:
                    bot.send_message(int(ref_id), "🎁 Ты получил бесплатный билет за друга!")
                except:
                    pass
    
    save_db(db)
    
    game = get_active_game(db)
    fast_game = get_active_fast_game(db)
    
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    text = "🏦 *LUCKY BANK*\n\n"
    
    if game:
        sold = len([t for t in db.get("tickets", []) if t["game_id"] == game["id"]])
        bank = sold * db["settings"]["ticket_price"] * (1 - db["settings"]["commission"] / 100)
        end_time = datetime.strptime(game["end_time"], "%Y-%m-%d %H:%M:%S")
        remaining = end_time - datetime.now()
        hours = max(0, remaining.seconds // 3600)
        minutes = max(0, (remaining.seconds % 3600) // 60)
        
        lines = [
            "💎 СТАНДАРТНЫЙ",
            "",
            f"🪙 Банк: {bank:.1f} TON",
            f"👥 Участников: {sold}/{game['max_tickets']}",
            f"🎯 Победителей: {game['winners_count']}",
            f"⏳ До конца: {hours}ч {minutes}м"
        ]
        text += format_block(lines)
        keyboard.add(types.InlineKeyboardButton("🎫 Купить (Стандарт)", callback_data="buy_standard"))
    
    if fast_game:
        sold_fast = len([t for t in db.get("fast_tickets", []) if t["game_id"] == fast_game["id"]])
        bank_fast = sold_fast * db["fast_game"]["ticket_price"] * (1 - db["fast_game"]["commission"] / 100)
        end_time_fast = datetime.strptime(fast_game["end_time"], "%Y-%m-%d %H:%M:%S")
        remaining_fast = end_time_fast - datetime.now()
        minutes_fast = max(0, remaining_fast.seconds // 60)
        
        lines_fast = [
            "⚡️ БЫСТРЫЙ",
            "",
            f"🪙 Банк: {bank_fast:.1f} TON",
            f"👥 Участников: {sold_fast}/{fast_game['max_tickets']}",
            f"🎯 Победитель: 1",
            f"⏳ До конца: {minutes_fast}м"
        ]
        text += "\n" + format_block(lines_fast)
        keyboard.add(types.InlineKeyboardButton("⚡️ Купить (Быстрый)", callback_data="buy_fast"))
    
    keyboard.add(
        types.InlineKeyboardButton("📊 Мои билеты", callback_data="my_tickets"),
        types.InlineKeyboardButton("🏆 Зал славы", callback_data="winners_history"),
        types.InlineKeyboardButton("👥 Рефералы", callback_data="referral"),
        types.InlineKeyboardButton("📖 Правила", callback_data="rules")
    )
    
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=keyboard)

@bot.message_handler(commands=['LuckyBank_X7k9M_Admin_2024'])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        return
    show_admin_main(message.chat.id)

def show_admin_main(chat_id):
    db = load_db()
    total = sum([g.get("prize_pool", 0) * db["settings"]["commission"] / 80 for g in db["games"] if g["status"] == "finished"])
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("⚙️ Стандартные настройки", callback_data="admin_standard"),
        types.InlineKeyboardButton("🎯 Разовый розыгрыш", callback_data="admin_temp"),
        types.InlineKeyboardButton("⚡️ Быстрый розыгрыш", callback_data="admin_fast"),
        types.InlineKeyboardButton("💰 Баланс", callback_data="admin_balance"),
        types.InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast"),
        types.InlineKeyboardButton("🚪 Выйти", callback_data="admin_exit")
    )
    
    bot.send_message(chat_id,
        f"🔐 *АДМИН-ПАНЕЛЬ*\n\n💰 Заработано: *{total:.1f} TON*",
        parse_mode="Markdown", reply_markup=markup)

# ==================== ПОКУПКА ====================

def buy_ticket(call, game_type):
    db = load_db()
    uid = str(call.from_user.id)
    
    if game_type == "standard":
        game = get_active_game(db)
        price = db["settings"]["ticket_price"]
    else:
        game = get_active_fast_game(db)
        price = db["fast_game"]["ticket_price"]
    
    if not game:
        bot.answer_callback_query(call.id, "Нет активной игры.")
        return
    
    data = create_invoice(call.from_user.id, game["id"], price, game_type)
    
    if data.get("ok"):
        inv_url = data["result"]["pay_url"]
        inv_id = str(data["result"]["invoice_id"])
        
        db["pending_payments"][uid] = {
            "invoice_id": inv_id, "game_id": game["id"],
            "amount": price, "game_type": game_type
        }
        save_db(db)
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(f"💳 Оплатить {price} TON", url=inv_url))
        markup.add(types.InlineKeyboardButton("🔄 Проверить", callback_data=f"check_{inv_id}"))
        
        bot.send_message(call.message.chat.id,
            f"💸 *ПОКУПКА БИЛЕТА*\n\nСтоимость: *{price} TON*\nНажми кнопку ниже.",
            parse_mode="Markdown", reply_markup=markup)
        bot.answer_callback_query(call.id)
    else:
        bot.answer_callback_query(call.id, "❌ Ошибка создания платежа.")

def check_payment(call, inv_id):
    db = load_db()
    uid = str(call.from_user.id)
    payment = db["pending_payments"].get(uid)
    
    if not payment or payment["invoice_id"] != inv_id:
        bot.answer_callback_query(call.id, "Платёж не найден.")
        return
    
    data = check_invoice(inv_id)
    
    if data.get("ok") and data["result"]["items"]:
        inv = data["result"]["items"][0]
        if inv["status"] == "paid":
            game_type = payment["game_type"]
            game_id = payment["game_id"]
            tickets_key = "fast_tickets" if game_type == "fast" else "tickets"
            
            db.setdefault(tickets_key, []).append({
                "user_id": call.from_user.id,
                "username": call.from_user.username,
                "game_id": game_id
            })
            db["processed_invoices"].append(inv_id)
            del db["pending_payments"][uid]
            save_db(db)
            
            if game_type == "standard":
                game = get_active_game(db)
            else:
                game = get_active_fast_game(db)
            
            sold = len([t for t in db.get(tickets_key, []) if t["game_id"] == game["id"]])
            
            bot.answer_callback_query(call.id, "✅ Оплачено!")
            bot.send_message(call.message.chat.id,
                f"✅ *БИЛЕТ ОПЛАЧЕН*\n\nНомер: #{sold}\nВ игре: {sold}/{game['max_tickets']}",
                parse_mode="Markdown")
            
            if sold >= game["max_tickets"]:
                if game_type == "fast":
                    finish_fast_game(game["id"])
                else:
                    finish_game(game["id"])
        else:
            bot.answer_callback_query(call.id, "⏳ Ещё не оплачен.")
    else:
        bot.answer_callback_query(call.id, "❌ Ошибка проверки.")

# ==================== КНОПКИ ====================

admin_states = {}

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    db = load_db()
    uid = str(call.from_user.id)
    
    # Покупка
    if call.data == "buy_standard":
        buy_ticket(call, "standard")
    elif call.data == "buy_fast":
        buy_ticket(call, "fast")
    
    # Проверка оплаты
    elif call.data.startswith("check_"):
        check_payment(call, call.data.replace("check_", ""))
    
    # Мои билеты
    elif call.data == "my_tickets":
        std = len([t for t in db.get("tickets", []) if t["user_id"] == call.from_user.id and 
                   any(g["id"] == t["game_id"] and g["status"] == "active" for g in db.get("games", []))])
        fast = len([t for t in db.get("fast_tickets", []) if t["user_id"] == call.from_user.id and 
                   any(g["id"] == t["game_id"] and g["status"] == "active" for g in db.get("fast_games", []))])
        bot.send_message(call.message.chat.id,
            f"📊 *ТВОИ БИЛЕТЫ*\n\n🎫 Стандарт: *{std}*\n⚡️ Быстрый: *{fast}*",
            parse_mode="Markdown")
        bot.answer_callback_query(call.id)
    
    # Зал славы
    elif call.data == "winners_history":
        winners = db.get("winners", [])[-10:]
        if winners:
            text = "🏆 *ЗАЛ СЛАВЫ*\n\n"
            for w in reversed(winners):
                name = f"@{w['username']}" if w['username'] else f"ID:{w['user_id']}"
                emoji = "⚡️" if w.get("type") == "fast" else "👑"
                text += f"{emoji} {name} — *{w['prize']:.1f} TON*\n"
        else:
            text = "Пока никто не выигрывал. Стань первым! 🚀"
        bot.send_message(call.message.chat.id, text, parse_mode="Markdown")
        bot.answer_callback_query(call.id)
    
    # Рефералы
    elif call.data == "referral":
        ref_link = f"https://t.me/{bot.get_me().username}?start=ref{call.from_user.id}"
        bot.send_message(call.message.chat.id,
            f"👥 *РЕФЕРАЛЫ*\n\nПригласи друга — получи бесплатный билет!\n\n🔗 Твоя ссылка:\n`{ref_link}`",
            parse_mode="Markdown")
        bot.answer_callback_query(call.id)
    
    # Правила
    elif call.data == "rules":
        bot.send_message(call.message.chat.id,
            f"📖 *ПРАВИЛА*\n\n🎫 Стандарт: {db['settings']['max_tickets']} билетов, каждые {db['settings']['duration_hours']}ч\n"
            f"⚡️ Быстрый: {db['fast_game']['max_tickets']} билетов, каждые {db['fast_game']['duration_minutes']}м\n"
            f"💵 Цена: {db['settings']['ticket_price']} TON\n📊 Комиссия: {db['settings']['commission']}%",
            parse_mode="Markdown")
        bot.answer_callback_query(call.id)
    
    # АДМИН-КНОПКИ
    elif call.data == "admin_standard" and call.from_user.id == ADMIN_ID:
        s = db["settings"]
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(f"🎫 Билетов: {s['max_tickets']}", callback_data="edit_tickets"),
            types.InlineKeyboardButton(f"🏆 Победителей: {s['winners_count']}", callback_data="edit_winners"),
            types.InlineKeyboardButton(f"💵 Цена: {s['ticket_price']} TON", callback_data="edit_price"),
            types.InlineKeyboardButton(f"📊 Комиссия: {s['commission']}%", callback_data="edit_commission"),
            types.InlineKeyboardButton(f"⏰ Длительность: {s['duration_hours']}ч", callback_data="edit_duration"),
            types.InlineKeyboardButton("🔙 Назад", callback_data="admin_back")
        )
        bot.edit_message_text("⚙️ *СТАНДАРТНЫЕ НАСТРОЙКИ*", call.message.chat.id, call.message.message_id,
                             parse_mode="Markdown", reply_markup=markup)
    
    elif call.data == "admin_temp" and call.from_user.id == ADMIN_ID:
        s = db["temp_settings"] if db["temp_settings"] else db["settings"]
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(f"🎫 Билетов: {s.get('max_tickets', db['settings']['max_tickets'])}", callback_data="temp_tickets"),
            types.InlineKeyboardButton(f"🏆 Победителей: {s.get('winners_count', db['settings']['winners_count'])}", callback_data="temp_winners"),
            types.InlineKeyboardButton(f"💵 Цена: {s.get('ticket_price', db['settings']['ticket_price'])} TON", callback_data="temp_price"),
            types.InlineKeyboardButton(f"⏰ Длительность: {s.get('duration_hours', db['settings']['duration_hours'])}ч", callback_data="temp_duration"),
            types.InlineKeyboardButton("✅ Применить", callback_data="temp_apply"),
            types.InlineKeyboardButton("🔄 Сбросить", callback_data="temp_reset"),
            types.InlineKeyboardButton("🔙 Назад", callback_data="admin_back")
        )
        bot.edit_message_text("🎯 *РАЗОВЫЙ РОЗЫГРЫШ*", call.message.chat.id, call.message.message_id,
                             parse_mode="Markdown", reply_markup=markup)
    
    elif call.data == "admin_fast" and call.from_user.id == ADMIN_ID:
        s = db["fast_game"]
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(f"🎫 Билетов: {s['max_tickets']}", callback_data="edit_fast_tickets"),
            types.InlineKeyboardButton(f"💵 Цена: {s['ticket_price']} TON", callback_data="edit_fast_price"),
            types.InlineKeyboardButton(f"⏰ Длительность: {s['duration_minutes']}м", callback_data="edit_fast_duration"),
            types.InlineKeyboardButton("🔙 Назад", callback_data="admin_back")
        )
        bot.edit_message_text("⚡️ *БЫСТРЫЙ РОЗЫГРЫШ*", call.message.chat.id, call.message.message_id,
                             parse_mode="Markdown", reply_markup=markup)
    
    elif call.data == "admin_balance" and call.from_user.id == ADMIN_ID:
        total = sum([g.get("prize_pool", 0) * db["settings"]["commission"] / 80 for g in db["games"] if g["status"] == "finished"])
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="admin_back"))
        bot.edit_message_text(f"💰 *БАЛАНС*\n\nЗаработано: *{total:.1f} TON*",
            call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
    
    elif call.data == "admin_broadcast" and call.from_user.id == ADMIN_ID:
        admin_states[uid] = {"broadcast": True}
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Отмена", callback_data="admin_back"))
        bot.edit_message_text("📢 Введи сообщение для рассылки:",
            call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    elif call.data == "admin_back" and call.from_user.id == ADMIN_ID:
        show_admin_main(call.message.chat.id)
    
    elif call.data == "admin_exit" and call.from_user.id == ADMIN_ID:
        if uid in admin_states:
            del admin_states[uid]
        bot.delete_message(call.message.chat.id, call.message.message_id)
    
    # Редактирование СТАНДАРТНЫХ
    elif call.data.startswith("edit_") and not call.data.startswith("edit_fast_") and call.from_user.id == ADMIN_ID:
        param = call.data.replace("edit_", "")
        admin_states[uid] = {"editing": param}
        names = {"tickets": "билетов", "winners": "победителей", "price": "цена (TON)", "commission": "комиссия (%)", "duration": "длительность (ч)"}
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="admin_standard"))
        bot.edit_message_text(f"Новое значение *{names[param]}*:\nТекущее: *{db['settings'][param]}*",
            call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
    
    # Редактирование БЫСТРЫХ
    elif call.data.startswith("edit_fast_") and call.from_user.id == ADMIN_ID:
        param = call.data.replace("edit_fast_", "")
        admin_states[uid] = {"editing_fast": param}
        names = {"tickets": "билетов", "price": "цена (TON)", "duration": "длительность (мин)"}
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="admin_fast"))
        bot.edit_message_text(f"Новое значение *{names[param]}*:\nТекущее: *{db['fast_game'][param]}*",
            call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
    
    # Разовые параметры
    elif call.data.startswith("temp_") and call.from_user.id == ADMIN_ID:
        action = call.data.replace("temp_", "")
        if action == "apply":
            bot.answer_callback_query(call.id, "✅ Применено!" if db["temp_settings"] else "ℹ️ Нет изменений")
        elif action == "reset":
            db["temp_settings"] = {}
            save_db(db)
            show_temp_settings(call.message.chat.id, call.message.message_id)
        elif action in ["tickets", "winners", "price", "duration"]:
            admin_states[uid] = {"editing_temp": action}
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="admin_temp"))
            bot.edit_message_text(f"Новое значение *{action}*:", call.message.chat.id, call.message.message_id,
                                parse_mode="Markdown", reply_markup=markup)

def show_temp_settings(chat_id, msg_id=None):
    db = load_db()
    s = db["temp_settings"] if db["temp_settings"] else db["settings"]
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(f"🎫 Билетов: {s.get('max_tickets', db['settings']['max_tickets'])}", callback_data="temp_tickets"),
        types.InlineKeyboardButton(f"🏆 Победителей: {s.get('winners_count', db['settings']['winners_count'])}", callback_data="temp_winners"),
        types.InlineKeyboardButton(f"💵 Цена: {s.get('ticket_price', db['settings']['ticket_price'])} TON", callback_data="temp_price"),
        types.InlineKeyboardButton(f"⏰ Длительность: {s.get('duration_hours', db['settings']['duration_hours'])}ч", callback_data="temp_duration"),
        types.InlineKeyboardButton("✅ Применить", callback_data="temp_apply"),
        types.InlineKeyboardButton("🔄 Сбросить", callback_data="temp_reset"),
        types.InlineKeyboardButton("🔙 Назад", callback_data="admin_back")
    )
    if msg_id:
        bot.edit_message_text("🎯 *РАЗОВЫЙ РОЗЫГРЫШ*", chat_id, msg_id, parse_mode="Markdown", reply_markup=markup)
    else:
        bot.send_message(chat_id, "🎯 *РАЗОВЫЙ РОЗЫГРЫШ*", parse_mode="Markdown", reply_markup=markup)

# ==================== ТЕКСТ ====================

@bot.message_handler(func=lambda m: True)
def text_handler(message):
    uid = str(message.from_user.id)
    
    if uid in admin_states and message.from_user.id == ADMIN_ID:
        state = admin_states[uid]
        
        if state.get("broadcast"):
            db = load_db()
            users = set()
            for t in db.get("tickets", []): users.add(t["user_id"])
            for t in db.get("fast_tickets", []): users.add(t["user_id"])
            count = 0
            for u in users:
                try:
                    bot.send_message(u, message.text)
                    count += 1
                except: pass
            bot.send_message(message.chat.id, f"📢 Отправлено {count} чел.")
            del admin_states[uid]
            show_admin_main(message.chat.id)
            return
        
        if state.get("editing"):
            param = state["editing"]
            try:
                val = float(message.text) if param in ["price", "commission"] else int(message.text)
                db = load_db()
                db["settings"][param] = val
                save_db(db)
                del admin_states[uid]
                # Показываем обновлённые настройки
                s = db["settings"]
                markup = types.InlineKeyboardMarkup(row_width=1)
                markup.add(
                    types.InlineKeyboardButton(f"🎫 Билетов: {s['max_tickets']}", callback_data="edit_tickets"),
                    types.InlineKeyboardButton(f"🏆 Победителей: {s['winners_count']}", callback_data="edit_winners"),
                    types.InlineKeyboardButton(f"💵 Цена: {s['ticket_price']} TON", callback_data="edit_price"),
                    types.InlineKeyboardButton(f"📊 Комиссия: {s['commission']}%", callback_data="edit_commission"),
                    types.InlineKeyboardButton(f"⏰ Длительность: {s['duration_hours']}ч", callback_data="edit_duration"),
                    types.InlineKeyboardButton("🔙 Назад", callback_data="admin_back")
                )
                bot.send_message(message.chat.id, "⚙️ *СТАНДАРТНЫЕ НАСТРОЙКИ*\n✅ Сохранено!", parse_mode="Markdown", reply_markup=markup)
            except:
                bot.send_message(message.chat.id, "❌ Неверное число.")
            return
        
        if state.get("editing_temp"):
            param = state["editing_temp"]
            try:
                val = float(message.text) if param == "price" else int(message.text)
                db = load_db()
                db.setdefault("temp_settings", {})[param] = val
                save_db(db)
                del admin_states[uid]
                show_temp_settings(message.chat.id)
            except:
                bot.send_message(message.chat.id, "❌ Неверное число.")
            return
        
        if state.get("editing_fast"):
            param = state["editing_fast"]
            try:
                val = float(message.text) if param == "price" else int(message.text)
                db = load_db()
                db["fast_game"][param] = val
                save_db(db)
                del admin_states[uid]
                s = db["fast_game"]
                markup = types.InlineKeyboardMarkup(row_width=1)
                markup.add(
                    types.InlineKeyboardButton(f"🎫 Билетов: {s['max_tickets']}", callback_data="edit_fast_tickets"),
                    types.InlineKeyboardButton(f"💵 Цена: {s['ticket_price']} TON", callback_data="edit_fast_price"),
                    types.InlineKeyboardButton(f"⏰ Длительность: {s['duration_minutes']}м", callback_data="edit_fast_duration"),
                    types.InlineKeyboardButton("🔙 Назад", callback_data="admin_back")
                )
                bot.send_message(message.chat.id, "⚡️ *БЫСТРЫЙ РОЗЫГРЫШ*\n✅ Сохранено!", parse_mode="Markdown", reply_markup=markup)
            except:
                bot.send_message(message.chat.id, "❌ Неверное число.")
            return
    
    bot.send_message(message.chat.id, "Используй /start")

# ==================== ЗАПУСК ====================

print("=" * 40)
print("🏦 LUCKY BANK v3.0")
print("=" * 40)

bot.remove_webhook()
time.sleep(1)

db = load_db()
if not get_active_game(db):
    create_game(db)
if not get_active_fast_game(db):
    create_fast_game(db)

print("✅ БОТ ГОТОВ!")
bot.polling(none_stop=True)
