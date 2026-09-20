"""Leitura dos arquivos brutos da RFB.

Duas particularidades da fonte governam este modulo:

1. Os CSV vem em ISO-8859-1 (latin-1). O polars le apenas UTF-8, entao o ZIP e
   transcodificado uma unica vez para um CSV UTF-8 em cache. Como latin-1 e
   monobyte, a transcodificacao por blocos e segura -- nao existe caractere
   partido entre blocos.
2. Os arquivos nao tem cabecalho. Os nomes vem de `layout.py`.

A leitura e preguicosa (`scan_csv`): nenhuma particao inteira e materializada
em memoria, o que mantem o pipeline executavel em maquina comum.
"""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path

import polars as pl

from . import layout

log = logging.getLogger(__name__)

BLOCO = 8 << 20  # 8 MiB


def transcodificar(caminho_zip: Path, dir_cache: Path) -> Path:
    """Extrai o unico membro do ZIP convertendo latin-1 -> UTF-8.

    Resultado fica em cache: reexecucoes do pipeline nao repetem o trabalho.
    """
    destino = dir_cache / (caminho_zip.stem + ".csv")
    if destino.exists():
        log.info("cache: %s (%.1f MB)", destino.name, destino.stat().st_size / 1024**2)
        return destino

    dir_cache.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_suffix(".csv.part")

    with zipfile.ZipFile(caminho_zip) as z:
        membro = z.namelist()[0]
        log.info("transcodificando %s -> %s", membro, destino.name)
        with z.open(membro) as origem, open(parcial, "wb") as saida:
            while bloco := origem.read(BLOCO):
                saida.write(bloco.decode("latin-1").encode("utf-8"))

    parcial.rename(destino)
    log.info("transcodificado: %s (%.1f MB)", destino.name, destino.stat().st_size / 1024**2)
    return destino


def _scan(caminho_csv: Path, colunas: list[str]) -> pl.LazyFrame:
    """LazyFrame com todas as colunas como texto.

    Tudo entra como texto de proposito: a conversao de tipo e uma etapa de
    transformacao explicita e validada, nao um efeito colateral da leitura.
    Deixar o polars inferir tipo aqui mascararia justamente os defeitos que a
    Atividade 01 pede para medir.
    """
    return pl.scan_csv(
        caminho_csv,
        separator=";",
        has_header=False,
        new_columns=colunas,
        schema_overrides={c: pl.String for c in colunas},
        quote_char='"',
        truncate_ragged_lines=True,
        infer_schema_length=0,
    )


def estabelecimentos(caminho_zip: Path, dir_cache: Path) -> pl.LazyFrame:
    return _scan(transcodificar(caminho_zip, dir_cache), layout.COLUNAS_ESTABELECIMENTOS)


def empresas(caminho_zip: Path, dir_cache: Path) -> pl.LazyFrame:
    return _scan(transcodificar(caminho_zip, dir_cache), layout.COLUNAS_EMPRESAS)


def empresas_completo(dir_raw: Path, dir_cache: Path) -> pl.LazyFrame:
    """Concatena as dez particoes de Empresas.

    Necessario porque o particionamento de Empresas e independente do de
    Estabelecimentos: usar apenas a particao de mesmo indice cobriria cerca de
    10% dos registros. Medido em 2026-09, ver docs/atividade-02-pipeline.md.
    """
    partes = sorted(dir_raw.glob("Empresas*.zip"))
    if not partes:
        raise FileNotFoundError(f"nenhuma particao de Empresas em {dir_raw}")
    log.info("Empresas: %d particoes", len(partes))
    return pl.concat([empresas(p, dir_cache) for p in partes], how="vertical")


def simples(caminho_zip: Path, dir_cache: Path) -> pl.LazyFrame:
    return _scan(transcodificar(caminho_zip, dir_cache), layout.COLUNAS_SIMPLES)


def cnaes(caminho_zip: Path, dir_cache: Path) -> pl.LazyFrame:
    return _scan(transcodificar(caminho_zip, dir_cache), layout.COLUNAS_CNAES)


def municipios(caminho_zip: Path, dir_cache: Path) -> pl.LazyFrame:
    return _scan(transcodificar(caminho_zip, dir_cache), layout.COLUNAS_MUNICIPIOS)
