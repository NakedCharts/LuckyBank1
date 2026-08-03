import telebot
from telebot import types
import json
import os
import random
import threading
import requests
import time
from datetime import datetime, timedelta

# ==================== НАСТРОЙКИ (ЗАМЕНИ ЭТО) ====================
BOT_TOKEN = "8896941108:AAGtzglNGd2JoNxKKxcr3IjsneBqi_OD5Wc"
ADMIN_ID = 1075018527  # Твой Telegram ID
CRYPTO_BOT_TOKEN = "617372:AATHO7ftVok1F576SuLMelt32cncAyWMatw"
# =================================================================

bot = telebot.TeleBot(BOT_TOKEN)
DB_FILE = "lucky_db.json"

def load_db():
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, 'w') as f:
            json.dump({
                "settings": {"max_tickets": 100, "winners_count": 3, "ticket_price": 0.5, "commission": 20, "duration_hours": 24},
                "temp_settings": {},
                "fast_game": {"max_tickets": 50, "winners_count": 1, "ticket_price": 0.5, "commission": 20, "duration_minutes": 10},
                "games": [], "fast_games": [], "tickets": [], "fast_tickets": [],
                "winners": [], "pending_payments": {}, "processed_invoices": [], "referrals": {}, "users": {}
            }, f)
    with open(DB_FILE, 'r') as f:
        return json.load(f)

def save_db(db):
    with open(DB_FILE, 'w') as f:
        json.dump(db, f, indent=2)

def get_active_game(db):
    for g in db["games"]:
        if g["status"] == "active": return g
    return None

def get_active_fast_game(db):
    for g in db.get("fast_games", []):
        if g["status"] == "active": return g
    return None

def create_game(db):
    s = db["temp_settings"] if db["temp_settings"] else db["settings"]
    game = {
        "id": len(db["games"]) + 1, "status": "active",
        "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "end_time": (datetime.now() + timedelta(hours=s["duration_hours"])).strftime("%Y-%m-%d %H:%M:%S"),
        "prize_pool": 0.0, "winners_count": s["winners_count"], "max_tickets": s["max_tickets"], "type": "standard"
    }
    db["games"].append(game)
    save_db(db)
    threading.Timer(s["duration_hours"] * 3600, finish_game, args=[game["id"]]).start()
    return game

def create_fast_game(db):
    s = db["fast_game"]
    game = {
        "id": len(db.get("fast_games", [])) + 1, "status": "active",
        "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "end_time": (datetime.now() + timedelta(minutes=s["duration_minutes"])).strftime("%Y-%m-%d %H:%M:%S"),
        "prize_pool": 0.0, "winners_count": 1, "max_tickets": s["max_tickets"], "type": "fast"
    }
    db.setdefault("fast_games", []).append(game)
    save_db(db)
    threading.Timer(s["duration_minutes"] * 60, finish_fast_game, args=[game["id"]]).start()
    return game

def process_finish(db, game, tickets_key, games_key):
    participants = [t for t in db.get(tickets_key, []) if t["game_id"] == game["id"]]
    if not participants:
        game["status"] = "finished"
        save_db(db)
        if game["type"] == "fast": create_fast_game(db)
        else:
            db["temp_settings"] = {}
            save_db(db)
            create_game(db)
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
            "username": w.get("username", "Аноним"), "prize": prize_each, "type": game["type"]
        })

    game["status"] = "finished"; game["prize_pool"] = prize_pool
    if game["type"] != "fast": db["temp_settings"] = {}
    save_db(db)

    tname = "⚡️БЫСТРЫЙ" if game["type"] == "fast" else "🏆СТАНДАРТНЫЙ"
    for w in winners:
        try: bot.send_message(w["user_id"], f"🎉 Ты выиграл *{prize_each:.1f} TON* в {tname} розыгрыше!", parse_mode="Markdown")
        except: pass
    for p in participants:
        try: bot.send_message(p["user_id"], f"{tname} розыгрыш #{game['id']} завершён!\n💰 Банк: *{prize_pool:.1f} TON*", parse_mode="Markdown")
        except: pass

    if game["type"] == "fast": create_fast_game(db)
    else: create_game(db)

def finish_game(game_id):
    db = load_db()
    game = next((g for g in db["games"] if g["id"] == game_id and g["status"] == "active"), None)
    if game: process_finish(db, game, "tickets", "games")

def finish_fast_game(game_id):
    db = load_db()
    game = next((g for g in db.get("fast_games", []) if g["id"] == game_id and g["status"] == "active"), None)
    if game: process_finish(db, game, "fast_tickets", "fast_games")

