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

Morena baja de 83% a 68%. Sigue siendo el jugador dominante, pero ya no es todopoderoso. Y aquí viene el detalle que importa: el **PAN** se convierte en el aliado más valioso del tablero.

Morena tiene 263 curules. El PAN tiene 73. Juntos suman 336, que supera los 334 necesarios. Es la coalición mínima ganadora más pequeña posible. En cambio, Morena más PVEM da 327: no alcanza. El Verde necesita también al PT para llegar.

La paradoja política es fascinante. Matemáticamente, Morena necesita al PAN más que al PVEM o al PT. Pero políticamente, la coalición real es Morena + PVEM + PT: 263 + 64 + 49 = 376. Sobran 42 votos. Negocian con sus aliados naturales, no con el adversario más eficiente.

Y si subimos el umbral a 3/4 (375 de 500), la distribución se acentúa: Morena cae a **55.71%** por Shapley-Shubik. El PT y el PVEM suben a 10.71% cada uno. El PAN baja a 12.38%. Pero Morena nunca pierde la mayoría del poder, sin importar el umbral.

La **Reforma Judicial** confirma todo esto con datos concretos. En la votación general (VE04), el resultado fue 359 a favor, 135 en contra, 6 ausentes. Umbral: 334. Margen: 25 votos. El desglose por partido revela que los tres miembros de la coalición fueron críticos:

- Morena: 250 a favor, 0 en contra, 5 ausentes
- PT: 47 a favor, 0 en contra
- PVEM: 62 a favor, 0 en contra

Sin PVEM y sus 62 votos, Morena más PT llegaban a 297. Quedaban 37 corto del umbral. Sin PT y sus 47 votos, Morena más PVEM llegaban a 312, 22 corto. La votación particular (VE05) cuenta la misma historia: 357 a favor, 130 en contra, margen de 23 votos. Mismo patrón.

Esto matiza la hipótesis del caso cero que presentamos en el primer artículo. La asimetría de poder existe, pero es puntual: aparece solo en votaciones calificadas. En mayoría simple, Morena domina unilateralmente.

Pero hay un hallazgo que cambia la lectura completa. El **Artículo 135 de la Constitución** establece que las reformas constitucionales necesitan dos tercios de los "individuos presentes", no de las 500 curules. El umbral real es dinámico según la asistencia. Si hay 450 presentes, 2/3 son 300, no 334.

México usa bases de cálculo diferentes según el tipo de votación: presentes para reformas (Art. 135), votos emitidos para veto presidencial (Art. 72-C), y total de miembros para quórum (Art. 63). Dos votaciones del dataset (VE34 y VE41) parecían no alcanzar 2/3 sobre 500 (332 y 327 votos respectivamente), pero calculadas sobre los presentes sí pasan: 73.61% y 73.48%. El scraper tenía un bug aquí: calculaba mayoría simple para todas las votaciones sin distinguir el tipo. Ya está documentado.

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

La oposición existe como bloque de votación. La co-votación entre PAN y PRI es de 0.95; entre PAN y MC de 0.88. Votan juntos, sistemáticamente en contra de la coalición. Pero como fuerza negociadora, su capacidad de influir en resultados es nula. No pueden bloquear nada. No pueden aprobar nada. No pueden modificar nada.

Su papel es simbólico: votan en contra, dan declaraciones, ocupan tribuna. Pero matemáticamente, ningún resultado de las 199 votaciones habría cambiado si PAN, PRI y MC no hubieran asistido. Eso es un dato, no una opinión.

Las implicaciones para la calidad democrática son serias. Un Congreso donde un tercio de los legisladores no puede influir en ningún resultado no está funcionando como contrapeso. La oposición es espectadora con curul.

---

## Los disidentes de cartón

Si la oposición no existe y la disciplina es casi perfecta, ¿qué pasa con los que rompen filas? Los medios occasionalmente destacan a legisladores "rebeldes" dentro de Morena. Veamos qué dicen los datos.

El ranking de disidentes tiene una sorpresa: 4 de los 5 principales son de Morena. Pero cuando examinas los números, la narrativa se desmorona.

| Rank | Nombre | Partido | % Disidencia | Votaciones | Votos Disidentes |
|------|--------|---------|-------------|------------|-----------------|
| 1 | Ifigenia Martínez | Morena | 100.0% | 10 | 10 |
| 2 | Mónica Becerra | PAN | 61.5% | 52 | 32 |
| 3 | Patricia Armendáriz | Morena | 55.8% | 52 | 29 |
| 4 | Magaly Armenta | Morena | 55.8% | 52 | 29 |
| 5 | Napoleón Gómez Urrutia | Morena | 53.8% | 52 | 28 |

Ifigenia Martínez encabeza la lista con 100% de disidencia. Cien por ciento. Suena devastador. Pero solo participó en 10 de las 199 votaciones. Probablemente ausencia prolongada o llegada tardía al periodo legislativo, no rebeldía ideológica. Cuando tu N es 10, cualquier patrón es ruido.

Napoleón Gómez Urrutia, senador y líder del Sindicato Nacional de Trabajadores Mineros, disiente en 53.8% de las votaciones. Si lees el titular, parece un rebelde con causa. Pero sus votos disidentes caen consistentemente en votaciones que no son decisivas. La coalición tiene margen suficiente para absorber su disidencia sin que cambie un solo resultado.

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

Los datos que presentamos tienen limitaciones que vale la pena ser explícitos. Las 199 votaciones provienen de una legislatura en curso, no son el universo completo. No todas las votaciones del Congreso son nominales: se necesitan 6 legisladores para solicitar votación nominal, lo que introduce un sesgo hacia votaciones contentious donde alguien tuvo interés en registrar el voto individual. Los índices de poder formal como Shapley-Shubik se calculan sobre escaños, no sobre asistentes reales. Y todo este análisis cubre solo la Cámara de Diputados, no el Senado.

Nada de esto cambia la conclusión central. El observatorio del Congreso es un proyecto en curso. Los datos seguirán creciendo, los métodos se refinarán, y los patrones podrían cambiar. Pero con lo que tenemos hoy, el diagnóstico es claro: el poder legislativo en México está hiperconcentrado, la oposición es irrelevante como fuerza negociadora, y la disidencia interna no tiene impacto en resultados. Eso no es motivo de celebración. Es motivo de observación.

---

## Fuentes

- *Shapley, L.S. (1953)* — "A Value for n-Person Games" — método para calcular distribución de poder entre jugadores en juegos cooperativos
- *Blondel et al. (2008)* — "Fast unfolding of communities in large networks" — algoritmo Louvain para detección de comunidades en grafos de co-votación
- *Poole & Rosenthal (1985)* — "A Spatial Model for Legislative Roll Call Analysis" — método NOMINATE para posicionamiento ideológico de legisladores
- *Ainsley et al. (2020, APSR)* — umbral de 6 legisladores para solicitar votación nominal en México y sesgo de selección documentado
- *Constitución Política de los Estados Unidos Mexicanos* — Art. 135 (reformas constitucionales, 2/3 de presentes), Art. 72-C (veto presidencial, votos emitidos), Art. 63 (quórum, total de miembros)
