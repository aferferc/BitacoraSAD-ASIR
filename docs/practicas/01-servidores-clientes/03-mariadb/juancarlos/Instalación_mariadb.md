
# 1. Instalación

## 1.1 Actualizar la lista de paquetes

```sh
sudo apt update
```

Actualizamos el índice de paquetes para instalar la versión más reciente que ofrece Debian.

## 1.2 Instalar MariaDB

```sh
sudo apt install -y mariadb-server mariadb-client
```

Instalamos el servidor (`mariadb-server`) y la herramienta de consola (`mariadb-client`). Debian 13 trae MariaDB 11.8 así que no necesitamos repositorios externos. El servicio se arranca solo al terminar.

## 1.3 Comprobar que está funcionando

```sh
sudo systemctl status mariadb --no-pager
mariadb --version
```

El primer comando nos dice si el servicio está activo. El segundo muestra la versión instalada.

```txt
juanka@oradeb:~$ sudo systemctl status mariadb --no-pager
mariadb --version
● mariadb.service - MariaDB 11.8.6 database server
     Loaded: loaded (/usr/lib/systemd/system/mariadb.service; enabled; preset: enabled)
     Active: active (running) since Sun 2026-10-11 12:49:56 CEST; 49s ago
 Invocation: a888046282f34472a888a1771d586da4
       Docs: man:mariadbd(8)
             https://mariadb.com/kb/en/library/systemd/
    Process: 2094 ExecStartPre=/bin/sh -c [ ! -e /usr/bin/galera_recovery ] && VAR= ||   VAR=`/usr/bin/galera_recovery`; [ $? -eq 0 ]   && echo _WSREP_START_POSITION=$VAR > /run/mysqld/wsrep-start-position || exit 1 (code=exited, status=0/SUCCESS)
    Process: 2160 ExecStartPost=/bin/rm -f /run/mysqld/wsrep-start-position /run/mysqld/wsrep-new-cluster (code=exited, status=0/SUCCESS)
    Process: 2162 ExecStartPost=/etc/mysql/debian-start (code=exited, status=0/SUCCESS)
   Main PID: 2147 (mariadbd)
     Status: "Taking your SQL requests now..."
      Tasks: 14 (limit: 62502)
     Memory: 125.6M (peak: 130.3M)
        CPU: 1.073s
     CGroup: /system.slice/mariadb.service
             └─2147 /usr/sbin/mariadbd

oct 11 12:49:56 oradeb.abd.local mariadbd[2147]: 2026-10-11 12:49:56 0 [Note] Plugin 'wsrep-provider' is disabled.
oct 11 12:49:56 oradeb.abd.local mariadbd[2147]: 2026-10-11 12:49:56 0 [Note] InnoDB: Buffer pool(s) load completed at 261011 12:49:56
oct 11 12:49:56 oradeb.abd.local mariadbd[2147]: 2026-10-11 12:49:56 0 [Note] Server socket created on IP: '127.0.0.1', port: '3306'.
oct 11 12:49:56 oradeb.abd.local mariadbd[2147]: 2026-10-11 12:49:56 0 [Note] mariadbd: Event Scheduler: Loaded 0 events
oct 11 12:49:56 oradeb.abd.local mariadbd[2147]: 2026-10-11 12:49:56 0 [Note] /usr/sbin/mariadbd: ready for connections.
oct 11 12:49:56 oradeb.abd.local mariadbd[2147]: Version: '11.8.6-MariaDB-0+deb13u1 from Debian'  socket: '/run/mysqld/mysqld.sock'  port: …aDB/Server
oct 11 12:49:56 oradeb.abd.local systemd[1]: Started mariadb.service - MariaDB 11.8.6 database server.
oct 11 12:49:56 oradeb.abd.local /etc/mysql/debian-start[2164]: Upgrading MariaDB tables if necessary.
oct 11 12:49:56 oradeb.abd.local /etc/mysql/debian-start[2177]: Checking for insecure root accounts.
oct 11 12:49:56 oradeb.abd.local /etc/mysql/debian-start[2181]: Triggering myisam-recover for all MyISAM tables and aria-recover for all Aria tables
Hint: Some lines were ellipsized, use -l to show in full.
mariadb from 11.8.6-MariaDB, client 15.2 for debian-linux-gnu (x86_64) using  EditLine wrapper
```

