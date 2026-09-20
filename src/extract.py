"""Extracao dos dados abertos de CNPJ da Receita Federal.

A RFB nao publica API de consulta em massa. A distribuicao e feita por um
compartilhamento publico Nextcloud, acessivel por WebDAV:

    endpoint : https://arquivos.receitafederal.gov.br/public.php/webdav/
    auth     : usuario = token do share, senha vazia
    caminho  : Dados/Cadastros/CNPJ/<AAAA-MM>/

O download e idempotente e retomavel: arquivo ja presente nao e rebaixado,
arquivo parcial continua de onde parou via cabecalho Range.
"""

from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

log = logging.getLogger(__name__)

BASE = "https://arquivos.receitafederal.gov.br/public.php/webdav/"
TOKEN = "gn672Ad4CF8N6TK"
AUTH = (TOKEN, "")
RAIZ = "Dados/Cadastros/CNPJ/"

NS = {"d": "DAV:"}
BLOCO = 1 << 20  # 1 MiB

# A amostra usa a particao 1 de Estabelecimentos: a particao 0 e
# desproporcional (2,1 GB contra ~330 MB nas demais).
#
# Empresas vem COMPLETO, e nao apenas a particao de mesmo indice. Medido na
# competencia 2026-09: os basicos de Estabelecimentos1 tem apenas 10,3% de
# intersecao com Empresas1 -- o particionamento das duas tabelas e
# independente. Usar so a particao 1 deixaria 77,6% dos registros sem porte,
# que e o discriminador principal da priorizacao.
#
# Simples nao e particionado: um unico arquivo cobre toda a base.
ARQUIVOS_AMOSTRA = (
    "Cnaes.zip",
    "Municipios.zip",
    "Estabelecimentos1.zip",
    "Simples.zip",
    *(f"Empresas{i}.zip" for i in range(10)),
)


def listar(caminho: str) -> list[str]:
    """PROPFIND Depth:1 -- nomes dos filhos diretos de `caminho`."""
    r = requests.request(
        "PROPFIND", BASE + caminho, auth=AUTH, headers={"Depth": "1"}, timeout=60
    )
    r.raise_for_status()
    hrefs = [e.text for e in ET.fromstring(r.content).findall("d:response/d:href", NS)]
    return [h.rstrip("/").split("/")[-1] for h in hrefs[1:]]


def competencia_mais_recente() -> str:
    """Competencia AAAA-MM mais recente publicada.

    Descoberta em tempo de execucao para que o pipeline nao expire quando a
    RFB publicar o mes seguinte.
    """
    meses = [n for n in listar(RAIZ) if len(n) == 7 and n[:4].isdigit()]
    if not meses:
        raise RuntimeError("nenhuma competencia encontrada no share da RFB")
    return max(meses)


def baixar(caminho_remoto: str, destino: Path, tentativas: int = 5) -> Path:
    """Baixa `caminho_remoto` para `destino`, retomando download parcial.

    Confere Content-Length ao final. Grava em .part e renomeia apenas apos a
    conferencia, para que uma execucao interrompida nunca deixe um arquivo
    truncado com aparencia de completo.

    O servidor da RFB derruba conexoes longas: cada tentativa retoma do ponto
    ja gravado em disco, entao a repeticao nao rebaixa o que ja veio.
    """
    if destino.exists():
        log.info(
            "ja em disco, pulando: %s (%.1f MB)",
            destino.name,
            destino.stat().st_size / 1024**2,
        )
        return destino

    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_suffix(destino.suffix + ".part")

    for tentativa in range(1, tentativas + 1):
        ja_baixado = parcial.stat().st_size if parcial.exists() else 0
        headers = {"Range": f"bytes={ja_baixado}-"} if ja_baixado else {}
        if ja_baixado:
            log.info(
                "retomando %s de %.1f MB (tentativa %d/%d)",
                destino.name,
                ja_baixado / 1024**2,
                tentativa,
                tentativas,
            )
        try:
            with requests.get(
                BASE + caminho_remoto,
                auth=AUTH,
                headers=headers,
                stream=True,
                timeout=(30, 300),
            ) as r:
                r.raise_for_status()
                esperado = ja_baixado + int(r.headers.get("Content-Length", 0))
                with open(parcial, "ab") as fh:
                    for bloco in r.iter_content(chunk_size=BLOCO):
                        fh.write(bloco)
        except (requests.Timeout, requests.ConnectionError) as erro:
            if tentativa == tentativas:
                raise
            log.warning("%s: %s -- nova tentativa", destino.name, type(erro).__name__)
            time.sleep(5 * tentativa)
            continue

        obtido = parcial.stat().st_size
        if esperado and obtido != esperado:
            raise IOError(f"{destino.name}: esperado {esperado} B, obtido {obtido} B")

        parcial.rename(destino)
        log.info("baixado: %s (%.1f MB)", destino.name, obtido / 1024**2)
        return destino

    raise RuntimeError(f"{destino.name}: download nao concluido")


def extrair_amostra(
    dir_destino: Path, competencia: str | None = None
) -> dict[str, Path]:
    """Baixa o recorte de arquivos usado pelo projeto. Devolve nome -> caminho."""
    competencia = competencia or competencia_mais_recente()
    log.info("competencia: %s", competencia)
    remoto = f"{RAIZ}{competencia}/"
    destino = dir_destino / competencia

    baixados: dict[str, Path] = {}
    for nome in ARQUIVOS_AMOSTRA:
        baixados[nome] = baixar(remoto + nome, destino / nome)
    return baixados


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    raiz = Path(__file__).resolve().parent.parent
    extrair_amostra(raiz / "data" / "raw")
