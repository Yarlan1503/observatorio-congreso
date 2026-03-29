---
title: "Los datos contra la narrativa: poder, disciplina y el mito de la oposición en la LXVI Legislatura"
description: "199 votaciones, 98,322 votos y 567 legisladores revelan que Morena concentra 83% del poder en leyes ordinarias, la disciplina partidista es perfecta, y la oposición tiene 0% de poder empírico."
date: 2026-03-27
category: "investigaciones"
tags: ["congreso", "politica_mexicana", "teoria_de_grafos", "teoria_de_juegos", "shapley_shubik", "covotacion", "lxvi_legislatura", "reforma_judicial"]
published: true
---

## La mayoría que no parece

¿Qué significa realmente tener mayoría en el Congreso? La respuesta intuitiva dice algo como "gobernar por consenso", "negociar con aliados", "construir puentes". Los datos de la LXVI Legislatura cuentan otra historia.

En el artículo anterior presenté el Observatorio del Congreso: un sistema que raspó, limpió y estructuró cada votación nominal de la Cámara de Diputados. El observatorio ya existe, ya tiene datos, y ahora toca ver qué dicen. El dataset incluye 199 votaciones nominales, 98,322 votos individuales de 567 legisladores, distribuidos en 4 periodos legislativos con datos disponibles (1, 3, 5 y 6). No es una muestra. Es el universo de lo votado nominalmente en la legislatura completa.

La pregunta central parece simple: ¿cuánto poder tiene realmente cada partido? Pero las respuestas que arrojan los datos no lo son. Desmienten al menos tres narrativas que circulan en el debate público: que la disciplina de partido tiene matices, que los aliados de Morena tienen poder de negociación real, y que la oposición puede frenar algo. Las tres son falsas, y los números no dejan margen para interpretación generosa.

Lo que sigue no es opinión. Es lo que dicen 98,322 votos cuando los dejas hablar sin filtro.

---

## El mapa que nadie esperaba

Si hay algo que la cobertura del Congreso vende como verdad sagrada es la idea de que los partidos tienen facciones internas, que hay "alas" y "corrientes", que la disciplina es una aspiración pero no una realidad. Los datos dicen otra cosa. Y no con matices.

Para medir la disciplina construí una **matriz de co-votación normalizada**: para cada par de legisladores del mismo partido, calculé la fracción de votaciones donde ambos coincidieron (a favor, en contra o abstención), contando solo las votaciones donde ambos estuvieron presentes. El resultado es un número entre 0 y 1 que indica qué tan alineados están dos diputados.

Los números no dejan espacio para la narrativa del partido dividido. **Morena** registra una co-votación intra-partido de 0.9994. El **PT** llega a 0.9989. El **PVEM** y el **PAN** alcanzan 1.0000 — disciplina perfecta, sin un solo desaline. El **PRI** queda en 0.9989. Y luego está **Movimiento Ciudadano**, el partido que se vende como la opción diferente, la voz crítica, la alternativa. Su co-votación intra-partido es 0.9974. El más "disidente" de la Cámara coincide con sus compañeros el 99.74% de las veces.

Para ponerlo en perspectiva: si MC es el partido rebelde, el concepto de rebeldía legislativa en México necesita una redefinición urgente.

Pero la disciplina interna es solo la mitad de la historia. La otra mitad es cómo se relacionan los bloques entre sí. Aquí uso el algoritmo **Louvain** de detección de comunidades, que toma la red completa de co-votación y encuentra grupos de legisladores que votan más parecido entre sí que con el resto. No le digo cuántos grupos buscar. No le doy nombres de partidos. Solo le dejo la red.

Louvain detecta exactamente 2 comunidades. No 3, no 5, no 8. Dos.

La **Comunidad 1** —la coalición— agrupa a 372 legisladores: morenistas, petistas y pevemistas. La **Comunidad 2** —la oposición— reúne a 136: panistas, priistas y emecistas. Dentro de cada bloque la co-votación supera 0.99. La co-votación entre la coalición y la oposición es brutalmente baja: Morena y PAN coinciden en 0.3824 de las votaciones. Morena y PRI en 0.4530. Morena y MC en 0.4796.

La frontera entre los dos bloques está entre 0.38 y 0.48. Cuando un legislador morenista cruza votos con un panista, coinciden apenas 38% de las veces. Eso no es desacuerdo. Eso es vivir en planetas distintos.

