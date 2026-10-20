# Instalación de Oracle AI Database 26ai en Debian 13 sobre un disco dedicado (Por Rubén)

En esta guía Oracle se instala **entero en un segundo disco**, separado del sistema operativo. El disco se gestiona con **LVM** y se divide en dos volúmenes: uno para el software (`/u01`) y otro para los datos (`/u02`). El software se instala con la *Gold Image* de Oracle y la base de datos se crea con **ficheros de respuesta** (`.rsp`) que editamos a mano, en lugar de pasar todas las opciones por la línea de comandos.

!!! note "¿Por qué un disco aparte?"
    - Si Oracle llena su disco, el sistema operativo sigue funcionando.
    - Con LVM se puede ampliar el espacio más adelante sin reinstalar.
    - Se puede reinstalar Debian sin tocar los datos de Oracle.

## Entorno

| Máquina | Nombre | IP | Recursos |
|---|---|---|---|
| Servidor Oracle | `oraserver.ruben.asir` | 192.168.122.20 | 4 GB de RAM (mejor 8), disco del sistema + **disco de 50 GB** |
| Cliente | `cliente.ruben.asir` | 192.168.122.50 | 2 GB de RAM |

- Sistema: Debian 13 (Trixie), x86_64.
- Oracle AI Database 26ai Enterprise Edition (versión interna 23.26).
- Red local: 192.168.122.0/24 (red por defecto de libvirt/KVM).

Cambia las IPs y nombres por los tuyos. Los comandos se ejecutan con un usuario que tenga `sudo`, salvo los marcados como **(oracle)**, que se ejecutan como el usuario `oracle`.

## 1. Añadir el segundo disco a la máquina virtual

Con la máquina **apagada**, en virt-manager: *Mostrar detalles* → *Agregar hardware* → *Almacenamiento* → 50 GB, bus **VirtIO** → *Finalizar*.

También se puede hacer desde la terminal del **anfitrión** (cambia `oraserver` por el nombre de tu VM):

```bash
sudo qemu-img create -f qcow2 /var/lib/libvirt/images/oraserver-oracle.qcow2 50G
sudo virsh attach-disk oraserver /var/lib/libvirt/images/oraserver-oracle.qcow2 vdb \
  --driver qemu --subdriver qcow2 --persistent
```

Arrancamos la VM y comprobamos que Debian ve el disco nuevo, vacío y sin particiones:

```bash
lsblk
```

```text
NAME   MAJ:MIN RM  SIZE RO TYPE MOUNTPOINTS
vda    254:0    0   20G  0 disk
├─vda1 254:1    0   19G  0 part /
...
vdb    254:16   0   50G  0 disk
```

El disco nuevo es `vdb`. Si en tu máquina tiene otro nombre (por ejemplo `sdb`), cámbialo en los comandos siguientes.

## 2. Preparar el disco con LVM

LVM funciona en tres capas:

1. **Volumen físico (PV)**: el disco real (`/dev/vdb`).
2. **Grupo de volúmenes (VG)**: una "bolsa" de espacio formada por uno o varios discos (`vg_oracle`).
3. **Volúmenes lógicos (LV)**: las "particiones" que sacamos de la bolsa (`lv_u01` y `lv_u02`).

```bash
sudo apt update
sudo apt install -y lvm2
sudo pvcreate /dev/vdb
sudo vgcreate vg_oracle /dev/vdb
sudo lvcreate -n lv_u01 -L 15G vg_oracle         # software de Oracle
sudo lvcreate -n lv_u02 -l 100%FREE vg_oracle    # datos: todo lo que queda
sudo lvs
```

- `-L 15G` reserva un tamaño fijo; `-l 100%FREE` usa todo el espacio libre que quede.
- `lvs` muestra los dos volúmenes creados.

Les damos formato ext4 y creamos los puntos de montaje:

```bash
sudo mkfs.ext4 -L ORA_U01 /dev/vg_oracle/lv_u01
sudo mkfs.ext4 -L ORA_U02 /dev/vg_oracle/lv_u02
sudo mkdir -p /u01 /u02
```

