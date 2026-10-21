# Instalación de MongoDB 8.0 y cliente mongosh remoto en Debian 13 (Por Rubén)

Guía para instalar MongoDB Community 8.0 en Debian 13, crear usuarios, activar la autenticación, permitir el acceso desde la red local y trabajar desde otra máquina con `mongosh`: crear una base de datos con tres colecciones, insertar documentos y consultarlos.

## Entorno

| Máquina | Nombre | IP |
|---|---|---|
| Servidor | `bdserver.ruben.asir` | 192.168.122.30 |
| Cliente | `cliente.ruben.asir` | 192.168.122.50 |

- Sistema: Debian 13 (Trixie) en las dos máquinas.
- MongoDB Community 8.0 y `mongosh` (cliente). Puerto 27017.
- Red local: 192.168.122.0/24.

Cambia las IPs por las tuyas.

!!! warning "La CPU de la máquina virtual debe tener AVX"
    MongoDB 8.0 solo funciona en procesadores con instrucciones AVX. En una máquina virtual de KVM/virt-manager, en *Detalles* → *CPUs*, marca **Copiar configuración de la CPU del anfitrión** (`host-passthrough`). Puedes comprobarlo dentro de la VM con `grep -c avx /proc/cpuinfo`: debe dar un número mayor que 0.

## Conceptos básicos

MongoDB es una base de datos **documental** (NoSQL). En lugar de tablas con filas, guarda **documentos** con formato parecido a JSON:

| MariaDB / PostgreSQL | MongoDB |
|---|---|
| Base de datos | Base de datos |
| Tabla | Colección |
| Fila | Documento |
| Columna | Campo |
| `PRIMARY KEY` | Campo `_id` (obligatorio y único) |

Los documentos de una misma colección no tienen por qué tener los mismos campos, y un campo puede contener una lista u otro documento.

## 1. Instalar MongoDB desde el repositorio oficial

MongoDB no está en los repositorios de Debian, así que añadimos el de MongoDB. Para Debian 13 se usan los paquetes de **Debian 12 (bookworm)**: MongoDB todavía no publica el servidor para Trixie y los de bookworm funcionan sin problemas.

En el **servidor**:

```bash
sudo apt update
sudo apt install -y gnupg curl
```

Descargamos la clave con la que MongoDB firma sus paquetes y la convertimos al formato de apt:

```bash
curl -fsSL https://www.mongodb.org/static/pgp/server-8.0.asc | \
  sudo gpg -o /usr/share/keyrings/mongodb-server-8.0.gpg --dearmor
```

Añadimos el repositorio. `signed-by` indica que solo se aceptan paquetes firmados con esa clave:

```bash
echo "deb [ arch=amd64 signed-by=/usr/share/keyrings/mongodb-server-8.0.gpg ] https://repo.mongodb.org/apt/debian bookworm/mongodb-org/8.0 main" | \
  sudo tee /etc/apt/sources.list.d/mongodb-org-8.0.list
```

Instalamos. El paquete `mongodb-org` incluye el servidor (`mongod`), el cliente (`mongosh`) y herramientas de copias (`mongodump`, `mongorestore`):

```bash
sudo apt update
sudo apt install -y mongodb-org
```

Arrancamos el servicio y lo activamos para cada inicio (MongoDB no se arranca solo al instalarlo):

```bash
sudo systemctl enable --now mongod
sudo systemctl status mongod --no-pager
mongod --version
```

Debe aparecer `active (running)` y `db version v8.0.x`. Si el estado es `failed` con `code=dumped, signal=ILL` (instrucción no válida), la CPU no tiene AVX (ver el aviso de arriba).

Ficheros importantes:

| Qué | Dónde |
|---|---|
| Configuración | `/etc/mongod.conf` |
| Datos | `/var/lib/mongodb/` |
| Registro (log) | `/var/log/mongodb/mongod.log` |

## 2. Crear los usuarios

Recién instalado, MongoDB **no pide contraseña** y solo escucha en `127.0.0.1`. Creamos los usuarios **antes** de abrirlo a la red.

En MongoDB cada usuario se crea **dentro de una base de datos** (su *base de datos de autenticación*) y recibe **roles**. Crearemos:

| Usuario | Se crea en | Rol | Qué puede hacer |
|---|---|---|---|
| `admin` | `admin` | `root` | Todo |
| `ruben` | `gimnasio` | `readWrite` sobre `gimnasio` | Leer y escribir en `gimnasio` |
| `consulta` | `gimnasio` | `read` sobre `gimnasio` | Solo leer en `gimnasio` |

Entramos en la consola de MongoDB:

```bash
mongosh
```

Dentro de `mongosh` creamos el administrador. `passwordPrompt()` pide la contraseña sin mostrarla, así no queda escrita en el historial:

```javascript
use admin
db.createUser({
  user: "admin",
  pwd: passwordPrompt(),
  roles: [ { role: "root", db: "admin" } ]
})
```

Y los dos usuarios de la base de datos `gimnasio`:

```javascript
use gimnasio
db.createUser({
  user: "ruben",
  pwd: passwordPrompt(),
  roles: [ { role: "readWrite", db: "gimnasio" } ]
})
db.createUser({
  user: "consulta",
  pwd: passwordPrompt(),
  roles: [ { role: "read", db: "gimnasio" } ]
})
db.getUsers()
exit
```

Cada `createUser` debe responder `{ ok: 1 }`. `use gimnasio` cambia a esa base de datos aunque todavía no exista: MongoDB la crea cuando se guarda el primer documento.

## 3. Activar la autenticación y el acceso remoto

Editamos `/etc/mongod.conf`. Es un fichero **YAML**: la sangría se hace con **espacios** (nunca tabuladores) y define qué opción pertenece a qué sección. Hacemos una copia y lo abrimos:

```bash
sudo cp /etc/mongod.conf /etc/mongod.conf.original
sudo nano /etc/mongod.conf
```

Buscamos la sección `net` y cambiamos `bindIp`:

```yaml
net:
  port: 27017
  bindIp: 127.0.0.1,192.168.122.30
```

Buscamos la línea `#security:`, le quitamos la `#` y añadimos debajo `authorization` con **dos espacios** delante:

```yaml
security:
  authorization: enabled
```

- `bindIp`: direcciones en las que escucha MongoDB: local y la IP de la red. Se separan con comas, sin espacios.
- `authorization: enabled`: obliga a identificarse con usuario y contraseña. Sin esto, cualquiera que llegue al puerto podría leer y borrar todo.

Guardamos (`Ctrl+O`, `Enter`, `Ctrl+X`), reiniciamos y comprobamos:

```bash
sudo systemctl restart mongod
sudo systemctl status mongod --no-pager
sudo ss -tlnp | grep 27017
```

`ss` debe mostrar `127.0.0.1:27017` y `192.168.122.30:27017`. Si el servicio no arranca, casi siempre es un error de sangría en el YAML: revisa `sudo tail -n 20 /var/log/mongodb/mongod.log`.

Comprobamos que ya **no se puede leer sin identificarse**:

```bash
mongosh --quiet --eval 'db.getSiblingDB("gimnasio").getCollectionNames()'
```

Debe dar `MongoServerError: Command listCollections requires authentication`.

Y que el administrador sí entra:

```bash
mongosh -u admin -p --authenticationDatabase admin --eval 'db.runCommand({ connectionStatus: 1 })'
```

- `-u` / `-p`: usuario y contraseña (al dejar `-p` vacío la pide por teclado).
- `--authenticationDatabase admin`: base de datos donde se creó el usuario.

Si el servidor tiene cortafuegos `ufw`, abrimos el puerto solo para la red local:

```bash
sudo ufw allow from 192.168.122.0/24 to any port 27017 proto tcp
```

## 4. Instalar el cliente remoto (mongosh)

En la máquina **cliente** instalamos solo `mongosh`, sin el servidor. Añadimos el mismo repositorio que en el paso 1:

```bash
sudo apt update
sudo apt install -y gnupg curl netcat-openbsd
curl -fsSL https://www.mongodb.org/static/pgp/server-8.0.asc | \
  sudo gpg -o /usr/share/keyrings/mongodb-server-8.0.gpg --dearmor
echo "deb [ arch=amd64 signed-by=/usr/share/keyrings/mongodb-server-8.0.gpg ] https://repo.mongodb.org/apt/debian bookworm/mongodb-org/8.0 main" | \
  sudo tee /etc/apt/sources.list.d/mongodb-org-8.0.list
sudo apt update
sudo apt install -y mongodb-mongosh
mongosh --version
```

Comprobamos que llegamos al puerto y nos conectamos como `ruben`:

```bash
nc -zv 192.168.122.30 27017
mongosh "mongodb://192.168.122.30:27017/gimnasio?authSource=gimnasio" -u ruben
```

La **cadena de conexión** (`mongodb://...`) tiene estas partes:

| Parte | Significado |
|---|---|
| `192.168.122.30:27017` | Servidor y puerto |
| `/gimnasio` | Base de datos con la que empezamos a trabajar |
| `?authSource=gimnasio` | Base de datos donde se creó el usuario |

Ya dentro, comprobamos con qué usuario y roles estamos conectados:

```javascript
db.runCommand({ connectionStatus: 1 })
```

Debe mostrar `user: 'ruben'` y `role: 'readWrite', db: 'gimnasio'`.

## 5. Crear las colecciones y los datos

Desde el **cliente**, conectados como `ruben`, creamos las tres colecciones de un gimnasio: socios, clases y reservas. Como en MongoDB las colecciones se crean al insertar el primer documento, basta con insertar. Ponemos nosotros el `_id` (1, 2, 3...) para que las reservas puedan hacer referencia a socios y clases fácilmente.

```javascript
db.socios.insertMany([
  { _id: 1, nombre: "Lucia Marquez",  email: "lucia@ejemplo.es",  edad: 27, cuota: "mensual", activo: true },
  { _id: 2, nombre: "Javier Ortega",  email: "javier@ejemplo.es", edad: 34, cuota: "anual",   activo: true },
  { _id: 3, nombre: "Carmen Vidal",   email: "carmen@ejemplo.es", edad: 45, cuota: "mensual", activo: false },
  { _id: 4, nombre: "Sergio Navarro", email: "sergio@ejemplo.es", edad: 22, cuota: "anual",   activo: true,
    telefono: "600123456" }
])

db.clases.insertMany([
  { _id: 1, nombre: "Spinning", monitor: "Ana",   plazas: 20, dias: ["lunes", "miercoles"] },
  { _id: 2, nombre: "Yoga",     monitor: "Pablo", plazas: 15, dias: ["martes", "jueves"] },
  { _id: 3, nombre: "Crossfit", monitor: "Ana",   plazas: 12, dias: ["viernes"] }
])

db.reservas.insertMany([
  { socio_id: 1, clase_id: 1, fecha: new Date("2026-10-26T18:00:00Z") },
  { socio_id: 2, clase_id: 2, fecha: new Date("2026-10-27T19:00:00Z") },
  { socio_id: 4, clase_id: 3, fecha: new Date("2026-10-30T17:00:00Z") },
  { socio_id: 1, clase_id: 2, fecha: new Date("2026-10-29T19:00:00Z") }
])

show collections
```

Fíjate en dos cosas que no se pueden hacer en una tabla SQL:

- El socio 4 tiene un campo `telefono` que los demás no tienen.
- El campo `dias` de las clases es una **lista**.

Las reservas no llevan `_id`: MongoDB genera uno automáticamente (`ObjectId(...)`).

## 6. Consultas

### 6.1 Consultas sencillas

```javascript
// Todos los socios
db.socios.find()

// Solo los activos
db.socios.find({ activo: true })

// Mayores de 30 años ($gt = mayor que)
db.socios.find({ edad: { $gt: 30 } })

// Clases que hay los martes (busca dentro de la lista "dias")
db.clases.find({ dias: "martes" })

// Solo nombre y email, sin _id (proyección)
db.socios.find({}, { nombre: 1, email: 1, _id: 0 })

// Ordenados por edad de mayor a menor, solo los 2 primeros
db.socios.find().sort({ edad: -1 }).limit(2)

// Cuántos socios tienen cuota anual
db.socios.countDocuments({ cuota: "anual" })
```

Operadores de comparación más usados:

| Operador | Significado |
|---|---|
| `$eq` / `$ne` | Igual / distinto |
| `$gt` / `$gte` | Mayor / mayor o igual |
| `$lt` / `$lte` | Menor / menor o igual |
| `$in` | Está en una lista de valores |

### 6.2 Modificar y borrar

```javascript
// Dar de alta otra vez a Carmen
db.socios.updateOne({ _id: 3 }, { $set: { activo: true } })

// Añadir el sábado a Yoga ($push añade a una lista)
db.clases.updateOne({ _id: 2 }, { $push: { dias: "sabado" } })

// Borrar una reserva
db.reservas.deleteOne({ socio_id: 1, clase_id: 2 })
```

