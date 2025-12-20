#!/usr/bin/env python3
"""
Multi-Exchange AMM Bot
A single-file Automated Market Maker for NonKYC, Bitstorage, and Exbitron exchanges.

Maximizes trading volume and order book availability by maintaining
deep liquidity on both sides of the order book.

Usage:
    1. Install dependencies: pip install aiohttp
    2. Configure your API keys in config.json (copy from config.example.json)
    3. Run: python amm_bot.py

    Or use the launcher scripts:
    - Linux/macOS: ./run_bot.sh --setup && ./run_bot.sh
    - Windows: run_bot.bat --setup && run_bot.bat

Supported Platforms: Linux, macOS, Windows
Python Version: 3.8+
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import platform
import signal
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

# =============================================================================
# VERSION AND PLATFORM CHECKS
# =============================================================================

MIN_PYTHON_VERSION = (3, 8)
__version__ = "1.0.0"

if sys.version_info < MIN_PYTHON_VERSION:
    print(f"ERROR: Python {MIN_PYTHON_VERSION[0]}.{MIN_PYTHON_VERSION[1]}+ is required.")
    print(f"Current version: {sys.version_info.major}.{sys.version_info.minor}")
    sys.exit(1)

IS_WINDOWS = platform.system() == "Windows"

try:
    import aiohttp
except ImportError:
    print("ERROR: aiohttp not installed. Run: pip install aiohttp")
    sys.exit(1)


# =============================================================================
# CONFIGURATION - EDIT THIS SECTION
# =============================================================================

CONFIG = {
    # Global Settings
    "dry_run": True,  # Set to False for live trading
    "update_interval_seconds": 15,  # How often to refresh orders
    "log_level": "INFO",  # DEBUG, INFO, WARNING, ERROR
    
    # Exchange Credentials
    "exchanges": {
        "nonkyc": {
            "enabled": False,  # Set to True to enable
            "api_key": "YOUR_NONKYC_API_KEY",
            "api_secret": "YOUR_NONKYC_API_SECRET",
            "base_url": "https://api.nonkyc.io/api/v2",
            "requests_per_second": 5.0,
        },
        "bitstorage": {
            "enabled": False,  # Set to True to enable
            "api_key": "YOUR_BITSTORAGE_API_KEY",
            "api_secret": "YOUR_BITSTORAGE_API_SECRET",
            "base_url": "https://bitstorage.finance/api/v2/peatio",
            "requests_per_second": 5.0,
        },
        "exbitron": {
            "enabled": False,  # Set to True to enable
            "api_key": "YOUR_EXBITRON_API_KEY",
            "api_secret": "YOUR_EXBITRON_API_SECRET",
            "base_url": "https://app.exbitron.com/api/v2/peatio",
            "requests_per_second": 5.0,
        },
    },
    
    # Markets to Trade (configure for each exchange)
    "markets": {
        "nonkyc": [
            {
                "symbol": "btcusdt",
                "base_currency": "btc",
                "quote_currency": "usdt",
                "num_orders_per_side": 10,
                "order_spacing_percent": 0.3,
                "min_order_size": 0.0001,
                "max_order_size": 0.1,
                "total_base_allocation": 0.5,
                "total_quote_allocation": 5000.0,
                "min_spread_percent": 0.2,
                "target_spread_percent": 0.5,
                "inventory_target_ratio": 0.5,
                "inventory_skew_factor": 0.1,
            },
        ],
        "bitstorage": [
            {
                "symbol": "btcusdt",
                "base_currency": "btc",
                "quote_currency": "usdt",
                "num_orders_per_side": 10,
                "order_spacing_percent": 0.3,
                "min_order_size": 0.0001,
                "max_order_size": 0.1,
                "total_base_allocation": 0.5,
                "total_quote_allocation": 5000.0,
                "min_spread_percent": 0.2,
                "target_spread_percent": 0.5,
                "inventory_target_ratio": 0.5,
                "inventory_skew_factor": 0.1,
            },
        ],
        "exbitron": [
            {
                "symbol": "btcusdt",
                "base_currency": "btc",
                "quote_currency": "usdt",
                "num_orders_per_side": 10,
                "order_spacing_percent": 0.3,
                "min_order_size": 0.0001,
                "max_order_size": 0.1,
                "total_base_allocation": 0.5,
                "total_quote_allocation": 5000.0,
                "min_spread_percent": 0.2,
                "target_spread_percent": 0.5,
                "inventory_target_ratio": 0.5,
                "inventory_skew_factor": 0.1,
            },
        ],
    },
}


# =============================================================================
# CONFIGURATION LOADING
# =============================================================================

def get_config_path() -> Optional[Path]:
    """Find config.json in the script directory or current directory."""
    script_dir = Path(__file__).parent

    # Check script directory first
    config_path = script_dir / "config.json"
    if config_path.exists():
        return config_path

    # Check current directory
    config_path = Path.cwd() / "config.json"
    if config_path.exists():
        return config_path

    return None


def load_config() -> Dict:
    """Load configuration from config.json or use defaults."""
    config_path = get_config_path()

    if config_path:
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                loaded_config = json.load(f)

            # Remove any comment fields
            if '_comment' in loaded_config:
                del loaded_config['_comment']

            # Merge with defaults (loaded config takes precedence)
            merged = CONFIG.copy()

            # Deep merge for nested dicts
            for key, value in loaded_config.items():
                if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                    merged[key].update(value)
                else:
                    merged[key] = value

            print(f"Loaded configuration from: {config_path}")
            return merged

        except json.JSONDecodeError as e:
            print(f"ERROR: Invalid JSON in config file: {e}")
            print("Using default configuration.")
        except Exception as e:
            print(f"ERROR: Failed to load config file: {e}")
            print("Using default configuration.")

    return CONFIG


# Load configuration (use external file if available)
ACTIVE_CONFIG = load_config()


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def utc_now() -> datetime:
    """Get current UTC time (compatible with Python 3.8-3.12+)."""
    return datetime.now(timezone.utc)


def format_timestamp(dt: datetime) -> str:
    """Format datetime for logging."""
    return dt.strftime('%Y-%m-%d %H:%M:%S UTC')


# =============================================================================
# LOGGING SETUP
# =============================================================================

def setup_logging(config: Dict) -> logging.Logger:
    """Configure logging based on settings."""
    log_level = getattr(logging, config.get("log_level", "INFO").upper(), logging.INFO)
    log_format = '%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'

    handlers: List[logging.Handler] = []

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(log_format, date_format))
    handlers.append(console_handler)

    # File handler (if configured)
    log_file = config.get("log_file")
    if log_file:
        try:
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setFormatter(logging.Formatter(log_format, date_format))
            handlers.append(file_handler)
        except Exception as e:
            print(f"Warning: Could not create log file {log_file}: {e}")

    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format=log_format,
        datefmt=date_format,
        handlers=handlers,
        force=True  # Override any existing configuration
    )

    return logging.getLogger("AMM")


logger = setup_logging(ACTIVE_CONFIG)


# =============================================================================
# DATA MODELS
# =============================================================================

class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    LIMIT = "limit"
    MARKET = "market"


class OrderStatus(Enum):
    PENDING = "pending"
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"


@dataclass
class OrderBookLevel:
    price: Decimal
    quantity: Decimal
    
    @property
    def value(self) -> Decimal:
        return self.price * self.quantity


@dataclass
class OrderBook:
    symbol: str
    bids: List[OrderBookLevel] = field(default_factory=list)
    asks: List[OrderBookLevel] = field(default_factory=list)
    timestamp: datetime = field(default_factory=utc_now)
    
    @property
    def best_bid(self) -> Optional[Decimal]:
        return self.bids[0].price if self.bids else None
    
    @property
    def best_ask(self) -> Optional[Decimal]:
        return self.asks[0].price if self.asks else None
    
    @property
    def mid_price(self) -> Optional[Decimal]:
        if self.best_bid and self.best_ask:
            return (self.best_bid + self.best_ask) / 2
        return self.best_bid or self.best_ask
    
    @property
    def spread(self) -> Optional[Decimal]:
        if self.best_bid and self.best_ask:
            return self.best_ask - self.best_bid
        return None
    
    @property
    def spread_percent(self) -> Optional[Decimal]:
        if self.mid_price and self.spread:
            return (self.spread / self.mid_price) * 100
        return None


@dataclass
class Order:
    id: Optional[str] = None
    symbol: str = ""
    side: OrderSide = OrderSide.BUY
    order_type: OrderType = OrderType.LIMIT
    price: Decimal = Decimal("0")
    quantity: Decimal = Decimal("0")
    filled_quantity: Decimal = Decimal("0")
    remaining_quantity: Decimal = Decimal("0")
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = field(default_factory=utc_now)
    exchange: str = ""
    
    @property
    def is_active(self) -> bool:
        return self.status in (OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED)


@dataclass
class Balance:
    currency: str
    available: Decimal
    locked: Decimal
    
    @property
    def total(self) -> Decimal:
        return self.available + self.locked


@dataclass
class AccountBalances:
    balances: Dict[str, Balance] = field(default_factory=dict)
    
    def get_available(self, currency: str) -> Decimal:
        currency = currency.lower()
        if currency in self.balances:
            return self.balances[currency].available
        return Decimal("0")


@dataclass
class MarketConfig:
    symbol: str
    base_currency: str
    quote_currency: str
    num_orders_per_side: int = 10
    order_spacing_percent: float = 0.5
    min_order_size: float = 0.001
    max_order_size: float = 1.0
    total_base_allocation: float = 1.0
    total_quote_allocation: float = 1000.0
    min_spread_percent: float = 0.5
    target_spread_percent: float = 1.0
    inventory_target_ratio: float = 0.5
    inventory_skew_factor: float = 0.1


@dataclass
class OrderLadder:
    buy_prices: List[Decimal] = field(default_factory=list)
    buy_quantities: List[Decimal] = field(default_factory=list)
    sell_prices: List[Decimal] = field(default_factory=list)
    sell_quantities: List[Decimal] = field(default_factory=list)
    mid_price: Decimal = Decimal("0")


# =============================================================================
# RATE LIMITER
# =============================================================================

class RateLimiter:
    """
    Async-safe rate limiter for API requests.

    Note: The asyncio.Lock is created lazily on first acquire() to ensure
    it's created in the correct event loop context.
    """

    def __init__(self, requests_per_second: float = 5.0):
        self.requests_per_second = requests_per_second
        self.min_interval = 1.0 / requests_per_second
        self.last_request_time = 0.0
        self._lock: Optional[asyncio.Lock] = None

    def _get_lock(self) -> asyncio.Lock:
        """Get or create the lock (must be called from async context)."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def acquire(self) -> None:
        """Acquire rate limit slot, waiting if necessary."""
        async with self._get_lock():
            now = time.time()
            elapsed = now - self.last_request_time
            if elapsed < self.min_interval:
                await asyncio.sleep(self.min_interval - elapsed)
            self.last_request_time = time.time()


