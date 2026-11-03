# Implantación de Snort como IDS en un escenario con PostgreSQL y Nginx (R1)

Gabriel Merencio Ortega 2º ASIR

## 1. Introducción

En esta documentación se describe la implantación de **Snort 3** como sistema de detección de intrusos (IDS) en el escenario R1.

El objetivo es disponer de un mecanismo que **vigile el tráfico de la red** y avise cuando detecte actividad sospechosa contra los servicios en producción, sin interferir en su funcionamiento. A diferencia de un sistema de integridad de ficheros como AIDE, que vigila *los archivos de cada servidor*, Snort vigila *lo que circula por la red*: escaneos, intentos de acceso no autorizados, fuerza bruta o ataques contra las aplicaciones.

Como ya vimos en la guía específica de instalación y configuración de Snort, la herramienta analiza cada paquete y lo compara con un conjunto de **firmas (reglas)**. En este caso adaptaremos esas reglas a las particularidades del escenario (Nginx y PostgreSQL) y comprobaremos su funcionamiento lanzando técnicas básicas de pentesting contra los servicios, verificando que el IDS las detecta.

Snort se despliega como **IDS pasivo**: observa una copia del tráfico y genera alertas, pero **no bloquea** nada. Más adelante se justifica esta decisión.

## 2. El escenario y la ubicación del sensor

### 2.1. Descripción del escenario

El escenario R1 está formado por un servidor que publica dos servicios, accedidos por dos clientes, todo dentro de la misma red conmutada:

| Máquina         | Dirección   | Función                                                |
| --------------- | ----------- | ------------------------------------------------------ |
| Servidor        | 10.20.30.10 | Nginx (HTTP, puerto 80) y PostgreSQL (puerto 5432)     |
| Cliente Linux   | 10.20.30.21 | Equipo legítimo que consulta la web y la base de datos |
| Cliente Windows | 10.20.30.22 | Equipo legítimo que accede a la web                    |
| Sensor Snort    | 10.20.30.40 | Máquina dedicada al IDS                                |
| Atacante        | 10.20.30.30 | Máquina usada para las pruebas de pentesting           |

Los servicios se publican **sin cifrar** (HTTP y PostgreSQL en claro), tal y como corresponde a muchos entornos internos reales, lo que permite además demostrar por qué el cifrado es importante.

### 2.2. Dónde se coloca el sensor

El profesor indicó un requisito clave: **el sensor debe ser una máquina aparte de la víctima**, no puede ir instalado en el propio servidor. Esto es también lo correcto en producción por tres motivos:

- Si el servidor se ve comprometido, el atacante podría desactivar o manipular un IDS instalado en él. Un sensor independiente conserva las evidencias.
- El análisis de tráfico consume CPU y memoria; separarlo evita penalizar el rendimiento del servicio.
- Un único sensor puede vigilar **toda la red**, no solo un equipo.

El sensor se sitúa de forma que **vea todo el tráfico del segmento** donde están el servidor y los clientes, es decir, conectado al switch que los une.

### 2.3. Cómo se conecta el sensor: port mirroring

Un switch, por diseño, solo envía a cada puerto el tráfico destinado a ese puerto. Para que el sensor pueda analizar las conversaciones entre el servidor y los clientes necesitamos configurar un **puerto espejo (port mirroring / SPAN)**: el switch copia todo el tráfico hacia el puerto donde está conectado el sensor.

- En el **laboratorio** usamos un switch virtual Open vSwitch y creamos el espejo con `ovs-vsctl` (mirror `span-sdi`, `select-all=true`) hacia el puerto del sensor.
- En un **entorno real** se hace igual pero en un switch gestionable. Por ejemplo, en un switch Cisco sería una sesión SPAN:

```text
monitor session 1 source vlan 30 both
monitor session 1 destination interface GigabitEthernet0/24
```

