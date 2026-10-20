# Guía de Instalación, Uso Básico y Replicación de Apache CouchDB en Debian 13

Esta guía cubre qué es CouchDB y cómo funciona, su instalación en Debian 13 (trixie), la configuración del acceso remoto y la autenticación, la gestión de usuarios, el uso básico (bases de datos, documentos y consultas) mediante la **API REST sobre HTTP** y, como parte principal, la **replicación maestro-maestro**: cada cliente tiene su propia base de datos local, que se sincroniza en ambos sentidos con los servidores del propietario del servicio.

## 1. Qué es CouchDB y cómo funciona

Apache CouchDB es una base de datos **NoSQL orientada a documentos**. Cada registro es un **documento JSON** con un identificador (`_id`) y se guarda dentro de una **base de datos** (equivalente a una colección, no a un servidor de bases de datos). Toda la interacción se hace mediante **HTTP**: crear, leer, modificar y borrar son peticiones `PUT`, `GET`, `POST` y `DELETE` a una URL.

**Cosas a tener en cuenta sobre CouchDB:**

- No hay esquema ni tablas: documentos de la misma base de datos pueden tener campos distintos.
- No existen relaciones (`JOIN`): la información relacionada se suele duplicar o incrustar dentro del propio documento.
- **Control de versiones multiversión (MVCC):** cada documento tiene un campo `_rev` (revisión). Para modificar o borrar un documento **hay que indicar la revisión que se conoce**. Si otro cliente lo ha cambiado antes, CouchDB responde `409 Conflict`. No hay bloqueos.
- Los datos **nunca se sobrescriben**: cada cambio añade una nueva revisión (el fichero solo se escribe al final, lo que lo hace muy robusto ante apagados). Las revisiones antiguas se eliminan con la compactación.
- No hay transacciones entre varios documentos: la unidad atómica es **un documento**.
- Las consultas rápidas se hacen por `_id`, por **vistas** (map/reduce) o por **índices de Mango**. Consultar por campos sin índice funciona pero recorre todos los documentos.
- **Su característica más importante es la replicación:** es incremental, bidireccional, tolera cortes de red y cualquiera de los dos extremos puede aceptar escrituras (maestro-maestro). Se desarrolla en el apartado 6.

### 1.1. Comparación con MongoDB

| | MongoDB | CouchDB |
|---|---|---|
| Modelo | Documentos JSON (almacenados como BSON) | Documentos JSON |
| Acceso | Driver con protocolo binario (puerto 27017) | HTTP REST (puerto 5984) |
| Consultas | Lenguaje de consulta y *aggregation pipeline* muy completos | Mango, vistas map/reduce e índices |
| Transacciones | Multidocumento (ACID) | Solo a nivel de un documento |
| Replicación | *Replica set*: un único primario acepta escrituras | Maestro-maestro: cualquier copia acepta escrituras |
| Clientes sin conexión | No es su uso previsto | Diseñado para ello (bases de datos locales que sincronizan) |
| Conflictos | No hay, al existir un único primario | Se conservan las dos revisiones y se elige un ganador determinista |
| Usuarios | Roles con permisos granulares por base de datos y colección | Usuarios en la base `_users`, permisos por base de datos |

### 1.2. Formas de interactuar con CouchDB

Como la API es HTTP, existen muchas formas de usarlo:

- **API REST con `curl`**: la más simple y universal, y la que se explica en esta guía.
- **Fauxton**: interfaz web incluida en el servidor, en `http://TU_IP_SERVIDOR:5984/_utils`. Permite crear bases de datos, editar documentos, gestionar permisos y configurar replicaciones sin escribir comandos.
- **Librerías cliente** de cada lenguaje: `nano` (Node.js), `CouchDB.NET`, `couchdb-python`, y muchas otras, que son envoltorios de la API HTTP.
- **PouchDB**: base de datos JavaScript que funciona **en el navegador, en aplicaciones móviles o en Node**, y que sincroniza con CouchDB de forma nativa. Es la opción habitual para el modelo "cada cliente con su base local" en aplicaciones web y móviles.
- Cualquier cliente HTTP (Postman, `wget`, un `fetch` en JavaScript...).

