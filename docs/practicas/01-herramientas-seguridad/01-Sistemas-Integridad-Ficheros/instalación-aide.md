# Guía de instalación y configuración del sistema detector de intrusos AIDE


AIDE funciona bajo un principio de **comparación de estados estáticos**. Su flujo de trabajo se divide en tres fases fundamentales:

1. **Fase de inicialización (`--init`):** escanea el sistema de archivos según las reglas definidas en su archivo de configuración y genera una base de datos con los hashes y metadatos de los archivos (estado limpio/seguro).
2. **Fase de producción:** la base de datos generada se establece como de "solo lectura" (idealmente movida a un almacenamiento externo o medio seguro).
3. **Fase de comprobación (`--check`):** escanea nuevamente el sistema en tiempo real, genera una instantánea actual y la compara contra la base de datos de confianza. Cualquier discrepancia genera una alerta.

---

## 1. Instalación

Podemos instalar AIDE en Debian desde el repositorio oficial:

```
sudo apt update && sudo apt install aide
```

---

## 2. Configuración

### 2.1 Explicación de opciones

El fichero principal de configuración de AIDE es `/etc/aide/aide.conf`, aunque nosotros no escribiremos dentro de él: pondremos nuestra configuración en un fichero dentro de `/etc/aide/aide.conf.d/`, por ejemplo **`99_custom_config`**.

> **Ojo con el nombre.** AIDE solo carga los ficheros de `aide.conf.d/` cuyo nombre cumple la expresión `^[a-zA-Z0-9_-]+$` (es lo que indica la última línea de `aide.conf`: `@@x_include /etc/aide/aide.conf.d ^[a-zA-Z0-9_-]+$`). Un nombre con punto, como `99_custom.config`, se ignoraría.

Por defecto, el paquete de Debian ya trae una configuración exhaustiva, repartida en cientos de ficheros de ese directorio. Nosotros escribiremos una configuración propia para que el sistema solo salte si detecta una modificación en los directorios que consideramos críticos.

En la configuración de AIDE podemos agregar los directorios que queremos que revise y también los que **no**, poniéndoles `!` delante. Además, por cada directorio que queremos revisar debemos indicarle, a su derecha, el **filtro** con el que se comprobará.

Estos filtros los declaramos nosotros de la siguiente forma:

`NombreFiltro = parametro1+parametro2+parametro3...`

Los parámetros pueden ser los siguientes:

| Parámetro | Descripción |
| :--- | :--- |
| **p** | Comprueba los permisos de los archivos o directorios seleccionados. |
| **i** | Comprueba el número de inodo. Cada nombre de archivo tiene un número de inodo único que no debería cambiar. |
| **n** | Comprueba el número de enlaces que apuntan al archivo. |
| **u** | Comprueba si el propietario del archivo ha cambiado. |
| **g** | Comprueba si el grupo del archivo ha cambiado. |
| **s** | Comprueba si el tamaño del archivo ha cambiado. |
| **b** | Comprueba si el número de bloques usados por el archivo ha cambiado. |
| **m** | Comprueba si la hora de modificación (*mtime*) ha cambiado. |
| **a** | Comprueba si la hora de acceso (*atime*) ha cambiado. |
| **c** | Comprueba si la hora de cambio del inodo (*ctime*) ha cambiado. Se actualiza con cualquier cambio de contenido, permisos o propietario, y no se puede falsear con `touch`. |
| **S** | Comprueba que el archivo solo ha **crecido** (tamaño creciente). Pensado para logs. |
| **I** | Ignora los cambios en el nombre del archivo (útil para logs rotados). |
| **md5** | Comprueba la suma de verificación md5. Recomendamos usar sha256 o sha512. |
| **sha1** | Comprueba la suma de verificación sha1 (160 bits). Recomendamos usar sha256 o sha512. |
| **sha256** | Comprueba la suma de verificación sha256. |
| **sha512** | Comprueba la suma de verificación sha512. |

Además, todas las reglas (directorio + filtro) se evalúan **en orden** y gana la primera que coincide. Por eso las exclusiones (`!`) van siempre antes de la regla general que podría capturarlas.

### 2.2 Preparación previa

