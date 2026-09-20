"""Pipeline de leads -- Atividade 02.

Entrada  : ZIP/CSV dos dados abertos de CNPJ da Receita Federal (competencia
           corrente), as dez particoes de Estabelecimentos e de Empresas,
           Simples e as tabelas de dominio Cnaes e Municipios.
Saida    : Parquet tratado com o universo recortado e CSV com a lista
           priorizada de leads, com telefone, e-mail e endereco para contato.
           Nenhum desses arquivos e versionado: `data/` esta no .gitignore.

Execucao:  python -m src.pipeline

Todas as etapas registram contagem em log. O relatorio de evidencia e gravado
em data/processed/evidencia.json para alimentar a documentacao sem que ninguem
precise copiar numero a mao.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import polars as pl

from . import carregar, extract, layout, perfilar, transformar, validar

log = logging.getLogger("pipeline")

RAIZ = Path(__file__).resolve().parent.parent
DIR_RAW = RAIZ / "data" / "raw"
DIR_CACHE = RAIZ / "data" / "cache"
DIR_OUT = RAIZ / "data" / "processed"


def executar() -> dict:
    inicio = time.perf_counter()
    DIR_OUT.mkdir(parents=True, exist_ok=True)

    # 1. Entrada -------------------------------------------------------------
    arquivos = extract.extrair(DIR_RAW)
    competencia = next(iter(arquivos.values())).parent.name
    dir_comp = DIR_RAW / competencia
    log.info("competencia processada: %s", competencia)

    lf_emp = carregar.empresas_completo(dir_comp, DIR_CACHE)
    lf_sim = carregar.simples(arquivos["Simples.zip"], DIR_CACHE)
    lf_cnae = carregar.cnaes(arquivos["Cnaes.zip"], DIR_CACHE)
    lf_mun = carregar.municipios(arquivos["Municipios.zip"], DIR_CACHE)

    # 2. Recorte -------------------------------------------------------------
    # Recorte fatia a fatia: o universo so existe inteiro dentro deste laco.
    # Cada fatia e materializada ja filtrada (BA + CNAE alvo, ~0,06% das
    # linhas) e o texto bruto e apagado antes da fatia seguinte.
    recebidos = 0
    na_uf = 0
    por_particao: dict[str, int] = {}
    recortes: list[pl.DataFrame] = []
    for particao, lf_fatia in carregar.estabelecimentos_particionado(
        dir_comp, DIR_CACHE
    ):
        # Um passe so: o polars compartilha a leitura da fatia entre as tres
        # consultas (common subplan elimination). O funil por filtro sai de
        # graca e e o que o slide precisa mostrar.
        contagem, contagem_uf, parcial = pl.collect_all(
            [
                lf_fatia.select(pl.len()),
                lf_fatia.filter(pl.col("uf") == layout.UF_ALVO).select(pl.len()),
                transformar.recortar(lf_fatia),
            ]
        )
        linhas = int(contagem.item())
        recebidos += linhas
        na_uf += int(contagem_uf.item())
        recortes.append(parcial)
        por_particao[particao] = por_particao.get(particao, 0) + parcial.height
        log.info("%s: %d linhas lidas, %d no recorte", particao, linhas, parcial.height)

    recortado = pl.concat(recortes, how="vertical")
    log.info("estabelecimentos lidos (censo): %d", recebidos)
    log.info("apos filtro UF=%s: %d", layout.UF_ALVO, na_uf)
    log.info(
        "apos recorte UF=%s e CNAE %s: %d",
        layout.UF_ALVO,
        "+".join(layout.CNAE_ALVO_PREFIXOS),
        recortado.height,
    )

    # 3. Validacao -----------------------------------------------------------
    cnaes_validos = lf_cnae.select(pl.col("codigo").str.zfill(7)).collect()["codigo"].to_list()
    marcado, regras = validar.aplicar(recortado.lazy(), cnaes_validos)
    marcado = marcado.collect()

    rel_validacao = validar.relatorio(marcado, regras)
    for r in rel_validacao:
        nivel = log.warning if r["reprovadas"] else log.info
        nivel("validacao %-20s reprovadas=%d  (%s)", r["regra"], r["reprovadas"], r["descricao"])

    valido, descartados = validar.descartar(marcado, regras)
    log.info("descartados por validacao: %d | restantes: %d", descartados, valido.height)

    # 4. Enriquecimento e contato -------------------------------------------
    enriquecido = transformar.enriquecer(valido.lazy(), lf_emp, lf_sim, lf_cnae, lf_mun)
    # Motor streaming: Empresas e Simples somam 8,1 GiB de texto e nao cabem
    # materializados, mesmo com a semi-juncao reduzindo o resultado.
    enriquecido = transformar.montar_contato(enriquecido).collect(engine="streaming")

    sem_porte = int(enriquecido["porte_empresa"].is_null().sum())
    if sem_porte:
        log.warning(
            "sem correspondencia em Empresas: %d (%.1f%%) -- particoes nao alinham por cnpj_basico",
            sem_porte,
            100 * sem_porte / enriquecido.height,
        )

    mei = int(enriquecido["is_mei"].sum())
    log.info("MEI na base recortada: %d (%.1f%%)", mei, 100 * mei / enriquecido.height)

    # 5. Priorizacao ---------------------------------------------------------
    leads = transformar.priorizar(enriquecido.lazy()).collect()
    log.info("leads ativos priorizados: %d", leads.height)

    # 6. Saida ---------------------------------------------------------------
    p_universo = DIR_OUT / "universo_tratado.parquet"
    p_leads = DIR_OUT / "leads_priorizados.csv"
    enriquecido.write_parquet(p_universo)
    leads.select(transformar.COLUNAS_SAIDA).write_csv(p_leads)
    log.info("gravado %s (%d linhas)", p_universo.name, enriquecido.height)
    log.info("gravado %s (%d linhas)", p_leads.name, leads.height)

    # 7. Evidencia -----------------------------------------------------------
    evidencia = {
        "competencia": competencia,
        "duracao_s": round(time.perf_counter() - inicio, 1),
        "recebidos": recebidos,
        "apos_uf": na_uf,
        "particoes_estabelecimentos": len(por_particao),
        "recorte_por_particao": por_particao,
        "apos_recorte": recortado.height,
        "descartados_validacao": descartados,
        "validacoes": rel_validacao,
        "sem_porte": sem_porte,
        "mei": mei,
        "universo_tratado": enriquecido.height,
        "leads_priorizados": leads.height,
        "ausentes": perfilar.ausentes(recortado.drop(["cnpj"], strict=False)).to_dicts(),
        "intervalo_temporal": perfilar.intervalo_temporal(recortado, "data_inicio_atividade"),
        "distribuicao_situacao": perfilar.distribuicao(enriquecido, "situacao_nome").to_dicts(),
        "distribuicao_porte": perfilar.distribuicao(enriquecido, "porte_nome").to_dicts(),
        "distribuicao_municipio": perfilar.distribuicao(enriquecido, "municipio_nome").to_dicts(),
        "distribuicao_cnae": perfilar.distribuicao(enriquecido, "cnae_descricao").to_dicts(),
    }
    (DIR_OUT / "evidencia.json").write_text(
        json.dumps(evidencia, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    log.info("evidencia gravada em %s", DIR_OUT / "evidencia.json")
    log.info("concluido em %.1fs", evidencia["duracao_s"])
    return evidencia


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    executar()
