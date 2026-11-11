# Operaciones sobre el corpus

| Programa | Propósito |
|---|---|
| `analizar_balance_fuentes.py` | Diagnóstico retrospectivo de volumen, longitud y autores observables; calcula escenarios de ponderación sin modificar entradas. |
| `generar_conjuntos_temporales.py` | Genera los tres corpus conjuntos por semanas (56/14/13), separa verificación de desarrollo y calibra pesos sólo con entrenamiento. |

Las decisiones vigentes están en [PONDERACION_FUENTES.md](../../documentos/PONDERACION_FUENTES.md) y [PARTICION_TEMPORAL_DATOS.md](../../documentos/PARTICION_TEMPORAL_DATOS.md). Estos programas no construyen indicadores de sentimiento o `MA5` ni entrenan modelos.

```python
from pathlib import Path
from scr.operaciones.generar_conjuntos_temporales import cargar_desarrollo

entrenamiento = cargar_desarrollo(Path("datos/radar_modelado/desarrollo"), "entrenamiento")
prueba = cargar_desarrollo(Path("datos/radar_modelado/desarrollo"), "prueba")
```

Cada elemento es el texto íntegro de una fuente en una semana, con su procedencia. El cargador rechaza verificación; los parámetros aprendidos se ajustan sólo con entrenamiento. Los corpus y diagnósticos generados se conservan localmente y no se incluyen en los commits de código.
