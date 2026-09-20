"""Transformacoes: recorte, enriquecimento, descarte LGPD e priorizacao.

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
    """
    return (
        lf.join(
            empresas.select("cnpj_basico", "razao_social", "porte_empresa", "natureza_juridica"),
            on="cnpj_basico",
            how="left",
        )
        .join(
            simples.select("cnpj_basico", "opcao_mei", "data_exclusao_mei"),
            on="cnpj_basico",
            how="left",
        )
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


def remover_dados_pessoais(lf: pl.LazyFrame) -> pl.LazyFrame:
    """Descarta colunas de contato e endereco antes da saida versionada.

    A base contem MEI cuja razao social e o nome civil da pessoa fisica. O
    contato permanece disponivel na etapa de extracao para uso operacional,
    mas nao entra em nenhum artefato publicado.
    """
    return lf.drop([c for c in layout.COLUNAS_SENSIVEIS], strict=False)


# --------------------------------------------------------------------------
# Priorizacao
# --------------------------------------------------------------------------
# Regra explicita e auditavel -- nivel 1 da disciplina. Cada criterio soma
# pontos e escreve o proprio motivo, de modo que o analista veja por que a
# empresa apareceu naquela posicao. Nenhum modelo entra antes de existir
# evidencia de que a regra nao basta.

CRITERIOS = [
    ("CNAE principal em servicos de TI (divisao 62)", pl.col("cnae_fiscal_principal").str.zfill(7).str.starts_with("62"), 30),
    ("porte acima de microempresa", pl.col("porte_empresa").str.zfill(2) == "05", 25),
    ("empresa de pequeno porte", pl.col("porte_empresa").str.zfill(2) == "03", 15),
    ("estabelecimento matriz", pl.col("identificador_matriz_filial") == "1", 10),
    ("mais de 3 anos de atividade", pl.col("inicio") < pl.date(2023, 1, 1), 15),
    ("possui nome fantasia declarado", pl.col("nome_fantasia").str.strip_chars().str.len_chars() > 0, 5),
]

PENALIDADE_MEI = ("MEI: teto de faturamento e no maximo um empregado", pl.col("is_mei"), -40)


def priorizar(lf: pl.LazyFrame) -> pl.LazyFrame:
    """Calcula score e justificativa, mantendo apenas estabelecimentos ativos.

    Situacao cadastral ativa e criterio eliminatorio, nao pontuacao: empresa
    baixada nao e lead, e a qualquer peso ela ainda apareceria na lista.
    """
    criterios = CRITERIOS + [PENALIDADE_MEI]
    score = sum(
        (pl.when(cond).then(pontos).otherwise(0) for _, cond, pontos in criterios),
        start=pl.lit(0),
    )
    motivos = pl.concat_list(
        [pl.when(cond).then(pl.lit(rotulo)).otherwise(None) for rotulo, cond, _ in criterios]
    ).list.drop_nulls()

    return (
        lf.filter(pl.col("situacao_cadastral") == layout.SITUACAO_ATIVA)
        .with_columns(
            score.alias("score"),
            motivos.list.join(" | ").alias("justificativa"),
        )
        .sort("score", descending=True)
    )


COLUNAS_SAIDA = [
    "cnpj",
    "razao_social",
    "nome_fantasia",
    "municipio_nome",
    "cnae_fiscal_principal",
    "cnae_descricao",
    "porte_nome",
    "is_mei",
    "matriz_filial_nome",
    "inicio",
    "situacao_nome",
    "score",
    "justificativa",
]