El paquete de Debian ya trae una enorme cantidad de reglas configuradas en `aide.conf.d/`, sin embargo estas reglas son bastante generalistas y saltaran hasta por funcionamiento de servicios del sistema. Como nosotros queremos que nos notifique solo si ha habido un cambio importante, desactivaremos estas reglas para poner las nuestras personalizadas, que solo seguirán directorios críticos del sistema.

 > Es necesario desactivarlas ya que de lo contrario pueden interferir y anular las nuestras.

Apartaremos a otro directorio los ficheros de reglas del paquete (los `31_`, `70_`, `98_` y `99_aide_root`) a otro directorio. Dejamos los `01_`, `10_`, `20_`, `21_` y `30_`, que solo preparan variables y la caché que usa el servicio diario:

```
sudo mkdir /etc/aide/aide.conf.d.orig
sudo mv /etc/aide/aide.conf.d/{31_aide_*,70_aide_*,98_aide_vfat,99_aide_root} /etc/aide/aide.conf.d.orig/
```

Si algún día queremos volver a la configuración del paquete, basta con devolverlos a su sitio.

### 2.3 Configuración propia (`aide.conf.d/99_custom_config`)

En este caso solo hemos trackeado directorios críticos del sistema que son estáticos (y las claves y configuraciones SSH de los usuarios):

```
cat << 'EOF' | sudo tee /etc/aide/aide.conf.d/99_custom_config
DirCriticos = p+i+n+u+g+s+m+c+sha256+sha512
DirLogs = p+n+u+g

!/var/log/aide
!/var/lib/aide
!/root/.*history.*
!/boot/grub/grubenv
!/boot/grub2/grubenv
!/home/[^/]+/\.ssh/[^/]+\.pub$

/home/[^/]+/\.ssh DirCriticos
!/home/[^/]+/.*

/etc DirCriticos
/bin DirCriticos
/sbin DirCriticos
/lib DirCriticos
/lib64 DirCriticos
/usr/bin DirCriticos
/usr/sbin DirCriticos
/usr/lib DirCriticos
/usr/lib64 DirCriticos
/usr/local DirCriticos
/var/spool/anacron DirCriticos
/boot DirCriticos
/opt DirCriticos
/var/spool/cron DirCriticos
/var/spool/anacron DirCriticos
/root$ p+i+n+u+g+s+sha256+sha512
/root DirCriticos

/var/log DirLogs
EOF
```

Lo que hemos puesto en detalle:

- **Filtros:** `DirCriticos` vigila permisos, propietario, tamaño, fechas y hashes. `DirLogs` es más ligero porque los logs cambian de contenido constantemente.
- **Exclusiones primero:** dejamos fuera las bases de datos y logs de AIDE, el historial de `root` y las claves públicas (`.pub`).
- **SSH:** vigilamos todo lo que hay en `~/.ssh` de cualquier usuario y descartamos el resto de su carpeta personal.
- **Resto:** directorios del sistema que no deberían cambiar si no es por una actualización.

Antes de continuar, comprobamos que la configuración no tiene errores de sintaxis:

```
sudo aide --config-check --config /etc/aide/aide.conf
```

```
debian@fim:~$ sudo aide --config-check --config /etc/aide/aide.conf
debian@fim:~$
```

---

## 3. Primera puesta en marcha

### 3.1 Creación de la primera snapshot/base de datos

Para crear la primera snapshot del estado del sistema ejecutamos AIDE con la opción `--init` y le pasamos con `--config` la ruta del fichero de configuración:

```
sudo aide --init --config /etc/aide/aide.conf
```

