
#  Guía de instalación de Neo4j en Debian 13 (Community)

## 1. ¿Qué es Neo4j?

Neo4j es una base de datos **orientada a grafos**. En lugar de guardar la información en tablas (como PostgreSQL o MariaDB) o en documentos (como MongoDB), la guarda como una red de **nodos** conectados entre sí por **relaciones**.

Un grafo tiene tres piezas básicas:

|Pieza|Qué es|Ejemplo|
|---|---|---|
|**Nodo**|Una entidad|Una persona, un producto, una ciudad|
|**Relación**|Una conexión con dirección y tipo entre dos nodos|Ana `COMPRÓ` un teclado|
|**Propiedad**|Un dato guardado en un nodo o relación|`nombre: "Ana"`, `cantidad: 2`|
## 2. ¿Cómo funciona?

En una base de datos relacional, para saber qué productos compraron los amigos de Ana hay que cruzar varias tablas y cuantos más saltos más lenta es la consulta. En Neo4j cada nodo **guarda directamente la dirección de sus vecinos**, así que recorrer una relación es seguir un puntero y no buscar en un índice. Por eso las consultas sobre datos muy conectados siguen siendo rápidas aunque la base de datos crezca.

Se consulta con **Cypher**, un lenguaje que describe los patrones del grafo de forma casi visual. Neo4j se conecta por dos puertos:

- **7687 (Bolt):** el protocolo que usan las aplicaciones y `cypher-shell`.
- **7474 (HTTP):** la interfaz web (Neo4j Browser).

## 3. Utilidades y ejemplos de la vida real

Neo4j destaca cuando lo importante son las **relaciones** entre los datos:

- **Redes sociales:** “amigos de amigos”, sugerencias de contactos (LinkedIn, Facebook).
- **Recomendaciones:** “quienes compraron esto también compraron...” (tiendas online, plataformas de streaming).
- **Detección de fraude:** encontrar cuentas que comparten teléfono, dirección o tarjeta de forma sospechosa (bancos, aseguradoras).
- **Rutas y logística:** calcular el camino más corto entre dos puntos (transporte, reparto).
- **Redes informáticas y ciberseguridad:** mapear qué equipo se conecta con cuál para ver hasta dónde llegaría un ataque.
- **Grafos de conocimiento:** conectar conceptos, documentos y personas (buscadores, asistentes de IA).

## 4. Sintaxis básica de Cypher

Cypher dibuja los patrones con “arte ASCII”: los nodos van entre paréntesis `()` y las relaciones entre corchetes `[]` con una flecha.

```cypher
(c:Cliente {nombre: "Ana"})-[:COMPRO]->(p:Producto {nombre: "Teclado"})
```

- `c` es una variable que apunta al nodo.
- `:Cliente` es su **etiqueta** (equivale a una “tabla”).
- `{nombre: "Ana"}` son sus propiedades.
- `-[:COMPRO]->` es una relación con dirección.

Las órdenes principales son:

|Orden|Para qué sirve|Ejemplo|
|---|---|---|
|`CREATE`|Crear nodos o relaciones|`CREATE (:Cliente {nombre:"Ana"});`|
|`MATCH`|Buscar un patrón|`MATCH (c:Cliente) RETURN c;`|
|`WHERE`|Filtrar resultados|`MATCH (c:Cliente) WHERE c.ciudad = "Sevilla" RETURN c;`|
|`RETURN`|Indicar qué devolver|`RETURN c.nombre;`|
|`SET`|Modificar propiedades|`MATCH (c:Cliente {nombre:"Ana"}) SET c.ciudad = "Cadiz";`|
|`MERGE`|Crear solo si no existe|`MERGE (:Cliente {nombre:"Ana"});`|
|`DELETE`|Borrar (con `DETACH` borra también sus relaciones)|`MATCH (c:Cliente {nombre:"Ana"}) DETACH DELETE c;`|
Todas las sentencias terminan con `;` .

## 5. Instalación

### 5.1 Instalar Java 21

```sh
sudo apt update
sudo apt install -y openjdk-21-jre-headless wget gnupg
java -version
```

