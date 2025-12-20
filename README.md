# Multi-CEX-AMM Bot

A cross-platform Automated Market Maker (AMM) bot for multiple centralized cryptocurrency exchanges.

## Supported Exchanges

- **NonKYC.io** - Privacy-focused exchange
- **Bitstorage.finance** - Multi-asset trading platform
- **Exbitron.com** - Cryptocurrency exchange

All exchanges use the Peatio API v2 standard.

## Features

- **Cross-platform**: Works on Linux, macOS, and Windows
- **Multiple Exchanges**: Manage liquidity across multiple exchanges simultaneously
- **Market Making Strategy**: Maintains order book depth with laddered orders
- **Inventory Management**: Automatic price skewing based on inventory balance
- **Rate Limiting**: Built-in request throttling per exchange
- **Dry Run Mode**: Test strategies without placing real orders
- **External Configuration**: JSON-based configuration file support
- **Graceful Shutdown**: Proper signal handling on all platforms

## Requirements

- Python 3.8 or higher
- aiohttp library

## Quick Start

### Linux / macOS

```bash
# Clone the repository
git clone https://github.com/Fry-Foundation/Multi-CEX-AMM.git
cd Multi-CEX-AMM

# Set up virtual environment and install dependencies
./run_bot.sh --setup

# Create your configuration file
./run_bot.sh --config

# Edit config.json with your API credentials
nano config.json  # or use your preferred editor

# Run the bot
./run_bot.sh
```

### Windows

```cmd
REM Clone the repository
git clone https://github.com/Fry-Foundation/Multi-CEX-AMM.git
cd Multi-CEX-AMM

REM Set up virtual environment and install dependencies
run_bot.bat --setup

REM Create your configuration file
run_bot.bat --config

REM Edit config.json with your API credentials (use notepad or your preferred editor)
notepad config.json

REM Run the bot
run_bot.bat
```

### Manual Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Or install as a package
pip install .

# Copy and configure
cp config.example.json config.json
# Edit config.json with your credentials

# Run
python amm_bot.py
```

## Configuration

Copy `config.example.json` to `config.json` and configure:

```json
{
    "dry_run": true,
    "update_interval_seconds": 15,
    "log_level": "INFO",

    "exchanges": {
        "nonkyc": {
            "enabled": true,
            "api_key": "YOUR_API_KEY",
            "api_secret": "YOUR_API_SECRET",
            "base_url": "https://api.nonkyc.io/api/v2",
            "requests_per_second": 5.0
        }
    },

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
                "inventory_skew_factor": 0.1
            }
        ]
    }
}
```

### Configuration Options

#### Global Settings

| Option | Description | Default |
|--------|-------------|---------|
| `dry_run` | Simulate trading without placing real orders | `true` |
| `update_interval_seconds` | How often to refresh orders | `15` |
| `log_level` | Logging verbosity (DEBUG, INFO, WARNING, ERROR) | `INFO` |
| `log_file` | Optional file path for logging | `null` |

#### Exchange Settings

| Option | Description |
|--------|-------------|
| `enabled` | Enable/disable the exchange |
| `api_key` | Your exchange API key |
| `api_secret` | Your exchange API secret |
| `base_url` | Exchange API base URL |
| `requests_per_second` | Rate limit for API requests |

#### Market Settings

| Option | Description |
|--------|-------------|
| `symbol` | Trading pair symbol (e.g., "btcusdt") |
| `base_currency` | Base asset (e.g., "btc") |
| `quote_currency` | Quote asset (e.g., "usdt") |
| `num_orders_per_side` | Number of orders on each side of the book |
| `order_spacing_percent` | Percentage gap between order levels |
| `min_order_size` | Minimum order quantity |
| `max_order_size` | Maximum order quantity |
| `total_base_allocation` | Maximum base currency to deploy |
| `total_quote_allocation` | Maximum quote currency to deploy |
| `min_spread_percent` | Minimum bid-ask spread |
| `target_spread_percent` | Target bid-ask spread |
| `inventory_target_ratio` | Target base/total value ratio (0.5 = 50/50) |
| `inventory_skew_factor` | How aggressively to rebalance inventory |

## How It Works

### Market Making Strategy

1. **Order Ladder**: Places multiple limit orders at different price levels on both sides of the order book
2. **Spread Management**: Maintains a configurable spread around the mid-price
3. **Inventory Skewing**: Adjusts prices based on inventory imbalance to encourage rebalancing
4. **Dynamic Updates**: Refreshes orders when price moves beyond threshold or orders are filled

### Order Placement

```
         ASKS (Sell orders)
    Level 3: $100.90 (0.03 BTC)
    Level 2: $100.60 (0.04 BTC)
    Level 1: $100.30 (0.05 BTC)  <- Best Ask
    -------- Mid Price: $100.00 --------
    Level 1: $99.70 (0.05 BTC)   <- Best Bid
    Level 2: $99.40 (0.04 BTC)
    Level 3: $99.10 (0.03 BTC)
         BIDS (Buy orders)
```

## Safety Features

- **Dry Run Mode**: Enabled by default - simulates all trading activity
- **Emergency Cancel**: All orders cancelled on shutdown
- **Rate Limiting**: Prevents API throttling
- **Error Recovery**: Continues operation on transient errors
- **Decimal Precision**: Uses Python Decimal for accurate calculations

## Project Structure

```
Multi-CEX-AMM/
├── amm_bot.py           # Main bot implementation
├── config.example.json  # Configuration template
├── requirements.txt     # Python dependencies
├── pyproject.toml       # Modern Python packaging
├── setup.py             # Legacy packaging support
├── run_bot.sh           # Linux/macOS launcher
├── run_bot.bat          # Windows launcher
└── README.md            # This file
```

## Development

### Installing Development Dependencies

```bash
pip install -e ".[dev]"
```

### Code Style

```bash
# Format code
black amm_bot.py

# Sort imports
isort amm_bot.py

# Type checking
mypy amm_bot.py

# Linting
flake8 amm_bot.py
```

## Troubleshooting

### Common Issues

**"aiohttp not installed"**
```bash
pip install aiohttp
```

**"Python version not supported"**
```bash
# Check your Python version
python --version
# Install Python 3.8+ from https://www.python.org/
```

**"No exchanges enabled"**
- Edit `config.json` and set `"enabled": true` for at least one exchange
- Ensure your API credentials are correct

**"API error 401"**
- Check your API key and secret are correct
- Ensure API key has trading permissions
- Verify the API key hasn't expired

**Windows: "run_bot.bat not working"**
- Make sure Python is in your PATH
- Try running `python amm_bot.py` directly

### Getting Help

1. Check the logs for error messages
2. Enable DEBUG logging: set `"log_level": "DEBUG"` in config.json
3. Run in dry mode first to test connectivity
4. Open an issue on GitHub with:
   - Your operating system
   - Python version (`python --version`)
   - Full error message/stack trace

## Disclaimer

**USE AT YOUR OWN RISK**

This software is provided for educational purposes. Trading cryptocurrencies involves significant risk of loss. The authors are not responsible for any financial losses incurred through the use of this software.

- Always start with `dry_run: true` to test your configuration
- Never risk more than you can afford to lose
- Monitor the bot actively, especially when first starting
- Keep your API keys secure and never share them

## License

MIT License - see LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

Please ensure your code follows the existing style and includes appropriate tests.
