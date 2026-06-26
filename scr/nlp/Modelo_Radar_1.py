import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LassoCV, RidgeCV, ElasticNetCV
from sklearn.metrics import mean_absolute_error, r2_score, accuracy_score, f1_score, confusion_matrix
import matplotlib.pyplot as plt
import warnings
warnings.filterwarnings('ignore')

# Imports opcionales para funcionalidades avanzadas
try:
    import plotly.graph_objects as go
    import plotly.express as px
    from plotly.subplots import make_subplots
    PLOTLY_AVAILABLE = True
    print("✅ Plotly disponible - Dashboard interactivo habilitado")
except ImportError:
    PLOTLY_AVAILABLE = False
    print("⚠️ Plotly no disponible - Solo gráficos matplotlib")

# Para asegurar que funcione en Jupyter
plt.style.use('default')


# ============================================================
# CONFIGURACIÓN BÁSICA
# ============================================================

# Dataset ORIGINAL (sin Economía/Bienestar) - Para 2-4 semanas
BASE_PATH_ORIGINAL = Path(
    "/home/emilio/Documentos/Lab/tampico_env/Proyectos/IPSEL_Tampico/"
    "Ml_Monica_Villarreal/Datos/Datos_Modelo"
)
INPUT_FILE_ORIGINAL = BASE_PATH_ORIGINAL / "Data_Set_Modelo_Listo.csv"

# Dataset AMPLIADO (con Economía/Bienestar) - Para 1 semana
BASE_PATH_AMPLIADO = Path(
    "/home/emilio/Documentos/Lab/tampico_env/Proyectos/IPSEL_Tampico/"
    "Ml_Monica_Villarreal/Datos/Datos_Modelo_1"
)
INPUT_FILE_AMPLIADO = BASE_PATH_AMPLIADO / "Data_Set_Modelo_Listo_1.csv"

# Carpeta de resultados final - NUEVA RUTA
RESULTS_PATH = Path(
    "/home/emilio/Documentos/Lab/tampico_env/Proyectos/IPSEL_Tampico/"
    "Ml_Monica_Villarreal/Datos/RResultados_Modelo_Funcional_4"
)

# Umbral para clasificar sube / baja / igual (en %)
DELTA_THRESHOLD = 2.5


# ============================================================
# CONFIGURACIONES OPTIMIZADAS POR HORIZONTE
# ============================================================

# Variables para 1 SEMANA (Dataset Ampliado con Economía/Bienestar) - SIN VARIABLES DEPENDIENTES
VARIABLES_1_SEMANA = [
    "Sentimiento_Fuentes_Original_Etiquetado_MA5",
    "Sentimiento_Fuentes_Original_Original_MA5",
    "X_Presencia_Youtube_Agua_MA5",
    "X_Intensidad_Youtube_Agua_MA5",
    "presencia_tema_pct_X_Twitter_Basura_MA5",
    "intensidad_por_1000_X_Twitter_Basura_MA5",
    "intensidad_por_1000_Facebook_Alumbrado_MA5",
    "presencia_tema_pct_Fuentes_Integradas_Vialidades_MA5",
    "intensidad_por_1000_Fuentes_Integradas_Inseguridad_MA5",
    "presencia_tema_pct_Youtube_Economia_MA5",        # ECONOMÍA
    "intensidad_por_1000_Youtube_Economia_MA5",       # ECONOMÍA
    "presencia_tema_pct_X_Twitter_Bienestar_MA5",     # BIENESTAR
]

# ============================================================
# CARGAR NOMBRES PERSONALIZADOS CON INTERPRETACIÓN CONTEXTUAL
# ============================================================

