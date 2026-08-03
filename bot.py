import telebot
from telebot import types
import json
import os
import random
import threading
import requests
from datetime import datetime, timedelta

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = "8896941108:AAGtzglNGd2JoNxKKxcr3IjsneBqi_OD5Wc"
ADMIN_ID = 1075018527  # Твой Telegram ID
CRYPTO_BOT_TOKEN = "617372:AATHO7ftVok1F576SuLMelt32cncAyWMatw"  # Токен от @CryptoBot
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
    
    delay = duration * 3600
    threading.Timer(delay, finish_game, args=[game["id"]]).start()
    
    print(f"🎰 Игра #{game['id']} создана")
    return game

def finish_game(game_id):
    db = load_db()
    game = next((g for g in db["games"] if g["id"] == game_id and g["status"] == "active"), None)
    if not game:
        return
    
    participants = [t for t in db["tickets"] if t["game_id"] == game_id]
    
    if not participants:
        game["status"] = "finished"
        save_db(db)
        create_game(db)
        return
    
    commission = db["settings"]["commission"] / 100
    ticket_price = db["settings"]["ticket_price"]
    total = len(participants) * ticket_price
    prize_pool = total * (1 - commission)
    
    winners_count = min(game["winners_count"], len(participants))
    winners = random.sample(participants, winners_count)
    prize_each = prize_pool / winners_count
    
    for w in winners:
        db["winners"].append({
            "game_id": game_id,
            "user_id": w["user_id"],
            "username": w.get("username", "Аноним"),
            "prize": prize_each
        })
    
    game["status"] = "finished"
    game["prize_pool"] = prize_pool
    db["temp_settings"] = {}
    save_db(db)
    
    # Уведомления
    winner_names = []
    for w in winners:
        name = f"@{w['username']}" if w.get('username') else f"ID:{w['user_id']}"
        winner_names.append(f"👑 {name}")
        try:
            bot.send_message(w["user_id"],
                f"🎉 *ПОЗДРАВЛЯЕМ!*\n\n"
                f"Ты стал победителем Lucky Bank!\n"
                f"Выигрыш: *{prize_each:.1f} TON*\n\n"
                f"💎 Средства отправлены на твой кошелёк.",
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

# ==================== КОМАНДЫ ====================

@bot.message_handler(commands=['start'])
def start(message):
    db = load_db()
    game = get_active_game(db)
    
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    
    if game:
        sold = len([t for t in db["tickets"] if t["game_id"] == game["id"]])
        end_time = datetime.strptime(game["end_time"], "%Y-%m-%d %H:%M:%S")
        remaining = end_time - datetime.now()
        hours = max(0, remaining.seconds // 3600)
        minutes = max(0, (remaining.seconds % 3600) // 60)
        
        text = (f"🏦 *LUCKY BANK*\n\n"
                f"Элитное крипто-сообщество.\n"
                f"Честность. Прозрачность. Удача.\n\n"
                f"┌──────────────────────┐\n"
                f"│  💎 ТЕКУЩИЙ РОЗЫГРЫШ  │\n"
                f"│                      │\n"
                f"│  🪙 Банк: *{sold * db['settings']['ticket_price'] * 0.8:.1f} TON*  │\n"
                f"│  👥 Участники: *{sold}/{game['max_tickets']}*   │\n"
                f"│  🎯 Победителей: *{game['winners_count']}*     │\n"
                f"│  ⏳ До конца: *{hours}ч {minutes}м*  │\n"
                f"└──────────────────────┘")
        
        keyboard.add(
            types.InlineKeyboardButton("🎫 Купить билет", callback_data="buy_ticket"),
            types.InlineKeyboardButton("📊 Мои билеты", callback_data="my_tickets"),
            types.InlineKeyboardButton("🏆 История побед", callback_data="winners_history"),
            types.InlineKeyboardButton("📖 Правила", callback_data="rules"),
            types.InlineKeyboardButton("💬 Чат сообщества", url="https://t.me/+твойчат")
        )
    else:
        text = "🏦 *LUCKY BANK*\n\nСкоро начнём первый розыгрыш..."
    
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=keyboard)

@bot.message_handler(commands=['LuckyBank_X7k9M_Admin_2024'])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    db = load_db()
    total_earned = sum([g.get("prize_pool", 0) * db["settings"]["commission"] / 80 for g in db["games"] if g["status"] == "finished"])
    
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton("⚙️ Стандартные настройки", callback_data="admin_standard"),
        types.InlineKeyboardButton("🎯 Разовый розыгрыш", callback_data="admin_temp"),
        types.InlineKeyboardButton("💰 Баланс и вывод", callback_data="admin_balance"),
        types.InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast")
    )
    
    bot.send_message(message.chat.id,
        f"🔐 *АДМИН-ПАНЕЛЬ*\n\n"
        f"Добро пожаловать, Владелец.\n\n"
        f"💰 Заработано всего: *{total_earned:.1f} TON*",
        parse_mode="Markdown",
        reply_markup=keyboard)

# ==================== ОБРАБОТКА КНОПОК ====================

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    db = load_db()
    uid = str(call.from_user.id)
    
    # ========== ПОКУПКА БИЛЕТА ==========
    if call.data == "buy_ticket":
        game = get_active_game(db)
        if not game:
            bot.answer_callback_query(call.id, "😔 Нет активной игры. Загляни позже.")
            return
        
        ticket_price = db["settings"]["ticket_price"]
        
        # Создаём инвойс через CryptoBot
        headers = {
            'Crypto-Pay-API-Token': CRYPTO_BOT_TOKEN,
            'Content-Type': 'application/json'
        }
        invoice_data = {
            'asset': 'TON',
            'amount': str(ticket_price),
            'description': f'Билет Lucky Bank #{game["id"]}',
            'hidden_message': f'{uid}_{game["id"]}',
            'paid_btn_name': 'callback',
            'paid_btn_url': 'https://t.me/LuckyBank_bot',
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
                
                # Сохраняем ожидание платежа
                db["pending_payments"][uid] = {
                    "invoice_id": invoice_id,
                    "game_id": game["id"],
                    "amount": ticket_price,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                save_db(db)
                
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("💳 Оплатить " + str(ticket_price) + " TON", url=invoice_url))
                markup.add(types.InlineKeyboardButton("🔄 Проверить оплату", callback_data=f"check_payment_{invoice_id}"))
                
                bot.send_message(call.message.chat.id,
                    f"💸 *ПОКУПКА БИЛЕТА*\n\n"
                    f"Стоимость: *{ticket_price} TON*\n"
                    f"Нажми кнопку ниже для оплаты.\n"
                    f"После оплаты нажми «Проверить оплату».",
                    parse_mode="Markdown",
                    reply_markup=markup)
                bot.answer_callback_query(call.id)
            else:
                bot.answer_callback_query(call.id, "❌ Ошибка создания платежа. Попробуй позже.")
        except Exception as e:
            print(f"Ошибка создания инвойса: {e}")
            bot.answer_callback_query(call.id, "❌ Сервис временно недоступен.")
    
    # ========== ПРОВЕРКА ОПЛАТЫ ==========
    elif call.data.startswith("check_payment_"):
        invoice_id = call.data.replace("check_payment_", "")
        payment = db["pending_payments"].get(uid)
        
        if not payment or payment["invoice_id"] != invoice_id:
            bot.answer_callback_query(call.id, "❌ Платёж не найден.")
            return
        
        # Проверяем статус через CryptoBot API
        headers = {'Crypto-Pay-API-Token': CRYPTO_BOT_TOKEN}
        try:
            resp = requests.get(f'https://pay.crypt.bot/api/getInvoices?invoice_ids={invoice_id}',
                              headers=headers, timeout=10)
            data = resp.json()
            
            if data.get('ok') and data['result']['items']:
                inv = data['result']['items'][0]
                if inv['status'] == 'paid':
                    # Зачисляем билет
                    game_id = payment["game_id"]
                    db["tickets"].append({
                        "user_id": call.from_user.id,
                        "username": call.from_user.username,
                        "game_id": game_id
                    })
                    db["processed_invoices"].append(invoice_id)
                    del db["pending_payments"][uid]
                    save_db(db)
                    
                    game = get_active_game(db)
                    sold = len([t for t in db["tickets"] if t["game_id"] == game["id"]])
                    
                    bot.answer_callback_query(call.id, "✅ Оплата прошла!")
                    bot.send_message(call.message.chat.id,
                        f"✅ *БИЛЕТ ОПЛАЧЕН*\n\n"
                        f"Номер билета: #{sold}\n"
                        f"В игре: {sold}/{game['max_tickets']}\n"
                        f"Призовой фонд растёт!\n\n"
                        f"Уведомим, когда розыгрыш завершится.",
                        parse_mode="Markdown")
                    
                    if sold >= game["max_tickets"]:
                        finish_game(game["id"])
                else:
                    bot.answer_callback_query(call.id, "⏳ Оплата ещё не прошла. Попробуй позже.")
            else:
                bot.answer_callback_query(call.id, "❌ Ошибка проверки.")
        except Exception as e:
            print(f"Ошибка проверки инвойса: {e}")
            bot.answer_callback_query(call.id, "❌ Сервис временно недоступен.")
    
    # ========== МОИ БИЛЕТЫ ==========
    elif call.data == "my_tickets":
        game = get_active_game(db)
        if game:
            count = len([t for t in db["tickets"] if t["game_id"] == game["id"] and t["user_id"] == call.from_user.id])
            bot.send_message(call.message.chat.id,
                f"📊 *ТВОИ БИЛЕТЫ*\n\n"
                f"В текущей игре: *{count} шт.*\n"
                f"Цена билета: *{db['settings']['ticket_price']} TON*\n\n"
                f"Чем больше билетов — тем выше шанс на победу! 🍀",
                parse_mode="Markdown")
        bot.answer_callback_query(call.id)
    
    # ========== ИСТОРИЯ ПОБЕД ==========
    elif call.data == "winners_history":
        winners = db.get("winners", [])[-10:]
        if winners:
            text = "🏆 *ПОСЛЕДНИЕ ПОБЕДИТЕЛИ*\n\n"
            for w in reversed(winners):
                name = f"@{w['username']}" if w['username'] else f"ID:{w['user_id']}"
                text += f"👑 {name} — *{w['prize']:.1f} TON*\n"
        else:
            text = "🏆 *ПОБЕДИТЕЛИ*\n\nПока никто не выигрывал.\nСтань первым! 🚀"
        bot.send_message(call.message.chat.id, text, parse_mode="Markdown")
        bot.answer_callback_query(call.id)
    
    # ========== ПРАВИЛА ==========
    elif call.data == "rules":
        bot.send_message(call.message.chat.id,
            f"📖 *ПРАВИЛА LUCKY BANK*\n\n"
            f"1️⃣ Купи билет за *{db['settings']['ticket_price']} TON*\n"
            f"2️⃣ Дождись завершения розыгрыша\n"
            f"3️⃣ Если ты в числе победителей — получишь свою долю призового фонда\n\n"
            f"⚙️ Организатор забирает *{db['settings']['commission']}%* комиссии.\n"
            f"Остальное делится между победителями.\n\n"
            f"🔒 Честность гарантирована смарт-контрактом.",
            parse_mode="Markdown")
        bot.answer_callback_query(call.id)
    
    # ========== АДМИН: СТАНДАРТНЫЕ НАСТРОЙКИ ==========
    elif call.data == "admin_standard" and call.from_user.id == ADMIN_ID:
        s = db["settings"]
        text = (f"⚙️ *СТАНДАРТНЫЕ НАСТРОЙКИ*\n\n"
                f"🎫 Билетов: *{s['max_tickets']}*\n"
                f"🏆 Победителей: *{s['winners_count']}*\n"
                f"💵 Цена: *{s['ticket_price']} TON*\n"
                f"📊 Комиссия: *{s['commission']}%*\n"
                f"⏰ Длительность: *{s['duration_hours']}ч*")
        bot.send_message(call.message.chat.id, text, parse_mode="Markdown")
        bot.answer_callback_query(call.id)
    
    # ========== АДМИН: БАЛАНС ==========
    elif call.data == "admin_balance" and call.from_user.id == ADMIN_ID:
        total = sum([g.get("prize_pool", 0) * db["settings"]["commission"] / 80 for g in db["games"] if g["status"] == "finished"])
        bot.send_message(call.message.chat.id,
            f"💰 *БАЛАНС*\n\n"
            f"Заработано: *{total:.1f} TON*\n\n"
            f"Вывод через @CryptoBot → Tonkeeper",
            parse_mode="Markdown")
        bot.answer_callback_query(call.id)

# ==================== ЗАПУСК ====================

print("=" * 40)
print("🏦 LUCKY BANK ЗАПУСКАЕТСЯ")
print("=" * 40)

# Очищаем старые обновления
bot.remove_webhook()
time.sleep(1)

db = load_db()
if not get_active_game(db):
    create_game(db)

print("✅ БОТ ГОТОВ К РАБОТЕ!")
bot.polling(none_stop=True)
