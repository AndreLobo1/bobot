# 🤖 Bot Financeiro Pessoal

Um assistente financeiro inteligente para Telegram que conecta diretamente com sua planilha Google Sheets para fornecer informações rápidas sobre saldos, transações e gráficos financeiros.

## 📋 Funcionalidades

### 🎯 Comandos Disponíveis

- **`/start`** - Mensagem de boas-vindas personalizada com lista de comandos
- **`/help`** - Ajuda detalhada sobre todas as funcionalidades
- **`/saldo`** - Mostra saldos atualizados de todas as contas com total geral
- **`/grafico [ano/mês]`** - Busca e envia gráficos da planilha para período específico
- **`/status`** - Verifica a saúde do cache e quando foi a última atualização

### 💡 Características Principais

- **Cache Inteligente**: Sistema de cache que mantém dados por 1 dia
- **Parsing Robusto**: Converte valores monetários brasileiros automaticamente
- **Busca de Gráficos**: Localiza e envia gráficos da planilha por período
- **Formatação HTML**: Mensagens bem formatadas e legíveis
- **Logs Detalhados**: Sistema de logging para monitoramento
- **Tratamento de Erros**: Respostas amigáveis para problemas de conexão

## 🚀 Como Executar

### Pré-requisitos

- Docker e Docker Compose instalados
- Conta Google Cloud com Google Sheets API habilitada
- Bot do Telegram criado via @BotFather
- Planilha Google Sheets com aba "Saldos" e gráficos

### 1. Configuração Inicial

Clone o repositório e configure as variáveis de ambiente:

```bash
git clone <seu-repositorio>
cd bobot
```

### 2. Configurar Variáveis de Ambiente

Crie o arquivo `.env` com as seguintes variáveis:

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

### 3. Executar com Docker

```bash
# Construir e executar o container
docker-compose up --build

# Para executar em background
docker-compose up -d --build

# Para parar
docker-compose down
```

## 📊 Estrutura da Planilha

### Aba "Saldos"

A planilha deve ter uma aba chamada "Saldos" com as seguintes colunas:

| Coluna | Descrição | Exemplo |
|--------|-----------|---------|
| `CONTA` | Nome da conta bancária | "Nubank", "Itaú" |
| `SALDO ATUAL (R$)` | Saldo atual da conta | "R$ 1.234,56" |

### Gráficos

Para o comando `/grafico` funcionar, sua planilha deve conter gráficos que podem ser:

- **Gráficos em abas específicas**: Abas nomeadas com padrões como "2024-09", "09/2024", etc.
- **Gráficos em qualquer aba**: Com títulos que contenham o ano/mês
- **Gráficos em células**: Localizados próximos a células com datas

### Exemplo de Dados

```
CONTA          | SALDO ATUAL (R$)
---------------|------------------
Nubank         | R$ 2.500,00
Itaú           | R$ 1.750,50
Caixa          | R$ 3.200,75
```

## 🔧 Como Funciona

### Arquitetura do Sistema

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Telegram      │    │   Bot Python    │    │  Google Sheets  │
│   (Usuário)     │◄──►│   (Docker)      │◄──►│   (Planilha)    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │   Cache Local   │
                       │   (1 dia)       │
                       └─────────────────┘
