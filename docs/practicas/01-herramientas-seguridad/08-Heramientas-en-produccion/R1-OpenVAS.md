# Implantación de OpenVAS (Greenbone) como escáner de vulnerabilidades en un escenario con PostgreSQL y Nginx (R1)

## 1. Introducción

En esta documentación describimos cómo ponemos en producción **OpenVAS** (Greenbone Community Edition) en el escenario R1: un servidor con **Nginx** y **PostgreSQL** al que acceden un **cliente Linux** y un **cliente Windows**.

Un escáner de vulnerabilidades no espera a que alguien ataque: **revisa él mismo cada equipo**, como lo haría un atacante, y nos dice qué fallos tiene cada servicio, lo graves que son y cómo se corrigen. Es una herramienta **preventiva**. Así se complementa con las demás herramientas del grupo:

| Herramienta | Qué hace | Cuándo actúa |
| --- | --- | --- |
| **OpenVAS** (esta parte) | Busca fallos de seguridad en los equipos y servicios | **Antes** de que alguien los aproveche |
| IDS (Snort) | Vigila el tráfico de la red y avisa de ataques | **Durante** el ataque |
| Integridad (AIDE) | Avisa si cambian ficheros importantes | **Después**, si alguien ha modificado algo |
| Contraseñas | Comprueba si las contraseñas se pueden adivinar | Revisión periódica |

Como ya explicamos en nuestra guía individual de OpenVAS, la herramienta compara cada servicio con más de 100 000 pruebas (*NVT*) que se actualizan a diario. Aquí aplicamos lo aprendido al caso concreto del escenario:

1. Preparamos los usuarios necesarios.
2. Escaneamos un equipo y después la red completa, con usuario y sin él.
3. Programamos escaneos periódicos y configuramos los avisos por correo.
4. Analizamos los informes.
5. Corregimos (parcheamos) las vulnerabilidades reales y demostramos con un nuevo escaneo que han desaparecido.


## 2. El escenario y dónde se coloca el escáner

### 2.1. Descripción del escenario

Todas las máquinas están en la misma red conmutada `10.20.30.0/24`:

| Máquina | Dirección | Sistema | Función |
| --- | --- | --- | --- |
| Servidor | 10.20.30.10 | Debian 13 | Nginx (HTTP, puerto 80) y PostgreSQL 17 (puerto 5432) |
| Cliente Linux | 10.20.30.21 | Debian 13 | Equipo legítimo que usa la web y la base de datos |
| Cliente Windows | 10.20.30.22 | Windows 11 Enterprise | Equipo legítimo que usa la web |
| Sensor IDS | 10.20.30.40 | Debian 13 | Máquina del compañero del IDS (no la escaneamos con credenciales) |
| **Escáner OpenVAS** | **10.20.30.1** | Debian 13 + Docker | Equipo de administración que ejecuta Greenbone y hace de puerta de enlace |

Igual que en el resto del grupo, los servicios del servidor se publican **sin cifrar** (HTTP y PostgreSQL en claro), tal y como están en muchas redes internas. En el apartado 11.6 explicamos qué hacemos con ello.

### 2.2. Dónde colocamos el escáner

El escáner va en una **máquina aparte**, no dentro del servidor, por tres motivos:

- **Ve lo mismo que vería un atacante** de la red: los puertos abiertos, las versiones que anuncia cada servicio y la configuración que se puede consultar desde fuera.
- **No carga el servidor de producción** con sus bases de datos y procesos (Greenbone necesita unos 4 GB de RAM).
- **Un único escáner revisa toda la red**: el servidor y los dos clientes.

La **interfaz web** de Greenbone solo escucha en `127.0.0.1` del propio equipo (`https://127.0.0.1`). Nadie de la red puede entrar en ella; solo quien está sentado en el equipo de administración.

**Cómo sale el escaneo a la red.** El motor de escaneo vive dentro de un contenedor de Docker, con su propia red interna. Docker **traduce su dirección** (NAT) al salir, así que las máquinas del escenario ven llegar el escaneo desde `10.20.30.1`. Tiene dos consecuencias:

- La prueba de «¿está encendido el equipo?» por **ARP no funciona** (ARP solo vale dentro de la misma red física). Usamos **ICMP Ping**.
- El IDS del grupo verá todos nuestros escaneos como un ataque desde `10.20.30.1`. Lo comentamos en las dificultades (apartado 13).

### 2.3. Comprobar que el escáner llega a las máquinas

Antes de nada, comprobamos desde **dentro del contenedor** del escáner que llega a los servicios del servidor:

```bash
for puerto in 22 80 5432; do
  docker exec greenbone-community-edition-ospd-openvas-1 \
    bash -c "timeout 3 bash -c '</dev/tcp/10.20.30.10/$puerto' && echo '$puerto abierto' || echo '$puerto NO llega'"
done
```

- `for puerto in 22 80 5432` repite la orden para los tres puertos del servidor: SSH, web y base de datos.
- `docker exec <contenedor> <orden>` ejecuta una orden dentro de un contenedor que ya está en marcha. Usamos el de `ospd-openvas`, que es el que lanza las pruebas.
- `/dev/tcp/IP/puerto` es una función de `bash` que intenta abrir una conexión. Si se abre, el escáner llega a ese servicio.
- `timeout 3` corta la prueba a los 3 segundos si no hay respuesta.

Resultado: `22 abierto`, `80 abierto` y `5432 abierto`.

```sh
juanka@JuankaPortatil:/mnt/midisco/lab-sdi$ for puerto in 22 80 5432; do
  docker exec greenbone-community-edition-ospd-openvas-1 \
    bash -c "timeout 3 bash -c '</dev/tcp/10.20.30.10/$puerto' && echo '$puerto abierto' || echo '$puerto NO llega'"
done
22 abierto
80 abierto
5432 abierto
```

## 3. Usuarios necesarios

Seguimos el principio de **mínimo privilegio**: cada usuario tiene solo los permisos que necesita para su tarea.

| Dónde | Usuario | Para qué |
| --- | --- | --- |
| Greenbone | `admin` | Administrador de Greenbone. Lo usamos en la web para crear objetivos, tareas, alertas y programaciones. Ya existe |
| Greenbone | `automatizacion` | Usuario sin permisos de administración, para las órdenes desde la terminal (`gmp.sh`). Ya existe |
| Servidor y cliente Linux | `escaneo` | Usuario del sistema **sin contraseña** que solo puede entrar con una **clave SSH exclusiva**. El escáner lo usa para leer la lista de programas instalados. **No tiene `sudo`** |
| Cliente Windows | `escaneo` | Cuenta local de **administrador**: el escaneo de Windows por SMB necesita leer el registro y los parches instalados |
| Servidor | `www-data` | Usuario con el que funciona Nginx. Viene de serie; lo nombramos porque es el que sirve la web |
| Servidor (PostgreSQL) | `labuser` | Usuario **de la base de datos** (no del sistema) propietario de la base `tienda`. Lo usan los clientes |

