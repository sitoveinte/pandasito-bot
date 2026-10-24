#!/usr/bin/env python3
"""Publica los siguientes mensajes de cola.md en el canal de Telegram.

Uso: python3 publicar.py [cuantos]   (por defecto 3)

cola.md: mensajes separados por una línea que solo tenga "---".
Si un mensaje empieza por "FOTO: <url>", se envía como foto con el resto de texto.
El texto admite HTML de Telegram: <b>negrita</b>, <i>cursiva</i>, <a href="url">enlace</a>.
Lo publicado se mueve a publicados.md. Si la cola se vacía y REPETIR es True,
se recicla publicados.md.
"""
import html, json, os, re, sys, time, urllib.parse, urllib.request
from datetime import datetime

CHAT_ID = "-1002248604842"
REPETIR = True
# Si la cola se vacía, se rellena con los productos del spreadsheet (de arriba abajo,
# en cada fila primero el de la izquierda y luego el de la derecha).
SHEET_ID = "1EgXJVOilSzZ4A89awTh8A6BrmhPg0Msrum-asCUZ-eE"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit?usp=sharing"
REGISTRO_URL = "https://www.usfans.com/register?ref=6T2VKE"
# Enlace del encabezado de cada post (la spreadsheet de USFans de jjsito).
# Mientras no haya otro, apunta al Google Sheet.
SPREADSHEET_LINK = SHEET_URL
# Foto QC real del almacén de USFans (si el producto tiene); si no, la foto del spreadsheet.
USAR_QC = True
# Fotos QC que manda jjsito para productos sin QC en USFans: qc/<ID de USFans>.jpg
QC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qc")
PAUSA_SEG = 60  # separación entre los mensajes de una misma tanda
DIR = os.path.dirname(os.path.abspath(__file__))
COLA = os.path.join(DIR, "cola.md")
PUBLICADOS = os.path.join(DIR, "publicados.md")
LOG = os.path.join(DIR, "registro.log")
SEP = "\n---\n"


def leer(path):
    if not os.path.exists(path):
        return []
    txt = open(path, encoding="utf-8").read().replace("\r\n", "\n")
    # quita la cabecera de instrucciones (líneas que empiezan por //) del primer bloque
    bloques = [b.strip() for b in ("\n" + txt + "\n").split(SEP)]
    out = []
    for b in bloques:
        lineas = [l for l in b.split("\n") if not l.startswith("//")]
        b = "\n".join(lineas).strip()
        if b:
            out.append(b)
    return out


def escribir(path, bloques, cabecera=""):
    with open(path, "w", encoding="utf-8") as f:
        f.write(cabecera + SEP.join(bloques) + ("\n" if bloques else ""))


def api(metodo, datos, archivos=None):
    """archivos = {nombre_campo: ruta local}; si hay, se sube todo como multipart."""
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    url = f"https://api.telegram.org/bot{token}/{metodo}"
    if archivos:
        limite = "----pandasito" + str(time.time_ns())
        partes = [
            f'--{limite}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
            for k, v in datos.items()
        ]
        for campo, ruta in archivos.items():
            with open(ruta, "rb") as f:
                partes.append(
                    f'--{limite}\r\nContent-Disposition: form-data; name="{campo}"; filename="{campo}.jpg"\r\n'
                    f"Content-Type: image/jpeg\r\n\r\n".encode() + f.read() + b"\r\n"
                )
        partes.append(f"--{limite}--\r\n".encode())
        req = urllib.request.Request(
            url, data=b"".join(partes), headers={"Content-Type": f"multipart/form-data; boundary={limite}"}
        )
    else:
        req = urllib.request.Request(url, data=urllib.parse.urlencode(datos).encode())
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return json.load(e)