## 2. Instalación

CouchDB no está en los repositorios de Debian, por lo que se añade el repositorio oficial de Apache.

### 2.1. Añadir el repositorio oficial

```
sudo apt update
sudo apt install -y curl apt-transport-https gnupg
curl -fsSL https://couchdb.apache.org/repo/keys.asc | gpg --dearmor | sudo tee /usr/share/keyrings/couchdb-archive-keyring.gpg > /dev/null
source /etc/os-release
echo "deb [signed-by=/usr/share/keyrings/couchdb-archive-keyring.gpg] https://apache.jfrog.io/artifactory/couchdb-deb/ ${VERSION_CODENAME} main" | sudo tee /etc/apt/sources.list.d/couchdb.list
sudo apt update
```

> Si el repositorio todavía no publicase paquetes para `trixie` (`apt update` mostraría un error 404), se puede sustituir `${VERSION_CODENAME}` por `bookworm` en el fichero `/etc/apt/sources.list.d/couchdb.list`. Comprueba el repositorio con `apt policy couchdb`.

### 2.2. Instalar CouchDB (modo standalone)

El instalador pregunta por el modo (un solo nodo o clúster), la dirección de escucha y la contraseña del administrador. Para no depender del asistente se pueden responder de antemano con `debconf`. Usaremos **standalone** (un solo nodo) y de momento solo `127.0.0.1`:

```
echo "couchdb couchdb/mode select standalone
couchdb couchdb/mode seen true
couchdb couchdb/bindaddress string 127.0.0.1
couchdb couchdb/bindaddress seen true
couchdb couchdb/adminpass password <PASSWORD_ADMIN>
couchdb couchdb/adminpass seen true
couchdb couchdb/adminpass_again password <PASSWORD_ADMIN>
couchdb couchdb/adminpass_again seen true" | sudo debconf-set-selections
sudo DEBIAN_FRONTEND=noninteractive apt install -y couchdb
```

Si se prefiere el asistente interactivo basta con `sudo apt install -y couchdb`. El usuario administrador se llama `admin` por defecto; en esta guía se supone que se ha creado uno llamado `couchadmin` según el apartado 4.1, por lo que en los ejemplos se usa `couchadmin`. Si te quedas con `admin`, sustitúyelo en los comandos.

Rutas importantes:

- Programa y configuración: `/opt/couchdb/`
- Configuración propia: `/opt/couchdb/etc/local.ini` y `/opt/couchdb/etc/local.d/*.ini`
- Datos: `/opt/couchdb/data/`
- Puerto: `5984` (HTTP)

### 2.3. Comprobación del servicio

```bash
sudo systemctl status couchdb --no-pager
curl http://127.0.0.1:5984/
```

```
{"couchdb":"Welcome","version":"3.5.3","git_sha":"7a1f97558","uuid":"3dac2d12a9969e0f5994f68ef0130b47","features":["access-ready","partitioned","pluggable-storage-engines","reshard","scheduler"],"vendor":{"name":"The Apache Software Foundation"}}
```

Comprobamos que la autenticación del administrador funciona y que existen las bases de datos del sistema (`_users`, `_replicator`):

```
curl -u couchadmin http://127.0.0.1:5984/_all_dbs
```

```
["_replicator","_users"]
```

> `curl -u usuario` sin contraseña la pide interactivamente, así se evita escribirla en el historial de la terminal. En los ejemplos siguientes se usa `-u couchadmin:<PASSWORD_ADMIN>` para simplificar, pero se puede quitar la contraseña.

Si `_users` o `_replicator` no existieran, se crean manualmente:

```
curl -X PUT -u couchadmin:<PASSWORD_ADMIN> http://127.0.0.1:5984/_users
curl -X PUT -u couchadmin:<PASSWORD_ADMIN> http://127.0.0.1:5984/_replicator
```

## 3. Configuración y acceso remoto

Los ficheros de `/opt/couchdb/etc/local.d/` se leen en orden alfabético y el último valor gana, por lo que creamos un fichero propio `99-custom.ini` en lugar de editar los de la instalación.

Para abrir el servicio a la red y **obligar a autenticarse en todas las peticiones**:

```
sudo tee /opt/couchdb/etc/local.d/99-custom.ini > /dev/null << 'EOF'
[chttpd]
bind_address = 0.0.0.0
require_valid_user = true
EOF
sudo chown couchdb:couchdb /opt/couchdb/etc/local.d/99-custom.ini
sudo systemctl restart couchdb
```

- `bind_address`: interfaz en la que atiende HTTP. `0.0.0.0` = todas. También se puede indicar la IP concreta del servidor.
- `require_valid_user = true`: sin esto, ciertas rutas (como la página de bienvenida) son públicas.

Verificamos desde el equipo cliente:

```
nc -zv TU_IP_SERVIDOR 5984
curl http://TU_IP_SERVIDOR:5984/
curl -u couchadmin:<PASSWORD_ADMIN> http://TU_IP_SERVIDOR:5984/
```

```
Connection to 192.168.122.163 5984 port [tcp/*] succeeded!
{"error":"unauthorized","reason":"Authentication required."}
{"couchdb":"Welcome","version":"3.5.3","git_sha":"7a1f97558","uuid":"3dac2d12a9969e0f5994f68ef0130b47","features":["access-ready","partitioned","pluggable-storage-engines","reshard","scheduler"],"vendor":{"name":"The Apache Software Foundation"}}
```

> HTTP plano **no cifra** usuarios, contraseñas ni datos. Si el servidor es accesible desde Internet debe ponerse delante un proxy inverso con HTTPS (nginx, Caddy, HAProxy...). CouchDB también soporta HTTPS de forma nativa, pero lo habitual es el proxy.

## 4. Gestión de usuarios y permisos

En CouchDB hay dos niveles:

- **Administradores**: definidos en la configuración (sección `[admins]`). Pueden hacerlo todo.
- **Usuarios normales**: son documentos de la base de datos `_users`. Su acceso a cada base de datos se define con su objeto `_security`.

### 4.1. Administradores

Se crean mediante la API de configuración. El cuerpo de la petición es una **cadena JSON** con la contraseña; CouchDB la guarda **con hash** en `local.ini`:

```
curl -X PUT -u admin:<PASSWORD_ACTUAL> http://127.0.0.1:5984/_node/_local/_config/admins/couchadmin -d '"<PASSWORD_ADMIN>"'
```

Para eliminar el administrador por defecto una vez creado el nuevo:

```
curl -X DELETE -u couchadmin:<PASSWORD_ADMIN> http://127.0.0.1:5984/_node/_local/_config/admins/admin
```

### 4.2. Crear un usuario normal

Para crear `usuario_prueba` se crea un documento en `_users` con el identificador `org.couchdb.user:<nombre>`. La contraseña se envía en texto, pero CouchDB la guarda con hash:

```
curl -X PUT -u couchadmin:<PASSWORD_ADMIN> http://TU_IP_SERVIDOR:5984/_users/org.couchdb.user:usuario_prueba -H 'Content-Type: application/json' -d '{"name":"usuario_prueba","password":"<PASSWORD_APP>","roles":[],"type":"user"}'
```

```
{"ok":true,"id":"org.couchdb.user:usuario_prueba","rev":"1-a5c88ac6dd045a2970eb622766164555"}
```

Listar usuarios (solo administradores):

```
curl -u couchadmin:<PASSWORD_ADMIN> 'http://TU_IP_SERVIDOR:5984/_users/_all_docs'
```

