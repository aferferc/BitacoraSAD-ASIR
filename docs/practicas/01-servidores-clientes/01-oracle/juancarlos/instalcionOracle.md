

# Instalación de Oracle AI Database 26ai Enterprise en Debian 13 mediante RPM (Por Juan Carlos)

RPM de Oracle Linux 9 funciona en Debian 13, ya que los binarios están compilados contra una glibc más antigua que la de Debian 13 y Linux ejecuta sin problema binarios enlazados con una glibc anterior. Si es verdad que el instalador del RPM (`dnf`/`rpm` con sus scripts) no funciona así que lo sustituiremos por pasos manuales.

Los comandos llevan una etiqueta:

- (**admin**): usuario con `sudo`.
- (**oracle**): sesión del usuario `oracle`.

## 1. Requisitos y comprobaciones iniciales

**(admin)** Comprobamos arquitectura, sistema, memoria, swap y disco:

```sh
uname -m
grep PRETTY_NAME /etc/os-release
free -h
swapon --show
df -h /opt /tmp
```

Necesitamos `x86_64`, Debian GNU/Linux 13, 4 GB de RAM o más (mínimo 2 GB), swap, al menos 25 GB libres en `/opt` y 1 GB libre en `/tmp`. Con 4 GB de RAM usaremos `totalMemory=2048` en la creación de la base de datos.

## 2. Descarga y transferencia del RPM

1. Descargamos el RPM **OL9** de Oracle AI Database 26ai (Linux x86-64) desde https://www.oracle.com/database/technologies/oracle26ai-linux-downloads.html. Hace falta una cuenta gratuita de Oracle.
2. Lo copiamos a la máquina Debian desde nuestro equipo:

```sh
scp oracle-ai-database-ee-26ai-1.0-1.el9.x86_64.rpm debian@IP_DEL_SERVIDOR:~/
```

## 3. Paquetes necesarios

**(admin)** Instalamos las dependencias, más las herramientas para abrir el RPM (`rpm`, `rpm2cpio`, `cpio`):

```sh
sudo apt update
sudo apt install -y \
  binutils gcc g++ make libc6-dev \
  libaio-dev libaio1t64 libnsl2 libstdc++6 \
  libelf-dev elfutils ksh bc unzip \
  net-tools sysstat psmisc lsof \
  libxi6 libxtst6 libxrender1 rlwrap \
  rpm rpm2cpio cpio
```

Debian 13 empaqueta `libaio` con el sufijo `t64`, pero Oracle busca `libaio.so.1`. Creamos el enlace y refrescamos la caché:

```sh
sudo ln -sf /usr/lib/x86_64-linux-gnu/libaio.so.1t64 /usr/lib/x86_64-linux-gnu/libaio.so.1
sudo ldconfig
ldconfig -p | grep -E 'libaio.so.1|libnsl'
```

Salida:

```txt
juanka@base:~$ sudo ln -sf /usr/lib/x86_64-linux-gnu/libaio.so.1t64 /usr/lib/x86_64-linux-gnu/libaio.so.1
sudo ldconfig
ldconfig -p | grep -E 'libaio.so.1|libnsl'
	libnsl.so.2 (libc6,x86-64) => /lib/x86_64-linux-gnu/libnsl.so.2
	libnsl.so.1 (libc6,x86-64) => /lib/x86_64-linux-gnu/libnsl.so.1
	libaio.so.1t64 (libc6,x86-64) => /lib/x86_64-linux-gnu/libaio.so.1t64
```

Deben aparecer `libaio.so.1` y `libnsl.so.2`. Si falta `libnsl.so.1`, lo enlazamos:

```sh
[ -e /usr/lib/x86_64-linux-gnu/libnsl.so.1 ] || sudo ln -s /usr/lib/x86_64-linux-gnu/libnsl.so.2 /usr/lib/x86_64-linux-gnu/libnsl.so.1
sudo ldconfig
```

## 4. Nombre del servidor y `/etc/hosts`

Oracle exige que el nombre completo (FQDN) resuelva a la **IP real** de la máquina. Debian añade una línea `127.0.1.1` con el hostname, que causa problemas con el Listener, así que la eliminamos.

```sh
sudo hostnamectl set-hostname oradeb.abd.local
sudo sed -i '/^127\.0\.1\.1/d' /etc/hosts
IP=$(hostname -I | awk '{print $1}')
echo "$IP   oradeb.abd.local   oradeb" | sudo tee -a /etc/hosts
```

Comprobamos que resuelve a una dirección IPv4 y no a una fe80::

```sh
hostname -f
getent ahostsv4 oradeb.abd.local
ping -c1 oradeb.abd.local
```

```txt
juanka@base:~$ hostname -f
getent ahostsv4 oradeb.abd.local
ping -c1 oradeb.abd.local
oradeb.abd.local
192.168.122.80  STREAM oradeb.abd.local
192.168.122.80  DGRAM  
192.168.122.80  RAW    
PING oradeb.abd.local (192.168.122.80) 56(84) bytes of data.
64 bytes from oradeb.abd.local (192.168.122.80): icmp_seq=1 ttl=64 time=0.074 ms

--- oradeb.abd.local ping statistics ---
1 packets transmitted, 1 received, 0% packet loss, time 0ms
rtt min/avg/max/mdev = 0.074/0.074/0.074/0.000 ms
```

