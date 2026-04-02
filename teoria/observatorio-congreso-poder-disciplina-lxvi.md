---
title: "El poder (mal)entendido: lo que revelan los datos del Congreso de la Unión"
description: "Disciplina casi perfecta, dos bloques sin matices y 83% del poder en un solo partido. Los datos del Periodo 1 de la LXVI Legislatura desmienten las narrativas sobre el Congreso mexicano."
date: 2026-03-27
category: "investigaciones"
tags: ["congreso", "poder_legislativo", "shapley_shubik", "morena", "lxvi_legislatura", "co_votacion", "reforma_judicial"]
published: false
---

## ¿Qué significa realmente tener mayoría en el Congreso?

Hay una pregunta que vuelta y vuelta aparece en el debate público cada vez que se aprueba una ley controversial en San Lázaro: ¿qué tan poderosa es realmente la mayoría? La respuesta que circula en conferencias de prensa y columnas de opinión suele ser una narrativa política. Los datos del Primer Periodo Ordinario de Sesiones de la LXVI Legislatura ofrecen otra cosa: una respuesta cuantitativa, y es incómoda.

Este artículo presenta los hallazgos del **Observatorio del Congreso de la Unión**, un proyecto que scrapea las votaciones nominales publicadas en el Sistema de Información Legislativa (SITL), construye grafos de co-votación entre legisladores y calcula índices de poder formales. No es una encuesta. No es una opinión. Es lo que dicen los registros oficiales de votación.

### Qué hicimos y cómo

Tomamos **54 votaciones nominales** del Primer Periodo Ordinario de Sesiones de la LXVI Legislatura. Cada votación registra cómo votó cada uno de los diputados presentes: a favor, en contra o abstención. Con eso construimos una matriz de **co-votación normalizada**: para cada par de legisladores, calculamos la proporción de veces que votaron igual, ajustada por las oportunidades que tuvieron de coincidir. El resultado es un valor entre 0 (nunca coinciden) y 1 (siempre coinciden).

Sobre esa matriz corrimos **detección de comunidades con el algoritmo Louvain**, que agrupa legisladores según la densidad de sus conexiones de co-votación, sin decirle al algoritmo a qué partido pertenecen. Lo que Louvain encuentra — o no encuentra — es revelador.

Además, calculamos **índices de poder formal** para tres umbrales de aprobación: mayoría simple (251 de 500), mayoría calificada de dos tercios (334 de 500) y tres cuartos (375 de 500). Usamos dos índices clásicos de la teoría de juegos cooperativos: **Shapley-Shubik** y **Banzhaf**. Ambos miden esencialmente lo mismo desde ángulos distintos: la probabilidad de que un partido sea el voto pivote que convierte una coalición perdedora en ganadora. La diferencia entre el porcentaje nominal de escaños y el porcentaje de poder real es donde están las sorpresas.

Lo que encontramos desmiente varias de las narrativas que circulan sobre el funcionamiento del Congreso. Empecemos por la más básica: cómo votan.

---

## El mapa que nadie esperaba: disciplina perfecta, dos bloques sin matices

Si hay una cosa que todo mundo asume del Congreso mexicano es que hay matices. Que dentro de cada partido hay corrientes, que la disciplina no es absoluta, que al menos unos cuantos diputados rompen filas con cierta regularidad. Los datos del Periodo 1 dicen lo contrario.

### Co-votación intra-partido: disciplina del 99.74% o más

La co-votación intra-partido mide qué tanto coinciden entre sí los legisladores de un mismo partido. Un valor de 1.000 significa que todos los miembros votaron exactamente igual en todas las votaciones registradas. Así se ve:

| Partido | Co-votación intra-partido |
|---------|--------------------------|
| PVEM    | 1.0000                   |
| PAN     | 1.0000                   |
| Morena  | 0.9994                   |
| PT      | 0.9989                   |
| PRI     | 0.9989                   |
| MC      | 0.9974                   |

