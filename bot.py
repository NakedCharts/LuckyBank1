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
                "games": [],
                "tickets": [],
                "winners": [],
                "pending_payments": {},
                "processed_invoices": []
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

def create_game(db):
    settings = db["temp_settings"] if db["temp_settings"] else db["settings"]
    max_t = settings["max_tickets"]
    winners = settings["winners_count"]
    duration = settings["duration_hours"]
    
    start_time = datetime.now()
    end_time = start_time + timedelta(hours=duration)
    
    game = {
        "id": len(db["games"]) + 1,
        "status": "active",
        "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
        "end_time": end_time.strftime("%Y-%m-%d %H:%M:%S"),
        "prize_pool": 0.0,
        "winners_count": winners,
        "max_tickets": max_t
    }
    db["games"].append(game)
    save_db(db)
    
    threading.Timer(duration * 3600, finish_game, args=[game["id"]]).start()
    return game

def finish_game(game_id):
    db = load_db()
    game = next((g for g in db["games"] if g["id"] == game_id and g["status"] == "active"), None)
    if not game:
        return
    
    participants = [t for t in db["tickets"] if t["game_id"] == game_id]
    
    if not participants:
        game["status"] = "finished"
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
        db["winners"].append({
            "game_id": game_id, "user_id": w["user_id"],
            "username": w.get("username", "Аноним"), "prize": prize_each
        })
    
    game["status"] = "finished"
    game["prize_pool"] = prize_pool
    db["temp_settings"] = {}
    save_db(db)
    
    winner_names = []
    for w in winners:
        name = f"@{w['username']}" if w.get('username') else f"ID:{w['user_id']}"
        winner_names.append(f"👑 {name}")
        try:
            bot.send_message(w["user_id"],
                f"🎉 *ПОЗДРАВЛЯЕМ!*\n\nТы выиграл *{prize_each:.1f} TON* в Lucky Bank!",
                parse_mode="Markdown")
        except:
            pass
    
    winners_text = "\n".join(winner_names)
    for p in participants:
        try:
            bot.send_message(p["user_id"],
                f"🏆 *РОЗЫГРЫШ #{game_id} ЗАВЕРШЁН*\n\n"
                f"👥 Участников: {len(participants)}\n"
                f"💰 Призовой фонд: *{prize_pool:.1f} TON*\n\n"
                f"*Победители:*\n{winners_text}\n\n"
                f"🏦 Новый розыгрыш уже стартовал!",
                parse_mode="Markdown")
        except:
            pass
    
    create_game(db)

def format_block(text, width=24):
    """Рисует красивый блок с ровными краями"""
    lines = text.strip().split('\n')
    result = ["╔" + "═" * width + "╗"]
    for line in lines:
        clean = line.strip()
        if clean:
            # Считаем длину без emoji (они занимают 2 символа)
            visual_len = 0
            for char in clean:
                if ord(char) > 127:
                    visual_len += 2
                else:
                    visual_len += 1
            padding = width - visual_len - 1
            result.append("║ " + clean + " " * max(0, padding) + "║")
    result.append("╚" + "═" * width + "╝")
    return "\n".join(result)

# Словарь состояний админа
admin_states = {}

# ==================== КОМАНДЫ ====================

