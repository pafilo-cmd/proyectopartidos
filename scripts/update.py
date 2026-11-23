#!/usr/bin/env python3
"""Genera docs/data.json: partidos próximos + canal + dial por plataforma.

Fuentes:
  - data/manual.json        partidos metidos a mano (con sus fuentes)
  - TheSportsDB (gratis)    próximos partidos de LaLiga y sus emisiones en España
Cada fuente vota qué canal emite cada partido; el resultado lleva un estado:
  confirmado  (un canal tiene 2 o más fuentes y nadie dice otra cosa)
  probable    (una sola fuente)
  conflicto   (las fuentes dicen canales distintos)

Solo usa la biblioteca estándar. Si una fuente falla, sigue con las demás.
"""
import json
import sys
import time
import unicodedata
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "data.json"
TSDB = "https://www.thesportsdb.com/api/v1/json/123"
LALIGA_ID = "4335"
MADRID = timezone(timedelta(hours=1))  # hora peninsular de invierno; el navegador muestra la hora local igualmente

# Nombre canónico de cada equipo (lo que se muestra) y sus variantes en otras fuentes.
TEAMS = {
    "Alavés": ["alaves", "deportivo alaves"],
    "Athletic Club": ["athletic", "athletic bilbao", "athletic club"],
    "Atlético de Madrid": ["atletico madrid", "atletico de madrid", "atletico"],
    "Barcelona": ["barcelona", "fc barcelona"],
    "Celta": ["celta", "celta vigo", "celta de vigo", "rc celta"],
    "Deportivo": ["deportivo", "deportivo la coruna", "rc deportivo", "depor"],
    "Elche": ["elche", "elche cf"],
    "Espanyol": ["espanyol", "rcd espanyol"],
    "Getafe": ["getafe", "getafe cf"],
    "Girona": ["girona"],
    "Levante": ["levante", "levante ud"],
    "Málaga": ["malaga", "malaga cf"],
    "Mallorca": ["mallorca", "rcd mallorca"],
    "Osasuna": ["osasuna", "ca osasuna"],
    "Racing de Santander": ["racing santander", "racing de santander", "racing"],
    "Rayo Vallecano": ["rayo vallecano", "rayo"],
    "Real Betis": ["real betis", "betis"],
    "Real Madrid": ["real madrid"],
    "Real Oviedo": ["real oviedo", "oviedo"],
    "Real Sociedad": ["real sociedad"],
    "Sevilla": ["sevilla", "sevilla fc"],
    "Valencia": ["valencia", "valencia cf"],
    "Villarreal": ["villarreal", "villarreal cf"],
}


def ascii_low(s):
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower().strip()


ALIAS = {ascii_low(v): k for k, vs in TEAMS.items() for v in vs + [k]}


def team(name):
    return ALIAS.get(ascii_low(name), name.strip())


def channel_id(name):
    """Traduce el nombre de canal que da una fuente al id de diales.json (o None si no es de los nuestros)."""
    n = ascii_low(name)
    if " bar" in n or "hdr" in n or "uhd" in n:  # canales de hostelería o de 4K: no cuentan
        return None
    if "dazn" in n and "laliga" in n.replace(" ", ""):
        return "dazn"
    if "laliga" in n.replace(" ", "") and ("m+" in n or "movistar" in n or "tv" in n):
        return "laliga"
    if n in ("movistar plus+", "movistar plus", "movistar+", "m+"):
        return "mplus"
    return None


def get_json(url, tries=2):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "proyectopartidos/1.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8") or "null")
        except Exception as e:  # noqa: BLE001
            print(f"  aviso: {url} -> {e}", file=sys.stderr)
            time.sleep(2 * (i + 1))
    return None


def from_manual():
    data = json.loads((ROOT / "data" / "manual.json").read_text("utf-8"))
    out = []
    for p in data.get("partidos", []):
        for src in p.get("fuentes", ["manual"]):
            out.append({"fecha": p["fecha"], "local": team(p["local"]), "visitante": team(p["visitante"]),
                        "canales": p.get("canales", []), "fuente": src})
    return out


