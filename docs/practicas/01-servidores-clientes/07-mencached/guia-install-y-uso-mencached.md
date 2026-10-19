# Guía de Instalación, Funcionamiento y Uso Básico de Memcached en Debian 13

Esta guía cubre qué es Memcached y cómo funciona, su instalación desde los repositorios de Debian 13 (trixie), su configuración básica, el uso de los comandos principales, la autenticación de clientes (gestión de usuarios, con las limitaciones que tiene este motor) y la consulta de estadísticas. No se cubre el acceso remoto: el servicio se deja escuchando solo en `localhost`.

## 1. Qué es Memcached y cómo funciona

Memcached **no es una base de datos al uso**, es una **caché clave-valor en memoria RAM**. Se coloca delante de una base de datos (MySQL, PostgreSQL...) para guardar temporalmente resultados costosos de calcular o consultar, y así evitar repetir la consulta.

**Cosas a tener en cuenta sobre Memcached:**

- Todo se guarda **en RAM**. Si el servicio se reinicia o el equipo se apaga, **todos los datos se pierden**. No hay persistencia en disco.
- Es un almacén de pares **clave → valor** y nada más. No hay tablas, esquemas, consultas, filtros ni ordenación. Solo se puede obtener un valor si se conoce su clave exacta.
- El valor es una cadena de bytes opaca para el servidor (texto, JSON, un objeto serializado...). Memcached no interpreta su contenido.
- Cada dato puede tener un **tiempo de vida (TTL)**. Cuando caduca, deja de devolverse.
- Cuando la memoria asignada se llena, Memcached **elimina automáticamente los datos menos usados recientemente (política LRU)**. Que un dato desaparezca antes de caducar es un comportamiento normal, por eso la aplicación siempre debe poder recuperar el dato de la fuente original.
- Límites por defecto: clave de hasta **250 bytes** (sin espacios ni saltos de línea) y valor de hasta **1 MB**.
- **No hay replicación ni clústeres entre servidores.** Si se usan varios servidores Memcached, es el **cliente** quien decide en cuál guardar cada clave (hash de la clave). Los servidores no se conocen entre sí.
- Es multihilo y extremadamente rápido: las operaciones tienen coste prácticamente constante.

### 1.1. Patrón de uso habitual (cache-aside)

1. La aplicación necesita un dato y pregunta primero a Memcached (`get`).
2. Si existe (*hit*), lo usa y termina.
3. Si no existe (*miss*), lo consulta a la base de datos real.
4. Guarda el resultado en Memcached con un TTL (`set`) para las próximas peticiones.
5. Cuando el dato original cambia, se borra o se actualiza en la caché (`delete` / `set`).

### 1.2. Comparación rápida con Redis

| | Redis | Memcached |
|---|---|---|
| Tipos de datos | Cadenas, listas, hashes, conjuntos, conjuntos ordenados y más | Solo cadenas de bytes |
| Persistencia | Opcional (snapshots y registro de operaciones en disco) | Ninguna, todo en RAM |
| Replicación | Sí (réplicas, Sentinel, Cluster) | No |
| Hilos | Ejecución de comandos en un único hilo | Multihilo |
| Tamaño máximo de valor | 512 MB | 1 MB por defecto |
| Usuarios | ACL por usuario, con permisos sobre comandos y claves | Autenticación básica opcional, sin permisos |

## 2. Instalación

Memcached está disponible en los repositorios oficiales de Debian, no hace falta añadir ninguno externo.

```
sudo apt update
sudo apt install -y memcached libmemcached-tools netcat-openbsd
```

- `memcached`: el servidor.
- `libmemcached-tools`: herramientas de línea de comandos opcionales (`memcstat`, `memccat`...).
- `netcat-openbsd`: para hablar con el servidor manualmente con `nc`.

El paquete crea el usuario `memcache`, el servicio de systemd y arranca el servicio automáticamente. Comprobamos el estado y la versión:

```
sudo systemctl status memcached --no-pager
memcached -h | head -n 1
```

Salida (resumida):

```
debian@memcached:~$ sudo systemctl status memcached --no-pager
● memcached.service - memcached daemon
     Loaded: loaded (/usr/lib/systemd/system/memcached.service; enabled; preset: enabled)
     Active: active (running) since Mon 2026-10-19 11:05:41 UTC; 934ms ago

debian@memcached:~$ memcached -h | head -n 1
memcached 1.6.38
```

Verificamos que escucha **solo en localhost** en el puerto 11211:

```
sudo ss -tlnp | grep 11211
```

```
LISTEN 0  1024  127.0.0.1:11211  0.0.0.0:*  users:(("memcached",pid=1182,fd=26))
LISTEN 0  1024      [::1]:11211     [::]:*  users:(("memcached",pid=1182,fd=27))
```

> Memcached **no debe exponerse nunca a Internet** sin cortafuegos: por defecto no exige autenticación y ha sido utilizado en ataques de amplificación DDoS. Por eso esta guía lo mantiene en `127.0.0.1`.

## 3. Configuración básica

En Debian, el fichero `/etc/memcached.conf` contiene **las opciones de línea de comandos del servidor, una por línea**. Parámetros más importantes:

| Opción | Significado | Valor por defecto |
|---|---|---|
| `-m` | Memoria RAM máxima para datos, en MB | `64` |
| `-p` | Puerto TCP | `11211` |
| `-l` | Dirección en la que escucha | `127.0.0.1` |
| `-c` | Conexiones simultáneas máximas | `1024` |
| `-u` | Usuario del sistema con el que se ejecuta | `memcache` |
| `-I` | Tamaño máximo de un valor | `1m` |
| `-v` | Mensajes de log detallados | desactivado |

Ejemplo: aumentamos la memoria de la caché a 256 MB y reiniciamos el servicio:

```
sudo sed -i 's/^-m .*/-m 256/' /etc/memcached.conf
sudo systemctl restart memcached
```

Verificamos:

```
grep -E '^-(m|p|l|c)' /etc/memcached.conf
```

```
-m 256
-p 11211
-l 127.0.0.1
-l ::1
```

> Hay dos líneas -l (IPv4 e IPv6) y -c no aparece en el fichero: se aplica su valor por defecto (1024). Al reiniciar el servicio **se vacía la caché**, ya que está en RAM.

## 4. Uso básico

Memcached usa un protocolo de texto muy sencillo, por lo que podemos conectarnos con `telnet` o con `nc` y escribir los comandos a mano. Con `nc` hay que usar la opción `-C` para que envíe los saltos de línea como `\r\n`, que es lo que exige el protocolo:

```
nc -C 127.0.0.1 11211
```

Para salir se escribe `quit`.

### 4.1. Guardar datos: `set`, `add`, `replace`

Sintaxis: `set <clave> <flags> <ttl_segundos> <bytes>` seguido, en la línea siguiente, del valor.

- `flags`: número de 32 bits que el servidor guarda y devuelve sin interpretar (los clientes lo usan para indicar el tipo de dato). Usaremos `0`.
- `ttl`: segundos hasta que caduque. `0` = no caduca por tiempo (aunque puede ser expulsado por falta de memoria). Si el valor supera 30 días (2592000), se interpreta como una fecha Unix absoluta.
- `bytes`: **longitud exacta del valor** en bytes. Si no coincide, da error.

```
set cliente:1 0 300 11
Juan Pérez
STORED
```

> Cuidado: `Juan Pérez` ocupa **11 bytes** en UTF-8 porque `é` ocupa 2. Si se declara una longitud incorrecta, el servidor devuelve `CLIENT_ERROR bad data chunk`. En la práctica el servidor responde CLIENT_ERROR bad data chunk y después un ERROR adicional, porque el byte que sobra se interpreta como un comando. Por eso, para las pruebas conviene usar texto ASCII.

Ejemplo correcto con texto ASCII:

```
set cliente:1 0 300 10
Juan Perez
STORED
```

Variantes:

- `add`: guarda **solo si la clave no existe** (si existe devuelve `NOT_STORED`).
- `replace`: guarda **solo si la clave ya existe**.
- `append` / `prepend`: añade datos al final / principio del valor existente.

```
add cliente:1 0 300 3
XXX
NOT_STORED
replace cliente:99 0 300 3
XXX
NOT_STORED
set cliente:2 0 300 9
Ana Gomez
STORED
append cliente:2 0 0 1
!
STORED
```

### 4.2. Leer datos: `get`, `gets`

```
get cliente:1
VALUE cliente:1 0 10
Juan Perez
END
```

Se pueden pedir varias claves a la vez, y si una no existe simplemente no aparece:

```
get cliente:1 cliente:2 cliente:99
VALUE cliente:1 0 10
Juan Perez
VALUE cliente:2 0 10
Ana Gomez!
END
```