# 2. Asegurar la instalación

Una instalación recién hecha trae ajustes pensados para pruebas, como usuarios anónimos y una base de datos de ejemplo. Los quitamos con las mismas acciones que hace el asistente `mariadb-secure-installation`, pero de forma directa:

```sh
sudo mariadb <<'EOF'
DELETE FROM mysql.global_priv WHERE User='';
DROP DATABASE IF EXISTS test;
FLUSH PRIVILEGES;
EOF
```

- `sudo mariadb` entra como administrador. El `root` de MariaDB se identifica por el usuario del sistema (`unix_socket`) así que no pide contraseña si usamos `sudo`. Es seguro porque solo funciona desde la propia máquina.
- `DELETE FROM mysql.global_priv ...` borra los usuarios anónimos que permitirían entrar sin identificarse.
- `DROP DATABASE test` elimina la base de datos de pruebas que viene por defecto.
- `FLUSH PRIVILEGES` hace que los cambios se apliquen al momento.

# 3. Configurar el acceso remoto

Por defecto MariaDB solo escucha en `127.0.0.1` (la propia máquina). Para aceptar conexiones de la red hay que cambiar la dirección en la que escucha.

## 3.1 Hacer que escuche en la red

```sh
sudo tee /etc/mysql/mariadb.conf.d/99-acceso-remoto.cnf > /dev/null <<'EOF'
[mysqld]
# Permite conexiones desde la red local
bind-address = 0.0.0.0
EOF
```

Creamos un fichero propio en lugar de editar `50-server.cnf` que es el original. MariaDB lee los ficheros por orden alfabético y gana el último, así que el `99-` sobrescribe el valor por defecto. Si queremos deshacerlo basta con borrarlo. `0.0.0.0` significa “escucha en todas las tarjetas de red”.

## 3.2 Reiniciar el servicio

```sh
sudo systemctl restart mariadb
```

El cambio de `bind-address` solo se aplica al reiniciar.

## 3.3 Comprobar que escucha en la red

```sh
sudo ss -tlnp | grep 3306
```

`ss` muestra los puertos abiertos. Debemos ver `0.0.0.0:3306`. Si aparece `127.0.0.1:3306` el paso 3.1 no se aplicó.

```txt
juanka@oradeb:~$ sudo ss -tlnp | grep 3306
LISTEN 0      80           0.0.0.0:3306       0.0.0.0:*    users:(("mariadbd",pid=2323,fd=28))   
```

# 4. Crear usuario, base de datos y tablas

## 4.1 Crear la base de datos y el usuario remoto

```sh
sudo mariadb <<'EOF'
CREATE DATABASE prueba_bd CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'usuario_prueba'@'192.168.122.%' IDENTIFIED BY 'prueba';
GRANT SELECT, INSERT, UPDATE, DELETE ON prueba_bd.* TO 'usuario_prueba'@'192.168.122.%';
FLUSH PRIVILEGES;
EOF
```

- `CREATE DATABASE` crea la base de datos. `utf8mb4` permite guardar tildes eñes y emojis sin problemas.
- `'usuario_prueba'@'192.168.122.%'` indica **quién** es el usuario y **desde dónde** puede conectarse. El `%` es un comodín que equivale a cualquier IP de nuestra red local y desde cualquier otra red no podrá entrar. En MariaDB esto sustituye al `pg_hba.conf` de PostgreSQL.
- `GRANT` le da permiso para leer, insertar, modificar y borrar filas pero solo dentro de `tienda`. No puede borrar tablas ni tocar otras bases de datos.

# 4.2 Crear las tablas y poblarlas

