# Detección de ActorExterno Faltante: Clustering sobre Residuos del Modelo de Pesos

**Fecha**: 2026-03-27  
**Versión**: v0.1  
**Etiqueta**: Notas de trabajo — Observatorio Congreso  

**Documento hermano**: [relaciones-de-poder-axiomas-y-pesos.md](relaciones-de-poder-axiomas-y-pesos.md) — Este documento consume la salida de ese modelo (específicamente el residuo ε).

---

## 1. El problema: influencias invisibles

Hay influencias en el Congreso que no aparecen en ninguna base de datos. El caso cero lo demostró: Alejandro Villarreal, Rocío Nahle y Ana María Pavlovich movieron votaciones sin ser legisladores. No tienen un asiento. No tienen un partido. No aparecen en el registro oficial. Y sin embargo, 12 diputados del PVEM votaron a favor de la Reforma Electoral contra la línea de su propio partido — y la investigación posterior atribuyó esa disidencia a la presión de estos tres actores.

El esquema Popolo no tiene un nodo natural para ellos. Son `Person` en un sentido amplio, pero no son legisladores — no tienen `Membership` ni `Post` en ninguna `Organization` del Congreso. Por eso creamos `actor_externo` como tercera extensión del esquema (tabla `actor_externo` en SQLite, junto con `relacion_poder` y `evento_politico`). Hoy tenemos 16 actores externos pre-poblados.

Pero el problema real no es registrar a Villarreal. El problema es: ¿cómo detectamos a los que *no conocemos*? ¿Cómo sabemos que algo está ahí sin saber qué es?

Esa es la pregunta que este documento atiende.

---

## 2. Pipeline completo

```
Axiomas → Pesos (ML) → Residuos (ε) → Clustering → Comunidades inexplicadas → ActorExterno latente → Validación manual
```

### Paso a paso

1. **Axiomas**: Definimos tres fuentes observables de relación entre legisladores — co-membership (misma party), co-votación (votaron igual), co-área (misma comisión/estado). Estas son las variables que el esquema Popolo captura directamente.

2. **Pesos (ML)**: Entrenamos un modelo (regresión o similar) que estima la similitud esperada de co-votación entre cada par (A, B) a partir de los tres axiomas. El modelo produce `Peso_total(A,B) = w₁·co_membership + w₂·co_votacion + w₃·co_area`. Este paso está documentado en el documento hermano.

3. **Residuos (ε)**: Para cada par (A, B), calculamos la diferencia entre lo que el modelo predice y lo que observamos en realidad. Si A y B votan *más parecido* de lo que partido + estado + comisión predicen, el residuo es positivo. Si votan *menos parecido*, es negativo. El residuo es la señal limpia — lo que queda después de controlar por lo que ya conocemos.

4. **Clustering**: Agrupamos legisladores en el espacio de residuos. No en el espacio de votos brutos, sino en el espacio de *lo que los votos tienen de inexplicable*. Los clusters que emergen son grupos de legisladores que votan más parecido entre sí de lo que deberían según los axiomas.

5. **Comunidades inexplicadas**: Cada cluster se evalúa: ¿se explica por relaciones de poder ya documentadas en `relacion_poder`? Si sí, no es nuevo. Si no, es una comunidad inexplicable — un candidato a ActorExterno latente.

6. **ActorExterno latente**: El cluster no nos dice *quién* es el actor externo. Nos dice *que existe* y *dónde actúa*: estos N legisladores, en este rango de fechas, responden a algo que no está en el modelo.

7. **Validación manual**: Investigación periodística, documental o de campo para identificar al actor. El modelo señala el dónde; la investigación humana identifica el quién. Esto siempre requiere trabajo humano.

---

## 3. Por qué residuos, no grafo bruto

Esta es la distinción metodológica más importante de todo el pipeline.

**Clustering en el grafo de co-votación bruto** detecta patrones que ya conocemos. Si haces community detection sobre quién vota igual que quién, obtienes clusters que se corresponden casi perfectamente con partidos y bancadas. "Estos 200 votan igual" — sí, porque son de Morena. "Estos 40 votan igual" — sí, porque son del PAN. Eso es ruido ya conocido. No aporta información nueva sobre quién influye sobre quién.

**Clustering en el espacio de residuos** detecta algo distinto: grupos de legisladores que votan igual *incluso después de controlar por partido, estado y bancada*. Si dos diputados de partidos distintos, de estados distintos, de comisiones distintas, votan sistemáticamente igual *más de lo que el modelo predice*, hay algo ahí. Algo que no capturan los tres axiomas.

La analogía es directa: es como restar la tendencia macro de una serie temporal para ver la señal real. Los votos brutos son la serie temporal con tendencia. Los residuos son la señal limpia, sin la tendencia que ya entendemos.

En términos prácticos: un residuo sistemáticamente positivo entre el diputado A (Morena, Veracruz) y el diputado B (PAN, Jalisco) después de controlar por todos los axiomas dice "estos dos votan más parecido de lo que deberían — hay un factor común que no estamos capturando". Ese factor común es lo que buscamos.

---

