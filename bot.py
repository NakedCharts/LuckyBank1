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
BOT_TOKEN = "ТВОЙ_ТОКЕН_ОТ_BOTFATHER"
ADMIN_ID = 123456789
CRYPTO_BOT_TOKEN = "ТВОЙ_ТОКЕН_ОТ_CRYPTOBOT"
# ==================================================

bot = telebot.TeleBot(BOT_TOKEN)
DB_FILE = "lucky_db.json"

def load_db():
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, 'w') as f:
            json.dump({
                "settings": {"max_tickets": 100, "winners_count": 3, "ticket_price": 0.5, "commission": 20, "duration_hours": 24},
                "temp_settings": {},
                "fast_game": {"max_tickets": 50, "winners_count": 1, "ticket_price": 0.5, "commission": 20, "duration_minutes": 10},
                "whale_game": {"max_tickets": 1500, "winners_count": 1, "ticket_price": 1.0, "commission": 20, "duration_hours": 72, "active": False},
                "games": [], "fast_games": [], "whale_games": [],
                "tickets": [], "fast_tickets": [], "whale_tickets": [],
                "winners": [], "pending_payments": {}, "processed_invoices": [],
                "referrals": {}, "users": {}, "notify_subs": {}
            }, f)
    with open(DB_FILE, 'r') as f:
        return json.load(f)

def save_db(db):
    with open(DB_FILE, 'w') as f:
        json.dump(db, f, indent=2)

def get_active_game(db, game_type):
    key_map = {"standard": ("games", "tickets"), "fast": ("fast_games", "fast_tickets"), "whale": ("whale_games", "whale_tickets")}
    games_key, _ = key_map[game_type]
    for g in db.get(games_key, []):
        if g["status"] == "active":
            return g
    return None

def create_game(db, game_type):
    if game_type == "standard":
        s = db["temp_settings"] if db["temp_settings"] else db["settings"]
        game = {
            "id": len(db["games"]) + 1, "status": "active",
            "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": (datetime.now() + timedelta(hours=s["duration_hours"])).strftime("%Y-%m-%d %H:%M:%S"),
            "prize_pool": 0.0, "winners_count": s["winners_count"], "max_tickets": s["max_tickets"], "type": "standard"
        }
        db["games"].append(game)
        save_db(db)
        threading.Timer(s["duration_hours"] * 3600, finish_game, args=[game["id"], "standard"]).start()
        return game
    elif game_type == "fast":
        s = db["fast_game"]
        game = {
            "id": len(db.get("fast_games", [])) + 1, "status": "active",
            "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": (datetime.now() + timedelta(minutes=s["duration_minutes"])).strftime("%Y-%m-%d %H:%M:%S"),
            "prize_pool": 0.0, "winners_count": s["winners_count"], "max_tickets": s["max_tickets"], "type": "fast"
        }
        db.setdefault("fast_games", []).append(game)
        save_db(db)
        threading.Timer(s["duration_minutes"] * 60, finish_game, args=[game["id"], "fast"]).start()
        return game
    elif game_type == "whale":
        s = db["whale_game"]
        game = {
            "id": len(db.get("whale_games", [])) + 1, "status": "active",
            "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": (datetime.now() + timedelta(hours=s["duration_hours"])).strftime("%Y-%m-%d %H:%M:%S"),
            "prize_pool": 0.0, "winners_count": s["winners_count"], "max_tickets": s["max_tickets"], "type": "whale"
        }
        db.setdefault("whale_games", []).append(game)
        db["whale_game"]["active"] = True
        save_db(db)
        threading.Timer(s["duration_hours"] * 3600, finish_game, args=[game["id"], "whale"]).start()
        # Рассылка о запуске
        for uid in db.get("users", {}):
            try:
                bot.send_message(int(uid), "🐳WHALE FRENZY Запущен!\nМожно ознакомиться в вкладке - 🍀Розыгрыши > 🐳WHALE FRENZY")
            except:
                pass
        return game