```sh
sudo mariadb prueba_bd <<'EOF'
CREATE TABLE clientes (
    id     INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL,
    email  VARCHAR(80) UNIQUE,
    ciudad VARCHAR(40)
) ENGINE=InnoDB;

CREATE TABLE productos (
    id     INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(60) NOT NULL,
    precio DECIMAL(8,2) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE pedidos (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    cliente_id  INT NOT NULL,
    producto_id INT NOT NULL,
    cantidad    INT NOT NULL,
    fecha       DATE DEFAULT (CURRENT_DATE),
    FOREIGN KEY (cliente_id)  REFERENCES clientes(id),
    FOREIGN KEY (producto_id) REFERENCES productos(id)
) ENGINE=InnoDB;

INSERT INTO clientes (nombre, email, ciudad) VALUES
    ('Ana Lopez',   'ana@correo.es',   'Sevilla'),
    ('Luis Perez',  'luis@correo.es',  'Dos Hermanas'),
    ('Marta Ruiz',  'marta@correo.es', 'Cadiz'),
    ('Pablo Gomez', 'pablo@correo.es', 'Malaga');

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

Entramos directamente en `prueba_bd`  y creamos las tres tablas. `ENGINE=InnoDB` es el motor que permite las claves foráneas (`FOREIGN KEY`), que impiden que un pedido apunte a un cliente o producto que no existe. Después insertamos datos de prueba. Como el usuario remoto ya tenía permisos sobre  `prueba_bd.*`, las tablas nuevas le quedan accesibles sin hacer nada más.

# 5. Pruebas de funcionamiento

## 5.1 Prueba local

```sh
sudo mariadb prueba_bd -e "SHOW TABLES; SELECT * FROM clientes;"
```

```txt
juanka@oradeb:~$ sudo mariadb prueba_bd -e "SHOW TABLES; SELECT * FROM clientes;"
+---------------------+
| Tables_in_prueba_bd |
+---------------------+
| clientes            |
| pedidos             |
| productos           |
+---------------------+
+----+-------------+-----------------+--------------+
| id | nombre      | email           | ciudad       |
+----+-------------+-----------------+--------------+
|  1 | Ana Lopez   | ana@correo.es   | Sevilla      |
|  2 | Luis Perez  | luis@correo.es  | Dos Hermanas |
|  3 | Marta Ruiz  | marta@correo.es | Cadiz        |
|  4 | Pablo Gomez | pablo@correo.es | Malaga       |
+----+-------------+-----------------+--------------+
```

`-e` ejecuta las órdenes y sale. Comprobamos que las tablas existen y que los datos se guardaron antes de probar la red.

## 5.2 Prueba remota

```sh
mariadb -h 192.168.122.185 -u usuario_prueba -p prueba_bd
```

- `-h`: dirección del servidor.
- `-u`: usuario con el que entramos.
- `-p`: pide la contraseña por pantalla, para que no quede escrita en el historial.
- `tienda`: base de datos a la que accedemos.

Ya dentro ejecutamos:

```sql
SHOW TABLES;
SELECT * FROM productos;
SELECT c.nombre AS cliente, pr.nombre AS producto, p.cantidad, p.fecha
FROM clientes c, productos pr, pedidos p
WHERE p.cliente_id = c.id
  AND p.producto_id = pr.id
ORDER BY c.nombre;
```

```txt
juanka@JuankaPortatil:~$ mariadb -h 192.168.122.185 -u usuario_prueba -p prueba_bd
Enter password: 
Reading table information for completion of table and column names
You can turn off this feature to get a quicker startup with -A

Welcome to the MariaDB monitor.  Commands end with ; or \g.
Your MariaDB connection id is 38
Server version: 11.8.6-MariaDB-0+deb13u1 from Debian -- Please help get to 10k stars at https://github.com/MariaDB/Server

Copyright (c) 2000, 2018, Oracle, MariaDB Corporation Ab and others.

Type 'help;' or '\h' for help. Type '\c' to clear the current input statement.

MariaDB [prueba_bd]> SHOW TABLES;
+---------------------+
| Tables_in_prueba_bd |
+---------------------+
| clientes            |
| pedidos             |
| productos           |
+---------------------+
3 rows in set (0,002 sec)

MariaDB [prueba_bd]> SELECT * FROM productos;
+----+---------+--------+
| id | nombre  | precio |
+----+---------+--------+
|  1 | Teclado |  24.90 |
|  2 | Raton   |  12.50 |
|  3 | Monitor | 149.00 |
|  4 | Webcam  |  39.95 |
+----+---------+--------+
4 rows in set (0,001 sec)

