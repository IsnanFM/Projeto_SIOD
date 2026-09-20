# Atividade 01 — Caracterização e avaliação inicial dos dados

**Projeto:** priorização de leads de tecnologia na Bahia
**Competência analisada:** 2026-09
**Execução:** `python -m src.extract && python -m src.pipeline`
**Exploração:** [`notebooks/01_exploracao_dados.ipynb`](../notebooks/01_exploracao_dados.ipynb)

---

## 1. Fonte de dados

**Dados abertos de CNPJ da Receita Federal**, competência 2026-09. É a fonte
principal prevista para o projeto, não substituto — não há limitação de
disponibilidade a registrar.

O processamento é **censo, não amostra**: as dez partições de Estabelecimentos
(73.366.147 registros), as dez de Empresas, Simples e os domínios Cnaes e
Municipios. A primeira versão deste documento usava só a partição 1; a seção 6
registra por que a amostragem foi abandonada.

Nenhum arquivo de dados é publicado neste repositório — inclusive os que
carregam contato. Ver seção 3.7.

## 2. Caracterização da fonte

| Aspecto | |
|---|---|
| **Origem / responsável** | Secretaria Especial da Receita Federal do Brasil |
| **Forma de acesso** | compartilhamento público Nextcloud, protocolo **WebDAV** sobre HTTPS — `https://arquivos.receitafederal.gov.br/public.php/webdav/`, usuário = token do share, senha vazia, caminho `Dados/Cadastros/CNPJ/<AAAA-MM>/` |
| **Formato** | ZIP contendo CSV; separador `;`, aspas `"`, codificação **ISO-8859-1**, **sem linha de cabeçalho** |
| **Dimensão** | 7,23 GB comprimidos na competência; 37 arquivos. Processado: 6,57 GiB comprimidos, 73.366.147 estabelecimentos |
| **Periodicidade** | mensal; competências disponíveis de `2025-03` a `2026-09` |
| **Restrições** | dado público, uso livre. A restrição é de republicação: a base traz contato e nome civil de pessoa física no caso de MEI, e não é redistribuída aqui |

**Não existe API de consulta em massa.** APIs por CNPJ individual (MinhaReceita,
BrasilAPI) servem para enriquecer um registro conhecido, não para construir
universo de prospecção. Para este projeto, arquivo em lote é o único caminho.

## 3. Avaliação inicial da qualidade

### 3.1 Integridade formal — nenhum defeito

As cinco validações implementadas reprovaram **zero registros** nos 15.095 do
recorte:

| Verificação | Reprovadas |
|---|---|
| dígito verificador do CNPJ (módulo 11) | 0 |
| situação cadastral no domínio oficial | 0 |
| CNAE principal existe em `Cnaes.zip` | 0 |
| data de início parseável e não futura | 0 |
| CNPJ de 14 dígitos único | 0 |

Conclusão relevante: **a base é formalmente íntegra**. Os problemas desta fonte
não são de formatação — são semânticos, e aparecem abaixo.

### 3.2 O identificador não existe pronto

O CNPJ vem quebrado em três colunas: `cnpj_basico` (8), `cnpj_ordem` (4) e
`cnpj_dv` (2). Montar a chave é pré-requisito de qualquer deduplicação.

### 3.3 Codificação de município não é IBGE

O campo `municipio` usa **tabela interna da RFB**, de 4 dígitos. Salvador é
`3849`; o código IBGE `2927408` não existe na tabela. Cruzar com qualquer fonte
externa — IBGE, CAGED, RAIS — exige o de-para de `Municipios.zip` (5.572 linhas).

### 3.4 Ausência codificada como sentinela, não como nulo

Colunas de data usam `"00000000"` para ausência. Tratar esse valor como data
válida inverte o sentido de qualquer condição que pergunte "este evento
ocorreu?". Foi exatamente o que ocorreu na primeira execução deste pipeline: a
condição de MEI ativo usava `data_exclusao_mei IS NULL` e retornou 0% de MEI,
número falso. Corrigido em `validar.expr_data_preenchida`.

### 3.5 Valores ausentes no recorte

