"""
Internationalization Service
国际化服务

Phase 5: 生态扩展期 (Ecosystem Expansion Period)
Provides multi-language and multi-currency support
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession


class Language(Enum):
    """Supported languages"""
    ZH_CN = "zh_CN"  # 简体中文
    ZH_TW = "zh_TW"  # 繁体中文
    EN_US = "en_US"  # English (US)
    EN_GB = "en_GB"  # English (UK)
    JA_JP = "ja_JP"  # 日本語
    KO_KR = "ko_KR"  # 한국어
    TH_TH = "th_TH"  # ไทย
    VI_VN = "vi_VN"  # Tiếng Việt


class Currency(Enum):
    """Supported currencies"""
    CNY = "CNY"  # 人民币
    USD = "USD"  # 美元
    EUR = "EUR"  # 欧元
    GBP = "GBP"  # 英镑
    JPY = "JPY"  # 日元
    KRW = "KRW"  # 韩元
    THB = "THB"  # 泰铢
    VND = "VND"  # 越南盾


@dataclass
class LocalizationConfig:
    """Localization configuration"""
    locale: str  # e.g., "zh_CN"
    language: Language
    currency: Currency
    timezone: str  # e.g., "Asia/Shanghai"
    date_format: str  # e.g., "YYYY-MM-DD"
    time_format: str  # e.g., "HH:mm:ss"
    number_format: str  # e.g., "1,234.56"


@dataclass
class Translation:
    """Translation entry"""
    key: str
    language: Language
    value: str
    context: Optional[str]  # Context for translators


class InternationalizationService:
    """
    Internationalization Service
    国际化服务

    Provides:
    1. Multi-language support (8 languages)
    2. Multi-currency support (8 currencies)
    3. Localization (date, time, number formats)
    4. Currency conversion
    5. Regional customization

    Key features:
    - Dynamic language switching
    - Real-time currency conversion
    - Locale-specific formatting
    - Translation management
    - Regional best practices
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        # Store translations
        self.translations: Dict[str, Dict[Language, str]] = {}
        # Store exchange rates (base: CNY)
        self.exchange_rates: Dict[Currency, float] = {
            Currency.CNY: 1.0,
            Currency.USD: 0.14,  # 1 CNY = 0.14 USD
            Currency.EUR: 0.13,
            Currency.GBP: 0.11,
            Currency.JPY: 20.0,
            Currency.KRW: 185.0,
            Currency.THB: 4.8,
            Currency.VND: 3500.0
        }
        # Store localization configs
        self.localization_configs: Dict[str, LocalizationConfig] = {}
        # Initialize default translations and configs
        self._initialize_defaults()

    def _initialize_defaults(self):
        """Initialize default translations and configs"""
        # Add common translations
        self.add_translation("app.name", Language.ZH_CN, "智链OS")
        self.add_translation("app.name", Language.EN_US, "Zhilian OS")
        self.add_translation("app.name", Language.JA_JP, "智鎖OS")

        self.add_translation("menu.dashboard", Language.ZH_CN, "仪表盘")
        self.add_translation("menu.dashboard", Language.EN_US, "Dashboard")
        self.add_translation("menu.dashboard", Language.JA_JP, "ダッシュボード")

        self.add_translation("menu.orders", Language.ZH_CN, "订单")
        self.add_translation("menu.orders", Language.EN_US, "Orders")
        self.add_translation("menu.orders", Language.JA_JP, "注文")

        # Add localization configs
        self.localization_configs["zh_CN"] = LocalizationConfig(
            locale="zh_CN",
            language=Language.ZH_CN,
            currency=Currency.CNY,
            timezone="Asia/Shanghai",
            date_format="YYYY-MM-DD",
            time_format="HH:mm:ss",
            number_format="1,234.56"
        )

        self.localization_configs["en_US"] = LocalizationConfig(
            locale="en_US",
            language=Language.EN_US,
            currency=Currency.USD,
            timezone="America/New_York",
            date_format="MM/DD/YYYY",
            time_format="hh:mm:ss A",
            number_format="1,234.56"
        )

        self.localization_configs["ja_JP"] = LocalizationConfig(
            locale="ja_JP",
            language=Language.JA_JP,
            currency=Currency.JPY,
            timezone="Asia/Tokyo",
            date_format="YYYY年MM月DD日",
            time_format="HH:mm:ss",
            number_format="1,234"
        )

    def add_translation(
        self,
        key: str,
        language: Language,
        value: str,
        context: Optional[str] = None
    ):
        """
        Add translation
        添加翻译

        Args:
            key: Translation key
            language: Target language
            value: Translated value
            context: Context for translators
        """
        if key not in self.translations:
            self.translations[key] = {}

        self.translations[key][language] = value

    def get_translation(
        self,
        key: str,
        language: Language,
        fallback: Optional[str] = None
    ) -> str:
        """
        Get translation
        获取翻译

        Args:
            key: Translation key
            language: Target language
            fallback: Fallback value if translation not found

        Returns:
            Translated string
        """
        if key in self.translations and language in self.translations[key]:
            return self.translations[key][language]

        # Try fallback to English
        if language != Language.EN_US and Language.EN_US in self.translations.get(key, {}):
            return self.translations[key][Language.EN_US]

        # Return fallback or key
        return fallback if fallback else key

    def translate_dict(
        self,
        data: Dict[str, Any],
        language: Language,
        keys_to_translate: List[str]
    ) -> Dict[str, Any]:
        """
        Translate dictionary values
        翻译字典值

        Args:
            data: Dictionary to translate
            language: Target language
            keys_to_translate: Keys to translate

        Returns:
            Translated dictionary
        """
        translated = data.copy()

        for key in keys_to_translate:
            if key in translated:
                translation_key = f"data.{key}.{translated[key]}"
                translated[key] = self.get_translation(
                    translation_key,
                    language,
                    fallback=translated[key]
                )

        return translated

    def convert_currency(
        self,
        amount: float,
        from_currency: Currency,
        to_currency: Currency
    ) -> float:
        """
        Convert currency
        货币转换

        Args:
            amount: Amount to convert
            from_currency: Source currency
            to_currency: Target currency

        Returns:
            Converted amount
        """
        if from_currency == to_currency:
            return amount

        # Convert to CNY first, then to target currency
        amount_in_cny = amount / self.exchange_rates[from_currency]
        converted_amount = amount_in_cny * self.exchange_rates[to_currency]

        return round(converted_amount, 2)

    def format_currency(
        self,
        amount: float,
        currency: Currency,
        locale: str = "zh_CN"
    ) -> str:
        """
        Format currency
        格式化货币

        Args:
            amount: Amount to format
            currency: Currency
            locale: Locale for formatting

        Returns:
            Formatted currency string
        """
        # Simplified formatting
        currency_symbols = {
            Currency.CNY: "¥",
            Currency.USD: "$",
            Currency.EUR: "€",
            Currency.GBP: "£",
            Currency.JPY: "¥",
            Currency.KRW: "₩",
            Currency.THB: "฿",
            Currency.VND: "₫"
        }

        symbol = currency_symbols.get(currency, "")

        # Format based on locale
        if locale == "zh_CN":
            return f"{symbol}{amount:,.2f}"
        elif locale == "en_US":
            return f"{symbol}{amount:,.2f}"
        elif locale == "ja_JP":
            return f"{symbol}{int(amount):,}"
        else:
            return f"{symbol}{amount:,.2f}"

    def format_date(
        self,
        date: datetime,
        locale: str = "zh_CN"
    ) -> str:
        """
        Format date
        格式化日期

        Args:
            date: Date to format
            locale: Locale for formatting

        Returns:
            Formatted date string
        """
        config = self.localization_configs.get(locale)
        if not config:
            config = self.localization_configs["zh_CN"]

        # Simplified formatting
        if locale == "zh_CN":
            return date.strftime("%Y-%m-%d")
        elif locale == "en_US":
            return date.strftime("%m/%d/%Y")
        elif locale == "ja_JP":
            return date.strftime("%Y年%m月%d日")
        else:
            return date.strftime("%Y-%m-%d")

    def format_number(
        self,
        number: float,
        locale: str = "zh_CN"
    ) -> str:
        """
        Format number
        格式化数字

        Args:
            number: Number to format
            locale: Locale for formatting

        Returns:
            Formatted number string
        """
        # Simplified formatting
        if locale == "ja_JP":
            return f"{int(number):,}"
        else:
            return f"{number:,.2f}"

    def get_localization_config(
        self,
        locale: str
    ) -> Optional[LocalizationConfig]:
        """
        Get localization configuration
        获取本地化配置

        Args:
            locale: Locale identifier

        Returns:
            Localization configuration
        """
        return self.localization_configs.get(locale)

    def get_supported_languages(self) -> List[Dict[str, str]]:
        """
        Get supported languages
        获取支持的语言

        Returns:
            List of supported languages
        """
        return [
            {"code": "zh_CN", "name": "简体中文", "native_name": "简体中文"},
            {"code": "zh_TW", "name": "繁体中文", "native_name": "繁體中文"},
            {"code": "en_US", "name": "English (US)", "native_name": "English (US)"},
            {"code": "en_GB", "name": "English (UK)", "native_name": "English (UK)"},
            {"code": "ja_JP", "name": "Japanese", "native_name": "日本語"},
            {"code": "ko_KR", "name": "Korean", "native_name": "한국어"},
            {"code": "th_TH", "name": "Thai", "native_name": "ไทย"},
            {"code": "vi_VN", "name": "Vietnamese", "native_name": "Tiếng Việt"}
        ]

    def get_supported_currencies(self) -> List[Dict[str, Any]]:
        """
        Get supported currencies
        获取支持的货币

        Returns:
            List of supported currencies with exchange rates
        """
        return [
            {"code": "CNY", "name": "Chinese Yuan", "symbol": "¥", "rate": self.exchange_rates[Currency.CNY]},
            {"code": "USD", "name": "US Dollar", "symbol": "$", "rate": self.exchange_rates[Currency.USD]},
            {"code": "EUR", "name": "Euro", "symbol": "€", "rate": self.exchange_rates[Currency.EUR]},
            {"code": "GBP", "name": "British Pound", "symbol": "£", "rate": self.exchange_rates[Currency.GBP]},
            {"code": "JPY", "name": "Japanese Yen", "symbol": "¥", "rate": self.exchange_rates[Currency.JPY]},
            {"code": "KRW", "name": "Korean Won", "symbol": "₩", "rate": self.exchange_rates[Currency.KRW]},
            {"code": "THB", "name": "Thai Baht", "symbol": "฿", "rate": self.exchange_rates[Currency.THB]},
            {"code": "VND", "name": "Vietnamese Dong", "symbol": "₫", "rate": self.exchange_rates[Currency.VND]}
        ]

    def update_exchange_rate(
        self,
        currency: Currency,
        rate: float
    ):
        """
        Update exchange rate
        更新汇率

        Args:
            currency: Currency
            rate: Exchange rate (relative to CNY)
        """
        self.exchange_rates[currency] = rate
