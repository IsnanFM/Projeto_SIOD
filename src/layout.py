"""Layout dos arquivos da RFB e dominios de referencia.

Os CSV da Receita Federal nao possuem linha de cabecalho: os nomes abaixo vem
do documento oficial de metadados e sao a unica fonte de verdade sobre a ordem
das colunas. Manter essa definicao isolada e o que torna a leitura auditavel.
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# Layout dos arquivos
# --------------------------------------------------------------------------

COLUNAS_ESTABELECIMENTOS = [
    "cnpj_basico",
    "cnpj_ordem",
    "cnpj_dv",
    "identificador_matriz_filial",
    "nome_fantasia",
    "situacao_cadastral",
    "data_situacao_cadastral",
    "motivo_situacao_cadastral",
    "nome_cidade_exterior",
    "pais",
    "data_inicio_atividade",
    "cnae_fiscal_principal",
    "cnae_fiscal_secundaria",
    "tipo_logradouro",
    "logradouro",
    "numero",
    "complemento",
    "bairro",
    "cep",
    "uf",
    "municipio",
    "ddd_1",
    "telefone_1",
    "ddd_2",
    "telefone_2",
    "ddd_fax",
    "fax",
    "correio_eletronico",
    "situacao_especial",
    "data_situacao_especial",
]

COLUNAS_EMPRESAS = [
    "cnpj_basico",
    "razao_social",
    "natureza_juridica",
    "qualificacao_responsavel",
    "capital_social",
    "porte_empresa",
    "ente_federativo_responsavel",
]

COLUNAS_SIMPLES = [
    "cnpj_basico",
    "opcao_simples",
    "data_opcao_simples",
    "data_exclusao_simples",
    "opcao_mei",
    "data_opcao_mei",
    "data_exclusao_mei",
]

COLUNAS_CNAES = ["codigo", "descricao"]
COLUNAS_MUNICIPIOS = ["codigo", "descricao"]

# --------------------------------------------------------------------------
# Dominios de referencia
# --------------------------------------------------------------------------

SITUACAO_CADASTRAL = {
    "01": "Nula",
    "02": "Ativa",
    "03": "Suspensa",
    "04": "Inapta",
    "08": "Baixada",
}
SITUACAO_ATIVA = "02"

PORTE_EMPRESA = {
    "00": "Nao informado",
    "01": "Micro empresa",
    "03": "Empresa de pequeno porte",
    "05": "Demais",
}

MATRIZ_FILIAL = {"1": "Matriz", "2": "Filial"}

# --------------------------------------------------------------------------
# Contato e publicacao
# --------------------------------------------------------------------------
# Telefone, e-mail e endereco sao publicados pela propria RFB no cadastro e
# sao o que torna a lista acionavel: sem eles o analista tem nomes, nao leads.
# Por isso entram na saida.
#
# A restricao e de PUBLICACAO, nao de uso: `data/` esta fora do controle de
# versao e nenhum arquivo com contato e commitado. A base inclui MEI e
# empresario individual, cuja razao social e o nome civil da pessoa fisica --
# ao divulgar qualquer recorte fora do time, o contato sai antes.

COLUNAS_CONTATO = [
    "ddd_1",
    "telefone_1",
    "correio_eletronico",
    "tipo_logradouro",
    "logradouro",
    "numero",
    "bairro",
    "cep",
]

# --------------------------------------------------------------------------
# Recorte do projeto
# --------------------------------------------------------------------------
# "Tecnologia" nao e um codigo CNAE: atravessa quatro secoes da CNAE 2.0.
# O nucleo do perfil-alvo do analista comercial sao os servicos de TI
# (divisao 62) e os servicos de informacao (divisao 63), ambos da secao J.
# Ficam de fora, por decisao registrada: divisao 26 (fabricacao de hardware,
# que e industria), 61 (telecomunicacoes), 95 (reparacao) e 4651 (revenda).

UF_ALVO = "BA"
CNAE_ALVO_PREFIXOS = ["62", "63"]