Neo4j está escrito en Java y necesita un entorno para funcionar. Instalamos la versión “headless” (sin entorno gráfico), que es más ligera y suficiente para un servidor. `wget` y `gnupg` los usaremos en el paso siguiente y `java -version` debe mostrar la versión 21.

```sh
juanka@oradeb:~$ java -version
openjdk version "21.0.12.1" 2026-08-18
OpenJDK Runtime Environment (build 21.0.12.1+1-1-deb13u1-Debian)
OpenJDK 64-Bit Server VM (build 21.0.12.1+1-1-deb13u1-Debian, mixed mode, sharing)
```

### 5.2 Añadir la clave y el repositorio de Neo4j

```sh
wget -O - https://debian.neo4j.com/neotechnology.gpg.key | \
  sudo gpg --dearmor -o /etc/apt/keyrings/neotechnology.gpg

sudo tee /etc/apt/sources.list.d/neo4j.list > /dev/null <<'EOF'
deb [signed-by=/etc/apt/keyrings/neotechnology.gpg] https://debian.neo4j.com stable latest
EOF
```

- La primera orden descarga la clave de firma de Neo4j y la convierte al formato de `apt`, para que Debian verifique que los paquetes son auténticos.
- La segunda indica dónde está el repositorio y con qué clave se comprueba.

### 5.3 Instalar Neo4j

```sh
sudo apt update
sudo apt install -y neo4j
```

Instalamos la edición **Community** (gratuita), que incluye el servidor y `cypher-shell` que es la consola .

### 5.4 Fijar la contraseña inicial

```sh
sudo neo4j-admin dbms set-initial-password 'admin123'
```

Neo4j trae un usuario administrador llamado `neo4j`. Con este comando le damos contraseña **antes del primer arranque** y así no depende de la contraseña por defecto (`neo4j`). (Minimo debe tener 8 caracteres).

### 5.5 Arrancar el servicio y activarlo en cada inicio

```sh
sudo systemctl enable --now neo4j
sudo systemctl status neo4j --no-pager
```

`enable --now` lo arranca y hace que se inicie solo cada vez que se enciende la máquina. `status` comprueba que está activo.

```sh
juanka@oradeb:~$ sudo systemctl enable --now neo4j
sudo systemctl status neo4j --no-pager
Synchronizing state of neo4j.service with SysV service script with /usr/lib/systemd/systemd-sysv-install.
Executing: /usr/lib/systemd/systemd-sysv-install enable neo4j
● neo4j.service - Neo4j Graph Database
     Loaded: loaded (/usr/lib/systemd/system/neo4j.service; enabled; preset: enabled)
     Active: active (running) since Mon 2026-10-12 12:02:28 CEST; 29ms ago
 Invocation: bb433e18631e445f8812b1f67d4a5e3a
   Main PID: 3816 (java)
      Tasks: 1 (limit: 9470)
     Memory: 1.8M (peak: 1.9M)
        CPU: 11ms
     CGroup: /system.slice/neo4j.service
             └─3816 /usr/bin/java -Xmx128m -XX:+IgnoreUnrecognizedVMOptions --sun-misc-unsafe-memory-access=allow -classpath "/usr/share/neo4j/lib/*:…

oct 12 12:02:28 oradeb.abd.local systemd[1]: Started neo4j.service - Neo4j Graph Database.
``` 

## 6. Prueba de funcionamiento local

```sh
cypher-shell -u neo4j -p 'admin123' "RETURN 'Neo4j funciona (Juan Carlos)' AS mensaje;"
```

Nos conectamos con `cypher-shell` y ejecutamos una consulta. Si devuelve el mensaje indicado, el servidor responde y la contraseña es correcta.

```sh
juanka@oradeb:~$ cypher-shell -u neo4j -p 'admin123' "RETURN 'Neo4j funciona (Juan Carlos)' AS mensaje;"
+--------------------------------+
| mensaje                        |
+--------------------------------+
| "Neo4j funciona (Juan Carlos)" |
+--------------------------------+

1 row
ready to start consuming query after 109 ms, results consumed after another 2 ms
```

