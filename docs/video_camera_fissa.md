# Automobili e telecamere fisse: elaborazione del video completo

**Aggiornamento: il confronto esteso con i metodi del corso e le nuove clip brevi, con linea YOLO rossa e riquadri per metodo, è descritto in [metodi_ed_esperimenti.md](metodi_ed_esperimenti.md).** Questo documento conserva i risultati del primo confronto sui filmati integrali.

## Risultato disponibile

Sono stati elaborati **tutti i 12.501 frame** di due filmati Urban Tracker, senza tagli né sottocampionamento, rilevando la classe `car` di YOLO. Le ricostruzioni sono distribuite lungo l'intera durata e su tutte le tracce utilizzabili.

| Filmato | Frame originali/esportati | Durata MP4 | Frame con almeno una ricostruzione | Tracce ricostruite |
|---|---:|---:|---:|---:|
| Sherbrooke | 4.000 / 4.000 | 2 min 13,33 s | 3.974 (99,35%) | 59 |
| René-Lévesque | 8.501 / 8.501 | 4 min 43,68 s | 8.136 (95,71%) | 159 |

La copertura temporale indica i frame con almeno un'automobile mascherata. Ogni traccia conserva osservazioni di appoggio prima, dopo e tra i gap: non viene nascosta tutta la traiettoria contemporaneamente. Le assenze naturali prive di riferimento non sono conteggiate come ricostruzioni valutabili.

### Aprire i risultati

I video completi e i relativi file generati non sono inclusi nella repository
GitHub per le loro dimensioni. Le figure e i risultati leggeri sono disponibili
nel [report del benchmark in pixel](pixel_benchmark_results.md) e nel
[README principale](../README.md).

Nei video:

- **verde / OBS:** box di un'osservazione disponibile;
- **rosso / REF:** box di riferimento di un'osservazione nascosta agli interpolatori;
- **blu, arancio e viola:** posizioni e brevi scie ricostruite da S1, S2 e S3 naturale;
- la fascia superiore mostra frame, tempo trascorso e numero di automobili visibili/nascoste, senza coprire la scena originale.

Le box rosse sono il riferimento: questo esperimento ricostruisce ancora il bottom center, non larghezza e altezza della box.

## GPU utilizzata

- **YOLO su NVIDIA RTX 3050 Laptop, `cuda:0`**.
- René-Lévesque completato in **FP16, batch 8**, circa **16,8 frame/s** complessivi. Il dispositivo effettivo è registrato nei metadati, insieme alla precisione e al batch.
- Sherbrooke era già stato completato su GPU con FP32 e batch 1.
- Entrambi i video finali sono codificati con **`h264_nvenc`**. È stata verificata l'attività dell'encoder NVIDIA durante il rendering.
- Decodifica, ByteTrack e disegno delle annotazioni includono operazioni CPU; i piccoli sistemi delle spline vengono risolti da NumPy/SciPy.

La precisione del detector differisce tra i due run, ma all'interno di ogni video tutti gli interpolatori usano esattamente lo stesso riferimento congelato e la stessa maschera.

## Dataset e geografia

