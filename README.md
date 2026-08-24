# Servarr media stack

Stack multimedia en construcción para Windows con Rancher Desktop. Los
servicios se incorporarán y validarán de forma incremental.

> Estado: alcance funcional inicial completado. Las imágenes están fijadas a
> versiones legibles validadas y la operación se realiza con controles de salud,
> diagnóstico y backup documentados.

## Requisitos

- Rancher Desktop iniciado con el motor **Moby/dockerd**.
- Docker Compose disponible mediante `docker compose`.
- Ejecutar los comandos desde la raíz de este repositorio.

## Inicializar la estructura de datos

El servicio one-shot `init-data` ejecuta
`scripts/init-data-dirs.py` dentro de `python:3.13-alpine`:

```powershell
docker compose up init-data
```

También puede ejecutarse sin conservar el contenedor terminado:

```powershell
docker compose run --rm init-data
```

El script aplica un **upsert de directorios** mediante `mkdir -p`: crea las
carpetas ausentes y deja intactas las existentes y su contenido. Por eso es
seguro volver a ejecutarlo cuando sea necesario.

Además, asigna a cada directorio el `PUID`/`PGID` compartido y permisos `775`.
Los contenedores LinuxServer utilizan esos mismos valores y `UMASK=002`, de modo
que los archivos nuevos quedan escribibles por el usuario y grupo compartidos.

El contenedor:

- termina inmediatamente después de completar la inicialización;
- no se reinicia (`restart: "no"`);
- no tiene acceso a red;
- usa un sistema raíz de sólo lectura;
- sólo escribe dentro de `./data`;
- monta `./scripts` como sólo lectura.

La estructura resultante es:

```text
data/
├── torrents/
│   ├── movies/
│   ├── music/
│   ├── books/
│   └── tv/
├── usenet/
│   ├── movies/
│   ├── music/
│   ├── books/
│   └── tv/
└── media/
    ├── Movies/
    ├── Music/
    ├── Books/
    └── TV/
```

Git conserva únicamente `data/.gitkeep`; las subcarpetas y su contenido son
datos locales ignorados por `.gitignore`.

## Transmission Web

Transmission funciona como cliente torrent del stack y como servidor Web para
uso humano. No es necesario instalar Transmission para Windows.

1. Crear la configuración local a partir del ejemplo:

   ```powershell
   Copy-Item .env.example .env
   ```

2. Editar `.env` y reemplazar obligatoriamente `TRANSMISSION_PASS=change-me` y
   `SERVARR_PASS=change-me-too`. `.env` está ignorado por Git.

   `SERVARR_USER` y `SERVARR_PASS` son las credenciales Web compartidas por
   Prowlarr y los futuros Sonarr, Radarr y Bazarr. Transmission conserva sus
   propias variables `TRANSMISSION_USER` y `TRANSMISSION_PASS`.
   `SERVARR_UI_LANGUAGE` define el idioma común de las interfaces *arr; el
   valor inicial `es_MX` corresponde a Español (Latino).

   Para este stack se mantiene una identidad Linux compartida por defecto:
   `PUID=1000`, `PGID=1000` y `UMASK=002`. Todos los futuros servicios que
   escriban en `/data` deberán utilizar esos mismos valores.

3. Iniciar Transmission junto con la inicialización de carpetas:

   ```powershell
   docker compose up -d transmission
   ```

