"""Caracterizacao da amostra -- suporte a Atividade 01.

As funcoes devolvem DataFrames em vez de imprimir, para que o mesmo codigo
sirva ao notebook de exploracao e ao relatorio de evidencia do pipeline. E o
que evita escrever a analise duas vezes.

Ausencia na RFB aparece de duas formas: campo vazio (nulo apos a leitura) e
campo com espacos. As duas contam como ausente aqui.
"""

from __future__ import annotations

import polars as pl


def _ausente(coluna: str) -> pl.Expr:
    c = pl.col(coluna)
    return c.is_null() | (c.str.strip_chars().str.len_chars() == 0)


def dimensoes(df: pl.DataFrame) -> dict:
    return {"registros": df.height, "atributos": df.width}


def ausentes(df: pl.DataFrame) -> pl.DataFrame:
    """Percentual de ausencia por coluna, do pior para o melhor."""
    total = df.height
    linhas = [
        {
            "coluna": c,
            "ausentes": int(df.select(_ausente(c).sum()).item()),
            "pct": round(100 * df.select(_ausente(c).sum()).item() / total, 2),
        }
        for c in df.columns
    ]
    return pl.DataFrame(linhas).sort("pct", descending=True)


def duplicidades(df: pl.DataFrame, chave: str) -> dict:
    unicos = df[chave].n_unique()
    return {"chave": chave, "linhas": df.height, "unicos": unicos, "duplicadas": df.height - unicos}


def distribuicao(df: pl.DataFrame, coluna: str, topo: int = 10) -> pl.DataFrame:
    total = df.height
    return (
        df.group_by(coluna)
        .len(name="registros")
        .with_columns((100 * pl.col("registros") / total).round(2).alias("pct"))
        .sort("registros", descending=True)
        .head(topo)
    )


def intervalo_temporal(df: pl.DataFrame, coluna: str) -> dict:
    data = df.select(pl.col(coluna).str.to_date("%Y%m%d", strict=False).alias("d"))["d"]
    return {
        "coluna": coluna,
        "minimo": str(data.min()),
        "maximo": str(data.max()),
        "nao_parseaveis": int(data.is_null().sum()),
    }
