# Pruebas de Radar V1

La GUI ofrece **Pruebas del panel y pipeline**. También pueden ejecutarse con `python -B -m unittest discover -s tests_Radar_V1 -v`.

La suite utiliza datos temporales para probar contratos, control de fugas, simulación, fallos, reinicio, restauración y controles de la GUI. No descarga datos ni certifica sesiones remotas. Las pruebas del comportamiento de la GUI funcionan sin pantalla; la revisión visual requiere un servidor gráfico disponible.
