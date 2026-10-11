
# Guía de instalación de MongoDB en Debian 13 (Juan Carlos)

## 1. Instalación

MongoDB no viene en los repositorios de Debian así que añadimos el repositorio oficial de MongoDB. Para Debian 13 los paquetes del servidor están en el componente de bookworm y funcionan correctamente en trixie por eso usaremos `bookworm` en la línea del repositorio aunque nuestro sistema sea Debian 13.

### 1.1 Instalar herramientas previas

```sh
sudo apt update
sudo apt install -y gnupg curl
```

`gnupg` nos permite manejar claves de firma y `curl` descarga ficheros de internet. Las necesitamos para el paso siguiente.

### 1.2 Añadir la clave de firma de MongoDB

```sh
curl -fsSL https://www.mongodb.org/static/pgp/server-8.0.asc | \
  sudo gpg --dearmor -o /usr/share/keyrings/mongodb-server-8.0.gpg
```

Descargamos la clave pública de MongoDB y la guardamos. 

### 1.3 Añadir el repositorio

```sh
sudo tee /etc/apt/sources.list.d/mongodb-org-8.0.list > /dev/null <<'EOF'
deb [ signed-by=/usr/share/keyrings/mongodb-server-8.0.gpg ] https://repo.mongodb.org/apt/debian bookworm/mongodb-org/8.0 main
EOF
```

Le inicamos a `apt` dónde buscar MongoDB 8.0 y con qué clave verificarlo.

### 1.4 Instalar MongoDB

```sh
sudo apt update
sudo apt install -y mongodb-org
```

Actualizamos la lista de paquetes para que `apt` vea el nuevo repositorio e instalamos `mongodb-org` que incluye el servidor (`mongod`), la consola (`mongosh`) y las herramientas de administración.

### 1.5 Arrancar el servicio y activarlo en cada inicio

```sh
sudo systemctl enable --now mongod
sudo systemctl status mongod --no-pager
mongod --version | head -n 1
```

```sh
juanka@oradeb:~$ sudo systemctl enable --now mongod
sudo systemctl status mongod --no-pager
mongod --version | head -n 1
Created symlink '/etc/systemd/system/multi-user.target.wants/mongod.service' → '/usr/lib/systemd/system/mongod.service'.
● mongod.service - MongoDB Database Server
     Loaded: loaded (/usr/lib/systemd/system/mongod.service; enabled; preset: enabled)
     Active: active (running) since Sun 2026-10-11 16:42:37 CEST; 42ms ago
 Invocation: 44fde2512662429d9fa225b179a4f937
       Docs: https://docs.mongodb.org/manual
   Main PID: 2227 (mongod)
     Memory: 7.9M (peak: 8.2M)
        CPU: 16ms
     CGroup: /system.slice/mongod.service
             └─2227 /usr/bin/mongod --config /etc/mongod.conf

oct 11 16:42:37 oradeb.abd.local systemd[1]: Started mongod.service - MongoDB Database Server.
db version v8.0.32
```

- `enable --now` arranca el servicio y hace que se inicie solo cada vez que se enciende la máquina.
- `status` comprueba que está activo.
- `mongod --version` muestra la versión instalada.

## 2. Crear el usuario administrador

Por defecto MongoDB **no pide contraseña** a nadie. Antes de abrirlo a la red creamos un administrador y exigiremos autenticación. Lo hacemos ahora mientras solo escucha en la propia máquina.

```sh
mongosh --quiet <<'EOF'
use admin
db.createUser({
  user: "admin",
  pwd: "admin",
  roles: [ { role: "root", db: "admin" } ]
})
EOF
```

```sh
juanka@oradeb:~$ mongosh --quiet <<'EOF'
use admin
db.createUser({
  user: "admin",
  pwd: "admin",
  roles: [ { role: "root", db: "admin" } ]
})
EOF
test> use admin
switched to db admin
admin> db.createUser({
|   user: "admin",
|   pwd: "admin",
|   roles: [ { role: "root", db: "admin" } ]
| })
{ ok: 1 }
```

- `mongosh` es la consola de MongoDB y `--quiet` oculta los mensajes de bienvenida.
- `use admin` selecciona la base de datos especial donde se guardan los administradores.
- `createUser` crea el usuario `admin` con el rol `root` que tiene control total. Lo usaremos solo para administrar desde el propio servidor.