`gets` devuelve además un identificador de versión (`cas unique`) del valor, que sirve para actualizaciones seguras (ver 4.4).

### 4.3. Contadores: `incr`, `decr`

Si el valor es un número, se puede incrementar o decrementar de forma atómica (útil para contadores de visitas o límites de peticiones):

```
set visitas 0 0 1
0
STORED
incr visitas 5
5
incr visitas 1
6
decr visitas 2
4
```

### 4.4. Actualización segura con `cas`

Si varios clientes pueden modificar la misma clave, `cas` (*check and set*) solo guarda si nadie la ha cambiado desde que se leyó:

```
gets cliente:1
VALUE cliente:1 0 10 6
Juan Perez
END
cas cliente:1 0 300 10 6
Juan Lopez
STORED
cas cliente:1 0 300 10 6
Juan Lopez
EXISTS
```

(Ahí el valor `Juan Lopez` tiene 10 bytes; ajustar la longitud al valor real. La segunda orden devuelve EXISTS porque el valor ya cambió desde la lectura con gets, que es la misma situación que si otro cliente lo hubiese modificado antes: la respuesta es `EXISTS`.)

### 4.5. Caducidad y borrado: `touch`, `delete`, `flush_all`

```
touch cliente:1 600
TOUCHED
delete cliente:1
DELETED
get cliente:1
END
```

- `touch <clave> <ttl>`: renueva el tiempo de vida sin tocar el valor.
- `delete <clave>`: elimina la clave.
- `flush_all`: **invalida todo el contenido** de la caché. Úsese con precaución.

Para comprobar la caducidad:

```
set temporal 0 5 4
hola
STORED
get temporal
VALUE temporal 0 4
hola
END
```

Pasados 5 segundos:

```
get temporal
END
```

### 4.6. Uso sin sesión interactiva

También se pueden ejecutar comandos puntuales de forma no interactiva con `printf` (en este caso hay que escribir explícitamente los `\r\n`):

```
printf 'set prueba 0 60 5\r\nhola1\r\nget prueba\r\nquit\r\n' | nc -q1 127.0.0.1 11211
```

```
STORED
VALUE prueba 0 5
hola1
END
```

## 5. Gestión de usuarios y autenticación

Memcached **no tiene una gestión de usuarios real**: no existe nada equivalente a `CREATE ROLE` ni a `GRANT`, y no se pueden dar permisos distintos a cada usuario sobre unos datos u otros. Lo único que existe es una autenticación opcional por fichero que, si se activa, exige unas credenciales antes de aceptar comandos. Se explica aquí para saber que existe y cómo se interactúa con ella, pero **no introduce ninguna securización real ni protección del acceso a los datos según el usuario**: todos los usuarios autenticados tienen acceso total a todo (incluido `flush_all`), no hay roles, el tráfico no se cifra y las contraseñas están en texto plano en un fichero. Su único efecto es impedir que un cliente sin credenciales hable con el servidor.

Existen dos mecanismos:

- **Autenticación por fichero (`-Y`)**: la más simple y funciona con el protocolo de texto, aunque está marcada como experimental. Es la que usaremos.
- **SASL (`-S`)**: más antigua, requiere el protocolo binario, paquetes adicionales (`sasl2-bin`) y clientes con soporte SASL. No se detalla aquí.

> En Memcached 1.6.38 (Debian 13) la ayuda del propio programa marca esta opción como EXPERIMENTAL (memcached -h | grep -i -E 'auth|sasl' muestra: -Y, --auth-file=<file> (EXPERIMENTAL) enable ASCII protocol authentication). Comprueba que tu versión soporta la opción `-Y` con `memcached -h | grep -i auth`.

### 5.1. Creación del fichero de usuarios

El fichero contiene una línea `usuario:contraseña` por usuario, **en texto plano**, por lo que debe protegerse con permisos estrictos:

```
sudo tee /etc/memcached.auth > /dev/null << 'EOF'
usuario_prueba:<PASSWORD_APP>
EOF
sudo chown memcache:memcache /etc/memcached.auth
sudo chmod 600 /etc/memcached.auth
ls -l /etc/memcached.auth
-rw------- 1 memcache memcache 28 Oct 19 11:06 /etc/memcached.auth
```

Para añadir otro usuario basta con añadir otra línea; para eliminarlo, quitar la línea. Para **cambiar una contraseña**, se edita la línea. En todos los casos hay que reiniciar el servicio, ya que el fichero se lee al arrancar.

### 5.2. Activación

