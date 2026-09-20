# Priorização de leads de tecnologia na Bahia

**PGCOMP / UFBA — Sistemas Inteligentes Orientados a Dados — 2026.2**

Sistema que transforma o cadastro público de CNPJ da Receita Federal em uma
lista ordenada de empresas de tecnologia na Bahia, com justificativa explícita
para cada posição.

---

## O problema em cinco campos

| Campo | |
|---|---|
| **Contexto** | Prospecção B2B de empresas de tecnologia na Bahia, feita semanalmente. |
| **Usuário** | O analista comercial que monta a lista de quem abordar. |
| **Dor** | Hoje a lista sai de filtragem manual de planilha: lenta, não repetível, sem critério registrado. Duas pessoas produzem listas diferentes a partir do mesmo dado. |
| **Dados** | Dados abertos de CNPJ da Receita Federal — cadastro completo, público, atualizado mensalmente. |
| **Resultado esperado** | O analista decide **quem abordar primeiro nesta semana**, a partir de uma lista ordenada e auditável em vez de um recorte de 4 mil linhas. |

**Premissa registrada:** a oferta considerada é serviço B2B de tecnologia com
ticket que pressupõe empresa estruturada. Trocar a oferta altera os pesos em
`src/transformar.py`, não o pipeline.

A premissa inicial previa que o MEI seria o principal ruído da lista. Os dados
refutaram: MEI é 1,5% do universo, porque as ocupações permitidas ao MEI
excluem desenvolvimento e consultoria em TI. O discriminador real passou a ser
**situação cadastral** e **porte**.

## Hipótese aplicada

> Se construirmos **uma lista priorizada de empresas de tecnologia da Bahia por
> CNAE**, usando **os dados abertos de CNPJ da RFB com regra explícita de
> aderência**, esperamos melhorar **o tempo até ter uma lista utilizável e a
> pertinência dos contatos** para **o analista comercial**, em comparação com
> **a filtragem manual de planilha que ele faz hoje**.

Verificação prevista: submeter os 20 primeiros leads ao analista e medir quantos
ele classifica como pertinentes. Ainda **não executado** — registrado como
próximo passo, não como resultado.

## Por que isto é um sistema orientado a dados

Um filtro `UF='BA' AND CNAE IN (62,63)` devolve 965 estabelecimentos — e
**50,5% deles estão baixados**, mais 19,9% inaptos. Sete em cada dez nomes da
lista filtrada são inúteis para prospecção. O cadastro registra existência
jurídica, não atividade econômica.

O que muda a decisão é o **ranqueamento com justificativa**: situação ativa é
critério eliminatório, e cada lead carrega por escrito o motivo da posição que
ocupa. Dos 965, restam 277 leads ativos priorizados.

Números completos em [`docs/atividade-01-dados.md`](docs/atividade-01-dados.md).

## Maior risco

**Suficiência da fonte**, não disponibilidade. A RFB não publica número de
funcionários, faturamento real nem qualquer sinal de atividade econômica —
situação cadastral "ativa" não significa empresa operando. A qualificação de
lead por porte é, portanto, grosseira.

Teste pequeno já executado: baixar a amostra, montar o CNPJ, conferir dígito
verificador, medir ausências e composição. Resultado em
[`docs/atividade-01-dados.md`](docs/atividade-01-dados.md).

## Arquitetura

Camadas **Fonte de dados** e **Pipeline** implementadas; as demais declaradas.
Ver [`docs/arquitetura.md`](docs/arquitetura.md).

```
RFB (WebDAV) → Pipeline (polars) → Parquet + CSV → [API] → [Interface]
                                                      ↕
                                            Regra de priorização
```

## Como executar

Requer Python 3.11+.

```bash
pip install -r requirements.txt

python -m src.extract     # baixa a amostra da RFB (~2 GB, idempotente e retomável)
python -m src.pipeline    # executa o pipeline completo
```

Saídas em `data/processed/`:

| Arquivo | Conteúdo |
|---|---|
| `universo_tratado.parquet` | universo recortado, validado e enriquecido |
| `leads_priorizados.csv` | lista ordenada, com score e justificativa |
| `evidencia.json` | contagens de entrada, descartes e saída |

A exploração da Atividade 01 está em
[`notebooks/01_exploracao_dados.ipynb`](notebooks/01_exploracao_dados.ipynb) e
importa os mesmos módulos de `src/` que o pipeline usa — exploração e produção
não divergem.

## Dados e privacidade

`data/` está fora do controle de versão. Os arquivos da RFB somam centenas de MB
e são reproduzíveis pelo comando acima.

O pipeline descarta e-mail, telefone e endereço antes de qualquer escrita
(`transformar.remover_dados_pessoais`). A base contém MEI cuja razão social é o
nome civil da pessoa física — por isso nenhum artefato de dados é publicado no
repositório.

## Estrutura

```
README.md                            este documento (entregável da Aula 01)
docs/atividade-01-dados.md           caracterização e avaliação dos dados
docs/atividade-02-pipeline.md        pipeline, validações e evidência
docs/arquitetura.md                  camadas e decisões
notebooks/01_exploracao_dados.ipynb  exploração reproduzível
src/extract.py                       download WebDAV, idempotente e retomável
src/layout.py                        layout dos arquivos e domínios
src/carregar.py                      transcodificação e leitura preguiçosa
src/validar.py                       cinco regras de validação
src/transformar.py                   recorte, enriquecimento, LGPD, priorização
src/perfilar.py                      estatísticas de caracterização
src/pipeline.py                      orquestração
```

## Próximos passos

1. Submeter os 20 primeiros leads ao analista e medir a pertinência.
2. Definir a oferta com precisão, para calibrar os pesos da priorização.
3. Persistência em PostgreSQL (aula 04) e endpoint de consulta (aula 05).