Para que se monten solos en cada arranque, los añadimos a `/etc/fstab`:

```bash
echo '/dev/vg_oracle/lv_u01  /u01  ext4  defaults  0  2' | sudo tee -a /etc/fstab
echo '/dev/vg_oracle/lv_u02  /u02  ext4  defaults  0  2' | sudo tee -a /etc/fstab
sudo systemctl daemon-reload
sudo mount -a
df -h /u01 /u02
```

`mount -a` monta todo lo que hay en `fstab`: si no da error, el fichero está bien escrito. `df -h` debe mostrar `/u01` con unos 15 GB y `/u02` con unos 35 GB.

!!! tip "Ampliar más adelante"
    Si añades otro disco (`vdc`), basta con `pvcreate /dev/vdc`, `vgextend vg_oracle /dev/vdc` y `lvextend -r -l +100%FREE /dev/vg_oracle/lv_u02`. La opción `-r` agranda también el sistema de ficheros.

## 3. Nombre del servidor

Oracle guarda el nombre del servidor en su configuración de red, así que debe resolver a la IP real. Debian añade una línea `127.0.1.1` con el nombre del equipo que hace que Oracle escuche solo en local; la borramos.

```bash
sudo hostnamectl set-hostname oraserver.ruben.asir
sudo sed -i '/^127\.0\.1\.1/d' /etc/hosts
echo "192.168.122.20   oraserver.ruben.asir   oraserver" | sudo tee -a /etc/hosts
hostname -f
getent hosts oraserver.ruben.asir
```

Los dos últimos comandos deben devolver `oraserver.ruben.asir` y `192.168.122.20`. La IP de la máquina tiene que ser fija (configurada en `/etc/network/interfaces` o con una reserva DHCP en libvirt).

## 4. Paquetes necesarios

```bash
sudo apt install -y \
  binutils gcc g++ make libc6-dev \
  libaio1t64 libaio-dev libnsl2 libstdc++6 \
  libelf-dev elfutils ksh bc unzip \
  net-tools sysstat psmisc lsof \
  libxi6 libxtst6 libxrender1 rlwrap rpm
```

- `gcc`, `make` y `binutils`: Oracle compila y enlaza sus programas durante la instalación.
- `libaio`: lectura y escritura asíncrona en disco, la usa el motor de la base de datos.
- `rlwrap`: añade historial y flechas a `sqlplus`.
- `rpm`: el asistente `dbca` consulta los paquetes con `rpm` porque está pensado para Oracle Linux. Instalando el paquete evitamos que falle.

En Debian 13 la librería se llama `libaio.so.1t64`, pero Oracle busca `libaio.so.1`. Creamos un enlace con el nombre que espera:

```bash
sudo ln -sf /usr/lib/x86_64-linux-gnu/libaio.so.1t64 /usr/lib/x86_64-linux-gnu/libaio.so.1
sudo ldconfig
ldconfig -p | grep libaio.so.1
```

## 5. Usuario y grupos

```bash
sudo groupadd -g 54321 oinstall
sudo groupadd -g 54322 dba
sudo groupadd -g 54323 oper
sudo useradd -m -u 54321 -g oinstall -G dba,oper -s /bin/bash oracle
sudo passwd oracle
id oracle
```

- `oinstall`: grupo propietario del software.
- `dba`: sus miembros entran en la base de datos como administrador (`sqlplus / as sysdba`).
- `oper`: solo pueden arrancar y parar la base de datos.

## 6. Parámetros del kernel y límites

Oracle necesita más memoria compartida, semáforos y ficheros abiertos de los que trae Debian por defecto. Los ponemos en un fichero propio dentro de `/etc/sysctl.d/`:

```bash
sudo tee /etc/sysctl.d/98-oracle.conf > /dev/null <<'EOF'
fs.file-max = 6815744
fs.aio-max-nr = 1048576
kernel.sem = 250 32000 100 128
kernel.shmmni = 4096
kernel.shmall = 1073741824
kernel.shmmax = 4398046511104
kernel.panic_on_oops = 1
net.core.rmem_default = 262144
net.core.rmem_max = 4194304
net.core.wmem_default = 262144
net.core.wmem_max = 1048576
net.ipv4.ip_local_port_range = 9000 65500
EOF
sudo sysctl --system
```