| Coluna | Ausente |
|---|---|
| `nome_cidade_exterior` | 100,00% |
| `situacao_especial`, `data_situacao_especial` | 99,98% |
| `pais` | 95,58% |
| `ddd_fax`, `fax` | 83,7% |
| `ddd_2`, `telefone_2` | 81,46% |

As quatro primeiras são estruturalmente vazias para empresas nacionais sem
situação especial — ausência esperada, não defeito.

### 3.6 Campo multivalorado dentro de CSV

`cnae_fiscal_secundaria` traz vários códigos separados por vírgula dentro de um
único campo. Normalizar exige explodir a coluna. Não usado nesta versão: o
recorte se apoia no CNAE principal.

### 3.7 Dado pessoal

A base contém `correio_eletronico`, telefones, endereço completo e — no caso de
MEI e empresário individual — razão social que **é o nome civil da pessoa
física**.

Esses campos **entram** na lista de leads: telefone, e-mail e endereço são o
que torna a lista acionável, e a própria RFB os publica. O cuidado é de
publicação, não de uso — `data/` está fora do controle de versão, nenhum
arquivo com contato é commitado, e qualquer recorte divulgado fora do time sai
sem contato.

## 4. Dicionário mínimo de dados

Apenas os campos que sustentam a decisão "quem abordar primeiro".

| Campo | Significado | Tipo | Exemplo | Observação / problema |
|---|---|---|---|---|
| `cnpj_basico` | raiz do CNPJ, identifica a empresa | texto(8) | `60498117` | chave de junção com Empresas e Simples |
| `cnpj` | CNPJ completo, derivado | texto(14) | `60498117000179` | **não existe na fonte**; montado de 3 colunas |
| `razao_social` | nome empresarial | texto | `TECNOATIVA CONSULTORIA E SISTEMAS` | vem de Empresas; é nome civil quando MEI |
| `nome_fantasia` | nome de fachada | texto | — | ausente com frequência; usado como sinal fraco de maturidade |
| `situacao_cadastral` | estado do registro | texto(2) | `02` | **53,3% do recorte não é `02`** |
| `data_inicio_atividade` | abertura | texto(8) | `19960315` | `AAAAMMDD`; `00000000` = ausente |
| `cnae_fiscal_principal` | atividade principal | texto(7) | `6204000` | subclasse; recorte por prefixo de divisão |
| `municipio` | município | texto(4) | `3849` | **código RFB, não IBGE** |
| `uf` | unidade federativa | texto(2) | `BA` | filtro do recorte |
| `identificador_matriz_filial` | matriz ou filial | texto(1) | `1` | evita contato duplicado no mesmo grupo |
| `porte_empresa` | porte | texto(2) | `05` | de Empresas; `01`/`03`/`05`; **não distingue MEI** |
| `opcao_mei` | optante pelo MEI | texto(1) | `S` | de Simples; exige checar `data_exclusao_mei` |

## 5. Análise exploratória

Censo: **73.366.147** estabelecimentos, **30** atributos.
Recorte `UF = BA` e CNAE divisões 62 + 63: **15.095** estabelecimentos (0,02%).

### Situação cadastral — o achado principal

| Situação | Registros | % |
|---|---|---|
| Ativa | 7.042 | 46,65% |
| **Baixada** | 5.821 | **38,56%** |
| Inapta | 2.091 | 13,85% |
| Suspensa | 132 | 0,87% |
| Nula | 9 | 0,06% |

**Mais da metade do universo recortado não está ativa.** Uma lista obtida por
filtro de CNAE entregaria 15.095 nomes, dos quais 8.053 não deveriam ser
contatados.

### Porte

| Porte | Registros | % |
|---|---|---|
| Micro empresa | 12.157 | 80,54% |
| Demais | 2.110 | 13,98% |
| Empresa de pequeno porte | 828 | 5,49% |

### MEI — hipótese inicial refutada

**517 estabelecimentos, 3,4% do recorte.**

A premissa de partida era que CNAEs de tecnologia seriam dominados por MEI. Os
dados dizem o contrário, e a explicação é normativa: as ocupações permitidas ao
MEI não incluem desenvolvimento de software nem consultoria em TI. A base
nacional tem 17,5 milhões de optantes pelo MEI, mas eles quase não aparecem nas
divisões 62 e 63.