## 5. Grupos y usuario `oracle`

Replicamos lo que haría el paquete `oracle-ai-database-preinstall-26ai` en Oracle Linux, que no existe para Debian.

```sh
sudo groupadd -g 54321 oinstall
sudo groupadd -g 54322 dba
sudo groupadd -g 54323 oper
sudo groupadd -g 54324 backupdba
sudo groupadd -g 54325 dgdba
sudo groupadd -g 54326 kmdba
sudo groupadd -g 54330 racdba
sudo useradd -m -u 54321 -g oinstall -G dba,oper,backupdba,dgdba,kmdba,racdba -s /bin/bash oracle
sudo passwd oracle
id oracle
```

## 6. Parámetros del kernel

En lugar de tocar `/etc/sysctl.conf`, creamos un fichero propio, que es más limpio y reversible:

```sh
sudo tee /etc/sysctl.d/97-oracle-ai-database.conf <<'EOF'
# Oracle AI Database 26ai
fs.file-max = 6815744
fs.aio-max-nr = 1048576
kernel.sem = 250 32000 100 128
kernel.shmmni = 4096
kernel.shmall = 1073741824
kernel.shmmax = 4398046511104
kernel.panic_on_oops = 1
kernel.panic = 10
net.core.rmem_default = 262144
net.core.rmem_max = 4194304
net.core.wmem_default = 262144
net.core.wmem_max = 1048576
net.ipv4.ip_local_port_range = 9000 65500
EOF
sudo sysctl --system > /dev/null
sysctl fs.aio-max-nr kernel.sem kernel.shmmax
```

Salida: 

```txt
juanka@base:~$ sudo tee /etc/sysctl.d/97-oracle-ai-database.conf <<'EOF'
# Oracle AI Database 26ai
fs.file-max = 6815744
fs.aio-max-nr = 1048576
kernel.sem = 250 32000 100 128
kernel.shmmni = 4096
kernel.shmall = 1073741824
kernel.shmmax = 4398046511104
kernel.panic_on_oops = 1
kernel.panic = 10
net.core.rmem_default = 262144
net.core.rmem_max = 4194304
net.core.wmem_default = 262144
net.core.wmem_max = 1048576
net.ipv4.ip_local_port_range = 9000 65500
EOF
sudo sysctl --system > /dev/null
sysctl fs.aio-max-nr kernel.sem kernel.shmmax
# Oracle AI Database 26ai
fs.file-max = 6815744
fs.aio-max-nr = 1048576
kernel.sem = 250 32000 100 128
kernel.shmmni = 4096
kernel.shmall = 1073741824
kernel.shmmax = 4398046511104
kernel.panic_on_oops = 1
kernel.panic = 10
net.core.rmem_default = 262144
net.core.rmem_max = 4194304
net.core.wmem_default = 262144
net.core.wmem_max = 1048576
net.ipv4.ip_local_port_range = 9000 65500
fs.aio-max-nr = 1048576
kernel.sem = 250	32000	100	128
kernel.shmmax = 4398046511104
```

## 7. Límites de recursos del usuario `oracle`

```sh
sudo tee /etc/security/limits.d/30-oracle.conf <<'EOF'
oracle   soft   nofile    1024
oracle   hard   nofile    65536
oracle   soft   nproc     16384
oracle   hard   nproc     16384
oracle   soft   stack     10240
oracle   hard   stack     32768
oracle   soft   memlock   134217728
oracle   hard   memlock   134217728
EOF
```

Nos aseguramos de que `su` aplique `pam_limits`. El comando es idempotente: solo añade la línea si no existe.

```sh
grep -q '^session.*pam_limits.so' /etc/pam.d/su || echo 'session required pam_limits.so' | sudo tee -a /etc/pam.d/su
sudo su - oracle -c 'ulimit -n; ulimit -u; ulimit -s'
```

Deben salir `1024`, `16384` y `10240`.

```txt
juanka@base:~$ grep -q '^session.*pam_limits.so' /etc/pam.d/su || echo 'session required pam_limits.so' | sudo tee -a /etc/pam.d/su
sudo su - oracle -c 'ulimit -n; ulimit -u; ulimit -s'
1024
16384
10240
```

## 8. Inspección del RPM

Antes de extraerlo, miramos qué haría el instalador oficial en sus scripts `%pre` y `%post`. Así sabemos exactamente qué tenemos que reproducir a mano:

```sh
RPM_FILE=$HOME/oracle-ai-database-ee-26ai-1.0-1.el9.x86_64.rpm
rpm -qip "$RPM_FILE"
rpm -qp --scripts "$RPM_FILE" > ~/rpm-scripts.txt
less ~/rpm-scripts.txt
```

- `rpm -qip` muestra versión y tamaño.
- `rpm-scripts.txt` conviene guardarlo como evidencia para la documentación.
- Buscamos en él referencias a `orainstRoot.sh`, `root.sh`, `/etc/oraInst.loc` y a la creación de `/etc/init.d/oracledb_ORCLCDB-26ai`.