def portadas():
    """portadas.json: {ID de USFans: URL o nombre de archivo de la foto que va primero}."""
    try:
        with open(os.path.join(DIR, "portadas.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def fotos_qc(bloque):
    """Fotos QC del producto enlazado en el mensaje, con la portada primero:
    las locales de qc/ (<ID>.jpg, <ID>_2.jpg...) si existen, si no las de USFans."""
    m = re.search(r"usfans\.com/product/\d+/(\d+)", bloque)
    if not m:
        return []
    gid = m.group(1)
    fotos = sorted(
        (os.path.join(QC_DIR, f) for f in os.listdir(QC_DIR) if re.fullmatch(rf"{gid}(_\d+)?\.jpg", f))
        if os.path.isdir(QC_DIR) else [],
        key=lambda r: int(re.search(r"_(\d+)\.jpg$", r).group(1)) if "_" in os.path.basename(r) else 1,
    )
    if not fotos:
        url = f"https://usfans.com/api/goods/estimate-info?goodsId={gid}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                fotos = (json.load(r).get("data") or {}).get("qcImages") or []
        except Exception:
            fotos = []
    portada = portadas().get(gid)
    if portada:
        fotos.sort(key=lambda f: not (f == portada or os.path.basename(f) == portada))
    return fotos[:10]  # máximo de un álbum de Telegram


def enviar_album(fotos, caption):
    media, archivos = [], {}
    for i, f in enumerate(fotos):
        item = {"type": "photo", "media": f}
        if f.startswith("/"):
            archivos[f"f{i}"] = f
            item["media"] = f"attach://f{i}"
        if i == 0:
            item.update(caption=caption, parse_mode="HTML")
        media.append(item)
    r = api("sendMediaGroup", {"chat_id": CHAT_ID, "media": json.dumps(media)}, archivos)
    if r.get("ok"):
        r["result"] = r["result"][0]
    return r


def enviar(bloque):
    datos = {"chat_id": CHAT_ID, "parse_mode": "HTML"}
    foto_sheet = ""
    if bloque.startswith("FOTO:"):
        primera, _, bloque = bloque.partition("\n")
        foto_sheet = primera[5:].strip()
        bloque = bloque.strip()
    qc = fotos_qc(bloque) if USAR_QC else []
    if len(qc) > 1:
        r = enviar_album(qc, bloque)
        if r.get("ok"):
            return r
        log(f"Álbum rechazado ({r.get('description')})")
    for foto in qc[:1] + ([foto_sheet] if foto_sheet else []):
        if foto.startswith("/"):
            r = api("sendPhoto", dict(datos, caption=bloque), {"photo": foto})
        else:
            r = api("sendPhoto", dict(datos, photo=foto, caption=bloque))
        if r.get("ok"):
            return r
        log(f"Foto rechazada ({r.get('description')})")
    log("Se envía solo el texto")
    datos.update(text=bloque, disable_web_page_preview="false")
    return api("sendMessage", datos)


def descargar_sheet():
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/htmlview/sheet?headers=false&gid=0"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def url_real(href):
    href = html.unescape(href)
    if "google.com/url" in href:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("q")
        if q:
            return q[0]
    return href


def celdas(fila_html):
    out = []
    for m in re.finditer(r"<td\b([^>]*)>(.*?)</td>", fila_html, re.S):
        attrs, cont = m.group(1), m.group(2)
        span = re.search(r'colspan="(\d+)"', attrs)
        href = re.search(r'<a\b[^>]*href="([^"]+)"', cont)
        img = re.search(r'<img\b[^>]*src="([^"]+)"', cont)
        texto = html.unescape(re.sub(r"<[^>]+>", " ", cont))
        celda = {
            "texto": re.sub(r"\s+", " ", texto).strip(),
            "link": url_real(href.group(1)) if href else "",
            "img": html.unescape(img.group(1)) if img else "",
        }
        out += [celda] + [{"texto": "", "link": "", "img": ""}] * (int(span.group(1)) - 1 if span else 0)
    return out


def producto(grupo):
    """grupo = 5 celdas: nombre, LINK, (foto), precio, (foto)."""
    if len(grupo) < 4:
        return None
    nombre, precio = grupo[0]["texto"], grupo[3]["texto"]
    link = grupo[1]["link"] or grupo[0]["link"]
    foto = next((c["img"] for c in grupo if c["img"]), "")
    if not nombre or not link or not precio or precio.upper().startswith("X"):
        return None
    return {"nombre": nombre, "precio": precio, "link": link, "foto": foto}


def formatear(p):
    e = html.escape
    texto = (
        f'🎖 <a href="{e(SPREADSHEET_LINK)}">PANDASITO_ SPREADSHEET</a> 🎖\n'
        f"🔎 <b><i>NOMBRE DEL ARTÍCULO: {e(p['nombre'].upper())}</i></b>\n"
        f"💶 <b><i>PRECIO: {e(p['precio'])}</i></b>\n"
        f'🛒 <a href="{e(p["link"])}">LINK DE USFANS</a>\n\n'
        f'🎰 <a href="{e(REGISTRO_URL)}"><b>PINCHA AQUÍ Y OBTÉN 40% DE DESCUENTO EN TU PRIMER ENVÍO Y +400€ EN CUPONES</b></a> 🎰'
    )
    return (f"FOTO: {p['foto']}\n" if p["foto"] else "") + texto


def productos_del_sheet(contenido):
    # solo la primera hoja (Hoja 1)
    tabla = re.search(r"<table\b.*?</table>", contenido, re.S)
    filas = re.findall(r"<tr\b[^>]*>(.*?)</tr>", tabla.group(0) if tabla else "", re.S)
    vistos, out = set(), []
    for f in filas:
        cs = celdas(f)  # el número de fila va en <th>, así que no cuenta
        for grupo in (cs[0:5], cs[5:10]):
            p = producto(grupo)
            if p and (p["nombre"], p["link"]) not in vistos:
                vistos.add((p["nombre"], p["link"]))
                out.append(p)
    return out


def log(msg):
    linea = f"{datetime.now().isoformat(timespec='seconds')} {msg}"
    print(linea)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(linea + "\n")


MENSAJE_DEL_DIA = 2650  # mensaje fijado de registro en USFans; se copia en la primera tanda del día
ESTADO_DIA = os.path.join(DIR, "mensaje-del-dia.json")


def mensaje_del_dia():
    """Antes de los productos de la primera tanda de cada día, vuelve a publicar el mensaje de registro."""
    from zoneinfo import ZoneInfo
    hoy = datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()
    try:
        with open(ESTADO_DIA, encoding="utf-8") as f:
            if json.load(f).get("fecha") == hoy:
                return
    except (OSError, ValueError):
        pass
    r = api("copyMessage", {"chat_id": CHAT_ID, "from_chat_id": CHAT_ID, "message_id": MENSAJE_DEL_DIA})
    log(f"Mensaje del día: {'OK message_id=' + str(r['result']['message_id']) if r.get('ok') else 'ERROR ' + str(r.get('description'))}")
    with open(ESTADO_DIA, "w", encoding="utf-8") as f:
        json.dump({"fecha": hoy}, f)
    time.sleep(PAUSA_SEG)


def main():
    if not os.environ.get("TELEGRAM_BOT_TOKEN") and sys.argv[1:] != ["--vista-previa"]:
        log("ERROR: falta TELEGRAM_BOT_TOKEN en el entorno")
        sys.exit(1)
    if sys.argv[1:] == ["--vista-previa"]:
        contenido = descargar_sheet()
        os.makedirs(os.path.join(DIR, "_debug"), exist_ok=True)
        with open(os.path.join(DIR, "_debug", "hoja1.html"), "w", encoding="utf-8") as f:
            f.write(contenido)
        ps = productos_del_sheet(contenido)
        with open(os.path.join(DIR, "vista-previa.md"), "w", encoding="utf-8") as f:
            f.write(f"{len(ps)} productos leídos del spreadsheet\n\n" + SEP.join(formatear(p) for p in ps) + "\n")
        log(f"Vista previa: {len(ps)} productos ({sum(1 for p in ps if p['foto'])} con foto)")
        return
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    mensaje_del_dia()
    cabecera = open(COLA, encoding="utf-8").read().split("\n")
    cabecera = "".join(l + "\n" for l in cabecera if l.startswith("//"))
    cola, publicados = leer(COLA), leer(PUBLICADOS)
    if len(cola) < n and SHEET_ID:
        try:
            nuevos = [formatear(p) for p in productos_del_sheet(descargar_sheet())]
            log(f"Cola rellenada con {len(nuevos)} productos del spreadsheet")
            cola, publicados = cola + nuevos, []
        except Exception as ex:
            log(f"ERROR leyendo el spreadsheet: {ex}")
    if len(cola) < n and REPETIR and publicados:
        cola, publicados = cola + publicados, []
    if not cola:
        log("Cola vacía, no se publica nada")
        return
    for i, bloque in enumerate(cola[:n]):
        if i:
            time.sleep(PAUSA_SEG)
        r = enviar(bloque)
        if r.get("ok"):
            log(f"OK message_id={r['result']['message_id']}: {bloque[:50]!r}")
            publicados.append(bloque)
        else:
            log(f"ERROR {r.get('description')}: {bloque[:50]!r}")
            publicados.append(bloque)  # no bloquear la cola con un mensaje roto
    escribir(COLA, cola[n:], cabecera)
    escribir(PUBLICADOS, publicados)


if __name__ == "__main__":
    main()