@bot.message_handler(commands=['start'])
def start(message):
    db = load_db()
    game = get_active_game(db)
    
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    
    if game:
        sold = len([t for t in db["tickets"] if t["game_id"] == game["id"]])
        bank = sold * db["settings"]["ticket_price"] * (1 - db["settings"]["commission"] / 100)
        end_time = datetime.strptime(game["end_time"], "%Y-%m-%d %H:%M:%S")
        remaining = end_time - datetime.now()
        hours = max(0, remaining.seconds // 3600)
        minutes = max(0, (remaining.seconds % 3600) // 60)
        
        block = (
            f"💎 Lucky Bank\n\n"
            f"🪙 Банк: {bank:.1f} TON\n"
            f"👥 Участники: {sold}/{game['max_tickets']}\n"
            f"🎯 Победители: {game['winners_count']}\n"
            f"⏳ До конца: {hours}ч {minutes}м"
        )
        
        text = f"🏦 *LUCKY BANK*\n\nЭлитное крипто-сообщество.\nЧестность. Прозрачность. Удача.\n\n{format_block(block)}"
        
        keyboard.add(
            types.InlineKeyboardButton("🎫 Купить билет", callback_data="buy_ticket"),
            types.InlineKeyboardButton("📊 Мои билеты", callback_data="my_tickets"),
            types.InlineKeyboardButton("🏆 История побед", callback_data="winners_history"),
            types.InlineKeyboardButton("📖 Правила", callback_data="rules")
        )
    else:
        text = "🏦 *LUCKY BANK*\n\nСкоро начнём..."
    
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=keyboard)

@bot.message_handler(commands=['LuckyBank_X7k9M_Admin_2024'])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        return
    show_admin_main(message.chat.id)

def show_admin_main(chat_id):
    db = load_db()
    total_earned = sum([g.get("prize_pool", 0) * db["settings"]["commission"] / 80 for g in db["games"] if g["status"] == "finished"])
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("⚙️ Стандартные настройки", callback_data="admin_standard"),
        types.InlineKeyboardButton("🎯 Разовый розыгрыш", callback_data="admin_temp"),
        types.InlineKeyboardButton("💰 Баланс и вывод", callback_data="admin_balance"),
        types.InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast"),
        types.InlineKeyboardButton("🚪 Выйти", callback_data="admin_exit")
    )
    
    bot.send_message(chat_id,
        f"🔐 *АДМИН-ПАНЕЛЬ*\n\nДобро пожаловать, Владелец.\n💰 Заработано: *{total_earned:.1f} TON*",
        parse_mode="Markdown", reply_markup=markup)

