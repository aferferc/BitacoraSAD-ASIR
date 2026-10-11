
# Instalación

## 1.1 Actualizar la lista de paquetes

```sh
sudo apt update
```

## 1.2 Instalar PostgreSQL

```sh
sudo apt install -y postgresql postgresql-client
```

Instalamos el servidor (`postgresql`) y la herramienta de consola `psql` (`postgresql-client`). Debian 13 trae la versión 17, así que no hace falta añadir repositorios externos. El instalador crea y arranca por sí solo un “clúster” llamado `main`.

## 1.3 Comprobar que el servicio está activo

```sh
sudo systemctl status postgresql --no-pager
pg_lsclusters
```

```txt
juanka@oradeb:~$ sudo systemctl status postgresql --no-pager
pg_lsclusters
● postgresql.service - PostgreSQL RDBMS
     Loaded: loaded (/usr/lib/systemd/system/postgresql.service; enabled; preset: enabled)
     Active: active (exited) since Sun 2026-10-11 12:14:18 CEST; 20s ago
 Invocation: 62e99153e5d84f7d8a9b3617912e1c21
   Main PID: 2852 (code=exited, status=0/SUCCESS)
   Mem peak: 1.8M
        CPU: 7ms

oct 11 12:14:18 oradeb.abd.local systemd[1]: Starting postgresql.service - PostgreSQL RDBMS...
oct 11 12:14:18 oradeb.abd.local systemd[1]: Finished postgresql.service - PostgreSQL RDBMS.
Ver Cluster Port Status Owner    Data directory              Log file
17  main    5432 online postgres /var/lib/postgresql/17/main /var/log/postgresql/postgresql-17-main.log
```

El primer comando nos dice si el servicio está en marcha. El segundo lista los clústeres de PostgreSQL con su versión, puerto y estado. Debemos ver `17 main 5432 online`.

# 2. Configurar el acceso remoto

Por defecto PostgreSQL solo escucha en la propia máquina (`localhost`). Para permitir conexiones desde la red local hay que tocar dos cosas: **en qué direcciones escucha** y **quién puede entrar**.

## 2.1 Hacer que escuche en la red

```sh
sudo tee /etc/postgresql/17/main/conf.d/acceso-remoto.conf > /dev/null <<'EOF'
# Permite que PostgreSQL escuche en todas las interfaces de red
listen_addresses = '*'
EOF
```

Con este comando creamos un fichero de configuración propio dentro de `conf.d`, que Debian lee automáticamente. Así no modificamos el `postgresql.conf` original y es fácil deshacer el cambio borrando este fichero. `'*'` significa “escucha en todas las tarjetas de red”.

## 2.2 Autorizar a nuestra red local

```sh
sudo tee -a /etc/postgresql/17/main/pg_hba.conf > /dev/null <<'EOF'

# Acceso remoto a prueba_bd desde la red de libvirt
host    prueba_bd    prueba_user    192.168.122.0/24    scram-sha-256
EOF
```

El fichero `pg_hba.conf` es el “portero” de PostgreSQL. Con `tee -a` añadimos una línea al final sin borrar lo que ya hay. Esa línea dice:

- `host`: conexiones por red.
- `prueba_bd`: solo a esa base de datos.
- `prueba_user`: solo ese usuario.
- `192.168.122.0/24`: solo desde nuestra red local.
- `scram-sha-256`: pide contraseña con un método de cifrado seguro.

Así abrimos solo lo imprescindible en lugar de dejar la puerta abierta a todo el mundo.

## 2.3 Reiniciar para aplicar los cambios

```sh
sudo systemctl restart postgresql
```

Los cambios de `listen_addresses` solo se aplican al reiniciar el servicio.

## 2.4 Comprobar que escucha en la red

```sh
sudo ss -tlnp | grep 5432
``` 

```txt
juanka@oradeb:~$ sudo ss -tlnp | grep 5432
LISTEN 0      200          0.0.0.0:5432       0.0.0.0:*    users:(("postgres",pid=3972,fd=6))       
LISTEN 0      200             [::]:5432          [::]:*    users:(("postgres",pid=3972,fd=7))       
```

`ss` muestra los puertos abiertos. Debemos ver `0.0.0.0:5432`, que indica que ya acepta conexiones externas. Si solo apareciera `127.0.0.1:5432`, el paso 2.1 no se aplicó.

# 3. Crear usuario, base de datos y tablas

Entramos como el usuario administrador `postgres` del sistema, que es el único que puede crear usuarios y bases de datos al principio.

## 3.1 Crear el usuario y la base de datos

```sh
cd /tmp
sudo -u postgres psql <<'EOF'
CREATE USER prueba_user WITH PASSWORD 'prueba';
CREATE DATABASE prueba_bd OWNER prueba_user;
EOF
```