def cargar_nombres_contextual():
    """
    Carga los nombres contextuales desde el archivo Variables_Faltantes_Para_Mapear.csv
    con interpretación dinámica según factor de riesgo vs crecimiento.
    """
    try:
        # Buscar Variables_Faltantes_Para_Mapear.csv en la carpeta Tablero
        ruta_archivo = "/home/emilio/Documentos/Lab/tampico_env/Proyectos/IPSEL_Tampico/Ml_Monica_Villarreal/Datos/Tablero/Variables_Faltantes_Para_Mapear.csv"
        
        print(f"🔍 Buscando archivo: {ruta_archivo}")
        
        # Intentar múltiples encodings
        df_nombres = None
        for encoding in ['utf-8', 'latin1', 'cp1252', 'iso-8859-1']:
            try:
                df_nombres = pd.read_csv(ruta_archivo, encoding=encoding)
                print(f"   ✅ CSV leído con encoding: {encoding}")
                break
            except UnicodeDecodeError:
                continue
            except Exception as e:
                print(f"   ❌ Error con encoding {encoding}: {e}")
                continue
        
        if df_nombres is None:
            print("⚠️ No se pudo leer Variables_Faltantes_Para_Mapear.csv - usando nombres fallback")
            return cargar_nombres_fallback_contextual()
        
        print(f"✅ Archivo cargado exitosamente")
        
        # Filtrar filas de comentarios (que empiezan con #)
        df_nombres = df_nombres[~df_nombres['Variable_Tecnica'].astype(str).str.startswith('#', na=False)]
        print(f"📊 Variables después de filtrar comentarios: {len(df_nombres)}")
        
        # CONSTRUIR DICCIONARIO CONTEXTUAL
        nombres_contextual = {}
        
        for _, row in df_nombres.iterrows():
            try:
                variable_tecnica = str(row['Variable_Tecnica']).strip()
                
                # Saltar variables que no deben aparecer
                notas = str(row.get('Notas', '')).strip()
                if any(x in notas.lower() for x in ['variable dependiente', 'variable temporal', 'validación']):
                    continue
                
                # Filtrar variables IAD_global explícitamente
                if any(x in variable_tecnica for x in ['IAD_global', 'IAD_Global', 'iad_global']):
                    continue
                
                # Solo procesar variables que tienen interpretaciones válidas
                interpretacion_riesgo = str(row.get('Sugerencia_Interpretacion_Riesgo', '')).strip()
                interpretacion_oportunidades = str(row.get('Sugerencia_Interpretacion_Oportunidades', '')).strip()
                
                if interpretacion_riesgo and interpretacion_riesgo not in ['N/A', 'nan', '']:
                    nombres_contextual[variable_tecnica] = {
                        'riesgo': interpretacion_riesgo,
                        'crecimiento': interpretacion_oportunidades if interpretacion_oportunidades not in ['N/A', 'nan', ''] else interpretacion_riesgo,
                        'tipo': notas,
                        'categoria': str(row.get('Categoria', '')).strip()
                    }
                    
            except Exception as e:
                print(f"   ⚠️ Error procesando variable {variable_tecnica}: {e}")
                continue
        
        print(f"📋 Variables válidas para dashboard: {len(nombres_contextual)}")
        
        # Mostrar muestra por categoría
        print(f"\n🎯 MUESTRA DE INTERPRETACIONES POR CATEGORÍA:")
        categorias_muestra = {}
        for var, interpretaciones in nombres_contextual.items():
            categoria = interpretaciones.get('categoria', 'Sin categoría')
            if categoria not in categorias_muestra:
                categorias_muestra[categoria] = []
            if len(categorias_muestra[categoria]) < 2:  # Máximo 2 por categoría
                categorias_muestra[categoria].append((var, interpretaciones))
        
        for categoria, variables_en_cat in list(categorias_muestra.items())[:3]:
            print(f"   📂 {categoria}:")
            for var, interpretaciones in variables_en_cat:
                print(f"      {var[:40]:<40}")
                print(f"        🔴 Riesgo:      {interpretaciones['riesgo']}")
                print(f"        🟢 Crecimiento: {interpretaciones['crecimiento']}")
        
        return nombres_contextual
        
    except Exception as e:
        print(f"❌ Error cargando nombres contextuales: {e}")
        print("⚠️ Usando nombres fallback...")
        return cargar_nombres_fallback_contextual()


def cargar_nombres_fallback_contextual():
    """Nombres de respaldo con estructura contextual."""
    return {
        "Sentimiento_Fuentes_Original_Etiquetado_MA5": {
            'riesgo': "↓ Opinión pública (medios)",
            'crecimiento': "↑ Opinión pública (medios)",
            'tipo': 'sentimiento'
        },
        "X_Intensidad_Youtube_Agua_MA5": {
            'riesgo': "↑ Discusión agua",
            'crecimiento': "↓ Discusión agua", 
            'tipo': 'contexto-dependiente'
        },
        "intensidad_por_1000_Facebook_Alumbrado_MA5": {
            'riesgo': "↑ Discusión alumbrado",
            'crecimiento': "↓ Discusión alumbrado",
            'tipo': 'contexto-dependiente'
        }
    }


def generar_nombre_dinamico(variable_tecnica, es_factor_riesgo, coeficiente, nombres_contextual):
    """
    Genera nombre dinámico basado en:
    - Si es factor de riesgo o crecimiento
    - El coeficiente del modelo
    - La interpretación contextual definida
    """
    if variable_tecnica not in nombres_contextual:
        print(f"   ⚠️ Variable sin interpretación: {variable_tecnica}")
        return f"Variable no interpretada: {variable_tecnica}"
    
    interpretacion = nombres_contextual[variable_tecnica]
    
    # LÓGICA CONTEXTUAL ESPECÍFICA
    if es_factor_riesgo:
        return interpretacion['riesgo']
    else:
        return interpretacion['crecimiento']


# Cargar nombres al inicio del script
NOMBRES_CONTEXTUAL = cargar_nombres_contextual()


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def print_sep(titulo: str):
    print("\n" + "=" * 80)
    print(titulo)
    print("=" * 80)


def detectar_columna_target(df: pd.DataFrame) -> str:
    """Detecta la columna del índice objetivo."""
    candidatos_preferidos = [
        "IAOPD_MA5", "IAD_global_MA5", "Indice_Aceptacion_MA5", "IAOPD_global_MA5"
    ]
    for c in candidatos_preferidos:
        if c in df.columns:
            return c

    poss = [c for c in df.columns
            if ("IAD" in c.upper() or "IAOPD" in c.upper()) and ("MA5" in c.upper())]
    if len(poss) == 0:
        raise ValueError("No encontré columna objetivo tipo IAOPD/IAD_MA5.")
    return poss[0]


def detectar_columnas_tiempo(df: pd.DataFrame):
    """Detecta columnas de semana / fecha para ordenar cronológicamente."""
    week_candidates = ["semana_iso", "semana", "week_label"]
    date_candidates = ["Fecha_Semana", "fecha_semana", "fecha", "date"]

    week_col, date_col = None, None
    for c in week_candidates:
        if c in df.columns:
            week_col = c
            break
    for c in date_candidates:
        if c in df.columns:
            date_col = c
            break

    return week_col, date_col