Consequência direta para o projeto: **o discriminador da priorização é `porte` e
`situação cadastral`, não a marcação de MEI**, que é praticamente inerte aqui.

### Concentração geográfica

Salvador 6.880 (45,58%), Lauro de Freitas 1.260 (8,35%), Feira de Santana 858
(5,68%), Vitória da Conquista 495 (3,28%), Camaçari 334 (2,21%). Mais da metade
do universo está na Região Metropolitana de Salvador.

### Composição por atividade

| CNAE | Registros | % |
|---|---|---|
| 6209 — Suporte técnico e manutenção em TI | 3.604 | 23,88% |
| 6201 — Desenvolvimento sob encomenda | 2.511 | 16,63% |
| 6204 — Consultoria em TI | 2.278 | 15,09% |
| 6319 — Portais e provedores de conteúdo | 1.688 | 11,18% |
| 6399 — Outros serviços de informação | 1.481 | 9,81% |
| 6311 — Tratamento de dados e hospedagem | 1.348 | 8,93% |

Suporte e manutenção — não desenvolvimento — é a maior fatia. Relevante para
calibrar a oferta.

### Intervalo temporal

No recorte: `1967-06-30` a `2026-09-11`, zero datas não parseáveis.

## 6. Síntese técnica

**1. Os dados necessários estão efetivamente disponíveis?**
Sim, para a versão atual. O universo de empresas de tecnologia na Bahia é
obtenível de forma pública, gratuita, reproduzível e com atualização mensal. A
extração está automatizada e o pipeline processa a competência inteira em 8
minutos.

**2. Qual é o principal problema identificado na fonte?**
Não é qualidade formal — as cinco validações reprovaram zero registros. O
problema é que **o cadastro descreve existência jurídica, não atividade
econômica**. 38,56% do recorte está baixado e outros 13,85% estão inaptos. Um
sistema que apenas filtrasse por CNAE entregaria uma lista em que mais da
metade dos nomes é inútil para prospecção. Isso confirma a necessidade de
ranqueamento com critério explícito, e não de um filtro.

**3. Há informação necessária que não está disponível?**
Sim, e é a limitação mais séria. A RFB não publica número de funcionários,
faturamento real nem qualquer sinal de operação corrente. `porte` é uma faixa
grosseira e `capital social` é autodeclarado. A qualificação do lead por
tamanho é, portanto, aproximada. Também não há histórico: cada competência é uma
fotografia, sem trilha de mudança de situação.

**4. A caracterização exige alteração no problema, hipótese ou escopo?**
No problema e na hipótese, não. No escopo da regra de priorização, sim — duas
mudanças. Primeira: situação cadastral ativa deixa de ser critério de ordenação
e vira **critério eliminatório**, dado que metade do universo está morta.
Segunda: o MEI, previsto como discriminador principal, é pequeno (3,4%) e
desceu na ordem; `porte` assumiu o primeiro lugar.

**5. Qual é o principal risco relacionado aos dados, neste momento?**
Era o viés de amostragem da partição, e ele foi eliminado processando o censo.
A partição 1 concentrava 147.576 aberturas em 2021 contra ~120 em 2022-2026
somados; no censo, 2022 a 2026 têm de 835 a 1.160 aberturas por ano no recorte.
O corte era artefato do particionamento, não fenômeno econômico.

O episódio deixou um registro que vale mais que o número: o particionamento da
RFB **não é uniforme**, nem em tamanho (a partição 0 tem 2,1 GB contra ~330 MB
nas demais) nem em conteúdo. Por isso nenhuma extrapolação de uma partição para
o universo era defensável — e de fato não seria: a amostra dava 965 no recorte e
277 leads, o censo deu 15.095 e 7.042, fatores de 15,6 e 25,4, diferentes entre
si porque a amostra também distorcia a proporção de empresas ativas.

O risco que permanece é o da pergunta 3: **suficiência**. Situação "ativa" não
significa empresa operando, e não há variável de operação na fonte.