- `cd /tmp` evita un aviso de permisos, porque el usuario `postgres` no puede entrar en nuestra carpeta personal.
- `sudo -u postgres psql` abre la consola de PostgreSQL como administrador.
- `<<'EOF'` pasa varias órdenes seguidas a `psql` sin tener que teclearlas una a una.
- `CREATE USER` crea el usuario con su contraseña.
- `CREATE DATABASE ... OWNER` crea la base de datos y se la asigna a ese usuario.

## 3.2 Crear las tablas y poblarlas

```sh
sudo -u postgres psql -d prueba_bd <<'EOF'
CREATE TABLE clientes (
    id     SERIAL PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL,
    email  VARCHAR(80) UNIQUE,
    ciudad VARCHAR(40)
);

CREATE TABLE productos (
    id     SERIAL PRIMARY KEY,
    nombre VARCHAR(60) NOT NULL,
    precio NUMERIC(8,2) NOT NULL
);

CREATE TABLE pedidos (
    id          SERIAL PRIMARY KEY,
    cliente_id  INT REFERENCES clientes(id),
    producto_id INT REFERENCES productos(id),
    cantidad    INT NOT NULL,
    fecha       DATE DEFAULT CURRENT_DATE
);

INSERT INTO clientes (nombre, email, ciudad) VALUES
    ('Ana Lopez',    'ana@correo.es',    'Sevilla'),
    ('Luis Perez',   'luis@correo.es',   'Dos Hermanas'),
    ('Marta Ruiz',   'marta@correo.es',  'Cadiz'),
    ('Pablo Gomez',  'pablo@correo.es',  'Malaga');

INSERT INTO productos (nombre, precio) VALUES
    ('Teclado',  24.90),
    ('Raton',    12.50),
    ('Monitor', 149.00),
    ('Webcam',   39.95);

INSERT INTO pedidos (cliente_id, producto_id, cantidad) VALUES
    (1, 1, 1),
    (1, 2, 2),
    (2, 3, 1),
    (3, 4, 1),
    (4, 2, 3);
EOF
```

Creamos las tres tablas (`clientes`, `productos`, `pedidos`) y las relacionamos con claves foráneas (`REFERENCES`) de modo que un pedido solo puede apuntar a un cliente y un producto que existan. Después insertamos datos de prueba. Entramos con `-d prueba_bd` para que las tablas se creen en esa base de datos y no en otra.

## 3.3 Dar permisos al usuario remoto

Hemos creado las tablas como administrador, así que el usuario remoto todavía no puede tocarlas. Se los damos:

```sh
sudo -u postgres psql -d prueba_bd <<'EOF'
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO prueba_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO prueba_user;
EOF
```

- La primera orden permite leer, insertar, modificar y borrar filas, pero no borrar ni cambiar la estructura de las tablas.
- La segunda permite usar los contadores automáticos (`SERIAL`) sin ella no podría insertar filas nuevas.

# 4. Pruebas de funcionamiento

## 4.1 Prueba local

```sh
sudo -u postgres psql -d prueba_bd -c "\dt"
sudo -u postgres psql -d prueba_bd -c "SELECT * FROM clientes;"
``` 

```txt
juanka@oradeb:/tmp$ sudo -u postgres psql -d prueba_bd -c "\dt"
sudo -u postgres psql -d prueba_bd -c "SELECT * FROM clientes;"
         Listado de relaciones
 Esquema |  Nombre   | Tipo  |  Dueño   
---------+-----------+-------+----------
 public  | clientes  | tabla | postgres
 public  | pedidos   | tabla | postgres
 public  | productos | tabla | postgres
(3 filas)

 id |   nombre    |      email      |    ciudad    
----+-------------+-----------------+--------------
  1 | Ana Lopez   | ana@correo.es   | Sevilla
  2 | Luis Perez  | luis@correo.es  | Dos Hermanas
  3 | Marta Ruiz  | marta@correo.es | Cadiz
  4 | Pablo Gomez | pablo@correo.es | Malaga
(4 filas)
```

`\dt` lista las tablas y el `SELECT` comprueba que los datos se han guardado. Así sabemos que la base de datos funciona antes de probar la red.

## 4.2 Prueba remota

Desde otra máquina de nuestra red:

```sh
psql -h 192.168.122.185 -U prueba_user -d prueba_bd
```

- `-h`: dirección del servidor.
- `-U`: usuario con el que entramos.
- `-d`: base de datos a la que accedemos.

Nos pedirá la contraseña. Ya dentro de `psql` ejecutamos:

```sql
\dt
SELECT * FROM productos;
SELECT c.nombre, pr.nombre, p.cantidad, p.fecha
FROM clientes c, productos pr, pedidos p
WHERE p.cliente_id = c.id
  AND p.producto_id = pr.id
ORDER BY c.nombre;
```