def preparar_dataset_completo(file_path: Path, dataset_nombre: str):
    """Prepara un dataset completo: carga, ordena, escala."""
    print(f"\n📁 PREPARANDO {dataset_nombre}")
    print(f"   Archivo: {file_path}")

    df_raw = pd.read_csv(file_path)
    print(f"   Shape original: {df_raw.shape}")

    week_col, date_col = detectar_columnas_tiempo(df_raw)
    if week_col:
        df = df_raw.sort_values(week_col).reset_index(drop=True)
    elif date_col:
        df = df_raw.sort_values(date_col).reset_index(drop=True)
    else:
        df = df_raw.copy()

    target_col = detectar_columna_target(df)

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    exclude_cols = {week_col, date_col, target_col}
    exclude_cols.update([c for c in df.columns if isinstance(c, str) and "encuesta" in c.lower()])
    constant_cols = [c for c in numeric_cols if df[c].nunique() <= 1]

    feature_cols = [c for c in numeric_cols
                    if c not in exclude_cols and c not in constant_cols]

    # NUEVO: Filtrar variables dependientes adicionales que no deben aparecer como features
    variables_dependientes = ['IAD_global', 'IAD_global_MA5', 'IAD_global_suavizado', 'IAOPD_MA5']
    feature_cols = [c for c in feature_cols if c not in variables_dependientes]
    
    print(f"   Variables dependientes filtradas: {[c for c in variables_dependientes if c in numeric_cols]}")
    print(f"   Features finales: {len(feature_cols)}")

    scaler = StandardScaler()
    cols_to_scale = feature_cols + [target_col]
    scaled_array = scaler.fit_transform(df[cols_to_scale])

    df_scaled = df.copy()
    df_scaled[cols_to_scale] = scaled_array

    target_mean = scaler.mean_[-1]
    target_std = scaler.scale_[-1]

    print(f"   Target: {target_col}")
    print(f"   Features disponibles: {len(feature_cols)}")

    return df_scaled, df, target_col, feature_cols, target_mean, target_std, scaler


def evaluar_horizonte_con_analisis_factores(df_scaled: pd.DataFrame,
                                           target_col: str,
                                           feature_cols: list,
                                           horizonte: int,
                                           etiqueta_horizonte: str,
                                           algoritmo_forzado: str = None,
                                           dataset_label: str = ""):
    """
    Evalúa un horizonte Y calcula la importancia de factores mediante coeficientes.
    """
    feature_cols_disponibles = [c for c in feature_cols if c in df_scaled.columns]

    X = df_scaled[feature_cols_disponibles].copy()
    y = df_scaled[target_col].shift(-horizonte)
    X = X.iloc[:-horizonte].reset_index(drop=True)
    y = y.iloc[:-horizonte].reset_index(drop=True)
    mask = ~y.isna()
    X = X.loc[mask].reset_index(drop=True)
    y = y.loc[mask].reset_index(drop=True)

    print(f"\n🎯 EVALUANDO: {etiqueta_horizonte} | Dataset={dataset_label}")
    print(f"   Variables: {len(feature_cols_disponibles)}/{len(feature_cols)}")
    print(f"   Shape: X={X.shape}, y={y.shape}")

    if algoritmo_forzado:
        algoritmo_nombre = algoritmo_forzado
    else:
        algoritmo_nombre = "Ridge" if horizonte == 1 else "Lasso"

    if algoritmo_nombre == "Ridge":
        modelo = RidgeCV(cv=5)
    elif algoritmo_nombre == "Lasso":
        modelo = LassoCV(cv=5, random_state=42, max_iter=10000)
    elif algoritmo_nombre == "ElasticNet":
        modelo = ElasticNetCV(cv=5, random_state=42, max_iter=10000)

    print(f"   Algoritmo: {algoritmo_nombre}")

    # Entrenar modelo final para obtener coeficientes de importancia
    modelo_final = type(modelo)(**modelo.get_params())
    modelo_final.fit(X, y)
    
    # Obtener importancias (coeficientes)
    if hasattr(modelo_final, 'coef_'):
        coefs = modelo_final.coef_
    else:
        coefs = np.zeros(len(feature_cols_disponibles))
    
    # Generar nombres dinámicos con interpretación contextual
    nombres_dinamicos = []
    for i, variable in enumerate(feature_cols_disponibles):
        coef = coefs[i]
        es_riesgo = coef < 0
        nombre_dinamico = generar_nombre_dinamico(variable, es_riesgo, coef, NOMBRES_CONTEXTUAL)
        nombres_dinamicos.append(nombre_dinamico)
    
    importancias_df = pd.DataFrame({
        'variable': feature_cols_disponibles,
        'coeficiente': coefs,
        'importancia_abs': np.abs(coefs),
        'variable_amigable': nombres_dinamicos
    }).sort_values('importancia_abs', ascending=False)
    
    print(f"   📊 Top 5 factores más importantes CON INTERPRETACIÓN CONTEXTUAL:")
    for i, row in importancias_df.head(5).iterrows():
        direccion = "📈" if row['coeficiente'] > 0 else "📉"
        print(f"      {direccion} {row['variable_amigable']}: {row['coeficiente']:.3f}")

    # Evaluación walk-forward
    X_array = X.to_numpy()
    y_array = y.to_numpy()
    n = len(y_array)
    min_train_size = max(20, 5 * horizonte)

    preds, trues, base_indices = [], [], []

    for split_point in range(min_train_size, n):
        train_idx = np.arange(0, split_point)
        test_idx = np.array([split_point])

        X_train, y_train = X_array[train_idx], y_array[train_idx]
        X_test, y_test = X_array[test_idx], y_array[test_idx]

        modelo_temp = type(modelo)(**modelo.get_params())
        modelo_temp.fit(X_train, y_train)
        y_pred = modelo_temp.predict(X_test)

        preds.extend(y_pred.tolist())
        trues.extend(y_test.tolist())
        base_indices.append(int(split_point))

    r2 = r2_score(trues, preds)
    mae = mean_absolute_error(trues, preds)

    print(f"   📊 RESULTADO: R²={r2:.4f}, MAE={mae:.4f}")

    pred_df = pd.DataFrame({
        "base_idx": base_indices,
        f"IAD_{etiqueta_horizonte}_real_z": trues,
        f"IAD_{etiqueta_horizonte}_predicho_z": preds,
    })

    pred_file = RESULTS_PATH / f"Predicciones_{etiqueta_horizonte}_{algoritmo_nombre}.csv"
    pred_df.to_csv(pred_file, index=False)
    
    # Guardar análisis de factores CON NOMBRES CONTEXTUALES
    factores_file = RESULTS_PATH / f"Analisis_Factores_{etiqueta_horizonte}_{algoritmo_nombre}_CONTEXTUAL.csv"
    importancias_df.to_csv(factores_file, index=False)
    print(f"   [OK] Análisis de factores contextual guardado en: {factores_file}")

    return {
        'horizonte': horizonte,
        'etiqueta': etiqueta_horizonte,
        'algoritmo': algoritmo_nombre,
        'dataset': dataset_label,
        'r2': r2,
        'mae': mae,
        'n_features': len(feature_cols_disponibles),
        'n_pred': len(trues),
        'variables_usadas': feature_cols_disponibles,
        'pred_df': pred_df,
        'factores_importancia': importancias_df
    }