### 4.3. Cambiar contraseña y eliminar un usuario

Como cualquier documento, requiere conocer la `_rev` actual:

```
curl -u couchadmin:<PASSWORD_ADMIN> http://TU_IP_SERVIDOR:5984/_users/org.couchdb.user:usuario_prueba
```

Con la `_rev` obtenida (por ejemplo `1-abc...`):

```
curl -X PUT -u couchadmin:<PASSWORD_ADMIN> http://TU_IP_SERVIDOR:5984/_users/org.couchdb.user:usuario_prueba -H 'Content-Type: application/json' -d '{"_rev":"1-abc...","name":"usuario_prueba","password":"<NUEVA_PASSWORD>","roles":[],"type":"user"}'
curl -X DELETE -u couchadmin:<PASSWORD_ADMIN> 'http://TU_IP_SERVIDOR:5984/_users/org.couchdb.user:usuario_temporal?rev=<REV>'
```

### 4.4. Permisos sobre una base de datos (`_security`)

Cada base de datos tiene dos listas: **admins** (pueden modificar permisos y *design documents*) y **members** (pueden leer y escribir documentos). **Si `members` está vacío, cualquier usuario autenticado puede leer y escribir.** En cuanto se añade algún nombre o rol, solo ellos pueden acceder.

Primero se crea la base de datos de pruebas:

```
curl -X PUT -u couchadmin:<PASSWORD_ADMIN> http://TU_IP_SERVIDOR:5984/couch-pruebas
```

Y se concede acceso a `usuario_prueba`:

```
curl -X PUT -u couchadmin:<PASSWORD_ADMIN> http://TU_IP_SERVIDOR:5984/couch-pruebas/_security -H 'Content-Type: application/json' -d '{"admins":{"names":[],"roles":[]},"members":{"names":["usuario_prueba"],"roles":[]}}'
curl -u couchadmin:<PASSWORD_ADMIN> http://TU_IP_SERVIDOR:5984/couch-pruebas/_security
```

```
{"admins":{"names":[],"roles":[]},"members":{"names":["usuario_prueba"],"roles":[]}}
```

Para acceder con el usuario normal ya no se usa `couchadmin`. Comprobación de que ve su base de datos y de que no puede crear otras:

```
curl -u usuario_prueba:<PASSWORD_APP> http://TU_IP_SERVIDOR:5984/couch-pruebas
curl -X PUT -u usuario_prueba:<PASSWORD_APP> http://TU_IP_SERVIDOR:5984/otra_bd
```

```
{"instance_start_time":"1792503271","db_name":"couch-pruebas","purge_seq":"0-g1AAAABXeJzLYWBgYMpgTmEQTM4vTc5ISXIwNDLXMwBCwxyQVB4LkGRoAFL_gSArkQGP2kSGpHqIoiwAtOgYRA","update_seq":"2-g1AAAACbeJzLYWBgYMpgTmEQTM4vTc5ISXIwNDLXMwBCwxyQVB4LkGRoAFL_gSArgzmRMRcowG5mmmxiZJmITR8e0xIZkupRjDEyNkxKS0zCpiELAOLeKHc","sizes":{"file":24892,"external":0,"active":0},"props":{},"doc_del_count":0,"doc_count":0,"disk_format_version":8,"compact_running":false,"cluster":{"q":2,"n":1,"w":1,"r":1}}
{"error":"unauthorized","reason":"You are not a server admin."}
```

## 5. Uso básico mediante la API REST

A partir de aquí se trabaja con el usuario normal sobre la base de datos `couch-pruebas`. Para abreviar se define una variable (la contraseña en la variable queda en el historial; válido solo para pruebas):

```
DB=http://usuario_prueba:<PASSWORD_APP>@TU_IP_SERVIDOR:5984/couch-pruebas
```

> Para que la salida sea legible se puede añadir `| jq` (`sudo apt install -y jq`).

### 5.1. Inserción de documentos