Y dentro de la coalición, la co-votación Morena-PT-PVEM supera 0.999. No hay gradación, no hay puente, no hay legislador bisagra que conecte ambos mundos. El Congreso de la LXVI Legislatura no tiene espectro ideológico. Tiene un muro.

Quizá lo más revelador es que el algoritmo no detecta sub-bloques dentro de Morena. Con 255 legisladores votando, con corrientes internas documentadas, con líderes regionales con peso propio, Louvain no encuentra facciones. Más allá de lo que se vea en las notas políticas del día, el voto dice que Morena es un bloque monolítico.

---

## El poder (mal)entendido

Si el mapa de co-votación revela cómo votan, queda la pregunta que importa: ¿qué peso tiene ese voto? Tener 73 escaños o 29 no es lo mismo... o sí?

Para responder esto uso **índices de poder de votación**, herramientas de la teoría de juegos cooperativos que miden no cuántos escaños tienes, sino en qué fracción de las coaliciones ganadoras tu voto es decisivo. El más conocido es el **índice de Shapley-Shubik**: imagina todas las ordenaciones posibles de los partidos, y cuenta en cuántas de ellas un partido específico es el que convierte una coalición perdedora en ganadora al sumarse. El **índice de Banzhaf** hace algo similar con otra lógica de conteo. Ambos miden lo mismo desde ángulos distintos: poder real, no tamaño nominal.

Los resultados para mayoría simple (umbral de 251 de 500 votos) son contundentes:

| Partido | Escaños | % Nominal | Shapley-Shubik | Banzhaf |
|---------|---------|-----------|----------------|---------|
| Morena | 263 | 50.87% | 83.33% | 86.11% |
| PAN | 73 | 14.12% | 3.33% | 2.78% |
| PVEM | 64 | 12.38% | 3.33% | 2.78% |
| PT | 49 | 9.48% | 3.33% | 2.78% |
| PRI | 38 | 7.35% | 3.33% | 2.78% |
| MC | 29 | 5.61% | 3.33% | 2.78% |

*Los escaños reflejan la composición máxima por partido durante la legislatura, incluyendo rotaciones de suplentes. El total supera las 500 curules constitucionales.*

Morena concentra 83.33% del poder con 50.87% de los escaños. La explicación es aritmética y fría: con 263 curules, Morena supera sola el umbral de 251. No necesita al PT. No necesita al PVEM. No necesita a nadie. Morena PASA SOLA cualquier ley ordinaria.

Lo que sigue es contraintuitivo pero matemáticamente inexorable: PAN, PVEM, PT, PRI y MC valen exactamente lo mismo. Tener 73 escaños (PAN) o 29 (MC) da el mismo poder formal — 3.33% con Shapley-Shubik — cuando Morena ya cruza el umbral por sí sola. En un escenario donde un partido puede gobernar unilateralmente, todos los demás son intercambiables. Sus escaños no suman nada que Morena no tenga ya.

Esto contradice directamente la narrativa de que Morena "necesita" a sus aliados para gobernar. Para leyes ordinarias, es simplemente falso. Los aliados son relevantes para otro tipo de votaciones — las que requieren mayorías calificadas de dos tercios — pero eso es otro juego con otras reglas.

El poder legislativo no es proporcional a los escaños. Es discontinuo. Si pasas el umbral, todo tu excedente vale muchísimo más que cada escaño individual. Si no lo pasas, acumular curules de poco sirve. La LXVI Legislatura es un caso de libro de texto: un solo partido cruza la línea, y el poder se concentra en un solo punto del tablero.

Los datos dicen esto. La interpretación política de qué significa para la democracia mexicana — esa es otra conversación.

---

## La trampa de las mayorías calificadas

Hasta aquí la historia es simple: Morena pasa sola. Pero las leyes ordinarias no son todo. Las reformas constitucionales necesitan **mayoría calificada** de dos tercios: 334 de 500 votos. Y ahí la aritmética cambia.

La primer lección de la teoría de juegos cooperativos es que el poder no depende solo de cuántos escaños tienes, sino de cuántos necesitas y quién más los tiene. Con umbral de 2/3, los índices **Shapley-Shubik** se reacomodan:

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

La **Reforma Judicial** confirma todo esto con datos concretos. En la votación general (VE04), el resultado fue 359 a favor, 135 en contra, 6 ausentes. Umbral: 334. Margen: 25 votos. El desglose por partido revela que los tres miembros de la coalición fueron críticos:

- Morena: 250 a favor, 0 en contra, 5 ausentes
- PT: 47 a favor, 0 en contra
- PVEM: 62 a favor, 0 en contra