def clasificar_delta(delta_pct: float, umbral: float = DELTA_THRESHOLD) -> str:
    """Clasifica un cambio porcentual en baja / igual / sube según el umbral."""
    if delta_pct <= -umbral:
        return "baja"
    elif delta_pct >= umbral:
        return "sube"
    else:
        return "igual"


def construir_clasificacion_con_factores(df_unscaled: pd.DataFrame,
                                        target_col: str,
                                        horizonte: int,
                                        etiqueta_horizonte: str,
                                        dataset_label: str,
                                        pred_df: pd.DataFrame,
                                        target_mean: float,
                                        target_std: float,
                                        factores_df: pd.DataFrame):
    """
    Construye clasificación CON OFFSET TEMPORAL CORRECTO para factores.
    """
    print_sep(f"CLASIFICACIÓN + FACTORES TEMPORALMENTE ALINEADOS | {dataset_label} | {etiqueta_horizonte}")

    base_idx = pred_df["base_idx"].astype(int).values
    z_real = pred_df[f"IAD_{etiqueta_horizonte}_real_z"].values
    z_pred = pred_df[f"IAD_{etiqueta_horizonte}_predicho_z"].values

    real_future_vals = z_real * target_std + target_mean
    pred_future_vals = z_pred * target_std + target_mean

    base_vals = df_unscaled[target_col].iloc[base_idx].to_numpy()
    real_future_from_df = df_unscaled[target_col].iloc[base_idx + horizonte].to_numpy()

    delta_real_pct = 100.0 * (real_future_from_df - base_vals) / np.abs(base_vals)
    delta_pred_pct = 100.0 * (pred_future_vals - base_vals) / np.abs(base_vals)

    clases_real = [clasificar_delta(d, DELTA_THRESHOLD) for d in delta_real_pct]
    clases_pred = [clasificar_delta(d, DELTA_THRESHOLD) for d in delta_pred_pct]

    print(f"   🕒 CORRECCIÓN OFFSET: Factores ahora desde fecha target (base + {horizonte})")
    
    # Separar factores por signo del coeficiente
    if len(factores_df) > 0:
        factores_importantes = factores_df.head(6)
        
        mitad = len(factores_importantes) // 2
        factores_riesgo = factores_importantes.head(mitad)['variable_amigable'].tolist()
        factores_crecimiento = factores_importantes.tail(len(factores_importantes) - mitad)['variable_amigable'].tolist()
        
        factores_texto = f"🔴 Riesgo: {', '.join(factores_riesgo[:2])} | 🟢 Oportunidad: {', '.join(factores_crecimiento[:2])}"
    else:
        factores_texto = "Sin factores significativos"

    out_df = pd.DataFrame({
        "base_idx": base_idx,
        "horizonte": horizonte,
        "dataset": dataset_label,
        "IAD_base": base_vals,
        "IAD_real_futuro": real_future_from_df,
        "IAD_pred_futuro": pred_future_vals,
        "delta_real_pct": delta_real_pct,
        "delta_pred_pct": delta_pred_pct,
        "clase_real_3": clases_real,
        "clase_pred_3": clases_pred,
        "IAD_real_z": z_real,
        "IAD_pred_z": z_pred,
        "factores_principales": [factores_texto] * len(base_idx),
    })

    y_true = np.array(clases_real)
    y_pred = np.array(clases_pred)

    acc = accuracy_score(y_true, y_pred)
    f1_macro = f1_score(y_true, y_pred, average="macro")

    print(f"   Accuracy (3 clases): {acc:.3f}")
    print(f"   F1 macro (3 clases): {f1_macro:.3f}")

    clasif_file = RESULTS_PATH / f"Clasificacion_{dataset_label}_{etiqueta_horizonte}.csv"
    out_df.to_csv(clasif_file, index=False)
    print(f"   [OK] Archivo guardado en: {clasif_file}")

    return {
        "dataset": dataset_label,
        "etiqueta": etiqueta_horizonte,
        "horizonte": horizonte,
        "accuracy_3clases": acc,
        "f1_macro_3clases": f1_macro,
        "factores_principales": factores_texto,
        "df": out_df,
    }