# =============================================================================
# EXCHANGE CONNECTOR BASE
# =============================================================================

class ExchangeConnector(ABC):
    def __init__(self, name: str, config: Dict):
        self.name = name
        self.api_key = config["api_key"]
        self.api_secret = config["api_secret"]
        self.base_url = config["base_url"].rstrip('/')
        self.rate_limiter = RateLimiter(config.get("requests_per_second", 5.0))
        self.session: Optional[aiohttp.ClientSession] = None
        self.logger = logging.getLogger(f"AMM.{name}")
        self._markets_cache: Dict[str, Dict] = {}
    
    async def start(self):
        self.session = aiohttp.ClientSession()
        self.logger.info(f"Started {self.name} connector")
    
    async def stop(self):
        if self.session:
            await self.session.close()
        self.logger.info(f"Stopped {self.name} connector")
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        auth: bool = False
    ) -> Any:
        await self.rate_limiter.acquire()
        
        url = f"{self.base_url}{endpoint}"
        headers = {"Content-Type": "application/json"}
        
        if auth:
            auth_headers = self._generate_auth_headers(method, endpoint, params, data)
            headers.update(auth_headers)
        
        try:
            async with self.session.request(
                method,
                url,
                params=params,
                json=data if method in ['POST', 'PUT', 'PATCH'] else None,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                response_text = await response.text()
                
                if response.status >= 400:
                    self.logger.error(f"API error: {response.status} - {response_text}")
                    raise Exception(f"API error {response.status}: {response_text}")
                
                if response_text:
                    return json.loads(response_text)
                return {}
                
        except asyncio.TimeoutError:
            self.logger.error(f"Request timeout: {endpoint}")
            raise
        except Exception as e:
            self.logger.error(f"Request failed: {e}")
            raise
    
    @abstractmethod
    def _generate_auth_headers(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict],
        data: Optional[Dict]
    ) -> Dict[str, str]:
        pass
    
    @abstractmethod
    async def get_order_book(self, symbol: str, limit: int = 50) -> OrderBook:
        pass
    
    @abstractmethod
    async def get_balances(self) -> AccountBalances:
        pass
    
    @abstractmethod
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        pass
    
    @abstractmethod
    async def create_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: Decimal,
        price: Optional[Decimal] = None
    ) -> Order:
        pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> bool:
        pass
    
    @abstractmethod
    async def cancel_all_orders(self, symbol: Optional[str] = None) -> int:
        pass
    
    def _parse_decimal(self, value: Any) -> Decimal:
        """Parse a value to Decimal safely."""
        if value is None:
            return Decimal("0")
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as e:
            self.logger.debug(f"Failed to parse decimal value '{value}': {e}")
            return Decimal("0")

    def _parse_timestamp(self, value: Any) -> datetime:
        """Parse a timestamp value to datetime safely."""
        if isinstance(value, datetime):
            # Ensure timezone awareness
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value
        if isinstance(value, (int, float)):
            try:
                # Handle milliseconds vs seconds
                if value > 1e12:
                    value = value / 1000
                return datetime.fromtimestamp(value, tz=timezone.utc)
            except (ValueError, OSError, OverflowError) as e:
                self.logger.debug(f"Failed to parse timestamp value '{value}': {e}")
                return utc_now()
        if isinstance(value, str):
            try:
                # Handle ISO format with Z suffix
                return datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError as e:
                self.logger.debug(f"Failed to parse timestamp string '{value}': {e}")
                return utc_now()
        return utc_now()

    def _hmac_sha256(self, message: str) -> str:
        """Generate HMAC-SHA256 signature."""
        return hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    def round_price(self, price: Decimal, precision: int = 8) -> Decimal:
        """Round price down to specified precision (avoids overpaying)."""
        if precision < 0:
            precision = 0
        quantize_str = '0.' + '0' * precision if precision > 0 else '1'
        return price.quantize(Decimal(quantize_str), rounding=ROUND_DOWN)

    def round_quantity(self, quantity: Decimal, precision: int = 8) -> Decimal:
        """Round quantity down to specified precision (avoids overselling)."""
        if precision < 0:
            precision = 0
        quantize_str = '0.' + '0' * precision if precision > 0 else '1'
        return quantity.quantize(Decimal(quantize_str), rounding=ROUND_DOWN)


