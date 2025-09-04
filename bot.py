import os
import json
import logging
import base64
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import requests
from PIL import Image
import io

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

def parse_ano_mes(texto):
    """Extrai ano e mês do texto do usuário."""
    logger.info(f"🔍 Parsing texto: '{texto}'")
    
    # Padrões aceitos: "2024/09", "2024-09", "09/2024", "setembro 2024", etc.
    padroes = [
        r'(\d{4})[/-](\d{1,2})',  # 2024/09 ou 2024-09
        r'(\d{1,2})[/-](\d{4})',  # 09/2024 ou 09-2024
        r'(\d{4})\s+(\d{1,2})',   # 2024 09
        r'(\d{1,2})\s+(\d{4})',   # 09 2024
    ]
    
    texto_limpo = texto.strip().lower()
    logger.info(f"🔍 Texto limpo: '{texto_limpo}'")
    
    # Mapeamento de meses por nome
    meses = {
        'janeiro': 1, 'jan': 1, '1': 1,
        'fevereiro': 2, 'fev': 2, '2': 2,
        'março': 3, 'mar': 3, '3': 3,
        'abril': 4, 'abr': 4, '4': 4,
        'maio': 5, 'mai': 5, '5': 5,
        'junho': 6, 'jun': 6, '6': 6,
        'julho': 7, 'jul': 7, '7': 7,
        'agosto': 8, 'ago': 8, '8': 8,
        'setembro': 9, 'set': 9, '9': 9,
        'outubro': 10, 'out': 10, '10': 10,
        'novembro': 11, 'nov': 11, '11': 11,
        'dezembro': 12, 'dez': 12, '12': 12
    }
    
    # Tenta encontrar mês por nome
    for mes_nome, mes_num in meses.items():
        if mes_nome in texto_limpo:
            logger.info(f"🔍 Encontrou mês por nome: '{mes_nome}' -> {mes_num}")
            # Procura por ano após o mês
            ano_match = re.search(r'(\d{4})', texto_limpo)
            if ano_match:
                ano = int(ano_match.group(1))
                logger.info(f"🔍 Resultado final (nome): ano={ano}, mes={mes_num}")
                return ano, mes_num
    
    # Tenta padrões numéricos
    for i, padrao in enumerate(padroes):
        match = re.search(padrao, texto_limpo)
        if match:
            grupo1, grupo2 = match.groups()
            logger.info(f"🔍 Padrão {i+1} encontrado: grupo1='{grupo1}', grupo2='{grupo2}'")
            # Determina qual é ano e qual é mês
            if len(grupo1) == 4:  # grupo1 é ano
                ano = int(grupo1)
                mes = int(grupo2)
                logger.info(f"🔍 Resultado final (numérico): ano={ano}, mes={mes}")
                return ano, mes
            else:  # grupo2 é ano
                ano = int(grupo2)
                mes = int(grupo1)
                logger.info(f"🔍 Resultado final (numérico): ano={ano}, mes={mes}")
                return ano, mes
    
    logger.error(f"❌ Nenhum padrão encontrado para: '{texto}'")
    return None, None

async def selecionar_periodo_planilha(spreadsheet, ano, mes):
    """Seleciona automaticamente o período na aba Home da planilha."""
    try:
        home_sheet = spreadsheet.worksheet("Home")
        
        # Seleciona o mês (coluna B4)
        home_sheet.update('B4', mes)
        
        # Seleciona o ano (coluna B5)
        home_sheet.update('B5', ano)
        
        # Aguarda um pouco para os gráficos serem atualizados
        import asyncio
        await asyncio.sleep(2)
        
        logger.info(f"✅ Período selecionado na planilha: {mes:02d}/{ano}")
        return True
        
    except Exception as e:
        logger.error(f"Erro ao selecionar período na planilha: {e}")
        return False

