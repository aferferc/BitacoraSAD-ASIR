# Instalación de MariaDB Server y cliente remoto en Debian 13 (Por Rubén)

Guía para instalar MariaDB desde los repositorios de Debian 13, permitir el acceso desde la red local, crear una base de datos con tres tablas y un usuario remoto, y conectarse desde otra máquina con el cliente `mariadb`.

## Entorno

| Máquina | Nombre | IP |
|---|---|---|
| Servidor | `bdserver.ruben.asir` | 192.168.122.30 |
| Cliente | `cliente.ruben.asir` | 192.168.122.50 |

- Sistema: Debian 13 (Trixie) en las dos máquinas.
- MariaDB 11.8 (la versión que trae Debian 13).
- Red local: 192.168.122.0/24.

Cambia las IPs por las tuyas.

## 1. Instalar el servidor

En el **servidor**:

```bash
sudo apt update
sudo apt install -y mariadb-server
```

- `apt update` descarga la lista de paquetes actualizada.
- `mariadb-server` instala el servidor y, como dependencia, también el cliente `mariadb`. El servicio se arranca solo al terminar.

Comprobamos la versión y que el servicio está activo y habilitado al arranque:

```bash
mariadb --version
sudo systemctl status mariadb --no-pager
systemctl is-enabled mariadb
```

Debe aparecer `active (running)` y `enabled`.

## 2. Asegurar la instalación

MariaDB trae un asistente que quita lo que solo sirve para pruebas:

```bash
sudo mariadb-secure-installation
```

Respuestas y por qué:

| Pregunta | Respuesta | Motivo |
|---|---|---|
| *Enter current password for root* | Enter | Aún no tiene contraseña |
| *Switch to unix_socket authentication* | `n` | En Debian ya lo usa: `root` entra con `sudo mariadb`, sin contraseña y solo desde el propio servidor |
| *Change the root password?* | `n` | No hace falta, por lo mismo |
| *Remove anonymous users?* | `Y` | Sin esto se podría entrar sin usuario |
| *Disallow root login remotely?* | `Y` | El administrador nunca entra por red |
| *Remove test database?* | `Y` | Base de datos de prueba accesible para todos |
| *Reload privilege tables now?* | `Y` | Aplica los cambios al momento |

Comprobamos que solo quedan los usuarios del sistema:

```bash
sudo mariadb -e "SELECT user, host, plugin FROM mysql.user;"
```

## 3. Permitir conexiones desde la red

Por defecto MariaDB solo escucha en `127.0.0.1` (el propio servidor). Para cambiarlo creamos **nuestro propio fichero** de configuración en lugar de editar `50-server.cnf`; así una actualización del paquete no borra nuestros cambios. Los ficheros de `/etc/mysql/mariadb.conf.d/` se leen en orden alfabético y gana el último, por eso empieza por `99-`.

```bash
sudo tee /etc/mysql/mariadb.conf.d/99-ruben.cnf > /dev/null <<'EOF'
[mysqld]
# Escuchar en la IP de la red local
bind-address = 192.168.122.30
EOF
sudo systemctl restart mariadb
sudo ss -tlnp | grep 3306
```

`ss` debe mostrar `192.168.122.30:3306`. Si sale `127.0.0.1:3306`, el fichero no se ha leído: revisa el nombre y la ruta.

Si el servidor tiene cortafuegos `ufw`, abrimos el puerto solo para la red local:

```bash
sudo ufw allow from 192.168.122.0/24 to any port 3306 proto tcp
```

## 4. Crear la base de datos y el usuario remoto

```bash
sudo mariadb <<'EOF'
CREATE DATABASE taller CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
CREATE USER 'ruben'@'192.168.122.%' IDENTIFIED BY '<CONTRASEÑA>';
GRANT SELECT, INSERT, UPDATE, DELETE ON taller.* TO 'ruben'@'192.168.122.%';
FLUSH PRIVILEGES;
EOF
```

- `utf8mb4`: guarda bien tildes, eñes y cualquier carácter.
- `'ruben'@'192.168.122.%'`: en MariaDB un usuario es **nombre + desde dónde se conecta**. El `%` es un comodín: puede entrar desde cualquier IP que empiece por `192.168.122.`, y desde ninguna otra.
- `GRANT ... ON taller.*`: puede leer, añadir, modificar y borrar filas en todas las tablas de `taller`, pero no crear ni borrar tablas, ni tocar otras bases de datos.

Comprobamos:

```bash
sudo mariadb -e "SHOW GRANTS FOR 'ruben'@'192.168.122.%';"
```

## 5. Crear las tablas y los datos

Base de datos de un pequeño taller mecánico: clientes, sus vehículos y las reparaciones.

