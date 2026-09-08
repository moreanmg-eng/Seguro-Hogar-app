# Cotizador de Seguro de Hogar

Portal en Python (Streamlit) para que clientes potenciales coticen un
seguro de hogar, descarguen su cotización en PDF, decidan si quieren
contratar, y para dar seguimiento hasta la emisión de la póliza con
tres roles: **Cliente**, **Asesor comercial** y **Administrador** (tú).

## Flujo completo

1. **Cliente**: llena el formulario (nombre, correo, teléfono, código
   postal, paquete deseado) → el sistema calcula la prima con base en
   el paquete y el código postal → genera un PDF de cotización
   descargable.
2. El cliente indica si quiere contratar. Si dice que sí (y
   opcionalmente elige un asesor de preferencia), se le notifica por
   correo al asesor correspondiente con los datos del prospecto.
3. **Asesor** (entra al portal con usuario/contraseña): ve sus
   prospectos interesados, les da seguimiento fuera del sistema, y
   cuando todo está listo, confirma en el portal que está listo para
   emitirse la póliza → esto te notifica por correo a ti.
4. **Administrador** (tú, con contraseña): ves las confirmaciones
   pendientes, subes el PDF de la póliza ya emitida → esto notifica
   automáticamente al asesor.
5. El **asesor** descarga la póliza desde el portal y se la comparte
   al cliente; puede marcarla como "entregada" para cerrar el ciclo.

Todo el historial (estatus, fechas, asesor asignado, archivos) queda
guardado en una base de datos local (`cotizaciones.db`, SQLite) para
que puedas ver el panorama completo en la vista de Administrador.

## Instalación

```bash
cd seguro_hogar_app
python3 -m venv venv
source venv/bin/activate        # En Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Configuración de correo (opcional para empezar a probar)

Copia `.env.example` a `.env` y llena tus datos:

```bash
cp .env.example .env
```

- Si usas Gmail, activa la verificación en 2 pasos y genera una
  **contraseña de aplicación** en
  https://myaccount.google.com/apppasswords — tu contraseña normal no
  funciona con el envío automático.
- **Mientras no configures `.env`**, la app sigue funcionando: los
  correos se "simulan" (se guardan como archivos `.txt` dentro de
  `correos_simulados/`) para que puedas probar todo el flujo sin
  necesidad de credenciales reales todavía.
- Define también `ADMIN_PASSWORD` (la contraseña para entrar a tu
  vista de Administrador) y `ADMIN_EMAIL` (a dónde te llegan los
  avisos de "asesor confirmó, listo para emitir").

## Conectar tu Excel real de paquetes y códigos postales

Ahora mismo la app usa datos de EJEMPLO (`data/paquetes_ejemplo.xlsx` y
`data/codigos_postales_ejemplo.xlsx`) para que puedas ver todo el flujo
funcionando. Cuando compartas tu Excel real:

1. Reviso la estructura de tus columnas (paquetes por suma asegurada,
   coberturas, y la tabla de primas/factores por código postal).
2. Adapto `cotizador.py` para leer directamente tu archivo y tu forma
   real de calcular la prima total (ahora mismo usa
   `prima_base_del_paquete × factor_de_la_zona_del_CP`, pero si tu
   lógica real es distinta —por ejemplo, una tabla de tarifas
   específica por CP y suma asegurada— la ajusto para que calce
   exactamente).
3. Reemplazo los archivos de ejemplo por los reales (o apunto
   `cotizador.py` a las rutas donde los coloques).

Igual para el catálogo de asesores: reemplaza
`data/asesores_ejemplo.xlsx` por tu lista real (nombre, correo,
usuario, contraseña) — dime los nombres/correos reales y te lo dejo
armado.

## Ejecutar la app localmente

```bash
streamlit run app.py
```

Se abre en tu navegador (normalmente `http://localhost:8501`). En la
barra lateral eliges si entras como Cliente, Asesor o Administrador.

## Desplegarla en internet (Streamlit Community Cloud)

Para que el asesor (o varios) y los clientes puedan entrar desde
cualquier lugar con un link, sin depender de tu computadora, la app
está lista para desplegarse gratis en **Streamlit Community Cloud**.
El proceso completo (sin necesidad de usar la terminal ni instalar
nada) es:

