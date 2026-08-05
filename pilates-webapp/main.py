import os
from datetime import datetime
from fastapi import FastAPI, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import text
from db import engine, init_db
import logic

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "super-secret-key-12345"))
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# CREDENZIALI E CODICE FISCALE AMMINISTRATORE
ADMIN_CF = os.getenv("ADMIN_CF", "")
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PWD = os.getenv("ADMIN_PWD", "admin123")

@app.on_event("startup")
def startup():
    init_db()
    queries = [
        "ALTER TABLE prenotazioni ADD COLUMN IF NOT EXISTS nome_2 TEXT",
        "ALTER TABLE prenotazioni ADD COLUMN IF NOT EXISTS codice_fiscale_2 TEXT",
        "ALTER TABLE prenotazioni ADD COLUMN IF NOT EXISTS stato_2 TEXT DEFAULT 'confermata'",
        "ALTER TABLE utenti ADD COLUMN IF NOT EXISTS bannato BOOLEAN DEFAULT false"
    ]
    with engine.connect() as conn:
        for q in queries:
            try:
                conn.execute(text(q))
                conn.commit()
            except Exception:
                pass

# Funzione ausiliaria per verificare se l'utente ha effettivamente usufruito (check-in 'presente') della prova
def utente_ha_usato_prova(cf: str) -> bool:
    with engine.begin() as conn:
        count = conn.execute(
            text("""
                SELECT COUNT(*) FROM prenotazioni 
                WHERE (
                    (UPPER(codice_fiscale) = :cf AND LOWER(stato) = 'presente') 
                    OR 
                    (UPPER(codice_fiscale_2) = :cf AND LOWER(stato_2) = 'presente')
                ) 
                AND LOWER(trattamento) LIKE '%prova%'
            """),
            {"cf": cf.strip().upper()}
        ).scalar()
        return count > 0

# --- LOGIN CLIENTE ---
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    user = request.session.get("user")
    if user:
        if user.get("cf") == ADMIN_CF:
            return RedirectResponse(url="/admin", status_code=303)
        return RedirectResponse(url="/prenota", status_code=303)
    return templates.TemplateResponse(request=request, name="login.html", context={"error": None, "success": None})

@app.post("/login")
def login(request: Request, nome: str = Form(...), cognome: str = Form(...), password: str = Form(...)):
    try:
        with engine.begin() as conn:
            res = conn.execute(
                text("SELECT id, nome, cognome, codice_fiscale, password_salt, password_hash, COALESCE(bannato, false) FROM utenti WHERE UPPER(nome) = :n AND UPPER(cognome) = :c"),
                {"n": nome.strip().upper(), "c": cognome.strip().upper()}
            ).fetchone()
            
            if res:
                if res[6]:
                    return templates.TemplateResponse(request=request, name="login.html", context={"error": "Account disabilitato. Contatta l'amministrazione.", "success": None})
                
                salt, pwd_hash = res[4], res[5]
                if salt and pwd_hash and logic.verifica_password(password, salt, pwd_hash):
                    request.session["user"] = {"id": str(res[0]), "nome": str(res[1]), "cognome": str(res[2]), "cf": str(res[3])}
                    if str(res[3]).upper() == ADMIN_CF.upper():
                        return RedirectResponse(url="/admin", status_code=303)
                    return RedirectResponse(url="/prenota", status_code=303)

    except Exception as e:
        print(f"Errore durante il login: {e}")
        return templates.TemplateResponse(request=request, name="login.html", context={"error": f"Errore di sistema: {e}", "success": None})

    return templates.TemplateResponse(request=request, name="login.html", context={"error": "Credenziali non valide o utente non trovato.", "success": None})

# --- LOGIN ADMIN ---
@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_get(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={
        "open_admin": True,
        "error": None,
        "success": None,
        "admin_error": None
    })

