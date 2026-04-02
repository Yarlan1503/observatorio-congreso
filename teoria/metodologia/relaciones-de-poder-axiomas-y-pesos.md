# RelacionPoder como Inferencia Ponderada sobre Axiomas de Relación

**Fecha**: 2026-03-27  
**Versión**: v0.1  
**Etiqueta**: Notas de trabajo — Observatorio Congreso  

---

## 1. Planteamiento del problema

RelacionPoder no se detecta directamente. No hay una tabla, una API ni una fuente pública que diga "esta persona tiene poder sobre esta otra". Las relaciones de poder en un congreso son informales: se negocian en pasillos, se ejercen a través de whips, se construyen con favores acumulados y se rompen sin aviso. No hay campo `power_relationship = TRUE` en ninguna base de datos.

Lo que sí tenemos son datos estructurados: quién pertenece a qué partido, quién votó qué en cada votación, quién representa qué estado. Esos datosPopolo son públicos y verificables. La pregunta es: ¿se puede inferir una relación de poder a partir de esos datos estructurales?

La respuesta es sí, pero parcialmente. No es un problema de clasificación (¿existe o no la relación?) sino de inferencia ponderada (¿cuánto peso tiene la relación entre estas dos personas y qué tan diferente es de lo que esperaríamos solo por su afiliación formal?). El problema es **supervisable parcialmente**: tenemos algunos ground truth (relaciones documentadas por periodismo) pero no suficientes para entrenar un modelo supervisado completo.

La estrategia: definir **axiomas de relación base** que capturan los factores observables, estimar sus pesos con ML, y analizar el residuo de la predicción. El residuo es donde viven las relaciones de poder informales.

---

## 2. Los tres axiomas base

### Axioma 1 — Co-membership

Dos `Person` en la misma `Organization` (partido, bancada, comisión) tienen una relación formal.

El peso no es binario (mismo partido = 1). Es una función del **tiempo compartido**: cuánto tiempo ambos fueron miembros simultáneamente de la misma organización. Un diputado que estuvo en PAN durante toda la LXIV Legislatura y otro que se afilió a mitad de término comparten menos tiempo que dos que llegaron juntos.

```
co_membership(A, B) = |{ t : A ∈ Org(t) ∧ B ∈ Org(t) }| / T
```

Donde T es el período total observado. El valor normalizado va de 0 (nunca compartieron) a 1 (siempre estuvieron juntos).

Esto captura **disciplina formal**: miembros del mismo partido tienden a votar igual porque el whip lo exige. Es el predictor más obvio y el más ruidoso.

### Axioma 2 — Co-votación

Dos `Person` que votan igual en un `VoteEvent` incrementan su peso. La métrica es el **índice de acuerdo**: la proporción de votaciones donde ambos emitieron el mismo voto (a favor/en contra/abstención).

```
co_votacion(A, B) = |{ v : vote(A,v) = vote(B,v) }| / |{ v : ambos votaron en v }|
```

Esto es esencialmente el **Rice index invertido**. El Rice clásico mide cohesión de un bloque; aquí lo usamos como similitud de par. Un valor alto (digamos 0.85+) indica que A y B votan consistentemente igual. Un valor cercano a 0.5 significa que sus votos son esencialmente independientes.

Esto captura **afinidad legislativa real** — no solo lo que el partido les ordena, sino lo que efectivamente hacen. Es el axioma más informativo, pero también el más peligroso (ver sección 5).

### Axioma 3 — Co-área

Dos `Person` que representan la misma `Area` (estado o distrito) tienen una relación territorial.

```
co_area(A, B) = 1 si area(A) = area(B), 0 en caso contrario
```

Es el axioma más simple y el más débil. Captura **factor territorial**: legisladores del mismo estado tienden a coordinarse en ciertas votaciones (asignaciones presupuestales, obras, políticas regionales). Coaliciones interestatales (ej. el bloque norteño) son un ejemplo de afinidad territorial que va más allá del partido.

En la práctica, co-area es una señal débil por sí sola pero útil como variable de control: si dos diputados de Veracruz votan igual, parte de eso se explica porque son de Veracruz, no porque tengan una relación de poder personal.

---

## 3. Modelo formal

La hipótesis central es que la relación observada entre dos legisladores se puede descomponer en la contribución de los tres axiomas más un residuo:

```
Peso_total(A, B) = w₁·co_membership(A,B) + w₂·co_votacion(A,B) + w₃·co_area(A,B) + ε
```

Donde:
- **w₁, w₂, w₃** son pesos estimados por ML (no son fijos ni se asignan a mano)
- **ε (residuo)** es la diferencia entre la relación observada y lo que el modelo predice a partir de los axiomas