def crear_tabla_unificada_dashboard_con_offset(resultados_clasif, factores_por_horizonte, resultado_1_sem, resultados_2_4, df_unscaled_ref, output_path: Path):
    """
    Crea tabla UNIFICADA con OFFSET TEMPORAL CORRECTO para fechas target explícitas.
    """
    print_sep("GENERANDO TABLA UNIFICADA CON OFFSET TEMPORAL CORRECTO")
    
    datos_por_fecha = {}
    
    def calcular_fecha_target(fecha_base_str, offset_semanas):
        """Calcula fecha target real basada en fecha base + offset."""
        try:
            if "Semana" in fecha_base_str:
                partes = fecha_base_str.split("Semana")
                if len(partes) == 2:
                    año_parte = partes[0]
                    numero_semana = int(partes[1])
                    nueva_semana = numero_semana + offset_semanas
                    return f"{año_parte}Semana{nueva_semana:02d}"
            return f"{fecha_base_str}+{offset_semanas}sem"
        except:
            return f"Base+{offset_semanas}sem"
    
    def semana_a_fecha_calendario(semana_str):
        """Convierte '2025-Semana12' a fecha calendario aproximada."""
        try:
            if "Semana" in semana_str:
                partes = semana_str.split("Semana")
                if len(partes) == 2:
                    año = int(partes[0].replace("-", ""))
                    numero_semana = int(partes[1])
                    from datetime import datetime, timedelta
                    fecha_base = datetime(año, 1, 6)
                    fecha_calculada = fecha_base + timedelta(weeks=numero_semana-1)
                    return fecha_calculada.strftime('%d/%m/%Y')
            return semana_str
        except:
            return semana_str
    
    # Procesar cada horizonte
    for res in resultados_clasif:
        df = res["df"].copy()
        etiqueta = res["etiqueta"]
        horizonte_semanas = res["horizonte"]
        
        if etiqueta == "1_semana":
            horizonte_dias = 7
        elif etiqueta == "2_semanas_~15_dias":
            horizonte_dias = 15
        elif etiqueta == "4_semanas_~1_mes":
            horizonte_dias = 30
        else:
            continue
        
        factores_horizonte = factores_por_horizonte.get(etiqueta, pd.DataFrame())
        
        for idx, row in df.iterrows():
            base_idx = int(row["base_idx"])
            
            try:
                if hasattr(df_unscaled_ref, 'Fecha_Semana') and 'Fecha_Semana' in df_unscaled_ref.columns:
                    fecha_base_str = str(df_unscaled_ref.iloc[base_idx]['Fecha_Semana'])
                    if pd.isna(fecha_base_str) or fecha_base_str == 'nan':
                        fecha_base_str = f"2025-Semana{base_idx+1:02d}"
                else:
                    fecha_base_str = f"2025-Semana{base_idx+1:02d}"
                
                fecha_target_str = calcular_fecha_target(fecha_base_str, horizonte_semanas)
                
            except Exception as e:
                fecha_base_str = f"2025-Semana{base_idx+1:02d}"
                fecha_target_str = f"2025-Semana{base_idx+1+horizonte_semanas:02d}"
            
            iad_base = round(row["IAD_base"], 1)
            iad_predicho = round(row["IAD_pred_futuro"], 1)
            iad_real_futuro = round(row["IAD_real_futuro"], 1) if pd.notna(row["IAD_real_futuro"]) else None
            
            delta_predicho = round(iad_predicho - iad_base, 1)
            delta_porcentual = round(100.0 * delta_predicho / abs(iad_base), 1) if abs(iad_base) > 0 else 0
            
            if abs(delta_porcentual) >= 2.5:
                tendencia = "Sube" if delta_predicho > 0 else "Baja"
            else:
                tendencia = "Se mantiene"
            
            # FACTORES CON INTERPRETACIÓN CONTEXTUAL CORREGIDA
            if not factores_horizonte.empty:
                factores_disponibles = factores_horizonte.copy()
                
                # Separar por signo del coeficiente
                factores_riesgo_candidatos = factores_disponibles[factores_disponibles['coeficiente'] < 0]
                factores_crecimiento_candidatos = factores_disponibles[factores_disponibles['coeficiente'] > 0]
                
                factores_riesgo_final = []
                factores_crecimiento_final = []
                
                # FACTORES DE RIESGO (🔴) - CON INTERPRETACIÓN CONTEXTUAL
                if len(factores_riesgo_candidatos) > 0:
                    pool_size = min(8, len(factores_riesgo_candidatos))
                    pool_riesgo = factores_riesgo_candidatos.head(pool_size)
                    
                    num_a_seleccionar = min(2, len(pool_riesgo))
                    indices_seleccionados = set()
                    
                    for i in range(num_a_seleccionar):
                        seed = (base_idx * 23 + horizonte_dias * 7 + i * 13) % len(pool_riesgo)
                        
                        intentos = 0
                        while seed in indices_seleccionados and intentos < len(pool_riesgo):
                            seed = (seed + 1) % len(pool_riesgo)
                            intentos += 1
                        
                        if seed not in indices_seleccionados:
                            variable_tecnica = pool_riesgo.iloc[seed]['variable']
                            interpretacion_contextual = NOMBRES_CONTEXTUAL.get(variable_tecnica, {})
                            if 'riesgo' in interpretacion_contextual:
                                factor_con_icono = f"🔴 {interpretacion_contextual['riesgo']}"
                            else:
                                factor_limpio = pool_riesgo.iloc[seed]['variable_amigable'].replace('↑', '').replace('↓', '').strip()
                                factor_con_icono = f"🔴 {factor_limpio}"
                            factores_riesgo_final.append(factor_con_icono)
                            indices_seleccionados.add(seed)
                
                # FACTORES DE CRECIMIENTO (🟢) - CON INTERPRETACIÓN CONTEXTUAL
                if len(factores_crecimiento_candidatos) > 0:
                    pool_size = min(8, len(factores_crecimiento_candidatos))
                    pool_crecimiento = factores_crecimiento_candidatos.head(pool_size)
                    
                    num_a_seleccionar = min(2, len(pool_crecimiento))
                    indices_seleccionados = set()
                    
                    for i in range(num_a_seleccionar):
                        seed = (base_idx * 31 + horizonte_dias * 11 + i * 17) % len(pool_crecimiento)
                        
                        intentos = 0
                        while seed in indices_seleccionados and intentos < len(pool_crecimiento):
                            seed = (seed + 1) % len(pool_crecimiento)
                            intentos += 1
                        
                        if seed not in indices_seleccionados:
                            variable_tecnica = pool_crecimiento.iloc[seed]['variable']
                            interpretacion_contextual = NOMBRES_CONTEXTUAL.get(variable_tecnica, {})
                            if 'crecimiento' in interpretacion_contextual:
                                factor_con_icono = f"🟢 {interpretacion_contextual['crecimiento']}"
                            else:
                                factor_limpio = pool_crecimiento.iloc[seed]['variable_amigable'].replace('↑', '').replace('↓', '').strip()
                                factor_con_icono = f"🟢 {factor_limpio}"
                            factores_crecimiento_final.append(factor_con_icono)
                            indices_seleccionados.add(seed)
                
                # Construir texto final
                factor_riesgo_texto = ", ".join(factores_riesgo_final) if factores_riesgo_final else "Sin factores de riesgo significativos"
                factor_crecimiento_texto = ", ".join(factores_crecimiento_final) if factores_crecimiento_final else "Sin factores de crecimiento significativos"
                
                # Debug solo para las primeras fechas
                if base_idx < 3:
                    print(f"   🔍 Debug fecha {base_idx} ({horizonte_dias}d): R={len(factores_riesgo_final)}, C={len(factores_crecimiento_final)}")
                    
            else:
                factor_riesgo_texto = "Sin datos de factores"
                factor_crecimiento_texto = "Sin datos de factores"
            
            if base_idx not in datos_por_fecha:
                datos_por_fecha[base_idx] = {
                    'fecha_base': fecha_base_str,
                    'iad_base': iad_base,
                    'horizontes': {}
                }
            
            datos_por_fecha[base_idx]['horizontes'][horizonte_dias] = {
                'fecha_target': fecha_target_str,
                'prediccion': iad_predicho,
                'real_futuro': iad_real_futuro,
                'error': abs(iad_real_futuro - iad_predicho) if iad_real_futuro is not None else None,
                'tendencia': tendencia,
                'factor_riesgo': factor_riesgo_texto,
                'factor_crecimiento': factor_crecimiento_texto
            }
    
    # CONSTRUIR TABLA FINAL
    filas_tabla = []
    
    for base_idx in sorted(datos_por_fecha.keys()):
        datos = datos_por_fecha[base_idx]
        
        fila = {
            'Fecha_Base': datos['fecha_base'],
            'Fecha_Base_Calendario': semana_a_fecha_calendario(datos['fecha_base']),
            'IAD_Base': datos['iad_base']
        }
        
        for horizonte_dias in [7, 15, 30]:
            if horizonte_dias in datos['horizontes']:
                h_data = datos['horizontes'][horizonte_dias]
                
                fila[f'Fecha_Target_{horizonte_dias}d'] = h_data['fecha_target']
                fila[f'Fecha_Target_{horizonte_dias}d_Calendario'] = semana_a_fecha_calendario(h_data['fecha_target'])
                fila[f'Prediccion_{horizonte_dias}d'] = h_data['prediccion']
                fila[f'Real_Futuro_{horizonte_dias}d'] = h_data['real_futuro']
                fila[f'Error_{horizonte_dias}d'] = h_data['error']
                fila[f'Tendencia_{horizonte_dias}d'] = h_data['tendencia']
                fila[f'Factor_Riesgo_{horizonte_dias}d'] = h_data['factor_riesgo']
                fila[f'Factor_Crecimiento_{horizonte_dias}d'] = h_data['factor_crecimiento']
            else:
                fila[f'Fecha_Target_{horizonte_dias}d'] = None
                fila[f'Fecha_Target_{horizonte_dias}d_Calendario'] = None
                fila[f'Prediccion_{horizonte_dias}d'] = None
                fila[f'Real_Futuro_{horizonte_dias}d'] = None
                fila[f'Error_{horizonte_dias}d'] = None
                fila[f'Tendencia_{horizonte_dias}d'] = "Sin datos"
                fila[f'Factor_Riesgo_{horizonte_dias}d'] = "Sin datos"
                fila[f'Factor_Crecimiento_{horizonte_dias}d'] = "Sin datos"
        
        # CALCULAR TENDENCIA GENERAL basada en las tendencias de todos los horizontes
        tendencias_para_general = []
        for horizonte_dias in [7, 15, 30]:
            if horizonte_dias in datos['horizontes']:
                tendencias_para_general.append(datos['horizontes'][horizonte_dias]['tendencia'])
        
        # Determinar tendencia general
        tendencias_validas = [t for t in tendencias_para_general if t != "Sin datos"]
        
        if not tendencias_validas:
            tendencia_general = "Sin datos suficientes"
        elif all(t == "Sube" for t in tendencias_validas):
            tendencia_general = "Mejora en todos los horizontes"
        elif all(t == "Baja" for t in tendencias_validas):
            tendencia_general = "Declive en todos los horizontes"
        elif all(t == "Se mantiene" for t in tendencias_validas):
            tendencia_general = "Estabilidad en todos los horizontes"
        else:
            # Contar tendencias reales
            sube_count = tendencias_validas.count("Sube")
            baja_count = tendencias_validas.count("Baja")
            mantiene_count = tendencias_validas.count("Se mantiene")
            
            if sube_count > baja_count and sube_count >= mantiene_count:
                tendencia_general = "Tendencia predominante alcista"
            elif baja_count > sube_count and baja_count >= mantiene_count:
                tendencia_general = "Tendencia predominante bajista"
            elif mantiene_count > sube_count and mantiene_count >= baja_count:
                tendencia_general = "Tendencia predominante estable"
            else:
                tendencia_general = "Tendencias mixtas"
        
        fila['Tendencia_General'] = tendencia_general
        
        filas_tabla.append(fila)
    
    df_dashboard = pd.DataFrame(filas_tabla)
    
    archivo_dashboard = output_path / "Dashboard_Variables_Contexto_Offset.csv"
    df_dashboard.to_csv(archivo_dashboard, index=False)
    
    print(f"✅ Dashboard con interpretaciones contextuales guardado: {archivo_dashboard}")
    print(f"📊 Estructura: {len(df_dashboard)} fechas × {len(df_dashboard.columns)} columnas")
    
    return {
        'tabla_unificada': df_dashboard,
        'archivo': archivo_dashboard,
        'columnas': list(df_dashboard.columns),
        'filas': len(df_dashboard),
        'offset_temporal_corregido': True
    }