```
debian@fim:~$ sudo aide --init --config /etc/aide/aide.conf
Start timestamp: 2026-10-15 13:50:50 +0000 (AIDE 0.19.1)
AIDE successfully initialized database.
New AIDE database written to /var/lib/aide/aide.db.new
Ignored e2fs attributes: EINV

Number of entries:      15217

---------------------------------------------------
The attributes of the (uncompressed) database(s):
---------------------------------------------------

/var/lib/aide/aide.db.new
 SHA256    : MOCh7gTi0IKL0QFJjcH87SV7qDGFwVyT
             M7uuXwgwdd8=
 SHA512    : XgAxnVNDnbZ5jnrU8JpMC0F0io3Hwock
             MZQf7DA6A0CSgg6g5xaSAW97qxETqofu
             ASa0khUavCUuylUDIwdlHw==
 STRIBOG256: wUQcJpjUUmJjnm65NAtIeYp/xM0XdlMd
             uv6T8am4Vhw=
 STRIBOG512: KhLj2RWvU8oxOvQ5Dtdm5rTZ3hKVIpxA
             mZi5aP373bW9MVxiEB5GteXolwOZRaMz
             ne7bWyouNz9oWWws7TIeZQ==
 SHA512/256: VS+QgcVBtp3NNROgErEAShmSyOLGkisg
             hk61xMp/8iI=
 SHA3-256  : 0P1Li5/hrlDDApsq3EXciW1KMNanw4CA
             0ou9y9kWuv8=
 SHA3-512  : 3rrIpFBStdROliFlABv62c525FWR45Oh
             B7ClaFck6AJf0FEb0hncZNy0+d7i9xau
             Y4SyJmspR+BVefcGzvsFrA==


End timestamp: 2026-10-15 13:50:57 +0000 (run time: 0m 7s)
```

> Al final del informe, AIDE imprime los hashes de la propia base de datos. Conviene respaldarlos fuera de la maquina, así podremos comprobar más adelante que la base de datos no ha sido manipulada.

Para activar esta snapshot y usarla en los siguientes escaneos le tenemos que quitar el **`.new`** del nombre:

```
sudo mv /var/lib/aide/aide.db.new /var/lib/aide/aide.db
```

Para registrar nuevos cambios en la snapshot usamos la directiva `--update`. Será la que usemos de ahora en adelante cada vez que queramos actualizar el estado de referencia:

```
sudo aide --update --config /etc/aide/aide.conf
```

Con esto se crea la nueva snapshot en la ruta indicada por `database_out=` (por defecto `/var/lib/aide/aide.db.new`). Una vez actualizada, volvemos a quitarle el `.new` al nombre para activarla.

Ya que hemos hablado de la ruta de la snapshot de salida, podemos ver las rutas que nos interesan en  `/etc/aide/aide.conf`:

| Directiva | Para qué sirve |
| :--- | :--- |
| `database_in=` | Base de datos que se **lee** en los escaneos (`aide.db`). |
| `database_out=` | Base de datos que se **escribe** con `--init` y `--update` (`aide.db.new`). |
| `database_new=` | Base de datos nueva que se lee con `--compare` (comparar dos bases entre sí). |

### 3.2 Escaneo manual del sistema

Para realizar un escaneo manual invocamos a AIDE con `--check`:

```
sudo aide --check --config /etc/aide/aide.conf
```

Si lo ejecutamos justo después de generar la base de datos no notificará ningún cambio. En el apartado 8 lo probaremos con casos reales para ver cómo reacciona.

---

## 4. Automatización

### 4.1 Timer de systemd incluido

Por defecto el paquete de Debian ya viene con un **timer de systemd** que lanza un escaneo todos los días, por lo que no tenemos que configurar nada adicional. Lo comprobamos con:

```
systemctl cat dailyaidecheck.timer
```

```
# /usr/lib/systemd/system/dailyaidecheck.timer
[Unit]
Description=Daily AIDE check

[Timer]
OnCalendar=*-*-* 01:50:00
RandomizedDelaySec=2h
Persistent=true

[Install]
WantedBy=timers.target
```
Podemos ver a continuacion que hace cada parte:

| Línea | Qué hace |
| :--- | :--- |
| `OnCalendar=*-*-* 01:50:00` | Se ejecuta todos los días a la 01:50. |
| `RandomizedDelaySec=2h` | Añade un retraso aleatorio de hasta 2 horas (evita que muchas máquinas lancen el escaneo a la vez). |
| `Persistent=true` | Si el equipo estaba apagado a esa hora, el escaneo se ejecuta en cuanto arranque. |

El timer no ejecuta AIDE directamente, sino que activa el servicio `dailyaidecheck.service` cuyo interior podemos revisar a continuación:

```
systemctl cat dailyaidecheck.service
```