## 3. Crear la base de datos, el usuario remoto y los datos

En MongoDB las “tablas” se llaman **colecciones** y las “filas” **documentos**. Una base de datos solo existe realmente cuando tiene datos así que la creamos insertando documentos.

### 3.1 Crear las colecciones y poblarlas

```sh
mongosh --quiet <<'EOF'
use prueba_bd

db.clientes.insertMany([
  { _id: 1, nombre: "Ana Lopez",   email: "ana@correo.es",   ciudad: "Sevilla" },
  { _id: 2, nombre: "Luis Perez",  email: "luis@correo.es",  ciudad: "Dos Hermanas" },
  { _id: 3, nombre: "Marta Ruiz",  email: "marta@correo.es", ciudad: "Cadiz" },
  { _id: 4, nombre: "Pablo Gomez", email: "pablo@correo.es", ciudad: "Malaga" }
])

db.productos.insertMany([
  { _id: 1, nombre: "Teclado", precio: 24.90 },
  { _id: 2, nombre: "Raton",   precio: 12.50 },
  { _id: 3, nombre: "Monitor", precio: 149.00 },
  { _id: 4, nombre: "Webcam",  precio: 39.95 }
])

db.pedidos.insertMany([
  { cliente_id: 1, producto_id: 1, cantidad: 1, fecha: new Date() },
  { cliente_id: 1, producto_id: 2, cantidad: 2, fecha: new Date() },
  { cliente_id: 2, producto_id: 3, cantidad: 1, fecha: new Date() },
  { cliente_id: 3, producto_id: 4, cantidad: 1, fecha: new Date() },
  { cliente_id: 4, producto_id: 2, cantidad: 3, fecha: new Date() }
])

show collections
EOF
```

```sh
juanka@oradeb:~$ mongosh --quiet <<'EOF'
use prueba_bd

db.clientes.insertMany([
  { _id: 1, nombre: "Ana Lopez",   email: "ana@correo.es",   ciudad: "Sevilla" },
  { _id: 2, nombre: "Luis Perez",  email: "luis@correo.es",  ciudad: "Dos Hermanas" },
  { _id: 3, nombre: "Marta Ruiz",  email: "marta@correo.es", ciudad: "Cadiz" },
  { _id: 4, nombre: "Pablo Gomez", email: "pablo@correo.es", ciudad: "Malaga" }
])

db.productos.insertMany([
  { _id: 1, nombre: "Teclado", precio: 24.90 },
  { _id: 2, nombre: "Raton",   precio: 12.50 },
  { _id: 3, nombre: "Monitor", precio: 149.00 },
  { _id: 4, nombre: "Webcam",  precio: 39.95 }
])

db.pedidos.insertMany([
  { cliente_id: 1, producto_id: 1, cantidad: 1, fecha: new Date() },
  { cliente_id: 1, producto_id: 2, cantidad: 2, fecha: new Date() },
  { cliente_id: 2, producto_id: 3, cantidad: 1, fecha: new Date() },
  { cliente_id: 3, producto_id: 4, cantidad: 1, fecha: new Date() },
  { cliente_id: 4, producto_id: 2, cantidad: 3, fecha: new Date() }
])

show collections
EOF
test> use prueba_bd
switched to db prueba_bd
prueba_bd> 

prueba_bd> db.clientes.insertMany([
|   { _id: 1, nombre: "Ana Lopez",   email: "ana@correo.es",   ciudad: "Sevilla" },
|   { _id: 2, nombre: "Luis Perez",  email: "luis@correo.es",  ciudad: "Dos Hermanas" },
|   { _id: 3, nombre: "Marta Ruiz",  email: "marta@correo.es", ciudad: "Cadiz" },
|   { _id: 4, nombre: "Pablo Gomez", email: "pablo@correo.es", ciudad: "Malaga" }
| ])
{ acknowledged: true, insertedIds: { '0': 1, '1': 2, '2': 3, '3': 4 } }
prueba_bd> 

prueba_bd> db.productos.insertMany([
|   { _id: 1, nombre: "Teclado", precio: 24.90 },
|   { _id: 2, nombre: "Raton",   precio: 12.50 },
|   { _id: 3, nombre: "Monitor", precio: 149.00 },
|   { _id: 4, nombre: "Webcam",  precio: 39.95 }
| ])
{ acknowledged: true, insertedIds: { '0': 1, '1': 2, '2': 3, '3': 4 } }
prueba_bd> 

prueba_bd> db.pedidos.insertMany([
|   { cliente_id: 1, producto_id: 1, cantidad: 1, fecha: new Date() },
|   { cliente_id: 1, producto_id: 2, cantidad: 2, fecha: new Date() },
|   { cliente_id: 2, producto_id: 3, cantidad: 1, fecha: new Date() },
|   { cliente_id: 3, producto_id: 4, cantidad: 1, fecha: new Date() },
|   { cliente_id: 4, producto_id: 2, cantidad: 3, fecha: new Date() }
| ])
{
  acknowledged: true,
  insertedIds: {
    '0': ObjectId('6acba119264a2f69993a247a'),
    '1': ObjectId('6acba119264a2f69993a247b'),
    '2': ObjectId('6acba119264a2f69993a247c'),
    '3': ObjectId('6acba119264a2f69993a247d'),
    '4': ObjectId('6acba119264a2f69993a247e')
  }
}
prueba_bd> 

prueba_bd> show collections
clientes
pedidos
productos
```

