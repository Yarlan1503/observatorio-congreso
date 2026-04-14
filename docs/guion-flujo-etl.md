## Apertura

[Mario] Hoy quiero contarles sobre un proyecto que lleva meses consumiéndonos y que, creo, tiene un valor enorme para la democracia mexicana.

[Mario] Nos propusimos construir la base de datos más completa que existe sobre el historial de votaciones del Congreso de la Unión. Hablamos de todo lo que se ha votado en la Cámara de Diputados y en el Senado desde el año dos mil seis hasta hoy.

[Mario] Siete legislaturas completas: desde la LX hasta la LXVI, que es la que está en curso. El resultado final son dos punto seis millones de votos individuales registrados, distribuidos en nueve mil trescientas ochenta y cinco votaciones.

[Mario] Y detrás de cada voto hay una persona: cuatro mil ochocientas cuarenta personas distintas que en algún momento ocuparon una curul. Todo eso pesa trescientos treinta y siete megabytes de datos limpios, con cero violaciones de llaves foráneas. Suena impresionante, ¿verdad?

[Mario] Pero aquí viene la parte frustrante. Nada de esto existía como base de datos abierta. El gobierno mexicano no ofrece un archivo descargable con el historial completo de votaciones.

[Sara] Lo que sí existen son dos portales web: el SITL para Diputados y el portal del Senado de la República. Ambos muestran las votaciones como páginas navegables, pero no en ningún formato estructurado que puedas descargar de una vez.

[Sara] Así que tuvimos que construirlo todo desde cero, extrayendo los datos página por página. Y cada portal es un mundo completamente distinto en cuanto a dificultad técnica. El del Senado, por ejemplo, está protegido por un cortafuegos de aplicación web bastante agresivo.

[Sara] El primer intento con un cliente web estándar fue bloqueado de inmediato. De hecho, se nos colaron páginas de error en la base de datos y tuvimos que limpiar casi diez mil registros fantasmas. Es decir, nos costó trabajo incluso darnos cuenta de que estábamos almacenando basura en vez de datos reales.

[Mario] Lo que hizo el equipo fue diseñar dos sistemas de extracción completamente paralelos. Dos rutas independientes, cada una adaptada a las particularidades de su portal, pero que al final convergen en una misma estructura de datos.

[Mario] Empecemos por el portal de Diputados, que es el más amigable de los dos. Y después nos metemos con el Senado, que fue toda una aventura de evasión de cortafuegos.

## Sistema de extracción de Diputados

[Mario] El portal SITL de la Cámara de Diputados es, relativamente hablando, un paraíso. Es público, no tiene cortafuegos agresivo, y sus páginas están estructuradas de manera predecible.

[Mario] El sistema usa un cliente web con un agente de usuario personalizado que se identifica como ObservatorioCongreso versión uno. Cada página se descarga y se almacena en un caché basado en archivos, usando el resumen criptográfico de la dirección como nombre de archivo.

[Mario] Y para no saturar el servidor, se establece un límite de dos segundos entre cada petición. Si algo falla, el sistema reintenta con una pausa exponencial: dos segundos, luego cuatro, luego ocho, con un máximo de tres intentos. Sara, cuéntanos cómo está organizada la extracción por dentro.

[Sara] El sistema tiene cuatro analizadores distintos, cada uno enfocado en un tipo de dato específico. El primero extrae el listado completo de votaciones: fecha, título, tipo de votación y enlace al desglose. El segundo saca las estadísticas por partido.

[Sara] El tercero es el más importante: extrae los votos individuales de cada diputado, y aquí hay un detalle clave. El partido del diputado no viene en la página de la votación, sino que se pasa como parámetro en la dirección de la petición. Es decir, para una misma votación hay que hacer una petición por cada partido representado en la sesión.

[Sara] El cuarto analizador extrae las fichas curriculares de cada legislador. Todo lo que extraen estos analizadores llega como datos crudos, y ahí entra una capa de transformación con un modelo de validación.