Hay dos formas: indicando nosotros el `_id` con `PUT`, o dejando que CouchDB genere uno con `POST`.

```
curl -X PUT $DB/1 -H 'Content-Type: application/json' -d '{"nombre":"Juan Pérez","email":"juan.perez@example.com","edad":30,"activo":true,"fecha_registro":"2026-10-08T19:18:48Z"}'
```

```
{"ok":true,"id":"1","rev":"1-64534bef6c0357f744b968b86419ac79"}
```

Inserción múltiple en una sola petición con `_bulk_docs`:

```
curl -X POST $DB/_bulk_docs -H 'Content-Type: application/json' -d '{"docs":[{"_id":"2","nombre":"Ana Gómez","email":"ana.gomez@example.com","edad":25,"activo":true},{"_id":"3","nombre":"Carlos Ruiz","email":"carlos.ruiz@example.com","edad":40,"activo":false}]}'
```

### 5.2. Lectura de documentos

```
curl $DB/1
```

```
{"_id":"1","_rev":"1-64534bef6c0357f744b968b86419ac79","nombre":"Juan Pérez","email":"juan.perez@example.com","edad":30,"activo":true,"fecha_registro":"2026-10-08T19:18:48Z"}
```

Listar todos los documentos de la base de datos (equivalente a `SELECT *`):

```
curl "$DB/_all_docs?include_docs=true"
```

### 5.3. Modificación y borrado

Para modificar hay que enviar **el documento completo** con la `_rev` vigente (no existe actualización parcial). Si la revisión no coincide: `409 Conflict`.

```
curl -X PUT $DB/1 -H 'Content-Type: application/json' -d '{"_rev":"1-9f1c...","nombre":"Juan Pérez","email":"juan.perez@example.com","edad":31,"activo":true}'
```

```
{"ok":true,"id":"1","rev":"2-0be51d15faa0ffff71a9e0820d1dd89d"}
```

Borrado (genera una "lápida" que también se replica):

```
curl -X DELETE "$DB/3?rev=<REV_ACTUAL>"
```

### 5.4. Consultas con Mango (`_find`)

Mango permite consultar por campos con una sintaxis JSON (selectores). Sin índice funciona recorriendo todo, así que para tablas grandes se crea un índice sobre los campos usados:

```
curl -X POST $DB/_index -H 'Content-Type: application/json' -d '{"index":{"fields":["edad"]},"name":"idx-edad","type":"json"}'
```

Clientes activos:

```
curl -X POST $DB/_find -H 'Content-Type: application/json' -d '{"selector":{"activo":true}}'
```

Clientes con edad mayor de 28 ordenados por edad descendente (la ordenación necesita un índice sobre ese campo):

```
curl -X POST $DB/_find -H 'Content-Type: application/json' -d '{"selector":{"edad":{"$gt":28}},"sort":[{"edad":"desc"}],"fields":["nombre","edad"]}'
```

```
{"docs":[
{"nombre":"Juan Pérez","edad":31}
],
"bookmark": "g2wAAAACaAJkAA5zdGFydGtleV9kb2NpZG0AAAABMWgCZAAIc3RhcnRrZXlrAAEfag"}
```

> Operadores habituales: `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`, `$in`, `$and`, `$or`, `$regex`.

## 6. Replicación maestro-maestro: bases de datos locales en cada cliente

### 6.1. La idea

En el modelo cliente-servidor clásico cada cliente consulta a un servidor remoto en cada operación: si no hay red, no hay datos. Con CouchDB se invierte el planteamiento:

- El propietario del servicio mantiene uno o varios **servidores centrales** con las bases de datos "oficiales".
- **Cada cliente tiene su propia instancia de CouchDB (o PouchDB) local**, con una copia de los datos que necesita. La aplicación lee y escribe **siempre en local**: es rápido y funciona sin conexión.
- Cuando hay red, las bases de datos **se sincronizan en ambos sentidos**: los cambios del cliente suben al servidor y los del servidor (o de otros clientes) bajan al cliente.

