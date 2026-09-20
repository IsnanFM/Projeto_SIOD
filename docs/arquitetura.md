# Arquitetura

## Referência da disciplina (Aula 01)

```
Operação e observabilidade  ·  envolve o sistema inteiro
        ┌──────────────────────────────────────────────────┐
        │                                                  │
   Fontes de dados → Pipeline → Persistência → API → Interface
                                                  ↕
                                            IA / modelo
```

A IA não é etapa final da fila: é chamada pela API e devolve resultado para ela.
Nem todo projeto precisa de todas as caixas — precisa saber dizer por que não precisa.

## Estado atual

Atividades 01 e 02 implementam as duas primeiras camadas. As demais permanecem
como hipótese de trabalho, a serem preenchidas nas aulas 04 a 06.

| Camada | Estado | Decisão |
|---|---|---|
| **Fonte de dados** | implementada | dados abertos de CNPJ da RFB, via WebDAV |
| **Pipeline** | implementado | polars, transformação em código, 5 validações |
| Persistência | declarada | Parquet em disco agora; PostgreSQL na aula 04 |
| API / serviço | não iniciada | FastAPI, endpoint de leads por CNAE |
| Interface | não iniciada | tabela ordenada com justificativa por lead |
| IA / modelo | **regra explícita** | nível 1 da disciplina; ML só com evidência de que a regra não basta |
| Operação | não iniciada | aula 12+ |

## Camada de Fonte de Dados — atualizada

O que mudou em relação ao desenho da Aula 01, e por quê:

**Não existe API de consulta em massa.** A hipótese inicial de "puxar por API" não
se sustenta. A RFB distribui os dados abertos de CNPJ por um compartilhamento
público Nextcloud, acessível por WebDAV:

```
https://arquivos.receitafederal.gov.br/public.php/webdav/
usuário = token do share, senha vazia
Dados/Cadastros/CNPJ/<AAAA-MM>/
```

APIs por CNPJ individual existem — MinhaReceita, BrasilAPI — mas servem para
enriquecer um registro conhecido, não para construir universo de prospecção.
Registrado como restrição da fonte, não como preferência de implementação.

**A competência é descoberta em execução.** `extract.competencia_mais_recente()`
faz `PROPFIND` e escolhe o mês mais novo, em vez de fixar `2026-09` no código.
O pipeline não expira quando a RFB publica o mês seguinte.

**A fonte é multiarquivo, não um arquivo.** O universo exige quatro tabelas
distintas, e a razão é estrutural: `porte` não está em Estabelecimentos, e a
marcação de MEI não está em nenhuma das duas.

```
Estabelecimentos0..9.zip → universo, CNAE, município, situação, datas
Empresas0..9.zip       →  razão social, porte, natureza jurídica
Simples.zip            →  opção pelo MEI
Cnaes.zip, Municipios.zip → domínios de validação e de-para
```

## Camada de Pipeline — atualizada

```
ZIP (latin-1, sem cabeçalho)
   │
   ├─ fatiar ──────────→ fatias UTF-8 de 1 GiB (descartadas após uso)
   │
   ├─ scan_csv lazy, tudo como texto       (tipagem é etapa explícita)
   │
   ├─ recortar         UF=BA ∧ CNAE 62|63, fatia a fatia
   │
   ├─ validar          5 regras, marcação separada do descarte
   │
   ├─ enriquecer       join porte, MEI, descrições
   │
   ├─ montar contato   telefone, e-mail e endereço legíveis
   │
   └─ ordenar          critérios em ordem declarada + justificativa
          │
          ├──→ data/processed/universo_tratado.parquet
          ├──→ data/processed/leads_priorizados.csv
          └──→ data/processed/evidencia.json
```

Quatro decisões que o desenho da Aula 01 não previa:

1. **Transcodificação e fatiamento em etapa própria.** O polars lê apenas UTF-8
   e a RFB publica em ISO-8859-1. Como latin-1 é monobyte, a conversão por
   blocos é segura. Estabelecimentos tem 15,9 GiB descompactado, então a
   conversão sai em fatias de 1 GiB que são filtradas e apagadas uma a uma.

2. **Tudo entra como texto.** Deixar o polars inferir tipo na leitura mascararia
   exatamente os defeitos que a Atividade 01 pede para medir. A conversão é
   transformação explícita e validada.

3. **Marcação separada do descarte.** Cada regra escreve uma coluna booleana; o
   descarte ocorre em um único ponto. Sem isso não é possível atribuir cada
   linha perdida à sua causa.

4. **O contato faz parte da saída.** Telefone, e-mail e endereço vêm do próprio
   cadastro público e são o que torna a lista acionável. A proteção é de
   publicação: `data/` fica fora do git, e qualquer recorte divulgado fora do
   time sai sem contato — a base inclui MEI, cuja razão social é nome civil de
   pessoa física.

## Caixa mais arriscada

Continua sendo **Fonte de dados**, mas o risco mudou de natureza. Na Aula 01 o
risco era *disponibilidade*. Após a implementação, os dados estão disponíveis e
íntegros — o risco agora é de **suficiência**: a RFB não tem número de
funcionários, faturamento real nem sinal de atividade econômica. Situação
cadastral ativa não significa empresa operando.

Consequência para a arquitetura: a caixa de IA permanece como regra explícita.
Não há variável que sustente modelo preditivo de propensão com esta fonte
apenas. Subir para ML exige uma segunda fonte, não um algoritmo melhor.
