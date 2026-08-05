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

# CODICE FISCALE DELL'AMMINISTRATORE (Modifica con il tuo Codice Fiscale reale)
ADMIN_CF = os.getenv("ADMIN_CF", "BRNFRC04E27C351V")

@app.on_event("startup")
def startup():
    init_db()

# --- PAGINA PRINCIPALE / LOGIN ---
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    user = request.session.get("user")
    if user:
        return RedirectResponse(url="/prenota", status_code=303)
    return templates.TemplateResponse(request=request, name="login.html", context={"error": None})

@app.post("/login")
def login(request: Request, nome: str = Form(...), cognome: str = Form(...), password: str = Form(...)):
    with engine.begin() as conn:
        res = conn.execute(
            text("SELECT id, nome, cognome, codice_fiscale, password_salt, password_hash, COALESCE(bannato, false) FROM utenti WHERE UPPER(nome) = :n AND UPPER(cognome) = :c"),
            {"n": nome.strip().upper(), "c": cognome.strip().upper()}
        ).fetchone()
        
        if res:
            if res[6]:  # Utente Bannato
                return templates.TemplateResponse(request=request, name="login.html", context={"error": "Account disabilitato. Contatta l'amministrazione."})
            
            if logic.verifica_password(password, res[4], res[5]):
                request.session["user"] = {"id": str(res[0]), "nome": str(res[1]), "cognome": str(res[2]), "cf": str(res[3])}
                return RedirectResponse(url="/prenota", status_code=303)
            
    return templates.TemplateResponse(request=request, name="login.html", context={"error": "Credenziali non valide o utente non trovato."})

# --- PAGINA REGISTRAZIONE ---
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
        return templates.TemplateResponse(
            request=request, 
            name="register.html", 
            context={"error": "Le password non coincidono."}
        )
    
    valido, msg = logic.valida_codice_fiscale(nome, cognome, cf)
    if not valido:
        return templates.TemplateResponse(
            request=request, 
            name="register.html", 
            context={"error": msg}
        )

    salt, pwd_hash = logic.hash_password(password)
    data_reg = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO utenti (nome, cognome, codice_fiscale, password_salt, password_hash, data_registrazione) VALUES (:n, :c, :cf, :s, :h, :d)"),
                {"n": nome.strip().title(), "c": cognome.strip().title(), "cf": cf.strip().upper(), "s": salt, "h": pwd_hash, "d": data_reg}
            )
        return templates.TemplateResponse(
            request=request, 
            name="login.html", 
            context={"success": "Registrazione completata! Ora puoi effettuare il login."}
        )
    except Exception:
        return templates.TemplateResponse(
            request=request, 
            name="register.html", 
            context={"error": "Codice Fiscale già registrato."}
        )

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)

