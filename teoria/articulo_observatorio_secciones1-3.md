## ¿Qué significa realmente tener mayoría en el Congreso?

Hay una pregunta que vuelta y vuelta aparece en el debate público cada vez que se aprueba una ley controversial en San Lázaro: ¿qué tan poderosa es realmente la mayoría? La respuesta que circula en conferencias de prensa y columnas de opinión suele ser una narrativa política. Los datos del Primer Periodo Ordinario de Sesiones de la LXVI Legislatura ofrecen otra cosa: una respuesta cuantitativa, y es incómoda.

Este artículo presenta los hallazgos del **Observatorio del Congreso de la Unión**, un proyecto que scrapea las votaciones nominales publicadas en el Sistema de Información de Tasas y Legislación (SITL), construye grafos de co-votación entre legisladores y calcula índices de poder formales. No es una encuesta. No es una opinión. Es lo que dicen los registros oficiales de votación.

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

PVEM y PAN votan como un bloque monolítico: 1.000 perfecto. Morena, con 263 legisladores — la bancada más grande — alcanza 0.9994. Y Movimiento Ciudadano, el partido que más se presenta como opción diferente, tiene la disciplina intra-partido más baja de todos: 0.9974. Es decir, sus diputados coinciden entre sí el **99.74% de las veces**. Si eso es "disidencia", el término necesita una redefine.

### Dos bloques, nada más

Cuando dejamos que el algoritmo Louvain agrupe a los legisladores solo por sus patrones de co-votación — sin decirle a qué partido pertenecen — detecta exactamente **2 comunidades**. No tres, no cuatro. Dos.

**Comunidad 1 (bloque coalición):**
- Morena: 263 legisladores
- PT: 49 legisladores
- PVEM: 64 legisladores
- **Total: 376 legisladores**

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

Morena concentra el **83.33% del poder formal** con solo el **50.87% de los escaños**. Los otros cinco partidos — aliados y opositores por igual — tienen exactamente el mismo poder: 3.33% cada uno.

La aritmética es simple: Morena tiene 263 escaños y el umbral es 251. Pasa sola. No necesita al PT, no necesita al PVEM, no necesita a nadie. Eso significa que en mayoría simple, PT y PVEM tienen el mismo poder de veto que PAN, PRI o MC: es decir, ninguno. Son irrelevantes para la aprobación de leyes ordinarias.

El **índice de Banzhaf** confirma el mismo patrón: Morena concentra el 86.11% del poder, y los cinco partidos restantes tienen 2.78% cada uno. Dos métodos distintos, misma conclusión.

### La narrativa que los datos desmienten

Se dice con frecuencia que "Morena necesita a sus aliados" para gobernar. Esto es cierto para reformas constitucionales — que requieren dos tercios —, y lo exploraremos en la siguiente sección. Pero para legislación ordinaria, la afirmación es falsa. Morena no necesita aliados; los aliados necesitan que Morena los necesite. Esa es una diferencia política enorme.

La concentración de poder en mayoría simple tiene una consecuencia directa: cualquier negociación entre el bloque coalición y el bloque oposición ocurre en términos de Morena. Los aliados (PT, PVEM) no son pivotes; los opositores (PAN, PRI, MC) no tienen palanca. El 83% del poder formal reside en una sola fuerza política, y los datos de co-votación confirman que esa fuerza política vota como bloque monolítico el 99.97% de las veces con sus aliados y el 99.94% de las veces internamente.

No es mayoría simple en el sentido técnico del término. Es mayoría simple en el sentido práctico: una sola fuerza decide, y las demás observan.
