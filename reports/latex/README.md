# Relazione sintetica con formule e implementazioni

**Lorenzo Maria Alberto Paoria — Matricola: 1000016111**

- `relazione_progetto.tex`: sorgente in italiano.
- `relazione_progetto.pdf`: PDF compilato.
- `relazione_progetto_sorgenti.zip`: sorgente e figure per Overleaf.

Ogni interpolatore è presentato tramite definizione breve, formula con la notazione delle dispense ed estratto Python essenziale. I frammenti mostrano fit e valutazione del codice effettivo, omettendo validazioni e gestione delle derivate. S2 e Floater–Hormann sono identificate come estensioni.

Il progetto riguarda traiettorie, calibrazione del piano stradale e la
successiva estrazione cinematica. Le tabelle riportano i risultati in pixel
e il primo confronto in metri sui 406 gap coperti dalle calibrazioni
pubblicate dall'utente. I video completi e le clip dei passaggi sono
collegati nella relazione; velocità e heading sono definiti come derivate
delle coordinate interpolate e valutati su 406 gap metrici con un
riferimento a differenze finite. Il capitolo 2 riassume in modo organico tutti i concetti
del corso utilizzati nel progetto.

## Compilazione

Caricare lo ZIP su Overleaf e selezionare `relazione_progetto.tex`, oppure estrarlo conservando `figures/` e compilare:

```bash
tectonic --keep-logs relazione_progetto.tex
```

È supportato anche pdfLaTeX, con due o tre passaggi. Non servono BibTeX, Biber o shell escape.

Nel repository, dalla directory principale:

```bash
python3 reports/latex/build_report.py
```

Lo script copia le figure della pipeline, compila e aggiorna lo ZIP. `--prepare-only` prepara soltanto figure e sorgenti. Le tabelle e i commenti sono una fotografia dei run documentati e vanno aggiornati se si cambiano gli esperimenti.

Il compilatore viene cercato nel PATH e poi nella cache locale `.cache/tools/tectonic-0.17.0/`. Un percorso specifico può essere passato con `--engine /percorso/al/tectonic`.
