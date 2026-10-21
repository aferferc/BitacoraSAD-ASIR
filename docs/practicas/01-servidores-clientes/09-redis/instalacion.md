# Instalación, configuración y uso básico de Redis en Debian 13 (Por Rubén)

Guía para instalar Redis en Debian 13, protegerlo con usuarios y contraseñas (ACL), permitir el acceso desde la red local y probar su funcionamiento básico: los distintos tipos de datos, la caducidad de las claves, los permisos y la persistencia en disco.

## 1. Qué es Redis

Redis (*REmote DIctionary Server*) es una base de datos **clave-valor** que guarda todos los datos **en memoria RAM**. Por eso responde en microsegundos, mucho más rápido que una base de datos que lee de disco.

- Cada dato se guarda bajo una **clave** (un nombre, por ejemplo `app:visitas`).
- El valor no es solo texto: Redis tiene **estructuras de datos** (listas, conjuntos, hashes, rankings...).
- Aunque trabaja en memoria, puede guardar los datos en disco para no perderlos al reiniciar (**persistencia**).
- No hay tablas ni SQL: se trabaja con comandos (`SET`, `GET`, `LPUSH`...).

Usos habituales:

| Uso | Ejemplo |
|---|---|
| Caché | Guardar el resultado de una consulta lenta a MariaDB durante 5 minutos |
| Sesiones web | Datos de la sesión de un usuario que caducan solos |
| Contadores | Visitas de una página, "me gusta" |
| Colas | Pedidos pendientes de procesar, en orden |
| Rankings | Clasificación de jugadores ordenada por puntuación |

Una convención muy extendida es nombrar las claves con dos puntos como separador: `app:producto:1`, `app:sesion:7f3a`. Redis no tiene carpetas, pero así se agrupan las claves y, como veremos, se pueden dar permisos por prefijo.

## Entorno

| Máquina | Nombre | IP |
|---|---|---|
| Servidor | `bdserver.ruben.asir` | 192.168.122.30 |
| Cliente | `cliente.ruben.asir` | 192.168.122.50 |

- Sistema: Debian 13 (Trixie) en las dos máquinas.
- Redis 8.0 (la versión que trae Debian 13). Puerto 6379.

Cambia las IPs por las tuyas.

## 2. Instalación

En el **servidor**:

```bash
sudo apt update
sudo apt install -y redis-server
```

- `redis-server`: el servidor. Como dependencia instala también `redis-tools`, que trae el cliente `redis-cli`.
- El servicio se arranca solo al terminar.

Comprobamos la versión, el servicio y que responde:

```bash
redis-server --version
sudo systemctl status redis-server --no-pager
systemctl is-enabled redis-server
redis-cli ping
```

`redis-cli ping` debe contestar `PONG`. Ahora mismo **cualquiera en el servidor puede entrar sin contraseña**: lo arreglamos en el paso 3.

Ficheros importantes:

| Qué | Dónde |
|---|---|
| Configuración | `/etc/redis/redis.conf` |
| Usuarios (lo crearemos) | `/etc/redis/users.acl` |
| Datos en disco | `/var/lib/redis/` |
| Registro (log) | `/var/log/redis/redis-server.log` |

## 3. Usuarios y contraseñas (ACL)

Desde Redis 6 existen las **ACL** (listas de control de acceso): varios usuarios, cada uno con su contraseña, los comandos que puede ejecutar y las claves que puede tocar. Crearemos tres reglas:

| Usuario | Para qué | Permisos |
|---|---|---|
| `default` | Usuario que se usa si no te identificas | **Desactivado** (`off`): nadie entra sin usuario |
| `admin` | Administración | Todo (`+@all`) sobre todas las claves (`~*`) |
| `ruben` | Aplicación / acceso remoto | Todos los comandos **menos los peligrosos** (`-@dangerous`), solo sobre claves que empiecen por `app:` |

Creamos el fichero de usuarios (pon tus contraseñas en lugar de `<CONTRASEÑA_ADMIN>` y `<CONTRASEÑA_RUBEN>`; el `>` delante es obligatorio, indica "esta es la contraseña"):

```bash
sudo tee /etc/redis/users.acl > /dev/null <<'EOF'
user default off
user admin on ><CONTRASEÑA_ADMIN> ~* &* +@all
user ruben on ><CONTRASEÑA_RUBEN> ~app:* &* +@all -@dangerous
EOF
sudo chown redis:redis /etc/redis/users.acl
sudo chmod 640 /etc/redis/users.acl
```

Significado de cada parte de una línea:

- `user ruben`: nombre del usuario.
- `on` / `off`: usuario activo o desactivado.
- `>contraseña`: su contraseña.
- `~app:*`: claves a las que puede acceder (patrón: todas las que empiezan por `app:`).
- `&*`: canales de mensajería (*pub/sub*) que puede usar.
- `+@all -@dangerous`: categorías de comandos permitidas y prohibidas. `@dangerous` incluye `FLUSHALL` (borrar todo), `CONFIG`, `KEYS`, `SHUTDOWN`...

`chown` y `chmod`: el fichero contiene contraseñas, así que solo lo leen el usuario `redis` y root.

## 4. Configuración: red, usuarios y persistencia

En vez de buscar cada opción dentro de `redis.conf` (tiene más de 2000 líneas), añadimos nuestro bloque al final. En Redis, si una opción aparece dos veces, **gana la última**. Primero hacemos una copia:

```bash
sudo cp /etc/redis/redis.conf /etc/redis/redis.conf.original
sudo tee -a /etc/redis/redis.conf > /dev/null <<'EOF'

# ===== Configuración de Rubén =====
# Escuchar en local y en la IP de la red local
bind 127.0.0.1 -::1 192.168.122.30
# Usuarios y contraseñas
aclfile /etc/redis/users.acl
# Persistencia AOF: apuntar cada escritura en disco
appendonly yes
EOF
sudo systemctl restart redis-server
sudo ss -tlnp | grep 6379
```

- `bind`: direcciones en las que escucha. Por defecto solo `127.0.0.1` (y `::1`, el local de IPv6; el `-` significa "si existe"). Añadimos la IP de la red.
- `aclfile`: fichero de usuarios del paso 3.
- `appendonly yes`: activa el registro AOF (paso 8).
- `protected-mode yes` ya viene activado: si alguien abre Redis a la red **sin** usuarios ni contraseña, Redis rechaza las conexiones remotas. Con ACL configuradas, las acepta.

`ss` debe mostrar `127.0.0.1:6379` y `192.168.122.30:6379`.

Comprobamos que ya **no se puede entrar sin usuario**:

```bash
redis-cli ping
```

Debe responder `NOAUTH Authentication required.` Ahora entramos como administrador; `--askpass` pide la contraseña sin mostrarla:

```bash
redis-cli --user admin --askpass
```

Dentro:

```text
127.0.0.1:6379> ACL WHOAMI
"admin"
127.0.0.1:6379> ACL LIST
1) "user admin on #c1e3... ~* &* +@all"
2) "user default off resetchannels -@all"
3) "user ruben on #7f9f... ~app:* &* +@all -@dangerous"
```

Redis enseña las contraseñas como un **hash** (`#c1e3...`), nunca en claro. Salimos con `exit`.

Si el servidor tiene cortafuegos `ufw`, abrimos el puerto solo para la red local:

```bash
sudo ufw allow from 192.168.122.0/24 to any port 6379 proto tcp
```

## 5. Cliente remoto

En la máquina **cliente** instalamos solo las herramientas de cliente:

```bash
sudo apt update
sudo apt install -y redis-tools netcat-openbsd
nc -zv 192.168.122.30 6379
redis-cli -h 192.168.122.30 --user ruben --askpass
```

- `-h`: servidor al que nos conectamos.
- `--user ruben --askpass`: usuario y contraseña.

Dentro comprobamos la conexión:

```text
192.168.122.30:6379> PING
PONG
192.168.122.30:6379> ACL WHOAMI
"ruben"
```

Todas las pruebas del paso 6 se hacen desde aquí, conectados como `ruben`.

## 6. Uso básico: los tipos de datos

### 6.1 Cadenas (strings): el tipo más simple

Una clave guarda un texto o un número.

```text
SET app:mensaje "Hola desde Redis"
GET app:mensaje
INCR app:visitas
INCRBY app:visitas 10
GET app:visitas
```

| Comando | Qué hace | Respuesta |
|---|---|---|
| `SET clave valor` | Guarda un valor | `OK` |
| `GET clave` | Lo lee | `"Hola desde Redis"` |
| `INCR clave` | Suma 1 (si no existe, empieza en 0) | `1` |
| `INCRBY clave 10` | Suma 10 | `11` |

`INCR` es **atómico**: aunque mil usuarios lo ejecuten a la vez, no se pierde ninguna suma. Por eso Redis es ideal para contadores.

### 6.2 Caducidad: claves que se borran solas

Es lo que hace a Redis perfecto como caché o para sesiones web.

```text
SET app:sesion:7f3a "ruben" EX 60
TTL app:sesion:7f3a
EXPIRE app:mensaje 300
TTL app:mensaje
PERSIST app:mensaje
TTL app:mensaje
```