1. Sube el código a un repositorio de GitHub (público o privado).
2. Entra a [share.streamlit.io](https://share.streamlit.io) con tu
   cuenta de GitHub, crea una app nueva apuntando a `app.py`.
3. En "Advanced settings → Secrets", pega el contenido de
   `.streamlit/secrets.toml.example` ya con tus datos reales (esto
   reemplaza al archivo `.env` cuando corre en la nube — el código ya
   está preparado para leer de cualquiera de los dos, ver `config.py`).
4. Despliega y prueba el link.

Te voy a armar una guía visual con estos pasos ilustrados uno por uno.

### ⚠️ Importante: el almacenamiento en la nube no es permanente

Streamlit Community Cloud **no garantiza que los archivos locales se
conserven** — puede borrar la base de datos (`cotizaciones.db`) y los
PDFs guardados (`pdfs_generados/`, `polizas_emitidas/`) cada vez que la
app se reinicia (por inactividad, una actualización de código, etc.).

Para que no pierdas información importante:

- La vista de Administrador tiene un botón **"Descargar respaldo
  completo (Excel)"** — úsalo seguido, sobre todo después de registrar
  contrataciones o emisiones.
- Cada notificación por correo ya lleva el PDF adjunto (cotización o
  póliza), así que aunque se perdiera el archivo local, ese correo
  sigue siendo un respaldo.
- Más adelante, cuando el volumen de cotizaciones lo amerite, conviene
  migrar la base de datos a algo permanente en la nube (por ejemplo,
  Google Sheets o una base de datos gratuita tipo Supabase) en vez del
  SQLite local — lo armamos cuando estés listo para ese paso.

## Probar todo el flujo sin usar la interfaz

```bash
python3 test_flujo_completo.py
```

Este script simula: cotización → cliente interesado → asesor confirma
→ administrador emite → asesor entrega, e imprime cada paso. Es una
buena forma de verificar que todo sigue funcionando si haces cambios.

## Seguridad — cosas a tener en cuenta

- El login de asesor y la contraseña de administrador son
  intencionalmente simples (para uso interno con pocas personas de
  confianza, corriendo en tu propia red). No es un sistema de
  autenticación de nivel empresarial (no hay hash de contraseñas, ni
  recuperación de cuenta, etc.).
- El archivo `.env` (con tus contraseñas reales) nunca debe
  compartirse ni subirse a un repositorio público — ya está excluido
  en `.gitignore`.
- Si en algún momento decides hostear esto en internet para que
  clientes o asesores externos entren desde cualquier lugar, conviene
  reforzar la seguridad antes (contraseñas con hash, HTTPS, tal vez un
  login por asesor más robusto).

## Estructura del proyecto

```
seguro_hogar_app/
├── app.py                        # Interfaz Streamlit (3 vistas: Cliente/Asesor/Admin)
├── cotizador.py                  # Cálculo de la prima (paquete + código postal)
├── pdf_generator.py              # Genera el PDF de cotización
├── email_utils.py                # Envío de correos + notificaciones del flujo
├── db.py                         # Base de datos SQLite (historial y estatus)
├── asesores.py                   # Catálogo de asesores y login simple
├── config.py                     # Lee credenciales de .env (local) o st.secrets (nube)
├── generar_datos_ejemplo.py      # Crea paquetes/CPs de EJEMPLO
├── generar_asesores_ejemplo.py   # Crea asesores de EJEMPLO
├── test_flujo_completo.py        # Prueba end-to-end de toda la lógica
├── data/                         # Excels de paquetes, CPs y asesores
├── pdfs_generados/                # PDFs de cotizaciones (se crea al usar la app)
├── polizas_emitidas/              # PDFs de pólizas subidas por el admin
├── correos_simulados/             # Correos "enviados" cuando no hay SMTP configurado
├── .env.example                  # Plantilla de configuración local (copiar a .env)
├── .streamlit/
│   └── secrets.toml.example      # Plantilla de configuración para la nube
└── requirements.txt
```
