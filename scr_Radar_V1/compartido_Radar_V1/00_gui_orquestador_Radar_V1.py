#!/usr/bin/env python3
"""Panel maestro Radar V1: ejecutar, simular, vigilar y reanudar."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
from queue import Queue,Empty
import sys
import threading
import tkinter as tk
from tkinter import ttk,scrolledtext,messagebox

REPO_ROOT=Path(__file__).resolve().parents[2]
def load_orchestrator_module():
    path=Path(__file__).with_name('00_orquestador_general_Radar_V1.py')
    spec=importlib.util.spec_from_file_location('radar_orquestador_general',path)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module);return module
ORQUESTADOR=load_orchestrator_module();PIPELINES=ORQUESTADOR.PIPELINES
from control_flujo_Radar_V1 import WorkflowEngine
STATES={'queued':'En espera','checking':'Comprobando','running':'En ejecución','completed':'Terminada','simulated':'Simulada','failed':'Error','cancelled':'Detenida'}

class OrquestadorGUI:
    def __init__(self,root):
        self.root=root;root.title('Radar V1 · Panel de control maestro');root.geometry('1220x940');root.minsize(1000,760)
        self.venv_python=str(ORQUESTADOR.PYTHON_EXECUTABLE)
        self.log_queue=Queue();self.worker=None;self.engine=None
        self.week_var=tk.StringVar(value=ORQUESTADOR.DEFAULT_GLOBAL_ISO_WEEK)
        a,b=ORQUESTADOR.iso_week_to_range(self.week_var.get());self.since_var=tk.StringVar(value=a);self.before_var=tk.StringVar(value=b)
        self.profile_var=tk.StringVar(value='historico');self.refresh_var=tk.BooleanVar(value=False);self.continue_on_error_var=tk.BooleanVar(value=False)
        self.stage_vars={s.code:tk.BooleanVar(value=s.key in {'preprocesamiento','validacion','ponderacion','nlp','particion','inspeccion','seleccion'}) for s in PIPELINES}
        self.extraction_source_vars={k:tk.BooleanVar(value=True) for k,_ in ORQUESTADOR.EXTRACTION_SOURCES}
        self.stage_checks={};self.status_labels={};self.source_run_buttons={};self.control_buttons=[]
        self.resume_var=tk.StringVar(value='validacion');self.summary_var=tk.StringVar(value='Listo. Selecciona las etapas y simula o ejecuta el flujo.')
        self.build_ui();self.refresh_stage_status();self.restore_last_status();root.after(80,self.process_log_queue);root.protocol('WM_DELETE_WINDOW',self.on_close)

    def button(self,parent,text,command):
        b=ttk.Button(parent,text=text,command=command);b.pack(side=tk.LEFT,padx=3,pady=2);self.control_buttons.append(b);return b

    def build_ui(self):
        body=ttk.Frame(self.root,padding=10);body.pack(fill=tk.BOTH,expand=True);body.columnconfigure(0,weight=1);body.rowconfigure(4,weight=1)
        top=ttk.LabelFrame(body,text='Alcance y periodo',padding=6);top.grid(row=0,column=0,sticky='ew')
        ttk.Label(top,text='Perfil:').grid(row=0,column=0);ttk.Combobox(top,textvariable=self.profile_var,values=['historico','semanal'],state='readonly',width=12).grid(row=0,column=1)
        ttk.Label(top,text='Semana:').grid(row=0,column=2);ttk.Entry(top,textvariable=self.week_var,width=10).grid(row=0,column=3)
        ttk.Button(top,text='Aplicar',command=self.apply_week).grid(row=0,column=4,padx=4)
        ttk.Label(top,text='Desde:').grid(row=0,column=5);ttk.Entry(top,textvariable=self.since_var,width=12).grid(row=0,column=6)
        ttk.Label(top,text='Hasta:').grid(row=0,column=7);ttk.Entry(top,textvariable=self.before_var,width=12).grid(row=0,column=8)
        ttk.Label(top,text='Histórico: 83 semanas/cuatro fuentes para NLP. El periodo semanal controla descargas y procesamiento semanal.').grid(row=1,column=0,columnspan=9,sticky='w',pady=4)
        sources=ttk.Frame(body);sources.grid(row=1,column=0,sticky='ew',pady=4)
        for key,label in ORQUESTADOR.EXTRACTION_SOURCES:ttk.Checkbutton(sources,text=label,variable=self.extraction_source_vars[key]).pack(side=tk.LEFT,padx=8)
        panes=ttk.Panedwindow(body,orient=tk.HORIZONTAL);panes.grid(row=2,column=0,sticky='nsew')
        stages=ttk.LabelFrame(panes,text='Llaves del flujo · cada etapa puede ejecutarse sola',padding=5);panes.add(stages,weight=1)
        monitor=ttk.LabelFrame(panes,text='Pantalla de control',padding=5);panes.add(monitor,weight=1)
        for row,stage in enumerate(PIPELINES):
            check=ttk.Checkbutton(stages,text=stage.code+'. '+stage.label,variable=self.stage_vars[stage.code]);check.grid(row=row,column=0,sticky='w',pady=1);self.stage_checks[stage.code]=check
            label=ttk.Label(stages,text='');label.grid(row=row,column=1,sticky='w',padx=8);self.status_labels[stage.code]=label
        self.monitor=ttk.Treeview(monitor,columns=('state',),show='tree headings',height=13)
        self.monitor.heading('#0',text='Etapa');self.monitor.heading('state',text='Estado');self.monitor.column('#0',width=230);self.monitor.column('state',width=130)
        self.monitor.pack(fill=tk.BOTH,expand=True)
        for stage in PIPELINES:self.monitor.insert('','end',iid=stage.key,text=stage.label,values=('En espera',))
        self.monitor.bind('<<TreeviewSelect>>',self.show_stage_details)
        self.details_var=tk.StringVar(value='Selecciona una etapa en esta pantalla para consultar su alcance y entradas.')
        self.details_text=scrolledtext.ScrolledText(monitor,height=5,wrap=tk.WORD,state=tk.DISABLED,font=('TkDefaultFont',9))
        self.details_text.pack(fill=tk.X,pady=5)
        self.set_stage_details(self.details_var.get())
        controls=ttk.Frame(body);controls.grid(row=3,column=0,sticky='ew',pady=5)
        presets=ttk.Frame(controls);presets.pack(fill=tk.X)
        self.button(presets,'Corpus existente',self.select_existing)
        self.button(presets,'Todas disponibles',self.select_all)
        self.button(presets,'Sólo extracción',self.select_extraction_only)
        self.button(presets,'Limpiar selección',self.select_none)
        ttk.Label(presets,text='Reiniciar desde:').pack(side=tk.LEFT,padx=(15,3))
        ttk.Combobox(presets,textvariable=self.resume_var,values=[s.key for s in PIPELINES],state='readonly',width=17).pack(side=tk.LEFT)
        self.button(presets,'Preparar reinicio',self.select_from_stage)
        run=ttk.Frame(controls);run.pack(fill=tk.X)
        self.dry_button=self.button(run,'Simular y comprobar',lambda:self.start_execution(dry_run=True))
        self.run_button=self.button(run,'Ejecutar seleccionadas',self.start_execution)
        self.test_button=self.button(run,'Pruebas del panel y pipeline',self.start_tests)
        self.button(run,'Actualizar documentación',self.start_documentation)
        self.stop_button=ttk.Button(run,text='Detener',command=self.stop_execution,state=tk.DISABLED);self.stop_button.pack(side=tk.LEFT,padx=3)
        options=ttk.Frame(controls);options.pack(fill=tk.X)
        ttk.Checkbutton(options,text='Renovar TXT/análisis con respaldo',variable=self.refresh_var).pack(side=tk.LEFT,padx=8)
        ttk.Checkbutton(options,text='Continuar si falla',variable=self.continue_on_error_var).pack(side=tk.LEFT)
        logs=ttk.LabelFrame(body,text='Terminal en tiempo real · registro persistente',padding=5);logs.grid(row=4,column=0,sticky='nsew');logs.rowconfigure(0,weight=1);logs.columnconfigure(0,weight=1)
        self.log=scrolledtext.ScrolledText(logs,height=13,wrap=tk.WORD,state=tk.DISABLED,font=('TkFixedFont',10));self.log.grid(row=0,column=0,sticky='nsew')
        ttk.Label(body,textvariable=self.summary_var).grid(row=5,column=0,sticky='w',pady=4)

    def apply_week(self):
        try:a,b=ORQUESTADOR.iso_week_to_range(self.week_var.get());self.since_var.set(a);self.before_var.set(b)
        except ValueError as e:messagebox.showerror('Semana inválida',str(e))
    def selected_stages(self):return [s for s in PIPELINES if self.stage_vars[s.code].get()]
    def selected_extraction_sources(self):return tuple(k for k,v in self.extraction_source_vars.items() if v.get())
    def select_none(self):
        for v in self.stage_vars.values():v.set(False)
    def select_all(self):
        for s in PIPELINES:self.stage_vars[s.code].set(ORQUESTADOR.stage_status(s)[0])
    def select_existing(self):
        for s in PIPELINES:self.stage_vars[s.code].set(s.key in {'preprocesamiento','validacion','ponderacion','nlp','particion','inspeccion','seleccion'})
    def select_extraction_only(self):
        self.profile_var.set('semanal')
        for s in PIPELINES:self.stage_vars[s.code].set(s.key=='extraccion')
    def select_from_stage(self):
        chosen=ORQUESTADOR.PIPELINES_BY_KEY[self.resume_var.get()]
        checkpoint=ORQUESTADOR.AUDIT_DIR/('control_'+chosen.key+'_actual_Radar_V1.json')
        if checkpoint.exists() and hasattr(self,'profile_var'):
            self.restore_parameters(json.loads(checkpoint.read_text()))
        for s in PIPELINES:self.stage_vars[s.code].set(int(s.code)>=int(chosen.code) and ORQUESTADOR.stage_status(s)[0])
    def refresh_stage_status(self):
        for s in PIPELINES:
            available,_=ORQUESTADOR.stage_status(s);self.status_labels[s.code].configure(text='Disponible' if available else 'Pendiente de implementar')
            self.stage_checks[s.code].state(['!disabled'] if available else ['disabled'])
            if not available:self.stage_vars[s.code].set(False);self.monitor.set(s.key,'state','No implementada')
    def show_stage_details(self,event=None):
        selected=self.monitor.selection()
        if not selected or selected[0] not in ORQUESTADOR.PIPELINES_BY_KEY:return
        stage=ORQUESTADOR.PIPELINES_BY_KEY[selected[0]]
        products=', '.join(str(p.relative_to(REPO_ROOT)) for p in ORQUESTADOR.stage_outputs(stage)) or 'Pendiente de definir para esta etapa'
        self.set_stage_details(stage.description+'\nEntrada: '+', '.join(str(p.relative_to(REPO_ROOT)) for p in ORQUESTADOR.stage_inputs(stage))+'\nProductos: '+products+'\nPrograma: '+str(stage.relative_runner))
    def set_stage_details(self,text):
        self.details_var.set(text);self.details_text.configure(state=tk.NORMAL)
        self.details_text.delete('1.0',tk.END);self.details_text.insert('1.0',text);self.details_text.configure(state=tk.DISABLED)
    def restore_last_status(self):
        for stage in PIPELINES:
            audit=ORQUESTADOR.AUDIT_DIR/('control_'+stage.key+'_actual_Radar_V1.json')
            if audit.is_file():
                try:
                    item=json.loads(audit.read_text());self.monitor.set(stage.key,'state',STATES.get(item['status'],item['status']))
                    if item['status'] in {'failed','cancelled'}:self.resume_var.set(stage.key)
                except (ValueError,KeyError):pass
        path=REPO_ROOT/'state/ejecuciones_Radar_V1/ultima_ejecucion_Radar_V1.json'
        if not path.exists():return
        try:
            report=json.loads(path.read_text())
            self.restore_parameters(report)
            for key,row in report['stages'].items():
                if self.monitor.exists(key):self.monitor.set(key,'state',STATES.get(row['status'],row['status']))
                if row['status'] in {'failed','cancelled','running'} and key in ORQUESTADOR.PIPELINES_BY_KEY:self.resume_var.set(key);break
            self.summary_var.set('Última ejecución: '+report['status']+'. Puedes preparar un reinicio desde la etapa elegida.')
        except (ValueError,KeyError):self.summary_var.set('No se pudo leer el último estado; los registros permanecen conservados.')
    def restore_parameters(self,report):
        if report.get('profile') in {'historico','semanal'}:self.profile_var.set(report['profile'])
        if report.get('since') and report.get('before'):
            self.since_var.set(report['since']);self.before_var.set(report['before']);self.week_var.set(ORQUESTADOR.date_range_to_iso_week(report['since']))
        if report.get('sources'):
            for key,value in self.extraction_source_vars.items():value.set(key in report['sources'])
    def validated_period(self):return ORQUESTADOR.validate_date_range(self.since_var.get(),self.before_var.get())
    def start_tests(self):
        stage=ORQUESTADOR.PipelineSpec('T','pruebas','Pruebas del panel y pipeline',REPO_ROOT/'tests_Radar_V1/test_orquestador_radar_Radar_V1.py','Suite local sin descargas.')
        if not self.monitor.exists('pruebas'):self.monitor.insert('','end',iid='pruebas',text=stage.label,values=('En espera',))
        self.start_execution(stages=[stage])
    def start_documentation(self):
        stage=ORQUESTADOR.PipelineSpec('D','documentacion','Actualizar documentación',ORQUESTADOR.SCR_DIR/'operaciones_Radar_V1/actualizar_documentacion_Radar_V1.py','Actualiza el estado y las rutas del repositorio.')
        if not self.monitor.exists('documentacion'):self.monitor.insert('','end',iid='documentacion',text=stage.label,values=('En espera',))
        self.start_execution(stages=[stage])
    def start_execution(self,*,dry_run=False,stages=None):
        if self.worker and self.worker.is_alive():return
        stages=stages or self.selected_stages()
        if not stages:messagebox.showwarning('Sin etapas','Selecciona al menos una etapa.');return
        try:since,before=self.validated_period()
        except ValueError as e:messagebox.showerror('Periodo inválido',str(e));return
        sources=self.selected_extraction_sources()
        if any(s.key in {'extraccion','procesar_csv','preprocesamiento'} for s in stages) and not sources:messagebox.showwarning('Sin fuentes','Selecciona al menos una fuente.');return
        self.engine=WorkflowEngine(ORQUESTADOR,self.log_queue.put)
        options=dict(dry_run=dry_run,profile=self.profile_var.get(),refresh=self.refresh_var.get(),continue_on_error=self.continue_on_error_var.get(),extraction_sources=sources)
        for b in self.control_buttons:b.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL)
        for stage in stages:self.monitor.set(stage.key,'state','En espera')
        self.summary_var.set('Simulación sin descargas' if dry_run else 'Ejecución iniciada')
        self.worker=threading.Thread(target=self.run_stages,args=(stages,since,before,options),daemon=True);self.worker.start()
    def run_stages(self,stages,since,before,options):
        try:self.engine.run(stages,since,before,**options)
        except BaseException as e:self.log_queue.put({'type':'line','text':'ERROR DEL PANEL: '+str(e)+'\n'});self.log_queue.put({'type':'finished','status':'failed','run_id':''})
    def stop_execution(self):
        if self.engine:self.engine.cancel();self.summary_var.set('Deteniendo el grupo de procesos…')
    def process_log_queue(self):
        try:
            while True:
                e=self.log_queue.get_nowait()
                if e['type']=='line':self.append_log(e['text'])
                elif e['type']=='stage':
                    if self.monitor.exists(e['key']):
                        self.monitor.set(e['key'],'state',STATES.get(e['status'],e['status']));self.monitor.see(e['key'])
                    self.summary_var.set(e['label']+': '+STATES.get(e['status'],e['status']))
                    if e['status'] in {'failed','cancelled'} and e['key'] in ORQUESTADOR.PIPELINES_BY_KEY:self.resume_var.set(e['key'])
                elif e['type']=='finished':
                    for b in self.control_buttons:b.configure(state=tk.NORMAL)
                    self.stop_button.configure(state=tk.DISABLED);self.summary_var.set('Resultado: '+e['status']+' · ejecución '+e.get('run_id',''))
        except Empty:pass
        self.root.after(80,self.process_log_queue)
    def append_log(self,text,tag=None):
        self.log.configure(state=tk.NORMAL);self.log.insert(tk.END,text);self.log.see(tk.END);self.log.configure(state=tk.DISABLED)
    def on_close(self):
        if self.worker and self.worker.is_alive():self.stop_execution()
        self.root.destroy()

def main():
    root=tk.Tk();OrquestadorGUI(root);root.mainloop()
if __name__=='__main__':main()