# =============================================================================
# NONKYC CONNECTOR
# =============================================================================

class NonKYCConnector(ExchangeConnector):
    """Connector for NonKYC.io exchange."""
    
    def __init__(self, config: Dict):
        super().__init__("nonkyc", config)
    
    def _generate_auth_headers(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict],
        data: Optional[Dict]
    ) -> Dict[str, str]:
        nonce = str(int(time.time() * 1000))
        body_str = ""
        if data:
            body_str = json.dumps(data, separators=(',', ':'))
        
        payload = f"{nonce}{method.upper()}{endpoint}{body_str}"
        signature = self._hmac_sha256(payload)
        
        return {
            "X-Auth-Apikey": self.api_key,
            "X-Auth-Nonce": nonce,
            "X-Auth-Signature": signature,
        }
    
    async def get_order_book(self, symbol: str, limit: int = 50) -> OrderBook:
        response = await self._request(
            "GET",
            f"/public/markets/{symbol}/depth",
            params={"limit": limit}
        )
        
        bids = [
            OrderBookLevel(
                price=self._parse_decimal(level[0]),
                quantity=self._parse_decimal(level[1])
            )
            for level in response.get("bids", [])
        ]
        
        asks = [
            OrderBookLevel(
                price=self._parse_decimal(level[0]),
                quantity=self._parse_decimal(level[1])
            )
            for level in response.get("asks", [])
        ]
        
        return OrderBook(symbol=symbol, bids=bids, asks=asks)
    
    async def get_balances(self) -> AccountBalances:
        response = await self._request("GET", "/account/balances", auth=True)
        
        balances = {}
        for balance_data in response:
            currency = balance_data.get("currency", "").lower()
            balances[currency] = Balance(
                currency=currency,
                available=self._parse_decimal(balance_data.get("balance")),
                locked=self._parse_decimal(balance_data.get("locked"))
            )
        
        return AccountBalances(balances=balances)
    
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        params = {"state": "wait", "limit": 100}
        if symbol:
            params["market"] = symbol
        
        response = await self._request("GET", "/market/orders", params=params, auth=True)
        
        orders = []
        for order_data in response:
            orders.append(self._parse_order(order_data))
        
        return orders
    
    async def create_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: Decimal,
        price: Optional[Decimal] = None
    ) -> Order:
        data = {
            "market": symbol,
            "side": side.value,
            "volume": str(self.round_quantity(quantity)),
            "ord_type": order_type.value
        }
        
        if order_type == OrderType.LIMIT and price is not None:
            data["price"] = str(self.round_price(price))
        
        response = await self._request("POST", "/market/orders", data=data, auth=True)
        return self._parse_order(response)
    
    async def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> bool:
        try:
            await self._request("POST", f"/market/orders/{order_id}/cancel", auth=True)
            return True
        except Exception as e:
            self.logger.error(f"Failed to cancel order {order_id}: {e}")
            return False
    
    async def cancel_all_orders(self, symbol: Optional[str] = None) -> int:
        data = {}
        if symbol:
            data["market"] = symbol
        
        try:
            response = await self._request("POST", "/market/orders/cancel", data=data, auth=True)
            if isinstance(response, list):
                return len(response)
            return 0
        except Exception as e:
            self.logger.error(f"Failed to cancel all orders: {e}")
            return 0
    
    def _parse_order(self, order_data: Dict) -> Order:
        status_map = {
            "wait": OrderStatus.OPEN,
            "pending": OrderStatus.PENDING,
            "done": OrderStatus.FILLED,
            "cancel": OrderStatus.CANCELLED,
        }
        
        return Order(
            id=str(order_data.get("id")),
            symbol=order_data.get("market", ""),
            side=OrderSide.BUY if order_data.get("side") == "buy" else OrderSide.SELL,
            order_type=OrderType.LIMIT if order_data.get("ord_type") == "limit" else OrderType.MARKET,
            price=self._parse_decimal(order_data.get("price")),
            quantity=self._parse_decimal(order_data.get("origin_volume")),
            filled_quantity=self._parse_decimal(order_data.get("executed_volume")),
            remaining_quantity=self._parse_decimal(order_data.get("remaining_volume")),
            status=status_map.get(order_data.get("state", ""), OrderStatus.PENDING),
            created_at=self._parse_timestamp(order_data.get("created_at")),
            exchange=self.name
        )


