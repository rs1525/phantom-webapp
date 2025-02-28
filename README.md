# Phantom Wallet Web App

Esta es una Web App para integrar Phantom Wallet con un bot de Telegram. La aplicación permite:

- Conectar tu wallet de Phantom de forma segura
- Ver tus tokens y balances
- Realizar operaciones seguras a través de Phantom

## Configuración

1. Instala las dependencias del bot:
```bash
pip install -r requirements.txt
```

2. Configura las variables de entorno en el archivo `.env`:
```
TELEGRAM_TOKEN=tu_token_aqui
WEBAPP_URL=https://tu-usuario.github.io/tu-repo
```

3. Ejecuta el bot:
```bash
python phantom_bot.py
```

## Seguridad

- La Web App nunca tiene acceso a tus llaves privadas
- Todas las transacciones requieren confirmación en Phantom
- No se almacenan datos sensibles 