# Instalación de PostgreSQL 17 Server y cliente remoto en Debian 13 (Por Rubén)

Guía para instalar PostgreSQL desde los repositorios de Debian 13, permitir el acceso desde la red local, crear una base de datos con tres tablas y un usuario remoto, y conectarse desde otra máquina con `psql`.

## Entorno

| Máquina | Nombre | IP |
|---|---|---|
| Servidor | `bdserver.ruben.asir` | 192.168.122.30 |
| Cliente | `cliente.ruben.asir` | 192.168.122.50 |

- Sistema: Debian 13 (Trixie) en las dos máquinas.
- PostgreSQL 17 (la versión que trae Debian 13).
- Red local: 192.168.122.0/24.

Cambia las IPs por las tuyas.

## 1. Instalar el servidor

En el **servidor**:

```bash
sudo apt update
sudo apt install -y postgresql
```

Comprobamos la versión, el clúster y el servicio:

```bash
psql --version
pg_lsclusters
sudo systemctl status postgresql@17-main --no-pager
```

- Debian organiza PostgreSQL en **clústeres** (`versión` + `nombre`). `pg_lsclusters` debe mostrar `17 main 5432 online`.
- El servicio que de verdad ejecuta la base de datos es `postgresql@17-main`. El servicio `postgresql` solo sirve para arrancar o parar todos los clústeres a la vez, por eso aparece como `active (exited)`.

Rutas que vamos a usar:

| Qué | Dónde |
|---|---|
| Configuración principal | `/etc/postgresql/17/main/postgresql.conf` |
| Configuración propia (carpeta) | `/etc/postgresql/17/main/conf.d/` |
| Quién puede conectarse | `/etc/postgresql/17/main/pg_hba.conf` |
| Registro (log) | `/var/log/postgresql/postgresql-17-main.log` |

## 2. Permitir conexiones desde la red

### 2.1 Dirección de escucha

Por defecto PostgreSQL solo escucha en `localhost`. Debian lee automáticamente los ficheros de la carpeta `conf.d/`, así que ponemos ahí nuestro cambio en vez de editar `postgresql.conf`:

```bash
sudo tee /etc/postgresql/17/main/conf.d/99-ruben.conf > /dev/null <<'EOF'
# Escuchar en local y en la IP de la red local
listen_addresses = 'localhost,192.168.122.30'
EOF
```

### 2.2 Reglas de acceso (pg_hba.conf)

`pg_hba.conf` decide **quién** puede conectarse, **a qué base de datos**, **desde dónde** y **cómo se identifica**. Se lee de arriba abajo y se aplica la primera línea que encaja. Añadimos una línea al final:

```bash
sudo tee -a /etc/postgresql/17/main/pg_hba.conf > /dev/null <<'EOF'

# Acceso remoto de ruben a la base de datos clinica desde la red local
host    clinica    ruben    192.168.122.0/24    scram-sha-256
EOF
```

Significado de cada columna:

| Columna | Valor | Significado |
|---|---|---|
| Tipo | `host` | Conexión por red (TCP/IP) |
| Base de datos | `clinica` | Solo a esta base de datos |
| Usuario | `ruben` | Solo este usuario |
| Dirección | `192.168.122.0/24` | Solo desde la red local |
| Método | `scram-sha-256` | Con contraseña, enviada de forma segura |

### 2.3 Reiniciar y comprobar

```bash
sudo systemctl restart postgresql@17-main
sudo ss -tlnp | grep 5432
```

Debe aparecer `192.168.122.30:5432` además de `127.0.0.1:5432`. Hace falta reiniciar porque `listen_addresses` solo se lee al arrancar.

Si el servidor tiene cortafuegos `ufw`, abrimos el puerto solo para la red local:

```bash
sudo ufw allow from 192.168.122.0/24 to any port 5432 proto tcp
```

## 3. Crear el usuario y la base de datos

En PostgreSQL el administrador es el usuario del sistema `postgres`, que entra sin contraseña desde el propio servidor:

```bash
sudo -u postgres psql
```

Dentro de `psql`:

```sql
CREATE USER ruben;
\password ruben
CREATE DATABASE clinica;
\q
```

- `CREATE USER`: crea un rol que puede iniciar sesión.
- `\password ruben`: pide la contraseña dos veces sin mostrarla y la guarda cifrada. Así no queda escrita en el historial.
- `CREATE DATABASE clinica`: la base de datos pertenece a `postgres`; a `ruben` le daremos solo los permisos que necesite.

## 4. Crear las tablas, los datos y los permisos

Base de datos de una clínica veterinaria: dueños, sus mascotas y las citas.

