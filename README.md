# Servarr media stack

Stack multimedia en construcción para Windows con Rancher Desktop. Los
servicios se incorporarán y validarán de forma incremental.

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

Los scripts Python concentran la automatización del proyecto:

- `scripts/init-data-dirs.py`: prepara filesystem, propietario y permisos.
- `scripts/configure-stack.py`: configura APIs después del arranque.

Cuando se incorporen Sonarr y Radarr, `configure-stack.py` recibirá sus
funciones para poder configurar las tres aplicaciones con el mismo comando.

## Incorporación de futuros servicios

Cuando se agreguen Transmission, Sonarr, Radarr y los demás componentes, podrán
declarar la siguiente dependencia para asegurar la estructura antes de iniciar:

```yaml
depends_on:
  init-data:
    condition: service_completed_successfully
```

La comunicación de APIs entre esos servicios se realizará sobre la red privada
de Compose utilizando nombres DNS internos, no `localhost`.

## Documentación del proyecto

- [`BACKLOG.md`](BACKLOG.md): alcance, orden de incorporación y pendientes.
- [`VALIDATION.md`](VALIDATION.md): pruebas realizadas sobre Rancher Desktop.
