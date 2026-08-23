# Servarr media stack — propuesta y backlog

> Estado: exploración inicial. Este documento registra decisiones, incógnitas y
> criterios de aceptación; todavía no define el `compose.yaml` definitivo.

## Objetivo

Construir y validar el stack **un servicio web por vez** sobre Windows con
Rancher Desktop, conservando rutas internas coherentes para descargas y medios.

```text
Prowlarr ──indexers──> Sonarr / Radarr ──descargas──> Transmission
                              │                            │
                              └──── importa / hardlink ────┘
                                           │
                                      /data/media
                                           │
                                        Jellyfin

Bazarr ── subtítulos ──> bibliotecas administradas por Sonarr / Radarr
Bash   ── herramientas y scripts del proyecto (perfil manual)
```

## Alcance inicial propuesto

- Rancher Desktop con motor **Moby/dockerd**, para disponer de Docker API y
  Docker CLI/Compose.
- Una red privada de Compose compartida por todos los servicios. Las APIs se
  consumirán mediante DNS interno (`http://prowlarr:9696`,
  `http://transmission:9091`, `http://sonarr:8989`, etc.); los puertos del host
  se reservan para acceso humano y no para comunicación entre contenedores.
- Servicios previstos: `bash`, `transmission`, `prowlarr`, `sonarr`, `radarr`,
  `jellyfin` y `bazarr`.
- Acceso inicial mediante puertos publicados en `localhost`; sin proxy inverso.
- Una sola raíz interna `/data` compartida por Transmission, Sonarr, Radarr,
  Jellyfin y Bazarr. Esto evita traducciones de rutas y permite investigar
  hardlinks/movimientos atómicos.
- Configuración persistente separada por servicio bajo `./config/<servicio>`.
- Datos bajo `./data`, inicialmente dentro de este proyecto para simplificar la
  validación. Git sólo conserva `data/.gitkeep`; las subcarpetas locales se crean
  de forma idempotente con `scripts/init-data-dirs.py`. Antes de cargar una
  biblioteca real se decidirá su ubicación final.
- Imágenes mantenidas por LinuxServer.io como opción inicial consistente para
  los servicios, sujetas a revisión y fijación de versión antes de producción.

## Decisiones de alcance ya tomadas

- [x] Reemplazar Jackett por Prowlarr.
- [x] Reemplazar qBittorrent por Transmission.
- [x] No incluir Caddy en la primera etapa.
- [x] No incluir todavía FlareSolverr, Jellyseerr ni Wizarr.
- [x] Incorporar un contenedor de Bash para ejecutar scripts/comandos Linux.
- [x] Avanzar servicio por servicio, con prueba y documentación antes de sumar
  el siguiente.

## Backlog por etapas

### 0. Base de Rancher Desktop, red y almacenamiento

- [x] Confirmar que Rancher Desktop usa `dockerd (moby)`, no `containerd`.
- [x] Registrar versiones de Rancher Desktop, Docker CLI y Compose (`docker
  version` y `docker compose version`).
- [x] Confirmar que Compose puede montar rutas relativas desde `H:\\Servarr`.
- [x] Probar creación, modificación y lectura de archivos desde host y
  contenedor en `./config` y `./data`.
- [x] Probar explícitamente hardlinks dentro del mismo montaje `/data` y
  documentar si NTFS + WSL/Rancher Desktop los preserva correctamente.
- [x] Validar red privada, DNS por nombre de servicio y consumo HTTP de una API
  simulada entre dos servicios de Compose.
- [x] Definir la estructura inicial y crearla mediante un script idempotente:

  ```text
  data/
  ├── torrents/{movies,music,books,tv}/
  ├── usenet/{movies,music,books,tv}/
  └── media/{Movies,Music,Books,TV}/
  ```

- [ ] Definir `.env.example` (`TZ`, rutas, puertos y, si corresponde,
  `PUID`/`PGID`) sin guardar secretos.
- [x] Adoptar una identidad Linux compartida (`PUID=1000`, `PGID=1000`) y
  `UMASK=002` para todos los servicios que escriban en `/data`; el inicializador
  aplica propietario/grupo y modo `775` a los directorios administrados.
- [ ] Completar `.gitignore` para `config/`, `.env` y otros datos generados. La
  exclusión de `data/*`, preservando `data/.gitkeep`, ya está definida.
- [ ] Elegir una política de tags: durante el spike puede usarse `latest`, pero
  la configuración reproducible debe fijar versiones/digests.

