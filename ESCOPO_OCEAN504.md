# Ocean Tower 504 — Escopo, Arquitetura e Lógica do Projeto

> Documento de referência para manutenção e correção de bugs na aba de código (Claude Code).
> Tudo vive em **um único arquivo `index.html`** (HTML + CSS + JS vanilla), servido por **GitHub Pages**, com backend **Supabase**. Sem build, sem framework, sem `localStorage`.

---

## 1. Objetivo do projeto

Painel compartilhado entre dois sócios (Victor e Dudu, 50/50) para o apartamento **504 do Residencial Ocean Tower** (compra na planta, a preço de custo, corrigida por INCC). O painel tem três funções:

1. **Controle de pagamentos** das 65 parcelas (valor pago, data, juros, multa, INCC embutido).
2. **Gestão de documentos** (boletos e comprovantes) em cofre privado, com leitura automática do boleto.
3. **Análise de investimento**: responder, com dados reais, se vale mais a pena pagar o imóvel ou aplicar as mesmas parcelas na renda fixa.

**Princípio do investimento:** comparar o desembolso (parcelas + aportes, nas datas reais) contra a mesma série aplicada em renda fixa até a entrega. **Não se usa suposição de aluguel nem de m² de mercado.** O veredito final sai por **break-even** (quanto o imóvel precisa valer na entrega para empatar) — sem chutar o futuro.

---

## 2. Arquitetura

- **Front:** `index.html` único. Bibliotecas via CDN: `supabase-js` (auth + banco + storage), `Chart.js` (gráficos), `pdf.js` (leitura de boleto, carregado sob demanda).
- **Hospedagem:** GitHub Pages — repo `victorpaimferrario/ocean-tower-504`, branch `main`, URL `https://victorpaimferrario.github.io/ocean-tower-504/`.
- **Backend:** Supabase — projeto `ocean-tower-504`, ref `aipgtnvflezqnhzbpxam`, org "Victor Paim PESSOAL", região sa-east-1.
- **CDI automático:** GitHub Action mensal grava `cdi.json` no repo; o painel lê esse arquivo para ancorar o slider de CDI.

### Configuração (constantes no JS)
```
SB_URL   = 'https://aipgtnvflezqnhzbpxam.supabase.co'
SB_KEY   = 'sb_publishable_t3S6My3JAie5UPwfc5SvNg_lH78ZbLf'   (publishable, pode ficar no front)
EDITORES = ['victorpaim@pasf.com.br','eduardodeabreuls@gmail.com']
BUCKET   = 'ocean504-anexos'
```

---

## 3. Banco de dados (Supabase)

### Tabela `ocean504_parcelas` (65 linhas, RLS ON)
| Coluna | Tipo | Observação |
|---|---|---|
| id | int (PK) | 1..65 |
| ref | text | "Sinal 1", "Mensal 1", "Semestral 1"... |
| tipo | text | sinal / mensal / semestral / aporte |
| vencimento | date | nullable |
| valor_base | numeric | valor nominal (sem INCC) |
| valor_pago | numeric | nullable — preenchido quando paga |
| data_pagamento | date | nullable |
| juros | numeric | nullable |
| multa | numeric | nullable |
| obs | text | nullable (descrição de aporte) |
| updated_at | timestamptz | trigger now() |

**RLS:** `leitura pública` (SELECT a todos) + `escrita sócios` (ALL para os 2 e-mails via `auth.jwt()->>'email'`).

### Tabela `ocean504_docs` (índice de documentos, RLS ON)
| Coluna | Tipo | Observação |
|---|---|---|
| id | bigint (PK, identity) | |
| categoria | text (CHECK) | boleto / pix_socios / comprovante_pago / comprovante / contrato / memorial / matricula / analise / outro |
| parcela_id | int (FK → parcelas.id) | nullable |
| titulo | text | nome do arquivo |
| arquivo | text | caminho dentro do bucket |
| tamanho | bigint | nullable |
| mime | text | nullable |
| enviado_por | text | e-mail de quem subiu |
| created_at | timestamptz | now() |

**RLS:** leitura e escrita **só** para os 2 e-mails (documentos são privados).

### Storage `ocean504-anexos` (bucket PRIVADO)
4 policies (ler/enviar/atualizar/apagar), todas restritas aos 2 e-mails. Arquivos organizados por `parcela_id/timestamp_nome` ou `negocio/timestamp_nome`. Abertura via `createSignedUrl` (link temporário).

---

## 4. Dados fixos do contrato (constantes no JS)