async def buscar_grafico_planilha(ano, mes):
    """Busca gráfico da planilha baseado no ano/mês."""
    try:
        gc = get_google_sheets_client()
        if not gc:
            return None, "Erro de autenticação com Google Sheets"
        
        spreadsheet = gc.open(SPREADSHEET_NAME)
        
        # PRIMEIRO: Seleciona automaticamente o período na planilha
        await selecionar_periodo_planilha(spreadsheet, ano, mes)
        
        # SEGUNDO: Busca na aba Home onde os gráficos são criados dinamicamente
        resultado = await buscar_grafico_aba_home(spreadsheet, ano, mes)
        if resultado[0]:
            return resultado
        
        # Estratégias alternativas se não encontrar na Home
        estrategias = [
            lambda: buscar_graficos_todas_abas(spreadsheet, ano, mes),
            lambda: buscar_aba_especifica(spreadsheet, ano, mes),
        ]
        
        for estrategia in estrategias:
            resultado = estrategia()
            if resultado[0]:  # Se encontrou gráfico
                return resultado
        
        return None, f"Nenhum gráfico encontrado para {mes:02d}/{ano}. Verifique se há dados na aba 'Transações' para este período."
        
    except Exception as e:
        logger.error(f"Erro ao buscar gráfico: {e}")
        return None, f"Erro interno: {str(e)}"

async def buscar_grafico_aba_home(spreadsheet, ano, mes):
    """Busca gráficos na aba Home onde são criados dinamicamente."""
    try:
        # Procura pela aba Home
        home_sheet = None
        try:
            home_sheet = spreadsheet.worksheet("Home")
        except:
            return None, "Aba 'Home' não encontrada"
        
        # Aguarda um pouco mais para garantir que os gráficos foram atualizados
        import asyncio
        await asyncio.sleep(1)
        
        # Verifica se há gráficos na aba Home
        charts = home_sheet.get_charts()
        if not charts:
            return None, "Nenhum gráfico encontrado na aba 'Home'. Aguarde mais alguns segundos e tente novamente."
        
        # Filtra gráficos por tipo (Entradas ou Saídas)
        graficos_disponiveis = []
        
        for chart in charts:
            chart_title = chart.get('title', '').lower()
            chart_type = None
            
            if 'entrada' in chart_title:
                chart_type = 'entradas'
            elif 'saída' in chart_title or 'saida' in chart_title:
                chart_type = 'saidas'
            elif 'cash flow' in chart_title or 'cashflow' in chart_title:
                chart_type = 'cashflow'
            else:
                # Se não consegue identificar, assume que é um gráfico válido
                chart_type = 'geral'
            
            graficos_disponiveis.append({
                'chart': chart,
                'type': chart_type,
                'title': chart.get('title', 'Gráfico sem título')
            })
        
        if not graficos_disponiveis:
            return None, "Nenhum gráfico válido encontrado na aba 'Home'"
        
        # Retorna o primeiro gráfico encontrado (pode ser expandido para escolha)
        primeiro_grafico = graficos_disponiveis[0]
        chart_image = primeiro_grafico['chart'].get_image()
        
        if chart_image:
            tipo_descricao = {
                'entradas': 'Gráfico de Entradas',
                'saidas': 'Gráfico de Saídas', 
                'cashflow': 'Gráfico de Cash Flow',
                'geral': 'Gráfico Geral'
            }.get(primeiro_grafico['type'], 'Gráfico')
            
            return chart_image, f"{tipo_descricao} encontrado na aba 'Home' para {mes:02d}/{ano}"
        
        return None, "Não foi possível obter a imagem do gráfico"
        
    except Exception as e:
        logger.error(f"Erro ao buscar na aba Home: {e}")
        return None, f"Erro ao buscar na aba Home: {str(e)}"