# ИДЕАЛЬНАЯ РАМКА
def perfect_block(title, lines):
    w = 26
    res = ["╔" + "═" * w + "╗"]
    res.append("║ " + title.center(w - 2) + " ║")
    res.append("║" + " " * w + "║")
    for line in lines:
        clean = line.replace("*","").replace("_","").replace("`","")
        length = sum(2 if ord(c) > 127 else 1 for c in clean)
        pad = max(0, w - length - 2)
        res.append("║ " + line + " " * pad + "║")
    res.append("╚" + "═" * w + "╝")
    return "\n".join(res)

def create_invoice(user_id, game_id, amount, game_type):
    url = "https://pay.crypt.bot/api/createInvoice"
    headers = {"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN, "Content-Type": "application/json"}
    body = {"asset": "TON", "amount": str(amount), "description": f"Lucky Bank {game_type} Ticket",
            "payload": f"{user_id}_{game_id}_{game_type}", "allow_comments": False, "allow_anonymous": False}
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=10).json()
        # Отправляем ответ API админу для диагностики
        if ADMIN_ID:
            try: bot.send_message(ADMIN_ID, f"🔍 Invoice Response:\n{json.dumps(resp, indent=2)}")
            except: pass
        return resp
    except Exception as e:
        return {"ok": False, "error": str(e)}