- `EX 60`: la clave se borra sola a los 60 segundos.
- `TTL`: segundos que le quedan. `-1` significa que no caduca; `-2`, que ya no existe.
- `EXPIRE` pone caducidad a una clave que ya existía; `PERSIST` se la quita.

Si esperamos un minuto y hacemos `GET app:sesion:7f3a`, devuelve `(nil)`: ya no existe.

### 6.3 Hashes: un objeto con campos

Un hash es como una fila de una tabla: una clave con varios campos.

```text
HSET app:producto:1 nombre "Teclado mecanico" precio 49.90 stock 12
HGET app:producto:1 precio
HINCRBY app:producto:1 stock -1
HGETALL app:producto:1
```

`HGETALL` devuelve los campos y sus valores alternados:

```text
1) "nombre"
2) "Teclado mecanico"
3) "precio"
4) "49.90"
5) "stock"
6) "11"
```

### 6.4 Listas: colas en orden

Una lista guarda elementos en orden de llegada. Sirve como cola de tareas.

```text
RPUSH app:cola:pedidos pedido-101 pedido-102 pedido-103
LRANGE app:cola:pedidos 0 -1
LPOP app:cola:pedidos
LLEN app:cola:pedidos
```

- `RPUSH`: añade al final (por la derecha).
- `LRANGE ... 0 -1`: muestra desde el primero (`0`) hasta el último (`-1`).
- `LPOP`: saca el primero (`pedido-101`), como quien atiende al primero de la cola.
- `LLEN`: cuántos quedan (`2`).

### 6.5 Conjuntos (sets): elementos sin repetir

```text
SADD app:etiquetas:1 gaming usb rgb
SADD app:etiquetas:2 usb oficina
SMEMBERS app:etiquetas:1
SINTER app:etiquetas:1 app:etiquetas:2
SISMEMBER app:etiquetas:2 rgb
```

- `SADD`: añade elementos; si uno ya existe, no se repite.
- `SINTER`: elementos comunes a los dos conjuntos (`usb`).
- `SISMEMBER`: ¿está este elemento? `0` = no, `1` = sí.

### 6.6 Conjuntos ordenados (sorted sets): rankings

Cada elemento lleva una **puntuación** y Redis los mantiene ordenados.

```text
ZADD app:ranking 150 lucia 90 javier 210 carmen
ZINCRBY app:ranking 70 javier
ZREVRANGE app:ranking 0 -1 WITHSCORES
ZSCORE app:ranking lucia
```

`ZREVRANGE` los muestra de mayor a menor puntuación:

```text
1) "carmen"
2) "210"
3) "javier"
4) "160"
5) "lucia"
6) "150"
```

### 6.7 Gestionar las claves

```text
SCAN 0 MATCH app:* COUNT 100
TYPE app:ranking
EXISTS app:visitas
DEL app:etiquetas:2
DBSIZE
```

- `SCAN`: lista las claves poco a poco, sin bloquear el servidor. El primer número de la respuesta es el cursor para seguir; si es `0`, ya no hay más.
- `TYPE`: tipo de dato de la clave (`zset`, `hash`, `list`...).
- `EXISTS`: `1` si existe.
- `DEL`: borra la clave.
- `DBSIZE`: número de claves de la base de datos.

## 7. Prueba de permisos

Seguimos conectados como `ruben` desde el cliente. Estos comandos **deben fallar**:

```text
SET otra:clave 1
FLUSHALL
KEYS *
CONFIG GET bind
```

| Comando | Error | Por qué |
|---|---|---|
| `SET otra:clave 1` | `NOPERM ... no permissions to access one of the keys` | La clave no empieza por `app:` |
| `FLUSHALL` | `NOPERM ... no permissions to run the 'flushall' command` | Borraría todo: es `@dangerous` |
| `KEYS *` | `NOPERM ... 'keys' command` | Bloquea el servidor con muchas claves: es `@dangerous`. Por eso usamos `SCAN` |
| `CONFIG GET bind` | `NOPERM ... 'config\|get' command` | Solo el administrador ve la configuración |

### 7.1 Crear un usuario de solo lectura desde Redis

También se pueden crear usuarios sin editar el fichero. En el **servidor**, como `admin`:

```bash
redis-cli --user admin --askpass
```

```text
ACL SETUSER lector on ><CONTRASEÑA_LECTOR> ~app:* +@read
ACL SAVE
```

- `+@read`: solo comandos de lectura (`GET`, `HGETALL`, `LRANGE`...).
- `ACL SAVE`: guarda los usuarios en `users.acl`. Si miramos el fichero (`sudo cat /etc/redis/users.acl`), las contraseñas ya aparecen como hash.

