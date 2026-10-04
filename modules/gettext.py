import json
from pathlib import Path

import modules.globals


def tr(key: str, **kwargs) -> str:
    """Çeviri anahtarı + isteğe bağlı str.format alanları (çekirdek mesajları için)."""
    s = modules.globals.translations.get(key, key)
    if not kwargs:
        return s
    try:
        return s.format(**kwargs)
    except (KeyError, ValueError):
        try:
            return key.format(**kwargs)
        except (KeyError, ValueError):
            return s


class LanguageManager:
    def __init__(self, default_language="tr"):
        self.current_language = default_language
        self.translations = {}
        self.load_language(default_language)

    def load_language(self, language_code) -> bool:
        """Dil dosyasını yükle ve modules.globals.translations ile paylaş."""
        if language_code == "en":
            self.translations = {}
            modules.globals.translations = {}
            self.current_language = language_code
            return True
        try:
            file_path = Path(__file__).parent.parent / f"locales/{language_code}.json"
            with open(file_path, "r", encoding="utf-8") as file:
                self.translations = json.load(file)
            modules.globals.translations = self.translations
            self.current_language = language_code
            return True
        except FileNotFoundError:
            print(f"Dil dosyası bulunamadı: {language_code}")
            self.translations = {}
            modules.globals.translations = {}
            return False

    def _(self, key, default=None) -> str:
        """Arayüz metinleri için çeviri."""
        return self.translations.get(key, default if default else key)