Y los límites del usuario `oracle` (procesos, ficheros abiertos y pila):

```bash
sudo tee /etc/security/limits.d/99-oracle.conf > /dev/null <<'EOF'
oracle   soft   nofile    1024
oracle   hard   nofile    65536
oracle   soft   nproc     16384
oracle   hard   nproc     16384
oracle   soft   stack     10240
oracle   hard   stack     32768
EOF
```

## 7. Directorios en el disco nuevo

Repartimos Oracle entre los dos volúmenes: el software y el inventario en `/u01`; los ficheros de datos y las copias de recuperación en `/u02`.

```bash
sudo mkdir -p /u01/app/oracle/product/23.26/dbhome_1
sudo mkdir -p /u01/app/oraInventory
sudo mkdir -p /u02/oradata /u02/fra /u02/instalador
sudo chown -R oracle:oinstall /u01 /u02
sudo chmod -R 775 /u01 /u02
```

| Ruta | Para qué |
|---|---|
| `/u01/app/oracle/product/23.26/dbhome_1` | Software de Oracle (`ORACLE_HOME`) |
| `/u01/app/oraInventory` | Inventario: registro de lo que hay instalado |
| `/u02/oradata` | Ficheros de datos de la base de datos |
| `/u02/fra` | Área de recuperación (copias y registros) |
| `/u02/instalador` | Sitio temporal para el ZIP de instalación |

## 8. Variables de entorno del usuario oracle

Las añadimos al final del `.profile` de `oracle`, que se lee cada vez que entramos con `sudo -iu oracle`:

```bash
sudo tee -a /home/oracle/.profile > /dev/null <<'EOF'

# Oracle AI Database 26ai
export ORACLE_BASE=/u01/app/oracle
export ORACLE_HOME=$ORACLE_BASE/product/23.26/dbhome_1
export ORACLE_SID=RUBCDB
export PATH=$ORACLE_HOME/bin:$PATH
export LD_LIBRARY_PATH=$ORACLE_HOME/lib
export NLS_LANG=SPANISH_SPAIN.AL32UTF8
export CV_ASSUME_DISTID=OL8
alias sqlp='rlwrap sqlplus / as sysdba'
EOF
sudo -iu oracle env | grep -E 'ORACLE|CV_'
```

- `ORACLE_HOME`: dónde está el software.
- `ORACLE_SID`: nombre de la instancia con la que trabajamos.
- `CV_ASSUME_DISTID=OL8`: hace creer al instalador que está en Oracle Linux 8, porque Debian no está soportado oficialmente.

## 9. Descargar y descomprimir Oracle

