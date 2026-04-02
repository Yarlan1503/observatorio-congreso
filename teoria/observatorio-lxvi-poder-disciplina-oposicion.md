---
title: "Poder, disciplina y el mito de la oposición: lo que dicen 199 votaciones de la LXVI Legislatura"
description: "199 votaciones nominales, 98,322 votos individuales y 567 legisladores revelan que Morena concentra 83% del poder formal en leyes ordinarias, la disciplina partidista es perfecta, y la oposición tiene 0% de poder empírico."
date: 2026-03-28
category: "investigaciones"
tags: ["congreso", "politica_mexicana", "teoria_de_grafos", "teoria_de_juegos", "shapley_shubik", "covotacion", "lxvi_legislatura", "reforma_judicial"]
published: true
---

## ¿Qué significa realmente tener mayoría en el Congreso?

Hay una pregunta que vuelve y vuelve en el debate público cada vez que se aprueba una ley controversial en San Lázaro: ¿qué tan poderosa es realmente la mayoría? La respuesta que circula en conferencias de prensa y columnas de opinión suele ser una narrativa política. Los datos de la LXVI Legislatura ofrecen otra cosa: una respuesta cuantitativa, y es incómoda.

Este artículo presenta los hallazgos del **Observatorio del Congreso de la Unión**, un proyecto que scrapea las votaciones nominales publicadas en el Sistema de Información Legislativa de la Cámara de Diputados, construye grafos de co-votación entre legisladores y calcula índices de poder formales. El dataset incluye **199 votaciones nominales, 98,322 votos individuales de 567 legisladores**, distribuidos en 4 periodos legislativos con datos disponibles. No es una muestra. Es el universo de lo votado nominalmente en la legislatura. No es una encuesta. No es una opinión. Es lo que dicen los registros oficiales de votación.

### Qué hicimos y cómo

Cada votación registra cómo votó cada uno de los diputados presentes: a favor, en contra o abstención. Con eso construimos una **matriz de co-votación normalizada**: para cada par de legisladores, calculamos la proporción de veces que votaron igual, ajustada por las oportunidades que tuvieron de coincidir. El resultado es un valor entre 0 (nunca coinciden) y 1 (siempre coinciden).

Sobre esa matriz corrimos **detección de comunidades con el algoritmo Louvain**, que agrupa legisladores según la densidad de sus conexiones de co-votación, sin decirle al algoritmo a qué partido pertenecen. Lo que Louvain encuentra — o no encuentra — es revelador.

Además, calculamos **índices de poder formal** para tres umbrales de aprobación: mayoría simple (251 de 500), mayoría calificada de dos tercios (334 de 500) y tres cuartos (375 de 500). Usamos dos índices clásicos de la teoría de juegos cooperativos: **Shapley-Shubik** y **Banzhaf**. Ambos miden esencialmente lo mismo desde ángulos distintos: la probabilidad de que un partido sea el voto pivote que convierte una coalición perdedora en ganadora. La diferencia entre el porcentaje nominal de escaños y el porcentaje de poder real es donde están las sorpresas.

Lo que encontramos desmiente varias de las narrativas que circulan sobre el funcionamiento del Congreso. Empecemos por la más básica: cómo votan.

---

## El mapa que nadie esperaba: disciplina perfecta, dos bloques sin matices

Si hay una cosa que todo mundo asume del Congreso mexicano es que hay matices. Que dentro de cada partido hay corrientes, que la disciplina no es absoluta, que al menos unos cuantos diputados rompen filas con cierta regularidad. Los datos dicen lo contrario.

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

PVEM y PAN votan como un bloque monolítico: 1.000 perfecto. Morena, con 263 legisladores — la bancada más grande — alcanza 0.9994. Y Movimiento Ciudadano, el partido que más se presenta como opción diferente, tiene la disciplina intra-partido más baja de todos: 0.9974. Es decir, sus diputados coinciden entre sí el **99.74% de las veces**. Si eso es "disidencia", el término necesita una redefinición urgente.