**Por qué un usuario `escaneo` y no nuestra cuenta.** Si la clave del escáner se filtrara algún día, el daño queda limitado a un usuario que no puede hacer nada con privilegios y que se borra con una orden. Nunca le damos al escáner nuestra cuenta ni la de `root`.

### 3.1. Usuario `escaneo` en las máquinas Linux

**Paso 1. Clave exclusiva para este escenario.** En el equipo del escáner:

```bash
mkdir -p /mnt/midisco/greenbone/claves && chmod 700 /mnt/midisco/greenbone/claves
ssh-keygen -t ed25519 -f /mnt/midisco/greenbone/claves/r1_escaneo_ed25519 -C "openvas-r1" -N ""
```

- `mkdir -p` crea la carpeta de claves si no existe, y `chmod 700` hace que solo nuestro usuario pueda entrar en ella.
- `ssh-keygen -t ed25519` crea un par de claves con el algoritmo Ed25519, moderno y seguro.
- `-f` es el nombre del fichero. Se crean dos: la clave **privada** (`r1_escaneo_ed25519`, que nunca sale de este equipo) y la **pública** (`.pub`, que copiamos a las máquinas).
- `-C` es un comentario para reconocerla.
- `-N ""` la deja sin frase de paso, porque el escáner tiene que usarla solo, sin que nadie escriba nada. Por eso la limitamos a un usuario sin privilegios.

**Paso 2. Crear el usuario en el servidor y en el cliente Linux.** Desde el mismo equipo, entrando con nuestra cuenta habitual:

```bash
CLAVE="$(cat /mnt/midisco/greenbone/claves/r1_escaneo_ed25519.pub)"
for ip in 10.20.30.10 10.20.30.21; do
  ssh -t juanka@$ip "sudo adduser --disabled-password --comment '' escaneo && \
    sudo install -d -m 700 -o escaneo -g escaneo /home/escaneo/.ssh && \
    echo '$CLAVE' | sudo tee /home/escaneo/.ssh/authorized_keys >/dev/null && \
    sudo chown escaneo:escaneo /home/escaneo/.ssh/authorized_keys && \
    sudo chmod 600 /home/escaneo/.ssh/authorized_keys && echo 'escaneo listo en $ip'"
done
```

- `CLAVE=...` guarda en una variable el contenido de la clave pública, para no copiarla a mano.
- `ssh -t juanka@$ip "..."` ejecuta en cada máquina todo lo que va entre comillas. La `-t` permite que `sudo` nos pida la contraseña.
- `adduser --disabled-password --comment '' escaneo` crea el usuario **sin contraseña** (solo podrá entrar con la clave) y sin pedir datos personales.
- `install -d -m 700 -o escaneo -g escaneo` crea la carpeta `.ssh` del usuario con los permisos y el propietario correctos en un solo paso.
- `tee .../authorized_keys` escribe la clave pública en el fichero de **claves autorizadas**: quien tenga la privada podrá entrar como `escaneo`.
- `chmod 600` es obligatorio: SSH rechaza el fichero si otros usuarios pueden leerlo.
- Los `&&` encadenan las órdenes: cada una solo se ejecuta si la anterior ha ido bien.

**Paso 3. Comprobar a mano que la clave funciona.** Si esto falla, el escáner también fallará:

```bash
for ip in 10.20.30.10 10.20.30.21; do
  ssh -i /mnt/midisco/greenbone/claves/r1_escaneo_ed25519 escaneo@$ip 'echo "$(hostname): soy $(whoami)"; dpkg -l | grep -c "^ii"'
done
```

- `-i` indica qué clave privada usar.
- `dpkg -l` lista los paquetes instalados, que es justo lo que leerá el escáner. `grep -c "^ii"` los cuenta.

Resultado esperado: `servidor: soy escaneo` y `cliente-linux: soy escaneo`, cada uno con su número de paquetes.

```sh
juanka@JuankaPortatil:/mnt/midisco/lab-sdi$ for ip in 10.20.30.10 10.20.30.21; do
  ssh -i /mnt/midisco/greenbone/claves/r1_escaneo_ed25519 escaneo@$ip 'echo "$(hostname): soy $(whoami)"; dpkg -l | grep -c "^ii"'
done
servidor: soy escaneo
354
cliente-linux: soy escaneo
323
```

### 3.2. Usuario `escaneo` en el cliente Windows

Para escanear Windows con usuario, OpenVAS entra por **SMB** (el protocolo de compartir ficheros de Windows, puerto 445) y consulta el registro para saber qué versión y qué parches tiene. Windows necesita cuatro cosas.

Abrimos **PowerShell como administrador** en el cliente Windows: clic derecho en Inicio → *Terminal (Administrador)*.

**1. Crear la cuenta local `escaneo` y hacerla administradora:**

```powershell
$clave = Read-Host -AsSecureString "Contraseña para escaneo"
New-LocalUser -Name "escaneo" -Password $clave -PasswordNeverExpires -Description "Cuenta para OpenVAS"
Add-LocalGroupMember -SID "S-1-5-32-544" -Member "escaneo"
```

- `Read-Host -AsSecureString` pide la contraseña sin mostrarla en pantalla. Elegimos una **larga y única**; la escribiremos después en Greenbone.
- `New-LocalUser` crea la cuenta; `-PasswordNeverExpires` evita que caduque y deje de funcionar el escaneo programado.
- `Add-LocalGroupMember -SID "S-1-5-32-544"` la añade al grupo de **Administradores**. Usamos su identificador fijo (`S-1-5-32-544`) en vez del nombre porque el nombre cambia con el idioma de Windows («Administradores» o «Administrators»).

**2. Arrancar el servicio de Registro remoto:**

```powershell
Set-Service -Name RemoteRegistry -StartupType Automatic
Start-Service -Name RemoteRegistry
```

- El servicio **RemoteRegistry** permite leer el registro de Windows por la red. Viene parado de fábrica. `Automatic` hace que arranque solo con Windows, para que funcionen también los escaneos programados.

**3. Permitir «Compartir archivos e impresoras» en el cortafuegos:**

```powershell
Enable-NetFirewallRule -Group "@FirewallAPI.dll,-28502"
```

- Activa el grupo de reglas de *Compartir archivos e impresoras*, que abre SMB (445) a la red local. Igual que antes, usamos el identificador del grupo para que funcione con Windows en cualquier idioma.

**4. Permitir que una cuenta local administre el equipo a distancia:**

```powershell
reg add HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System /v LocalAccountTokenFilterPolicy /t REG_DWORD /d 1 /f
```

- Por seguridad, Windows quita los permisos de administrador a las cuentas **locales** cuando entran por la red (forma parte del *Control de cuentas de usuario*). Con este valor a `1`, la cuenta `escaneo` conserva sus permisos y el escáner puede leer el registro.
- **Esto debilita una protección de Windows.** En una empresa real se usa una **cuenta de dominio** del Directorio Activo y no hace falta este cambio. En el laboratorio lo dejamos mientras dure la vigilancia continua y lo quitamos al terminar la práctica (apartado 11).

