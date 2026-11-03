# Implantación de AIDE en servidores Debian con PostgreSQL y Nginx (R1)

## 1. Introducción

En esta documentación se describe la implantación de AIDE en el escenario R1.

El objetivo es disponer de un mecanismo de detección de modificaciones no autorizadas en los archivos críticos de ambos sistemas, prestando especial atención a los binarios, configuraciones, permisos y componentes relacionados con la seguridad.

Como vimos ya en la guia especifica de instalacion y configuracion general de AIDE, la herramienta permite establecer una base de referencia y realizar comprobaciones periódicas para identificar modificaciones posteriores.

En este caso, adaptaremos las reglas de monitorización a las particularidades de cada servicio, evitando que los cambios habituales de funcionamiento generen alertas innecesarias.

## 2. Configuración de AIDE en el servidor PostgreSQL

### 2.1. Elementos que debemos monitorizar

En el servidor PostgreSQL nos interesa vigilar especialmente los siguientes elementos:

| Directorio | Motivo |
|---|---|
| `/etc` | Configuración general del sistema. |
| `/usr/bin` | Ejecutables del sistema. |
| `/usr/sbin` | Ejecutables administrativos. |
| `/usr/lib` | Bibliotecas del sistema. |
| `/usr/lib/postgresql` | Binarios y componentes de PostgreSQL. |
| `/usr/share/postgresql` | Archivos auxiliares de PostgreSQL. |
| `/var/spool/cron` | Tareas programadas. |
| `/root` | Archivos y configuraciones del administrador. |
| `/home` | Configuraciones y claves SSH de usuarios. |

Dentro de `/etc` destacan especialmente los archivos de configuración de PostgreSQL:

- `postgresql.conf`: configuración general del servicio.
- `pg_hba.conf`: reglas de autenticación y acceso.
- `pg_ident.conf`: asignaciones de identidades.

Una modificación no autorizada de estos archivos podría alterar las condiciones de acceso a la base de datos o comprometer su seguridad.

### 2.2. Exclusiones

PostgreSQL modifica continuamente sus archivos de datos como consecuencia de las operaciones normales de lectura y escritura.

Por este motivo, excluiremos `/var/lib/postgresql`, donde habitualmente se almacenan los datos, archivos WAL y demás elementos dinámicos del servicio.

También excluiremos los siguientes directorios:

- `/var/log`: registros del sistema y servicios.
- `/run` y `/var/run`: información temporal de ejecución.
- `/proc`, `/sys` y `/dev`: sistemas de archivos virtuales.

La exclusión de los datos de PostgreSQL no implica que estos no necesiten protección. Su integridad debe garantizarse mediante mecanismos propios de la base de datos, auditoría y copias de seguridad.

### 2.3. Configuración personalizada

Creamos el archivo de configuración:

```bash
sudo nano /etc/aide/aide.conf.d/99_custom_config
```

Configuración propuesta:

```text
DirCriticos = p+i+n+u+g+s+m+c+sha256+sha512

!/var/log/aide
!/var/lib/aide
!/var/log
!/var/lib/postgresql
!/var/run
!/run
!/proc
!/sys
!/dev

/etc DirCriticos
/usr/bin DirCriticos
/usr/sbin DirCriticos
/usr/lib DirCriticos
/usr/lib64 DirCriticos
/usr/local DirCriticos
/usr/lib/postgresql DirCriticos
/usr/share/postgresql DirCriticos
/var/spool/cron DirCriticos
/var/spool/anacron DirCriticos
/boot DirCriticos
/opt DirCriticos

/root$ p+i+n+u+g+s+sha256+sha512
/root DirCriticos
```

La configuración permite vigilar los componentes críticos del sistema y de PostgreSQL, excluyendo los datos dinámicos de la base de datos.

Las rutas deberán adaptarse si el servidor utiliza una ubicación de almacenamiento diferente.

### 2.4. Inicialización

Una vez terminada la configuración y comprobado que el sistema se encuentra en un estado confiable, generamos la base de referencia:

```bash
sudo aide --config-check --config /etc/aide/aide.conf
sudo aide --init --config /etc/aide/aide.conf
```

Activamos la nueva base:

```bash
sudo mv /var/lib/aide/aide.db.new /var/lib/aide/aide.db
```

La base de datos generada será la referencia utilizada para las comprobaciones posteriores.

## 3. Configuración de AIDE en el servidor Nginx

### 3.1. Elementos que debemos monitorizar

En el servidor web centraremos la monitorización en los componentes que pueden modificar el comportamiento del servicio o comprometer su seguridad.

