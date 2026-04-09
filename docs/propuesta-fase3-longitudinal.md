# Propuesta: Fase 3 — Análisis Longitudinal
## Observatorio del Congreso
### Fecha: 2026-04-09

---

## 1. Visión General

La Fase 3 extiende el análisis del Observatorio de cortes transversales (una legislatura) a un enfoque longitudinal (7 legislaturas, LX–LXVI). Aprovecha los datos de 9,385 votaciones emitidas (VEs), 2.6M de votos y 4,840 legisladores únicos para responder preguntas sobre evolución ideológica, disciplina partidista, brecha de género y efecto del tipo de curul. Los 4 análisis están diseñados para ejecutarse con los datos existentes — no requieren scraping adicional.

| # | Análisis | Pregunta central | Esfuerzo | Cómputo |
|---|----------|-----------------|----------|---------|
| 1 | Trayectorias Individuales | ¿Cómo cambian los legisladores entre legislaturas? | 15h | ~45min |
| 2 | Evolución de Partidos | ¿Cómo evoluciona la disciplina y cohesión partidista? | 14h | ~45min |
| 3 | Efecto Género | ¿Existe una brecha de disciplina por género? | 16h | ~55min |
| 4 | Efecto curul_tipo | ¿Los plurinominales son más disciplinados? | 14h | ~40min |

**Esfuerzo total**: 59h de desarrollo + ~3h de cómputo. 4 scripts nuevos (~1,600 líneas). Timeline: 7–8 días de trabajo concentrado.

---

## 2. Estado de datos (por qué estamos listos)

La BD está limpia y lista para análisis longitudinal. Datos post-dedup, post-backfill, con 68/68 tests passing.

### Coverage por legislatura (Diputados)

| Legislatura | Periodo | VEs | Personas | Nota |
|-------------|---------|-----|----------|------|
| LX | 2006-2009 | ~700 | ~560 | Dataset base |
| LXI | 2009-2012 | ~900 | ~570 | Dataset base |
| LXII | 2012-2015 | ~1,100 | ~580 | Dataset base |
| LXIII | 2015-2018 | ~1,200 | ~590 | Dataset base |
| LXIV | 2018-2021 | ~1,400 | ~570 | Dataset base |
| LXV | 2021-2024 | ~1,500 | ~570 | Post-scrape completo |
| LXVI | 2024-2027 | ~500 | ~520 | En curso |

**Legisladores cross-legislatura**: 853 personas con 2+ legislaturas (737×2, 101×3, 14×4, 1×5). Base suficiente para análisis within-person.

### Outputs existentes que se reutilizan

| Output | Ubicación | Uso en Fase 3 |
|--------|-----------|---------------|
| NOMINATE por-legislatura | `analisis-diputados/output/` | Base para Procrustes alignment |
| `disciplina_partidista.csv` | `analisis-diputados/output/` | Directo a análisis 2 y 3 |
| `co_votacion_{leg}.csv` | `analisis-diputados/output/` | Redes de alianzas por legislatura |
| `poder_empirico.csv` | `analisis-diputados/output/` | Poder empírico por partido-legislatura |
| `nominate_{leg}.csv` | `analisis-diputados/output/` | Coordenadas DW-NOMINATE por legislador |

> **Nota sobre poder**: Los índices de poder existentes son estáticos (una legislatura). Para la Fase 3 se calcularán por partido×legislatura usando el Shapley-Shubik con DP (ya optimizado, 0.06s por cálculo).

---

## 3. Análisis 1: Trayectorias Individuales

**Análisis fundacional** — los 3 análisis restantes consumen sus outputs.

### Preguntas de investigación

- ¿Los legisladores mantienen posiciones ideológicas consistentes entre legislaturas?
- ¿Los "switchers" (cambio de partido) exhiben saltos ideológicos detectables en NOMINATE?
- ¿El mismo legislador se comporta distinto en legislaturas diferentes (within-person variance)?

### Metodología

Procrustes alignment para comparar coordenadas NOMINATE cross-legislatura. NOMINATE se calcula por-legislatura (ya existe), pero los espacios no son directamente comparables — Procrustes los alinea mediante rotación/reflexión óptima. Luego se calculan métricas de trayectoria individual.

- **Población**: 853 legisladores con 2+ legislaturas (737×2, 101×3, 14×4, 1×5)
- **Switcher detection**: Identificar cambios de partido entre legislaturas, medir distancia NOMINATE pre/post switch
- **Within-person**: Descomponer varianza intra-sujeto (mismo legislador, diferente comportamiento entre legislaturas)
- **Stability index**: Correlación de coordenadas NOMINATE entre legislaturas para cada legislador