`use prueba_bd` selecciona (y crea) la base de datos. `insertMany` inserta varios documentos de una vez y crea la colección si no existe. Nosotros asignamos un `_id` numérico en clientes y productos para poder relacionarlos con los pedidos. Al final `show collections` debe listar las tres.

### 3.2 Crear el usuario remoto

```sh
mongosh --quiet <<'EOF'
use prueba_bd
db.createUser({
  user: "usuario_prueba",
  pwd: "prueba",
  roles: [ { role: "readWrite", db: "prueba_bd" } ]
})
EOF
```

```sh
juanka@oradeb:~$ mongosh --quiet <<'EOF'
use prueba_bd
db.createUser({
  user: "usuario_prueba",
  pwd: "prueba",
  roles: [ { role: "readWrite", db: "prueba_bd" } ]
})
EOF
test> use prueba_bd
switched to db prueba_bd
prueba_bd> db.createUser({
|   user: "usuario_prueba",
|   pwd: "prueba",
|   roles: [ { role: "readWrite", db: "prueba_bd" } ]
| })
{ ok: 1 }
```

Creamos el usuario **dentro de `prueba_bd`** con el rol `readWrite` que permite leer y modificar documentos solo en esa base de datos. No puede crear usuarios ni tocar otras bases de datos. Como se crea en `prueba_bd` esa será su **base de datos de autenticación** al conectarse.

## 4. Configurar el acceso remoto y la autenticación

```sh
sudo cp /etc/mongod.conf /etc/mongod.conf.bak

sudo tee /etc/mongod.conf > /dev/null <<'EOF'
# Dónde se guardan los datos
storage:
  dbPath: /var/lib/mongodb

# Registro de actividad
systemLog:
  destination: file
  logAppend: true
  path: /var/log/mongodb/mongod.log

# Red: escucha en todas las interfaces (acceso remoto)
net:
  port: 27017
  bindIp: 0.0.0.0

# Seguridad: obliga a usar usuario y contraseña
security:
  authorization: enabled

processManagement:
  timeZoneInfo: /usr/share/zoneinfo
EOF
```

- `cp ... .bak` guarda una copia del fichero original.
- `bindIp: 0.0.0.0` hace que MongoDB acepte conexiones desde la red, no solo desde la propia máquina.
- `authorization: enabled` es lo más importante: sin él cualquiera que llegue al puerto tendría acceso total a los datos.

Reiniciamos para aplicar los cambios:

```sh
sudo systemctl restart mongod
```

Y comprobamos que escucha en la red:

```sh
sudo ss -tlnp | grep 27017
```

```sh
juanka@oradeb:~$ sudo ss -tlnp | grep 27017
LISTEN 0      4096         0.0.0.0:27017      0.0.0.0:*    users:(("mongod",pid=2421,fd=9))    
``` 

Debemos ver `0.0.0.0:27017`. Si aparece `127.0.0.1:27017` el cambio no se aplicó.

## 5. Pruebas locales

### 5.1 Sin credenciales no debe dejar leer

