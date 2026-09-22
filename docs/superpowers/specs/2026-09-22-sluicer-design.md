# Sluicer — design

Data: 2026-09-22. Autore: Nichita Briculschi (con Claude).
Stato: approvato l'impianto, da approvare il dettaglio.

## 1. Il problema

Portare una pagina web a dato strutturato oggi costa: o un LLM a consumo
(Firecrawl `extract`, ScrapeGraph), o selettori scritti a mano che si rompono al
primo restyling. Entrambe le strade hanno una bolletta: la prima in token, la
seconda in manutenzione umana.

## 2. Le prove raccolte il 22/09/2026

Raccolta: 14 query su GitHub, **823 repo unici**, filtrati a **240 vivi**
(push < 12 mesi, non archiviati, >= 1.000 stelle).

| strato | quota dei 240 |
| --- | --- |
| browser / stealth / anti-bot | 32% |
| LLM / agenti | 31% |
| framework di crawl | 21% |
| **parser / estrazione** | **10%** |
| markdown / documenti | 4% |
| no-code / visuale | 2% |

Commit negli ultimi 12 mesi nello strato dell'estrazione deterministica:
`autoscraper` (7.990 stelle) **1**; `extruct` (972) **0**; `trafilatura` (6.846)
57, ed e' l'unico sano ma fa solo il corpo dell'articolo.

Banchi di prova esistenti, liberi e riusabili: **WCXB** (2.008 pagine riviste a
mano, 7 tipi, 1.613 domini, CC-BY-4.0, con i risultati di 14 sistemi),
**WebMainBench** (7.809 pagine annotate, 5.434 domini, 46 lingue, Apache-2.0),
**ChatNoir** (8 dataset unificati). WCXB esiste proprio perche' i banchi
precedenti misuravano solo articoli di news.

Precedente gia' occupato: **`fastcrw/crw`** (Rust, AGPL, 1.061 stelle, nato
03/2026) fa il "Firecrawl gratis" con API compatibile. Non e' il nostro terreno.

## 3. Vincoli, non desideri

1. **Nessun LLM in nessun punto del percorso.** Neanche come ripiego.
2. **Nessuna API a pagamento.** Se una funzione richiede la chiave di qualcuno,
   non entra.
3. **Licenza permissiva (MIT)** e **nessun codice AGPL incorporato**: Firecrawl e
   crw si possono studiare, non copiare.
4. **Deterministico**: stessa pagina, stesso risultato, sempre. E' anche cio' che
   rende possibile un banco di prova onesto.
5. **Manutenibile da poche mani**: niente corsa agli armamenti anti-bot.

## 4. Architettura

### 4.1 Cosa componiamo (non riscriviamo)

| pezzo | delega a | licenza |
| --- | --- | --- |
| fetch HTTP con impersonazione TLS, browser, stealth, spider | `scrapling` | BSD-3 |
| corpo dell'articolo e rimozione boilerplate | `trafilatura` | Apache-2.0 |
| parsing HTML/XPath | `lxml` | BSD-3 |

### 4.2 Cosa scriviamo noi (il prodotto)

1. **`ladder`** — scala di costo automatica. Prova il gradino piu' economico
   (HTTP) e sale a browser o stealth **solo su una misura**, non a tentativi.
   La misura e' esplicita e verificabile: la risposta e' un rifiuto travestito
   (challenge, 403 con corpo di sfida, redirect a login), oppure il corpo e'
   scheletrico rispetto al peso della pagina (testo utile sotto soglia mentre
   il DOM dichiara contenitori vuoti), oppure i dati dichiarati mancano **e** il
   testo estratto e' sotto soglia. Ogni salita viene registrata con il motivo,
   e il motivo finisce nel risultato.
2. **`declared`** — legge i dati gia' dichiarati nella pagina: JSON-LD,
   microdata, RDFa, OpenGraph. Riprende l'eredita' di `extruct` (0 commit/anno).
3. **`induce`** — induzione di struttura: trova i sottoalberi ripetuti, allinea i
   campi fra i record, restituisce righe. Riprende l'idea di `autoscraper`
   (1 commit/anno) ma senza dover dare esempi a mano.
4. **`trust`** — punteggio di confidenza **senza LLM**: due pagine dello stesso
   template devono dare gli stessi campi; la divergenza e' il segnale. Con una
   sola pagina a disposizione il confronto non esiste: in quel caso `trust`
   restituisce esplicitamente `unverified`, mai un punteggio inventato.
5. **`heal`** — diff di schema fra due giri: quando il sito cambia, dice **cosa**
   si e' rotto invece di restituire una lista vuota.
6. **`bench`** — il tabellone: gira sui dataset liberi + una fetta nostra
   multilingue, misura noi **e i concorrenti**, pubblica anche le sconfitte.

### 4.3 Flusso

    URL/HTML -> ladder -> HTML+contesto
                           |
                   declared? --si--> record
                           |no
                    induce? --si--> record
                           |no
                    trafilatura --> testo
                           |
                    trust (confronto fra pagine dello stesso template)
                           |
                    heal (diff vs giro precedente, se esiste)

## 5. Come lo installano gli altri

Un pacchetto, quattro porte d'ingresso:

- **CLI**: `uv tool install sluicer` -> `sluicer extract <url>`.
- **Libreria Python**: `from sluicer import extract`.
- **Server MCP** (stdio): per Claude Code, Codex e chiunque parli il protocollo.
- **Plugin Claude Code**: `.claude-plugin/marketplace.json` nel repo, come fa
  linkedin-agent-skill, cosi' si installa con due comandi.

## 6. Prove

TDD, e ogni prova deve poter fallire per il motivo giusto. In particolare:

- ogni strato ha pagine campione salvate su disco (niente rete nei test unitari);
- per `trust`: una prova che un'estrazione **sbagliata ma coerente** venga
  comunque segnalata, e una che una pagina legittimamente diversa **non** lo sia;
- per `ladder`: una prova che il salto a browser avvenga **solo** quando la
  misura lo impone, contando le richieste;
- il tabellone gira in CI e il suo esito e' un file versionato, non un log.

## 7. Fuori perimetro

Ricerca web, crawl distribuito su piu' macchine, aggiramento captcha, qualunque
estrazione basata su modelli, interfaccia grafica.

## 8. Rischi dichiarati

- **L'induzione di struttura e' la parte difficile**: e' ricerca vecchia (MDR,
  RoadRunner) mai spedita in una libreria moderna. Se fallisce, restano
  `declared` + `trust` + il tabellone, che valgono comunque.
- **Il tabellone ci puo' dare torto.** E' il punto: lo pubblichiamo lo stesso.