**Comprobación desde el equipo del escáner:**

```bash
nmap -Pn -p 135,139,445 10.20.30.22
```

- `nmap -p` comprueba solo esos puertos; `-Pn` no espera respuesta al ping antes de mirar.
- El 445 debe salir `open`. Si sale `filtered`, el cortafuegos de Windows sigue cerrado: repetimos el paso 3.

```sh
juanka@JuankaPortatil:/mnt/midisco/lab-sdi$ nmap -Pn -p 135,139,445 10.20.30.22
Starting Nmap 7.95 ( https://nmap.org ) at 2026-11-03 19:26 CET
Nmap scan report for 10.20.30.22
Host is up (0.00079s latency).

PORT    STATE SERVICE
135/tcp open  msrpc
139/tcp open  netbios-ssn
445/tcp open  microsoft-ds

Nmap done: 1 IP address (1 host up) scanned in 0.04 seconds
```

## 4. Preparar Greenbone para el escenario

### 4.1. Comprobaciones previas

Antes de cualquier escaneo comprobamos tres cosas. Si el *feed* no está cargado, los escaneos salen vacíos **sin dar ningún error**.

```bash
sudo docker compose -f /root/greenbone-community-container/compose.yaml -p greenbone-community-edition ps
```

- Lista los contenedores de Greenbone. Los principales deben estar `Up` o `healthy`.

Después, en el navegador:

1. Entramos en `https://127.0.0.1` con el usuario `admin`.
2. En **Administration → Feed Status**, las filas NVT, SCAP, CERT y GVMD_DATA deben estar al día (*Current*).
3. En **Configuration → Scan Configs** debe existir `Full and fast`.

### 4.2. Lista de puertos del escenario

Revisar los casi 6 000 puertos de *All IANA assigned TCP* en cada máquina es lento. Como sabemos qué servicios hay en el escenario, creamos una **lista propia** con solo los puertos que nos interesan. Así cada escaneo tarda minutos en lugar de horas.

*Configuration → Port Lists → New Port List*:

- *Name*: `R1 servicios`
- *Port Ranges*: *Manual* → `T:22,80,135,139,443,445,3389,5432,5985`
- *Save*.

| Puerto | Servicio | Por qué lo incluimos |
| --- | --- | --- |
| 22 | SSH | Administración remota de los Linux |
| 80 | HTTP | La web de Nginx |
| 443 | HTTPS | Hoy está cerrado. Lo incluimos para detectar si alguien publica la web cifrada (o una web no autorizada) |
| 5432 | PostgreSQL | La base de datos |
| 135, 139, 445 | RPC, NetBIOS y SMB | Servicios de red de Windows; el 445 lo usa el escaneo autenticado |
| 3389 | Escritorio remoto | Muy atacado si está abierto en Windows |
| 5985 | WinRM | Administración remota de Windows |

- `T:` significa TCP; los puertos se separan con comas.
- No incluimos UDP: es muy lento de escanear y el escenario no tiene servicios UDP publicados.
- Aunque reduzcamos los puertos, OpenVAS sigue haciendo las pruebas generales del equipo (sistema operativo, ICMP, opciones TCP).

### 4.3. Credenciales para los escaneos con usuario

*Configuration → Credentials → New Credential*. Creamos dos:

**Credencial SSH para los Linux:**

- *Name*: `R1-ssh-escaneo`
- *Type*: `Username + SSH Key`
- *Username*: `escaneo`
- *Private Key*: subimos el fichero `/mnt/midisco/greenbone/claves/r1_escaneo_ed25519` (el que **no** acaba en `.pub`).
- *Save*.

**Credencial SMB para Windows:**

- *Name*: `R1-smb-escaneo`
- *Type*: `Username + Password`
- *Username*: `escaneo`
- *Password*: la que pusimos en el apartado 3.2.
- *Save*.

> Greenbone guarda las credenciales **cifradas** en su base de datos, y en la web nunca vuelve a mostrar la clave ni la contraseña.

### 4.4. Objetivos (*targets*)

*Configuration → Targets → New Target*. Creamos tres objetivos, uno por cada prueba:

| Nombre                     | *Hosts*                                 | *Exclude Hosts* | *Port List*    | *Alive Test* | Credenciales                                                  |
| -------------------------- | --------------------------------------- | --------------- | -------------- | ------------ | ------------------------------------------------------------- |
| `R1 red completa`          | `10.20.30.0/24`                         | `10.20.30.1`    | `R1 servicios` | `ICMP Ping`  | Ninguna                                                       |
| `R1 servidor`              | `10.20.30.10`                           | —               | `R1 servicios` | `ICMP Ping`  | Ninguna                                                       |
| `R1 escenario autenticado` | `10.20.30.10, 10.20.30.21, 10.20.30.22` | —               | `R1 servicios` | `ICMP Ping`  | *SSH*: `R1-ssh-escaneo`, puerto `22`. *SMB*: `R1-smb-escaneo` |

- **Hosts** acepta una IP, una lista separada por comas o una red completa (`/24` son las 254 direcciones de `10.20.30.1` a `10.20.30.254`).
- **Exclude Hosts** deja fuera nuestro propio equipo: no tiene sentido que el escáner se escanee a sí mismo por la red.
- **Alive Test = ICMP Ping**: antes de escanear un equipo, el escáner le hace un *ping* para saber si está encendido. El cliente Windows responde porque abrimos el ping en su cortafuegos al instalarlo.
- En el objetivo autenticado ponemos **las dos credenciales**: OpenVAS usa SSH con los Linux y SMB con Windows, según lo que encuentre en cada equipo.
- El sensor del IDS (`10.20.30.40`) aparecerá en el inventario de la red, pero no lo incluimos en el escaneo autenticado porque no tiene el usuario `escaneo`. Su revisión le corresponde al compañero del IDS.

## 5. Prueba 1: inventario de la red

**Para qué sirve:** saber **qué equipos hay** en la red antes de buscar fallos. Un equipo que no conocemos es un equipo que nadie está protegiendo.

*Scans → Tasks → New Task*:

- *Name*: `R1-00 Inventario de la red`
- *Scan Targets*: `R1 red completa`
- *Scan Config*: `Host Discovery`
- *Add results to Assets*: `Yes`
- *Save* y pulsamos ▶ (*Start*).

Tarda uno o dos minutos. Al terminar, en **Assets → Hosts** aparecen los equipos encontrados.

Lo comparamos con Nmap desde el equipo del escáner:

```bash
nmap -sn 10.20.30.0/24
```

- `-sn` solo comprueba qué equipos responden, sin mirar sus puertos.

**Cómo sabemos que ha funcionado:** OpenVAS encuentra `.10`, `.21`, `.22` y `.40`, los mismos que Nmap sin contar `.1`, que excluimos a propósito.


![[Pasted image 20261103193705.png]]