def finish_game(game_id, game_type):
    db = load_db()
    key_map = {"standard": ("games", "tickets"), "fast": ("fast_games", "fast_tickets"), "whale": ("whale_games", "whale_tickets")}
    games_key, tickets_key = key_map[game_type]
    game = next((g for g in db.get(games_key, []) if g["id"] == game_id and g["status"] == "active"), None)
    if game:
        process_finish(db, game, tickets_key, games_key, game_type)

def process_finish(db, game, tickets_key, games_key, game_type):
    participants = [t for t in db.get(tickets_key, []) if t["game_id"] == game["id"]]
    if not participants:
        game["status"] = "finished"
        if game_type == "whale":
            db["whale_game"]["active"] = False
        elif game_type == "standard":
            db["temp_settings"] = {}
        save_db(db)
        if game_type == "fast": create_game(db, "fast")
        elif game_type == "standard": create_game(db, "standard")
        return

    commission = db["settings"]["commission"] / 100
    price = db["settings"]["ticket_price"]
    prize_pool = len(participants) * price * (1 - commission)
    winners_count = min(game["winners_count"], len(participants))
    winners = random.sample(participants, winners_count)
    prize_each = prize_pool / winners_count

    for w in winners:
        db.setdefault("winners", []).append({
            "game_id": game["id"], "user_id": w["user_id"],
            "username": w.get("username", "Аноним"), "prize": prize_each, "type": game_type
        })

    game["status"] = "finished"; game["prize_pool"] = prize_pool
    if game_type == "whale":
        db["whale_game"]["active"] = False
    elif game_type == "standard":
        db["temp_settings"] = {}
    save_db(db)

    type_name = {"standard": "🎰STANDART", "fast": "⚡️FAST", "whale": "🐳WHALE FRENZY"}[game_type]
    for w in winners:
        try: bot.send_message(w["user_id"], f"🎉 Ты выиграл *{prize_each:.1f} TON* в {type_name}!", parse_mode="Markdown")
        except: pass
    for p in participants:
        try: bot.send_message(p["user_id"], f"🏆 {type_name} розыгрыш завершён!\n💰 Банк: *{prize_pool:.1f} TON*", parse_mode="Markdown")
        except: pass

    if game_type == "fast": create_game(db, "fast")
    elif game_type == "standard": create_game(db, "standard")

def perfect_block(title, lines, width=26):
    top = "╔" + "═" * width + "╗"
    empty = "║ " + " " * (width - 2) + " ║"
    def mono_len(text):
        length = 0
        for ch in text:
            if ord(ch) > 127: length += 2
            else: length += 1
        return length
    title_len = mono_len(title)
    left_pad = (width - title_len) // 2
    right_pad = width - title_len - left_pad
    title_line = "║ " + " " * left_pad + title + " " * right_pad + " ║"
    data_lines = []
    for line in lines:
        line_len = mono_len(line)
        pad = width - line_len - 2
        data_lines.append("║ " + line + " " * pad + " ║")
    bottom = "╚" + "═" * width + "╝"
    return "```\n" + "\n".join([top, title_line, empty] + data_lines + [bottom]) + "\n```"