```

### Sistema de Cache

O bot utiliza um sistema de cache inteligente para otimizar performance:

- **Duração**: Cache válido por 1 dia
- **Atualização**: Automática quando necessário
- **Fallback**: Busca dados da planilha se cache estiver vazio
- **Timestamp**: Mostra quando foi a última atualização

### Busca de Gráficos

O comando `/grafico` utiliza múltiplas estratégias para encontrar gráficos:

1. **Busca em Todas as Abas**: Procura por gráficos em todas as abas da planilha
2. **Busca em Aba Específica**: Procura por abas com nomes como "2024-09", "09/2024"
3. **Busca em Células**: Procura por gráficos próximos a células com datas

### Fluxo de Funcionamento

1. **Inicialização**: Bot inicia e conecta ao Telegram
2. **Primeira Requisição**: Usuário envia `/saldo` ou `/grafico`
3. **Verificação de Cache**: Bot verifica se tem dados em cache (apenas para saldos)
4. **Busca de Dados**: Se necessário, busca da planilha Google Sheets
5. **Processamento**: Converte valores monetários brasileiros ou localiza gráficos
6. **Resposta**: Envia mensagem formatada ou imagem do gráfico

## 🛠️ Desenvolvimento

### Estrutura do Projeto

```
bobot/
├── bot.py              # Código principal do bot
├── requirements.txt    # Dependências Python
├── Dockerfile          # Configuração Docker
├── docker-compose.yml  # Orquestração Docker
├── .env                # Variáveis de ambiente
├── .gitignore          # Arquivos ignorados pelo Git
├── env.example         # Exemplo de variáveis de ambiente
└── README.md           # Esta documentação
```

### Dependências Principais

- `python-telegram-bot[job-queue]` - Framework do bot Telegram
- `python-dotenv` - Gerenciamento de variáveis de ambiente
- `gspread` - Integração com Google Sheets
- `oauth2client` - Autenticação Google
- `pandas` - Manipulação de dados
- `Pillow` - Processamento de imagens
- `requests` - Requisições HTTP

### Funções Principais

#### `get_google_sheets_client()`
- Decodifica credenciais Base64
- Configura autenticação OAuth2
- Retorna cliente autorizado do Google Sheets

#### `update_cache(context)`
- Busca dados da planilha
- Atualiza cache local
- Registra timestamp da atualização

#### `parse_valor_brl(valor_raw)`
- Converte valores monetários brasileiros
- Remove "R$", pontos e vírgulas
- Retorna float para cálculos

#### `parse_ano_mes(texto)`
- Extrai ano e mês do texto do usuário
- Suporta múltiplos formatos (2024/09, setembro 2024, etc.)
- Valida entrada do usuário

#### `buscar_grafico_planilha(ano, mes)`
- Coordena a busca de gráficos
- Utiliza múltiplas estratégias de busca
- Retorna imagem do gráfico ou mensagem de erro

## 🧪 Como Testar

### 1. Teste Local

```bash
# Executar bot localmente
docker-compose up --build

# Verificar logs
docker-compose logs -f
```

### 2. Teste no Telegram

1. Abra o Telegram
2. Procure seu bot pelo username
3. Envie `/start` para iniciar
4. Teste os comandos:
   - `/help` - Ver ajuda
   - `/saldo` - Ver saldos
   - `/grafico 2024/09` - Buscar gráfico
   - `/status` - Ver status do cache

### 3. Verificar Funcionamento

**Resposta esperada do `/saldo`:**
```
💰 SALDOS DAS CONTAS

🏦 Nubank: R$ 2.500,00
🏦 Itaú: R$ 1.750,50
🏦 Caixa: R$ 3.200,75

📊 TOTAL GERAL: R$ 7.451,25

🔄 Cache de 04/09/2024 14:30:15
```

**Resposta esperada do `/grafico 2024/09`:**
```
🔍 Buscando gráfico para: 2024/09
Isso pode levar alguns segundos...

📊 Gráfico 09/2024