```sh
juanka@JuankaPortatil:/mnt/midisco/lab-sdi$ nmap -sn 10.20.30.0/24
Starting Nmap 7.95 ( https://nmap.org ) at 2026-11-03 19:35 CET
Nmap scan report for 10.20.30.1
Host is up (0.00032s latency).
Nmap scan report for 10.20.30.10
Host is up (0.00040s latency).
Nmap scan report for 10.20.30.21
Host is up (0.00067s latency).
Nmap done: 256 IP addresses (3 hosts up) scanned in 2.52 seconds
```

## 6. Prueba 2: escaneo de un equipo (el servidor, sin usuario)

**Para qué sirve:** ver el servidor **como lo ve un atacante** de la red: sin usuario ni contraseña, solo con lo que anuncian sus servicios.

*Scans → Tasks → New Task*:

- *Name*: `R1-01 Servidor sin credenciales`
- *Scan Targets*: `R1 servidor`
- *Scanner*: `OpenVAS Default`
- *Scan Config*: `Full and fast` (todas las pruebas que no son peligrosas para el servicio)
- *Apply Overrides*: `Yes`; *Min QoD*: `70` (el valor por defecto)
- *Alterable Task*: `Yes` (para poder cambiarla después de ejecutarla)
- *Save* y ▶.

Con nuestra lista de puertos tarda unos **10-20 minutos**. Podemos ver lo que hace el escáner en directo:

```bash
sudo docker compose -f /root/greenbone-community-container/compose.yaml -p greenbone-community-edition logs -f ospd-openvas
```

- `logs -f` muestra el registro del escáner y se queda esperando líneas nuevas. Salimos con `Ctrl+C` (no detiene nada).

Al terminar (*Done*), abrimos el informe: clic en la fecha de la columna *Last Report* → pestaña *Results*, ordenada por *Severity*.

**Qué cabe esperar en este servidor** (Debian 13 con Nginx 1.26.3, OpenSSH 10.0 y PostgreSQL 17):

| Hallazgo probable | Puerto | Gravedad orientativa |
| --- | --- | --- |
| *Weak MAC Algorithm(s) Supported (SSH)* | 22/tcp | Baja (2,6) |
| *TCP Timestamps Information Disclosure* | general/tcp | Baja (2,6) |
| *ICMP Timestamp Reply Information Disclosure* | general/icmp | Baja (2,1) |
| *SSH Terrapin Attack* y *OpenSSH CVE-2016-20012* | 22/tcp | Media |
| *Nginx Information Disclosure (CVE-2025-53859)* deducido por la versión que anuncia Nginx | 80/tcp | Baja |
| Detección de Nginx, PostgreSQL, OpenSSH y del sistema operativo | varios | Log (informativo) |


![[Pasted image 20261103195050.png]]

![[Pasted image 20261103195058.png]]

## 7. Prueba 3: escaneo de la red con usuario (todo el escenario)

**Para qué sirve:** desde fuera, el escáner tiene que **adivinar** las versiones. Con el usuario `escaneo` **entra** en cada máquina, lee la lista exacta de programas instalados y la compara con los avisos de seguridad de Debian y de Microsoft. Encuentra más y se equivoca menos.

*Scans → Tasks → New Task*:

- *Name*: `R1-02 Escenario autenticado`
- *Scan Targets*: `R1 escenario autenticado`
- *Scan Config*: `Full and fast`
- *Add results to Assets*: `Yes`; *Apply Overrides*: `Yes`; *Alterable Task*: `Yes`
- *Order for target hosts*: `Sequential`; *Maximum concurrently scanned hosts*: `3`
- *Auto Delete Reports*: conservar los **10** últimos (para no llenar el disco con los escaneos programados)
- *Save* y ▶.

**Cómo sabemos que el inicio de sesión ha funcionado.** En el informe buscamos (escribiendo en el filtro o en la pestaña *Results*):

- En los Linux: *SSH Login Successful For Authenticated Checks* y *Authenticated Scan / LSC Info Consolidation (Linux/Unix SSH Login)*.
- En Windows: *Authenticated Scan / LSC Info Consolidation (Windows SMB Login)* y resultados que muestran la versión exacta de Windows y sus parches.
- La pestaña ***Error Messages*** del informe no debe tener errores de inicio de sesión. Si los tiene:
  - En Linux, repetimos la comprobación manual del apartado 3.1.
  - En Windows, revisamos los cuatro pasos del apartado 3.2.

Para leer el informe **por equipos**, usamos la pestaña ***Hosts***: muestra la gravedad máxima de cada máquina y nos dice cuál atender primero.

**Qué cabe esperar además de lo de la prueba 2:**

| Equipo | Hallazgo probable | Comentario |
| --- | --- | --- |
| Servidor y cliente Linux | *Sudo Local Privilege Escalation* (CVE-2025-32462 y CVE-2025-32463), gravedad alta | Probable **falso positivo**: se comprueba en el apartado 10.3 |
| Servidor y cliente Linux | Avisos de procesador Intel (*INTEL-SA-...*) con QoD muy bajo | Dependen del procesador físico, no de la máquina virtual |
| Servidor y cliente Linux | Paquetes con actualizaciones de seguridad pendientes | Solo si hay actualizaciones sin instalar |
| Cliente Windows | Actualizaciones de Windows que faltan, configuración de SMB | Depende de los parches que tenga instalados |



![[Pasted image 20261103195221.png]]

![[Pasted image 20261103195230.png]]
## 8. Alertas por correo

### 8.1. El correo en Greenbone (ya configurado)

Greenbone no trae servidor de correo: cuando una alerta tiene que mandar un email, el contenedor `gvmd` llama a `msmtp`, que lo entrega a **Gmail** con una **contraseña de aplicación**. Los datos están en un fichero aparte (`correo.env`, con permisos `600`), que se carga encima del fichero oficial mediante `correo.override.yaml`. El paso a paso está en nuestra guía individual (apartado 6.6.4).

Comprobamos que sigue cargado, **sin mostrar la contraseña**:

```bash
docker exec greenbone-community-edition-gvmd-1 env | grep ^MTA_ | grep -v PASSWORD
```

- `env` muestra las variables del contenedor; `grep ^MTA_` se queda con las del correo, y `grep -v PASSWORD` quita la línea de la contraseña.

Deben aparecer `MTA_HOST=smtp.gmail.com`, `MTA_PORT=587`, `MTA_TLS=on`, `MTA_STARTTLS=on`, `MTA_AUTH=on`, `MTA_USER`, `MTA_FROM` y `MTA_LOGFILE`.

Mandamos un correo de prueba con el mismo usuario que usan las alertas:

```bash
docker exec -u gvmd greenbone-community-edition-gvmd-1 bash -c \
  'printf "Subject: Prueba R1 OpenVAS\n\nCorreo de prueba del escenario R1.\n" | sendmail -f "$MTA_FROM" juanka.fdez05@gmail.com; echo "salida: $?"'
docker exec greenbone-community-edition-gvmd-1 tail -1 /var/log/gvm/msmtp.log
```