### Outputs esperados

| Archivo | Columnas clave | Descripción |
|---------|---------------|-------------|
| `trayectorias_individuales.csv` | person_id, leg_1, leg_2, nom_dim1_L1, nom_dim1_L2, delta_nom, stability_index | Trayectoria NOMINATE por par de legislaturas |
| `switchers.csv` | person_id, party_from, party_to, nom_before, nom_after, delta_nom, legs | Legisladores que cambiaron partido |
| `procrustes_alignment.csv` | leg_pair, rotation_angle, scale, correlation_before, correlation_after | Parámetros de alineación por par |
| `within_person_variance.csv` | person_id, n_legs, var_dim1, var_dim2, mean_displacement | Métricas de estabilidad individual |

### Hipótesis principales

- Switchers muestran saltos NOMINATE detectables (>0.3 unidades en dim_1)
- La mayoría de legisladores son estables (correlación >0.7 entre legislaturas)
- Within-person variance es baja comparada con between-person
- **Limitación**: Congreso Congelado (disciplina >99%) puede enmascarar preferencias individuales genuinas

### Esfuerzo

15h desarrollo + ~45min cómputo. Script: `analysis/trayectorias.py` (~400 líneas).

---

## 4. Análisis 2: Evolución de Partidos

### Preguntas de investigación

- ¿Cómo evoluciona la disciplina partidista entre legislaturas?
- ¿Hay evidencia de dealignment (pérdida de cohesión)?
- ¿MORENA ha consolidado disciplina desde LXIII hasta LXVI?

### Metodología

Panel partido×legislatura con métricas agregadas: disciplina (ya existe como CSV), dispersión NOMINATE (desviación estándar de coordenadas dentro del partido), poder empírico (Shapley-Shubik dinámico). Se calculan tendencias y puntos de inflexión.

- **Dealignment**: PRI post-2018 (¿caída de disciplina tras perder hegemonía?), PRD pre-desaparición
- **MORENA consolidación**: Evolución disciplina LXIII (61.5%) → LXVI (~92.5%)
- **PT fractura**: Reforma electoral 11/mar/2026 — PT votó en bloque contra la coalición
- **Poder dinámico**: Shapley-Shubik por partido×legislatura (ya optimizado con DP, 0.06s)

### Outputs esperados

| Archivo | Columnas clave | Descripción |
|---------|---------------|-------------|
| `evolucion_partidos.csv` | org_id, legislatura, disciplina, nom_dispersion, poder_ss, n_members | Panel partido×legislatura |
| `dealignment_candidatos.csv` | org_id, legislatura_pair, delta_disciplina, delta_dispersion | Partidos con pérdida de cohesión |
| `morena_consolidacion.csv` | legislatura, disciplina, dispersion, poder, n_members | Serie temporal MORENA |
| `poder_por_legislatura.csv` | legislatura, org_id, shapley_shubik, banzhaf, is_critical, n_calificadas | Índices de poder dinámicos |

### Hipótesis principales

- MORENA disciplina creciente: LXIII 61.5% → LXVI ~92.5% (consolidación del bloque)
- PRI dealignment post-2018: dispersión creciente, disciplina decreciente
- PRD desaparece con disciplina en caída libre
- PT muestra fractura detectable en LXVI (reforma electoral)
- **Limitación**: Congreso Congelado (disciplina >99% reciente) comprime varianza entre partidos

### Esfuerzo

14h desarrollo + ~45min cómputo. Script: `analysis/evolucion_partidos.py` (~350 líneas).

---

## 5. Análisis 3: Efecto Género

### Preguntas de investigación

- ¿Existe una brecha de disciplina de voto entre hombres y mujeres?
- ¿La brecha varía por partido y por legislatura?
- ¿El efecto de feminización del Congreso (26.6% → 50.1%) correlaciona con cambios en métricas agregadas?

### Metodología

Panel género×partido×legislatura con métricas de disciplina y dispersión NOMINATE. Se aplica ANOVA factorial (género×partido) y análisis de tendencia temporal sobre la composición de género del Congreso. Coverage de género: 98% (M=2,774, F=1,970). Los 96 registros NULL corresponden a nombres ambiguos sin asignación posible.

- **Coverage**: 98% (M=2,774, F=1,970). 96 NULLs restantes son nombres ambiguos.
- **Evolución M/F ratio**: LX 26.6% mujeres → LXVI 50.1% mujeres (paridad).
- **Brecha disciplina**: Diferencia promedio M/F por partido-legislatura.
- **ANOVA factorial**: género × partido × legislatura — interacciones significativas.
- **Efecto feminización**: correlación entre proporción de mujeres y métricas agregadas de disciplina/cohesión del Congreso.