[Sara] Los datos crudos se validan contra un esquema estricto, y luego se convierten a una representación estandarizada basada en el formato Popolo, un estándar abierto para datos legislativos que usan muchas organizaciones cívicas en el mundo.

[Mario] Una vez que tienes los datos limpios y estandarizados, viene una parte fundamental: la clasificación del tipo de votación. Porque no es lo mismo una votación de mayoría simple que una que requiere dos tercios del pleno.

[Mario] El portal no te dice explícitamente qué tipo de mayoría se necesita para cada asunto, así que construyeron un clasificador basado en palabras clave del título. ¿Cómo funciona exactamente, Sara?

[Sara] El clasificador busca palabras específicas en el título de la votación. Si encuentra la raíz "constituci", la marca como mayoría calificada, porque las reformas constitucionales requieren dos tercios. Si encuentra "presupuesto", la clasifica como ley secundaria.

[Sara] Para las mayorías simples, la regla es directa: que los votos a favor sean más que los votos en contra. Para las calificadas, se necesitan dos tercios de los legisladores presentes, no de los que emitieron voto. Este es un detalle sutil pero importante: si hay quinientos diputados presentes pero solo cuatrocientos votan, la base sigue siendo quinientos.

[Sara] Finalmente, el cargador toma todos estos datos y los inserta en siete tablas distintas por cada votación. Usa una instrucción de inserción que ignora duplicados, así que el sistema es idempotente: puedes correrlo cuantas veces quieras sin crear registros repetidos. Y todo se ejecuta dentro de una transacción atómica con verificación de llaves foráneas, así que o se guarda todo completo o no se guarda nada.

[Mario] Así que el sistema de Diputados es robusto y bien pensado. Cuatro analizadores especializados, validación estricta de datos, clasificación automática de mayorías según el tema, y un cargador idempotente con transacciones atómicas. Si algo falla a la mitad, no queda nada a medias y puedes volver a intentar sin riesgo.

[Mario] Pero si el portal de Diputados era un jardín, el del Senado es un campo minado. Ahí es donde la historia se pone realmente interesante.

## Sistema de extracción del Senado

[Mario] El portal del Senado de la República está protegido por un sistema de seguridad web llamado Incapsula. Es un cortafuegos de aplicación web bastante agresivo que analiza cada petición y decide si viene de un navegador real o de un programa automatizado.

[Mario] El primer intento fue con el mismo cliente web que usamos para Diputados. Resultado: bloqueado de inmediato. Y no solo bloqueado, sino que las páginas de error se colaron en nuestra base de datos. Fueron nueve mil cuatrocientos treinta y siete registros fantasmas que después tuvimos que limpiar a mano.

[Sara] La solución fue cambiar completamente de herramienta. En vez de un cliente web normal, usamos una biblioteca que imita las huellas digitales de navegadores reales a nivel del protocolo de seguridad de la conexión.

[Sara] El cortafuegos analiza detalles sutiles de cómo se negocia la comunicación inicial, y un programa automatizado tiene una huella distinta a la de un navegador real. Así que implementamos cinco capas de evasión trabajando en conjunto.

[Sara] La primera es un grupo de seis huellas digitales de navegadores distintos: Chrome, Safari y Edge en diferentes versiones. La segunda capa son cookies persistentes guardadas en disco, para que el cortafuegos crea que es el mismo navegador que visitó antes.

[Sara] La tercera es un disyuntor de seguridad: si hay dos bloqueos consecutivos, la sesión se marca como quemada y se descarta por completo. La cuarta es la rotación: cada diez peticiones se cambia de huella digital. Y la quinta es un calentamiento: después de quemar una sesión, se hace una petición de prueba antes de intentar descargar datos reales.

[Mario] Con un sistema de cinco capas y tantas piezas móviles, las cosas podían salir mal en cualquier momento. Y de hecho, hubo un error de programación bastante sutil. El sistema rotaba las huellas cada diez peticiones, pero en la práctica no estaba rotando absolutamente nada.

[Mario] Todo parecía funcionar, las peticiones se hacían, pero algo no cuadraba. Sara, cuéntanos qué pasó exactamente con ese error.

