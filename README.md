# Priorização de leads de tecnologia na Bahia

**PGCOMP / UFBA — Sistemas Inteligentes Orientados a Dados — 2026.2**

Sistema que transforma o cadastro público de CNPJ da Receita Federal em uma
lista ordenada de empresas de tecnologia na Bahia, com justificativa explícita
para cada posição.

---

## O problema em cinco campos

| Campo | |
|---|---|
| **Contexto** | Prospecção de empresas de tecnologia na Bahia: venda de serviço para outras empresas. |
| **Usuário** | O analista comercial que monta a lista de quem abordar. |
| **Dor** | Hoje a lista sai de filtragem manual de planilha: lenta, não repetível, sem critério registrado. Duas pessoas produzem listas diferentes a partir do mesmo dado. |
| **Cadência** | A Receita Federal publica uma competência por mês. A lista é regerada a cada competência nova e consumida ao longo do mês; o que muda entre semanas é quem já foi abordado, não o dado. |
| **Dados** | Dados abertos de CNPJ da Receita Federal — cadastro completo, público, atualizado mensalmente. |
| **Resultado esperado** | O analista decide **quem abordar primeiro**, a partir de uma lista ordenada e auditável, com telefone e e-mail, em vez de um recorte de milhares de linhas. |

**Premissa registrada:** a oferta considerada é serviço de tecnologia vendido
a outras empresas, com preço que pressupõe empresa estruturada. Trocar a oferta
altera a ordem dos critérios em `src/transformar.py`, não o pipeline.

A premissa inicial previa que o MEI seria o principal ruído da lista. Os dados
refutaram: MEI é 3,4% do universo, porque as ocupações permitidas ao MEI
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

Um filtro `UF='BA' AND CNAE IN (62,63)` devolve 15.095 estabelecimentos — e
**38,6% deles estão baixados**, mais 13,9% inaptos. Mais da metade dos nomes da
lista filtrada é inútil para prospecção. O cadastro registra existência
jurídica, não atividade econômica.

O que muda a decisão é o **ranqueamento com justificativa**: situação ativa é
critério eliminatório, e cada lead carrega por escrito o motivo da posição que
ocupa. Dos 15.095, restam 7.042 leads ativos priorizados.

Números completos em [`docs/atividade-01-dados.md`](docs/atividade-01-dados.md).

## Maior risco

**Suficiência da fonte**, não disponibilidade. A RFB não publica número de
funcionários, faturamento real nem qualquer sinal de atividade econômica —
situação cadastral "ativa" não significa empresa operando. A qualificação de
lead por porte é, portanto, grosseira.

O risco anterior — viés de amostragem, por processar uma partição de dez — foi
eliminado: o pipeline processa a competência inteira. O corte temporal que a
amostra exibia era artefato do particionamento, e o fator entre amostra e
universo não era estimável (deu 15,6 no recorte e 25,4 nos leads). Resultado em
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

python -m src.extract     # baixa a competência (6,6 GiB, paralelo e retomável)
python -m src.pipeline    # executa o pipeline completo (~8 min na 1a vez)
```

Requer ~10 GiB livres além dos ZIP: o cache de Empresas e Simples fica em
disco e cada partição de Estabelecimentos é transcodificada em fatias de 1 GiB,
descartadas conforme o recorte avança.

Saídas em `data/processed/`:

| Arquivo | Conteúdo |
|---|---|
| `universo_tratado.parquet` | universo recortado, validado e enriquecido |
| `leads_priorizados.csv` | lista ordenada, com posição, contato e justificativa |
| `evidencia.json` | contagens de entrada, descartes e saída |

A exploração da Atividade 01 está em
[`notebooks/01_exploracao_dados.ipynb`](notebooks/01_exploracao_dados.ipynb) e
importa os mesmos módulos de `src/` que o pipeline usa — exploração e produção
não divergem.

Os slides são LaTeX/Beamer sobre o template do DCC/UFBA, em
[`docs/slides/`](docs/slides/); `make` naquele diretório regenera
`docs/apresentacao.pdf`.

## Dados e privacidade

`data/` está fora do controle de versão. Os arquivos da RFB somam centenas de MB
e são reproduzíveis pelo comando acima.

A lista de leads sai **com telefone, e-mail e endereço** — são dados que a
própria Receita Federal publica, e sem eles a lista não serve para prospecção:
o analista teria nomes e nenhuma forma de abordar.

A restrição é de publicação, não de uso. `data/` está fora do controle de
versão e nenhum arquivo com contato é commitado. A base inclui MEI e empresário
individual, cuja razão social é o nome civil da pessoa física; ao divulgar
qualquer recorte fora do time, o contato sai antes.

## Estrutura

```
README.md                            este documento (entregável da Aula 01)
docs/atividade-01-dados.md           caracterização e avaliação dos dados
docs/atividade-02-pipeline.md        pipeline, validações e evidência
docs/arquitetura.md                  camadas e decisões
docs/slides/                         apresentação em LaTeX (template DCC/UFBA)
notebooks/01_exploracao_dados.ipynb  exploração reproduzível
src/extract.py                       download WebDAV paralelo e retomável
src/layout.py                        layout dos arquivos e domínios
src/carregar.py                      fatiamento e leitura preguiçosa
src/validar.py                       cinco regras de validação
src/transformar.py                   recorte, enriquecimento, contato, priorização
src/perfilar.py                      estatísticas de caracterização
src/pipeline.py                      orquestração
```

## Próximos passos

1. Submeter os 20 primeiros leads ao analista e medir a pertinência.
2. Definir a oferta com precisão, para rever a ordem dos critérios — com
   7.042 leads, a ordenação passa a valer mais que o recorte.
3. Persistência em PostgreSQL (aula 04) e endpoint de consulta (aula 05).
