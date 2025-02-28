# Phantom Wallet Web App

Esta es una Web App para integrar Phantom Wallet con un bot de Telegram. La aplicación permite:

- Conectar tu wallet de Phantom de forma segura
- Ver tus tokens y balances
- Realizar operaciones seguras a través de Phantom

## Demo

Puedes ver la Web App en funcionamiento aquí: [https://rs1525.github.io/phantom-webapp](https://rs1525.github.io/phantom-webapp)

## Configuración

1. Instala las dependencias del bot:
```bash
pip install -r requirements.txt
```

2. Copia `.env.example` a `.env` y configura tus variables de entorno:
```bash
cp .env.example .env
```

3. Edita el archivo `.env` con tus credenciales:
```
TELEGRAM_TOKEN=tu_token_aqui
WEBAPP_URL=https://rs1525.github.io/phantom-webapp
```

4. Ejecuta el bot:
```bash
python phantom_bot.py
```

## Seguridad

- La Web App nunca tiene acceso a tus llaves privadas
- Todas las transacciones requieren confirmación en Phantom
- No se almacenan datos sensibles 