Donde `source` es la VLAN o los puertos a vigilar y `destination` el puerto del sensor. Como alternativa al SPAN existen los **TAP de red**, dispositivos físicos que duplican el tráfico sin cargar al switch, recomendables en enlaces muy saturados.

La interfaz del sensor que recibe el espejo se configura en **modo promiscuo y sin dirección IP**: así captura todo el tráfico y, al no tener IP, no es accesible desde la red (el sensor es "invisible" para el atacante). El sensor usa una **segunda interfaz, solo para su gestión** (acceso SSH del administrador), separada de la de escucha.

## 3. Usuarios necesarios

Para la puesta en producción del IDS se crean los siguientes usuarios, siguiendo el principio de **mínimo privilegio**:

| Máquina  | Usuario                 | Finalidad                                                                                                                                                                                        |
| -------- | ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Sensor   | `snort`                 | Usuario de servicio **sin shell de inicio de sesión** con el que se ejecuta el proceso Snort. No es un usuario con el que se inicie sesión; solo sirve para que el demonio no corra como `root`. |
| Sensor   | `admin` (administrador) | Usuario con `sudo` para la gestión del sensor (actualizar reglas, revisar alertas). Accede por la interfaz de gestión.                                                                           |
| Servidor | `www-data`              | Usuario del sistema con el que se ejecuta Nginx (ya existe por defecto; se documenta porque es el que sirve la web).                                                                             |
| Servidor | `labuser`               | Rol de PostgreSQL propietario de la base de datos `tienda`. Es un usuario **de la base de datos**, no del sistema operativo.                                                                     |
| Servidor | `admin` (administrador) | Usuario con `sudo` para administrar el servidor.                                                                                                                                                 |

El usuario `snort` se crea así en el sensor:

```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin snort
```

El uso de un usuario de servicio dedicado es importante: si existiera un fallo de seguridad en el propio Snort, el impacto quedaría limitado a los permisos de `snort`, no a los de `root`.

## 4. Instalación y puesta en marcha de Snort

Snort 3 no viene empaquetado en Debian, por lo que se compila desde el código fuente junto con su librería de captura **libdaq**. El resultado utilizado es **libdaq 3.0.28.0** y **Snort 3.12.4.0**.

El proceso, resumido, es:

1. Instalar las dependencias de compilación (`build-essential`, `cmake`, `libpcap-dev`, `libpcre2-dev`, `libdnet-dev`, `hwloc`, `flex`, `bison`, `libhyperscan-dev`, etc.).
2. Compilar e instalar libdaq.
3. Compilar e instalar Snort 3.
4. Comprobar la instalación:

```bash
snort -V
snort --daq-list
```

El primer comando confirma la versión y que se ha compilado con **Hyperscan** (motor de búsqueda rápido de patrones, importante para el rendimiento en producción). El segundo lista los módulos de captura disponibles.

## 5. Configuración de red de Snort: qué vigilar

La configuración se escribe en `/usr/local/etc/snort/snort.lua`. Lo más relevante para el escenario:

- **`HOME_NET`**: la red que protegemos. En el escenario es `10.20.30.0/24`. Es la referencia que usan las reglas para saber qué es "nuestra red".
- **`EXTERNAL_NET`**: se deja en `any` (cualquier origen), lo que permite detectar también ataques internos, no solo los que vienen de fuera.
- **Módulo `daq` en modo `afpacket` pasivo**, leyendo la interfaz de escucha que recibe el espejo, con `snaplen` de 65535 para capturar el paquete completo.
- **`ips` en modo `tap`**: modo pasivo, solo alerta.
- Salidas de alertas: `alert_fast` (texto legible) y `alert_json` (formato estructurado, útil si en el futuro se envía a un SIEM).

Al tratarse de tráfico recibido por un puerto espejo, se desactiva la validación de *checksums* (`checksum_eval = 'none'`), ya que en el tráfico duplicado pueden aparecer sumas de comprobación incompletas.

## 6. Reglas por defecto