```sh
mongosh --quiet --eval "db.getSiblingDB('tienda').clientes.find()"
```

Debe fallar con `MongoServerError: Command find requires authentication`. Es la prueba de que la autenticación está activa.

```javascript
juanka@oradeb:~$ mongosh --quiet --eval "db.getSiblingDB('tienda').clientes.find()"
MongoServerError: Command find requires authentication
```

### 5.2 Con el usuario remoto sí

```sh
mongosh --quiet --host 192.168.122.185 --port 27017 \
  -u usuario_prueba -p --authenticationDatabase prueba_bd prueba_bd \
  --eval "db.getCollectionNames()"
```

- `-u` es el usuario y `-p` pide la contraseña por pantalla para que no quede en el historial.
- `--authenticationDatabase prueba_bd` indica dónde se creó el usuario.
- El último `prueba_bd` es la base de datos a la que accedemos.
- `--host` indiacmos el host.
- `--port` indicamos el puerto

```javascript
juanka@oradeb:~$ mongosh --quiet --host 192.168.122.185 --port 27017 \
  -u usuario_prueba -p --authenticationDatabase prueba_bd prueba_bd \
  --eval "db.getCollectionNames()"
Enter password: ******
[ 'productos', 'pedidos', 'clientes' ]
```

## 6. Pruebas remotas

### 6.1 Cortafuegos

```sh
sudo ufw allow from 192.168.122.0/24 to any port 27017
```

 Este comando abre el puerto 27017 únicamente para nuestra red local. Si no tienes cortafuegos, no hace falta.

### 6.2 Conectarse desde el cliente

```sh
mongosh --host 192.168.122.185 --port 27017 \
  -u usuario_prueba -p --authenticationDatabase prueba_bd prueba_bd
```

```javascript
mongosh --host 192.168.122.185 --port 27017 \
  -u usuario_prueba -p --authenticationDatabase prueba_bd prueba_bd
Enter password: ******
Current Mongosh Log ID:	6acba632d6a020c7740395e4
Connecting to:		mongodb://<credentials>@192.168.122.185:27017/prueba_bd?directConnection=true&authSource=prueba_bd&appName=mongosh+2.13.0
Using MongoDB:		8.0.32
Using Mongosh:		2.13.0

For mongosh info see: https://www.mongodb.com/docs/mongodb-shell/


To help improve our products, pseudo-anonymous usage data is collected from interactive and agentic sessions only, and sent to MongoDB periodically (https://www.mongodb.com/legal/privacy-policy).
You can opt-out by running the disableTelemetry() command.

prueba_bd> 

```

Ya dentro de la consola ejecutamos:

```javascript
show collections
db.productos.find()
db.pedidos.find({ cliente_id: 1 })
db.pedidos.aggregate([
  { $lookup: { from: "clientes",  localField: "cliente_id",  foreignField: "_id", as: "cliente" } },
  { $lookup: { from: "productos", localField: "producto_id", foreignField: "_id", as: "producto" } },
  { $project: { _id: 0, cliente: { $first: "$cliente.nombre" }, producto: { $first: "$producto.nombre" }, cantidad: 1 } }
])
```

```javascript
prueba_bd> show collections
clientes
pedidos
productos
prueba_bd> db.productos.find()
| 
[
  { _id: 1, nombre: 'Teclado', precio: 24.9 },
  { _id: 2, nombre: 'Raton', precio: 12.5 },
  { _id: 3, nombre: 'Monitor', precio: 149 },
  { _id: 4, nombre: 'Webcam', precio: 39.95 }
]
prueba_bd> db.pedidos.find({ cliente_id: 1 })
| 
[
  {
    _id: ObjectId('6acba119264a2f69993a247a'),
    cliente_id: 1,
    producto_id: 1,
    cantidad: 1,
    fecha: ISODate('2026-10-11T14:45:45.174Z')
  },
  {
    _id: ObjectId('6acba119264a2f69993a247b'),
    cliente_id: 1,
    producto_id: 2,
    cantidad: 2,
    fecha: ISODate('2026-10-11T14:45:45.174Z')
  }
]
prueba_bd> db.pedidos.aggregate([
|   { $lookup: { from: "clientes",  localField: "cliente_id",  foreignField: "_id", as: "cliente" } },
|   { $lookup: { from: "productos", localField: "producto_id", foreignField: "_id", as: "producto" } },
|   { $project: { _id: 0, cliente: { $first: "$cliente.nombre" }, producto: { $first: "$producto.nombre" }, cantidad: 1 } }
| ])
[
  { cantidad: 1, cliente: 'Ana Lopez', producto: 'Teclado' },
  { cantidad: 2, cliente: 'Ana Lopez', producto: 'Raton' },
  { cantidad: 1, cliente: 'Luis Perez', producto: 'Monitor' },
  { cantidad: 1, cliente: 'Marta Ruiz', producto: 'Webcam' },
  { cantidad: 3, cliente: 'Pablo Gomez', producto: 'Raton' }
]
```

