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
| **Volume processado** | **6,57 GiB comprimidos**; 73.366.147 estabelecimentos lidos |

Arquivos e função de cada um:

| Arquivo | Papel | Tamanho |
|---|---|---|
| `Estabelecimentos0..9.zip` | universo: CNAE, município, UF, situação, datas, matriz/filial | 5,01 GiB |
| `Empresas0..9.zip` | razão social, porte, natureza jurídica | 1,28 GiB |
| `Simples.zip` | opção pelo MEI | 294 MiB |
| `Cnaes.zip`, `Municipios.zip` | domínios de validação e de-para | < 1 MiB |

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
   ├─ 1. fatiar           latin-1 → UTF-8 em fatias de 1 GiB, descartáveis
   ├─ 2. ler              scan_csv preguiçoso, todas as colunas como texto
   ├─ 3. recortar         UF = BA ∧ CNAE ∈ {62*, 63*}, fatia a fatia
   ├─ 4. validar          5 regras; marcação separada do descarte
   ├─ 5. enriquecer       join porte, MEI, descrição de CNAE e município
   ├─ 6. montar contato   telefone, e-mail e endereço legíveis
   └─ 7. ordenar          critérios em ordem declarada + justificativa
```

Seis decisões de transformação que merecem registro:

**Transcodificação em etapa própria.** O polars lê apenas UTF-8 e a RFB publica
em ISO-8859-1. Como latin-1 é monobyte, a conversão por blocos de 8 MiB é segura
— nenhum caractere é partido entre blocos.

**Fatiamento em vez de cache inteiro.** Estabelecimentos tem **15,9 GiB**
descompactado, e só a partição 0 tem **6,7 GiB** (medido nos cabeçalhos dos
ZIP). Somado ao cache de Empresas (5,1 GiB) e Simples (3,0 GiB), materializar
as partições inteiras não cabe no disco disponível. Cada partição é transcodificada em fatias de 1 GiB, filtrada
e a fatia é apagada antes da seguinte — o pico de disco é o de **uma** fatia. O
corte entre fatias só ocorre em fim de linha fora de aspas, para não partir
registro citado ao meio.

**Tudo entra como texto.** Deixar o polars inferir tipo na leitura destruiria
zeros à esquerda de CNPJ e CNAE e mascararia o sentinela `"00000000"` em datas.
A conversão de tipo é etapa explícita e validada.

**Recorte por prefixo, não por código.** Nenhum perfil-alvo real é uma subclasse
de 7 dígitos: a mesma software house pode estar em 6201, 6202 ou 6204 conforme
a escolha do contador. O parâmetro é uma lista de prefixos de divisão.

**Chave derivada.** O CNPJ de 14 dígitos não existe na fonte; é montado de três
colunas com preenchimento de zeros antes de qualquer deduplicação.

**Ordem declarada, não pontuação.** A primeira versão somava pesos (porte +25,
matriz +10, e assim por diante). Somar exige afirmar quanto um critério vale
frente a outro, e não há venda registrada que sustente esses números — o peso
vira opinião escondida dentro de uma conta. A lista passou a ser ordenada pelos
mesmos critérios, aplicados em ordem declarada de importância: o primeiro
manda, os seguintes desempatam. Mudar a ordem é uma decisão visível.

**Contato na saída, publicação fora.** Telefone, e-mail e endereço vêm do
cadastro público da RFB e vão para o CSV: sem eles o analista não consegue
abordar ninguém. O que não acontece é republicação — `data/` está no
`.gitignore` e nenhum artefato com contato é commitado.

**Junção reduzida antes de casar.** Empresas e Simples somam 8,1 GiB de texto,
66 e 40 milhões de linhas, contra as 15 mil do recorte. A primeira tentativa de
censo estourou a memória. Hoje uma semi-junção reduz os dois lados ao conjunto
de `cnpj_basico` do recorte antes do `left join`, e a coleta usa o motor de
streaming.

## 3. Implementação

```
src/extract.py      download WebDAV: paralelo, idempotente, retomável
src/layout.py       layout dos 30/7/7/2 campos e domínios oficiais
src/carregar.py     fatiamento, transcodificação e leitura preguiçosa
src/validar.py      cinco regras + módulo 11 do CNPJ
src/transformar.py  recorte, enriquecimento, contato, priorização
src/perfilar.py     estatísticas de caracterização
src/pipeline.py     orquestração e relatório de evidência
```

Reprodutibilidade: `pip install -r requirements.txt && python -m src.pipeline`.
O download é idempotente (arquivo presente não é rebaixado), retomável por
cabeçalho `Range` e tolera queda de conexão com até cinco tentativas — o
servidor da RFB derrubou a conexão duas vezes durante o desenvolvimento.

O download roda com quatro conexões simultâneas: o servidor limita por conexão,
não a banda. Medido em 2026-09: um segundo fluxo rendeu 1,08 MiB/s sem reduzir
o primeiro (1,27 MiB/s), e a execução com quatro conexões trouxe 5,2 GiB em
27min36s — **3,2 MiB/s agregados**, cerca de três vezes uma conexão sozinha.
Extrapolando essa taxa, os 6,57 GiB levariam ~35 min contra ~100 min em série;
o relógio da execução real foi maior porque a primeira fase rodou em série.

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

Execução de **2026-09-20**, competência **2026-09**, duração **209,7 s** com
o cache de Empresas e Simples já em disco; **481,2 s** na primeira execução,
que inclui transcodificar essas duas tabelas.

| Etapa | Registros |
|---|---|
| Estabelecimentos lidos (dez partições) | **73.366.147** |
| Após recorte `UF=BA` ∧ CNAE 62+63 | **15.095** |
| Descartados pelas validações | **0** |
| Universo tratado (saída Parquet) | **15.095** |
| Leads ativos priorizados (saída CSV) | **7.042** |

Contribuição de cada partição para o recorte: 6.464 na partição 0 e entre 873 e
1.125 nas demais. A partição 0 responde por 43% do recorte — é ela que carrega
os registros recentes que faltavam na amostra.

Resultado das validações:

| Regra | Reprovadas |
|---|---|
| `dv_cnpj` | 0 |
| `situacao_dominio` | 0 |
| `cnae_existe` | 0 |
| `data_inicio_valida` | 0 |
| `cnpj_unico` | 0 |

**Alertas e correções durante a execução:**

1. **Junção incompleta (corrigido).** Uma execução anterior deixou **77,6% dos
   registros sem `porte`**. Investigação: os básicos de uma partição de
   Estabelecimentos têm apenas **10,3%** de interseção com a partição de mesmo
   índice de Empresas — o particionamento das duas tabelas é independente.
   Corrigido lendo as dez partições de Empresas. Nesta execução, 0 registros
   sem porte.

2. **Sentinela de data (corrigido).** A condição de MEI ativo usava
   `data_exclusao_mei IS NULL` e produziu **0% de MEI**, resultado falso: a RFB
   grava `"00000000"`, não nulo. A base tem 17,5 milhões de optantes. Corrigido
   em `validar.expr_data_preenchida`; resultado real 3,4%.

3. **Queda de conexão.** Timeout de leitura em `Empresas6.zip`. Motivou a
   retentativa com retomada em `extract.baixar`.

4. **Estouro de memória (corrigido).** A primeira execução em censo abortou no
   enriquecimento: o `left join` materializava 66 milhões de linhas de Empresas
   para casar com 15 mil. Corrigido com semi-junção pelo `cnpj_basico` do
   recorte antes do join, e coleta em streaming.

5. **Arquivo mapeado em memória (corrigido).** Reaproveitar o mesmo caminho de
   fatia falhava no Windows com `EINVAL`: o polars ainda mantinha o mapeamento
   da fatia anterior. Cada fatia passou a ter nome próprio e a remoção tolera o
   mapeamento residual.

Saídas geradas:

| Arquivo | Linhas |
|---|---|
| `data/processed/universo_tratado.parquet` | 15.095 |
| `data/processed/leads_priorizados.csv` | 7.042 |
| `data/processed/evidencia.json` | — |

Cobertura de contato na lista de leads: **6.968 com telefone (98,9%)** e 6.904
com e-mail (98,0%). É o que torna a saída acionável sem consulta adicional.

Como a lista se distribui entre os 7.042 leads: **306** atendem os seis
critérios positivos e abrem a lista; **512** têm porte acima de microempresa;
**311** atendem um único critério e ficam no fim; 442 são MEI. A ordenação é
lexicográfica pelos critérios, não por soma de pontos.

## 6. Atualização da arquitetura

Documento completo em [`arquitetura.md`](arquitetura.md). Resumo do que mudou
nas duas camadas exigidas:

**Fonte de dados.** A hipótese da Aula 01 previa acesso por API. Não existe API
de consulta em massa na RFB — a distribuição é por compartilhamento Nextcloud
via WebDAV. A camada passou também de fonte única a **multiarquivo**: `porte`
não está em Estabelecimentos e a marcação de MEI não está em nenhuma das duas,
o que obriga a juntar quatro tabelas.

**Pipeline.** Ganhou duas etapas não previstas — transcodificação de codificação
e montagem dos campos de contato — e a decisão de manter tipagem como
transformação explícita em vez de inferência na leitura.

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
   problema é semântico: **38,6% do universo está baixado** e 13,9% inapto.
   Filtro entrega lista morta; é o ranqueamento que gera valor.
4. A premissa de que TI seria dominada por MEI está errada: 3,4%. As ocupações
   permitidas ao MEI excluem desenvolvimento e consultoria em TI. O
   discriminador virou `porte` + situação cadastral.
5. O corte temporal da partição 1 — 147.576 aberturas em 2021 contra ~120 em
   2022-2026 — era artefato do particionamento: no censo, 2022 a 2026 têm de
   835 a 1.160 aberturas por ano. Amostrar por partição não era defensável, e o
   fator entre amostra e universo não era estimável a priori: deu 15,6 no
   recorte e 25,4 nos leads.

## 8. Limitações desta versão

- Uma competência apenas: sem histórico entre meses, não dá para medir
  mudança de situação cadastral.
- A ordem dos critérios vem de julgamento sobre a oferta, ainda não conferida
  contra julgamento humano nem contra venda fechada. O teste com 20 leads é o
  próximo passo.
- `cnae_fiscal_secundaria` não utilizado; empresas cuja atividade de tecnologia
  é secundária ficam fora do recorte.
- Sem persistência em banco: a saída é arquivo, não serviço consultável.