```
[Unit]
Description=daily AIDE check
Documentation=file:/usr/share/doc/aide/README.Debian.gz
StartLimitIntervalSec=7200
StartLimitBurst=1
Requires=dailyaidecheck-buildcache.service
After=dailyaidecheck-buildcache.service

[Service]
Type=oneshot
User=_aide
Group=_aide
AmbientCapabilities=CAP_DAC_READ_SEARCH CAP_AUDIT_WRITE
# we need those to see the "real" system
PrivateDevices=no
# We cannot use any of systemd's sandboxing features here since
# that would mask away a couple of /run subdirectories including
# /run/credentials
ExecStart=/usr/share/aide/bin/dailyaidecheck --systemdservice
```

Lo importante del este servicio es la última línea: el servicio ejecuta el script `/usr/share/aide/bin/dailyaidecheck`, que es quien lanza AIDE, prepara el informe y lo envía por correo. Se ejecuta con un usuario sin privilegios (`_aide`) al que solo se le da la capacidad de leer todo el sistema (`CAP_DAC_READ_SEARCH`).

Si fuese necesario podríamos comprobar el estado de este servicio con:

```
systemctl list-timers dailyaidecheck.timer
journalctl -u dailyaidecheck.service
```

También podemos lanzarlo a mano cuando queramos (por ejemplo para hacer pruebas) con:

```
sudo systemctl start dailyaidecheck.service
```

> **Importante** el servicio tiene `StartLimitIntervalSec=7200` y `StartLimitBurst=1`, es decir, solo se puede arrancar **una vez cada 2 horas**. Si lo repetimos antes, systemd lo rechazará. Se libera con `sudo systemctl reset-failed dailyaidecheck.service`.

El comportamiento de este script lo controla `/etc/default/aide`. En nuestro sistema hay dos líneas relevantes:

```
COMMAND=update
COPYNEWDB=no
```

Cada día se ejecuta `aide --update`: compara el sistema con la base de datos activa, informa de las diferencias y genera una base nueva, pero **no la activa** (`COPYNEWDB=no`). Es la forma segura de funcionar, porque nadie "bendice" cambios sin que un administrador los revise.

Tiene, sin embargo, dos limitaciones: la base nueva siempre se llama `aide.db.new`, así que **se sobrescribe cada día y no queda histórico**, y nada cubre las actualizaciones de APT. De eso se encargan los siguientes apartados.

### 4.2 Nuestro script: poner fecha a la base de datos

El script que viene con aide en debian nos resuelve enormemente el trabajo, pero cada que este hace un escaneo y saca una base de datos nueva, le pone siempre el mismo nombre, ademas de que puede reescribir si ya a sacado varias. Esto no es lo optimo ya que nos conviene poder tener un control de versiones de estas snapshots, por lo que escribiremos un pequeño script que se llame junto al que ya esta y su función sea cambiar el nombre de la snapshot de salida para ponerle también en que fecha se ha realizado y poder traquear fácilmente las versiones.

>Ademas, aunque esto es para el siguiente apartado, podemos ver que el script también activa la ultima snapshot hecha si se le pasa el parámetro --activar, esto es ya que mas adelante lo aprovecharemos para automatizar también las snapshot generadas por apt

Creamos `/usr/local/sbin/aide-snapshot`:

```
cat << 'EOF' | sudo tee /usr/local/sbin/aide-snapshot
#!/bin/bash

DIR=/var/lib/aide
FECHA=$(date +%Y-%m-%d_%H%M)

[ -f "$DIR/aide.db.new" ] || exit 0        # nada que renombrar

mv "$DIR/aide.db.new" "$DIR/aide.db.$FECHA"

if [ "$1" = "--activar" ]; then
    ln -sf "aide.db.$FECHA" "$DIR/aide.db"
fi
exit 0
EOF
```
Le damos permisos:

```
sudo chmod 755 /usr/local/sbin/aide-snapshot
```

### 4.3 Que el timer active a nuestro script

Para que el timer llame tambien a nuestro script cada que hace un escaneo, añadimos nuestro script **después** del original con un **'drop-in'**, un fichero que modifica solo lo que indiquemos del servicio:

```
sudo systemctl edit dailyaidecheck.service
```

Se abre un editor y escribimos:

```
[Service]
ExecStartPost=/usr/local/sbin/aide-snapshot
```
Cosas a tener en cuenta:

- `ExecStartPost` añade un paso que se ejecuta **tras** el análisis original, sin tocar este. Por eso no hace falta borrar el `ExecStart` del servicio.
- El script se lanza **sin** `--activar`: la snapshot de la noche queda guardada con su fecha, pero la activación es siempre manual.
- Usamos un *drop-in* (se guarda en `/etc/systemd/system/dailyaidecheck.service.d/override.conf`) en lugar de editar el fichero de `/usr/lib/systemd/system/`, porque una actualización del paquete sobrescribiría esa edición.

Comprobamos que se ha aplicado y lo probamos:

```
systemctl cat dailyaidecheck.service
sudo systemctl start dailyaidecheck.service
sudo ls -l /var/lib/aide/
```

```
debian@fim:~$ systemctl cat dailyaidecheck.service
# /usr/lib/systemd/system/dailyaidecheck.service
[Unit]
Description=daily AIDE check
Documentation=file:/usr/share/doc/aide/README.Debian.gz
StartLimitIntervalSec=7200
StartLimitBurst=1
Requires=dailyaidecheck-buildcache.service
After=dailyaidecheck-buildcache.service

[Service]
Type=oneshot
User=_aide
Group=_aide
AmbientCapabilities=CAP_DAC_READ_SEARCH CAP_AUDIT_WRITE
# we need those to see the "real" system
PrivateDevices=no
# We cannot use any of systemd's sandboxing features here since
# that would mask away a couple of /run subdirectories including
# /run/credentials
ExecStart=/usr/share/aide/bin/dailyaidecheck --systemdservice



# /etc/systemd/system/dailyaidecheck.service.d/override.conf
[Service]
ExecStartPost=/usr/local/sbin/aide-snapshot
debian@fim:~$ sudo systemctl start dailyaidecheck.service
debian@fim:~$ sudo ls -l /var/lib/aide/
total 2884
-rw------- 1 _aide root     107 Oct 15 14:46 10_aide_rootrules_cache
-rw------- 1 root  root 1473399 Oct 15 13:50 aide.db
-rw------- 1 root  root 1473401 Oct 15 13:52 aide.db.2026-10-15_1446
debian@fim:~$
```

> Estos ficheros están en `/etc`, un directorio vigilado: AIDE nos avisará del cambio la próxima vez que se ejecute.

### 4.4 Hook de APT

Cuando el sistema se actualiza cambian cientos de ficheros de `/usr/bin`, `/usr/lib`, `/etc`... y esos cambios son legítimos. APT permite ejecutar un comando cada vez que `dpkg` termina de instalar, actualizar o eliminar paquetes. Creamos `/etc/apt/apt.conf.d/99aide-snapshot`:

```
cat << 'EOF' | sudo tee/etc/apt/apt.conf.d/99aide-snapshot
DPkg::Post-Invoke { "/usr/share/aide/bin/dailyaidecheck && /usr/local/sbin/aide-snapshot --activar || true"; };
EOF
```

Lo que hemos escrito en nuestro hook hace:

1. `dailyaidecheck`: el mismo análisis de Debian que lanza el timer.
2. `&& aide-snapshot --activar`: solo si el análisis ha terminado bien, ponemos fecha a la base nueva **y la activamos** para que en un proximo escaneo no nos salte una alerta falsa.
3. `|| true`: aunque algo fallara, APT no debe dar la instalación por fallida.

Tras cada `apt upgrade` (o `install`/`remove`) quedará una snapshot con fecha, ya activa para que el sistema no salte en los escaneos diarios por culpa de las acciones de apt.

---

## 5. Notificaciones por correo

El script `dailyaidecheck` es quien envía el informe por correo, y se configura en `/etc/default/aide`. Por defecto estas variables vienen comentadas (el correo iría a `root`). Descomentamos y ajustamos las siguientes lineas:

```
MAILTO=tu_direccion@gmail.com
MAILCMD=mail
QUIETREPORTS=yes
```

| Variable | Función |
| :--- | :--- |
| `MAILTO` | Dirección a la que se envía el informe. |
| `QUIETREPORTS=yes` | **Solo** envía correo si se han detectado cambios (o ha habido errores). Sin esto recibiríamos un correo cada día aunque todo esté igual. |
| `MAILCMD=mail` | Decimos al script que use el comando mail para los correos |