MariaDB [prueba_bd]> SELECT c.nombre AS cliente, pr.nombre AS producto, p.cantidad, p.fecha
    -> FROM clientes c, productos pr, pedidos p
    -> WHERE p.cliente_id = c.id
    ->   AND p.producto_id = pr.id
    -> ORDER BY c.nombre;
+-------------+----------+----------+------------+
| cliente     | producto | cantidad | fecha      |
+-------------+----------+----------+------------+
| Ana Lopez   | Raton    |        2 | 2026-10-11 |
| Ana Lopez   | Teclado  |        1 | 2026-10-11 |
| Luis Perez  | Monitor  |        1 | 2026-10-11 |
| Marta Ruiz  | Webcam   |        1 | 2026-10-11 |
| Pablo Gomez | Raton    |        3 | 2026-10-11 |
+-------------+----------+----------+------------+
5 rows in set (0,002 sec)
```

## 5.3 Prueba de escritura remota

```sql
INSERT INTO clientes (nombre, email, ciudad) VALUES ('Prueba Remota', 'prueba@correo.es', 'Sevilla');
SELECT * FROM clientes;
```

Comprobamos que el usuario también puede insertar datos desde la red. Para salir escribimos `exit`.

```txt
MariaDB [prueba_bd]> INSERT INTO clientes (nombre, email, ciudad) VALUES ('Prueba Remota', 'prueba@correo.es', 'Sevilla');
Query OK, 1 row affected (0,003 sec)

MariaDB [prueba_bd]> SELECT * FROM clientes;
+----+---------------+------------------+--------------+
| id | nombre        | email            | ciudad       |
+----+---------------+------------------+--------------+
|  1 | Ana Lopez     | ana@correo.es    | Sevilla      |
|  2 | Luis Perez    | luis@correo.es   | Dos Hermanas |
|  3 | Marta Ruiz    | marta@correo.es  | Cadiz        |
|  4 | Pablo Gomez   | pablo@correo.es  | Malaga       |
|  5 | Prueba Remota | prueba@correo.es | Sevilla      |
+----+---------------+------------------+--------------+
5 rows in set (0,001 sec)
```

## 5.4 Prueba de que los permisos funcionan

```sql
DROP TABLE pedidos;
```

Debe **fallar** con `DROP command denied` porque solo le dimos permisos sobre los datos no sobre la estructura. Es la prueba de que el usuario tiene solo los privilegios necesarios.

```txt
MariaDB [prueba_bd]> DROP TABLE pedidos;
ERROR 1142 (42000): DROP command denied to user 'usuario_prueba'@'192.168.122.1' for table `prueba_bd`.`pedidos`
```
 
# 6. Manejo de errores

| Mensaje de error                            | Causa probable                                                                            | Solución                                                                                                                                      |
| ------------------------------------------- | ----------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `ERROR 2002/2003: Can't connect to server`  | El servidor no escucha en la red o hay un cortafuegos                                     | Revisar el paso 3.1 y reiniciar. Comprobar con `ss -tlnp \| grep 3306`. Si hay `ufw`: `sudo ufw allow from 192.168.122.0/24 to any port 3306` |
| `ERROR 1045: Access denied for user`        | Contraseña incorrecta, o la IP del cliente no encaja con el `'192.168.122.%'` del usuario | Ver los usuarios con `sudo mariadb -e "SELECT User, Host FROM mysql.user;"` y recrear el usuario con el host correcto                         |
| `ERROR 1044: Access denied ... to database` | Faltan permisos sobre esa base de datos                                                   | Repetir el `GRANT` del paso 4.1                                                                                                               |
| `ERROR 1142: command denied`                | Intentamos una operación para la que no tiene permiso                                     | Es lo esperado si probamos algo como `DROP` o `CREATE`                                                                                        |

Para ver qué ha pasado en el servidor miramos su registro:

```sh
sudo journalctl -u mariadb -n 20 --no-pager
```

Este comando muestra las últimas 20 líneas del registro del servicio donde MariaDB explica por qué falló un arranque o una conexión.