## 4. Las 4 cosas que se pueden saber sin saber quién es

El modelo no identifica al actor externo. Pero sí da cuatro tipos de información accionable:

### 4.1 Delimitar el cluster

Quiénes están en el grupo. Si 5 diputados forman un cluster tight en el espacio de residuos, sabemos que esos 5 responden a la misma influencia (o a algo lo suficientemente similar como para agruparlos). Esto reduce el espacio de búsqueda de "500 legisladores" a "estos 5".

### 4.2 Estimar intensidad

Magnitud del residuo promedio del cluster. Un cluster con residuo promedio de +0.3 indica una influencia moderada — votan algo más parecido de lo esperado. Un cluster con +0.8 indica una influencia fuerte — votan mucho más parecido de lo esperado. Esto permite priorizar: primero investigar los clusters de mayor magnitud.

### 4.3 Ubicación temporal

El residuo se activa en fechas específicas. Si el cluster de 5 diputados tiene residuos cercanos a cero en las primeras 20 votaciones y luego salta a +0.6 en la votación 21, algo cambió. Permite situar temporalmente el evento político: una elección interna de partido, un cambio de liderazgo, un escándalo, una negociación presupuestal. La ventana temporal reduce aún más la búsqueda.

### 4.4 Validación cruzada

Cruzar con la tabla `relacion_poder` existente. Si las relaciones ya documentadas explican el cluster (ej., los 5 ya tienen RelacionPoder entre sí o con un actor externo conocido), el cluster no es nuevo. Si no se explican, es un hallazgo genuino — un punto de partida para investigación.

---

## 5. Técnicas de clustering por fase

No hay una técnica universal. La elección depende de cuántos datos tengamos.

### Fase temprana (5-10 votaciones)

**Hierarchical clustering** con distancia euclideana en el espacio de residuos.

- Construyes un dendrograma y decides dónde cortar.
- Ventaja: no requiere definir el número de clusters a priori. El dendrograma te muestra la estructura jerárquica natural de los datos.
- Desventaja: sensible a outliers. Con pocos datos, un par de votaciones atípicas puede dominar la estructura. Los residuos con 5 votaciones son ruidosos — hay que interpretar con cautela.

### Fase media (30+ votaciones)

**DBSCAN** (Density-Based Spatial Clustering of Applications with Noise).

- Agrupa puntos que están densamente packed y marca el resto como ruido (outliers).
- Ventaja: no asume forma esférica como k-means. Detecta clusters de forma arbitraria. Maneja ruido naturalmente — un legislador que no pertenece a ningún grupo influyente queda clasificado como outlier, no forzado a un cluster.
- Desventaja: requiere tuning de dos hiperparámetros — `eps` (radio de vecindad) y `min_samples` (mínimo de puntos para formar un cluster). El tuning depende del dominio; no hay valores universales.
- En la práctica: con 30-50 votaciones, DBSCAN es probablemente la mejor opción. Suficientes datos para que los residuos sean estables, y suficiente ruido legislativo natural para que la detección de densidad tenga sentido.

### Fase avanzada (100+ votaciones)

**GNN embedding + clustering**.

- Entrenas un Graph Neural Network sobre el grafo de co-votación. El GNN produce un embedding (vector) por legislador que captura patrones de votación complejos, incluyendo relaciones indirectas (A influye en B que influye en C).
- Luego clusterizas en el espacio de embeddings con DBSCAN o hierarchical clustering.
- Ventaja: captura la estructura relacional completa del Congreso, no solo pares aislados. Un GNN puede detectar que A y C están relacionados aunque nunca votaron igual directamente — porque ambos están conectados a B de forma similar.
- Desventaja: requiere muchos datos (100+ votaciones como mínimo para que el GNN generalice), cómputo significativo, y tuning de arquitectura. No es viable en las fases tempranas del observatorio.

### Resumen rápido

| Fase | Datos | Técnica | Por qué |
|------|-------|---------|---------|
| Temprana | 5-10 votaciones | Hierarchical clustering | Sin asumir k; interpretable visualmente |
| Media | 30+ votaciones | DBSCAN | Detecta forma arbitraria; maneja ruido |
| Avanzada | 100+ votaciones | GNN embedding + clustering | Captura relaciones indirectas |

---

## 6. Ejemplo hipotético

Imagina que después de 40 votaciones, DBSCAN identifica un cluster de 5 diputados con residuo promedio de +0.55:

| Diputado | Partido | Estado | Comisión principal |
|----------|---------|--------|-------------------|
| García López | PAN | Chihuahua | Hacienda |
| Martínez Ríos | PRI | Oaxaca | Energía |
| Hernández Ruiz | Morena | Puebla | Seguridad |
| Torres Medina | Movimiento Ciudadano | Nuevo León | Economía |
| Castro Flores | PAN | Tabasco | Justicia |

Cinco diputados, cuatro estados distintos, tres partidos distintos, cuatro comisiones distintas. Los tres axiomas del modelo predicen que su co-votación debería ser baja — no hay razón estructural para que voten igual. Y sin embargo, sus residuos son positivos y sistemáticos.

