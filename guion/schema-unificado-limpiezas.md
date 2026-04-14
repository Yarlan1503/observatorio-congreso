## El Schema Unificado

[Mario] Dos cámaras del Congreso, dos portales completamente distintos, dos formas de organizar la información.
[Mario] Cada uno con su propia lógica, sus propios formatos y sus propias inconsistencias.
[Mario] ¿Cómo se unifica todo eso en una sola base de datos coherente?
[Sara] Con un esquema basado en el estándar Popolo-Graph, extendido con tres tablas propias del proyecto.
[Sara] En total son doce tablas que modelan todo el ecosistema legislativo mexicano.
[Javier] Empecemos por las que vienen del estándar: area, organization, person, membership, post, motion, vote_event, vote y count.
[Enrique] Nueve tablas de la especificación Popolo que cubren la mayor parte del modelo parlamentario genérico.
[Enrique] Y tres tablas que tuvimos que agregar nosotros porque el estándar no alcanzaba para lo que necesitábamos.
[Enrique] Esas extensiones son actor_externo, relacion_poder y evento_político.
[Javier] Actor externo modela organizaciones que no son cámaras ni partidos: el Poder Ejecutivo, organismos autónomos, la Judicatura.
[Javier] Relacion poder captura las dinámicas entre actores: alianzas legislativas, oposiciones, bloqueos.
[Sara] Y evento político sitúa cada votación en su contexto más amplio: una reforma constitucional, una controversia, una crisis.
[Enrique] El estándar Popolo se diseñó como un formato genérico para datos parlamentarios de cualquier país.
[Enrique] Pero el Congreso mexicano tiene complejidades que requieren extensiones específicas.
[Sara] Cada tabla del esquema tiene un propósito claro y bien delimitado dentro del modelo.
[Sara] Area modela las divisiones geográficas: circunscripciones, distritos, entidades federativas.
[Sara] Person es la persona física: un diputado o senador con nombre, género y curul asignada.
[Enrique] Organization es el contenedor polivalente: sirve para partidos políticos, cámaras y grupos parlamentarios.
[Javier] Membership es el nexo que une ambas tablas: conecta personas con organizaciones.
[Javier] Este diputado pertenece a MORENA, este senador integra la comisión de justicia.
[Sara] Post modela los cargos: diputado federal, senador de la República, coordinador de grupo parlamentario.
[Sara] Motion es la propuesta legislativa que se somete a votación en el pleno.
[Sara] Es el qué se vota: una iniciativa, una reforma, un dictamen.
[Mario] Vote_event es la instancia concreta: una votación específica con su fecha, hora y resultado final.
[Javier] Y vote es el átomo fundamental de todo el sistema: el voto individual de un legislador.
[Javier] Un sí a favor, un no en contra, una abstención.
[Sara] Count agrupa los totales por organización: cuántos votos del PAN a favor, cuántos de MORENA en contra.
[Enrique] Pero ojo con la tabla count, que de eso hablaremos con detalle en las limpiezas.
[Enrique] Es una tabla derivada que puede contener errores provenientes de los portales.
[Sara] Los identificadores usan una convención de prefijos con padding de cinco dígitos.
[Sara] Esto permite saber de un vistazo a qué tabla pertenece cada registro y de qué cámara proviene.
[Sara] Por ejemplo, VE_D00042 es un evento de votación de Diputados.
[Javier] VE_S00015 sería uno del Senado.
[Mario] Las letras indican la tabla y la cámara de origen de cada registro.
[Mario] V_D para un voto individual de Diputados, V_S para Senado.
[Sara] Para las motions usamos la letra Y: Y_D para Diputados, Y_S para Senado.
[Sara] Las memberships son M_D y M_S respectivamente.
[Javier] Las tablas globales no llevan sufijo de cámara porque son compartidas entre ambas cámaras.
[Javier] Person usa solo P, count usa C, y post usa T.
[Enrique] Las organizaciones también tienen IDs fijos que asignamos de forma manual para mantener consistencia.
[Enrique] Diputados es O08, Senado es O09.
[Mario] Y los partidos políticos van del O11 al O18.
[Enrique] MORENA es O11, PAN es O12, PVEM O13, PT O14, PRI O15, MC O16.
[Enrique] Independientes O17 y PRD O18.
[Sara] Un detalle crucial: cada cámara maneja sus propios IDs internos de forma totalmente independiente.
[Sara] Pero en nuestra base unificada, todo confluye bajo estos prefijos estandarizados.
[Sara] Así un análisis cruzado entre cámaras es posible sin ambigüedad.
[Javier] El resultado es una base de datos de 337 megabytes con información de siete legislaturas.
[Javier] Y lo más importante de todo: cero violaciones de llaves foráneas.
[Mario] Integridad referencial total.
[Enrique] Cada voto apunta a una persona real, cada persona a una organización que existe.
[Enrique] No hay registros huérfanos en ninguna de las doce tablas.
[Mario] Suena simple, pero mantener esa integridad mientras se importan millones de registros de dos fuentes distintas es todo un reto.
[Mario] Y de eso habla exactamente la siguiente parte de la historia.

