# Escáner de vulnerabilidades: OpenVAS / Greenbone Community Edition en Debian 13


## Índice

1. Introducción a la herramienta
2. Preparación del entorno
3. Método A: instalación con Docker (el que usamos)
4. Método B: compilación desde el código fuente (verificado y desactivado)
5. Configuración de la herramienta en la interfaz web (GSA)
6. Pruebas de funcionamiento y uso real del escáner
7. Automatización desde la línea de comandos
8. Mantenimiento, copias de seguridad y problemas habituales
9. Cierre
- Anexo. Ficheros y rutas de nuestra instalación

## 1. Introducción a la herramienta

### 1.1 ¿Qué es un escáner de vulnerabilidades?

Un **escáner de vulnerabilidades** es un programa que examina una máquina o una red, descubre qué equipos están encendidos, qué puertos tienen abiertos, qué servicios y versiones corren en ellos, y **compara todo eso con una base de datos de fallos conocidos** (CVE). Al final entrega un informe ordenado por gravedad con el fallo encontrado, la prueba que lo demuestra y la solución recomendada.

Conceptos que vamos a usar todo el tiempo:

- **CVE** (Common Vulnerabilities and Exposures): identificador público de un fallo concreto, por ejemplo `CVE-2021-44228` (Log4Shell, el que veremos en la parte R4).
- **CVSS**: nota de 0 a 10 que mide la gravedad de un CVE. En el informe aparece como *severidad*: 0 Log, 0,1-3,9 Baja, 4,0-6,9 Media, 7,0-8,9 Alta, 9,0-10 Crítica.
- **NVT / VT** (Network Vulnerability Test): cada una de las pruebas individuales del escáner. Son miles de pequeños scripts en un lenguaje propio llamado NASL. El conjunto de todas se llama *feed*.
- **QoD** (Quality of Detection): porcentaje que indica lo seguro que está el escáner de que el fallo existe de verdad (un 99 % significa que lo ha comprobado con una prueba directa; un 30 % significa que solo lo deduce por la versión del software).
- **Falso positivo**: el informe dice que hay un fallo y en realidad no lo hay (por ejemplo, porque la distribución ha parcheado el fallo sin cambiar el número de versión).
- **Escaneo autenticado**: el escáner entra en la máquina con un usuario (por SSH o SMB) y mira los paquetes instalados. Es mucho más exacto que mirar solo desde fuera.

### 1.2 ¿Qué es OpenVAS / Greenbone?

OpenVAS (*Open Vulnerability Assessment Scanner*) nació en 2005 como bifurcación libre de Nessus cuando este dejó de ser software libre. Hoy lo mantiene la empresa alemana Greenbone, y su versión gratuita se llama **Greenbone Community Edition**. Incluye el *Community Feed*, con del orden de cien mil pruebas, y se actualiza a diario.

No es un único programa, sino un conjunto de servicios:

| Componente | Función |
| --- | --- |
| **gvmd** (Greenbone Vulnerability Manager) | El «cerebro»: usuarios, objetivos, tareas, informes, alertas, programaciones. Guarda todo en PostgreSQL |
| **openvas-scanner** + **ospd-openvas** | El motor que lanza las pruebas contra los equipos y habla con gvmd |
| **openvasd** / **notus** | Servicio que comprueba versiones de paquetes cuando hay credenciales (escaneo autenticado) |
| **PostgreSQL** (con la extensión **pg-gvm**) | Base de datos de gvmd |
| **Redis** | Almacén en memoria que usa el escáner para las pruebas y los resultados temporales |
| **MQTT broker** | Mensajería interna entre scanner y servicios (en la versión de contenedores) |
| **gsad** + **GSA** (Greenbone Security Assistant) | Servidor y aplicación web: la interfaz con la que trabajamos en el navegador |
| **gvm-tools** | Herramientas de línea de comandos (`gvm-cli`, `gvm-script`) para automatizar |
| **Feed de datos** | VTs, datos SCAP (CPE/CVE), datos CERT, listas de puertos, configuraciones de escaneo y formatos de informe |

### 1.3 ¿Para qué sirve? Casos reales de uso

1. **Gestión de parches en una empresa.** Cada semana se escanea la red interna y se compara con la semana anterior: ¿qué servidores han quedado sin parchear? Es el uso más habitual.
2. **Cumplimiento normativo.** Auditorías ISO 27001, PCI-DSS (tarjetas de pago) o el Esquema Nacional de Seguridad exigen análisis de vulnerabilidades periódicos con evidencia.
3. **Pruebas de intrusión (pentesting).** Es la fase de descubrimiento: antes de intentar explotar nada se escanea para saber por dónde entrar. Encaja directamente con nuestra parte R2 (reconocimiento) y R3 (Metasploitable).
4. **Verificar un parche.** Tras corregir una vulnerabilidad, volvemos a escanear para comprobar que ha desaparecido del informe.
5. **Inventario.** Un escaneo de descubrimiento (*Host Discovery*) sirve para saber qué máquinas hay realmente en una red, incluidas las que nadie recordaba.

Ejemplos de incidentes reales en los que un escáner habría dado el aviso a tiempo:

- **Equifax (2017):** una brecha de unos 147 millones de personas que se atribuyó a una vulnerabilidad conocida de Apache Struts (CVE-2017-5638) sin parchear.
- **WannaCry (2017):** se propagó explotando MS17-010 (EternalBlue) en equipos Windows sin actualizar; un escáner detecta este fallo con una prueba directa.
- **Log4Shell (2021, CVE-2021-44228):** miles de servicios tenían una librería Java vulnerable sin saberlo; los escáneres incorporaron la detección en cuestión de días.

### 1.4 Alternativas y por qué elegimos OpenVAS

| Herramienta | Licencia | Comentario |
| --- | --- | --- |
| **OpenVAS / Greenbone CE** | Software libre (GPL), gratis | La elegida: gratuita, completa y sin límite de IPs |
| Nessus Essentials | Propietaria, gratis hasta 16 IPs | Muy pulida, pero limitada en la versión gratuita |
| Nexpose / InsightVM | Propietaria | Orientada a empresa |
| Nmap + scripts NSE | Libre | No es un escáner de vulnerabilidades completo, aunque `--script vuln` es útil como complemento |

## 2. Preparación del entorno

### 2.1 Requisitos de hardware

Según la documentación de Greenbone, el mínimo para compilar desde fuente es de 2 núcleos, 4 GB de RAM y 20 GB libres y lo recomendado es 4 núcleos, 8 GB de RAM y 60 GB libres. Para los contenedores pasa algo parecido. El feed inicial y las imágenes ocupan varios GB, y la carga inicial de las pruebas consume mucha CPU durante bastante rato.

Comprobamos nuestro equipo:

```sh
nproc
free -h
df -h /mnt/midisco
```

- `nproc` muestra el número de núcleos de CPU.
- `free -h` muestra la memoria RAM y el swap en un formato legible (`-h` = *human*, con unidades G/M).
- `df -h /mnt/midisco` muestra el espacio libre del disco donde vamos a trabajar. Necesitamos **al menos 40-60 GB libres**.

También revisamos el espacio del disco del sistema, porque es donde Docker guardaría todo si no lo cambiamos:

```
df -h / /mnt/midisco
```

### 2.2 Comprobar el sistema de ficheros de /mnt/midisco

Docker guarda sus capas con el controlador `overlay2`, que **no funciona** sobre sistemas de ficheros como NTFS, exFAT o FAT. Debe ser ext4 o XFS.

```sh
findmnt -no SOURCE,FSTYPE,OPTIONS /mnt/midisco
```

- `findmnt` consulta la tabla de montajes. Con `-n` quitamos la cabecera y con `-o` elegimos columnas: dispositivo, tipo de sistema de ficheros y opciones de montaje.
- Si el tipo es `ext4` o `xfs`, podemos continuar. Si es `ntfs`, `exfat` o `vfat`, tenemos que usar otro disco o, para el método A, una imagen/volumen intermedio con ext4.
- Además, `/mnt/midisco` debe montarse automáticamente **antes** de que arranque Docker (entrada en `/etc/fstab`). Si no, Docker arrancará con un directorio vacío y creará todo de nuevo.

### 2.3 Estructura de directorios

Organizamos todo en un único árbol para saber siempre dónde está cada cosa:

```sh
sudo mkdir -p /mnt/midisco/greenbone/{compose,backup,informes,fuentes,build}
sudo chown -R $USER:$USER /mnt/midisco/greenbone
ls /mnt/midisco/greenbone
```

- `mkdir -p` crea el directorio y todos los intermedios sin error si ya existen; la expansión `{a,b,c}` de bash crea varios a la vez.
- `chown -R $USER:$USER` hace que nuestro usuario sea el propietario, para no tener que usar `sudo` cada vez.
- Usaremos `compose/` para el método A, `fuentes/` y `build/` para el método B, `backup/` para copias de seguridad e `informes/` para exportar los informes PDF.

### 2.4 Actualizar el sistema

```bash
sudo apt update && sudo apt full-upgrade -y
```

- `apt update` refresca la lista de paquetes disponibles.
- `apt full-upgrade -y` instala todas las actualizaciones, incluidas las que cambian dependencias; `-y` responde «sí» automáticamente.

Instalamos también las dos herramientas que usaremos para descargar ficheros de forma segura:

```
sudo apt update
sudo apt install -y ca-certificates curl
```

- `apt update` actualiza los índices de paquetes de Debian.
- `ca-certificates` instala certificados de autoridades de confianza que se utilizan para validar conexiones HTTPS.
- `curl` descarga ficheros desde las direcciones oficiales.
- `-y` permite confirmar automáticamente la instalación de los paquetes.

## 3. Método A: instalación con Docker (el que usamos)

En este apartado documentamos la instalación que tenemos funcionando: los contenedores oficiales de Greenbone, instalados con su script `setup-and-start-greenbone-community-edition.sh`, más los ajustes que hemos añadido para guardar los datos en `/mnt/midisco` y para que todo arranque solo al encender el equipo.