El modelo no dice quién los une. Dice: *hay algo* que hace que estos cinco voten más parecido de lo esperado, y ese algo no está capturado por partido, estado ni comisión.

El residuo se activa a partir de la votación 28 (después de las elecciones internas de febrero de 2026). La ubicación temporal apunta a un evento político en esa ventana.

La validación cruzada con `relacion_poder` no muestra relaciones documentadas entre los cinco ni con un actor externo común. Es un hallazgo genuino.

**Qué haces con esto**: la investigación manual empieza por revisar qué compartieron estos cinco legisladores entre febrero y la fecha actual. ¿Coinciden en alguna coalición? ¿Alguien los presionó sobre un tema específico (reforma energética, presupuesto, justicia)? ¿Tienen un donante común? ¿Alguien de su equipo compartió información con el equipo de otro? El modelo no responde estas preguntas — pero reduce el espacio de búsqueda de "todo el Congreso" a "estos 5 diputados en esta ventana temporal". Eso ya es un punto de partida concreto.

---

## 7. Limitaciones

Sin adornos:

1. **No identifica al actor externo**. Solo señala su existencia y localización aproximada. La identificación siempre requiere investigación manual (periodística, documental, de campo). El modelo es un detector de anomalías, no un oráculo.

2. **Requiere un mínimo de votaciones**. Con menos de 5-10 votaciones, los residuos son estadísticamente ruido. Un par de coincidencias en votación no significan nada. Necesitas suficiente densidad temporal para que el patrón sea robusto.

3. **Confunde influencia externa con afinidad ideológica genuina**. Dos legisladores pueden votar igual por convicción compartida, no porque un actor externo los presione. Un diputado progresista de Morena y un diputado progresista de Movimiento Ciudadano pueden coincidir en temas de derechos humanos por convicción, no por lobby. La validación manual es obligatoria — el modelo genera hipótesis, no conclusiones.

4. **Relación N:N entre actores y clusters**. Un solo ActorExterno puede generar múltiples clusters (si su influencia se ejerce de forma diferente sobre subgrupos distintos del Congreso). Inversamente, múltiples actores externos pueden crear un solo cluster superpuesto (si sus esferas de influencia coinciden parcialmente). La correspondencia entre clusters y actores externos no es 1:1.

5. **Depende de la calidad de los axiomas**. Si los tres axiomas (co-membership, co-votación, co-área) son incompletos — si hay una variable observable importante que no estamos capturando (ej., coincidencia en generación de legisladores, o coincidencia en alumnado de la misma universidad) — los residuos absorberán esa señal y la confundirán con influencia externa. Cuanto mejores los axiomas, más limpios los residuos.

---

## 8. Conexión con el caso cero

Los 12 disidentes del PVEM que votaron a favor de la Reforma Electoral son un cluster natural en el espacio de residuos.

Piensa en lo que el modelo habría detectado si se hubiera corrido *antes* de la investigación periodística:

- **Co-membership**: Los 12 son del mismo partido (PVEM). El axioma predice alta co-votación entre ellos.
- **Co-votación observada**: En la Reforma Electoral, los 12 votaron a favor. Pero el resto del PVEM votó en contra.
- **Residuo**: Los 12 tienen un residuo *negativo* respecto al resto de su partido (votaron distinto a lo que co-membership PVEM predice), pero un residuo *positivo entre sí* (votaron igual entre ellos, contra la línea).
- **Clustering**: DBSCAN los agrupa como un cluster separado del bloque principal del PVEM.
- **Resultado**: "12 diputados del PVEM votan sistemáticamente distinto a su partido en votaciones clave — hay un factor no capturado por co-membership que los une".

Ese factor, como se descubrió después, era la presión de Villarreal y otros actores externos. El modelo habría señalado la anomalía *antes* de saber quién estaba detrás. Habría dado un punto de partida concreto: investigar qué une a estos 12 diputados.

Este es el caso de validación más fuerte del pipeline. No es hipotético — es exactamente el patrón que el caso cero produjo. El pipeline retrospectivo reproduce el hallazgo.

---

## 9. Referencias rápidas

- **DBSCAN**: Ester, M., Kriegel, H.-P., Sander, J., & Xu, X. (1996). "A Density-Based Algorithm for Discovering Clusters in Large Spatial Databases with Noise." KDD '96.
- **GNNs para legislaturas**: Trojan, A., et al. (2022). "Representation Learning for Legislative Voting." COMSOC.
- **Community detection en redes legislativas**: Porter, M.A., et al. (2007). "Communities in Networks." Notices of the AMS.
- **Residuos como señal**: La analogía con detrended series temporales es estándar en econometría (Box-Jenkins). Aplicada a co-votación por diversos trabajos de political science computacional.
- **Esquema Popolo**: [popoloproject.com](http://popoloproject.com) — estándar abierto para datos legislativos.
- **Caso cero**: Documentado en `Disidentes PVEM.md` y `Conclusiones Reforma Electoral.md` en este repositorio.

---

*Última actualización: 2026-03-27. Documento de trabajo — sujeto a revisión conforme se implemente el pipeline.*