Cada operación responde con `matchedCount`, `modifiedCount` o `deletedCount`, que indican cuántos documentos ha encontrado y cambiado.

### 6.3 Unir colecciones con aggregate

Para ver cada reserva con el **nombre** del socio y de la clase (lo que en SQL sería un `JOIN`), usamos una **tubería de agregación**: una lista de etapas que se aplican en orden.

```javascript
db.reservas.aggregate([
  { $lookup: { from: "socios", localField: "socio_id", foreignField: "_id", as: "socio" } },
  { $lookup: { from: "clases", localField: "clase_id", foreignField: "_id", as: "clase" } },
  { $unwind: "$socio" },
  { $unwind: "$clase" },
  { $project: { _id: 0, socio: "$socio.nombre", clase: "$clase.nombre", fecha: 1 } },
  { $sort: { fecha: 1 } }
])
```

- `$lookup`: busca en otra colección los documentos relacionados y los añade como lista.
- `$unwind`: convierte esa lista de un elemento en un documento normal.
- `$project`: elige qué campos mostrar.
- `$sort`: ordena por fecha.

Y cuántas reservas tiene cada clase (como un `GROUP BY`):

```javascript
db.reservas.aggregate([
  { $group: { _id: "$clase_id", total: { $sum: 1 } } },
  { $sort: { total: -1 } }
])
```

### 6.4 Índices

Un índice hace que las búsquedas por un campo sean rápidas y puede impedir duplicados. Creamos uno **único** sobre el email de los socios:

```javascript
db.socios.createIndex({ email: 1 }, { unique: true })
db.socios.getIndexes()
db.socios.insertOne({ _id: 5, nombre: "Copia", email: "lucia@ejemplo.es" })
```

El último `insertOne` debe fallar con `E11000 duplicate key error`: ya existe un socio con ese email.

## 7. Prueba de permisos

Seguimos conectados como `ruben`. Intentamos usar otra base de datos:

```javascript
use admin
db.getUsers()
```

Debe fallar con `MongoServerError: not authorized on admin`: `ruben` solo tiene permisos en `gimnasio`. Salimos con `exit`.

Ahora nos conectamos como `consulta`, que solo puede leer:

```bash
mongosh "mongodb://192.168.122.30:27017/gimnasio?authSource=gimnasio" -u consulta
```

```javascript
db.socios.find({}, { nombre: 1, _id: 0 })
db.socios.insertOne({ _id: 6, nombre: "No deberia entrar" })
```

La consulta funciona y el `insertOne` falla con `not authorized on gimnasio to execute command { insert: ...`.

## Problemas frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| `mongod` en estado `failed` con `signal=ILL` | La CPU de la VM no tiene AVX | Copiar la CPU del anfitrión en virt-manager (`host-passthrough`) |
| `E: Unable to locate package mongodb-org` | Repositorio mal escrito o con `trixie` | Usar `bookworm/mongodb-org/8.0` en el `.list` |
| `mongod` no arranca tras editar la configuración | Error de sangría en el YAML | Revisar `/etc/mongod.conf` (espacios, no tabuladores) y `/var/log/mongodb/mongod.log` |
| `MongoServerSelectionError: connect ECONNREFUSED` | No escucha en la red o cortafuegos | `sudo ss -tlnp \| grep 27017` y `sudo ufw status` en el servidor |
| `Authentication failed` | Contraseña incorrecta o `authSource` equivocado | `ruben` y `consulta` usan `authSource=gimnasio`; `admin`, `authSource=admin` |
| `not authorized on ...` | El rol del usuario no lo permite | Es lo esperado en las pruebas; ver roles con `db.getUsers()` como `admin` |

## Fuentes

- [MongoDB: instalar MongoDB Community en Debian](https://www.mongodb.com/docs/manual/tutorial/install-mongodb-on-debian/)
- [MongoDB: activar el control de acceso](https://www.mongodb.com/docs/manual/tutorial/enable-authentication/)
- [MongoDB: roles integrados](https://www.mongodb.com/docs/manual/reference/built-in-roles/)
- [MongoDB: $lookup](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/)
- [Computingforgeeks: MongoDB en Debian 13 con los paquetes de bookworm](https://computingforgeeks.com/install-mongodb-on-debian/)
