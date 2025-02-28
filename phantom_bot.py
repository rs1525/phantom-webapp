import os
import json
import qrcode
from io import BytesIO
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InputFile, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from cryptography.fernet import Fernet
import requests
from dotenv import load_dotenv
import time
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from typing import Dict, List
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import base58

# Load environment variables
load_dotenv()

# Configuration
class Config:
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
    BIRDEYE_API_KEY = os.getenv("BIRDEYE_API_KEY", "c9c65095c0864519a3d0e8a7b0c1e4c4")
    PHANTOM_API_BASE = "https://phantom.app/api"
    PHANTOM_DEEPLINK_BASE = "https://phantom.app/ul/browse"
    JUPITER_API_BASE = "https://price.jup.ag/v4"
    COINGECKO_API_BASE = "https://api.coingecko.com/api/v3"
    BIRDEYE_API_BASE = "https://public-api.birdeye.so"
    RAYDIUM_API_BASE = "https://api.raydium.io/v2"
    WEBAPP_URL = os.getenv("WEBAPP_URL", "https://your-webapp-url.com")  # Actualiza esto con tu URL

# Keyboard Markup
def get_main_keyboard():
    """Get the main keyboard markup with Web App button"""
    keyboard = [
        [
            KeyboardButton(
                "🔗 Conectar Phantom",
                web_app=WebAppInfo(url=Config.WEBAPP_URL)
            )
        ],
        [
            KeyboardButton("💰 Mi Portfolio"),
            KeyboardButton("📈 Tokens en Tendencia")
        ]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_trading_keyboard():
    """Get trading keyboard markup"""
    keyboard = [
        [
            KeyboardButton("🔄 Swap Tokens"),
            KeyboardButton("📊 Precios")
        ],
        [
            KeyboardButton("⬅️ Volver al Menú")
        ]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Technical Analysis Parameters
TA_PARAMS = {
    'RSI_PERIOD': 14,
    'RSI_OVERBOUGHT': 70,
    'RSI_OVERSOLD': 30,
    'MACD_FAST': 12,
    'MACD_SLOW': 26,
    'MACD_SIGNAL': 9,
    'VOLUME_CHANGE_THRESHOLD': 50  # Percentage
}

class TokenAnalyzer:
    def __init__(self):
        self.setup_selenium()
        self.headers = {
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
    
    def setup_selenium(self):
        """Configure Selenium for headless browsing"""
        try:
            chrome_options = Options()
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--log-level=3")
            
            try:
                service = Service()
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
            except Exception as e:
                print(f"Error installing ChromeDriver: {str(e)}")
                self.driver = None
        except Exception as e:
            print(f"Error setting up Selenium: {str(e)}")
            self.driver = None

    def __del__(self):
        """Cleanup Selenium driver"""
        try:
            if hasattr(self, 'driver'):
                self.driver.quit()
        except Exception:
            pass
    
    async def get_token_price(self, token_address: str) -> Dict:
        """Get real-time token price and history from Jupiter Aggregator"""
        try:
            # Get current price
            price_url = f"{Config.JUPITER_API_BASE}/price?ids={token_address}"
            price_response = requests.get(price_url)
            price_data = price_response.json()
            
            # Get price history (24h)
            history_url = f"{Config.JUPITER_API_BASE}/price/history?ids={token_address}&interval=1h"
            history_response = requests.get(history_url)
            history_data = history_response.json()
            
            if price_data.get('data') and history_data.get('data'):
                token_info = price_data['data'][token_address]
                price_history = history_data['data'][token_address]
                
                # Calculate price change
                current_price = float(token_info['price'])
                prices_24h = [float(p['price']) for p in price_history]
                price_24h_ago = prices_24h[0] if prices_24h else current_price
                price_change = ((current_price - price_24h_ago) / price_24h_ago) * 100
                
                return {
                    "price": current_price,
                    "price_change_24h": price_change,
                    "price_history": prices_24h,
                    "volume_24h": float(token_info.get('volume24h', 0)),
                    "volume_history": [float(p.get('volume', 0)) for p in price_history]
                }
        except Exception as e:
            print(f"Error getting price data: {str(e)}")
        return {
            "price": 0,
            "price_change_24h": 0,
            "price_history": [],
            "volume_24h": 0,
            "volume_history": []
        }

    async def get_trending_tokens(self) -> List[Dict]:
        """Get trending tokens from Raydium"""
        try:
            # Get trending tokens from Raydium API
            url = f"{Config.RAYDIUM_API_BASE}/main/pairs"
            response = requests.get(url)
            data = response.json()
            
            if not data:
                raise Exception("No se pudieron obtener los tokens en tendencia")
            
            # Sort by volume
            pairs = sorted(data, key=lambda x: float(x.get('volume24h', 0)), reverse=True)
            trending_tokens = []
            
            for pair in pairs[:5]:  # Get top 5 by volume
                try:
                    token = pair['tokenInfo']
                    price_url = f"{Config.JUPITER_API_BASE}/price?ids={token['mint']}"
                    price_response = requests.get(price_url)
                    price_data = price_response.json()
                    
                    if price_data.get('data', {}).get(token['mint']):
                        price_info = price_data['data'][token['mint']]
                        trending_tokens.append({
                            "name": token['name'],
                            "symbol": token['symbol'],
                            "address": token['mint'],
                            "price": float(price_info['price']),
                            "price_change_24h": float(pair.get('priceChange24h', 0)),
                            "volume_24h": float(pair['volume24h']),
                            "liquidity": float(pair['liquidity']),
                            "market_cap": float(price_info['price']) * float(token.get('supply', 0))
                        })
                except Exception as e:
                    print(f"Error getting data for token {token['symbol']}: {str(e)}")
                    continue
            
            return trending_tokens
            
        except Exception as e:
            print(f"Error fetching trending tokens: {str(e)}")
            return []

    async def get_token_data(self, token_address: str) -> Dict:
        """Get comprehensive token data"""
        try:
            # Get token data from Birdeye
            token_url = f"{Config.BIRDEYE_API_BASE}/public/token/{token_address}"
            token_response = requests.get(token_url, headers=self.headers, timeout=10)
            token_data = token_response.json()
            
            if not token_data.get('success'):
                raise Exception("No token data available")
            
            token_info = token_data['data']
            
            # Get additional market data
            market_url = f"{Config.BIRDEYE_API_BASE}/public/market_program/{token_address}"
            market_response = requests.get(market_url, headers=self.headers, timeout=10)
            market_data = market_response.json()
            
            # Get price history
            history_url = f"{Config.BIRDEYE_API_BASE}/public/price_history?address={token_address}&type=1H&limit=24"
            history_response = requests.get(history_url, headers=self.headers, timeout=10)
            history_data = history_response.json()
            
            price_history = []
            volume_history = []
            
            if history_data.get('success'):
                history = history_data['data']
                price_history = [float(p['value']) for p in history]
                volume_history = [float(p.get('volume', 0)) for p in history]
            
            return {
                "name": token_info.get('name', ''),
                "symbol": token_info.get('symbol', ''),
                "price": float(token_info.get('price', 0)),
                "price_change_24h": float(token_info.get('priceChange24h', 0)),
                "market_cap": float(token_info.get('marketCap', 0)),
                "volume_24h": float(token_info.get('volume24h', 0)),
                "holders_count": int(token_info.get('holderCount', 0)),
                "liquidity": float(token_info.get('liquidity', 0)),
                "created_at": token_info.get('createdAt', ''),
                "price_history": price_history,
                "volume_history": volume_history
            }
            
        except Exception as e:
            print(f"Error getting token data: {str(e)}")
            return None

    def calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        """Calculate RSI indicator"""
        try:
            if len(prices) < period:
                return 50  # Default value if not enough data
                
            deltas = np.diff(prices)
            gains = np.where(deltas > 0, deltas, 0)
            losses = np.where(deltas < 0, -deltas, 0)
            
            avg_gain = np.mean(gains[:period])
            avg_loss = np.mean(losses[:period])
            
            if avg_loss == 0:
                return 100
            
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            return round(rsi, 2)
        except Exception:
            return 50

    def calculate_macd(self, prices: List[float]) -> Dict:
        """Calculate MACD indicator"""
        try:
            prices_series = pd.Series(prices)
            exp1 = prices_series.ewm(span=TA_PARAMS['MACD_FAST']).mean()
            exp2 = prices_series.ewm(span=TA_PARAMS['MACD_SLOW']).mean()
            macd = exp1 - exp2
            signal = macd.ewm(span=TA_PARAMS['MACD_SIGNAL']).mean()
            return {
                'macd': macd.iloc[-1],
                'signal': signal.iloc[-1],
                'histogram': macd.iloc[-1] - signal.iloc[-1]
            }
        except Exception:
            return {'macd': 0, 'signal': 0, 'histogram': 0}

    def analyze_volume_trend(self, volumes: List[float]) -> Dict:
        """Analyze volume trends"""
        try:
            avg_volume = sum(volumes) / len(volumes)
            recent_volume = volumes[-1]
            volume_change = ((recent_volume - avg_volume) / avg_volume) * 100
            return {
                'volume_change': volume_change,
                'is_volume_spike': volume_change > TA_PARAMS['VOLUME_CHANGE_THRESHOLD']
            }
        except Exception:
            return {'volume_change': 0, 'is_volume_spike': False}

    def generate_analysis_report(self, token_data: Dict) -> str:
        """Generate comprehensive analysis report"""
        try:
            # Technical indicators
            rsi = self.calculate_rsi(token_data['price_history'])
            macd = self.calculate_macd(token_data['price_history'])
            volume = self.analyze_volume_trend(token_data['volume_history'])
            
            # Market analysis
            market_trend = "ALCISTA" if token_data['price_change_24h'] > 0 else "BAJISTA"
            
            report = [
                f"📊 *Análisis Técnico Detallado*",
                f"➤ Tendencia: {market_trend}",
                f"➤ RSI (14): {rsi:.2f}",
                f"{'🟢 Sobrecompra' if rsi > 70 else '🔴 Sobreventa' if rsi < 30 else '⚪ Neutral'}",
                "",
                f"📈 *Indicadores MACD*",
                f"➤ MACD: {macd['macd']:.4f}",
                f"➤ Señal: {macd['signal']:.4f}",
                f"➤ Histograma: {macd['histogram']:.4f}",
                "",
                f"📊 *Análisis de Volumen*",
                f"➤ Cambio: {volume['volume_change']:.2f}%",
                f"{'🚨 ¡Spike de volumen detectado!' if volume['is_volume_spike'] else ''}",
                "",
                "💡 *Recomendación*"
            ]
            
            # Add trading recommendation based on indicators
            if rsi > 70 and macd['histogram'] < 0:
                report.append("⚠️ Considerar tomar ganancias - Señales de sobrecompra")
            elif rsi < 30 and macd['histogram'] > 0:
                report.append("✅ Posible oportunidad de compra - Señales de sobreventa")
            else:
                report.append("➡️ Mantener posición actual - Sin señales claras")
            
            return "\n".join(report)
        except Exception as e:
            print(f"Error generating analysis report: {str(e)}")
            return "❌ No se pudo generar el análisis técnico"

# Telegram Bot Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    welcome_message = (
        "👋 ¡Bienvenido al Bot de Phantom!\n\n"
        "Usa el botón '🔗 Conectar Phantom' para comenzar.\n"
        "Este botón abrirá una Web App segura donde podrás:\n"
        "• Conectar tu wallet de Phantom\n"
        "• Ver tus tokens\n"
        "• Realizar operaciones seguras\n\n"
        "❗ *Importante*: Nunca compartas tu llave privada"
    )
    await update.message.reply_text(
        welcome_message,
        reply_markup=get_main_keyboard(),
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command handler"""
    help_text = (
        "🔍 *Comandos Disponibles*\n\n"
        "/trending - Muestra los tokens más populares en Phantom\n"
        "/analyze <dirección_token> - Realiza un análisis técnico detallado de un token\n"
        "/help - Muestra este mensaje de ayuda\n\n"
        "📝 *Ejemplo de uso*:\n"
        "`/analyze DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263`"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def trending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Trending tokens command handler"""
    await update.message.reply_text("🔍 Buscando los tokens en tendencia en Phantom...")
    
    analyzer = TokenAnalyzer()
    try:
        trending_tokens = await analyzer.get_trending_tokens()
        
        if not trending_tokens:
            await update.message.reply_text("❌ No se pudieron obtener los tokens en tendencia")
            return
        
        response = ["🏆 *TOP 5 Tokens en Tendencia en Phantom*\n"]
        
        for i, token in enumerate(trending_tokens, 1):
            age = datetime.now() - datetime.fromtimestamp(int(token['created_at'])) if token['created_at'] else timedelta()
            age_str = f"{age.days} días" if age.days > 0 else "Menos de 1 día"
            
            response.append(
                f"{'🥇' if i == 1 else '🥈' if i == 2 else '🥉' if i == 3 else '🔹'} *{i}. {token['name']} ({token['symbol']})*\n"
                f"└ Precio: ${token['price']:.4f}\n"
                f"└ Cambio 24h: {token['price_change_24h']:+.2f}%\n"
                f"└ Capitalización: ${token['market_cap']:,.2f}\n"
                f"└ Volumen 24h: ${token['volume_24h']:,.2f}\n"
                f"└ Liquidez: ${token['liquidity']:,.2f}\n"
                f"└ Holders: {token['holders_count']:,}\n"
                f"└ Edad: {age_str}\n"
                f"└ Contrato: `{token['address']}`\n"
                f"\n[Ver en Phantom]({Config.PHANTOM_DEEPLINK_BASE}/{token['address']})\n"
            )
        
        # Split message if too long
        message = "\n".join(response)
        if len(message) > 4096:
            chunks = [message[i:i+4096] for i in range(0, len(message), 4096)]
            for chunk in chunks:
                await update.message.reply_text(chunk, parse_mode='Markdown', disable_web_page_preview=True)
        else:
            await update.message.reply_text(message, parse_mode='Markdown', disable_web_page_preview=True)
            
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
    finally:
        del analyzer

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Token analysis command handler"""
    if not context.args:
        await update.message.reply_text("❌ Por favor, proporciona la dirección del token a analizar")
        return
    
    token_address = context.args[0]
    analyzer = TokenAnalyzer()
    try:
        token_data = await analyzer.get_token_data(token_address)
        if not token_data:
            await update.message.reply_text("❌ No se pudo obtener la información del token")
            return
        
        analysis_report = analyzer.generate_analysis_report(token_data)
        response = (
            f"💎 *Análisis de Token*\n"
            f"Precio: ${token_data['price']:.4f}\n"
            f"Cambio 24h: {token_data['price_change_24h']:.2f}%\n"
            f"Volumen 24h: ${token_data['volume_24h']:,.2f}\n\n"
            f"{analysis_report}\n\n"
            f"[Ver en Phantom]({Config.PHANTOM_DEEPLINK_BASE}/{token_address})"
        )
        
        await update.message.reply_text(response, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
    finally:
        del analyzer

async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle data received from Web App"""
    try:
        data = json.loads(update.message.web_app_data.data)
        
        if data.get('action') == 'connect':
            # Guardar la dirección de la wallet
            context.user_data['wallet_address'] = data['publicKey']
            await update.message.reply_text(
                f"✅ Wallet conectada exitosamente!\n"
                f"Dirección: `{data['publicKey']}`",
                parse_mode='Markdown'
            )
            
        elif data.get('action') == 'tokens':
            # Procesar lista de tokens
            tokens = data.get('tokens', [])
            if not tokens:
                await update.message.reply_text("No se encontraron tokens en esta wallet")
                return
                
            response = ["💰 *Tus Tokens*\n"]
            for token_account in tokens:
                token = token_account['account']['data']['parsed']['info']
                amount = float(token['tokenAmount']['uiAmount'])
                if amount > 0:
                    response.append(
                        f"• Token: `{token['mint']}`\n"
                        f"  └ Cantidad: {amount:,.4f}\n"
                    )
            
            await update.message.reply_text(
                "\n".join(response),
                parse_mode='Markdown'
            )
            
    except Exception as e:
        await update.message.reply_text(f"❌ Error procesando datos: {str(e)}")

async def handle_trading(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle trading options"""
    if 'wallet_address' not in context.user_data:
        await update.message.reply_text(
            "❌ Primero debes conectar tu wallet usando el botón '🔗 Conectar Phantom'"
        )
        return
        
    trading_message = (
        "💱 *Trading con Phantom*\n\n"
        "*Opciones disponibles:*\n"
        "• 🔄 Swap Tokens - Intercambia tokens usando Jupiter\n"
        "• 📊 Precios - Ver precios en tiempo real\n\n"
        "❗ *Importante*:\n"
        "• Todas las transacciones requieren aprobación en Phantom\n"
        "• Verifica siempre los precios antes de operar\n"
        "• Usa el botón correspondiente para la acción deseada"
    )
    
    await update.message.reply_text(
        trading_message,
        parse_mode='Markdown',
        reply_markup=get_trading_keyboard()
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages"""
    text = update.message.text
    
    if text == "🔗 Conectar Phantom":
        await start(update, context)
    elif text == "💰 Mi Portfolio":
        await get_wallet_balance(update, context)
    elif text == "📈 Tokens en Tendencia":
        await trending(update, context)
    elif text == "💱 Trading":
        await handle_trading(update, context)
    elif text == "⬅️ Volver al Menú":
        await start(update, context)
    elif text == "🔄 Swap Tokens":
        await update.message.reply_text(
            "🔄 Para hacer swap:\n"
            "1. Abre Phantom\n"
            "2. Ve a la sección Swap\n"
            "3. Selecciona los tokens\n"
            "4. Confirma la transacción en Phantom\n\n"
            "❗ Por seguridad, todas las operaciones deben realizarse directamente en Phantom"
        )
    elif text == "📊 Precios":
        await trending(update, context)

def main():
    """Main function to run the bot"""
    app = Application.builder().token(Config.TELEGRAM_TOKEN).build()
    
    # Add command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("trending", trending))
    app.add_handler(CommandHandler("analyze", analyze))
    
    # Add message handlers
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))
    
    # Start the bot
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main() 