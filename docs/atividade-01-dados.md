# Atividade 01 — Caracterização e avaliação inicial dos dados

**Projeto:** priorização de leads de tecnologia na Bahia
**Competência analisada:** 2026-09
**Execução:** `python -m src.extract && python -m src.pipeline`
**Exploração:** [`notebooks/01_exploracao_dados.ipynb`](../notebooks/01_exploracao_dados.ipynb)

---

## 1. Fonte de dados

Amostra real dos **dados abertos de CNPJ da Receita Federal**, competência
2026-09. É a fonte principal prevista para o projeto, não substituto — não há
limitação de disponibilidade a registrar.

O recorte processado é a **partição 1 de 10** do arquivo de Estabelecimentos
(4.753.435 registros), acompanhada das tabelas completas de Empresas (10
partições), Simples e dos domínios Cnaes e Municipios. A escolha de uma única
partição de Estabelecimentos é amostragem declarada, e sua consequência está
medida na seção 6.

Nenhum dado pessoal é publicado neste repositório. Ver seção 3.6.

## 2. Caracterização da fonte

| Aspecto | |
|---|---|
| **Origem / responsável** | Secretaria Especial da Receita Federal do Brasil |
| **Forma de acesso** | compartilhamento público Nextcloud, protocolo **WebDAV** sobre HTTPS — `https://arquivos.receitafederal.gov.br/public.php/webdav/`, usuário = token do share, senha vazia, caminho `Dados/Cadastros/CNPJ/<AAAA-MM>/` |
| **Formato** | ZIP contendo CSV; separador `;`, aspas `"`, codificação **ISO-8859-1**, **sem linha de cabeçalho** |
| **Dimensão** | 7,23 GB comprimidos na competência; 37 arquivos. Amostra deste trabalho: 2,0 GB comprimidos, 4.753.435 estabelecimentos |
| **Periodicidade** | mensal; competências disponíveis de `2025-03` a `2026-09` |
| **Restrições** | dado público, uso livre. A restrição é de saída, não de entrada: a base contém dado pessoal e não pode ser republicada integralmente |

**Não existe API de consulta em massa.** APIs por CNPJ individual (MinhaReceita,
BrasilAPI) servem para enriquecer um registro conhecido, não para construir
universo de prospecção. Para este projeto, arquivo em lote é o único caminho.

## 3. Avaliação inicial da qualidade

### 3.1 Integridade formal — nenhum defeito

As cinco validações implementadas reprovaram **zero registros** nos 965 do
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
| `nome_cidade_exterior`, `pais`, `situacao_especial`, `data_situacao_especial` | 100,00% |
| `ddd_2`, `telefone_2` | 79,27% |
| `ddd_fax`, `fax` | 74,61% |

As quatro primeiras são estruturalmente vazias para empresas nacionais sem
situação especial — ausência esperada, não defeito.

### 3.6 Campo multivalorado dentro de CSV

`cnae_fiscal_secundaria` traz vários códigos separados por vírgula dentro de um
único campo. Normalizar exige explodir a coluna. Não usado nesta versão: o
recorte se apoia no CNAE principal.

### 3.7 Dado pessoal

A base contém `correio_eletronico`, telefones, endereço completo e — no caso de
MEI e empresário individual — razão social que **é o nome civil da pessoa
física**. O pipeline descarta essas colunas antes de qualquer escrita
(`transformar.remover_dados_pessoais`). Verificado na saída: nenhuma coluna
sensível presente.

## 4. Dicionário mínimo de dados

Apenas os campos que sustentam a decisão "quem abordar primeiro".

| Campo | Significado | Tipo | Exemplo | Observação / problema |
|---|---|---|---|---|
| `cnpj_basico` | raiz do CNPJ, identifica a empresa | texto(8) | `60498117` | chave de junção com Empresas e Simples |
| `cnpj` | CNPJ completo, derivado | texto(14) | `60498117000179` | **não existe na fonte**; montado de 3 colunas |
| `razao_social` | nome empresarial | texto | `TECNOATIVA CONSULTORIA E SISTEMAS` | vem de Empresas; é nome civil quando MEI |
| `nome_fantasia` | nome de fachada | texto | — | ausente com frequência; usado como sinal fraco de maturidade |
| `situacao_cadastral` | estado do registro | texto(2) | `02` | **50,5% do recorte não é `02`** |
| `data_inicio_atividade` | abertura | texto(8) | `19960315` | `AAAAMMDD`; `00000000` = ausente |
| `cnae_fiscal_principal` | atividade principal | texto(7) | `6204000` | subclasse; recorte por prefixo de divisão |
| `municipio` | município | texto(4) | `3849` | **código RFB, não IBGE** |
| `uf` | unidade federativa | texto(2) | `BA` | filtro do recorte |
| `identificador_matriz_filial` | matriz ou filial | texto(1) | `1` | evita contato duplicado no mesmo grupo |
| `porte_empresa` | porte | texto(2) | `05` | de Empresas; `01`/`03`/`05`; **não distingue MEI** |
| `opcao_mei` | optante pelo MEI | texto(1) | `S` | de Simples; exige checar `data_exclusao_mei` |

