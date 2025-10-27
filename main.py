import json, os, asyncio
from datetime import datetime, timedelta
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from env import BOT_TOKEN, ADMIN_ID, ADMIN_GROUP_ID, DATA_FILE
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
import logging

# MongoDB Connection
class MongoDBHandler:
    def __init__(self):
        self.uri = os.getenv('MONGODB_URI', 'mongodb+srv://wanglinmongodb:wanglin@cluster0.tny5vhz.mongodb.net/?retryWrites=true&w=majority')
        self.client = None
        self.db = None
        self.connect()
    
    def connect(self):
        """MongoDB နဲ့ ချိတ်ဆက်မယ်"""
        try:
            self.client = MongoClient(self.uri)
            self.client.admin.command('ping')
            self.db = self.client.mlbb_bot
            print("✅ MongoDB နဲ့ ချိတ်ဆက်ပြီးပါပြီ")
        except ConnectionFailure as e:
            print(f"❌ MongoDB ချိတ်ဆက်မရပါ: {e}")
            raise
    
    def get_collection(self, collection_name):
        """Collection တစ်ခုရယူမယ်"""
        if self.db is None:
            self.connect()
        return self.db[collection_name]

# MongoDB Instance
mongo_handler = MongoDBHandler()

class UserManager:
    def __init__(self):
        self.users = mongo_handler.get_collection('users')
        self.orders = mongo_handler.get_collection('orders')
        self.topups = mongo_handler.get_collection('topups')
        self.settings = mongo_handler.get_collection('settings')
    
    def load_data(self):
        """Data အားလုံးကို ယူမယ် - JSON compatibility အတွက်"""
        return {
            "users": self.get_all_users(),
            "prices": self.get_prices(),
            "authorized_users": self.get_authorized_users(),
            "admin_ids": self.get_admin_ids()
        }
    
    def get_all_users(self):
        """User အားလုံးကို dict အဖြစ်ရမယ်"""
        users_dict = {}
        for user in self.users.find():
            # Convert ObjectId to string for compatibility
            user_data = user.copy()
            user_id = str(user_data.pop('_id'))
            users_dict[user_id] = user_data
        return users_dict
    
    def get_user(self, user_id):
        """User တစ်ဦးကို ရှာမယ်"""
        return self.users.find_one({'_id': str(user_id)})
    
    def create_user(self, user_data):
        """User အသစ်လုပ်မယ်"""
        user_data['_id'] = str(user_data['user_id'])
        user_data['created_at'] = datetime.now().isoformat()
        user_data['balance'] = user_data.get('balance', 0)
        user_data['orders'] = user_data.get('orders', [])
        user_data['topups'] = user_data.get('topups', [])
        return self.users.insert_one(user_data)
    
    def update_user(self, user_id, update_data):
        """User update လုပ်မယ်"""
        return self.users.update_one(
            {'_id': str(user_id)},
            {'$set': update_data}
        )
    
    def update_user_balance(self, user_id, new_balance):
        """User balance update လုပ်မယ်"""
        return self.users.update_one(
            {'_id': str(user_id)},
            {'$set': {'balance': new_balance}}
        )
    
    def add_user_order(self, user_id, order_data):
        """User ထံ order ထည့်မယ်"""
        return self.users.update_one(
            {'_id': str(user_id)},
            {'$push': {'orders': order_data}}
        )
    
    def add_user_topup(self, user_id, topup_data):
        """User ထံ topup ထည့်မယ်"""
        return self.users.update_one(
            {'_id': str(user_id)},
            {'$push': {'topups': topup_data}}
        )
    
    def create_order(self, order_data):
        """Order အသစ်လုပ်မယ်"""
        order_data['created_at'] = datetime.now().isoformat()
        return self.orders.insert_one(order_data)
    
    def update_order_status(self, order_id, status, admin_name=None):
        """Order status update လုပ်မယ်"""
        update_data = {
            'status': status,
            'updated_at': datetime.now().isoformat()
        }
        if admin_name:
            update_data[f'{status}_by'] = admin_name
            update_data[f'{status}_at'] = datetime.now().isoformat()
        
        return self.orders.update_one(
            {'order_id': order_id},
            {'$set': update_data}
        )
    
    def get_order(self, order_id):
        """Order တစ်ခုရှာမယ်"""
        return self.orders.find_one({'order_id': order_id})
    
    def create_topup(self, topup_data):
        """Topup request အသစ်လုပ်မယ်"""
        topup_data['created_at'] = datetime.now().isoformat()
        return self.topups.insert_one(topup_data)
    
    def update_topup_status(self, topup_id, status, admin_name=None):
        """Topup status update လုပ်မယ်"""
        update_data = {
            'status': status,
            'updated_at': datetime.now().isoformat()
        }
        if admin_name:
            update_data[f'{status}_by'] = admin_name
            update_data[f'{status}_at'] = datetime.now().isoformat()
        
        return self.topups.update_one(
            {'topup_id': topup_id},
            {'$set': update_data}
        )
    
    def get_topup(self, topup_id):
        """Topup တစ်ခုရှာမယ်"""
        return self.topups.find_one({'topup_id': topup_id})
    
    def get_prices(self):
        """Price settings များရမယ်"""
        settings = self.settings.find_one({'type': 'prices'})
        return settings.get('data', {}) if settings else {}
    
    def update_prices(self, prices):
        """Price settings update လုပ်မယ်"""
        return self.settings.update_one(
            {'type': 'prices'},
            {'$set': {'data': prices, 'updated_at': datetime.now().isoformat()}},
            upsert=True
        )
    
    def get_authorized_users(self):
        """Authorized users list ရမယ်"""
        settings = self.settings.find_one({'type': 'authorized_users'})
        return settings.get('data', []) if settings else []
    
    def update_authorized_users(self, users_list):
        """Authorized users update လုပ်မယ်"""
        return self.settings.update_one(
            {'type': 'authorized_users'},
            {'$set': {'data': users_list, 'updated_at': datetime.now().isoformat()}},
            upsert=True
        )
    
    def get_admin_ids(self):
        """Admin IDs များရမယ်"""
        settings = self.settings.find_one({'type': 'admin_ids'})
        return settings.get('data', [ADMIN_ID]) if settings else [ADMIN_ID]
    
    def update_admin_ids(self, admin_list):
        """Admin IDs update လုပ်မယ်"""
        return self.settings.update_one(
            {'type': 'admin_ids'},
            {'$set': {'data': admin_list, 'updated_at': datetime.now().isoformat()}},
            upsert=True
        )