```bash
sudo mariadb taller <<'EOF'
CREATE TABLE clientes (
  id_cliente INT AUTO_INCREMENT PRIMARY KEY,
  nombre     VARCHAR(60) NOT NULL,
  telefono   VARCHAR(15)
) ENGINE=InnoDB;

CREATE TABLE vehiculos (
  matricula  CHAR(7) PRIMARY KEY,
  marca      VARCHAR(30) NOT NULL,
  modelo     VARCHAR(30) NOT NULL,
  id_cliente INT NOT NULL,
  FOREIGN KEY (id_cliente) REFERENCES clientes(id_cliente)
) ENGINE=InnoDB;

CREATE TABLE reparaciones (
  id_reparacion INT AUTO_INCREMENT PRIMARY KEY,
  matricula     CHAR(7) NOT NULL,
  descripcion   VARCHAR(200) NOT NULL,
  importe       DECIMAL(8,2) NOT NULL,
  fecha         DATE DEFAULT (CURRENT_DATE),
  FOREIGN KEY (matricula) REFERENCES vehiculos(matricula)
) ENGINE=InnoDB;

INSERT INTO clientes (nombre, telefono) VALUES
  ('Elena Prieto',    '600111222'),
  ('Marcos Iglesias', '600333444'),
  ('Nuria Campos',    '600555666');

INSERT INTO vehiculos VALUES
  ('1234LMN', 'Seat',    'Ibiza',   1),
  ('5678BCD', 'Toyota',  'Corolla', 2),
  ('9012KJH', 'Renault', 'Clio',    3);

INSERT INTO reparaciones (matricula, descripcion, importe) VALUES
  ('1234LMN', 'Cambio de aceite y filtros',  89.90),
  ('5678BCD', 'Revision de frenos',         145.00),
  ('9012KJH', 'Sustitucion de embrague',    620.50);
EOF
```

- `AUTO_INCREMENT`: MariaDB numera solo los identificadores.
- `FOREIGN KEY`: no deja crear un vehículo de un cliente que no existe, ni una reparación de un vehículo que no existe.
- `ENGINE=InnoDB`: el motor que admite claves foráneas y transacciones.

Comprobamos en local:

```bash
sudo mariadb taller -e "SHOW TABLES; SELECT * FROM reparaciones;"
```

## 6. Instalar el cliente remoto

En la máquina **cliente** instalamos solo el cliente:

```bash
sudo apt update
sudo apt install -y mariadb-client netcat-openbsd
```

Antes de conectar comprobamos que el puerto del servidor está accesible:

```bash
nc -zv 192.168.122.30 3306
```

Debe responder `succeeded`. Si no, revisa el paso 3 (`bind-address` y cortafuegos).

## 7. Conectar y probar

```bash
mariadb -h 192.168.122.30 -u ruben -p taller
```

- `-h`: servidor al que nos conectamos.
- `-u`: usuario.
- `-p`: pide la contraseña sin mostrarla.
- `taller`: base de datos en la que entramos.

Dentro, comprobamos quiénes somos y consultamos los datos:

```sql
SELECT CURRENT_USER(), USER();
SHOW TABLES;
SELECT c.nombre, v.marca, v.modelo, r.descripcion, r.importe
  FROM reparaciones r
  JOIN vehiculos v ON v.matricula = r.matricula
  JOIN clientes  c ON c.id_cliente = v.id_cliente;
```

`CURRENT_USER()` debe devolver `ruben@192.168.122.%` y `USER()` `ruben@192.168.122.50`: entramos desde el cliente gracias a la regla de red.

Probamos que puede escribir datos:

```sql
INSERT INTO reparaciones (matricula, descripcion, importe) VALUES ('1234LMN', 'Alineado de ruedas', 40);
SELECT * FROM reparaciones;
```

Y que **no** puede cambiar la estructura:

```sql
DROP TABLE clientes;
```

Debe fallar con `ERROR 1142: DROP command denied to user 'ruben'`. Es lo esperado: solo tiene permisos sobre los datos. Salimos con `exit`.

## Problemas frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| `ERROR 2002` / `2003: Can't connect` | El servidor no escucha en la red o el cortafuegos bloquea | `sudo ss -tlnp \| grep 3306` y `sudo ufw status` en el servidor |
| `ERROR 1130: Host ... is not allowed to connect` | No hay usuario para la IP del cliente | Revisar el `host` del usuario: `SELECT user, host FROM mysql.user;` |
| `ERROR 1045: Access denied` | Contraseña incorrecta | Cambiarla: `ALTER USER 'ruben'@'192.168.122.%' IDENTIFIED BY '...';` |
| El servicio no arranca tras editar la configuración | Error de sintaxis en `99-ruben.cnf` | `sudo journalctl -u mariadb -n 30 --no-pager` |

## Fuentes

- [MariaDB: mariadb-secure-installation](https://mariadb.com/docs/server/clients-and-utilities/deployment-tools/mariadb-secure-installation)
- [MariaDB: configurar el acceso remoto](https://mariadb.com/docs/server/mariadb-quickstart-guides/mariadb-remote-connection-guide)
- [MariaDB: guía de instalación del servidor](https://mariadb.com/docs/server/mariadb-quickstart-guides/installing-mariadb-server-guide)
