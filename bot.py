import os
import json
import logging
import base64
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd

# --- CONFIGURAÇÃO INICIAL ---
load_dotenv()
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- VARIÁVEIS DE AMBIENTE E CACHE ---
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
SPREADSHEET_NAME = os.getenv('SPREADSHEET_NAME')
GOOGLE_CREDENTIALS_BASE64 = os.getenv('GOOGLE_CREDENTIALS_BASE64')

cache = {
    "saldos_df": pd.DataFrame(),
    "transacoes_df": pd.DataFrame(),
    "last_update": None,
    "cache_duration": timedelta(days=1) # Cache é válido por 1 dia
}

# --- FUNÇÕES AUXILIARES ---
def get_google_sheets_client():
    """Decodifica as credenciais e autoriza o cliente gspread."""
    try:
        if not GOOGLE_CREDENTIALS_BASE64:
            logger.error("Segredo GOOGLE_CREDENTIALS_BASE64 não encontrado no .env!")
            return None
        
        credentials_json = base64.b64decode(GOOGLE_CREDENTIALS_BASE64).decode('utf-8')
        credentials_dict = json.loads(credentials_json)
        
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict, scope)
        return gspread.authorize(creds)
    except Exception as e:
        logger.error(f"Falha ao autorizar com Google Sheets: {e}", exc_info=True)
        return None

async def update_cache(context: ContextTypes.DEFAULT_TYPE):
    """Atualiza o cache com dados da planilha."""
    logger.info("🔄 Atualizando cache...")
    gc = get_google_sheets_client()
    if not gc or not SPREADSHEET_NAME:
        logger.error("Cliente do Sheets ou nome da planilha não configurado. Abortando atualização do cache.")
        return

    try:
        spreadsheet = gc.open(SPREADSHEET_NAME)
        saldos_ws = spreadsheet.worksheet("Saldos")
        saldos_records = saldos_ws.get_all_records(value_render_option='FORMULA')
        cache["saldos_df"] = pd.DataFrame(saldos_records)
        logger.info(f"✅ Cache de saldos atualizado: {len(saldos_records)} registros.")
        cache["last_update"] = datetime.now()
    except Exception as e:
        logger.error(f"Erro geral ao atualizar cache: {e}", exc_info=True)

def parse_valor_brl(valor_raw):
    """Converte uma string de moeda brasileira para um float."""
    if isinstance(valor_raw, (int, float)):
        return float(valor_raw)
    try:
        valor_limpo = str(valor_raw).replace('R$', '').strip().replace('.', '').replace(',', '.')
        return float(valor_limpo)
    except (ValueError, TypeError):
        logger.error(f"Não foi possível converter o valor '{valor_raw}' para float.")
        return 0.0

# --- COMANDOS DO BOT ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Envia uma mensagem de boas-vindas completa."""
    user = update.effective_user
    welcome_message = (
        f"Olá, {user.first_name}! 👋\n\n"
        "Eu sou seu assistente financeiro pessoal, pronto para te dar acesso rápido aos seus dados.\n\n"
        "Aqui estão os comandos que você pode usar:\n"
        " • <code>/saldo</code> - Mostra os saldos atualizados de todas as suas contas.\n"
        " • <code>/status</code> - Verifica a saúde do meu cache de dados.\n"
        " • <code>/help</code> - Exibe esta mensagem de ajuda novamente.\n\n"
        "Para começar, que tal um <code>/saldo</code>?"
    )
    await update.message.reply_text(welcome_message, parse_mode='HTML')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra a mensagem de ajuda."""
    help_message = (
        "ℹ️ <b>Ajuda do Assistente Financeiro</b>\n\n"
        "Aqui estão os detalhes dos comandos disponíveis:\n\n"
        "▫️ <code>/saldo</code>\n"
        "Busca os saldos mais recentes de todas as suas contas diretamente da sua planilha Google Sheets. A resposta é quase instantânea graças a um sistema de cache inteligente.\n\n"
        "▫️ <code>/status</code>\n"
        "Mostra informações de diagnóstico sobre o cache de dados, incluindo quando foi a última vez que os dados foram atualizados da planilha.\n\n"
        "▫️ <code>/start</code>\n"
        "Exibe a mensagem inicial de boas-vindas.\n\n"
        "▫️ <code>/help</code>\n"
        "Mostra esta mensagem."
    )
    await update.message.reply_text(help_message, parse_mode='HTML')

async def saldo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra os saldos das contas a partir do cache."""
    await update.message.reply_text("💰 Buscando saldos...")

    if cache["saldos_df"].empty:
        await update_cache(context)

    if cache["saldos_df"].empty:
        await update.message.reply_text("📊 Nenhum saldo encontrado na planilha ou o cache está vazio.")
        return

    saldos_df = cache["saldos_df"]
    logger.info(f"Colunas encontradas no cache de saldos: {list(saldos_df.columns)}")

    COLUNA_CONTA = 'CONTA'
    COLUNA_SALDO = 'SALDO ATUAL (R$)'

    if COLUNA_CONTA not in saldos_df.columns or COLUNA_SALDO not in saldos_df.columns:
        error_msg = f"❌ Erro! Colunas esperadas ('{COLUNA_CONTA}', '{COLUNA_SALDO}') não encontradas na sua planilha."
        await update.message.reply_text(error_msg)
        return
        
    saldo_message = "💰 <b>SALDOS DAS CONTAS</b>\n\n"
    total_geral = 0.0

    for _, row in saldos_df.iterrows():
        conta = row.get(COLUNA_CONTA, 'N/A')
        saldo_raw = row.get(COLUNA_SALDO, '0')
        
        saldo_float = parse_valor_brl(saldo_raw)
        total_geral += saldo_float
        saldo_formatado = f"R$ {saldo_float:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        
        saldo_message += f"🏦 <b>{conta}</b>: {saldo_formatado}\n"

    total_formatado_final = f"R$ {total_geral:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    saldo_message += f"\n📊 <b>TOTAL GERAL: {total_formatado_final}</b>"

    if cache["last_update"]:
        cache_time = cache["last_update"].strftime("%d/%m/%Y %H:%M:%S")
        saldo_message += f"\n\n🔄 <i>Cache de {cache_time}</i>"
        
    await update.message.reply_text(saldo_message, parse_mode='HTML')

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra o status do cache."""
    if not cache["last_update"]:
        await update.message.reply_text("❌ Cache ainda não foi populado. Use /saldo para a primeira carga.")
        return

    is_valid = datetime.now() - cache["last_update"] < cache["cache_duration"]
    status_text = "Válido ✅" if is_valid else "Expirado ⚠️ (será atualizado no próximo /saldo)"
    
    await update.message.reply_text(
        f"📊 <b>Status do Cache</b>\n"
        f"Status: {status_text}\n"
        f"Última Atualização: {cache['last_update'].strftime('%H:%M:%S')}\n"
        f"Saldos em Cache: {len(cache['saldos_df'])} registros",
        parse_mode='HTML'
    )

# --- INICIALIZAÇÃO DO BOT ---
def main() -> None:
    """Inicia o bot em modo polling."""
    if not TELEGRAM_TOKEN:
        logger.critical("TELEGRAM_TOKEN não definido no arquivo .env! O bot não pode iniciar.")
        return

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Adiciona os handlers para TODOS os comandos do MVP
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("saldo", saldo_command))
    application.add_handler(CommandHandler("status", status_command))

    logger.info("Bot iniciado no modo Polling... Pressione Ctrl+C para parar.")
    application.run_polling()

if __name__ == '__main__':
    main()