4. Abrir [http://localhost:9091](http://localhost:9091) e ingresar con
   `TRANSMISSION_USER` y `TRANSMISSION_PASS`.

5. En las preferencias de Transmission, establecer el directorio de descarga
   en `/data/torrents`. Los servicios *arr verán exactamente la misma ruta.

La Web UI está enlazada a `127.0.0.1` y sólo es accesible desde este equipo. Los
puertos peer TCP/UDP `51413` se publican en todas las interfaces para recibir
conexiones BitTorrent. Ambos puertos pueden cambiarse en `.env`.

Comandos operativos:

```powershell
# Estado
docker compose ps

# Logs
docker compose logs -f transmission

# Detener sin borrar configuración ni datos
docker compose down
```

## Prowlarr Web

Prowlarr centraliza los indexers de Sonarr, Radarr y otros servicios *arr. Su
configuración persiste en `./config/prowlarr` y utiliza la identidad compartida
`PUID`/`PGID` definida en `.env`.

Iniciar Prowlarr:

```powershell
docker compose up -d prowlarr
```

Abrir [http://localhost:9696](http://localhost:9696) e ingresar con
`SERVARR_USER` y `SERVARR_PASS`. La Web UI está enlazada únicamente a
`127.0.0.1`. `configure-stack` habilita la autenticación por formulario y
reconcilia esas credenciales en cada ejecución. La autenticación se omite para
direcciones locales, pero continúa requerida para accesos no locales.

Cuando se incorporen Sonarr y Radarr, Prowlarr los alcanzará por
la red privada de Compose mediante:

```text
http://sonarr:8989
http://radarr:7878
```

Si se configura Transmission como cliente para búsquedas manuales de Prowlarr,
su dirección interna será:

```text
http://transmission:9091
```

No debe utilizarse `localhost` para conexiones entre contenedores.

La integración se automatiza con el servicio one-shot `configure-stack`. Forma
parte del arranque normal, por lo que este comando inicia los servidores y
aplica la configuración:

```powershell
docker compose up
```

Para volver a ejecutar únicamente el upsert:

```powershell
docker compose run --rm configure-stack
```

El script espera a Prowlarr y Transmission, lee la API key directamente desde
`/config`, toma ambos juegos de credenciales desde `.env`, prueba la conexión,
crea o actualiza el Download Client y configura el acceso Web de Prowlarr
mediante la API oficial. También valida y configura el idioma indicado por
`SERVARR_UI_LANGUAGE`. No imprime secretos ni los guarda en el repositorio y
puede ejecutarse nuevamente sin duplicar el cliente.

### FlareSolverr

FlareSolverr se ejecuta como proxy anti-bot interno para los indexers de
Prowlarr que lo necesiten. No publica ningún puerto en Windows: Prowlarr lo
alcanza exclusivamente por la red privada de Compose en
`http://flaresolverr:8191`.

`configure-stack` espera su healthcheck y crea o actualiza de forma idempotente
el **Indexer Proxy** llamado `FlareSolverr`, probando la conexión antes de
guardarlo. También crea el tag `flaresolver` y lo asigna al proxy. Para utilizar
FlareSolverr, se debe asignar ese mismo tag a cada indexer protegido; así los
demás indexers no envían tráfico innecesario por el proxy.

Los valores operativos se ajustan desde `.env`:

```dotenv
FLARESOLVERR_LOG_LEVEL=info
FLARESOLVERR_LOG_HTML=false
FLARESOLVERR_TAG=flaresolver
FLARESOLVERR_REQUEST_TIMEOUT=60
```

Los scripts Python concentran la automatización del proyecto:

- `scripts/init-data-dirs.py`: prepara filesystem, propietario y permisos.
- `scripts/configure-stack.py`: configura APIs después del arranque.

Cuando se incorporen Sonarr y Radarr, `configure-stack.py` recibirá sus
funciones para poder configurar las tres aplicaciones con el mismo comando.

## Sonarr, Radarr y Bazarr

Los tres servicios se publican sólo en loopback:

- Sonarr: [http://localhost:8989](http://localhost:8989)
- Radarr: [http://localhost:7878](http://localhost:7878)
- Bazarr: [http://localhost:6767](http://localhost:6767)

Sonarr utiliza `/data/media/TV` como carpeta raíz y la categoría `tv` de
Transmission. Radarr utiliza `/data/media/Movies` y la categoría `movies`.
Ambos reciben las credenciales compartidas, el idioma `SERVARR_UI_LANGUAGE` y
la política `disabledForLocalAddresses`, igual que Prowlarr.

Prowlarr registra Sonarr y Radarr como **Applications** mediante sus direcciones
internas y sincronización completa de indexers. Bazarr no es una Application
compatible de Prowlarr: es Bazarr quien consume directamente las APIs de
Sonarr y Radarr. `configure-stack` también automatiza esas dos conexiones.

Bazarr tampoco ofrece el modo `disabledForLocalAddresses` ni comparte la API
de idioma de Servarr. El script no modifica su autenticación ni promete
configurar el idioma de su UI; por ahora la protección efectiva es publicar su
puerto exclusivamente en `127.0.0.1`. Sus proveedores y perfiles de idiomas de
subtítulos se configurarán en una etapa posterior.

Jellyfin permanece instalado directamente en Windows y no forma parte de este
Compose. Bazarr puede integrarse con él mediante la API usando:

```dotenv
JELLYFIN_HOST=host.docker.internal
JELLYFIN_PORT=8096
JELLYFIN_API_KEY=clave-creada-en-el-dashboard-de-jellyfin
```

La clave se crea en Jellyfin bajo **Dashboard → API Keys** y sólo se guarda en
el `.env` ignorado por Git. Si la clave está presente, `configure-stack`
habilita la integración, configura el método de refresco `immediate` y ejecuta
el test de conexión de Bazarr. Si está vacía, omite únicamente esta integración
sin impedir el resto del arranque. Las bibliotecas concretas se seleccionan
después desde la UI de Bazarr, ya que sus identificadores dependen de Jellyfin.

Arrancar el stack y aplicar todos los upserts:

```powershell
docker compose up -d
```

## Endurecimiento operativo

Los servicios permanentes usan `restart: unless-stopped`,
`no-new-privileges`, healthchecks HTTP y rotación `json-file`. `init-data`,
`configure-stack` y las herramientas del perfil `ops` son procesos one-shot y
conservan `restart: "no"`. Los límites de logs y la alarma de disco se pueden
ajustar en `.env`:

```dotenv
LOG_MAX_SIZE=10m
LOG_MAX_FILES=3
MIN_FREE_SPACE_GB=20
```

Docker no impone aquí una cuota al bind mount `./data`: el umbral sólo hace
fallar el diagnóstico antes de que el disco se agote. Los límites de velocidad,
ratio, horarios y retención se configuran deliberadamente en Transmission.

Las UIs permanecen publicadas en `127.0.0.1`; únicamente el puerto peer de
Transmission está disponible en todas las interfaces. No se monta el socket de
Docker ni se usan contenedores privilegiados. Para acceso desde fuera del
equipo se debe incorporar primero VPN o proxy con TLS; no se deben publicar las
UIs directamente en Internet.

### Diagnóstico

Ejecutar desde PowerShell:

```powershell
.\scripts\diagnose-stack.ps1
```

El wrapper comprueba estado y health de los contenedores y luego ejecuta una
sonda sin privilegios sobre DNS interno, HTTP, estructura `/data`, espacio
libre y Jellyfin externo. No imprime contraseñas ni API keys. Para investigar:

```powershell
docker compose ps
docker compose logs --tail 200 prowlarr flaresolverr sonarr radarr bazarr transmission
```

### Backup y restauración

El backup contiene `config/` y `.env`, por lo tanto contiene bases de datos,
contraseñas y API keys. `backups/` está ignorado por Git; copie cada archivo y
su `.sha256` a un almacenamiento externo protegido.

```powershell
# Crear backup con checksum SHA-256
docker compose --profile ops run --rm backup-config

# Listar los archivos creados
Get-ChildItem .\backups\servarr-config-*
```

Una copia sólo cuenta como válida después de probar la restauración. Para
restaurar, detener primero todo el stack y seleccionar únicamente el nombre del
archivo, sin rutas:

```powershell
docker compose down
$env:RESTORE_ARCHIVE = "servarr-config-AAAAMMDDTHHMMSSZ.tar.gz"
docker compose --profile ops run --rm restore-config
Remove-Item Env:RESTORE_ARCHIVE
docker compose up -d
.\scripts\diagnose-stack.ps1
```

El restaurador verifica el checksum y rechaza rutas, enlaces o miembros no
permitidos antes de reemplazar `config/` y `.env`. No respalda torrents ni
medios; `data/media` debe tener su propia estrategia de copia si no existe otra
copia recuperable.

### Secretos

- `.env`, `config/` y `backups/` nunca deben agregarse a Git.
- `.env.example` contiene sólo credenciales ficticias y versiones públicas.
- No copiar salidas de configuración completas a incidencias o documentación.
- Si una API key se filtra, revocarla/regenerarla en la aplicación y ejecutar
  nuevamente `configure-stack`.
- Mantener una copia protegida de `.env` junto al backup; quien pueda leer el
  archivo puede acceder a todas las aplicaciones.

## Actualización y rollback

Las imágenes no usan `latest`: `.env` fija tags de versión legibles validados. Se
actualiza **un servicio por vez**:

1. Leer las notas de la nueva versión y confirmar compatibilidad.
2. Crear un backup y copiarlo fuera del repositorio.
3. Guardar el tag anterior de la variable `*_IMAGE`.
4. Elegir el nuevo tag de versión y cambiar sólo esa variable en `.env` y
   `.env.example`.
5. Ejecutar `docker compose pull <servicio>` y luego
   `docker compose up -d <servicio>`.
6. Esperar `healthy`, revisar sus logs y ejecutar
   `.\scripts\diagnose-stack.ps1`.
7. Verificar manualmente la integración relevante antes de actualizar otro.

Si falla, restaurar el tag anterior y recrear el servicio:

```powershell
docker compose pull <servicio>
docker compose up -d --force-recreate <servicio>
```

Si la aplicación migró su base de datos de forma incompatible, mantener el
stack detenido, restaurar el backup correspondiente y volver a iniciar. No se
debe ejecutar `docker compose down -v`: los datos usan bind mounts, pero ese
comando establece un precedente peligroso para futuros volúmenes.

## Incorporación de futuros servicios

Cuando se agreguen los demás componentes, podrán
declarar la siguiente dependencia para asegurar la estructura antes de iniciar:

```yaml
depends_on:
  init-data:
    condition: service_completed_successfully
```

La comunicación de APIs entre esos servicios se realizará sobre la red privada
de Compose utilizando nombres DNS internos, no `localhost`.

## Documentación del proyecto

- [`VALIDATION.md`](VALIDATION.md): pruebas realizadas sobre Rancher Desktop.