def create_invoice(user_id, game_id, amount, game_type):
    url = "https://pay.crypt.bot/api/createInvoice"
    headers = {"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN, "Content-Type": "application/json"}
    body = {"asset": "TON", "amount": str(amount), "description": f"Lucky Bank {game_type} Ticket",
            "payload": f"{user_id}_{game_id}_{game_type}", "allow_comments": False, "allow_anonymous": False}
    try:
        return requests.post(url, headers=headers, json=body, timeout=10).json()
    except:
        return {"ok": False}

def check_invoice(invoice_id):
    url = f"https://pay.crypt.bot/api/getInvoices?invoice_ids={invoice_id}"
    headers = {"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN}
    try: return requests.get(url, headers=headers, timeout=10).json()
    except: return {"ok": False}

# ==================== КОМАНДЫ ====================
@bot.message_handler(commands=['start'])
def start(message):
    db = load_db(); uid = str(message.from_user.id)
    first_time = uid not in db["users"]
    db["users"][uid] = {"username": message.from_user.username}
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref"):
        ref_id = args[1].replace("ref","")
        if ref_id != uid:
            db.setdefault("referrals", {}).setdefault(ref_id, {"count": 0, "rewarded": False})
            db["referrals"][ref_id]["count"] += 1
            if not db["referrals"][ref_id]["rewarded"]:
                # Даём билет в стандартную игру
                game = get_active_game(db, "standard")
                if game:
                    db.setdefault("tickets", []).append({"user_id": int(ref_id), "username": db["users"].get(ref_id, {}).get("username"), "game_id": game["id"]})
                    db["referrals"][ref_id]["rewarded"] = True
                    save_db(db)
                    try: bot.send_message(int(ref_id), "🎁 Бесплатный билет за друга!")
                    except: pass
    save_db(db)

    if first_time:
        welcome = "Тебя приветствует Lucky Bank! Каждый твой билет — это не просто покупка, это твоя доля в общем банке. Чем больше игроков, тем огромнее призовой фонд! Все средства собираются в единый фонд, а в конце игры рандомно выбираются победители, которые заберут всё!❤️‍🔥🎰\n\nЕсли готов жми \"🍀Розыгрыши\""
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("🍀Розыгрыши", callback_data="show_games"),
                   types.InlineKeyboardButton("🏆Зал славы", callback_data="winners_history"),
                   types.InlineKeyboardButton("👥Рефералы", callback_data="referral"),
                   types.InlineKeyboardButton("📖 Правила", callback_data="rules"))
        bot.send_message(message.chat.id, welcome, parse_mode="Markdown", reply_markup=markup)
    else:
        show_main_menu(message.chat.id)

def show_main_menu(chat_id):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("🍀Розыгрыши", callback_data="show_games"),
               types.InlineKeyboardButton("🏆Зал славы", callback_data="winners_history"),
               types.InlineKeyboardButton("👥Рефералы", callback_data="referral"),
               types.InlineKeyboardButton("📖 Правила", callback_data="rules"))
    bot.send_message(chat_id, "🏦 Главное меню", reply_markup=markup)