# =============================================================================
# BITSTORAGE CONNECTOR
# =============================================================================

class BitstorageConnector(ExchangeConnector):
    """Connector for Bitstorage.finance exchange."""
    
    def __init__(self, config: Dict):
        super().__init__("bitstorage", config)
    
    def _generate_auth_headers(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict],
        data: Optional[Dict]
    ) -> Dict[str, str]:
        nonce = str(int(time.time() * 1000))
        
        query_string = ""
        if params:
            sorted_params = sorted(params.items())
            query_string = "&".join(f"{k}={v}" for k, v in sorted_params)
        
        payload = f"{nonce}{method.upper()}{endpoint}"
        if query_string:
            payload += f"?{query_string}"
        if data:
            payload += json.dumps(data, separators=(',', ':'))
        
        signature = self._hmac_sha256(payload)
        
        return {
            "X-Auth-Apikey": self.api_key,
            "X-Auth-Nonce": nonce,
            "X-Auth-Signature": signature,
        }
    
    async def get_order_book(self, symbol: str, limit: int = 50) -> OrderBook:
        response = await self._request(
            "GET",
            f"/public/markets/{symbol}/depth",
            params={"limit": limit}
        )
        
        bids = [
            OrderBookLevel(
                price=self._parse_decimal(level[0]),
                quantity=self._parse_decimal(level[1])
            )
            for level in response.get("bids", [])
        ]
        
        asks = [
            OrderBookLevel(
                price=self._parse_decimal(level[0]),
                quantity=self._parse_decimal(level[1])
            )
            for level in response.get("asks", [])
        ]
        
        return OrderBook(symbol=symbol, bids=bids, asks=asks)
    
    async def get_balances(self) -> AccountBalances:
        response = await self._request("GET", "/account/balances", auth=True)
        
        balances = {}
        for balance_data in response:
            currency = balance_data.get("currency", "").lower()
            balances[currency] = Balance(
                currency=currency,
                available=self._parse_decimal(balance_data.get("balance")),
                locked=self._parse_decimal(balance_data.get("locked"))
            )
        
        return AccountBalances(balances=balances)
    
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        params = {"state": "wait", "limit": 100}
        if symbol:
            params["market"] = symbol
        
        response = await self._request("GET", "/market/orders", params=params, auth=True)
        
        orders = []
        for order_data in response:
            orders.append(self._parse_order(order_data))
        
        return orders
    
    async def create_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: Decimal,
        price: Optional[Decimal] = None
    ) -> Order:
        data = {
            "market": symbol,
            "side": side.value,
            "volume": str(self.round_quantity(quantity)),
            "ord_type": order_type.value
        }
        
        if order_type == OrderType.LIMIT and price is not None:
            data["price"] = str(self.round_price(price))
        
        response = await self._request("POST", "/market/orders", data=data, auth=True)
        return self._parse_order(response)
    
    async def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> bool:
        try:
            await self._request("POST", f"/market/orders/{order_id}/cancel", auth=True)
            return True
        except Exception as e:
            self.logger.error(f"Failed to cancel order {order_id}: {e}")
            return False
    
    async def cancel_all_orders(self, symbol: Optional[str] = None) -> int:
        data = {}
        if symbol:
            data["market"] = symbol
        
        try:
            response = await self._request("POST", "/market/orders/cancel", data=data, auth=True)
            if isinstance(response, list):
                return len(response)
            return 0
        except Exception as e:
            self.logger.error(f"Failed to cancel all orders: {e}")
            return 0
    
    def _parse_order(self, order_data: Dict) -> Order:
        status_map = {
            "wait": OrderStatus.OPEN,
            "pending": OrderStatus.PENDING,
            "done": OrderStatus.FILLED,
            "cancel": OrderStatus.CANCELLED,
        }
        
        return Order(
            id=str(order_data.get("id")),
            symbol=order_data.get("market", ""),
            side=OrderSide.BUY if order_data.get("side") == "buy" else OrderSide.SELL,
            order_type=OrderType.LIMIT if order_data.get("ord_type") == "limit" else OrderType.MARKET,
            price=self._parse_decimal(order_data.get("price")),
            quantity=self._parse_decimal(order_data.get("origin_volume")),
            filled_quantity=self._parse_decimal(order_data.get("executed_volume")),
            remaining_quantity=self._parse_decimal(order_data.get("remaining_volume")),
            status=status_map.get(order_data.get("state", ""), OrderStatus.PENDING),
            created_at=self._parse_timestamp(order_data.get("created_at")),
            exchange=self.name
        )


