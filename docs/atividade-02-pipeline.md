# Atividade 02 — Pipeline inicial de dados

**Projeto:** priorização de leads de tecnologia na Bahia
**Execução:** `python -m src.pipeline`
**Evidência bruta:** `data/processed/evidencia.json` (gerada pela execução)

---

## 1. Definição da entrada

| Aspecto | |
|---|---|
| **Fonte** | dados abertos de CNPJ da Receita Federal, competência **2026-09** |
| **Acesso** | WebDAV sobre HTTPS; a competência é descoberta em execução por `PROPFIND`, não fixada no código |
| **Formato** | ZIP → CSV, separador `;`, ISO-8859-1, sem cabeçalho |
| **Volume processado** | **2,0 GB comprimidos**; 4.753.435 estabelecimentos lidos |

Arquivos e função de cada um:

| Arquivo | Papel | Tamanho |
|---|---|---|
| `Estabelecimentos1.zip` | universo: CNAE, município, UF, situação, datas, matriz/filial | 326 MB |
| `Empresas0..9.zip` | razão social, porte, natureza jurídica | 1,28 GB |
| `Simples.zip` | opção pelo MEI | 294 MB |
| `Cnaes.zip`, `Municipios.zip` | domínios de validação e de-para | < 1 MB |

Campos relevantes ao sistema: `cnpj_basico`, `cnpj_ordem`, `cnpj_dv`,
`identificador_matriz_filial`, `nome_fantasia`, `situacao_cadastral`,
`data_inicio_atividade`, `cnae_fiscal_principal`, `uf`, `municipio`,
`porte_empresa`, `razao_social`, `opcao_mei`, `data_exclusao_mei`.

## 2. Definição da transformação

Tipo de dado: **tabular**. Processamento: leitura, limpeza, padronização,
validação e geração de saída tratada.

```
ZIP (latin-1, sem cabeçalho)
   │
   ├─ 1. transcodificar   latin-1 → UTF-8, uma vez, em cache
   ├─ 2. ler              scan_csv preguiçoso, todas as colunas como texto
   ├─ 3. recortar         UF = BA ∧ CNAE ∈ {62*, 63*}
   ├─ 4. validar          5 regras; marcação separada do descarte
   ├─ 5. enriquecer       join porte, MEI, descrição de CNAE e município
   ├─ 6. remover pessoais LGPD, antes de qualquer escrita
   └─ 7. priorizar        regra explícita + justificativa por lead
```

Cinco decisões de transformação que merecem registro:

**Transcodificação em etapa própria.** O polars lê apenas UTF-8 e a RFB publica
em ISO-8859-1. Como latin-1 é monobyte, a conversão por blocos de 8 MiB é segura
— nenhum caractere é partido entre blocos. O resultado fica em cache e não é
refeito entre execuções.

**Tudo entra como texto.** Deixar o polars inferir tipo na leitura destruiria
zeros à esquerda de CNPJ e CNAE e mascararia o sentinela `"00000000"` em datas.
A conversão de tipo é etapa explícita e validada.

**Recorte por prefixo, não por código.** Nenhum perfil-alvo real é uma subclasse
de 7 dígitos: a mesma software house pode estar em 6201, 6202 ou 6204 conforme
a escolha do contador. O parâmetro é uma lista de prefixos de divisão.

**Chave derivada.** O CNPJ de 14 dígitos não existe na fonte; é montado de três
colunas com preenchimento de zeros antes de qualquer deduplicação.

**LGPD como etapa, não convenção.** `remover_dados_pessoais()` roda antes da
escrita. Verificado na saída: nenhuma coluna sensível presente.

## 3. Implementação

```
src/extract.py      download WebDAV: idempotente, retomável, com retentativa
src/layout.py       layout dos 30/7/7/2 campos e domínios oficiais
src/carregar.py     transcodificação em cache e leitura preguiçosa
src/validar.py      cinco regras + módulo 11 do CNPJ
src/transformar.py  recorte, enriquecimento, LGPD, priorização
src/perfilar.py     estatísticas de caracterização
src/pipeline.py     orquestração e relatório de evidência
```

Reprodutibilidade: `pip install -r requirements.txt && python -m src.pipeline`.
O download é idempotente (arquivo presente não é rebaixado), retomável por
cabeçalho `Range` e tolera queda de conexão com até cinco tentativas — o
servidor da RFB derrubou a conexão duas vezes durante o desenvolvimento.

Escrita atômica: cada download grava em `.part` e só é renomeado após conferir
`Content-Length`. Sem isso, uma execução interrompida deixaria arquivo truncado
com aparência de completo.

## 4. Validações

Cinco, todas ligadas a defeitos plausíveis desta fonte:

| # | Regra | Por quê |
|---|---|---|
| 1 | dígito verificador do CNPJ pelo **módulo 11** | detecta corrupção ou truncamento da chave |
| 2 | `situacao_cadastral` ∈ {01,02,03,04,08} | valor fora do domínio invalidaria o corte de leads |
| 3 | `cnae_fiscal_principal` existe em `Cnaes.zip` | integridade referencial contra a tabela oficial |
| 4 | `data_inicio_atividade` parseável e não futura | `"00000000"` e datas impossíveis |
| 5 | CNPJ de 14 dígitos único | duplicidade inflaria a lista de prospecção |

