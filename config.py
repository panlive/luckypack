import os

# === Пользователи и права ===
SUPERADMIN_ID = os.getenv('SUPERADMIN_ID')
MAJOR_ID = os.getenv('MAJOR_ID')
SECRETARY_ID = os.getenv('SECRETARY_ID')
ADMINS = [SUPERADMIN_ID, MAJOR_ID, SECRETARY_ID]

# === Ключи и токены ===
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# === Ссылки на внешние ресурсы ===
YANDEX_DISK_LINK_PHOTOS = os.getenv('YANDEX_DISK_LINK_PHOTOS')
YANDEX_DISK_LINK_PRICES = os.getenv('YANDEX_DISK_LINK_PRICES')

# === Пути по умолчанию ===
PHOTO_DOWNLOAD_PATH = os.getenv('PHOTO_DOWNLOAD_PATH', '/app/data/photos/original')
VISION_TEMP_DIR = os.getenv('VISION_TEMP_DIR', '/app/data/cards/vision_temp')
PARSE_RESULTS_DIR = os.getenv('PARSE_RESULTS_DIR', '/app/data/cards/parse_results')

# === Почтовые настройки ===
EMAIL_HOST = os.getenv("EMAIL_HOST")
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

# === Разрешённые расширения файлов ===
ALLOWED_PHOTO_EXTENSIONS = [".jpg", ".jpeg", ".png"]

# === Логирование ===
LOGS_DIR = os.getenv("LOGS_DIR", "/srv/luckypack/logs")

PHOTOS_LOG = os.path.join(LOGS_DIR, "photos.log")
PARSING_LOG = os.path.join(LOGS_DIR, "parsing.log")
VISION_LOG = os.path.join(LOGS_DIR, "vision.log")
CLIENT_MSG_ANALYZER_LOG = os.path.join(LOGS_DIR, "client_message_analyzer.log")
SELECT_PRODUCTS_LOG = os.path.join(LOGS_DIR, "select_products.log")