# Global instance
user_manager = UserManager()

# Authorized users - only these users can use the bot
AUTHORIZED_USERS = set()

# User states for restricting actions after screenshot
user_states = {}

# Bot maintenance mode
bot_maintenance = {
    "orders": True,    # True = enabled, False = disabled
    "topups": True,    # True = enabled, False = disabled
    "general": True    # True = enabled, False = disabled
}

# Payment information
payment_info = {
    "kpay_number": "09678786528",
    "kpay_name": "Ma May Phoo Wai",
    "kpay_image": None,  # Store file_id of KPay QR code image
    "wave_number": "09673585480",
    "wave_name": "Nine Nine",
    "wave_image": None   # Store file_id of Wave QR code image
}

def is_user_authorized(user_id):
    """Check if user is authorized to use the bot"""
    return str(user_id) in AUTHORIZED_USERS or int(user_id) == ADMIN_ID

async def is_bot_admin_in_group(bot, chat_id):
    """Check if bot is admin in the group"""
    try:
        me = await bot.get_me()
        bot_member = await bot.get_chat_member(chat_id, me.id)
        is_admin = bot_member.status in [ChatMember.ADMINISTRATOR, ChatMember.OWNER]
        print(f"Bot admin check for group {chat_id}: {is_admin}, status: {bot_member.status}")
        return is_admin
    except Exception as e:
        print(f"Error checking bot admin status in group {chat_id}: {e}")
        return False

def simple_reply(message_text):
    """
    Simple auto-replies for common queries
    """
    message_lower = message_text.lower()

    # Greetings
    if any(word in message_lower for word in ["hello", "hi", "မင်္ဂလာပါ", "ဟယ်လို", "ဟိုင်း", "ကောင်းလား"]):
        return ("👋 မင်္ဂလာပါ! 𝙅𝘽 𝙈𝙇𝘽𝘽 𝘼𝙐𝙏𝙊 𝙏𝙊𝙋 𝙐𝙋 𝘽𝙊𝙏 မှ ကြိုဆိုပါတယ်!\n\n"
                "📱 Bot commands များ သုံးရန် /start နှိပ်ပါ\n")

    # Help requests
    elif any(word in message_lower for word in ["help", "ကူညီ", "အကူအညီ", "မသိ", "လမ်းညွှန်"]):
        return ("📱 ***အသုံးပြုနိုင်တဲ့ commands:***\n\n"
                "• /start - Bot စတင်အသုံးပြုရန်\n"
                "• /mmb gameid serverid amount - Diamond ဝယ်ယူရန်\n"
                "• /balance - လက်ကျန်ငွေ စစ်ရန်\n"
                "• /topup amount - ငွေဖြည့်ရန်\n"
                "• /price - ဈေးနှုန်းများ ကြည့်ရန်\n"
                "• /history - မှတ်တမ်းများ ကြည့်ရန်\n\n"
                "💡 အသေးစိတ် လိုအပ်ရင် admin ကို ဆက်သွယ်ပါ!")

    # Default response
    else:
        return ("📱 ***MLBB Diamond Top-up Bot***\n\n"
                "💎 ***Diamond ဝယ်ယူရန် /mmb command သုံးပါ။***\n"
                "💰 ***ဈေးနှုန်းများ သိရှိရန် /price နှိပ်ပါ။***\n"
                "🆘 ***အကူအညီ လိုရင် /start နှိပ်ပါ။***")