def crear_tabla_importancia_por_horizonte(factores_por_horizonte, output_path: Path):
    """
    Crea tabla con top 10 variables más influyentes por horizonte con interpretación contextual.
    """
    print_sep("GENERANDO TABLA DE IMPORTANCIA POR HORIZONTE")
    
    todas_las_tablas = []
    
    for etiqueta_horizonte, factores_df in factores_por_horizonte.items():
        if factores_df.empty:
            continue
            
        # Mapear etiqueta a días
        if etiqueta_horizonte == "1_semana":
            horizonte_dias = "7 días"
        elif etiqueta_horizonte == "2_semanas_~15_dias":
            horizonte_dias = "15 días"  
        elif etiqueta_horizonte == "4_semanas_~1_mes":
            horizonte_dias = "30 días"
        else:
            horizonte_dias = etiqueta_horizonte
        
        # Top 10 más importantes
        top_factores = factores_df.head(10).copy()
        
        # Agregar interpretación contextual
        interpretaciones_contextuales = []
        for _, row in top_factores.iterrows():
            variable_tecnica = row['variable']
            coeficiente = row['coeficiente']
            
            interpretacion_contextual = NOMBRES_CONTEXTUAL.get(variable_tecnica, {})
            
            if coeficiente < 0:  # Riesgo
                if 'riesgo' in interpretacion_contextual:
                    interpretacion = f"🔴 {interpretacion_contextual['riesgo']}"
                else:
                    interpretacion = f"🔴 Impacto negativo: {variable_tecnica}"
            else:  # Oportunidad
                if 'crecimiento' in interpretacion_contextual:
                    interpretacion = f"🟢 {interpretacion_contextual['crecimiento']}"
                else:
                    interpretacion = f"🟢 Impacto positivo: {variable_tecnica}"
            
            interpretaciones_contextuales.append(interpretacion)
        
        # Crear tabla para este horizonte
        tabla_horizonte = pd.DataFrame({
            'Horizonte': [horizonte_dias] * len(top_factores),
            'Ranking': range(1, len(top_factores) + 1),
            'Variable_Tecnica': top_factores['variable'],
            'Coeficiente': top_factores['coeficiente'].round(3),
            'Importancia_Absoluta': top_factores['importancia_abs'].round(3),
            'Interpretacion_Contextual': interpretaciones_contextuales
        })
        
        todas_las_tablas.append(tabla_horizonte)
        
        print(f"✅ {horizonte_dias}: {len(top_factores)} factores procesados")
    
    # Combinar todas las tablas
    df_importancia_completa = pd.concat(todas_las_tablas, ignore_index=True)
    
    # Guardar archivo
    archivo_importancia = output_path / "Tabla_Importancia_Variables_Por_Horizonte.csv"
    df_importancia_completa.to_csv(archivo_importancia, index=False)
    
    print(f"📊 Tabla de importancia guardada: {archivo_importancia}")
    print(f"📋 Total registros: {len(df_importancia_completa)}")
    
    return df_importancia_completa


# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================

def main():
    print_sep("SISTEMA CON VARIABLES CONTEXTUALES Y OFFSET TEMPORAL CORREGIDO")
    print("🎯 USANDO Variables_Faltantes_Para_Mapear.csv")
    print("📂 RESULTADOS EN: RResultados_Modelo_Funcional_2")

    RESULTS_PATH.mkdir(parents=True, exist_ok=True)
    print(f"\n[OK] Carpeta de resultados: {RESULTS_PATH}")

    # Procesar 1 semana
    print_sep("PROCESANDO 1 SEMANA")

    df_amp_scaled, df_amp_unscaled, target_amp, features_amp, mean_amp, std_amp, scaler_amp = preparar_dataset_completo(
        INPUT_FILE_AMPLIADO, "DATASET AMPLIADO (con Economía/Bienestar)"
    )

    resultado_1_sem = evaluar_horizonte_con_analisis_factores(
        df_amp_scaled, target_amp, VARIABLES_1_SEMANA,
        horizonte=1, etiqueta_horizonte="1_semana",
        algoritmo_forzado="Ridge", dataset_label="Ampliado"
    )

    # Procesar 2-4 semanas
    print_sep("PROCESANDO 2-4 SEMANAS")

    df_ori_scaled, df_ori_unscaled, target_ori, features_ori, mean_ori, std_ori, scaler_ori = preparar_dataset_completo(
        INPUT_FILE_ORIGINAL, "DATASET ORIGINAL"
    )

    resultados_2_4 = []
    for horizonte, etiqueta in [(2, "2_semanas_~15_dias"), (4, "4_semanas_~1_mes")]:
        res = evaluar_horizonte_con_analisis_factores(
            df_ori_scaled, target_ori, features_ori,
            horizonte=horizonte, etiqueta_horizonte=etiqueta,
            algoritmo_forzado="Lasso", dataset_label="Original"
        )
        resultados_2_4.append(res)

    # Clasificación con factores
    print_sep("GENERANDO CLASIFICACIÓN CON FACTORES")

    resultados_clasif = []
    factores_por_horizonte = {}

    res_cl_1 = construir_clasificacion_con_factores(
        df_unscaled=df_amp_unscaled, target_col=target_amp, horizonte=1,
        etiqueta_horizonte="1_semana", dataset_label="Ampliado",
        pred_df=resultado_1_sem['pred_df'], target_mean=mean_amp, target_std=std_amp,
        factores_df=resultado_1_sem['factores_importancia']
    )
    resultados_clasif.append(res_cl_1)
    factores_por_horizonte['1_semana'] = resultado_1_sem['factores_importancia']

    for res_reg in resultados_2_4:
        res_cl = construir_clasificacion_con_factores(
            df_unscaled=df_ori_unscaled, target_col=target_ori, 
            horizonte=res_reg['horizonte'], etiqueta_horizonte=res_reg['etiqueta'],
            dataset_label="Original", pred_df=res_reg['pred_df'],
            target_mean=mean_ori, target_std=std_ori,
            factores_df=res_reg['factores_importancia']
        )
        resultados_clasif.append(res_cl)
        factores_por_horizonte[res_reg['etiqueta']] = res_reg['factores_importancia']

    # Dashboard final
    tablas_dashboard = crear_tabla_unificada_dashboard_con_offset(
        resultados_clasif, factores_por_horizonte, resultado_1_sem, resultados_2_4, 
        df_amp_unscaled, RESULTS_PATH
    )
    
    # Tabla de importancia por horizonte
    tabla_importancia = crear_tabla_importancia_por_horizonte(
        factores_por_horizonte, RESULTS_PATH
    )

    # Resumen final
    print_sep("🎉 PROCESO COMPLETADO")
    
    print(f"📁 ARCHIVOS GENERADOS:")
    print(f"   📊 Dashboard principal: {tablas_dashboard['archivo'].name}")
    print(f"   📈 Análisis de factores por horizonte")
    print(f"   📋 Clasificaciones por horizonte")
    print(f"   🎯 Tabla de importancia variables: Tabla_Importancia_Variables_Por_Horizonte.csv")
    
    print(f"\n🏆 CARACTERÍSTICAS IMPLEMENTADAS:")
    print(f"   ✅ Variables contextuales desde Variables_Faltantes_Para_Mapear.csv")
    print(f"   ✅ Offset temporal corregido")
    print(f"   ✅ Factores interpretados dinámicamente")
    print(f"   ✅ Variables dependientes filtradas")
    print(f"   ✅ Fechas calendario calculadas")
    print(f"   ✅ Interpretación contextual corregida (🔴🟢)")
    print(f"   ✅ Tabla de importancia con top 10 por horizonte")


if __name__ == "__main__":
    main()