Snort se apoya en dos conjuntos de reglas que no escribimos nosotros:

- **Reglas internas (builtin)** de los inspectores (detección de escaneos, anomalías de protocolo, ARP spoofing, etc.).
- **Reglas de la comunidad** publicadas por **Cisco Talos** (`snort3-community-rules`, unas 4024 reglas), que cubren ataques conocidos contra servicios muy habituales.

Se descargan, se colocan junto a la configuración y se incluyen en el bloque `ips`. Por servicio, el grupo más numeroso suele ser `http`, lo que encaja con nuestro escenario, donde el servicio más expuesto es el servidor web.

En producción estas reglas **deben actualizarse periódicamente**, igual que un antivirus actualiza sus firmas. Lo habitual es automatizar la descarga con una herramienta como **PulledPork** lanzada por una tarea programada (`cron` o un *timer* de systemd).

## 7. Reglas propias adaptadas al escenario

Las reglas de la comunidad cubren ataques genéricos, pero no conocen *nuestro* escenario. Por eso se escriben reglas propias en `/usr/local/etc/rules/local.rules`, con SID a partir de 1000000 y el prefijo `LAB` en el mensaje para distinguirlas. Las principales:

| SID               | Qué detecta                                                | Para qué sirve en el escenario                           |
| ----------------- | ---------------------------------------------------------- | -------------------------------------------------------- |
| 1000001           | Ping (ICMP) hacia la red interna                           | Regla de prueba para validar que el sensor ve el tráfico |
| 1000010           | Acceso a `/admin` desde un equipo **no autorizado**        | Vigila el panel de administración del servidor web       |
| 1000011           | Peticiones con el *User-Agent* de **Nikto**                | Detecta escáneres web conocidos                          |
| 1000012           | Peticiones con el *User-Agent* de **Nmap**                 | Detecta sondeo web con Nmap                              |
| 1000020           | Sentencia `DROP TABLE` hacia PostgreSQL                    | Detecta intentos de destrucción de datos                 |
| 1000021           | Respuesta de **autenticación fallida** de PostgreSQL       | Detecta intentos de acceso con credenciales incorrectas  |
| 1000030           | Más de 5 conexiones nuevas a SSH en 60 s desde la misma IP | Detecta **fuerza bruta** contra SSH                      |
| 1000040 / 1000041 | Acceso a `/config`, con excepción para el cliente legítimo | Ejemplo de uso de la acción `pass`                       |

Para no depender de direcciones IP fijas dentro de cada regla, se definen **variables** en `snort.lua` (por ejemplo `CLIENTES_LAB` y `SERVIDOR_LAB`). Así, si el escenario cambia, solo se edita la variable y no todas las reglas.

## 8. Opciones de las reglas y reducción de ruido

Cada regla se compone de una **cabecera** (acción, protocolo, origen, destino) y un **cuerpo** entre paréntesis con **opciones**:

- **Informativas**: `msg`, `sid`, `rev`, `classtype` (describen la alerta).
- **De flujo y protocolo**: `flow`, `flags`, `itype` (acotan cuándo mirar).
- **De contenido**: `content`, `nocase`, `http_uri`, `http_header`, `pcre` (buscan datos dentro del paquete).
- **De control de frecuencia**: `detection_filter` (por ejemplo, alertar solo a partir de X eventos en Y segundos, que es como se detecta la fuerza bruta).

Un problema real de todo IDS es el **exceso de alertas**. Un solo escaneo con Nikto puede generar miles. Para evitar la *fatiga de alertas* se usan:

- **`suppress`**: silenciar por completo una regla concreta (por ejemplo, un falso positivo conocido).
- **`event_filter` (type=limit)**: limitar cuántas veces se registra una misma alerta en un intervalo.

Esto es una de las tareas más importantes al llevar Snort a producción: **ajustar** las reglas al tráfico normal del escenario para que las alertas que queden sean significativas.

