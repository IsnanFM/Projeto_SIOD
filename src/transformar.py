"""Transformacoes: recorte, enriquecimento, contato e priorizacao.

A saida deste modulo e o artefato que o analista comercial consome: uma lista
ordenada de leads com a justificativa de cada posicao. Filtro sozinho nao
resolveria -- a base de TI na Bahia e dominada por MEI, e devolver tudo que
casa com o CNAE apenas transfere o problema de triagem para a pessoa.
"""

from __future__ import annotations

import logging

import polars as pl

from . import layout, validar

log = logging.getLogger(__name__)


def recortar(lf: pl.LazyFrame) -> pl.LazyFrame:
    """Aplica o recorte do projeto: UF alvo e prefixos de CNAE alvo.

    O filtro e por prefixo de divisao porque nenhum perfil-alvo real e uma
    subclasse unica de 7 digitos: uma software house pode estar em 6201, 6202
    ou 6204 conforme a escolha do contador.
    """
    prefixos = layout.CNAE_ALVO_PREFIXOS
    cnae = pl.col("cnae_fiscal_principal").str.zfill(7)
    return lf.filter(
        (pl.col("uf") == layout.UF_ALVO)
        & pl.any_horizontal([cnae.str.starts_with(p) for p in prefixos])
    )


def enriquecer(
    lf: pl.LazyFrame,
    empresas: pl.LazyFrame,
    simples: pl.LazyFrame,
    cnaes: pl.LazyFrame,
    municipios: pl.LazyFrame,
) -> pl.LazyFrame:
    """Junta porte, flag de MEI e descricoes legiveis de CNAE e municipio.

    MEI nao e um valor de `porte`: o campo so distingue micro, pequeno porte e
    demais. A marcacao vive em Simples.zip, e por isso exige esta juncao.

    Empresas e Simples sao reduzidos por semi-juncao antes do join: sao 66 e 40
    milhoes de linhas contra as ~15 mil do recorte, e casar tudo para depois
    descartar 99,98% estoura a memoria. A semi-juncao monta a tabela hash a
    partir do lado pequeno e so deixa passar o que interessa.
    """
    basicos = lf.select("cnpj_basico").unique()
    empresas_alvo = empresas.select(
        "cnpj_basico", "razao_social", "porte_empresa", "natureza_juridica"
    ).join(basicos, on="cnpj_basico", how="semi")
    simples_alvo = simples.select(
        "cnpj_basico", "opcao_mei", "data_exclusao_mei"
    ).join(basicos, on="cnpj_basico", how="semi")

    return (
        lf.join(empresas_alvo, on="cnpj_basico", how="left")
        .join(simples_alvo, on="cnpj_basico", how="left")
        .join(
            cnaes.rename({"codigo": "cnae_cod", "descricao": "cnae_descricao"}),
            left_on=pl.col("cnae_fiscal_principal").str.zfill(7),
            right_on=pl.col("cnae_cod").str.zfill(7),
            how="left",
        )
        .join(
            municipios.rename({"codigo": "mun_cod", "descricao": "municipio_nome"}),
            left_on="municipio",
            right_on="mun_cod",
            how="left",
        )
        .with_columns(
            # MEI ativo = optou e nao foi excluido. A exclusao ausente vem
            # como '00000000', nunca como nulo.
            (
                (pl.col("opcao_mei") == "S")
                & ~validar.expr_data_preenchida("data_exclusao_mei")
            )
            .fill_null(False)
            .alias("is_mei"),
            pl.col("situacao_cadastral")
            .replace_strict(layout.SITUACAO_CADASTRAL, default="Desconhecida")
            .alias("situacao_nome"),
            pl.col("porte_empresa")
            .str.zfill(2)
            .replace_strict(layout.PORTE_EMPRESA, default="Nao informado")
            .alias("porte_nome"),
            pl.col("identificador_matriz_filial")
            .replace_strict(layout.MATRIZ_FILIAL, default="Desconhecido")
            .alias("matriz_filial_nome"),
            pl.col("data_inicio_atividade").str.to_date("%Y%m%d", strict=False).alias("inicio"),
        )
    )


