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
    JUPITER_API_BASE = "https://price.jup.ag/v4"
    RAYDIUM_API_BASE = "https://api.raydium.io/v2"
    WEBAPP_URL = os.getenv("WEBAPP_URL", "https://your-webapp-url.com")

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
    
    async def get_token_info(self, token_address: str) -> dict:
        """Obtener información detallada de un token usando endpoints públicos"""
        try:
            # Usar Jupiter API para precio y datos básicos
            jupiter_url = f"{Config.JUPITER_API_BASE}/price?ids={token_address}"
            response = requests.get(jupiter_url)
            price_data = response.json()
            
            # Usar Raydium API para datos adicionales
            raydium_url = f"{Config.RAYDIUM_API_BASE}/token/{token_address}"
            raydium_response = requests.get(raydium_url)
            token_data = raydium_response.json()
            
            if not price_data or not token_data:
                return None

            # Calcular cambio de precio usando datos históricos de Raydium
            history_url = f"{Config.RAYDIUM_API_BASE}/price-history?address={token_address}&type=1D"
            history_response = requests.get(history_url)
            history_data = history_response.json()
            
            price_change_24h = 0
            if history_data and len(history_data) > 1:
                old_price = history_data[0]['price']
                new_price = history_data[-1]['price']
                price_change_24h = ((new_price - old_price) / old_price) * 100

            return {
                "name": token_data.get('name'),
                "symbol": token_data.get('symbol'),
                "price": float(price_data['data'][token_address].get('price', 0)),
                "price_change_24h": price_change_24h,
                "volume_24h": float(token_data.get('volume24h', 0)),
                "market_cap": float(token_data.get('marketCap', 0)),
                "holders": token_data.get('holderCount', 0),
                "created_at": token_data.get('createdAt', int(time.time()))
            }
        except Exception as e:
            print(f"Error getting token info: {str(e)}")
            return None

    async def get_trending_tokens(self) -> list:
        """Obtener tokens en tendencia usando Raydium"""
        try:
            # Obtener pares de trading de Raydium
            url = f"{Config.RAYDIUM_API_BASE}/pairs"
            response = requests.get(url)
            pairs_data = response.json()
            
            if not isinstance(pairs_data, list):
                return []

            # Filtrar y ordenar por volumen
            valid_pairs = []
            for pair in pairs_data:
                try:
                    volume = float(pair.get('volume24h', 0))
                    if volume > 0 and 'tokenInfo' in pair:
                        valid_pairs.append({
                            'volume': volume,
                            'token': pair['tokenInfo']
                        })
                except (ValueError, TypeError):
                    continue

            # Ordenar por volumen y tomar los top 10
            valid_pairs.sort(key=lambda x: x['volume'], reverse=True)
            trending = []

            for pair_data in valid_pairs[:10]:
                token = pair_data['token']
                token_info = await self.get_token_info(token['mint'])
                
                if token_info:
                    trending.append({
                        **token_info,
                        "address": token['mint']
                    })

            return trending
        except Exception as e:
            print(f"Error getting trending tokens: {str(e)}")
            return []

    def analyze_token(self, token_data: dict) -> dict:
        """Analizar un token y dar recomendaciones"""
        try:
            analysis = []
            risk_level = "BAJO"

            # Análisis de precio
            if token_data['price_change_24h'] > 20:
                analysis.append("⚠️ Precio subió más de 20% en 24h")
                risk_level = "ALTO"
            elif token_data['price_change_24h'] < -20:
                analysis.append("⚠️ Precio bajó más de 20% en 24h")
                risk_level = "ALTO"

            # Análisis de volumen
            if token_data['volume_24h'] < 10000:
                analysis.append("⚠️ Volumen bajo (<$10k)")
                risk_level = "ALTO"
            elif token_data['volume_24h'] > 1000000:
                analysis.append("✅ Alto volumen (>$1M)")

            # Análisis de holders
            if token_data['holders'] < 100:
                analysis.append("⚠️ Pocos holders (<100)")
                risk_level = "ALTO"
            elif token_data['holders'] > 1000:
                analysis.append("✅ Buena distribución (>1000 holders)")

            # Análisis de edad
            created_at = datetime.fromtimestamp(token_data['created_at'])
            age_days = (datetime.now() - created_at).days
            
            if age_days < 7:
                analysis.append("⚠️ Token muy nuevo (<7 días)")
                risk_level = "ALTO"
            elif age_days > 30:
                analysis.append("✅ Token establecido (>30 días)")

            return {
                "analysis": analysis,
                "risk_level": risk_level
            }
        except Exception as e:
            print(f"Error analyzing token: {str(e)}")
            return {
                "analysis": ["❌ Error en análisis"],
                "risk_level": "DESCONOCIDO"
            }