```bash
sudo -u postgres psql -d clinica <<'EOF'
CREATE TABLE duenos (
  id_dueno  INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  nombre    VARCHAR(60) NOT NULL,
  telefono  VARCHAR(15)
);

CREATE TABLE mascotas (
  id_mascota INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  nombre     VARCHAR(40) NOT NULL,
  especie    VARCHAR(20) NOT NULL,
  id_dueno   INT NOT NULL REFERENCES duenos(id_dueno)
);

CREATE TABLE citas (
  id_cita    INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  id_mascota INT NOT NULL REFERENCES mascotas(id_mascota),
  fecha      TIMESTAMP NOT NULL,
  motivo     TEXT NOT NULL,
  precio     NUMERIC(7,2) NOT NULL
);

INSERT INTO duenos (nombre, telefono) VALUES
  ('Rosa Delgado',    '611222333'),
  ('Alberto Fuentes', '622333444'),
  ('Irene Molina',    '633444555');

INSERT INTO mascotas (nombre, especie, id_dueno) VALUES
  ('Toby',  'perro',  1),
  ('Misha', 'gato',   2),
  ('Copo',  'conejo', 3);

INSERT INTO citas (id_mascota, fecha, motivo, precio) VALUES
  (1, '2026-10-20 10:00', 'Vacuna anual',     35.00),
  (2, '2026-10-20 11:30', 'Revision general', 28.50),
  (3, '2026-10-21 09:15', 'Corte de unas',    12.00);

-- Permisos de ruben: trabajar con los datos, pero no con la estructura
GRANT CONNECT ON DATABASE clinica TO ruben;
GRANT USAGE ON SCHEMA public TO ruben;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ruben;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ruben;
EOF
```

- `GENERATED ALWAYS AS IDENTITY`: PostgreSQL numera solo los identificadores (es la forma moderna de `SERIAL`).
- `REFERENCES`: clave foránea; no deja crear una mascota de un dueño que no existe.
- `GRANT ... ON ALL TABLES`: `ruben` puede leer, añadir, modificar y borrar filas, pero no borrar tablas, porque no es su dueño.
- `GRANT ... ON ALL SEQUENCES`: permiso sobre los contadores que numeran los identificadores, necesario para insertar.

Comprobamos en local:

```bash
sudo -u postgres psql -d clinica -c "\dt" -c "\dp" -c "SELECT * FROM citas;"
```

`\dp` muestra los permisos de cada tabla: debe aparecer `ruben=arwd` (**a**ppend = INSERT, **r**ead = SELECT, **w**rite = UPDATE, **d**elete = DELETE).

## 5. Instalar el cliente remoto

En la máquina **cliente** instalamos solo el cliente:

```bash
sudo apt update
sudo apt install -y postgresql-client netcat-openbsd
nc -zv 192.168.122.30 5432
```

`nc` debe responder `succeeded`. Si no, revisa el paso 2.

## 6. Conectar y probar

```bash
psql -h 192.168.122.30 -U ruben -d clinica
```

- `-h`: servidor.
- `-U`: usuario.
- `-d`: base de datos.

Dentro de `psql`:

```sql
\conninfo
SELECT current_user, inet_client_addr();
\dt
SELECT m.nombre AS mascota, d.nombre AS dueno, c.fecha, c.motivo, c.precio
  FROM citas c
  JOIN mascotas m ON m.id_mascota = c.id_mascota
  JOIN duenos   d ON d.id_dueno   = m.id_dueno
 ORDER BY c.fecha;
```

`\conninfo` muestra el servidor, el puerto y el usuario de la conexión. `inet_client_addr()` devuelve la IP desde la que nos conectamos (la del cliente).

Probamos que puede escribir datos:

```sql
INSERT INTO citas (id_mascota, fecha, motivo, precio)
VALUES (1, '2026-10-27 12:00', 'Desparasitacion', 20.00);
SELECT * FROM citas;
```

Y que **no** puede cambiar la estructura:

```sql
DROP TABLE duenos;
```

Debe fallar con `ERROR: must be owner of table duenos` (o `debe ser dueño de la tabla duenos`). Salimos con `\q`.

Por último, comprobamos que `pg_hba.conf` limita a qué base de datos puede ir `ruben`:

```bash
psql -h 192.168.122.30 -U ruben -d postgres
```

Debe dar `FATAL: no pg_hba.conf entry for host "192.168.122.50", user "ruben", database "postgres"`: solo tiene permitida la base de datos `clinica`.

## Problemas frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| `Connection refused` | No escucha en la red o el cortafuegos bloquea | `sudo ss -tlnp \| grep 5432` y `sudo ufw status` en el servidor |
| `no pg_hba.conf entry for host` | Ninguna línea de `pg_hba.conf` encaja | Revisar base de datos, usuario y red de la línea añadida y recargar: `sudo systemctl reload postgresql@17-main` |
| `password authentication failed` | Contraseña incorrecta | Cambiarla como `postgres`: `\password ruben` |
| `permission denied for table` | Faltan los `GRANT` | Repetir los `GRANT` del paso 4 |
| El clúster no arranca | Error en `99-ruben.conf` | `sudo tail -n 30 /var/log/postgresql/postgresql-17-main.log` |

## Fuentes

- [Documentación de PostgreSQL 17: pg_hba.conf](https://www.postgresql.org/docs/17/auth-pg-hba-conf.html)
- [Documentación de PostgreSQL 17: listen_addresses](https://www.postgresql.org/docs/17/runtime-config-connection.html)
- [Documentación de PostgreSQL 17: GRANT](https://www.postgresql.org/docs/17/sql-grant.html)
- [Wiki de Debian: PostgreSQL](https://wiki.debian.org/PostgreSql)
