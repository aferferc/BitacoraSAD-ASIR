# Guía básica: Postfix con Gmail para enviar los correos del sistema

Este documento complementa la guía de AIDE. Explica cómo instalar **Postfix** y configurarlo de forma muy básica para que reenvíe los correos a través de una cuenta de **Gmail**.

---

## 1. Requisitos previos: contraseña de aplicación de Gmail

Gmail no permite que un programa use la contraseña normal de la cuenta. Hay que crear una **contraseña de aplicación**:

1. Activar la **verificación en dos pasos** en la cuenta de Google.
2. Entrar en <https://myaccount.google.com/apppasswords>.
3. Crear una contraseña de aplicación (por ejemplo, con el nombre `postfix-fim`).
4. Copiar los 16 caracteres que se muestran. Solo se enseñan una vez.

> Usa una cuenta dedicada para esto, no tu cuenta personal. La contraseña va a quedar guardada en el servidor.

---

## 2. Instalación

```
sudo apt update && sudo apt install postfix libsasl2-modules
```

Durante la instalación, Postfix pregunta por el tipo de configuración. Elegimos **Internet Site** y dejamos como nombre de correo del sistema el nombre de la máquina. Lo demás lo ajustamos a mano.

---

## 3. Credenciales de Gmail

Creamos el fichero `/etc/postfix/sasl_passwd` con esta única línea:

```
[smtp.gmail.com]:587 tu_cuenta@gmail.com:contraseña_de_aplicación
```

Como contiene una credencial, solo debe poder leerlo `root`. Después lo convertimos al formato que Postfix puede consultar:

```
sudo chmod 600 /etc/postfix/sasl_passwd
sudo postmap /etc/postfix/sasl_passwd
```

Esto genera `/etc/postfix/sasl_passwd.db`.

---

## 4. Configuración de Postfix

Editamos `/etc/postfix/main.cf` y añadimos estas líneas al final (si ya existe alguna con el mismo nombre, como `relayhost`, hay que modificarla en lugar de duplicarla):

```
# Enviar todo el correo a través de Gmail
relayhost = [smtp.gmail.com]:587

# Autenticación
smtp_sasl_auth_enable = yes
smtp_sasl_password_maps = hash:/etc/postfix/sasl_passwd
smtp_sasl_security_options = noanonymous

# Cifrado obligatorio
smtp_tls_security_level = encrypt
smtp_tls_CAfile = /etc/ssl/certs/ca-certificates.crt

# Solo aceptar correo generado por la propia máquina
inet_interfaces = loopback-only
```

| Bloque | Qué hace |
| :--- | :--- |
| `relayhost` | Indica que no entregamos el correo directamente, sino que lo pasamos a Gmail por el puerto 587. |
| `smtp_sasl_*` | Activa la autenticación con el usuario y la contraseña de `sasl_passwd`. |
| `smtp_tls_*` | Obliga a cifrar la conexión (si no hay TLS, no se envía). |
| `inet_interfaces` | Postfix solo escucha en local; nadie desde la red puede usarlo como relay. |

Reiniciamos el servicio:

```
sudo systemctl restart postfix
```

---

## 5. Comprobación

Enviamos un correo de prueba:

```
echo "Prueba desde fim" | mail -s "Prueba Postfix" tu_direccion@gmail.com
```

Para ver qué ha pasado:

```
mailq
sudo journalctl -u postfix@-.service -n 20
```

- `mailq` muestra los mensajes pendientes. Si está vacío, el correo salió.
- En el log, la línea `status=sent` indica que Gmail lo aceptó. Si aparece `Authentication failed`, revisa la contraseña de aplicación y el fichero `sasl_passwd` (recuerda repetir `postmap` si lo modificas).
