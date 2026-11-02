#!/usr/bin/env python3
"""
Vigia os horários do Metro do Porto (via GTFS) e avisa por email quando a
hora do teu metro muda. Só depende da biblioteca-padrão do Python.

Configuração por variáveis de ambiente (no GitHub Actions, via Secrets):
  Obrigatórias:
    METRO_STOP        nome da paragem, como está no GTFS (ex.: "Fórum Maia")
    METRO_HEADSIGN    destino/sentido (ex.: "Campanhã", "Póvoa de Varzim")
    SMTP_USER, SMTP_PASS, MAIL_TO   (para enviar o email)
  Opcionais:
    METRO_LINE        nº da linha (ex.: "C", "B"); vazio = todas as linhas
    METRO_WINDOW_START / METRO_WINDOW_END   janela de horas (default 07:45–08:45)
    METRO_GTFS_URL    força um URL de GTFS; vazio = descobre na página
    SMTP_HOST, SMTP_PORT, MAIL_FROM
"""
import csv, io, json, os, re, smtplib, sys, zipfile, datetime, unicodedata
import urllib.request
from urllib.parse import urljoin
from email.message import EmailMessage

# ---------- Configuração ----------
PAGE_URL   = os.environ.get("METRO_PAGE_URL", "https://www.metrodoporto.pt/pages/337")
GTFS_URL   = os.environ.get("METRO_GTFS_URL", "").strip()   # vazio = descobre na página
STOP_NAME  = os.environ.get("METRO_STOP", "").strip()       # obrigatório
HEADSIGN   = os.environ.get("METRO_HEADSIGN", "").strip()   # obrigatório
LINE       = os.environ.get("METRO_LINE", "").strip()       # opcional; vazio = todas
WIN_START  = os.environ.get("METRO_WINDOW_START", "07:45")
WIN_END    = os.environ.get("METRO_WINDOW_END", "08:45")
STATE_FILE = os.environ.get("METRO_STATE_FILE", "state.json")

UA = {"User-Agent": "Mozilla/5.0 (metro-watch; +github-actions)"}

def norm(s):
    s = s or ""
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()

def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()

def discover_gtfs_url(page_url):
    html = fetch(page_url).decode("utf-8", "replace")
    m = re.search(r'href="([^"]*gtfs[^"]*\.zip|[^"]*google_transit[^"]*\.zip)"', html, re.I)
    if not m:
        raise RuntimeError("Não encontrei o link do GTFS na página.")
    return urljoin(page_url, m.group(1))