## Limpiezas y Migraciones

[Enrique] Si los datos del gobierno mexicano fueran limpios, este proyecto habría tardado la mitad.
[Enrique] Pero no lo son, y las limpiezas fueron una saga con varios capítulos.
[Javier] El primer capítulo grande es la deduplicación masiva de registros.
[Javier] Dos millones de votos duplicados eliminados de un plumazo.
[Sara] Además de dieciocho mil counts duplicados que también había que limpiar de la base.
[Sara] En un momento dado, había más votos basura acumulados que votos reales en la base de datos.
[Mario] Imaginen eso: tener que limpiar dos millones de registros fantasmas que se fueron acumulando sin control.
[Enrique] El problema venía de ejecuciones múltiples del scraper que insertaban los mismos votos una y otra vez.
[Enrique] Sin un mecanismo de deduplicación adecuado, la basura se multiplicaba exponencialmente.
[Enrique] Después de la limpieza se agregaron restricciones de unicidad en todas las tablas afectadas.
[Enrique] Así la propia base de datos rechaza cualquier intento de insertar un duplicado en el futuro.
[Sara] Un escudo a nivel de esquema para que este problema no se repita nunca.
[Javier] Con esas restricciones en lugar, cualquier ejecución duplicada del scraper se detecta automáticamente.
[Javier] Pero los votos duplicados no fueron el único problema que vino del Senado.
[Javier] Recuerdan los fantasmas del firewall de aplicación web que mencionamos antes?
[Enrique] Nueve mil cuatrocientas treinta y siete páginas de error cacheadas como si fueran datos legislativos reales.
[Enrique] El parser las tragó sin rechistar porque la respuesta HTTP tenía código doscientos, aparentando éxito.
[Mario] La lección quedó grabada a fuego: siempre validar el contenido antes de cachear.
[Mario] Nunca asumas que lo que descargaste es correcto solo porque llegó sin error de conexión.
[Sara] Y luego estuvo el bug de la rotación de huella digital.
[Sara] Un error absurdo en su simplicidad pero devastador en sus consecuencias prácticas.
[Javier] El módulo de rotación hacía módulo uno para elegir qué huella TLS usar en cada petición.
[Javier] Módulo uno siempre da cero, sin importar el índice de la lista.
[Sara] Es decir, la huella digital nunca rotaba entre las opciones disponibles.
[Sara] El firewall de aplicación web veía exactamente la misma huella digital miles de veces seguidas.
[Mario] Es el equivalente a entrar a un edificio mostrando la misma credencial falsa sin cambiarla jamás.
[Enrique] Un solo operador matemático mal escrito y miles de peticiones al firewall fueron completamente inútiles.
[Enrique] Las organizaciones basura son otro capítulo de limpieza que merece su propia mención.
[Enrique] El parser confundía comisiones con partidos políticos al extraer nombres de las páginas del Senado.
[Sara] Y encima creaba organizaciones distintas por variaciones tipográficas del mismo nombre.
[Sara] "Partido Acción Nacional", "Partido de Acción Nacional", "PAN" terminaban como tres organizaciones separadas.
[Javier] Todo se resolvió con normalización de nombres y una lista maestra de organizaciones válidas predefinidas.
[Enrique] También aparecieron personas fantasma en el sistema durante las primeras cargas.
[Enrique] Suplentes que figuraban en fichas curriculares del Senado pero que jamás votaron en ningún registro de votación.
[Mario] Estaban en el sistema porque su perfil público existía, pero no tenían actividad legislativa real alguna.
[Sara] Hablando de personas, el relleno de datos demográficos fue un trabajo considerable por separado.
[Sara] El género al principio solo tenía 222 mujeres diputadas y 55 senadoras identificadas correctamente.
[Javier] Después de mejorar el scraper de perfiles del Senado con mil veintitrés líneas de código.
[Javier] El resultado: 480 mujeres diputadas y 598 senadoras con género verificado.
[Sara] Más del doble en Diputados, más de diez veces más en el Senado.
[Sara] La diferencia es abismal y cambia cualquier análisis de representación de género que se quiera hacer.
[Sara] Una mejora enorme en la calidad de los datos demográficos del padrón legislativo.
[Sara] Lo mismo pasó con el tipo de curul: antes solo teníamos cuarenta y siete de mayoría relativa y cuarenta y uno plurinominales.
[Javier] Ahora tenemos 404 de mayoría relativa y 555 plurinominales.
[Javier] Una cobertura casi completa que permite análisis por tipo de elección.
[Enrique] Ahora hablemos de los catorce empates fantasma, uno de los bugs más sutiles del proyecto.
[Enrique] La lógica original comparaba los totales de la tabla count para determinar si una votación terminaba en empate.
[Enrique] Pero los portales legislativos reportan totales incorrectos con una frecuencia alarmante.
[Mario] Por eso la fuente de verdad siempre debe ser contar los votos individuales, no confiar en los agregados del portal.
[Sara] El fix fue directo: usar el conteo directo de votos como árbitro final de cualquier empate declarado.
[Sara] Si el portal dice que hubo empate, cuéntame los votos uno por uno y verificamos si es verdad.
[Mario] Resulta que de esos catorce empates reportados, varios no lo eran en realidad.
[Mario] Los totales del portal estaban mal y la lógica original los validó como correctos sin cuestionarlos.
[Javier] Y el Senado tenía otro problema estructural serio con sus identificadores internos.
[Javier] Reusaban los mismos IDs numéricos entre legislaturas distintas.
[Sara] Un mismo senado_id podía referirse a personas completamente diferentes en la LXIV y la LXV legislatura.
[Sara] La solución fue migrar toda la tabla a una llave primaria compuesta: senado_id combinado con el número de legislatura.
[Mario] Así cada registro es único e inequívoco, aunque el Senado recicle sus números internos entre periodos.
[Sara] Fue una migración delicada porque afectaba todas las relaciones existentes en la base.
[Sara] Cada referencia a un senador tenía que actualizarse para incluir la legislatura correspondiente.
[Enrique] Pero el caso más extremo de todo el proyecto fue lo que llamamos el Caso Cero.
[Enrique] La votación de la Reforma Político-Electoral.
[Enrique] Mil seiscientas catorce líneas de SQL escritas a mano, una por una.
[Mario] Porque esa votación simplemente no existía en ningún portal del Congreso.
[Enrique] No estaba en Diputados, no estaba en Senado, no estaba en ningún sistema oficial de registro.
[Enrique] Como si esa votación nunca hubiera ocurrido.
[Enrique] La reconstruimos voto por voto desde el Diario de Debates del Senado, que es texto libre.
[Sara] Un documento en formato PDF sin estructura tabular, sin campos de base de datos que facilitaran la extracción.
[Sara] Literalmente leyendo las actas de sesión y convirtiendo cada intervención parlamentaria en un registro de voto individual.
[Javier] Cada diputado que levantaba la mano, cada senador que pedía la palabra, todo convertido en datos estructurados.
[Javier] Mil seiscientas catorce líneas de inserciones manuales para una votación que los portales decidieron ignorar.
[Mario] Un trabajo de arqueología legislativa, sin exagerar ni un poco.
[Enrique] Probablemente la parte más tediosa y satisfactoria de todo el proyecto al mismo tiempo.
[Enrique] Y todo esto nos deja una reflexión importante sobre la realidad de los datos públicos en México.
[Enrique] Los portales del Congreso nunca fueron diseñados para consumo programático.
[Enrique] Los datos del gobierno mexicano vienen con trampas.
[Sara] Identificadores que se reusan entre legislaturas, totales que mienten, páginas de error disfrazadas de contenido válido.
[Javier] Votaciones completas que simplemente desaparecen de los sistemas oficiales sin explicación.
[Enrique] A veces uno se pregunta si es negligencia o si hay algo peor.
[Mario] Pero después de todas estas limpiezas, migraciones y correcciones, la base está sólida.
[Mario] Dos millones de votos verificados, integridad referencial total, doce tablas impecables.
[Javier] Y con esa base limpia y confiable ya se pueden hacer cosas que antes eran simplemente imposibles.
[Javier] Pero de los resultados finales y los números consolidados habla el cierre.
