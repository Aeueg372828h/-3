import telebot
from telebot import types
import requests
from datetime import datetime, timedelta

BOT_TOKEN = "8179092727:AAFuKcTZAgJrMGdMGLYYGukCV64UHcY2sx8"
API_TOKEN = "69b9e0a9db675b45445ec37e847a0b2b"


bot = telebot.TeleBot(BOT_TOKEN)

user_favorites = {}  
last_search_results = {} 

def manual_escape_html(text):
    """Заменяет символы, опасные для HTML-разметки, на их сущности."""
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def get_airport_code(city_name):
    url = "https://api.travelpayouts.com/data/ru/cities.json"

    try:
        r = requests.get(url)
        r.raise_for_status()
        cities = r.json()

        for c in cities:
            if city_name.lower().strip() == c.get("name", "").lower().strip():
                return c.get("code")
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при получении кодов аэропортов: {e}")
    except Exception as e:
        print(f"Общая ошибка в get_airport_code: {e}")

    return None

def search_tickets(origin_code, dest_code, departure_date=None):
    url = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
    results = []
    
    dates_to_search = []
    if departure_date:
        try:
            datetime.strptime(departure_date, "%Y-%m-%d") 
            dates_to_search.append(departure_date)
        except ValueError:
            pass
    else:
        today = datetime.today()
        for i in range(3):
            dates_to_search.append((today + timedelta(days=i)).strftime("%Y-%m-%d"))

    for date in dates_to_search:
        params = {
            "origin": origin_code,
            "destination": dest_code,
            "departure_at": date,
            "sorting": "price",
            "limit": 5,
            "token": API_TOKEN
        }

        try:
            r = requests.get(url, params=params)
            r.raise_for_status()
            data = r.json()
        except requests.exceptions.RequestException as e:
            print(f"Ошибка API при поиске билетов на {date}: {e}")
            continue

        if "data" in data and data["data"]:
            for f in data["data"]:
                results.append({
                    "date": date,
                    "price": f["price"],
                    "airline": f.get("airline", "—"),
                    "flight_number": f.get("flight_number", "—"),
                    "link": f.get("link", "—"),
                    "origin_code": origin_code,
                    "dest_code": dest_code
                })

    results = sorted(results, key=lambda x: x["price"])
    return results[:5]


def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("Поиск билетов", "Избранное") 
    kb.add("О нас", "Помощь") 
    return kb

def get_flight_inline_kb(flight_data, index, is_favorite=False):
    kb = types.InlineKeyboardMarkup()
    fav_text = "⭐️ Добавлено" if is_favorite else "⭐️ В Избранное"
    
    add_fav_btn = types.InlineKeyboardButton(
        text=fav_text, 
        callback_data=f"add_fav|{index}"
    )
    buy_btn = types.InlineKeyboardButton(
        text="💳 Купить", 
        callback_data=f"buy|{index}"
    )
    kb.add(add_fav_btn, buy_btn)
    return kb

def get_favorite_inline_kb(ticket_info, index):
    kb = types.InlineKeyboardMarkup()
    buy_btn = types.InlineKeyboardButton(
        text="💳 Купить этот билет", 
        callback_data=f"buy|{index}"
    )
    del_fav_btn = types.InlineKeyboardButton(
        text="❌ Удалить", 
        callback_data=f"del_fav|{index}"
    )
    kb.add(buy_btn, del_fav_btn)
    return kb


@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(
        message.chat.id,
        "✈ Добро пожаловать в бот поиска авиабилетов!\nВыберите действие:",
        reply_markup=main_menu()
    )

@bot.message_handler(func=lambda m: m.text == "Поиск билетов")
def ask_route_and_date(message):
    msg = bot.send_message(
        message.chat.id,
        "Введите маршрут и дату (необязательно).\n"
        "Пример 1: *Алматы Астана*\n"
        "Пример 2: *Алматы Астана 2026-01-20*",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, process_route_and_date)

def process_route_and_date(message):
    chat_id = message.chat.id
    try:
        parts = message.text.split()
        if len(parts) not in [2, 3]:
            bot.send_message(chat_id, "Пиши так: *Город1 Город2* или *Город1 Город2 ГГГГ-ММ-ДД*.")
            return

        city_from = parts[0]
        city_to = parts[1]
        departure_date = parts[2] if len(parts) == 3 else None

        if departure_date:
            try:
                datetime.strptime(departure_date, "%Y-%m-%d")
            except ValueError:
                bot.send_message(chat_id, "❌ Неверный формат даты. Используй *ГГГГ-ММ-ДД* (например, 2026-01-20).")
                return

        bot.send_message(chat_id, f"🔍 Ищу билеты: {city_from} → {city_to}" + (f" на {departure_date}" if departure_date else " на ближайшие даты"))

        from_code = get_airport_code(city_from)
        to_code = get_airport_code(city_to)

        if not from_code or not to_code:
            bot.send_message(chat_id, "❌ Не нашел код аэропорта. Попробуй другой город.")
            return

        flights = search_tickets(from_code, to_code, departure_date)

        if not flights:
            bot.send_message(chat_id, "❌ Билетов не найдено по вашему запросу.")
        else:
            last_search_results[chat_id] = flights
            
            bot.send_message(chat_id, f"✈ Билеты {city_from} ({from_code}) → {city_to} ({to_code}):\n")
            
            for i, f in enumerate(flights):
                ticket_text = f"""
*Вариант №{i+1}:*
**ДАТА:** {f['date']}
**СУММА:** {f['price']}₸
**Рейс:** {f['airline']} {f['flight_number']}
---
"""
                bot.send_message(
                    chat_id, 
                    ticket_text, 
                    parse_mode="Markdown", 
                    reply_markup=get_flight_inline_kb(f, i)
                )

    except Exception as e:
        bot.send_message(chat_id, f"Произошла ошибка при поиске: {e}")