Sin PVEM y sus 62 votos, Morena más PT llegaban a 297. Quedaban 37 corto del umbral. Sin PT y sus 47 votos, Morena más PVEM llegaban a 312, 22 corto. La votación particular (VE05) cuenta la misma historia: 357 a favor, 130 en contra, 13 ausentes, margen de 23 votos. Mismo patrón.

Esto matiza la hipótesis del caso cero que presenté en el primer artículo. La asimetría de poder existe, pero es puntual: aparece solo en votaciones calificadas. En mayoría simple, Morena domina unilateralmente.

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

Primero, no cambia resultados. La coalición tiene márgenes de holgura suficientes en la mayoría de las votaciones calificadas (25 y 23 votos en las Reformas Judiciales), y en mayoría simple Morena pasa sola.

Segundo, no forma facciones. El algoritmo de Louvain no detecta sub-bloques dentro de Morena con 199 votaciones. Los "rebeldes" no votan juntos de forma sistemática que permita identificar una corriente interna. Son islas dispersas, no un archipiélago.

Tercero, incluso el disidente más extremo coincide con su partido más del 91% del tiempo en co-votación ponderada. Si alguien vota contigo 9 de cada 10 veces, no es tu opositor. Es tu compañero con desacuerdos puntuales.

Los disidentes existen. Los datos no mienten sobre eso. Pero su impacto en los resultados legislativos es indistinguible de cero.

---

## Lo que dicen los datos

El Congreso mexicano tiene un problema estructural. No es un problema de personas ni de partidos específicos. Es un problema de diseño: disciplina perfecta más oposición irrelevante igual a cero contrapesos reales.

Cuando un solo bloque puede aprobar leyes ordinarias unilateralmente, aprobar reformas constitucionales con sus aliados sin negociar con la oposición, y absorber la disidencia interna sin que afecte ningún resultado, el legislativo deja de ser un espacio de deliberación y se convierte en un sello automático. Los datos de 199 votaciones lo confirman sin ambigüedad.

Pero hay una buena noticia: el observatorio funciona. Con 199 votaciones nominales y 98,322 votos individuales de 567 legisladores, los patrones son claros, replicables y cuantificables. Podemos medir quién tiene poder, cuándo lo tiene, y cuándo no. El siguiente paso es **NOMINATE**, el método de Poole y Rosenthal que ubica a cada legislador en un espacio ideológico a partir de sus votos. Con 199 votaciones, el modelo es viable. Eso era la Fase 4 del roadmap, y ahora está desbloqueada.

También estamos explorando grafos dinámicos para observar cómo cambian las alianzas entre periodos legislativos. La co-votación es una fotografía estática; necesitamos el video.

Los datos que presentamos tienen limitaciones que vale la pena hacer explícitas. Las 199 votaciones provienen de una legislatura en curso, no son el universo completo. No todas las votaciones del Congreso son nominales: se necesitan 6 legisladores para solicitar votación nominal, lo que introduce un sesgo hacia votaciones contenciosas donde alguien tuvo interés en registrar el voto individual. Los índices de poder formal como Shapley-Shubik se calculan sobre escaños, no sobre asistentes reales. Y todo este análisis cubre solo la Cámara de Diputados, no el Senado.

Nada de esto cambia la conclusión central. El observatorio del Congreso es un proyecto en curso. Los datos seguirán creciendo, los métodos se refinarán, y los patrones podrían cambiar. Pero con lo que tenemos hoy, el diagnóstico es claro: el poder legislativo en México está hiperconcentrado, la oposición es irrelevante como fuerza negociadora, y la disidencia interna no tiene impacto en resultados. Eso no es motivo de celebración. Es motivo de observación.

---

## Fuentes

- *Shapley, L.S. (1953)* — "A Value for n-Person Games" — método para calcular distribución de poder entre jugadores en juegos cooperativos
- *Blondel et al. (2008)* — "Fast unfolding of communities in large networks" — algoritmo Louvain para detección de comunidades en grafos de co-votación
- *Poole & Rosenthal (1985)* — "A Spatial Model for Legislative Roll Call Analysis" — método NOMINATE para posicionamiento ideológico de legisladores
- *Ainsley et al. (2020, APSR)* — umbral de 6 legisladores para solicitar votación nominal en México y sesgo de selección documentado
- *Constitución Política de los Estados Unidos Mexicanos* — Art. 135 (reformas constitucionales, 2/3 de presentes), Art. 72-C (veto presidencial, votos emitidos), Art. 63 (quórum, total de miembros)