# 9. Extracción del contenido y permisos

Preparamos los directorios que usaremos después:

```sh
sudo mkdir -p /opt/oracle/{oradata,fast_recovery_area,oraInventory,scripts}
```

Extraemos el contenido del RPM sobre `/`. Las rutas internas del RPM son relativas (`./home/oracle/oracle/...`), por eso hacemos `cd /` antes. Tarda unos minutos.

```sh
sudo bash -c "cd / && rpm2cpio '$RPM_FILE' | cpio -idm --quiet"
ls /opt/oracle/product/26ai/dbhome_1 | head
du -sh /opt/oracle/product/26ai/dbhome_1
```

Entregamos todo a `oracle:oinstall`:

```sh
sudo chown -R oracle:oinstall /opt/oracle
sudo chmod 775 /opt/oracle /opt/oracle/oraInventory
```

Para no confundirnos, desactivamos los ficheros Red Hat que traía el RPM y que no vamos a usar:

```sh
ls /etc/init.d/oracledb_ORCLCDB-26ai /etc/sysconfig/oracledb_ORCLCDB-26ai.conf 2>/dev/null
sudo rm -f /etc/init.d/oracledb_ORCLCDB-26ai
```

Salida:

```txt
juanka@oradeb:~$ ls /etc/init.d/oracledb_ORCLCDB-26ai /etc/sysconfig/oracledb_ORCLCDB-26ai.conf 2>/dev/null
sudo rm -f /etc/init.d/oracledb_ORCLCDB-26ai
/etc/init.d/oracledb_ORCLCDB-26ai  /etc/sysconfig/oracledb_ORCLCDB-26ai.conf
```

## 10. Variables de entorno

Creamos un fichero propio y lo cargamos desde `~/.profile`. Los shells de login (`su - oracle`, `sudo su - oracle -c ...`) lo leen, y así no hay que tocar el bloque que Debian pone en `.bashrc`.

```sh
sudo tee /home/oracle/.oracle_env <<'EOF'
export TMP=/tmp
export TMPDIR=/tmp
export ORACLE_HOSTNAME=oradeb.abd.local
export ORACLE_BASE=/opt/oracle
export ORACLE_HOME=$ORACLE_BASE/product/26ai/dbhome_1
export ORACLE_SID=ABDCDB
export TNS_ADMIN=$ORACLE_HOME/network/admin
export PATH=$ORACLE_HOME/bin:$PATH
export LD_LIBRARY_PATH=$ORACLE_HOME/lib
export NLS_LANG=AMERICAN_AMERICA.AL32UTF8
export CV_ASSUME_DISTID=OL8
alias sqlp='rlwrap sqlplus / as sysdba'
EOF
sudo chown oracle:oinstall /home/oracle/.oracle_env
echo '[ -f ~/.oracle_env ] && . ~/.oracle_env' | sudo tee -a /home/oracle/.profile
sudo su - oracle -c 'env | grep -E "ORACLE|CV_ASSUME|TNS_ADMIN"'
```

Salida:

```txt
juanka@oradeb:~$ sudo tee /home/oracle/.oracle_env <<'EOF'
export TMP=/tmp
export TMPDIR=/tmp
export ORACLE_HOSTNAME=oradeb.abd.local
export ORACLE_BASE=/opt/oracle
export ORACLE_HOME=$ORACLE_BASE/product/26ai/dbhome_1
export ORACLE_SID=ABDCDB
export TNS_ADMIN=$ORACLE_HOME/network/admin
export PATH=$ORACLE_HOME/bin:$PATH
export LD_LIBRARY_PATH=$ORACLE_HOME/lib
export NLS_LANG=AMERICAN_AMERICA.AL32UTF8
export CV_ASSUME_DISTID=OL8
alias sqlp='rlwrap sqlplus / as sysdba'
EOF
sudo chown oracle:oinstall /home/oracle/.oracle_env
echo '[ -f ~/.oracle_env ] && . ~/.oracle_env' | sudo tee -a /home/oracle/.profile
sudo su - oracle -c 'env | grep -E "ORACLE|CV_ASSUME|TNS_ADMIN"'
export TMP=/tmp
export TMPDIR=/tmp
export ORACLE_HOSTNAME=oradeb.abd.local
export ORACLE_BASE=/opt/oracle
export ORACLE_HOME=$ORACLE_BASE/product/26ai/dbhome_1
export ORACLE_SID=ABDCDB
export TNS_ADMIN=$ORACLE_HOME/network/admin
export PATH=$ORACLE_HOME/bin:$PATH
export LD_LIBRARY_PATH=$ORACLE_HOME/lib
export NLS_LANG=AMERICAN_AMERICA.AL32UTF8
export CV_ASSUME_DISTID=OL8
alias sqlp='rlwrap sqlplus / as sysdba'
[ -f ~/.oracle_env ] && . ~/.oracle_env
ORACLE_BASE=/opt/oracle
ORACLE_HOME=/opt/oracle/product/26ai/dbhome_1
ORACLE_HOSTNAME=oradeb.abd.local
CV_ASSUME_DISTID=OL8
ORACLE_SID=ABDCDB
TNS_ADMIN=/opt/oracle/product/26ai/dbhome_1/network/admin
```

