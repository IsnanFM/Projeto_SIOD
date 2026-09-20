"""Validacoes do pipeline.

Cinco regras, todas ligadas a defeitos reais observados na fonte. Cada regra
marca linhas invalidas em coluna propria; o descarte acontece em um unico
ponto, de modo que o relatorio consiga atribuir cada linha perdida a sua causa
-- exigencia do item 5 da Atividade 02 ("erros, descartes, correcoes ou
alertas gerados durante a execucao").
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass

import polars as pl

from . import layout

log = logging.getLogger(__name__)

# Pesos do modulo 11 para os dois digitos verificadores do CNPJ.
PESOS_DV1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
PESOS_DV2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]


def expr_cnpj() -> pl.Expr:
    """CNPJ de 14 digitos, montado a partir das tres colunas da RFB.

    O identificador nao existe pronto no arquivo: vem quebrado em basico (8),
    ordem (4) e digito verificador (2).
    """
    return (
        pl.col("cnpj_basico").str.zfill(8)
        + pl.col("cnpj_ordem").str.zfill(4)
        + pl.col("cnpj_dv").str.zfill(2)
    ).alias("cnpj")


def _digito(coluna: str, pos: int) -> pl.Expr:
    return pl.col(coluna).str.slice(pos, 1).cast(pl.Int32, strict=False)


def _dv_esperado(pesos: list[int]) -> pl.Expr:
    soma = sum(
        (_digito("cnpj", i) * peso for i, peso in enumerate(pesos)),
        start=pl.lit(0),
    )
    resto = soma % 11
    return pl.when(resto < 2).then(0).otherwise(11 - resto)


def expr_dv_valido() -> pl.Expr:
    """Confere os dois digitos verificadores pelo modulo 11."""
    dv1 = _dv_esperado(PESOS_DV1)
    dv2 = _dv_esperado(PESOS_DV2)
    return (_digito("cnpj", 12) == dv1) & (_digito("cnpj", 13) == dv2)


def expr_data_valida(coluna: str) -> pl.Expr:
    """Data AAAAMMDD parseavel, nao nula e nao futura.

    A RFB usa '00000000' como ausencia; o parse nao estrito devolve nulo nesse
    caso, o que e exatamente o comportamento desejado.
    """
    data = pl.col(coluna).str.to_date("%Y%m%d", strict=False)
    return data.is_not_null() & (data <= pl.lit(dt.date.today()))


DATA_AUSENTE = "00000000"


def expr_data_preenchida(coluna: str) -> pl.Expr:
    """Verdadeiro quando a coluna de data traz um valor real.

    A RFB nao usa nulo em coluna de data: ausencia vem como '00000000'. Tratar
    esse sentinela como data valida inverte o sentido de qualquer condicao que
    pergunte "este evento ocorreu?".
    """
    c = pl.col(coluna).str.strip_chars()
    return c.is_not_null() & (c != DATA_AUSENTE) & (c.str.len_chars() > 0)


@dataclass(frozen=True)
class Regra:
    nome: str
    descricao: str
    expr: pl.Expr


def regras(cnaes_validos: list[str]) -> list[Regra]:
    return [
        Regra(
            "dv_cnpj",
            "digito verificador do CNPJ confere pelo modulo 11",
            expr_dv_valido(),
        ),
        Regra(
            "situacao_dominio",
            "situacao cadastral pertence ao dominio oficial",
            pl.col("situacao_cadastral").is_in(list(layout.SITUACAO_CADASTRAL)),
        ),
        Regra(
            "cnae_existe",
            "CNAE principal existe na tabela oficial Cnaes.zip",
            pl.col("cnae_fiscal_principal").str.zfill(7).is_in(cnaes_validos),
        ),
        Regra(
            "data_inicio_valida",
            "data de inicio de atividade parseavel e nao futura",
            expr_data_valida("data_inicio_atividade"),
        ),
    ]


def aplicar(lf: pl.LazyFrame, cnaes_validos: list[str]) -> tuple[pl.LazyFrame, list[Regra]]:
    """Adiciona coluna booleana por regra, sem descartar nada ainda.

    Manter a marcacao separada do descarte permite contar quantas linhas cada
    regra reprovou, inclusive quando a mesma linha reprova em varias.
    """
    rs = regras(cnaes_validos)
    lf = lf.with_columns(expr_cnpj())
    return lf.with_columns([r.expr.alias(f"ok_{r.nome}") for r in rs]), rs


def relatorio(df: pl.DataFrame, rs: list[Regra]) -> list[dict]:
    """Quantas linhas cada regra reprovou, e o total efetivamente descartado."""
    linhas = []
    for r in rs:
        reprovadas = int(df.height - df[f"ok_{r.nome}"].sum())
        linhas.append({"regra": r.nome, "descricao": r.descricao, "reprovadas": reprovadas})

    duplicados = int(df.height - df["cnpj"].n_unique())
    linhas.append(
        {
            "regra": "cnpj_unico",
            "descricao": "CNPJ de 14 digitos nao se repete na amostra",
            "reprovadas": duplicados,
        }
    )
    return linhas


def descartar(df: pl.DataFrame, rs: list[Regra]) -> tuple[pl.DataFrame, int]:
    """Remove linhas reprovadas em qualquer regra e duplicidades de CNPJ."""
    antes = df.height
    colunas_ok = [f"ok_{r.nome}" for r in rs]
    valido = df.filter(pl.all_horizontal(colunas_ok)).unique(subset=["cnpj"], keep="first")
    return valido.drop(colunas_ok), antes - valido.height
