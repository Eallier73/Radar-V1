# GUI del pipeline Radar V1

La interfaz centraliza el control de las seis etapas previstas de Radar:

1. Extracción.
2. Preprocesamiento.
3. NLP.
4. Modelado.
5. Tablero.
6. Reporte.

Las seis aparecen desde ahora en la interfaz. Una etapa solo se puede seleccionar
cuando su runner existe; las demás muestran el estado `Próximamente`. La selección
inicial activa únicamente **Extracción**.

## Abrir la interfaz

Desde la raíz del repositorio:

```bash
/home/emilio/anaconda3/envs/radar-v1/bin/python -B abrir_gui_orquestador.py
```

El lanzador usa el intérprete resuelto por Radar para los procesos internos:
`RADAR_PYTHON`, `.venv`, `venv`, el entorno Conda `radar-v1` o el Python actual,
en ese orden.

## Etapa 1: Extracción

La GUI permite activar de forma independiente:

- YouTube.
- Twitter/X.
- Medios.
- Facebook (posts y comentarios).

Cada fuente tiene un botón **Ejecutar solo...** que selecciona Extracción,
desactiva las otras fuentes e inicia inmediatamente esa descarga. Las casillas
se conservan para ejecutar cualquier combinación con el botón general.

Facebook conserva su dependencia operativa: descarga primero los posts y usa
ese CSV temporal como entrada del extractor de comentarios. Al terminar queda
un solo CSV canónico de Facebook por semana. Si no existen posts, confirma un
CSV canónico vacío y evita una llamada innecesaria al actor de comentarios.

La interfaz abre en la última semana terminada. La semana ISO se traduce a
lunes y domingo inclusivos. Antes de ejecutar se pueden revisar los comandos
con **Mostrar comandos**. La consola presenta la salida en tiempo real y
**Detener** termina el grupo de procesos activo.

## Uso por terminal

El mismo contrato está disponible sin GUI:

```bash
/home/emilio/anaconda3/envs/radar-v1/bin/python -B \
  scr/compartido/00_orquestador_general.py \
  --stages 1 \
  --week 2026-W33 \
  --sources youtube twitter medios facebook \
  --dry-run
```

El runner directo de extracción acepta las mismas fuentes:

```bash
/home/emilio/anaconda3/envs/radar-v1/bin/python -B \
  scr/extraccion/run_extraccion.py \
  --since 2026-08-10 \
  --before 2026-08-16 \
  --sources youtube medios \
  --dry-run
```
