# Confronto dei metodi del corso e clip dei passaggi

- 8 metodi nel benchmark stradale, 5517 gap, 44136 valutazioni.
- Fallimenti numerici: 0; maschere salvate riutilizzate: True.
- 12 clip di passaggi, durata 6.40–8.01 s, codificate con NVENC.
- Ogni clip: riferimento YOLO/ByteTrack rosso acceso, zoom fisso e un riquadro per interpolatore.
- Le clip sono illustrative e selezionate per movimento e distribuzione temporale, indipendentemente dagli errori. Le metriche coprono tutti i casi ammissibili dei video completi.

## Metodi

Vandermonde (sistema monomiale), Lagrange (formula diretta), Newton (differenze divise e Horner), S1, S3 naturale e S3 vincolata costituiscono il nucleo trattato nelle slide.
La S3 vincolata stima le derivate ai bordi dai primi/ultimi tre campioni visibili. Non usa velocità ricavate dai punti nascosti.
S2 è un'estensione dalla definizione generale di spline. La famiglia razionale è introdotta nelle slide; la specifica costruzione Floater–Hormann, parametro d=3, è un'estensione esterna esplicitamente indicata.

## Risultati sui video, 8 nodi

| Metodo | Gap | ADE (px) | RMS (px) | Fit mediano (ms) | Fallimenti |
|---|---:|---:|---:|---:|---:|
| Lagrange | 3 | 0.4362 | 0.6955 | 0.1174 | 0 |
| Lagrange | 6 | 0.9756 | 1.4814 | 0.1176 | 0 |
| Lagrange | 12 | 3.1968 | 5.2456 | 0.1179 | 0 |
| Lagrange | 24 | 14.2928 | 25.3907 | 0.1177 | 0 |
| Newton | 3 | 0.4362 | 0.6955 | 0.0545 | 0 |
| Newton | 6 | 0.9756 | 1.4814 | 0.0549 | 0 |
| Newton | 12 | 3.1968 | 5.2456 | 0.0548 | 0 |
| Newton | 24 | 14.2928 | 25.3907 | 0.0553 | 0 |
| Razionale FH (est.) | 3 | 0.6792 | 1.0875 | 0.1980 | 0 |
| Razionale FH (est.) | 6 | 1.8519 | 2.8934 | 0.1982 | 0 |
| Razionale FH (est.) | 12 | 7.2033 | 12.5734 | 0.1987 | 0 |
| Razionale FH (est.) | 24 | 35.1647 | 65.8957 | 0.1987 | 0 |
| S1 lineare | 3 | 0.3005 | 0.4821 | 0.1005 | 0 |
| S1 lineare | 6 | 0.4154 | 0.7901 | 0.1000 | 0 |
| S1 lineare | 12 | 0.6166 | 1.3814 | 0.0996 | 0 |
| S1 lineare | 24 | 0.8799 | 2.2591 | 0.0992 | 0 |
| S2 (estensione) | 3 | 0.7501 | 1.1024 | 0.0793 | 0 |
| S2 (estensione) | 6 | 1.1856 | 1.8181 | 0.0802 | 0 |
| S2 (estensione) | 12 | 1.9437 | 3.0040 | 0.0801 | 0 |
| S2 (estensione) | 24 | 3.3569 | 5.9658 | 0.0806 | 0 |
| S3 vincolata | 3 | 0.3382 | 0.5195 | 0.6253 | 0 |
| S3 vincolata | 6 | 0.5236 | 0.8300 | 0.6272 | 0 |
| S3 vincolata | 12 | 0.8320 | 1.3137 | 0.6283 | 0 |
| S3 vincolata | 24 | 1.3402 | 2.3050 | 0.6313 | 0 |
| S3 naturale | 3 | 0.3382 | 0.5189 | 0.3008 | 0 |
| S3 naturale | 6 | 0.5233 | 0.8296 | 0.3016 | 0 |
| S3 naturale | 12 | 0.8315 | 1.3137 | 0.3010 | 0 |
| S3 naturale | 24 | 1.3387 | 2.3018 | 0.3022 | 0 |
| Vandermonde | 3 | 0.4362 | 0.6955 | 0.0733 | 0 |
| Vandermonde | 6 | 0.9756 | 1.4814 | 0.0736 | 0 |
| Vandermonde | 12 | 3.1968 | 5.2456 | 0.0735 | 0 |
| Vandermonde | 24 | 14.2928 | 25.3907 | 0.0738 | 0 |

I tempi sono misure descrittive di singoli fit, aggregate su molte prove; includono le due coordinate. Il calcolo del condizionamento è escluso dall'intervallo cronometrato.
Il condizionamento esportato si riferisce alla matrice monomiale sul tempo normalizzato, non a ogni famiglia di interpolatori. L'eccesso rispetto al rettangolo dei nodi di supporto è un indicatore geometrico, non un errore fisico.

![Confronto](assets/course_comparison.png)

## Equivalenza delle formulazioni polinomiali

- Vandermonde / lagrange: 56928 punti confrontati, differenza euclidea massima **1.044e-10 pixel**.
- Vandermonde / newton: 56928 punti confrontati, differenza euclidea massima **2.966e-11 pixel**.

Con gli stessi nodi i tre metodi rappresentano lo stesso polinomio. Le oscillazioni rispetto al riferimento non si risolvono semplicemente passando da una formulazione all'altra.

## Esperimenti dedicati

- **Chebyshev/Runge:** gradi 4, 8, 12, 16, 24 e 32; n+1 nodi equispaziati o radici esatte di Chebyshev. Valutazione matematica su [-1,1], comprese le piccole fasce esterne alle radici; nessun accesso ai dati video nascosti.
- **Periodicità:** traiettoria analitica chiusa con periodo noto; S3 periodica e interpolazione trigonometrica confrontate con S1 e S3 naturale. Per i campioni mancanti si risolve il sistema trigonometrico, non si applica direttamente una FFT alla griglia incompleta.
- **Supporto:** 4, 6 e 8 osservazioni visibili sugli stessi punti nascosti. Per i polinomi corrispondono a gradi massimi 3, 5 e 7. Le maschere derivate mantengono l'esclusione globale dei campioni nascosti.

![Chebyshev](assets/chebyshev_runge.png)

![Periodicità](assets/periodic.png)

La trigonometrica può riprodurre quasi esattamente il segnale sintetico perché questo appartiene alla base scelta. Ciò non dimostra superiorità sui video di traffico non periodici.
Le ricostruzioni stradali sono riferite a output YOLO/ByteTrack post-tracking, non a posizioni fisiche esatte o identità manualmente validate.