## 7. Crear datos

```sh
cypher-shell -u neo4j -p 'admin123' <<'EOF'
CREATE (ana:Cliente   {nombre:"Ana Lopez",   ciudad:"Sevilla"})
CREATE (luis:Cliente  {nombre:"Luis Perez",  ciudad:"Dos Hermanas"})
CREATE (marta:Cliente {nombre:"Marta Ruiz",  ciudad:"Cadiz"})
CREATE (pablo:Cliente {nombre:"Pablo Gomez", ciudad:"Malaga"})

CREATE (teclado:Producto {nombre:"Teclado", precio:24.90})
CREATE (raton:Producto   {nombre:"Raton",   precio:12.50})
CREATE (monitor:Producto {nombre:"Monitor", precio:149.00})
CREATE (webcam:Producto  {nombre:"Webcam",  precio:39.95})

CREATE (perif:Categoria {nombre:"Perifericos"})
CREATE (pant:Categoria  {nombre:"Pantallas"})

CREATE (teclado)-[:PERTENECE_A]->(perif)
CREATE (raton)-[:PERTENECE_A]->(perif)
CREATE (webcam)-[:PERTENECE_A]->(perif)
CREATE (monitor)-[:PERTENECE_A]->(pant)

CREATE (ana)-[:COMPRO {cantidad:1}]->(teclado)
CREATE (ana)-[:COMPRO {cantidad:2}]->(raton)
CREATE (luis)-[:COMPRO {cantidad:1}]->(monitor)
CREATE (marta)-[:COMPRO {cantidad:1}]->(webcam)
CREATE (pablo)-[:COMPRO {cantidad:3}]->(raton)

CREATE (ana)-[:CONOCE]->(luis)
CREATE (luis)-[:CONOCE]->(marta)
CREATE (marta)-[:CONOCE]->(pablo);
EOF
```

Creamos tres tipos de nodos (`Cliente`, `Producto`, `Categoria`) y tres tipos de relaciones (`COMPRO`, `PERTENECE_A`, `CONOCE`). Cada `CREATE` añade un nodo o una relación. Guardamos cada nodo en una variable (`ana`, `teclado`...) para poder conectarlos entre sí dentro de la misma sentencia. La relación `COMPRO` lleva la propiedad `cantidad`.

#### Consultas de comprobación

```sh
cypher-shell -u neo4j -p 'admin123' <<'EOF'
MATCH (n) RETURN labels(n) AS tipo, count(*) AS total;

MATCH (c:Cliente)-[r:COMPRO]->(p:Producto)
RETURN c.nombre AS cliente, p.nombre AS producto, r.cantidad AS cantidad
ORDER BY cliente;

MATCH (:Cliente {nombre:"Ana Lopez"})-[:CONOCE*1..3]->(amigo:Cliente)
RETURN amigo.nombre AS conocidos_de_ana;
EOF
```

- La primera cuenta los nodos de cada tipo.
- La segunda muestra qué ha comprado cada cliente siguiendo la relación `COMPRO` sin cruzar tablas.
- La tercera recorre la red de conocidos de Ana hasta 3 saltos (`*1..3`). Esta es la clase de consulta más interesante.

```sh
juanka@oradeb:~$ cypher-shell -u neo4j -p 'admin123' <<'EOF'
MATCH (n) RETURN labels(n) AS tipo, count(*) AS total;

MATCH (c:Cliente)-[r:COMPRO]->(p:Producto)
RETURN c.nombre AS cliente, p.nombre AS producto, r.cantidad AS cantidad
ORDER BY cliente;

MATCH (:Cliente {nombre:"Ana Lopez"})-[:CONOCE*1..3]->(amigo:Cliente)
RETURN amigo.nombre AS conocidos_de_ana;
EOF
tipo, total
["Cliente"], 4
["Producto"], 4
["Categoria"], 2
cliente, producto, cantidad
"Ana Lopez", "Raton", 2
"Ana Lopez", "Teclado", 1
"Luis Perez", "Monitor", 1
"Marta Ruiz", "Webcam", 1
"Pablo Gomez", "Raton", 3
conocidos_de_ana
"Luis Perez"
"Marta Ruiz"
"Pablo Gomez"
```