class PhantomBot:
    def __init__(self):
        self.token_analyzer = TokenAnalyzer()
        self.connected_wallets = {}  # Almacenar wallets conectadas por usuario_id

    def get_main_keyboard(self):
        """Obtener teclado principal con botón de Web App"""
        keyboard = [
            [KeyboardButton("🔗 Conectar Phantom", web_app=WebAppInfo(url=Config.WEBAPP_URL))],
            [KeyboardButton("📈 Tokens en Tendencia"), KeyboardButton("ℹ️ Ayuda")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /start"""
        user_id = update.effective_user.id
        
        welcome_message = (
            "🤖 *Bienvenido al Bot de Trading en Solana*\n\n"
            "Este bot te ayuda a:\n"
            "• Conectar tu Phantom Wallet\n"
            "• Ver tus tokens y balances\n"
            "• Analizar tokens en tendencia\n\n"
            "Para comenzar, usa el botón '🔗 Conectar Phantom'"
        )
        
        # Limpiar datos anteriores del usuario
        if user_id in self.connected_wallets:
            del self.connected_wallets[user_id]
        
        await update.message.reply_text(
            welcome_message,
            parse_mode='Markdown',
            reply_markup=self.get_main_keyboard()
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /help"""
        help_message = (
            "📚 *Comandos disponibles:*\n\n"
            "/start - Iniciar el bot\n"
            "/trending - Ver tokens en tendencia\n"
            "/analyze <dirección> - Analizar un token específico\n"
            "/portfolio - Ver tu portfolio de tokens\n"
            "/disconnect - Desconectar tu wallet\n\n"
            "🔒 *Seguridad:*\n"
            "• Nunca compartimos tus claves privadas\n"
            "• Todas las transacciones requieren tu confirmación\n"
            "• La conexión es directa con Phantom"
        )
        await update.message.reply_text(help_message, parse_mode='Markdown')

    async def trending(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /trending"""
        await update.message.reply_text("🔍 Buscando tokens en tendencia...")
        
        trending_tokens = await self.token_analyzer.get_trending_tokens()
        
        if not trending_tokens:
            await update.message.reply_text("❌ Error obteniendo tokens en tendencia")
            return

        response = ["📈 *Tokens en Tendencia*\n"]
        
        for token in trending_tokens:
            analysis = self.token_analyzer.analyze_token(token)
            price_change = token['price_change_24h']
            price_emoji = "🟢" if price_change >= 0 else "🔴"
            
            response.append(
                f"\n*{token['symbol']}* ({price_emoji}{price_change:+.2f}%)\n"
                f"💰 Precio: ${token['price']:.6f}\n"
                f"📊 Vol 24h: ${token['volume_24h']:,.0f}\n"
                f"👥 Holders: {token['holders']:,}\n"
                f"⚠️ Riesgo: {analysis['risk_level']}\n"
                f"🔍 Análisis:\n" + "\n".join(f"  • {a}" for a in analysis['analysis'])
            )

        # Enviar en chunks si es muy largo
        message = "\n".join(response)
        if len(message) > 4096:
            for i in range(0, len(message), 4096):
                await update.message.reply_text(
                    message[i:i+4096],
                    parse_mode='Markdown'
                )
        else:
            await update.message.reply_text(message, parse_mode='Markdown')

    async def analyze(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /analyze <dirección>"""
        if not context.args:
            await update.message.reply_text(
                "❌ Por favor proporciona la dirección del token\n"
                "Ejemplo: `/analyze TokenAddress`",
                parse_mode='Markdown'
            )
            return

        token_address = context.args[0]
        await update.message.reply_text(f"🔍 Analizando token {token_address}...")

        token_info = await self.token_analyzer.get_token_info(token_address)
        
        if not token_info:
            await update.message.reply_text("❌ No se encontró información del token")
            return

        analysis = self.token_analyzer.analyze_token(token_info)
        price_change = token_info['price_change_24h']
        price_emoji = "🟢" if price_change >= 0 else "🔴"

        response = (
            f"*{token_info['name']} ({token_info['symbol']})*\n\n"
            f"💰 Precio: ${token_info['price']:.6f}\n"
            f"📊 Cambio 24h: {price_emoji}{price_change:+.2f}%\n"
            f"💎 Market Cap: ${token_info['market_cap']:,.0f}\n"
            f"📈 Vol 24h: ${token_info['volume_24h']:,.0f}\n"
            f"👥 Holders: {token_info['holders']:,}\n"
            f"⚠️ Nivel de Riesgo: {analysis['risk_level']}\n\n"
            f"🔍 *Análisis:*\n" + "\n".join(f"• {a}" for a in analysis['analysis'])
        )

        await update.message.reply_text(response, parse_mode='Markdown')

    async def handle_webapp_data(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Manejar datos de la Web App"""
        try:
            user_id = update.effective_user.id
            data = json.loads(update.message.web_app_data.data)
            
            if data.get('action') == 'wallet_connected':
                # Guardar dirección de wallet
                wallet_address = data['publicKey']
                self.connected_wallets[user_id] = wallet_address
                
                await update.message.reply_text(
                    f"✅ *Wallet conectada exitosamente*\n"
                    f"Dirección: `{wallet_address[:6]}...{wallet_address[-4:]}`\n\n"
                    f"Ahora puedes:\n"
                    f"• Ver tu portfolio con /portfolio\n"
                    f"• Analizar tokens con /analyze\n"
                    f"• Ver tokens en tendencia con /trending",
                    parse_mode='Markdown'
                )
            
            elif data.get('action') == 'wallet_disconnected':
                if user_id in self.connected_wallets:
                    del self.connected_wallets[user_id]
                    await update.message.reply_text(
                        "✅ Wallet desconectada exitosamente",
                        reply_markup=self.get_main_keyboard()
                    )
            
            elif data.get('action') == 'token_balances':
                if user_id not in self.connected_wallets:
                    await update.message.reply_text(
                        "❌ No hay wallet conectada. Usa el botón 'Conectar Phantom'"
                    )
                    return

                tokens = data.get('tokens', [])
                if not tokens:
                    await update.message.reply_text(
                        "📝 No se encontraron tokens en tu wallet"
                    )
                    return

                response = ["💰 *Tu Portfolio*\n"]
                total_value = 0

                for token in tokens:
                    if token['amount'] > 0:
                        try:
                            token_info = await self.token_analyzer.get_token_info(token['mint'])
                            if token_info:
                                value = token['amount'] * token_info['price']
                                total_value += value
                                price_change = token_info['price_change_24h']
                                emoji = "🟢" if price_change >= 0 else "🔴"
                                
                                response.append(
                                    f"\n*{token_info['symbol']}*\n"
                                    f"• Cantidad: {token['amount']:,.4f}\n"
                                    f"• Precio: ${token_info['price']:.6f}\n"
                                    f"• Cambio 24h: {emoji}{price_change:+.2f}%\n"
                                    f"• Valor: ${value:,.2f}"
                                )
                        except Exception as e:
                            print(f"Error procesando token {token['mint']}: {str(e)}")
                            response.append(
                                f"\n*Token {token['mint'][:6]}...{token['mint'][-4:]}*\n"
                                f"• Cantidad: {token['amount']:,.4f}\n"
                                f"• Error: No se pudo obtener información"
                            )

                response.append(f"\n\n💵 *Valor Total:* ${total_value:,.2f}")
                
                # Enviar en chunks si es necesario
                message = "\n".join(response)
                if len(message) > 4096:
                    for i in range(0, len(message), 4096):
                        await update.message.reply_text(
                            message[i:i+4096],
                            parse_mode='Markdown'
                        )
                else:
                    await update.message.reply_text(message, parse_mode='Markdown')

        except json.JSONDecodeError:
            await update.message.reply_text("❌ Error: Datos inválidos de la Web App")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
            print(f"Error completo: {str(e)}")

    async def portfolio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /portfolio"""
        user_id = update.effective_user.id
        
        if user_id not in self.connected_wallets:
            await update.message.reply_text(
                "❌ No hay wallet conectada\n"
                "Usa el botón '🔗 Conectar Phantom' primero",
                reply_markup=self.get_main_keyboard()
            )
            return
        
        wallet_address = self.connected_wallets[user_id]
        
        await update.message.reply_text(
            f"🔄 Obteniendo tokens de la wallet `{wallet_address[:6]}...{wallet_address[-4:]}`\n"
            f"Por favor espera un momento...",
            parse_mode='Markdown'
        )
        
        # Enviar mensaje para abrir la Web App y obtener tokens
        await update.message.reply_text(
            "Para ver tus tokens actualizados, haz clic en el botón 'Conectar Phantom'",
            reply_markup=self.get_main_keyboard()
        )

    async def disconnect(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /disconnect"""
        user_id = update.effective_user.id
        
        if user_id in self.connected_wallets:
            del self.connected_wallets[user_id]
            await update.message.reply_text(
                "✅ Wallet desconectada exitosamente",
                reply_markup=self.get_main_keyboard()
            )
        else:
            await update.message.reply_text(
                "❌ No hay wallet conectada",
                reply_markup=self.get_main_keyboard()
            )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Manejar mensajes de texto"""
        text = update.message.text

        if text == "📈 Tokens en Tendencia":
            await self.trending(update, context)
        elif text == "ℹ️ Ayuda":
            await self.help_command(update, context)
        elif text == "🔗 Conectar Phantom":
            await self.start(update, context)

def main():
    """Función principal"""
    bot = PhantomBot()
    app = Application.builder().token(Config.TELEGRAM_TOKEN).build()

    # Comandos
    app.add_handler(CommandHandler("start", bot.start))
    app.add_handler(CommandHandler("help", bot.help_command))
    app.add_handler(CommandHandler("trending", bot.trending))
    app.add_handler(CommandHandler("analyze", bot.analyze))
    app.add_handler(CommandHandler("portfolio", bot.portfolio))
    app.add_handler(CommandHandler("disconnect", bot.disconnect))

    # Mensajes
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, bot.handle_webapp_data))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))

    # Iniciar bot
    print("Bot iniciado...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main() 