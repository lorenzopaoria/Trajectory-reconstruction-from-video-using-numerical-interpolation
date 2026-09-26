# Metodi del corso e clip brevi dei passaggi

La relazione attuale è sintetica e include gli estratti Python dei metodi: **[PDF](../relazione_progetto.pdf)**. Il confronto è stato esteso anche al [piano stradale calibrato](reports/generated/ground/RESULTS.md), su 406 gap ammissibili. I video completi e le clip sono linkati nella relazione; la cinematica è definita tramite derivate delle stesse interpolazioni di posizione e valutata nel [report cinematico](data/urbantracker/results/ground/KINEMATICS.md).

## Aprire le nuove clip

Sono disponibili **12 clip separate**, sei per scena, della durata di circa **6,4–8 secondi**, in **1920×1080**, codificate sulla GPU con NVIDIA NVENC.

- **[Indice di tutte le clip con anteprime](reports/generated/course/clips/INDEX.md)**
- [Esempio René-Lévesque: passaggio dell'auto 1229](reports/generated/course/clips/urban_rene_car1229_f00611.mp4)
- [Esempio Sherbrooke: passaggio dell'auto 3154](reports/generated/course/clips/urban_sherbrooke_car3154_f02922.mp4)
- **[Report completo degli esperimenti](reports/generated/course/RESULTS.md)**

Ogni clip contiene nove riquadri sincronizzati: riferimento e otto interpolatori. La traiettoria originale YOLO/ByteTrack è una **linea rosso acceso `#FF0000`, spessa e con contorno scuro**. Ogni metodo ha un colore distinto; il riferimento rosso rimane visibile anche nel suo riquadro. Le curve non sono traslate artificialmente per distinguerle.

Il ritaglio è fisso per tutta la clip e uguale nei nove riquadri. Le coordinate degli errori rimangono quelle originali, prima dello zoom. Sono indicati ID dell'auto, tempo del filmato originale, stato osservato/nascosto, lunghezza del gap ed errore corrente. Le stime fuori dal ritaglio vengono segnalate quando si verificano; non vengono limitate nei dati numerici. Le box bianche identificano l'auto di riferimento, non una box ricostruita.

## Metodi implementati e relazione con le dispense

Riferimento: [dispense di interpolazione](../Materiale/OneDrive_1_9-15-2026/Interpolazione.pdf).

| Metodo | Implementazione disponibile | Collegamento con il corso |
|---|---|---|
| S1 | Interpolazione lineare a tratti | Pagine 36 e 38 |
| Vandermonde | Sistema nella base monomiale, tempo normalizzato | Pagine 7–9 |
| Lagrange | Formula diretta nella base di Lagrange | Pagine 10–12 |
| Newton | Differenze divise e Horner generalizzato | Pagine 18–27 |
| S3 naturale | Derivate seconde nulle agli estremi | Pagine 38–41 |
| S3 vincolata | Derivate ai bordi stimate da tre osservazioni visibili per lato | Pagina 40 |
| S2 | Quadratiche C1, derivata seconda del primo tratto nulla | Estensione della definizione generale a pagina 37 |
| Razionale Floater–Hormann | Formula baricentrica con parametro locale `d=3` | Famiglia razionale introdotta a pagina 4; algoritmo specifico esterno alle slide |
| S3 periodica | Chiusura dei valori e delle prime due derivate | Pagina 40; esperimento periodico dedicato |
| Trigonometrica | Sistema nella base seno/coseno, periodo dichiarato, convenzione pari/dispari | Famiglia introdotta alle pagine 4–6; esperimento periodico dedicato |
| Nodi di Chebyshev | Radici esatte, confrontate con nodi equispaziati sulla funzione di Runge | Pagine 28–32; esperimento sulla distribuzione dei nodi |

La S3 vincolata usa le derivate di interpolanti quadratici locali costruiti sui primi/ultimi tre nodi visibili. Le derivate sono correttamente convertite tra tempo fisico e normalizzato. Non si usano velocità ricavate dai valori nascosti.

Vandermonde, Lagrange e Newton rappresentano **lo stesso polinomio** sugli stessi nodi. La differenza massima misurata su 56.928 punti è circa **1,04×10⁻¹⁰ pixel** tra Vandermonde e Lagrange e **2,97×10⁻¹¹ pixel** tra Vandermonde e Newton. I riquadri separati permettono di identificarli anche quando le curve coincidono.

Chebyshev è una scelta dei nodi, non un quarto algoritmo che debba produrre una curva diversa sugli stessi punti. Spline periodiche e trigonometrica sono analizzate su un moto chiuso sintetico, con periodo noto e ipotesi compatibili.

## Confronto esteso sui video

Configurazione: [`configs/course_static.json`](configs/course_static.json).

- **5.517 gap originali riutilizzati**, con manifest e checksum invariati.
- Gap di **3, 6, 12 e 24 frame**: la richiesta di clip brevi non cambia le lunghezze dei gap.
- Otto nodi visibili per caso, quattro prima e quattro dopo, uguali per tutti i metodi.
- **44.136 valutazioni** e **455.424 posizioni stimate** nel confronto principale, nessun fallimento numerico.
- Metriche su tutte le tracce ammissibili dei filmati completi; le clip sono una selezione illustrativa.
- Errori micro e macro, RMS euclideo, tempi di fit/valutazione, condizionamento della matrice monomiale e superamento del rettangolo dei nodi di supporto.

I tempi misurano i piccoli fit NumPy/SciPy su CPU; il condizionamento viene calcolato fuori dall'intervallo cronometrato. La codifica delle clip usa la GPU; il tracking già salvato è riutilizzato.

Con otto nodi e gap di 24 frame, ADE rispetto al riferimento salvato:

| Metodo | ADE (pixel) |
|---|---:|
| S1 | 0,880 |
| S3 naturale | 1,339 |
| S3 vincolata | 1,340 |
| S2 | 3,357 |
| Vandermonde / Lagrange / Newton | 14,293 |
| Razionale FH | 35,165 |

Questi risultati mostrano che aumentare la complessità dell'interpolante non garantisce una ricostruzione migliore dei dati rumorosi. L'assenza di poli reali della costruzione razionale in aritmetica esatta non impedisce grandi oscillazioni nel gap. Le conclusioni sono relative a queste scene e configurazioni; il riferimento resta YOLO/ByteTrack post-tracking.

## Esperimenti complementari

### Numero di nodi

Ripetizione sui **medesimi istanti nascosti** con 4, 6 e 8 nodi visibili. I nodi vengono selezionati simmetricamente tra quelli già disponibili; tutti i campioni globalmente nascosti restano esclusi. Per i polinomi i gradi massimi sono rispettivamente 3, 5 e 7.

Risultati: [`support_study.csv`](reports/generated/course/experiments/support_study.csv). I manifest derivati contengono il campo `support_study` con il numero effettivo di nodi e l'hash della maschera originale; la configurazione originale è conservata come provenienza.

### Chebyshev e Runge

Funzione $f(t)=1/(1+25t^2)$ su $[-1,1]$, gradi 4, 8, 12, 16, 24 e 32, con $n+1$ nodi equispaziati oppure radici di Chebyshev. Il polinomio di Newton viene valutato matematicamente su tutto l'intervallo, comprese le piccole fasce esterne alle radici. Questo è un test sintetico di approssimazione, distinto dalla ricostruzione dei gap video, che rifiuta l'estrapolazione.

[Grafico](reports/generated/course/experiments/chebyshev_runge.png) · [CSV](reports/generated/course/experiments/chebyshev_runge.csv)

### Periodicità

Traiettoria chiusa analitica, periodo 6 secondi, 49 campioni comprendenti l'estremo duplicato. Si nascondono otto campioni in tre collocazioni diverse. Le spline usano i campioni rimanenti con entrambi gli estremi; la trigonometrica esclude l'estremo duplicato e risolve il sistema sui tempi osservati incompleti. Non viene applicata una FFT a dati già riempiti.

Questo segnale appartiene alla base trigonometrica scelta, quindi è attesa una ricostruzione quasi esatta in aritmetica sufficientemente precisa. I risultati sono in unità sintetiche e non vengono mescolati con quelli stradali in pixel.

[Grafico](reports/generated/course/experiments/periodic.png) · [CSV](reports/generated/course/experiments/periodic.csv)

## Selezione dei passaggi

Configurazione: [`configs/clips.json`](configs/clips.json). Si selezionano finestre di circa otto secondi, almeno sei, su tratti consecutivi con riferimenti disponibili. I criteri usano movimento robusto, spostamento rapportato alla dimensione dell'auto, dimensione visibile e continuità. Il filtraggio robusto serve soltanto alla selezione visiva e non modifica i dati del fit.

Sono state selezionate sei auto diverse per ciascuna scena, distribuendo le clip nel tempo tra 156 finestre candidate. Non si usano né graduatorie né errori degli interpolatori per scegliere i casi. Una clip può essere parte del passaggio completo; il suo intervallo preciso è indicato nel manifest. I fit possono utilizzare osservazioni visibili immediatamente esterne alla clip.

## Riproduzione

Dalla directory principale della repository, con i dataset e il tracking già presenti:

```bash
python3 -m unittest discover -s tests -v

python3 -m src.benchmark --data-root data/urbantracker --config configs/course_static.json --mask-file data/urbantracker/masks/full_video.json --output data/urbantracker/results/course

python3 -m src.course_experiments

python3 -m src.passage_clips

python3 -m src.course_report --verify-clips
```

La suite attuale comprende **35 test**, inclusa la proiezione geografica. La verifica delle **12 clip**, per **2.783 frame**, controlla codec H.264, risoluzione, numero di frame e checksum. Risultati della verifica in [`clip_validation.json`](reports/generated/course/clip_validation.json).

Gli esperimenti periodici e sui nodi sono riproducibili da `src/course_experiments.py`; `src/passage_clips.py --select-only` genera soltanto il manifest dei passaggi. Colori, etichette e appartenenza al programma sono centralizzati in `src/methods.py`.