def buscar_graficos_todas_abas(spreadsheet, ano, mes):
    """Busca gráficos em todas as abas da planilha."""
    try:
        # Lista todas as abas
        worksheets = spreadsheet.worksheets()
        
        for ws in worksheets:
            try:
                # Verifica se a aba tem gráficos
                charts = ws.get_charts()
                if charts:
                    # Verifica se algum gráfico corresponde ao período
                    for chart in charts:
                        chart_title = chart.get('title', '').lower()
                        if f"{ano}" in chart_title or f"{mes:02d}" in chart_title:
                            # Tenta obter a imagem do gráfico
                            chart_image = chart.get_image()
                            if chart_image:
                                return chart_image, f"Gráfico encontrado na aba '{ws.title}'"
            except Exception as e:
                logger.warning(f"Erro ao verificar aba {ws.title}: {e}")
                continue
        
        return None, "Nenhum gráfico encontrado nas abas"
    except Exception as e:
        logger.error(f"Erro ao buscar em todas as abas: {e}")
        return None, f"Erro ao buscar abas: {str(e)}"

def buscar_aba_especifica(spreadsheet, ano, mes):
    """Busca em aba específica com nome do mês/ano."""
    try:
        # Padrões de nomes de aba para procurar
        padroes_aba = [
            f"{ano}-{mes:02d}",
            f"{mes:02d}-{ano}",
            f"{ano}/{mes:02d}",
            f"{mes:02d}/{ano}",
            f"{ano}_{mes:02d}",
            f"{mes:02d}_{ano}"
        ]
        
        for padrao in padroes_aba:
            try:
                ws = spreadsheet.worksheet(padrao)
                charts = ws.get_charts()
                if charts:
                    chart_image = charts[0].get_image()
                    if chart_image:
                        return chart_image, f"Gráfico encontrado na aba '{padrao}'"
            except:
                continue
        
        return None, "Aba específica não encontrada"
    except Exception as e:
        logger.error(f"Erro ao buscar aba específica: {e}")
        return None, f"Erro ao buscar aba específica: {str(e)}"

# --- COMANDOS DO BOT ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Envia uma mensagem de boas-vindas completa."""
    user = update.effective_user
    welcome_message = (
        f"Olá, {user.first_name}! 👋\n\n"
        "Eu sou seu assistente financeiro pessoal, pronto para te dar acesso rápido aos seus dados.\n\n"
        "Aqui estão os comandos que você pode usar:\n"
        " • <code>/saldo</code> - Mostra os saldos atualizados de todas as suas contas.\n"
        " • <code>/grafico 2024/09</code> - Busca gráfico da planilha para ano/mês específico.\n"
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
        "▫️ <code>/grafico [ano/mês]</code>\n"
        "Busca e envia gráficos da sua planilha para um período específico.\n"
        "<b>Exemplos:</b>\n"
        "• <code>/grafico 2024/09</code>\n"
        "• <code>/grafico setembro 2024</code>\n"
        "• <code>/grafico 09/2024</code>\n\n"
        "▫️ <code>/status</code>\n"
        "Mostra informações de diagnóstico sobre o cache de dados, incluindo quando foi a última vez que os dados foram atualizados da planilha.\n\n"
        "▫️ <code>/start</code>\n"
        "Exibe a mensagem inicial de boas-vindas.\n\n"
        "▫️ <code>/help</code>\n"
        "Mostra esta mensagem."
    )
    await update.message.reply_text(help_message, parse_mode='HTML')