# MongoDB versions of data functions
def load_data():
    """Load data from MongoDB"""
    return user_manager.load_data()

def save_data(data):
    """Save data to MongoDB - maintained for compatibility"""
    # Data is saved automatically in MongoDB operations
    pass

def load_authorized_users():
    """Load authorized users from MongoDB"""
    global AUTHORIZED_USERS
    AUTHORIZED_USERS = set(user_manager.get_authorized_users())

def save_authorized_users():
    """Save authorized users to MongoDB"""
    user_manager.update_authorized_users(list(AUTHORIZED_USERS))

def load_prices():
    """Load custom prices from MongoDB"""
    return user_manager.get_prices()

def save_prices(prices):
    """Save prices to MongoDB"""
    user_manager.update_prices(prices)

def validate_game_id(game_id):
    """Validate MLBB Game ID (6-10 digits)"""
    if not game_id.isdigit():
        return False
    if len(game_id) < 6 or len(game_id) > 10:
        return False
    return True

def validate_server_id(server_id):
    """Validate MLBB Server ID (3-5 digits)"""
    if not server_id.isdigit():
        return False
    if len(server_id) < 3 or len(server_id) > 5:
        return False
    return True

def is_banned_account(game_id):
    """
    Check if MLBB account is banned
    """
    banned_ids = [
        "123456789",  # Example banned ID
        "000000000",  # Invalid pattern
        "111111111",  # Invalid pattern
    ]

    if game_id in banned_ids:
        return True

    if len(set(game_id)) == 1:  # All same digits like 111111111
        return True

    if game_id.startswith("000") or game_id.endswith("000"):
        return True

    return False

def get_price(diamonds):
    # Load custom prices first - these override defaults
    custom_prices = load_prices()
    if diamonds in custom_prices:
        return custom_prices[diamonds]

    # Default prices
    if diamonds.startswith("wp") and diamonds[2:].isdigit():
        n = int(diamonds[2:])
        if 1 <= n <= 10:
            return n * 6000
    table = {
        "11": 950, "22": 1900, "33": 2850, "56": 4200, "112": 8200,
        "86": 5100, "172": 10200, "257": 15300, "343": 20400,
        "429": 25500, "514": 30600, "600": 35700, "706": 40800,
        "878": 51000, "963": 56100, "1049": 61200, "1135": 66300,
        "1412": 81600, "2195": 122400, "3688": 204000,
        "5532": 306000, "9288": 510000, "12976": 714000,
        "55": 3500, "165": 10000, "275": 16000, "565": 33000
    }
    return table.get(diamonds)

def is_payment_screenshot(update):
    """
    Check if the image is likely a payment screenshot
    """
    if update.message.photo:
        caption = update.message.caption or ""
        payment_keywords = ["kpay", "wave", "payment", "pay", "transfer", "လွှဲ", "ငွေ"]
        return True
    return False

pending_topups = {}

async def check_pending_topup(user_id):
    """Check if user has pending topups from MongoDB"""
    user_data = user_manager.get_user(user_id)
    if user_data and 'topups' in user_data:
        for topup in user_data['topups']:
            if topup.get("status") == "pending":
                return True
    return False

