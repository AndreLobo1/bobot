import os
import json
import logging
import base64
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import requests
from PIL import Image
import io
import google.generativeai as genai

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
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Configurar Gemini AI
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-1.5-flash')
else:
    gemini_model = None
    logger.warning("GEMINI_API_KEY não encontrado no .env! Funcionalidade de IA desabilitada.")

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

async def processar_linguagem_natural(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa mensagens em linguagem natural usando Gemini AI."""
    if not gemini_model:
        await update.message.reply_text("🤖 Funcionalidade de IA não disponível. Use os comandos disponíveis.")
        return
    
    user_message = update.message.text
    logger.info(f"🧠 Processando linguagem natural: '{user_message}'")
    
    # Preparar contexto sobre a planilha
    contexto_planilha = ""
    if not cache["saldos_df"].empty:
        saldos_info = []
        total_geral = 0.0
        for _, row in cache["saldos_df"].iterrows():
            conta = row.get('CONTA', 'N/A')
            saldo_raw = row.get('SALDO ATUAL (R$)', '0')
            saldo_float = parse_valor_brl(saldo_raw)
            total_geral += saldo_float
            saldos_info.append(f"- {conta}: R$ {saldo_float:,.2f}")
        
        contexto_planilha = f"""
DADOS ATUAIS DA PLANILHA FINANCEIRA:
Saldo total geral: R$ {total_geral:,.2f}
Contas disponíveis:
{chr(10).join(saldos_info)}

Última atualização: {cache["last_update"].strftime("%d/%m/%Y %H:%M:%S") if cache["last_update"] else "Nunca"}
"""
    
    # Prompt para o Gemini
    prompt = f"""Você é um assistente financeiro pessoal inteligente. Você tem acesso aos dados da planilha financeira do usuário.

{contexto_planilha}

COMANDOS DISPONÍVEIS:
- /saldo - Mostra saldos de todas as contas
- /grafico [ano/mês] - Busca gráfico para período específico (ex: /grafico 2025/08)
- /status - Verifica saúde do cache
- /help - Mostra ajuda

INSTRUÇÕES:
1. Responda de forma amigável e útil em português brasileiro
2. Se o usuário perguntar sobre saldos, use os dados da planilha acima
3. Se pedir gráfico, sugira usar o comando /grafico
4. Se não souber algo específico, seja honesto e sugira comandos disponíveis
5. Mantenha respostas concisas mas informativas
6. Use emojis quando apropriado

PERGUNTA DO USUÁRIO: {user_message}

RESPOSTA:"""
    
    try:
        response = gemini_model.generate_content(prompt)
        resposta = response.text.strip()
        
        # Limitar tamanho da resposta para Telegram
        if len(resposta) > 4000:
            resposta = resposta[:4000] + "\n\n... (resposta truncada)"
        
        await update.message.reply_text(resposta)
        logger.info("✅ Resposta do Gemini enviada com sucesso")
        
    except Exception as e:
        logger.error(f"❌ Erro ao processar com Gemini: {e}")
        await update.message.reply_text("🤖 Desculpe, ocorreu um erro ao processar sua mensagem. Tente usar os comandos disponíveis.")

def parse_ano_mes(texto):
    """Extrai ano e mês do texto do usuário."""
    logger.info(f"🔍 Parsing texto: '{texto}'")
    
    texto_limpo = texto.strip().lower()
    logger.info(f"🔍 Texto limpo: '{texto_limpo}'")
    
    # ESTRATÉGIA 1: Padrão YYYY/MM ou YYYY-MM (PRIORIDADE MÁXIMA)
    match = re.search(r'(\d{4})[/-](\d{1,2})', texto_limpo)
    if match:
        ano = int(match.group(1))
        mes = int(match.group(2))
        logger.info(f"🔍 Resultado final (YYYY/MM): ano={ano}, mes={mes}")
        return ano, mes
    
    # ESTRATÉGIA 2: Padrão MM/YYYY ou MM-YYYY
    match = re.search(r'(\d{1,2})[/-](\d{4})', texto_limpo)
    if match:
        mes = int(match.group(1))
        ano = int(match.group(2))
        logger.info(f"🔍 Resultado final (MM/YYYY): ano={ano}, mes={mes}")
        return ano, mes
    
    # ESTRATÉGIA 3: Padrão YYYY MM (com espaço)
    match = re.search(r'(\d{4})\s+(\d{1,2})', texto_limpo)
    if match:
        ano = int(match.group(1))
        mes = int(match.group(2))
        logger.info(f"🔍 Resultado final (YYYY MM): ano={ano}, mes={mes}")
        return ano, mes
    
    # ESTRATÉGIA 4: Padrão MM YYYY (com espaço)
    match = re.search(r'(\d{1,2})\s+(\d{4})', texto_limpo)
    if match:
        mes = int(match.group(1))
        ano = int(match.group(2))
        logger.info(f"🔍 Resultado final (MM YYYY): ano={ano}, mes={mes}")
        return ano, mes
    
    # ESTRATÉGIA 5: Mês por nome (APENAS DEPOIS de tentar padrões numéricos)
    meses = {
        'janeiro': 1, 'jan': 1,
        'fevereiro': 2, 'fev': 2,
        'março': 3, 'mar': 3,
        'abril': 4, 'abr': 4,
        'maio': 5, 'mai': 5,
        'junho': 6, 'jun': 6,
        'julho': 7, 'jul': 7,
        'agosto': 8, 'ago': 8,
        'setembro': 9, 'set': 9,
        'outubro': 10, 'out': 10,
        'novembro': 11, 'nov': 11,
        'dezembro': 12, 'dez': 12
    }
    
    for mes_nome, mes_num in meses.items():
        if mes_nome in texto_limpo:
            logger.info(f"🔍 Encontrou mês por nome: '{mes_nome}' -> {mes_num}")
            # Procura por ano (4 dígitos) APENAS se não for parte de outro número
            ano_match = re.search(r'\b(\d{4})\b', texto_limpo)
            if ano_match:
                ano = int(ano_match.group(1))
                logger.info(f"🔍 Resultado final (nome): ano={ano}, mes={mes_num}")
                return ano, mes_num
    
    logger.error(f"❌ Nenhum padrão encontrado para: '{texto}'")
    return None, None

async def selecionar_periodo_planilha(spreadsheet, ano, mes):
    """Seleciona automaticamente o período na aba Home da planilha."""
    try:
        home_sheet = spreadsheet.worksheet("Home")
        
        # Corrige o formato de atualização - usa update_cell em vez de update
        home_sheet.update_cell(4, 2, mes)  # B4 = linha 4, coluna 2
        home_sheet.update_cell(5, 2, ano)  # B5 = linha 5, coluna 2
        
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
        logger.info(f"🔍 Iniciando busca de gráficos para {mes:02d}/{ano}")
        
        # Procura pela aba Home
        home_sheet = None
        try:
            home_sheet = spreadsheet.worksheet("Home")
            logger.info("✅ Aba 'Home' encontrada")
        except Exception as e:
            logger.error(f"❌ Aba 'Home' não encontrada: {e}")
            return None, "Aba 'Home' não encontrada"
        
        # Aguarda um pouco mais para garantir que os gráficos foram atualizados
        import asyncio
        await asyncio.sleep(3)
        logger.info("⏳ Aguardou 3 segundos para atualização dos gráficos")
        
        # ESTRATÉGIA SIMPLIFICADA: Tentar obter dados básicos primeiro
        try:
            logger.info("🔍 ESTRATÉGIA SIMPLIFICADA: Obtendo informações básicas")
            
            # Obtém o ID da planilha
            spreadsheet_id = spreadsheet.id
            logger.info(f"📋 ID da planilha: {spreadsheet_id}")
            
            # Lista todas as abas para debug
            worksheets = spreadsheet.worksheets()
            logger.info(f"📊 Abas encontradas: {[ws.title for ws in worksheets]}")
            
            # Encontra o ID da aba Home
            sheet_id = None
            for worksheet in worksheets:
                if worksheet.title == "Home":
                    sheet_id = worksheet.id
                    break
            
            if not sheet_id:
                logger.error("❌ ID da aba Home não encontrado")
                return None, "Aba 'Home' não encontrada"
            
            logger.info(f"📋 ID da aba Home: {sheet_id}")
            
            # ESTRATÉGIA ALTERNATIVA: Tentar usar a API REST do Google Sheets
            try:
                logger.info("🔍 ESTRATÉGIA ALTERNATIVA: Tentando API REST do Google Sheets")
                
                # Gera um novo token de acesso
                credentials_json = base64.b64decode(GOOGLE_CREDENTIALS_BASE64).decode('utf-8')
                credentials_dict = json.loads(credentials_json)
                from oauth2client.service_account import ServiceAccountCredentials
                scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
                creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict, scope)
                
                # Obtém o token de acesso
                token = creds.get_access_token().access_token
                logger.info(f"✅ Token obtido com sucesso (primeiros 10 chars): {token[:10]}...")
                
                import requests
                
                # Constrói a URL da API
                url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}"
                logger.info(f"🌐 URL da API: {url}")
                
                # Faz a requisição para obter informações da planilha incluindo gráficos
                response = requests.get(url, headers={
                    'Authorization': f'Bearer {token}',
                    'Content-Type': 'application/json'
                })
                
                logger.info(f"📡 Status da resposta: {response.status_code}")
                
                if response.status_code != 200:
                    logger.error(f"❌ Erro na API REST: {response.status_code} - {response.text}")
                    return None, f"Erro ao acessar planilha: {response.status_code}"
                
                data = response.json()
                logger.info(f"✅ Dados da planilha obtidos com sucesso")
                
                # Procura por gráficos na aba Home
                charts = []
                for sheet in data.get('sheets', []):
                    if sheet.get('properties', {}).get('title') == 'Home':
                        logger.info(f"📊 Encontrou aba Home nos dados da API")
                        if 'charts' in sheet:
                            charts = sheet['charts']
                            logger.info(f"📈 Encontrados {len(charts)} gráficos na aba Home")
                        else:
                            logger.warning("⚠️ Nenhum gráfico encontrado na aba Home")
                        break
                
                if not charts:
                    logger.warning("❌ Nenhum gráfico encontrado na aba Home via API REST")
                    return None, "Nenhum gráfico encontrado na aba 'Home'. Aguarde mais alguns segundos e tente novamente."
                
                # Processa os gráficos encontrados
                graficos_disponiveis = []
                
                for i, chart in enumerate(charts):
                    try:
                        chart_id = chart.get('chartId', f'chart_{i}')
                        chart_title = chart.get('basicChart', {}).get('chartId', '')
                        
                        logger.info(f"📊 Processando gráfico {i+1}: ID={chart_id}, Título={chart_title}")
                        
                        chart_type = None
                        if 'entrada' in str(chart_title).lower():
                            chart_type = 'entradas'
                        elif 'saída' in str(chart_title).lower() or 'saida' in str(chart_title).lower():
                            chart_type = 'saidas'
                        elif 'cash flow' in str(chart_title).lower() or 'cashflow' in str(chart_title).lower():
                            chart_type = 'cashflow'
                        else:
                            chart_type = 'geral'
                        
                        graficos_disponiveis.append({
                            'chart': chart,
                            'type': chart_type,
                            'title': chart_title or f'Gráfico {i+1}',
                            'chart_id': chart_id
                        })
                        
                        logger.info(f"✅ Gráfico {i+1} processado: tipo={chart_type}")
                        
                    except Exception as e:
                        logger.warning(f"⚠️ Erro ao processar gráfico {i+1}: {e}")
                        continue
                
                if not graficos_disponiveis:
                    logger.error("❌ Nenhum gráfico válido encontrado")
                    return None, "Nenhum gráfico válido encontrado na aba 'Home'"
                
                logger.info(f"🎯 Total de gráficos válidos: {len(graficos_disponiveis)}")
                
                # ESTRATÉGIA FINAL: Tentar obter a imagem do primeiro gráfico
                primeiro_grafico = graficos_disponiveis[0]
                chart_id = primeiro_grafico['chart_id']
                
                logger.info(f"🖼️ Tentando obter imagem do gráfico: {chart_id}")
                
                # Tenta obter a imagem do gráfico
                image_url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/sheets/{sheet_id}/charts/{chart_id}/image"
                logger.info(f"🌐 URL da imagem: {image_url}")
                
                image_response = requests.get(image_url, headers={
                    'Authorization': f'Bearer {token}',
                    'Content-Type': 'application/json'
                })
                
                logger.info(f"📡 Status da resposta da imagem: {image_response.status_code}")
                
                if image_response.status_code == 200:
                    logger.info(f"✅ Imagem obtida com sucesso! Tamanho: {len(image_response.content)} bytes")
                    
                    # Verifica se o conteúdo é válido
                    if len(image_response.content) > 100:  # Deve ter pelo menos 100 bytes
                        logger.info(f"✅ Conteúdo da imagem parece válido")
                        return image_response.content, f"Gráfico encontrado na aba 'Home' para {mes:02d}/{ano}"
                    else:
                        logger.warning(f"⚠️ Conteúdo da imagem muito pequeno: {len(image_response.content)} bytes")
                        logger.warning(f"📄 Primeiros bytes: {image_response.content[:50]}")
                else:
                    logger.warning(f"⚠️ Não foi possível obter imagem do gráfico: {image_response.status_code}")
                    logger.warning(f"📄 Resposta da API: {image_response.text[:200]}...")
                
                # ESTRATÉGIA 2: Tentar exportar a aba Home como PNG (PRIORIDADE MÁXIMA)
                try:
                    logger.info("🖼️ ESTRATÉGIA 2: Tentando exportar aba Home como PNG")
                    
                    # PRIMEIRA TENTATIVA: PNG sem range (sempre funciona)
                    png_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=png&gid={sheet_id}"
                    logger.info(f"🌐 URL do PNG (sem range): {png_url}")
                    
                    png_response = requests.get(png_url, headers={
                        'Authorization': f'Bearer {token}',
                        'Accept': 'image/png',
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    })
                    
                    logger.info(f"📡 Status da resposta do PNG: {png_response.status_code}")
                    
                    if png_response.status_code == 200 and len(png_response.content) > 1000:
                        logger.info(f"✅ PNG obtido com sucesso! Tamanho: {len(png_response.content)} bytes")
                        return png_response.content, f"Imagem da aba 'Home' para {mes:02d}/{ano}"
                    else:
                        logger.warning(f"⚠️ PNG não obtido: {png_response.status_code}")
                        
                except Exception as e:
                    logger.error(f"❌ Erro ao exportar PNG: {e}")

                # ESTRATÉGIA 3: Tentar exportar a aba Home como PDF (fallback)
                try:
                    logger.info("📄 ESTRATÉGIA 3: Tentando exportar aba Home como PDF (fallback)")
                    
                    # URL para exportar a aba Home como PDF sem range (mais confiável)
                    pdf_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=pdf&gid={sheet_id}"
                    logger.info(f"🌐 URL do PDF (sem range): {pdf_url}")
                    
                    pdf_response = requests.get(pdf_url, headers={
                        'Authorization': f'Bearer {token}',
                        'Content-Type': 'application/pdf'
                    })
                    
                    logger.info(f"📡 Status da resposta do PDF: {pdf_response.status_code}")
                    
                    if pdf_response.status_code == 200 and len(pdf_response.content) > 1000:
                        logger.info(f"✅ PDF obtido com sucesso! Tamanho: {len(pdf_response.content)} bytes")
                        return pdf_response.content, f"PDF da aba 'Home' para {mes:02d}/{ano}"
                    else:
                        logger.warning(f"⚠️ PDF não obtido: {pdf_response.status_code}")
                        
                except Exception as e:
                    logger.error(f"❌ Erro ao exportar PDF: {e}")

                # ESTRATÉGIA 4: Tentar obter dados como CSV e criar resumo
                try:
                    logger.info("📊 ESTRATÉGIA 4: Tentando obter dados como CSV")
                    
                    # URL para exportar dados como CSV
                    csv_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv&gid={sheet_id}"
                    logger.info(f"🌐 URL do CSV: {csv_url}")
                    
                    csv_response = requests.get(csv_url, headers={
                        'Authorization': f'Bearer {token}',
                        'Content-Type': 'text/csv'
                    })
                    
                    logger.info(f"📡 Status da resposta CSV: {csv_response.status_code}")
                    
                    if csv_response.status_code == 200 and len(csv_response.content) > 100:
                        logger.info(f"✅ CSV obtido com sucesso! Tamanho: {len(csv_response.content)} bytes")
                        return "SUCCESS_DATA_ONLY", f"Dados da aba 'Home' para {mes:02d}/{ano}"
                    else:
                        logger.warning(f"⚠️ CSV não obtido: {csv_response.status_code}")
                        
                except Exception as e:
                    logger.error(f"❌ Erro ao exportar CSV: {e}")

                # ESTRATÉGIA 5: Tentar obter uma visualização geral via Google Drive API
                try:
                    logger.info("🖼️ ESTRATÉGIA 5: Tentando visualização via Google Drive API")
                    
                    # URL para visualização geral da planilha
                    drive_url = f"https://drive.google.com/uc?export=view&id={spreadsheet_id}"
                    logger.info(f"🌐 URL do Drive: {drive_url}")
                    
                    drive_response = requests.get(drive_url, headers={
                        'Authorization': f'Bearer {token}',
                        'Accept': 'image/*'
                    })
                    
                    logger.info(f"📡 Status da resposta Drive: {drive_response.status_code}")
                    
                    if drive_response.status_code == 200 and len(drive_response.content) > 1000:
                        logger.info(f"✅ Drive view obtido com sucesso! Tamanho: {len(drive_response.content)} bytes")
                        return drive_response.content, f"Visualização da planilha para {mes:02d}/{ano}"
                    else:
                        logger.warning(f"⚠️ Drive view não obtido: {drive_response.status_code}")
                        
                except Exception as e:
                    logger.error(f"❌ Erro ao obter Drive view: {e}")

                logger.warning("❌ Todas as estratégias falharam")
                return "SUCCESS_NO_IMAGE", f"Gráfico encontrado mas imagem não disponível para {mes:02d}/{ano}"
                
            except Exception as e:
                logger.error(f"❌ Erro ao usar API REST: {e}")
                return None, f"Erro ao acessar gráficos: {str(e)}"
        
        except Exception as e:
            logger.error(f"❌ Erro ao obter informações básicas: {e}")
            return None, f"Erro ao acessar planilha: {str(e)}"
        
    except Exception as e:
        logger.error(f"❌ Erro geral ao buscar na aba Home: {e}")
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
        "🤖 <b>NOVO: Inteligência Artificial!</b>\n"
        "Agora você pode conversar comigo em linguagem natural! "
        "Pergunte coisas como:\n"
        "• \"Quanto tenho na conta X?\"\n"
        "• \"Mostra meus saldos\"\n"
        "• \"Qual meu saldo total?\"\n"
        "• \"Preciso de um gráfico de agosto\"\n\n"
        "📋 <b>Comandos Disponíveis:</b>\n\n"
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
        "Mostra esta mensagem.\n\n"
        "💡 <b>Dica:</b> Você pode usar tanto comandos quanto linguagem natural!"
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
            if chart_image == "SUCCESS_NO_IMAGE":
                # Gráfico encontrado mas imagem não disponível
                await processing_msg.edit_text(
                    f"✅ <b>Gráfico encontrado!</b>\n\n"
                    f"Período: <b>{mes:02d}/{ano}</b>\n"
                    f"Status: <i>{message}</i>\n\n"
                    f"<b>Nota:</b> O gráfico foi encontrado na planilha, mas não foi possível obter a imagem. "
                    f"Isso pode acontecer devido a limitações da API do Google Sheets.",
                    parse_mode='HTML'
                )
            elif chart_image == "SUCCESS_DATA_ONLY":
                # Dados encontrados mas sem imagem
                await processing_msg.edit_text(
                    f"📊 <b>Dados encontrados!</b>\n\n"
                    f"Período: <b>{mes:02d}/{ano}</b>\n\n"
                    f"{message}\n\n"
                    f"<b>Nota:</b> Os dados foram encontrados, mas não foi possível gerar uma imagem do gráfico.",
                    parse_mode='HTML'
                )
            else:
                # Envia a imagem/PDF do gráfico
                logger.info(f"📤 Enviando arquivo (tamanho: {len(chart_image)} bytes)")
                try:
                    # Verifica se é PDF ou imagem
                    if "PDF" in message or len(chart_image) > 10000:  # PDFs são maiores
                        await update.message.reply_document(
                            document=chart_image,
                            filename=f"grafico_{mes:02d}_{ano}.pdf",
                            caption=f"📊 <b>Gráfico {mes:02d}/{ano}</b>\n\n{message}",
                            parse_mode='HTML'
                        )
                    else:
                        await update.message.reply_photo(
                            photo=chart_image,
                            caption=f"📊 <b>Gráfico {mes:02d}/{ano}</b>\n\n{message}",
                            parse_mode='HTML'
                        )
                    await processing_msg.delete()
                    logger.info("✅ Arquivo enviado com sucesso!")
                except Exception as photo_error:
                    logger.error(f"❌ Erro ao enviar arquivo: {photo_error}")
                    await processing_msg.edit_text(
                        f"⚠️ <b>Gráfico encontrado mas erro ao enviar!</b>\n\n"
                        f"Período: <b>{mes:02d}/{ano}</b>\n"
                        f"Status: <i>{message}</i>\n\n"
                        f"<b>Erro:</b> {str(photo_error)}",
                        parse_mode='HTML'
                    )
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
    
    # Handler para mensagens em linguagem natural (deve ser o último)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, processar_linguagem_natural))

    logger.info("Bot iniciado no modo Polling... Pressione Ctrl+C para parar.")
    application.run_polling()

if __name__ == '__main__':
    main()