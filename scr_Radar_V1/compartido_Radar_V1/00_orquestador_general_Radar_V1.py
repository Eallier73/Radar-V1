#!/usr/bin/env python3
"""Catálogo del panel maestro y sus trece etapas de trabajo.

El módulo mantiene la coordinación separada de la implementación de cada etapa.
Cada etapa tiene un único punto de entrada (runner), de modo que sus scripts
internos pueden evolucionar sin convertir este archivo en otro pipeline monolítico.
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Sequence

SHARED_DIR = Path(__file__).resolve().parent
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from radar_paths_Radar_V1 import resolve_python_executable


REPO_ROOT = Path(__file__).resolve().parents[2]
SCR_DIR = REPO_ROOT / "scr_Radar_V1"
DATA_DIR = REPO_ROOT / "datos_Radar_V1"
PYTHON_EXECUTABLE = resolve_python_executable()


def _load_env_file(path: Path) -> None:
    """Carga variables simples sin sobrescribir las ya definidas."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            os.environ.setdefault(key, value.strip().strip("'\""))


for _env_path in (REPO_ROOT / ".env", REPO_ROOT / ".env.local"):
    _load_env_file(_env_path)


@dataclass(frozen=True)
class PipelineSpec:
    """Contrato de una etapa seleccionable."""

    code: str
    key: str
    label: str
    runner: Path
    description: str

    @property
    def filename(self) -> str:
        return self.runner.name

    @property
    def relative_runner(self) -> Path:
        try:
            return self.runner.relative_to(REPO_ROOT)
        except ValueError:
            return self.runner



def parse_iso_week(value: str) -> tuple[int, int]:
    raw = (value or "").strip().upper().replace("_", "-")
    if "-W" not in raw:
        raise ValueError("Formato inválido. Usa YYYY-Www, por ejemplo 2026-W14.")
    year_text, week_text = raw.split("-W", 1)
    try:
        year = int(year_text)
        week = int(week_text)
        date.fromisocalendar(year, week, 1)
    except ValueError as exc:
        raise ValueError(f"Semana ISO inválida: {value}") from exc
    return year, week

def iso_week_to_range(value: str) -> tuple[str, str]:
    year, week = parse_iso_week(value)
    since = date.fromisocalendar(year, week, 1)
    before = since + timedelta(days=6)
    return since.isoformat(), before.isoformat()

def date_range_to_iso_week(since: str) -> str:
    parsed = datetime.strptime(since, "%Y-%m-%d").date()
    iso = parsed.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"