## 5. Análise exploratória

Amostra: **4.753.435** estabelecimentos, **30** atributos.
Recorte `UF = BA` e CNAE divisões 62 + 63: **965** estabelecimentos (0,02%).

### Situação cadastral — o achado principal

| Situação | Registros | % |
|---|---|---|
| **Baixada** | 487 | **50,47%** |
| Ativa | 277 | 28,70% |
| Inapta | 192 | 19,90% |
| Suspensa | 9 | 0,93% |

**Metade do universo recortado é empresa encerrada.** Uma lista obtida por
filtro de CNAE entregaria 965 nomes, dos quais 688 não deveriam ser contatados.

### Porte

| Porte | Registros | % |
|---|---|---|
| Micro empresa | 733 | 75,96% |
| Demais | 186 | 19,27% |
| Empresa de pequeno porte | 46 | 4,77% |

### MEI — hipótese inicial refutada

**14 estabelecimentos, 1,5% do recorte.**

A premissa de partida era que CNAEs de tecnologia seriam dominados por MEI. Os
dados dizem o contrário, e a explicação é normativa: as ocupações permitidas ao
MEI não incluem desenvolvimento de software nem consultoria em TI. A base
nacional tem 17,5 milhões de optantes pelo MEI, mas eles quase não aparecem nas
divisões 62 e 63.

Consequência direta para o projeto: **o discriminador da priorização é `porte` e
`situação cadastral`, não a marcação de MEI**, que é praticamente inerte aqui.

### Concentração geográfica

Salvador 428 (44,35%), Lauro de Freitas 102 (10,57%), Feira de Santana 42
(4,35%), Vitória da Conquista 23, Camaçari 22. Mais da metade do universo está
na Região Metropolitana de Salvador.

### Composição por atividade

| CNAE | Registros | % |
|---|---|---|
| 6209 — Suporte técnico e manutenção em TI | 285 | 29,53% |
| 6311 — Tratamento de dados e hospedagem | 138 | 14,30% |
| 6204 — Consultoria em TI | 132 | 13,68% |
| 6319 — Portais e provedores de conteúdo | 105 | 10,88% |
| 6201 — Desenvolvimento sob encomenda | 101 | 10,47% |

Suporte e manutenção — não desenvolvimento — é a maior fatia. Relevante para
calibrar a oferta.

### Intervalo temporal

No recorte: `1975-05-19` a `2021-05-18`, zero datas não parseáveis.

## 6. Síntese técnica

**1. Os dados necessários estão efetivamente disponíveis?**
Sim, para a versão atual. O universo de empresas de tecnologia na Bahia é
obtenível de forma pública, gratuita, reproduzível e com atualização mensal. A
extração está automatizada e o pipeline roda de ponta a ponta em 87 segundos.

**2. Qual é o principal problema identificado na fonte?**
Não é qualidade formal — as cinco validações reprovaram zero registros. O
problema é que **o cadastro descreve existência jurídica, não atividade
econômica**. Metade do recorte (50,47%) está baixada e outros 19,9% estão
inaptos. Um sistema que apenas filtrasse por CNAE entregaria uma lista em que
sete de cada dez nomes são inúteis para prospecção. Isso confirma a necessidade
de ranqueamento com critério explícito, e não de um filtro.

**3. Há informação necessária que não está disponível?**
Sim, e é a limitação mais séria. A RFB não publica número de funcionários,
faturamento real nem qualquer sinal de operação corrente. `porte` é uma faixa
grosseira e `capital social` é autodeclarado. A qualificação do lead por
tamanho é, portanto, aproximada. Também não há histórico: cada competência é uma
fotografia, sem trilha de mudança de situação.

**4. A caracterização exige alteração no problema, hipótese ou escopo?**
No problema e na hipótese, não. No escopo da regra de priorização, sim — duas
mudanças. Primeira: situação cadastral ativa passa de critério de pontuação a
**critério eliminatório**, dado que metade do universo está morta. Segunda: a
penalização de MEI, prevista como discriminador principal, é irrelevante (1,5%)
e foi rebaixada; `porte` assumiu esse papel.

**5. Qual é o principal risco relacionado aos dados, neste momento?**
Viés de amostragem da partição. Medido na partição 1 inteira: o ano de 2021
concentra 147.576 aberturas, enquanto 2022 a 2026 somam cerca de 120 registros
no total — uma queda de quatro ordens de grandeza que nenhuma dinâmica
econômica explica. A partição, portanto, **não representa registros recentes**,
e empresas recém-abertas são justamente leads de interesse. A causa do corte não
foi determinada. Mitigação para a próxima versão: processar as dez partições de
Estabelecimentos, não uma, e verificar se o corte desaparece.