async def grafico_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Busca e envia gráfico da planilha para ano/mês específico."""
    # Verifica se foi fornecido argumento
    if not context.args:
        await update.message.reply_text(
            "📊 <b>Comando Gráfico</b>\n\n"
            "Use este comando para buscar gráficos da sua planilha:\n\n"
            "<b>Exemplos:</b>\n"
            "• <code>/grafico 2024/09</code>\n"
            "• <code>/grafico setembro 2024</code>\n"
            "• <code>/grafico 09/2024</code>\n\n"
            "O bot irá automaticamente:\n"
            "1. Selecionar o período na aba 'Home'\n"
            "2. Aguardar os gráficos serem gerados\n"
            "3. Enviar a imagem do gráfico\n\n"
            "<b>Tipos de gráficos disponíveis:</b>\n"
            "• Gráfico de Entradas por Categoria\n"
            "• Gráfico de Saídas por Categoria\n"
            "• Gráfico de Cash Flow Mensal",
            parse_mode='HTML'
        )
        return
    
    # Junta os argumentos em uma string
    texto_periodo = ' '.join(context.args)
    
    # Envia mensagem de processamento
    processing_msg = await update.message.reply_text(
        f"🔍 Buscando gráfico para: <b>{texto_periodo}</b>\n"
        "Selecionando período na planilha...",
        parse_mode='HTML'
    )
    
    # Extrai ano e mês
    ano, mes = parse_ano_mes(texto_periodo)
    
    if ano is None or mes is None:
        await processing_msg.edit_text(
            f"❌ <b>Formato inválido!</b>\n\n"
            f"Não consegui entender o período: <b>{texto_periodo}</b>\n\n"
            "<b>Formatos aceitos:</b>\n"
            "• <code>/grafico 2024/09</code>\n"
            "• <code>/grafico setembro 2024</code>\n"
            "• <code>/grafico 09/2024</code>",
            parse_mode='HTML'
        )
        return
    
    # Valida ano e mês
    if ano < 2000 or ano > 2030:
        await processing_msg.edit_text(
            f"❌ <b>Ano inválido!</b>\n\n"
            f"O ano deve estar entre 2000 e 2030. Você informou: <b>{ano}</b>",
            parse_mode='HTML'
        )
        return
    
    if mes < 1 or mes > 12:
        await processing_msg.edit_text(
            f"❌ <b>Mês inválido!</b>\n\n"
            f"O mês deve estar entre 1 e 12. Você informou: <b>{mes}</b>",
            parse_mode='HTML'
        )
        return
    
    # Atualiza mensagem de processamento
    await processing_msg.edit_text(
        f"🔍 Buscando gráfico para: <b>{texto_periodo}</b>\n"
        f"Período selecionado: <b>{mes:02d}/{ano}</b>\n"
        "Aguardando gráficos serem gerados...",
        parse_mode='HTML'
    )
    
    # Busca o gráfico
    try:
        chart_image, message = await buscar_grafico_planilha(ano, mes)
        
        if chart_image:
            # Envia a imagem do gráfico
            await update.message.reply_photo(
                photo=chart_image,
                caption=f"📊 <b>Gráfico {mes:02d}/{ano}</b>\n\n{message}",
                parse_mode='HTML'
            )
            await processing_msg.delete()
        else:
            await processing_msg.edit_text(
                f"❌ <b>Gráfico não encontrado!</b>\n\n"
                f"Período: <b>{mes:02d}/{ano}</b>\n"
                f"Erro: <i>{message}</i>\n\n"
                "<b>Dicas:</b>\n"
                "• Verifique se há transações na aba 'Transações' para este período\n"
                "• Certifique-se de que a aba 'Home' existe e está funcionando\n"
                "• Tente um período diferente que tenha dados",
                parse_mode='HTML'
            )
    
    except Exception as e:
        logger.error(f"Erro no comando gráfico: {e}")
        await processing_msg.edit_text(
            f"❌ <b>Erro interno!</b>\n\n"
            f"Ocorreu um erro ao buscar o gráfico:\n"
            f"<i>{str(e)}</i>\n\n"
            "Tente novamente mais tarde ou entre em contato com o suporte.",
            parse_mode='HTML'
        )

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
    
    # Adiciona os handlers para TODOS os comandos
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("saldo", saldo_command))
    application.add_handler(CommandHandler("grafico", grafico_command))
    application.add_handler(CommandHandler("status", status_command))

    logger.info("Bot iniciado no modo Polling... Pressione Ctrl+C para parar.")
    application.run_polling()

if __name__ == '__main__':
    main()