| Directorio | Motivo |
|---|---|
| `/etc` | Configuración general y de Nginx. |
| `/usr/bin` | Ejecutables del sistema. |
| `/usr/sbin` | Ejecutables administrativos y binarios del sistema. |
| `/usr/lib` | Bibliotecas del sistema. |
| `/usr/share/nginx` | Archivos auxiliares de Nginx. |
| `/etc/ssl` | Certificados y material criptográfico. |
| `/etc/letsencrypt` | Certificados de Let's Encrypt, si se utilizan. |
| `/var/spool/cron` | Tareas programadas. |
| `/root` | Archivos y configuraciones del administrador. |
| `/home` | Configuraciones y claves SSH. |

La configuración de Nginx es especialmente importante, ya que permite modificar servidores virtuales, reglas de acceso, redirecciones, certificados TLS y configuraciones de proxy inverso.

También resulta interesante vigilar el contenido web publicado, ya que una modificación no autorizada podría introducir páginas fraudulentas o archivos maliciosos.

### 3.2. Exclusiones

En este servidor excluiremos los directorios cuyo contenido cambia habitualmente:

- `/var/log/nginx`: registros de acceso y errores.
- `/var/cache/nginx`: archivos de caché.
- `/var/lib/nginx`: información dinámica, si corresponde.
- `/run` y `/var/run`: información temporal.
- `/tmp`: archivos temporales.
- `/proc`, `/sys` y `/dev`: sistemas de archivos virtuales.

Prestaremos especial atención a `/var/www`.

Si contiene una aplicación web dinámica, no debemos monitorizar indiscriminadamente todo su contenido. Es recomendable separar el código y los archivos estáticos de los directorios destinados a sesiones, cachés, subidas de usuarios y datos generados.

### 3.3. Configuración personalizada

Creamos el archivo:

```bash
sudo nano /etc/aide/aide.conf.d/99_custom_config
```

Configuración propuesta:

```text
DirCriticos = p+i+n+u+g+s+m+c+sha256+sha512

!/var/log/aide
!/var/lib/aide
!/var/log
!/var/run
!/run
!/proc
!/sys
!/dev
!/tmp
!/var/cache/nginx
!/var/lib/nginx

/etc DirCriticos
/usr/bin DirCriticos
/usr/sbin DirCriticos
/usr/lib DirCriticos
/usr/lib64 DirCriticos
/usr/local DirCriticos
/usr/share/nginx DirCriticos
/etc/ssl DirCriticos
/etc/letsencrypt DirCriticos
/var/spool/cron DirCriticos
/var/spool/anacron DirCriticos
/boot DirCriticos
/opt DirCriticos

/root$ p+i+n+u+g+s+sha256+sha512
/root DirCriticos
```

Si el servidor publica contenido estático que no cambia fuera de los despliegues autorizados, podemos añadir:

```text
/var/www/html DirCriticos
```

Esta regla deberá adaptarse a la estructura real de la aplicación.

### 3.4. Inicialización

Comprobamos la configuración y generamos la base de referencia:

```bash
sudo aide --config-check --config /etc/aide/aide.conf
sudo aide --init --config /etc/aide/aide.conf
```

Activamos la base:

```bash
sudo mv /var/lib/aide/aide.db.new /var/lib/aide/aide.db
```

Cada servidor mantendrá su propia base de referencia, adaptada a sus componentes y necesidades de monitorización.

## 4. Automatización de comprobaciones y gestión de referencias

Una vez inicializados ambos servidores, estableceremos comprobaciones periódicas mediante el mecanismo de systemd proporcionado por Debian.

Comprobamos la existencia del temporizador:

```bash
systemctl cat dailyaidecheck.timer
```

Lo habilitamos:

```bash
sudo systemctl enable --now dailyaidecheck.timer
```

Verificamos su planificación:

```bash
systemctl list-timers dailyaidecheck.timer
```

También debemos comprobar que el servicio ejecuta una operación de verificación y no una actualización automática de la base de referencia.

Para ello, revisamos `/etc/default/aide` y la unidad de ejecución instalada, comprobando el valor de `COMMAND` y el comportamiento de `COPYNEWDB`.

En producción, las referencias no deben actualizarse automáticamente ante cualquier modificación detectada.

### 4.1. Gestión de snapshots

Es recomendable conservar distintas versiones de las bases de referencia para disponer de trazabilidad y poder recuperar estados anteriores.

Las nuevas referencias deberán generarse únicamente después de revisar las diferencias detectadas.

Podemos utilizar un procedimiento de snapshots como el siguiente:

```bash
sudo mkdir -p /var/lib/aide/snapshots
sudo chmod 700 /var/lib/aide/snapshots
```

Después de generar una nueva base:

```bash
sudo cp /var/lib/aide/aide.db.new \
/var/lib/aide/snapshots/aide.db.$(date +%F_%H%M)
```

Una vez revisados y autorizados los cambios, podremos activar la nueva referencia:

```bash
sudo mv /var/lib/aide/aide.db.new /var/lib/aide/aide.db
```

Es importante conservar copias externas de las bases de referencia y sus hashes, ya que un atacante con privilegios administrativos podría intentar modificar la base almacenada localmente.

## 5. Configuración de notificaciones por correo

Para recibir los informes de AIDE utilizaremos Postfix como agente de envío, empleando un servidor SMTP relay.

Instalamos los paquetes necesarios:

```bash
sudo apt install postfix libsasl2-modules bsd-mailx
```

Configuramos el relay SMTP en `/etc/postfix/main.cf`:

```ini
relayhost = [smtp.gmail.com]:587

smtp_sasl_auth_enable = yes
smtp_sasl_password_maps = hash:/etc/postfix/sasl_passwd
smtp_sasl_security_options = noanonymous

smtp_tls_security_level = encrypt
smtp_tls_CAfile = /etc/ssl/certs/ca-certificates.crt

inet_interfaces = loopback-only
```

Configuramos las credenciales en `/etc/postfix/sasl_passwd`:

```text
[smtp.gmail.com]:587 cuenta_fim@gmail.com:CONTRASEÑA_APLICACION
```

Protegemos el fichero y generamos el mapa:

```bash
sudo chmod 600 /etc/postfix/sasl_passwd
sudo postmap /etc/postfix/sasl_passwd
```

Reiniciamos Postfix:

```bash
sudo systemctl restart postfix
```

En `/etc/default/aide` configuramos:

```text
MAILTO=administracion@empresa.com
MAILCMD=mail
QUIETREPORTS=yes
```

Los valores deberán adaptarse a la dirección de administración y al sistema de correo utilizado.

Comprobamos el envío:

```bash
echo "Prueba de integridad AIDE" | mail \
-s "Prueba AIDE" administracion@empresa.com
```

Verificamos los registros:

```bash
sudo journalctl -u postfix -n 30
```

La recepción efectiva del mensaje deberá comprobarse también desde el buzón de destino.

## 6. Pruebas de funcionamiento

Una vez configurados ambos servidores, realizaremos pruebas controladas para comprobar que AIDE identifica modificaciones en los elementos críticos y no genera alertas por las operaciones normales de los servicios.

### 6.1. Pruebas en PostgreSQL

**Modificación de la configuración de autenticación**

Localizamos el archivo:

```bash
sudo find /etc/postgresql -name pg_hba.conf
```

Realizamos una copia y añadimos un comentario:

```bash
sudo cp /etc/postgresql/VERSION/CLUSTER/pg_hba.conf \
/root/pg_hba.conf.backup

echo "# Prueba AIDE" | sudo tee -a \
/etc/postgresql/VERSION/CLUSTER/pg_hba.conf
```

Ejecutamos:

```bash
sudo aide --check --config /etc/aide/aide.conf
```

Resultado esperado: AIDE detectará la modificación del archivo, incluyendo cambios en su tamaño, fechas y hashes.

Restauramos el archivo original después de la prueba.

**Modificación de permisos de un ejecutable**

Simulamos una alteración de permisos:

```bash
sudo chmod u+s /usr/bin/find
```

Ejecutamos nuevamente AIDE:

```bash
sudo aide --check --config /etc/aide/aide.conf
```

Resultado esperado: se detectará la modificación de los permisos del ejecutable.

Restauramos el estado original:

```bash
sudo chmod u-s /usr/bin/find
```

**Operaciones normales de PostgreSQL**

Realizamos una inserción o actualización de registros y ejecutamos AIDE.

Resultado esperado: no deben generarse alertas relativas a los archivos de datos de PostgreSQL, puesto que su directorio se encuentra excluido.

### 6.2. Pruebas en Nginx

**Modificación de la configuración**

Añadimos un comentario a la configuración:

```bash
echo "# Prueba AIDE" | sudo tee -a /etc/nginx/nginx.conf
```

Ejecutamos:

```bash
sudo aide --check --config /etc/aide/aide.conf
```

Resultado esperado: AIDE identificará la modificación del archivo de configuración.

**Modificación del contenido web**

Si hemos incluido `/var/www/html` en la monitorización, creamos un archivo de prueba:

```bash
echo "Prueba AIDE" | sudo tee /var/www/html/prueba.txt
```

Ejecutamos:

```bash
sudo aide --check --config /etc/aide/aide.conf
```

Resultado esperado: se detectará la aparición de un nuevo archivo.

Eliminamos el archivo una vez finalizada la prueba.

**Modificación de permisos de Nginx**

Simulamos un cambio de permisos:

```bash
sudo chmod o+w /usr/sbin/nginx
```

Ejecutamos AIDE y comprobamos que identifica la modificación.

Restauramos los permisos originales, previamente registrados.