```
APTO    = 456009.87           // valor do apartamento (base da entrada)
ITBI    = 0.02 ; REG = 0.013  // ITBI 2% + registro 1,3%
ENTRADA = (ITBI+REG)*APTO = 15.048,33   // custos de cartório (saem em T0)
AMB     = 12000               // ambientação/mobília
AREA    = 47.41               // m² privativos
M2BASE  = 10000               // R$/m² de referência da compra (valorHoje = M2BASE*AREA)
T0      = 2026-06-01          // início da análise
ENTREGA = 2031-07-01          // prazo (editável no painel)
PV      = 0.50                // parte de cada sócio
```

**As 65 parcelas (geradas por `genItens()`):**
- **3 Sinais:** R$ 23.750,53 — venc. dia 30, jun/jul/ago 2026.
- **55 Mensais:** R$ 3.454,62 — venc. dia 11, set/2026 a mar/2031.
- **7 Semestrais:** R$ 30.536,37 — venc. dia 1, nov/2026, mai/nov 2027-2029.

`genItens()` é a fonte de verdade das parcelas base; o banco guarda os pagamentos por cima. **Serve também de fallback** se o banco não responder (ver bug, seção 8).

---

## 5. Módulos e lógica do JS

### 5.1 Inicialização — `bootstrap()`
Ordem: `initCharts()` → pega sessão (`getSession`) e define `canEdit`/`currentEmail` → registra `onAuthStateChange` → `loadFromDB()` → binds dos controles → `setupDropzone()` → `fillParcelaSelects()` → `loadDocs()` → lê `cdi.json` → `render()` + `renderDocs()`.

### 5.2 Parcelas
- **`loadFromDB()`** — lê `ocean504_parcelas`. Se erro ou vazio, cai para `genItens()` (fallback).
- **`renderTable(c)`** — monta o `<tbody id="tbody">` com 9 colunas: Parcela (+selos) · Venc. · Base · 50% · Valor pago (input) · Data pgto (input) · Juros (input) · Multa (input) · INCC embutido. Inputs disparam `saveRow` + `render()`.
- **`saveRow(row)`** — UPDATE no Supabase (só se `canEdit`).
- **`addAporte()`** — INSERT de uma linha tipo `aporte` (aporte extra/chamada de capital da incorporação).

### 5.3 INCC
- **`inccObs()`** — para cada parcela paga: `incc = valor_pago - valor_base - juros - multa`; taxa mensal implícita `= (1+incc/base)^(1/n) - 1`, onde `n = nOf(vencimento)` (meses desde jun/2026). Retorna média mensal/anual observada.
- **`taxaProjMensal()`** — usa o INCC observado (se toggle "usar observado" ligado) ou o slider de INCC ("e se").
- A projeção das parcelas futuras = `valor_base * (1+imP)^n`.

### 5.4 Documentos
- **`setupDropzone()`** — clique e drag-and-drop disparam `uploadFiles`. Input `accept="image/*,application/pdf"` + `multiple` (no celular: câmera/galeria/arquivos).
- **`uploadFiles(fileList)`** — para cada arquivo: se categoria=boleto e PDF, chama `lerBoleto`→`casarParcela` (auto-vínculo). Sobe ao bucket + INSERT em `ocean504_docs`. Trava de 25 MB.
- **`lerBoleto(file)`** — carrega pdf.js sob demanda, extrai texto, captura datas (dd/mm/aaaa) e valores (9.999,99).
- **`casarParcela(lido)`** — casa por vencimento+valor, depois só vencimento, depois só valor.
- **`upMsgPix(p)`** — ao casar boleto, mostra "Seu Pix p/ Dudu: R$ X" (metade arredondada) com botão copiar.
- **`renderDocs()`** — lista em cartões; abrir (signed URL 1h), compartilhar (`navigator.share`), excluir.
- **`docsIndex()` / `selosParcela()`** — selos por parcela: 📄 boleto · 💸 meu Pix · ✅ boleto pago.

### 5.5 Análise de investimento (o núcleo)
- **`getEntrega()`** — lê a data de entrega editável (prazo / +180d / atraso custom).
- **`aliqIR(anos)`** — IR regressivo: >2a=15% · >1a=17,5% · >0,5a=20% · senão 22,5%.
- **`analisar(c)`** — retorna o objeto com todas as métricas (ver fórmulas na seção 6).
- **`renderCusto(c)`** — preenche os indicadores e o veredito.