Desde el cliente, `lector` puede hacer `GET app:visitas` pero `SET app:visitas 0` da `NOPERM ... 'set' command`.

## 8. Persistencia: que los datos sobrevivan a un reinicio

Redis trabaja en memoria, pero tiene dos formas de guardar en disco:

| Método | Cómo funciona | Fichero |
|---|---|---|
| **RDB** (*snapshot*) | Cada cierto tiempo guarda una "foto" de todos los datos | `/var/lib/redis/dump.rdb` |
| **AOF** (*append only file*) | Apunta cada escritura en un registro; al arrancar la repite | `/var/lib/redis/appendonlydir/` |

Debian trae RDB activado y nosotros activamos AOF en el paso 4. Con AOF se pierde como mucho un segundo de datos si el servidor se apaga de golpe.

En el **servidor**, como `admin`, forzamos una foto y consultamos el estado:

```text
BGSAVE
INFO persistence
INFO keyspace
```

- `BGSAVE`: guarda la foto RDB en segundo plano (`Background saving started`).
- En `INFO persistence` deben aparecer `aof_enabled:1` y `rdb_last_bgsave_status:ok`.
- `INFO keyspace` muestra cuántas claves hay y cuántas caducan (`db0:keys=7,expires=1`).

Comprobamos los ficheros y reiniciamos el servicio:

```bash
sudo ls -l /var/lib/redis/ /var/lib/redis/appendonlydir/
sudo systemctl restart redis-server
```

Volvemos a conectarnos desde el cliente como `ruben`:

```text
GET app:visitas
HGETALL app:producto:1
```

Los datos siguen ahí: Redis los ha recargado desde el disco al arrancar.

## 9. Información y supervisión

Como `admin`:

```text
INFO server
INFO memory
INFO clients
```

- `INFO server`: versión (`redis_version`), puerto, tiempo encendido.
- `INFO memory`: memoria usada (`used_memory_human`).
- `INFO clients`: clientes conectados (`connected_clients`).

Para ver en directo todos los comandos que llegan al servidor (útil para depurar una aplicación), `MONITOR`; se sale con `Ctrl+C`.

## Resumen de comandos

| Tipo | Escribir | Leer | Otros |
|---|---|---|---|
| String | `SET`, `INCR` | `GET` | `EXPIRE`, `TTL` |
| Hash | `HSET`, `HINCRBY` | `HGET`, `HGETALL` | `HDEL` |
| List | `RPUSH`, `LPUSH` | `LRANGE`, `LLEN` | `LPOP`, `RPOP` |
| Set | `SADD` | `SMEMBERS`, `SISMEMBER` | `SINTER`, `SREM` |
| Sorted set | `ZADD`, `ZINCRBY` | `ZRANGE`, `ZREVRANGE`, `ZSCORE` | `ZREM` |
| Claves | `DEL` | `SCAN`, `EXISTS`, `TYPE` | `DBSIZE` |
| Usuarios | `ACL SETUSER`, `ACL SAVE` | `ACL LIST`, `ACL WHOAMI` | `ACL DELUSER` |

## Problemas frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| `NOAUTH Authentication required` | Conexión sin usuario | Añadir `--user ... --askpass` |
| `WRONGPASS invalid username-password pair` | Usuario o contraseña incorrectos | Revisar `/etc/redis/users.acl` (recuerda el `>` delante de la contraseña) |
| `Could not connect to Redis at 192.168.122.30:6379: Connection refused` | No escucha en la red o cortafuegos | `sudo ss -tlnp \| grep 6379` y `sudo ufw status` en el servidor |
| `NOPERM` | El usuario no tiene permiso para ese comando o esa clave | Es lo esperado en las pruebas; si no, revisar su línea en `users.acl` |
| El servicio no arranca tras editar la configuración | Error en `redis.conf` o `users.acl` sin permisos | `sudo tail -n 30 /var/log/redis/redis-server.log`; comprobar `chown redis:redis` del paso 3 |
| `WRONGTYPE Operation against a key holding the wrong kind of value` | Comando de un tipo sobre una clave de otro (p. ej. `GET` sobre un hash) | Ver el tipo con `TYPE clave` y usar su comando |

## Fuentes

- [Documentación de Redis: ACL](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/)
- [Documentación de Redis: persistencia](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/)
- [Documentación de Redis: tipos de datos](https://redis.io/docs/latest/develop/data-types/)
- [Paquete redis en Debian](https://tracker.debian.org/pkg/redis)