### Dos bloques, nada más

Cuando dejamos que el algoritmo Louvain agrupe a los legisladores solo por sus patrones de co-votación — sin decirle a qué partido pertenecen — detecta exactamente **2 comunidades**. No tres, no cuatro. Dos.

**Comunidad 1 (bloque coalición):** 372 legisladores — morenistas, petistas y pevemistas.

**Comunidad 0 (bloque oposición):** 136 legisladores — panistas, priistas y emecistas.

No hay errores de clasificación. Cada legislador de Morena, PT y PVEM cae en la comunidad 1. Cada legislador de PAN, PRI y MC cae en la comunidad 0. El algoritmo no sabe de partidos; solo ve patrones de votación. Y esos patrones dibujan una frontera nítida.

Lo más revelador es que Louvain no detecta sub-bloques dentro de Morena. Con 263 legisladores, con corrientes internas documentadas, con líderes regionales con peso propio, el algoritmo no encuentra facciones. Más allá de lo que se vea en las notas políticas del día, el voto dice que Morena es un bloque monolítico.

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

| Partido | Escaños | % Nominal | Shapley-Shubik | Banzhaf |
|---------|---------|-----------|----------------|---------|
| Morena  | 263     | 50.87%    | 83.33%         | 86.11%  |
| PAN     | 73      | 14.12%    | 3.33%          | 2.78%   |
| PT      | 49      | 9.48%     | 3.33%          | 2.78%   |
| PVEM    | 64      | 12.38%    | 3.33%          | 2.78%   |
| PRI     | 38      | 7.35%     | 3.33%          | 2.78%   |
| MC      | 29      | 5.61%     | 3.33%          | 2.78%   |

*Los escaños reflejan la composición máxima por partido durante la legislatura, incluyendo rotaciones de suplentes. El total supera las 500 curules constitucionales.*

Morena concentra el **83.33% del poder formal** con solo el **50.87% de los escaños**. Los otros cinco partidos — aliados y opositores por igual — tienen exactamente el mismo poder: 3.33% cada uno.

La aritmética es simple: Morena tiene 263 escaños y el umbral es 251. Pasa sola. No necesita al PT, no necesita al PVEM, no necesita a nadie. Eso significa que en mayoría simple, PT y PVEM tienen el mismo poder de veto que PAN, PRI o MC: es decir, ninguno. Son irrelevantes para la aprobación de leyes ordinarias.

El **índice de Banzhaf** confirma el mismo patrón: Morena concentra el 86.11% del poder, y los cinco partidos restantes tienen 2.78% cada uno. Dos métodos distintos, misma conclusión.

Lo que sigue es contraintuitivo pero matemáticamente inexorable: PAN, PVEM, PT, PRI y MC valen exactamente lo mismo. Tener 73 escaños (PAN) o 29 (MC) da el mismo poder formal cuando Morena ya cruza el umbral por sí sola. En un escenario donde un partido puede gobernar unilateralmente, todos los demás son intercambiables. Sus escaños no suman nada que Morena no tenga ya.

### La narrativa que los datos desmienten

Se dice con frecuencia que "Morena necesita a sus aliados" para gobernar. Esto es cierto para reformas constitucionales — que requieren dos tercios —, y lo exploraremos a continuación. Pero para legislación ordinaria, la afirmación es falsa. Morena no necesita aliados; los aliados necesitan que Morena los necesite. Esa es una diferencia política enorme.

La concentración de poder en mayoría simple tiene una consecuencia directa: cualquier negociación entre el bloque coalición y el bloque oposición ocurre en términos de Morena. Los aliados (PT, PVEM) no son pivotes; los opositores (PAN, PRI, MC) no tienen palanca. El 83% del poder formal reside en una sola fuerza política, y los datos de co-votación confirman que esa fuerza política vota como bloque monolítico el 99.97% de las veces con sus aliados y el 99.94% de las veces internamente.