Otras variables útiles del mismo fichero son:

| Variable | Función |
| :--- | :--- |
| `MAILSUBJ` | Asunto del correo (por defecto `Daily AIDE report for $FQDN`). |
| `FILTERUPDATES=yes` | Oculta del correo los cambios provocados por actualizaciones de paquetes (siguen en el log). |
| `SILENTREPORTS=yes` | No envía correo en ningún caso. |

### El servidor de correo

AIDE no envía correos por sí mismo: usa el servidor de correo local del sistema. Nosotros usaremos **Postfix**, configurado para reenviar los mensajes a través de una cuenta de Gmail. Su instalación y configuración básica se explica en el documento aparte sobre configuracion basica de postfix.

Para probar el conjunto, provocamos un cambio, lanzamos el servicio y comprobamos que llega el correo:

```
sudo systemctl start dailyaidecheck.service
```

---

## 6. Buenas prácticas

**1. Crear la primera snapshot en un sistema limpio.** Todo lo que haya en el sistema cuando hacemos `--init` se considera de confianza. Hay que hacerlo antes de exponer el equipo y tras instalar y configurar lo que vayamos a vigilar.

**2. Conservar varias snapshots, con la fecha en el nombre.** Las snapshots con fecha (`aide.db.2026-10-14_1622`) permiten saber cuándo apareció un cambio y volver a comparar con un estado anterior. Conviene establecer una política de retención, por ejemplo borrar las de más de 90 días:

```
sudo find /var/lib/aide -name 'aide.db.20*' -mtime +90 -delete
```

**3. No aceptar cambios sin revisarlos.** Activar una snapshot sin haber leído los cambios que registro antes es algo extremadamente peligroso.

**4. Guardar los hashes de la base de datos fuera del equipo.** Los que imprime `--init`/`--update` al final del informe permiten verificar que la base no ha sido manipulada.

**5. Proteger contra escritura todo lo que AIDE necesita para ser fiable.** Si un atacante consigue privilegios de administrador, podría modificar la base de datos, la configuración o el propio binario para ocultar sus huellas. Por eso conviene mantener en un medio protegido contra escritura:

| Qué proteger | Ejemplos |
| :--- | :--- |
| La base de datos y sus snapshots | `/var/lib/aide/` |
| Los ficheros de configuración | `/etc/aide/aide.conf` y `aide.conf.d/` |
| El binario y los scripts | `/usr/bin/aide`, `/usr/local/sbin/aide-snapshot` |

Que medidas podríamos tomar, de menos a más seguridad:

- `chattr +i` sobre los ficheros: sencillo, pero un atacante con privilegios de administrador puede quitarlo. Solo frena modificaciones automáticas.
- Guardar todo en un medio montado en solo lectura, como una partición o recurso de red dedicado.
- Guardar todo en un **Medio extraíble** (por ejemplo un USB con interruptor físico de protección contra escritura), que solo se conecta durante las comprobaciones y el resto del tiempo permanece desconectado, fuera del alcance de cualquier atacante. Claro, esto ultimo romperia la automatización.

Con un medio así se ejecuta AIDE apuntando a él (`database_in=` y `--config`). Si dejamos la base en un medio de solo lectura, el servicio diario no podrá escribir en él: hay que cambiar `COMMAND=update` por `COMMAND=check` en `/etc/default/aide`.

**6. Vigilar solo lo que debe ser estático.** Cuantos menos directorios cambiantes vigilemos, menos ruido habrá y antes notaremos una alerta de verdad. Si el correo salta todos los días, acabaremos ignorándolo.

---

## 7. Pruebas de funcionamiento

Para comprobar que la configuración propia que hemos hecho detecta lo que debe y ignora lo que no, vamos a simular 3 casos ipoteticos que podrian darse en la realidad. Partimos de una snapshot recién creada y activa, con `~/.ssh/authorized_keys` ya existente en ese momento, y de un escaneo limpio:

```
sudo aide --check --config /etc/aide/aide.conf
```

