# 🤖 Bot Financeiro Pessoal com IA

**Atividade Ponderada - Programação | Semana 5 | Módulo 7 | Engenharia de Software | Inteli**

## 📋 Enunciado da Atividade

Esta atividade consistiu na implementação de um chatbot inteligente integrado à API do Telegram, seguindo os seguintes requisitos:

### ✅ Requisitos Implementados

- **Integração à API do Telegram** - Bot funcional conectado ao Telegram
- **Vídeo de até 5 minutos** - Apresentação completa do chatbot
- **4 perguntas diferentes com 4 respostas distintas** - Demonstração de funcionalidades variadas
- **Memória de curto prazo** - Implementação de contexto conversacional onde uma pergunta realizada após outra pergunta provoca uma resposta diferente do chatbot (pergunta dependente de contexto)

### 🎬 Vídeo de Apresentação

**Assista ao vídeo completo da demonstração:**
[📹 Vídeo da Atividade - Bot Financeiro com IA](https://drive.google.com/file/d/1G0o-4t00H-KcGfeN_SxYs0LMkMiOODvd/view?usp=sharing)

## 🎯 Sobre o Projeto

Um assistente financeiro inteligente para Telegram que conecta diretamente com sua planilha Google Sheets para fornecer informações rápidas sobre saldos, transações e gráficos financeiros. **Agora com Inteligência Artificial integrada e memória de curto prazo!**

### 📊 **Configuração da Planilha**

**As instruções para criar a planilha e configurar tudo necessário para o bot ter acesso estão disponíveis neste repositório:**
[📋 Repositório de Configuração da Planilha](https://github.com/AndreLobo1/AQUI/tree/main)

Siga o passo a passo completo do repositório acima para gerar uma planilha idêntica à nossa e configurar todas as credenciais necessárias.

## 🚀 Configuração e Instalação

### 📋 Pré-requisitos

- Docker e Docker Compose instalados
- Conta Google Cloud com Google Sheets API habilitada
- Bot do Telegram criado via @BotFather
- **Chave da API do Google AI Studio (Gemini)** - [Obter aqui](https://aistudio.google.com/app/apikey)
- Planilha Google Sheets com aba "Saldos" e "Transações"

### 🔧 Como Obter as Credenciais

#### 1. **Token do Telegram Bot**
1. Abra o Telegram e procure por `@BotFather`
2. Envie `/newbot` e siga as instruções
3. Copie o token fornecido

#### 2. **Chave da API do Gemini**
1. Acesse [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Faça login com sua conta Google
3. Clique em "Create API Key"
4. Copie a chave gerada

#### 3. **Credenciais do Google Sheets**
1. Acesse [Google Cloud Console](https://console.cloud.google.com/)
2. Crie um novo projeto ou selecione um existente
3. Ative as APIs:
   - Google Sheets API
   - Google Drive API
4. Vá em "Credenciais" → "Criar credenciais" → "Conta de serviço"
5. Baixe o arquivo JSON da conta de serviço
6. **Converter para Base64:**
   ```bash
   # No terminal (macOS/Linux)
   base64 -i caminho/para/seu/arquivo.json
   
   # No Windows (PowerShell)
   [Convert]::ToBase64String([IO.File]::ReadAllBytes("caminho/para/seu/arquivo.json"))
   ```

### 📁 Configuração do Projeto

1. **Clone o repositório:**
   ```bash
   git clone <seu-repositorio>
   cd bobot
   ```

2. **Configure o arquivo `.env`:**
   ```env
   # Token do seu bot, obtido com o @BotFather
   TELEGRAM_TOKEN=seu_token_aqui
   
   # Chave da API do Google AI Studio para o Gemini
   GEMINI_API_KEY=sua_chave_aqui
   
   # Nome exato da sua planilha no Google Sheets
   SPREADSHEET_NAME=Carteira
   
   # O conteúdo Base64 do seu arquivo .json de credenciais do Google
   GOOGLE_CREDENTIALS_BASE64=seu_base64_aqui
   ```

3. **Execute com Docker:**
   ```bash
   # Construir e executar o container
   docker-compose up --build
   
   # Para executar em background
   docker-compose up -d --build
   
   # Para parar
   docker-compose down
   ```

## 🎯 Funcionalidades Demonstradas

### 🤖 **Inteligência Artificial (Gemini)**
- **Conversação Natural**: Fale com o bot em linguagem natural
- **Perguntas Inteligentes**: "Quanto tenho na conta X?", "Mostra meus saldos", "Qual meu saldo total?"
- **Contexto Financeiro**: O bot entende seus dados e responde de forma contextualizada
- **Memória de Curto Prazo**: Lembra do contexto da conversa anterior

### 🎯 **Comandos Disponíveis**
- **`/start`** - Mensagem de boas-vindas personalizada
- **`/help`** - Ajuda detalhada sobre todas as funcionalidades
- **`/saldo`** - Mostra saldos atualizados de todas as contas
- **`/grafico [ano/mês]`** - Busca e envia gráficos da planilha
- **`/status`** - Verifica a saúde do cache

### 🧠 **Memória Contextual**
- **Detecção de Perguntas Dependentes**: Identifica quando "quanto foi?" se refere ao contexto anterior
- **Respostas Contextuais**: Diferentes respostas baseadas na pergunta anterior
- **Limpeza Inteligente**: Limpa memória quando muda de tópico/período

## 🧪 Como Testar

### 1. **Teste Local**
```bash
# Executar bot localmente
docker-compose up --build

# Verificar logs
docker-compose logs -f
```

### 2. **Teste da Memória Contextual**

#### **Sequência 1: Contexto "Maior Gasto"**
1. Pergunte: "qual foi meu maior gasto?"
2. Bot responde: "Blablacar com R$ 150,00"
3. Pergunte: "quanto foi?"
4. Bot responde: "💰 R$ 150,00"

#### **Sequência 2: Contexto "Categoria que Gastou Mais"**
1. Pergunte: "com qual categoria gastei mais em agosto?"
2. Bot responde: "Blablacar"
3. Pergunte: "quanto foi?"
4. Bot responde: "💰 O total gasto com blablacar em agosto foi R$ 427,90"

**Mesma pergunta "quanto foi?" mas respostas diferentes!**

### 3. **Verificar Logs da Memória**
```bash
# Ver logs específicos de memória
docker-compose logs --tail=20 | grep -E "(🧠|memória|dependente)"

# Ver logs de debug
docker-compose logs --tail=30 | grep -E "(DEBUG|Filtrando)"
```

## 🎓 Conclusão da Atividade

Este projeto demonstra com sucesso a implementação de um chatbot inteligente que atende todos os requisitos da atividade:

✅ **Integração à API do Telegram** - Bot funcional e responsivo  
✅ **Vídeo de apresentação** - Demonstração completa das funcionalidades  
✅ **4 perguntas diferentes com 4 respostas distintas** - Variedade de funcionalidades  
✅ **Memória de curto prazo** - Contexto conversacional implementado com sucesso  

A implementação da memória de curto prazo permite que o bot mantenha contexto entre perguntas, respondendo de forma inteligente e contextualizada, demonstrando uma evolução significativa em relação a chatbots tradicionais.