def montar_contato(lf: pl.LazyFrame) -> pl.LazyFrame:
    """Monta telefone, e-mail e endereco legiveis para o analista ligar.

    Sem contato a lista nao e acionavel: o analista teria nomes e nenhuma
    forma de abordar. Os tres campos vem do proprio cadastro da RFB, que e
    publico. O que nao acontece e publicacao: `data/` fica fora do git.
    """
    vazio = pl.lit("")
    telefone = (
        pl.when(pl.col("telefone_1").str.strip_chars().str.len_chars() > 0)
        .then(
            pl.format(
                "({}) {}",
                pl.col("ddd_1").str.strip_chars(),
                pl.col("telefone_1").str.strip_chars(),
            )
        )
        .otherwise(vazio)
    )
    endereco = pl.concat_str(
        [
            pl.col("tipo_logradouro").str.strip_chars(),
            pl.col("logradouro").str.strip_chars(),
            pl.col("numero").str.strip_chars(),
            pl.col("bairro").str.strip_chars(),
            pl.col("cep").str.strip_chars(),
        ],
        separator=" ",
        ignore_nulls=True,
    )
    return lf.with_columns(
        telefone.alias("telefone"),
        pl.col("correio_eletronico").str.strip_chars().str.to_lowercase().alias("email"),
        endereco.alias("endereco"),
    )


# --------------------------------------------------------------------------
# Priorizacao
# --------------------------------------------------------------------------
# Regra explicita e auditavel -- nivel 1 da disciplina. Nao ha pontuacao: somar
# pesos exigiria afirmar quanto "porte" vale em relacao a "matriz", e nao
# existe venda registrada que sustente esse numero. A lista e ordenada por
# criterios em ordem declarada de importancia -- o primeiro criterio manda, o
# segundo so desempata, e assim por diante. Trocar a ordem e uma decisao
# visivel; trocar um peso seria uma decisao escondida.

CRITERIOS = [
    (
        "porte acima de microempresa",
        pl.col("porte_empresa").str.zfill(2) == "05",
    ),
    (
        "empresa de pequeno porte",
        pl.col("porte_empresa").str.zfill(2) == "03",
    ),
    (
        "nao e MEI",
        ~pl.col("is_mei"),
    ),
    (
        "tecnologia como atividade-fim (CNAE na divisao 62)",
        pl.col("cnae_fiscal_principal").str.zfill(7).str.starts_with("62"),
    ),
    (
        "estabelecimento matriz",
        pl.col("identificador_matriz_filial") == "1",
    ),
    (
        "mais de 3 anos de atividade",
        pl.col("inicio") < pl.date(2023, 1, 1),
    ),
    (
        "possui nome fantasia declarado",
        pl.col("nome_fantasia").str.strip_chars().str.len_chars() > 0,
    ),
]

# Lead que nao atende criterio nenhum entrou so pelo filtro eliminatorio.
# Dizer isso por escrito mantem a invariante: nenhuma linha fica sem motivo.
SEM_CRITERIO = "nenhum criterio atendido: entrou apenas por estar ativa"


def priorizar(lf: pl.LazyFrame) -> pl.LazyFrame:
    """Ordena os estabelecimentos ativos pelos criterios, na ordem declarada.

    Situacao cadastral ativa e criterio eliminatorio, nao de ordenacao:
    empresa baixada nao e lead, e nao deve aparecer em posicao alguma.

    O que ordena e o que aparece escrito na coluna `justificativa`, entao a
    posicao nunca discorda do motivo.
    """
    atende = [cond.fill_null(False) for _, cond in CRITERIOS]
    motivos = pl.concat_list(
        [
            pl.when(cond).then(pl.lit(rotulo)).otherwise(None)
            for (rotulo, _), cond in zip(CRITERIOS, atende)
        ]
    ).list.drop_nulls()
    justificativa = (
        pl.when(motivos.list.len() == 0)
        .then(pl.lit(SEM_CRITERIO))
        .otherwise(motivos.list.join(" | "))
    )

    return (
        lf.filter(pl.col("situacao_cadastral") == layout.SITUACAO_ATIVA)
        .with_columns(
            *[c.alias(f"_c{i}") for i, c in enumerate(atende)],
            justificativa.alias("justificativa"),
        )
        .sort(
            [f"_c{i}" for i in range(len(CRITERIOS))] + ["inicio"],
            descending=[True] * len(CRITERIOS) + [False],
            nulls_last=True,
        )
        .drop([f"_c{i}" for i in range(len(CRITERIOS))])
        .with_row_index("posicao", offset=1)
    )


COLUNAS_SAIDA = [
    "posicao",
    "cnpj",
    "razao_social",
    "nome_fantasia",
    "telefone",
    "email",
    "municipio_nome",
    "endereco",
    "cnae_fiscal_principal",
    "cnae_descricao",
    "porte_nome",
    "is_mei",
    "matriz_filial_nome",
    "inicio",
    "situacao_nome",
    "justificativa",
]
