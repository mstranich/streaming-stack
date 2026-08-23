# Servarr media stack

Stack multimedia en construcción para Windows con Rancher Desktop. Los
servicios se incorporarán y validarán de forma incremental.

## Requisitos

- Rancher Desktop iniciado con el motor **Moby/dockerd**.
- Docker Compose disponible mediante `docker compose`.
- Ejecutar los comandos desde la raíz de este repositorio.

## Inicializar la estructura de datos

El servicio one-shot `init-data` ejecuta
`scripts/init-data-dirs.sh` dentro de `bash:5.3.3`:

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