## 8. Acceso remoto

### 8.1 Configurar el servidor

Por defecto Neo4j solo escucha en `localhost`. Cambiamos la dirección de escucha:

```sh
sudo cp /etc/neo4j/neo4j.conf /etc/neo4j/neo4j.conf.bak
sudo sed -i 's/^#server.default_listen_address=0.0.0.0/server.default_listen_address=0.0.0.0/' /etc/neo4j/neo4j.conf
grep -n '^server.default_listen_address' /etc/neo4j/neo4j.conf
```

- `cp ... .bak` guarda una copia del fichero original.
- `sed -i` descomenta la línea `server.default_listen_address=0.0.0.0` hace que Neo4j acepte conexiones desde cualquier tarjeta de red.
- `grep` comprueba que la línea quedó activa sin `#` delante. Si no aparece nada mira el fichero con `grep -n listen_address /etc/neo4j/neo4j.conf` y descomenta la línea a mano.

Reiniciamos y comprobamos los puertos:

```sh
sudo systemctl restart neo4j
sudo ss -tlnp | grep -E '7474|7687'
```

Debemos ver `0.0.0.0:7474` y `0.0.0.0:7687`. Si aparece `127.0.0.1`, el cambio no se aplicó.

```sh
juanka@oradeb:~$ sudo ss -tlnp | grep -E '7474|7687'
LISTEN 0      4096               *:7687             *:*    users:(("java",pid=4248,fd=364))         
```

Si usas `ufw`, abrimos los puertos solo para nuestra red local:

```sh
sudo ufw allow from 192.168.122.0/24 to any port 7474,7687 proto tcp
```

### 8.2 Conectarse desde el cliente

En la **otra máquina** instalamos solo la consola. Añadimos el mismo repositorio (pasos 5.1 y 5.2) y después:

```sh
sudo apt update
sudo apt install -y cypher-shell
```

Nos conectamos al servidor:

```sh
cypher-shell -a bolt://192.168.122.185:7687 -u neo4j -p admin123
```

- `-a` es la dirección del servidor y `bolt://` el protocolo. Usamos `bolt://` y no `neo4j://` porque tenemos un único servidor y así evitamos problemas de enrutamiento.
- `-p` Indicamos la contraseña.

```sh
juanka@JuankaPortatil:/mnt/midisco$ cypher-shell -a bolt://192.168.122.185:7687 -u neo4j -p admin123
Connected to Neo4j using Bolt protocol version 6.1 at bolt://192.168.122.185:7687 as user neo4j.
Type :help for a list of available commands or :exit to exit the shell.
Note that Cypher queries must end with a semicolon.
neo4j@neo4j> 
``` 

Ya dentro, ejecutamos:

```cypher
MATCH (c:Cliente)-[r:COMPRO]->(p:Producto)
RETURN c.nombre, p.nombre, r.cantidad;
```

```cypher
neo4j@neo4j> MATCH (c:Cliente)-[r:COMPRO]->(p:Producto)
             RETURN c.nombre, p.nombre, r.cantidad;
+----------------------------------------+
| c.nombre      | p.nombre  | r.cantidad |
+----------------------------------------+
| "Ana Lopez"   | "Raton"   | 2          |
| "Ana Lopez"   | "Teclado" | 1          |
| "Luis Perez"  | "Monitor" | 1          |
| "Marta Ruiz"  | "Webcam"  | 1          |
| "Pablo Gomez" | "Raton"   | 3          |
+----------------------------------------+

5 rows
ready to start consuming query after 406 ms, results consumed after another 10 ms
```

Salimos con `:exit`.

#### Prueba de escritura remota

```cypher
CREATE (:Cliente {nombre:"Prueba Remota", ciudad:"Sevilla"});
MATCH (c:Cliente) RETURN c.nombre ORDER BY c.nombre;
```