def from_thesportsdb():
    """Próximos partidos de LaLiga y canales en España. La clave gratuita da pocos resultados: es un voto más, no la base."""
    out = []
    nxt = get_json(f"{TSDB}/eventsnextleague.php?id={LALIGA_ID}") or {}
    for ev in (nxt.get("events") or [])[:15]:
        ts = ev.get("strTimestamp") or ""
        if not ts:
            continue
        fecha = ts if ("+" in ts[10:] or ts.endswith("Z")) else ts + "+00:00"
        tv = get_json(f"{TSDB}/lookuptv.php?id={ev.get('idEvent')}") or {}
        canales = sorted({c for t in (tv.get("tvevent") or [])
                          if ascii_low(t.get("strCountry", "")) in ("spain", "espana")
                          for c in [channel_id(t.get("strChannel", ""))] if c})
        out.append({"fecha": fecha, "local": team(ev.get("strHomeTeam", "")),
                    "visitante": team(ev.get("strAwayTeam", "")), "canales": canales, "fuente": "thesportsdb"})
        time.sleep(2.5)  # la clave gratuita admite unas 30 peticiones por minuto
    return out


def merge(cands, now):
    groups = {}
    for c in cands:
        try:
            dt = datetime.fromisoformat(c["fecha"].replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt + timedelta(hours=3) < now:
            continue
        key = (ascii_low(c["local"]), ascii_low(c["visitante"]), dt.astimezone(MADRID).date().isoformat())
        groups.setdefault(key, []).append((dt, c))
    partidos, avisos = [], []
    for key, items in groups.items():
        votos, fuentes, fechas = {}, set(), {}
        con_canal = []
        for dt, c in items:
            fuentes.add(c["fuente"])
            fechas[dt] = fechas.get(dt, 0) + 1
            if c["canales"]:
                con_canal.append(frozenset(c["canales"]))
                for ch in c["canales"]:
                    votos.setdefault(ch, set()).add(c["fuente"])
        fecha = max(fechas, key=lambda d: (fechas[d], d))
        if not votos:
            canales, estado = [], "sin canal"
        else:
            top = max(len(v) for v in votos.values())
            canales = sorted(votos, key=lambda ch: (-len(votos[ch]), ch))
            disjuntos = len(con_canal) > 1 and not frozenset.intersection(*con_canal)
            if disjuntos:
                estado = "conflicto"
                avisos.append(f"{items[0][1]['local']}–{items[0][1]['visitante']}: las fuentes no coinciden en el canal")
            elif top >= 2:
                estado = "confirmado"
            else:
                estado = "probable"
        local, visit = items[0][1]["local"], items[0][1]["visitante"]
        partidos.append({
            "id": f"{key[2]}-{ascii_low(local)[:3]}-{ascii_low(visit)[:3]}".replace(" ", ""),
            "fecha": fecha.astimezone(MADRID).isoformat(), "local": local, "visitante": visit,
            "canales": canales, "fuentes": sorted(fuentes), "estado": estado,
        })
    partidos.sort(key=lambda p: p["fecha"])
    return partidos, avisos


def main():
    now = datetime.now(timezone.utc)
    diales = json.loads((ROOT / "data" / "diales.json").read_text("utf-8"))
    cands = from_manual()
    try:
        cands += from_thesportsdb()
    except Exception as e:  # noqa: BLE001
        print(f"  aviso: TheSportsDB falló: {e}", file=sys.stderr)
    partidos, avisos = merge(cands, now)
    for ch in {c for p in partidos for c in p["canales"]} - set(diales["canales"]):
        avisos.append(f"Canal sin diales: {ch}")
    out = {
        "generado": now.astimezone(MADRID).isoformat(timespec="seconds"),
        "plataformas": diales["plataformas"], "canales": diales["canales"], "fuentes": diales["fuentes"],
        "partidos": partidos, "avisos": avisos,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), "utf-8")
    print(f"{len(partidos)} partidos, {len(avisos)} avisos -> {OUT}")
    for a in avisos:
        print("AVISO:", a)


if __name__ == "__main__":
    main()