Añadimos la opción al fichero de configuración y reiniciamos:

```
echo '-Y /etc/memcached.auth' | sudo tee -a /etc/memcached.conf
sudo systemctl restart memcached
sudo systemctl status memcached --no-pager
```

### 5.3. Comprobación

Sin autenticar, los comandos son rechazados:

```
nc -C 127.0.0.1 11211
get cliente:1
CLIENT_ERROR unauthenticated
```

Para autenticarse, el **primer comando** de la conexión debe ser un `set` cuyo valor sea `usuario contraseña` (separados por un espacio). La clave del `set` es irrelevante. Si las credenciales son correctas, responde `STORED`:

```
printf 'set x 0 0 27\r\nusuario_prueba ClaveApp2026\r\nset cliente:1 0 300 10\r\nJuan Perez\r\nget cliente:1\r\nquit\r\n' | nc -q1 127.0.0.1 11211
STORED
STORED
VALUE cliente:1 0 10
Juan Perez
END

# credenciales incorrectas
printf 'set x 0 0 24\r\nusuario_prueba claveMala\r\nget cliente:1\r\nquit\r\n' | nc -q1 127.0.0.1 11211
CLIENT_ERROR unauthenticated

# un usuario autenticado puede ejecutar cualquier comando, incluido flush_all
printf 'set x 0 0 27\r\nusuario_prueba ClaveApp2026\r\nflush_all\r\nquit\r\n' | nc -q1 127.0.0.1 11211
STORED
OK
```

(Con la contraseña de ejemplo ClaveApp2026 la longitud `27` debe ajustarse al número exacto de caracteres de `usuario contraseña`.)

> **Sobre la seguridad:** esta autenticación es solo una barrera de entrada, no un control de acceso. Cualquiera con unos credenciales válidos puede leer, modificar o borrar toda la caché; usuario y contraseña viajan en claro por la red y el fichero guarda las contraseñas sin cifrar. La protección real de Memcached se consigue a nivel de red: escuchar solo en `127.0.0.1` (o en una red privada) y usar un cortafuegos que limite qué equipos llegan al puerto 11211. Si hay que separar los datos de varias aplicaciones, lo correcto es usar una instancia de Memcached distinta para cada una; los prefijos en las claves son solo una convención, no una restricción.

## 6. Estadísticas y mantenimiento

El comando `stats` devuelve el estado interno del servidor:

```
nc -C 127.0.0.1 11211
stats
(salida abreviada)
STAT uptime 37
STAT curr_connections 2
STAT get_hits 9
STAT get_misses 3
STAT limit_maxbytes 268435456
STAT bytes 294
STAT curr_items 4
STAT evictions 0
```

Campos más útiles:

| Campo | Significado |
|---|---|
| `uptime` | Segundos desde el arranque |
| `curr_items` | Número de claves almacenadas ahora |
| `bytes` / `limit_maxbytes` | Memoria usada / máxima |
| `curr_connections` | Conexiones abiertas |
| `get_hits` / `get_misses` | Aciertos y fallos de lectura |
| `evictions` | Claves expulsadas por falta de memoria |

La **tasa de aciertos** es `get_hits / (get_hits + get_misses)`. Si es baja, o si `evictions` crece constantemente, conviene revisar los TTL o aumentar la memoria con `-m`.

Otros comandos de información: `stats items`, `stats slabs`, `stats settings` y `version`. Desde fuera de una sesión interactiva, con las herramientas de `libmemcached-tools`:

```
memcstat --servers=127.0.0.1:11211
Server: 127.0.0.1 (11211)
     pid: 1226
     uptime: 39
     version: 1.6.38
     libevent: 2.1.13-stable
     max_connections: 1024
     curr_connections: 2
```

Si se activó la autenticación por fichero, los comandos de estadísticas también requieren autenticarse primero en la misma conexión.

### 6.1. CheatSheet

| Operación | Comando |
|---|---|
| Guardar (siempre) | `set clave flags ttl bytes` |
| Guardar si no existe | `add ...` |
| Guardar si existe | `replace ...` |
| Leer | `get clave [clave2 ...]` |
| Leer con versión | `gets clave` |
| Actualizar con control de versión | `cas clave flags ttl bytes version` |
| Contador | `incr clave n` / `decr clave n` |
| Renovar caducidad | `touch clave ttl` |
| Borrar | `delete clave` |
| Vaciar todo | `flush_all` |
| Estadísticas | `stats` |