Fonte: [Urban Tracker, pagina degli autori](https://www.jpjodoin.com/urbantracker/dataset.html).

Citazione richiesta dagli autori: J.-P. Jodoin, G.-A. Bilodeau, N. Saunier, *Urban Tracker: Multiple Object Tracking in Urban Mixed Traffic*, WACV 2014. La pagina consultata non indica una licenza esplicita; questa informazione e la citazione sono registrate nei manifest di provenienza.

La pagina descrive estratti annotati di circa 1.000 frame. I **file video originali scaricabili sono più lunghi**: vengono utilizzati per intero, rispettivamente 4.000 e 8.501 frame. Gli archivi originali delle annotazioni Polytrack sono conservati, ma non sono ancora utilizzati per valutare le ricostruzioni.

I metadati conservano i link geografici pubblicati per le scene di Montréal. Questi link localizzano l'inquadratura: **non forniscono latitudine/longitudine per ogni automobile**. Gli errori di questo esperimento sono in pixel. Il percorso metrico usa la [calibrazione manuale del piano stradale](calibrazione.md).

## Mascheramento continuo

Configurazione: [`configs/static_full.json`](../configs/static_full.json).

1. Tracking sul video completo, solo classe COCO `2` (`car`).
2. Selezione delle tracce: almeno 24 osservazioni, confidence media almeno 0,35, geometria valida, classe costante e spostamento nell'immagine di almeno 8 pixel. Le motivazioni degli scarti sono salvate.
3. Separazione di ogni traccia nei suoi tratti osservati consecutivamente.
4. Distribuzione di gap di **3, 6, 12, 24, 48, 72, 120 e 240 frame**, dall'inizio alla fine di ciascun tratto utilizzabile.
5. Quattro osservazioni visibili tra due gap successivi; ogni interpolatore usa quattro nodi prima e quattro dopo il gap. Le osservazioni di appoggio possono essere condivise, ma **nessun punto nascosto è mai usato come supporto di un altro gap**.
6. Le stesse maschere sono utilizzate per S1, S2 e S3 naturale. Tutti i gap vengono visualizzati durante il filmato completo, non viene scelto un singolo caso dimostrativo.

È una valutazione post-tracking condizionata agli ID salvati, non un test di riassociazione durante vere occlusioni. I riferimenti sono le osservazioni YOLO/ByteTrack, non annotazioni manuali verificate. I risultati sono descrittivi e i gap con supporti condivisi non sono campioni indipendenti.

## Numeri del run

- **259.658 osservazioni** di automobili complessive: 40.331 a Sherbrooke e 219.327 a René-Lévesque.
- **218 tracce** con ricostruzioni.
- **2.148 gap** e **70.485 osservazioni nascoste** nel benchmark ufficiale esteso.
- **16.551 valutazioni** e **170.784 stime di posizione** contando i tre metodi.
- Nessun fallimento numerico; 15 test automatici superati, inclusa l'esclusione globale di tutti i punti nascosti dagli input del fit.
- Decodifica finale verificata con `ffprobe`: 4.000 e 8.501 frame, H.264.

Con gap di 24 frame, ADE aggregato rispetto al riferimento salvato:

| Metodo | ADE (pixel) |
|---|---:|
| S1 | 0,880 |
| S2 | 3,357 |
| S3 naturale | 1,339 |

In queste scene S1 ottiene l'errore medio minore. Il confronto resta dipendente da traiettorie, rumore, supporto e condizione al bordo.

## Comandi riproducibili

Dalla directory principale della repository, con le dipendenze di `docs/requirements.txt`, CUDA e FFmpeg/NVENC disponibili:

```bash
python3 -m src.prepare_urbantracker

# Impostazioni dei due run effettivamente eseguiti.
python3 -m src.detect_and_track --data-root data/urbantracker --sequences urban_sherbrooke --classes 2 --imgsz 960 --device 0
python3 -m src.detect_and_track --data-root data/urbantracker --sequences urban_rene --classes 2 --imgsz 960 --half --batch 8 --device 0

python3 -m src.benchmark --data-root data/urbantracker --config configs/static_full.json --mask-file data/urbantracker/masks/full_video.json --output data/urbantracker/results/full_video
python3 -m src.report_full_video --encoder h264_nvenc
python3 -m unittest discover -s tests -v
```

La preparazione ora supporta lettura diretta dei video e timestamp di presentazione, evitando l'esportazione di PNG intermedi. La sequenza Sherbrooke già preparata con PNG è ugualmente supportata. Il numero di frame decodificati deve coincidere con il manifest, altrimenti tracking e rendering si interrompono segnalando l'incoerenza.

Il tracking completo è già salvato: per rigenerare grafici e video basta il comando `src.report_full_video`. Se si cambiano dati o configurazioni, usare nuovi percorsi di maschere e risultati tramite `--mask-file`, `--output` e `--results`.

Artefatti principali:

- `data/urbantracker/raw/`: video e ZIP delle annotazioni originali, provenienza e checksum;
- `data/urbantracker/prepared/`: anteprime MP4, timestamp e metadati delle sequenze;
- `data/urbantracker/tracks/`: riferimenti di tracking e configurazioni effettive;
- `data/urbantracker/masks/full_video.json`: maschera complessiva condivisa;
- `data/urbantracker/results/full_video/`: metriche, stime per frame, selezione tracce e riepilogo;
- `reports/generated/static_full/`: video integrali, report, grafici, snapshot e CSV di copertura per frame.