async def send_pending_topup_warning(update: Update):
    """Send pending topup warning message"""
    await update.message.reply_text(
        "⏳ ***Pending Topup ရှိနေပါတယ်!***\n\n"
        "❌ သင့်မှာ admin က approve မလုပ်သေးတဲ့ topup ရှိနေပါတယ်။\n\n"
        "***လုပ်ရမည့်အရာများ***:\n"
        "***• Admin က topup ကို approve လုပ်ပေးတဲ့အထိ စောင့်ပါ။***\n"
        "***• Approve ရပြီးမှ command တွေကို ပြန်အသုံးပြုနိုင်ပါမယ်။***\n\n"
        "📞 ***အရေးပေါ်ဆိုရင် admin ကို ဆက်သွယ်ပါ။***\n\n"
        "💡 /balance ***နဲ့ status စစ်ကြည့်နိုင်ပါတယ်။***",
        parse_mode="Markdown"
    )

async def check_maintenance_mode(command_type):
    """Check if specific command type is in maintenance mode"""
    return bot_maintenance.get(command_type, True)

async def send_maintenance_message(update: Update, command_type):
    """Send maintenance mode message with beautiful UI"""
    user_name = update.effective_user.first_name or "User"

    if command_type == "orders":
        msg = (
            f"မင်္ဂလာပါ {user_name}! 👋\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "⏸️ ***Bot အော်ဒါတင်ခြင်းအား ခေတ္တ ယာယီပိတ်ထားပါသည်** ⏸️***\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "***🔄 Admin မှ ပြန်လည်ဖွင့်ပေးမှ အသုံးပြုနိုင်ပါမည်။***\n\n"
            "📞 အရေးပေါ်ဆိုရင် Admin ကို ဆက်သွယ်ပါ။"
        )
    elif command_type == "topups":
        msg = (
            f"မင်္ဂလာပါ {user_name}! 👋\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "⏸️ ***Bot ငွေဖြည့်ခြင်းအား ခေတ္တ ယာယီပိတ်ထားပါသည်*** ⏸️\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "***🔄 Admin မှ ပြန်လည်ဖွင့်ပေးမှ အသုံးပြုနိုင်ပါမည်။***\n\n"
            "📞 ***အရေးပေါ်ဆိုရင် Admin ကို ဆက်သွယ်ပါ။***"
        )
    else:
        msg = (
            f"***မင်္ဂလာပါ*** {user_name}! 👋\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "⏸️ ***Bot အား ခေတ္တ ယာယီပိတ်ထားပါသည်*** ⏸️\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "***🔄 Admin မှ ပြန်လည်ဖွင့်ပေးမှ အသုံးပြုနိုင်ပါမည်။***\n\n"
            "📞 ***အရေးပေါ်ဆိုရင် Admin ကို ဆက်သွယ်ပါ။***"
        )

    await update.message.reply_text(msg, parse_mode="Markdown")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    username = user.username or "-"
    name = f"{user.first_name} {user.last_name or ''}".strip()

    # Load authorized users
    load_authorized_users()

    # Check if user is authorized
    if not is_user_authorized(user_id):
        keyboard = [
            [InlineKeyboardButton("📝 Register တောင်းဆိုမယ်", callback_data="request_register")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"🚫 ***Bot အသုံးပြုခွင့် မရှိပါ!***\n\n"
            f"👋 ***မင်္ဂလာပါ*** `{name}`!\n"
            f"🆔 Your ID: `{user_id}`\n\n"
            "❌ ***သင်သည် ဤ bot ကို အသုံးပြုခွင့် မရှိသေးပါ။***\n\n"
            "***လုပ်ရမည့်အရာများ***:\n"
            "***• အောက်က 'Register တောင်းဆိုမယ်' button ကို နှိပ်ပါ***\n"
            "***• သို့မဟုတ်*** /register ***command သုံးပါ။***\n"
            "***• Owner က approve လုပ်တဲ့အထိ စောင့်ပါ။***\n\n"
            "✅ ***Owner က approve လုပ်ပြီးမှ bot ကို အသုံးပြုနိုင်ပါမယ်။***\n\n",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return

    # Check for pending topups first
    if await check_pending_topup(user_id):
        await send_pending_topup_warning(update)
        return

    # Check if user exists in MongoDB, if not create
    user_data = user_manager.get_user(user_id)
    if not user_data:
        user_data = {
            "user_id": user_id,
            "name": name,
            "username": username,
            "balance": 0,
            "orders": [],
            "topups": []
        }
        user_manager.create_user(user_data)

    # Clear any restricted state when starting
    if user_id in user_states:
        del user_states[user_id]

    # Create clickable name
    clickable_name = f"[{name}](tg://user?id={user_id})"

    msg = (
        f"👋 ***မင်္ဂလာပါ*** {clickable_name}!\n"
        f"🆔 ***Telegram User ID:*** `{user_id}`\n\n"
        "💎 ***𝙅𝘽 𝙈𝙇𝘽𝘽 𝘼𝙐𝙏𝙊 𝙏𝙊𝙋 𝙐𝙋 𝘽𝙊𝙏*** မှ ကြိုဆိုပါတယ်။\n\n"
        "***အသုံးပြုနိုင်တဲ့ command များ***:\n"
        "➤ /mmb gameid serverid amount\n"
        "➤ /balance - ဘယ်လောက်လက်ကျန်ရှိလဲ စစ်မယ်\n"
        "➤ /topup amount - ငွေဖြည့်မယ် (screenshot တင်ပါ)\n"
        "➤ /price - Diamond များရဲ့ ဈေးနှုန်းများ\n"
        "➤ /history - အော်ဒါမှတ်တမ်းကြည့်မယ်\n\n"
        "***📌 ဥပမာ***:\n"
        "`/mmb 123456789 12345 wp1`\n"
        "`/mmb 123456789 12345 86`\n\n"
        "***လိုအပ်တာရှိရင် Owner ကို ဆက်သွယ်နိုင်ပါတယ်။***"
    )

    # Try to send with user's profile photo
    try:
        user_photos = await context.bot.get_user_profile_photos(user_id=int(user_id), limit=1)
        if user_photos.total_count > 0:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=user_photos.photos[0][0].file_id,
                caption=msg,
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(msg, parse_mode="Markdown")

async def mmb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    # Check authorization
    load_authorized_users()
    if not is_user_authorized(user_id):
        keyboard = [[InlineKeyboardButton("👑 Contact Owner", url=f"tg://user?id={ADMIN_ID}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🚫 အသုံးပြုခွင့် မရှိပါ!\n\n"
            "Owner ထံ bot အသုံးပြုခွင့် တောင်းဆိုပါ။",
            reply_markup=reply_markup
        )
        return

    # Check maintenance mode
    if not await check_maintenance_mode("orders"):
        await send_maintenance_message(update, "orders")
        return

    # Check if user is restricted after screenshot
    if user_id in user_states and user_states[user_id] == "waiting_approval":
        await update.message.reply_text(
            "⏳ ***Screenshot ပို့ပြီးပါပြီ!***\n\n"
            "❌ ***Admin က လက်ခံပြီးကြောင်း အတည်ပြုတဲ့အထိ commands တွေ အသုံးပြုလို့ မရပါ။***\n\n"
            "⏰ ***Admin က approve လုပ်ပြီးမှ ပြန်လည် အသုံးပြုနိုင်ပါမယ်။***\n"
            "📞 ***အရေးပေါ်ဆိုရင် admin ကို ဆက်သွယ်ပါ။***",
            parse_mode="Markdown"
        )
        return

    # Check for pending topups first
    if await check_pending_topup(user_id):
        await send_pending_topup_warning(update)
        return

    # Check if user has pending topup process
    if user_id in pending_topups:
        await update.message.reply_text(
            "⏳ ***Topup လုပ်ငန်းစဉ် အရင်ပြီးဆုံးပါ!***\n\n"
            "❌ ***လက်ရှိ topup လုပ်ငန်းစဉ်ကို မပြီးသေးပါ။***\n\n"
            "***လုပ်ရမည့်အရာများ***:\n"
            "***• Payment app ရွေးပြီး screenshot တင်ပါ***\n"
            "***• သို့မဟုတ် /cancel နှိပ်ပြီး ပယ်ဖျက်ပါ***\n\n"
            "💡 ***Topup ပြီးမှ order တင်နိုင်ပါမယ်။***",
            parse_mode="Markdown"
        )
        return

    args = context.args

    if len(args) != 3:
        await update.message.reply_text(
            "❌ အမှားရှိပါတယ်!\n\n"
            "***မှန်ကန်တဲ့ format***:\n"
            "/mmb gameid serverid amount\n\n"
            "***ဥပမာ***:\n"
            "`/mmb 123456789 12345 wp1`\n"
            "`/mmb 123456789 12345 86`",
            parse_mode="Markdown"
        )
        return

    game_id, server_id, amount = args

    # Validate Game ID
    if not validate_game_id(game_id):
        await update.message.reply_text(
            "❌ ***Game ID မှားနေပါတယ်!***\n\n"
            "***Game ID requirements***:\n"
            "***• ကိန်းဂဏန်းများသာ ပါရမည်။***\n"
            "***• 6-10 digits ရှိရမည်။***\n\n"
            "***ဥပမာ***: `123456789`",
            parse_mode="Markdown"
        )
        return

    # Validate Server ID
    if not validate_server_id(server_id):
        await update.message.reply_text(
            "❌ ***Server ID မှားနေပါတယ်!***\n\n"
            "***Server ID requirements***:\n"
            "***• ကိန်းဂဏန်းများသာ ပါရမည်။***\n"
            "***• 3-5 digits ရှိရမည်။***\n\n"
            "***ဥပမာ***: `8662`, `12345`",
            parse_mode="Markdown"
        )
        return

    # Check if account is banned
    if is_banned_account(game_id):
        await update.message.reply_text(
            "🚫 ***Account Ban ဖြစ်နေပါတယ်!***\n\n"
            f"🎮 Game ID: `{game_id}`\n"
            f"🌐 Server ID: `{server_id}`\n\n"
            "❌ ဒီ account မှာ diamond topup လုပ်လို့ မရပါ။\n\n"
            "***အကြောင်းရင်းများ***:\n"
            "***• Account suspended/banned ဖြစ်နေခြင်း***\n"
            "***• Invalid account pattern***\n"
            "***• MLBB မှ ပိတ်ပင်ထားခြင်း***\n\n"
            "🔄 ***အခြား account သုံးပြီး ထပ်ကြိုးစားကြည့်ပါ။***\n\n\n"
            "📞 ***ပြဿနာရှိရင် admin ကို ဆက်သွယ်ပါ။***",
            parse_mode="Markdown"
        )

        # Notify admin about banned account attempt
        admin_msg = (
            f"🚫 ***Banned Account Topup ကြိုးစားမှု***\n\n"
            f"👤 ***User:*** [{update.effective_user.first_name}](tg://user?id={user_id})\n\n"
            f"🆔 ***User ID:*** `{user_id}`\n"
            f"🎮 ***Game ID:*** `{game_id}`\n"
            f"🌐 ***Server ID:*** `{server_id}`\n"
            f"💎 ***Amount:*** {amount}\n"
            f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            "***⚠️ ဒီ account မှာ topup လုပ်လို့ မရပါ။***"
        )

        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg, parse_mode="Markdown")
        except:
            pass

        return

    price = get_price(amount)

    if not price:
        await update.message.reply_text(
            "❌ Diamond amount မှားနေပါတယ်!\n\n"
            "***ရရှိနိုင်တဲ့ amounts***:\n"
            "***• Weekly Pass:*** wp1-wp10\n\n"
            "***• Diamonds:*** 11, 22, 33, 56, 86, 112, 172, 257, 343, 429, 514, 600, 706, 878, 963, 1049, 1135, 1412, 2195, 3688, 5532, 9288, 12976",
            parse_mode="Markdown"
        )
        return

    # Get user data from MongoDB
    user_data = user_manager.get_user(user_id)
    if not user_data:
        await update.message.reply_text("❌ User data not found. Please use /start first.")
        return

    user_balance = user_data.get("balance", 0)

    if user_balance < price:
        keyboard = [[InlineKeyboardButton("💳 ငွေဖြည့်မယ်", callback_data="topup_button")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"❌ ***လက်ကျန်ငွေ မလုံလောက်ပါ!***\n\n"
            f"💰 ***လိုအပ်တဲ့ငွေ***: {price:,} MMK\n"
            f"💳 ***သင့်လက်ကျန်***: {user_balance:,} MMK\n"
            f"❗ ***လိုအပ်သေးတာ***: {price - user_balance:,} MMK\n\n"
            "***ငွေဖြည့်ရန်*** `/topup amount` ***သုံးပါ။***",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return

    # Process order with MongoDB
    order_id = f"ORD{datetime.now().strftime('%Y%m%d%H%M%S')}"
    order_data = {
        "order_id": order_id,
        "game_id": game_id,
        "server_id": server_id,
        "amount": amount,
        "price": price,
        "status": "pending",
        "timestamp": datetime.now().isoformat(),
        "user_id": user_id,
        "chat_id": update.effective_chat.id
    }

    # Deduct balance and add order in MongoDB
    new_balance = user_balance - price
    user_manager.update_user_balance(user_id, new_balance)
    user_manager.add_user_order(user_id, order_data)
    user_manager.create_order(order_data)

    # Create confirm/cancel buttons for admin
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data=f"order_confirm_{order_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"order_cancel_{order_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Get user name
    user_name = f"{update.effective_user.first_name} {update.effective_user.last_name or ''}".strip()

    # Notify admin
    admin_msg = (
        f"🔔 ***အော်ဒါအသစ်ရောက်ပါပြီ!***\n\n"
        f"📝 ***Order ID:*** `{order_id}`\n"
        f"👤 ***User Name:*** [{user_name}](tg://user?id={user_id})\n\n"
        f"🆔 ***User ID:*** `{user_id}`\n"
        f"🎮 ***Game ID:*** `{game_id}`\n"
        f"🌐 ***Server ID:*** `{server_id}`\n"
        f"💎 ***Amount:*** {amount}\n"
        f"💰 ***Price:*** {price:,} MMK\n"
        f"⏰ ***Time:*** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"📊 Status: ⏳ ***စောင့်ဆိုင်းနေသည်***"
    )

    # Send to all admins
    data = load_data()
    admin_list = data.get("admin_ids", [ADMIN_ID])
    for admin_id in admin_list:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=admin_msg,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        except:
            pass

    # Notify admin group
    try:
        bot = Bot(token=BOT_TOKEN)
        if await is_bot_admin_in_group(bot, ADMIN_GROUP_ID):
            group_msg = (
                f"🛒 ***အော်ဒါအသစ် ရောက်ပါပြီ!***\n\n"
                f"📝 ***Order ID:*** `{order_id}`\n"
                f"👤 ***User Name:*** [{user_name}](tg://user?id={user_id})\n"
                f"🎮 ***Game ID:*** `{game_id}`\n"
                f"🌐 ***Server ID:*** `{server_id}`\n"
                f"💎 ***Amount:*** {amount}\n"
                f"💰 ***Price:*** {price:,} MMK\n"
                f"⏰ ***Time:*** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"📊 ***Status:*** ⏳ စောင့်ဆိုင်းနေသည်\n\n"
                f"#NewOrder #MLBB"
            )
            await bot.send_message(chat_id=ADMIN_GROUP_ID, text=group_msg, parse_mode="Markdown")
    except Exception as e:
        pass

    await update.message.reply_text(
        f"✅ ***အော်ဒါ အောင်မြင်ပါပြီ!***\n\n"
        f"📝 ***Order ID:*** `{order_id}`\n"
        f"🎮 ***Game ID:*** `{game_id}`\n"
        f"🌐 ***Server ID:*** `{server_id}`\n"
        f"💎 ***Diamond:*** {amount}\n"
        f"💰 ***ကုန်ကျစရိတ်:*** {price:,} MMK\n"
        f"💳 ***လက်ကျန်ငွေ:*** {new_balance:,} MMK\n"
        f"📊 Status: ⏳ ***စောင့်ဆိုင်းနေသည်***\n\n"
        "⚠️ ***Admin က confirm လုပ်ပြီးမှ diamonds များ ရရှိပါမယ်။***\n"
        "📞 ***ပြဿနာရှိရင် admin ကို ဆက်သွယ်ပါ။***",
        parse_mode="Markdown"
    )

# Continue with other functions... (balance_command, topup_command, etc.)
# The rest of your existing functions will work with minor adjustments

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    # Check authorization
    load_authorized_users()
    if not is_user_authorized(user_id):
        keyboard = [[InlineKeyboardButton("👑 Contact Owner", url=f"tg://user?id={ADMIN_ID}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🚫 အသုံးပြုခွင့် မရှိပါ!\n\n"
            "Owner ထံ bot အသုံးပြုခွင့် တောင်းဆိုပါ။",
            reply_markup=reply_markup
        )
        return

    # Check if user is restricted after screenshot
    if user_id in user_states and user_states[user_id] == "waiting_approval":
        await update.message.reply_text(
            "⏳ ***Screenshot ပို့ပြီးပါပြီ!***\n\n"
            "❌ ***Admin က လက်ခံပြီးကြောင်း အတည်ပြုတဲ့အထိ commands တွေ အသုံးပြုလို့ မရပါ။***\n\n"
            "⏰ ***Admin က approve လုပ်ပြီးမှ ပြန်လည် အသုံးပြုနိုင်ပါမယ်။***\n\n"
            "📞 ***အရေးပေါ်ဆိုရင် admin ကို ဆက်သွယ်ပါ။***",
            parse_mode="Markdown"
        )
        return

    # Check if user has pending topup process
    if user_id in pending_topups:
        await update.message.reply_text(
            "⏳ ***Topup လုပ်ငန်းစဉ် ဆက်လက်လုပ်ဆောင်ပါ!***\n\n"
            "❌ ***လက်ရှိ topup လုပ်ငန်းစဉ်ကို မပြီးသေးပါ။***\n\n"
            "***လုပ်ရမည့်အရာများ***:\n"
            "***• Payment app ရွေးပြီး screenshot တင်ပါ***\n"
            "***• သို့မဟုတ် /cancel နှိပ်ပြီး ပယ်ဖျက်ပါ***\n\n"
            "💡 ***ပယ်ဖျက်ပြီးမှ အခြား commands များ အသုံးပြုနိုင်ပါမယ်။***",
            parse_mode="Markdown"
        )
        return

    # Check for pending topups in data (already submitted, waiting for approval)
    if await check_pending_topup(user_id):
        await send_pending_topup_warning(update)
        return

    # Get user data from MongoDB
    user_data = user_manager.get_user(user_id)
    if not user_data:
        await update.message.reply_text("❌ အရင်ဆုံး /start နှိပ်ပါ။")
        return

    balance = user_data.get("balance", 0)
    total_orders = len(user_data.get("orders", []))
    total_topups = len(user_data.get("topups", []))

    # Check for pending topups
    pending_topups_count = 0
    pending_amount = 0

    for topup in user_data.get("topups", []):
        if topup.get("status") == "pending":
            pending_topups_count += 1
            pending_amount += topup.get("amount", 0)

    # Escape special characters in name and username
    name = user_data.get('name', 'Unknown')
    username = user_data.get('username', 'None')

    # Remove or escape problematic characters for Markdown
    name = name.replace('*', '').replace('_', '').replace('`', '').replace('[', '').replace(']', '')
    username = username.replace('*', '').replace('_', '').replace('`', '').replace('[', '').replace(']', '')

    status_msg = ""
    if pending_topups_count > 0:
        status_msg = f"\n⏳ ***Pending Topups***: {pending_topups_count} ခု ({pending_amount:,} MMK)\n❗ ***Diamond order ထားလို့မရပါ။ Admin approve စောင့်ပါ။***"

    # Create inline keyboard with topup button
    keyboard = [[InlineKeyboardButton("💳 ငွေဖြည့်မယ်", callback_data="topup_button")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    balance_text = (
        f"💳 ***သင့်ရဲ့ Account အချက်အလက်များ***\n\n"
        f"💰 ***လက်ကျန်ငွေ***: `{balance:,} MMK`\n"
        f"📦 ***စုစုပေါင်း အော်ဒါများ***: {total_orders}\n"
        f"💳 ***စုစုပေါင်း ငွေဖြည့်မှုများ***: {total_topups}{status_msg}\n\n"
        f"***👤 နာမည်***: {name}\n"
        f"***🆔 Username***: @{username}"
    )

    # Try to get user's profile photo
    try:
        user_photos = await context.bot.get_user_profile_photos(user_id=int(user_id), limit=1)
        if user_photos.total_count > 0:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=user_photos.photos[0][0].file_id,
                caption=balance_text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                balance_text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
    except:
        await update.message.reply_text(
            balance_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

# Add other command functions here (topup_command, price_command, etc.)
# They will work similarly with MongoDB integration

def is_owner(user_id):
    """Check if user is the owner"""
    return int(user_id) == ADMIN_ID

def is_admin(user_id):
    """Check if user is any admin (owner or appointed admin)"""
    if int(user_id) == ADMIN_ID:
        return True
    data = load_data()
    admin_list = data.get("admin_ids", [])
    return int(user_id) in admin_list

# Continue with the rest of your existing functions...
# Add the remaining functions from your original code

def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN environment variable မရှိပါ!")
        return

    application = Application.builder().token(BOT_TOKEN).build()

    # Load authorized users on startup
    load_authorized_users()

    # Command handlers (add your existing handlers)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("mmb", mmb_command))
    application.add_handler(CommandHandler("balance", balance_command))
    # Add other command handlers...

    # Callback query handler
    application.add_handler(CallbackQueryHandler(button_callback))

    # Photo handler (for payment screenshots)
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # Handle all other message types
    application.add_handler(MessageHandler(
        (filters.TEXT | filters.VOICE | filters.Sticker.ALL | filters.VIDEO |
         filters.ANIMATION | filters.AUDIO | filters.Document.ALL |
         filters.FORWARDED | filters.Entity("url") | filters.POLL) & ~filters.COMMAND,
        handle_restricted_content
    ))

    print("🤖 Bot စတင်နေပါသည် - MongoDB Version")
    print("✅ MongoDB Integration Ready")
    print("🔧 Admin commands များ အသုံးပြုနိုင်ပါပြီ")

    # Run main bot
    application.run_polling()

if __name__ == "__main__":
    main()