@bot.message_handler(func=lambda m: m.text == "Избранное")
def show_favorites(message):
    chat_id = message.chat.id
    favorites = user_favorites.get(chat_id, [])

    if not favorites:
        bot.send_message(chat_id, "Избранное пусто") 
        return

    bot.send_message(chat_id, "⭐ Ваши Избранные билеты:")
    
    for i, f in enumerate(favorites):
        ticket_text = f"""
*Избранный билет №{i+1}:*
**ОТКУДА:** {f['origin_code']}
**КУДА:** {f['dest_code']}
**ДАТА:** {f['date']}
**СУММА:** {f['price']}₸
**Рейс:** {f['airline']} {f['flight_number']}
"""
        bot.send_message(chat_id, ticket_text, parse_mode="Markdown", reply_markup=get_favorite_inline_kb(f, i))



@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    chat_id = call.message.chat.id
    try:
        action, index_str = call.data.split("|")
        index = int(index_str)
        
        
        if action == "add_fav":
            flights = last_search_results.get(chat_id, [])
            if 0 <= index < len(flights):
                flight = flights[index]
                
                if flight not in user_favorites.get(chat_id, []):
                    user_favorites.setdefault(chat_id, []).append(flight)
                    bot.answer_callback_query(call.id, "✅ Билет добавлен в Избранное!")
                    
                    original_text = call.message.text 
                    new_kb = get_flight_inline_kb(flight, index, is_favorite=True)
                    
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=call.message.message_id,
                        text=original_text, 
                        parse_mode="Markdown",
                        reply_markup=new_kb
                    )
                else:
                    bot.answer_callback_query(call.id, "Этот билет уже в Избранном!")
            else:
                bot.answer_callback_query(call.id, "Ошибка: неверный индекс билета.")

        
        elif action == "buy":
            source_list = last_search_results.get(chat_id)
            if not source_list or index >= len(source_list):
                 source_list = user_favorites.get(chat_id)
            
            if source_list and 0 <= index < len(source_list):
                ticket_to_buy = source_list[index]
                
                raw_ticket_info = f"{ticket_to_buy['origin_code']} → {ticket_to_buy['dest_code']} ({ticket_to_buy['date']}) за {ticket_to_buy['price']}₸"
                
                
                ticket_info = manual_escape_html(raw_ticket_info)
                
                bot.answer_callback_query(call.id, "⏳ Переходим к имитации покупки...")
                
                msg = bot.send_message(
                    chat_id, 
                    f"💳 <b>ПОКУПКА БИЛЕТА</b>:\n\n{ticket_info}\n\n"
                    "Для завершения 'покупки' напишите <b>купить</b>",
                    parse_mode="HTML"
                )
                
                bot.register_next_step_handler_by_chat_id(
                    chat_id, 
                    simulate_payment_step, 
                    ticket_info=ticket_info 
                )
            else:
                bot.answer_callback_query(call.id, "Ошибка: билет не найден.")
                
       
        elif action == "del_fav":
            favorites = user_favorites.get(chat_id, [])
            if 0 <= index < len(favorites):
                ticket_info = favorites.pop(index) 
                bot.answer_callback_query(call.id, "❌ Билет удален из Избранного.")
                
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=call.message.message_id,
                    text=f"~Билет удален: {ticket_info['origin_code']} → {ticket_info['dest_code']} ({ticket_info['date']})~",
                    parse_mode="Markdown"
                )
            else:
                bot.answer_callback_query(call.id, "Ошибка при удалении.")

    except Exception as e:
        print(f"Ошибка в callback_handler: {e}")
        bot.answer_callback_query(call.id, "Произошла внутренняя ошибка.")


def simulate_payment_step(message, ticket_info):
    chat_id = message.chat.id
    
    if message.text and message.text.lower().strip() == "купить":
        bot.send_message(
            chat_id,
            f"🎉 <b>ПОЗДРАВЛЯЕМ!</b> 🎉\n"
            f"Вы успешно 'приобрели' билет:\n\n{ticket_info}\n\n"
            "Спасибо за использование нашего 'сервиса'! (Это была имитация)",
            parse_mode="HTML",
            reply_markup=main_menu()
        )
    else:
        msg = bot.send_message(
            chat_id,
            "❌ Неверная команда. Для 'покупки' билета, пожалуйста, напишите *купить*.",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler_by_chat_id(
            chat_id, 
            simulate_payment_step, 
            ticket_info=ticket_info
        )


@bot.message_handler(func=lambda m: m.text == "Помощь")
def help_message(message):
    text = """
📌 *Как пользоваться ботом:*
1. Нажми кнопку **"Поиск билетов"**.
2. Напиши маршрут и дату:
   - **Алматы Москва** (поиск на ближайшие 3 дня)
   - **Алматы Москва 2025-12-31** (поиск на конкретную дату)
3. Бот выдаст вам список билетов с ценой и датой.
4. Вы можете 'купить' билет, нажав кнопку **"💳 Купить"** под нужным вариантом.
5. Или выбрать билет и добавить его в **"⭐️ В Избранное"**, чтобы сохранить.
"""
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "О нас")
def about(message):
    bot.send_message(message.chat.id, "Мы ищем самые дешёвые билеты по реальным данным Aviasales ✈🔥")

print("работаю")    
bot.polling(non_stop=True)