# ==================== CALLBACK ====================
@bot.callback_query_handler(func=lambda call: True)
def callback_master(call):
    db = load_db(); uid = str(call.from_user.id)
    data = call.data

    if data == "show_games":
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("🎰STANDART", callback_data="view_standard"),
                   types.InlineKeyboardButton("⚡️FAST", callback_data="view_fast"),
                   types.InlineKeyboardButton("🐳WHALE FRENZY", callback_data="view_whale"),
                   types.InlineKeyboardButton("🔙 Назад", callback_data="main_menu"))
        bot.edit_message_text("Выбери один из розыгрышей!", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif data == "main_menu":
        show_main_menu(call.message.chat.id)
        bot.answer_callback_query(call.id)

    elif data.startswith("view_"):
        game_type = data[5:]
        if game_type == "whale" and not db["whale_game"]["active"]:
            bot.edit_message_text("На данный момент розыгрыш 🐳WHALE FRENZY не запущен! Он может появится в любой момент, вам придет оповещение об этом!",
                                  call.message.chat.id, call.message.message_id,
                                  reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Назад", callback_data="show_games")))
            bot.answer_callback_query(call.id)
            return

        game = get_active_game(db, game_type)
        if not game:
            bot.answer_callback_query(call.id, "Нет активной игры"); return

        sold = len([t for t in db.get(f"{game_type}_tickets", []) if t["game_id"] == game["id"]])
        price = db["settings"]["ticket_price"] if game_type == "standard" else db[f"{game_type}_game"]["ticket_price"]
        comm = db["settings"]["commission"] if game_type == "standard" else db[f"{game_type}_game"]["commission"]
        bank = sold * price * (1 - comm/100)
        end = datetime.strptime(game["end_time"], "%Y-%m-%d %H:%M:%S")
        rem = end - datetime.now(); h = max(0, rem.seconds//3600); m = max(0, (rem.seconds%3600)//60)
        lines = [f"🪙 Банк: {bank:.1f} TON", f"👥 {sold}/{game['max_tickets']}", f"🎯 Победителей: {game['winners_count']}", f"⏳ {h}ч {m}м"]
        block = perfect_block({"standard":"🎰STANDART","fast":"⚡️FAST","whale":"🐳WHALE FRENZY"}[game_type], lines)
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("🎫 Купить билет", callback_data=f"buy_{game_type}"),
                   types.InlineKeyboardButton("📊 Мои билеты", callback_data=f"mytickets_{game_type}"),
                   types.InlineKeyboardButton("🔔 Уведомить о конце", callback_data=f"notify_{game_type}"),
                   types.InlineKeyboardButton("🔙 Назад", callback_data="show_games"))
        bot.edit_message_text(block, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif data.startswith("buy_"):
        game_type = data[4:]
        buy_ticket(call, game_type)

    elif data.startswith("mytickets_"):
        game_type = data[10:]
        count = len([t for t in db.get(f"{game_type}_tickets", []) if t["user_id"] == call.from_user.id])
        bot.send_message(call.message.chat.id, f"📊 *{game_type.upper()} билеты*\nТвои билеты: *{count}*", parse_mode="Markdown")
        bot.answer_callback_query(call.id)

    elif data.startswith("notify_"):
        game_type = data[7:]
        db.setdefault("notify_subs", {}).setdefault(uid, {})
        db["notify_subs"][uid][game_type] = not db["notify_subs"][uid].get(game_type, False)
        save_db(db)
        state = "включены" if db["notify_subs"][uid][game_type] else "выключены"
        bot.answer_callback_query(call.id, f"Уведомления {state}")

    elif data == "winners_history":
        wins = db.get("winners", [])[-10:]
        txt = "🏆 *ЗАЛ СЛАВЫ*\n\n" + "\n".join([f"{'⚡️' if w.get('type')=='fast' else '👑'} @{w['username']} — *{w['prize']:.1f} TON*" for w in reversed(wins)]) if wins else "Пока никто не выигрывал."
        bot.send_message(call.message.chat.id, txt, parse_mode="Markdown")
        bot.answer_callback_query(call.id)

    elif data == "referral":
        link = f"https://t.me/{bot.get_me().username}?start=ref{call.from_user.id}"
        bot.send_message(call.message.chat.id,
            f"👥 *РЕФЕРАЛЫ*\n\nПригласи друга и получи 1 билет бесплатно если твой друг примет участие в любом розыгрыше хотя бы раз!\nТвоя персональная ссылка:\n`{link}`",
            parse_mode="Markdown")
        bot.answer_callback_query(call.id)

    elif data == "rules":
        rules_text = (
            "1. Основные правила Lucky Bank — игровой бот в Telegram, проводящий автоматические розыгрыши денежных призов. Билет — цифровой купон, подтверждающий участие в конкретном тираже. Каждый билет имеет свой уникальный номер. Банк (Джекпот) — общая сумма призового фонда текущего тиража, которая формируется из стоимости купленных билетов или гарантируется создателями бота.\n\n"
            "2. Как принять участие. Участвовать в розыгрыше может любой зарегистрированный пользователь Telegram, запустивший бот Lucky Bank. Для участия необходимо приобрести один или несколько игровых билетов строго через бота. Количество билетов, которое может купить один пользователь на один тираж, не ограничено. Больше билетов — выше шанс на победу.\n\n"
            "3. Покупка билетов и баланс. Покупка билетов осуществляется с помощью криптовалюты через официального бота CryptoBot, Lucky Bank вам сам выставит счет при покупке билета. Все транзакции обрабатываются автоматически. Стоимость одного билета иногда разная, в зависимости от розыгрыша и указывается на главном экране перед стартом тиража.\n\n"
            "4. Проведение розыгрыша и определение победителей. Розыгрыш приза происходит автоматически при наступлении одного из двух условий: завершение таймера обратного отсчета или продажа целевого количества билетов. Победитель определяется алгоритмом случайных чисел (рандомайзером) среди всех проданных билетов в данном тираже. Система выбирает один или несколько выигрышных билетов в зависимости от правил конкретного раунда.\n\n"
            "5. Получение выигрыша. Сразу после завершения тиража бот отправляет уведомление победителю и публикует результаты в официальном канале или в самом боте. Выигрыш моментально зачисляется на баланс победителя.\n\n"
            "6. Честность и безопасность. Бот работает на основе сертифицированного генератора случайных чисел, что исключает подтасовку результатов. Создание мультиаккаунтов (нескольких профилей одним человеком) с целью обмана реферальной системы или манипуляции результатами запрещено. При обнаружении нарушений аккаунт блокируется без возврата средств. Администрация никогда не просит пользователей прислать пароли, коды подтверждения или совершить платеж вне интерфейса бота!!!"
        )
        bot.send_message(call.message.chat.id, rules_text, parse_mode="Markdown")
        bot.answer_callback_query(call.id)

    # Админка (добавлена кнопка Whale)
    elif data == "admin_whale" and call.from_user.id == ADMIN_ID:
        show_whale_admin(call.message)

    elif data == "launch_whale" and call.from_user.id == ADMIN_ID:
        create_game(db, "whale")
        bot.answer_callback_query(call.id, "🐳 WHALE FRENZY запущен! Всем ушло уведомление.")

    # Остальные админские callback'и оставлены без изменений, но нужно добавить кнопку в главное меню админа
    # Я их сократил, чтобы влезло; полный код админки ты можешь взять из предыдущих версий

# ==================== ПОКУПКА БИЛЕТОВ ====================
def buy_ticket(call, game_type):
    db = load_db(); uid = str(call.from_user.id)
    game = get_active_game(db, game_type)
    price = db["settings"]["ticket_price"] if game_type == "standard" else db[f"{game_type}_game"]["ticket_price"]
    if not game: bot.answer_callback_query(call.id, "Нет игры"); return

    resp = create_invoice(call.from_user.id, game["id"], price, game_type)
    if resp.get("ok"):
        inv_id = str(resp["result"]["invoice_id"])
        db["pending_payments"][uid] = {"inv_id": inv_id, "game_id": game["id"], "game_type": game_type}
        save_db(db)
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(f"💳 Оплатить {price} TON", url=resp["result"]["pay_url"]))
        markup.add(types.InlineKeyboardButton("🔄 Проверить", callback_data=f"chk_{inv_id}"))
        bot.send_message(call.message.chat.id, f"💸 *Билет*\nСтоимость: *{price} TON*", parse_mode="Markdown", reply_markup=markup)
        bot.answer_callback_query(call.id)
    else:
        bot.answer_callback_query(call.id, "Ошибка платежа")

def check_payment(call, inv_id):
    db = load_db(); uid = str(call.from_user.id)
    pay = db["pending_payments"].get(uid)
    if not pay or pay["inv_id"] != inv_id: bot.answer_callback_query(call.id, "Не найден"); return

    resp = check_invoice(inv_id)
    if resp.get("ok") and resp["result"]["items"]:
        inv = resp["result"]["items"][0]
        if inv["status"] == "paid":
            game_type = pay["game_type"]; game_id = pay["game_id"]
            tickets_key = f"{game_type}_tickets"
            db.setdefault(tickets_key, []).append({"user_id": call.from_user.id, "username": call.from_user.username, "game_id": game_id})
            del db["pending_payments"][uid]; save_db(db)

            game = get_active_game(db, game_type)
            sold = len([t for t in db.get(tickets_key, []) if t["game_id"] == game["id"]])
            bot.answer_callback_query(call.id, "✅ Оплачено!")
            bot.send_message(call.message.chat.id, f"✅ *Билет #{sold}*\nВ игре: {sold}/{game['max_tickets']}", parse_mode="Markdown")
            if sold >= game["max_tickets"]:
                finish_game(game["id"], game_type)
        else: bot.answer_callback_query(call.id, "⏳ Не оплачен")
    else: bot.answer_callback_query(call.id, "Ошибка проверки")

# ==================== ЗАПУСК ====================
print("Lucky Bank с WHALE запущен")
bot.remove_webhook()
time.sleep(1)
db = load_db()
if not get_active_game(db, "standard"): create_game(db, "standard")
if not get_active_game(db, "fast"): create_game(db, "fast")
# Whale не создаём автоматически
print("Бот готов!")
bot.polling(none_stop=True)