# =============================================================================
# EXBITRON CONNECTOR
# =============================================================================

class ExbitronConnector(ExchangeConnector):
    """Connector for Exbitron.com exchange."""
    
    def __init__(self, config: Dict):
        super().__init__("exbitron", config)
    
    def _generate_auth_headers(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict],
        data: Optional[Dict]
    ) -> Dict[str, str]:
        nonce = str(int(time.time() * 1000))
        
        query_string = ""
        if params:
            sorted_params = sorted(params.items())
            query_string = "&".join(f"{k}={v}" for k, v in sorted_params)
        
        payload = f"{nonce}{method.upper()}{endpoint}"
        if query_string:
            payload += f"?{query_string}"
        if data:
            payload += json.dumps(data, separators=(',', ':'))
        
        signature = self._hmac_sha256(payload)
        
        return {
            "X-Auth-Apikey": self.api_key,
            "X-Auth-Nonce": nonce,
            "X-Auth-Signature": signature,
        }
    
    async def get_order_book(self, symbol: str, limit: int = 50) -> OrderBook:
        response = await self._request(
            "GET",
            f"/public/markets/{symbol}/depth",
            params={"limit": limit}
        )
        
        bids = [
            OrderBookLevel(
                price=self._parse_decimal(level[0]),
                quantity=self._parse_decimal(level[1])
            )
            for level in response.get("bids", [])
        ]
        
        asks = [
            OrderBookLevel(
                price=self._parse_decimal(level[0]),
                quantity=self._parse_decimal(level[1])
            )
            for level in response.get("asks", [])
        ]
        
        return OrderBook(symbol=symbol, bids=bids, asks=asks)
    
    async def get_balances(self) -> AccountBalances:
        response = await self._request("GET", "/account/balances", auth=True)
        
        balances = {}
        for balance_data in response:
            currency = balance_data.get("currency", "").lower()
            balances[currency] = Balance(
                currency=currency,
                available=self._parse_decimal(balance_data.get("balance")),
                locked=self._parse_decimal(balance_data.get("locked"))
            )
        
        return AccountBalances(balances=balances)
    
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        params = {"state": "wait", "limit": 100}
        if symbol:
            params["market"] = symbol
        
        response = await self._request("GET", "/market/orders", params=params, auth=True)
        
        orders = []
        for order_data in response:
            orders.append(self._parse_order(order_data))
        
        return orders
    
    async def create_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: Decimal,
        price: Optional[Decimal] = None
    ) -> Order:
        data = {
            "market": symbol,
            "side": side.value,
            "volume": str(self.round_quantity(quantity)),
            "ord_type": order_type.value
        }
        
        if order_type == OrderType.LIMIT and price is not None:
            data["price"] = str(self.round_price(price))
        
        response = await self._request("POST", "/market/orders", data=data, auth=True)
        return self._parse_order(response)
    
    async def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> bool:
        try:
            await self._request("POST", f"/market/orders/{order_id}/cancel", auth=True)
            return True
        except Exception as e:
            self.logger.error(f"Failed to cancel order {order_id}: {e}")
            return False
    
    async def cancel_all_orders(self, symbol: Optional[str] = None) -> int:
        data = {}
        if symbol:
            data["market"] = symbol
        
        try:
            response = await self._request("POST", "/market/orders/cancel", data=data, auth=True)
            if isinstance(response, list):
                return len(response)
            return 0
        except Exception as e:
            self.logger.error(f"Failed to cancel all orders: {e}")
            return 0
    
    def _parse_order(self, order_data: Dict) -> Order:
        status_map = {
            "wait": OrderStatus.OPEN,
            "pending": OrderStatus.PENDING,
            "done": OrderStatus.FILLED,
            "cancel": OrderStatus.CANCELLED,
        }
        
        return Order(
            id=str(order_data.get("id")),
            symbol=order_data.get("market", ""),
            side=OrderSide.BUY if order_data.get("side") == "buy" else OrderSide.SELL,
            order_type=OrderType.LIMIT if order_data.get("ord_type") == "limit" else OrderType.MARKET,
            price=self._parse_decimal(order_data.get("price")),
            quantity=self._parse_decimal(order_data.get("origin_volume")),
            filled_quantity=self._parse_decimal(order_data.get("executed_volume")),
            remaining_quantity=self._parse_decimal(order_data.get("remaining_volume")),
            status=status_map.get(order_data.get("state", ""), OrderStatus.PENDING),
            created_at=self._parse_timestamp(order_data.get("created_at")),
            exchange=self.name
        )


# =============================================================================
# MARKET MAKER STRATEGY
# =============================================================================