```
debian@fim:~$ sudo aide --check --config /etc/aide/aide.conf
Start timestamp: 2026-10-15 16:14:11 +0000 (AIDE 0.19.1)
AIDE found NO differences between database and filesystem. Looks okay!!
Ignored e2fs attributes: EINV

Number of entries:      15339

---------------------------------------------------
The attributes of the (uncompressed) database(s):
---------------------------------------------------

/var/lib/aide/aide.db
 SHA256    : QcD6z/BKa+fgemh2TlnGu9w2tOuI7FS9
             n8rzpAAmeMc=
 SHA512    : NjiDQYJEiGkRsHNRf7jeS/rfimcB4zoq
             aTrqCAWxgUcYnob5RY0usPjg8gd4f25u
             m4ZUElHRvQaLlVrNrGx7Lg==
 STRIBOG256: NKNQKTcRIiRar8Cz4+aTc2l7MjhNz7Wv
             UPyxiBWbjtM=
 STRIBOG512: 34AsWADtdgw0LTktT+eT2rLS7iqQ3/Ou
             Pc5KRZ/TJ+0OJ2kTivWv9ojtuWF0DjO+
             foZ4SRWGgC5fsBprO6jhtA==
 SHA512/256: +UPcTCu6b+kAy5tjUQzRw6GpQ24yDBLz
             mvb2H93Rfvc=
 SHA3-256  : b5P2WVYWd7451hxzz0dEorWHsVEYQZ5s
             D5nxoHpbLfM=
 SHA3-512  : pJXRDC8+Z5I5Ws5OgKWCp/ONwcsvLGv/
             VJS1hit77lP/yezk9agk21hoxmKoVK4q
             ALGX9NkGvuvh1eBSVJBBFw==


End timestamp: 2026-10-15 16:14:13 +0000 (run time: 0m 2s)
```

### Caso 1: puertas traseras tras un acceso no autorizado

**Caso hipotetico:** un atacante ha entrado en la maquina y quiere asegurarse de poder volver. Deja un binario común con el bit SUID, para escalar privilegios después, y añade su clave a los accesos SSH permitidos.

```
sudo chmod u+s /usr/bin/find
echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFAKEKEYFAKEKEYFAKEKEYFAKEKEYFAKEKEYFAKEKEY atacante@kali" >> ~/.ssh/authorized_keys
sudo aide --check --config /etc/aide/aide.conf
```

AIDE informa de dos ficheros modificados. Del primero, el cambio clave es el de permisos:

```
File: /usr/bin/find
 Perm      : -rwxr-xr-x                 | -rwsr-xr-x
```

Podemos ver a continuacion las reglas de nuestra configuracion implicadas en la detección:

| Fichero | Regla que lo detecta | Cambios detectados |
| :--- | :--- | :--- |
| `/usr/bin/find` | `/usr/bin DirCriticos` | permisos (`p`) y ctime (`c`) |
| `~/.ssh/authorized_keys` | `/home/[^/]+/\.ssh DirCriticos` | tamaño, mtime, ctime y hashes |

**Que podemos observar:** Un atacante puede falsear la fecha de modificación, pero no el ctime ni los hashes. Por eso en el filtro `DirCriticos` se incluye `c`, `sha256` y `sha512`.

### Caso 2: escalada y persistencia como administrador

**Caso hipoteticoco:** con privilegios de administrador, el atacante crea un usuario con UID 0 (equivalente a `root`), se concede `sudo` sin contraseña y se deja un comando que se ejecutará cada vez que `root` abra una terminal.

```
echo 'soporte:x:0:0::/root:/bin/bash' | sudo tee -a /etc/passwd
echo 'debian ALL=(ALL) NOPASSWD:ALL' | sudo tee /etc/sudoers.d/90-debian
echo '/tmp/.update.sh &' | sudo tee -a /root/.bashrc
sudo aide --check --config /etc/aide/aide.conf
```

