from __future__ import annotations
import importlib.util,json,subprocess,sys,tempfile,unittest
import threading,time
from pathlib import Path
from queue import Queue
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
SHARED=ROOT/'scr_Radar_V1/compartido_Radar_V1'
sys.path.insert(0,str(SHARED))
from control_flujo_Radar_V1 import WorkflowEngine,digest

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module);return module
GUI=load('radar_gui_master_test',SHARED/'00_gui_orquestador_Radar_V1.py')
DOC=load('radar_doc_master_test',ROOT/'scr_Radar_V1/operaciones_Radar_V1/actualizar_documentacion_Radar_V1.py')

class Var:
    def __init__(self,value=None):self.value=value
    def get(self):return self.value
    def set(self,value):self.value=value
class Widget:
    def __init__(self):self.state={};self.text=''
    def configure(self,**kwargs):self.state.update(kwargs)
    def insert(self,*args):self.text+=args[-1]
    def see(self,*args):pass
class Monitor:
    def __init__(self,keys):self.rows={k:'' for k in keys}
    def exists(self,key):return key in self.rows
    def set(self,key,column,value):self.rows[key]=value
    def see(self,key):pass

class ControlPanelTests(unittest.TestCase):
    def fixture(self,root,scripts,dependencies=None):
        stages=[]
        for i,(key,text) in enumerate(scripts.items()):
            path=root/(key+'_Radar_V1.py');path.write_text(text)
            stages.append(SimpleNamespace(code=str(i+1),key=key,label=key,runner=path))
        catalog=SimpleNamespace(REPO_ROOT=root,DATA_DIR=root/'datos_Radar_V1',SCR_DIR=root/'scr_Radar_V1',AUDIT_DIR=root/'audit_Radar_V1',STAGE_DEPENDENCIES=dependencies or {},
          build_stage_commands=lambda s,a,b,**k:[([sys.executable,str(s.runner)],{})],stage_inputs=lambda s:[],render_command=lambda c:' '.join(c))
        return stages,catalog

    def test_dry_run_never_launches_a_process_and_records_simulation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);stages,cat=self.fixture(root,{'a':"raise AssertionError('No ejecutar')\n"})
            events=[];engine=WorkflowEngine(cat,events.append)
            with patch('control_flujo_Radar_V1.subprocess.Popen',side_effect=AssertionError('No lanzar')):
                self.assertEqual(engine.run(stages,'2026-04-27','2026-05-03',dry_run=True),0)
            self.assertEqual(engine.report['stages']['a']['status'],'simulated')
            self.assertEqual(engine.report['mode'],'dry_run')
            saved=json.loads((engine.state_dir/'ultima_ejecucion_Radar_V1.json').read_text())
            self.assertEqual(saved['status'],'completed')

    def test_stream_failure_dependency_block_and_restart(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);flag=root/'should_not_run'
            stages,cat=self.fixture(root,{'a':"print('primera linea',flush=True)\nraise SystemExit(2)\n",'b':f"from pathlib import Path\nPath({str(flag)!r}).write_text('bad')\n"},{'b':['a']})
            events=[];engine=WorkflowEngine(cat,events.append)
            self.assertEqual(engine.run(stages,'2026-04-27','2026-05-03',continue_on_error=True),1)
            self.assertFalse(flag.exists());self.assertIn('bloqueada',engine.report['stages']['b']['error'])
            self.assertTrue(any(e['type']=='line' and 'primera linea' in e['text'] for e in events))
            stages[0].runner.write_text("print('reanudada',flush=True)\n")
            self.assertEqual(engine.run([stages[0]],'2026-04-27','2026-05-03'),0)
            self.assertEqual(list(engine.report['stages']),['a'])
            self.assertEqual(len(list(engine.state_dir.glob('*_Radar_V1.log'))),2)

    def test_failure_restores_prior_output_and_removes_partial_files(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);out=root/'output_Radar_V1';out.mkdir();(out/'original_Radar_V1.csv').write_text('original')
            stages,cat=self.fixture(root,{'a':f"from pathlib import Path\np=Path({str(out)!r});p.mkdir();(p/'partial_Radar_V1.csv').write_text('partial');raise SystemExit(1)\n"})
            stages[0].key='particion'
            cat.build_stage_commands=lambda s,a,b,**k:[([sys.executable,str(s.runner),'--output-dir',str(out)],{})]
            engine=WorkflowEngine(cat,lambda e:None)
            self.assertEqual(engine.run(stages,'2026-04-27','2026-05-03',refresh=True),1)
            self.assertEqual((out/'original_Radar_V1.csv').read_text(),'original')
            self.assertFalse((out/'partial_Radar_V1.csv').exists())

    def test_text_refresh_backup_preserves_csv_and_restores_prior_txt(self):
        from output_naming_Radar_V1 import build_week_folder_name,build_source_filename
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);_,cat=self.fixture(root,{})
            cat.SCR_DIR=ROOT/'scr_Radar_V1'
            week=build_week_folder_name('2026-04-27','2026-05-03')
            folder=root/'processed_Radar_V1/youtube_semanal_procesado_Radar_V1'/week;folder.mkdir(parents=True)
            csvfile=folder/(build_source_filename(week,'youtube')+'.csv');csvfile.write_text('comment_text,published_at,query\n')
            txt=csvfile.with_suffix('.txt');txt.write_text('original\n')
            before=csvfile.read_bytes();engine=WorkflowEngine(cat,lambda e:None)
            command=[sys.executable,'promoter_Radar_V1.py','--processed-dir',str(root/'processed_Radar_V1'),'--sources','youtube','--all-weeks','--overwrite']
            records=engine.backup_texts(command);txt.write_text('nuevo\n');engine.restore_texts(records)
            self.assertEqual(txt.read_text(),'original\n');self.assertEqual(csvfile.read_bytes(),before)

    def test_gui_dry_action_updates_terminal_and_stage_monitor(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);stages,cat=self.fixture(root,{'dry':"raise RuntimeError('no ejecutar')\n"})
            gui=GUI.OrquestadorGUI.__new__(GUI.OrquestadorGUI)
            gui.worker=None;gui.log_queue=Queue();gui.selected_stages=lambda:stages
            gui.validated_period=lambda:('2026-04-27','2026-05-03');gui.selected_extraction_sources=lambda:('youtube',)
            gui.profile_var=Var('historico');gui.refresh_var=Var(False);gui.continue_on_error_var=Var(False)
            gui.control_buttons=[Widget()];gui.stop_button=Widget();gui.monitor=Monitor(['dry']);gui.summary_var=Var();gui.resume_var=Var()
            gui.root=SimpleNamespace(after=lambda *a:None);gui.log=Widget()
            with patch.object(GUI,'ORQUESTADOR',cat),patch('control_flujo_Radar_V1.subprocess.Popen',side_effect=AssertionError('No ejecutar')):
                gui.start_execution(dry_run=True);gui.worker.join(5);self.assertFalse(gui.worker.is_alive());gui.process_log_queue()
            self.assertEqual(gui.monitor.rows['dry'],'Simulada')
            self.assertIn('dry_Radar_V1.py',gui.log.text)
            self.assertIn('completed',gui.summary_var.get())
            self.assertEqual(gui.control_buttons[0].state['state'],'normal')

    def test_gui_restart_selects_all_available_downstream_operations(self):
        gui=GUI.OrquestadorGUI.__new__(GUI.OrquestadorGUI);gui.resume_var=Var('particion')
        gui.stage_vars={s.code:Var(False) for s in GUI.PIPELINES}
        gui.select_from_stage()
        self.assertEqual([s.key for s in gui.selected_stages()],['particion','inspeccion','seleccion'])

    def test_restart_restores_checkpoint_period_profile_and_sources(self):
        gui=GUI.OrquestadorGUI.__new__(GUI.OrquestadorGUI);gui.resume_var=Var('particion')
        gui.stage_vars={s.code:Var(False) for s in GUI.PIPELINES}
        gui.profile_var=Var('historico');gui.since_var=Var('');gui.before_var=Var('');gui.week_var=Var('')
        gui.extraction_source_vars={k:Var(True) for k,_ in GUI.ORQUESTADOR.EXTRACTION_SOURCES}
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            (folder/'control_particion_actual_Radar_V1.json').write_text(json.dumps({'profile':'semanal','since':'2026-04-27','before':'2026-05-03','sources':['youtube']}))
            with patch.object(GUI.ORQUESTADOR,'AUDIT_DIR',folder):gui.select_from_stage()
        self.assertEqual(gui.profile_var.get(),'semanal');self.assertEqual(gui.since_var.get(),'2026-04-27')
        self.assertEqual(gui.before_var.get(),'2026-05-03');self.assertEqual(gui.selected_extraction_sources(),('youtube',))

    def test_native_tk_dry_button_and_status_monitor(self):
        try:window=GUI.tk.Tk()
        except GUI.tk.TclError as exc:self.skipTest('No hay servidor gráfico accesible: '+str(exc))
        self.addCleanup(window.destroy);window.withdraw()
        panel=GUI.OrquestadorGUI(window)
        self.assertEqual(len(panel.stage_checks),13)
        with tempfile.TemporaryDirectory() as d:
            stages,cat=self.fixture(Path(d),{'nlp':"raise AssertionError('No ejecutar')\n"})
            panel.selected_stages=lambda:stages
            panel.validated_period=lambda:('2026-04-27','2026-05-03')
            with patch.object(GUI,'ORQUESTADOR',cat),patch('control_flujo_Radar_V1.subprocess.Popen',side_effect=AssertionError('No lanzar')):
                panel.dry_button.invoke();deadline=time.monotonic()+5
                while panel.worker.is_alive() and time.monotonic()<deadline:window.update();time.sleep(.01)
                self.assertFalse(panel.worker.is_alive());panel.process_log_queue()
            self.assertEqual(panel.monitor.set('nlp','state'),'Simulada')
            self.assertEqual(panel.engine.report['mode'],'dry_run')

    def test_gui_test_command_runs_local_suite_not_a_download(self):
        stage=GUI.ORQUESTADOR.PipelineSpec('T','pruebas','tests',ROOT/'tests_Radar_V1/test_orquestador_radar_Radar_V1.py','')
        command,_=GUI.ORQUESTADOR.build_pipeline(stage,'2026-04-27','2026-05-03')
        self.assertEqual(command[1:4],['-m','unittest','discover'])
        self.assertNotIn('--since',command)

    def test_cancellation_stops_the_process_and_records_a_restartable_state(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);stages,cat=self.fixture(root,{'slow':"import time\nprint('activo',flush=True)\ntime.sleep(30)\n"})
            events=[];engine=WorkflowEngine(cat,events.append)
            worker=threading.Thread(target=lambda:engine.run(stages,'2026-04-27','2026-05-03'))
            worker.start()
            deadline=time.monotonic()+5
            while not any(e['type']=='line' and e['text']=='activo\n' for e in events) and time.monotonic()<deadline:time.sleep(.01)
            engine.cancel();worker.join(5)
            self.assertFalse(worker.is_alive());self.assertEqual(engine.report['status'],'cancelled')
            self.assertEqual(engine.report['stages']['slow']['status'],'cancelled')

    def test_source_contract_brands_week_and_filename_once(self):
        from output_naming_Radar_V1 import build_week_folder_name,build_source_filename
        week=build_week_folder_name('2026-04-27','2026-05-03')
        filename=build_source_filename(week,'facebook')
        self.assertTrue(week.endswith('_Radar_V1'));self.assertTrue(filename.endswith('_Radar_V1'))
        self.assertEqual(filename.count('_Radar_V1'),1)

    def test_source_discovery_uses_branded_csv_names(self):
        from output_naming_Radar_V1 import build_week_folder_name,build_source_filename
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);week=build_week_folder_name('2026-04-27','2026-05-03');folder=root/week;folder.mkdir()
            for source in ['youtube','twitter']:
                module=load('radar_discovery_'+source,ROOT/f'scr_Radar_V1/preprocesamiento_Radar_V1/procesar_{source}_semanal_Radar_V1.py')
                expected=folder/(build_source_filename(week,source)+'.csv');expected.write_text('header\n')
                (folder/('old_'+source+'.csv')).write_text('legacy\n')
                discover=getattr(module,'discover_'+source+'_files')
                self.assertEqual(discover(root,set()),[expected])

    def test_new_facebook_processing_never_loads_historical_registry(self):
        processor=load('radar_strict_fb_panel_test',ROOT/'scr_Radar_V1/preprocesamiento_Radar_V1/procesar_facebook_semanal_Radar_V1.py')
        from output_naming_Radar_V1 import build_week_folder_name,build_source_filename
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);week=build_week_folder_name('2026-04-27','2026-05-03');folder=root/week;folder.mkdir()
            path=folder/(build_source_filename(week,'facebook')+'.csv')
            path.write_text(','.join(processor.FACEBOOK_PROCESSED_COLUMNS)+'\n')
            with patch.object(processor,'load_historical_facebook_rows',side_effect=AssertionError('No consultar histórico')):
                result=processor.process_file(path,root/'out_Radar_V1',dry_run=True)
            self.assertEqual(result.status,'success_dry_run');self.assertFalse(result.historical_corpus)

    def test_missing_future_stage_cannot_be_reported_as_simulated_success(self):
        stage=GUI.ORQUESTADOR.PIPELINES_BY_KEY['insumo_tablero']
        with self.assertRaises(GUI.ORQUESTADOR.MissingStageRunner):
            GUI.ORQUESTADOR.build_stage_commands(stage,'2026-04-27','2026-05-03')

    def test_commit_documentation_guard_compares_the_staged_sources(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);subprocess.run(['git','init','-q',str(root)],check=True)
            code=root/'scr_Radar_V1/example_Radar_V1.py';code.parent.mkdir();code.write_text('value=1\n')
            doc=root/DOC.DOCS/DOC.ARCH;doc.parent.mkdir();doc.write_text('<!-- source-fingerprint: '+DOC.fingerprint(root)+' -->\n')
            subprocess.run(['git','add','.'],cwd=root,check=True)
            self.assertEqual(DOC.check_staged(root),0)
            code.write_text('value=2\n');subprocess.run(['git','add',str(code)],cwd=root,check=True)
            with self.assertRaisesRegex(ValueError,'no corresponde'):DOC.check_staged(root)

if __name__=='__main__':unittest.main()