Cada regra grava uma coluna booleana própria; o descarte ocorre num único ponto.
Sem essa separação não seria possível atribuir cada linha perdida à sua causa
quando a mesma linha reprova em mais de uma regra.

## 5. Evidência de execução

Execução de **2026-09-19**, competência **2026-09**, duração **87,2 s**.

| Etapa | Registros |
|---|---|
| Estabelecimentos recebidos (partição 1) | **4.753.435** |
| Após recorte `UF=BA` ∧ CNAE 62+63 | **965** |
| Descartados pelas validações | **0** |
| Universo tratado (saída Parquet) | **965** |
| Leads ativos priorizados (saída CSV) | **277** |

Resultado das validações:

| Regra | Reprovadas |
|---|---|
| `dv_cnpj` | 0 |
| `situacao_dominio` | 0 |
| `cnae_existe` | 0 |
| `data_inicio_valida` | 0 |
| `cnpj_unico` | 0 |

**Alertas e correções durante a execução:**

1. **Junção incompleta (corrigido).** A primeira execução deixou **749 de 965
   registros (77,6%) sem `porte`**. Investigação: os básicos de
   `Estabelecimentos1` têm apenas **10,3%** de interseção com `Empresas1` — o
   particionamento das duas tabelas é independente. Corrigido lendo as dez
   partições de Empresas. Após a correção, 0 registros sem porte.

2. **Sentinela de data (corrigido).** A condição de MEI ativo usava
   `data_exclusao_mei IS NULL` e produziu **0% de MEI**, resultado falso: a RFB
   grava `"00000000"`, não nulo. A base tem 17,5 milhões de optantes. Corrigido
   em `validar.expr_data_preenchida`; resultado real 1,5%.

3. **Queda de conexão.** Timeout de leitura em `Empresas6.zip`. Motivou a
   retentativa com retomada em `extract.baixar`.

Saídas geradas:

| Arquivo | Linhas |
|---|---|
| `data/processed/universo_tratado.parquet` | 965 |
| `data/processed/leads_priorizados.csv` | 277 |
| `data/processed/evidencia.json` | — |

Distribuição do score entre os 277 leads: mínimo −15, mediana 60, máximo 85.
Os quatro primeiros somam 85 pontos — empresas de porte "Demais", matriz, mais
de três anos de atividade, CNAE na divisão 62.

## 6. Atualização da arquitetura

Documento completo em [`arquitetura.md`](arquitetura.md). Resumo do que mudou
nas duas camadas exigidas:

**Fonte de dados.** A hipótese da Aula 01 previa acesso por API. Não existe API
de consulta em massa na RFB — a distribuição é por compartilhamento Nextcloud
via WebDAV. A camada passou também de fonte única a **multiarquivo**: `porte`
não está em Estabelecimentos e a marcação de MEI não está em nenhuma das duas,
o que obriga a juntar quatro tabelas.

**Pipeline.** Ganhou duas etapas não previstas — transcodificação de codificação
e remoção de dados pessoais — e a decisão de manter tipagem como transformação
explícita em vez de inferência na leitura.

**Caixa mais arriscada: mudou de natureza.** Na Aula 01 o risco era
disponibilidade do dado. Os dados estão disponíveis e formalmente íntegros. O
risco agora é **suficiência**: não há variável de operação, faturamento ou
quadro de pessoal. Isso mantém a caixa de IA como regra explícita — subir para
ML exige uma segunda fonte, não um algoritmo melhor.

## 7. Registro de decisão

O que a implementação revelou e não estava claro antes:

1. Não existe API em massa; a fonte é um share WebDAV, e isso é restrição da
   fonte, não preferência de implementação.
2. As partições de Estabelecimentos e Empresas **não se correspondem**: 10,3%
   de interseção. Amostrar por partição não produz recorte autossuficiente para
   junções.
3. A base é formalmente impecável — zero reprovação nas cinco validações. O
   problema é semântico: **50,5% do universo está baixado**. Filtro entrega
   lista morta; é o ranqueamento que gera valor.
4. A premissa de que TI seria dominada por MEI está errada: 1,5%. As ocupações
   permitidas ao MEI excluem desenvolvimento e consultoria em TI. O
   discriminador virou `porte` + situação cadastral.
5. A partição 1 não representa registros posteriores a 2021 — 147.576 aberturas
   em 2021 contra ~120 em 2022-2026 somados. É o principal risco em aberto.

## 8. Limitações desta versão

- Uma partição de dez em Estabelecimentos, com viés temporal medido e não
  explicado.
- Pesos da priorização definidos por julgamento, ainda não calibrados contra
  julgamento humano. O teste com 20 leads é o próximo passo.
- `cnae_fiscal_secundaria` não utilizado; empresas cuja atividade de tecnologia
  é secundária ficam fora do recorte.
- Sem persistência em banco e sem histórico entre competências.