[Sara] El problema era que el tamaño del grupo de huellas estaba configurado en uno en vez de seis. Entonces el cálculo de cuál huella usar siempre daba cero, porque el operador módulo uno siempre devuelve cero sin importar el número.

[Sara] Es decir, la rotación estaba activada en el código, pero matemáticamente era imposible que rotara. Siempre usaba la misma huella digital, y el cortafuegos terminaba detectando el patrón porque veía exactamente la misma una y otra vez.

[Sara] Además, para evadir mejor la detección, se forzó el uso de la versión uno del protocolo de transferencia de hipertexto, porque la versión dos altera la huella digital y la hace más fácil de identificar como automatizada.

[Sara] Por el lado de la extracción, el portal del Senado requiere una petición doble para cada votación. Primero se piden los metadatos con una petición normal, y luego una petición asíncrona separada para obtener los votos nominales individuales. El analizador está unificado para todas las legislaturas, desde la LX hasta la LXVI.

[Mario] Y para completar el panorama, también tuvieron que extraer los perfiles de todos los senadores y senadoras. Un extractor aparte de mil veintitrés líneas de código para capturar género, tipo de curul, partido y entidad federativa.

[Mario] El resultado final de la extracción de perfiles fue impresionante: mil setecientos cincuenta y cuatro perfiles completados. Cero sesiones comprometidas, solo tres bloqueos que se lograron recuperar, y todo el proceso en dos horas con cincuenta y seis minutos. Lo que empezó como un bloqueo total terminó en un sistema capaz de navegar el portal del Senado casi como lo haría un humano.

## Esquema unificado

[Mario] Una vez que logramos extraer los datos de ambas cámaras, el siguiente gran desafío era unificarlos en un solo modelo coherente. No se trataba de simplemente juntar dos bases distintas. Cada cámara tiene su propia estructura, sus propios identificadores, su propia forma de nombrar las cosas.

[Mario] Para esto adoptamos el estándar Popolo, un formato abierto usado internacionalmente para datos parlamentarios, y lo extendimos con tres tablas adicionales. El resultado final son doce tablas. Nueve vienen del estándar y tres son extensiones propias del observatorio. Sara, cuéntanos cómo se estructura este modelo.

[Sara] La idea central del estándar es separar entidades de relaciones. Una persona es una entidad física con nombre y datos biográficos. Una organización puede ser un partido político, una cámara legislativa o un grupo parlamentario. La membresía es la relación que vincula a una persona con una organización en un período determinado.

[Sara] Del lado legislativo hay tres niveles de granularidad. La propuesta legislativa es el documento que se debate. La instancia de votación es el momento en que se vota. Y el voto individual conecta a la persona con esa instancia. El voto individual es el átomo fundamental de todo el sistema: cada registro dice qué persona votó de qué manera en qué votación concreta.

[Sara] La tabla de totales simplemente agrupa esos votos por organización para consultas rápidas, pero es una vista derivada, nunca la fuente original de datos. Las tres tablas propias capturan lo que el estándar no cubre: actores externos como el presidente y la Suprema Corte, relaciones de poder entre instituciones, y eventos políticos como elecciones y crisis nacionales.

[Mario] Algo muy curioso de este diseño es la convención de identificadores. No son números secuenciales simples, sino que cada uno lleva un prefijo codificado que te dice de un vistazo qué tipo de entidad es y de qué cámara proviene. ¿Por qué no usar simplemente números autoincrementales?

[Sara] La ventaja principal es la legibilidad inmediata. En una base con millones de registros, poder identificar el tipo de entidad y su origen con solo leer el identificador es invaluable. La regla general es un prefijo de uno o dos caracteres seguido de cinco dígitos con relleno de ceros.

[Sara] Para entidades globales, las que no pertenecen a una cámara específica, el prefijo es una sola letra: P para persona, T para cargo y C para totales agregados. Para entidades específicas de cada cámara se agrega la letra de la cámara, separada por un guion bajo. Diputados usa la D y Senado la S.