PVEM y PAN votan como un bloque monolítico: 1.000 perfecto. Morena, con 263 legisladores — la bancada más grande — alcanza 0.9994. Y Movimiento Ciudadano, el partido que más se presenta como opción diferente, tiene la disciplina intra-partido más baja de todos: 0.9974. Es decir, sus diputados coinciden entre sí el **99.74% de las veces**. Si eso es "disidencia", el término necesita una redefinición.

### Dos bloques, nada más

Cuando dejamos que el algoritmo Louvain agrupe a los legisladores solo por sus patrones de co-votación — sin decirle a qué partido pertenecen — detecta exactamente **2 comunidades**. No tres, no cuatro. Dos.

**Comunidad 1 (bloque coalición):**
- Morena: 263 legisladores
- PT: 49 legisladores
- PVEM: 64 legisladores
- Independientes: 1 legislador (co-vota a 1.0 con PT y PVEM)
- **Total: 377 legisladores**

**Comunidad 0 (bloque oposición):**
- PAN: 73 legisladores
- PRI: 38 legisladores
- MC: 29 legisladores
- **Total: 140 legisladores**

No hay errores de clasificación. Cada legislador de Morena, PT y PVEM cae en la comunidad 1. Cada legislador de PAN, PRI y MC cae en la comunidad 0. El algoritmo no sabe de partidos; solo ve patrones de votación. Y esos patrones dibujan una frontera nítida.

### La frontera entre bloques

La co-votación **inter-bloque** — es decir, qué tanto coincide un partido del bloque coalición con uno del bloque oposición — oscila entre 0.38 y 0.48:

| Par inter-bloque | Co-votación |
|------------------|-------------|
| Morena - MC      | 0.4796      |
| Morena - PRI     | 0.4530      |
| Morena - PAN     | 0.3824      |

Comparen eso con la co-votación **intra-coalición**:

| Par intra-coalición | Co-votación |
|---------------------|-------------|
| Morena - PVEM       | 0.9997      |
| PT - PVEM           | 0.9995      |
| Morena - PT         | 0.9991      |

La diferencia no es sutil. Morena y el PVEM coinciden el 99.97% de las veces. Morena y el PAN coinciden el 38.24% de las veces. No es un gradiente; es un muro.

### La narrativa que los datos desmienten

Movimiento Ciudadano se posiciona públicamente como "la verdadera oposición" — un partido distinto al PRI y al PAN, con autonomía y voz propia. Pero sus datos de co-votación lo colocan firmemente dentro del bloque opositor, con una disciplina interna (0.9974) que apenas difiere de la del PRI (0.9989). En el grafo de co-votación, MC es indistinguible de PAN y PRI. Louvain no encuentra ni un solo sub-grupo dentro del bloque oposición.

Dicho de otra forma: si la disciplina partidista es de 99.74%, la diferencia entre MC y el resto de la oposición no es de naturaleza sino de grado. Y el grado es mínimo.

---

## El poder (mal)entendido: 83% con 51% de escaños

Contar escaños es el ejercicio más común — y más engañoso — para medir el poder legislativo. Morena tiene 263 curules de 500, es decir, 50.87% de la Cámara. Conclusión rápida: tiene la mayoría, pero apenas por arriba de la línea. ¿Verdad que necesita aliados?

No necesariamente. Depende de la regla de votación.

### Qué mide Shapley-Shubik (y por qué debería importarte)

El **índice de Shapley-Shubik** mide la probabilidad de que un partido sea el voto pivote en una coalición ganadora. Imagina que se forman coaliciones de todos los tamaños y composiciones posibles, en orden aleatorio. El jugador que, al unirse, convierte una coalición perdedora en ganadora es el "pivote". Shapley-Shubik cuenta cuántas veces cada partido es pivote, dividido entre el total de coaliciones posibles.

A diferencia del conteo nominal de escaños, este índice captura algo crucial: **no todos los votos valen lo mismo**. Un partido con 263 escaños en un umbral de 251 es cualitativamente distinto a un partido con 73 escaños en el mismo umbral. El primero puede ganar solo; el segundo necesita aliados o no importa.

### Mayoría simple: Morena no necesita a nadie

Para leyes ordinarias, el umbral es mayoría simple: 251 votos de 500. Así se distribuye el poder:

| Partido | Escaños | % Nominal | Shapley-Shubik |
|---------|---------|-----------|----------------|
| Morena  | 263     | 50.87%    | 83.33%         |
| PAN     | 73      | 14.12%    | 3.33%          |
| PT      | 49      | 9.48%     | 3.33%          |
| PVEM    | 64      | 12.38%    | 3.33%          |
| PRI     | 38      | 7.35%     | 3.33%          |
| MC      | 29      | 5.61%     | 3.33%          |

Independientes (1 escaño) tienen 0% de poder formal: su voto individual nunca es pivote.

Morena concentra el **83.33% del poder formal** con solo el **50.87% de los escaños**. Los otros cinco partidos — aliados y opositores por igual — tienen exactamente el mismo poder: 3.33% cada uno.

La aritmética es simple: Morena tiene 263 escaños y el umbral es 251. Pasa sola. No necesita al PT, no necesita al PVEM, no necesita a nadie. Eso significa que en mayoría simple, PT y PVEM tienen el mismo poder de veto que PAN, PRI o MC: es decir, ninguno. Son irrelevantes para la aprobación de leyes ordinarias.

El **índice de Banzhaf** confirma el mismo patrón: Morena concentra el 86.11% del poder, y los cinco partidos restantes tienen 2.78% cada uno. Dos métodos distintos, misma conclusión.

### La narrativa que los datos desmienten

Se dice con frecuencia que "Morena necesita a sus aliados" para gobernar. Esto es cierto para reformas constitucionales — que requieren dos tercios —, y lo exploraremos en la siguiente sección. Pero para legislación ordinaria, la afirmación es falsa. Morena no necesita aliados; los aliados necesitan que Morena los necesite. Esa es una diferencia política enorme.

La concentración de poder en mayoría simple tiene una consecuencia directa: cualquier negociación entre el bloque coalición y el bloque oposición ocurre en términos de Morena. Los aliados (PT, PVEM) no son pivotes; los opositores (PAN, PRI, MC) no tienen palanca. El 83% del poder formal reside en una sola fuerza política, y los datos de co-votación confirman que esa fuerza política vota como bloque monolítico el 99.97% de las veces con sus aliados y el 99.94% de las veces internamente.

No es mayoría simple en el sentido técnico del término. Es mayoría simple en el sentido práctico: una sola fuerza decide, y las demás observan.

---

## La trampa de las mayorías calificadas: donde sí importan los aliados

Para leyes ordinarias, Morena no necesita a nadie. Con 263 escaños y un umbral de 251, la cuenta es sencilla: sobran 12 votos. Pero las reformas constitucionales exigen una mayoría calificada de dos tercios: 334 de 500. Y ahí la aritmética cambia todo.

La tabla lo cuenta mejor que cualquier discurso:

| Partido | Escaños | % Nominal | Poder Simple (Shapley-Shubik) | Poder Calificada 2/3 (Shapley-Shubik) |
|---------|---------|-----------|-------------------------------|---------------------------------------|
| Morena  | 263     | 50.87%    | 83.33%                        | 68.33%                                |
| PAN     | 73      | 14.12%    | 3.33%                         | 11.67%                                |
| PVEM    | 64      | 12.38%    | 3.33%                         | 6.67%                                 |
| PT      | 49      | 9.48%     | 3.33%                         | 6.67%                                 |
| PRI     | 38      | 7.35%     | 3.33%                         | 3.33%                                 |
| MC      | 29      | 5.61%     | 3.33%                         | 3.33%                                 |

El PAN es el aliado más valioso del universo calificado. Morena (263) + PAN (73) = 336, que supera los 334 por apenas dos votos. Es la coalición más pequeña posible que alcanza la mayoría calificada. Por eso el PAN pasa de valer 3.33% en mayoría simple a 11.67% en calificada: multiplicó su poder por tres sin ganar un solo escaño.

Pero aquí viene lo interesante: PVEM no alcanza. Morena (263) + PVEM (64) = 327, que son siete votos corto de 334. El Verde necesita también al PT para completar la ecuación: 263 + 64 + 49 = 376, que sobrepasa con holgura. PT y PVEM ganan poder en el escenario calificado (pasan de 3.33% a 6.67%), pero solo como par, nunca como individuos.