- `-u gvmd` ejecuta la orden con el usuario interno `gvmd`, el mismo que envía las alertas de verdad.
- `printf` escribe un correo mínimo: el asunto, una línea en blanco y el texto. `sendmail` lo envía a través de `msmtp`.
- `salida: 0` significa que no hubo error. La última línea del registro debe terminar en `smtpstatus=250` (Gmail lo ha aceptado).

### 8.2. Alertas del escenario

*Configuration → Alerts → New Alert*. Creamos tres alertas, cada una para un caso distinto:

| Nombre       | *Event*                            | *Condition*                            | *Method* y contenido                                                                            |
| ------------ | ---------------------------------- | -------------------------------------- | ----------------------------------------------------------------------------------------------- |
| `R1-informe` | *Task run status changed* → `Done` | `Always`                               | *Email*, *Attach report*, formato **PDF**                                                       |
| `R1-grave`   | *Task run status changed* → `Done` | *Severity at least* `7.0`              | *Email*, *Include report*, formato **TXT**                                                      |
| `R1-empeora` | *Task run status changed* → `Done` | *Severity Level changed* → `increased` | *Email*, *Attach report*, **PDF**, *Delta Report*: *Previous completed report of the same task* |

En las tres rellenamos:

- *To Address*: `juanka.fdez05@gmail.com` (se pueden poner varios destinatarios separados por comas, por ejemplo todo el grupo).
- *From Address*: la misma cuenta que envía (`MTA_FROM`). Si no coincide, Gmail lo cambia o lo rechaza.
- *Subject*: `[OpenVAS R1] $n: $e` (`$n` se cambia por el nombre de la tarea y `$e` por el evento).
- En *Report Result Filter*, el filtro por defecto (QoD mínimo 70 %), para no mandar resultados poco fiables.

Qué aporta cada una:

- **`R1-informe`**: cada vez que termina un escaneo nos llega el informe completo en PDF. Es el registro de lo que se ha hecho.
- **`R1-grave`**: solo escribe si aparece algo **alto o crítico** (gravedad 7 o más) y lo pone en el propio correo para leerlo en el móvil. Es la que hay que atender enseguida.
- **`R1-empeora`**: compara con el escaneo anterior y avisa si la red ha **empeorado**: un servicio nuevo, un fallo nuevo, un equipo que antes no estaba.

**Probar cada alerta sin escanear:** en la lista *Configuration → Alerts*, el icono ▶ (*Test Alert*) la dispara con datos de ejemplo. Debe llegar el correo.

**Asociarlas a las tareas:** editamos `R1-01` y `R1-02` y en el campo *Alerts* elegimos las tres. Una alerta no hace nada hasta que está en una tarea.

**Cómo sabemos que ha funcionado:** al terminar un escaneo llega el correo `[OpenVAS R1] R1-02 Escenario autenticado: Task status changed to 'Done'` con el PDF adjunto, y el registro de `msmtp` muestra `smtpstatus=250`. Si no llega, buscamos en el registro de `gvmd`:

```bash
sudo docker compose -f /root/greenbone-community-container/compose.yaml -p greenbone-community-edition logs gvmd | grep -i -E "alert|mail"
```



![[Pasted image 20261103201436.png]]

![[Pasted image 20261103201449.png]]
## 9. Vigilancia continua: escaneos programados

Un escaneo suelto es una foto. Cada día se publican vulnerabilidades nuevas para programas que ayer eran seguros, así que el escaneo tiene que **repetirse solo**.

*Configuration → Schedules → New Schedule*:

| Nombre           | *First Run*         | *Timezone*      | *Recurrence*           | Para qué                                                     |
| ---------------- | ------------------- | --------------- | ---------------------- | ------------------------------------------------------------ |
| `R1-diario-0300` | Mañana a las 03:00  | `Europe/Madrid` | *Daily* (cada 1 día)   | La vigilancia real: de noche, cuando nadie usa los servicios |
| `R1-cada-hora`   | Dentro de 5 minutos | `Europe/Madrid` | *Hourly* (cada 1 hora) | Solo para la demostración en el vídeo                        |

Editamos `R1-02 Escenario autenticado` y en *Schedule* elegimos `R1-diario-0300` (o `R1-cada-hora` para la demostración). En *Scans → Tasks* aparece un **icono de reloj** con la fecha de la próxima ejecución.

- Con las alertas del apartado 8, cada mañana tenemos en el correo el informe y, si algo ha empeorado, un aviso aparte.
- La columna ***Trend*** de la lista de tareas indica si la gravedad sube, baja o se mantiene respecto a la ejecución anterior.
- *Auto Delete Reports* (apartado 7) borra los informes antiguos y conserva los 10 últimos.
- **Importante:** Greenbone tiene que estar encendido a esa hora. Los contenedores arrancan solos con el equipo (servicio `greenbone-compose`), pero si el equipo está apagado o suspendido, el escaneo no se hace. En producción el escáner es un servidor siempre encendido.

![[Pasted image 20261103201740.png]]

## 10. Análisis de los informes

Un informe no es una lista de problemas: es una lista de **candidatos** a problema que tenemos que **comprobar** y **ordenar**. Seguimos siempre el mismo método.

### 10.1. Cómo leemos cada resultado

Al hacer clic en una vulnerabilidad del informe aparecen estos apartados:

| Apartado | Qué nos dice |
| --- | --- |
| *Summary* | Qué es, en una frase |
| *Detection Result* | La prueba concreta que encontró en nuestra máquina |
| *Detection Method* y **QoD** | Cómo lo comprobó y con qué fiabilidad (de 0 a 100 %). **QoD 30 % significa que solo ha mirado el número de versión**, no ha comprobado el fallo |
| *Impact* | Qué podría hacer un atacante |
| *Solution* | Qué hacer: *VendorFix* (hay actualización oficial), *Mitigation* (cambiar la configuración), *Workaround* o *WillNotFix* |

### 10.2. Método de triaje

1. **Ordenar por gravedad** y revisar aparte lo que tenga QoD bajo.
2. **Agrupar por equipo y por servicio**: varios resultados del mismo programa suelen arreglarse con una sola acción.
3. **Comprobar a mano** cada hallazgo importante, sin fiarnos solo del escáner.
4. **Clasificar** cada uno:
   - **Real:** se corrige (apartado 11).
   - **Falso positivo:** se documenta y se marca con un *override* (cambio de gravedad), con una nota que explique la comprobación.
   - **Riesgo aceptado:** se anota por qué no se corrige.
5. **Priorizar**: primero lo real y fácil de corregir sin romper el servicio; después lo grave que exige más trabajo; al final, lo que no depende de nosotros.

### 10.3. Cómo comprobamos los hallazgos del servidor

**Algoritmos MAC débiles en SSH.** Preguntamos al servidor qué algoritmos admite, igual que hace OpenVAS:

```bash
nmap -Pn -p 22 --script ssh2-enum-algos 10.20.30.10 | grep -A12 mac_algorithms
```

- `--script ssh2-enum-algos` lista los algoritmos que ofrece el servidor SSH.
- `grep -A12 mac_algorithms` muestra solo la parte de los MAC (las 12 líneas siguientes).
- Si aparecen `umac-64-etm@openssh.com` y `umac-64@openssh.com`, el hallazgo es **real**.

**Marcas de tiempo TCP:**

```bash
ssh juanka@10.20.30.10 '/usr/sbin/sysctl net.ipv4.tcp_timestamps'
```

- Ponemos la ruta completa porque en Debian `sysctl` está en `/usr/sbin`, que no está en el `PATH` de un usuario normal (sin ella sale `sysctl: command not found`). También vale `cat /proc/sys/net/ipv4/tcp_timestamps`.
- `= 1` significa que están activadas: hallazgo **real**.

**Sudo y Nginx con QoD 30 %.** El escáner dice que `sudo` 1.9.16p2 y `nginx` 1.26.3 son vulnerables porque la corrección oficial llegó en versiones más nuevas. Pero Debian suele **copiar la corrección a la versión que ya tiene** sin cambiar el número (lo llama *backport*). Lo comprobamos en el registro de cambios del paquete:

```bash
ssh juanka@10.20.30.10 'zcat /usr/share/doc/sudo/changelog.Debian.gz | grep -n -E "CVE-2025-3246[23]"'
ssh juanka@10.20.30.10 'zcat /usr/share/doc/nginx/changelog.Debian.gz | grep -n "CVE-2025-53859"'
```

- `zcat` lee un fichero comprimido sin descomprimirlo, y `grep -n` busca el identificador del fallo y muestra en qué línea está.
- Si aparece el CVE (por ejemplo, `backport upstream patch for CVE-2025-32463`), el fallo **ya está corregido** en el paquete instalado: es un **falso positivo**.

```sh
juanka@JuankaPortatil:/mnt/midisco$ nmap -Pn -p 22 --script ssh2-enum-algos 10.20.30.10 | grep -A12 mac_algorithms
|   mac_algorithms: (10)
|       umac-64-etm@openssh.com
|       umac-128-etm@openssh.com
|       hmac-sha2-256-etm@openssh.com
|       hmac-sha2-512-etm@openssh.com
|       hmac-sha1-etm@openssh.com
|       umac-64@openssh.com
|       umac-128@openssh.com
|       hmac-sha2-256
|       hmac-sha2-512
|       hmac-sha1
|   compression_algorithms: (2)
|       none
juanka@JuankaPortatil:/mnt/midisco$ ssh juanka@10.20.30.10 '/usr/sbin/sysctl net.ipv4.tcp_timestamps'
net.ipv4.tcp_timestamps = 1
juanka@JuankaPortatil:/mnt/midisco$ ssh juanka@10.20.30.10 'zcat /usr/share/doc/sudo/changelog.Debian.gz | grep -n -E "CVE-2025-3246[23]"'
ssh juanka@10.20.30.10 'zcat /usr/share/doc/nginx/changelog.Debian.gz | grep -n "CVE-2025-53859"'
22:  * backport upstream patch for CVE-2025-32463
23:  * add upstream patch for CVE-2025-32462
134:  * d/p/CVE-2025-53859.patch add, fix potential information leak
135:    in ngx_mail_smtp_module (CVE-2025-53859).
```


### 10.5. Exportar los informes

En *Scans → Reports*, clic en el informe → icono de **descarga** → formato **PDF**. Antes de descargar escribimos en el filtro `apply_overrides=1 min_qod=0 rows=-1 levels=chmlgf`, para que el PDF lleve **todos** los resultados, incluidos los de QoD bajo y los marcados como falsos positivos. Los guardamos en `/mnt/midisco/greenbone/informes/` con nombres como `R1-01-servidor-antes.pdf`.

> Los informes contienen información sensible: direcciones, versiones y debilidades. No se publican tal cual fuera del grupo.

## 11. Parcheo de las vulnerabilidades

Corregimos lo que es **real y sencillo** de arreglar sin cambiar el funcionamiento del escenario. Después repetimos el escaneo y demostramos con un informe comparativo (*delta*) que los fallos han desaparecido.

### 11.1. Antes de tocar nada: instantánea del servidor

```bash
virsh -c qemu:///system snapshot-create-as servidor antes-de-parchear-r1 "Servidor antes del parcheo de OpenVAS"
virsh -c qemu:///system snapshot-list servidor
```

- `snapshot-create-as` guarda el estado completo de la máquina virtual (disco y memoria) con ese nombre.
- `snapshot-list` comprueba que se ha creado.
- Si algo se rompe, volvemos atrás con `virsh -c qemu:///system snapshot-revert servidor antes-de-parchear-r1`.

### 11.2. Corrección 1: algoritmos MAC débiles en SSH

**Qué dice el informe:** *Weak MAC Algorithm(s) Supported (SSH)*, *Solution*: *Disable the reported weak MAC algorithm(s)*.

**Qué significa:** cada paquete que viaja por SSH lleva un «sello» (MAC) que demuestra que nadie lo ha modificado por el camino. Un sello de 64 bits es corto y, en teoría, más fácil de falsificar.

Entramos en el servidor (`ssh juanka@10.20.30.10`) y ejecutamos:

```bash
sudo sshd -T | grep -E "^macs"
sudo cp -a /etc/ssh /etc/ssh.bak-openvas
echo "MACs -umac-64-etm@openssh.com,umac-64@openssh.com" | sudo tee /etc/ssh/sshd_config.d/10-endurecido.conf
sudo sshd -t && sudo systemctl reload ssh && echo "SSH recargado"
sudo sshd -T | grep -E "^macs"
```

- `sshd -T` muestra la configuración **real** de SSH. La primera vez vemos los dos `umac-64`; la última, ya no.
- `cp -a` hace una copia de seguridad de toda la configuración de SSH, conservando los permisos.
- Escribimos la corrección en un **fichero nuevo** dentro de `sshd_config.d/`, en lugar de editar el fichero principal: el cambio queda aislado y se deshace borrando ese fichero.
- `MACs -lista`: el signo `-` significa «la lista de fábrica **menos** estos». Quitamos solo lo que señala el informe.
- `sshd -t` comprueba que la configuración es correcta **sin aplicarla**. Gracias al `&&`, si hubiera un error no se recargaría SSH y no perderíamos el acceso.

**Comprobación:** dejamos abierta la sesión actual y, desde otra terminal del equipo del escáner, comprobamos que seguimos entrando con `ssh juanka@10.20.30.10 'echo sigo entrando'`.

```sh
juanka@JuankaPortatil:/mnt/midisco$ ssh juanka@10.20.30.10 'echo sigo entrando'
sigo entrando
```
### 11.3. Corrección 2: marcas de tiempo TCP