**Resultado validado el 2026-08-23:** Compose funciona desde PowerShell, la red
interna resuelve nombres de servicio, un contenedor consumió HTTP desde otro,
el bind mount sobre `H:` fue escribible y dos nombres enlazados conservaron el
mismo inode con contador de enlaces `2`. Detalle en `VALIDATION.md`.

### 1. Contenedor de inicialización

- [x] Unificar la automatización en `python:3.13-alpine`.
- [x] Configurarlo como servicio one-shot `init-data`, sin reinicio ni daemon
  permanente.
- [x] Montar `./scripts` como `/workspace/scripts` en modo lectura y establecer
  `/workspace` como directorio de trabajo.
- [x] Montar únicamente `./data` con escritura; desactivar red y usar el sistema
  raíz del contenedor como sólo lectura.
- [ ] Añadir utilidades únicamente cuando exista un caso concreto (`curl`,
  `jq`, `git`, etc.); si hacen falta varias, crear un Dockerfile pequeño y
  reproducible en vez de instalar en cada ejecución.
- [x] Documentar en `README.md` los comandos `docker compose up init-data` y
  `docker compose run --rm init-data`.
- [x] Ejecutar `scripts/init-data-dirs.py` desde este contenedor para inicializar
  `data/`; no se necesita BusyBox ni Bash adicional. Se validó su
  idempotencia ejecutándolo dos veces.

**Criterio de salida:** se puede abrir Bash, leer scripts del repositorio y
crear un archivo de prueba en el volumen autorizado.

### 2. Transmission

- [x] Usar `lscr.io/linuxserver/transmission:latest` durante esta etapa.
- [x] Persistir `/config`; montar la raíz común del host como `/data`.
- [x] Publicar la Web UI `9091` para acceso humano desde Windows; Transmission
  en Docker será también el cliente de uso manual, sin instalar otro
  Transmission nativo.
- [x] Enlazar inicialmente la Web UI sólo a `127.0.0.1:9091`; no exponerla a
  Internet directamente.
- [x] Publicar los puertos peer TCP/UDP `51413`, parametrizables desde `.env`.
- [x] Definir autenticación de la UI mediante `.env` ignorado por Git.
- [x] Configurar y documentar el destino de descargas bajo `/data/torrents`.
- [x] Validar Web UI/RPC autenticada, reinicio y persistencia de configuración.
- [ ] Validar la descarga de un archivo legal de prueba.

**Criterio de salida:** Transmission conserva su configuración y escribe en la
ruta que luego verán Sonarr/Radarr exactamente como `/data/...`.

### 3. Prowlarr

- [x] Usar `lscr.io/linuxserver/prowlarr:latest` durante esta etapa.
- [x] Persistir `/config` y publicar `9696` sólo para acceso local inicial.
- [x] Aplicar la identidad compartida `PUID=1000`, `PGID=1000`, `UMASK=002`.
- [ ] Crear cuenta/autenticación y añadir un indexer de prueba permitido.
- [x] Crear un servicio/script one-shot `configure-stack` que, después del
  asistente inicial, lea la API key desde `/config/config.xml`, tome las
  credenciales de Transmission desde `.env`, pruebe la conexión y haga upsert
  del Download Client mediante `/api/v1/downloadclient`.
- [x] Validar dos ejecuciones consecutivas: creación inicial y actualización
  posterior del mismo Download Client sin duplicados.
- [x] Verificar búsqueda desde Radarr usando indexers sincronizados por Prowlarr
  y envío del torrent seleccionado a Transmission.
- [ ] Documentar API key como secreto operativo, no en Git.

**Criterio de salida:** Prowlarr reinicia sin perder datos y un indexer de prueba
responde correctamente.

### 4. Sonarr

- [x] Añadir Sonarr con `/config` y la misma raíz `/data`.
- [x] Configurar raíz de series en `/data/media/TV`.
- [x] Conectar Prowlarr mediante su integración de Applications.
- [x] Conectar Transmission usando hostname interno `transmission` y puerto
  interno `9091`.
- [ ] Validar categorías, importación y hardlink/movimiento con contenido de
  prueba.

**Criterio de salida:** flujo completo de serie de prueba desde búsqueda hasta
importación, sin Remote Path Mapping innecesario.

### 5. Radarr

- [x] Repetir el patrón de Sonarr para `/data/media/Movies`.
- [x] Conectar Prowlarr y Transmission por DNS interno de Compose.
- [ ] Validar descarga efectiva, categoría e importación de película de prueba;
  Big Buck Bunny llegó correctamente a Transmission, pero no inició por falta
  de seeds.

**Criterio de salida:** flujo completo de película y coexistencia con Sonarr.