### A mayor umbral, más distribución

Si subimos la barra a tres cuartos (375 de 500), la distribución se acentúa:

| Partido | Poder 3/4 (Shapley-Shubik) |
|---------|---------------------------|
| Morena  | 55.71%                    |
| PAN     | 12.38%                    |
| PT      | 10.71%                    |
| PVEM    | 10.71%                    |
| PRI     | 5.71%                     |
| MC      | 4.05%                     |

A medida que el umbral sube, el poder se distribuye más. Pero Morena nunca pierde la mayoría del poder: incluso al 75%, conserva 55.71%.

### La paradoja de la negociación

Aquí está la paradoja política: Morena necesita al PAN para alcanzar 2/3 con la coalición más pequeña posible (336 ≥ 334), pero el PAN es el partido que más se opone a la agenda morenista. La negociación real no ocurre con Acción Nacional sino con PT y PVEM, que juntos suman 113 escaños. La combinación Morena + PT + PVEM da 376, que supera 334 con 42 votos de margen. No es la coalición más pequeña, pero es la políticamente viable.

El poder de negociación de PT y PVEM no viene de su tamaño sino de su posicionamiento: son los únicos aliados dispuestos a votar con la coalición en votaciones calificadas. El PAN podría ser matemáticamente más valioso, pero políticamente no es una opción real.

---

## La Reforma Judicial: cuando cada voto contó

La Reforma Judicial es el caso de estudio perfecto para ver cómo funciona esta aritmética en la práctica.

La votación general (VE04) se resolvió con 359 votos a favor, 135 en contra y 6 ausentes. El umbral calificado era 334. Margen: 25 votos. La votación particular (VE05) quedó en 357 a favor, 130 en contra y 13 ausentes, con un margen de 23.

### El desglose que lo explica todo

VE04, voto por voto:

| Partido | A favor | En contra | Ausentes | Total |
|---------|---------|-----------|----------|-------|
| Morena  | 250     | 0         | 5        | 255   |
| PT      | 47      | 0         | 0        | 47    |
| PVEM    | 62      | 0         | 0        | 62    |
| PAN     | 0       | 71        | 0        | 71    |
| PRI     | 0       | 37        | 0        | 37    |
| MC      | 0       | 27        | 0        | 27    |

Los tres partidos de la coalición fueron críticos. Sin PVEM y sus 62 votos, Morena más PT sumaban 297: 37 corto de los 334 necesarios. Sin PT y sus 47 votos, Morena más PVEM quedaban en 312: 22 votos abajo. Y sin los 250 de Morena, imposible. Cada uno era indispensable.

Pero el margen fue de 25 votos. Suficiente para no depender de un diputado individual, pero insuficiente para perder un partido entero. Si PVEM hubiera votado en contra, la reforma no pasaba. Punto.

### Dos votaciones que no cuadran

El análisis detectó dos votaciones con inconsistencias. VE34 aparece marcada como aprobada pero solo registró 332 votos a favor, dos menos que los 334 requeridos. VE41 llegó a solo 327 a favor. En ambos casos, el margen sobre el umbral es negativo (-2 y -7 respectivamente). La explicación más probable es que el resultado se calculó sobre asistentes presentes, no sobre el total de 500 curules. Esto merecería una verificación más detallada del reglamento aplicado.

### El poder que realmente se ejerció

El índice de Shapley-Shubik mide poder teórico: cuánto vale cada partido en todas las coaliciones posibles. Pero las votaciones reales de las 54 nominales permiten calcular algo más concreto: el **poder empírico**.

El poder empírico responde a una pregunta simple: ¿en cuántas votaciones un partido fue crítico? Un partido es crítico cuando su ausencia habría cambiado el resultado (de aprobado a rechazado o viceversa).

De las 52 votaciones con datos completos (VE03 a VE54):

| Partido | Poder Empírico |
|---------|---------------|
| Morena  | 96.15%        |
| PVEM    | 23.08%        |
| PT      | 23.08%        |
| PAN     | 0.00%         |
| PRI     | 0.00%         |
| MC      | 0.00%         |
| Independientes | 1.92%  |

