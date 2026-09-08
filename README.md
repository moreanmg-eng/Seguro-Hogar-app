# Cotizador de Seguro de Hogar

Portal en Python (Streamlit) para que clientes potenciales coticen un
seguro de hogar, descarguen su cotización en PDF, decidan si quieren
contratar, y para dar seguimiento hasta la emisión de la póliza con
tres roles: **Cliente**, **Asesor comercial** y **Administrador** (tú).

## Flujo completo

1. **Cliente**: llena un formulario de 3 secciones — (1) datos
   personales, código postal y si es propietario o arrendatario; (2)
   dirección y paquete de interés (Propietario, Arrendatario o
   Estándar, o una suma personalizada mayor a los paquetes); (3) si
   quiere agregar cobertura de Terremoto (cuando aplica). El sistema
   calcula la prima real: prima base del paquete + zona de riesgo
   hidrometeorológico (siempre) + zona sísmica (si pidió Terremoto),
   prorrateada por los días que quedan hasta el fin de vigencia de la
   póliza de flotilla, + 16% IVA + $1 de derecho de emisión. Genera un
   PDF de cotización descargable con el desglose completo.
   - Si el cliente pide una suma mayor a la de los paquetes, no se
     calcula nada automático: se guarda su solicitud y se te notifica
     para que un asesor lo cotice manualmente.
   - Antes de poder dar clic en "Cotizar", el cliente debe marcar una
     casilla de aceptación del Aviso de Privacidad (el texto vive en
     `assets/aviso_privacidad.md` — puedes editarlo cuando quieras,
     ver la sección "Aviso de privacidad" más abajo).
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

## Datos: paquetes, zonas y fecha de vigencia

La app ya usa tus tarifas reales de Zurich:

- `data/paquetes.xlsx` — catálogo de paquetes (Propietario y
  Arrendatario, cada uno con 4 niveles, y Estándar, que es un solo
  paquete fijo), con todas las sumas aseguradas, la prima base anual y
  los adicionales por zona de riesgo. Se generó a partir de tus archivos
  `PAQUETES VIGENTES ZURICH.xlsx` (Propietario/Arrendatario) y
  `Paq Solo contenidos.xlsx` (Estándar) con el script
  `../excel_review/preparar_datos_reales.py` (fuera de esta carpeta) —
  si Zurich actualiza tarifas, se vuelve a correr ese script con los
  Excel nuevos.
- `data/zonas_cp.xlsx` — un renglón por código postal con su zona de
  riesgo hidrometeorológico y su zona sísmica, generado a partir de tu
  archivo `Zonas Alfa y TEV por CP.xlsx`.
- **Fecha de fin de vigencia**: no está en un archivo, se edita
  directamente desde la vista de Administrador dentro de la app (cada
  cotización se prorratea contra esa fecha). Actualízala cada vez que
  renueve la póliza de flotilla, normalmente el 1 de enero.

Para el catálogo de asesores: reemplaza `data/asesores_ejemplo.xlsx`
por tu lista real (nombre, correo, usuario, contraseña) — dime los
nombres/correos reales y te lo dejo armado.

## Aviso de privacidad

El texto que ve el cliente antes de cotizar vive en
`assets/aviso_privacidad.md` — es un borrador general, **no es
asesoría legal**, y conviene que lo revise tu asesor legal antes de
usarlo con clientes reales (sobre todo el correo de contacto para
derechos ARCO, que quedó como pendiente de definir). Para actualizarlo
solo edita ese archivo de texto (puedes hacerlo directo en GitHub, con
el ícono de lápiz) — no hace falta tocar nada de código, y el cliente
no puede dar clic en "Cotizar" sin antes marcar la casilla de
aceptación.

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
- La app también puede sincronizar sola cada cotización a una hoja de
  Google Sheets en tiempo real, para no depender de acordarte de
  descargar el Excel — ver la siguiente sección.

## Respaldo automático en Google Sheets

Con esto activado, cada vez que se cotiza algo o cambia de estatus
(interesado, confirmado, emitida, entregada), la app sobrescribe una
hoja de tu Google Sheet con el snapshot completo de todas las
cotizaciones — automático, sin que nadie tenga que darle clic a nada.
Es la forma recomendada de no perder información si la app corre en
Streamlit Community Cloud.

Mientras no lo configures, la app sigue funcionando exactamente igual
(este respaldo es opcional) — el panel de Administrador simplemente te
seguirá recordando usar el botón de descargar Excel.

**Pasos para configurarlo (una sola vez):**

