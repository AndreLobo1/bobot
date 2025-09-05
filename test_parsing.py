#!/usr/bin/env python3
"""
Script de teste para verificar o parsing de datas
"""

import re

def parse_ano_mes(texto):
    """Extrai ano e mês do texto do usuário."""
    print(f"🔍 Parsing texto: '{texto}'")
    
    texto_limpo = texto.strip().lower()
    print(f"🔍 Texto limpo: '{texto_limpo}'")
    
    # ESTRATÉGIA 1: Padrão YYYY/MM ou YYYY-MM (PRIORIDADE MÁXIMA)
    match = re.search(r'(\d{4})[/-](\d{1,2})', texto_limpo)
    if match:
        ano = int(match.group(1))
        mes = int(match.group(2))
        print(f"🔍 Resultado final (YYYY/MM): ano={ano}, mes={mes}")
        return ano, mes
    
    # ESTRATÉGIA 2: Padrão MM/YYYY ou MM-YYYY
    match = re.search(r'(\d{1,2})[/-](\d{4})', texto_limpo)
    if match:
        mes = int(match.group(1))
        ano = int(match.group(2))
        print(f"🔍 Resultado final (MM/YYYY): ano={ano}, mes={mes}")
        return ano, mes
    
    # ESTRATÉGIA 3: Padrão YYYY MM (com espaço)
    match = re.search(r'(\d{4})\s+(\d{1,2})', texto_limpo)
    if match:
        ano = int(match.group(1))
        mes = int(match.group(2))
        print(f"🔍 Resultado final (YYYY MM): ano={ano}, mes={mes}")
        return ano, mes
    
    # ESTRATÉGIA 4: Padrão MM YYYY (com espaço)
    match = re.search(r'(\d{1,2})\s+(\d{4})', texto_limpo)
    if match:
        mes = int(match.group(1))
        ano = int(match.group(2))
        print(f"🔍 Resultado final (MM YYYY): ano={ano}, mes={mes}")
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
            print(f"🔍 Encontrou mês por nome: '{mes_nome}' -> {mes_num}")
            # Procura por ano (4 dígitos) APENAS se não for parte de outro número
            ano_match = re.search(r'\b(\d{4})\b', texto_limpo)
            if ano_match:
                ano = int(ano_match.group(1))
                print(f"🔍 Resultado final (nome): ano={ano}, mes={mes_num}")
                return ano, mes_num
    
    print(f"❌ Nenhum padrão encontrado para: '{texto}'")
    return None, None

def test_parsing():
    """Testa diferentes formatos de data"""
    test_cases = [
        "2025/08",
        "agosto 2025", 
        "08/2025",
        "2025-08",
        "08-2025",
        "2025 08",
        "08 2025",
        "setembro 2024",
        "2024/09",
        "09/2024"
    ]
    
    print("🧪 TESTANDO PARSING DE DATAS")
    print("=" * 50)
    
    for test_case in test_cases:
        print(f"\n📝 Testando: '{test_case}'")
        resultado = parse_ano_mes(test_case)
        if resultado[0] and resultado[1]:
            print(f"✅ SUCESSO: {resultado[1]:02d}/{resultado[0]}")
        else:
            print(f"❌ FALHOU: {test_case}")
        print("-" * 30)

if __name__ == "__main__":
    test_parsing()