No es mayoría simple en el sentido técnico del término. Es mayoría simple en el sentido práctico: una sola fuerza decide, y las demás observan.

---

## La trampa de las mayorías calificadas

Hasta aquí la historia es simple: Morena pasa sola. Pero las leyes ordinarias no son todo. Las reformas constitucionales necesitan **mayoría calificada** de dos tercios: 334 de 500 votos. Y ahí la aritmética cambia.

La primer lección de la teoría de juegos cooperativos es que el poder no depende solo de cuántos escaños tienes, sino de cuántos necesitas y quién más los tiene. Con umbral de 2/3, los índices se reacomodan:

| Partido | Escaños | % Nominal | Shapley-Shubik | Banzhaf |
|---------|---------|-----------|----------------|---------|
| Morena | 263 | 50.87% | 68.33% | 59.09% |
| PAN | 73 | 14.12% | 11.67% | 13.64% |
| PVEM | 64 | 12.38% | 6.67% | 9.09% |
| PT | 49 | 9.48% | 6.67% | 9.09% |
| PRI | 38 | 7.35% | 3.33% | 4.55% |
| MC | 29 | 5.61% | 3.33% | 4.55% |

*Los escaños reflejan la composición máxima por partido durante la legislatura, incluyendo rotaciones de suplentes.*

Morena baja de 83% a 68%. Sigue siendo el jugador dominante, pero ya no es todopoderoso. Y aquí viene el detalle que importa: el **PAN** se convierte en el aliado más valioso del tablero.

Morena tiene 263 curules. El PAN tiene 73. Juntos suman 336, que supera los 334 necesarios. Es la coalición mínima ganadora más pequeña posible. En cambio, Morena más PVEM da 327: no alcanza. El Verde necesita también al PT para llegar.

La paradoja política es fascinante. Matemáticamente, Morena necesita al PAN más que al PVEM o al PT. Pero políticamente, la coalición real es Morena + PVEM + PT: 263 + 64 + 49 = 376. Sobran 42 votos. Negocian con sus aliados naturales, no con el adversario más eficiente.

Y si subimos el umbral a 3/4 (375 de 500), la distribución se acentúa: Morena cae a **55.71%** por Shapley-Shubik. El PT y el PVEM suben a 10.71% cada uno. El PAN baja a 12.38%. Pero Morena nunca pierde la mayoría del poder, sin importar el umbral.

### La Reforma Judicial: la prueba de fuego

La Reforma Judicial confirma todo esto con datos concretos. En la votación general (VE04), el resultado fue 359 a favor, 135 en contra, 6 ausentes. Umbral: 334. Margen: 25 votos. El desglose por partido revela que los tres miembros de la coalición fueron críticos:

- Morena: 250 a favor, 0 en contra, 5 ausentes
- PT: 47 a favor, 0 en contra
- PVEM: 62 a favor, 0 en contra

Sin PVEM y sus 62 votos, Morena más PT llegaban a 297. Quedaban 37 corto del umbral. Sin PT y sus 47 votos, Morena más PVEM llegaban a 312, 22 corto. La votación particular (VE05) cuenta la misma historia: 357 a favor, 130 en contra, 13 ausentes, margen de 23 votos. Mismo patrón.

### El umbral que se mueve

Pero hay un hallazgo que cambia la lectura completa. El **Artículo 135 de la Constitución** establece que las reformas constitucionales necesitan dos tercios de los "individuos presentes", no de las 500 curules. El umbral real es dinámico según la asistencia. Si hay 450 presentes, 2/3 son 300, no 334.