class MarketMaker:
    """
    Market Making Strategy Engine.
    
    Maintains order book depth by placing laddered orders on both sides.
    Adjusts prices based on inventory to maintain balance.
    """
    
    def __init__(
        self,
        connector: ExchangeConnector,
        market_config: MarketConfig,
        dry_run: bool = True
    ):
        self.connector = connector
        self.config = market_config
        self.dry_run = dry_run
        
        self.base_balance = Decimal("0")
        self.quote_balance = Decimal("0")
        self.buy_orders: List[Order] = []
        self.sell_orders: List[Order] = []
        self.last_mid_price: Optional[Decimal] = None
        self.last_update = utc_now()
        
        self.logger = logging.getLogger(f"AMM.{connector.name}.{market_config.symbol}")
    
    async def initialize(self):
        """Initialize the market maker."""
        self.logger.info(f"Initializing market maker for {self.config.symbol}")
        
        await self._update_balances()
        await self._sync_orders()
        
        self.logger.info(
            f"Initialized: Base={self.base_balance:.8f}, Quote={self.quote_balance:.8f}"
        )
    
    async def _update_balances(self):
        """Update balance state from exchange."""
        balances = await self.connector.get_balances()
        self.base_balance = balances.get_available(self.config.base_currency)
        self.quote_balance = balances.get_available(self.config.quote_currency)
    
    async def _sync_orders(self):
        """Sync current orders from exchange."""
        orders = await self.connector.get_open_orders(self.config.symbol)
        self.buy_orders = [o for o in orders if o.side == OrderSide.BUY]
        self.sell_orders = [o for o in orders if o.side == OrderSide.SELL]
    
    def _calculate_inventory_skew(self) -> float:
        """Calculate how much to skew prices based on inventory."""
        if not self.last_mid_price or self.last_mid_price <= 0:
            return 0.0
        
        base_value = self.base_balance * self.last_mid_price
        total_value = base_value + self.quote_balance
        
        if total_value <= 0:
            return 0.0
        
        current_ratio = float(base_value / total_value)
        target_ratio = self.config.inventory_target_ratio
        
        deviation = current_ratio - target_ratio
        max_deviation = max(target_ratio, 1 - target_ratio)
        skew = deviation / max_deviation if max_deviation > 0 else 0
        
        return max(-1.0, min(1.0, skew))
    
    def calculate_order_ladder(self, order_book: OrderBook) -> OrderLadder:
        """Calculate optimal order prices and quantities."""
        mid_price = order_book.mid_price
        if not mid_price or mid_price <= 0:
            self.logger.warning("Invalid mid price")
            return OrderLadder()
        
        # Calculate inventory skew
        inventory_skew = self._calculate_inventory_skew()
        
        # Calculate spread
        spread_percent = self.config.target_spread_percent / 100
        min_spread_percent = self.config.min_spread_percent / 100
        
        # Adjust spread based on market
        market_spread = order_book.spread_percent
        if market_spread and market_spread > Decimal("0"):
            spread_percent = max(
                float(min_spread_percent),
                min(float(spread_percent), float(market_spread) / 200)
            )
        
        # Apply skew to bid/ask
        bid_adjustment = -inventory_skew * self.config.inventory_skew_factor
        ask_adjustment = inventory_skew * self.config.inventory_skew_factor
        
        best_bid = mid_price * Decimal(1 - spread_percent / 2 + bid_adjustment)
        best_ask = mid_price * Decimal(1 + spread_percent / 2 + ask_adjustment)
        
        # Ensure minimum spread
        min_spread = mid_price * Decimal(min_spread_percent)
        if best_ask - best_bid < min_spread:
            adjustment = (min_spread - (best_ask - best_bid)) / 2
            best_bid -= adjustment
            best_ask += adjustment
        
        # Generate price levels
        num_levels = self.config.num_orders_per_side
        spacing = self.config.order_spacing_percent / 100
        
        buy_prices = []
        sell_prices = []
        
        for i in range(num_levels):
            level_offset = Decimal(i * spacing)
            buy_prices.append(best_bid * (1 - level_offset))
            sell_prices.append(best_ask * (1 + level_offset))
        
        # Calculate quantities
        buy_quantities = self._calculate_quantities(buy_prices, OrderSide.BUY, mid_price)
        sell_quantities = self._calculate_quantities(sell_prices, OrderSide.SELL, mid_price)
        
        return OrderLadder(
            buy_prices=buy_prices,
            buy_quantities=buy_quantities,
            sell_prices=sell_prices,
            sell_quantities=sell_quantities,
            mid_price=mid_price
        )
    
    def _calculate_quantities(
        self,
        prices: List[Decimal],
        side: OrderSide,
        mid_price: Decimal
    ) -> List[Decimal]:
        """Calculate order quantities for each price level."""
        if not prices:
            return []
        
        num_levels = len(prices)
        weights = [1 / (i + 1) for i in range(num_levels)]
        total_weight = sum(weights)
        
        if side == OrderSide.BUY:
            total_allocation = self.config.total_quote_allocation
            available = float(self.quote_balance)
            allocation = min(total_allocation, available * 0.95)
            
            quantities = []
            for i, price in enumerate(prices):
                level_allocation = allocation * weights[i] / total_weight
                quantity = Decimal(level_allocation) / price
                quantity = max(
                    Decimal(self.config.min_order_size),
                    min(Decimal(self.config.max_order_size), quantity)
                )
                quantities.append(quantity)
        else:
            total_allocation = self.config.total_base_allocation
            available = float(self.base_balance)
            allocation = min(total_allocation, available * 0.95)
            
            quantities = []
            for i in range(num_levels):
                quantity = Decimal(allocation * weights[i] / total_weight)
                quantity = max(
                    Decimal(self.config.min_order_size),
                    min(Decimal(self.config.max_order_size), quantity)
                )
                quantities.append(quantity)
        
        return quantities
    
    def _should_update_orders(self, order_book: OrderBook) -> bool:
        """Determine if orders should be updated."""
        if not self.last_mid_price:
            return True
        
        price_change = abs(
            (order_book.mid_price - self.last_mid_price) / self.last_mid_price
        )
        
        update_threshold = Decimal(self.config.target_spread_percent / 200)
        
        if price_change > update_threshold:
            return True
        
        if len(self.buy_orders) < self.config.num_orders_per_side // 2:
            return True
        if len(self.sell_orders) < self.config.num_orders_per_side // 2:
            return True
        
        return False
    
    async def update_orders(self) -> Tuple[int, int]:
        """Main order update method. Returns (created, cancelled)."""
        order_book = await self.connector.get_order_book(self.config.symbol)
        
        if not order_book.mid_price:
            self.logger.warning("No valid order book data")
            return (0, 0)
        
        ladder = self.calculate_order_ladder(order_book)
        
        if not self._should_update_orders(order_book):
            self.logger.debug("No update needed")
            return (0, 0)
        
        self.last_mid_price = order_book.mid_price
        self.last_update = utc_now()
        
        # Cancel existing orders
        cancelled = await self._cancel_all_orders()
        
        # Place new orders
        created = await self._place_ladder_orders(ladder)
        
        # Sync state
        await self._sync_orders()
        await self._update_balances()
        
        self.logger.info(
            f"Updated: cancelled={cancelled}, created={created}, mid={order_book.mid_price:.8f}"
        )
        
        return (created, cancelled)
    
    async def _cancel_all_orders(self) -> int:
        """Cancel all orders for this market."""
        if self.dry_run:
            count = len(self.buy_orders) + len(self.sell_orders)
            self.logger.info(f"[DRY RUN] Would cancel {count} orders")
            return count
        
        return await self.connector.cancel_all_orders(self.config.symbol)
    
    async def _place_ladder_orders(self, ladder: OrderLadder) -> int:
        """Place all orders in the ladder."""
        created = 0
        
        # Place buy orders
        for price, quantity in zip(ladder.buy_prices, ladder.buy_quantities):
            if quantity <= 0:
                continue
            
            price = self.connector.round_price(price)
            quantity = self.connector.round_quantity(quantity)
            
            if self.dry_run:
                self.logger.info(f"[DRY RUN] BUY {quantity:.8f} @ {price:.8f}")
                created += 1
                continue
            
            try:
                await self.connector.create_order(
                    symbol=self.config.symbol,
                    side=OrderSide.BUY,
                    order_type=OrderType.LIMIT,
                    quantity=quantity,
                    price=price
                )
                created += 1
            except Exception as e:
                self.logger.error(f"Failed to place buy order: {e}")
        
        # Place sell orders
        for price, quantity in zip(ladder.sell_prices, ladder.sell_quantities):
            if quantity <= 0:
                continue
            
            price = self.connector.round_price(price)
            quantity = self.connector.round_quantity(quantity)
            
            if self.dry_run:
                self.logger.info(f"[DRY RUN] SELL {quantity:.8f} @ {price:.8f}")
                created += 1
                continue
            
            try:
                await self.connector.create_order(
                    symbol=self.config.symbol,
                    side=OrderSide.SELL,
                    order_type=OrderType.LIMIT,
                    quantity=quantity,
                    price=price
                )
                created += 1
            except Exception as e:
                self.logger.error(f"Failed to place sell order: {e}")
        
        return created
    
    async def emergency_cancel(self):
        """Emergency cancellation of all orders."""
        self.logger.warning("Emergency cancel triggered!")
        if not self.dry_run:
            await self.connector.cancel_all_orders(self.config.symbol)
        self.buy_orders.clear()
        self.sell_orders.clear()
    
    def get_status(self) -> Dict:
        """Get current status."""
        return {
            "symbol": self.config.symbol,
            "exchange": self.connector.name,
            "base_balance": str(self.base_balance),
            "quote_balance": str(self.quote_balance),
            "buy_orders": len(self.buy_orders),
            "sell_orders": len(self.sell_orders),
            "last_mid_price": str(self.last_mid_price) if self.last_mid_price else None,
            "last_update": self.last_update.isoformat(),
            "dry_run": self.dry_run
        }