Por eso se llama maestro-maestro (*multi-master*): todas las copias aceptan escrituras y ninguna es solo de lectura. No hace falta que el servidor pueda conectar con el cliente: **es el cliente quien inicia la conexión hacia fuera**, por lo que funciona detrás de NAT o cortafuegos.

### 6.2. Cómo funciona la replicación

- **Unidireccional por definición**: una replicación copia de un *origen* a un *destino*. La **sincronización bidireccional** son simplemente **dos replicaciones**, una en cada sentido.
- **Incremental**: CouchDB usa el *feed de cambios* (`_changes`) de la base de datos y un punto de control (*checkpoint*). Solo transfiere lo que ha cambiado desde la última vez, aunque sea tras semanas sin conexión.
- **Continua o puntual**: con `"continuous": true` la replicación permanece activa y propaga los cambios casi al instante. Si se corta la red, reintenta sola.
- **Tolerante a cortes**: puede interrumpirse en cualquier momento y retoma donde lo dejó.
- **Replica documentos y su historial de revisiones**, incluidos los borrados. Los *design documents* (vistas e índices) también se replican, pero **no** el objeto `_security` ni los usuarios de `_users` (salvo que se replique explícitamente esa base de datos). Por tanto, hay que crear los usuarios y permisos en cada servidor.

### 6.3. Preparación del escenario

- **Servidor central** (`TU_IP_SERVIDOR`): el CouchDB instalado en los apartados anteriores, con la base `couch-pruebas` y el usuario `usuario_prueba` con acceso de `member`.
- **Cliente** (otro equipo): CouchDB instalado con los mismos pasos del apartado 2 en modo standalone y con `bind_address = 127.0.0.1` (solo se usa en local).

En el cliente se crea una base de datos local con el mismo nombre:

```
curl -X PUT -u couchadmin:<PASSWORD_ADMIN> http://127.0.0.1:5984/couch-pruebas
```

### 6.4. Replicación puntual (`_replicate`)

Para probar, una replicación de una sola ejecución. Primero **bajar** los datos del servidor al cliente (*pull*):

```
curl -X POST -u couchadmin:<PASSWORD_ADMIN> http://127.0.0.1:5984/_replicate -H 'Content-Type: application/json' -d '{"source":{"url":"http://TU_IP_SERVIDOR:5984/couch-pruebas","auth":{"basic":{"username":"usuario_prueba","password":"<PASSWORD_APP>"}}},"target":"couch-pruebas"}'
```

```
{"ok":true,"session_id":"e2b3e5ca1320836cd4386ad4b95fd019","source_last_seq":"11-g1AAAACbeJzLYWBgYMpgTmEQTM4vTc5ISXIwNDLXMwBCwxyQVCJDUv3___-zMpgT2XOBAuxGxoZJaYlJ2DTgMSaPBUgyNACp_1DTWMCmmZkmmxhZJmLTlwUANKkogA","replication_id_version":4,"history":[{"session_id":"e2b3e5ca1320836cd4386ad4b95fd019","start_time":"Tue, 20 Oct 2026 13:58:36 GMT","end_time":"Tue, 20 Oct 2026 13:58:37 GMT","start_last_seq":0,"end_last_seq":"11-g1AAAACbeJzLYWBgYMpgTmEQTM4vTc5ISXIwNDLXMwBCwxyQVCJDUv3___-zMpgT2XOBAuxGxoZJaYlJ2DTgMSaPBUgyNACp_1DTWMCmmZkmmxhZJmLTlwUANKkogA","recorded_seq":"11-g1AAAACbeJzLYWBgYMpgTmEQTM4vTc5ISXIwNDLXMwBCwxyQVCJDUv3___-zMpgT2XOBAuxGxoZJaYlJ2DTgMSaPBUgyNACp_1DTWMCmmZkmmxhZJmLTlwUANKkogA","missing_checked":7,"missing_found":7,"docs_read":7,"docs_written":7,"doc_write_failures":0,"bulk_get_docs":6,"bulk_get_attempts":6}]}
```