**Qué dice el informe:** *TCP Timestamps Information Disclosure*, *Solution*: desactivar `net.ipv4.tcp_timestamps`.

**Qué significa:** con las marcas de tiempo de dos paquetes se puede calcular cuánto tiempo lleva encendida la máquina. A un atacante le sirve para saber si se ha reiniciado tras actualizar el núcleo.

En el servidor:

```bash
echo "net.ipv4.tcp_timestamps = 0" | sudo tee /etc/sysctl.d/99-endurecimiento.conf
sudo sysctl --system >/dev/null
/usr/sbin/sysctl net.ipv4.tcp_timestamps
```

- El informe propone `/etc/sysctl.conf`, pero en Debian 13 los ajustes del núcleo van en ficheros sueltos dentro de `/etc/sysctl.d/`, que se aplican en cada arranque.
- `sysctl --system` aplica todos esos ficheros sin reiniciar.
- La última orden debe mostrar `= 0`.

```sh
juanka@servidor:~$ echo "net.ipv4.tcp_timestamps = 0" | sudo tee /etc/sysctl.d/99-endurecimiento.conf
sudo sysctl --system >/dev/null
/usr/sbin/sysctl net.ipv4.tcp_timestamps
net.ipv4.tcp_timestamps = 0
net.ipv4.tcp_timestamps = 0
```

### 11.4. Corrección 3: ocultar la versión de Nginx

**Qué dice el informe:** Nginx anuncia su versión exacta en cada respuesta, y el escáner la usa para deducir vulnerabilidades. Un atacante haría lo mismo para buscar *exploits* de esa versión.

En el servidor:

```bash
curl -sI http://10.20.30.10/ | grep -i ^server
sudo tee /etc/nginx/conf.d/seguridad.conf >/dev/null <<'EOF'
server_tokens off;
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
EOF
sudo nginx -t && sudo systemctl reload nginx
curl -sI http://10.20.30.10/ | grep -i -E "^(server|x-frame|x-content|referrer)"
```

- `curl -sI` pide solo las **cabeceras** de la respuesta. Antes del cambio, `Server:` dice `nginx/1.26.3`; después, solo `nginx`.
- `server_tokens off` oculta la versión en las cabeceras y en las páginas de error.
- Aprovechamos para añadir tres **cabeceras de seguridad** que no cambian cómo se ve la web:
  - `X-Frame-Options` impide que otra web meta la nuestra dentro de un marco para engañar al usuario (*clickjacking*).
  - `X-Content-Type-Options: nosniff` evita que el navegador intente adivinar el tipo de un fichero.
  - `Referrer-Policy` limita la información que se envía a otras webs al seguir un enlace.
  - `always` hace que se envíen también en las respuestas de error.
- Los ficheros de `conf.d/` los carga Nginx automáticamente. `nginx -t` comprueba la configuración y, solo si es correcta, `reload` la aplica sin cortar las conexiones.

Comprobamos que los clientes siguen funcionando con normalidad:

```bash
ssh juanka@10.20.30.21 'curl -s http://10.20.30.10/ | head -1; PGPASSWORD=labpass psql -h 10.20.30.10 -U labuser -d tienda -c "SELECT count(*) FROM clientes;"'
```

- Desde el cliente Linux pedimos la web y consultamos la base de datos. Las dos deben responder igual que antes del parcheo. Hacemos lo mismo en Windows con `curl.exe -s http://10.20.30.10/`.

```sh
juanka@JuankaPortatil:/mnt/midisco$ ssh juanka@10.20.30.21 'curl -s http://10.20.30.10/ | head -1; PGPASSWORD=labpass psql -h 10.20.30.10 -U labuser -d tienda -c "SELECT count(*) FROM clientes;"'
<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Tienda LAB</title></head>
bash: line 1: psql: command not found
```

### 11.5. Corrección 4: marcar los falsos positivos (*overrides*)

Los avisos de `sudo` y `nginx` que comprobamos en el apartado 10.3 no se arreglan, porque ya están corregidos. Se **marcan** para que no cuenten en la gravedad y para que quien lea el informe sepa que alguien lo revisó. El resultado no se borra: sigue en el informe con su etiqueta.

En el informe, clic en el resultado → icono ***Add Override***:

- *New Severity*: `False Positive`
- *Hosts*: la IP del equipo comprobado (por ejemplo `10.20.30.10`), para que no oculte el resultado en otras máquinas.
- *Text*: la explicación. Por ejemplo: «Falso positivo: Debian 13 corrigió CVE-2025-32463 en sudo 1.9.16p2 (*backport*). Comprobado en /usr/share/doc/sudo/changelog.Debian.gz. El escáner solo compara la versión (QoD 30 %).»
- *Save*.

Repetimos con cada falso positivo. Como las tareas tienen *Apply Overrides* = `Yes`, los siguientes informes ya los muestran como *False Positive*.

**Cliente Windows.** Si el informe muestra **actualizaciones de Windows pendientes**, la corrección es instalarlas: *Configuración → Windows Update → Buscar actualizaciones*, reiniciar y volver a escanear. Si no hay actualizaciones pendientes, documentamos los hallazgos de configuración que aparezcan siguiendo el mismo método del apartado 10.

### 11.6. Riesgos que aceptamos y por qué

| Hallazgo | Por qué no lo corregimos | Cómo se corregiría en producción |
| --- | --- | --- |
| **HTTP y PostgreSQL sin cifrar** | Es el diseño del escenario: red interna, y el IDS del grupo necesita ver el contenido del tráfico para detectar ataques | Web por **HTTPS** con un certificado (en `/etc/nginx/sites-available/default`, `listen 443 ssl` con `ssl_certificate` y `ssl_certificate_key`, y redirección del 80 al 443). PostgreSQL con `ssl = on` en `postgresql.conf` y líneas `hostssl` en `pg_hba.conf` para obligar a cifrar |
| *Terrapin* (SSH) | OpenSSH 10.0 ya incluye la defensa (*strict KEX*); el aviso se basa en los algoritmos que se ofrecen | Mantener OpenSSH actualizado |
| *OpenSSH CVE-2016-20012* | No existe corrección: OpenSSH no lo considera un fallo. Solo revela si una clave pública es válida para un usuario | Limitar quién puede llegar al puerto 22 con un cortafuegos |
| *ICMP Timestamp Reply* | Gravedad muy baja; el escenario no tiene cortafuegos en las máquinas | Bloquear con el cortafuegos los mensajes ICMP *timestamp* (tipos 13 y 14) |
| Avisos de procesador Intel (QoD 1 %) | Dependen del procesador físico y de su BIOS, no de la máquina virtual | Actualizar la BIOS del equipo físico |
| `LocalAccountTokenFilterPolicy=1` en Windows | Lo necesita el escaneo con cuenta local mientras dura la vigilancia continua | Usar una cuenta de dominio. Al terminar la práctica lo quitamos con `reg delete HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System /v LocalAccountTokenFilterPolicy /f` |