## 9. Acciones de las reglas: por qué IDS pasivo

Snort dispone de varias acciones. Las pasivas (`alert`, `log`, `pass`) no tocan el tráfico; las activas (`drop`, `block`, `reject`, `react`, `rewrite`) requieren que Snort esté **en línea** (modo IPS), es decir, que todo el tráfico pase físicamente a través de él.

En este escenario Snort está conectado a un **puerto espejo**, que entrega una **copia** del tráfico. Sobre una copia **no se puede bloquear** el original, por lo que el despliegue es necesariamente **IDS (detección)**, no IPS (prevención). Esto se decidió a propósito:

- No introduce un punto único de fallo en la red: si el sensor se cae, los servicios siguen funcionando.
- No corre el riesgo de bloquear tráfico legítimo por un falso positivo.
- Es el rol que pedía el enunciado y el más seguro para empezar.

La acción `pass` se usa como ejemplo para **eximir** de una alerta a un origen concreto (el cliente legítimo accediendo a `/config`), demostrando que en Snort 3 las reglas `pass` tienen prioridad sobre las `alert`.

## 10. Notificaciones por correo

Snort registra las alertas en un fichero (`alert_fast.txt`), pero no envía correos por sí mismo. Para avisar al administrador se usa un **script de vigilancia** que lee ese fichero en tiempo real con `tail -F` y, por cada alerta de **prioridad alta** (`Priority: 1`), envía un correo mediante **msmtp** a través de una cuenta de Gmail con contraseña de aplicación.

El script incorpora un **tiempo de espera (`COOLDOWN`)** de 120 segundos: si se produce una ráfaga de muchas alertas (por ejemplo, una fuerza bruta que genera decenas de eventos), **agrupa** todas en un único correo en lugar de enviar decenas. Esto es clave en producción para no saturar el buzón del administrador.

El script se ejecuta como **servicio systemd**, que arranca junto al sistema y se reinicia solo si falla.

En un despliegue mayor, este mismo fichero `alert_json.txt` podría enviarse además a un **SIEM** (por ejemplo ELK o Wazuh) para correlacionar las alertas de Snort con las de otros equipos. En nuestro caso el envío por correo es suficiente para el escenario.

## 11. Pruebas de funcionamiento (técnicas de pentesting)

> **Nota importante.** Todas estas pruebas se realizan en un **entorno controlado y propio**, con autorización. El pentesting solo es legal sobre sistemas de los que se tiene permiso expreso.

Para comprobar que el IDS funciona se lanzan, desde la máquina atacante (10.20.30.30), técnicas básicas de reconocimiento y explotación contra el servidor, y se verifica que Snort las detecta. Antes de cada prueba se anota el número de alertas y después se vuelve a medir, para contar las que ha generado cada ataque.

### 11.1. Reconocimiento: escaneo de puertos

```bash
sudo nmap -sS -p- 10.20.30.10
```

Un escaneo SYN de todos los puertos descubre 22 (SSH), 80 (HTTP) y 5432 (PostgreSQL).

**Resultado esperado:** el inspector interno `port_scan` (GID 122) genera la alerta `(portscan) TCP portscan`. Snort agrupa el escaneo en **una sola alerta** por sesión, no una por puerto.

### 11.2. Reconocimiento: detección de servicios y versiones

```bash
sudo nmap -sV -sC 10.20.30.10
```

Nmap identifica las versiones (OpenSSH, nginx, PostgreSQL) y ejecuta scripts de reconocimiento.

**Resultado esperado:** saltan reglas internas y reglas de la comunidad asociadas al sondeo de servicios.

### 11.3. Escaneo web con Nikto

```bash
nikto -h http://10.20.30.10
```

Nikto lanza miles de peticiones buscando rutas y fallos conocidos; encuentra, entre otras cosas, la zona `/admin/`.

**Resultado esperado:** el inspector `http_inspect` y las reglas de la comunidad generan un gran número de alertas.