Comprobamos que los documentos están ya en el CouchDB local:

```
curl -u couchadmin:<PASSWORD_ADMIN> http://127.0.0.1:5984/couch-pruebas/_all_docs
```

Y **subir** al servidor los cambios hechos en local (*push*), invirtiendo origen y destino:

```
curl -X POST -u couchadmin:<PASSWORD_ADMIN> http://127.0.0.1:5984/_replicate -H 'Content-Type: application/json' -d '{"source":"couch-pruebas","target":{"url":"http://TU_IP_SERVIDOR:5984/couch-pruebas","auth":{"basic":{"username":"usuario_prueba","password":"<PASSWORD_APP>"}}}}'
```

> El usuario usado en la URL remota necesita ser `member` de la base remota. Para replicar *design documents* necesita ser `admin` de esa base de datos.

### 6.5. Sincronización permanente: la base de datos `_replicator`

Las replicaciones lanzadas con `_replicate` se pierden al reiniciar. Para que sean **permanentes**, se guardan como documentos en la base `_replicator` del CouchDB **cliente**; CouchDB las arranca solas al iniciarse y las reintenta si falla la red.

Replicación continua de servidor a cliente (*pull*):

```
curl -X PUT -u couchadmin:<PASSWORD_ADMIN> http://127.0.0.1:5984/_replicator/pull_couch-pruebas -H 'Content-Type: application/json' -d '{"source":{"url":"http://TU_IP_SERVIDOR:5984/couch-pruebas","auth":{"basic":{"username":"usuario_prueba","password":"<PASSWORD_APP>"}}},"target":"couch-pruebas","continuous":true}'
```

Replicación continua de cliente a servidor (*push*):

```
curl -X PUT -u couchadmin:<PASSWORD_ADMIN> http://127.0.0.1:5984/_replicator/push_couch-pruebas -H 'Content-Type: application/json' -d '{"source":"couch-pruebas","target":{"url":"http://TU_IP_SERVIDOR:5984/couch-pruebas","auth":{"basic":{"username":"usuario_prueba","password":"<PASSWORD_APP>"}}},"continuous":true}'
```

Con estas dos replicaciones la base de datos local y la del servidor quedan sincronizadas en ambos sentidos de forma continua.

Estado de las replicaciones:

```
curl -u couchadmin:<PASSWORD_ADMIN> http://127.0.0.1:5984/_scheduler/docs
curl -u couchadmin:<PASSWORD_ADMIN> http://127.0.0.1:5984/_scheduler/jobs
```

El campo `state` de cada replicación indica su situación: `running` (activa), `pending` (en cola), `crashing` (está fallando y reintentando) o `failed`.

> Las credenciales quedan guardadas en el documento de `_replicator`. Esa base de datos solo es legible por administradores, pero conviene usar en el cliente un usuario remoto con permisos mínimos (solo `member` de esa base) y HTTPS.

### 6.6. Prueba de sincronización

Con las dos replicaciones activas, se crea un documento en el cliente:

```
curl -X PUT -u couchadmin:<PASSWORD_ADMIN> http://127.0.0.1:5984/couch-pruebas/4 -H 'Content-Type: application/json' -d '{"nombre":"Lucía Torres","email":"lucia.torres@example.com","edad":35,"activo":true}'
```

Y pasados unos segundos se consulta **en el servidor**:

```
curl -u usuario_prueba:<PASSWORD_APP> http://TU_IP_SERVIDOR:5984/couch-pruebas/4
```

El documento aparece. Y a la inversa: lo que se escriba en el servidor llegará a la base local del cliente. Para probar el trabajo **sin conexión**, se bloquea el acceso al servidor (por ejemplo, desconectando la red), se escribe en el cliente, y se restablece: los cambios suben solos.