Morena fue crítica en 50 de 52 votaciones (96.15%). PT y PVEM fueron críticos en 12 cada uno (23.08%) — siempre en las mismas votaciones calificadas donde la coalición entera era necesaria. PAN, PRI y MC: cero. Nunca estuvieron en posición de cambiar un resultado.

La oposición no fue una fuerza negociadora. En ninguna de las 54 votaciones nominales su voto habría alterado el resultado final. Su poder empírico es literalmente cero.

---

## Los disidentes de cartón: Napoleón Gómez Urrutia y los rebeldes que no son

Si la oposición no puede cambiar resultados, ¿qué pasa con los disidentes dentro de la coalición? ¿Existen facciones reales?

Los datos dicen que no. Los 10 legisladores con mayor porcentaje de votos disidentes (votar diferente a la mayoría de su partido):

| Rank | Nombre | Partido | % Disidencia | Votaciones | Votos Disidentes |
|------|--------|---------|-------------|------------|-----------------|
| 1 | Ifigenia Martha Martínez y Hernández | Morena | 100.0% | 10 | 10 |
| 2 | Mónica Becerra Moreno | PAN | 61.5% | 52 | 32 |
| 3 | Carmen Patricia Armendáriz Guerra | Morena | 55.8% | 52 | 29 |
| 4 | Magaly Armenta Oliveros | Morena | 55.8% | 52 | 29 |
| 5 | Napoleón Gómez Urrutia | Morena | 53.8% | 52 | 28 |
| 6 | Freyda Marybel Villegas Canché | Morena | 50.0% | 30 | 15 |
| 7 | Jorge Luis Villatoro Osorio | PVEM | 49.0% | 51 | 25 |
| 8 | Casandra Prisilla De Los Santos Flores | PVEM | 43.1% | 51 | 22 |
| 9 | Claudia Quiñones Garrido | PAN | 40.4% | 52 | 21 |
| 10 | Adrián Oseguera Kernion | Morena | 38.5% | 52 | 20 |

Cuatro de los cinco principales disidentes son de Morena, el partido con más escaños. Napoleón Gómez Urrutia — líder histórica del Sindicato Nacional de Trabajadores Mineros, Metalúrgicos, Siderúrgicos y Similares — disiente en el 53.8% de las votaciones. Si uno lee el titular sin contexto, parece un rebelde.

### La trampa del porcentaje

Ifigenia Martínez aparece con 100% de disidencia. Pero participó en apenas 10 de 52 votaciones. Probablemente por ausencia prolongada o llegada tardía al periodo legislativo, no por rebeldía ideológica. Un porcentaje sobre 10 observaciones no es comparable a uno sobre 52.

Mónica Becerra Moreno (PAN) disiente en el 61.5% de las votaciones. Pero — y aquí está la clave — la co-votación intra-PAN es 1.000 perfecta. ¿Cómo puede alguien disentir el 61.5% dentro de un partido que vota como bloque monolítico?

La respuesta está en la metodología. "Disidencia" aquí significa votar diferente a la mayoría del partido en una votación específica. Si el PAN vota unánimemente a favor en 30 votaciones y Becerra Moreno vota en contra en 32, su disidencia es alta. Pero la co-votación se calcula normalizada por frecuencia: si ella coincide con su partido en las votaciones donde el partido es relevante, su co-votación ponderada sigue siendo alta. Son métricas que capturan cosas distintas.

### Ruido, no señal

La disidencia en esta legislatura es ruido estadístico, no señal política. No cambia resultados (la coalición tiene margen suficiente en todas las votaciones calificadas), no forma facciones discernibles (el análisis de grafos no detecta sub-bloques dentro de Morena), y no amenaza la disciplina del bloque. Los "rebeldes" votan diferente en votaciones que no son decisivas.

### Limitaciones del análisis

Esto se basa en 54 votaciones nominales de un solo periodo ordinario. No todas las votaciones del pleno son nominales: se necesitan 6 legisladores para solicitar una votación nominal (Ainsley et al. 2020), lo que introduce un sesgo de selección hacia votaciones políticamente relevantes o contentious. Las votaciones por cédula o económicas quedan fuera. Además, un solo periodo no captura la dinámica completa de la legislatura. Los patrones pueden cambiar en periodos subsiguientes.