### 5.6 Auth
`canEdit = EDITORES.includes(email)`. Sem login = leitura pública (inputs desabilitados, documentos ocultos). Logado com um dos 2 e-mails = edição total.

---

## 6. Fórmulas financeiras (carteira paralela)

Parâmetros do painel: `cdi` (a.a.), `pctcdi` (% do CDI da aplicação), `trib` (isento/tributado), data de entrega.

```
taxa = cdi * pctcdi                      // taxa anual da aplicação
Para cada fluxo (parcela corrigida, aporte, entrada+amb) com valor v na data d:
    anos = (entrega - d) em anos
    vf_bruto = v * (1 + taxa)^anos
    se isento:    vf = vf_bruto
    se tributado: vf = v + (vf_bruto - v) * (1 - aliqIR(anos))
    vfRF += vf                           // carteira paralela acumulada

totalNom   = soma de todos os fluxos nominais (parcelas com INCC + aportes + entrada + amb)
breakeven  = vfRF                        // o imóvel precisa valer isso na entrega p/ empatar
custoOp    = vfRF - totalNom             // custo de oportunidade
breakM2    = vfRF / AREA                 // break-even por m²
valorizNec = (vfRF / (M2BASE*AREA))^(1/anos) - 1   // valorização a.a. p/ empatar
inccProxy  = soma das parcelas corrigidas pelo INCC   // valor "de custo" do imóvel
```

**Veredito:** se o usuário preencher a avaliação real na entrega, compara `avaliação vs breakeven` → "bateu / não bateu a renda fixa". Sem avaliação, mostra o break-even como limiar.

**Valores de referência hoje** (CDI 14,25%, 95%, isento, entrega jul/2031): sai do bolso ≈ R$ 565.512 · carteira paralela ≈ R$ 857.770 · custo de oportunidade ≈ R$ 292.259 · break-even ≈ R$ 18.093/m² · valorização p/ empatar ≈ 12,4% a.a.

---

## 7. Convenções / regras de ouro

1. **Um arquivo só** (`index.html`). Vanilla JS, sem build.
2. **Nunca usar `localStorage`/`sessionStorage`** — o estado vem do Supabase.
3. **Sempre validar o JS** antes de publicar (extrair o `<script>` e rodar `node --check`).
4. **RLS é a segurança real:** parcelas com leitura pública; documentos e bucket privados (só os 2 e-mails). Não afrouxar.
5. **A `publishable key` pode ficar no front** (é pública por design). Nunca colocar service_role key.
6. **Não supor mercado** (aluguel, m² da região). Só dado real: INCC, CDI, taxa de renda fixa.
7. **Uma mudança por vez**, partindo sempre da versão atual do arquivo.
8. **Paleta/fontes** do tema "ocean" (navy/dourado) devem ser preservadas.

---

## 8. BUG REPORTADO — parcelas não aparecem

**Sintoma:** o painel não mostra as parcelas, valores e vencimentos.

**Diagnóstico:** o código de `loadFromDB()` e `renderTable()` está correto (lê de `ocean504_parcelas`, que tem as 65 linhas, e monta a tabela). Logo, as causas prováveis são:
1. **A versão publicada no GitHub não é a atual** (ficou uma versão intermediária no ar). → Conferir se o `index.html` do repo é o mais recente (deve ter `loadFromDB` lendo de `ocean504_parcelas` e `genItens()` como fallback).
2. **Falha de leitura do banco sem fallback** (versão antiga zerava `state.itens` no erro). → Já corrigido: agora, em erro ou retorno vazio, `loadFromDB()` usa `genItens()` e as 65 parcelas aparecem mesmo offline.

**Como o Claude Code deve investigar:**
- Abrir o painel publicado e o console (F12). Procurar erro de leitura do Supabase, lib `supabase-js` não carregada, ou `sb is not defined`.
- Confirmar que `bootstrap()` chega em `render()` (um `throw` antes aborta a tabela).
- Confirmar que a publishable key e a URL no arquivo batem com o projeto.
- Garantir que a versão do repo é a que contém o fallback `genItens()`.

---

## 9. Roadmap (melhorias previstas)
- Puxar a série **oficial do INCC (FGV)** automaticamente, em vez de derivar só dos boletos.
- **Gráfico da carteira paralela** crescendo mês a mês (linha temporal).
- **Trocar o vínculo de parcela** de um documento direto no cartão (sem reanexar).
- **Rastreabilidade**: registrar quem (Victor/Dudu) lançou/editou cada parcela.
- Publicação automática (a estudar): a API do GitHub permitiria commit direto via token.