Esta prueba sirve además para demostrar una **limitación de los IDS basados en firmas**: por defecto Nikto se presenta con el *User-Agent* de un navegador, por lo que la regla propia que busca la palabra `Nikto` **no salta**. Solo al forzar el *User-Agent* (`-useragent "Nikto"`) se identifica. Es un ejemplo real de cómo un atacante puede evadir una firma, y de por qué conviene combinar reglas propias con las de comportamiento (como `port_scan`).

### 11.4. Acceso no autorizado al panel de administración

```bash
curl http://10.20.30.10/admin/
```

**Resultado esperado:** la regla propia 1000010 genera una alerta por cada acceso a `/admin` **desde un origen no autorizado** (la máquina atacante). El mismo acceso desde el cliente legítimo **no** genera alerta, porque la regla excluye su dirección. Esto demuestra cómo se adapta una regla al escenario concreto.

### 11.5. Fuerza bruta contra SSH

```bash
hydra -l admin -P /usr/share/wordlists/rockyou.txt ssh://10.20.30.10
```

Hydra prueba miles de contraseñas del diccionario `rockyou.txt` contra el usuario SSH.

**Resultado esperado:** la regla propia 1000030, que usa `detection_filter`, genera alerta al superar el umbral de 5 conexiones nuevas en 60 segundos desde la misma IP. Gracias al `COOLDOWN` del script, el administrador recibe **un solo correo** que resume la ráfaga.

### 11.6. Ataque contra PostgreSQL

```bash
PGPASSWORD=incorrecta psql -h 10.20.30.10 -U labuser -d tienda -c "SELECT 1;"
PGPASSWORD=correcta  psql -h 10.20.30.10 -U labuser -d tienda -c "DROP TABLE clientes;"
```

**Resultado esperado:** la regla 1000021 detecta cada **autenticación fallida** (respuesta del servidor), y la regla 1000020 detecta la sentencia **`DROP TABLE`**. Ambas son de prioridad alta y disparan correo.

### 11.7. Captura de tráfico en claro (sniffing)

Como el sensor recibe una copia de **todo** el tráfico, se puede comprobar que una consulta SQL y su respuesta viajan **en texto plano**:

```bash
sudo tcpdump -i <interfaz_escucha> -A port 5432
```

**Resultado esperado:** se ve la consulta `SELECT * FROM clientes;` y los datos devueltos (nombres y correos) legibles. Esto demuestra el riesgo de no cifrar: con TLS en PostgreSQL y HTTPS en Nginx, esa información aparecería cifrada. Es una conclusión de seguridad importante que el propio IDS ayuda a evidenciar.

### 11.8. Resumen

| Técnica / herramienta            | Qué busca el atacante         | Cómo lo detecta Snort                                             |
| -------------------------------- | ----------------------------- | ----------------------------------------------------------------- |
| `nmap -sS`                       | Puertos abiertos              | Inspector `port_scan` (GID 122)                                   |
| `nmap -sV -sC`                   | Versiones y vulnerabilidades  | Reglas internas y de la comunidad                                 |
| `nikto`                          | Rutas y fallos web            | `http_inspect` + reglas comunidad (+ regla propia si no se evade) |
| `curl /admin`                    | Panel de administración       | Regla propia 1000010                                              |
| `hydra` SSH                      | Contraseñas por fuerza bruta  | Regla propia 1000030 (`detection_filter`)                         |
| `psql` credenciales/`DROP TABLE` | Acceso y destrucción de datos | Reglas propias 1000020 y 1000021                                  |
| Tráfico en claro                 | Robo de credenciales/datos    | El sensor evidencia la falta de cifrado                           |

## 12. Gestión de alertas y mantenimiento en producción

Para que el IDS siga siendo útil con el tiempo:

- **Actualización de reglas:** descargar periódicamente las reglas de la comunidad (PulledPork + tarea programada). Las firmas caducan igual que las de un antivirus.
- **Rotación de logs:** los ficheros de alertas crecen; se configura `logrotate` para que no llenen el disco del sensor.
- **Ajuste continuo:** revisar los falsos positivos y añadir `suppress`/`event_filter` según el tráfico real del escenario.
- **Protección del propio sensor:** interfaz de escucha sin IP (invisible), acceso de gestión restringido por **lista blanca** (solo las IP de administración, denegando el resto por defecto), y el servicio ejecutándose con el usuario `snort`, no `root`.
- **Revisión de alertas:** definir quién lee los correos y qué se hace ante una alerta de prioridad alta.

## 13. Dificultades encontradas en la implantación

Al llevar Snort de la teoría a un caso real aparecen varias dificultades:

- **Instalación desde el código fuente:** Snort 3 no está empaquetado en Debian; compilarlo junto con libdaq y resolver las dependencias es más laborioso que un simple `apt install`.
- **Configuración del puerto espejo:** el mirroring debe rehacerse si se reinicia el switch o las máquinas; hubo que automatizarlo en el arranque del laboratorio. En un switch físico hay que tener un puerto libre y permisos para configurar el SPAN.
- **Exceso de alertas:** un solo escaneo genera miles de eventos. Sin `suppress` ni `event_filter`, el volumen es inmanejable y aparece la **fatiga de alertas**.
- **Evasión de firmas:** como se vio con Nikto, un atacante puede cambiar un detalle (el *User-Agent*) y evitar una regla basada en contenido. Un IDS de firmas no detecta lo que no tiene firma.
- **Tráfico cifrado:** si los servicios usaran TLS, Snort **no podría** inspeccionar el contenido de las conexiones; solo vería metadatos. Esto condiciona qué se puede detectar.
- **Equilibrio entre detección y ruido:** afinar las reglas para que detecten lo importante sin saturar es un trabajo continuo, no una configuración única.

## 14. Conclusiones: utilidad de un sistema de detección de intrusos

La implantación de Snort demuestra la utilidad de disponer de un mecanismo que **vigile la red** y avise de la actividad sospechosa antes de que se convierta en un incidente mayor.

En el escenario, Snort complementa perfectamente a un sistema de integridad de ficheros como AIDE: mientras AIDE detecta que **ya se ha modificado un archivo** en un servidor, Snort puede detectar el **ataque en curso** sobre la red (el escaneo, la fuerza bruta, el acceso al panel) **antes** de que llegue a modificar nada. Son capas distintas que se apoyan.

Considero especialmente recomendable utilizar un IDS como Snort en los siguientes contextos:

- **Redes con servicios expuestos:** servidores web y de base de datos, que son el objetivo habitual de escaneos y ataques.
- **Segmentos donde conviven usuarios y servidores:** para detectar también amenazas internas, no solo las que vienen de Internet.
- **Entornos que necesitan trazabilidad:** el registro de alertas sirve como evidencia ante una auditoría o un incidente.
- **Como apoyo a un SIEM:** Snort aporta la visión de red que, correlacionada con los registros de los equipos, da una imagen completa.

No obstante, como hemos observado, un IDS **no es una solución de seguridad completa**. No bloquea los ataques (en modo pasivo), no detecta lo que no tiene firma y no puede inspeccionar el tráfico cifrado. Tampoco sustituye al cortafuegos, al control de acceso, a las actualizaciones ni a las copias de seguridad.

La principal dificultad de su uso en producción es **mantener las reglas afinadas y actualizadas**, diferenciando el tráfico normal del realmente sospechoso para que las alertas sean fiables.

Por tanto, Snort es una herramienta muy recomendable como **capa de detección** dentro de una estrategia de **defensa en profundidad**, especialmente en redes con servicios expuestos. Su utilidad no depende de generar el mayor número posible de alertas, sino de **detectar correctamente la actividad que nunca debería producirse** en la red que protege.
