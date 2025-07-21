import os
import requests
from telegram import Bot
from telegram.ext import Application, ContextTypes
import datetime
import asyncio
import threading
from apscheduler.schedulers.background import BackgroundScheduler
import time

print("weather_bot.py стартует!")

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
WEATHER_API_KEY = os.environ.get('WEATHER_API_KEY')
LAT = 49.8369
LON = 36.7594
CHAT_ID = '@pogoda_veleten'  # Публичный канал

def get_wind_direction_ua(deg):
    dirs = [
        'північ', 'північний схід', 'схід', 'південний схід',
        'південь', 'південний захід', 'захід', 'північний захід'
    ]
    ix = int((deg + 22.5) // 45) % 8
    return dirs[ix]

UA_WEEKDAYS = {
    0: 'пн', 1: 'вт', 2: 'ср', 3: 'чт', 4: 'пт', 5: 'сб', 6: 'нд'
}

UA_MONTHS = {
    1: 'січня', 2: 'лютого', 3: 'березня', 4: 'квітня', 5: 'травня', 6: 'червня',
    7: 'липня', 8: 'серпня', 9: 'вересня', 10: 'жовтня', 11: 'листопада', 12: 'грудня'
}

UA_WEATHER = {
    'ясно': '☀️ Ясно',
    'чисте небо': '☀️ Чисте небо',
    'хмарно': '☁️ Хмарно',
    'похмуро': '☁️ Похмуро',
    'мінлива хмарність': '🌤🌥 Мінлива хмарність',
    'рвані хмари': '🌥 Рвані хмари',
    'дощ': '🌧 Дощ',
    'легкий дощ': '🌦 Легкий дощ',
    'невеликий дощ': '🌦🌧 Невеликий дощ',
    'гроза': '🌩 Гроза',
    'сніг': '❄️ Сніг',
    'туман': '😶‍🌫️ Туман',
}

def get_weather_forecast():
    url = f'https://api.openweathermap.org/data/2.5/forecast?lat={LAT}&lon={LON}&appid={WEATHER_API_KEY}&units=metric&lang=ua'
    response = requests.get(url, timeout=10)
    data = response.json()
    days = {}
    for item in data['list']:
        dt = datetime.datetime.fromtimestamp(item['dt'])
        day_key = dt.date()
        weather_desc = item['weather'][0]['description'].lower()
        ua_desc = UA_WEATHER.get(weather_desc, weather_desc)
        entry = {
            'temp': item['main']['temp'],
            'wind_speed': item['wind']['speed'],
            'wind_dir': get_wind_direction_ua(item['wind']['deg']),
            'humidity': item['main']['humidity'],
            'description': ua_desc,
            'desc_raw': weather_desc,  # для жирного
            'time': dt.strftime('%H:%M'),
        }
        if day_key not in days:
            days[day_key] = {'date': dt, 'night': None, 'day': None}
        if dt.hour == 3:
            days[day_key]['night'] = entry
        if dt.hour == 15:
            days[day_key]['day'] = entry
    # Гарантируем 5 дней, даже если нет ночи/дня
    all_dates = sorted([datetime.date.today() + datetime.timedelta(days=i) for i in range(5)])
    forecast = []
    for d in all_dates:
        day = days.get(d, {'date': datetime.datetime.combine(d, datetime.time()), 'night': None, 'day': None})
        forecast.append(day)
    return forecast

async def send_weather(context: ContextTypes.DEFAULT_TYPE):
    print("[send_weather] Початок формування прогнозу")
    forecast = get_weather_forecast()
    msg = '🌤 Прогноз погоди у Велетені на 5 днів\n\n'
    for i, day in enumerate(forecast):
        dt = day['date']
        weekday = UA_WEEKDAYS[dt.weekday()]
        month_ua = UA_MONTHS[dt.month]
        msg += f"📅 {dt.day} {month_ua} ({weekday})\n"
        night = day['night']
        if night:
            desc = night['description']
            desc_raw = night.get('desc_raw', '')
            desc_bold = f"<b>{desc}</b>" if desc_raw in [
                'легкий дощ', 'хмарно', 'ясно', 'чисте небо', 'мінлива хмарність',
                'похмуро', 'дощ', 'гроза', 'сніг', 'туман', 'невеликий дощ', 'рвані хмари'
            ] else desc
            msg += (
                f"🌙 Ніч: {night['temp']:.1f}°C, {desc_bold}\n"
                f"вітер {night['wind_speed']} м/с, {night['wind_dir']}, вологість {night['humidity']}%\n"
            )
        else:
            msg += "🌙 Ніч: —\n"
        daypart = day['day']
        if daypart:
            desc = daypart['description']
            desc_raw = daypart.get('desc_raw', '')
            desc_bold = f"<b>{desc}</b>" if desc_raw in [
                'легкий дощ', 'хмарно', 'ясно', 'чисте небо', 'мінлива хмарність',
                'похмуро', 'дощ', 'гроза', 'сніг', 'туман', 'невеликий дощ', 'рвані хмари'
            ] else desc
            msg += (
                f"☀️ День: {daypart['temp']:.1f}°C, {desc_bold}\n"
                f"вітер {daypart['wind_speed']} м/с, {daypart['wind_dir']}, вологість {daypart['humidity']}%\n"
            )
        else:
            msg += "☀️ День: —\n"
        if i < len(forecast) - 1:
            msg += "\n\n"
    msg += "\n\n🎯 Велетеньский прогноз \n☁️☀️ Оновлення щодня — будь у курсі 🌦\n#погода #велетень"
    try:
        print("[send_weather] Відправка повідомлення у Telegram...")
        await context.bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='HTML')
        print("[send_weather] Повідомлення успішно відправлено!")
    except Exception as e:
        print(f"[send_weather] Помилка при відправці повідомлення: {e}")

async def run_send_weather(app):
    print("[run_send_weather] Старт задачи")
    class DummyContext:
        def __init__(self, bot):
            self.bot = bot
    context = DummyContext(app.bot)
    print("[run_send_weather] Запуск отправки прогноза...")
    try:
        await send_weather(context)
        print("[run_send_weather] Прогноз успешно отправлен!")
    except Exception as e:
        print(f"[run_send_weather] Ошибка: {e}")
    finally:
        print("[run_send_weather] Завершение задачи")

def start_scheduler(app, loop):
    scheduler = BackgroundScheduler(timezone="Europe/Kiev")
    scheduler.add_job(lambda: asyncio.run_coroutine_threadsafe(run_send_weather(app), loop), 'interval', minutes=3)
    scheduler.start()

def main():
    print("=== weather_bot.py MAIN STARTED ===")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    threading.Thread(target=start_scheduler, args=(app, loop), daemon=True).start()
    print("Бот запущен і буде відправляти прогноз кожну годину в канал @pogoda_veleten")
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        print("Остановка бота...")
    finally:
        loop.close()

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"FATAL ERROR: {e}")
        import time
        time.sleep(60)