**ε es el concepto más importante de este documento.** Todo lo que no explican los tres axiomas queda ahí: relaciones personales, lealtades a actores externos, favores políticos, chantaje, alianzas familiares. Si el modelo predice que A y B deberían tener un peso de 0.3 (porque son de partidos distintos y estados distintos) pero su co-votación real es 0.8, entonces ε = +0.5. Ese residuo positivo sistemático es una **señal** de que hay algo más entre A y B que los axiomas no capturan.

Los pesos w no son constantes. Cambian con el tiempo (las dinámicas legislativas evolucionan) y dependen del tipo de votación (en votaciones de política económica puede pesar más w₂ que en votaciones de procedimiento, donde w₁ domina por disciplina).

---

## 4. La trampa de la independencia

La co-votación NO es independiente de la co-membership. Esto es obvio en la práctica (miembros del mismo partido votan igual porque el whip lo exige) pero fácil de olvidar en el modelo.

Si no se controla esta dependencia, w₂ absorbe el efecto de w₁: el modelo dirá "la co-votación importa muchísimo" cuando en realidad lo que está midiendo es disciplina partidaria. El residuo ε pierde poder explicativo porque ya no separa lo que es afínidad genuina de lo que es efecto de pertenecer al mismo bloque.

Este es un **problema conocido en congressional voting literature**. Poole & Rosenthal lo documentaron extensivamente en su trabajo sobre NOMINATE: la mayor parte de la varianza en votaciones del Congreso de EUA se explica por un solo eje (partidario), y la señal de afinidad cruzada es residual y pequeña.

La solución: el modelo debe descomponer la varianza correctamente. Hay dos caminos:

1. **Regresión jerárquica**: primero ajustar w₁ (co-membership), luego ver cuánta varianza de co-votación queda sin explicar después de controlar por partido. Esa varianza residual es la co-votación "limpia".

2. **Factores latentes**: en lugar de usar co-votación directamente, extraer dimensiones latentes de la matriz de votos (NMF, SVD) y usar esas dimensiones como features. La primera dimensión captura el eje partidario; las dimensiones subsiguientes capturan afinidades cruzadas.

Ambos caminos llevan al mismo objetivo: que w₂ mida afinidad real, no redundancia con w₁.

---

## 5. Escalado por fase

El observatorio tiene una ruta de fases escalonada. El modelo de pesos también:

### Fase temprana (5-10 votaciones)

**Modelo**: regresión lineal con features de interacción (w₁w₂, w₁w₃, w₂w₃).

Con tan pocas votaciones, no hay datos suficientes para separar efectos limpiamente. El modelo da una primera aproximación, pero w₂ estará contaminado por w₁ (la trampa de la independencia en toda su gloria).

Lo que sí se puede hacer: calcular el índice de Rice por par, identificar outliers (pares que votan igual pero no deberían según sus afiliaciones), y usar esos outliers como hipótesis de investigación manual.

### Fase media (30+ votaciones)

**Modelo**: factores latentes (NMF o SVD sobre la matriz de co-votación).

Con 30+ votaciones, la matriz de votos persona×votación empieza a tener estructura. SVD/NMF descompone esa matriz en dimensiones ocultas: la primera dimensión captura el eje partidario, la segunda puede capturar un eje regional, la tercera puede capturar corrientes internas de un partido, etc.

Las dimensiones 2+ son la señal limpia de afinidad cruzada. Se pueden usar directamente como features del modelo en lugar de co-votación cruda, evitando la trampa de la independencia.

### Fase avanzada (100+ votaciones)

**Modelo**: Graph Neural Networks (GNN).

Con 100+ votaciones, el grafo completo del Congreso tiene suficiente densidad para GNNs. Nodos = `Person`, aristas = `Membership` (a organizaciones) y `Vote` (a votaciones). Los edge weights se aprenden con message passing.

La ventaja clave de las GNN: capturan **relaciones indirectas**. Si A y B nunca votaron juntos (quizás uno falta frecuentemente), pero ambos son cercanos a C, el message passing propaga esa señal: A-C-B forma un camino que el modelo puede detectar. Esto es imposible con regresión o factores latentes, que solo ven pares directos.

---

## 6. Ejemplo: caso cero y Braña Mojica

El caso cero del observatorio fue la votación de la Reforma Electoral. Braña Mojica (diputado PVEM) votó consistentemente con Morena en la votación clave — no fue un voto aislado, sino un patrón de alineación sostenida.

¿Qué diría el modelo?