```cypher
neo4j@neo4j> CREATE (:Cliente {nombre:"Prueba Remota", ciudad:"Sevilla"});
             MATCH (c:Cliente) RETURN c.nombre ORDER BY c.nombre;
0 rows
ready to start consuming query after 207 ms, results consumed after another 0 ms
Created 1 node, set 2 properties, added 1 label
+-----------------+
| c.nombre        |
+-----------------+
| "Ana Lopez"     |
| "Luis Perez"    |
| "Marta Ruiz"    |
| "Pablo Gomez"   |
| "Prueba Remota" |
+-----------------+

5 rows
ready to start consuming query after 108 ms, results consumed after another 2 ms
```

####  Interfaz web

Desde el navegador del cliente abrimos `http://192.168.122.185:7474` ponemos como URL de conexión `bolt://192.168.122.185:7687` e iniciamos sesión con `neo4j`. Ahí podemos ejecutar `MATCH (n) RETURN n LIMIT 25;` y ver el grafo dibujado.

![[Neo4j Interfaz web.png]]

## 9. Gestión básica de usuarios

```sh
cypher-shell -u neo4j -p 'admin123' -d system <<'EOF'
CREATE USER usuario_preuba SET PASSWORD 'prueba1234' CHANGE NOT REQUIRED;
SHOW USERS;
EOF
```

Con `-d system` entramos en la base de datos interna donde Neo4j guarda los usuarios. `CHANGE NOT REQUIRED` evita que el usuario deba cambiar la contraseña en el primer acceso. En la edición **Community** todos los usuarios tienen acceso completo, porque los roles y permisos finos son una función de la edición Enterprise. Tampoco puede crear más bases de datos: solo existe `neo4j`.

```sh
juanka@oradeb:~$ cypher-shell -u neo4j -p 'admin123' -d system <<'EOF'
CREATE USER usuario_preuba SET PASSWORD 'prueba1234' CHANGE NOT REQUIRED;
SHOW USERS;
EOF
user, roles, passwordChangeRequired, suspended, home
"neo4j", NULL, FALSE, NULL, NULL
"usuario_preuba", NULL, FALSE, NULL, NULL
```

Conexión de prueba:

```sh
cypher-shell -a bolt://192.168.122.185:7687 -u usuario_preuba -p prueba1234
```

```sh
juanka@JuankaPortatil:~$ cypher-shell -a bolt://192.168.122.185:7687 -u usuario_preuba -p prueba1234
Connected to Neo4j using Bolt protocol version 6.1 at bolt://192.168.122.185:7687 as user usuario_preuba.
Type :help for a list of available commands or :exit to exit the shell.
Note that Cypher queries must end with a semicolon.
usuario_preuba@neo4j> 
```

## 10. Manejo de errores

| Mensaje de error                                           | Causa probable                                     | Solución                                                                                                                                                 |     |
| ---------------------------------------------------------- | -------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | --- |
| `Unable to connect to localhost:7687`                      | Neo4j no está activo o no ha terminado de arrancar | `sudo systemctl status neo4j` y `sudo journalctl -u neo4j -n 30 --no-pager`                                                                              |     |
| `Connection refused` desde el cliente                      | No escucha en la red o hay cortafuegos             | Revisar el paso 8.1 y reiniciar. Comprobar con `ss -tlnp \| grep 7687`                                                                                   |     |
| `The client is unauthorized due to authentication failure` | Contraseña incorrecta                              | Restablecerla parando el servicio y usando `neo4j-admin dbms set-initial-password` solo si es una instalación nueva, o `ALTER USER` si aún puedes entrar |     |
| Neo4j no arranca y el registro menciona Java               | La versión de Java por defecto no es 21            | `java -version` y `sudo update-alternatives --config java`, eligiendo Java 21                                                                            |     |
| `Failed to obtain connection towards WRITE server`         | Usamos `neo4j://` contra un único servidor         | Conectarse con `bolt://`                                                                                                                                 |     |

Para ver los registros del servidor:

```sh
sudo tail -n 30 /var/log/neo4j/neo4j.log
```