[Sara] Así, una instancia de votación de Diputados empieza con VE_D y una del Senado con VE_S. Los votos son V_D o V_S, las propuestas Y_D o Y_S, las membresías M_D o M_S. El ejemplo clásico: VE_D00042 es la votación número cuarenta y dos de Diputados. Con solo leerlo sabes qué es y de dónde viene.

[Sara] Los identificadores fijos son igual de sistemáticos. Diputados es siempre O08, Senado es O09. Los partidos van del O11 al O18: Morena, PAN, Verde, PT, PRI, Movimiento Ciudadano, independientes y PRD. Esto permite consultas consistentes sin depender de nombres que puedan cambiar.

[Mario] Pero hay un principio fundamental en este esquema que vale la pena destacar. Uno pensaría que los totales que reportan los portales oficiales serían la referencia, pero no siempre es así. Los portales a veces tienen errores en sus cifras agregadas.

[Sara] Los portales legislativos a veces reportan totales incorrectos. Puede decir que trescientos diputados votaron a favor, pero al contar voto por voto salen doscientos noventa y ocho. Esos dos votos de diferencia pueden cambiar el resultado de una votación.

[Sara] Por eso nuestra regla es tajante: la fuente de verdad es siempre el conteo individual de votos. Nunca la tabla derivada, nunca lo que diga el portal. Los totales se recalculan cada vez que se necesitan, lo cual tiene un costo de cómputo mayor, pero garantiza integridad absoluta. Cada voto apunta a una persona real, cada persona está vinculada a su organización, cada dato es trazable hasta su fuente original.

## Limpiezas y migraciones

[Mario] Pero diseñar el esquema fue solo la mitad del trabajo. La otra mitad fue limpiar los datos, y aquí es donde las cosas se pusieron realmente interesantes. Cuando descargas datos de portales gubernamentales mexicanos, no llegan limpios ni bien estructurados.

[Mario] Llegan con duplicados, inconsistencias, identificadores que se contradicen entre sí y errores de todo tipo. El primer gran problema fue la deduplicación de votos. Encontramos cerca de dos millones de registros duplicados en la tabla de votos. Para ponerlo en perspectiva: eliminamos casi tantos votos duplicados como votos reales permanecieron en la base final.

[Mario] También limpiamos cerca de dieciocho mil registros duplicados en la tabla de totales y agregamos restricciones de unicidad para prevenirlo. Además hubo que eliminar organizaciones basura y personas fantasma, suplentes registrados sin ninguna actividad legislativa real. Sara, cuéntanos los casos más técnicos que enfrentaron.

[Sara] Empecemos por los catorce empates fantasma. La lógica original del sistema comparaba totales derivados para determinar si una votación había terminado en empate. Pero como los portales a veces reportan totales incorrectos, el sistema detectaba empates que en realidad no existían. Al corregir la lógica para que contara votos individuales, los catorce empates desaparecieron por completo.

[Sara] Luego vino el problema del Senado con sus identificadores reutilizados entre legislaturas. El Senado asigna los mismos identificadores a votaciones distintas en legislaturas diferentes, lo cual rompe cualquier llave primaria simple. La solución fue migrar toda la base del Senado a una llave primaria compuesta que combina el identificador con el número de legislatura.

[Sara] En el tema de datos faltantes, extrajimos perfiles del Senado para completar género y tipo de curul. Pasamos de doscientas veintidós mujeres a cuatrocientas ochenta y de cincuenta y cinco hombres a quinientos noventa y ocho. También eliminamos manualmente los nueve mil cuatrocientos treinta y siete registros fantasmas generados por el cortafuegos.

[Sara] Y el caso más extremo de todos: mil seiscientas catorce líneas de código para insertar datos de la Reforma Político-Electoral, reconstruidos manualmente del Diario de Debates del Senado en formato de texto libre. No había tabla ni interfaz de programación. Solo la narrativa de lo que pasó en la sesión, escrita en prosa.