1. **Crea la hoja de cálculo.** En [sheets.google.com](https://sheets.google.com)
   crea una hoja nueva (puede estar vacía, o puedes usarla también para
   ver los datos tú mismo). Cópiate el ID de la URL: es la parte entre
   `/d/` y `/edit`, por ejemplo
   `https://docs.google.com/spreadsheets/d/`**`1AbCdEfGhIjKlMnOpQr`**`/edit`.

2. **Crea una "cuenta de servicio" en Google Cloud** (es una cuenta
   especial solo para que la app pueda escribir en tu Sheet, no es tu
   cuenta personal de Gmail):
   - Entra a [console.cloud.google.com](https://console.cloud.google.com),
     crea un proyecto nuevo (o usa uno que ya tengas).
   - En el buscador de arriba escribe "Google Sheets API" y dale
     **Habilitar** (Enable). Haz lo mismo para "Google Drive API".
   - Ve a "APIs y servicios → Credenciales → Crear credenciales →
     Cuenta de servicio". Dale cualquier nombre (p. ej.
     "cotizador-backup") y termina el asistente sin agregarle roles
     especiales.
   - Ya creada, entra a esa cuenta de servicio → pestaña "Claves" →
     "Agregar clave → Crear clave nueva" → tipo **JSON** → Crear. Se
     descarga un archivo `.json` a tu computadora — esa es tu única
     copia de la contraseña, guárdalo bien y no lo subas a GitHub.

3. **Comparte tu Google Sheet con esa cuenta de servicio.** Abre el
   archivo `.json` que descargaste y copia el valor del campo
   `client_email` (se ve como
   `algo@tu-proyecto.iam.gserviceaccount.com`). En tu Google Sheet dale
   clic a "Compartir" y agrega ese correo como **Editor**. Si te
   saltas este paso, la sincronización va a fallar con un error de
   permisos.

4. **Configura las credenciales en la app:**
   - **En Streamlit Community Cloud:** entra a "Manage app → Settings
     → Secrets" y agrega `GOOGLE_SHEET_ID` con el ID del paso 1, más
     una tabla `[gcp_service_account]` con todos los campos del
     `.json` que descargaste (mira la plantilla completa en
     `.streamlit/secrets.toml.example` — solo copia cada valor de tu
     `.json` al campo correspondiente).
   - **En tu computadora (para probar local):** guarda el `.json`
     descargado como `google_service_account.json` dentro de esta
     misma carpeta (ya está en `.gitignore`, nunca se sube), y agrega
     `GOOGLE_SHEET_ID=...` a tu archivo `.env`.

5. Reinicia la app (o "Reboot app" en Streamlit Cloud). En el panel de
   Administrador, en "Panel general de todas las cotizaciones", debe
   aparecer "✅ Respaldo automático a Google Sheets activado" en vez
   de la advertencia de almacenamiento — con un botón "🔄 Sincronizar
   ahora" por si en algún momento quieres forzar una sincronización
   manual (por ejemplo, la primera vez, para traer el historial que ya
   tenías antes de activarlo).

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
├── cotizador.py                  # Cálculo real de la prima (paquete + zona + prorrateo)
├── pdf_generator.py              # Genera el PDF de cotización con el desglose completo
├── email_utils.py                # Envío de correos + notificaciones del flujo
├── db.py                         # Base de datos SQLite (historial, estatus y configuración)
├── asesores.py                   # Catálogo de asesores y login simple
├── config.py                     # Lee credenciales de .env (local) o st.secrets (nube)
├── generar_asesores_ejemplo.py   # Crea asesores de EJEMPLO
├── test_flujo_completo.py        # Prueba end-to-end de toda la lógica
├── data/
│   ├── paquetes.xlsx              # Catálogo real: Propietario/Arrendatario/Estándar
│   ├── zonas_cp.xlsx              # Zona hidro + zona sísmica por código postal
│   └── asesores_ejemplo.xlsx      # Catálogo de asesores (reemplazar por el real)
├── assets/
│   ├── logo_raspberry.png         # Logo del broker (aparece en la app y en el PDF)
│   ├── logo_zurich.png            # Logo de la aseguradora (aparece en la app y en el PDF)
│   └── aviso_privacidad.md        # Texto del Aviso de Privacidad (editable)
├── pdfs_generados/                # PDFs de cotizaciones (se crea al usar la app)
├── polizas_emitidas/              # PDFs de pólizas subidas por el admin
├── correos_simulados/             # Correos "enviados" cuando no hay SMTP configurado
├── .env.example                  # Plantilla de configuración local (copiar a .env)
├── .streamlit/
│   └── secrets.toml.example      # Plantilla de configuración para la nube
└── requirements.txt
```
