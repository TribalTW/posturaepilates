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
            text("SELECT id, nome, cognome, codice_fiscale, password_salt, password_hash FROM utenti WHERE UPPER(nome) = :n AND UPPER(cognome) = :c"),
            {"n": nome.strip().upper(), "c": cognome.strip().upper()}
        ).fetchone()
        
        if res and logic.verifica_password(password, res[4], res[5]):
            request.session["user"] = {"id": res[0], "nome": res[1], "cognome": res[2], "cf": res[3]}
            return RedirectResponse(url="/prenota", status_code=303)
            
    return templates.TemplateResponse(request=request, name="login.html", context={"error": "Credenziali non valide o utente non trovato."})

# --- PAGINA REGISTRAZIONE (GET) ---
@app.get("/registrati", response_class=HTMLResponse)
def pagina_registrazione(request: Request):
    user = request.session.get("user")
    if user:
        return RedirectResponse(url="/prenota", status_code=303)
    return templates.TemplateResponse(request=request, name="register.html", context={"error": None})

# --- ELABORAZIONE REGISTRAZIONE (POST) ---
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
        # Verifica se l'orario è ancora libero
        occupati = [r[0] for r in conn.execute(text("SELECT ora FROM prenotazioni WHERE data = :d"), {"d": data}).fetchall()]
        if ora in occupati:
            return templates.TemplateResponse("prenota.html", {
                "request": request, "user": user, "error": "Spiacenti, questo orario è stato appena prenotato da qualcun altro!"
            })

        # Salva la prenotazione
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

# --- API ORARI DISPONIBILI ---
@app.get("/api/orari")
def get_orari_disponibili(data: str):
    try:
        dt = datetime.strptime(data, "%Y-%m-%d")
    except ValueError:
        return JSONResponse({"orari": []})

    orari_teorici = logic.get_orari_per_data(dt)
    if not orari_teorici:
        return JSONResponse({"orari": []})

    with engine.begin() as conn:
        prenotati = [r[0] for r in conn.execute(text("SELECT ora FROM prenotazioni WHERE data = :d"), {"d": data}).fetchall()]

    orari_liberi = [o for o in orari_teorici if o not in prenotati]
    return JSONResponse({"orari": orari_liberi})

# --- DOWNLOAD CALENDARIO .ICS ---
@app.get("/download-ics")
def download_ics(trattamento: str, data: str, ora: str):
    ics_content = logic.genera_file_ics(trattamento, data, ora)
    return Response(content=ics_content, media_type="text/calendar", headers={"Content-Disposition": "attachment; filename=appuntamento_pilates.ics"})