1. En tu equipo, descarga **Oracle AI Database 26ai for Linux x86-64 (ZIP)** desde la [web de Oracle](https://www.oracle.com/database/technologies/oracle23ai-linux-downloads.html). Necesitas una cuenta gratuita.
2. Cópialo al servidor, directamente al disco de Oracle:

```bash
scp LINUX.X64_2326100_db_home.zip usuario@192.168.122.20:/u02/instalador/
```

Si tu fichero tiene otro número de versión, cambia el nombre en los comandos.

**(oracle)** Entramos como `oracle` y descomprimimos en el `ORACLE_HOME`. Una *Gold Image* es el software ya instalado y empaquetado: solo hay que descomprimirlo y registrarlo.

```bash
sudo -iu oracle
unzip -q /u02/instalador/LINUX.X64_2326100_db_home.zip -d $ORACLE_HOME
ls $ORACLE_HOME | head
```

## 10. Instalar el software con un fichero de respuesta

Un fichero de respuesta (`.rsp`) guarda las respuestas que daríamos en el asistente gráfico. Oracle trae una plantilla; la copiamos y la editamos.

**(oracle)**

```bash
mkdir -p ~/rsp
cp $ORACLE_HOME/install/response/db_install.rsp ~/rsp/db_install.rsp
nano ~/rsp/db_install.rsp
```

Buscamos (con `Ctrl+W` en nano) cada una de estas líneas y les ponemos el valor:

```ini
installOption=INSTALL_DB_SWONLY
UNIX_GROUP_NAME=oinstall
INVENTORY_LOCATION=/u01/app/oraInventory
ORACLE_HOME=/u01/app/oracle/product/23.26/dbhome_1
ORACLE_BASE=/u01/app/oracle
installEdition=EE
OSDBA=dba
OSOPER=oper
OSBACKUPDBA=dba
OSDGDBA=dba
OSKMDBA=dba
OSRACDBA=dba
```

- `INSTALL_DB_SWONLY`: instala solo el software; la base de datos la crearemos después.
- `installEdition=EE`: Enterprise Edition.
- Los `OS...` indican qué grupo del sistema tiene cada tipo de permiso de administración.

Comprobamos que quedaron bien (muestra solo las líneas con valor):

```bash
grep -v '^#' ~/rsp/db_install.rsp | grep -v '=$' | grep =
```

Lanzamos el instalador. Tarda unos minutos:

```bash
cd $ORACLE_HOME
./runInstaller -silent -ignorePrereqFailure -waitforcompletion \
  -responseFile /home/oracle/rsp/db_install.rsp
```

El aviso `[INS-13001] Oracle Database is not supported on this operating system` es normal en Debian. Al terminar, pide ejecutar dos scripts como root. Salimos de `oracle` (`exit`) y los ejecutamos:

```bash
exit
sudo /u01/app/oraInventory/orainstRoot.sh
sudo /u01/app/oracle/product/23.26/dbhome_1/root.sh
```

Si `root.sh` pregunta por el directorio *local bin*, pulsamos Enter. Ya podemos borrar el ZIP:

```bash
sudo rm /u02/instalador/LINUX.X64_2326100_db_home.zip
sudo -iu oracle sqlplus -V
```

## 11. Configurar el listener

El *listener* es el proceso que escucha en el puerto 1521 y recibe las conexiones de los clientes. Lo configuramos en `listener.ora`:

**(oracle)**

```bash
sudo -iu oracle
cat > $ORACLE_HOME/network/admin/listener.ora <<'EOF'
LISTENER =
  (DESCRIPTION_LIST =
    (DESCRIPTION =
      (ADDRESS = (PROTOCOL = TCP)(HOST = oraserver.ruben.asir)(PORT = 1521))
      (ADDRESS = (PROTOCOL = IPC)(KEY = EXTPROC1521))
    )
  )
EOF
lsnrctl start
lsnrctl status
```

- `PROTOCOL = TCP`: conexiones por red, en el nombre del servidor y el puerto 1521.
- `PROTOCOL = IPC`: conexiones locales dentro del propio servidor.

`lsnrctl status` debe terminar con `The command completed successfully`. El mensaje "The listener supports no services" es normal: aún no hay base de datos.

## 12. Crear la base de datos con un fichero de respuesta

Igual que antes, copiamos la plantilla de `dbca` (el asistente que crea bases de datos) y la editamos.

**(oracle)**

```bash
cp $ORACLE_HOME/assistants/dbca/dbca.rsp ~/rsp/dbca.rsp
nano ~/rsp/dbca.rsp
```

Valores a poner:

```ini
gdbName=RUBCDB
sid=RUBCDB
databaseConfigType=SI
createAsContainerDatabase=true
numberOfPDBs=1
pdbName=RUBPDB1
templateName=General_Purpose.dbc
storageType=FS
datafileDestination=/u02/oradata
recoveryAreaDestination=/u02/fra
recoveryAreaSize=10240
characterSet=AL32UTF8
nationalCharacterSet=AL16UTF16
listeners=LISTENER
memoryMgmtType=AUTO_SGA
totalMemory=2048
databaseType=MULTIPURPOSE
emConfiguration=NONE
sampleSchema=false
```

- `gdbName` y `sid`: nombre de la base de datos y de la instancia (`RUBCDB`).
- `createAsContainerDatabase=true` + `pdbName`: arquitectura *multitenant*. La CDB (contenedor) guarda el diccionario de Oracle y nuestros datos irán en la PDB `RUBPDB1`.
- `datafileDestination` y `recoveryAreaDestination`: los datos van al **disco nuevo** (`/u02`).
- `totalMemory=2048`: 2 GB para Oracle; adecuado con 4 GB de RAM (con 8 GB pon 4096).
- `listeners=LISTENER`: la base de datos se registra en el listener del paso anterior.

Las contraseñas **no** las escribimos en el fichero. Las pedimos por teclado (no se ven al escribir) y se las pasamos a `dbca`:

```bash
read -s -p "Contraseña para SYS, SYSTEM y PDBADMIN: " ORA_PWD; echo
dbca -silent -createDatabase -responseFile /home/oracle/rsp/dbca.rsp \
  -sysPassword "$ORA_PWD" -systemPassword "$ORA_PWD" -pdbAdminPassword "$ORA_PWD" \
  -ignorePrereqFailure
```

Tarda entre 10 y 30 minutos. El aviso `DBT-06801` sobre el tamaño del área de recuperación es solo informativo. Si algo falla, el registro está en `/u01/app/oracle/cfgtoollogs/dbca/RUBCDB/`.

Comprobamos que los ficheros de datos están en el disco nuevo y que el listener ya ve la base de datos:

```bash
ls /u02/oradata/RUBCDB/
df -h /u02
lsnrctl services | grep -E 'Service|READY'
```

Deben aparecer los servicios `RUBCDB` y `rubpdb1`.

## 13. Parámetros de arranque en el SPFILE

Cuando la instancia arranca, lee sus parámetros de un fichero. Oracle usa el **SPFILE** (`$ORACLE_HOME/dbs/spfileRUBCDB.ora`), un fichero binario que se modifica con `ALTER SYSTEM`. Al cambiar un parámetro elegimos dónde se aplica con `SCOPE`:

| SCOPE | Qué hace |
|---|---|
| `MEMORY` | Se aplica ahora y se pierde al reiniciar |
| `SPFILE` | Se guarda en el SPFILE y se aplica en el próximo arranque |
| `BOTH` | Se aplica ahora y se guarda (lo normal) |

**(oracle)** Entramos como administrador con `sqlp` (el alias que creamos) y consultamos los nombres de la instancia y del servicio:

```sql
SHOW PARAMETER spfile
SHOW PARAMETER db_name
SHOW PARAMETER instance_name
SHOW PARAMETER service_names
```

- `spfile`: ruta del SPFILE en uso; si sale vacío, la instancia arrancó con un fichero de texto.
- `db_name`: nombre de la base de datos (`RUBCDB`).
- `instance_name`: nombre de la instancia, igual que el `ORACLE_SID`.
- `service_names`: nombre de servicio con el que se anuncia al listener (`RUBCDB`). La PDB tiene su propio servicio, `rubpdb1`.

Ahora cambiamos algunos parámetros:

```sql
-- Dirección del listener en el que se registra la instancia
ALTER SYSTEM SET local_listener='(ADDRESS=(PROTOCOL=TCP)(HOST=oraserver.ruben.asir)(PORT=1521))' SCOPE=BOTH;
ALTER SYSTEM REGISTER;

-- Más sesiones simultáneas: es un parámetro estático, solo se aplica al reiniciar
ALTER SYSTEM SET processes=400 SCOPE=SPFILE;

-- Más cursores abiertos por sesión: se aplica al momento
ALTER SYSTEM SET open_cursors=500 SCOPE=BOTH;

-- Que la PDB se abra sola cada vez que arranque la base de datos
ALTER PLUGGABLE DATABASE RUBPDB1 SAVE STATE;

-- Copia en texto del SPFILE, guardada en el disco de datos
CREATE PFILE='/u02/initRUBCDB_copia.ora' FROM SPFILE;
EXIT
```

Podemos leer la copia en texto para ver todos los parámetros:

```bash
cat /u02/initRUBCDB_copia.ora
```

Comprobaremos en el paso 16 que `processes` vale 400 después de reiniciar: eso demuestra que el SPFILE guarda los cambios.

## 14. Configurar tnsnames.ora

`tnsnames.ora` asocia un nombre corto (alias) con la dirección completa de una base de datos. `dbca` ya creó el fichero; hacemos una copia y añadimos nuestros alias.

**(oracle)**

```bash
cd $ORACLE_HOME/network/admin
cp tnsnames.ora tnsnames.ora.copia
cat tnsnames.ora
```

Si en la salida **no** aparece ya `RUBCDB =`, lo añadimos junto con `RUBPDB1` (si ya aparece, añade solo el bloque de `RUBPDB1`):

```bash
cat >> tnsnames.ora <<'EOF'

RUBCDB =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)(HOST = oraserver.ruben.asir)(PORT = 1521))
    (CONNECT_DATA =
      (SERVER = DEDICATED)
      (SERVICE_NAME = RUBCDB)
    )
  )

RUBPDB1 =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)(HOST = oraserver.ruben.asir)(PORT = 1521))
    (CONNECT_DATA =
      (SERVER = DEDICATED)
      (SERVICE_NAME = rubpdb1)
    )
  )
EOF
tnsping RUBCDB
tnsping RUBPDB1
```

Los dos `tnsping` deben terminar en `OK`.

## 15. Arranque automático con systemd

Primero marcamos la instancia con `Y` en `/etc/oratab`. Los scripts de Oracle `dbstart` y `dbshut` solo arrancan y paran las instancias marcadas así.

```bash
exit     # volvemos a nuestro usuario
sudo sed -i 's|^\(RUBCDB:[^:]*\):N$|\1:Y|' /etc/oratab
grep ^RUBCDB /etc/oratab
```

Creamos el servicio. La línea clave es `RequiresMountsFor`: systemd **espera a que el disco de Oracle esté montado** antes de arrancar la base de datos. Si el disco falla, Oracle no intenta arrancar sin sus ficheros.

```bash
sudo tee /etc/systemd/system/oracle-rubcdb.service > /dev/null <<'EOF'
[Unit]
Description=Oracle AI Database 26ai (RUBCDB) en disco dedicado
After=network-online.target
Wants=network-online.target
RequiresMountsFor=/u01 /u02

[Service]
Type=oneshot
RemainAfterExit=yes
User=oracle
Group=oinstall
Environment=ORACLE_HOME=/u01/app/oracle/product/23.26/dbhome_1
Environment=ORACLE_BASE=/u01/app/oracle
ExecStart=/u01/app/oracle/product/23.26/dbhome_1/bin/dbstart /u01/app/oracle/product/23.26/dbhome_1
ExecStop=/u01/app/oracle/product/23.26/dbhome_1/bin/dbshut /u01/app/oracle/product/23.26/dbhome_1
TimeoutSec=600
LimitNOFILE=65536
LimitNPROC=16384

[Install]
WantedBy=multi-user.target
EOF
```

- `dbstart $ORACLE_HOME`: arranca el listener y todas las instancias con `Y` en `oratab`. `dbshut` las para.
- `Type=oneshot` + `RemainAfterExit=yes`: el script termina, pero el servicio sigue apareciendo como activo.
- `Limit...`: systemd no lee `limits.conf`, por eso repetimos aquí los límites.

Paramos lo que arrancamos a mano y dejamos que lo gestione systemd:

```bash
sudo -iu oracle bash -c 'echo "SHUTDOWN IMMEDIATE" | sqlplus -s / as sysdba; lsnrctl stop'
sudo systemctl daemon-reload
sudo systemctl enable --now oracle-rubcdb.service
systemctl status oracle-rubcdb.service --no-pager
```

Debe quedar `active (exited)`. Si falla: `journalctl -u oracle-rubcdb -n 50 --no-pager`.

## 16. Abrir el puerto y probar un reinicio

Si usas cortafuegos, permitimos el puerto 1521 solo desde la red local:

```bash
sudo apt install -y ufw
sudo ufw allow 22/tcp
sudo ufw allow from 192.168.122.0/24 to any port 1521 proto tcp
sudo ufw enable
sudo ufw status
```

La regla del puerto 22 va antes de `enable` para no perder la conexión SSH.

Reiniciamos el servidor y comprobamos que todo vuelve solo:

```bash
sudo reboot
```

```bash
df -h /u01 /u02
systemctl is-active oracle-rubcdb
sudo -iu oracle bash -c 'echo "SHOW PARAMETER processes" | sqlplus -s / as sysdba'
```

`processes` debe valer `400`: el cambio con `SCOPE=SPFILE` se aplicó en el arranque.

## 17. Usuario, tablas y datos

Creamos en la PDB el usuario `ruben`, que podrá conectarse por red y tendrá sus propias tablas.

**(oracle)** `sqlplus system@RUBPDB1`:

```sql
CREATE USER ruben IDENTIFIED BY "<CONTRASEÑA>"
  DEFAULT TABLESPACE users QUOTA UNLIMITED ON users;
GRANT CREATE SESSION, CREATE TABLE, CREATE VIEW, CREATE SEQUENCE TO ruben;
EXIT
```

- `CREATE SESSION`: puede conectarse.
- `CREATE TABLE`, `CREATE VIEW`, `CREATE SEQUENCE`: puede crear objetos en su propio esquema.
- `QUOTA UNLIMITED ON users`: puede ocupar espacio en el *tablespace* `USERS` (que está en `/u02`).

Ahora entramos como `ruben` (`sqlplus ruben@RUBPDB1`) y creamos tres tablas de una pequeña biblioteca:

```sql
CREATE TABLE socios (
  id_socio  NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  nombre    VARCHAR2(60)  NOT NULL,
  email     VARCHAR2(100) UNIQUE
);

CREATE TABLE libros (
  id_libro  NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  titulo    VARCHAR2(120) NOT NULL,
  autor     VARCHAR2(80),
  anio      NUMBER(4)
);

CREATE TABLE prestamos (
  id_prestamo NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  id_socio    NUMBER NOT NULL REFERENCES socios(id_socio),
  id_libro    NUMBER NOT NULL REFERENCES libros(id_libro),
  fecha       DATE DEFAULT SYSDATE
);

INSERT INTO socios (nombre, email) VALUES ('Lucia Marquez', 'lucia@ejemplo.es');
INSERT INTO socios (nombre, email) VALUES ('Javier Ortega', 'javier@ejemplo.es');
INSERT INTO socios (nombre, email) VALUES ('Carmen Vidal',  'carmen@ejemplo.es');

INSERT INTO libros (titulo, autor, anio) VALUES ('La sombra del viento', 'Carlos Ruiz Zafon', 2001);
INSERT INTO libros (titulo, autor, anio) VALUES ('Dune', 'Frank Herbert', 1965);
INSERT INTO libros (titulo, autor, anio) VALUES ('El nombre del viento', 'Patrick Rothfuss', 2007);

INSERT INTO prestamos (id_socio, id_libro) VALUES (1, 2);
INSERT INTO prestamos (id_socio, id_libro) VALUES (2, 1);
INSERT INTO prestamos (id_socio, id_libro) VALUES (3, 3);
COMMIT;

SELECT s.nombre, l.titulo, p.fecha
  FROM prestamos p
  JOIN socios s ON s.id_socio = p.id_socio
  JOIN libros l ON l.id_libro = p.id_libro;
```

`GENERATED ALWAYS AS IDENTITY` hace que Oracle numere solo los identificadores (1, 2, 3...). No olvides el `COMMIT`: sin él, los datos no se guardan para las demás sesiones.

## 18. Cliente remoto con SQLcl

En la máquina cliente usamos **SQLcl**, el cliente de línea de comandos de Oracle hecho en Java. No necesita librerías de Oracle instaladas en el sistema y entiende `tnsnames.ora`.

```bash
sudo apt update
sudo apt install -y openjdk-21-jre-headless unzip
wget https://download.oracle.com/otn_software/java/sqldeveloper/sqlcl-latest.zip
sudo unzip -q sqlcl-latest.zip -d /opt/
sudo ln -sf /opt/sqlcl/bin/sql /usr/local/bin/sql
sql -V
```

Creamos el `tnsnames.ora` del cliente con la IP del servidor:

```bash
mkdir -p ~/oracle
cat > ~/oracle/tnsnames.ora <<'EOF'
RUBPDB1 =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)(HOST = 192.168.122.20)(PORT = 1521))
    (CONNECT_DATA =
      (SERVER = DEDICATED)
      (SERVICE_NAME = rubpdb1)
    )
  )
EOF
echo 'export TNS_ADMIN=$HOME/oracle' >> ~/.bashrc
source ~/.bashrc
```

`TNS_ADMIN` le dice al cliente en qué carpeta buscar `tnsnames.ora`.

Probamos que el puerto responde y nos conectamos:

```bash
nc -zv 192.168.122.20 1521
sql ruben@RUBPDB1
```

También se puede conectar sin `tnsnames.ora`, escribiendo la dirección completa (formato *EZConnect*):

```bash
sql ruben@//192.168.122.20:1521/rubpdb1
```

Una vez dentro, comprobamos desde dónde estamos conectados y consultamos los datos:

```sql
SELECT sys_context('USERENV','CON_NAME')   AS contenedor,
       sys_context('USERENV','IP_ADDRESS') AS ip_cliente
  FROM dual;
SELECT table_name FROM user_tables;
SELECT * FROM libros;
```

Debe mostrar `RUBPDB1` como contenedor, la IP del cliente (192.168.122.50) y las tres tablas.

## Problemas frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| `lsblk` no muestra `vdb` | El disco no se añadió o la VM no se reinició | Revisar el hardware de la VM y reiniciarla |
| `mount -a` da error | Línea mal escrita en `/etc/fstab` | Revisar `/etc/fstab` **antes de reiniciar** (si no, Debian puede no arrancar) |
| `libaio.so.1: cannot open shared object file` | Falta el enlace de la librería | Repetir el enlace del paso 4 y `sudo ldconfig` |
| `[INS-13001] ... not supported` | Debian no está soportado | Es un aviso; comprobar que `CV_ASSUME_DISTID=OL8` está cargado |
| `sqlplus: orden no encontrada` | Variables sin cargar | Entrar con `sudo -iu oracle` (con `-i`) |
| `ORA-12541: no listener` | Listener parado | `sudo systemctl restart oracle-rubcdb` |
| `ORA-12514: listener does not currently know of service` | La base de datos no se ha registrado | `ALTER SYSTEM REGISTER;` y esperar unos segundos |
| `ORA-12170` o tiempo agotado desde el cliente | Cortafuegos o IP | `sudo ufw status` y comprobar `/etc/hosts` del servidor |
| `ORA-01017` al conectar con `ruben` | Conexión a la CDB en lugar de a la PDB | Usar el alias `RUBPDB1` |
| `oracle-rubcdb` no arranca tras reiniciar | Disco no montado o `oratab` sin `Y` | `df -h /u01 /u02`, `grep RUBCDB /etc/oratab` y `journalctl -u oracle-rubcdb` |

## Fuentes

- [Descarga de Oracle AI Database 26ai para Linux](https://www.oracle.com/database/technologies/oracle23ai-linux-downloads.html)
- [ORACLE-BASE: instalación de Oracle 26ai en Oracle Linux 9](https://oracle-base.com/articles/26/oracle-db-26-installation-on-oracle-linux-9)
- [Oracle Database 26 Reference: SERVICE_NAMES](https://docs.oracle.com/en/database/oracle/oracle-database/26/refrn/SERVICE_NAMES.html)
- [Notas de versión de Oracle SQLcl](https://www.oracle.com/tools/sqlcl/sqlcl-relnotes-25.2.html)
- [Manual de LVM en Debian (`man lvm`)](https://manpages.debian.org/trixie/lvm2/lvm.8.en.html)