@app.post("/admin/login", response_class=HTMLResponse)
def admin_login_post(request: Request, username: str = Form(""), password: str = Form("")):
    if username and password and username.strip() == ADMIN_USER and password.strip() == ADMIN_PWD:
        request.session["user"] = {
            "id": "0",
            "nome": "Amministratore",
            "cognome": "Studio",
            "cf": ADMIN_CF
        }
        return RedirectResponse(url="/admin", status_code=303)

    return templates.TemplateResponse(request=request, name="login.html", context={
        "error": None,
        "success": None,
        "admin_error": "Username o Password Admin non validi.",
        "open_admin": True
    })

# --- REGISTRAZIONE ---
@app.get("/registrati", response_class=HTMLResponse)
def pagina_registrazione(request: Request):
    user = request.session.get("user")
    if user:
        return RedirectResponse(url="/prenota", status_code=303)
    return templates.TemplateResponse(request=request, name="register.html", context={"error": None})

@app.post("/registrati")
def registrati(
    request: Request, 
    nome: str = Form(...), 
    cognome: str = Form(...), 
    cf: str = Form(...), 
    password: str = Form(...), 
    conferma_password: str = Form(...)
):
    if password != conferma_password:
        return templates.TemplateResponse(request=request, name="register.html", context={"error": "Le password non coincidono."})
    
    valido, msg = logic.valida_codice_fiscale(nome, cognome, cf)
    if not valido:
        return templates.TemplateResponse(request=request, name="register.html", context={"error": msg})

    salt, pwd_hash = logic.hash_password(password)
    data_reg = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO utenti (nome, cognome, codice_fiscale, password_salt, password_hash, data_registrazione, bannato) VALUES (:n, :c, :cf, :s, :h, :d, false)"),
                {"n": nome.strip().title(), "c": cognome.strip().title(), "cf": cf.strip().upper(), "s": salt, "h": pwd_hash, "d": data_reg}
            )
        return templates.TemplateResponse(request=request, name="login.html", context={"success": "Registrazione completata! Ora puoi effettuare il login.", "error": None})
    except Exception as e:
        print(f"Errore registrazione: {e}")
        return templates.TemplateResponse(request=request, name="register.html", context={"error": "Codice Fiscale già registrato."})

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)