def load_gtfs(data):
    z = zipfile.ZipFile(io.BytesIO(data))
    names = set(z.namelist())
    tables = {}
    for t in ["stops", "routes", "trips", "stop_times", "calendar", "calendar_dates"]:
        fn = t + ".txt"
        if fn in names:
            with z.open(fn) as f:
                tables[t] = list(csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig")))
        else:
            tables[t] = []
    return tables

def to_minutes(hms):
    p = hms.strip().split(":")
    return int(p[0]) * 60 + int(p[1])

def active_services(tables, date):
    ymd = date.strftime("%Y%m%d")
    cols = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
    wd = cols[date.weekday()]
    active = set()
    for row in tables["calendar"]:
        if row.get("start_date","") <= ymd <= row.get("end_date","") and row.get(wd) == "1":
            active.add(row["service_id"])
    for row in tables["calendar_dates"]:
        if row.get("date") == ymd:
            if row.get("exception_type") == "1": active.add(row["service_id"])
            elif row.get("exception_type") == "2": active.discard(row["service_id"])
    return active

def next_weekday(d):
    while d.weekday() >= 5:          # 5=sáb, 6=dom
        d += datetime.timedelta(days=1)
    return d

def stop_matches(stop_name):
    toks = norm(STOP_NAME).split()
    n = norm(stop_name)
    return all(tok in n for tok in toks)

def compute_times(tables):
    ref = next_weekday(datetime.date.today())
    services = active_services(tables, ref)

    route_ids = None
    if LINE:
        route_ids = {r["route_id"] for r in tables["routes"]
                     if norm(r.get("route_short_name","")) == norm(LINE)}

    stop_ids = {s["stop_id"] for s in tables["stops"] if stop_matches(s.get("stop_name",""))}

    def trip_ok(t):
        if t.get("service_id") not in services: return False
        if route_ids is not None and t.get("route_id") not in route_ids: return False
        return norm(HEADSIGN) in norm(t.get("trip_headsign",""))

    trip_ids = {t["trip_id"] for t in tables["trips"] if trip_ok(t)}

    lo, hi = to_minutes(WIN_START), to_minutes(WIN_END)
    times = set()
    for st in tables["stop_times"]:
        if st.get("trip_id") in trip_ids and st.get("stop_id") in stop_ids:
            dep = st.get("departure_time") or st.get("arrival_time")
            if dep and lo <= to_minutes(dep) <= hi:
                times.add(dep[:5])
    return sorted(times), ref.isoformat(), len(stop_ids), len(trip_ids)

def send_email(subject, body):
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    pw   = os.environ.get("SMTP_PASS")
    to   = os.environ.get("MAIL_TO", user)
    frm  = os.environ.get("MAIL_FROM", user)
    if not (user and pw and to):
        print("[sem SMTP configurado — email que seria enviado:]")
        print("ASSUNTO:", subject); print(body); return
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, frm, to
    msg.set_content(body)
    with smtplib.SMTP(host, port, timeout=60) as s:
        s.starttls(); s.login(user, pw); s.send_message(msg)
    print("Email enviado para", to)

def main():
    missing = [k for k, v in {"METRO_STOP": STOP_NAME, "METRO_HEADSIGN": HEADSIGN}.items() if not v]
    if missing:
        sys.exit("Faltam secrets obrigatórios: " + ", ".join(missing))

    url = GTFS_URL or discover_gtfs_url(PAGE_URL)
    print("GTFS:", url)
    tables = load_gtfs(fetch(url))
    times, ref, n_stops, n_trips = compute_times(tables)
    print(f"Data de referência: {ref} | paragens={n_stops} viagens={n_trips}")
    print("Horários encontrados:", times or "(nenhum — verifica METRO_STOP/METRO_LINE/METRO_HEADSIGN)")

    old = None
    if os.path.exists(STATE_FILE):
        try: old = json.load(open(STATE_FILE, encoding="utf-8")).get("times")
        except Exception: old = None

    line_txt = f"linha {LINE}" if LINE else "todas as linhas"
    label = f"{STOP_NAME} → {HEADSIGN} ({line_txt})"

    if old is None:
        send_email(
            f"🚇 Monitor do metro ativo — {STOP_NAME}",
            f"Monitorização configurada para {label}.\n\n"
            f"Horários atuais (janela {WIN_START}–{WIN_END}, dias úteis):\n  "
            + ", ".join(times) + "\n\nVais ser avisado apenas quando mudarem.")
    elif times != old:
        removed = [t for t in old if t not in times]
        added   = [t for t in times if t not in old]
        send_email(
            f"🚇 O horário do teu metro MUDOU — {STOP_NAME}",
            f"{label}\n\n"
            f"Antes: {', '.join(old)}\n"
            f"Agora: {', '.join(times)}\n\n"
            + (f"Saíram: {', '.join(removed)}\n" if removed else "")
            + (f"Novos:  {', '.join(added)}\n" if added else "")
            + f"\n(janela {WIN_START}–{WIN_END}, dias úteis)")
    else:
        print("Sem alterações.")

    json.dump({"stop": STOP_NAME, "headsign": HEADSIGN, "line": LINE,
               "times": times, "ref": ref,
               "updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")},
              open(STATE_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()