---

## Lo que dicen los datos sobre el futuro del legislativo mexicano

Los datos del Periodo 1 de la LXVI Legislatura pintan un panorama que no debería sorprender a nadie que haya seguido la evolución del sistema de partidos mexicano, pero que las cifras hacen innegable.

**La disciplina partidista es perfecta.** No hay facciones reales, no hay corrientes discernibles en los datos de co-votación. Ni siquiera dentro de Morena, con 263 legisladores de orígenes y trayectorias heterogéneas, el algoritmo detecta sub-bloques. El Congreso no funciona como un espacio de deliberación entre posiciones diversas; funciona como dos ejércitos que votan en bloque.

**El poder de los aliados es limitado y puntual.** PT y PVEM son irrelevantes para leyes ordinarias. Su poder de negociación existe exclusivamente en el universo de las mayorías calificadas, y aun ahí dependen de que Morena no logre persuadir a un puñado de opositores. La Reforma Judicial fue su momento de mayor relevancia — sin ellos, no se aprobaba — pero ese momento fue la excepción, no la regla. La mayoría de las votaciones calificadas del periodo las ganó Morena sola.

**La oposición tiene cero poder empírico.** Esto no es una exageración retórica; es un dato. En 54 votaciones, ningún partido de oposición fue crítico. Nunca su ausencia habría cambiado un resultado. La función de la oposición en esta legislatura es simbólica: votar en contra, aparece en el registro, pero no altera nada.

**Los disidentes son ruido, no señal.** Napoleón Gómez Urrutia puede disentir en el 53.8% de las votaciones, pero su disidencia no tiene consecuencia alguna sobre los resultados. No forma facción, no contagia, no amenaza la cohesión del bloque. Es ruido estadístico dentro de una máquina que vota al 99.94% de disciplina.

**Las limitaciones importan.** Esto es un periodo. Las dinámicas cambian. Las votaciones nominales son un subconjunto sesgado del total. Pero incluso con esas salvedades, los datos son contundentes: la LXVI Legislatura opera con una concentración de poder sin contrapesos efectivos, y la disciplina de bloque hace que esos contrapesos teóricos — los aliados que podrían negociar, la oposición que podría moderar — sean irrelevantes en la práctica.

La pregunta que sigue no es si esto es bueno o malo — eso depende de donde uno se pare — sino si es sostenible. Una legislatura donde una fuerza concentra 83% del poder formal, 96% del poder empírico y vota con 99.94% de disciplina interna no es un sistema de pesos y contrapesos. Es un sistema de mayoría efectiva sin freno. Los datos no juzgan; simplemente describen. Pero lo que describen debería preocupar a cualquiera que crea en la deliberación legislativa como mecanismo de gobierno.

## Fuentes

- *Sistema de Información Legislativa (SITL/INFOPAL), Cámara de Diputados* — Datos de votaciones nominales, Periodo 1, LXVI Legislatura (54 votaciones, 25,829 votos)
- *Observatorio del Congreso de la Unión* — Análisis de co-votación normalizada, detección de comunidades Louvain, índices de poder Shapley-Shubik y Banzhaf, poder empírico
- *Shapley, L.S. (1953). "A Value for n-Person Games." Contributions to the Theory of Games* — Metodología del índice de poder Shapley-Shubik
- *Banzhaf, J.F. (1965). "Weighted Voting Doesn't Work: A Mathematical Analysis." Rutgers Law Review* — Metodología del índice de poder Banzhaf
- *Blondel, V.D. et al. (2008). "Fast unfolding of communities in large networks." Journal of Statistical Mechanics* — Metodología del algoritmo Louvain para detección de comunidades
- *Ainsley, C. et al. (2020). American Political Science Review* — Umbral de 6 legisladores para solicitar votación nominal en México, sesgo de selección documentado
- *Magar, E. (ITAM)* — Productor principal de datos de votación nominal mexicana, papers en APSR, JOP, LSQ
