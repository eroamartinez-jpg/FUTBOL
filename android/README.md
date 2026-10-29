# Pocket Bot para Android

App nativa (Kotlin) con la misma estrategia que `pocket_bot/` (Python):
escanea los activos de Pocket Option, calcula la tendencia (CALL/PUT), la
valida con un backtest por activo e indica la **hora de entrada** y de
expiración en la hora del teléfono. Sigue escaneando en segundo plano y
**avisa con una notificación** cuando aparece una señal recomendada, así
puedes tener abierta la app de Pocket Option mientras tanto.

> **Aviso:** las opciones binarias son de muy alto riesgo y la mayoría de los
> operadores pierde dinero. Las señales son estimaciones estadísticas, no
> garantías. Úsala primero con la cuenta DEMO. Pocket Option no tiene API
> oficial: la conexión imita a su web y puede dejar de funcionar si la cambian.
> La app solo da señales; no abre operaciones.

## Instalar

1. En GitHub: **Actions** → *App Android pocket_bot* → última ejecución en
   verde → **Artifacts** → `PocketBot-android`. Descarga el zip en el móvil y
   extrae `PocketBot.apk`.
2. Ábrelo. Android pedirá permitir "instalar apps de origen desconocido" para
   el navegador o el gestor de archivos; acéptalo solo para esta instalación.
3. Al abrir la app, acepta el permiso de notificaciones.

Requiere Android 7.0 o superior.

## Usar

1. **Iniciar sesión**: abre pocketoption.com dentro de la app. Entra con tu
   cuenta y abre la sala de operaciones (demo o real). La app captura la
   sesión (SSID) automáticamente y vuelve a la pantalla principal.
   - Alternativa: **Pegar SSID** si ya tienes el mensaje `42["auth",…]`.
   - La sesión se guarda solo en el teléfono. Si caduca, vuelve a iniciar sesión.
2. Elige temporalidad, expiración, payout y confianza mínimos.
3. **▶ Iniciar escaneo**. En cada cierre de vela analiza todos los activos
   activos y muestra las señales ★ con:
   - **Entrada HH:MM:SS → expira HH:MM:SS** y la cuenta atrás.
   - Confianza, payout y % de acierto histórico frente al % de equilibrio.
4. Para detenerlo: **■ Detener** o el botón *Detener* de la notificación.

Ten activada la hora automática del teléfono: la hora de entrada se calcula
con el reloj del dispositivo.

## Código

- `core/` — Kotlin puro, sin Android: indicadores, estrategia, backtest,
  hora de entrada y protocolo de Pocket Option. Probado contra los resultados
  del bot de Python (`ParityTest`): `gradle -p core test`.
- `app/` — interfaz, inicio de sesión (WebView), conexión WebSocket (OkHttp)
  y servicio de escaneo en primer plano.

Compilar localmente (requiere Android SDK): `gradle :app:assembleRelease`
dentro de `android/`.