`CV_ASSUME_DISTID=OL8` hace que las herramientas de Oracle crean que están en Oracle Linux 8, que es lo que permite pasar por alto la distro no soportada.

## 11 Registro del home en el inventario de Oracle

Esto sustituye al `runInstaller` de instalación: el software ya está en su sitio y solo hay que **registrarlo**.

**(admin)** Creamos el puntero al inventario:

```sh
sudo tee /etc/oraInst.loc <<'EOF'
inventory_loc=/opt/oracle/oraInventory
inst_group=oinstall
EOF
sudo chown oracle:oinstall /etc/oraInst.loc
sudo chmod 664 /etc/oraInst.loc
```

Salida:

```txt
juanka@oradeb:~$ sudo tee /etc/oraInst.loc <<'EOF'
inventory_loc=/opt/oracle/oraInventory
inst_group=oinstall
EOF
sudo chown oracle:oinstall /etc/oraInst.loc
sudo chmod 664 /etc/oraInst.loc
inventory_loc=/opt/oracle/oraInventory
inst_group=oinstall
```

**(oracle)** Entramos como `oracle` y registramos el home:

```sh
sudo su - oracle
$ORACLE_HOME/runInstaller -silent -attachHome \
  -invPtrLoc /etc/oraInst.loc \
  ORACLE_HOME=$ORACLE_HOME \
  ORACLE_HOME_NAME=OraAI26Home1 \
  ORACLE_BASE=$ORACLE_BASE
exit
```

Un aviso `INS-13001` (sistema operativo no soportado) es esperable. Si `runInstaller` no está en la raíz del home, probamos con `$ORACLE_HOME/oui/bin/runInstaller`.

**(admin)** Ejecutamos los scripts de root. Si `root.sh` pregunta por el directorio local bin, pulsamos Enter:

```sh
sudo /opt/oracle/oraInventory/orainstRoot.sh
sudo /opt/oracle/product/26ai/dbhome_1/root.sh
```

Salida:

```txt
oracle@oradeb:~$ sudo /opt/oracle/oraInventory/orainstRoot.sh
sudo /opt/oracle/product/26ai/dbhome_1/root.sh
sudo: /opt/oracle/oraInventory/orainstRoot.sh: command not found
Check /opt/oracle/product/26ai/dbhome_1/install/root_oradeb.abd.local_2026-10-07_19-06-11-404494197.log for the output of root script
```

Comprobamos el registro y la versión:

```sh
sudo su - oracle -c 'sqlplus -V'
cat /opt/oracle/oraInventory/ContentsXML/inventory.xml
```

La versión debe ser `23.26.1.0.0` y el `inventory.xml` debe listar `OraAI26Home1`.

## 12. Configuración del Listener, escrita a mano

**(oracle)** Entramos de nuevo como `oracle` (`sudo su - oracle`). Creamos `listener.ora` con un listener llamado `LISTENER_ABD` en el puerto 1521. Añadimos una entrada estática (`SID_LIST`) para poder arrancar la base de datos remotamente aunque esté parada.

```sh
cat > $TNS_ADMIN/listener.ora <<'EOF'
LISTENER_ABD =
  (DESCRIPTION_LIST =
    (DESCRIPTION =
      (ADDRESS = (PROTOCOL = TCP)(HOST = oradeb.abd.local)(PORT = 1521))
      (ADDRESS = (PROTOCOL = IPC)(KEY = EXTPROC1521))
    )
  )

SID_LIST_LISTENER_ABD =
  (SID_LIST =
    (SID_DESC =
      (GLOBAL_DBNAME = ABDCDB_STATIC)
      (ORACLE_HOME = /opt/oracle/product/26ai/dbhome_1)
      (SID_NAME = ABDCDB)
    )
  )

ADR_BASE_LISTENER_ABD = /opt/oracle
EOF
lsnrctl start LISTENER_ABD
lsnrctl status LISTENER_ABD
```

Debe aparecer `The command completed successfully` y el servicio estático `ABDCDB_STATIC` en `UNKNOWN`. Eso es normal mientras no exista la instancia.

## 13. Creación de la base de datos CDB + PDB con `dbca`

Seguimos en la sesión **(oracle)**. Pedimos la contraseña sin que quede en el historial y la guardamos en una variable. Con `-listeners` hacemos que la base de datos se registre en nuestro Listener.

```sh
read -s -p "Contraseña para SYS, SYSTEM y PDBADMIN: " ORA_PWD; echo
```

Recomendamos usar `tmux` por si se corta la conexión SSH:

```sh
dbca -silent -createDatabase \
  -templateName General_Purpose.dbc \
  -gdbName ABDCDB -sid ABDCDB \
  -createAsContainerDatabase true \
  -numberOfPDBs 1 -pdbName ABDPDB1 \
  -sysPassword "$ORA_PWD" -systemPassword "$ORA_PWD" -pdbAdminPassword "$ORA_PWD" \
  -databaseConfigType SINGLE \
  -storageType FS -datafileDestination /opt/oracle/oradata \
  -recoveryAreaDestination /opt/oracle/fast_recovery_area -recoveryAreaSize 12288 \
  -characterSet AL32UTF8 -nationalCharacterSet AL16UTF16 \
  -memoryMgmtType AUTO_SGA -totalMemory 2048 \
  -listeners LISTENER_ABD \
  -sampleSchema false -emConfiguration NONE \
  -ignorePrereqFailure
```

- `-totalMemory 2048` se ajusta a la RAM: unos 2 GB para una VM de 4 GB.
- `-ignorePrereqFailure` es necesario porque dbca no reconoce Debian.
- Un aviso `DBT-06801` sobre el tamaño del área de recuperación es normal.
- Si falla, el log está en `/opt/oracle/cfgtoollogs/dbca/ABDCDB/`.

Al terminar comprobamos que el Listener ve la instancia:

```sh
lsnrctl status LISTENER_ABD
ps -ef | grep -E 'pmon|tnslsnr' | grep -v grep
```

Debe aparecer `ora_pmon_ABDCDB` y los servicios `ABDCDB`, `abdpdb1` y `ABDCDBXDB`.

## 14. Parámetros de arranque en el SPFILE

Primero comprobamos qué escribió `dbca`:

```sh
sqlplus -s / as sysdba <<'EOF'
SET LINESIZE 200
SET PAGESIZE 100
COL name FORMAT A28
COL value FORMAT A75
SELECT name, value FROM v$parameter
 WHERE name IN ('spfile','db_name','db_unique_name','instance_name','service_names',
                'local_listener','sga_target','pga_aggregate_target','processes',
                'open_cursors','enable_pluggable_database');
EXIT;
EOF
```

Salida:

```txt

NAME			     VALUE
---------------------------- ---------------------------------------------------------------------------
processes		     300
spfile			     /opt/oracle/product/26ai/dbhome_1/dbs/spfileABDCDB.ora
service_names		     ABDCDB
sga_target		     1610612736
instance_name		     ABDCDB
local_listener		     LISTENER_ABDCDB
db_name 		     ABDCDB
db_unique_name		     ABDCDB
open_cursors		     300
pga_aggregate_target	     536870912
enable_pluggable_database    TRUE

11 filas seleccionadas.
```

Después fijamos los parámetros de identidad y red, y ajustamos algunos de rendimiento:

```sh
sqlplus -s / as sysdba <<'EOF'
-- Servicio y listener (SCOPE=BOTH: se aplica ya y persiste en el SPFILE)
ALTER SYSTEM SET service_names='ABDCDB' SCOPE=BOTH;
ALTER SYSTEM SET local_listener='LISTENER_ABD' SCOPE=BOTH;
ALTER SYSTEM REGISTER;

-- Ajustes de capacidad
ALTER SYSTEM SET open_cursors=500 SCOPE=BOTH;
ALTER SYSTEM SET processes=400 SCOPE=SPFILE;   -- se aplicará en el próximo arranque

-- La PDB debe abrirse sola cuando arranque la CDB
ALTER PLUGGABLE DATABASE ABDPDB1 OPEN;
ALTER PLUGGABLE DATABASE ABDPDB1 SAVE STATE;

-- Copia legible del SPFILE
CREATE PFILE='/opt/oracle/scripts/init_ABDCDB.ora.bak' FROM SPFILE;
EXIT;
EOF
cat /opt/oracle/scripts/init_ABDCDB.ora.bak
```

- `local_listener='LISTENER_ABD'` es un **alias**: la instancia lo resuelve en `tnsnames.ora`, que configuramos a continuación.
- `processes=400` con `SCOPE=SPFILE` no cambia nada hasta el reinicio. Es una buena prueba de que el SPFILE persiste, porque lo comprobaremos tras reiniciar en el paso 16.

Salida:

```txt
oracle@oradeb:/home/juanka$ sqlplus -s / as sysdba <<'EOF'
-- Servicio y listener (SCOPE=BOTH: se aplica ya y persiste en el SPFILE)
ALTER SYSTEM SET service_names='ABDCDB' SCOPE=BOTH;
ALTER SYSTEM SET local_listener='LISTENER_ABD' SCOPE=BOTH;
ALTER SYSTEM REGISTER;

-- Ajustes de capacidad
ALTER SYSTEM SET open_cursors=500 SCOPE=BOTH;
ALTER SYSTEM SET processes=400 SCOPE=SPFILE;   -- se aplicará en el próximo arranque

-- La PDB debe abrirse sola cuando arranque la CDB
ALTER PLUGGABLE DATABASE ABDPDB1 OPEN;
ALTER PLUGGABLE DATABASE ABDPDB1 SAVE STATE;

-- Copia legible del SPFILE
CREATE PFILE='/opt/oracle/scripts/init_ABDCDB.ora.bak' FROM SPFILE;
EXIT;
EOF
cat /opt/oracle/scripts/init_ABDCDB.ora.bak

Sistema modificado.

ALTER SYSTEM SET local_listener='LISTENER_ABD' SCOPE=BOTH
*
ERROR en linea 1:
ORA-32017: fallo al actualizar SPFILE
ORA-00119: especificacion no valida para el parametro del sistema
LOCAL_LISTENER
ORA-00141: Las direcciones o alias especificados para el parametro
LOCAL_LISTENER no son validos.
ORA-00132: error de sintaxis o nombre de red no resuelto 'LISTENER_ABD'
Help: https://docs.oracle.com/error-help/db/ora-32017/



Sistema modificado.


Sistema modificado.

ALTER PLUGGABLE DATABASE ABDPDB1 OPEN
*
ERROR en linea 1:
ORA-65019: la base de datos de conexion ABDPDB1 ya esta abierta
Help: https://docs.oracle.com/error-help/db/ora-65019/



Base de datos de conexion modificada.


Archivo creado.

ABDCDB.__data_transfer_cache_size=0
ABDCDB.__datamemory_area_size=0
ABDCDB.__db_cache_size=1090519040
ABDCDB.__inmemory_ext_roarea=0
ABDCDB.__inmemory_ext_rwarea=0
ABDCDB.__java_pool_size=0
ABDCDB.__large_pool_size=16777216
ABDCDB.__oracle_base='/opt/oracle'#ORACLE_BASE set from environment
ABDCDB.__pga_aggregate_target=536870912
ABDCDB.__sga_target=1610612736
ABDCDB.__shared_io_pool_size=83886080
ABDCDB.__shared_pool_size=385875968
ABDCDB.__streams_pool_size=0
ABDCDB.__unified_pga_pool_size=0
ABDCDB._instance_recovery_bloom_filter_size=1048576
*.compatible='23.6.0'
*.control_files='/opt/oracle/oradata/ABDCDB/control01.ctl','/opt/oracle/fast_recovery_area/ABDCDB/control02.ctl'
*.db_block_size=8192
*.db_name='ABDCDB'
*.db_recovery_file_dest='/opt/oracle/fast_recovery_area'
*.db_recovery_file_dest_size=12288m
*.diagnostic_dest='/opt/oracle'
*.dispatchers='(PROTOCOL=TCP) (SERVICE=ABDCDBXDB)'
*.enable_pluggable_database=true
*.local_listener='LISTENER_ABDCDB'
*.nls_language='SPANISH'
*.nls_territory='SPAIN'
*.open_cursors=500
*.pga_aggregate_target=512m
*.processes=300
*.remote_login_passwordfile='EXCLUSIVE'
*.service_names='ABDCDB'
*.sga_target=1536m
*.undo_tablespace='UNDOTBS1'
```

## 15. Configuración de `tnsnames.ora` y `sqlnet.ora`

`dbca` ya habrá creado entradas propias en `tnsnames.ora`. **No lo sobrescribimos**: hacemos copia de seguridad y añadimos solo lo que falte.

```sh
cp $TNS_ADMIN/tnsnames.ora $TNS_ADMIN/tnsnames.ora.bak
cat $TNS_ADMIN/tnsnames.ora
grep -E '^(LISTENER_ABD|ABDCDB|ABDPDB1)\s*=' $TNS_ADMIN/tnsnames.ora
```

Salida:

```txt
oracle@oradeb:/home/juanka$ cp $TNS_ADMIN/tnsnames.ora $TNS_ADMIN/tnsnames.ora.bak
cat $TNS_ADMIN/tnsnames.ora
grep -E '^(LISTENER_ABD|ABDCDB|ABDPDB1)\s*=' $TNS_ADMIN/tnsnames.ora
# tnsnames.ora Network Configuration File: /opt/oracle/product/26ai/dbhome_1/network/admin/tnsnames.ora
# Generated by Oracle configuration tools.

ABDCDB =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)(HOST = oradeb.abd.local)(PORT = 1521))
    (CONNECT_DATA =
      (SERVER = DEDICATED)
      (SERVICE_NAME = ABDCDB)
    )
  )

LISTENER_ABDCDB =
  (ADDRESS = (PROTOCOL = TCP)(HOST = oradeb.abd.local)(PORT = 1521))


ABDCDB =
```

Añadimos al final los alias que no aparezcan en el `grep` anterior. Si uno ya existe, lo quitamos del bloque para no duplicarlo.

```sh
cat >> $TNS_ADMIN/tnsnames.ora <<'EOF'

LISTENER_ABD =
  (ADDRESS = (PROTOCOL = TCP)(HOST = oradeb.abd.local)(PORT = 1521))

ABDCDB =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)(HOST = oradeb.abd.local)(PORT = 1521))
    (CONNECT_DATA =
      (SERVER = DEDICATED)
      (SERVICE_NAME = ABDCDB)
    )
  )

ABDPDB1 =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)(HOST = oradeb.abd.local)(PORT = 1521))
    (CONNECT_DATA =
      (SERVER = DEDICATED)
      (SERVICE_NAME = abdpdb1)
    )
  )
EOF
```

Ahora el `sqlnet.ora`, con el método de resolución de nombres y detección de conexiones muertas:

```sh
[ -f $TNS_ADMIN/sqlnet.ora ] && cp $TNS_ADMIN/sqlnet.ora $TNS_ADMIN/sqlnet.ora.bak
cat > $TNS_ADMIN/sqlnet.ora <<'EOF'
NAMES.DIRECTORY_PATH = (TNSNAMES, EZCONNECT)
SQLNET.EXPIRE_TIME = 10
EOF
tnsping ABDCDB
tnsping ABDPDB1
tnsping LISTENER_ABD
```

Los tres `tnsping` deben terminar en `OK (… msec)`.

## 16. Arranque automático con systemd

**(admin)** Primero marcamos la instancia con `Y` en `/etc/oratab`:

```sh
sudo sed -i 's|^\(ABDCDB:[^:]*\):N$|\1:Y|' /etc/oratab
grep ^ABDCDB /etc/oratab
```

Creamos el fichero de entorno para systemd (que no lee `.profile`) y los dos scripts:

```sh
sudo tee /opt/oracle/scripts/oracle.env <<'EOF'
ORACLE_BASE=/opt/oracle
ORACLE_HOME=/opt/oracle/product/26ai/dbhome_1
ORACLE_SID=ABDCDB
LD_LIBRARY_PATH=/opt/oracle/product/26ai/dbhome_1/lib
CV_ASSUME_DISTID=OL8
EOF

sudo tee /opt/oracle/scripts/db_start.sh <<'EOF'
#!/bin/bash
$ORACLE_HOME/bin/sqlplus -s / as sysdba <<EOS
STARTUP
EXIT
EOS
EOF

sudo tee /opt/oracle/scripts/db_stop.sh <<'EOF'
#!/bin/bash
$ORACLE_HOME/bin/sqlplus -s / as sysdba <<EOS
SHUTDOWN IMMEDIATE
EXIT
EOS
EOF

sudo chown oracle:oinstall /opt/oracle/scripts/*
sudo chmod 750 /opt/oracle/scripts/*.sh
```

Unidad del Listener:

```sh
sudo tee /etc/systemd/system/oracle-listener.service <<'EOF'
[Unit]
Description=Oracle Net Listener LISTENER_ABD
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
User=oracle
Group=oinstall
EnvironmentFile=/opt/oracle/scripts/oracle.env
ExecStart=/opt/oracle/product/26ai/dbhome_1/bin/lsnrctl start LISTENER_ABD
ExecStop=/opt/oracle/product/26ai/dbhome_1/bin/lsnrctl stop LISTENER_ABD
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
EOF
```

Unidad de la base de datos, que depende del Listener:

```sh
sudo tee /etc/systemd/system/oracle-db.service <<'EOF'
[Unit]
Description=Oracle AI Database 26ai (ABDCDB)
After=oracle-listener.service
Requires=oracle-listener.service

[Service]
Type=oneshot
RemainAfterExit=yes
User=oracle
Group=oinstall
EnvironmentFile=/opt/oracle/scripts/oracle.env
ExecStart=/opt/oracle/scripts/db_start.sh
ExecStop=/opt/oracle/scripts/db_stop.sh
TimeoutStartSec=900
TimeoutStopSec=900
LimitNOFILE=65536
LimitNPROC=16384
LimitMEMLOCK=infinity

[Install]
WantedBy=multi-user.target
EOF
```

Ahora **paramos a mano** lo que arrancamos antes, para que systemd lo arranque de verdad y probemos las unidades:

```sh
sudo su - oracle -c "sqlplus -s / as sysdba <<'EOF'
SHUTDOWN IMMEDIATE
EXIT
EOF"
sudo su - oracle -c 'lsnrctl stop LISTENER_ABD'

sudo systemctl daemon-reload
sudo systemctl enable oracle-listener.service oracle-db.service
sudo systemctl start oracle-db.service
systemctl status oracle-listener.service oracle-db.service --no-pager
```

Ambas unidades deben quedar `active (exited)`. Si falla alguna: `journalctl -u oracle-db -n 50 --no-pager`.

## 17. Verificación final

### 17.1 Procesos, Listener y servicios

```sh
ps -ef | grep -E 'pmon|tnslsnr' | grep -v grep
sudo su - oracle -c 'lsnrctl services LISTENER_ABD'
```

El `ps` debe mostrar `ora_pmon_ABDCDB` y `tnslsnr`. En `lsnrctl services`, la instancia `ABDCDB` debe estar en `READY` con los servicios `ABDCDB` y `abdpdb1`. El registro dinámico puede tardar hasta un minuto en aparecer.

### 17.2 Estado de la CDB, la PDB y el SPFILE

```sh
sudo su - oracle -c "sqlplus -s / as sysdba <<'EOF'
SET LINESIZE 200
COL name FORMAT A20
COL value FORMAT A60
SELECT name, open_mode, cdb FROM v\$database;
SELECT instance_name, status, host_name FROM v\$instance;
SELECT name, open_mode FROM v\$pdbs;
SELECT name, value FROM v\$parameter WHERE name IN ('spfile','processes','open_cursors','local_listener','service_names');
EXIT;
EOF"
```

Esperamos `READ WRITE` en la CDB y en `ABDPDB1`. Sobre todo, `processes` debe valer `400`, lo que confirma que el SPFILE persistió el cambio tras el reinicio.

