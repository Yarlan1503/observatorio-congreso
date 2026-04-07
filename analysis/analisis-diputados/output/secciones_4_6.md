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

Morena fue crítica en 50 de 52 votaciones (96.15%). PT y PVEM fueron críticos en 12 cada uno (23.08%) --- siempre en las mismas votaciones calificadas donde la coalición entera era necesaria. PAN, PRI y MC: cero. Nunca estuvieron en posición de cambiar un resultado.

La oposición no fue una fuerza negociadora. En ninguna de las 54 votaciones nominales su voto habría alterado el resultado final. Su poder empírico es literalmente cero.


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

Cuatro de los cinco principales disidentes son de Morena, el partido con más escaños. Napoleón Gómez Urrutia --- senador y líder histórica del Sindicato Nacional de Trabajadores de la Educación --- disiente en el 53.8% de las votaciones. Si uno lee el titular sin contexto, parece un rebelde.

### La trampa del porcentaje

Ifigenia Martínez aparece con 100% de disidencia. Pero participó en apenas 10 de 52 votaciones. Probablemente por ausencia prolongada o llegada tardía al periodo legislativo, no por rebeldía ideológica. Un porcentaje sobre 10 observaciones no es comparable a uno sobre 52.

Mónica Becerra Moreno (PAN) disiente en el 61.5% de las votaciones. Pero --- y aquí está la clave --- la co-votación intra-PAN es 1.000 perfecta. ¿Cómo puede alguien disentir el 61.5% dentro de un partido que vota como bloque monolítico?

La respuesta está en la metodología. "Disidencia" aquí significa votar diferente a la mayoría del partido en una votación específica. Si el PAN vota unánimemente a favor en 30 votaciones y Becerra Moreno vota en contra en 32, su disidencia es alta. Pero la co-votación se calcula normalizada por frecuencia: si ella coincide con su partido en las votaciones donde el partido es relevante, su co-votación ponderada sigue siendo alta. Son métricas que capturan cosas distintas.

### Ruido, no señal

La disidencia en esta legislatura es ruido estadístico, no señal política. No cambia resultados (la coalición tiene margen suficiente en todas las votaciones calificadas), no forma facciones discernibles (el análisis de grafos no detecta sub-bloques dentro de Morena), y no amenaza la disciplina del bloque. Los "rebeldes" votan diferente en votaciones que no son decisivas.

### Limitaciones del análisis

Esto se basa en 54 votaciones nominales de un solo periodo ordinario. No todas las votaciones del pleno son nominales: se necesitan 6 legisladores para solicitar una votación nominal (Ainsley et al. 2020), lo que introduce un sesgo de selección hacia votaciones políticamente relevantes o contentious. Las votaciones por cédula o económicas quedan fuera. Además, un solo periodo no captura la dinámica completa de la legislatura. Los patrones pueden cambiar en periodos subsiguientes.