# =============================================================================
# MAIN BOT
# =============================================================================

class AMMBot:
    """Main AMM Bot orchestrator."""
    
    def __init__(self, config: Dict):
        self.config = config
        self.running = False
        self.connectors: Dict[str, ExchangeConnector] = {}
        self.market_makers: Dict[str, MarketMaker] = {}
        
        self.start_time: Optional[datetime] = None
        self.total_updates = 0
        self.total_orders_created = 0
        self.total_orders_cancelled = 0
    
    def _create_connector(self, name: str, ex_config: Dict) -> ExchangeConnector:
        """Create connector for an exchange."""
        connector_map = {
            "nonkyc": NonKYCConnector,
            "bitstorage": BitstorageConnector,
            "exbitron": ExbitronConnector
        }
        
        connector_class = connector_map.get(name)
        if not connector_class:
            raise ValueError(f"Unknown exchange: {name}")
        
        return connector_class(ex_config)
    
    async def start(self):
        """Initialize and start the bot."""
        logger.info("=" * 60)
        logger.info("STARTING MULTI-EXCHANGE AMM BOT")
        logger.info("=" * 60)
        
        if self.config["dry_run"]:
            logger.warning("DRY RUN MODE - No real orders will be placed")
        
        # Initialize connectors
        for ex_name, ex_config in self.config["exchanges"].items():
            if not ex_config.get("enabled", False):
                logger.info(f"Exchange {ex_name} is disabled, skipping")
                continue
            
            try:
                connector = self._create_connector(ex_name, ex_config)
                await connector.start()
                self.connectors[ex_name] = connector
                logger.info(f"Started connector for {ex_name}")
            except Exception as e:
                logger.error(f"Failed to start {ex_name} connector: {e}")
        
        if not self.connectors:
            logger.error("No exchanges enabled! Configure API credentials in CONFIG.")
            return
        
        # Initialize market makers
        for ex_name, markets in self.config["markets"].items():
            if ex_name not in self.connectors:
                continue
            
            connector = self.connectors[ex_name]
            
            for market_dict in markets:
                try:
                    market_config = MarketConfig(**market_dict)
                    
                    mm = MarketMaker(
                        connector=connector,
                        market_config=market_config,
                        dry_run=self.config["dry_run"]
                    )
                    await mm.initialize()
                    
                    key = f"{ex_name}_{market_config.symbol}"
                    self.market_makers[key] = mm
                    logger.info(f"Initialized market maker: {key}")
                    
                except Exception as e:
                    logger.error(f"Failed to initialize MM for {ex_name}/{market_dict.get('symbol')}: {e}")
        
        if not self.market_makers:
            logger.error("No market makers initialized!")
            return
        
        self.running = True
        self.start_time = utc_now()

        await self._run_loop()
    
    async def _run_loop(self):
        """Main bot loop."""
        interval = self.config["update_interval_seconds"]
        logger.info(f"Starting main loop (interval: {interval}s)")
        
        while self.running:
            try:
                for key, mm in self.market_makers.items():
                    try:
                        created, cancelled = await mm.update_orders()
                        self.total_orders_created += created
                        self.total_orders_cancelled += cancelled
                    except Exception as e:
                        logger.error(f"Error updating {key}: {e}")
                
                self.total_updates += 1
                
                if self.total_updates % 10 == 0:
                    self._log_status()
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
            
            await asyncio.sleep(interval)
    
    def _log_status(self):
        """Log current status."""
        runtime = utc_now() - self.start_time if self.start_time else None
        
        logger.info("-" * 50)
        logger.info("BOT STATUS")
        logger.info(f"  Runtime: {runtime}")
        logger.info(f"  Updates: {self.total_updates}")
        logger.info(f"  Orders Created: {self.total_orders_created}")
        logger.info(f"  Orders Cancelled: {self.total_orders_cancelled}")
        
        for key, mm in self.market_makers.items():
            status = mm.get_status()
            logger.info(f"  {key}: Buys={status['buy_orders']}, Sells={status['sell_orders']}, Mid={status['last_mid_price']}")
        
        logger.info("-" * 50)
    
    async def stop(self):
        """Stop the bot gracefully."""
        logger.info("Stopping AMM Bot...")
        self.running = False
        
        for key, mm in self.market_makers.items():
            try:
                await mm.emergency_cancel()
            except Exception as e:
                logger.error(f"Error stopping {key}: {e}")
        
        for ex_name, connector in self.connectors.items():
            try:
                await connector.stop()
            except Exception as e:
                logger.error(f"Error stopping {ex_name}: {e}")
        
        logger.info("AMM Bot stopped")


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