### 6.7. Replicación selectiva

Normalmente un cliente no necesita todos los datos. Se puede filtrar con un `selector` Mango en el documento de replicación; así cada cliente descarga solo lo que le corresponde (por ejemplo, un campo `tienda`):

```
curl -X PUT -u couchadmin:<PASSWORD_ADMIN> http://127.0.0.1:5984/_replicator/pull_filtrado -H 'Content-Type: application/json' -d '{"source":{"url":"http://TU_IP_SERVIDOR:5984/couch-pruebas","auth":{"basic":{"username":"usuario_prueba","password":"<PASSWORD_APP>"}}},"target":"couch-filtrada","continuous":true,"selector":{"tienda":"cliente01"}}'
```

> El filtrado limita lo que se **descarga**, pero no es un mecanismo de seguridad: si un usuario tiene acceso `member` a la base de datos, puede leerla entera. Para aislar datos por cliente, lo habitual es una base de datos por cliente en el servidor, cada una con su propio usuario.

### 6.8. Conflictos

Al ser maestro-maestro, dos copias pueden modificar el mismo documento a la vez sin conexión. Al sincronizar, CouchDB **no pierde ninguna de las versiones**: elige de forma determinista (igual en todos los nodos) una revisión **ganadora** que es la que se devuelve normalmente, y mantiene la otra como **conflicto**.

Para ver los conflictos de un documento:

```
curl "$DB/1?conflicts=true"
```

```
{"_id":"1","_rev":"3-da9f5f0bb70ab88c62169fd6699743e6","nombre":"Juan Pérez","email":"juan.perez@example.com","edad":33,"activo":true,"_conflicts":["3-5c949e82bc6b9794ed680e0362c0dd17"]}
```

Para resolverlo, la aplicación decide qué contenido es el correcto (el de la revisión ganadora, el de la otra, o una mezcla), guarda ese contenido sobre la revisión ganadora y **elimina la revisión perdedora**:

```
curl -X DELETE "$DB/1?rev=3-bbb..."
```

Recomendaciones de diseño para reducir conflictos:

- Separar los datos que edita cada cliente en **documentos distintos** (por ejemplo, un documento por pedido o por lectura, en lugar de un único documento "cliente" con todo).
- Preferir documentos **de solo añadir** (registros, eventos) a documentos que se modifican con frecuencia.
- Evitar contadores compartidos dentro de un documento: cada cliente debería añadir sus propios documentos y el total se calcula con una vista.

### 6.9. Replicación entre servidores del propietario

Los servidores centrales también pueden replicarse entre sí con el mismo mecanismo (dos documentos en `_replicator`, uno en cada sentido), para disponer de redundancia geográfica o alta disponibilidad. Alternativamente se puede montar un **clúster** de CouchDB (modo `clustered` en la instalación), que fragmenta y replica los datos internamente; los clientes siguen sincronizando contra el clúster como si fuera un único servidor.

## 7. CheatSheed

| Operación | Petición |
|---|---|
| Comprobar servidor | `GET /` |
| Listar bases de datos | `GET /_all_dbs` |
| Crear / borrar base de datos | `PUT /bd` / `DELETE /bd` |
| Crear usuario | `PUT /_users/org.couchdb.user:nombre` |
| Dar permisos a una base de datos | `PUT /bd/_security` |
| Insertar documento | `PUT /bd/id` o `POST /bd` |
| Insertar varios | `POST /bd/_bulk_docs` |
| Leer documento | `GET /bd/id` |
| Listar documentos | `GET /bd/_all_docs?include_docs=true` |
| Modificar documento | `PUT /bd/id` con `_rev` |
| Borrar documento | `DELETE /bd/id?rev=...` |
| Consultar | `POST /bd/_find` |
| Replicación puntual | `POST /_replicate` |
| Replicación permanente | `PUT /_replicator/nombre` |
| Estado de replicaciones | `GET /_scheduler/docs` |