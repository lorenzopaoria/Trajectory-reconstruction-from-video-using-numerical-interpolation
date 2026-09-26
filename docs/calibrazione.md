# Calibrazione manuale e piano stradale georeferenziato

## Stato

Le due calibrazioni dell'utente sono pubblicate e il confronto metrico disponibile
copre **406 gap validi su 5.517** del run metrico originale. Sono state
proiettate **2.186/40.331** osservazioni a Sherbrooke e **7.345/219.327** a
René-Lévesque. Il benchmark pixel ufficiale è stato successivamente esteso a
gap più lunghi; il run metrico esteso richiede una rigenerazione delle
proiezioni con una calibrazione compatibile. La zona validata è una parte dei
filmati; ampliarla richiede ulteriori riferimenti stradali affidabili. La
cinematica è valutata separatamente sui 406 gap validi con riferimento a
differenze finite della traiettoria completa; non è una misura GPS o inerziale
indipendente.

**[Risultati metrici e figure delle zone calibrate](metric_benchmark_results.md)**

Il lanciatore usa, quando presente, l'editor standalone:

`~/Work/GeminiPort-Master/GeminiPort/ground_geometry/run_calibration.py`

La copia di GeminiPort può avere due strutture: l'API schema v2 in `ground_geometry/modules/calibration.py`, oppure in `trafficdetGUI/modules/ground_projection.py` con nucleo `ground_geometry/homography.py`. L'adattatore riconosce entrambe. Se manca il launcher standalone, apre in sequenza il dialogo di calibrazione schema v2 di `trafficdetGUI`: in questa variante le coordinate sono inserite manualmente, consultando la mappa esterna. Non vengono convertiti implicitamente i diversi formati legacy di `homographyGUI`.

Percorso e associazione camera/video sono configurati in `configs/georeferencing.json`. La variabile `GEMINIPORT_ROOT` può sostituire il percorso del repository.

## Come calibrare

Dalla directory principale della repository:

```bash
python3 -m src.calibrate_ground
```

Si apre l'editor con le due sorgenti originali:

- **UrbanSherbrooke:** incrocio Sherbrooke/Amherst, oggi Atateken, Montréal;
- **UrbanRene:** scena René-Lévesque, da riconoscere tramite il [riferimento geografico del dataset](https://www.bing.com/maps/?v=2&cp=rkg7498w1ygj&lvl=19.26&dir=359.66&sty=o).

I link originali e i nomi delle scene sono anche nel file di configurazione. Servono a localizzare l'inquadratura, non costituiscono punti di controllo già misurati.

### Coordinate per centrare la mappa

| Scena | Latitudine | Longitudine | Zona |
|---|---:|---:|---|
| Sherbrooke | 45.521379 | -73.565683 | Sherbrooke / Atateken, ex Amherst |
| René-Lévesque | 45.494921 | -73.574007 | Boulevard René-Lévesque Ouest, zona 1425 |

Questi sono centri approssimativi delle scene, ricavati dal parametro `cp` dei link Bing pubblicati dal dataset. Il formato legacy codifica separatamente le due coordinate in base 30 (alfabeto `0123456789bcdfghjkmnpqrstvwxyz`), su sei caratteri ciascuna: latitudine = `180*a/30**6 - 90`, longitudine = `360*b/30**6 - 180`. L'incrocio di Sherbrooke e la zona di René-Lévesque sono stati riscontrati anche su OpenStreetMap/Nominatim.

- [Mappa Sherbrooke](https://www.openstreetmap.org/?mlat=45.521379&mlon=-73.565683#map=19/45.521379/-73.565683)
- [Mappa René-Lévesque](https://www.openstreetmap.org/?mlat=45.494921&mlon=-73.574007#map=19/45.494921/-73.574007)

Non vengono impostati come `camera_location`: non sono posizioni misurate delle telecamere. Non usarli come corrispondenze dell'omografia senza aver individuato lo stesso punto preciso nell'immagine.

Per ogni sorgente:

1. Individua sulla mappa l'incrocio e riconosci gli stessi elementi presenti nel video.
2. Clicca un punto **sul piano stradale** nell'immagine: per esempio un angolo riconoscibile della segnaletica a terra.
3. Scegli la corrispondente posizione geografica o inserisci coordinate attendibili. Lo sfondo CARTO è una mappa: per riferimenti fini usa un'ortofoto adeguata o coordinate rilevate, senza attribuire precisione centimetrica a un click approssimativo.
4. Premi **Accetta coordinata**. Ripeti con almeno quattro coppie non degeneri; preferibilmente 6–10 distribuite vicino, lontano e sui lati della zona da valutare.
5. Controlla residui e punti segnalati come outlier; correggi le corrispondenze sbagliate.
6. Premi **Pubblica**. Vengono salvati `calibration/UrbanSherbrooke.json` e `calibration/UrbanRene.json`.

Nel dialogo della struttura alternativa, le coppie vengono salvate durante l'inserimento e il pulsante finale è **Usa calibrazione**. Le stesse calibrazioni già pubblicate possono essere caricate e verificate.

Per aprire una sola camera:

```bash
python3 -m src.calibrate_ground --scenes urban_sherbrooke
```

Per lasciare l'editor aperto sul desktop e tornare al terminale:

```bash
python3 -m src.calibrate_ground --detach
```

## Coordinate, dominio e compatibilità

La matrice GeminiPort trasforma pixel **normalizzati** in un piano metrico con ordine **Nord, Est**. L'adattatore del progetto espone campi nominati `east_m`, `north_m` e usa **Est, Nord** negli interpolatori.

Il flusso è:

**bottom center in pixel → omografia → Est/Nord in metri → interpolazione → latitudine/longitudine WGS84**.

La griglia geografica è calcolata soltanto all'interno del poligono valido. Una singola omografia descrive un piano: non fornisce coordinate fisiche corrette per tetti, facciate, oggetti sopraelevati o strade su quote differenti. Zone esterne e punti non proiettabili sono registrati come non validi, senza coordinate sostitutive.

Calibrazione e tracking devono utilizzare la stessa sorgente, lo stesso rapporto d'aspetto e lo stesso preprocessing. Il tracking salvato usa i pixel originali. L'adattatore rifiuta una calibrazione eseguita su un diverso crop, zoom, undistortion o unwrap. Se è necessaria una rettifica ottica, va adottata coerentemente per entrambi prima del nuovo confronto. Gli zoom dei video dimostrativi non entrano nella calibrazione.

## Dopo la pubblicazione

```bash
python3 -m src.calibrate_ground --status
python3 -m src.project_ground
python3 -m src.metric_benchmark
python3 -m src.ground_report
```

Il primo script esporta per ciascuna osservazione coordinate metriche/geografiche e stato di validità; produce anche una griglia pixel→coordinate, in CSV e GeoJSON.

Il benchmark conserva soltanto i gap per cui **tutti i nodi visibili e i campioni di riferimento nascosti** sono nella zona calibrata. Confronta gli interpolatori in metri e ripete la baseline in pixel su quello stesso sottoinsieme. Il numero di casi esclusi viene riportato; non si confrontano medie calcolate su popolazioni differenti.

Output:

- `data/urbantracker/georeferenced/<video>/tracks_ground.csv`
- `data/urbantracker/georeferenced/<video>/ground_grid.csv`
- `data/urbantracker/georeferenced/<video>/ground_grid.geojson`
- `data/urbantracker/georeferenced/<video>/projection.json`
- `data/urbantracker/results/ground/RESULTS.md`

Il riferimento metrico deriva dalle osservazioni YOLO/ByteTrack trasformate: l'errore di interpolazione così misurato non coincide con l'accuratezza assoluta di localizzazione.

Il run attuale usa 7 punti a Sherbrooke (6 inlier, RMS del fit circa 0,280 m) e 4 a René-Lévesque (residuo numericamente nullo). Nessun checkpoint indipendente è stato ancora fornito. Lo snapshot della calibrazione usata viene salvato insieme alle coordinate proiettate, così una modifica successiva dei punti resta distinguibile dai risultati precedenti.

## Verifica indipendente della calibrazione

Copia `calibration/checkpoints_template.csv` in `calibration/checkpoints.csv` e compila le righe con punti **non utilizzati nel fit**, con pixel e coordinate geografiche attendibili. Quindi:

```bash
python3 -m src.project_ground --checkpoints calibration/checkpoints.csv
```

Il residuo sui punti del fit e quello sui punti indipendenti vengono tenuti distinti. Un fit a quattro punti può avere residuo quasi nullo senza certificare l'accuratezza della calibrazione sull'intera zona.
