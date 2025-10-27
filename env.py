import os

# Load environment variables from .env file
try:
    with open('.env', 'r') as f:
        for line in f:
            if '=' in line:
                key, value = line.strip().split('=', 1)
                os.environ[key] = value
except FileNotFoundError:
    pass

# Bot configuration
BOT_TOKEN = (os.getenv("BOT_TOKEN","8257255279:AAFp6kNzbb-KGjAykevQeuteGci_uJ8Nwds"))
ADMIN_ID = int(os.getenv("ADMIN_ID", "1318826936"))
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID", "-1002356385851"))
DATA_FILE = "data.json"