### 6.3. Comprobación de alertas

Para comprobar el funcionamiento de las notificaciones, ejecutamos el servicio de comprobación:

```bash
sudo systemctl start dailyaidecheck.service
```

Revisamos su ejecución:

```bash
sudo journalctl -u dailyaidecheck.service
```

Finalmente, verificamos que el informe llega correctamente al buzón configurado.

Las pruebas anteriores deben realizarse en un entorno controlado, restaurando los archivos modificados y sin actualizar la referencia de integridad hasta haber revisado los resultados.

## 7. Gestión de cambios autorizados

En producción se producirán modificaciones legítimas derivadas de actualizaciones, despliegues, renovaciones de certificados y cambios administrativos.

Para evitar que estas operaciones generen alertas permanentes, estableceremos un procedimiento de aceptación de cambios:

1. Registrar la intervención prevista.
2. Identificar los archivos afectados.
3. Ejecutar las modificaciones.
4. Comprobar el funcionamiento del servicio.
5. Ejecutar AIDE.
6. Revisar las diferencias detectadas.
7. Verificar que corresponden a la intervención autorizada.
8. Generar y activar una nueva referencia.
9. Conservar la versión anterior.

Si AIDE detecta cambios que no corresponden a ninguna intervención conocida, no debemos actualizar la referencia.

En ese caso será necesario investigar los archivos afectados, revisar los registros del sistema y determinar si existe una posible intrusión.

## 8. Dificultades encontradas en la implantación

Durante la adaptación de AIDE a un entorno real podemos encontrar las siguientes dificultades:

- **Cambios constantes:** PostgreSQL y Nginx generan modificaciones legítimas que pueden provocar numerosas alertas si no se establecen exclusiones adecuadas.
- **Personalización de reglas:** cada servicio tiene necesidades diferentes, por lo que no resulta recomendable utilizar una configuración idéntica en ambos servidores.
- **Actualizaciones de paquetes:** las actualizaciones pueden modificar numerosos archivos críticos y obligan a revisar las diferencias antes de aceptar una nueva referencia.
- **Protección de la base de referencia:** un atacante con privilegios administrativos podría intentar modificar la propia base de AIDE para ocultar cambios.
- **Gestión de alertas:** un exceso de notificaciones irrelevantes puede provocar fatiga de alertas y reducir la capacidad de detectar modificaciones realmente sospechosas.
- **Integración operativa:** es necesario incorporar las comprobaciones y actualizaciones de referencias a los procedimientos habituales de mantenimiento y despliegue.

## 9. Conclusiones: utilidad de un sistema de integridad de ficheros

La implantación de un sistema de integridad de ficheros como AIDE en los servidores demuestra la utilidad de disponer de un mecanismo que permita identificar modificaciones no autorizadas en los componentes críticos de un sistema Linux.

En un servidor de base de datos como el postgres del escenario resulta especialmente interesante para detectar cambios en los archivos de configuración, binarios y mecanismos de autenticación. Una modificación no autorizada de `pg_hba.conf`, por ejemplo, podría alterar las condiciones de acceso a la base de datos.

Por otro lado, en el servidor nginx nos permite vigilar configuraciones, certificados, ejecutables y contenido web, ayudando a identificar la introducción de archivos desconocidos o modificaciones que puedan comprometer el servicio.

Considero especialmente recomendable utilizar sistemas de integridad de ficheros en los siguientes contextos:

- **Servidores con información sensible:** bases de datos, sistemas empresariales y plataformas que almacenan información personal.
- **Servidores expuestos a Internet:** servidores web y aplicaciones con mayor superficie de exposición.
- **Infraestructuras sujetas a auditorías:** entornos donde es necesario disponer de mecanismos de control y detección de modificaciones.
- **Servidores de infraestructura crítica:** sistemas que deben mantener una configuración estable y controlada.
- **Entornos donde se necesita detectar persistencia:** sistemas en los que una intrusión podría implicar modificaciones de archivos, claves SSH o tareas programadas.

No obstante, como hemos observado a lo largo de la practica, los sistemas de integridad de ficheros no deben considerarse una solución de seguridad completa. No bloquea modificaciones, no detecta todas las técnicas de intrusión y tampoco sustituye a los sistemas de auditoría, monitorización, control de acceso o copias de seguridad.

La principal dificultad de su utilización en producción es mantener una referencia confiable y diferenciar correctamente las modificaciones legítimas de las que pueden representar una amenaza.

Por tanto, considero que AIDE es una herramienta recomendable como capa adicional de seguridad, especialmente en servidores críticos cuyo estado de referencia puede definirse y mantenerse bajo control.

Su utilidad no depende de vigilar el mayor número posible de archivos, sino de identificar correctamente aquellos cuya modificación debería estar siempre justificada y documentada.