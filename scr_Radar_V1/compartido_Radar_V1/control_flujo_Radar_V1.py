"""Motor único: planes, salida en vivo, estados, cancelación y auditorías."""
from __future__ import annotations
import hashlib
import importlib
import json
import os
import signal
import subprocess
import sys
import threading
import uuid
from datetime import datetime,timezone
from pathlib import Path

def now():return datetime.now(timezone.utc).isoformat()
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name('.'+path.name+'.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');temp.replace(path)

class WorkflowEngine:
    def __init__(self,catalog,emit=None,*,state_dir=None,audit_dir=None):
        self.catalog=catalog;self.emit=emit or self.console
        self.state_dir=Path(state_dir or catalog.REPO_ROOT/'state/ejecuciones_Radar_V1')
        self.audit_dir=Path(audit_dir or catalog.AUDIT_DIR)
        self.cancelled=threading.Event();self.process=None;self.report=None

    @staticmethod
    def console(event):
        if event['type']=='line':print(event['text'],end='',flush=True)
        elif event['type']=='stage':print(event['key']+': '+event['status'],flush=True)
        elif event['type']=='error':print(event['text'],flush=True)

    def cancel(self):
        self.cancelled.set()
        process=self.process
        if process and process.poll() is None:
            try:os.killpg(process.pid,signal.SIGTERM)
            except (ProcessLookupError,PermissionError):process.terminate()

    def save(self):
        write_json(self.state_dir/(self.report['run_id']+'_Radar_V1.json'),self.report)
        write_json(self.state_dir/'ultima_ejecucion_Radar_V1.json',self.report)

    def stage_event(self,stage,status,**extra):
        record=self.report['stages'][stage.key];record.update(status=status,updated_at=now(),**extra)
        self.save();self.emit({'type':'stage','key':stage.key,'label':stage.label,'status':status,**extra})

    def reusable(self,stage,command):
        """Comprueba salidas heredadas; no basta con que exista una carpeta."""
        key=stage.key
        if '--output-dir' not in command:return False
        output=Path(command[command.index('--output-dir')+1])
        if not output.is_dir():return False
        p=self.catalog.DATA_DIR
        if key=='nlp':return False  # El propio constructor verifica/reutiliza sus productos.
        audit=output/('auditoria_Radar_V1.json' if key=='particion' else 'diagnostico_ponderacion_fuentes_Radar_V1.json' if key=='ponderacion' else 'diagnostico_Radar_V1.json')
        if not audit.is_file():return False
        report=json.loads(audit.read_text())
        if key=='ponderacion':
            products=['diagnostico_ponderacion_fuentes_Radar_V1.json','pesos_fuentes_propuestos_Radar_V1.json','analisis_ponderacion_fuentes_Radar_V1.md']
            return all((output/name).is_file() for name in products) and bool(report.get('input_sha256')) and all(Path(a).is_file() and digest(a)==b for a,b in report['input_sha256'].items())
        if key=='particion':
            table=p/'radar_indicadores_Radar_V1/archivo_Radar_V1/tabla_analisis_completa_83_semanas_Radar_V1.csv'
            weights=p/'radar_indicadores_Radar_V1/pesos_fuentes_entrenamiento_Radar_V1.json'
            if report.get('input_table_sha256')!=digest(table) or report.get('input_weights_sha256')!=digest(weights):return False
            development=output/report['development_table'];copied=output/'desarrollo_Radar_V1/entrenamiento_Radar_V1/pesos_fuentes_Radar_V1.json'
            return development.is_file() and digest(development)==report['development_table_sha256'] and copied.is_file() and digest(copied)==digest(weights) and len(report.get('subsets',{}))==3 and all((output/r['table']).is_file() and digest(output/r['table'])==r['sha256'] for r in report['subsets'].values())
        training=p/'radar_modelado_Radar_V1/desarrollo_Radar_V1/entrenamiento_Radar_V1/indicadores_Radar_V1.csv'
        if report.get('input_sha256')!=digest(training):return False
        if report.get('target')!='Sentimiento_Conjunto_Original_Original':return False
        if key=='seleccion':
            sys.path.insert(0,str(self.catalog.SCR_DIR/'operaciones_Radar_V1'))
            selector=importlib.import_module('seleccionar_indicadores_Radar_V1')
            inputs=selector.load_inputs(training.parent.parent,p/'radar_indicadores_Radar_V1/tabla_indicadores_83_semanas_Radar_V1.csv')
            if inputs.evidence['support_prefix_sha256']!=report.get('support_prefix_sha256'):return False
        hashes=report.get('output_sha256',{})
        return bool(hashes) and all((output/a).is_file() and digest(output/a)==b for a,b in hashes.items())

    def archive_output(self,path):
        """Sólo salidas exclusivas; se restaura la carpeta si la operación falla."""
        import shutil
        path=Path(path)
        base=self.catalog.REPO_ROOT/'trash_Radar_V1/respaldos_historico_Radar_V1'/('salida_'+uuid.uuid4().hex+'_historico_Radar_V1')
        moved=[]
        for source in sorted(path.rglob('*')):
            if not source.is_file():continue
            rel=source.relative_to(path)
            parts=[]
            for part in rel.parts:
                q=Path(part);stem=q.stem.removesuffix('_Radar_V1')
                parts.append(stem+'_historico_Radar_V1'+q.suffix)
            target=base/Path(*parts);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
            moved.append({'original':str(source),'backup':str(target),'sha256':digest(source),'output_root':str(path)})
        write_json(base/'manifest_salida_historico_Radar_V1.json',{'files':moved,'created_at':now()})
        shutil.rmtree(path)
        return moved

    @staticmethod
    def restore_output(files):
        import shutil
        if files and Path(files[0]['output_root']).exists():shutil.rmtree(files[0]['output_root'])
        for item in files:
            target=Path(item['original']);target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(item['backup'],target)

    def backup_texts(self,command):
        """La renovación de TXT guarda los anteriores sin mover sus CSV."""
        import shutil
        sys.path.insert(0,str(self.catalog.SCR_DIR/'preprocesamiento_Radar_V1'))
        promoter=importlib.import_module('promover_csv_a_texto_Radar_V1')
        args=promoter.parse_args(command[2:])
        sources=promoter.normalize_sources(args.sources)
        selected,missing=promoter.discover_csv_files(args.processed_dir,sources,source_dir=args.source_dir,since=args.since,before=args.before,weeks=args.weeks,all_weeks=args.all_weeks)
        if missing:raise ValueError('; '.join(missing))
        base=self.catalog.REPO_ROOT/'trash_Radar_V1/respaldos_historico_Radar_V1'/('textos_'+uuid.uuid4().hex+'_historico_Radar_V1')
        records=[]
        for _,csv_path in selected:
            source=csv_path.with_suffix('.txt')
            item={'original':str(source),'existed':source.exists()}
            if source.exists():
                rel=source.relative_to(args.processed_dir)
                parts=[Path(p).stem.removesuffix('_Radar_V1')+'_historico_Radar_V1'+Path(p).suffix for p in rel.parts]
                target=base/Path(*parts);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
                item.update(backup=str(target),sha256=digest(source))
            records.append(item)
        write_json(base/'manifest_textos_historico_Radar_V1.json',{'files':records})
        return records

    @staticmethod
    def restore_texts(records):
        import shutil
        for item in records:
            target=Path(item['original'])
            if item['existed']:shutil.copy2(item['backup'],target)
            elif target.exists():target.unlink()

    def run(self,stages,since,before,*,dry_run=False,continue_on_error=False,extraction_sources=None,profile='historico',refresh=False):
        self.cancelled.clear()
        run_id=datetime.now().strftime('%Y%m%dT%H%M%S')+'_'+uuid.uuid4().hex[:8]
        self.report={'run_id':run_id,'started_at':now(),'mode':'dry_run' if dry_run else 'execution',
          'profile':profile,'since':since,'before':before,'sources':list(extraction_sources or getattr(self.catalog,'EXTRACTION_SOURCE_KEYS',[])),
          'refresh':refresh,'continue_on_error':continue_on_error,'status':'running','stages':{s.key:{'status':'queued','label':s.label} for s in stages}}
        self.state_dir.mkdir(parents=True,exist_ok=True)
        logfile=self.state_dir/(run_id+'_Radar_V1.log')
        errors=0;failed_keys=set();simulated_keys=set()
        def line(text):
            with logfile.open('a') as handle:handle.write(text)
            self.emit({'type':'line','text':text})
        self.save()
        for stage in stages:
            if self.cancelled.is_set():break
            self.stage_event(stage,'checking')
            backups=[];text_backups=[]
            try:
                failed_dependencies=set(getattr(self.catalog,'STAGE_DEPENDENCIES',{}).get(stage.key,[]))&failed_keys
                if failed_dependencies:raise RuntimeError('Etapa bloqueada por fallos anteriores: '+', '.join(sorted(failed_dependencies)))
                plans=self.catalog.build_stage_commands(stage,since,before,require_runner=True,extraction_sources=extraction_sources,continue_on_error=continue_on_error,profile=profile,refresh=refresh)
                missing=[str(p) for p in self.catalog.stage_inputs(stage) if not p.exists()]
                planned=dry_run and bool(set(getattr(self.catalog,'STAGE_DEPENDENCIES',{}).get(stage.key,[]))&simulated_keys)
                if missing and not planned:raise FileNotFoundError('Faltan entradas: '+', '.join(missing))
                if dry_run:
                    for cmd,_ in plans:
                        if cmd[1]!='-m' and not Path(cmd[1]).is_file():raise FileNotFoundError(cmd[1])
                        line('$ '+self.catalog.render_command(cmd)+'\n')
                    self.stage_event(stage,'simulated',commands=[c for c,_ in plans],input_validation='planned' if missing else 'existing')
                    simulated_keys.add(stage.key)
                else:
                    self.stage_event(stage,'running',started_at=now())
                    for command,env_updates in plans:
                        line('$ '+self.catalog.render_command(command)+'\n')
                        if stage.key=='preprocesamiento' and refresh:text_backups=self.backup_texts(command)
                        if stage.key in {'ponderacion','particion','inspeccion','seleccion'} and not refresh and self.reusable(stage,command):
                            line('Productos existentes verificados; no se recalcularon.\n');continue
                        if stage.key in {'ponderacion','nlp','particion','inspeccion','seleccion'}:
                            output=Path(command[command.index('--output-dir')+1])
                            if output.exists() and refresh:backups=self.archive_output(output)
                            elif output.exists() and stage.key!='nlp':raise ValueError('La salida no coincide con las entradas. Activa Recalcular con respaldo para renovarla.')
                        env={**os.environ,**env_updates,'PYTHONUNBUFFERED':'1','PYTHONDONTWRITEBYTECODE':'1'}
                        self.process=subprocess.Popen(command,cwd=self.catalog.REPO_ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1,start_new_session=True)
                        for text in self.process.stdout:line(text)
                        rc=self.process.wait();self.process=None
                        if rc:raise RuntimeError('La operación terminó con código '+str(rc))
                    self.stage_event(stage,'completed',finished_at=now())
                audit={**{k:self.report[k] for k in ['run_id','mode','profile','since','before','sources']},'stage':stage.key,'runner_sha256':digest(stage.runner),**self.report['stages'][stage.key]}
                write_json(self.audit_dir/'ejecuciones_Radar_V1'/(run_id+'_'+stage.key+'_Radar_V1.json'),audit)
                write_json(self.audit_dir/('control_'+stage.key+'_actual_Radar_V1.json'),audit)
            except Exception as exc:
                errors+=1
                failed_keys.add(stage.key)
                if backups:self.restore_output(backups)
                if text_backups:self.restore_texts(text_backups)
                status='cancelled' if self.cancelled.is_set() else 'failed'
                self.stage_event(stage,status,error=str(exc));line('ERROR: '+str(exc)+'\n')
                audit={**{k:self.report[k] for k in ['run_id','mode','profile','since','before','sources']},'stage':stage.key,**self.report['stages'][stage.key]}
                write_json(self.audit_dir/'ejecuciones_Radar_V1'/(run_id+'_'+stage.key+'_Radar_V1.json'),audit)
                write_json(self.audit_dir/('control_'+stage.key+'_actual_Radar_V1.json'),audit)
                if not continue_on_error:break
        self.report.update(status='cancelled' if self.cancelled.is_set() else 'failed' if errors else 'completed',finished_at=now(),log_path=str(logfile))
        self.save();self.emit({'type':'finished','status':self.report['status'],'run_id':run_id})
        return 1 if errors or self.cancelled.is_set() else 0
