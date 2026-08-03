import telebot
from telebot import types
import json
import os
import random
import threading
import time
from datetime import datetime, timedelta

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = "8896941108:AAGtzglNGd2JoNxKKxcr3IjsneBqi_OD5Wc"
ADMIN_ID = 1075018527  # Твой Telegram ID
# ==================================================

bot = telebot.TeleBot(BOT_TOKEN)

# Файл-база данных
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
                "tickets": []
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
    
    # Таймер на завершение
    delay = duration * 3600
    threading.Timer(delay, finish_game, args=[game["id"]]).start()
    
    print(f"Игра #{game['id']} создана. Билетов: {max_t}, победителей: {winners}, длительность: {duration}ч")
    return game

def finish_game(game_id):
    db = load_db()
    game = next((g for g in db["games"] if g["id"] == game_id and g["status"] == "active"), None)
    if not game:
        return
    
    # Участники этой игры
    participants = [t for t in db["tickets"] if t["game_id"] == game_id]
    
    if participants:
        commission = db["settings"]["commission"] / 100
        ticket_price = db["settings"]["ticket_price"]
        total = len(participants) * ticket_price
        prize_pool = total * (1 - commission)
        
        # Победители
        winners_count = min(game["winners_count"], len(participants))
        winners = random.sample(participants, winners_count)
        prize_each = prize_pool / winners_count
        
        # Уведомления
        for p in participants:
            try:
                bot.send_message(p["user_id"], f"🏆 Розыгрыш #{game_id} завершён!\nПризовой фонд: {prize_pool:.1f} TON\nПобедителей: {winners_count}")
            except:
                pass
        
        for w in winners:
            try:
                bot.send_message(w["user_id"], f"🎉 Ты выиграл {prize_each:.1f} TON в Lucky Bank!")
            except:
                pass
    
    # Закрываем игру
    game["status"] = "finished"
    game["prize_pool"] = prize_pool if participants else 0.0
    db["temp_settings"] = {}
    save_db(db)
    
    # Запускаем новую игру
    create_game(db)

# ==================== КОМАНДЫ ====================

@bot.message_handler(commands=['start'])
def start(message):
    db = load_db()
    game = get_active_game(db)
    
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton("🎫 Купить билет", callback_data="buy"),
        types.InlineKeyboardButton("📊 Мои билеты", callback_data="my"),
        types.InlineKeyboardButton("🏆 Победители", callback_data="winners"),
        types.InlineKeyboardButton("📖 Правила", callback_data="rules")
    )
    
    if game:
        sold = len([t for t in db["tickets"] if t["game_id"] == game["id"]])
        end_time = datetime.strptime(game["end_time"], "%Y-%m-%d %H:%M:%S")
        remaining = end_time - datetime.now()
        hours = remaining.seconds // 3600
        minutes = (remaining.seconds % 3600) // 60
        
        text = (f"🏦 LUCKY BANK\n\n"
                f"💎 Банк: {(sold * db['settings']['ticket_price'] * 0.8):.1f} TON\n"
                f"👥 Участников: {sold}/{game['max_tickets']}\n"
                f"🎯 Победителей: {game['winners_count']}\n"
                f"⏳ До конца: {hours}ч {minutes}м")
    else:
        text = "🏦 LUCKY BANK\n\nЗапускаем первый розыгрыш..."
    
    bot.send_message(message.chat.id, text, reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    db = load_db()
    
    if call.data == "buy":
        game = get_active_game(db)
        if not game:
            bot.answer_callback_query(call.id, "Нет активной игры")
            return
        
        # Добавляем билет
        db["tickets"].append({
            "user_id": call.from_user.id,
            "username": call.from_user.username,
            "game_id": game["id"]
        })
        save_db(db)
        
        sold = len([t for t in db["tickets"] if t["game_id"] == game["id"]])
        bot.answer_callback_query(call.id, "✅ Билет куплен!")
        bot.send_message(call.message.chat.id, f"✅ Твой билет в игре #{game['id']}!\nУчастников: {sold}/{game['max_tickets']}")
        
        if sold >= game["max_tickets"]:
            finish_game(game["id"])
    
    elif call.data == "my":
        game = get_active_game(db)
        if game:
            count = len([t for t in db["tickets"] if t["game_id"] == game["id"] and t["user_id"] == call.from_user.id])
            bot.send_message(call.message.chat.id, f"📊 Твоих билетов: {count}")
    
    elif call.data == "winners":
        bot.send_message(call.message.chat.id, "🏆 Победители будут тут после розыгрыша")
    
    elif call.data == "rules":
        bot.send_message(call.message.chat.id, "📖 Купи билет → жди → выиграй TON!")

# ==================== ЗАПУСК ====================

print("=" * 40)
print("LUCKY BANK ЗАПУСКАЕТСЯ")
print("=" * 40)

db = load_db()
if not get_active_game(db):
    create_game(db)

print("БОТ ГОТОВ. ЖМИ /start В TELEGRAM")
bot.polling(none_stop=True)