class GracefulShutdown:
    """
    Cross-platform graceful shutdown handler.

    On Unix: Uses asyncio signal handlers
    On Windows: Uses a background thread to monitor for Ctrl+C
    """

    def __init__(self, bot: AMMBot):
        self.bot = bot
        self.shutdown_event = asyncio.Event()
        self._shutdown_requested = False

    def request_shutdown(self) -> None:
        """Request graceful shutdown."""
        if self._shutdown_requested:
            return
        self._shutdown_requested = True
        logger.info("Shutdown requested...")

        # Set event in thread-safe manner
        try:
            loop = asyncio.get_running_loop()
            loop.call_soon_threadsafe(self.shutdown_event.set)
        except RuntimeError:
            # No running loop, set directly
            self.shutdown_event.set()

    async def wait_for_shutdown(self) -> None:
        """Wait for shutdown signal."""
        await self.shutdown_event.wait()

    def setup_signal_handlers(self) -> None:
        """Set up signal handlers based on platform."""
        if IS_WINDOWS:
            self._setup_windows_handlers()
        else:
            self._setup_unix_handlers()

    def _setup_unix_handlers(self) -> None:
        """Set up Unix signal handlers."""
        try:
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, self.request_shutdown)
            logger.debug("Unix signal handlers installed")
        except Exception as e:
            logger.warning(f"Could not install Unix signal handlers: {e}")
            # Fall back to basic signal handling
            signal.signal(signal.SIGINT, lambda s, f: self.request_shutdown())
            signal.signal(signal.SIGTERM, lambda s, f: self.request_shutdown())

    def _setup_windows_handlers(self) -> None:
        """Set up Windows signal handlers."""
        # On Windows, we use traditional signal handlers
        # They work for Ctrl+C but not for asyncio event loop integration
        def win_handler(signum: int, frame: Any) -> None:
            self.request_shutdown()

        signal.signal(signal.SIGINT, win_handler)
        signal.signal(signal.SIGTERM, win_handler)
        logger.debug("Windows signal handlers installed")


async def run_bot(config: Dict) -> None:
    """Run the bot with proper shutdown handling."""
    bot = AMMBot(config)
    shutdown = GracefulShutdown(bot)
    shutdown.setup_signal_handlers()

    try:
        # Start bot in a task
        bot_task = asyncio.create_task(bot.start())

        # Wait for either bot completion or shutdown signal
        shutdown_task = asyncio.create_task(shutdown.wait_for_shutdown())

        done, pending = await asyncio.wait(
            [bot_task, shutdown_task],
            return_when=asyncio.FIRST_COMPLETED
        )

        # If shutdown was requested, stop the bot
        if shutdown_task in done:
            await bot.stop()
            if not bot_task.done():
                bot_task.cancel()
                try:
                    await bot_task
                except asyncio.CancelledError:
                    pass

        # If bot completed (error or normally), cancel shutdown wait
        if bot_task in done:
            shutdown_task.cancel()
            try:
                await shutdown_task
            except asyncio.CancelledError:
                pass

            # Re-raise any exception from the bot
            if bot_task.exception():
                raise bot_task.exception()

    except asyncio.CancelledError:
        logger.info("Bot task cancelled")
    except Exception as e:
        logger.error(f"Bot error: {e}")
        raise
    finally:
        # Ensure cleanup
        if bot.running:
            await bot.stop()


async def main() -> None:
    """Main entry point."""
    await run_bot(ACTIVE_CONFIG)


def main_entry() -> None:
    """Entry point for console script (pyproject.toml)."""
    print("""
╔═══════════════════════════════════════════════════════════════╗
║           MULTI-EXCHANGE AMM BOT v{}                        ║
║                                                               ║
║   Exchanges: NonKYC | Bitstorage | Exbitron                   ║
║                                                               ║
║   Configuration:                                              ║
║   - Copy config.example.json to config.json                   ║
║   - Edit config.json with your API credentials                ║
║   - Set 'enabled: true' for your exchanges                    ║
║                                                               ║
║   Start with dry_run=true to test without placing orders.     ║
╚═══════════════════════════════════════════════════════════════╝
    """.format(__version__))

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot stopped by user")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main_entry()
