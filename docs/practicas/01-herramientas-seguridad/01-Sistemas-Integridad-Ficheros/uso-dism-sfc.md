#Sistemas de integridad de ficheros en windows: SFC y DISM

Windows incluye de serie dos herramientas para comprobar y reparar la integridad de los ficheros del sistema: **SFC** y **DISM**. A diferencia de las herramienta que abarcamos en linux, AIDE, no comparan el sistema contra una base de datos que creamos nosotros, sino contra copias de referencia que el propio Windows guarda.

---

## 1. Cómo funcionan

Windows mantiene una copia de los ficheros del sistema en el **almacén de componentes** en `C:\Windows\WinSxS`. Cada herramienta actúa sobre una capa distinta:


-**SFC**: Comprueba los ficheros protegidos del sistema (DLL, ejecutables, drivers...). Compara estos con as copias del almacén de componentes. 

-**DISM**: Comprueba la integridad del propio **almacén de componentes**. Usa como fuente para comparar Windows Update o un origen que indiquemos (por ejemplo, un ISO).

La relación entre ambas es la clave: SFC repara los ficheros del sistema a partir del almacén, y DISM repara el almacén. Si el almacén está dañado, SFC no tiene de dónde copiar los ficheros buenos y falla. Por eso, cuando SFC no puede reparar algo, se usa primero DISM.

> **Importante** SFC y DISM solo cubren los ficheros propios de Windows. No vigilan documentos, configuraciones de usuario ni aplicaciones de terceros, y no guardan un histórico de cambios. Además, confían en el almacén local: si un atacante lo manipulara a la vez, no lo notarían.

Todos los comandos se ejecutan desde un CMD como administrador.

---

## 2. SFC

### Opciones principales

| Comando | Qué hace |
| :--- | :--- |
| `sfc /scannow` | Analiza **todos** los ficheros protegidos y repara automáticamente los dañados. |
| `sfc /verifyonly` | Analiza todos los ficheros protegidos pero **no repara** nada. Sirve para comprobar. |
| `sfc /scanfile=<ruta>` | Analiza y repara **un fichero concreto**. |
| `sfc /verifyfile=<ruta>` | Solo verifica un fichero concreto, sin reparar. |

Ejemplos:

```
sfc /verifyonly
sfc /scannow
sfc /verifyfile=C:\Windows\System32\kernel32.dll
```

El análisis completo puede tardar varios minutos. No hay que cerrar la ventana hasta que termine.

### Interpretar el resultado

Al terminar, SFC muestra uno de estos tres resultados:

| Resultado | Significado | Qué hacer |
| :--- | :--- | :--- |
| No encontró infracciones de integridad | Todos los ficheros protegidos coinciden con su copia de referencia. | Nada. |
| Encontró ficheros dañados y los reparó | Había diferencias y se han restaurado. | Revisar el log para saber cuáles. |
| Encontró ficheros dañados y no pudo repararlos | El almacén de componentes también está dañado. | Usar DISM (apartado 3) y repetir SFC. |

### Ver qué ficheros se han detectado

SFC guarda el detalle en `C:\Windows\Logs\CBS\CBS.log`, que es muy extenso. Para quedarnos solo con las líneas de SFC (marcadas con `[SR]`) y guardarlas en un fichero del escritorio, desde **CMD**:

```
findstr /c:"[SR]" %windir%\Logs\CBS\CBS.log > "%userprofile%\Desktop\sfclogs.txt"
```

---

## 3. DISM

DISM tiene tres niveles de comprobación, de menor a mayor profundidad:

| Comando | Qué hace | Repara |
| :--- | :--- | :---: |
| `DISM /Online /Cleanup-Image /CheckHealth` | Comprobación rápida: solo consulta si ya hay daños **marcados** en el almacén. | No |
| `DISM /Online /Cleanup-Image /ScanHealth` | Análisis completo del almacén. Tarda más. | No |
| `DISM /Online /Cleanup-Image /RestoreHealth` | Analiza y **repara** el almacén descargando los componentes buenos desde Windows Update. | Sí |

> Con `/Online` indicamos que trabaje sobre el sistema que está en ejecución.

### Reparar usando un origen local (ISO o DVD de Windows)

Si el equipo no tiene acceso a Windows Update, se puede indicar un origen como una iso que sepamos que es segura con `/Source`.

> Con `/LimitAccess` evitamos que intente contactar con Windows Update:

```
DISM /Online /Cleanup-Image /RestoreHealth /Source:wim:D:\sources\install.wim:1 /LimitAccess
```

Aquí `D:` es la unidad donde está montado el ISO y `1` es el índice de la edición de Windows dentro de la imagen. Para consultar los índices disponibles:

```
DISM /Get-WimInfo /WimFile:D:\sources\install.wim
```

> Si el ISO trae un `install.esd` en lugar de `install.wim`, se usa `esd:` en lugar de `wim:`.

DISM registra su actividad en `C:\Windows\Logs\DISM\dism.log`.

---

## 4. Orden recomendado de uso

El orden de uso recomensado es:

1. Usar sfc para tratar de reparar daños.
2. Si sfc encuentra daños y no logra repararlos, usar dism.
3. Volver a correr sfc.

Tras reparar con DISM conviene reiniciar el equipo antes de volver a ejecutar SFC.