### 6. Bazarr

- [x] Añadir Bazarr con `/config` y acceso a `/data/media`.
- [x] Conectar Sonarr y Radarr por sus nombres de servicio y API keys.
- [x] Documentar que Bazarr no es una Application soportada por Prowlarr y que
  no implementa la política Servarr `disabledForLocalAddresses`.
- [ ] Validar descarga y almacenamiento de un subtítulo de prueba.

**Criterio de salida:** Bazarr encuentra los archivos con las mismas rutas que
Sonarr/Radarr y persiste su configuración.

### 7. Validación de GPU en Rancher Desktop/Moby

- [ ] Identificar fabricante, modelo y controlador instalado en Windows.
- [ ] Confirmar que la GPU es visible desde el backend WSL2 usado por Rancher
  Desktop.
- [ ] Confirmar que Moby puede entregar el dispositivo a un contenedor de
  prueba sin privilegiarlo innecesariamente.
- [ ] Ejecutar una carga de transcodificación o cómputo reproducible y registrar
  evidencia de que usa GPU en lugar de CPU.
- [ ] Documentar la sintaxis Compose necesaria (`devices`, CDI u otra opción
  compatible con el fabricante) y cualquier prerrequisito del host.
- [ ] Definir un fallback explícito a CPU si la GPU no resulta estable.

**Criterio de salida:** un contenedor de prueba detecta y utiliza la GPU con la
misma configuración que se incorporará luego a Jellyfin.

### 8. Jellyfin

- [ ] Añadir Jellyfin usando la estrategia de aceleración decidida en la etapa
  anterior; no configurar GPU basándose sólo en detección teórica.
- [ ] Montar `/data/media` como sólo lectura inicialmente.
- [ ] Crear bibliotecas de películas y series y validar escaneo/reproducción.
- [ ] Revisar puertos de descubrimiento sólo si realmente se necesitan.

**Criterio de salida:** Jellyfin detecta y reproduce los medios importados sin
capacidad de modificar descargas.

### 9. Endurecimiento y operación

- [ ] Añadir healthchecks sólo donde exista una comprobación fiable.
- [ ] Definir `restart`, límites razonables y rotación de logs.
- [ ] Revisar exposición: enlazar UIs a `127.0.0.1` mientras no haya acceso LAN
  deliberado.
- [ ] Evitar privilegios, Docker socket y secretos dentro del repositorio.
- [ ] Crear scripts idempotentes para inicialización y diagnóstico.
- [ ] Documentar backup/restore de `config/` y qué partes de `data/` se respaldan.
- [ ] Validar actualización servicio por servicio y rollback.
- [ ] Sólo después evaluar Caddy/TLS y los servicios postergados.

## Incógnitas que debemos resolver antes del Compose definitivo

1. **Ubicación real de medios:** ¿seguirán en `H:` o irán a otro disco/ruta?
2. **Hardlinks sobre Windows:** la prueba básica sobre `H:` resultó exitosa;
   falta repetirla con archivos grandes y el flujo real Transmission → *arr.
3. **Acceso:** ¿sólo `localhost`, toda la LAN o eventualmente Internet? La
   respuesta cambia puertos, autenticación y proxy/TLS.
4. **GPU de Jellyfin:** fabricante/modelo y disponibilidad dentro de la VM WSL.
5. **Identidad de archivos:** validar si `PUID=1000`/`PGID=1000` es apropiado en
   este backend; no asumir que los permisos se comportan igual que en Linux
   nativo.
6. **Bash:** qué comandos concretos deberá ejecutar y qué montajes necesita.
7. **Contenido adicional:** confirmar si Lidarr/música queda fuera o entra en
   una fase posterior.

## Servicios expresamente postergados

- Caddy / proxy inverso / TLS.
- FlareSolverr.
- Jellyseerr.
- Wizarr.
- Clonado y build local de Prowlarr.

## Fuentes de referencia

- [Servarr Wiki — Docker Guide](https://wiki.servarr.com/docker-guide)
- [Pelado Nerdworks — media-stack](https://github.com/Pelado-Nerdworks/media-stack)
- [Rancher Desktop — selección de container engine](https://docs.rancherdesktop.io/ui/preferences/container-engine/general/)
- [LinuxServer.io — Prowlarr](https://docs.linuxserver.io/images/docker-prowlarr/)
- [LinuxServer.io — Transmission](https://docs.linuxserver.io/images/docker-transmission/)
- [Repositorio upstream de Prowlarr](https://github.com/Prowlarr/Prowlarr)