### Outputs esperados

| Archivo | Columnas clave | Descripción |
|---------|---------------|-------------|
| `genero_disciplina.csv` | legislatura, org_id, genero, disciplina_mean, disciplina_std, n | Disciplina M/F por partido-legislatura |
| `genero_brecha.csv` | legislatura, org_id, delta_disciplina_MF, significancia | Brecha M/F y test estadístico |
| `genero_anova.csv` | factor, sum_sq, df, f_stat, p_value | Resultados ANOVA factorial |
| `genero_evolucion.csv` | legislatura, pct_mujeres, disciplina_congreso, dispersion_congreso | Efecto feminización sobre métricas agregadas |
| `genero_nominate.csv` | legislatura, org_id, genero, nom_dim1_mean, nom_dim1_std | Posición ideológica M/F |

### Hipótesis principales

- Brecha de género pequeña (<2% en disciplina), con variación por partido.
- MORENA: sin brecha significativa (disciplina alta uniforme).
- PAN/PRD: posible brecha marginal (mayor heterogeneidad interna).
- Feminización creciente no necesariamente correlaciona con cambios en disciplina (confounder: Congreso Congelado).
- **Limitación**: El Congreso Congelado comprime varianza, dificultando la detección de efectos de género pequeños.

### Esfuerzo

16h desarrollo + ~55min cómputo. Script: `analysis/efecto_genero.py` (~450 líneas).

---

## 6. Análisis 4: Efecto curul_tipo

### Preguntas de investigación

- ¿Los legisladores plurinominales son más disciplinados que los de mayoría relativa?
- ¿El efecto persiste cuando se controla por partido?
- ¿El mismo legislador cambia de comportamiento cuando cambia de tipo de curul?

### Metodología

Panel curul_tipo×partido×legislatura con métricas de disciplina. Coverage: 89% (4,306/4,840). El análisis combina comparación entre grupos y análisis within-person para legisladores que cambiaron de tipo de curul entre legislaturas. Se controla siempre por partido para aislar el efecto tipo-curul.

- **Coverage**: 89% (4,306/4,840). Los NULLs son principalmente legisladores históricos sin datos de tipo.
- **Within-person**: Mismo legislador cuando cambia de tipo de curul (MR→PL o viceversa).
- **Interacción triple**: curul_tipo × partido × tiempo — evalúa si el efecto cambia por partido o legislatura.
- **Control por partido**: el efecto tipo-curul puede estar confundido por composición partidista.

### Outputs esperados

| Archivo | Columnas clave | Descripción |
|---------|---------------|-------------|
| `curul_tipo_disciplina.csv` | legislatura, org_id, curul_tipo, disciplina_mean, n | Disciplina por tipo-curul y partido-legislatura |
| `curul_tipo_within.csv` | person_id, tipo_from, tipo_to, disciplina_before, disciplina_after, delta | Within-person (mismo legislador, distinto tipo) |
| `curul_tipo_interaccion.csv` | legislatura, org_id, curul_tipo, efecto_marginal, significancia | Interacción curul_tipo × partido × tiempo |
| `curul_tipo_resumen.csv` | curul_tipo, disciplina_global, dispersion_nominate, n | Resumen agregado por tipo |

### Hipótesis principales

- Plurinominales marginalmente más disciplinados (<3% diferencia).
- Efecto desaparece o se reduce al controlar por partido.
- MORENA: sin diferencia (disciplina alta uniforme independientemente del tipo).
- Within-person: legisladores que cambian de MR a PL no muestran cambio de comportamiento significativo.
- **Limitación**: Coverage 89% puede introducir sesgo de selección (legisladores históricos sin tipo son mayoría relativa de legislaturas antiguas).

### Esfuerzo

14h desarrollo + ~40min cómputo. Script: `analysis/efecto_curul_tipo.py` (~400 líneas).

---

## 7. Plan de ejecución

### Dependencias entre análisis

```
Trayectorias Individuales (fundacional)
    │
    ├──► Evolución de Partidos
    ├──► Efecto Género
    └──► Efecto curul_tipo
```

**Trayectorias** es el prerrequisito de los tres análisis restantes: produce el Procrustes alignment y genera coordenadas comparables cross-legislatura. Los otros análisis consumen esos outputs y son independientes entre sí.

### Timeline