```
debian@fim:~$ echo 'soporte:x:0:0::/root:/bin/bash' | sudo tee -a /etc/passwd
echo 'debian ALL=(ALL) NOPASSWD:ALL' | sudo tee /etc/sudoers.d/90-debian
echo '/tmp/.update.sh &' | sudo tee -a /root/.bashrc
sudo aide --check --config /etc/aide/aide.conf
soporte:x:0:0::/root:/bin/bash
debian ALL=(ALL) NOPASSWD:ALL
/tmp/.update.sh &
Start timestamp: 2026-10-15 16:16:41 +0000 (AIDE 0.19.1)
AIDE found differences between database and filesystem!!
Ignored e2fs attributes: EINV

Summary:
  Total number of entries:      15340
  Added entries:                1
  Removed entries:              0
  Changed entries:              3

---------------------------------------------------
Added entries:
---------------------------------------------------

f++++++++++++++++++: /etc/sudoers.d/90-debian

---------------------------------------------------
Changed entries:
---------------------------------------------------

f > ... mc..H      : /etc/passwd
d = ... mc..       : /etc/sudoers.d
f > ... mc..H      : /root/.bashrc

---------------------------------------------------
Detailed information about changes:
---------------------------------------------------

File: /etc/passwd
 Size      : 1671                             | 1702
 Mtime     : 2026-10-15 16:06:31 +0000        | 2026-10-15 16:16:41 +0000
 Ctime     : 2026-10-15 16:06:31 +0000        | 2026-10-15 16:16:41 +0000
 SHA256    : 0HKkgVC4MwjWQiWHPzTOEOmkddZf+tzF | UZYuXUIureM5WCcGy+somHLH3ur3rjmX
             UdPCgK9X7FE=                     | 2WmeJzFwyjU=
 SHA512    : VPUImBDBk6xFUW6S74mj3nBn49TRyfGJ | Mqb11H1Rgt8ScRku7AJ3f2Xm0g9URyiW
             r4cHLLh3nwAJtjbfjJRmm2yrZNeHAYiR | yO3CrQLe5o6aP0VMEJOxvBWyZloFs7J1
             /zbkpMuWn9Q6ukqF1sNM4g==         | x/y+Fh0kq0ET0VQS7O0jig==

Directory: /etc/sudoers.d
 Mtime     : 2026-10-15 16:06:31 +0000        | 2026-10-15 16:16:41 +0000
 Ctime     : 2026-10-15 16:06:31 +0000        | 2026-10-15 16:16:41 +0000

File: /root/.bashrc
 Size      : 588                              | 606
 Mtime     : 2026-10-15 16:06:31 +0000        | 2026-10-15 16:16:41 +0000
 Ctime     : 2026-10-15 16:06:31 +0000        | 2026-10-15 16:16:41 +0000
 SHA256    : /vjd5xpR2FyhO0mTVjxJW84oO9SvMMM5 | iKq3+1a5LKhGt65TGH668rX8XxFzO6J2
             D/sQL83NHcM=                     | 9t0RDFoRR8E=
 SHA512    : 0SasKiGneG1KYV3N5UiBoVTMfUcXfJSJ | a90wzidB0Zcdhx7VDPDSuPpZwGqaS1cf
             5SU3/BEYKVLAwjjsHm6h98EehbiaK1C9 | 6rLRl6F3x+36mAjVLIwYFT94+9yOWi8s
             SwDhKtTwVss3RiPpS8ge/A==         | COpEFSlJ9dgY6idwgWtHqQ==
```

| Fichero | Regla que lo detecta | Cambios detectados |
| :--- | :--- | :--- |
| `/etc/passwd` | `/etc DirCriticos` | Modificado (tamaño, fechas, hashes) |
| `/etc/sudoers.d/90-debian` | `/etc DirCriticos` | **Añadido** |
| `/root/.bashrc` | `/root DirCriticos` | Modificado (tamaño, fechas, hashes) |

**Que podemos observar:** AIDE no distingue entre "legítimo" y "malicioso": avisa de cualquier cambio en lo vigilado, tanto de ficheros modificados como de ficheros nuevos que aparecen donde no debería haber nada.

### Después de las prueba

Podemos deshacer todos los cambios hechos para las pruebas con los comandos a continuación:

```
sudo chmod u-s /usr/bin/find
sed -i '$d' ~/.ssh/authorized_keys
sudo sed -i '/^soporte:/d' /etc/passwd
sudo rm /etc/sudoers.d/90-debian
sudo sed -i '$d' /root/.bashrc
```

Aun así, un nuevo `--check` seguirá avisando, ya que a pesar de haber revertido los cambios, los **ctime** de los ficheros siguen alterados respecto a la snapshot, asi que tendremos que crear una nueva snapshot.