# --- PRENOTAZIONI ---
@app.get("/prenota", response_class=HTMLResponse)
def prenota_page(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/", status_code=303)

    ha_usato_prova = utente_ha_usato_prova(user['cf'])

    return templates.TemplateResponse(request=request, name="prenota.html", context={
        "user": user, 
        "ha_usato_prova": ha_usato_prova
    })

@app.post("/prenota")
def effettua_prenotazione(
    request: Request, 
    trattamento: str = Form(...), 
    data: str = Form(...), 
    ora: str = Form(...),
    nome_2: str = Form(None),
    cognome_2: str = Form(None),
    cf_2: str = Form(None)
):
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/", status_code=303)

    ha_usato_prova = utente_ha_usato_prova(user['cf'])

    if "prova" in trattamento.lower() and ha_usato_prova:
        return templates.TemplateResponse(request=request, name="prenota.html", context={
            "user": user, 
            "ha_usato_prova": True,
            "error": "Hai già usufruito della Seduta di Prova (limite massimo: 1 a persona)."
        })

    nome_completo = f"{user['nome']} {user['cognome']}"
    data_creazione = logic.get_current_time_local().strftime("%Y-%m-%d %H:%M:%S")

    nome_completo_2 = None
    cf_2_clean = None

    if "coppia" in trattamento.lower():
        if not nome_2 or not cognome_2 or not cf_2:
            return templates.TemplateResponse(request=request, name="prenota.html", context={
                "user": user, 
                "ha_usato_prova": ha_usato_prova,
                "error": "Per la lezione di coppia è necessario inserire tutti i dati della seconda persona."
            })
        
        valido, msg = logic.valida_codice_fiscale(nome_2.strip(), cognome_2.strip(), cf_2.strip())
        if not valido:
            return templates.TemplateResponse(request=request, name="prenota.html", context={
                "user": user, 
                "ha_usato_prova": ha_usato_prova,
                "error": f"Dati 2° partecipante errati: {msg}"
            })

        nome_completo_2 = f"{nome_2.strip().title()} {cognome_2.strip().title()}"
        cf_2_clean = cf_2.strip().upper()

    # Calcolo posti occupati in tempo reale (Capienza massima = 2 lettini)
    with engine.begin() as conn:
        prenotazioni_esistenti = conn.execute(
            text("SELECT trattamento, COALESCE(stato, 'confermata') FROM prenotazioni WHERE data = :d AND ora = :o"), 
            {"d": data, "o": ora}
        ).fetchall()

        posti_occupati = 0
        for p_trattamento, p_stato in prenotazioni_esistenti:
            if str(p_stato).lower() == 'cancellata':
                continue
            peso = 2 if "coppia" in str(p_trattamento).lower() else 1
            posti_occupati += peso

        posti_richiesti = 2 if "coppia" in trattamento.lower() else 1

        if (posti_occupati + posti_richiesti) > 2:
            return templates.TemplateResponse(request=request, name="prenota.html", context={
                "user": user, 
                "ha_usato_prova": ha_usato_prova,
                "error": "Spiacenti, i lettini per questo orario sono appena stati occupati da un'altra prenotazione!"
            })

        conn.execute(
            text("""
                INSERT INTO prenotazioni 
                (nome, data, ora, trattamento, data_creazione, codice_fiscale, nome_2, codice_fiscale_2, stato, stato_2) 
                VALUES (:n, :d, :o, :t, :dc, :cf, :n2, :cf2, 'confermata', 'confermata')
            """),
            {
                "n": nome_completo, "d": data, "o": ora, "t": trattamento,
                "dc": data_creazione, "cf": user['cf'],
                "n2": nome_completo_2, "cf2": cf_2_clean
            }
        )

    return templates.TemplateResponse(request=request, name="prenota.html", context={
        "user": user,
        "ha_usato_prova": ha_usato_prova,
        "success": f"Prenotazione confermata per il {data} alle ore {ora}!",
        "ultimo_trattamento": trattamento,
        "ultima_data": data,
        "ultima_ora": ora
    })

# --- API ORARI DISPONIBILI ---
@app.get("/api/orari")
def get_orari_disponibili(data: str):
    try:
        dt = datetime.strptime(data, "%Y-%m-%d")
    except ValueError:
        return JSONResponse({"orari": []})

    with engine.begin() as conn:
        # Verifica se l'intera giornata è bloccata
        giorno_bloccato = conn.execute(text("SELECT id FROM blocchi WHERE data = :d AND ora IS NULL"), {"d": data}).fetchone()
        if giorno_bloccato:
            return JSONResponse({"orari": []})

        # Estrae orari bloccati specifici per quel giorno
        orari_bloccati = [r[0] for r in conn.execute(text("SELECT ora FROM blocchi WHERE data = :d AND ora IS NOT NULL"), {"d": data}).fetchall()]
        
        # Estrae le prenotazioni esistenti per calcolare quanti posti sono occupati
        prenotazioni_giorno = conn.execute(
            text("SELECT ora, trattamento, COALESCE(stato, 'confermata') FROM prenotazioni WHERE data = :d"), 
            {"d": data}
        ).fetchall()

    # Calcoliamo i posti occupati per ogni ora (Max 2 posti / 2 lettini)
    posti_occupati_per_ora = {}
    for ora, trattamento, stato in prenotazioni_giorno:
        if stato.lower() == 'cancellata':
            continue
        
        peso = 2 if "coppia" in trattamento.lower() else 1
        posti_occupati_per_ora[ora] = posti_occupati_per_ora.get(ora, 0) + peso

    orari_teorici = logic.get_orari_per_data(dt)
    if not orari_teorici:
        return JSONResponse({"orari": []})

    # Filtra prima gli orari passati tramite la funzione centralizzata in logic.py
    orari_filtrati = logic.get_orari_disponibili_filtrati(data, orari_teorici)

    orari_liberi = []
    for o in orari_filtrati:
        # Salta se l'orario è bloccato dall'admin
        if o in orari_bloccati:
            continue

        # Verifica capienza (massimo 2 posti disponibili in totale per slot)
        posti_occupati = posti_occupati_per_ora.get(o, 0)
        if posti_occupati < 2:
            orari_liberi.append(o)

    return JSONResponse({"orari": orari_liberi})

# --- AZIONI ADMIN ---
@app.get("/admin", response_class=HTMLResponse)
def admin_panel(request: Request, data: str = None):
    user = request.session.get("user")
    if not user or user.get("cf") != ADMIN_CF:
        return RedirectResponse(url="/admin/login", status_code=303)

    if not data:
        data = logic.get_current_time_local().strftime("%Y-%m-%d")

    with engine.begin() as conn:
        prenotazioni = conn.execute(
            text("""
                SELECT id, nome, data, ora, trattamento, codice_fiscale, stato, 
                       nome_2, codice_fiscale_2, stato_2 
                FROM prenotazioni 
                WHERE data = :d 
                ORDER BY ora ASC
            """),
            {"d": data}
        ).fetchall()

        blocchi = conn.execute(text("SELECT id, data, ora FROM blocchi ORDER BY data ASC")).fetchall()
        utenti = conn.execute(text("SELECT id, nome, cognome, codice_fiscale, data_registrazione, COALESCE(bannato, false) FROM utenti")).fetchall()

    return templates.TemplateResponse(request=request, name="admin.html", context={
        "prenotazioni": prenotazioni,
        "blocchi": blocchi,
        "utenti": utenti,
        "data_selezionata": data
    })

@app.post("/admin/prenotazione/elimina")
def elimina_prenotazione(request: Request, id_prenotazione: int = Form(...)):
    user = request.session.get("user")
    if user and user.get("cf") == ADMIN_CF:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM prenotazioni WHERE id = :id"), {"id": id_prenotazione})
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/prenotazione/stato")
def cambia_stato_prenotazione(request: Request, id_prenotazione: int = Form(...), nuovo_stato: str = Form(...)):
    user = request.session.get("user")
    if user and user.get("cf") == ADMIN_CF:
        with engine.begin() as conn:
            conn.execute(text("UPDATE prenotazioni SET stato = :s, stato_2 = :s WHERE id = :id"), {"s": nuovo_stato, "id": id_prenotazione})
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/blocca")
def blocca_orario(request: Request, data: str = Form(...), ora: str = Form(None)):
    user = request.session.get("user")
    if user and user.get("cf") == ADMIN_CF:
        ora_val = ora.strip() if ora and ora.strip() != "" else None
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO blocchi (data, ora) VALUES (:d, :o)"), {"d": data, "o": ora_val})
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/sblocca")
def sblocca_orario(request: Request, id_blocco: int = Form(...)):
    user = request.session.get("user")
    if user and user.get("cf") == ADMIN_CF:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM blocchi WHERE id = :id"), {"id": id_blocco})
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/utente/banna")
def toggle_ban_utente(request: Request, id_utente: int = Form(...), stato_ban: bool = Form(...)):
    user = request.session.get("user")
    if user and user.get("cf") == ADMIN_CF:
        with engine.begin() as conn:
            conn.execute(text("UPDATE utenti SET bannato = :b WHERE id = :id"), {"b": not stato_ban, "id": id_utente})
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/utente/elimina")
def elimina_utente(request: Request, id_utente: int = Form(...)):
    user = request.session.get("user")
    if user and user.get("cf") == ADMIN_CF:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM utenti WHERE id = :id"), {"id": id_utente})
    return RedirectResponse(url="/admin", status_code=303)

# --- CHECK-IN ---
def esegui_checkin_utente(cf: str):
    now = logic.get_current_time_local()
    now_naive = now.replace(tzinfo=None)
    data_oggi = now_naive.strftime("%Y-%m-%d")
    cf_upper = cf.strip().upper()

    with engine.begin() as conn:
        prenotazioni = conn.execute(
            text("""
                SELECT id, ora, COALESCE(stato, 'confermata'), COALESCE(stato_2, 'confermata'), 
                       codice_fiscale, codice_fiscale_2 
                FROM prenotazioni 
                WHERE (UPPER(codice_fiscale) = :cf OR UPPER(codice_fiscale_2) = :cf) AND data = :d
            """),
            {"cf": cf_upper, "d": data_oggi}
        ).fetchall()

        for p_id, p_ora, p_stato, p_stato_2, cf1, cf2 in prenotazioni:
            try:
                ora_pulita = str(p_ora).strip()[:5]
                dt_appuntamento = datetime.strptime(f"{data_oggi} {ora_pulita}", "%Y-%m-%d %H:%M")
                
                diff_minuti = (now_naive - dt_appuntamento).total_seconds() / 60

                if -35 <= diff_minuti <= 35:
                    if cf1 and cf_upper == cf1.strip().upper():
                        if p_stato == 'presente':
                            return True, "Presenza già confermata per la prima persona!"
                        conn.execute(text("UPDATE prenotazioni SET stato = 'presente' WHERE id = :id"), {"id": p_id})
                        return True, "Presenza confermata con successo! Buon allenamento!"
                    
                    elif cf2 and cf_upper == cf2.strip().upper():
                        if p_stato_2 == 'presente':
                            return True, "Presenza già confermata per la seconda persona!"
                        conn.execute(text("UPDATE prenotazioni SET stato_2 = 'presente' WHERE id = :id"), {"id": p_id})
                        return True, "Presenza confermata con successo! Buon allenamento!"
            except Exception:
                continue

    return False, "Nessuna prenotazione a tuo nome trovata per l'orario attuale (finestra consentita: ±30 min)."

@app.get("/checkin", response_class=HTMLResponse)
def checkin_qr_get(request: Request):
    user = request.session.get("user")
    if not user:
        return templates.TemplateResponse(request=request, name="checkin_login.html", context={"error": None})

    successo, messaggio = esegui_checkin_utente(user['cf'])
    context = {"success": messaggio} if successo else {"error": messaggio}
    return templates.TemplateResponse(request=request, name="checkin_result.html", context=context)

@app.post("/checkin", response_class=HTMLResponse)
def checkin_qr_post(
    request: Request,
    nome: str = Form(...),
    cognome: str = Form(...),
    password: str = Form(...)
):
    with engine.begin() as conn:
        res = conn.execute(
            text("SELECT id, nome, cognome, codice_fiscale, password_salt, password_hash, COALESCE(bannato, false) FROM utenti WHERE UPPER(nome) = :n AND UPPER(cognome) = :c"),
            {"n": nome.strip().upper(), "c": cognome.strip().upper()}
        ).fetchone()

        if not res or not logic.verifica_password(password, res[4], res[5]):
            return templates.TemplateResponse(request=request, name="checkin_login.html", context={"error": "Credenziali non valide o utente non trovato."})

        if res[6]:
            return templates.TemplateResponse(request=request, name="checkin_login.html", context={"error": "Account disabilitato. Contatta l'amministrazione."})

        user = {"id": str(res[0]), "nome": str(res[1]), "cognome": str(res[2]), "cf": str(res[3])}
        request.session["user"] = user

    successo, messaggio = esegui_checkin_utente(user['cf'])
    context = {"success": messaggio} if successo else {"error": messaggio}
    return templates.TemplateResponse(request=request, name="checkin_result.html", context=context)

# --- DOWNLOAD CALENDARIO .ICS ---
@app.get("/download-ics")
def download_ics(trattamento: str, data: str, ora: str):
    ics_content = logic.genera_file_ics(trattamento, data, ora)
    return Response(content=ics_content, media_type="text/calendar", headers={"Content-Disposition": "attachment; filename=appuntamento_pilates.ics"})