Gráfico encontrado na aba '2024-09'
```

## 📊 Comando Gráfico

### Como Usar

O comando `/grafico` permite buscar gráficos da sua planilha por período:

```bash
/grafico 2024/09          # Setembro de 2024
/grafico setembro 2024     # Setembro de 2024
/grafico 09/2024           # Setembro de 2024
/grafico 2024-09           # Setembro de 2024
```

### Formatos Aceitos

- **Numérico**: `2024/09`, `09/2024`, `2024-09`, `09-2024`
- **Texto**: `setembro 2024`, `set 2024`, `dezembro 2024`
- **Misto**: `2024 09`, `09 2024`

### Estratégias de Busca

1. **Busca por Título**: Procura gráficos com ano/mês no título
2. **Busca por Aba**: Procura abas nomeadas com o período
3. **Busca por Célula**: Procura gráficos próximos a células com datas

### Dicas para Gráficos

- **Nomeie suas abas** com padrões como "2024-09" ou "09/2024"
- **Use títulos descritivos** nos gráficos incluindo o período
- **Mantenha os gráficos visíveis** (não ocultos)
- **Teste diferentes formatos** de data

## 🔍 Troubleshooting

### Problemas Comuns

#### 1. "Cache vazio" ou "Não foi possível buscar os dados"

**Causa**: Problemas de autenticação ou configuração
**Solução**: 
- Verificar se `GOOGLE_CREDENTIALS_BASE64` está no `.env`
- Confirmar se a planilha tem permissão para o service account
- Verificar se o nome da planilha está correto

#### 2. "Colunas esperadas não encontradas"

**Causa**: Estrutura da planilha diferente do esperado
**Solução**:
- Verificar se a aba se chama "Saldos"
- Confirmar se as colunas são "CONTA" e "SALDO ATUAL (R$)"
- Verificar se não há espaços extras nos nomes

#### 3. "Gráfico não encontrado"

**Causa**: Gráfico não existe ou não está acessível
**Solução**:
- Verificar se existe gráfico para o período solicitado
- Confirmar se o gráfico está visível (não oculto)
- Tentar diferentes formatos de data
- Verificar se a planilha tem permissões adequadas

#### 4. Bot não responde

**Causa**: Problemas de conexão ou token inválido
**Solução**:
- Verificar se `TELEGRAM_TOKEN` está correto
- Confirmar se o bot não foi bloqueado
- Verificar logs do Docker

### Logs Úteis

```bash
# Ver logs em tempo real
docker-compose logs -f

# Ver logs específicos do bot
docker-compose logs bot

# Ver logs de erro
docker-compose logs bot | grep ERROR

# Ver logs de gráfico
docker-compose logs bot | grep -i grafico
```

## 🔐 Segurança

### Boas Práticas

- **Nunca commite** o arquivo `.env` no Git
- **Use service account** do Google Cloud (não credenciais pessoais)
- **Restrinja permissões** do service account apenas ao necessário
- **Monitore logs** regularmente para detectar problemas

### Variáveis Sensíveis

- `TELEGRAM_TOKEN` - Token do bot (não compartilhe)
- `GOOGLE_CREDENTIALS_BASE64` - Credenciais do Google (não compartilhe)
- `GEMINI_API_KEY` - Chave da API do Gemini (não compartilhe)

## 📈 Monitoramento

### Métricas Importantes

- **Tempo de resposta** do comando `/saldo`
- **Taxa de sucesso** das atualizações de cache
- **Taxa de sucesso** da busca de gráficos
- **Erros de autenticação** com Google Sheets
- **Uso de memória** do container Docker

### Logs de Monitoramento

O bot gera logs detalhados para monitoramento:

```
2024-09-04 14:30:15 - __main__ - INFO - 🔄 Atualizando cache...
2024-09-04 14:30:16 - __main__ - INFO - ✅ Cache de saldos atualizado: 3 registros.
2024-09-04 14:30:17 - __main__ - INFO - 🔍 Buscando gráfico para: 2024/09
2024-09-04 14:30:18 - __main__ - INFO - 📊 Gráfico encontrado na aba '2024-09'
2024-09-04 14:30:19 - __main__ - INFO - Bot iniciado no modo Polling...
```

## 🤝 Contribuição

### Como Contribuir

1. Fork o projeto
2. Crie uma branch para sua feature (`git checkout -b feature/nova-funcionalidade`)
3. Commit suas mudanças (`git commit -am 'Adiciona nova funcionalidade'`)
4. Push para a branch (`git push origin feature/nova-funcionalidade`)
5. Abra um Pull Request

### Padrões de Código

- Use docstrings para documentar funções
- Mantenha logs informativos
- Trate erros adequadamente
- Teste suas mudanças antes de commitar

## 📄 Licença

Este projeto está sob a licença MIT. Veja o arquivo LICENSE para mais detalhes.

## 🆘 Suporte

### Onde Obter Ajuda

- **Issues do GitHub**: Para bugs e problemas
- **Documentação**: Este README e comentários no código
- **Logs**: Sempre verifique os logs primeiro

### Informações Úteis

- **Versão do Bot**: 1.1.0
- **Python**: 3.11
- **Docker**: Última versão estável
- **Telegram Bot API**: v6.0+

---

**Desenvolvido com ❤️ para facilitar o controle financeiro pessoal**