La última consulta relaciona las tres colecciones con `$lookup` (el equivalente aproximado a cruzar tablas en SQL) y muestra qué ha comprado cada cliente.

### 6.3 Prueba de escritura

```javascript
db.clientes.insertOne({ _id: 5, nombre: "Prueba Remota", email: "prueba@correo.es", ciudad: "Sevilla" })
db.clientes.find()
``` 

```javascript
prueba_bd> db.clientes.insertOne({ _id: 5, nombre: "Prueba Remota", email: "prueba@correo.es", ciudad: "Sevilla" })
| 
{ acknowledged: true, insertedId: 5 }
prueba_bd> db.clientes.find()
[
  {
    _id: 1,
    nombre: 'Ana Lopez',
    email: 'ana@correo.es',
    ciudad: 'Sevilla'
  },
  {
    _id: 2,
    nombre: 'Luis Perez',
    email: 'luis@correo.es',
    ciudad: 'Dos Hermanas'
  },
  {
    _id: 3,
    nombre: 'Marta Ruiz',
    email: 'marta@correo.es',
    ciudad: 'Cadiz'
  },
  {
    _id: 4,
    nombre: 'Pablo Gomez',
    email: 'pablo@correo.es',
    ciudad: 'Malaga'
  },
  {
    _id: 5,
    nombre: 'Prueba Remota',
    email: 'prueba@correo.es',
    ciudad: 'Sevilla'
  }
]
prueba_bd> 
```

Comprobamos que el usuario también puede insertar datos desde la red. Para salir escribimos `exit`.

### 6.4 Prueba de que los permisos funcionan

```javascript
use admin
db.getUsers()
```

```txt
prueba_bd> use admin
switched to db admin
admin> db.getUsers()
MongoServerError[Unauthorized]: not authorized on admin to execute command { usersInfo: 1, lsid: { id: UUID("46a1db51-8671-4b1a-ad71-9b10a3eef049") }, $db: "admin" }
admin> 
```

Debe fallar con `not authorized`, porque el usuario solo tiene permisos sobre `prueba_bd`. Es la prueba de que cada usuario ve únicamente lo que le corresponde.

## 7. Manejo de errores

| Mensaje de error                                 | Causa probable                                                   | Solución                                                                                                     |
| ------------------------------------------------ | ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `ECONNREFUSED` / `connection refused`            | MongoDB no escucha en la red o hay un cortafuegos                | Revisar `bindIp` en el paso 4 y reiniciar. Comprobar con `ss -tlnp \| grep 27017` y abrir el puerto en `ufw` |
| `Authentication failed`                          | Contraseña incorrecta, o falta `--authenticationDatabase tienda` | Revisar ambos datos. El usuario se creó en `tienda`, no en `admin`                                           |
| `not authorized on tienda to execute command`    | El usuario no tiene el rol necesario                             | Repetir el paso 3.2 con el rol correcto                                                                      |
| `requires authentication`                        | Hemos entrado sin usuario                                        | Es lo esperado: hay que conectarse con `-u` y `-p`                                                           |
| El servicio no arranca tras editar `mongod.conf` | Error de sintaxis (YAML)                                         | Revisar la sangría con espacios y restaurar con `sudo cp /etc/mongod.conf.bak /etc/mongod.conf`              |

Para ver qué ha pasado en el servidor miramos su registro:

```sh
sudo tail -n 20 /var/log/mongodb/mongod.log
```

Muestra las últimas líneas del registro donde MongoDB deja los errores de arranque y de autenticación.