# --- PAGINA PRENOTAZIONE ---
@app.get("/prenota", response_class=HTMLResponse)
def prenota_page(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(request=request, name="prenota.html", context={"user": user})

@app.post("/prenota")
def effettua_prenotazione(request: Request, trattamento: str = Form(...), data: str = Form(...), ora: str = Form(...)):
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/", status_code=303)

    nome_completo = f"{user['nome']} {user['cognome']}"
    data_creazione = logic.get_current_time_local().strftime("%Y-%m-%d %H:%M:%S")

    with engine.begin() as conn:
        occupati = [r[0] for r in conn.execute(text("SELECT ora FROM prenotazioni WHERE data = :d"), {"d": data}).fetchall()]
        if ora in occupati:
            return templates.TemplateResponse("prenota.html", {
                "request": request, "user": user, "error": "Spiacenti, questo orario è stato appena prenotato da qualcun altro!"
            })

        conn.execute(
            text("INSERT INTO prenotazioni (nome, data, ora, trattamento, data_creazione, codice_fiscale) VALUES (:n, :d, :o, :t, :dc, :cf)"),
            {"n": nome_completo, "d": data, "o": ora, "t": trattamento, "dc": data_creazione, "cf": user['cf']}
        )

    return templates.TemplateResponse(request=request, name="prenota.html", context={
        "user": user,
        "success": f"Prenotazione confermata per il {data} alle ore {ora}!",
        "ultimo_trattamento": trattamento,
        "ultima_data": data,
        "ultima_ora": ora
    })

# --- API ORARI DISPONIBILI (CON GESTIONE BLOCCAGGI ADMIN) ---
@app.get("/api/orari")
def get_orari_disponibili(data: str):
    try:
        dt = datetime.strptime(data, "%Y-%m-%d")
    except ValueError:
        return JSONResponse({"orari": []})

    with engine.begin() as conn:
        giorno_bloccato = conn.execute(text("SELECT id FROM blocchi WHERE data = :d AND ora IS NULL"), {"d": data}).fetchone()
        if giorno_bloccato:
            return JSONResponse({"orari": []})

        orari_bloccati = [r[0] for r in conn.execute(text("SELECT ora FROM blocchi WHERE data = :d AND ora IS NOT NULL"), {"d": data}).fetchall()]
        prenotati = [r[0] for r in conn.execute(text("SELECT ora FROM prenotazioni WHERE data = :d"), {"d": data}).fetchall()]

    orari_teorici = logic.get_orari_per_data(dt)
    if not orari_teorici:
        return JSONResponse({"orari": []})

    orari_liberi = [o for o in orari_teorici if o not in prenotati and o not in orari_bloccati]
    return JSONResponse({"orari": orari_liberi})

# --- AREA ADMIN DASHBOARD ---
@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    user = request.session.get("user")
    if not user or user.get("cf") != ADMIN_CF:
        return RedirectResponse(url="/", status_code=303)

    with engine.begin() as conn:
        prenotazioni = conn.execute(text("SELECT id, nome, data, ora, trattamento, codice_fiscale, COALESCE(stato, 'confermata') FROM prenotazioni ORDER BY data DESC, ora ASC")).fetchall()
        utenti = conn.execute(text("SELECT id, nome, cognome, codice_fiscale, data_registrazione, COALESCE(bannato, false) FROM utenti ORDER BY nome ASC")).fetchall()
        blocchi = conn.execute(text("SELECT id, data, ora FROM blocchi ORDER BY data DESC")).fetchall()

    return templates.TemplateResponse(request=request, name="admin.html", context={
        "user": user, "prenotazioni": prenotazioni, "utenti": utenti, "blocchi": blocchi
    })

# --- AZIONI ADMIN PRENOTAZIONI ---
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
            conn.execute(text("UPDATE prenotazioni SET stato = :s WHERE id = :id"), {"s": nuovo_stato, "id": id_prenotazione})
    return RedirectResponse(url="/admin", status_code=303)

# --- AZIONI ADMIN BLOCCO CALENDARIO ---
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

# --- AZIONI ADMIN UTENTI ---
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

# --- CHECK-IN QR CODE PAZIENTE (RANGE ±30 MINUTI) ---
@app.get("/checkin", response_class=HTMLResponse)
def checkin_qr(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/", status_code=303)

    now = datetime.now()
    data_oggi = now.strftime("%Y-%m-%d")

    with engine.begin() as conn:
        prenotazioni = conn.execute(
            text("SELECT id, ora FROM prenotazioni WHERE codice_fiscale = :cf AND data = :d"),
            {"cf": user['cf'], "d": data_oggi}
        ).fetchall()

        for p_id, p_ora in prenotazioni:
            try:
                dt_appuntamento = datetime.strptime(f"{data_oggi} {p_ora}", "%Y-%m-%d %H:%M")
                diff_minuti = (now - dt_appuntamento).total_seconds() / 60
                
                if -30 <= diff_minuti <= 30:
                    conn.execute(text("UPDATE prenotazioni SET stato = 'presente' WHERE id = :id"), {"id": p_id})
                    return templates.TemplateResponse(request=request, name="checkin_result.html", context={
                        "success": "Presenza confermata con successo! Buon allenamento!"
                    })
            except Exception:
                continue

    return templates.TemplateResponse(request=request, name="checkin_result.html", context={
        "error": "Nessuna prenotazione valida trovata per l'orario attuale (finestra consentita: ±30 min)."
    })

# --- DOWNLOAD CALENDARIO .ICS ---
@app.get("/download-ics")
def download_ics(trattamento: str, data: str, ora: str):
    ics_content = logic.genera_file_ics(trattamento, data, ora)
    return Response(content=ics_content, media_type="text/calendar", headers={"Content-Disposition": "attachment; filename=appuntamento_pilates.ics"})