México usa bases de cálculo diferentes según el tipo de votación: presentes para reformas (Art. 135), votos emitidos para veto presidencial (Art. 72-C), y total de miembros para quórum (Art. 63). Dos votaciones del dataset (VE34 y VE41) parecían no alcanzar 2/3 sobre 500 (332 y 327 votos respectivamente), pero calculadas sobre los presentes sí pasan: 73.61% y 73.48%.

Esto importa porque significa que el poder real en votaciones calificadas depende no solo de cuántos aliados tienes, sino de cuánta gente se presentó ese día. La disciplina partidista se vuelve aún más valiosa: controlar la asistencia es controlar el umbral.

---

## Y la oposición, ¿qué?

PAN, PRI, MC: **0.00% de poder empírico**. Cero punto cero cero por ciento.

No es una metáfora. No es una exageración retórica. Es el resultado de revisar las 199 votaciones y contar en cuántas la oposición fue crítica para el resultado. La respuesta es: en ninguna.

| Partido | Poder Empírico |
|---------|---------------|
| Morena | 96.15% |
| PVEM | 23.08% |
| PT | 23.08% |
| PAN | 0.00% |
| PRI | 0.00% |
| MC | 0.00% |
| Independientes | 1.92% |

La oposición existe como bloque de votación. La co-votación entre PAN y PRI es de 0.9459; entre PAN y MC de 0.8758. Votan juntos, sistemáticamente en contra de la coalición. Pero como fuerza negociadora, su capacidad de influir en resultados es nula. No pueden bloquear nada. No pueden aprobar nada. No pueden modificar nada.

Su papel es simbólico: votan en contra, dan declaraciones, ocupan tribuna. Pero matemáticamente, ningún resultado de las 199 votaciones habría cambiado si PAN, PRI y MC no hubieran asistido. Eso es un dato, no una opinión.

Las implicaciones para la calidad democrática son serias. Un Congreso donde un tercio de los legisladores no puede influir en ningún resultado no está funcionando como contrapeso. La oposición es espectadora con curul.

---

## Los disidentes de cartón

Si la oposición no existe y la disciplina es casi perfecta, ¿qué pasa con los que rompen filas? Los medios ocasionalmente destacan a legisladores "rebeldes" dentro de Morena. Veamos qué dicen los datos.

El ranking de disidentes tiene una sorpresa: 4 de los 5 principales son de Morena. Pero cuando examinas los números, la narrativa se desmorona.

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

Ifigenia Martínez encabeza la lista con 100% de disidencia. Cien por ciento. Suena devastador. Pero solo participó en 10 de las 199 votaciones. Probablemente ausencia prolongada o llegada tardía al periodo legislativo, no rebeldía ideológica. Cuando tu N es 10, cualquier patrón es ruido.

Napoleón Gómez Urrutia, líder del Sindicato Nacional de Trabajadores Mineros, disiente en 53.8% de las votaciones. Si lees el titular, parece un rebelde con causa. Pero sus votos disidentes caen consistentemente en votaciones que no son decisivas. La coalición tiene margen suficiente para absorber su disidencia sin que cambie un solo resultado.

El caso de Mónica Becerra Moreno es el más instructivo metodológicamente. Tiene 61.5% de disidencia dentro del PAN. Pero la co-votación intra-PAN es de **1.000**: perfecta. ¿Cómo puede alguien disentir el 61.5% dentro de un partido monolítico?

La respuesta está en lo que mide cada métrica. "Disidencia" cuenta cuántas veces votas diferente a la mayoría de tu partido en una votación específica. Si el PAN vota unánimemente a favor en 30 votaciones y Becerra vota en contra en 32 de las 52 analizadas, su disidencia es alta. Pero la co-votación ponderada, que evalúa la correlación global entre todos los pares de legisladores, sigue siendo perfecta porque la inmensa mayoría de las votaciones coinciden. Capturan cosas distintas.

La disidencia en esta legislatura es **ruido estadístico, no señal política**. Tres razones:

**Primero, no cambia resultados.** La coalición tiene márgenes de holgura suficientes en la mayoría de las votaciones calificadas (25 y 23 votos en las Reformas Judiciales), y en mayoría simple Morena pasa sola.

**Segundo, no forma facciones.** El algoritmo de Louvain no detecta sub-bloques dentro de Morena con 199 votaciones. Los "rebeldes" no votan juntos de forma sistemática que permita identificar una corriente interna. Son islas dispersas, no un archipiélago.

**Tercero, incluso el disidente más extremo coincide con su partido más del 91% del tiempo en co-votación ponderada.** Si alguien vota contigo 9 de cada 10 veces, no es tu opositor. Es tu compañero con desacuerdos puntuales.

Los disidentes existen. Los datos no mienten sobre eso. Pero su impacto en los resultados legislativos es indistinguible de cero.

---

## Lo que dicen los datos

El Congreso mexicano tiene un problema estructural. No es un problema de personas ni de partidos específicos. Es un problema de diseño: disciplina perfecta más oposición irrelevante igual a cero contrapesos reales.

Cuando un solo bloque puede aprobar leyes ordinarias unilateralmente, aprobar reformas constitucionales con sus aliados sin negociar con la oposición, y absorber la disidencia interna sin que afecte ningún resultado, el legislativo deja de ser un espacio de deliberación y se convierte en un sello automático. Los datos de 199 votaciones lo confirman sin ambigüedad.

Pero hay una buena noticia: el observatorio funciona. Con 199 votaciones nominales y 98,322 votos individuales de 567 legisladores, los patrones son claros, replicables y cuantificables. Podemos medir quién tiene poder, cuándo lo tiene, y cuándo no. El siguiente paso es **NOMINATE**, el método de Poole y Rosenthal que ubica a cada legislador en un espacio ideológico a partir de sus votos. Con 199 votaciones, el modelo es viable. Eso era la Fase 4 del roadmap, y ahora está desbloqueada.

También estamos explorando grafos dinámicos para observar cómo cambian las alianzas entre periodos legislativos. La co-votación es una fotografía estática; necesitamos el video.

### Limitaciones

Los datos que presentamos tienen limitaciones que vale la pena hacer explícitas. Las 199 votaciones provienen de una legislatura en curso, no son el universo completo. No todas las votaciones del Congreso son nominales: se necesitan 6 legisladores para solicitar votación nominal, lo que introduce un sesgo hacia votaciones contenciosas donde alguien tuvo interés en registrar el voto individual. Los índices de poder formal como Shapley-Shubik se calculan sobre escaños, no sobre asistentes reales. Y todo este análisis cubre solo la Cámara de Diputados, no el Senado.

Nada de esto cambia la conclusión central. El poder legislativo en México está hiperconcentrado, la oposición es irrelevante como fuerza negociadora, y la disidencia interna no tiene impacto en resultados. Eso no es motivo de celebración. Es motivo de observación.

---

## Fuentes

- *[Shapley, L.S. (1953)](https://doi.org/10.1515/9781400881970-018)* — "A Value for n-Person Games" — método para calcular distribución de poder entre jugadores en juegos cooperativos
- *[Blondel et al. (2008)](https://doi.org/10.1088/1742-5468/2008/10/P10008)* — "Fast unfolding of communities in large networks" — algoritmo Louvain para detección de comunidades en grafos de co-votación
- *[Poole & Rosenthal (1985)](https://doi.org/10.2307/1960888)* — "A Spatial Model for Legislative Roll Call Analysis" — método NOMINATE para posicionamiento ideológico de legisladores
- *Ainsley et al. (2020, APSR)* — umbral de 6 legisladores para solicitar votación nominal en México y sesgo de selección documentado
- *Constitución Política de los Estados Unidos Mexicanos* — Art. 135 (reformas constitucionales, 2/3 de presentes), Art. 72-C (veto presidencial, votos emitidos), Art. 63 (quórum, total de miembros)