| Fase | Análisis | Duración | Dependencia |
|------|----------|----------|-------------|
| 1 | Trayectorias Individuales | ~2 días (15 h) | Ninguna |
| 2a | Evolución de Partidos | ~2 días (14 h) | Trayectorias ✓ |
| 2b | Efecto Género | ~2 días (16 h) | Trayectorias ✓ |
| 2c | Efecto curul_tipo | ~2 días (14 h) | Trayectorias ✓ |
| 3 | Integración + validación | ~1 día (4 h) | Todos ✓ |

Fase 1: secuencial. Fase 2: paralelo (3 scripts independientes). Fase 3: integración.

**Total estimado**: 7-8 días de trabajo concentrado (59 h desarrollo + ~3 h cómputo).

### Checkpoints de decisión

| Checkpoint | Tras | Pregunta clave | Criterio de paso |
|-----------|------|----------------|-----------------|
| CP1 | Trayectorias | ¿Procrustes alignment viable? ¿Correlaciones cross-legislatura > 0.5? | Si no → investigar causas, ajustar método |
| CP2 | Evolución Partidos | ¿Tendencias claras o el Congreso Congelado domina la señal? | Si Congelado domina → reportar limitación, no forzar interpretación |
| CP3 | Género + curul_tipo | ¿Efectos significativos o marginales? | Si marginales → documentar con honestidad |
| CP4 | Integración | ¿Coherencia entre análisis? ¿Contradicciones? | Resolver antes de entregar |

---

## 8. Riesgos y mitigaciones

### Tabla de riesgos

| # | Riesgo | Prob. | Impacto | Mitigación |
|---|--------|-------|---------|------------|
| 1 | **Congreso Congelado limita detección** — Disciplina >99% en legislaturas recientes comprime varianza NOMINATE y aplana efectos individuales | Alta | Alto | Documentar honestamente. Foco en legislaturas con más varianza (LX-LXIII). Análisis within-person más robusto al detectar efectos sutiles |
| 2 | **Procrustes alignment inestable** — Cambios radicales en estructura ideológica entre legislaturas pueden producir alignments arbitrarios | Media | Alto | Verificar correlaciones pre/post alignment. Si <0.5, investigar causas y considerar métodos alternativos |
| 3 | **Coverage curul_tipo (89%)** — 11% sin tipo asignado puede sesgar resultados, especialmente en legislaturas antiguas | Media | Medio | Reportar coverage por legislatura. Filtrar NULLs. Sensitivity check con/sin imputación |
| 4 | **Switchers: muestra pequeña** — Pocos legisladores cambian de partido (estimado <50) | Alta | Medio | Reportar N por análisis. Si N<20, reportar como descriptivo, no inferencial |
| 5 | **LXVI en curso** — Legislatura incompleta puede distorsionar tendencias | Baja | Medio | Flag en outputs. Sensitivity check excluyendo LXVI |

### Limitación estructural: Congreso Congelado

Disciplina partidista >99% en legislaturas recientes. Es la limitación más relevante de la Fase 3 y afecta los cuatro análisis:

- **Trayectorias**: NOMINATE colapsa con disciplina extrema. Las coordenadas son artefactos del método, no preferencias genuinas (cf. "El Espejismo NOMINATE").
- **Partidos**: Varianza cross-partido mínima cuando todos tienen disciplina >99%. Tendencias se aplanan.
- **Género**: Brechas <2% son indistinguibles de ruido cuando la varianza total es baja.
- **curul_tipo**: Efectos marginales se vuelven estadísticamente insignificantes.

**Estrategia**: centrar el análisis en legislaturas con más varianza (LX-LXIII). Documentar limitaciones con honestidad. Los modelos within-person ofrecen mayor robustez porque controlan por individuo.

---

## 9. Recomendación

### Prioridad de ejecución

**Trayectorias primero.** Es el análisis fundacional: produce los outputs que los otros tres consumen. Además, valida la viabilidad del Procrustes alignment (checkpoint CP1). Si el alignment falla, los análisis restantes pueden ejecutarse con coordenadas no alineadas, pero con menor poder comparativo.

**Luego en paralelo**: Evolución de Partidos + Efecto Género + Efecto curul_tipo. Los tres son mutuamente independientes y pueden desarrollarse de forma simultánea.

### Siguiente paso inmediato

Tras aprobación de esta propuesta:

1. Crear `analysis/trayectorias.py` — template base con carga de datos y estructura de outputs.
2. Implementar Procrustes alignment sobre coordenadas NOMINATE existentes.
3. Ejecutar sobre 853 legisladores cross-legislatura.
4. **Checkpoint CP1**: verificar viabilidad del alignment antes de continuar.

### Resumen

4 scripts nuevos (~1,600 líneas) · 59 h desarrollo · ~3 h cómputo