- **co_membership(Braña, Morena)** = baja. PVEM es un partido pequeño (poquísimos diputados), así que el tiempo compartido con cualquier diputado de Morena es cero (no comparten organización). El axioma 1 prácticamente no contribuye.
- **co_votacion(Braña, bancada Morena)** = alta. Si calculamos el índice de acuerdo entre Braña y el promedio de la bancada de Morena, obtendríamos un valor significativamente mayor al que se esperaría por azar.
- **co_area(Braña, diputados clave)** = depende. Braña representa un distrito específico; si los diputados de Morena con los que más coincide son de estados distintos, este axioma no explica nada.
- **ε = alto y positivo**. El modelo predice una co-votación baja (partidos distintos, estados distintos), pero la observada es alta. El residuo grande y sistemático es una **señal de ActorExterno**: hay un actor que no aparece en los axiomas (no es un partido, no es un estado, no es una votación) que está alineando a Braña con Morena.

Ese actor es Villarreal. Pero el modelo no dice quién es — solo dice que *algo* falta. La conexión con el documento hermano sobre detección de actores externos (`deteccion-actores-externos-clustering-residuos.md`) es directa: el clustering sobre residuos positivos agrupa a legisladores que comparten un ActorExterno latente, y luego la investigación manual identifica quién.

---

## 7. Sistema híbrido

RelacionPoder tiene dos fuentes que se retroalimentan:

### Fuente manual

Relaciones documentadas con investigación periodística. Ejemplos del caso cero: Villarreal → PVEM (alinea al partido verde con Morena), Salgado → disidentes de Morena (coordina a legisladores que rompen disciplina).

- **Confianza**: alta. Son relaciones verificadas con fuentes.
- **Cobertura**: baja. Solo cubren los casos que alguien investigó y documentó.
- **Formato**: la tabla `relacion_poder` en el esquema SQLite, con `source_type = 'manual'`.

### Fuente inferida (ML)

Relaciones inferidas por el modelo de pesos. Un residuo ε alto y sistemático entre A y B es una hipótesis de relación no documentada.

- **Confianza**: baja individualmente. Un residuo alto puede tener muchas explicaciones.
- **Cobertura**: alta. Se calcula para todos los pares de legisladores, no solo los investigados.
- **Formato**: misma tabla `relacion_poder`, con `source_type = 'inferred'` y un campo de score de confianza.

### Retroalimentación

Las dos fuentes se retroalimentan:

1. **Manual → ML**: Las relaciones manuales sirven como ground truth para calibrar el modelo. Si el modelo predice residuo alto para (Braña, Villarreal) y la investigación confirma que Villarreal influye sobre PVEM, eso valida la señal. Se usa para ajustar los pesos w y mejorar la precisión del ε.

2. **ML → Manual**: El modelo señala dónde buscar. Si el clustering de residuos identifica un grupo de 5 diputados que votan igual más de lo esperado y no comparten partido ni estado, eso es un punto de partida para investigación periodística. El modelo no dice *quién* es el actor externo, pero dice *dónde* buscar.

Esto es un sistema de **bucle semi-supervisado**: pocas etiquetas manuales de alta calidad + muchas predicciones de baja calidad → el modelo usa las etiquetas para calibrar → las predicciones calibradas generan nuevas etiquetas → repetir.

---

## 8. Pipeline completo

La arquitectura de inference del observatorio para RelacionPoder:

```
Datos Popolo (SQLite)
    ↓
Extraer features de los 3 axiomas
    ↓
Modelo ML (fase-dependiente: regresión → NMF/SVD → GNN)
    ↓
Calcular ε (residuo) para cada par (A, B)
    ↓
Clustering sobre residuos → comunidades inexplicadas
    ↓
Hipótesis de ActorExterno latente
    ↓
Validación cruzada con RelacionPoder manual
    ↓
Nuevas relaciones manuales → recalibrar modelo → loop
```

---

## Referencias rápidas

- **Popolo standard**: https://www.popoloproject.com/ — esquema base del observatorio. Tabla `Vote` (legislador × votación × opción) como activo principal.
- **Poole & Rosenthal, NOMINATE**: método de escalado ideológico del Congreso de EUA. Demuestra que la mayor parte de la varianza de votación se explica por un eje partidario único. Referencia teórica para la trampa de la independencia.
- **Rice index**: medida clásica de cohesión de votación en ciencias políticas. Proporción de miembros de un bloque que votan igual en una votación dada. Aquí usamos la versión invertida (por par, no por bloque).
- **Documento hermano**: [deteccion-actores-externos-clustering-residuos.md](deteccion-actores-externos-clustering-residuos.md) — cómo convertir los residuos ε en hipótesis de actores externos mediante clustering.