### 11.7. Comprobación final: nuevo escaneo e informe *delta*

Volvemos a lanzar **la misma tarea** `R1-01 Servidor sin credenciales` (▶). Es importante que sea la misma, para que los dos informes se puedan comparar.

Al terminar, en la web:

1. *Scans → Reports*: filtramos por la tarea `R1-01`.
2. En el informe **anterior** al parche pulsamos el icono ***Delta*** (lo marca como referencia).
3. Pulsamos en el informe **nuevo**. Greenbone muestra cada resultado con una etiqueta:
   - ***Gone***: ha desaparecido, es decir, **está corregido**.
   - ***Same***: sigue igual.
   - ***New***: ha aparecido.
   - ***Changed***: ha cambiado.

**Qué debe salir:**

- *Weak MAC Algorithm(s) Supported (SSH)*: **Gone** (corrección 1).
- *TCP Timestamps Information Disclosure*: **Gone** (corrección 2).
- El aviso de Nginx que se deducía por la versión debería desaparecer o cambiar, porque Nginx ya no la anuncia (corrección 3).
- Los falsos positivos siguen apareciendo, pero con gravedad *False Positive* (corrección 4).

Descargamos los dos informes en PDF (apartado 10.5): `R1-01-servidor-antes.pdf` y `R1-01-servidor-despues.pdf`. La siguiente ejecución programada de `R1-02` confirmará lo mismo con el escaneo autenticado.

![[Pasted image 20261103203855.png]]

![[Pasted image 20261103203906.png]]

## 12. Mantenimiento en producción

Para que el escáner siga siendo útil con el tiempo:

- **Feed al día:** las pruebas se actualizan a diario. Una vez por semana actualizamos las imágenes de datos (`docker compose ... pull` y `up -d`, guía individual 3.10) y comprobamos *Administration → Feed Status*.
- **Escaneos programados y correo:** revisamos cada mañana los correos de `R1-grave` y `R1-empeora`. Un aviso que nadie lee no sirve de nada.
- **Después de cada cambio importante** (un servicio nuevo, una actualización grande, un equipo nuevo) lanzamos `R1-02` a mano, sin esperar a la noche.
- **Credenciales del escáner:** la clave `r1_escaneo_ed25519` y la contraseña de `escaneo` en Windows se cambian periódicamente. Si se sospecha una filtración, se borra el usuario `escaneo` de cada máquina.
- **Espacio en disco:** *Auto Delete Reports* conserva los 10 últimos informes; los importantes se exportan en PDF.
- **Copias de seguridad** de los volúmenes de Greenbone (base de datos con informes, *overrides* y configuración), como explicamos en la guía individual.
- **Coordinación con el IDS:** los escaneos se lanzan siempre desde `10.20.30.1` y a la misma hora, para que el compañero del IDS pueda reconocerlos.

## 13. Dificultades encontradas en la implantación

| Dificultad | Cómo la resolvimos |
| --- | --- |
| **El escáner está dentro de Docker**: las máquinas ven el escaneo desde `10.20.30.1` y la prueba de equipo encendido por ARP no funciona | Usar *ICMP Ping* como *Alive Test* y comprobar la conectividad desde el contenedor antes de escanear (apartado 2.3) |
| **Escanear Windows con usuario es mucho más complicado que Linux**: hace falta una cuenta de administrador, el Registro remoto, abrir SMB en el cortafuegos y rebajar una protección de Windows | Cuenta `escaneo` dedicada y documentar el riesgo. En una empresa se usaría una cuenta de dominio |
| **Falsos positivos**: OpenVAS deduce fallos por el número de versión y no sabe que Debian ya los ha corregido | Escaneo con usuario, comprobación en el *changelog* del paquete y *override* documentado |
| **El escaneo completo es lento** y genera mucho tráfico | Lista de puertos propia del escenario (`R1 servicios`) y escaneos programados de noche |
| **Choque con el IDS**: cada escaneo dispara cientos de alertas en el sensor del grupo | Lanzar los escaneos desde una IP y a una hora conocidas, para que el IDS las identifique o las silencie para esa IP |
| **Cifrar o no cifrar**: OpenVAS recomienda cifrar HTTP y PostgreSQL, pero entonces el IDS no podría leer el contenido del tráfico | Decisión de grupo: se mantiene sin cifrar como riesgo aceptado en la red interna, y se documenta cómo cifrar en producción |
| **No detecta contraseñas débiles propias**: OpenVAS solo prueba contraseñas por defecto (`postgres`/`postgres`), no una contraseña débil inventada como la de `labuser` | Esa revisión le corresponde a la herramienta de fortaleza de contraseñas del grupo |
| **La vigilancia depende de que el equipo esté encendido**: en un portátil apagado, el escaneo programado no se hace | En producción, el escáner va en un servidor siempre encendido |

## 14. Conclusiones: utilidad de un escáner de vulnerabilidades

La implantación de OpenVAS en el escenario demuestra la utilidad de **revisar los equipos antes de que lo haga un atacante**. En pocos minutos nos dice qué servicios hay abiertos, qué versiones anuncian, qué configuración débil tienen y cómo se corrige cada cosa. Con el informe comparativo, además, **demuestra** que lo hemos corregido.

En el escenario, OpenVAS es la **primera capa**, la preventiva. Encuentra los fallos para que los cerremos antes de que el IDS tenga que detectar un ataque contra ellos, o antes de que la herramienta de integridad tenga que avisar de que alguien ha modificado un fichero.

Lo vemos necesario en estos contextos:

- **Antes de poner un servidor en producción**, como el de Nginx y PostgreSQL de este escenario, y después de cada cambio importante.
- **De forma programada** (diaria o semanal) en cualquier red con servidores, porque cada día se publican vulnerabilidades nuevas.
- **En redes con equipos variados** (Linux y Windows), donde es imposible revisar a mano cada versión de cada programa.
- **Cuando una norma lo exige**, como el Esquema Nacional de Seguridad, ISO 27001 o PCI-DSS, que piden revisiones periódicas de vulnerabilidades.

No obstante, OpenVAS **no es una solución completa**:

- **No corrige nada por sí mismo**: alguien tiene que leer los informes y aplicar los parches.
- **No detecta ataques en curso**: para eso está el IDS.
- **No adivina contraseñas débiles propias**: para eso está la herramienta de contraseñas.
- **Sus resultados hay que comprobarlos**, porque incluye falsos positivos.

La principal dificultad en un caso real no es instalarlo, sino **gestionar lo que encuentra**: comprobar cada resultado, separar lo real de lo falso, decidir qué riesgos se aceptan y no dejar que los avisos se acumulen sin leer.

Por tanto, OpenVAS es una herramienta muy recomendable como **capa preventiva** dentro de una estrategia de **defensa en profundidad**. Su valor no está en el número de vulnerabilidades que encuentra, sino en que nos dice **dónde mirar primero** y nos permite **demostrar** que la red es cada día un poco más segura.

