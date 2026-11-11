# Referencia histórica del notebook y flujo vigente

El notebook anterior se consultó para recuperar metodología y diccionarios autorizados. No se reutilizaron publicaciones, CSV extraídos ni resultados numéricos de ese proyecto.

La corrección del 11 de noviembre de 2026 sustituye la preparación histórica: **sin MA5, sin rezagos adicionales de X y sin estandarización global antes de separar temporalmente**. La tabla vigente contiene 70 filas y 24 columnas: fechas, Original semanal y veinte candidatas temáticas. Véase [INDICADORES_SEMANALES.md](INDICADORES_SEMANALES.md).

Las funciones copiadas en `preparar_indicadores_semanales.py` ajustaban `StandardScaler` sobre la tabla completa, incluido el objetivo. El script `Modelo_Radar_1.py` también incluía preparación global y rutas a tablas del proyecto anterior. Ambos carecían de consumidores en el flujo vigente y se archivaron íntegros en `trash/respaldos/correccion_sin_suavizado_2026-11-11_vzi2rys5/codigo_retirado/`, con hashes en su manifiesto. No se ejecutaron sobre el corpus actual.

La copia del código y las notas anteriores se conservan en el mismo respaldo. Se retira su ejemplo de uso para impedir que se aplique por error a prueba o verificación.

El flujo activo es construcción de indicadores semanales, partición 56/14/13 e inspección/selección con ajuste de pesos y escalas dentro de cada corte temporal. Las escalas no se guardan aplicadas a toda la tabla ni se ajustan con prueba o verificación. Los horizontes desplazan sólo la respuesta hacia una semana futura concreta.