> **Nota sobre la distribución.** Docker Engine sí ofrece paquetes para Debian 13 (Trixie). La documentación de contenedores de Greenbone consultada para esta práctica enumera Debian 12 (Bookworm), Ubuntu 24.04, Fedora 35/36 y CentOS Stream 9 como plataformas documentadas. Aunque el script ha funcionado en nuestro Debian 13, dejamos constancia de que Trixie no aparece en esa lista de sistemas probados por la guía de contenedores. Fuentes: [Docker Engine en Debian](https://docs.docker.com/engine/install/debian/) y [Greenbone Community Containers](https://greenbone.github.io/docs/latest/22.4/container/).

### 3.1 Qué es Docker y qué piezas instalamos

Un **contenedor** es un proceso aislado que lleva dentro todo lo que necesita (programa, librerías, configuración). Greenbone publica contenedores oficiales de cada componente y un fichero **Docker Compose** que describe cómo se conectan entre sí. Con eso evitamos compilar, resolver dependencias y configurar a mano PostgreSQL, Redis y systemd: se levanta todo con dos comandos y se puede destruir y repetir sin ensuciar el sistema.

En este método no compilamos los componentes de Greenbone uno por uno. Ejecutamos las imágenes oficiales publicadas por Greenbone, y Docker Compose se encarga de crear la red interna, los contenedores, los volúmenes y las dependencias entre servicios.

Los servicios principales son:

|Servicio|Función|
|---|---|
|`vulnerability-tests`|Copia al volumen persistente las pruebas de vulnerabilidad NASL (VT/NVT).|
|`notus-data`|Copia los datos que utiliza Notus para las comprobaciones autenticadas de paquetes.|
|`scap-data`|Proporciona la información SCAP, incluidos datos CVE/CPE.|
|`cert-bund-data` y `dfn-cert-data`|Proporcionan los avisos de seguridad de CERT-Bund y DFN-CERT.|
|`data-objects` y `report-formats`|Copian configuraciones de escaneo, listas de puertos, políticas y formatos de informe.|
|`redis-server`|Almacena datos temporales y datos de trabajo utilizados por el escáner.|
|`pg-gvm`|Ejecuta PostgreSQL, donde se almacena la base de datos de Greenbone.|
|`gpg-data`|Copia las claves de firma de Greenbone para comprobar que el feed es auténtico.|
|`mqtt-broker`|Mensajería interna entre el escáner y los demás servicios.|
|`gvmd`|Gestiona usuarios, objetivos, tareas, resultados y la importación de información del feed.|
|`openvas`, `ospd-openvas` y `openvasd`|Proporcionan el motor de escaneo, su interfaz OSP y el servicio Notus.|
|`gsad` y `gsa`|Proporcionan el servidor y la interfaz web.|
|`nginx`|Publica la interfaz web local mediante HTTPS y reenvía las peticiones a los servicios internos.|
|`gvm-tools`|Contenedor opcional con `gvm-cli` y `gvm-script` para manejar el escáner por línea de comandos (sección 7).|

Los contenedores de datos copian los ficheros del feed en volúmenes de Docker. Después, los servicios `ospd-openvas` y `gvmd` procesan los datos. Por eso, que un contenedor esté iniciado o saludable no significa por sí solo que toda la importación haya terminado. La documentación oficial distingue estas dos fases: descargar/copiar los datos y cargarlos en memoria y en la base de datos.

### 3.2 Instalar Docker Engine (repositorio oficial de Docker)

```sh
sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
```

- `ca-certificates` y `curl` permiten descargar por HTTPS con validación de certificados.
- `install -d` crea el directorio `/etc/apt/keyrings` con permisos 755; es el sitio estándar para guardar claves de repositorios de terceros.
- `curl -fsSL` descarga el fichero: `-f` falla si hay error HTTP, `-s` silencioso, `-S` muestra errores aun siendo silencioso, `-L` sigue redirecciones. La clave GPG sirve para que `apt` verifique que los paquetes realmente vienen de Docker.
- `chmod a+r` permite que cualquier usuario lea la clave (apt la lee con un usuario sin privilegios).

Añadimos el repositorio:

```sh
sudo tee /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/debian
Suites: $(. /etc/os-release && echo "$VERSION_CODENAME")
Components: stable
Signed-By: /etc/apt/keyrings/docker.asc
EOF
```

- `tee` escribe en un fichero con privilegios (con `sudo echo > fichero` no funcionaría, porque la redirección la hace nuestro usuario, no root).
- El `$(. /etc/os-release && echo "$VERSION_CODENAME")` se sustituye por `trixie`, el nombre en clave de Debian 13.
- Es el formato moderno `.sources` (deb822) que usa Debian 13.

Instalamos los paquetes:

```sh
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

- `docker-ce`: el servicio (demonio) de Docker. `docker-ce-cli`: el comando `docker`. `containerd.io`: el motor que ejecuta contenedores.
- `docker-compose-plugin`: da el subcomando `docker compose`, que usaremos para levantar toda la pila de Greenbone.

Prueba de funcionalidad:

```sh
sudo systemctl status docker --no-pager
sudo docker run --rm hello-world
```

- El primer comando debe mostrar `active (running)`.
- `docker run --rm hello-world` descarga una imagen mínima y la ejecuta; `--rm` borra el contenedor al terminar. Si imprime «Hello from Docker!», el motor funciona.

```sh
juanka@JuankaPortatil:/mnt/midisco/greenbone/compose$ sudo systemctl status docker --no-pager
sudo docker run --rm hello-world
[sudo] contraseña para juanka: 
● docker.service - Docker Application Container Engine
     Loaded: loaded (/usr/lib/systemd/system/docker.service; enabled; preset: enabled)
     Active: active (running) since Sun 2026-10-18 13:36:55 CEST; 39min ago
 Invocation: 57e45316c5a94705b6c9646af36396f7
TriggeredBy: ● docker.socket
       Docs: https://docs.docker.com
   Main PID: 1355 (dockerd)
      Tasks: 32
     Memory: 282.8M (peak: 438.4M, swap: 5.3M, swap peak: 5.3M, zswap: 1.9M)
        CPU: 1min 26.356s
     CGroup: /system.slice/docker.service
             ├─ 1355 /usr/bin/dockerd -H fd:// --containerd=/run/containerd/containerd.sock
             ├─10428 /usr/bin/docker-proxy -proto tcp -host-ip 127.0.0.1 -host-port 443 -container-ip 172.18.0.17 -container-port 443 -use-listen-fd
             └─10443 /usr/bin/docker-proxy -proto tcp -host-ip 127.0.0.1 -host-port 9392 -container-ip 172.18.0.17 -container-port 9392 -use-listen-fd

oct 18 14:05:00 JuankaPortatil dockerd[1355]: time="2026-10-18T14:05:00.861091706+02:00" level=info msg="sbJoin: gwep4 ''->'c46918d658da', …d9d1d4e666
oct 18 14:05:26 JuankaPortatil dockerd[1355]: time="2026-10-18T14:05:26.840837841+02:00" level=info msg="sbJoin: gwep4 ''->'df27f90ee1fd', …d9d1d4e666
oct 18 14:05:29 JuankaPortatil dockerd[1355]: time="2026-10-18T14:05:29.444875488+02:00" level=info msg="sbJoin: gwep4 ''->'fc439f215ae8', …d9d1d4e666
oct 18 14:05:30 JuankaPortatil dockerd[1355]: time="2026-10-18T14:05:30.268580991+02:00" level=info msg="received task-delete event from co…askDelete"
oct 18 14:05:31 JuankaPortatil dockerd[1355]: time="2026-10-18T14:05:31.724416097+02:00" level=info msg="sbJoin: gwep4 ''->'c486bf181602', …d9d1d4e666
oct 18 14:07:29 JuankaPortatil dockerd[1355]: time="2026-10-18T14:07:29.611075012+02:00" level=info msg="sbJoin: gwep4 ''->'f3b5f6001efc', …d9d1d4e666
oct 18 14:07:30 JuankaPortatil dockerd[1355]: time="2026-10-18T14:07:30.401455019+02:00" level=info msg="sbJoin: gwep4 ''->'0f77e0b29a4e', …d9d1d4e666
oct 18 14:07:31 JuankaPortatil dockerd[1355]: time="2026-10-18T14:07:31.023053671+02:00" level=info msg="sbJoin: gwep4 ''->'a726d33e6b80', …d9d1d4e666
oct 18 14:07:31 JuankaPortatil dockerd[1355]: time="2026-10-18T14:07:31.320668022+02:00" level=info msg="received task-delete event from co…askDelete"
oct 18 14:07:31 JuankaPortatil dockerd[1355]: time="2026-10-18T14:07:31.877408952+02:00" level=info msg="sbJoin: gwep4 ''->'2ea28728977d', …d9d1d4e666
Hint: Some lines were ellipsized, use -l to show in full.

Hello from Docker!
This message shows that your installation appears to be working correctly.

To generate this message, Docker took the following steps:
 1. The Docker client contacted the Docker daemon.
 2. The Docker daemon pulled the "hello-world" image from the Docker Hub.
    (amd64)
 3. The Docker daemon created a new container from that image which runs the
    executable that produces the output you are currently reading.
 4. The Docker daemon streamed that output to the Docker client, which sent it
    to your terminal.

To try something more ambitious, you can run an Ubuntu container with:
 $ docker run -it ubuntu bash

Share images, automate workflows, and more with a free Docker ID:
 https://hub.docker.com/

For more examples and ideas, visit:
 https://docs.docker.com/get-started/
```

Comprobamos también que tenemos el complemento Compose, que es el que levanta toda la pila de Greenbone:

```
sudo docker compose version
```

`docker compose version` confirma que el complemento Compose está disponible.

### 3.3 Guardar los datos de Docker en /mnt/midisco

Por defecto Docker guarda imágenes y volúmenes en `/var/lib/docker`, que está en el disco del sistema sin espacio. Cambiamos esa ubicación con la opción `data-root`:

```sh
sudo systemctl stop docker docker.socket
sudo mkdir -p /mnt/midisco/docker
echo '{ "data-root": "/mnt/midisco/docker" }' | sudo tee /etc/docker/daemon.json
sudo systemctl start docker
sudo docker info | grep "Docker Root Dir"
```

- Paramos el servicio y su socket (si no, el socket reactiva Docker automáticamente).
- `/etc/docker/daemon.json` es el fichero de configuración del demonio. `data-root` indica dónde guardar todo.
- La última línea debe devolver `Docker Root Dir: /mnt/midisco/docker`. Si no, la configuración no se ha aplicado.
- Si ya existían contenedores en `/var/lib/docker` que queremos conservar, antes de arrancar habría que copiarlos con `sudo rsync -aP /var/lib/docker/ /mnt/midisco/docker/`. En una instalación nueva no hace falta.

> **Importante para reproducir la instalación:** esta configuración se hace preferentemente antes de descargar las imágenes y crear los contenedores. Si ya hay una instalación con datos en `/var/lib/docker`, no cambiamos `data-root` sin planificar antes una migración y una copia de seguridad: Docker podría empezar a ver un directorio nuevo y parecer que los contenedores han desaparecido.

En la reinstalación con el script repetimos el cambio escribiendo los nombres completos de las unidades de systemd:

En una instalación inicial, configuramos Docker así:

```
sudo systemctl stop docker.service docker.socket
sudo mkdir -p /mnt/midisco/docker
echo '{ "data-root": "/mnt/midisco/docker" }' | sudo tee /etc/docker/daemon.json
sudo systemctl start docker.service
sudo docker info --format 'Docker Root Dir: {{.DockerRootDir}}'
```

- Paramos `docker.service` y `docker.socket` para evitar que el socket reactive el servicio mientras cambiamos la configuración.
- `mkdir -p` crea el directorio de almacenamiento.
- `tee` escribe la configuración JSON de Docker con `data-root` apuntando al disco grande.
- Arrancamos de nuevo Docker.
- El último comando verifica la ruta efectiva. En nuestro equipo esperamos `Docker Root Dir: /mnt/midisco/docker`.

Para comprobar la ruta sin buscar en toda la salida de `docker info`, podemos pedir solo ese dato:

```
sudo docker info --format 'Docker Root Dir: {{.DockerRootDir}}'
```

**En el equipo que documentamos, la ruta efectiva ya es `/mnt/midisco/docker` y `/mnt/midisco` está en el dispositivo `/dev/sda1`.** La comprobación dentro del contenedor PostgreSQL también mostró su almacenamiento en esa unidad. Por tanto, no repetimos ahora el cambio de `data-root` ni borramos los datos existentes.

#### 3.3.1 Asegurar que el disco se monte antes que Docker

Como `/mnt/midisco` es un disco montado aparte, evitamos que Docker arranque antes de que esté montado. Primero comprobamos que el disco se monta automáticamente durante el arranque, por ejemplo mediante una entrada correcta en `/etc/fstab`, y después añadimos una dependencia a systemd:

```
sudo mkdir -p /etc/systemd/system/docker.service.d
sudo tee /etc/systemd/system/docker.service.d/midisco.conf >/dev/null <<'EOF'
[Unit]
RequiresMountsFor=/mnt/midisco
EOF
sudo systemctl daemon-reload
```

- `mkdir -p` crea el directorio donde systemd admite configuraciones adicionales de servicios.
- El fichero `midisco.conf` incorpora `RequiresMountsFor=/mnt/midisco`. Esto hace que systemd ordene los montajes necesarios antes de arrancar Docker.
- `systemctl daemon-reload` hace que systemd vuelva a leer las unidades y sus configuraciones.

Este ajuste protege contra una situación especialmente peligrosa: que el disco esté desconectado o tarde en montarse y Docker comience a escribir en una carpeta vacía del disco raíz con la misma ruta.

### 3.4 Instalar Greenbone con el script oficial

La documentación oficial ofrece el script `setup-and-start-greenbone-community-edition.sh` como atajo para los pasos de descarga y arranque de la pila de contenedores. Primero descargamos el script desde la dirección oficial:

```
curl -f -O https://greenbone.github.io/docs/latest/_static/setup-and-start-greenbone-community-edition.sh
chmod u+x setup-and-start-greenbone-community-edition.sh
```

- `curl -f -O` descarga el script al directorio actual y conserva su nombre original. Con `-f`, la descarga falla si el servidor devuelve un error HTTP.
- `chmod u+x` añade permiso de ejecución al usuario propietario del fichero.

Antes de ejecutarlo podemos inspeccionar su contenido:

```
less setup-and-start-greenbone-community-edition.sh
```

`less` permite revisar el script página por página antes de ejecutar código descargado de Internet. Salimos pulsando `q`.

Ejecutamos el script desde el directorio donde lo hemos descargado:

```
./setup-and-start-greenbone-community-edition.sh
```

Si nuestra configuración de permisos requiere privilegios para comunicarse con Docker, usamos el usuario autorizado o `sudo` según la configuración del equipo. En nuestra máquina hemos ejecutado los comandos Docker con `sudo`.

**Qué hace el script por dentro, paso a paso.** Lo leímos con `less` antes de ejecutarlo. Una copia está en `/mnt/midisco/setup-and-start-greenbone-community-edition.sh`. Son siete pasos:

| Paso | Línea del script | Qué hace, en sencillo |
| --- | --- | --- |
| 1 | `installed curl` · `installed docker` · `installed docker compose` | Comprueba que están instalados **curl**, **Docker** y **Docker Compose**. Si falta alguno, se para y nos da la dirección de la guía de requisitos |
| 2 | `DOWNLOAD_DIR=$HOME/greenbone-community-container` y `mkdir -p` | Crea la carpeta de la instalación dentro de la carpeta personal. **Como lo ejecutamos con `sudo`, `$HOME` es `/root`**: por eso nuestro fichero está en `/root/greenbone-community-container` |
| 3 | `curl -f -O https://greenbone.github.io/docs/latest/_static/compose.yaml` | Descarga el **plano** de la instalación (`compose.yaml`): qué contenedores hay y cómo se conectan. El nombre del proyecto, `greenbone-community-edition`, viene dentro de este fichero, y de ahí salen los nombres de los contenedores |
| 4 | `docker compose … pull` | Descarga las **imágenes** de todos los contenedores (varios GB). Es lo que más tarda |
| 5 | `docker compose … up -d` | **Arranca** todos los contenedores en segundo plano (`-d`) |
| 6 | `read -r -s -p "Password for admin user: "` y `gvmd --user=admin --new-password=…` | Nos **pide la contraseña del usuario `admin`** sin mostrarla en pantalla (`-s`) y la guarda dentro del contenedor gvmd |
| 7 | `echo "The feed data will be loaded now…"` y `xdg-open "http://127.0.0.1:9392"` | Avisa de que ahora se carga el **feed** (de minutos a horas, y mientras tanto los escaneos salen incompletos) y abre el navegador en la web |

> La línea `set -e` del principio hace que el script **se pare en cuanto un paso falla**, para no seguir con una instalación a medias.

El script facilita el procedimiento oficial de Compose: descarga/usa el fichero `compose.yaml`, obtiene las imágenes necesarias y pone los servicios en marcha. El script no sustituye las configuraciones que hacemos por separado para `data-root`, el montaje de `/mnt/midisco` ni la persistencia de systemd. Tampoco significa que la carga inicial del feed haya terminado en cuanto vuelve el terminal.

#### 3.4.1 Ubicación y nombre del proyecto que usamos

Para evitar que los comandos creen una segunda instalación, usamos siempre el mismo fichero Compose y el mismo nombre de proyecto. En nuestro equipo, el fichero que usamos realmente es:

```
/root/greenbone-community-container/compose.yaml
```

Y fijamos el proyecto con `-p greenbone-community-edition`. Por ello, a partir de aquí mantenemos esta forma de escribir los comandos:

```
sudo docker compose \
  -f /root/greenbone-community-container/compose.yaml \
  -p greenbone-community-edition ps
```

- `-f` indica el fichero Compose exacto.
- `-p` fija el nombre del proyecto; esto mantiene estables los nombres de los contenedores y volúmenes.
- `ps` lista los contenedores del proyecto y su estado.

No alternamos entre ficheros `compose.yaml` distintos ni omitimos `-p`, porque Docker Compose podría interpretar que estamos iniciando otro proyecto y crear recursos separados.

Si queremos actualizar manualmente las imágenes de la pila, los comandos oficiales son:

```
sudo docker compose \
  -f /root/greenbone-community-container/compose.yaml \
  -p greenbone-community-edition pull

sudo docker compose \
  -f /root/greenbone-community-container/compose.yaml \
  -p greenbone-community-edition up -d
```

`pull` descarga las imágenes referenciadas en el fichero Compose. `up -d` crea o recrea los contenedores que lo necesiten y los deja ejecutándose en segundo plano. En una instalación inicial, la descarga de imágenes puede tardar varios minutos y ocupa varios gigabytes.

> **Sobre la variable `$DOWNLOAD_DIR`.** En nuestra primera prueba descargamos el fichero Compose a mano en `/mnt/midisco/greenbone/compose` (apartado 3.4.2), y muchos comandos de este documento usan la forma corta `-f $DOWNLOAD_DIR/compose.yaml`. Desde que usamos el script oficial, el fichero activo es el de `/root/greenbone-community-container`. Para que todos esos comandos apunten a la instalación que funciona, al abrir una terminal ejecutamos:
>
> ```
> export DOWNLOAD_DIR=/root/greenbone-community-container
> ```
>
> Así, `-f $DOWNLOAD_DIR/compose.yaml` y `-f /root/greenbone-community-container/compose.yaml` son exactamente lo mismo.

#### 3.4.2 Alternativa: descargar el fichero Compose a mano (nuestra primera prueba)

Antes de usar el script, hicimos el mismo proceso paso a paso. Lo dejamos documentado porque ayuda a entender qué hace el script por dentro.

```sh
export DOWNLOAD_DIR=/mnt/midisco/greenbone/compose
cd /mnt/midisco/greenbone/compose
curl -f -L https://greenbone.github.io/docs/latest/_static/compose.yaml -o compose.yaml
```

- `export` crea una variable de entorno que usaremos en los comandos siguientes. **Si cerramos la terminal, tenemos que volver a exportarla.**
- `curl -f -L ... -o compose.yaml` descarga el fichero oficial y lo guarda como `compose.yaml`.
- Si la URL diera error 404, es que Greenbone ha renombrado el fichero: copiamos el enlace desde la sección «Docker Compose File» de la guía oficial (*Greenbone Community Containers*, en greenbone.github.io/docs).
- Abrimos el fichero (`less compose.yaml`) para ver qué servicios define. Con `sudo docker compose -f compose.yaml config --services` listamos sus nombres.

```bash
sudo docker compose -f $DOWNLOAD_DIR/compose.yaml -p greenbone-community-edition pull
sudo docker compose -f $DOWNLOAD_DIR/compose.yaml -p greenbone-community-edition up -d
```

- `docker compose -f <fichero>` le indica qué fichero Compose usar.
- `-p greenbone-community-edition` fija el **nombre del proyecto**, que se usa como prefijo en volúmenes y redes. Usar siempre el mismo evita crear duplicados.
- `pull` descarga las imágenes (varios GB: puede tardar bastante).
- `up -d` crea y arranca los contenedores; `-d` los deja en segundo plano (*detached*).

### 3.5 Comprobar el estado de los contenedores

Una vez arrancada la pila, revisamos el estado:

```
sudo docker compose \
  -f /root/greenbone-community-container/compose.yaml \
  -p greenbone-community-edition ps
```

Los servicios principales deberían aparecer como `Up`, `running` o `healthy`. Algunos contenedores auxiliares copian los datos del feed, terminan y aparecen como `Exited`; puede ser normal si acabaron sin error. En nuestro fichero algunos contenedores de datos permanecen activos para mantener su estado de salud.

Deben aparecer los servicios en estado `running` o `healthy`; los de datos del feed pueden aparecer como `exited (0)`, y es normal porque ya han copiado sus datos.

Con la variable `$DOWNLOAD_DIR` (sección 3.4.1) el mismo comando es:

```sh
sudo docker compose -f $DOWNLOAD_DIR/compose.yaml -p greenbone-community-edition ps
```

Salida que obtuvimos en nuestro equipo tras el primer arranque:

```sh
juanka@JuankaPortatil:/mnt/midisco/greenbone/compose$ sudo docker compose -f $DOWNLOAD_DIR/compose.yaml -p greenbone-community-edition ps
NAME                                                IMAGE                                                               COMMAND                  SERVICE               CREATED         STATUS                    PORTS
greenbone-community-edition-cert-bund-data-1        registry.community.greenbone.net/community/cert-bund-data           "/bin/init.sh"           cert-bund-data        2 minutes ago   Up 2 minutes (healthy)    
greenbone-community-edition-data-objects-1          registry.community.greenbone.net/community/data-objects             "/bin/init.sh"           data-objects          2 minutes ago   Up 2 minutes (healthy)    
greenbone-community-edition-dfn-cert-data-1         registry.community.greenbone.net/community/dfn-cert-data            "/bin/init.sh"           dfn-cert-data         2 minutes ago   Up 2 minutes (healthy)    
greenbone-community-edition-gsa-1                   registry.community.greenbone.net/community/gsa:stable-slim          "/usr/local/bin/entr…"   gsa                   2 minutes ago   Up 2 minutes (healthy)    
greenbone-community-edition-gsad-1                  registry.community.greenbone.net/community/gsad:stable              "/usr/local/bin/entr…"   gsad                  2 minutes ago   Up 13 seconds             
greenbone-community-edition-gvmd-1                  registry.community.greenbone.net/community/gvmd:stable              "/usr/local/bin/entr…"   gvmd                  2 minutes ago   Up 14 seconds (healthy)   
greenbone-community-edition-nginx-1                 registry.community.greenbone.net/community/nginx:latest             "/docker-entrypoint.…"   nginx                 2 minutes ago   Up 12 seconds             127.0.0.1:443->443/tcp, 80/tcp, 127.0.0.1:9392->9392/tcp
greenbone-community-edition-notus-data-1            registry.community.greenbone.net/community/notus-data               "/bin/init.sh"           notus-data            2 minutes ago   Up 2 minutes (healthy)    
greenbone-community-edition-openvas-1               registry.community.greenbone.net/community/openvas-scanner:stable   "/bin/sh -c 'cat /et…"   openvas               2 minutes ago   Up 2 minutes              
greenbone-community-edition-openvasd-1              registry.community.greenbone.net/community/openvas-scanner:stable   "/usr/local/bin/open…"   openvasd              2 minutes ago   Up 2 minutes              
greenbone-community-edition-ospd-openvas-1          registry.community.greenbone.net/community/ospd-openvas:stable      "/usr/bin/tini -- /u…"   ospd-openvas          2 minutes ago   Up 2 minutes              
greenbone-community-edition-pg-gvm-1                registry.community.greenbone.net/community/pg-gvm:stable            "/usr/local/bin/entr…"   pg-gvm                2 minutes ago   Up 2 minutes (healthy)    
greenbone-community-edition-redis-server-1          registry.community.greenbone.net/community/redis-server             "docker-entrypoint.s…"   redis-server          2 minutes ago   Up 2 minutes              6379/tcp
greenbone-community-edition-report-formats-1        registry.community.greenbone.net/community/report-formats           "/bin/init.sh"           report-formats        2 minutes ago   Up 2 minutes (healthy)    
greenbone-community-edition-scap-data-1             registry.community.greenbone.net/community/scap-data                "/bin/init.sh"           scap-data             2 minutes ago   Up 2 minutes (healthy)    
greenbone-community-edition-vulnerability-tests-1   registry.community.greenbone.net/community/vulnerability-tests      "/bin/init.sh"           vulnerability-tests   2 minutes ago   Up 2 minutes (healthy)    
```

Para ver los registros de los servicios de escaneo y del gestor:

```
sudo docker compose \
  -f /root/greenbone-community-container/compose.yaml \
  -p greenbone-community-edition logs -f ospd-openvas gvmd
```

`logs` muestra los registros de los contenedores indicados y `-f` sigue las nuevas líneas en tiempo real. Para dejar de seguir los registros pulsamos `Ctrl+C`; eso no detiene los contenedores.

### 3.6 Esperar a que se cargue el feed (paso crítico)

Aunque los contenedores estén arrancados, **el escáner todavía no sirve**: tiene que cargar el feed en memoria y en la base de datos y la primera vez tarda desde varios minutos hasta horas. Si lanzamos un escaneo antes de que termine, los resultados saldrán incompletos o vacíos sin ningún error visible.

El feed de Greenbone no se considera listo solamente porque los contenedores se hayan iniciado. La sincronización tiene dos fases:

1. **Descarga y copia:** las imágenes de datos contienen los archivos de VT/NVT, Notus, SCAP, CERT, listas de puertos, configuraciones y formatos de informe. Al arrancar, los contenedores de datos copian su contenido a volúmenes persistentes.
2. **Importación:** `ospd-openvas` carga las pruebas de vulnerabilidad en memoria y `gvmd` importa la información de seguridad a PostgreSQL. Esta primera importación puede tardar desde varios minutos hasta horas.

Seguimos los registros:

```
sudo docker compose \
  -f /root/greenbone-community-container/compose.yaml \
  -p greenbone-community-edition logs -f ospd-openvas gvmd
```

Mensajes que buscamos, en este orden:

1. En `ospd-openvas`: `Finished loading VTs. The VT cache has been updated from version X to Y.` → el escáner ya conoce las pruebas.
2. En `gvmd`: `Updating VTs in database ... done (X VTs).` → gvmd ha cargado las pruebas.
3. En `gvmd`: `update_scap_end: Updating SCAP info succeeded` → datos CVE/CPE cargados.
4. En `gvmd`: `sync_cert: Updating CERT info succeeded.` → datos CERT cargados.
5. En `gvmd`: líneas `Scan config Full and fast (...) has been created by admin` → ya existen las configuraciones de escaneo.

Para medir el progreso sin leer logs, en la web: *Administration → Feed Status* muestra si cada tipo de dato está actualizado.

Forma corta del mismo comando, con la variable `$DOWNLOAD_DIR`:

```sh
sudo docker compose -f $DOWNLOAD_DIR/compose.yaml -p greenbone-community-edition logs -f ospd-openvas gvmd
```

- `logs -f` muestra los registros y se queda esperando nuevas líneas (`-f` = *follow*). Salimos con `Ctrl+C`.

También comprobamos **Administration → Feed Status** en la interfaz web. Las filas NVT, SCAP, CERT y GVMD_DATA deberían terminar en `Current`. En **Configuration → Scan Configs** verificamos que exista `Full and fast`.

**No lanzamos escaneos completos durante una importación inicial que siga en curso**, porque el resultado podría ser incompleto. No ejecutamos el `greenbone-feed-sync` de la instalación compilada contra los volúmenes del método Docker: el flujo oficial de contenedores utiliza sus imágenes de datos y los demonios cargan automáticamente el contenido copiado.

**Estado comprobado en nuestro equipo (1 de noviembre de 2026):** el registro de `ospd-openvas` muestra `Finished loading VTs. The VT cache has been updated from version 0 to 202610241320`, y desde la línea de comandos (sección 7) el feed aparece completo:

| Feed | Versión | Estado |
| --- | --- | --- |
| NVT | 202610241320 | Al día |
| SCAP | 202610241203 | Al día |
| CERT | 202610230425 | Al día |
| GVMD_DATA | 202610230512 | Al día |

#### 3.6.1 Comprobación adicional de la importación SCAP en PostgreSQL

Si SCAP sigue mostrando `Update in progress...`, podemos comprobar si PostgreSQL está procesando una importación `COPY`:

```
sudo docker compose \
  -f /root/greenbone-community-container/compose.yaml \
  -p greenbone-community-edition \
  exec pg-gvm psql -U postgres -d gvmd -c "
SELECT pid, command, type, bytes_processed, bytes_total, tuples_processed
FROM pg_stat_progress_copy;

SELECT pid, state, wait_event_type, wait_event,
       now() - query_start AS duracion,
       left(query, 160) AS consulta
FROM pg_stat_activity
WHERE datname = 'gvmd'
  AND pid <> pg_backend_pid()
  AND state <> 'idle'
ORDER BY query_start;
"
```

- `exec pg-gvm` ejecuta `psql` dentro del contenedor PostgreSQL.
- `pg_stat_progress_copy` muestra las operaciones `COPY` activas. En una importación a través de una tubería, `bytes_total` puede ser `0`, ya que el tamaño total no se conoce por anticipado.
- `pg_stat_activity` permite ver las consultas activas, su duración y los eventos de espera.
- `DataFileRead` suele indicar espera de lectura de archivos; por sí solo no demuestra que PostgreSQL esté bloqueado.

Podemos repetir la consulta pasados unos minutos y comparar los contadores, pero no interpretamos los contadores de una única operación como el porcentaje total del feed. Si `gvmd` no registra errores y la interfaz indica `Update in progress...`, esperamos antes de reiniciar o modificar volúmenes.

### 3.7 Configurar la contraseña del administrador

La guía oficial advierte de que no debemos mantener la contraseña de ejemplo si el usuario administrador se ha creado con credenciales predeterminadas. Para establecer nuestra contraseña ejecutamos:

```
sudo docker compose \
  -f /root/greenbone-community-container/compose.yaml \
  -p greenbone-community-edition \
  exec -u gvmd gvmd gvmd --user=admin --new-password='SUSTITUIR_POR_UNA_CLAVE_LARGA'
```

- `exec` ejecuta un comando dentro del contenedor `gvmd`.
- `-u gvmd` ejecuta el comando con el usuario interno `gvmd`.
- `gvmd --user=admin --new-password=...` cambia la contraseña del usuario `admin`.
- Sustituimos el texto de ejemplo por una contraseña larga y única. Las comillas simples impiden que caracteres especiales como `$` sean interpretados por la shell. No guardamos una contraseña real en esta práctica ni en el repositorio del grupo.

Con la variable `$DOWNLOAD_DIR` de la sección 3.4.1, el mismo comando queda más corto:

```sh
sudo docker compose -f $DOWNLOAD_DIR/compose.yaml -p greenbone-community-edition \
    exec -u gvmd gvmd gvmd --user=admin --new-password='<CONTRASEÑA>'
```

- Elegimos una contraseña larga y la guardamos en un gestor de contraseñas. **No** la ponemos en el repositorio del blog.

### 3.8 Acceder a la interfaz web

La configuración Compose que estamos utilizando publica la interfaz únicamente en la dirección local del equipo, no en todas las interfaces de red. Abrimos:

```
https://127.0.0.1
```

El navegador puede advertir que el certificado TLS es autofirmado. En un entorno de laboratorio local es esperable; comprobamos que la dirección sea `127.0.0.1` antes de continuar. También comprobamos los puertos si no carga la página:

```
sudo ss -ltnp | grep -E ':(9392|443)\b'
```

`ss -ltnp` lista los sockets TCP en escucha, sin resolver nombres, e intenta mostrar el proceso que los utiliza. En nuestro caso, Nginx publica `127.0.0.1:443` y `127.0.0.1:9392`. No exponemos la interfaz a la red local salvo que cambiemos conscientemente la configuración y adoptemos las medidas de seguridad necesarias.

La interfaz también responde en el puerto 9392 del propio equipo:

```
http://127.0.0.1:9392
```

![[Pasted image 20261018142315.png]]

### 3.9 Persistencia de los datos y de los contenedores

Hay dos conceptos distintos:

- **Persistencia del feed y la base de datos:** Docker guarda los datos relevantes en volúmenes con nombres como `greenbone-community-edition_vt_data_vol`, `greenbone-community-edition_scap_data_vol`, `greenbone-community-edition_gvmd_data_vol` y `greenbone-community-edition_psql_data_vol`. Como el `Docker Root Dir` está en `/mnt/midisco/docker`, los volúmenes se guardan bajo esa ubicación. Por ello, los datos no se vuelven a descargar desde cero al reiniciar el ordenador, siempre que el disco esté montado, se conserve `data-root` y no se borren los volúmenes.
- **Arranque automático:** para que todos los contenedores se vuelvan a levantar al iniciar Debian, además de activar Docker creamos un servicio systemd que ejecuta `docker compose up -d` con el mismo fichero y proyecto.

Comprobamos la ruta efectiva de Docker y los volúmenes:

```
sudo docker info --format 'Docker Root Dir: {{.DockerRootDir}}'
sudo docker volume ls | grep greenbone-community-edition
```

El primer comando debería mostrar `/mnt/midisco/docker`. El segundo lista los volúmenes de Greenbone que conservan los datos. Podemos inspeccionar un volumen concreto sin modificarlo:

```
sudo docker volume inspect greenbone-community-edition_psql_data_vol
```

No usamos `docker compose down -v` para detener o reiniciar Greenbone. La opción `-v` elimina también los volúmenes definidos por Compose y puede borrar la base de datos, informes y datos del feed. Tampoco ejecutamos una limpieza global de volúmenes sin saber qué contienen.

#### 3.9.1 Habilitar Docker en el arranque

Nos aseguramos de que Docker y `containerd` estén habilitados y arrancados:

```
sudo systemctl enable --now docker.service containerd.service
systemctl is-enabled docker.service
```

- `enable` configura el servicio para que arranque con Debian.
- `--now` lo inicia inmediatamente, sin esperar al siguiente reinicio.
- `is-enabled` confirma que el servicio está habilitado; el resultado esperado es `enabled`.

#### 3.9.2 Evitar conflictos con la instalación compilada manualmente

En este mismo equipo también habíamos creado servicios systemd para la instalación compilada en `/usr/local`. Ambos métodos intentaban utilizar el puerto `9392`; la instalación manual ejecutaba `gsad` en `127.0.0.1:9392` y por eso impedía que Nginx de Docker publicase el puerto.

Como decidimos usar el método Docker, detenemos y deshabilitamos el arranque automático de los servicios compilados:

```
sudo systemctl disable --now \
  gsad.service gvmd.service ospd-openvas.service openvasd.service redis-server@openvas.service
```

- `--now` detiene esos servicios si están activos.
- `disable` elimina sus enlaces de arranque automático; no desinstala los programas ni borra sus datos.

Comprobamos que los puertos estén libres antes de arrancar Nginx y que sea el contenedor el que los publica:

```
sudo ss -ltnp | grep -E ':(9392|443)\b'
sudo docker compose \
  -f /root/greenbone-community-container/compose.yaml \
  -p greenbone-community-edition ps
```

No desinstalamos la instalación compilada en este paso; solo impedimos que arranque en paralelo. Así evitamos mezclar dos instalaciones que tienen sus propios gestores, bases de datos, feeds y servicios.

#### 3.9.3 Crear el servicio systemd para Greenbone Compose

Para que systemd levante el proyecto Compose tras cada arranque, creamos `/etc/systemd/system/greenbone-compose.service`:

```
sudo tee /etc/systemd/system/greenbone-compose.service >/dev/null <<'EOF'
[Unit]
Description=Greenbone Community Edition Docker Compose
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/root/greenbone-community-container
ExecStart=/usr/bin/docker compose -f /root/greenbone-community-container/compose.yaml -p greenbone-community-edition up -d
ExecStop=/usr/bin/docker compose -f /root/greenbone-community-container/compose.yaml -p greenbone-community-edition stop
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF
```

Explicamos sus bloques:

- `[Unit]` describe el servicio e indica que depende de Docker y debe ejecutarse después de él.
- `[Service]` define las acciones. `Type=oneshot` indica que systemd ejecuta una orden y espera a que termine; `RemainAfterExit=yes` mantiene el servicio como activo aunque la orden `up -d` ya haya terminado. Por eso el estado `Active: active (exited)` es normal para esta unidad.
- `WorkingDirectory` documenta el directorio de trabajo utilizado.
- `ExecStart` levanta el proyecto en segundo plano con el fichero y el nombre de proyecto correctos.
- `ExecStop` detiene los contenedores conservando los volúmenes; no ejecuta `down -v`.
- `TimeoutStartSec=0` evita que systemd aplique un límite de tiempo de inicio a esa orden.
- `[Install]` con `WantedBy=multi-user.target` permite habilitar el servicio para el arranque normal del sistema.

Recargamos systemd y activamos el servicio:

```
sudo systemctl daemon-reload
sudo systemctl enable --now greenbone-compose.service
```

- `daemon-reload` hace que systemd lea la nueva unidad.
- `enable --now` la habilita para futuros arranques y la ejecuta inmediatamente.

Verificamos la configuración y el estado:

```
systemctl is-enabled docker.service
systemctl is-enabled greenbone-compose.service
sudo systemctl status greenbone-compose.service --no-pager
sudo docker compose \
  -f /root/greenbone-community-container/compose.yaml \
  -p greenbone-community-edition ps
```

En nuestra instalación los dos servicios responden `enabled`, la unidad `greenbone-compose.service` termina con `status=0/SUCCESS` y los contenedores principales aparecen `Up` o `healthy`. El estado `active (exited)` de la unidad propia es esperado por su tipo `oneshot`; no significa que Greenbone se haya apagado.

La persistencia depende también de que `/mnt/midisco` se monte antes de arrancar Docker. Por eso mantenemos el ajuste `RequiresMountsFor=/mnt/midisco` descrito en el apartado 3.4.1.

> **Cambio posterior:** cuando configuramos el correo (sección 6.6.4) añadimos a las líneas `ExecStart` y `ExecStop` de esta unidad un segundo fichero, `-f /mnt/midisco/greenbone/compose/correo.override.yaml`, para que la configuración del correo también se cargue al arrancar el equipo.

### 3.10 Cómo arrancar, detener, revisar y actualizar Greenbone

#### Consultar el estado

```
sudo systemctl status docker.service --no-pager
sudo systemctl status greenbone-compose.service --no-pager
sudo docker compose \
  -f /root/greenbone-community-container/compose.yaml \
  -p greenbone-community-edition ps
```

Con estos comandos comprobamos Docker, el servicio de arranque de Greenbone y cada contenedor.

#### Arrancar o detener la pila

```
sudo systemctl start greenbone-compose.service
sudo systemctl stop greenbone-compose.service
```

`start` ejecuta `docker compose up -d`. `stop` ejecuta la orden `docker compose stop` de la unidad: detiene los contenedores, pero conserva los contenedores, las imágenes y los volúmenes de datos.

#### Reiniciar la pila

```
sudo systemctl restart greenbone-compose.service
```

La unidad ejecuta `ExecStop` y después `ExecStart`. Tras el reinicio, `ospd-openvas` puede tardar varios minutos en volver a cargar las pruebas en memoria. La persistencia de los volúmenes evita comenzar de cero, aunque el servicio debe volver a procesar en memoria los datos al arrancar.

#### Actualizar las imágenes y el feed

Actualizamos el feed cuando la instalación inicial ya haya terminado y tengamos comprobado que el estado actual del feed es correcto. Greenbone documenta el flujo en dos partes: descargar nuevas imágenes de datos y arrancar los contenedores de datos para copiar su contenido a los volúmenes; después, los demonios cargan esos datos automáticamente.

Para una actualización de las imágenes de toda la pila:

```
sudo docker compose \
  -f /root/greenbone-community-container/compose.yaml \
  -p greenbone-community-edition pull

sudo docker compose \
  -f /root/greenbone-community-container/compose.yaml \
  -p greenbone-community-edition up -d
```

Para actualizar concretamente los contenedores de datos del feed según la guía de Greenbone:

```
sudo docker compose \
  -f /root/greenbone-community-container/compose.yaml \
  -p greenbone-community-edition pull \
  notus-data vulnerability-tests scap-data dfn-cert-data cert-bund-data report-formats data-objects

sudo docker compose \
  -f /root/greenbone-community-container/compose.yaml \
  -p greenbone-community-edition up -d \
  notus-data vulnerability-tests scap-data dfn-cert-data cert-bund-data report-formats data-objects

sudo docker compose \
  -f /root/greenbone-community-container/compose.yaml \
  -p greenbone-community-edition up -d
```

El primer `pull` descarga las imágenes de datos. El segundo `up -d` arranca o recrea esos servicios para que copien los datos actualizados a los volúmenes. El último `up -d` confirma que el resto de la pila está levantada para que `ospd-openvas` y `gvmd` procesen la actualización.

Una sincronización del feed **no es lo mismo que el arranque automático**: tener Docker habilitado no implica descargar una nueva versión de las pruebas cada día. La actualización periódica debe planificarse por separado. No ejecutamos estas órdenes durante la primera importación si SCAP, CERT o GVMD_DATA siguen mostrando `Update in progress...`.

### 3.11 Incidencias que hemos encontrado

#### Conflicto entre `gsad` manual y Nginx de Docker

El proceso compilado `/usr/local/sbin/gsad` estaba escuchando en `127.0.0.1:9392`, el mismo puerto que Nginx de Docker necesita publicar. El error de Docker era `bind: address already in use`. Lo resolvimos deteniendo los servicios manuales y dejando Docker como método activo. La lección es no arrancar a la vez ambos métodos en los mismos puertos.

#### Advertencias de volúmenes existentes

Al ejecutar Compose aparecieron advertencias similares a `volume ... already exists but was not created by Docker Compose`. Como ya existían volúmenes de Greenbone y los contenedores pudieron arrancar, mantuvimos la ubicación y el nombre de proyecto existentes. No borramos los volúmenes ni usamos `down -v`. Antes de cambiar el fichero Compose o el nombre del proyecto, inspeccionamos los volúmenes y preparamos una copia de seguridad.

#### Primera carga del feed pendiente

En nuestro equipo, el 25 de octubre de 2026, la interfaz mostraba NVT como `Current` en la versión `20261024T1320`, mientras SCAP, CERT y GVMD_DATA aparecían como `Update in progress...`. PostgreSQL mostraba una consulta activa `COPY scap2.cpe_matches ... FROM STDIN`, señal de que estaba procesando correspondencias CPE. El espacio de almacenamiento no parecía el problema: había aproximadamente 18 GB libres en `/` y 4,2 TB en `/mnt/midisco`.

La cantidad de archivos NASL comprobada en el volumen era de 95.105 y existía `/var/lib/openvas/plugins/plugin_feed_info.inc`. El registro del motor contenía errores de intentos antiguos en los que faltaban directorios NASL y ese archivo de metadatos, pero también mostraba una carga posterior completada y la versión de caché `202610241320`. Por ello no borramos datos ni interpretamos automáticamente los registros antiguos como un fallo actual.

Mientras el feed está importándose, revisamos periódicamente **Administration → Feed Status**, los registros de `ospd-openvas` y `gvmd`, y las operaciones activas de PostgreSQL. Solo consideramos terminada la sincronización cuando los estados del feed estén actualizados y el gestor haya completado las importaciones.

#### Aviso de Redis sobre `vm.overcommit_memory`

Redis mostró la recomendación de habilitar `vm.overcommit_memory = 1`. Lo configuramos de forma persistente:

```
echo 'vm.overcommit_memory = 1' | sudo tee /etc/sysctl.d/99-greenbone.conf
sudo sysctl --system
sudo sysctl vm.overcommit_memory
```

- `tee` guarda el ajuste en `/etc/sysctl.d/99-greenbone.conf`.
- `sysctl --system` aplica los ficheros de configuración sysctl.
- La comprobación final debe mostrar `vm.overcommit_memory = 1`. Si ejecutamos `sysctl` sin `sudo` y el usuario no tiene ese comando en su `PATH`, puede aparecer `sysctl: orden no encontrada`; usamos `sudo sysctl vm.overcommit_memory` para comprobarlo con privilegios.

#### Comandos que evitamos

No ejecutamos los siguientes comandos como método de reparación rutinario:

```
sudo docker compose -f /root/greenbone-community-container/compose.yaml -p greenbone-community-edition down -v
sudo docker system prune --volumes
```

El primero elimina los volúmenes del proyecto; el segundo puede eliminar volúmenes no usados por contenedores. Ambos podrían borrar la base de datos, el feed u otros datos que queramos conservar.

#### Al escribir `127.0.0.1` en el navegador salía otra aplicación web

En nuestro portátil tenemos otra aplicación web (una herramienta para administrar PostgreSQL) servida por el nginx del propio sistema en el **puerto 80**. Si escribimos solo `127.0.0.1` o `localhost`, el navegador añade `http://` por su cuenta y va al puerto 80, así que abre esa aplicación y no Greenbone. **Greenbone no estaba caído:** el registro de su nginx (`docker logs greenbone-community-edition-nginx-1`) demostraba que nuestro navegador ni siquiera le llegaba.

Lo solucionamos escribiendo siempre la dirección completa y guardándola en marcadores:

- `https://127.0.0.1` → Greenbone (puerto 443, con `https://` delante).
- `http://127.0.0.1:9392` → también Greenbone: nos redirige solo a la dirección anterior.
- `http://127.0.0.1` o `localhost` sin nada más → la otra aplicación, **no** Greenbone.

Para saber qué programa usa cada puerto: `sudo ss -tlpn | grep -E ':(80|443|9392) '`.

#### El programa `gvm-cli` del contenedor no podía leer nuestras credenciales

Al usar el contenedor `gvm-tools` con nuestro fichero `~/.config/gvm-tools.conf` (permisos `600`), obtuvimos `Permission denied`: dentro del contenedor el programa se ejecuta con otro usuario, que no puede leer un fichero que solo es nuestro. Lo solucionamos ejecutando el contenedor con nuestro propio usuario (`--user "$(id -u):$(id -g)"`), como explicamos en la sección 7.1. **No** abrimos los permisos del fichero, porque contiene una contraseña.

#### Al recrear `gvmd` se interrumpieron los escaneos en curso

Aplicamos el correo (sección 6.6.4) mientras había dos escaneos en marcha, pensando que no les afectaría porque el que escanea es `ospd-openvas`. No fue así: `gvmd` es quien coordina las tareas y, al reiniciarse, las dos pasaron a estado *Interrupted* (al 18 % y al 31 %). Primero intentamos reanudarlas desde donde se quedaron (en la web, el botón *Resume*):

```
/mnt/midisco/greenbone/scripts/gmp.sh '<resume_task task_id="<ID_TAREA>"/>'
```

No funcionó: `ospd-openvas` todavía tenía registrados los escaneos antiguos y, al reanudar, `gvmd` los detuvo (`Scan stopped` en el registro de `ospd-openvas`) y las tareas volvieron a *Interrupted*. Como efecto secundario se dispararon las alertas con los informes parciales y nos llegaron varios correos. Lo resolvimos lanzando las tareas de nuevo desde el principio:

```
/mnt/midisco/greenbone/scripts/gmp.sh '<start_task task_id="<ID_TAREA>"/>'
```

Los informes parciales quedan guardados en la tarea como evidencia. **Lección:** los cambios que reinician `gvmd` se hacen con el escáner parado.

#### El registro de msmtp quedó con el propietario equivocado

Nuestro primer correo de prueba lo enviamos con `docker exec` sin indicar usuario, es decir, como `root`. Eso creó el registro `/var/log/gvm/msmtp.log` con propietario `root`. Después, cuando `gvmd` enviaba las alertas con su propio usuario, el correo salía, pero **no quedaba apuntado** en el registro y parecía que no se había enviado. Lo arreglamos así:

```
docker exec greenbone-community-edition-gvmd-1 chown gvmd:gvmd /var/log/gvm/msmtp.log
```

**Lección:** las pruebas de correo se hacen con el mismo usuario que enviará de verdad (`docker exec -u gvmd ...`), igual que en el método B usamos `sudo -u gvm`.

#### La contraseña de aplicación de Google se copió con espacios

Google muestra la contraseña de aplicación en cuatro grupos (`abcd efgh ijkl mnop`). Si se copia así, ocupa 19 caracteres y el servidor la rechaza con el error 535. Comprobamos la longitud sin mostrar la contraseña y quitamos los espacios:

```
awk -F= '/^MTA_PASSWORD=/{print length($2)}' /mnt/midisco/greenbone/compose/correo.env
sed -i '/^MTA_PASSWORD=/s/ //g' /mnt/midisco/greenbone/compose/correo.env
```

- `awk` cuenta los caracteres de la línea `MTA_PASSWORD` sin imprimirla; debe dar 16.
- `sed -i` borra los espacios solo de esa línea.



## 4. Método B: compilación a mano desde el código fuente

> **Estado en nuestro equipo.** Este método lo completamos en el propio portátil y comprobamos que funcionaba: los programas están en `/usr/local` y los datos en `/mnt/midisco/greenbone` (carpetas `fuentes`, `build`, `instalacion` y `datos`). Cuando decidimos quedarnos con Docker, **detuvimos y deshabilitamos** sus servicios (sección 3.9.2) para que no ocupen los mismos puertos. No los desinstalamos: si se necesitan, basta con parar el método A y volver a habilitarlos.

### 4.1 Qué vamos a hacer y qué aviso tenemos que tener en cuenta

En este método instalamos cada pieza de la tabla de la sección 1.2 por separado: descargamos el código, **verificamos su firma**, compilamos, instalamos y configuramos los servicios con `systemd`. Es el camino que sigue la guía oficial de Greenbone (*Building from Source*) y es la mejor forma de entender cómo encajan los componentes.

> **Aviso honesto sobre Debian 13.** La guía oficial de Greenbone documenta oficialmente Debian 12 (bookworm), Ubuntu 24.04, Fedora y CentOS; Debian 13 (trixie) no aparece como distribución soportada. Los comandos de esta sección son los oficiales con las adaptaciones que esperamos necesitar en trixie (PostgreSQL 17 en lugar de 15, bloqueo de `pip` por PEP 668 y Rust por `rustup`). **Hay que probarlos en nuestra máquina**: si algún paquete cambia de nombre se resuelve con `apt search <nombre>`. Greenbone indica además que esta vía es para desarrolladores y pruebas, no para producción.

> **Recomendación:** hacer este método en una **máquina virtual Debian 13 limpia** (4 núcleos, 8 GB de RAM, 60 GB de disco), no en el equipo físico. Así no se mezcla con el método A y, si algo sale mal, se borra la VM. Si se hace en el equipo físico, el método A debe estar parado.

### 4.2 Crear el usuario y el grupo del servicio

```bash
sudo useradd -r -M -U -G sudo -s /usr/sbin/nologin gvm
sudo usermod -aG gvm $USER
su $USER
```

- `useradd -r` crea un usuario de **sistema**; `-M` no crea carpeta personal; `-U` crea un grupo con el mismo nombre; `-G sudo` lo añade al grupo sudo; `-s /usr/sbin/nologin` impide que alguien inicie sesión como `gvm`.
- Todos los servicios de Greenbone correrán como `gvm`, no como root: es el principio de **mínimo privilegio**.
- `usermod -aG gvm $USER` añade nuestro usuario al grupo `gvm` (`-a` añade sin quitar otros grupos) para poder ejecutar `gvmd` desde nuestra sesión.
- `su $USER` refresca los grupos en la terminal actual (o cerramos sesión y volvemos a entrar).

### 4.3 Variables de entorno y directorios en /mnt/midisco

```bash
export INSTALL_PREFIX=/usr/local
export PATH=$PATH:$INSTALL_PREFIX/sbin
export SOURCE_DIR=/mnt/midisco/greenbone/fuentes
export BUILD_DIR=/mnt/midisco/greenbone/build
export INSTALL_DIR=/mnt/midisco/greenbone/instalacion
mkdir -p $SOURCE_DIR $BUILD_DIR $INSTALL_DIR
```

- `INSTALL_PREFIX`: dónde se instalará el software ya compilado. `/usr/local` es el sitio estándar para programas instalados a mano; los binarios ocupan poco, así que no hace falta moverlos de disco.
- `PATH`: en Debian `/usr/local/sbin` no está en el PATH de los usuarios normales, y ahí se instala `gvmd`.
- `SOURCE_DIR` (código descargado), `BUILD_DIR` (ficheros intermedios de compilación) e `INSTALL_DIR` (carpeta temporal donde se instala antes de copiar al sistema) **van en `/mnt/midisco`**, porque compilar genera varios GB.
- **Si cerramos la terminal, tenemos que repetir estos `export`.** Por eso los guardamos en un fichero `variables.sh` y cargarlo con `source variables.sh`.

### 4.4 Mover los datos pesados a /mnt/midisco (montajes *bind*)

El feed y los datos del escáner se guardan en `/var/lib/gvm` y `/var/lib/openvas` (varios GB). Para que ocupen espacio en `/mnt/midisco` sin cambiar ninguna ruta de los programas usamos un **montaje *bind***: un directorio de un disco que aparece también en otra ruta.

```bash
sudo mkdir -p /mnt/midisco/greenbone/datos/{gvm,openvas,notus}
sudo mkdir -p /var/lib/gvm /var/lib/openvas /var/lib/notus
sudo tee -a /etc/fstab <<'EOF'
/mnt/midisco/greenbone/datos/gvm     /var/lib/gvm     none bind,x-systemd.requires-mounts-for=/mnt/midisco 0 0
/mnt/midisco/greenbone/datos/openvas /var/lib/openvas none bind,x-systemd.requires-mounts-for=/mnt/midisco 0 0
/mnt/midisco/greenbone/datos/notus   /var/lib/notus   none bind,x-systemd.requires-mounts-for=/mnt/midisco 0 0
EOF
sudo systemctl daemon-reload
sudo mount -a
findmnt /var/lib/gvm
```

- `mkdir` crea los directorios de origen en el disco grande y los puntos de montaje vacíos en `/var/lib`.
- `tee -a /etc/fstab` **añade** (`-a` = *append*) tres líneas al fichero de montajes. La palabra `bind` indica el tipo de montaje; `x-systemd.requires-mounts-for=/mnt/midisco` obliga a systemd a montar antes `/mnt/midisco`. Las comillas en `'EOF'` evitan que la shell expanda variables dentro del texto.
- `systemctl daemon-reload` hace que systemd relea `fstab`; `mount -a` monta todo lo que esté en `fstab` y aún no lo esté.
- `findmnt /var/lib/gvm` debe mostrar el origen `/mnt/midisco/greenbone/datos/gvm`. Si sale vacío, el montaje no se ha hecho.
- Un error en `fstab` puede impedir arrancar el sistema: revisar las líneas antes de reiniciar (`sudo findmnt --verify`).

### 4.5 Dependencias comunes y clave de firma de Greenbone

```bash
sudo apt update
sudo apt install --no-install-recommends --assume-yes build-essential curl cmake pkg-config python3 python3-pip gnupg
```

- `build-essential`: compilador de C/C++ y `make`. `cmake`: el sistema de construcción que usan los componentes. `pkg-config`: ayuda a encontrar librerías. `curl`: descargas. `gnupg`: verificar firmas.
- `--no-install-recommends` evita paquetes opcionales; `--assume-yes` responde «sí» a todo.

Importamos la clave con la que Greenbone firma sus versiones:

```bash
curl -f -L https://www.greenbone.net/GBCommunitySigningKey.asc -o /tmp/GBCommunitySigningKey.asc
gpg --import /tmp/GBCommunitySigningKey.asc
echo "8AE4BE429B60A59B311C2E739823FAA60ED1E580:6:" | gpg --import-ownertrust
```

- Descargamos la clave pública y la importamos a nuestro llavero. **Por qué es importante:** al compilar código descargado de internet y ejecutarlo luego con privilegios, necesitamos asegurarnos de que no ha sido alterado. La firma lo demuestra.
- El último comando marca esa clave como «totalmente de confianza» (`:6:`) para que `gpg --verify` muestre un mensaje limpio.

### 4.6 Compilar e instalar cada componente

El orden **importa**: cada pieza depende de las anteriores. Para todas se repite el mismo patrón de cinco pasos, que explicamos aquí una vez:

1. **Instalar dependencias** con `apt` (librerías de desarrollo `-dev`).
2. **Descargar** el tarball y su firma `.asc` con `curl -f -L ... -o ...`.
3. **Verificar** con `gpg --verify firma.asc tarball`. Debe aparecer `Good signature from "Greenbone Community Feed integrity key"`. Si dice `BAD signature`, **paramos y volvemos a descargar**.
4. **Compilar** con `cmake -S <fuentes> -B <build> ...` (configurar) y `cmake --build <build> -j$(nproc)` (compilar usando todos los núcleos).
5. **Instalar** en dos pasos: `make DESTDIR=$INSTALL_DIR/<comp> install` (instala en una carpeta temporal para poder revisar qué se instala) y `sudo cp -rv $INSTALL_DIR/<comp>/* /` (lo copia al sistema real).

> Las versiones siguientes son las de la guía oficial cuando preparamos este documento. Antes de empezar comprobamos en la página *Building from Source* de greenbone.github.io/docs si hay versiones más nuevas; si una descarga da error 404, es que la versión ha cambiado.

#### 4.6.1 gvm-libs (librería base)

```bash
export GVM_LIBS_VERSION=23.9.3
sudo apt install -y libcjson-dev libcurl4-gnutls-dev libgcrypt-dev libglib2.0-dev libgnutls28-dev libgpgme-dev libhiredis-dev libnet1-dev libpaho-mqtt-dev libpcap-dev libssh-dev libxml2-dev uuid-dev libldap2-dev libradcli-dev
curl -f -L https://github.com/greenbone/gvm-libs/archive/refs/tags/v$GVM_LIBS_VERSION.tar.gz -o $SOURCE_DIR/gvm-libs-$GVM_LIBS_VERSION.tar.gz
curl -f -L https://github.com/greenbone/gvm-libs/releases/download/v$GVM_LIBS_VERSION/gvm-libs-$GVM_LIBS_VERSION.tar.gz.asc -o $SOURCE_DIR/gvm-libs-$GVM_LIBS_VERSION.tar.gz.asc
gpg --verify $SOURCE_DIR/gvm-libs-$GVM_LIBS_VERSION.tar.gz.asc $SOURCE_DIR/gvm-libs-$GVM_LIBS_VERSION.tar.gz
tar -C $SOURCE_DIR -xvzf $SOURCE_DIR/gvm-libs-$GVM_LIBS_VERSION.tar.gz
mkdir -p $BUILD_DIR/gvm-libs
cmake -S $SOURCE_DIR/gvm-libs-$GVM_LIBS_VERSION -B $BUILD_DIR/gvm-libs -DCMAKE_INSTALL_PREFIX=$INSTALL_PREFIX -DCMAKE_BUILD_TYPE=Release -DSYSCONFDIR=/etc -DLOCALSTATEDIR=/var
cmake --build $BUILD_DIR/gvm-libs -j$(nproc)
mkdir -p $INSTALL_DIR/gvm-libs && cd $BUILD_DIR/gvm-libs
make DESTDIR=$INSTALL_DIR/gvm-libs install
sudo cp -rv $INSTALL_DIR/gvm-libs/* /
```

- Las dependencias son librerías de XML, red, criptografía (gcrypt/gnutls), SSH, MQTT, etc. `libldap2-dev` y `libradcli-dev` son opcionales (autenticación LDAP/RADIUS).
- Opciones de `cmake`: `-DCMAKE_BUILD_TYPE=Release` compila optimizado; `-DSYSCONFDIR=/etc` y `-DLOCALSTATEDIR=/var` fijan dónde van configuración y datos variables (si no, por defecto irían a `/usr/local/etc`).
- `$(nproc)` se sustituye por el número de núcleos: compila en paralelo.

#### 4.6.2 gvmd (el gestor)

```bash
export GVMD_VERSION=26.37.0
sudo apt install -y libbsd-dev libcjson-dev libglib2.0-dev libgnutls28-dev libgpgme-dev libical-dev libpq-dev postgresql-server-dev-all rsync xsltproc
sudo apt install -y --no-install-recommends dpkg fakeroot gnupg gnutls-bin gpgsm nsis openssh-client python3 python3-lxml rpm smbclient snmp socat sshpass texlive-fonts-recommended texlive-latex-extra wget xmlstarlet zip
curl -f -L https://github.com/greenbone/gvmd/archive/refs/tags/v$GVMD_VERSION.tar.gz -o $SOURCE_DIR/gvmd-$GVMD_VERSION.tar.gz
curl -f -L https://github.com/greenbone/gvmd/releases/download/v$GVMD_VERSION/gvmd-$GVMD_VERSION.tar.gz.asc -o $SOURCE_DIR/gvmd-$GVMD_VERSION.tar.gz.asc
gpg --verify $SOURCE_DIR/gvmd-$GVMD_VERSION.tar.gz.asc $SOURCE_DIR/gvmd-$GVMD_VERSION.tar.gz
tar -C $SOURCE_DIR -xvzf $SOURCE_DIR/gvmd-$GVMD_VERSION.tar.gz
mkdir -p $BUILD_DIR/gvmd
cmake -S $SOURCE_DIR/gvmd-$GVMD_VERSION -B $BUILD_DIR/gvmd -DCMAKE_INSTALL_PREFIX=$INSTALL_PREFIX -DCMAKE_BUILD_TYPE=Release -DLOCALSTATEDIR=/var -DSYSCONFDIR=/etc -DGVM_DATA_DIR=/var -DGVM_LOG_DIR=/var/log/gvm -DGVMD_RUN_DIR=/run/gvmd -DOPENVAS_DEFAULT_SOCKET=/run/ospd/ospd-openvas.sock -DGVM_FEED_LOCK_PATH=/var/lib/gvm/feed-update.lock -DLOGROTATE_DIR=/etc/logrotate.d
cmake --build $BUILD_DIR/gvmd -j$(nproc)
mkdir -p $INSTALL_DIR/gvmd && cd $BUILD_DIR/gvmd
make DESTDIR=$INSTALL_DIR/gvmd install
sudo cp -rv $INSTALL_DIR/gvmd/* /
```

- `libpq-dev` y `postgresql-server-dev-all` permiten hablar con PostgreSQL. `libical-dev` sirve para las programaciones (calendario iCalendar).
- El segundo bloque de `apt` son **dependencias opcionales** con funciones concretas: `texlive-*` para generar informes en PDF, `smbclient`/`snmp` para escaneos de Windows/SNMP, `sshpass`/`openssh-client` para credenciales SSH, `zip`/`rpm`/`nsis`/`dpkg`/`fakeroot` para generar instaladores de credenciales. **Los paquetes `texlive` son grandes (cientos de MB)**; si falta espacio, se puede omitir y se pierde el formato PDF.
- Opciones de `cmake`: `GVM_LOG_DIR` (logs en `/var/log/gvm`), `GVMD_RUN_DIR` (donde está su socket), `OPENVAS_DEFAULT_SOCKET` (socket del escáner con el que habla gvmd) y `GVM_FEED_LOCK_PATH` (fichero de bloqueo para que no haya dos sincronizaciones a la vez).

si falla :

1

```sh
echo "$SOURCE_DIR | $BUILD_DIR | $INSTALL_DIR | $INSTALL_PREFIX"
```

2

```sh
cd /mnt/midisco/greenbone
rm -rf $BUILD_DIR/gvmd
export GVMD_VERSION=26.37.0
curl -f -L https://github.com/greenbone/gvmd/archive/refs/tags/v$GVMD_VERSION.tar.gz -o $SOURCE_DIR/gvmd-$GVMD_VERSION.tar.gz
curl -f -L https://github.com/greenbone/gvmd/releases/download/v$GVMD_VERSION/gvmd-$GVMD_VERSION.tar.gz.asc -o $SOURCE_DIR/gvmd-$GVMD_VERSION.tar.gz.asc
gpg --verify $SOURCE_DIR/gvmd-$GVMD_VERSION.tar.gz.asc $SOURCE_DIR/gvmd-$GVMD_VERSION.tar.gz
ls -lh $SOURCE_DIR
```

3

```sh
tar -C $SOURCE_DIR -xvzf $SOURCE_DIR/gvmd-$GVMD_VERSION.tar.gz
mkdir -p $BUILD_DIR/gvmd
cmake -S $SOURCE_DIR/gvmd-$GVMD_VERSION -B $BUILD_DIR/gvmd -DCMAKE_INSTALL_PREFIX=$INSTALL_PREFIX -DCMAKE_BUILD_TYPE=Release -DLOCALSTATEDIR=/var -DSYSCONFDIR=/etc -DGVM_DATA_DIR=/var -DGVM_LOG_DIR=/var/log/gvm -DGVMD_RUN_DIR=/run/gvmd -DOPENVAS_DEFAULT_SOCKET=/run/ospd/ospd-openvas.sock -DGVM_FEED_LOCK_PATH=/var/lib/gvm/feed-update.lock -DLOGROTATE_DIR=/etc/logrotate.d
```

4

```sh
cmake --build $BUILD_DIR/gvmd -j$(nproc)
mkdir -p $INSTALL_DIR/gvmd && cd $BUILD_DIR/gvmd
make DESTDIR=$INSTALL_DIR/gvmd install
sudo cp -rv $INSTALL_DIR/gvmd/* /
```

```sh
juanka@JuankaPortatil:/mnt/midisco/greenbone/build/gvmd$ sudo ldconfig
ls -l /usr/local/sbin/gvmd
/usr/local/sbin/gvmd --version
-rwxr-xr-x 1 root root 3090776 oct 22 08:41 /usr/local/sbin/gvmd
Greenbone Vulnerability Manager 26.37.0
Manager DB revision 281
Copyright (C) 2009-2026 Greenbone AG
License: AGPL-3.0-or-later
This is free software: you are free to change and redistribute it.
There is NO WARRANTY, to the extent permitted by law.
```
#### 4.6.3 pg-gvm (extensión de PostgreSQL)

```bash
export PG_GVM_VERSION=22.6.9
sudo apt install -y libglib2.0-dev libical-dev postgresql-server-dev-all
curl -f -L https://github.com/greenbone/pg-gvm/archive/refs/tags/v$PG_GVM_VERSION.tar.gz -o $SOURCE_DIR/pg-gvm-$PG_GVM_VERSION.tar.gz
curl -f -L https://github.com/greenbone/pg-gvm/releases/download/v$PG_GVM_VERSION/pg-gvm-$PG_GVM_VERSION.tar.gz.asc -o $SOURCE_DIR/pg-gvm-$PG_GVM_VERSION.tar.gz.asc
gpg --verify $SOURCE_DIR/pg-gvm-$PG_GVM_VERSION.tar.gz.asc $SOURCE_DIR/pg-gvm-$PG_GVM_VERSION.tar.gz
tar -C $SOURCE_DIR -xvzf $SOURCE_DIR/pg-gvm-$PG_GVM_VERSION.tar.gz
mkdir -p $BUILD_DIR/pg-gvm
cmake -S $SOURCE_DIR/pg-gvm-$PG_GVM_VERSION -B $BUILD_DIR/pg-gvm -DCMAKE_BUILD_TYPE=Release
cmake --build $BUILD_DIR/pg-gvm -j$(nproc)
mkdir -p $INSTALL_DIR/pg-gvm && cd $BUILD_DIR/pg-gvm
make DESTDIR=$INSTALL_DIR/pg-gvm install
sudo cp -rv $INSTALL_DIR/pg-gvm/* /
```

- Es una **extensión** de PostgreSQL que añade funciones usadas por gvmd (cálculo de rangos de hosts, calendarios). Se instala dentro de los directorios de extensiones de PostgreSQL, por eso necesita `postgresql-server-dev-all`.

#### 4.6.4 GSA (aplicación web) y gsad (servidor web)

```bash
export GSA_VERSION=28.3.0
curl -f -L https://github.com/greenbone/gsa/releases/download/v$GSA_VERSION/gsa-dist-$GSA_VERSION.tar.gz -o $SOURCE_DIR/gsa-$GSA_VERSION.tar.gz
curl -f -L https://github.com/greenbone/gsa/releases/download/v$GSA_VERSION/gsa-dist-$GSA_VERSION.tar.gz.asc -o $SOURCE_DIR/gsa-$GSA_VERSION.tar.gz.asc
gpg --verify $SOURCE_DIR/gsa-$GSA_VERSION.tar.gz.asc $SOURCE_DIR/gsa-$GSA_VERSION.tar.gz
mkdir -p $SOURCE_DIR/gsa-$GSA_VERSION
tar -C $SOURCE_DIR/gsa-$GSA_VERSION -xvzf $SOURCE_DIR/gsa-$GSA_VERSION.tar.gz
sudo mkdir -p $INSTALL_PREFIX/share/gvm/gsad/web/
sudo cp -rv $SOURCE_DIR/gsa-$GSA_VERSION/* $INSTALL_PREFIX/share/gvm/gsad/web/
```

- GSA está escrita en JavaScript (React). Compilarla exige Node.js y mucho tiempo, así que usamos la **versión ya compilada** (`gsa-dist`), que simplemente se copia al directorio que sirve `gsad`.

```bash
export GSAD_VERSION=27.2.0
sudo apt install -y libbrotli-dev libglib2.0-dev libgnutls28-dev libmicrohttpd-dev libxml2-dev
curl -f -L https://github.com/greenbone/gsad/archive/refs/tags/v$GSAD_VERSION.tar.gz -o $SOURCE_DIR/gsad-$GSAD_VERSION.tar.gz
curl -f -L https://github.com/greenbone/gsad/releases/download/v$GSAD_VERSION/gsad-$GSAD_VERSION.tar.gz.asc -o $SOURCE_DIR/gsad-$GSAD_VERSION.tar.gz.asc
gpg --verify $SOURCE_DIR/gsad-$GSAD_VERSION.tar.gz.asc $SOURCE_DIR/gsad-$GSAD_VERSION.tar.gz
tar -C $SOURCE_DIR -xvzf $SOURCE_DIR/gsad-$GSAD_VERSION.tar.gz
mkdir -p $BUILD_DIR/gsad
cmake -S $SOURCE_DIR/gsad-$GSAD_VERSION -B $BUILD_DIR/gsad -DCMAKE_INSTALL_PREFIX=$INSTALL_PREFIX -DCMAKE_BUILD_TYPE=Release -DSYSCONFDIR=/etc -DLOCALSTATEDIR=/var -DGVMD_RUN_DIR=/run/gvmd -DGSAD_RUN_DIR=/run/gsad -DGVM_LOG_DIR=/var/log/gvm -DLOGROTATE_DIR=/etc/logrotate.d
cmake --build $BUILD_DIR/gsad -j$(nproc)
mkdir -p $INSTALL_DIR/gsad && cd $BUILD_DIR/gsad
make DESTDIR=$INSTALL_DIR/gsad install
sudo cp -rv $INSTALL_DIR/gsad/* /
```

- `gsad` es el servidor web en C: sirve los ficheros de GSA y traduce lo que hace el navegador a mensajes **GMP** (*Greenbone Management Protocol*) hacia gvmd.

#### 4.6.5 openvas-smb (opcional, necesario para escanear Windows)

```bash
export OPENVAS_SMB_VERSION=22.5.3
sudo apt install -y gcc-mingw-w64 libgnutls28-dev libglib2.0-dev libpopt-dev libunistring-dev heimdal-multidev perl-base
curl -f -L https://github.com/greenbone/openvas-smb/archive/refs/tags/v$OPENVAS_SMB_VERSION.tar.gz -o $SOURCE_DIR/openvas-smb-$OPENVAS_SMB_VERSION.tar.gz
curl -f -L https://github.com/greenbone/openvas-smb/releases/download/v$OPENVAS_SMB_VERSION/openvas-smb-v$OPENVAS_SMB_VERSION.tar.gz.asc -o $SOURCE_DIR/openvas-smb-$OPENVAS_SMB_VERSION.tar.gz.asc
gpg --verify $SOURCE_DIR/openvas-smb-$OPENVAS_SMB_VERSION.tar.gz.asc $SOURCE_DIR/openvas-smb-$OPENVAS_SMB_VERSION.tar.gz
tar -C $SOURCE_DIR -xvzf $SOURCE_DIR/openvas-smb-$OPENVAS_SMB_VERSION.tar.gz
mkdir -p $BUILD_DIR/openvas-smb
cmake -S $SOURCE_DIR/openvas-smb-$OPENVAS_SMB_VERSION -B $BUILD_DIR/openvas-smb -DCMAKE_INSTALL_PREFIX=$INSTALL_PREFIX -DCMAKE_BUILD_TYPE=Release
cmake --build $BUILD_DIR/openvas-smb -j$(nproc)
mkdir -p $INSTALL_DIR/openvas-smb && cd $BUILD_DIR/openvas-smb
make DESTDIR=$INSTALL_DIR/openvas-smb install
sudo cp -rv $INSTALL_DIR/openvas-smb/* /
```

- Contiene las librerías y el programa `winexe` que permiten al escáner conectarse a Windows (WMI/SMB) con credenciales y ejecutar comprobaciones. Sin él, los escaneos autenticados de máquinas Windows no funcionan. Es necesario para nuestro escenario con cliente Windows (R1).

Si falla:

1

```sh
echo "$SOURCE_DIR | $BUILD_DIR | $INSTALL_DIR | $INSTALL_PREFIX"
``` 

y ejecutamos de nuevo.

#### 4.6.6 openvas-scanner (el motor de escaneo)

```bash
export OPENVAS_SCANNER_VERSION=23.20.1
sudo apt install -y bison libglib2.0-dev libgnutls28-dev libgcrypt20-dev libpcap-dev libgpgme-dev libksba-dev rsync nmap libjson-glib-dev libcurl4-gnutls-dev libbsd-dev krb5-multidev python3-impacket libsnmp-dev
curl -f -L https://github.com/greenbone/openvas-scanner/archive/refs/tags/v$OPENVAS_SCANNER_VERSION.tar.gz -o $SOURCE_DIR/openvas-scanner-$OPENVAS_SCANNER_VERSION.tar.gz
curl -f -L https://github.com/greenbone/openvas-scanner/releases/download/v$OPENVAS_SCANNER_VERSION/openvas-scanner-v$OPENVAS_SCANNER_VERSION.tar.gz.asc -o $SOURCE_DIR/openvas-scanner-$OPENVAS_SCANNER_VERSION.tar.gz.asc
gpg --verify $SOURCE_DIR/openvas-scanner-$OPENVAS_SCANNER_VERSION.tar.gz.asc $SOURCE_DIR/openvas-scanner-$OPENVAS_SCANNER_VERSION.tar.gz
tar -C $SOURCE_DIR -xvzf $SOURCE_DIR/openvas-scanner-$OPENVAS_SCANNER_VERSION.tar.gz
mkdir -p $BUILD_DIR/openvas-scanner
cmake -S $SOURCE_DIR/openvas-scanner-$OPENVAS_SCANNER_VERSION -B $BUILD_DIR/openvas-scanner -DCMAKE_INSTALL_PREFIX=$INSTALL_PREFIX -DCMAKE_BUILD_TYPE=Release -DSYSCONFDIR=/etc -DLOCALSTATEDIR=/var -DOPENVAS_FEED_LOCK_PATH=/var/lib/openvas/feed-update.lock -DOPENVAS_RUN_DIR=/run/ospd
cmake --build $BUILD_DIR/openvas-scanner -j$(nproc)
mkdir -p $INSTALL_DIR/openvas-scanner && cd $BUILD_DIR/openvas-scanner
make DESTDIR=$INSTALL_DIR/openvas-scanner install
sudo cp -rv $INSTALL_DIR/openvas-scanner/* /
printf "table_driven_lsc = yes\n" | sudo tee /etc/openvas/openvas.conf
printf "openvasd_server = http://127.0.0.1:3000\n" | sudo tee -a /etc/openvas/openvas.conf
```

- Es el programa `openvas` que ejecuta los miles de scripts NASL. Usa `nmap` para el descubrimiento de puertos y `impacket` para algunas pruebas de Windows.
- Las dos últimas líneas crean `/etc/openvas/openvas.conf`: `table_driven_lsc = yes` activa las comprobaciones por tabla de versiones de paquetes (Notus), mucho más rápidas que las antiguas; `openvasd_server` indica dónde está el servicio `openvasd` que las responde. Con `tee` sin `-a` se **crea/sobrescribe** el fichero; con `-a` se añade.

#### 4.6.7 ospd-openvas (puente entre gvmd y el scanner)

```bash
export OSPD_OPENVAS_VERSION=22.10.5
sudo apt install -y python3 python3-pip python3-setuptools python3-packaging python3-wrapt python3-cffi python3-psutil python3-lxml python3-defusedxml python3-paramiko python3-redis python3-gnupg python3-paho-mqtt
curl -f -L https://github.com/greenbone/ospd-openvas/archive/refs/tags/v$OSPD_OPENVAS_VERSION.tar.gz -o $SOURCE_DIR/ospd-openvas-$OSPD_OPENVAS_VERSION.tar.gz
curl -f -L https://github.com/greenbone/ospd-openvas/releases/download/v$OSPD_OPENVAS_VERSION/ospd-openvas-v$OSPD_OPENVAS_VERSION.tar.gz.asc -o $SOURCE_DIR/ospd-openvas-$OSPD_OPENVAS_VERSION.tar.gz.asc
gpg --verify $SOURCE_DIR/ospd-openvas-$OSPD_OPENVAS_VERSION.tar.gz.asc $SOURCE_DIR/ospd-openvas-$OSPD_OPENVAS_VERSION.tar.gz
tar -C $SOURCE_DIR -xvzf $SOURCE_DIR/ospd-openvas-$OSPD_OPENVAS_VERSION.tar.gz
cd $SOURCE_DIR/ospd-openvas-$OSPD_OPENVAS_VERSION
mkdir -p $INSTALL_DIR/ospd-openvas
python3 -m pip install --root=$INSTALL_DIR/ospd-openvas --no-warn-script-location --break-system-packages .
sudo cp -rv $INSTALL_DIR/ospd-openvas/* /
```

- Es un programa en Python que recibe órdenes de gvmd por un socket Unix (protocolo OSP) y controla el scanner.
- **Adaptación Debian 13:** Debian 12 y 13 protegen el Python del sistema con la norma PEP 668 y `pip` falla con `error: externally-managed-environment`. Como instalamos con `--root` en una carpeta temporal y luego copiamos nosotros, añadimos `--break-system-packages`. Es la única vez que ignoramos esa protección, y es controlado: los ficheros acaban bajo `/usr/local`, no mezclados con los paquetes de `apt`.
- `--root=<carpeta>` instala todo dentro de esa carpeta temporal imitando la estructura real (`<carpeta>/usr/local/bin/...`).

#### 4.6.8 openvasd (Rust) y herramientas auxiliares

```bash
export OPENVAS_DAEMON=23.20.0
sudo apt install -y pkg-config libssl-dev
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source $HOME/.cargo/env
rustup update stable
curl -f -L https://github.com/greenbone/openvas-scanner/archive/refs/tags/v$OPENVAS_DAEMON.tar.gz -o $SOURCE_DIR/openvas-scanner-$OPENVAS_DAEMON.tar.gz
curl -f -L https://github.com/greenbone/openvas-scanner/releases/download/v$OPENVAS_DAEMON/openvas-scanner-v$OPENVAS_DAEMON.tar.gz.asc -o $SOURCE_DIR/openvas-scanner-$OPENVAS_DAEMON.tar.gz.asc
gpg --verify $SOURCE_DIR/openvas-scanner-$OPENVAS_DAEMON.tar.gz.asc $SOURCE_DIR/openvas-scanner-$OPENVAS_DAEMON.tar.gz
tar -C $SOURCE_DIR -xvzf $SOURCE_DIR/openvas-scanner-$OPENVAS_DAEMON.tar.gz
mkdir -p $INSTALL_DIR/openvasd/usr/local/bin
cd $SOURCE_DIR/openvas-scanner-$OPENVAS_DAEMON/rust
cargo build --release
sudo cp -v ../target/release/openvasd $INSTALL_DIR/openvasd/usr/local/bin/
sudo cp -v ../target/release/scannerctl $INSTALL_DIR/openvasd/usr/local/bin/
sudo cp -rv $INSTALL_DIR/openvasd/* /
```

- `openvasd` está escrito en **Rust**. La guía oficial indica que la versión de Rust de Debian puede ser demasiado antigua, así que instalamos `rustup` (instalador oficial de Rust) con la orden `curl ... | sh`. Ese comando descarga un script y lo ejecuta: lo hacemos porque es el método oficial de rustup.rs, pero sabemos que **ejecutar scripts de internet sin leerlos es un riesgo**; lo más prudente es descargarlo primero, leerlo y luego ejecutarlo.
- `source $HOME/.cargo/env` añade `cargo` (el gestor de compilación de Rust) al PATH de la terminal actual.
- `cargo build --release` compila de forma optimizada y deja los binarios en `target/release/`. **Ojo:** la ruta exacta de `target/` puede variar; si no se encuentra el binario, `find $SOURCE_DIR -name openvasd -type f` lo localiza y se ajustan las rutas de `cp`.
- Su papel aquí: servir las comprobaciones **Notus** (versiones de paquetes) cuando hay un escaneo autenticado con SSH.

Herramientas Python auxiliares:

```bash
mkdir -p $INSTALL_DIR/greenbone-feed-sync $INSTALL_DIR/gvm-tools
python3 -m pip install --root=$INSTALL_DIR/greenbone-feed-sync --no-warn-script-location --break-system-packages greenbone-feed-sync
sudo cp -rv $INSTALL_DIR/greenbone-feed-sync/* /
sudo apt install -y python3-lxml python3-packaging python3-paramiko python3-venv python3-setuptools
python3 -m pip install --root=$INSTALL_DIR/gvm-tools --no-warn-script-location --break-system-packages gvm-tools
sudo cp -rv $INSTALL_DIR/gvm-tools/* /
```

- `greenbone-feed-sync` descarga el feed (VTs, SCAP, CERT y datos de gvmd) con `rsync`.
- `gvm-tools` instala `gvm-cli` y `gvm-script`, que usaremos en la sección de automatización.

### 4.7 Configuración del sistema tras compilar

#### 4.7.1 Redis (almacén de datos del escáner)

```bash
sudo apt install -y redis-server
sudo cp $SOURCE_DIR/openvas-scanner-$OPENVAS_SCANNER_VERSION/config/redis-openvas.conf /etc/redis/
sudo chown redis:redis /etc/redis/redis-openvas.conf
echo "db_address = /run/redis-openvas/redis.sock" | sudo tee -a /etc/openvas/openvas.conf
sudo systemctl start redis-server@openvas.service
sudo systemctl enable redis-server@openvas.service
sudo usermod -aG redis gvm
```

- Instalamos Redis y usamos una **segunda instancia** dedicada al escáner (`redis-server@openvas`), con la configuración que trae el código de openvas-scanner, para no interferir con otros usos de Redis.
- La línea `db_address` le dice al scanner por qué socket Unix hablar con Redis.
- `usermod -aG redis gvm` permite al usuario `gvm` acceder a ese socket.

#### 4.7.2 Permisos de directorios

```bash
sudo mkdir -p /var/lib/notus /run/gvmd
sudo chown -R gvm:gvm /var/lib/gvm /var/lib/openvas /var/lib/notus /var/log/gvm /run/gvmd
sudo chmod -R g+srw /var/lib/gvm /var/lib/openvas /var/log/gvm
sudo chown gvm:gvm /usr/local/sbin/gvmd
sudo chmod 6750 /usr/local/sbin/gvmd
```

- `chown -R gvm:gvm` hace propietario al usuario del servicio de todos los directorios de datos y logs. Como `/var/lib/gvm` es un montaje *bind*, el cambio se aplica en `/mnt/midisco/greenbone/datos/gvm`.
- `chmod g+srw` da lectura/escritura al grupo y activa **setgid** (`s`), de modo que los ficheros nuevos hereden el grupo `gvm`.
- `chmod 6750` sobre `gvmd` activa setuid+setgid: el binario siempre se ejecuta como `gvm:gvm` aunque lo lance otro usuario del grupo.

#### 4.7.3 Llavero GPG para validar el feed

```bash
export GNUPGHOME=/tmp/openvas-gnupg
mkdir -p $GNUPGHOME
gpg --import /tmp/GBCommunitySigningKey.asc
echo "8AE4BE429B60A59B311C2E739823FAA60ED1E580:6:" | gpg --import-ownertrust
export OPENVAS_GNUPG_HOME=/etc/openvas/gnupg
sudo mkdir -p $OPENVAS_GNUPG_HOME
sudo cp -r /tmp/openvas-gnupg/* $OPENVAS_GNUPG_HOME/
sudo chown -R gvm:gvm $OPENVAS_GNUPG_HOME
unset GNUPGHOME
```

- El feed también va firmado. Creamos un llavero GPG aparte (`GNUPGHOME`) con la clave de Greenbone y lo copiamos a `/etc/openvas/gnupg`, que es donde el scanner busca las claves para validar cada prueba. El `unset` final restaura el llavero normal de nuestro usuario.

#### 4.7.4 sudo para el scanner

```bash
echo "%gvm ALL = NOPASSWD: /usr/local/sbin/openvas" | sudo tee /etc/sudoers.d/gvm
sudo chmod 0440 /etc/sudoers.d/gvm
```

- El escáner necesita crear *sockets raw* (paquetes de red a bajo nivel), algo que solo puede hacer root. Esta regla permite a los miembros del grupo `gvm` ejecutar **solo** `/usr/local/sbin/openvas` como root sin contraseña. `0440` son los permisos obligatorios de los ficheros de `sudoers.d`.
- **Riesgo conocido:** los scripts NASL del feed se ejecutan con privilegios de root, y quien pertenezca al grupo `gvm` puede modificarlos. Por eso no añadimos más usuarios a ese grupo de los estrictamente necesarios.

#### 4.7.5 PostgreSQL

```bash
sudo apt install -y postgresql
sudo systemctl start postgresql@17-main
sudo -u postgres bash -c "createuser -DRS gvm && createdb -O gvm gvmd && psql gvmd -c 'create role dba with superuser noinherit; grant dba to gvm;'"
```

- En Debian 13 la versión de PostgreSQL es la 17, por eso el servicio se llama `postgresql@17-main` (en la guía oficial, para Debian 12, `postgresql@15-main`). Lo comprobamos con `systemctl list-units 'postgresql*'`.
- `createuser -DRS gvm` crea el rol `gvm` sin permiso para crear bases de datos (`-D`), ni roles (`-R`), ni superusuario (`-S`). `createdb -O gvm gvmd` crea la base de datos `gvmd` con ese propietario.
- La última orden crea un rol `dba` con permisos de superusuario y se lo concede al usuario `gvm`: gvmd lo necesita para instalar la extensión `pg-gvm`.
- La base de datos crece con el uso (informes, resultados). Si el disco del sistema es pequeño, también se puede llevar `/var/lib/postgresql` a `/mnt/midisco` con otro montaje *bind* **antes** de instalar PostgreSQL.

#### 4.7.6 Usuario administrador y propietario del feed

```bash
/usr/local/sbin/gvmd --create-user=admin --password='<CONTRASEÑA>'
/usr/local/sbin/gvmd --modify-setting 78eceaec-3385-11ea-b237-28d24461215b --value `/usr/local/sbin/gvmd --get-users --verbose | grep admin | awk '{print $2}'`
```

- La primera orden crea el usuario `admin`. Si todo va bien, escribe `User created.`; si no, el motivo está en `/var/log/gvm/gvmd.log`.
- La segunda fija a `admin` como **Feed Import Owner**: gvmd solo crea configuraciones de escaneo como «Full and fast» si existe un propietario para ellas. El identificador largo es el de ese ajuste concreto. La parte entre comillas invertidas obtiene el UUID de admin (`--get-users --verbose` lista los usuarios, `grep admin` filtra y `awk '{print $2}'` coge la segunda columna).

#### 4.7.7 Servicios systemd

Creamos los ficheros de servicio en `$BUILD_DIR` y los copiamos a `/etc/systemd/system/`. Mostramos el de ospd-openvas completo y explicamos sus líneas; los de gvmd, gsad y openvasd siguen la misma estructura.

```bash
cat << EOF > $BUILD_DIR/ospd-openvas.service
[Unit]
Description=OSPd Wrapper for the OpenVAS Scanner (ospd-openvas)
Documentation=man:ospd-openvas(8) man:openvas(8)
After=network.target networking.service redis-server@openvas.service openvasd.service
Wants=redis-server@openvas.service openvasd.service
ConditionKernelCommandLine=!recovery

[Service]
Type=exec
User=gvm
Group=gvm
RuntimeDirectory=ospd
RuntimeDirectoryMode=2775
PIDFile=/run/ospd/ospd-openvas.pid
ExecStart=/usr/local/bin/ospd-openvas --foreground --unix-socket /run/ospd/ospd-openvas.sock --pid-file /run/ospd/ospd-openvas.pid --log-file /var/log/gvm/ospd-openvas.log --lock-file-dir /var/lib/openvas --socket-mode 0o770 --notus-feed-dir /var/lib/notus/advisories
SuccessExitStatus=SIGKILL
Restart=always
RestartSec=60

[Install]
WantedBy=multi-user.target
EOF
sudo cp -v $BUILD_DIR/ospd-openvas.service /etc/systemd/system/
```

- `[Unit]`: descripción y **orden de arranque**: `After=` arranca después de la red y de Redis; `Wants=` lo arrastra si no está arrancado.
- `[Service]`: `User/Group=gvm` ejecuta como el usuario sin privilegios; `RuntimeDirectory=ospd` hace que systemd cree `/run/ospd` en cada arranque con esos permisos; `ExecStart` es el comando real, con rutas del socket, log y fichero de bloqueo; `Restart=always` lo reinicia si se cae.
- `[Install]`: `WantedBy=multi-user.target` permite que `systemctl enable` lo arranque con el sistema.

Unidad de gvmd (se diferencia en `ExecStart`, que le pasa el socket de ospd y el grupo que puede conectarse):

```bash
cat << EOF > $BUILD_DIR/gvmd.service
[Unit]
Description=Greenbone Vulnerability Manager daemon (gvmd)
After=network.target networking.service postgresql.service ospd-openvas.service
Wants=postgresql.service ospd-openvas.service
Documentation=man:gvmd(8)
ConditionKernelCommandLine=!recovery

[Service]
Type=exec
User=gvm
Group=gvm
PIDFile=/run/gvmd/gvmd.pid
RuntimeDirectory=gvmd
RuntimeDirectoryMode=2775
ExecStart=/usr/local/sbin/gvmd --foreground --osp-vt-update=/run/ospd/ospd-openvas.sock --listen-group=gvm
Restart=always
TimeoutStopSec=10

[Install]
WantedBy=multi-user.target
EOF
sudo cp -v $BUILD_DIR/gvmd.service /etc/systemd/system/
```

Unidad de gsad (la web, solo escucha en 127.0.0.1:9392; `--http-only` desactiva TLS porque es local):

```bash
cat << EOF > $BUILD_DIR/gsad.service
[Unit]
Description=Greenbone Security Assistant daemon (gsad)
Documentation=man:gsad(8) https://www.greenbone.net
After=network.target gvmd.service
Wants=gvmd.service

[Service]
Type=exec
User=gvm
Group=gvm
RuntimeDirectory=gsad
RuntimeDirectoryMode=2775
PIDFile=/run/gsad/gsad.pid
ExecStart=/usr/local/sbin/gsad --foreground --listen=127.0.0.1 --port=9392 --http-only
Restart=always
TimeoutStopSec=10

[Install]
WantedBy=multi-user.target
Alias=greenbone-security-assistant.service
EOF
sudo cp -v $BUILD_DIR/gsad.service /etc/systemd/system/
```

Unidad de openvasd (modo `service_notus`: solo atiende las comprobaciones Notus):

```bash
cat << EOF > $BUILD_DIR/openvasd.service
[Unit]
Description=OpenVASD
Documentation=https://github.com/greenbone/openvas-scanner/tree/main/rust/openvasd
ConditionKernelCommandLine=!recovery

[Service]
Type=exec
User=gvm
RuntimeDirectory=openvasd
RuntimeDirectoryMode=2775
ExecStart=/usr/local/bin/openvasd --mode service_notus --products /var/lib/notus/products --advisories /var/lib/notus/advisories --listening 127.0.0.1:3000
SuccessExitStatus=SIGKILL
Restart=always
RestartSec=60

[Install]
WantedBy=multi-user.target
EOF
sudo cp -v $BUILD_DIR/openvasd.service /etc/systemd/system/
sudo systemctl daemon-reload
```

- `daemon-reload` hace que systemd lea los ficheros nuevos.

### 4.8 Descargar el feed y arrancar los servicios

```bash
sudo /usr/local/bin/greenbone-feed-sync
```

- Descarga por `rsync` los cuatro tipos de datos (VT, SCAP, CERT y datos de gvmd). La primera vez son varios GB y puede tardar mucho. Podemos ejecutarlo por partes con `--type nasl`, `--type notus`, `--type scap`, `--type cert` y `--type gvmd-data`.

```bash
sudo systemctl start ospd-openvas gvmd gsad openvasd
sudo systemctl enable ospd-openvas gvmd gsad openvasd
sudo systemctl status ospd-openvas gvmd gsad openvasd --no-pager
sudo tail -f /var/log/gvm/ospd-openvas.log /var/log/gvm/gvmd.log
```

- `start` arranca los cuatro servicios; `enable` los configura para arrancar con el sistema; `status` debe mostrar `active (running)` en todos.
- `tail -f` sigue los logs. Esperamos a los mismos mensajes de carga de feed que en la sección 3.6 (VTs, SCAP, CERT y *Scan config ... has been created*). La primera carga puede tardar **desde minutos hasta horas**.
- Cuando todo esté cargado abrimos `http://127.0.0.1:9392` y entramos con `admin`.

**Si el feed no funciona**

```sh
sudo systemctl stop ospd-openvas gvmd
sudo mkdir -p /var/lib/openvas/plugins /var/lib/notus /var/lib/gvm
sudo chown -R gvm:gvm /var/lib/openvas /var/lib/notus /var/lib/gvm
sudo -u gvm /usr/local/bin/greenbone-feed-sync
```

```sh
sudo du -sh /var/lib/openvas/plugins /var/lib/notus /var/lib/gvm
```

```sh
sudo systemctl start ospd-openvas gvmd
sudo tail -f /var/log/gvm/ospd-openvas.log /var/log/gvm/gvmd.log
```

Si sigue fallando tras descargar el feed.

Ejecuta a mano el comando que falla, para ver el error real en vez de solo el código `1`:

```bash
sudo -u gvm sudo /usr/local/sbin/openvas --update-vt-info
sudo systemctl status redis-server@openvas --no-pager
```
### 4.9 Problemas típicos de este método

| Síntoma | Causa probable | Solución |
| --- | --- | --- |
| `cmake` dice que no encuentra una librería | Falta un paquete `-dev` | `apt search <nombre>` e instalarlo |
| Error de cabecera `libpq-fe.h` al compilar gvmd | Cabecera en otra ruta | `sudo mkdir /usr/include/postgresql && sudo cp /usr/include/libpq-fe.h /usr/include/postgresql/` (lo usa la guía oficial en algunas distribuciones) |
| `externally-managed-environment` con pip | PEP 668 | Añadir `--break-system-packages` (ver 4.6.7) |
| gvmd no conecta con PostgreSQL | Servicio de PostgreSQL no arrancado o base de datos sin crear | `systemctl status postgresql@17-main` y repetir 4.7.5 |
| Escaneos sin resultados | Feed aún cargando o sin propietario del feed | Esperar a los mensajes de 3.6 y repetir 4.7.6 |
| gsad no abre en 9392 | Servicio caído, o el método A usa el mismo puerto | `systemctl status gsad` y parar el método A |

## 5. Configuración de la herramienta: recorrido por Greenbone Security Assistant (GSA)

A partir de aquí el contenido vale igual para el método A y para el B: la interfaz web es la misma. Los nombres de los menús pueden variar ligeramente entre versiones de GSA; la lógica es siempre la misma.

### 5.1 Comprobaciones previas obligatorias

1. **Feed al día:** *Administration → Feed Status*. Las filas de NVT, SCAP, CERT y datos de gvmd deben mostrar una fecha reciente y ningún mensaje de actualización en curso. Si el estado indica que se está actualizando, **esperamos**.
2. **Configuraciones de escaneo cargadas:** *Configuration → Scan Configs* debe listar al menos *Full and fast*. Si está vacío, falta el *Feed Import Owner* o no ha terminado la carga.
3. **Escáner disponible:** *Configuration → Scanners* debe mostrar *OpenVAS Default* (y *CVE*). Pulsando el icono de verificación comprobamos la conexión; debe devolver el número de versión.

### 5.2 Ajustes del usuario

En el menú del usuario (arriba a la derecha) → *My Settings* configuramos lo que afecta a la comodidad y a la lectura de informes:

| Ajuste | Para qué sirve | Valor recomendado |
| --- | --- | --- |
| Timezone | Las fechas de informes y las programaciones usan esta zona horaria | `Europe/Madrid` |
| Password | Cambiar la contraseña | Larga y única |
| User Interface Language | Idioma de la interfaz | Español o inglés |
| Rows Per Page | Filas por tabla | 50 |
| Details Export File Name / Report Export File Name | Plantilla del nombre al exportar | Con fecha y nombre de tarea, para ordenar `informes/` |
| Default Severity | Severidad aplicada a resultados sin CVSS | 10 (lo más prudente) |
| Dynamic Severity | Si los resultados cambian de gravedad al cambiar el CVSS en el feed | Activado en producción |
| Auto Cache Rebuild | Reconstruye cachés del interfaz | Activado |

La zona horaria es importante para la **monitorización continua**: si queda en UTC, una tarea programada «las 03:00» se ejecutará a otra hora local.

### 5.3 Mapa de objetos de Greenbone

Todo se articula en torno a unos pocos objetos que se **crean una vez y se reutilizan**:

| Objeto | Qué es | Menú |
| --- | --- | --- |
| **Target** (objetivo) | *Qué* escaneamos: IPs, rangos, redes, nombres; qué puertos y con qué credenciales | Configuration → Targets |
| **Port List** | Qué puertos se prueban | Configuration → Port Lists |
| **Credential** | Usuario/clave para escaneo autenticado | Configuration → Credentials |
| **Scan Config** | *Cómo* escaneamos: qué pruebas (NVTs) y con qué parámetros | Configuration → Scan Configs |
| **Scanner** | Qué motor ejecuta la tarea | Configuration → Scanners |
| **Schedule** | *Cuándo* y cada cuánto | Configuration → Schedules |
| **Alert** | *Qué hacer* cuando ocurre algo (por ejemplo, enviar un correo) | Configuration → Alerts |
| **Task** (tarea) | Une Target + Scan Config + Scanner (+ Schedule + Alert) y se ejecuta | Scans → Tasks |
| **Report** | El resultado de una ejecución de una tarea | Scans → Reports |
| **Overrides / Notes** | Anotaciones y cambios de gravedad sobre resultados concretos | Scans → Overrides / Notes |

El orden de creación natural es: Credential → Target → (Schedule) → (Alert) → Task → ejecutar → Report.

### 5.4 Targets (objetivos): cada opción

*Configuration → Targets → icono de nueva estrella*. Campos:

| Campo | Qué hace | Notas |
| --- | --- | --- |
| Name | Nombre del objetivo | Usar una convención: `lab-servidorweb`, `lab-red-completa` |
| Hosts | IPs o nombres a escanear. Acepta IP única, rango (`192.168.10.1-50`), CIDR (`192.168.10.0/24`), nombres DNS y listas separadas por comas | Alternativa: *From file* (un fichero de texto con una línea por host) |
| Exclude Hosts | Hosts que **no** tocamos | Imprescindible para excluir el propio escáner, el router o equipos frágiles |
| Allow simultaneous scanning via multiple IPs | Si un equipo tiene varias IPs, las escanea a la vez | Mejor desactivarlo para equipos con varias IPs en la misma máquina |
| Port List | Lista de puertos a explorar | Ver 5.5 |
| Alive Test | Cómo decide el escáner si un host está encendido antes de escanearlo | Ver tabla siguiente |
| Credentials for authenticated checks: SSH, SMB, ESXi, SNMP | Credenciales usadas en los escaneos autenticados | Ver 5.6 |
| Reverse Lookup Only | Solo escanea IPs que tengan nombre DNS inverso | Rara vez |
| Reverse Lookup Unify | Si varias IPs resuelven al mismo nombre, solo escanea una | Útil con balanceadores |

Opciones del **Alive Test** (prueba de que el equipo está vivo):

| Opción | Cómo funciona | Cuándo usarla |
| --- | --- | --- |
| Scan Config Default | Usa lo que dicta la configuración del escaneo | Por defecto |
| ICMP Ping | Envía *ping* | Redes sin cortafuegos |
| TCP-ACK Service Ping | Envía paquetes TCP ACK a puertos comunes | Cuando el ICMP está bloqueado |
| TCP-SYN Service Ping | Paquetes TCP SYN | Alternativa al ACK |
| ARP Ping | Pregunta ARP | **La más fiable en la misma red local (LAN)** |
| ICMP & TCP-ACK Service Ping, ICMP & ARP Ping, TCP-ACK Service & ARP Ping, ICMP & TCP-ACK Service & ARP Ping | Combinaciones de las anteriores | Para máxima detección |
| Consider Alive | No comprueba nada: da por vivos todos los hosts | Cuando sabemos que el equipo está y bloquea todo; tarda mucho en rangos grandes |

> En redes con un cortafuegos que descarta el ping, un *Alive Test* por defecto puede concluir que el equipo no existe y el escaneo termina sin resultados. Si pasa, probamos con *Consider Alive* en un host concreto.

### 5.5 Listas de puertos

*Configuration → Port Lists*. Las predefinidas incluyen (los nombres exactos llevan fecha):

| Lista | Contenido | Uso |
| --- | --- | --- |
| All IANA assigned TCP | Los puertos TCP registrados en IANA (unos 5.900) | **Buen equilibrio** velocidad/cobertura |
| All IANA assigned TCP and UDP | Lo anterior más los UDP registrados | Más lento: UDP es lento por naturaleza |
| All TCP and Nmap top 100 UDP | Los 65.535 puertos TCP + los 100 UDP más habituales de Nmap | Escaneo exhaustivo |

También podemos crear una lista propia con una sintaxis como `T:22,80,443,5432,U:53,161` (T = TCP, U = UDP; se admiten rangos `T:1-1024`). Una lista corta como `T:22,80,443,5432` acelera mucho el escaneo de un servidor concreto.

### 5.6 Credenciales (escaneos autenticados)

Un escaneo **sin credenciales** solo ve lo que se ve desde la red: puertos, banners y versiones anunciadas. Un escaneo **con credenciales** entra en la máquina y lista los paquetes instalados, comparando cada uno con los avisos de seguridad (comprobaciones Notus). Encuentra bastantes más fallos y con menos falsos positivos.

*Configuration → Credentials → nueva*. Tipos:

| Tipo | Para qué |
| --- | --- |
| Username + Password | Acceso SSH, SMB, ESXi, etc. con usuario y contraseña |
| Username + SSH Key | Acceso SSH con clave privada (preferible) |
| Client Certificate | Autenticación con certificado de cliente |
| SNMP | Comunidad SNMP v1/v2c o usuario SNMPv3 |
| S/MIME Certificate | Cifrar informes enviados por correo con S/MIME |
| PGP Encryption Key | Cifrar informes enviados por correo con PGP |
| Password only | Servicios que solo piden contraseña |

Opciones: *Allow insecure use* (si no se activa, la credencial no se puede usar en objetivos que no estén cifrados), y *Auto-generate* (crea un par usuario/clave y un paquete instalable para desplegarlo en la máquina objetivo).

**Buena práctica:** no usar `root`. Creamos en la máquina objetivo un usuario dedicado, por ejemplo `escaneo`, con una clave SSH solo para este fin. Lo haremos en la sección 6.4.

### 5.7 Scan Configs: qué pruebas se ejecutan

*Configuration → Scan Configs*. Las configuraciones que trae el feed:

| Config | Qué hace | Cuándo usarla |
| --- | --- | --- |
| **Discovery** | Solo descubre servicios y datos del sistema; no busca fallos | Inventario rápido |
| **Host Discovery** | Únicamente comprueba qué hosts están vivos | Mapa de una red |
| **System Discovery** | Descubre hosts y sistemas operativos | Inventario con SO |
| **Base** | Pruebas básicas, sin las intrusivas | Primer contacto |
| **Full and fast** | Casi todas las pruebas no peligrosas, usando los resultados del descubrimiento para ejecutar solo lo aplicable | **La recomendada por defecto** |
| **Full and very deep** | Lo anterior sin atajos: ejecuta pruebas aunque el descubrimiento no las considere aplicables | Mucho más lento; útil si se sospechan servicios en puertos raros |
| Empty / Log4Shell y otras de feed | Configuraciones vacías o específicas para una amenaza | Según el caso; las específicas son muy rápidas |

**Clonar y editar una configuración** (las predefinidas no se pueden editar): clonar *Full and fast* y modificarla permite:

- **Familias de NVT:** activar o desactivar familias enteras (por ejemplo, desactivar *Denial of Service* para no tumbar servicios, o activar solo *Web application abuses* y *Product detection* para un servidor web). Las familias nuevas que aparezcan en futuras actualizaciones se pueden incluir o no automáticamente (*dynamic families*).
- **NVT concretos:** activar o desactivar pruebas individuales y ajustar sus parámetros.
- **Preferencias del escáner:** parámetros globales como el número de pruebas simultáneas por host, de hosts simultáneos, tiempos de espera o las credenciales por defecto de ciertas pruebas. Los nombres exactos cambian con la versión, pero los más importantes son *max\_checks* (pruebas a la vez por host) y *max\_hosts* (hosts a la vez); subirlos acelera, pero satura la red y las máquinas.

### 5.8 Opciones de una tarea

*Scans → Tasks → nueva*:

| Campo | Qué hace |
| --- | --- |
| Name / Comment | Identificación |
| Scan Targets | El objetivo creado antes |
| Alerts | Las alertas que se dispararán (ver 5.9) |
| Schedule | Programación; y *Once* para que se ejecute una sola vez |
| Add results to Assets | Si los hosts y sistemas operativos detectados se guardan en el inventario (*Resources → Hosts*) |
| Apply Overrides | Si se aplican las excepciones definidas (cambio de gravedad, falso positivo) al informe |
| Min QoD | Calidad mínima de detección para mostrar un resultado; por defecto **70 %**. Bajarlo muestra más resultados pero más falsos positivos |
| Alterable Task | Permite cambiar objetivo/configuración aunque ya tenga informes; **si no se marca, no se puede cambiar el objetivo después de ejecutar** |
| Auto Delete Reports | Borrar informes antiguos y conservar los *n* últimos (ahorra espacio) |
| Scanner | `OpenVAS Default` para escaneos de red; `CVE` para correlacionar CVEs de productos ya conocidos en el inventario |
| Scan Config | La configuración de la sección anterior |
| Network Source Interface | Interfaz de red desde la que sale el escaneo (si hay varias) |
| Order for target hosts | Orden de los hosts: *Sequential*, *Random* o *Reverse* |
| Maximum concurrently executed NVTs per host / Maximum concurrently scanned hosts | Paralelismo de la tarea, que anula el de la configuración |

### 5.9 Alertas: todas las opciones de configuración

*Configuration → Alerts → nueva*. Una alerta se define con **tres elementos**: un *evento* (cuándo se mira), una *condición* (si se cumple, se actuará) y un *método* (qué se hace).

**Evento (cuándo):**

| Evento | Significado |
| --- | --- |
| Task run status changed | Una tarea cambia de estado; elegimos a cuál: *Done* (terminada), *New*, *Requested*, *Running*, *Stop Requested*, *Stopped*. **Es el más útil: «la tarea ha terminado»** |
| New SecInfo arrives | Llegan nuevos datos de seguridad al feed (NVTs, CVEs, CPEs, avisos CERT…) |
| Updated SecInfo arrives | Se actualizan datos existentes |
| Ticket received / Assigned ticket changed / Owned ticket changed | Eventos del sistema de tickets integrado |

**Condición (si):**

| Condición | Significado |
| --- | --- |
| Always | Siempre |
| Severity at least | Si el informe tiene al menos una vulnerabilidad de gravedad ≥ X (por ejemplo 7,0 = alta) |
| Severity changed | Si la gravedad del informe aumenta, disminuye o cambia respecto al informe anterior |
| Filter count at least | Si hay al menos *N* resultados que cumplan un filtro |
| Filter count changed | Si el número de resultados filtrados cambia respecto al informe anterior |

**Método (qué hacer):**

| Método | Qué hace |
| --- | --- |
| **Email** | Envía un correo (ver opciones abajo) |
| HTTP Get | Hace una petición GET a una URL (útil para avisar a otro sistema o a un *webhook*) |
| Start Task | Lanza otra tarea (por ejemplo, un escaneo profundo tras detectar algo grave) |
| Send to host | Envía el informe a un host y puerto TCP |
| SCP | Copia el informe por SCP a un servidor |
| SMB | Guarda el informe en un recurso compartido de Windows |
| System Logger (syslog) | Escribe en el registro del sistema |
| SNMP | Envía un *trap* SNMP |
| Otros | Conectores a productos de terceros (Sourcefire, TippingPoint, verinice, vFire) |

**Opciones del método Email:**

| Opción | Qué hace |
| --- | --- |
| To Address | Destinatario(s) |
| From Address | Remitente (debe coincidir con la cuenta que autentica en el servidor SMTP, si no, muchos servidores lo rechazan) |
| Subject | Asunto; admite marcadores que se rellenan solos, por ejemplo con el nombre de la tarea |
| Email Encryption | Cifrar con una credencial S/MIME o PGP |
| Content | *Simple Notice* (solo aviso), *Include report* (informe dentro del cuerpo) o *Attach report* (informe como adjunto) |
| Report Format | Formato: PDF, HTML, texto, XML, CSV, etc. |
| Delta Report | Compara con el informe anterior de la misma tarea (nuevas y resueltas) |
| Maximum Included Results | Límite de resultados en el cuerpo del correo |
| Notice Attach Format | Formato del informe cuando se adjunta |
| Filter | Qué resultados incluir (por ejemplo, solo gravedad ≥ 7) |

#### 5.9.1 Las opciones de cada evento, una a una

Lo que sigue lo hemos comprobado en el formulario *New Alert* de nuestra versión de la web (GSA 26).

- **Task run status changed to:** desplegable con *Done*, *New*, *Requested*, *Running*, *Stop Requested* y *Stopped*. Nosotros usamos siempre **Done** («cuando termine»).
- **SecInfo:** se combinan dos desplegables:
  - qué ha pasado: *New* (nuevo) o *Updated* (actualizado);
  - de qué tipo es la información: *NVTs*, *CVEs*, *CPEs*, *CERT-Bund Advisories* o *DFN-CERT Advisories*.

  Ejemplo: «New + NVTs» avisa cuando el feed trae pruebas nuevas.
- **Ticket Received / Assigned Ticket Changed / Owned Ticket Changed:** son para el sistema de tickets interno, con el que asignamos la corrección de un fallo a una persona. Con estos eventos el formulario no deja escribir el asunto ni elegir informe, porque no hay escaneo.

#### 5.9.2 Las opciones de cada condición

| Condición | Qué se rellena en la web | Ejemplo |
| --- | --- | --- |
| Always | Nada | Avisar siempre que termine la tarea (nuestra alerta `informe-al-terminar`) |
| Severity at least | Un número con un decimal (por defecto 0.1) | `7.0`: avisar solo si hay algo alto o crítico (nuestra alerta `critica-inmediata`) |
| Severity Level changed | *changed* (cambia), *increased* (sube) o *decreased* (baja) respecto al escaneo anterior | *increased*: avisar si la red ha empeorado |
| Filter … matches at least *N* result(s) | Un filtro guardado y un número | Filtro «solo puerto 22» y 1: avisar si aparece cualquier fallo de SSH |
| Filter … matches at least *N* result(s) more than previous scan | Un filtro guardado y un número | Avisar si hay al menos 1 resultado **más** que la vez anterior |

Las dos últimas necesitan un **filtro guardado** antes. Lo creamos en la página de resultados escribiendo el filtro y pulsando el icono de guardar (*Save filter*), o en *Configuration → Filters*.

#### 5.9.3 Las opciones de cada método

| Método | Campos que pide el formulario |
| --- | --- |
| **Email** | *To Address*, *From Address*, *Subject*, *Email Encryption* (una credencial S/MIME o PGP del destinatario) y *Content* (ver 5.9.4) |
| **HTTP Get** | *HTTP Get URL*. Podemos usar `$n` (nombre de la tarea), `$e` (evento) y `$c` (condición) dentro de la URL para avisar a otro programa |
| **SCP** | *Credential* (usuario y contraseña o clave SSH), *Host*, *Port*, *Known Hosts* (la huella del servidor, para evitar suplantaciones), *Path* (por defecto `report.xml`) y *Report* (formato del informe) |
| **Send to host** | *Send to host*, *on port* y *Report Format*. Envía el informe tal cual por TCP, sin cifrar |
| **SMB** | *Credential*, *Share path* (por ejemplo `\\servidor\informes`), *File path*, *Report Format* y *Max Protocol* (*Default*, *NT1*, *SMB2*, *SMB3*). La propia web avisa de que SMB no permite comprobar la identidad del servidor, así que no evita del todo un ataque de intermediario |
| **SNMP** | *Community*, *Agent* (el equipo que recibe el *trap*) y *Message* |
| **System Logger** | Escribe el aviso en el registro del sistema (*syslog*) |
| **Start Task** | Elegimos qué tarea lanzar. Útil para encadenar: si el escaneo rápido encuentra algo grave, lanza uno profundo |
| **Sourcefire Connector** | *Defense Center IP*, *Defense Center Port* (por defecto 8307), *PKCS12 Credential* y *PKCS12 File* (envía los resultados al IDS de Cisco Firepower) |
| **TippingPoint SMS** | *Hostname / IP*, *Credential*, *SSL / TLS Certificate* y *Use workaround for default certificate* |
| **verinice.PRO Connector** | *verinice.PRO URL*, *Credential* y *verinice.PRO Report* (solo formatos `.vna`). Lleva los resultados a una herramienta de gestión de riesgos ISO 27001 |
| **Alemba vFire** | *Base URL*, *Credential*, *Session Type* (*Analyst* o *User*), *Alemba Client ID*, *Partition*, *Call Description*, *Call Template*, *Call Type*, *Impact* y *Urgency*. Abre una incidencia en esa herramienta de soporte |

Los cuatro últimos son conectores con productos comerciales. Los documentamos porque la práctica pide todas las opciones, pero en el laboratorio no los podemos probar.

#### 5.9.4 El contenido del correo y sus «comodines»

En *Content* elegimos una de tres opciones:

1. **Simple Notice:** solo un aviso corto, sin informe.
2. **Include report:** el informe va **dentro del texto** del correo. Solo deja elegir formatos de texto (TXT, por ejemplo). Es lo que usa nuestra alerta `critica-inmediata`.
3. **Attach report:** el informe va **adjunto** en el formato que elijamos (PDF, HTML, XML, CSV…). Es lo que usa nuestra alerta `informe-al-terminar`.

Cada opción tiene, además:
- un desplegable ***Report Config***, que sirve para ajustar algunos formatos;
- un **cuadro con el texto del mensaje**, que podemos cambiar.

El texto lleva **comodines** que Greenbone sustituye al enviar. El asunto por defecto es `[GVM] Task '$n': $e`. En nuestra alerta `informe-al-terminar` lo cambiamos por `[OpenVAS] Terminada la tarea $n`, y el correo llega como «[OpenVAS] Terminada la tarea P3 Appweb autenticado».

| Comodín | Se sustituye por |
| --- | --- |
| `$n` | Nombre de la tarea |
| `$N` | Nombre de la alerta |
| `$e` | Descripción del evento (por ejemplo, «Task status changed to 'Done'») |
| `$c` | Descripción de la condición que se cumplió |
| `$r` | Nombre del formato del informe |
| `$i` | El informe incluido (solo con *Include report*) |
| `$t` | Aviso de que el informe se ha recortado, si era demasiado largo |
| `$d`, `$T`, `$q`, `$S` | En las alertas de SecInfo: fecha de la última comprobación, cuántos elementos hay, si son nuevos o actualizados, y de qué tipo |
| `$$` | Un símbolo `$` normal |

#### 5.9.5 Opciones comunes a todas las alertas

- **Name** y **Comment:** nombre y descripción.
- **Report Result Filter:** qué resultados entran en el informe que se envía. Por ejemplo, un filtro con `min_qod=70` evita mandar resultados poco fiables.
- **Delta Report:**
  - *None:* informe normal.
  - *Previous completed report of the same task:* compara con el escaneo anterior y marca lo nuevo y lo que ha desaparecido. Es nuestra alerta `cambios-respecto-a-ayer`.
  - *Report with id:* compara con un informe concreto.
- **Opciones del informe** (en la versión 26 se llaman *Composer*): *Ignore Pagination* (enviar todos los resultados, no solo la primera página), *Include Notes* (incluir las notas) e *Include Overrides* (aplicar nuestras anulaciones, por ejemplo los falsos positivos).
- **Active:** si está en *No*, la alerta existe pero no se dispara. Sirve para desactivarla sin borrarla.
- **Probar la alerta:** en la lista *Configuration → Alerts*, el icono de **Test Alert** la dispara en ese momento con datos de ejemplo. Lo usamos para comprobar el correo (sección 6.6.5).
- **Asociarla a una tarea:** una alerta no hace nada hasta que la elegimos en el campo ***Alerts*** de la tarea. Una tarea puede tener varias alertas, y una alerta puede estar en varias tareas.

La configuración de la alerta no basta: **el servidor tiene que poder enviar correo realmente**. De eso nos ocupamos en la sección 6.6.

### 5.10 Programaciones (*Schedules*)

*Configuration → Schedules → nueva*. Definimos:

- **First Run:** fecha y hora del primer arranque.
- **Timezone:** debe ser la local.
- **Duration:** tiempo máximo; si se agota, la tarea se detiene. Sin duración, no hay límite.
- **Recurrence:** una sola vez, cada *n* horas/días/semanas/meses, o días concretos de la semana/mes (se guarda como un evento iCalendar). Algunas versiones aceptan una expresión de calendario tipo RRULE.

Una vez creada, la elegimos en el campo *Schedule* de la tarea. Si el escáner estaba apagado a la hora programada, la tarea se lanza cuando vuelva a funcionar, dentro de lo que permita la programación.

### 5.11 Notas y *overrides* (gestión de falsos positivos)

Tras analizar un informe, se pueden registrar decisiones **sin tocar el sistema escaneado**:

- **Nota:** comentario asociado a un resultado («confirmado: el servicio solo escucha en la red interna»).
- **Override:** cambia la gravedad de un resultado (por ejemplo, de 7,5 a 0 si es un falso positivo documentado) y puede aplicarse a un host, un puerto, una vulnerabilidad o una tarea concretos, y tener fecha de caducidad.

Solo se aplican a los informes si en la tarea está marcado *Apply Overrides*.

## 6. Pruebas de funcionamiento y uso real del escáner

En este capítulo usamos el escáner de verdad. **Todas las pruebas y configuraciones avanzadas (correo, escaneo autenticado, vigilancia continua y parcheo) las hacemos con la instalación Docker (método A)**, que es la que dejamos funcionando.

### Cómo están organizadas las pruebas

Cada prueba sigue siempre el mismo esquema, para que no haya que adivinar nada:

1. **Para qué sirve:** qué queremos demostrar.
2. **Qué necesitamos antes:** lo que tiene que estar hecho para empezar.
3. **Paso a paso en la web:** los clics exactos en la interfaz de Greenbone (GSA). Es la forma recomendada si es la primera vez.
4. **Lo mismo desde la terminal (opcional):** los comandos equivalentes, que son los que usamos nosotros para repetir pruebas rápidamente (se preparan en la sección 7).
5. **Cómo sabemos que ha funcionado.**
6. **Resultado en nuestro laboratorio:** lo que obtuvimos de verdad.

> **Antes de empezar cualquier prueba**, comprobamos tres cosas: que los contenedores están en marcha (sección 3.5), que el feed está al día (*Administration → Feed Status*, sección 3.6) y que podemos entrar en `https://127.0.0.1` (sección 3.8). Si el feed no ha terminado de cargar, los escaneos salen vacíos sin avisar.

> **Cuánto tarda cada escaneo.** Con la configuración «Full and fast», un equipo tarda entre 20 y 60 minutos y una red pequeña, una o dos horas. Podemos lanzar varias pruebas a la vez y seguir con otra cosa: si configuramos el correo (prueba 5), Greenbone nos avisará al terminar.

### 6.1 Preparar el laboratorio de pruebas

#### 6.1.1 Qué máquinas vamos a escanear

**Regla número uno: solo escaneamos máquinas que son nuestras.** Escanear equipos ajenos sin permiso es ilegal, y un escaneo puede llegar a colgar servicios. Por eso usamos máquinas virtuales en una red virtual aislada, y **nunca** la red de casa, del aula o del trabajo.

Nuestro laboratorio está en la red virtual `default` de libvirt (192.168.122.0/24):

| Máquina virtual | IP | Para qué la usamos |
| --- | --- | --- |
| `Metasploitable3-ubuntu` | 192.168.122.52 | Máquina **vulnerable a propósito**, creada para practicar. Prueba 1 |
| `debian13` | 192.168.122.217 | Debian 13 sencilla. Forma parte de la red de la prueba 2 |
| `Appweb` | 192.168.122.245 | Servidor web Debian 13 (de otra práctica). Pruebas 3 y 6 |
| Anfitrión (nuestro portátil) | 192.168.122.1 | Ejecuta Greenbone. Lo **excluimos** de los escaneos de red |

Si otra persona repite la práctica, puede usar cualquier combinación de máquinas virtuales propias. Estas son otras opciones que valoramos:

| N.º | Objetivo | Qué demuestra |
| --- | --- | --- |
| 1 | El propio equipo anfitrión (Debian 13) | Escaneo de un host y de lo que expone a la red |
| 2 | Una VM Debian 13 de laboratorio con servicios «mal configurados a propósito» (nginx, SSH, PostgreSQL, FTP) | Hallazgos reales con parche demostrable |
| 3 | Las VMs de libvirt/OpenTofu que ya usamos en otras prácticas (por ejemplo servidor web y cliente) | Escaneo de red completa y monitorización continua |
| 4 | Metasploitable 2 (VM intencionadamente vulnerable) | Gran cantidad de vulnerabilidades críticas; coordinar con la parte R3 |
| 5 | Un cliente Windows (si el grupo dispone de la VM del escenario) | Escaneo autenticado por SMB |
| 6 | El servidor de Minecraft de la parte R4 | Detección de Log4Shell (CVE-2021-44228) |

**Regla de oro:** todas estas máquinas viven en una red virtual aislada (libvirt «default» 192.168.122.0/24 u otra red solo de laboratorio). **Metasploitable jamás se conecta a una red con salida a internet o al aula.**

#### 6.1.2 Encender las máquinas y averiguar sus IPs

Encendemos las VMs desde la terminal del anfitrión:

```
virsh -c qemu:///system list --all
virsh -c qemu:///system start Metasploitable3-ubuntu
virsh -c qemu:///system start debian13
virsh -c qemu:///system start Appweb
```

- `virsh list --all` muestra todas las máquinas virtuales, encendidas o apagadas.
- `virsh start <nombre>` enciende una. Tardan uno o dos minutos en arrancar del todo; Metasploitable3 es la más lenta.

Para saber qué IP tiene cada una, preguntamos a la red virtual y hacemos un barrido rápido con Nmap:

```
virsh -c qemu:///system net-dhcp-leases default
nmap -sn 192.168.122.0/24
```

- `net-dhcp-leases default` lista las IPs que la red `default` ha repartido. Las máquinas con IP fija (como nuestra Metasploitable3) no aparecen aquí.
- `nmap -sn` comprueba qué direcciones responden, sin mirar puertos. En nuestro caso respondieron cuatro: `.1` (el anfitrión), `.52`, `.217` y `.245`.

> **Memoria RAM.** Greenbone usa unos 4 GB. Cada VM necesita la suya (en nuestro caso 2 GB Metasploitable3, 2 GB debian13 y 4 GB Appweb). Lo comprobamos con `free -h` antes de encenderlas y no arrancamos más de las que caben.

#### 6.1.3 Comprobar que el escáner llega a las máquinas

En el método A el escáner vive **dentro de un contenedor**, con su propia red interna. Consecuencias que debemos entender:

- **`127.0.0.1` dentro del contenedor es el contenedor, no nuestro equipo.** Para escanear el anfitrión usamos su IP real (`ip -br a`), no 127.0.0.1. Los servicios que solo escuchan en `127.0.0.1` no se verán (y eso, de hecho, es una buena noticia de seguridad).
- El tráfico del contenedor sale por la red de Docker con traducción de direcciones (NAT). Funciona para ICMP y TCP; **las pruebas ARP no funcionan** (ARP solo vale dentro de la misma red local). En los objetivos usamos *Alive Test = ICMP Ping* o *Consider Alive*.
- El compose oficial concede al contenedor `ospd-openvas` las capacidades `NET_ADMIN` y `NET_RAW` para poder crear paquetes en bruto; sin ellas el escaneo no funcionaría.
- **Docker y libvirt:** Docker establece una política de reenvío `DROP` que puede cortar el tráfico de las redes virtuales de libvirt (las VMs pierden conectividad tras instalar Docker). Comprobamos con `sudo iptables -S FORWARD | head`. Si ocurre, permitimos explícitamente el tráfico del puente de libvirt (ajustar `virbr0` al nombre real que muestra `ip -br link`):

```bash
sudo iptables -I DOCKER-USER -i virbr0 -j ACCEPT
sudo iptables -I DOCKER-USER -o virbr0 -j ACCEPT
```

- `DOCKER-USER` es la cadena que Docker reserva para reglas del administrador; `-i` es la interfaz de entrada, `-o` la de salida, `-I` inserta al principio. Estas reglas **no persisten** tras reiniciar (habría que guardarlas con `iptables-persistent` o similar).

Comprobación de conectividad desde el contenedor (antes de lanzar ningún escaneo):

```sh
sudo docker compose -f $DOWNLOAD_DIR/compose.yaml -p greenbone-community-edition exec ospd-openvas ping -c 2 <IP> 
```

- Si hay respuesta, la ruta contenedor → VM funciona. Si `ping` no existe en la imagen, usamos otra herramienta o simplemente lanzamos el escaneo y miramos si el host se detecta.

**Comprobación en nuestro equipo.** La imagen de `ospd-openvas` no incluye `ping`, así que probamos a abrir una conexión TCP al puerto 22 de una VM con la propia shell `bash` del contenedor:

```
docker exec greenbone-community-edition-ospd-openvas-1 bash -c 'timeout 3 bash -c "</dev/tcp/192.168.122.217/22" && echo "TCP 22 abierto: el contenedor llega a la VM" || echo "no llega"'
```

- `docker exec <contenedor> <orden>` ejecuta una orden dentro de un contenedor que ya está en marcha.
- `/dev/tcp/IP/puerto` es una función de `bash` que abre una conexión TCP. Si se abre, el contenedor llega a la VM.
- `timeout 3` corta la prueba a los 3 segundos si no hay respuesta.

Resultado: `TCP 22 abierto: el contenedor llega a la VM`. En nuestro equipo **no hizo falta** añadir las reglas `DOCKER-USER`.

#### 6.1.4 Cómo entrar en la web para hacer las pruebas

1. Abrimos el navegador en `https://127.0.0.1`. Aceptamos el aviso del certificado (es nuestro propio equipo).
2. Iniciamos sesión con `admin` y la contraseña de la sección 3.7.
3. El menú está arriba: **Dashboards** (resumen), **Scans** (tareas e informes), **Assets** (equipos encontrados), **Resilience**, **SecInfo** (base de datos de vulnerabilidades), **Configuration** (objetivos, credenciales, alertas, programaciones) y **Administration** (usuarios y feed).
4. Los botones de crear están arriba a la izquierda de cada lista, con un icono de estrella o de «+» (*New ...*).

> En nuestro caso, muchas tareas las creamos desde la terminal con el usuario `automatizacion` (sección 7). Para verlas en la web, iniciamos sesión con ese usuario; su contraseña está en `~/.config/gvm-tools.conf`.

#### 6.1.5 Opcional: preparar una VM con fallos puestos a propósito

Si no tenemos una máquina vulnerable, podemos fabricarla: una Debian limpia con servicios mal configurados. Nosotros usamos Metasploitable3, así que no fue necesario, pero lo dejamos explicado:

Creamos una VM Debian 13 limpia (con nuestro flujo habitual de libvirt/cloud-init) y dentro instalamos varios servicios:

```sh
sudo apt update
sudo apt install -y nginx openssh-server postgresql vsftpd snmpd
```

- `nginx`: servidor web. `openssh-server`: acceso remoto. `postgresql`: base de datos. `vsftpd`: servidor FTP. `snmpd`: agente SNMP. Cada uno es un servicio muy real que cualquier empresa usa y que suele estar mal configurado.

Introducimos configuraciones **inseguras a propósito** (las corregiremos en 6.8, así que apuntamos qué cambiamos):

```sh
# 1) FTP anónimo habilitado
sudo sed -i 's/^anonymous_enable=.*/anonymous_enable=YES/' /etc/vsftpd.conf
sudo systemctl restart vsftpd

# 2) SSH con contraseña y root permitido
echo -e 'PermitRootLogin yes\nPasswordAuthentication yes' | sudo tee /etc/ssh/sshd_config.d/00-lab-inseguro.conf
sudo systemctl reload ssh

# 3) PostgreSQL accesible desde la red con contraseña débil
sudo -u postgres psql -c "ALTER USER postgres WITH PASSWORD 'postgres';"
echo "listen_addresses = '*'" | sudo tee /etc/postgresql/17/main/conf.d/00-lab.conf
echo 'host all all 0.0.0.0/0 md5' | sudo tee -a /etc/postgresql/17/main/pg_hba.conf
sudo systemctl restart postgresql

# 4) SNMP con comunidad por defecto 'public' abierta a toda la red
sudo sed -i 's/^agentaddress.*/agentaddress udp:161/' /etc/snmp/snmpd.conf
sudo systemctl restart snmpd

# 5) Una página web con formulario de login por HTTP (sin cifrar)
echo '<form method="post" action="/login">Usuario <input name="user"> Clave <input type="password" name="pass"><input type="submit"></form>' | sudo tee /var/www/html/index.html
```

Qué hace cada bloque:

1. `sed -i 's/viejo/nuevo/' fichero` sustituye texto dentro del fichero (`-i` = en el sitio). Habilita que cualquiera entre al FTP sin usuario.
2. Los ficheros en `sshd_config.d/` se leen antes de la configuración principal; permitimos acceso de root y por contraseña (mala práctica: abre la puerta a ataques de fuerza bruta). `echo -e` interpreta `\n` como salto de línea.
3. Ponemos a PostgreSQL una contraseña trivial, lo hacemos escuchar en todas las interfaces (`listen_addresses = '*'`) y añadimos a `pg_hba.conf` (reglas de quién puede conectarse) una línea que acepta a cualquier IP. Ajustar `17` si la versión es distinta.
4. `snmpd` por defecto solo escucha en local; con `agentaddress udp:161` escucha en toda la red. El escáner prueba comunidades como `public`. **Es posible que la comunidad `public` no esté definida en la configuración por defecto de Debian**; si el escáner no lo detecta, se añade `rocommunity public` a `/etc/snmp/snmpd.conf` y se reinicia.
5. Un formulario con campo de contraseña servido por HTTP sin TLS es un hallazgo clásico (credenciales en texto claro).

Apuntamos la IP de la VM con `ip -br a` (lo usaremos como `<IP_LAB>`).

#### 6.1.6 Opcional: Metasploitable 2

La descargamos de la página de Rapid7 (es un fichero `.zip` con un disco `.vmdk`). Para libvirt:

```sh
unzip metasploitable-linux-2.0.0.zip -d /mnt/midisco/greenbone/metasploitable
qemu-img convert -f vmdk -O qcow2 /mnt/midisco/greenbone/metasploitable/Metasploitable2-Linux/Metasploitable.vmdk /mnt/midisco/greenbone/metasploitable/metasploitable2.qcow2
sudo virt-install --name metasploitable2 --memory 512 --vcpus 1 --disk /mnt/midisco/greenbone/metasploitable/metasploitable2.qcow2 --import --os-variant ubuntu8.04 --network network=aislada --graphics none --noautoconsole
```

- `unzip -d` extrae en la carpeta indicada. `qemu-img convert -f vmdk -O qcow2` convierte el formato del disco (de VMware a QEMU).
- `virt-install --import` crea la VM usando ese disco ya existente (sin instalar nada). `--network network=aislada` debe ser **una red virtual sin salida a internet** (un `forward mode` vacío en libvirt) y distinta de la que usan las demás VMs, salvo que queramos escanearla desde ahí. `--os-variant ubuntu8.04` es la distribución más cercana (`osinfo-query os` lista las disponibles).
- Las credenciales de Metasploitable son `msfadmin` / `msfadmin`: precisamente una vulnerabilidad que el escáner detecta.

### 6.2 Prueba 1: escaneo de un equipo

**Para qué sirve:** ver qué descubre el escáner sobre **una sola máquina** mirando desde fuera, como lo haría un atacante en la misma red, sin usuario ni contraseña.

**Qué necesitamos antes:** la VM `Metasploitable3-ubuntu` encendida (IP 192.168.122.52) y la comprobación de 6.1.3 hecha.

**Paso a paso en la web:**

1. **Crear el objetivo** (qué vamos a escanear). Menú *Configuration → Targets* → botón *New Target*. Rellenamos:
   - *Name*: `MS3 - host individual`
   - *Hosts*: *Manual* → `192.168.122.52`
   - *Port List*: `All IANA assigned TCP` (todos los puertos TCP con servicio conocido)
   - *Alive Test*: `ICMP Ping` (si la máquina no responde al ping, usar `Consider Alive`)
   - Pulsamos *Save*.

![[Pasted image 20261018162806.png]]

2. **Crear la tarea** (qué hacer con ese objetivo). Menú *Scans → Tasks* → *New Task*:
   - *Name*: `P1 Host Metasploitable3`
   - *Scan Targets*: `MS3 - host individual`
   - *Scanner*: `OpenVAS Default`
   - *Scan Config*: `Full and fast` (el análisis completo recomendado)
   - Si ya configuramos el correo (prueba 5), en *Alerts* añadimos `informe-al-terminar`.
   - *Save*.
3. **Lanzarla:** en la lista de tareas, botón ▶ (*Start*) de su fila. El estado pasa por *Requested → Queued → Running* con un porcentaje.
4. **Esperar.** Con una VM tarda de 20 a 60 minutos. Podemos seguir lo que hace el escáner en directo con:

   ```
   sudo docker compose -f /root/greenbone-community-container/compose.yaml -p greenbone-community-edition logs -f ospd-openvas
   ```

5. **Abrir el informe:** cuando el estado sea *Done*, clic en la fecha de la columna *Last Report* → pestaña *Results*, ordenada por *Severity* de mayor a menor.

**Lo mismo desde la terminal (opcional):** con el script `gmp.sh` de la sección 7.1. Cada orden devuelve un identificador (`id="..."`) que usamos en la siguiente:

```
/mnt/midisco/greenbone/scripts/gmp.sh '<create_target><name>MS3 - host individual</name><hosts>192.168.122.52</hosts><port_list id="33d0cd82-57c6-11e1-8ed1-406186ea4fc5"/><alive_tests>ICMP Ping</alive_tests></create_target>'
/mnt/midisco/greenbone/scripts/gmp.sh '<create_task><name>P1 Host Metasploitable3</name><config id="daba56c8-73ec-11df-a475-002264764cea"/><target id="ID_DEL_OBJETIVO"/><scanner id="08b69003-5fc2-4037-a479-93b440211c73"/></create_task>'
/mnt/midisco/greenbone/scripts/gmp.sh '<start_task task_id="ID_DE_LA_TAREA"/>'
/mnt/midisco/greenbone/scripts/esperar_tarea.sh ID_DE_LA_TAREA
```

- `create_target` crea el objetivo; `33d0cd82-...` es la lista de puertos *All IANA assigned TCP*.
- `create_task` crea la tarea; `daba56c8-...` es *Full and fast* y `08b69003-...` es el escáner *OpenVAS Default* (tabla de 7.3).
- `start_task` la lanza y `esperar_tarea.sh` (sección 7.5) nos avisa cuando termina.

**Cómo sabemos que ha funcionado:** la tarea acaba en *Done* (no en *Interrupted*), el informe tiene resultados de varias gravedades y la pestaña *Error Messages* del informe está vacía o casi vacía.

**Qué cabe esperar en una máquina con fallos** (orientativo, según lo que se configure en 6.1.5):

| Servicio | Hallazgo típico | Gravedad orientativa |
| --- | --- | --- |
| PostgreSQL | Credenciales por defecto aceptadas (`postgres` / `postgres`) | Alta o crítica |
| FTP | Acceso anónimo permitido | Media |
| SSH | Autenticación por contraseña y/o algoritmos débiles aceptados | Baja o media |
| HTTP | Transmisión de credenciales en texto claro (formulario sin TLS) | Media |
| TCP | Marcas de tiempo TCP (*TCP timestamps*) reveladoras del tiempo de actividad | Baja (2,6) |
| SNMP | Comunidad predeterminada accesible (si se configuró `public`) | Alta |
| General | Detección del sistema operativo y de productos (informativos, gravedad 0) | Log |

Una ejecución real casi siempre enseña algo inesperado; lo documentamos todo, también lo que no esperábamos.

> **Resultado en nuestro laboratorio (tarea `P1 Host Metasploitable3`, 192.168.122.52, 1 de noviembre de 2026).**
>
> Metasploitable3 es una máquina **vulnerable a propósito**, así que el informe es muy largo. OpenVAS encontró estos servicios abiertos: FTP (21), SSH (22), HTTP con Apache (80), Samba (445), CUPS (631), MySQL (3306), una aplicación web en el 3500, UnrealIRCd (6697) y Jetty (8080).
>
> | Gravedad | Número de resultados |
> | --- | --- |
> | Crítica (9,0 – 10) | 21 |
> | Alta (7,0 – 8,9) | 54 |
> | Media (4,0 – 6,9) | 80 |
> | Baja (0,1 – 3,9) | 7 |
> | Log (informativos) | 54 |
>
> Algunos de los más graves:
>
> | Gravedad | Hallazgo | Puerto | QoD |
> | --- | --- | --- | --- |
> | 10,0 | Samba End of Life (versión sin soporte) | 445/tcp | 30 % |
> | 10,0 | Jetty End of Life | 8080/tcp | 30 % |
> | 9,8 | Samba RCE Vulnerability (*SambaCry*): ejecución remota de código | 445/tcp | 30 % |
> | 9,8 | ProFTPD ≤ 1.3.6 *Arbitrary File Copy* (copia de ficheros sin iniciar sesión) | 21/tcp | 30 % |
> | 9,8 | OpenSSH < 9.3p2 *RCE* | 22/tcp | 30 % |
> | 9,8 | Apache HTTP Server, varias vulnerabilidades (2017 – 2024) | 80/tcp | 30 % |
>
> **Lo que aprendimos de esta prueba:**
>
> - **Casi todos los críticos tienen un QoD del 30 %.** OpenVAS los deduce por el número de versión que anuncia cada servicio. Con el filtro por defecto de la web (`min_qod=70`), **no aparece ninguno de los críticos**: solo se ven 6 resultados medios y 1 alto (*SSL/TLS: Report Vulnerable Cipher Suites for HTTPS*, en CUPS). Para ver el informe completo escribimos en el filtro `min_qod=0`. En una máquina tan antigua sí nos los creemos: sus versiones de Samba, Apache, ProFTPD y OpenSSH son realmente de 2014 a 2016.
> - **El escaneo fue muy lento.** La pestaña *Error Messages* muestra 155 avisos `NVT timed out after 320 seconds`: las pruebas de aplicaciones web se quedan esperando a las aplicaciones de los puertos 80, 3500 y 8080 hasta agotar su tiempo. No es un fallo de la instalación, sino el comportamiento normal con un servidor web lento y lleno de aplicaciones. Por eso, en una red real, escanearíamos estos equipos en horario sin carga.
> - **Detuvimos la tarea al 82 %** (*Stopped*), tras más de 5 horas. Solo quedaban las pruebas web lentas y los resultados ya no cambiaban: el escaneo completo que habíamos hecho antes de la misma máquina da prácticamente lo mismo (ver abajo). La tarea de red P2b la detuvimos al 94 % por el mismo motivo; esa tarea se repite cada noche con la programación de la prueba 4.
> - **No la parcheamos.** Metasploitable3 está hecha para practicar ataques (la usamos en la parte R3) y sus programas ya no tienen soporte. En un caso real, la decisión correcta sería **reemplazarla** por un sistema actual, no parchear servicio a servicio.
>
> Como referencia, nuestro escaneo completo de la misma máquina desde la web, con el usuario `admin` y la lista *All IANA assigned TCP* (tarea `escaneo-metasploitable3-ubuntu`, 27 de octubre), dio **23 críticas, 50 altas, 92 medias y 6 bajas**. Es prácticamente el mismo resultado.
>
> Informe completo: `/mnt/midisco/greenbone/informes/P1-Metasploitable3.pdf`.

##### Escanear el propio anfitrión

Creamos otro objetivo con la IP real del equipo (método A) o `127.0.0.1` (método B, que corre en el mismo sistema), excluimos las IPs que no queramos tocar y usamos *Full and fast*. Es un escaneo muy instructivo: veremos qué expone nuestro portátil (por ejemplo, la interfaz web de Greenbone si se abrió a toda la red, SSH, servicios de libvirt, etc.).

Complemento con herramientas locales para contrastar el resultado:

```sh
sudo ss -tulpn
nmap -sV -p- 
```

- `ss -tulpn` lista los puertos en escucha del propio equipo: `-t` TCP, `-u` UDP, `-l` solo los que esperan conexiones, `-p` el proceso, `-n` sin resolver nombres.
- `nmap -sV -p- <IP>` explora **todos** los puertos (`-p-`) e intenta identificar la versión de cada servicio (`-sV`). Debe coincidir con los puertos que detectó OpenVAS; si no, algo falla (cortafuegos, *Alive Test*, lista de puertos).

### 6.3 Prueba 2: escaneo de una red completa

**Para qué sirve:** descubrir **qué equipos hay** en una red (inventario) y después buscar vulnerabilidades en todos a la vez. Es lo que haría una empresa cada semana.

**Qué necesitamos antes:** varias VMs encendidas en la red 192.168.122.0/24 (en nuestro caso, las tres de 6.1.1).

**Paso a paso en la web:**

1. **Objetivo de red.** *Configuration → Targets → New Target*:
   - *Name*: `Red laboratorio 192.168.122.0/24`
   - *Hosts*: `192.168.122.0/24` (las 254 direcciones de la red)
   - *Exclude Hosts*: `192.168.122.1` (nuestro propio equipo, que hace de puerta de enlace)
   - *Port List*: `All IANA assigned TCP` o, mejor, nuestra propia lista `Puertos laboratorio` (ver recuadro siguiente); *Alive Test*: `ICMP Ping`.

   > **Elegir nosotros los puertos.** Revisar los ~5.900 puertos de *All IANA assigned TCP* en toda una red es lento. Si sabemos qué servicios nos interesan, creamos una lista propia: *Configuration → Port Lists → New Port List*, *Name* `Puertos laboratorio`, *Port Ranges* → *Manual*:
   >
   > ```
   > T:21-23,25,53,80,110,139,143,443,445,3306,3389,5432,6697,8080,8443,U:53,161
   > ```
   >
   > `T:` son puertos TCP y `U:` puertos UDP; se separan por comas y se admiten rangos con guion (`21-23` = FTP, SSH y Telnet). Hemos incluido los servicios más habituales: correo (25, 110, 143), DNS (53), web (80, 443, 8080, 8443), compartición de Windows (139, 445), bases de datos (3306 MySQL, 5432 PostgreSQL), escritorio remoto (3389), IRC (6697, el servicio vulnerable de Metasploitable) y SNMP (UDP 161).
2. **Primera tarea, descubrimiento (rápida, un par de minutos).** *Scans → Tasks → New Task*: nombre `P2a Descubrimiento red`, el objetivo anterior, *Scan Config* = `Host Discovery`, y *Add results to Assets* = *Yes*. Ejecutar.
3. **Ver el inventario:** *Assets → Hosts* lista los equipos encontrados.
4. **Comprobar con Nmap** que la lista coincide (orden de abajo).
5. **Segunda tarea, vulnerabilidades.** Nueva tarea `P2b Vulnerabilidades red`, mismo objetivo, *Scan Config* = `Full and fast`, *Order for target hosts* = `Random` y *Maximum concurrently scanned hosts* = `5`. Ejecutar.
6. **Leer el informe por equipos:** en el informe, pestaña *Hosts*: muestra la gravedad máxima de cada máquina y nos dice cuál arreglar primero.

```bash
$ nmap -sn 192.168.122.0/24
```

- `-sn` es «no escanear puertos»: solo hace descubrimiento de hosts (equivalente a *Host Discovery*). Los equipos que lista Nmap deben aparecer también en GSA.

El informe de red agrupa los resultados por host (*Hosts* → gravedad máxima de cada uno), lo que permite priorizar: qué máquina arreglar primero.

> **Impacto:** un *Full and fast* sobre una red de 254 direcciones con varias VMs puede tardar horas y generar mucho tráfico. Para el vídeo de la práctica es mejor escanear un rango reducido (por ejemplo `192.168.122.10-20`).

**Lo mismo desde la terminal (opcional):**

```
/mnt/midisco/greenbone/scripts/gmp.sh '<create_target><name>Red laboratorio 192.168.122.0/24</name><hosts>192.168.122.0/24</hosts><exclude_hosts>192.168.122.1</exclude_hosts><port_list id="33d0cd82-57c6-11e1-8ed1-406186ea4fc5"/><alive_tests>ICMP Ping</alive_tests></create_target>'
/mnt/midisco/greenbone/scripts/gmp.sh '<create_task><name>P2a Descubrimiento red</name><config id="2d3f051c-55ba-11e3-bf43-406186ea4fc5"/><target id="ID_DEL_OBJETIVO"/><scanner id="08b69003-5fc2-4037-a479-93b440211c73"/><preferences><preference><scanner_name>in_assets</scanner_name><value>yes</value></preference></preferences></create_task>'
/mnt/midisco/greenbone/scripts/gmp.sh '<create_task><name>P2b Vulnerabilidades red</name><config id="daba56c8-73ec-11df-a475-002264764cea"/><target id="ID_DEL_OBJETIVO"/><scanner id="08b69003-5fc2-4037-a479-93b440211c73"/><hosts_ordering>random</hosts_ordering><preferences><preference><scanner_name>max_hosts</scanner_name><value>5</value></preference><preference><scanner_name>in_assets</scanner_name><value>yes</value></preference></preferences></create_task>'
```

- `exclude_hosts` deja fuera nuestro equipo.
- La lista de puertos propia se crea con `<create_port_list><name>Puertos laboratorio</name><port_range>T:21-23,25,53,80,110,139,143,443,445,3306,3389,5432,6697,8080,8443,U:53,161</port_range></create_port_list>` y su identificador se usa en `port_list id="..."` en lugar del de *All IANA assigned TCP*.
- `2d3f051c-...` es la configuración *Host Discovery*; `in_assets` = *Add results to Assets*.
- `hosts_ordering` y `max_hosts` son el orden aleatorio y el máximo de 5 equipos a la vez.
- Después, `start_task` y `esperar_tarea.sh` igual que en la prueba 1.

**Cómo sabemos que ha funcionado:** el descubrimiento encuentra los mismos equipos que Nmap (sin contar el excluido) y el informe de vulnerabilidades tiene una fila por equipo en la pestaña *Hosts*.

> **Resultado en nuestro laboratorio (tareas `P2a Descubrimiento red` y `P2b Vulnerabilidades red`, 192.168.122.0/24 sin la .1, 1 de noviembre de 2026).**
>
> **Descubrimiento (P2a).** OpenVAS encontró **3 equipos encendidos**: .52 (Metasploitable3), .217 (debian13) y .245 (Appweb). Es lo mismo que `nmap -sn`, sin contar el anfitrión .1, que excluimos a propósito.
>
> **Vulnerabilidades (P2b)**, con nuestra lista `Puertos laboratorio`:
>
> | Equipo | Crítica | Alta | Media | Baja | Log |
> | --- | --- | --- | --- | --- | --- |
> | 192.168.122.52 – Metasploitable3 | 21 | 54 | 80 | 7 | 54 |
> | 192.168.122.245 – Appweb | 0 | 0 | 3 | 4 | 19 |
> | 192.168.122.217 – debian13 | 0 | 0 | 2 | 4 | 17 |
>
> **Lo que nos dice la pestaña *Hosts*:** la prioridad está clarísima. Metasploitable3 concentra casi todo el riesgo. Las dos Debian 13 solo tienen avisos medios y bajos de configuración de SSH y TCP: Terrapin, CVE-2016-20012, MAC débiles, TCP Timestamps e ICMP Timestamp. Appweb tiene además el aviso de WordPress `wp-cron.php`.
>
> **Comparación: Appweb sin credenciales frente a Appweb con credenciales (prueba 3).**
>
> | | Sin credenciales (P2b) | Con credenciales (P3) |
> | --- | --- | --- |
> | Críticas / altas | 0 / 0 | 1 / 3 |
> | Medias | 3 | 8 |
> | Bajas | 4 | 7 |
> | Qué ve | Solo lo que anuncian los servicios por la red: SSH, HTTP, TCP e ICMP | También los **paquetes instalados**: sudo, nginx, la versión de OpenSSH, el microcódigo de Intel… |
>
> El escaneo autenticado encontró **12 resultados más**: los de sudo, nginx y los avisos de Intel. Algunos de ellos resultaron ser **falsos positivos** (lo comprobamos en la prueba 3 y en el apartado 6.9). Conclusión: el escaneo **sin credenciales** sirve para ver lo que ve un atacante desde fuera; el **autenticado** es imprescindible para saber qué software vulnerable tenemos dentro, pero exige revisar cada resultado.
>
> Informe completo: `/mnt/midisco/greenbone/informes/P2b-red-laboratorio.pdf`.

### 6.4 Prueba 3: escaneo autenticado (con usuario y clave)

**Para qué sirve:** desde fuera, el escáner solo ve los servicios de red y tiene que **adivinar** las versiones. Si le damos un usuario para entrar en la máquina, puede **leer la lista exacta de programas instalados** y compararla con los avisos de seguridad. Encuentra mucho más y se equivoca mucho menos.

**Qué necesitamos antes:** una máquina Linux con SSH en la que podamos usar `sudo` (en nuestro caso `Appweb`, 192.168.122.245, a la que ya entramos con el alias `app` de `~/.ssh/config`).

**Idea de seguridad:** no le damos al escáner nuestra cuenta ni nuestra clave. Creamos un **usuario exclusivo**, `escaneo`, sin contraseña, que **solo** puede entrar con una **clave exclusiva**. Si algún día se filtra, basta con borrar ese usuario.

**Paso 1. Crear la clave en el anfitrión y el usuario en la VM.** La forma general (en dos máquinas) es esta:

**En la máquina que ejecuta el escáner** (anfitrión):

```bash
$ mkdir -p /mnt/midisco/greenbone/claves && chmod 700 /mnt/midisco/greenbone/claves
$ ssh-keygen -t ed25519 -f /mnt/midisco/greenbone/claves/escaneo_ed25519 -C "openvas-escaneo" -N ""
```

- `chmod 700` deja la carpeta accesible solo al propietario.
- `ssh-keygen -t ed25519` genera un par de claves con el algoritmo Ed25519 (moderno y seguro); `-f` indica el fichero de salida (se crea también `.pub`); `-C` es un comentario; `-N ""` deja la clave sin frase de paso, necesario para que el escáner pueda usarla sin intervención. **Por eso la clave solo sirve para este usuario limitado.**

**En la VM objetivo:**

```bash
$ sudo adduser --disabled-password --gecos "" escaneo
$ sudo mkdir -p /home/escaneo/.ssh && sudo chmod 700 /home/escaneo/.ssh
$ sudo tee /home/escaneo/.ssh/authorized_keys < escaneo_ed25519.pub
$ sudo chmod 600 /home/escaneo/.ssh/authorized_keys && sudo chown -R escaneo:escaneo /home/escaneo/.ssh
```

- `adduser --disabled-password --gecos ""` crea el usuario `escaneo` sin contraseña (solo entrará con clave) y sin pedir datos personales.
- `authorized_keys` contiene las claves públicas que pueden entrar como ese usuario. Pegamos ahí el contenido del fichero `.pub` (lo copiamos de una máquina a otra con `scp` o a mano).
- Los permisos 700/600 son obligatorios: SSH rechaza claves con permisos abiertos.

Nosotros lo hicimos todo con **una sola orden** desde el anfitrión, usando el acceso SSH que ya teníamos a la VM (alias `app`):

```
mkdir -p /mnt/midisco/greenbone/claves && chmod 700 /mnt/midisco/greenbone/claves && ssh-keygen -q -t ed25519 -f /mnt/midisco/greenbone/claves/escaneo_ed25519 -C "openvas-escaneo" -N "" && ssh app "sudo adduser --disabled-password --gecos '' escaneo && sudo mkdir -p /home/escaneo/.ssh && sudo chmod 700 /home/escaneo/.ssh && echo '$(cat /mnt/midisco/greenbone/claves/escaneo_ed25519.pub)' | sudo tee /home/escaneo/.ssh/authorized_keys && sudo chmod 600 /home/escaneo/.ssh/authorized_keys && sudo chown -R escaneo:escaneo /home/escaneo/.ssh"
```

- Los `&&` encadenan las órdenes: cada una solo se ejecuta si la anterior ha ido bien.
- `ssh app "..."` ejecuta en la VM todo lo que va entre comillas.
- `$(cat ...pub)` se sustituye **en el anfitrión** por el contenido de la clave pública antes de enviarlo, así no hay que copiarla a mano.

**Paso 2. Comprobar a mano que la clave funciona** (si esto falla, el escáner también fallará):

```bash
$ ssh -i /mnt/midisco/greenbone/claves/escaneo_ed25519 escaneo@<IP_LAB> 'dpkg -l | head -n 5'
```

- Ejecuta un comando remoto: `dpkg -l` lista los paquetes instalados, que es justo lo que el escáner leerá para las comprobaciones Notus.

En nuestro caso:

```
ssh -i /mnt/midisco/greenbone/claves/escaneo_ed25519 escaneo@192.168.122.245 'whoami; dpkg -l | head -n 5'
```

Respuesta: `escaneo` y la cabecera de la lista de paquetes. Funciona.

**Paso 3. Paso a paso en la web:**

1. *Configuration → Credentials → New Credential*:
   - *Name*: `ssh-escaneo`
   - *Type*: `Username + SSH Key`
   - *Username*: `escaneo`
   - *Private Key*: subimos el fichero `/mnt/midisco/greenbone/claves/escaneo_ed25519` (el que **no** acaba en `.pub`).
   - *Save*.
2. *Configuration → Targets → New Target*: *Name* `Appweb con credenciales`; *Hosts* `192.168.122.245`; *Port List* `All IANA assigned TCP`; en *Credentials for authenticated checks*, *SSH* = `ssh-escaneo` en el puerto `22`. *Save*.
3. *Scans → Tasks → New Task*: *Name* `P3 Appweb autenticado`, el objetivo anterior, `Full and fast`, y las alertas que queramos. *Save* y ▶.

**Lo mismo desde la terminal (opcional).** La credencial lleva la clave privada. Para que no aparezca en la lista de procesos del sistema, escribimos la orden en un fichero temporal protegido, se lo pasamos al contenedor y lo borramos:

```
umask 077
python3 -c 'import html; k=open("/mnt/midisco/greenbone/claves/escaneo_ed25519").read(); print(f"<create_credential><name>ssh-escaneo</name><type>usk</type><login>escaneo</login><key><private>{html.escape(k)}</private></key></create_credential>")' > /tmp/cred.xml
docker run --rm -i --user "$(id -u):$(id -g)" -e HOME=/tmp -v greenbone-community-edition_gvmd_socket_vol:/run/gvmd -v "$HOME/.config/gvm-tools.conf:/tmp/gvm-tools.conf:ro" -v /tmp/cred.xml:/tmp/orden.xml:ro --entrypoint gvm-cli registry.community.greenbone.net/community/gvm-tools:latest --config /tmp/gvm-tools.conf socket --socketpath /run/gvmd/gvmd.sock /tmp/orden.xml
rm -f /tmp/cred.xml
```

- `umask 077` hace que el fichero temporal se cree con permisos `600`.
- `type usk` significa *Username + SSH Key*. `html.escape` adapta la clave para que pueda ir dentro del XML.
- Al final de `gvm-cli` le pasamos el fichero (`/tmp/orden.xml`) en lugar de `--xml`.

Después creamos el objetivo con la credencial y la tarea:

```
/mnt/midisco/greenbone/scripts/gmp.sh '<create_target><name>Appweb con credenciales</name><hosts>192.168.122.245</hosts><port_list id="33d0cd82-57c6-11e1-8ed1-406186ea4fc5"/><alive_tests>ICMP Ping</alive_tests><ssh_credential id="ID_DE_LA_CREDENCIAL"><port>22</port></ssh_credential></create_target>'
/mnt/midisco/greenbone/scripts/gmp.sh '<create_task><name>P3 Appweb autenticado</name><config id="daba56c8-73ec-11df-a475-002264764cea"/><target id="ID_DEL_OBJETIVO"/><scanner id="08b69003-5fc2-4037-a479-93b440211c73"/></create_task>'
```

**Cómo sabemos que ha funcionado:** aparecen resultados de **paquetes concretos con versión vulnerable** (con su CVE y la versión corregida), detección de **parches pendientes**, y una entrada tipo *«Authenticated Scan / LSC Information»* que confirma que el inicio de sesión funcionó. Si esa entrada indica error de autenticación, revisamos la clave, el usuario y el puerto.

> **Resultado en nuestro laboratorio (tarea `P3 Appweb autenticado`, 1 de noviembre de 2026).**
>
> El escaneo **entró correctamente** en la máquina: el informe contiene los resultados *SSH Login Successful For Authenticated Checks* y *Authenticated Scan / LSC Info Consolidation (Linux/Unix SSH Login)*, y la pestaña *Error Messages* no muestra fallos de inicio de sesión.
>
> | Gravedad | Número de resultados |
> | --- | --- |
> | Alta | 3 |
> | Media | 8 |
> | Baja | 7 |
> | Log (informativos) | 37 |
>
> Hallazgos principales:
>
> | Gravedad | Hallazgo | Puerto | QoD | Qué es en realidad |
> | --- | --- | --- | --- | --- |
> | 8,8 | Sudo 1.8.8 - 1.9.17 Local Privilege Escalation (CVE-2025-32462) | general/tcp | 30 % | **Falso positivo** (ver abajo) |
> | 7,8 | Sudo 1.9.14 - 1.9.17 Local Privilege Escalation (CVE-2025-32463) | general/tcp | 30 % | **Falso positivo** (ver abajo) |
> | 7,8 | Intel BIOS Privilege Escalation (INTEL-SA-00686) | general/tcp | 1 % | Depende del procesador físico, no de la VM. QoD casi nulo |
> | 5,9 | Terrapin Attack (SSH) | 22/tcp | 30 % | Debilidad del protocolo SSH; OpenSSH 10 ya incluye la defensa (*strict KEX*) |
> | 5,3 | OpenSSH Information Disclosure (CVE-2016-20012) | 22/tcp | 50 % | Permite averiguar si una clave pública es válida para un usuario. Riesgo aceptado (no tiene parche) |
> | 5,3 | WordPress `wp-cron.php` accesible | 80/tcp | 30 % | La web de Appweb es un WordPress; podemos limitarlo |
> | 3,7 | Nginx Information Disclosure (CVE-2025-53859) | general/tcp | 30 % | **Falso positivo** (ver abajo) |
> | 2,6 | TCP Timestamps Information Disclosure | general/tcp | 80 % | Real. Lo corregimos en la prueba 6 |
> | 2,6 | Weak MAC Algorithm(s) Supported (SSH): `umac-64-etm@openssh.com`, `umac-64@openssh.com` | 22/tcp | 80 % | Real. Lo corregimos en la prueba 6 |
> | 2,1 | ICMP Timestamp Reply Information Disclosure | general/icmp | 80 % | Real, gravedad muy baja |
>
> **Cómo descubrimos los falsos positivos.** El escáner dice que `sudo` 1.9.16p2 y `nginx` 1.26.3 son vulnerables porque la corrección oficial llegó en versiones posteriores (1.9.17p1 y 1.29.1). Pero Debian suele **copiar la corrección a la versión que ya tiene** sin cambiar el número (lo llama *backport*). Lo comprobamos leyendo el registro de cambios de los paquetes en la máquina:
>
> ```
> ssh app 'zcat /usr/share/doc/sudo/changelog.Debian.gz | grep -n -E "CVE-2025-3246[23]"'
> ssh app 'zcat /usr/share/doc/nginx/changelog.Debian.gz | grep -n "CVE-2025-53859"'
> ```
>
> - `zcat` lee un fichero comprimido sin descomprimirlo; `grep -n -E` busca los identificadores de los CVE y muestra el número de línea.
> - Respuesta: `backport upstream patch for CVE-2025-32463`, `add upstream patch for CVE-2025-32462` y `d/p/CVE-2025-53859.patch add, fix potential information leak`. **Los tres fallos ya están corregidos** en los paquetes instalados (`sudo 1.9.16p2-3+deb13u2`, `nginx 1.26.3-3+deb13u10`).
>
> La pista estaba en el **QoD del 30 %**: significa que el escáner solo ha mirado el número de versión, no ha comprobado el fallo. Estos resultados se marcan con un *override* (sección 5.11) de gravedad *False Positive*, con una nota que explique la comprobación.
>
> **Comparación con el escaneo sin credenciales.** En la prueba 2 escaneamos la misma máquina desde fuera; la diferencia de resultados entre ambos informes es lo que aporta el escaneo autenticado (detalle en 6.3).

#### Si el laboratorio tiene un equipo Windows

**Windows (si el grupo lo escanea):** necesita una cuenta de administrador local, el servicio *Registro remoto* (RemoteRegistry) iniciado, el cortafuegos permitiendo «Compartir archivos e impresoras» y, si la cuenta no es de dominio, el valor de registro `LocalAccountTokenFilterPolicy=1`:

```
reg add HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System /v LocalAccountTokenFilterPolicy /t REG_DWORD /d 1 /f
```

Ese valor debilita una protección de Windows (permite administración remota con cuentas locales), así que **solo se aplica en la VM de laboratorio y se revierte después**. En GSA el credencial es *Username + Password* asociado al campo *SMB* del objetivo. Requiere `openvas-smb` (sección 4.6.5); en el método A ya viene incluido.

### 6.5 Prueba 4: vigilancia continua de la red

**Para qué sirve:** un escaneo suelto es una foto. Para que el escáner sea útil, tenemos que hacer que se **repita solo** cada cierto tiempo y **enterarnos de los cambios** (máquinas nuevas, vulnerabilidades nuevas o ya resueltas).

**Qué necesitamos antes:** la tarea de red de la prueba 2 y, para recibir avisos, el correo de la prueba 5.

**Paso a paso en la web:**

1. **Programación.** *Configuration → Schedules → New Schedule*: nombre `diario-03h`; *First Run*: mañana a las 03:00; *Timezone*: `Europe/Madrid`; *Recurrence*: cada 1 día. Para la demostración en el vídeo creamos otra, `cada-hora`, con repetición horaria y arranque en los próximos minutos.
2. **Tarea ligada a la programación.** Editamos la tarea de la red (6.3) y elegimos en *Schedule* la anterior. Marcamos también *Auto Delete Reports* conservando, por ejemplo, los 10 últimos para no llenar el disco. En la lista de tareas aparece un icono de reloj y la fecha del próximo arranque.
3. **Alerta de cambios** (sección 6.6): enviar correo al terminar y cuando aparezcan vulnerabilidades graves nuevas.
4. **Informes comparativos (*delta*).** Con varios informes de la misma tarea, en *Scans → Reports* seleccionamos uno como referencia (icono de *delta*) y luego otro. GSA muestra cada resultado como *new* (nuevo), *same*, *gone* (resuelto) o *changed*. Es la evidencia de que un parche funciona.
5. **Tendencia.** La columna *Trend* de la lista de tareas indica si la gravedad sube, baja o se mantiene respecto a la ejecución anterior.
6. **Que el escáner arranque solo.** En el método A basta con `restart: on-failure` (viene en el compose) y que Docker arranque con el sistema (`sudo systemctl enable docker`, que `apt` ya activa). Si el equipo es un portátil que se suspende o se apaga, **la tarea no se ejecutará a su hora**: debemos decirlo en la memoria y, para la demostración, usar la programación horaria con el equipo encendido.

Una alternativa o complemento, para quien prefiera `cron`: lanzar la tarea por línea de comandos con `gvm-cli` (sección 7).

**Lo mismo desde la terminal (opcional):**

```
/mnt/midisco/greenbone/scripts/gmp.sh '<create_schedule><name>diario-03h</name><timezone>Europe/Madrid</timezone><icalendar>BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//SAD 2ASIR//OpenVAS//ES
BEGIN:VEVENT
DTSTART;TZID=Europe/Madrid:20261102T030000
RRULE:FREQ=DAILY
END:VEVENT
END:VCALENDAR</icalendar></create_schedule>'
/mnt/midisco/greenbone/scripts/gmp.sh '<modify_task task_id="ID_TAREA_RED"><schedule id="ID_PROGRAMACION"/><preferences><preference><scanner_name>auto_delete</scanner_name><value>keep</value></preference><preference><scanner_name>auto_delete_data</scanner_name><value>10</value></preference></preferences></modify_task>'
```

- Greenbone guarda las programaciones en formato **iCalendar** (el mismo de los calendarios de Google o Outlook): `DTSTART` es la primera ejecución (2 de noviembre a las 03:00) y `RRULE:FREQ=DAILY` significa «cada día».
- `PRODID` es obligatorio en iCalendar: identifica qué programa creó el calendario. Sin esa línea, Greenbone rechaza la programación (ver el resultado más abajo).
- `modify_task` asocia la programación a la tarea de red y activa *Auto Delete Reports* conservando los 10 últimos informes.

**Cómo sabemos que ha funcionado:** en *Scans → Tasks* la tarea muestra un icono de reloj con la fecha de la próxima ejecución, y tras cada ejecución llega el correo de la alerta.

> **Resultado en nuestro laboratorio (1 de noviembre de 2026).**
>
> 1. **Creamos la programación `diario-03h`** (todos los días a las 03:00, zona horaria *Europe/Madrid*). La primera vez que lo intentamos, Greenbone respondió:
>
>    `Invalid ICALENDAR: ... Failed iTIP restrictions for PRODID property. Expected 1 instances of the property and got 0`
>
>    El formato iCalendar exige una línea `PRODID`, que identifica el programa que crea el calendario. Al añadirla (`PRODID:-//SAD 2ASIR//OpenVAS//ES`, como en el comando de arriba), la respuesta fue `status="201" ... resource created`. Desde la web no hace falta: el formulario *New Schedule* la escribe solo.
> 2. **La asociamos a la tarea `P2b Vulnerabilidades red`**, con *Auto Delete Reports* conservando los **10** últimos informes (`modify_task` respondió `status="200" OK`). En *Scans → Tasks* la tarea muestra ahora el icono del reloj.
> 3. **Alertas de la tarea:** `informe-al-terminar` (PDF cada mañana), `critica-inmediata` (solo si aparece algo de gravedad ≥ 7) y `cambios-respecto-a-ayer` (un informe *delta* con lo nuevo y lo desaparecido respecto al día anterior).
> 4. **Comparación de informes:** ya la hemos usado de verdad con Appweb. Comparando el escaneo de antes del parche con el de después, *Weak MAC Algorithms* y *TCP Timestamps* salieron como **Gone** (apartado 6.9).
>
> Con esto, la red del laboratorio queda **vigilada sin intervención**: cada noche se escanea y, si algo cambia, por la mañana tenemos el correo.

### 6.6 Prueba 5: aviso por correo de lo encontrado

**Para qué sirve:** que Greenbone nos **mande un correo** cuando termine un escaneo o cuando encuentre algo grave, para no tener que estar mirando la web.

**Qué necesitamos antes:** una cuenta de correo con la que enviar (nosotros usamos Gmail) y la instalación Docker funcionando.

#### 6.6.1 Qué necesitamos entender (primera vez con SMTP)

- **SMTP** es el protocolo con el que se **envían** correos. Para enviar hace falta un **servidor SMTP** (por ejemplo el de Gmail) y, casi siempre, **usuario y contraseña**.
- **Greenbone no incluye servidor de correo.** Cuando una alerta debe enviar un email, gvmd ejecuta el comando `sendmail` del sistema. Nosotros tenemos que proporcionar un `sendmail` que reenvíe el correo a un servidor SMTP real.
- En los **contenedores** (método A) la imagen de gvmd ya trae `msmtp`, un cliente SMTP muy ligero que actúa como `sendmail`, configurable con variables de entorno `MTA_*`. En el **método B** lo instalamos nosotros.
- Puertos habituales: **587** (STARTTLS, el recomendado), **465** (TLS implícito) y 25 (sin cifrar, evitar).

#### 6.6.2 Qué recomendamos para el grupo

| Opción | Ventajas | Inconvenientes | Veredicto |
| --- | --- | --- | --- |
| **Gmail con «contraseña de aplicación»** (cuenta dedicada) | Gratis, conocida por todos, cifrado STARTTLS, el propio compose oficial incluye un ejemplo con Gmail | Exige verificación en dos pasos; Google puede cambiar esta política; límites de envío diario | **Recomendada para empezar** |
| Un relay transaccional gratuito (por ejemplo Brevo, Mailjet) | No depende de una cuenta personal; «clave SMTP» revocable; buenas estadísticas de entrega | Registro y verificación del remitente | Buena alternativa si Gmail da problemas |
| Postfix local reenviando a otro servidor | Aprendes administración de correo; sirve para varios servicios | Más configuración; sin DNS/SPF/DKIM los correos suelen ir a spam | No para esta práctica |

**Recomendación concreta:** crear una **cuenta de Gmail nueva solo para esta práctica** (por ejemplo `grupo.sad.alertas@gmail.com`), **nunca la personal**, activar la verificación en dos pasos y generar una **contraseña de aplicación** (Cuenta de Google → Seguridad → Verificación en dos pasos → Contraseñas de aplicaciones). Google entrega 16 caracteres que se usan **en lugar** de la contraseña normal. Si en el momento de hacerlo Google ya no ofrece esa opción para la cuenta, se usa el relay alternativo con los datos que entregue el proveedor (servidor, puerto 587, usuario y clave SMTP).

> **Seguridad de las credenciales:** la contraseña de aplicación se guarda en un fichero con permisos restringidos y **jamás se sube al repositorio del blog de grupo ni se muestra en capturas**. Si se filtra, se revoca en la cuenta y se genera otra.

**Cómo crear la contraseña de aplicación de Gmail, paso a paso:**

1. Entrar en la cuenta de Google → *Seguridad* → activar la **Verificación en dos pasos** (si no lo estaba). Sin ella, Google no deja crear contraseñas de aplicación.
2. Abrir `https://myaccount.google.com/apppasswords`.
3. Escribir un nombre, por ejemplo `Greenbone`, y pulsar *Crear*.
4. Google muestra 16 letras en cuatro grupos. Las copiamos **sin espacios**. Solo se muestran una vez; si se pierden, se borra y se crea otra.

#### 6.6.3 Primera idea: editar `compose.yaml` (la descartamos)

Esta fue nuestra primera idea. La dejamos documentada porque funciona, pero **no es la que aplicamos**, por el motivo que explicamos al final de este apartado.

Guardamos las credenciales en un fichero `.env` junto al compose (Docker Compose lo lee solo):

```bash
$ cd $DOWNLOAD_DIR
$ cat > .env <<'EOF'
SMTP_USER=grupo.sad.alertas@gmail.com
SMTP_PASSWORD=xxxxxxxxxxxxxxxx
EOF
$ chmod 600 .env
```

- `cat > .env <<'EOF'` escribe el texto siguiente en el fichero `.env`. Sustituimos usuario y contraseña de aplicación (16 caracteres, sin espacios).
- `chmod 600` deja el fichero legible solo por nuestro usuario.

Editamos `compose.yaml` y en el servicio **`gvmd`** añadimos (o fusionamos, si ya existe un bloque `environment:`):

```yaml
  gvmd:
    environment:
      - MTA_HOST=smtp.gmail.com
      - MTA_PORT=587
      - MTA_TLS=on
      - MTA_STARTTLS=on
      - MTA_AUTH=on
      - MTA_USER=${SMTP_USER}
      - MTA_PASSWORD=${SMTP_PASSWORD}
      - MTA_FROM=${SMTP_USER}
```

| Variable | Significado |
| --- | --- |
| `MTA_HOST` / `MTA_PORT` | Servidor SMTP y puerto |
| `MTA_TLS=on` | Activa el cifrado TLS |
| `MTA_STARTTLS=on` | Inicia TLS dentro de la sesión (puerto 587). Con `off` se usa TLS directo (puerto 465) |
| `MTA_AUTH=on` | Activa la autenticación con usuario y contraseña |
| `MTA_USER` / `MTA_PASSWORD` | Credenciales. `${SMTP_USER}` y `${SMTP_PASSWORD}` se leen de `.env` |
| `MTA_FROM` | Dirección remitente del sobre del correo. Debe coincidir con la cuenta autenticada |
| `MTA_TLS_CERTCHECK` | Comprobación del certificado del servidor. **No desactivar** salvo diagnóstico |
| `MTA_LOGFILE` | Fichero de registro de msmtp (útil para depurar) |

Recreamos solo el contenedor `gvmd`:

```bash
$ sudo docker compose -f $DOWNLOAD_DIR/compose.yaml -p greenbone-community-edition up -d gvmd
```

- `up -d gvmd` aplica los cambios al servicio indicado sin tocar los demás. Los datos no se pierden porque están en volúmenes.

**Por qué la descartamos.** El script oficial `setup-and-start-greenbone-community-edition.sh` vuelve a descargar `compose.yaml` cada vez que lo ejecutamos para actualizar. Cualquier cambio que hagamos dentro de ese fichero **se perdería** en la siguiente actualización, y el correo dejaría de funcionar sin avisar.

#### 6.6.4 Método A: configuración que aplicamos (fichero aparte, *override*)

Docker Compose permite usar **varios ficheros a la vez**: el oficial y otro nuestro con solo los cambios. Compose los «suma» al arrancar. Así no tocamos el fichero oficial y nuestro cambio sobrevive a las actualizaciones.

Antes de nada comprobamos cómo configura el correo la imagen de `gvmd`:

```
docker exec greenbone-community-edition-gvmd-1 ls -l /usr/sbin/sendmail
docker exec greenbone-community-edition-gvmd-1 cat /usr/local/bin/setup-mta
```

- El primer comando muestra que `sendmail` es en realidad un enlace a `msmtp`.
- El segundo muestra el script que, al arrancar el contenedor, escribe `/etc/msmtprc` a partir de las variables `MTA_HOST`, `MTA_PORT`, `MTA_TLS`, `MTA_STARTTLS`, `MTA_AUTH`, `MTA_USER`, `MTA_FROM`, `MTA_PASSWORD` y `MTA_LOGFILE`. Si `MTA_HOST` está vacía, no configura nada; por eso al principio el correo no funcionaba.

**Paso 1. Fichero con los datos del correo (sin la contraseña en el documento).** Creamos una plantilla sin la contraseña:

```
cat > /mnt/midisco/greenbone/compose/correo.env.ejemplo <<'EOF'
MTA_HOST=smtp.gmail.com
MTA_PORT=587
MTA_TLS=on
MTA_STARTTLS=on
MTA_AUTH=on
MTA_USER=juanka.fdez05@gmail.com
MTA_FROM=juanka.fdez05@gmail.com
MTA_PASSWORD=PON_AQUI_LA_CONTRASEÑA_DE_APLICACION
MTA_LOGFILE=/var/log/gvm/msmtp.log
EOF
```

La copiamos al fichero real, la protegemos y escribimos la contraseña de aplicación con un editor:

```
cp /mnt/midisco/greenbone/compose/correo.env.ejemplo /mnt/midisco/greenbone/compose/correo.env
chmod 600 /mnt/midisco/greenbone/compose/correo.env
nano /mnt/midisco/greenbone/compose/correo.env
```

- `chmod 600` deja el fichero legible solo por nuestro usuario (y por `root`, que es quien arranca Docker).
- Escribimos la contraseña **sin espacios** (16 caracteres; ver incidencia en 3.11).
- `MTA_LOGFILE` hace que msmtp guarde un registro de cada envío, muy útil si algo falla.

##### El fichero `correo.env` explicado variable por variable

**Qué es y quién lo lee.** `correo.env` es un fichero de texto que guarda los datos de nuestro servidor de correo. Greenbone no lo lee directamente: pasa por cuatro programas, uno detrás de otro.

```
correo.env  ──(Docker Compose, env_file)──►  variables MTA_* dentro del contenedor gvmd
            ──(script setup-mta al arrancar)──►  /etc/msmtprc
            ──(msmtp, que hace de «sendmail»)──►  smtp.gmail.com  ──►  nuestro buzón
```

1. **Docker Compose** lee `correo.env` (porque lo indicamos con `env_file` en `correo.override.yaml`) y mete cada línea como **variable de entorno** en el contenedor `gvmd`.
2. Al arrancar el contenedor, el script de la imagen **`/usr/local/bin/setup-mta`** convierte cada variable `MTA_*` en una línea del fichero **`/etc/msmtprc`**, la configuración de msmtp.
3. Cuando una alerta envía un correo, `gvmd` llama a `sendmail`, que en esta imagen es un enlace a **msmtp**. msmtp lee `/etc/msmtprc` y entrega el correo al servidor de Gmail.

**Reglas para escribir el fichero** (es el formato `env_file` de Docker Compose):
- Una variable por línea, con la forma `NOMBRE=valor`, **sin espacios** alrededor del `=`.
- Sin comillas: el valor es todo lo que hay después del `=`.
- Las líneas que empiezan por `#` son comentarios. **No** se pueden poner comentarios al final de una línea con valor, porque formarían parte del valor.
- Si una variable no aparece o está vacía, `setup-mta` no escribe esa línea y msmtp usa su valor por defecto.

**Todas las variables que entiende la imagen.** Las hemos sacado del propio script `setup-mta`, que lee exactamente estas diez:

| Variable | Línea que genera en `/etc/msmtprc` | Para qué sirve | Valores posibles | Nuestro valor |
| --- | --- | --- | --- | --- |
| `MTA_HOST` | `host …` | Servidor de correo de salida (SMTP). **Obligatoria:** si está vacía, `setup-mta` no configura nada y el correo no sale | nombre o IP del servidor | `smtp.gmail.com` |
| `MTA_PORT` | `port …` | Puerto del servidor | `587` (envío con STARTTLS), `465` (SMTPS, cifrado desde el principio), `25` (entre servidores, sin cifrar) | `587` |
| `MTA_TLS` | `tls …` | Cifrar la conexión | `on` / `off` | `on` |
| `MTA_STARTTLS` | `tls_starttls …` | Cómo se cifra. `on`: se conecta en claro y pide el cifrado con la orden STARTTLS (puerto 587). `off`: cifrado desde el primer byte (puerto 465) | `on` / `off` | `on` |
| `MTA_TLS_CERTCHECK` | `tls_certcheck …` | Comprobar el certificado del servidor. Si no la ponemos, msmtp **lo comprueba** (`on`), que es lo seguro. Solo la pondríamos en `off` en un laboratorio con un servidor de certificado autofirmado | `on` / `off` | *(no la ponemos)* |
| `MTA_AUTH` | `auth …` | Iniciar sesión en el servidor antes de enviar. Gmail lo exige | `on`, `off` o un método concreto (`plain`, `login`…) | `on` |
| `MTA_USER` | `user …` | Usuario con el que iniciamos sesión | normalmente la dirección de correo completa | `juanka.fdez05@gmail.com` |
| `MTA_FROM` | `from …` | Remitente del sobre. Con Gmail **tiene que ser la misma cuenta** que `MTA_USER`; si no, Gmail lo cambia o lo rechaza | una dirección de correo | `juanka.fdez05@gmail.com` |
| `MTA_PASSWORD` | `password …` | Contraseña de esa cuenta. Con Gmail es una **contraseña de aplicación** de 16 letras, **sin espacios**, nunca la contraseña normal | texto | *(la nuestra; no aparece en este documento)* |
| `MTA_LOGFILE` | `logfile …` | Fichero donde msmtp apunta cada envío: fecha, servidor, tamaño y resultado (`smtpstatus=250` = aceptado) | ruta dentro del contenedor | `/var/log/gvm/msmtp.log` |

**Nuestro fichero completo, comentado** (con la contraseña sustituida):

```
# /mnt/midisco/greenbone/compose/correo.env
# Datos de correo para el contenedor gvmd de Greenbone.
# Permisos: 600 (solo lo lee nuestro usuario y root). NO subir a ningún sitio.

# Servidor de salida de Gmail y puerto de envío con STARTTLS
MTA_HOST=smtp.gmail.com
MTA_PORT=587

# Conexión cifrada: empezamos en claro y pedimos cifrado (STARTTLS)
MTA_TLS=on
MTA_STARTTLS=on

# Iniciamos sesión con nuestra cuenta; el remitente es la misma cuenta
MTA_AUTH=on
MTA_USER=juanka.fdez05@gmail.com
MTA_FROM=juanka.fdez05@gmail.com

# Contraseña de aplicación de Google: 16 letras seguidas, sin espacios
MTA_PASSWORD=abcdefghijklmnop

# Registro de envíos (para comprobar si sale el correo)
MTA_LOGFILE=/var/log/gvm/msmtp.log
```

> `abcdefghijklmnop` es un **ejemplo inventado**. En nuestro fichero real está la contraseña de aplicación que creamos para Greenbone.

**El resultado: el `/etc/msmtprc` que genera dentro del contenedor.** Lo vemos sin mostrar la contraseña:

```
docker exec greenbone-community-edition-gvmd-1 sh -c 'ls -l /etc/msmtprc; grep -v -i password /etc/msmtprc'
```

En nuestro equipo devuelve:

```
-rwxr-x--- 1 gvmd mail 175 Nov  1 11:28 /etc/msmtprc
host smtp.gmail.com
port 587
tls on
tls_starttls on
auth on
user juanka.fdez05@gmail.com
from juanka.fdez05@gmail.com
logfile /var/log/gvm/msmtp.log
```

Cada variable se ha convertido en su línea. `setup-mta` deja el fichero como propiedad de `gvmd` y con permisos `750`, para que solo lo lean `gvmd` y el grupo `mail`.

**Otros ejemplos, por si usamos otro servidor:**

| Caso | Cambios respecto al nuestro |
| --- | --- |
| Gmail por el puerto 465 (SMTPS) | `MTA_PORT=465` y `MTA_STARTTLS=off` (el cifrado empieza directamente) |
| Servidor de correo interno de la empresa, sin usuario | `MTA_HOST=correo.empresa.local`, `MTA_PORT=25`, `MTA_AUTH=off`, sin `MTA_USER` ni `MTA_PASSWORD`; `MTA_FROM=openvas@empresa.local` |
| Servidor de laboratorio con certificado autofirmado | Añadir `MTA_TLS_CERTCHECK=off` (**solo** en laboratorio: sin comprobar el certificado, alguien podría hacerse pasar por el servidor) |

**Cómo conseguimos la contraseña de aplicación de Google, paso a paso:**

1. Entramos en nuestra cuenta de Google → **Seguridad**.
2. Comprobamos que la **Verificación en dos pasos** está activada. Sin ella, Google no deja crear contraseñas de aplicación.
3. Entramos en **Contraseñas de aplicación** (`https://myaccount.google.com/apppasswords`).
4. Escribimos un nombre que la identifique, por ejemplo `Greenbone`, y pulsamos **Crear**.
5. Google muestra 16 letras en cuatro grupos (`abcd efgh ijkl mnop`). Las copiamos **sin los espacios** en `MTA_PASSWORD`. Con espacios, Gmail responde con el error 535 (incidencia en 3.11).
6. Si algún día queremos cortar el acceso, la borramos desde esa misma página. La contraseña normal de la cuenta no cambia.

**Si cambiamos algo en `correo.env`:** las variables solo se leen al **crear** el contenedor. Un `docker restart` no basta: tenemos que recrearlo con el mismo comando del paso 3 (`… up -d gvmd`), y siempre con ningún escaneo en marcha.

**Errores típicos y qué significan** (los vemos en `/var/log/gvm/msmtp.log` o en la salida de la prueba):

| Mensaje | Causa | Solución |
| --- | --- | --- |
| `535 5.7.8 Username and Password not accepted` | Contraseña mal copiada (con espacios) o es la contraseña normal | Copiar la contraseña de aplicación sin espacios |
| `cannot connect to smtp.gmail.com, port 587` | Sin salida a Internet por ese puerto, o `MTA_HOST` mal escrito | Probar la red; revisar el nombre |
| No hay `/etc/msmtprc` en el contenedor | `MTA_HOST` vacía o el *override* no se cargó | `docker exec … env \| grep ^MTA_` y recrear `gvmd` con los dos `-f` |
| La alerta «se envía» pero no queda en el registro | El registro es de `root` y `gvmd` no puede escribir | `chown gvmd:gvmd /var/log/gvm/msmtp.log` (incidencia en 3.11) |

**Paso 2. Fichero *override* que añade esas variables a `gvmd`:**

```
cat > /mnt/midisco/greenbone/compose/correo.override.yaml <<'EOF'
services:
  gvmd:
    env_file:
      - /mnt/midisco/greenbone/compose/correo.env
EOF
```

- `services: gvmd:` indica que solo cambiamos el servicio `gvmd`.
- `env_file` carga como variables de entorno todas las líneas de `correo.env`. Las variables llegan directamente al contenedor, sin pasar por `compose.yaml`.

**Paso 3. Recrear `gvmd` con los dos ficheros:**

```
sudo docker compose -f /root/greenbone-community-container/compose.yaml -f /mnt/midisco/greenbone/compose/correo.override.yaml -p greenbone-community-edition up -d gvmd
```

- El segundo `-f` añade nuestro fichero encima del oficial.
- `up -d gvmd` recrea solo el gestor. Los datos se conservan en los volúmenes, pero **los escaneos que estén en marcha se interrumpen** (ver incidencia en 3.11). Por eso lo hacemos cuando no hay tareas en marcha o, si las hay, las reanudamos después.

**Paso 4. Que también se cargue al arrancar el equipo.** Añadimos el *override* a la unidad `greenbone-compose.service` (sección 3.9.3):

```
sudo sed -i 's#-f /root/greenbone-community-container/compose.yaml #&-f /mnt/midisco/greenbone/compose/correo.override.yaml #g' /etc/systemd/system/greenbone-compose.service && sudo systemctl daemon-reload
```

- `sed -i 's#buscar#&añadido#g'` busca el texto del fichero oficial y añade detrás (`&` es el texto encontrado) nuestro segundo `-f`, en las líneas `ExecStart` y `ExecStop`.
- `daemon-reload` hace que systemd lea la unidad modificada.

**Paso 5. Comprobar que `gvmd` tiene la configuración**, sin mostrar la contraseña:

```
docker exec greenbone-community-edition-gvmd-1 env | grep ^MTA_ | grep -v PASSWORD
```

> **Resultado en nuestro laboratorio.** La comprobación muestra las variables cargadas (`MTA_HOST=smtp.gmail.com`, `MTA_PORT=587`, `MTA_TLS=on`, `MTA_STARTTLS=on`, `MTA_AUTH=on`, `MTA_USER` y `MTA_FROM` con nuestra cuenta, `MTA_LOGFILE=/var/log/gvm/msmtp.log`), y el contenedor ha generado `/etc/msmtprc` con permisos `750` y propietario `gvmd:mail`. La unidad `greenbone-compose.service` contiene el *override* en sus dos líneas (`grep -c correo.override` devuelve `2`).

> **Nuestra elección de cuenta:** usamos la cuenta `juanka.fdez05@gmail.com` con una **contraseña de aplicación** creada solo para Greenbone. No es la contraseña de la cuenta: solo sirve para enviar correo y se puede revocar en cualquier momento sin afectar a nada más.

**Prueba de funcionalidad del correo, independiente de Greenbone** (vale para las dos opciones):

```bash
$ sudo docker compose -f $DOWNLOAD_DIR/compose.yaml -p greenbone-community-edition exec gvmd bash -c 'printf "Subject: Prueba OpenVAS\n\nCorreo de prueba desde el contenedor.\n" | sendmail -f "$MTA_FROM" destino@ejemplo.com'
```

- Ejecutamos dentro del contenedor un correo mínimo: la cabecera `Subject:`, una línea en blanco y el cuerpo. `sendmail -f <remitente> <destino>` envía a través de msmtp. Si no hay error y el mensaje llega al buzón (revisar *Spam*), el correo funciona.
- Si falla, consultar los registros con `docker compose ... logs gvmd` y las notas de resolución de problemas (sección 8).

#### 6.6.5 Crear las alertas en la web

Creamos tres alertas pensadas para casos distintos (*Configuration → Alerts → New Alert*):

| Alerta | Evento | Condición | Método / contenido |
| --- | --- | --- | --- |
| `informe-al-terminar` | Task run status changed → **Done** | Always | Email, *Attach report*, formato PDF |
| `critica-inmediata` | Task run status changed → **Done** | Severity at least **7.0** | Email, *Include report* en texto con límite de resultados, asunto claro |
| `cambios-respecto-a-ayer` | Task run status changed → **Done** | Severity changed → **Increased** | Email con informe *Delta* respecto al anterior de la tarea |

Rellenamos *To Address* con el correo de destino (por ejemplo, el de cada miembro del grupo separado por comas) y *From Address* con la cuenta emisora.

Prueba de la alerta sin tener que escanear: en la lista de alertas, el icono **▶ *Test Alert*** envía un correo de prueba con datos de ejemplo. Después la asociamos a una tarea (campo *Alerts* de la tarea), la ejecutamos y comprobamos que el correo llega con el informe adjunto.

**Lo mismo desde la terminal (opcional).** Así creamos nosotros las tres alertas:

```
G=/mnt/midisco/greenbone/scripts/gmp.sh; M=juanka.fdez05@gmail.com
EV='<event>Task run status changed<data>Done<name>status</name></data></event>'
$G "<create_alert><name>informe-al-terminar</name><condition>Always</condition>$EV<method>Email<data>$M<name>to_address</name></data><data>$M<name>from_address</name></data><data>[OpenVAS] Terminada la tarea \$n<name>subject</name></data><data>2<name>notice</name></data><data>c402cc3e-b531-11e1-9163-406186ea4fc5<name>notice_attach_format</name></data></method></create_alert>"
$G "<create_alert><name>critica-inmediata</name><condition>Severity at least<data>7.0<name>severity</name></data></condition>$EV<method>Email<data>$M<name>to_address</name></data><data>$M<name>from_address</name></data><data>[OpenVAS] ALERTA gravedad alta en \$n<name>subject</name></data><data>0<name>notice</name></data><data>a3810a62-1f62-11e1-9219-406186ea4fc5<name>notice_report_format</name></data></method></create_alert>"
$G "<create_alert><name>cambios-respecto-a-ayer</name><condition>Severity changed<data>increased<name>direction</name></data></condition>$EV<method>Email<data>$M<name>to_address</name></data><data>$M<name>from_address</name></data><data>[OpenVAS] Cambios en \$n respecto al escaneo anterior<name>subject</name></data><data>2<name>notice</name></data><data>c402cc3e-b531-11e1-9163-406186ea4fc5<name>notice_attach_format</name></data><data>Previous<name>delta_type</name></data></method></create_alert>"
```

- `G` y `M` son variables para no repetir la ruta del script y la dirección de correo.
- `EV` es el evento común: «la tarea ha terminado» (*Done*).
- `notice` indica qué se envía: `0` el informe dentro del correo, `1` solo un aviso, `2` el informe adjunto. El identificador `c402cc3e-...` es el formato PDF y `a3810a62-...` el de texto (TXT).
- `$n` en el asunto se sustituye por el nombre de la tarea (va con `\` delante para que la terminal no lo trate como variable).
- `delta_type Previous` hace que el informe se compare con el anterior de la misma tarea.

Para asociarlas a una tarea ya creada:

```
/mnt/midisco/greenbone/scripts/gmp.sh '<modify_task task_id="ID_DE_LA_TAREA"><alert id="ID_ALERTA_1"/><alert id="ID_ALERTA_2"/><alert id="ID_ALERTA_3"/></modify_task>'
```

**Cómo sabemos que ha funcionado:** al pulsar *Test Alert* (o al terminar una tarea) llega el correo y el registro de msmtp muestra `smtpstatus=250`.

> **Resultado en nuestro laboratorio.** Creamos las tres alertas también desde la línea de comandos (sección 7), con destino `juanka.fdez05@gmail.com`, y las asociamos a las tareas de las pruebas 1 y 2. La orden equivalente al botón *Test Alert* es:
>
> ```
> /mnt/midisco/greenbone/scripts/gmp.sh '<test_alert alert_id="<ID_ALERTA>"/>'
> ```
>
> El registro de `gvmd` muestra `The alert informe-al-terminar was triggered (Event: Task status changed to 'Done', Condition: Always)` y el de msmtp confirma la entrega del correo con el PDF adjunto (unos 112 KB):
>
> ```
> Nov 01 11:32:08 host=smtp.gmail.com tls=on auth=on user=juanka.fdez05@gmail.com ... mailsize=114650 smtpstatus=250 smtpmsg='250 2.0.0 OK ...' exitcode=EX_OK
> ```
>
> `smtpstatus=250` es la respuesta de Gmail que significa «aceptado».

Prueba de envío con el usuario correcto (el mismo que usa `gvmd` para las alertas):

```
docker exec -u gvmd greenbone-community-edition-gvmd-1 bash -c 'printf "Subject: Prueba como gvmd\n\nx\n" | sendmail -f "$MTA_FROM" juanka.fdez05@gmail.com; echo "salida: $?"'
docker exec greenbone-community-edition-gvmd-1 tail -1 /var/log/gvm/msmtp.log
```

**Si el correo no llega:**

```
sudo docker compose -f /root/greenbone-community-container/compose.yaml -p greenbone-community-edition logs gvmd | grep -i -E "alert|mail|sendmail"
docker exec greenbone-community-edition-gvmd-1 tail /var/log/gvm/msmtp.log
```

- El primero busca en el registro de `gvmd` los mensajes de alertas y correo.
- El segundo muestra los últimos envíos de msmtp con la respuesta del servidor (el error 535 indica usuario o contraseña incorrectos; ver tabla de 8.4).

Depuración si no llega: método A, `docker compose ... logs gvmd | grep -i -E "alert|mail|sendmail"`; método B, `sudo grep -i alert /var/log/gvm/gvmd.log` y `sudo tail /var/log/gvm/msmtp.log`.

### 6.7 Análisis de los informes

Un informe abierto no es una lista de problemas: es una lista de **candidatos** a problema que tenemos que **validar y priorizar**.

#### 6.7.1 Anatomía de un informe

| Pestaña | Qué contiene |
| --- | --- |
| Information | Resumen: fecha, duración, configuración usada, número de hosts y resultados por gravedad |
| Results | Todos los hallazgos, con columnas: *Vulnerability*, *Severity*, *QoD*, *Host*, *Location* (puerto/protocolo), *Created* |
| Hosts | Gravedad máxima por máquina |
| Ports | Puertos abiertos y gravedad asociada |
| Applications | Software detectado (CPE) |
| Operating Systems | Sistemas operativos detectados |
| CVEs | CVEs encontrados |
| Closed CVEs | CVEs que el escáner descartó por estar ya parcheados (aparecen en escaneos autenticados) |
| TLS Certificates | Certificados detectados, con caducidad y emisor |
| Error Messages | Fallos del propio escaneo (conexiones perdidas, credenciales rechazadas): **tenemos que leerlos** |

#### 6.7.2 Anatomía de un resultado

Al abrir una vulnerabilidad aparecen, entre otros, estos apartados:

- **Summary:** en una frase, qué es.
- **Detection Result:** la evidencia concreta (por ejemplo, la respuesta del servidor).
- **Detection Method:** cómo lo ha comprobado y su **QoD**.
- **Insight:** el contexto técnico.
- **Impact:** qué puede hacer un atacante.
- **Solution:** el tipo (*VendorFix*: hay parche oficial; *Mitigation*: se puede reducir el riesgo; *Workaround*: solución alternativa; *NoneAvailable* / *WillNotFix*) y las instrucciones.
- **Affected Software/OS** y **References** (enlaces a CVE, avisos del fabricante y a la ficha de la prueba).

#### 6.7.3 Método de triaje

1. **Filtrar el ruido:** ordenar por gravedad, mantener un QoD de al menos 70 % y revisar aparte lo que tenga QoD bajo.
2. **Agrupar por host y por servicio:** si diez resultados provienen de `nginx` 1.22, probablemente baste una actualización.
3. **Validar cada hallazgo importante a mano.** Ejemplos: si dice «FTP anónimo», `ftp <IP_LAB>` con usuario `anonymous`; si dice «PostgreSQL con credenciales por defecto», `psql -h <IP_LAB> -U postgres`; si dice «SSH acepta contraseña», `ssh -o PreferredAuthentications=password usuario@<IP_LAB>`.
4. **Clasificar:**
   - *Verdadero positivo:* se corrige (sección 6.8).
   - *Falso positivo:* se documenta y se crea un *override* de gravedad 0 con una nota explicando por qué.
   - *Riesgo aceptado:* se anota quién lo acepta y hasta cuándo.
5. **Priorizar** por: gravedad CVSS, si el servicio está expuesto a la red o solo en local, si existe un *exploit* público (la ficha lo indica en las referencias) y la importancia del equipo.

#### 6.7.4 Exportar y guardar los informes

En la lista de informes, icono de descarga → formato. Los más útiles: **PDF** (para entregar), **HTML** (para el blog), **XML** y **CSV** (para procesarlos con scripts o hojas de cálculo) y **TXT**. Los guardamos en `/mnt/midisco/greenbone/informes/` con el nombre `AAAA-MM-DD_tarea.pdf`.

> Los informes contienen información sensible (IPs, versiones, debilidades). **No se publican tal cual**: en el blog público del grupo se tapan o se sustituyen las IPs y se omiten los datos que permitan atacar equipos reales. Existe un formato «Anonymous XML» pensado para compartir informes con menos datos identificativos.

> **Cómo analizamos nuestros informes (1 de noviembre de 2026).**
>
> Aplicamos el método de triaje de 6.7.3 a los tres equipos:
>
> | Equipo | Resultado del análisis | Decisión |
> | --- | --- | --- |
> | Metasploitable3 (.52) | 21 críticas y 54 altas, casi todas con QoD 30 % (deducidas por versión), pero creíbles porque sus programas son de 2014 – 2016 | **Reemplazar** la máquina; no se parchea (es vulnerable a propósito) |
> | Appweb (.245) | 2 reales fáciles de corregir (QoD 80 %): *Weak MAC* y *TCP Timestamps*. 3 **falsos positivos** confirmados en el *changelog* de Debian (sudo ×2 y nginx). El resto, riesgos aceptados | **Corregir** las 2 reales, marcar los 3 falsos positivos con *override* y documentar el resto (6.9) |
> | debian13 (.217) | Los mismos avisos de configuración que Appweb (SSH y TCP) | Aplicar los **mismos dos ficheros** de Appweb (`10-endurecido.conf` y `99-endurecimiento.conf`) |
>
> **Cómo validamos cada hallazgo importante, sin fiarnos solo del escáner:**
>
> - *Weak MAC (SSH)* → `nmap --script ssh2-enum-algos` mostró los dos `umac-64`: **real**.
> - *Sudo* y *Nginx* (QoD 30 %) → `zcat /usr/share/doc/<paquete>/changelog.Debian.gz | grep CVE-…` mostró que Debian ya había corregido esos CVE: **falsos positivos**.
> - *Intel BIOS / CPU* (QoD 1 %) → dependen del procesador físico, no de la VM: **riesgo aceptado**.
>
> **Cómo priorizamos:** primero lo que es **real** (QoD alto) y **fácil de corregir sin romper nada**; después lo grave que necesita más trabajo; y al final documentamos lo que no depende de nosotros. Por eso empezamos por dos hallazgos de gravedad 2,6 y no por el de sudo de 8,8: el de sudo era falso.
>
> **Informes exportados** (PDF completos, con todos los niveles de QoD y aplicando nuestros *overrides*), en `/mnt/midisco/greenbone/informes/`:
>
> | Fichero | Contenido | Páginas |
> | --- | --- | --- |
> | `P1-Metasploitable3.pdf` | Prueba 1, un host | 173 |
> | `P2b-red-laboratorio.pdf` | Prueba 2, red completa | 209 |
> | `P3-Appweb-autenticado-antes-del-parche.pdf` | Prueba 3, antes de corregir | 42 |
> | `P3-Appweb-autenticado-despues-del-parche.pdf` | Después de corregir (prueba 6) | 41 |
>
> Los exportamos desde la terminal con el filtro `apply_overrides=1 min_qod=0 rows=-1 levels=chmlgf`. Si los descargamos desde la web, escribimos ese filtro antes de pulsar el icono de descarga (apartado 6.10.1).

### 6.8 Prueba 6: parcheo de las vulnerabilidades encontradas

Para cada hallazgo que hayamos validado aplicamos la corrección, volvemos a escanear **la misma tarea** y mostramos en el informe *delta* que el resultado pasa a *gone*. Esa evidencia (informe antes/después) es lo que pide la rúbrica.

Antes de tocar nada: **copia de seguridad** de la configuración que vamos a cambiar (`sudo cp -a /etc/nginx /etc/nginx.bak`, etc.) y, si es una VM, una instantánea (`virsh snapshot-create-as <vm> antes-de-parchear`).

> **Cómo usar los apartados 6.8.1 a 6.8.7.** Son «recetas» para los fallos más típicos, pensadas para la VM con fallos de 6.1.5. **Solo aplicamos las que correspondan a lo que ha encontrado nuestro escáner.** Lo que hicimos nosotros en `Appweb` está en el recuadro de resultados al final de 6.8.

#### 6.8.1 Paquetes desactualizados (detectados con credenciales)

```bash
$ sudo apt update
$ apt list --upgradable
$ sudo apt full-upgrade -y
$ sudo needrestart -r a
```

- `apt list --upgradable` muestra qué paquetes tienen versión nueva; es la lista que debe coincidir con los hallazgos del informe.
- `full-upgrade` los instala (incluyendo los que cambian dependencias).
- `needrestart` (`sudo apt install needrestart` si no está) detecta qué servicios siguen usando librerías viejas y `-r a` los reinicia automáticamente. Un parche instalado pero con el servicio sin reiniciar **sigue siendo vulnerable**, y el escáner lo seguirá detectando.

#### 6.8.2 SSH: acceso por contraseña y root

Primero comprobamos que podemos entrar con clave (6.4) para no quedarnos fuera. Luego:

```bash
$ sudo rm /etc/ssh/sshd_config.d/00-lab-inseguro.conf
$ printf 'PermitRootLogin no\nPasswordAuthentication no\nPubkeyAuthentication yes\nMaxAuthTries 3\n' | sudo tee /etc/ssh/sshd_config.d/10-endurecido.conf
$ sudo sshd -t && sudo systemctl reload ssh
```

- Borramos la configuración insegura del laboratorio y escribimos otra con: sin acceso directo de root, solo claves, y máximo de 3 intentos por conexión.
- `sshd -t` **comprueba la sintaxis** de la configuración sin aplicarla; el `&&` solo recarga el servicio si la comprobación es correcta. Así evitamos dejar SSH roto.
- **Mantener siempre una sesión SSH abierta mientras se prueba la nueva desde otra terminal.**

#### 6.8.3 nginx: versión visible y cabeceras de seguridad

```bash
$ sudo tee /etc/nginx/conf.d/seguridad.conf <<'EOF'
server_tokens off;
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Content-Security-Policy "default-src 'self'" always;
EOF
$ sudo nginx -t && sudo systemctl reload nginx
$ curl -sI http://<IP_LAB> | head -n 12
```

- `server_tokens off` oculta la versión de nginx en las cabeceras y páginas de error (menos información para un atacante que busca versiones vulnerables).
- `X-Frame-Options` impide que otra web incruste la nuestra en un marco (*clickjacking*); `X-Content-Type-Options: nosniff` evita que el navegador adivine tipos de contenido; `Referrer-Policy` limita qué se envía en el encabezado *Referer*; `Content-Security-Policy` restringe de dónde carga recursos la página. `always` hace que se envíen también en respuestas de error.
- `nginx -t` comprueba la configuración. `curl -sI` pide solo las cabeceras (`-s` silencioso, `-I` método HEAD) para verificarlas.
- Para el hallazgo de **credenciales en texto claro** la solución real es servir el sitio por **HTTPS** (certificado de Let's Encrypt si tiene dominio público; en el laboratorio uno autofirmado con `openssl`) y redirigir HTTP a HTTPS. Con HTTPS se añade también `Strict-Transport-Security`.

#### 6.8.4 PostgreSQL: contraseña y exposición

```bash
$ sudo -u postgres psql -c "ALTER USER postgres WITH PASSWORD '<CLAVE_LARGA_Y_UNICA>';"
$ sudo sed -i '/0.0.0.0\/0/d' /etc/postgresql/17/main/pg_hba.conf
$ echo 'host all all 192.168.122.0/24 scram-sha-256' | sudo tee -a /etc/postgresql/17/main/pg_hba.conf
$ sudo systemctl restart postgresql
```

- Cambiamos la contraseña por una larga y única.
- `sed -i '/patrón/d'` **borra** la línea que abría PostgreSQL a todo internet.
- La nueva regla de `pg_hba.conf` solo admite conexiones de la red del laboratorio y con `scram-sha-256`, el método de contraseña moderno (mucho más seguro que `md5`).
- Si no hace falta acceso remoto, lo más seguro es `listen_addresses = 'localhost'` y quitar la regla. Un cortafuegos también debe limitar el puerto 5432.

#### 6.8.5 FTP anónimo, SNMP, TCP timestamps

```bash
$ sudo sed -i 's/^anonymous_enable=.*/anonymous_enable=NO/' /etc/vsftpd.conf && sudo systemctl restart vsftpd
$ sudo sed -i 's/^agentaddress.*/agentaddress 127.0.0.1,[::1]/' /etc/snmp/snmpd.conf && sudo systemctl restart snmpd
$ echo 'net.ipv4.tcp_timestamps = 0' | sudo tee /etc/sysctl.d/99-endurecimiento.conf && sudo sysctl --system
```

- FTP anónimo: lo desactivamos. Si el FTP no es necesario, lo desinstalamos (`apt purge vsftpd`); es un protocolo sin cifrar.
- SNMP: el agente vuelve a escuchar solo en local. Si se necesita en red, se usa SNMPv3 con autenticación y cifrado, no comunidades como `public`.
- `sysctl net.ipv4.tcp_timestamps = 0` desactiva las marcas de tiempo TCP: lo guardamos en `/etc/sysctl.d/` para que persista y `sysctl --system` lo aplica. Es un hallazgo de gravedad baja que muchas organizaciones aceptan; conviene indicar en el informe si se acepta o se corrige.

#### 6.8.6 Cortafuegos: cerrar lo que no se usa

```bash
$ sudo apt install -y ufw
$ sudo ufw default deny incoming
$ sudo ufw default allow outgoing
$ sudo ufw allow from 192.168.122.0/24 to any port 22 proto tcp
$ sudo ufw allow 80/tcp
$ sudo ufw enable
$ sudo ufw status verbose
```

- `ufw` (*Uncomplicated Firewall*) es una interfaz sencilla sobre el cortafuegos del kernel. `default deny incoming` bloquea todo lo entrante salvo lo que se permita; `allow from <red> to any port 22` limita SSH a la red de laboratorio; `allow 80/tcp` deja la web.
- **Antes de `ufw enable` asegurarse de haber permitido SSH**, o perderemos el acceso a la VM.
- Resultado esperado: tras el cortafuegos el escáner ya no ve los puertos cerrados (PostgreSQL, FTP, SNMP) y esos hallazgos desaparecen. Un cortafuegos **no sustituye** a arreglar el servicio: si se abre el puerto otra vez, la vulnerabilidad vuelve.

#### 6.8.7 Metasploitable y Log4Shell (casos especiales)

- **Metasploitable 2** está construida con software de 2008 y no se «parchea»: la solución real es **retirar o sustituir** cada servicio. Los hallazgos típicos (por ejemplo la puerta trasera de *vsftpd 2.3.4*, CVE-2011-2523, o `usermap_script` de Samba, CVE-2007-2447) se documentan con su CVE, el impacto y la solución indicada por el fabricante: actualizar a una versión corregida. En el informe lo expresamos así: «En un entorno real esta máquina se reemplazaría».
- **Servidor de Minecraft (R4):** escaneamos con una configuración que incluya las pruebas de Log4Shell sobre su IP y puerto. La corrección real es actualizar el servidor y Log4j a una versión corregida (2.17.1 o posterior); como mitigación temporal en versiones afectadas 2.10 en adelante existe el parámetro de Java `-Dlog4j2.formatMsgNoLookups=true`. Coordinamos con el compañero de R4 para no duplicar trabajo.

#### 6.8.8 Verificar el parche con un nuevo escaneo

1. Volvemos a lanzar **la misma tarea** (no una nueva) para que los informes sean comparables.
2. Abrimos el nuevo informe y lo comparamos con el anterior mediante el informe *delta* (6.5). Los hallazgos corregidos aparecen como *gone*; los que quedan, como *same*.
3. Si algún resultado sigue apareciendo, comprobamos que el servicio se reinició, que el parche se aplicó al servicio correcto y que el escáner no cachea una detección antigua (repetir con un nuevo objetivo).
4. Guardamos ambos informes (antes y después) en PDF.

### 6.9 Lo que hicimos nosotros: parcheo de `Appweb` paso a paso

Partimos del informe de la prueba 3 (`P3 Appweb autenticado`). Antes de tocar nada hicimos una **instantánea** de la VM, para poder volver atrás si algo se rompía:

```
virsh -c qemu:///system snapshot-create-as Appweb antes-de-parchear "Estado de Appweb antes de la practica de OpenVAS"
virsh -c qemu:///system snapshot-list Appweb
```

- `snapshot-create-as` guarda el estado completo de la VM (disco y memoria) con el nombre `antes-de-parchear`. Solo funciona si el disco es `qcow2`; lo comprobamos con `virsh domblklist Appweb` y `qemu-img info`.
- Para deshacer todos los cambios: `virsh -c qemu:///system snapshot-revert Appweb antes-de-parchear`.

Aplicamos **cuatro correcciones**. Para cada una explicamos dónde lo dice el informe, qué propone, por qué lo hacemos de esa forma y cómo comprobamos que ha funcionado.

> **Cómo leer un resultado en la web.** Abrimos el informe (*Scans → Reports*), pestaña *Results*, y hacemos clic en el nombre de la vulnerabilidad. Se despliegan estos apartados: *Summary* (qué es), *Detection Result* (la prueba concreta que encontró en nuestra máquina), *Insight* (explicación técnica), *Detection Method* (cómo lo comprobó, con su QoD), *Impact* (qué podría hacer un atacante) y *Solution* (qué hacer, con su tipo: *VendorFix* = hay actualización oficial; *Mitigation* = cambiar la configuración).

#### Corrección 1: algoritmos MAC débiles en SSH

**Dónde lo dice el informe.** Resultado *Weak MAC Algorithm(s) Supported (SSH)*, puerto `22/tcp`, gravedad 2,6, QoD 80 %.

| Apartado | Qué pone |
| --- | --- |
| *Summary* | *The remote SSH server is configured to allow / support weak MAC algorithm(s).* (el servidor SSH admite algoritmos MAC débiles) |
| *Detection Result* | Lista los algoritmos débiles encontrados: `umac-64-etm@openssh.com` y `umac-64@openssh.com`, en las dos direcciones |
| *Detection Method* | Pregunta al servidor qué algoritmos admite y marca como débiles los basados en MD5, los de 96 bits, los de **64 bits** y el algoritmo `none` |
| *Solution* (*Mitigation*) | *Disable the reported weak MAC algorithm(s).* (desactivar los algoritmos indicados) |

**Qué significa.** Cada paquete que viaja por SSH lleva un «sello» (MAC) que demuestra que nadie lo ha modificado por el camino. Un sello de 64 bits es corto y, en teoría, más fácil de falsificar. Los de 128 bits o más se consideran seguros.

**Paso 1. Ver qué hay configurado ahora**, para no pisar ninguna configuración existente:

```
ssh app 'sudo sshd -T | grep -E "^macs"'
ssh app 'ls -l /etc/ssh/sshd_config.d/; sudo grep -rniE "^\s*macs" /etc/ssh/sshd_config /etc/ssh/sshd_config.d/'
```

- `sshd -T` muestra la configuración **real** que está usando SSH, con todos los valores, incluidos los de fábrica.
- El `grep` busca si algún fichero fija ya los MAC. No había ninguno: se usaba la lista de fábrica, que efectivamente incluía los dos `umac-64`.

**Paso 2. Copia de seguridad y corrección:**

```
ssh app 'sudo cp -a /etc/ssh /etc/ssh.bak-openvas && echo "MACs -umac-64-etm@openssh.com,umac-64@openssh.com" | sudo tee /etc/ssh/sshd_config.d/10-endurecido.conf && sudo sshd -t && sudo systemctl reload ssh && echo "RECARGADO OK"'
```

- `cp -a` copia la carpeta de configuración conservando permisos.
- Escribimos la corrección en un **fichero nuevo** dentro de `sshd_config.d/` en lugar de editar el `sshd_config` principal: el cambio queda aislado y se deshace borrando ese fichero.
- `MACs -lista`: el signo `-` significa «la lista de fábrica **menos** estos». Es el cambio más pequeño posible, solo quitamos lo que dice el informe. (La receta general de 6.8.2 cambia más cosas, como prohibir el acceso por contraseña; no la aplicamos entera porque el informe no lo señalaba y podía afectar a la otra práctica que usa esta máquina.)
- `sshd -t` comprueba la sintaxis **sin aplicar nada**. Gracias a los `&&`, si hubiera un error no se recargaría el servicio y no perderíamos el acceso.

**Paso 3. Comprobar**, desde dentro, desde fuera y que seguimos pudiendo entrar:

```
ssh app 'sudo sshd -T | grep -E "^macs"'
nmap -Pn -p22 --script ssh2-enum-algos 192.168.122.245
ssh app 'echo "ssh app sigue funcionando"'
```

- `nmap --script ssh2-enum-algos` le pregunta al servidor SSH qué algoritmos admite, igual que hace OpenVAS.
- Resultado: la lista pasa de 10 a **8 algoritmos MAC** y ya no aparece ningún `umac-64`. El acceso sigue funcionando.

#### Corrección 2: marcas de tiempo TCP

**Dónde lo dice el informe.** Resultado *TCP Timestamps Information Disclosure*, `general/tcp`, gravedad 2,6, QoD 80 %.

| Apartado | Qué pone |
| --- | --- |
| *Summary* | *The remote host implements TCP timestamps and therefore allows to compute the uptime.* (la máquina usa marcas de tiempo TCP y eso permite calcular cuánto tiempo lleva encendida) |
| *Detection Method* | Envía dos paquetes con un segundo de diferencia y lee la marca de tiempo de cada respuesta |
| *Detection Result* | *Packet 1: 4014704865 / Packet 2: 439530435*: las dos marcas que obtuvo |
| *Impact* | Se puede calcular el tiempo que lleva encendida la máquina |
| *Solution* (*Mitigation*) | Añadir `net.ipv4.tcp_timestamps = 0` a `/etc/sysctl.conf` y ejecutar `sysctl -p` |

**Qué significa.** Las marcas de tiempo son un dato que el sistema añade a las conexiones. Con dos de ellas se puede deducir desde cuándo está encendida la máquina. A un atacante le sirve para saber si se ha reiniciado tras una actualización del núcleo: si lleva meses encendida, probablemente no.

**Por qué no lo hacemos exactamente como dice el informe.** En Debian 13 los ajustes del núcleo no se ponen en `/etc/sysctl.conf`, sino en ficheros sueltos dentro de `/etc/sysctl.d/`, que se aplican en cada arranque. Es lo que hace nuestra receta 6.8.5.

```
ssh app 'echo "antes: $(sudo sysctl -n net.ipv4.tcp_timestamps)"; echo "net.ipv4.tcp_timestamps = 0" | sudo tee /etc/sysctl.d/99-endurecimiento.conf && sudo sysctl --system >/dev/null && echo "después: $(sudo sysctl -n net.ipv4.tcp_timestamps)"'
```

- `sysctl -n` muestra solo el valor del ajuste (`1` = activado, `0` = desactivado).
- `tee` escribe el fichero; `sysctl --system` aplica todos los ficheros de configuración sin reiniciar.
- Usamos `sudo sysctl` porque `sysctl` está en `/usr/sbin`, que no está en la ruta de búsqueda de un usuario normal (la misma situación que vimos con Redis en 3.11).
- Resultado: `antes: 1` → `después: 0`.

> **Una comprobación que no nos sirvió.** Intentamos ver desde el anfitrión, con `ss -ti`, si las conexiones a la VM llevaban la opción `ts`. Ni siquiera aparecía en una VM sin parchear (`debian13`), así que en nuestro laboratorio ese método no es fiable y no lo usamos como prueba. La comprobación válida es el nuevo escaneo de OpenVAS (más abajo).

#### Corrección 3: actualizaciones de seguridad pendientes

**Dónde lo dice el informe.** En este caso **no lo dice**: el informe no listaba estos paquetes como vulnerables. Lo descubrimos con `apt list --upgradable`, que mostraba paquetes del repositorio `stable-security` (las actualizaciones de seguridad de Debian). Es una corrección **preventiva** (receta 6.8.1). Lo indicamos para ser exactos: este cambio no hará desaparecer ningún resultado del informe.

**Paso 1. Ver qué se va a actualizar antes de hacerlo:**

```
ssh app 'sudo apt-get update -qq && apt list --upgradable 2>/dev/null | tail -n +2'
```

Había 7 paquetes: `libbrotli1` (compresión que usa el servidor web), seis de `libheif` (lectura de imágenes, que puede usar WordPress) y `tzdata` (zonas horarias).

**Paso 2. Instalar:**

```
ssh app 'sudo DEBIAN_FRONTEND=noninteractive apt-get full-upgrade -y'
```

- `DEBIAN_FRONTEND=noninteractive` evita que `apt` se quede esperando respuestas en pantalla, porque lo ejecutamos a distancia.
- Resultado: `7 actualizados` y, después, ningún paquete pendiente.

**Paso 3. ¿Hay que reiniciar algo?** Un parche instalado no protege si el programa que usaba la librería vieja sigue en marcha. Lo comprueba `needrestart` (ya estaba instalado, en `/usr/sbin`):

```
ssh app 'sudo needrestart -b -r l'
```

- `-b` da la respuesta en un formato breve y `-r l` solo **lista**, sin reiniciar nada.
- Respuesta: `NEEDRESTART-KSTA: 1` (el núcleo en uso es el último instalado, no hace falta reiniciar la VM) y `NEEDRESTART-SVC: php8.4-fpm.service` (el PHP del WordPress tenía cargada la librería vieja).

**Paso 4. Reiniciar solo PHP y comprobar que la web sigue funcionando:**

```
ssh app 'sudo systemctl restart php8.4-fpm && systemctl is-active php8.4-fpm && sudo needrestart -b -r l | grep -c SVC'
curl -s -o /dev/null -w "web Appweb: HTTP %{http_code}\n" http://192.168.122.245/
```

Resultado: `active`, `0` servicios pendientes y la web responde `HTTP 200`.

#### Corrección 4: marcar los falsos positivos (*overrides*)

**Dónde lo dice el informe.** Resultado *Sudo 1.8.8 - 1.9.17 Local Privilege Escalation Vulnerability* (gravedad 8,8). Lo mismo ocurre con *Sudo 1.9.14 - 1.9.17* (7,8) y con *Nginx 0.7.22 - 1.29.0 Information Disclosure* (3,7).

| Apartado | Qué pone |
| --- | --- |
| *Detection Result* | *Installed version: 1.9.16p2 / Fixed version: 1.9.17p1* |
| *Detection Method* | *Checks if a vulnerable version is present on the target host.* Solo compara números de versión; por eso el **QoD es del 30 %** |
| *Solution* (*VendorFix*) | *Update to version 1.9.17p1 or later.* (actualizar a la 1.9.17p1 o posterior) |

**Por qué no seguimos la solución.** En Debian 13 no existe esa versión, y no hace falta: Debian copió la corrección a su versión (*backport*), como comprobamos en la prueba 3 leyendo `/usr/share/doc/sudo/changelog.Debian.gz`. No hay nada que arreglar, así que, como indica 6.7.3, el resultado se **documenta y se marca como falso positivo** con una nota. El resultado no se borra: sigue en el informe con su etiqueta, y quien lo lea sabe que alguien lo comprobó.

**En la web:**

1. En el informe, clic en el resultado.
2. Icono de *override* (*Add Override*) en la parte superior del detalle.
3. *New Severity*: **False Positive**; *Hosts*: `192.168.122.245` (para que no oculte el resultado en otras máquinas); *Text*: la explicación y dónde lo comprobamos.
4. *Save*. A partir de ahí, en los informes con *Apply Overrides* activado, ese resultado aparece como *False Positive* y no cuenta en la gravedad.

**Desde la terminal.** Primero obtenemos el identificador de cada prueba (OID), que aparece en el detalle del resultado o en el XML del informe:

| OID | Prueba |
| --- | --- |
| `1.3.6.1.4.1.25623.1.0.119060` | Sudo 1.8.8 - 1.9.17 (CVE-2025-32462) |
| `1.3.6.1.4.1.25623.1.0.119061` | Sudo 1.9.14 - 1.9.17 (CVE-2025-32463) |
| `1.3.6.1.4.1.25623.1.0.124888` | Nginx 0.7.22 - 1.29.0 (CVE-2025-53859) |

```
/mnt/midisco/greenbone/scripts/gmp.sh '<create_override><nvt oid="1.3.6.1.4.1.25623.1.0.119060"/><hosts>192.168.122.245</hosts><new_severity>-1</new_severity><text>Falso positivo: Debian 13 corrigió CVE-2025-32462 en sudo 1.9.16p2-3+deb13u1 (backport). Comprobado en /usr/share/doc/sudo/changelog.Debian.gz: "add upstream patch for CVE-2025-32462". El escáner solo compara la versión (QoD 30).</text></create_override>'
```

- `new_severity -1` es el valor interno de *False Positive*.
- Repetimos la orden con los otros dos OID y su texto correspondiente.

#### Comprobación final: nuevo escaneo e informe *delta*

Volvemos a lanzar **la misma tarea** `P3 Appweb autenticado`, para que los dos informes sean comparables (6.8.8):

```
/mnt/midisco/greenbone/scripts/gmp.sh '<start_task task_id="ID_DE_LA_TAREA_P3"/>'
```

Cuando termina, en la web: *Scans → Reports*, seleccionamos como referencia el informe anterior (icono *Delta*) y después el nuevo. Cada resultado aparece como *New*, *Same*, *Gone* (desaparecido = corregido) o *Changed*.

> **Resultado en nuestro laboratorio.** Comparamos el informe del 1 de noviembre a las 13:22 (antes) con el de las 14:39 (después). El informe *delta* clasifica los 55 resultados así: **2 *Gone***, 2 *Changed* y 51 *Same*.
>
> | Estado en el *delta* | Resultado | Qué significa |
> | --- | --- | --- |
> | **Gone** | *Weak MAC Algorithm(s) Supported (SSH)* | Corrección 1 confirmada |
> | **Gone** | *TCP Timestamps Information Disclosure* | Corrección 2 confirmada |
> | Same, con gravedad *False Positive* | Sudo ×2 y Nginx | Corrección 4: los *overrides* se aplican |
> | Changed | *SSH Protocol Algorithms Supported* (informativo) | Normal: ha cambiado la lista de algoritmos SSH |
> | Changed | *WordPress `wp-cron.php` Accessible* | Mismo hallazgo con otra respuesta del servidor; sin corregir (riesgo aceptado, ver abajo) |
>
> Recuento por gravedad, con los *overrides* aplicados:
>
> | | Alta | Media | Baja | Falso positivo | Log |
> | --- | --- | --- | --- | --- | --- |
> | Antes de parchear (sin *overrides*) | 3 | 8 | 7 | 0 | 37 |
> | Antes de parchear (con *overrides*) | 1 | 8 | 6 | 3 | 37 |
> | **Después de parchear (con *overrides*)** | **1** | **8** | **4** | **3** | **37** |
>
> Con estas correcciones, la gravedad máxima de la máquina baja de **8,8 a 7,8**. Esa «Alta» que queda es *Intel BIOS Privilege Escalation (INTEL-SA-00686)*, con un **QoD del 1 %**: depende del procesador físico y de su BIOS, no de la máquina virtual, así que no se corrige desde Debian. Se trataría igual que los falsos positivos (con un *override*) o actualizando la BIOS del equipo físico.
>
> **Riesgos que aceptamos y por qué:**
>
> | Hallazgo | Motivo |
> | --- | --- |
> | *Terrapin Attack* (5,9) | OpenSSH 10.0 ya incluye la defensa (*strict KEX*); el aviso se basa en los algoritmos que se ofrecen |
> | *OpenSSH CVE-2016-20012* (5,3) | No existe corrección: OpenSSH considera que no es un fallo. Solo revela si una clave pública es válida |
> | *WordPress `wp-cron.php` accesible* (5,3) | Es el WordPress de otra práctica; restringirlo podría afectar a su funcionamiento |
> | *Intel CPU* (5,5 a 6,5, QoD 1 %) | Dependen del procesador físico |
> | *ICMP Timestamp Reply* (2,1) | Gravedad muy baja; lo cerraríamos con el cortafuegos (receta 6.8.6) |
> | *OpenSSH < 10.1* (2,4) | Debian publica las correcciones de seguridad en su versión 10.0; lo revisamos en las próximas actualizaciones |

### 6.10 Los informes en PDF que descargamos desde la web

Además de trabajar desde la consola, descargamos dos informes en PDF desde la web de Greenbone. Están guardados en `/mnt/midisco/Claude/reportes/`.

**Cómo se descarga un informe en PDF desde la web, paso a paso:**

1. Entramos en **Scans → Reports** y pulsamos la fecha del informe que nos interesa.
2. Arriba a la derecha pulsamos el icono de **descarga** (la flecha hacia abajo).
3. En la ventana que aparece elegimos el formato **PDF** y pulsamos **OK**.
4. El navegador guarda un fichero llamado `report-<identificador>.pdf`.

| Fichero | Tarea | Qué escaneamos | Duración |
| --- | --- | --- | --- |
| `report-cffc9bfd-3cd9-41f7-a5c1-22d14547e671.pdf` (25 páginas) | P3 Appweb autenticado (después de parchear) | 192.168.122.245 con el usuario `escaneo` | 13:06 → 13:38 UTC (≈ 32 min) |
| `report-0fe5964c-6415-4711-94ec-b9de29e020a5.pdf` (44 páginas) | Casa-coreo | Nuestra red de casa 192.168.1.0/24 | 11:51 → 13:05 UTC (≈ 1 h 14 min) |

> **Ojo con la hora:** el PDF siempre muestra las horas en **UTC**. En España, en noviembre, sumamos **una hora** (13:06 UTC son las 14:06 en Madrid).

#### 6.10.1 Por qué el PDF muestra menos resultados que la web

Al abrir el PDF de Appweb vemos solo **1 resultado Low y 37 Log**, mientras que en la consola contamos más resultados (medios y bajos). No es un error. Al principio del PDF el propio informe explica el motivo:

- `Only results with a minimum QoD of 70 are shown.` → solo aparecen los resultados con una **fiabilidad (QoD) del 70 % o más**. Los que OpenVAS deduce solo por el número de versión (QoD 30 %, por ejemplo Terrapin o el BIOS de Intel) quedan fuera.
- `Overrides are off.` → el PDF **no aplica las anulaciones** (overrides). Por eso no aparecen nuestros tres falsos positivos marcados.
- `This report contains all 38 results selected by the filtering described above. Before filtering there were 54 results.` → hay 54 resultados en total, pero el filtro deja 38.

La web aplica este filtro por defecto (`min_qod=70`) y el PDF se genera **con el mismo filtro que tengamos puesto en pantalla**. Si queremos el informe completo:

1. En la página del informe, en la caja **Filter**, escribimos `apply_overrides=1 min_qod=0 levels=chmlgf rows=-1` y pulsamos **Update** (la lupa).
2. Comprobamos que el número de resultados ha subido.
3. Descargamos el PDF otra vez.

La página **1.1 Host Authentications** del PDF de Appweb también es útil: muestra `SSH Success Protocol SSH, Port 22, User escaneo`. Es la prueba de que **el escaneo autenticado funcionó**.

#### 6.10.2 Qué encontramos en la red de casa (tarea «Casa-coreo»)

Esta tarea la creamos nosotros desde la web, para ver qué pasa al escanear una red real (con el router y los dispositivos de casa) en lugar del laboratorio. **Solo se debe escanear una red propia o una red para la que tengamos permiso.**

OpenVAS encontró **4 equipos**. Ninguno tiene vulnerabilidades críticas ni altas:

| Equipo | Qué parece ser (según OpenVAS) | Servicios vistos | Medium | Low | Log |
| --- | --- | --- | --- | --- | --- |
| 192.168.1.135 | Debian 13 (vsftpd 3.0.5, OpenSSH 10.0p2, nginx) | 21, 22, 80, 3389 | 2 | 3 | 20 |
| 192.168.1.1 | El router (Linux) | 53, 80, 443 | 1 | 1 | 32 |
| 192.168.1.131 | Dispositivo Linux con una web en el 8080 | 8080 | 0 | 1 | 10 |
| 192.168.1.139 | Dispositivo FreeBSD / Apple | — | 0 | 0 | 4 |
| **Total** | | | **3** | **5** | **66** |

**Los hallazgos uno a uno, y qué haríamos con cada uno:**

| Gravedad | Hallazgo | Equipo | Qué significa en lenguaje sencillo | Solución que propone OpenVAS |
| --- | --- | --- | --- | --- |
| Medium 4.8 | *FTP Unencrypted Cleartext Login* (21/tcp) | .135 | El servidor FTP deja iniciar sesión sin cifrar. Alguien que escuche la red podría ver el usuario y la contraseña. | **Mitigation:** activar FTPS (`ssl_enable=YES` en vsftpd) o usar SFTP, que va por SSH y ya está cifrado. |
| Medium 4.8 | *Cleartext Transmission of Sensitive Information via HTTP* (80/tcp) | .135 y .1 | Hay un formulario con contraseña que se envía por HTTP sin cifrar. | **Workaround:** servir esa página solo por HTTPS. En el router: entrar siempre por `https://` y, si lo permite, desactivar la administración por HTTP. |
| Low 2.6 | *Weak MAC Algorithm(s) Supported (SSH)* (22/tcp) | .135 | **Es el mismo hallazgo que corregimos en Appweb** (parche 1, apartado 6.9). | El mismo fichero `10-endurecido.conf` que usamos en Appweb. |
| Low 2.6 | *TCP Timestamps Information Disclosure* | .135 y .1 | Igual que en Appweb (parche 2). | En .135, el mismo `sysctl`. En el router no se puede cambiar: **riesgo aceptado**. |
| Low 2.1 | *ICMP Timestamp Reply Information Disclosure* | .135 y .131 | El equipo dice la hora si se le pregunta. Gravedad muy baja. | Filtrar ICMP *timestamp* en el cortafuegos, o aceptarlo. |

**Conclusiones que sacamos:**

- Los mismos fallos que vimos en el laboratorio (MAC débiles y TCP Timestamps) aparecen en equipos reales. Por eso los parches del apartado 6.9 sirven para cualquier Debian.
- En dispositivos que no controlamos, como el router o los aparatos de la marca, muchas veces no podemos aplicar el parche. Lo correcto es **documentarlo como riesgo aceptado** y, si existe, instalar la actualización del fabricante.
- Escanear una red de casa es **lento** (1 h 14 min para 4 equipos) porque OpenVAS prueba muchos puertos y servicios. Por eso en el laboratorio usamos nuestra lista reducida `Puertos laboratorio`.

## 7. Automatización desde la línea de comandos (gvm-cli)

Todo lo que hacemos en la web se puede hacer por línea de comandos mediante el protocolo **GMP**, que habla con gvmd en XML. Es útil para repetir pruebas, programar con `cron` o integrar el escáner en scripts.

### 7.1 Entrar en la herramienta

**Método A (contenedores):** el compose incluye un contenedor con las herramientas.

```bash
$ sudo docker compose -f $DOWNLOAD_DIR/compose.yaml -p greenbone-community-edition run --rm gvm-tools
$ gvm-cli --gmp-username admin socket --pretty --xml "<get_version/>"
```

- `run --rm gvm-tools` abre una terminal en un contenedor temporal (`--rm` lo borra al salir) que ya está conectado al socket de gvmd.
- `gvm-cli` envía un mensaje XML a gvmd. `socket` indica que se conecta por socket Unix. `--pretty` formatea la respuesta. Pregunta la contraseña de `admin`. Si todo va bien devuelve la versión del protocolo GMP.

**Método A, forma que usamos nosotros: un pequeño script.** Para no tener que entrar en una terminal del contenedor cada vez, creamos `/mnt/midisco/greenbone/scripts/gmp.sh`, que lanza el contenedor oficial `gvm-tools`, le pasa una orden y se borra solo:

```
mkdir -p /mnt/midisco/greenbone/scripts
cat > /mnt/midisco/greenbone/scripts/gmp.sh <<'EOF'
#!/bin/bash
# Envía una orden GMP (XML) a gvmd usando el contenedor oficial gvm-tools.
# Usuario y contraseña se leen de ~/.config/gvm-tools.conf (chmod 600).
# El contenedor se ejecuta con nuestro propio usuario para poder leer ese fichero.
# Uso: gmp.sh '<get_version/>'
exec docker run --rm -i --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v greenbone-community-edition_gvmd_socket_vol:/run/gvmd \
  -v "$HOME/.config/gvm-tools.conf:/tmp/gvm-tools.conf:ro" \
  --entrypoint gvm-cli \
  registry.community.greenbone.net/community/gvm-tools:latest \
  --config /tmp/gvm-tools.conf \
  socket --socketpath /run/gvmd/gvmd.sock --xml "$1"
EOF
chmod +x /mnt/midisco/greenbone/scripts/gmp.sh
/mnt/midisco/greenbone/scripts/gmp.sh '<get_version/>'
```

- `docker run --rm` crea un contenedor temporal que se borra al terminar.
- `--user "$(id -u):$(id -g)"` lo ejecuta con nuestro usuario, para que pueda leer nuestro fichero de credenciales (ver incidencia en 3.11).
- `-v greenbone-community-edition_gvmd_socket_vol:/run/gvmd` conecta el contenedor al «enchufe» (*socket*) por el que se habla con `gvmd`.
- `-v ...gvm-tools.conf:...:ro` le presta nuestro fichero de credenciales en modo solo lectura (`ro`).
- Nuestro usuario está en el grupo `docker`, así que no hace falta `sudo`.

Respuesta en nuestro equipo: `<get_version_response status="200" status_text="OK"><version>22.7</version></get_version_response>`.

### 7.2 Guardar las credenciales para no escribirlas siempre

```bash
$ mkdir -p ~/.config && cat > ~/.config/gvm-tools.conf <<'EOF'
[gmp]
username=automatizacion
password=<CLAVE>
EOF
$ chmod 600 ~/.config/gvm-tools.conf
```

- `gvm-tools` lee este fichero y ya no pide la contraseña. Por seguridad creamos en GSA (*Administration → Users*) un usuario **específico para automatizar** en lugar de usar `admin`, y protegemos el fichero con `chmod 600`.

**Cómo lo hicimos nosotros.** Creamos el usuario `automatizacion` desde la línea de comandos, con una contraseña aleatoria que nadie tiene que escribir ni recordar, y con el rol `User` (no administrador):

```
P=$(openssl rand -base64 18 | tr -d '/+='); umask 077; printf '[gmp]\nusername=automatizacion\npassword=%s\n' "$P" > ~/.config/gvm-tools.conf; docker exec -u gvmd greenbone-community-edition-gvmd-1 gvmd --create-user=automatizacion --password="$P" --role=User
```

- `openssl rand -base64 18` genera una contraseña aleatoria; `tr -d '/+='` le quita los símbolos que pueden dar problemas.
- `umask 077` hace que el fichero se cree ya con permisos `600`.
- `printf` escribe el fichero `~/.config/gvm-tools.conf` con el formato de 7.2.
- `gvmd --create-user ... --role=User` crea el usuario dentro de Greenbone. Respuesta: `User created.`

> Las tareas que crea este usuario son suyas: para verlas en la web, iniciamos sesión en GSA con `automatizacion` (la contraseña está en `~/.config/gvm-tools.conf`).

### 7.3 Operaciones habituales

Identificadores que necesitaremos (son fijos en el feed de la comunidad; se pueden consultar con los comandos `get_*`):

| Elemento | UUID |
| --- | --- |
| Lista de puertos «All IANA assigned TCP» | `33d0cd82-57c6-11e1-8ed1-406186ea4fc5` |
| Config «Full and fast» | `daba56c8-73ec-11df-a475-002264764cea` |
| Escáner «OpenVAS Default» | `08b69003-5fc2-4037-a479-93b440211c73` |
| Formato de informe PDF | `c402cc3e-b531-11e1-9163-406186ea4fc5` |
| Formato de informe XML | `a994b278-1f62-11e1-96ac-406186ea4fc5` |

En nuestra instalación comprobamos todos estos identificadores con `gmp.sh '<get_configs/>'`, `<get_port_lists/>`, `<get_scanners/>` y `<get_report_formats/>`, y coinciden.

Si algún identificador falla, se obtiene el correcto con `<get_port_lists/>`, `<get_configs/>`, `<get_scanners/>` o `<get_report_formats/>`.

```bash
# Crear un objetivo
$ gvm-cli --gmp-username admin socket --pretty --xml '<create_target><name>lab-cli</name><hosts>192.168.122.10</hosts><port_list id="33d0cd82-57c6-11e1-8ed1-406186ea4fc5"/><alive_tests>ICMP Ping</alive_tests></create_target>'

# Crear la tarea con el id del objetivo devuelto
$ gvm-cli --gmp-username admin socket --pretty --xml '<create_task><name>tarea-cli</name><config id="daba56c8-73ec-11df-a475-002264764cea"/><target id="<ID_OBJETIVO>"/><scanner id="08b69003-5fc2-4037-a479-93b440211c73"/></create_task>'

# Lanzarla y consultar su estado
$ gvm-cli --gmp-username admin socket --pretty --xml '<start_task task_id="<ID_TAREA>"/>'
$ gvm-cli --gmp-username admin socket --pretty --xml '<get_tasks task_id="<ID_TAREA>"/>'
```

- Cada comando es un mensaje XML: `create_target` define nombre, hosts, lista de puertos y *Alive Test*; `create_task` enlaza una configuración, un objetivo y un escáner; `start_task` la ejecuta; `get_tasks` muestra el estado y el progreso.
- Las comillas simples externas evitan que la shell interprete las dobles internas del XML.
- Para ver todas las respuestas en texto legible usamos `--pretty`; sin ella obtenemos el XML plano.

Descargar un informe en PDF (la respuesta viene codificada en base64 y la decodificamos):

```bash
$ gvm-cli --gmp-username admin socket --xml '<get_reports report_id="<ID_INFORME>" format_id="c402cc3e-b531-11e1-9163-406186ea4fc5" details="1"/>' > /tmp/informe.xml
$ xmllint --xpath 'string(//report/report_format/../text())' /tmp/informe.xml | base64 -d > /mnt/midisco/greenbone/informes/informe.pdf
```

- Es la parte más delicada: el contenido del PDF llega codificado dentro del XML. Si `xmllint` (paquete `libxml2-utils`) no da el resultado esperado, es más sencillo exportar el PDF desde la web (6.7.4) o usar `gvm-script` con un script de exportación de la colección `gvm-tools`.

### 7.4 Lanzar un escaneo cada noche con cron

```bash
$ crontab -e
# línea a añadir (3:00 cada día):
0 3 * * * /mnt/midisco/greenbone/scripts/gmp.sh '<start_task task_id="<ID_TAREA>"/>' >> /mnt/midisco/greenbone/cron.log 2>&1
```

- `crontab -e` edita las tareas programadas del usuario. Los cinco primeros campos son minuto, hora, día del mes, mes y día de la semana (`0 3 * * *` = a las 03:00 todos los días). Redirigimos la salida a un registro (`>>` añade, `2>&1` incluye los errores).
- La programación nativa de GSA (sección 5.10) es más sencilla y es la que recomendamos; `cron` es una alternativa si necesitamos lógica adicional.

### 7.5 Esperar a que termine una tarea

Para no tener que mirar la web continuamente, creamos un segundo script que consulta el estado cada minuto y termina cuando la tarea acaba:

```
cat > /mnt/midisco/greenbone/scripts/esperar_tarea.sh <<'EOF'
#!/bin/bash
# Espera a que una tarea termine. Uso: esperar_tarea.sh <task_id>
G=/mnt/midisco/greenbone/scripts/gmp.sh
while :; do
  r=$($G "<get_tasks task_id=\"$1\"/>")
  st=$(echo "$r" | grep -o '<status>[^<]*' | head -1 | cut -d'>' -f2)
  pr=$(echo "$r" | grep -o '<progress>[^<]*' | head -1 | cut -d'>' -f2)
  echo "$(date +%H:%M) $st $pr%"
  case "$st" in Done|Stopped|Interrupted) break;; esac
  sleep 60
done
EOF
chmod +x /mnt/midisco/greenbone/scripts/esperar_tarea.sh
```

- `while :` repite sin fin; `case ... break` sale cuando el estado es *Done*, *Stopped* o *Interrupted*.
- `grep -o '<status>[^<]*'` saca el estado de la respuesta XML, y `cut` se queda con el texto.

## 8. Mantenimiento, copias de seguridad y problemas habituales

### 8.1 Actualizar

**Método A:** actualiza el software y el feed descargando imágenes nuevas.

```bash
$ sudo docker compose -f $DOWNLOAD_DIR/compose.yaml -p greenbone-community-edition pull
$ sudo docker compose -f $DOWNLOAD_DIR/compose.yaml -p greenbone-community-edition up -d
```

- `pull` baja las imágenes nuevas (incluidas las de los datos del feed) y `up -d` recrea solo los contenedores cuya imagen ha cambiado. Antes volvemos a descargar el fichero compose oficial por si ha cambiado.
- Tras actualizar, esperamos de nuevo a que se cargue el feed (3.6).

### 8.2 Parar, reiniciar y borrar

| Acción | Comando |
| --- | --- |
| Ver estado | `docker compose -f ... -p ... ps` |
| Parar (se conservan datos) | `docker compose -f ... -p ... stop` |
| Arrancar | `docker compose -f ... -p ... start` |
| Quitar contenedores conservando datos | `docker compose -f ... -p ... down` |
| **Borrar todo, datos incluidos** | `docker compose -f ... -p ... down -v` |

**Cuidado con `down -v`:** la opción `-v` borra también los volúmenes, es decir, la base de datos, los informes y el feed. Solo se usa para empezar de cero.

### 8.3 Copias de seguridad

```bash
$ sudo docker volume ls | grep greenbone
$ sudo docker run --rm -v greenbone-community-edition_gvmd_data_vol:/datos -v /mnt/midisco/greenbone/backup:/backup debian:13-slim tar czf /backup/gvmd_data_vol.tar.gz -C /datos .
```

- `docker volume ls` muestra los volúmenes del proyecto (los nombres llevan el prefijo del proyecto `greenbone-community-edition_`).
- El segundo comando monta el volumen y la carpeta de copias dentro de un contenedor temporal y los comprime con `tar` (`c` crear, `z` comprimir, `f` fichero, `-C` cambiar de directorio antes). Repetimos para cada volumen que nos interese, en especial el de la base de datos (`psql_data_vol`) y el de datos de gvmd. Para una copia consistente de la base de datos, la hacemos con los servicios parados.
- Lo más valioso son los **informes exportados** en PDF/XML: los guardamos también fuera del escáner.

### 8.4 Resolución de problemas

| Síntoma | Causa probable | Qué hacer |
| --- | --- | --- |
| La tarea queda en *Requested* o *Queued* muchos minutos | El escáner sigue cargando el feed | Esperar al mensaje `Finished loading VTs` (3.6) |
| La tarea termina con *Interrupted* o *Stopped* | Reinicio del escáner o falta de memoria (RAM) | Mirar `free -h`, `docker stats` y los registros de `ospd-openvas` |
| El informe sale vacío o solo con *Log* | *Alive Test* inadecuado, objetivo bloqueando ping, o feed sin cargar | Probar *Consider Alive*; comprobar conectividad (6.1.3); revisar *Feed Status* |
| Las VMs pierden la red después de instalar Docker | La política `DROP` de Docker | Reglas de `DOCKER-USER` de 6.1.3 |
| *Scan Configs* vacío | Falta *Feed Import Owner* o carga sin terminar | Esperar y revisar los registros de `gvmd` |
| No se puede entrar a `127.0.0.1:9392` | Contenedor `gsad`/`nginx` caído o puerto ocupado | `docker compose ps`; \`sudo ss -tlpn |
| No llegan los correos | Credenciales SMTP, remitente distinto a la cuenta, o `sendmail` sin configurar | Probar el envío a mano (6.6.4) y leer el registro de msmtp |
| Error 534 o *Application-specific password required* (Gmail) | Se usó la contraseña normal | Generar una contraseña de aplicación |
| Error 535 *Username and Password not accepted* | Usuario o clave mal escritos, o con espacios | Revisar `.env` (sin comillas ni espacios) |
| msmtp se queja de *ehlo* / *domain* | Algunos servidores exigen un nombre de dominio de cliente | Añadir una línea `domain <nombre>` en la configuración de msmtp; en contenedor puede ser necesario ampliar la imagen |
| El escaneo autenticado no se autentica | Clave mal copiada, permisos de `.ssh`, usuario inexistente | Probar a mano con `ssh -i` (6.4) y mirar *Error Messages* del informe |
| Docker se llena y falla | Poco espacio | `df -h /mnt/midisco`; `docker system df`; borrar imágenes sin uso con `docker image prune` |

## 9. Cierre

### 9.1 Lista de comprobación para la entrega (RI1)

- [x] Herramienta instalada y accesible: *Dashboard* y *Feed Status* con todo en *Current* (sección 3 y vídeo).
- [x] Explicación de qué es la herramienta, para qué sirve y casos reales (sección 1).
- [x] Instalación con Docker documentada paso a paso y verificada en nuestra máquina (sección 3).
- [x] Instalación compilada documentada y verificada; la dejamos detenida y deshabilitada para usar Docker (sección 4).
- [x] Configuración: objetivos, listas de puertos, credenciales, configuraciones, tareas, programaciones y alertas explicadas (sección 5), con **todas las opciones de las alertas** (5.9).
- [x] Prueba sobre **un host** con informe real (6.2).
- [x] Prueba sobre **una red** con informe real (6.3).
- [x] Escaneo **autenticado** (6.4).
- [x] **Monitorización continua** con programación diaria y comparación entre informes (6.5).
- [x] **Alerta por correo** recibida en Gmail (6.6 y vídeo).
- [x] Análisis razonado de los informes: validación, falsos positivos y priorización (6.7).
- [x] **Parches** aplicados y demostrados con el informe *delta* (*Gone*) (6.9).
- [x] Informes de antes y después exportados a PDF y guardados en `/mnt/midisco/greenbone/informes/` (6.7).
- [x] Credenciales (contraseña de aplicación de Gmail, contraseñas y claves) fuera del documento y del vídeo: `correo.env` y la clave SSH tienen permisos `600`.
- [x] Conclusiones: utilidad, dificultades y contexto de uso (9.4).

### 9.2 Buenas prácticas y límites

- Un escáner **no encuentra todo**: no detecta fallos de lógica de negocio, malas contraseñas propias, ni vulnerabilidades desconocidas (*0-day*). Complementa a un *pentest*, no lo sustituye.
- Puede dar **falsos positivos** y **falsos negativos**: siempre se valida.
- Un escaneo agresivo puede **tumbar servicios**: escaneamos en horarios acordados y con configuraciones prudentes.
- Escaneamos **solo con autorización**. En el laboratorio, todo es nuestro.
- Los informes son **material sensible**: los guardamos y compartimos con cuidado.
- Al terminar la práctica: `docker compose ... stop` para no consumir recursos, y **no dejar la interfaz web expuesta** a otras redes.

### 9.3 Fuentes y documentación

- Documentación oficial de Greenbone Community Edition: greenbone.github.io/docs (secciones *Greenbone Community Containers* y *Building from Source*, y el apartado *Workflows* de cada una, donde se explica la configuración del correo con las variables `MTA_*`).
- Foro de la comunidad Greenbone: forum.greenbone.net (resolución de problemas de alertas por correo).
- Documentación de Docker Engine para Debian: docs.docker.com/engine/install/debian.
- Base de datos nacional de vulnerabilidades: nvd.nist.gov; catálogo CVE: cve.org; sistema de puntuación CVSS: first.org/cvss.
- Manual de `msmtp`: marlam.de/msmtp.
- Greenbone, *Greenbone Community Containers*: https://greenbone.github.io/docs/latest/22.4/container/
- Greenbone, *Workflows: actualizar contenedores y sincronizar el feed*: https://greenbone.github.io/docs/latest/22.4/container/workflows.html
- Docker, *Configure and troubleshoot the Docker daemon*: https://docs.docker.com/engine/daemon/
- Docker, *Merge Compose files* (uso de varios ficheros `-f`): https://docs.docker.com/compose/how-tos/multiple-compose-files/merge/
- Google, *Iniciar sesión con contraseñas de aplicación*: https://support.google.com/accounts/answer/185833

### 9.4 Conclusiones: utilidad, dificultades y cuándo usar OpenVAS

**Para qué nos ha servido.** OpenVAS hace en media hora lo que a mano nos llevaría días: revisa cada servicio de cada equipo contra más de 100 000 pruebas actualizadas a diario. En `Appweb` nos enseñó fallos que no habríamos buscado nunca, como los algoritmos MAC débiles de SSH o los *TCP timestamps*. Después del parche, el informe comparativo (*delta*) **demostró** que los habíamos corregido. Además vigila sin que estemos delante: escanea por la noche y nos manda un correo si algo cambia.

**Dificultades que encontramos:**

| Dificultad | Cómo la resolvimos |
| --- | --- |
| La primera carga del feed tarda mucho y, mientras tanto, los escaneos salen vacíos sin avisar | Esperar a que *Feed Status* esté al día antes de escanear (3.6) |
| El escaneo es lento (más de 1 hora para una red pequeña) y carga los equipos | Lista de puertos reducida, `max_hosts` y escanear de noche (6.5) |
| El correo no sale «de fábrica» en Docker | Variables `MTA_*` en un fichero aparte con la contraseña de aplicación (6.6.4) |
| Reiniciar `gvmd` interrumpe los escaneos en curso | Hacer los cambios con el escáner parado (3.11) |
| **Falsos positivos**: sin credenciales, OpenVAS adivina por el número de versión y no sabe que Debian ya ha corregido el fallo | Escaneo autenticado y comprobación en el *changelog* de Debian, y después *override* documentado (6.4 y 6.9) |
| Fallos que no dependen de nosotros (router, BIOS del procesador) | Documentarlos como **riesgo aceptado** (6.9 y 6.10) |
| Los objetos creados con un usuario no los ven los demás | Saber con qué usuario trabajamos o compartirlos con permisos (capítulo 7) |

**En qué contexto lo vemos necesario:**

- **Siempre antes de poner un servidor en producción**, como el de nuestro escenario con Nginx y PostgreSQL, y **después de cada cambio importante**.
- **De forma programada** (diaria o semanal) en cualquier red con servidores, porque cada día se publican vulnerabilidades nuevas para programas que ayer eran seguros.
- **Cuando una norma lo exige**, por ejemplo el Esquema Nacional de Seguridad, ISO 27001 o PCI-DSS, que piden revisiones periódicas de vulnerabilidades.

**Lo que no hace:** no corrige nada por sí mismo, no detecta ataques en curso (para eso está el IDS) y no sustituye a una auditoría manual. Es la primera capa: nos dice **dónde mirar** y nos permite **demostrar** que hemos corregido.

## Anexo. Ficheros y rutas de nuestra instalación

| Ruta | Qué es |
| --- | --- |
| `/root/greenbone-community-container/compose.yaml` | Fichero Compose oficial que descarga el script de Greenbone. **No lo modificamos** |
| `/mnt/midisco/greenbone/compose/correo.override.yaml` | Nuestro fichero adicional: añade el correo a `gvmd` |
| `/mnt/midisco/greenbone/compose/correo.env` | Datos del correo, incluida la contraseña de aplicación. Permisos `600`. **Nunca se publica** |
| `/mnt/midisco/greenbone/compose/correo.env.ejemplo` | Plantilla del anterior, sin contraseña |
| `/etc/systemd/system/greenbone-compose.service` | Unidad que levanta la pila al arrancar el equipo (con el *override*) |
| `/etc/systemd/system/docker.service.d/midisco.conf` | Obliga a Docker a esperar a que `/mnt/midisco` esté montado |
| `/etc/docker/daemon.json` | Configuración de Docker con `data-root` en `/mnt/midisco/docker` |
| `/etc/sysctl.d/99-greenbone.conf` | Ajuste `vm.overcommit_memory = 1` para Redis |
| `~/.config/gvm-tools.conf` | Usuario y contraseña de `automatizacion` para la línea de comandos. Permisos `600` |
| `/mnt/midisco/greenbone/scripts/gmp.sh` | Script para enviar órdenes a Greenbone (sección 7.1) |
| `/mnt/midisco/greenbone/scripts/esperar_tarea.sh` | Script que espera a que una tarea termine (sección 7.5) |
| `/mnt/midisco/greenbone/claves/` | Clave SSH exclusiva para el escaneo autenticado. Permisos `700` |
| `/mnt/midisco/greenbone/informes/` | Informes exportados (PDF, XML) |
| `/mnt/midisco/greenbone/backup/` | Copias de seguridad de los volúmenes |
| `/mnt/midisco/greenbone/{fuentes,build,instalacion,datos}` | Restos del método B (compilado), conservados |
| Volúmenes `greenbone-community-edition_*` | Datos del feed, base de datos e informes (dentro de `/mnt/midisco/docker`) |
| Instantánea `antes-de-parchear` de la VM `Appweb` | Estado de la VM antes de la prueba 6; se restaura con `virsh snapshot-revert Appweb antes-de-parchear` |