[Mario] Literalmente reconstruyendo votaciones a partir de texto narrativo. Es el tipo de trabajo invisible que nadie nota cuando consulta la base final, pero sin el cual esa parte de la historia legislativa simplemente no existiría.

[Mario] Resumiendo todo este proceso, ¿cuáles dirías que son las lecciones principales? Porque cada capa del sistema generó su propio tipo de error: portales con totales incorrectos, cortafuegos generando basura, identificadores reusados. ¿Qué principio general nos deja esta experiencia?

[Sara] La lección más importante se resume en tres palabras: validar siempre. Validar antes de almacenar en caché, antes de insertar en la base, antes de confiar en cualquier dato que entre al sistema. Los portales van a tener errores, los cortafuegos van a generar respuestas basura, los identificadores se van a reusar. Es inherente al ecosistema.

[Sara] Lo que sí puedes controlar es cuántos de esos errores sobreviven hasta tu base final. Hoy tenemos cero violaciones de llaves foráneas, no porque los datos originales fueran buenos, sino por cientos de horas de limpieza y detección de problemas.

[Sara] La otra lección es definir la fuente de verdad antes de que aparezcan las discrepancias. En nuestro caso, siempre gana el conteo individual de votos. Y finalmente, que los datos más valiosos a veces requieren el trabajo más manual. La Reforma Político-Electoral no estaba en ninguna base digital. Estaba enterrada en el texto de un diario de sesiones.

## Cierre

[Mario] Después de todo este recorrido, vale la pena detenerse a mirar los números finales del proyecto. Dos millones seiscientas diecinueve mil noventa y seis votos individuales registrados en la base. De esos, dos millones ciento cincuenta y cuatro mil ciento dieciséis corresponden a Diputados y cuatrocientas sesenta y cuatro mil novecientas cincuenta y seis al Senado.

[Mario] Son nueve mil trescientas ochenta y cinco instancias de votación: cuatro mil trescientas cincuenta de Diputados y cinco mil treinta y tres del Senado. La base contiene cuatro mil ochocientas cuarenta personas, con solapamiento entre ambas cámaras. Todo esto cubre siete legislaturas y veintiún años de actividad legislativa mexicana.

[Mario] Son cifras que dan dimensión de lo que se construyó. Pero lo más importante no es el volumen, sino lo que se puede hacer con estos datos. Sara, ¿qué tipo de preguntas se pueden responder ahora que antes eran prácticamente imposibles?

[Sara] Ahora puedes preguntar cosas como: ¿cómo vota un partido específico en reformas constitucionales versus leyes secundarias? ¿Cuál es la disciplina partidista real, medida voto por voto, versus la que los partidos declaran públicamente?

[Sara] ¿Cuáles son los patrones de asistencia a las votaciones? ¿Qué legisladores faltan más? Puedes comparar el comportamiento de un legislador antes y después de cambiar de partido. Puedes medir el grado de cohesión interna de cada bancada. Puedes identificar votaciones donde un partido se dividió, donde hubo disidencias internas, donde el resultado final fue inesperado.

[Sara] Todo esto con datos trazables hasta la fuente original en cada portal legislativo. Cada número se puede verificar. Cada afirmación se puede respaldar con el registro individual de cada voto emitido.

[Mario] Y ese es precisamente el valor democrático de este proyecto: la transparencia de las decisiones legislativas. Cada voto que un legislador emite queda registrado y es consultable por cualquier persona.

[Mario] Cuando un partido dice que apoyó una reforma, se puede verificar cuántos de sus legisladores realmente votaron a favor y cuáles se abstuvieron. Cuando un diputado afirma que siempre ha defendido una causa, se puede comprobar su historial completo de votaciones en ese tema.

[Mario] Este observatorio pone a disposición de cualquier ciudadano la misma información que antes requería acceso a portales especializados y horas de navegación manual. Es democratizar el acceso a la información legislativa. Y eso, al final del día, es lo que justifica cada hora invertida en la construcción de este sistema.

[Mario] Muchas gracias por acompañarnos en este recorrido por el Observatorio del Congreso. Hasta la próxima.