### 17.3 Conexión mediante alias TNS

Con la contraseña en la variable `ORA_PWD` (si abrimos una sesión nueva, repetimos el `read -s`):

```sh
sudo su - oracle
sqlplus system/"$ORA_PWD"@ABDCDB <<'EOF'
SELECT sys_context('USERENV','CON_NAME') AS contenedor FROM dual;
EXIT;
EOF
sqlplus system/"$ORA_PWD"@ABDPDB1 <<'EOF'
SELECT sys_context('USERENV','CON_NAME') AS contenedor FROM dual;
EXIT;
EOF
```

Deben devolver CDB$ROOT y ABDPDB1 respectivamente.

### 17.4 Prueba funcional en la PDB

Creamos un usuario temporal, una tabla y una consulta, y lo borramos después:

```sh
sqlplus system/"$ORA_PWD"@ABDPDB1 <<EOF
CREATE USER abd_test IDENTIFIED BY "$ORA_PWD" QUOTA UNLIMITED ON USERS;
GRANT CREATE SESSION, CREATE TABLE TO abd_test;
EXIT;
EOF
sqlplus abd_test/"$ORA_PWD"@ABDPDB1 <<'EOF'
CREATE TABLE prueba (id NUMBER, texto VARCHAR2(40));
INSERT INTO prueba VALUES (1, 'Oracle 26ai en Debian 13');
COMMIT;
SELECT * FROM prueba;
EXIT;
EOF
sqlplus system/"$ORA_PWD"@ABDPDB1 <<'EOF'
DROP USER abd_test CASCADE;
EXIT;
EOF
exit
```

### 17.5 Acceso remoto desde otra máquina

Desde un equipo cliente de la red local, que no sea el servidor:

```sh
nc -zv IP_DEL_SERVIDOR 1521
``` 

Debe responder `succeeded`. Si no, revisamos el cortafuegos (`sudo ufw allow 1521/tcp` si usáis ufw) y que el `HOST` del listener resuelva a la IP real.

### 17.6 Prueba de reinicio

```sh
sudo reboot
```

Tras el reinicio, repetimos 17.1 y 17.2. Si todo vuelve solo, el arranque automático está bien configurado.

## 18. Manejo de errores

|Síntoma|Causa probable|Solución|
|---|---|---|
|`rpm2cpio: command not found`|Falta el paquete|`sudo apt install rpm2cpio cpio rpm`|
|`error while loading shared libraries: libaio.so.1`|Falta el enlace `t64`|Repetir el enlace del paso 3 y `sudo ldconfig`|
|`libnsl.so.1: cannot open shared object file`|Falta el enlace de `libnsl`|Enlace `libnsl.so.2` → `libnsl.so.1` (paso 3)|
|`[INS-13001] Oracle Database is not supported on this operating system`|Debian no está certificado|Es un aviso esperado. Verificar `CV_ASSUME_DISTID=OL8`|
|`sqlplus: command not found`|Variables sin cargar|Entrar con `sudo su - oracle` (shell de login)|
|`DBT-06801` (tamaño del área de recuperación)|Aviso de dimensionamiento|Subir `-recoveryAreaSize` o ignorarlo|
|`dbca` se queja de `rpm` o de prerrequisitos|Comprobación de Red Hat|Mantener `-ignorePrereqFailure`. Como último recurso, un wrapper que devuelva 0 en el PATH del usuario `oracle`|
|`ORA-00845: MEMORY_TARGET not supported`|`/dev/shm` pequeño|Usamos `AUTO_SGA`. Revisar `df -h /dev/shm`|
|`ORA-27125` / `ORA-27300` / `ORA-27301`|Kernel o memoria compartida|Revisar `sysctl` (paso 6) y `memlock` (paso 7)|
|`ORA-12541: TNS:no listener`|Listener parado|`lsnrctl start LISTENER_ABD` o `systemctl start oracle-listener`|
|`ORA-12514: listener does not currently know of service`|Servicio sin registrar|`ALTER SYSTEM REGISTER;`, comprobar `local_listener` y esperar 60 s|
|`ORA-12154: could not resolve the connect identifier`|`tnsnames.ora` mal escrito o `TNS_ADMIN` incorrecto|Revisar sintaxis y `echo $TNS_ADMIN`|
|`ORA-12170` / `TNS-12545` desde un cliente remoto|IP, host o cortafuegos|Verificar `/etc/hosts`, el `HOST` del listener y el puerto 1521|
|`ORA-01017: invalid username/password`|Contraseña incorrecta o conectado a la CDB y no a la PDB|Comprobar el servicio usado (`ABDCDB` frente a `abdpdb1`)|
|`ORA-01034: ORACLE not available`|Instancia parada|`systemctl start oracle-db`|
|`oracle-db.service` en `failed`|Variables o permisos|`journalctl -u oracle-db -n 50` y revisar `oracle.env` y los scripts|
|Errores de enlazado (`undefined reference`) en alguna herramienta|Binario que necesita reenlazarse|Como `oracle`: `relink all` (con `gcc` y `make` instalados)|