La última consulta cruza las tres tablas y nos muestra qué ha comprado cada cliente. Con ella demostramos que los datos son accesibles de forma remota y que las relaciones funcionan.

```txt
juanka@JuankaPortatil:~$ psql -h 192.168.122.185 -U prueba_user -d prueba_bd
Contraseña para usuario prueba_user: 
psql (17.11 (Debian 17.11-0+deb13u1))
Conexión SSL (protocolo: TLSv1.3, cifrado: TLS_AES_256_GCM_SHA384, compresión: desactivado, ALPN: postgresql)
Digite «help» para obtener ayuda.

prueba_bd=> \dt
         Listado de relaciones
 Esquema |  Nombre   | Tipo  |  Dueño   
---------+-----------+-------+----------
 public  | clientes  | tabla | postgres
 public  | pedidos   | tabla | postgres
 public  | productos | tabla | postgres
(3 filas)

prueba_bd=> SELECT * FROM productos;
 id | nombre  | precio 
----+---------+--------
  1 | Teclado |  24.90
  2 | Raton   |  12.50
  3 | Monitor | 149.00
  4 | Webcam  |  39.95
(4 filas)

prueba_bd=> SELECT c.nombre, pr.nombre, p.cantidad, p.fecha
FROM clientes c, productos pr, pedidos p
WHERE p.cliente_id = c.id
  AND p.producto_id = pr.id
ORDER BY c.nombre;
   nombre    | nombre  | cantidad |   fecha    
-------------+---------+----------+------------
 Ana Lopez   | Teclado |        1 | 2026-10-11
 Ana Lopez   | Raton   |        2 | 2026-10-11
 Luis Perez  | Monitor |        1 | 2026-10-11
 Marta Ruiz  | Webcam  |        1 | 2026-10-11
 Pablo Gomez | Raton   |        3 | 2026-10-11
(5 filas)
```

## 4.3 Prueba de escritura remota

```sh
INSERT INTO clientes (nombre, email, ciudad) VALUES ('Prueba Remota', 'prueba@correo.es', 'Sevilla');
SELECT * FROM clientes;
```

```txt
prueba_bd=> INSERT INTO clientes (nombre, email, ciudad) VALUES ('Prueba Remota', 'prueba@correo.es', 'Sevilla');
SELECT * FROM clientes;
INSERT 0 1
 id |    nombre     |      email       |    ciudad    
----+---------------+------------------+--------------
  1 | Ana Lopez     | ana@correo.es    | Sevilla
  2 | Luis Perez    | luis@correo.es   | Dos Hermanas
  3 | Marta Ruiz    | marta@correo.es  | Cadiz
  4 | Pablo Gomez   | pablo@correo.es  | Malaga
  5 | Prueba Remota | prueba@correo.es | Sevilla
(5 filas)
```

Comprobamos que el usuario no solo lee, sino que también puede insertar datos desde la red. Para salir, escribimos `\q`.

## 4.4 Prueba de que la seguridad funciona

```sh
psql -h 192.168.122.185 -U preuba_user -d postgres
```

Esta conexión debe **fallar** con un mensaje de que no hay entrada en `pg_hba.conf`. Es la prueba de que solo se puede acceder a la base de datos autorizada.

```txt
juanka@JuankaPortatil:~$ psql -h 192.168.122.185 -U preuba_user -d postgres
psql: error: falló la conexión al servidor en «192.168.122.185», puerto 5432: FATAL:  no hay una línea en pg_hba.conf para «192.168.122.1», usuario «preuba_user», base de datos «postgres», cifrado SSL
falló la conexión al servidor en «192.168.122.185», puerto 5432: FATAL:  no hay una línea en pg_hba.conf para «192.168.122.1», usuario «preuba_user», base de datos «postgres», sin cifrado
```

# 5. Si algo falla

|Mensaje de error|Causa probable|Solución|
|---|---|---|
|`Connection refused`|El servidor no escucha en la red|Revisar el paso 2.1 y reiniciar. Comprobar con `ss -tlnp \| grep 5432`|
|`Connection timed out`|Un cortafuegos bloquea el puerto|Abrir el 5432 (`sudo ufw allow from 192.168.1.0/24 to any port 5432` si usamos `ufw`)|
|`no pg_hba.conf entry for host...`|La IP, usuario o base de datos no coinciden con la regla|Revisar la línea del paso 2.2 y reiniciar|
|`password authentication failed`|Contraseña incorrecta|Cambiarla con `ALTER USER usuario_remoto PASSWORD 'nueva';`|
|`permission denied for table`|Faltan permisos|Repetir el paso 3.3|
Para saber qué ha pasado en el servidor miramos su registro:

```sh
sudo tail -n 20 /var/log/postgresql/postgresql-17-main.log
```

Este comando muestra las últimas 20 líneas del log, donde PostgreSQL explica con detalle por qué rechazó una conexión.