def validate_date_range(since: str, before: str) -> tuple[str, str]:
    try:
        since_date = datetime.strptime(since, "%Y-%m-%d").date()
        before_date = datetime.strptime(before, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("Las fechas deben usar el formato YYYY-MM-DD.") from exc
    if since_date > before_date:
        raise ValueError("La fecha inicial no puede ser posterior a la final.")
    return since_date.isoformat(), before_date.isoformat()

def parse_pipeline_selection(raw: str) -> list[PipelineSpec]:
    normalized = (raw or "").strip().lower()
    if normalized in {"all", "todos", "*"}:
        return list(PIPELINES)

    selected: list[PipelineSpec] = []
    seen: set[str] = set()
    for part in normalized.split(","):
        token = part.strip()
        if not token:
            continue
        stage = PIPELINES_BY_CODE.get(token) or PIPELINES_BY_KEY.get(token)
        if stage is None:
            valid = ", ".join(stage.key for stage in PIPELINES)
            raise ValueError(f"Etapa desconocida: {token}. Opciones: {valid}.")
        if stage.code not in seen:
            selected.append(stage)
            seen.add(stage.code)
    if not selected:
        raise ValueError("No se seleccionó ninguna etapa.")
    return sorted(selected, key=lambda stage: int(stage.code))

def stage_status(stage: PipelineSpec) -> tuple[bool, str]:
    if stage.runner.is_file():
        return True, f"disponible: {stage.relative_runner}"
    return False, f"runner pendiente: {stage.relative_runner}"

def normalize_extraction_sources(
    raw_sources: Sequence[str] | None,
) -> tuple[str, ...]:
    if not raw_sources:
        return EXTRACTION_SOURCE_KEYS
    requested: list[str] = []
    for raw in raw_sources:
        requested.extend(
            token.strip().lower()
            for token in str(raw).split(",")
            if token.strip()
        )
    if any(token in {"all", "todas", "*"} for token in requested):
        return EXTRACTION_SOURCE_KEYS
    unknown = sorted(set(requested) - set(EXTRACTION_SOURCE_KEYS))
    if unknown:
        raise ValueError(
            "Fuentes de extracción desconocidas: "
            + ", ".join(unknown)
            + ". Opciones: "
            + ", ".join(EXTRACTION_SOURCE_KEYS)
        )
    selected = tuple(key for key in EXTRACTION_SOURCE_KEYS if key in requested)
    if not selected:
        raise ValueError("Selecciona al menos una fuente de extracción.")
    return selected

def render_command(cmd: Sequence[str]) -> str:
    return " ".join(shlex.quote(str(part)) for part in cmd)

def print_stage_catalog() -> None:
    for stage in PIPELINES:
        available, status = stage_status(stage)
        marker = "OK" if available else "PENDIENTE"
        print(f"{stage.code}. {stage.label:<18} [{marker}] {status}")

def _script(folder,name):
    return SCR_DIR/(folder+'_Radar_V1')/(name+'_Radar_V1.py')

AUDIT_DIR=REPO_ROOT/'documentos_Radar_V1/auditorias_Radar_V1'
STAGE_DEPENDENCIES={'procesar_csv':['extraccion'],'preprocesamiento':['procesar_csv'],'validacion':['preprocesamiento'],
 'ponderacion':['validacion'],'nlp':['validacion'],'particion':['nlp'],'inspeccion':['particion'],
 'seleccion':['particion','nlp'],'modelado':['seleccion'],'insumo_tablero':['modelado'],'tablero':['insumo_tablero'],'reporte':['tablero']}
PIPELINES=[
 PipelineSpec('1','extraccion','Extracción',_script('extraccion','run_extraccion'),'Descarga semanal de las fuentes seleccionadas.'),
 PipelineSpec('2','procesar_csv','Procesar CSV por fuente',_script('preprocesamiento','procesar_youtube_semanal'),'Normaliza CSV; Facebook nuevo aplica fechas estrictas.'),
 PipelineSpec('3','preprocesamiento','CSV → TXT',_script('preprocesamiento','promover_csv_a_texto'),'Limpieza ASCII; Medios: título y contenido desde CSV.'),
 PipelineSpec('4','validacion','Validar corpus',_script('preprocesamiento','validar_homogeneidad_semanal'),'Contratos, fechas, cobertura y correspondencia CSV/TXT.'),
 PipelineSpec('5','ponderacion','Balance y ponderaciones',_script('operaciones','analizar_balance_fuentes'),'Diagnóstico de fuentes; alpha=0.5 en indicadores con ajuste inicial de 56 semanas.'),
 PipelineSpec('6','nlp','NLP · tabla de indicadores',_script('nlp','construir_tabla_indicadores'),'Diccionarios, Original y temas; 83 semanas/cuatro fuentes.'),
 PipelineSpec('7','particion','Separar 56 / 14 / 13',_script('operaciones','generar_conjuntos_temporales'),'Divide la tabla existente sin reajustar valores.'),
 PipelineSpec('8','inspeccion','Inspección estadística',_script('operaciones','inspeccionar_indicadores'),'Descriptivos y regresiones exploratorias sólo con las 56 iniciales.'),
 PipelineSpec('9','seleccion','Redundancia y selección',_script('operaciones','seleccionar_indicadores'),'Horizontes 1–4; no abre prueba ni verificación.'),
 PipelineSpec('10','modelado','Modelado',_script('modelado','run_modelado'),'Pendiente: no hay modelo productivo aprobado.'),
 PipelineSpec('11','insumo_tablero','Tabla para tablero',_script('modelado','run_insumo_tablero'),'Pendiente: salida del modelo para tablero.'),
 PipelineSpec('12','tablero','Tablero',_script('tablero','run_tablero'),'Pendiente de implementación.'),
 PipelineSpec('13','reporte','Reporte',_script('reporte','run_reporte'),'Pendiente de implementación.'),
]
PIPELINES_BY_CODE={s.code:s for s in PIPELINES};PIPELINES_BY_KEY={s.key:s for s in PIPELINES}
STAGES=PIPELINES;STAGES_BY_CODE=PIPELINES_BY_CODE;STAGES_BY_KEY=PIPELINES_BY_KEY
EXTRACTION_SOURCES=(('youtube','YouTube'),('twitter','Twitter/X'),('medios','Medios'),('facebook','Facebook (posts y comentarios)'))
EXTRACTION_SOURCE_KEYS=tuple(k for k,_ in EXTRACTION_SOURCES)
last=date.today()-timedelta(days=date.today().weekday()+1)
DEFAULT_GLOBAL_ISO_WEEK=f'{last.isocalendar().year}-W{last.isocalendar().week:02d}'
class MissingStageRunner(FileNotFoundError):pass

def build_stage_commands(stage,since,before,*,require_runner=True,extraction_sources=None,continue_on_error=False,profile='historico',refresh=False):
    since,before=validate_date_range(since,before)
    if require_runner and not stage.runner.is_file():raise MissingStageRunner(stage_status(stage)[1])
    sources=normalize_extraction_sources(extraction_sources)
    cmd=[str(PYTHON_EXECUTABLE),str(stage.runner)];key=stage.key
    if key=='extraccion':
        cmd+=['--since',since,'--before',before,'--only-extract','--sources',*sources]
        if continue_on_error:cmd+=['--continue-on-error']
    elif key=='procesar_csv':
        plans=[]
        for source in sources:
            c=[str(PYTHON_EXECUTABLE),str(_script('preprocesamiento','procesar_'+source+'_semanal'))]
            if profile=='historico' and source!='medios':c+=['--all-weeks']
            elif profile=='historico' and source=='medios':
                from datetime import timedelta,date
                for path in sorted((DATA_DIR/'radar_semanal_extraido_Radar_V1').glob('*/*_medios_Radar_V1.csv')):
                    start=date.fromisoformat(path.parent.name[:10])
                    plans.append((c+['--since',str(start),'--before',str(start+timedelta(days=6))],{}))
                continue
            else:c+=['--since',since,'--before',before]
            if source=='facebook' and profile=='historico':c+=['--historical-corpus']
            if source in {'youtube','twitter'}:c+=['--overwrite']
            plans.append((c,{}))
        if not plans:raise ValueError('No hay CSV históricos de las fuentes seleccionadas; los TXT de Medios se conservan como histórico.')
        return plans
    elif key=='preprocesamiento':
        cmd+=['--processed-dir',str(DATA_DIR/'radar_semanal_procesado_Radar_V1')]
        cmd+=['--all-weeks'] if profile=='historico' else ['--since',since,'--before',before]
        cmd+=['--sources',*sources]
        if refresh:cmd+=['--overwrite']
    elif key=='validacion':
        cmd+=['--processed-dir',str(DATA_DIR/'radar_semanal_procesado_Radar_V1'),'--require-same-weeks','--require-nonempty-text','--accept-historical-media-txt','--audit-path',str(AUDIT_DIR/'validacion_corpus_actual_Radar_V1.json')]
        if profile!='historico':cmd+=['--weeks',since,'--sources',*sources]
    elif key=='ponderacion':cmd+=['--processed-dir',str(DATA_DIR/'radar_semanal_procesado_Radar_V1'),'--output-dir',str(DATA_DIR/'radar_analisis_Radar_V1/ponderacion_fuentes_Radar_V1')]
    elif key=='nlp':cmd+=['--processed-dir',str(DATA_DIR/'radar_semanal_procesado_Radar_V1'),'--resources-dir',str(DATA_DIR/'recursos_indicadores_Radar_V1'),'--output-dir',str(DATA_DIR/'radar_indicadores_Radar_V1'),'--reuse-existing']
    elif key=='particion':cmd+=['--table',str(DATA_DIR/'radar_indicadores_Radar_V1/archivo_Radar_V1/tabla_analisis_completa_83_semanas_Radar_V1.csv'),'--weights',str(DATA_DIR/'radar_indicadores_Radar_V1/pesos_fuentes_entrenamiento_Radar_V1.json'),'--output-dir',str(DATA_DIR/'radar_modelado_Radar_V1')]
    elif key in {'inspeccion','seleccion'}:
        cmd+=['--development-dir',str(DATA_DIR/'radar_modelado_Radar_V1/desarrollo_Radar_V1'),'--output-dir',str(DATA_DIR/('radar_analisis_Radar_V1/'+('inspeccion' if key=='inspeccion' else 'seleccion')+'_indicadores_Radar_V1'))]
        if key=='seleccion':cmd+=['--support-table',str(DATA_DIR/'radar_indicadores_Radar_V1/tabla_indicadores_83_semanas_Radar_V1.csv')]
    elif key=='pruebas':cmd=[str(PYTHON_EXECUTABLE),'-m','unittest','discover','-s',str(REPO_ROOT/'tests_Radar_V1'),'-v']
    elif key=='documentacion':pass
    else:cmd+=['--since',since,'--before',before]
    return [(cmd,{})]

def build_pipeline(stage,since,before,**kwargs):return build_stage_commands(stage,since,before,**kwargs)[0]
def stage_inputs(stage):
    p=DATA_DIR;proc=p/'radar_semanal_procesado_Radar_V1'
    return {'extraccion':[],'procesar_csv':[p/'radar_semanal_extraido_Radar_V1'],
      'preprocesamiento':[proc],'validacion':[proc],'ponderacion':[proc],
      'nlp':[proc,p/'recursos_indicadores_Radar_V1'],
      'particion':[p/'radar_indicadores_Radar_V1/archivo_Radar_V1/tabla_analisis_completa_83_semanas_Radar_V1.csv',p/'radar_indicadores_Radar_V1/pesos_fuentes_entrenamiento_Radar_V1.json'],
      'inspeccion':[p/'radar_modelado_Radar_V1/desarrollo_Radar_V1/entrenamiento_Radar_V1/indicadores_Radar_V1.csv'],
      'seleccion':[p/'radar_modelado_Radar_V1/desarrollo_Radar_V1/entrenamiento_Radar_V1/indicadores_Radar_V1.csv',p/'radar_indicadores_Radar_V1/tabla_indicadores_83_semanas_Radar_V1.csv']}.get(stage.key,[])
def execute_stages(stages,since,before,**kwargs):
    from control_flujo_Radar_V1 import WorkflowEngine
    return WorkflowEngine(sys.modules[__name__]).run(stages,since,before,**kwargs)
def stage_outputs(stage):
    p=DATA_DIR
    return {'extraccion':[p/'radar_semanal_extraido_Radar_V1'],
      'procesar_csv':[p/'radar_semanal_procesado_Radar_V1'],'preprocesamiento':[p/'radar_semanal_procesado_Radar_V1'],
      'validacion':[AUDIT_DIR/'validacion_corpus_actual_Radar_V1.json'],
      'ponderacion':[p/'radar_analisis_Radar_V1/ponderacion_fuentes_Radar_V1'],
      'nlp':[p/'radar_indicadores_Radar_V1'],'particion':[p/'radar_modelado_Radar_V1'],
      'inspeccion':[p/'radar_analisis_Radar_V1/inspeccion_indicadores_Radar_V1'],
      'seleccion':[p/'radar_analisis_Radar_V1/seleccion_indicadores_Radar_V1'],
      'documentacion':[REPO_ROOT/'documentos_Radar_V1']}.get(stage.key,[])
def parse_args(argv=None):
    p=argparse.ArgumentParser(description='Control maestro Radar V1')
    p.add_argument('--stages','--pipelines',default='validacion,ponderacion,nlp,particion,inspeccion,seleccion')
    p.add_argument('--week');p.add_argument('--since');p.add_argument('--before');p.add_argument('--sources',nargs='+')
    p.add_argument('--profile',choices=['historico','semanal'],default='historico')
    p.add_argument('--dry-run',action='store_true');p.add_argument('--refresh',action='store_true')
    p.add_argument('--continue-on-error',action='store_true');p.add_argument('--list',action='store_true')
    return p.parse_args(argv)
def main(argv=None):
    args=parse_args(argv)
    if args.list:print_stage_catalog();return 0
    if args.week and (args.since or args.before):raise SystemExit('No combines semana ISO y fechas')
    if bool(args.since)!=bool(args.before):raise SystemExit('Indica ambas fechas')
    since,before=(args.since,args.before) if args.since else iso_week_to_range(args.week or DEFAULT_GLOBAL_ISO_WEEK)
    return execute_stages(parse_pipeline_selection(args.stages),since,before,dry_run=args.dry_run,refresh=args.refresh,profile=args.profile,continue_on_error=args.continue_on_error,extraction_sources=args.sources)
if __name__=='__main__':raise SystemExit(main())
