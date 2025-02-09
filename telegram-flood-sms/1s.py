from telethon.sync import TelegramClient
from telethon.errors import PhoneCodeInvalidError
from time import sleep
import os

phone_numbers = '+998909332368'.split(",")  # Telefon raqamlarini vergul bilan ajrating
api_id = 10953300
api_hash = '9c24426e5d6fa1d441913e3906627f87'

session = "uzzz"
client = TelegramClient(session, api_id, api_hash)
client.connect()

for number in phone_numbers:
    number = number.strip()  
    try:
        client.send_code_request(number)
        print(f"Code request sent to {number}")
       
        try:
          
            
            client.sign_in(number, 12345)
            print(f"Successfully signed in with {number} ✓")

        except PhoneCodeInvalidError:
            print(f"Invalid code for {number}. Please try again.")

    except Exception as e:
        print(f"An error occurred with {number}: {e}")

os.remove("uzzz.session") 
os.system("python 1s.py")  