# ==================== ОБРАБОТКА КНОПОК ====================

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    db = load_db()
    uid = str(call.from_user.id)
    
    # ПОКУПКА БИЛЕТА
    if call.data == "buy_ticket":
        game = get_active_game(db)
        if not game:
            bot.answer_callback_query(call.id, "😔 Нет активной игры.")
            return
        
        ticket_price = db["settings"]["ticket_price"]
        
        headers = {'Crypto-Pay-API-Token': CRYPTO_BOT_TOKEN, 'Content-Type': 'application/json'}
        invoice_data = {
            'asset': 'TON',  # <-- ИСПРАВЛЕНО: GRAM → TON
            'amount': str(ticket_price),
            'description': f'Lucky Bank Ticket #{game["id"]}',
            'payload': f'{uid}_{game["id"]}',
            'allow_comments': False,
            'allow_anonymous': False
        }
        
        try:
            resp = requests.post('https://pay.crypt.bot/api/createInvoice',
                                headers=headers, json=invoice_data, timeout=10)
            data = resp.json()
            
            if data.get('ok'):
                invoice_url = data['result']['pay_url']
                invoice_id = str(data['result']['invoice_id'])
                
                db["pending_payments"][uid] = {
                    "invoice_id": invoice_id, "game_id": game["id"],
                    "amount": ticket_price, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                save_db(db)
                
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton(f"💳 Оплатить {ticket_price} TON", url=invoice_url))
                markup.add(types.InlineKeyboardButton("🔄 Проверить оплату", callback_data=f"check_{invoice_id}"))
                
                bot.send_message(call.message.chat.id,
                    f"💸 *ПОКУПКА БИЛЕТА*\n\nСтоимость: *{ticket_price} TON*\nНажми кнопку ниже.",
                    parse_mode="Markdown", reply_markup=markup)
                bot.answer_callback_query(call.id)
            else:
                bot.answer_callback_query(call.id, "❌ Ошибка платежа.")
        except:
            bot.answer_callback_query(call.id, "❌ Сервис недоступен.")
    
    # ПРОВЕРКА ОПЛАТЫ
    elif call.data.startswith("check_"):
        invoice_id = call.data.replace("check_", "")
        payment = db["pending_payments"].get(uid)
        
        if not payment or payment["invoice_id"] != invoice_id:
            bot.answer_callback_query(call.id, "❌ Платёж не найден.")
            return
        
        headers = {'Crypto-Pay-API-Token': CRYPTO_BOT_TOKEN}
        try:
            resp = requests.get(f'https://pay.crypt.bot/api/getInvoices?invoice_ids={invoice_id}',
                              headers=headers, timeout=10)
            data = resp.json()
            
            if data.get('ok') and data['result']['items']:
                inv = data['result']['items'][0]
                if inv['status'] == 'paid':
                    game_id = payment["game_id"]
                    db["tickets"].append({"user_id": call.from_user.id, "username": call.from_user.username, "game_id": game_id})
                    db["processed_invoices"].append(invoice_id)
                    del db["pending_payments"][uid]
                    save_db(db)
                    
                    game = get_active_game(db)
                    sold = len([t for t in db["tickets"] if t["game_id"] == game["id"]])
                    
                    bot.answer_callback_query(call.id, "✅ Оплата прошла!")
                    bot.send_message(call.message.chat.id,
                        f"✅ *БИЛЕТ ОПЛАЧЕН*\n\nНомер: #{sold}\nВ игре: {sold}/{game['max_tickets']}\n\nУведомим о розыгрыше!",
                        parse_mode="Markdown")
                    
                    if sold >= game["max_tickets"]:
                        finish_game(game["id"])
                else:
                    bot.answer_callback_query(call.id, "⏳ Ещё не оплачен.")
        except:
            bot.answer_callback_query(call.id, "❌ Ошибка проверки.")
    
    # МОИ БИЛЕТЫ
    elif call.data == "my_tickets":
        game = get_active_game(db)
        if game:
            count = len([t for t in db["tickets"] if t["game_id"] == game["id"] and t["user_id"] == call.from_user.id])
            bot.send_message(call.message.chat.id,
                f"📊 *ТВОИ БИЛЕТЫ*\n\nВ игре: *{count} шт.*\nЦена: *{db['settings']['ticket_price']} TON*",
                parse_mode="Markdown")
        bot.answer_callback_query(call.id)
    
    # ИСТОРИЯ ПОБЕД
    elif call.data == "winners_history":
        winners = db.get("winners", [])[-10:]
        if winners:
            text = "🏆 *ПОБЕДИТЕЛИ*\n\n"
            for w in reversed(winners):
                name = f"@{w['username']}" if w['username'] else f"ID:{w['user_id']}"
                text += f"👑 {name} — *{w['prize']:.1f} TON*\n"
        else:
            text = "🏆 *ПОБЕДИТЕЛИ*\n\nПока никто не выигрывал. Стань первым! 🚀"
        bot.send_message(call.message.chat.id, text, parse_mode="Markdown")
        bot.answer_callback_query(call.id)
    
    # ПРАВИЛА
    elif call.data == "rules":
        bot.send_message(call.message.chat.id,
            f"📖 *ПРАВИЛА*\n\n1️⃣ Купи билет\n2️⃣ Жди розыгрыш\n3️⃣ Выиграй TON\n\nКомиссия: *{db['settings']['commission']}%*",
            parse_mode="Markdown")
        bot.answer_callback_query(call.id)
    
    # ========== АДМИН-КНОПКИ ==========
    
    elif call.data == "admin_standard" and call.from_user.id == ADMIN_ID:
        show_standard_settings(call.message.chat.id, call.message.message_id)
    
    elif call.data == "admin_temp" and call.from_user.id == ADMIN_ID:
        show_temp_settings(call.message.chat.id, call.message.message_id)
    
    elif call.data == "admin_balance" and call.from_user.id == ADMIN_ID:
        total = sum([g.get("prize_pool", 0) * db["settings"]["commission"] / 80 for g in db["games"] if g["status"] == "finished"])
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="admin_back"))
        bot.edit_message_text(f"💰 *БАЛАНС*\n\nЗаработано: *{total:.1f} TON*\nВывод: @CryptoBot → Tonkeeper",
            call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
    
    elif call.data == "admin_broadcast" and call.from_user.id == ADMIN_ID:
        admin_states[uid] = {"broadcast": True}
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Отмена", callback_data="admin_back"))
        bot.edit_message_text("📢 Введи сообщение для рассылки:",
            call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    elif call.data == "admin_back" and call.from_user.id == ADMIN_ID:
        db = load_db()
        total_earned = sum([g.get("prize_pool", 0) * db["settings"]["commission"] / 80 for g in db["games"] if g["status"] == "finished"])
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("⚙️ Стандартные настройки", callback_data="admin_standard"),
            types.InlineKeyboardButton("🎯 Разовый розыгрыш", callback_data="admin_temp"),
            types.InlineKeyboardButton("💰 Баланс и вывод", callback_data="admin_balance"),
            types.InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast"),
            types.InlineKeyboardButton("🚪 Выйти", callback_data="admin_exit")
        )
        bot.edit_message_text(
            f"🔐 *АДМИН-ПАНЕЛЬ*\n\n💰 Заработано: *{total_earned:.1f} TON*",
            call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
    
    elif call.data == "admin_exit" and call.from_user.id == ADMIN_ID:
        if uid in admin_states:
            del admin_states[uid]
        bot.delete_message(call.message.chat.id, call.message.message_id)
    
    # РЕДАКТИРОВАНИЕ СТАНДАРТНЫХ НАСТРОЕК
    elif call.data.startswith("edit_") and call.from_user.id == ADMIN_ID:
        param = call.data.replace("edit_", "")
        admin_states[uid] = {"editing": param}
        param_names = {"tickets": "билетов", "winners": "победителей", "price": "цена (TON)", "commission": "комиссия (%)", "duration": "длительность (часов)"}
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="admin_standard"))
        bot.edit_message_text(
            f"Введи новое значение: *{param_names.get(param, param)}*\nТекущее: *{db['settings'].get(param, '—')}*",
            call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
    
    # РЕДАКТИРОВАНИЕ РАЗОВЫХ НАСТРОЕК
    elif call.data.startswith("temp_") and call.from_user.id == ADMIN_ID:
        action = call.data.replace("temp_", "")
        
        if action == "apply":
            if db["temp_settings"]:
                bot.answer_callback_query(call.id, "✅ Применено! Следующая игра — по новым правилам.")
            else:
                bot.answer_callback_query(call.id, "ℹ️ Изменений нет. Игра по стандарту.")
        
        elif action == "reset":
            db["temp_settings"] = {}
            save_db(db)
            show_temp_settings(call.message.chat.id, call.message.message_id)
            bot.answer_callback_query(call.id, "🔄 Сброшено!")
        
        elif action in ["tickets", "winners", "price", "duration"]:
            admin_states[uid] = {"editing_temp": action}
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="admin_temp"))
            bot.edit_message_text(f"Введи значение для *{action}*:",
                call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

def show_standard_settings(chat_id, msg_id=None):
    db = load_db()
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
    if msg_id:
        bot.edit_message_text("⚙️ *СТАНДАРТНЫЕ НАСТРОЙКИ*", chat_id, msg_id, parse_mode="Markdown", reply_markup=markup)
    else:
        bot.send_message(chat_id, "⚙️ *СТАНДАРТНЫЕ НАСТРОЙКИ*", parse_mode="Markdown", reply_markup=markup)

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

# ==================== ТЕКСТОВЫЕ СООБЩЕНИЯ ====================

@bot.message_handler(func=lambda m: True)
def text_handler(message):
    uid = str(message.from_user.id)
    
    if uid in admin_states and message.from_user.id == ADMIN_ID:
        state = admin_states[uid]
        
        # Рассылка
        if state.get("broadcast"):
            db = load_db()
            users = set()
            for t in db["tickets"]:
                users.add(t["user_id"])
            count = 0
            for u in users:
                try:
                    bot.send_message(u, message.text)
                    count += 1
                except:
                    pass
            bot.send_message(message.chat.id, f"📢 Отправлено {count} чел.")
            del admin_states[uid]
            show_admin_main(message.chat.id)
            return
        
        # Редактирование стандартных
        if state.get("editing"):
            param = state["editing"]
            try:
                val = float(message.text) if param in ["price", "commission"] else int(message.text)
                db = load_db()
                db["settings"][param] = val
                save_db(db)
                del admin_states[uid]
                show_standard_settings(message.chat.id)
            except:
                bot.send_message(message.chat.id, "❌ Неверное число.")
            return
        
        # Редактирование разовых
        if state.get("editing_temp"):
            param = state["editing_temp"]
            try:
                val = float(message.text) if param == "price" else int(message.text)
                db = load_db()
                if "temp_settings" not in db:
                    db["temp_settings"] = {}
                db["temp_settings"][param] = val
                save_db(db)
                del admin_states[uid]
                show_temp_settings(message.chat.id)
            except:
                bot.send_message(message.chat.id, "❌ Неверное число.")
            return
    
    bot.send_message(message.chat.id, "Используй кнопки меню. /start")

# ==================== ЗАПУСК ====================

print("=" * 40)
print("🏦 LUCKY BANK")
print("=" * 40)

bot.remove_webhook()
time.sleep(1)

db = load_db()
if not get_active_game(db):
    create_game(db)

print("✅ ГОТОВ!")
bot.polling(none_stop=True)