def check_invoice(invoice_id):
    url = f"https://pay.crypt.bot/api/getInvoices?invoice_ids={invoice_id}"
    headers = {"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN}
    try: return requests.get(url, headers=headers, timeout=10).json()
    except: return {"ok": False}

# ==================== КОМАНДЫ ====================
@bot.message_handler(commands=['start'])
def start(message):
    db = load_db(); uid = str(message.from_user.id)
    db["users"][uid] = {"username": message.from_user.username}
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref"):
        ref_id = args[1].replace("ref","")
        if ref_id != uid:
            game = get_active_game(db)
            if game:
                db.setdefault("tickets", []).append({"user_id": int(ref_id), "username": db.get("users",{}).get(ref_id,{}).get("username"), "game_id": game["id"]})
                save_db(db)
                try: bot.send_message(int(ref_id), "🎁 Бесплатный билет за друга!")
                except: pass
    save_db(db)

    game = get_active_game(db); fast = get_active_fast_game(db)
    markup = types.InlineKeyboardMarkup(row_width=1)
    txt = "🏦 *LUCKY BANK*\n\n"

    if game:
        sold = len([t for t in db.get("tickets",[]) if t["game_id"]==game["id"]])
        bank = sold * db["settings"]["ticket_price"] * (1 - db["settings"]["commission"]/100)
        end = datetime.strptime(game["end_time"],"%Y-%m-%d %H:%M:%S")
        rem = end - datetime.now(); h = max(0, rem.seconds//3600); m = max(0, (rem.seconds%3600)//60)
        lines = [f"🪙 Банк: {bank:.1f} TON", f"👥 {sold}/{game['max_tickets']}", f"🎯 Победителей: {game['winners_count']}", f"⏳ {h}ч {m}м"]
        txt += perfect_block("💎 СТАНДАРТ", lines)
        markup.add(types.InlineKeyboardButton("🎫 Купить (Стандарт)", callback_data="buy_standard"))

    if fast:
        sold_f = len([t for t in db.get("fast_tickets",[]) if t["game_id"]==fast["id"]])
        bank_f = sold_f * db["fast_game"]["ticket_price"] * (1 - db["fast_game"]["commission"]/100)
        end_f = datetime.strptime(fast["end_time"],"%Y-%m-%d %H:%M:%S")
        rem_f = end_f - datetime.now(); mins = max(0, rem_f.seconds//60)
        lines_f = [f"🪙 Банк: {bank_f:.1f} TON", f"👥 {sold_f}/{fast['max_tickets']}", f"🎯 Победитель: 1", f"⏳ {mins}м"]
        txt += perfect_block("⚡️ БЫСТРЫЙ", lines_f)
        markup.add(types.InlineKeyboardButton("⚡️ Купить (Быстрый)", callback_data="buy_fast"))

    markup.add(types.InlineKeyboardButton("📊 Мои билеты", callback_data="my_tickets"),
               types.InlineKeyboardButton("🏆 Зал славы", callback_data="winners_history"),
               types.InlineKeyboardButton("👥 Рефералы", callback_data="referral"),
               types.InlineKeyboardButton("📖 Правила", callback_data="rules"))
    bot.send_message(message.chat.id, txt, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(commands=['LuckyBank_X7k9M_Admin_2024'])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID: return
    show_admin_main(message.chat.id)

def show_admin_main(chat_id):
    db = load_db()
    total = sum([g.get("prize_pool",0)*db["settings"]["commission"]/80 for g in db["games"] if g["status"]=="finished"])
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("⚙️ Стандартные настройки", callback_data="adm_std"),
               types.InlineKeyboardButton("🎯 Разовый розыгрыш", callback_data="adm_temp"),
               types.InlineKeyboardButton("⚡️ Быстрый розыгрыш", callback_data="adm_fast"),
               types.InlineKeyboardButton("💰 Баланс", callback_data="adm_bal"),
               types.InlineKeyboardButton("📢 Рассылка", callback_data="adm_broad"),
               types.InlineKeyboardButton("🚪 Выйти", callback_data="adm_exit"))
    bot.send_message(chat_id, f"🔐 *АДМИН-ПАНЕЛЬ*\n💰 Заработано: *{total:.1f} TON*", parse_mode="Markdown", reply_markup=markup)

# ==================== УНИВЕРСАЛЬНЫЙ CALLBACK ====================
admin_input_state = {}

@bot.callback_query_handler(func=lambda call: True)
def callback_master(call):
    db = load_db(); uid = str(call.from_user.id)
    data = call.data

    # --- Покупки и проверка ---
    if data == "buy_standard": buy_ticket(call, "standard")
    elif data == "buy_fast": buy_ticket(call, "fast")
    elif data.startswith("chk_"): check_payment(call, data[4:])
    elif data == "my_tickets":
        std = len([t for t in db.get("tickets",[]) if t["user_id"]==call.from_user.id])
        fast = len([t for t in db.get("fast_tickets",[]) if t["user_id"]==call.from_user.id])
        bot.send_message(call.message.chat.id, f"📊 *Билеты*\n🎫 Стандарт: *{std}*\n⚡️ Быстрый: *{fast}*", parse_mode="Markdown")
        bot.answer_callback_query(call.id)
    elif data == "winners_history":
        wins = db.get("winners",[])[-10:]
        txt = "🏆 *ЗАЛ СЛАВЫ*\n\n" + "\n".join([f"{'⚡️' if w.get('type')=='fast' else '👑'} @{w['username']} — *{w['prize']:.1f} TON*" for w in reversed(wins)]) if wins else "Пока никто не выигрывал."
        bot.send_message(call.message.chat.id, txt, parse_mode="Markdown")
        bot.answer_callback_query(call.id)
    elif data == "referral":
        link = f"https://t.me/{bot.get_me().username}?start=ref{call.from_user.id}"
        bot.send_message(call.message.chat.id, f"👥 *Рефералы*\n🔗 `{link}`", parse_mode="Markdown")
        bot.answer_callback_query(call.id)
    elif data == "rules":
        bot.send_message(call.message.chat.id, f"📖 *Правила*\nСтандарт: {db['settings']['max_tickets']} бил., {db['settings']['duration_hours']}ч\nБыстрый: {db['fast_game']['max_tickets']} бил., {db['fast_game']['duration_minutes']}м\nЦена: {db['settings']['ticket_price']} TON\nКомиссия: {db['settings']['commission']}%", parse_mode="Markdown")
        bot.answer_callback_query(call.id)

    # --- АДМИНКА ---
    elif data == "adm_std" and call.from_user.id == ADMIN_ID: show_std_settings(call.message)
    elif data == "adm_temp" and call.from_user.id == ADMIN_ID: show_temp_settings(call.message)
    elif data == "adm_fast" and call.from_user.id == ADMIN_ID: show_fast_settings(call.message)
    elif data == "adm_bal" and call.from_user.id == ADMIN_ID:
        total = sum([g.get("prize_pool",0)*db["settings"]["commission"]/80 for g in db["games"] if g["status"]=="finished"])
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Назад", callback_data="adm_back"))
        bot.edit_message_text(f"💰 *Баланс*\nЗаработано: *{total:.1f} TON*", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
    elif data == "adm_broad" and call.from_user.id == ADMIN_ID:
        admin_input_state[uid] = "broadcast"
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Отмена", callback_data="adm_back"))
        bot.edit_message_text("📢 Введи сообщение для рассылки:", call.message.chat.id, call.message.message_id, reply_markup=markup)
    elif data == "adm_back" and call.from_user.id == ADMIN_ID:
        bot.delete_message(call.message.chat.id, call.message.message_id)
        show_admin_main(call.message.chat.id)
    elif data == "adm_exit" and call.from_user.id == ADMIN_ID:
        admin_input_state.pop(uid, None)
        bot.delete_message(call.message.chat.id, call.message.message_id)

    # --- Редактирование стандартных ---
    elif data.startswith("std_") and call.from_user.id == ADMIN_ID:
        param = data[4:]
        admin_input_state[uid] = f"set_std_{param}"
        names = {"tickets":"билетов","winners":"победителей","price":"цена (TON)","commission":"комиссия (%)","duration":"длительность (ч)"}
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Назад", callback_data="adm_std"))
        bot.edit_message_text(f"Новое значение *{names[param]}*:\nТекущее: *{db['settings'][param]}*",
                              call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    # --- Редактирование быстрых ---
    elif data.startswith("fst_") and call.from_user.id == ADMIN_ID:
        param = data[4:]
        admin_input_state[uid] = f"set_fast_{param}"
        names = {"tickets":"билетов","price":"цена (TON)","duration":"длительность (мин)"}
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Назад", callback_data="adm_fast"))
        bot.edit_message_text(f"Новое значение *{names[param]}*:\nТекущее: *{db['fast_game'][param]}*",
                              call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    # --- Разовые ---
    elif data.startswith("tmp_") and call.from_user.id == ADMIN_ID:
        act = data[4:]
        if act == "apply":
            bot.answer_callback_query(call.id, "✅ Применено!" if db["temp_settings"] else "Нет изменений")
        elif act == "reset":
            db["temp_settings"] = {}; save_db(db)
            show_temp_settings(call.message)
        elif act in ["tickets","winners","price","duration"]:
            admin_input_state[uid] = f"set_tmp_{act}"
            markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Назад", callback_data="adm_temp"))
            bot.edit_message_text(f"Новое значение *{act}*:", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
        else: bot.answer_callback_query(call.id)

    else: bot.answer_callback_query(call.id)

# --- Функции отображения админки ---
def show_std_settings(message):
    db = load_db(); s = db["settings"]
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton(f"🎫 Билетов: {s['max_tickets']}", callback_data="std_tickets"),
               types.InlineKeyboardButton(f"🏆 Победителей: {s['winners_count']}", callback_data="std_winners"),
               types.InlineKeyboardButton(f"💵 Цена: {s['ticket_price']} TON", callback_data="std_price"),
               types.InlineKeyboardButton(f"📊 Комиссия: {s['commission']}%", callback_data="std_commission"),
               types.InlineKeyboardButton(f"⏰ Длительность: {s['duration_hours']}ч", callback_data="std_duration"),
               types.InlineKeyboardButton("🔙 Назад", callback_data="adm_back"))
    bot.edit_message_text("⚙️ *СТАНДАРТНЫЕ НАСТРОЙКИ*", message.chat.id, message.message_id, parse_mode="Markdown", reply_markup=markup)

def show_temp_settings(message):
    db = load_db(); s = db["temp_settings"] if db["temp_settings"] else db["settings"]
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton(f"🎫 Билетов: {s.get('max_tickets', db['settings']['max_tickets'])}", callback_data="tmp_tickets"),
               types.InlineKeyboardButton(f"🏆 Победителей: {s.get('winners_count', db['settings']['winners_count'])}", callback_data="tmp_winners"),
               types.InlineKeyboardButton(f"💵 Цена: {s.get('ticket_price', db['settings']['ticket_price'])} TON", callback_data="tmp_price"),
               types.InlineKeyboardButton(f"⏰ Длительность: {s.get('duration_hours', db['settings']['duration_hours'])}ч", callback_data="tmp_duration"),
               types.InlineKeyboardButton("✅ Применить", callback_data="tmp_apply"),
               types.InlineKeyboardButton("🔄 Сбросить", callback_data="tmp_reset"),
               types.InlineKeyboardButton("🔙 Назад", callback_data="adm_back"))
    bot.edit_message_text("🎯 *РАЗОВЫЙ РОЗЫГРЫШ*", message.chat.id, message.message_id, parse_mode="Markdown", reply_markup=markup)

def show_fast_settings(message):
    db = load_db(); s = db["fast_game"]
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton(f"🎫 Билетов: {s['max_tickets']}", callback_data="fst_tickets"),
               types.InlineKeyboardButton(f"💵 Цена: {s['ticket_price']} TON", callback_data="fst_price"),
               types.InlineKeyboardButton(f"⏰ Длительность: {s['duration_minutes']}м", callback_data="fst_duration"),
               types.InlineKeyboardButton("🔙 Назад", callback_data="adm_back"))
    bot.edit_message_text("⚡️ *БЫСТРЫЙ РОЗЫГРЫШ*", message.chat.id, message.message_id, parse_mode="Markdown", reply_markup=markup)

# --- Покупка ---
def buy_ticket(call, game_type):
    db = load_db(); uid = str(call.from_user.id)
    game = get_active_game(db) if game_type == "standard" else get_active_fast_game(db)
    price = db["settings"]["ticket_price"] if game_type == "standard" else db["fast_game"]["ticket_price"]
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
        bot.send_message(call.message.chat.id, f"❌ Ошибка создания платежа.\n{resp.get('error','')}")
        bot.answer_callback_query(call.id, "Ошибка")

def check_payment(call, inv_id):
    db = load_db(); uid = str(call.from_user.id)
    pay = db["pending_payments"].get(uid)
    if not pay or pay["inv_id"] != inv_id: bot.answer_callback_query(call.id, "Не найден"); return

    resp = check_invoice(inv_id)
    if resp.get("ok") and resp["result"]["items"]:
        inv = resp["result"]["items"][0]
        if inv["status"] == "paid":
            game_type = pay["game_type"]; game_id = pay["game_id"]
            tickets_key = "fast_tickets" if game_type == "fast" else "tickets"
            db.setdefault(tickets_key, []).append({"user_id": call.from_user.id, "username": call.from_user.username, "game_id": game_id})
            del db["pending_payments"][uid]; save_db(db)

            game = get_active_game(db) if game_type == "standard" else get_active_fast_game(db)
            sold = len([t for t in db.get(tickets_key, []) if t["game_id"] == game["id"]])
            bot.answer_callback_query(call.id, "✅ Оплачено!")
            bot.send_message(call.message.chat.id, f"✅ *Билет #{sold}*\nВ игре: {sold}/{game['max_tickets']}", parse_mode="Markdown")
            if sold >= game["max_tickets"]:
                if game_type == "fast": finish_fast_game(game["id"])
                else: finish_game(game["id"])
        else: bot.answer_callback_query(call.id, "⏳ Не оплачен")
    else: bot.answer_callback_query(call.id, "Ошибка проверки")

# ==================== ОБРАБОТКА ТЕКСТА ====================
@bot.message_handler(func=lambda m: True)
def text_handler(message):
    uid = str(message.from_user.id)
    if uid in admin_input_state and message.from_user.id == ADMIN_ID:
        state = admin_input_state[uid]
        db = load_db()

        if state == "broadcast":
            users = set()
            for t in db.get("tickets",[]): users.add(t["user_id"])
            for t in db.get("fast_tickets",[]): users.add(t["user_id"])
            cnt = 0
            for u in users:
                try: bot.send_message(u, message.text); cnt+=1
                except: pass
            bot.send_message(message.chat.id, f"📢 Отправлено {cnt} чел.")
            del admin_input_state[uid]
            show_admin_main(message.chat.id)
            return

        elif state.startswith("set_"):
            parts = state.split("_")
            if parts[1] == "std":
                param = parts[2]
                try:
                    val = float(message.text) if param in ["price","commission"] else int(message.text)
                    db["settings"][param] = val; save_db(db)
                    del admin_input_state[uid]
                    show_std_settings(message)
                except: bot.send_message(message.chat.id, "❌ Неверное число.")
            elif parts[1] == "fast":
                param = parts[2]
                try:
                    val = float(message.text) if param == "price" else int(message.text)
                    db["fast_game"][param] = val; save_db(db)
                    del admin_input_state[uid]
                    show_fast_settings(message)
                except: bot.send_message(message.chat.id, "❌ Неверное число.")
            elif parts[1] == "tmp":
                param = parts[2]
                try:
                    val = float(message.text) if param == "price" else int(message.text)
                    db.setdefault("temp_settings", {})[param] = val; save_db(db)
                    del admin_input_state[uid]
                    show_temp_settings(message)
                except: bot.send_message(message.chat.id, "❌ Неверное число.")
            return

    bot.send_message(message.chat.id, "Используй /start")

# ==================== ЗАПУСК ====================
print("Lucky Bank v4.0")
bot.remove_webhook()
time.sleep(1)
db = load_db()
if not get_active_game(db): create_game(db)
if not get_active_fast_game(db): create_fast_game(db)
print("Бот запущен!")
bot.polling(none_stop=True)
