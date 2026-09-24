import os
from datetime import datetime, timedelta
import random

from fastapi import FastAPI, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional

from db import engine, init_db
import logic


app = FastAPI()

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv(
        "SESSION_SECRET",
        "super-secret-key-12345"
    )
)

app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static"
)

templates = Jinja2Templates(directory="templates")


# ============================================================
# CREDENZIALI ADMIN
# ============================================================

ADMIN_CF = os.getenv("ADMIN_CF")
ADMIN_USER = os.getenv("ADMIN_USER")
ADMIN_PWD = os.getenv("ADMIN_PWD")

if not ADMIN_USER or not ADMIN_PWD:
    raise ValueError(
        "Attenzione: Le credenziali ADMIN_USER e ADMIN_PWD "
        "devono essere configurate nelle variabili d'ambiente (.env)."
    )


# ============================================================
# MODELLI PYDANTIC
# ============================================================

class ClienteCreate(BaseModel):
    nome: str
    email: Optional[str] = None
    data_nascita: Optional[str] = None
    tipo_abbonamento: Optional[str] = None
    sedute_totali: Optional[int] = 0
    sedute_residue: Optional[int] = 0
    note: Optional[str] = None


class ClienteUpdate(BaseModel):
    nome: Optional[str] = None
    email: Optional[str] = None
    data_nascita: Optional[str] = None
    tipo_abbonamento: Optional[str] = None
    sedute_totali: Optional[int] = None
    sedute_residue: Optional[int] = None
    note: Optional[str] = None


class UtenteGestionaleUpdate(BaseModel):
    data_nascita: Optional[str] = None
    luogo_nascita: Optional[str] = None
    luogo_residenza: Optional[str] = None

    telefono: Optional[str] = None
    email: Optional[str] = None
    note: Optional[str] = None

    tipo_abbonamento: Optional[str] = None
    data_inizio_abbonamento: Optional[str] = None
    data_fine_abbonamento: Optional[str] = None

    sedute_totali: Optional[int] = None
    sedute_residue: Optional[int] = None

    pagamento_effettuato: Optional[bool] = None
    metodo_pagamento: Optional[str] = None


class StatoPrenotazioneUpdate(BaseModel):
    partecipante: int
    stato: str


# ============================================================
# DATABASE / MIGRAZIONI
# ============================================================

@app.on_event("startup")
def startup():

    init_db()

    queries = [

        # ----------------------------
        # PRENOTAZIONI
        # ----------------------------

        "ALTER TABLE prenotazioni ADD COLUMN IF NOT EXISTS nome_2 TEXT",

        "ALTER TABLE prenotazioni ADD COLUMN IF NOT EXISTS codice_fiscale_2 TEXT",

        "ALTER TABLE prenotazioni ADD COLUMN IF NOT EXISTS stato_2 TEXT DEFAULT 'confermata'",

        "ALTER TABLE prenotazioni ADD COLUMN IF NOT EXISTS seduta_scalata BOOLEAN DEFAULT false",

        "ALTER TABLE prenotazioni ADD COLUMN IF NOT EXISTS seduta_scalata_2 BOOLEAN DEFAULT false",


        # ----------------------------
        # UTENTI
        # ----------------------------

        "ALTER TABLE utenti ADD COLUMN IF NOT EXISTS bannato BOOLEAN DEFAULT false",

        "ALTER TABLE utenti ADD COLUMN IF NOT EXISTS email TEXT",

        "ALTER TABLE utenti ADD COLUMN IF NOT EXISTS reset_code VARCHAR(6)",

        "ALTER TABLE utenti ADD COLUMN IF NOT EXISTS reset_expires_at TIMESTAMP",


        # ----------------------------
        # DATI GESTIONALI
        # ----------------------------

        "ALTER TABLE utenti ADD COLUMN IF NOT EXISTS data_nascita TEXT",

        "ALTER TABLE utenti ADD COLUMN IF NOT EXISTS luogo_nascita TEXT",

        "ALTER TABLE utenti ADD COLUMN IF NOT EXISTS luogo_residenza TEXT",

        "ALTER TABLE utenti ADD COLUMN IF NOT EXISTS telefono TEXT",

        "ALTER TABLE utenti ADD COLUMN IF NOT EXISTS note TEXT",

        "ALTER TABLE utenti ADD COLUMN IF NOT EXISTS tipo_abbonamento TEXT",

        "ALTER TABLE utenti ADD COLUMN IF NOT EXISTS data_inizio_abbonamento TEXT",

        "ALTER TABLE utenti ADD COLUMN IF NOT EXISTS data_fine_abbonamento TEXT",

        "ALTER TABLE utenti ADD COLUMN IF NOT EXISTS sedute_totali INTEGER DEFAULT 0",

        "ALTER TABLE utenti ADD COLUMN IF NOT EXISTS sedute_residue INTEGER DEFAULT 0",

        "ALTER TABLE utenti ADD COLUMN IF NOT EXISTS pagamento_effettuato BOOLEAN DEFAULT false",

        "ALTER TABLE utenti ADD COLUMN IF NOT EXISTS metodo_pagamento TEXT",


        # ----------------------------
        # VECCHIA TABELLA GESTIONALE
        # ----------------------------

        """
        CREATE TABLE IF NOT EXISTS clienti_gestionale (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            email TEXT,
            data_nascita TEXT,
            tipo_abbonamento TEXT,
            sedute_totali INTEGER DEFAULT 0,
            sedute_residue INTEGER DEFAULT 0,
            note TEXT
        )
        """
    ]

    with engine.connect() as conn:

        for query in queries:

            try:
                conn.execute(text(query))
                conn.commit()

            except Exception as e:
                print(
                    f"Avviso migrazione DB: {e}"
                )


# ============================================================
# FUNZIONE: VERIFICA SE LA PROVA È GIÀ STATA UTILIZZATA
# ============================================================

def utente_ha_usato_prova(cf: str) -> bool:

    with engine.begin() as conn:

        count = conn.execute(
            text("""
                SELECT COUNT(*)
                FROM prenotazioni
                WHERE
                    (
                        (
                            UPPER(codice_fiscale) = :cf
                            AND LOWER(
                                COALESCE(stato, 'confermata')
                            ) = 'presente'
                        )
                        OR
                        (
                            UPPER(codice_fiscale_2) = :cf
                            AND LOWER(
                                COALESCE(stato_2, 'confermata')
                            ) = 'presente'
                        )
                    )
                    AND LOWER(trattamento) LIKE '%prova%'
            """),
            {
                "cf": cf.strip().upper()
            }
        ).scalar()

        return count > 0


# ============================================================
# LOGIN CLIENTE
# ============================================================

@app.get("/", response_class=HTMLResponse)
def index(request: Request):

    user = request.session.get("user")

    if user:

        if user.get("cf") == ADMIN_CF:
            return RedirectResponse(
                url="/admin",
                status_code=303
            )

        return RedirectResponse(
            url="/prenota",
            status_code=303
        )

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "error": None,
            "success": None,
            "admin_error": None
        }
    )


@app.get("/login", response_class=HTMLResponse)
def login_get(request: Request):

    user = request.session.get("user")

    if user:

        if user.get("cf") == ADMIN_CF:
            return RedirectResponse(
                url="/admin",
                status_code=303
            )

        return RedirectResponse(
            url="/prenota",
            status_code=303
        )

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "error": None,
            "success": None,
            "admin_error": None
        }
    )


@app.post("/login")
def login(
    request: Request,
    nome: str = Form(...),
    cognome: str = Form(...),
    password: str = Form(...)
):

    nome_clean = nome.strip().upper()
    cognome_clean = cognome.strip().upper()

    try:

        with engine.connect() as conn:

            res = conn.execute(
                text("""
                    SELECT
                        id,
                        nome,
                        cognome,
                        codice_fiscale,
                        password_salt,
                        password_hash,
                        COALESCE(bannato, false)
                    FROM utenti
                    WHERE
                        UPPER(nome) = :n
                        AND UPPER(cognome) = :c
                """),
                {
                    "n": nome_clean,
                    "c": cognome_clean
                }
            ).fetchone()

        if not res:

            return templates.TemplateResponse(
                request=request,
                name="login.html",
                context={
                    "error":
                        "Utente non trovato. Controlla nome e cognome.",
                    "admin_error": None
                }
            )

        (
            user_id,
            db_nome,
            db_cognome,
            db_cf,
            salt,
            pwd_hash,
            bannato
        ) = res

        if bannato:

            return templates.TemplateResponse(
                request=request,
                name="login.html",
                context={
                    "error":
                        "Il tuo account è stato bannato. "
                        "Contatta l'amministrazione.",
                    "admin_error": None
                }
            )

        if not logic.verifica_password(
            password,
            salt,
            pwd_hash
        ):

            return templates.TemplateResponse(
                request=request,
                name="login.html",
                context={
                    "error": "Password errata.",
                    "admin_error": None
                }
            )

        request.session["user"] = {
            "id": str(user_id),
            "nome": db_nome,
            "cognome": db_cognome,
            "cf": db_cf
        }

        return RedirectResponse(
            url="/prenota",
            status_code=303
        )

    except Exception as e:

        print(f"Errore login: {e}")

        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "error":
                    f"Errore durante il login: {str(e)}",
                "admin_error": None
            }
        )


# ============================================================
# RECUPERO PASSWORD
# ============================================================

@app.get(
    "/recupero-password",
    response_class=HTMLResponse
)
def recupero_password_get(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="recupero_password.html",
        context={
            "error": None,
            "success": None
        }
    )


@app.post(
    "/recupero-password",
    response_class=HTMLResponse
)
def recupero_password_post(
    request: Request,
    nome: str = Form(...),
    cognome: str = Form(...),
    codice_fiscale: str = Form(...),
    nuova_password: str = Form(...)
):

    nome_clean = nome.strip().upper()
    cognome_clean = cognome.strip().upper()
    cf_clean = codice_fiscale.strip().upper()

    with engine.begin() as conn:

        res = conn.execute(
            text("""
                SELECT id
                FROM utenti
                WHERE
                    UPPER(nome) = :n
                    AND UPPER(cognome) = :c
                    AND UPPER(codice_fiscale) = :cf
            """),
            {
                "n": nome_clean,
                "c": cognome_clean,
                "cf": cf_clean
            }
        ).fetchone()

        if not res:

            return templates.TemplateResponse(
                request=request,
                name="recupero_password.html",
                context={
                    "error":
                        "I dati inseriti non corrispondono "
                        "a nessun utente registrato nel sistema.",
                    "success": None
                }
            )

        salt, pwd_hash = logic.hash_password(
            nuova_password
        )

        conn.execute(
            text("""
                UPDATE utenti
                SET
                    password_salt = :s,
                    password_hash = :h
                WHERE
                    UPPER(codice_fiscale) = :cf
            """),
            {
                "s": salt,
                "h": pwd_hash,
                "cf": cf_clean
            }
        )

    return RedirectResponse(
        url="/login?success=password_aggiornata",
        status_code=303
    )


# ============================================================
# LOGIN ADMIN
# ============================================================

@app.get(
    "/admin/login",
    response_class=HTMLResponse
)
def admin_login_get(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "open_admin": True,
            "error": None,
            "success": None,
            "admin_error": None
        }
    )


@app.post(
    "/admin/login",
    response_class=HTMLResponse
)
def admin_login_post(
    request: Request,
    username: str = Form(""),
    password: str = Form("")
):

    if (
        username
        and password
        and username.strip() == ADMIN_USER
        and password.strip() == ADMIN_PWD
    ):

        request.session["user"] = {
            "id": "0",
            "nome": "Amministratore",
            "cognome": "Studio",
            "cf": ADMIN_CF or "ADMIN_CF_PLACEHOLDER"
        }

        return RedirectResponse(
            url="/admin",
            status_code=303
        )

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "error": None,
            "success": None,
            "admin_error":
                "Username o Password Admin non validi.",
            "open_admin": True
        }
    )


# ============================================================
# REGISTRAZIONE
# ============================================================

@app.get(
    "/registrati",
    response_class=HTMLResponse
)
def pagina_registrazione(request: Request):

    user = request.session.get("user")

    if user:
        return RedirectResponse(
            url="/prenota",
            status_code=303
        )

    return templates.TemplateResponse(
        request=request,
        name="register.html",
        context={
            "error": None
        }
    )


@app.post("/registrati")
def registrati(
    request: Request,
    nome: str = Form(...),
    cognome: str = Form(...),
    codice_fiscale: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    conferma_password: str = Form(...)
):

    if password != conferma_password:

        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={
                "error":
                    "Le password non coincidono."
            }
        )

    valido, msg = logic.valida_codice_fiscale(
        nome,
        cognome,
        codice_fiscale
    )

    if not valido:

        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={
                "error": msg
            }
        )

    salt, pwd_hash = logic.hash_password(
        password
    )

    data_reg = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    cf_clean = codice_fiscale.strip().upper()

    try:

        with engine.begin() as conn:

            conn.execute(
                text("""
                    INSERT INTO utenti
                    (
                        nome,
                        cognome,
                        codice_fiscale,
                        password_salt,
                        password_hash,
                        data_registrazione,
                        bannato,
                        email
                    )
                    VALUES
                    (
                        :n,
                        :c,
                        :cf,
                        :s,
                        :h,
                        :d,
                        false,
                        :e
                    )
                """),
                {
                    "n": nome.strip().title(),
                    "c": cognome.strip().title(),
                    "cf": cf_clean,
                    "s": salt,
                    "h": pwd_hash,
                    "d": data_reg,
                    "e": email.strip().lower()
                }
            )

            res_user = conn.execute(
                text("""
                    SELECT id
                    FROM utenti
                    WHERE codice_fiscale = :cf
                """),
                {
                    "cf": cf_clean
                }
            ).fetchone()

            user_id = (
                str(res_user[0])
                if res_user
                else "0"
            )

        request.session["user"] = {
            "id": user_id,
            "nome": nome.strip().title(),
            "cognome": cognome.strip().title(),
            "cf": cf_clean
        }

        return RedirectResponse(
            url="/prenota",
            status_code=303
        )

    except Exception as e:

        print(f"Errore registrazione: {e}")

        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={
                "error":
                    "Codice Fiscale già registrato "
                    "o email già in uso."
            }
        )


@app.get("/logout")
def logout(request: Request):

    request.session.clear()

    return RedirectResponse(
        url="/",
        status_code=303
    )


# ============================================================
# PRENOTAZIONI
# ============================================================

@app.get(
    "/prenota",
    response_class=HTMLResponse
)
def prenota_page(request: Request):

    user = request.session.get("user")

    if not user:
        return RedirectResponse(
            url="/",
            status_code=303
        )

    ha_usato_prova = utente_ha_usato_prova(
        user["cf"]
    )

    return templates.TemplateResponse(
        request=request,
        name="prenota.html",
        context={
            "user": user,
            "ha_usato_prova": ha_usato_prova
        }
    )


@app.post("/prenota")
def effettua_prenotazione(
    request: Request,
    trattamento: str = Form(None),
    data: str = Form(None),
    ora: str = Form(None),
    nome_2: str = Form(None),
    cognome_2: str = Form(None),
    cf_2: str = Form(None)
):

    user = request.session.get("user")

    if not user:
        return RedirectResponse(
            url="/",
            status_code=303
        )

    ha_usato_prova = utente_ha_usato_prova(
        user["cf"]
    )

    with engine.begin() as conn:

        is_bannato = conn.execute(
            text("""
                SELECT COALESCE(bannato, false)
                FROM utenti
                WHERE UPPER(codice_fiscale) = :cf
            """),
            {
                "cf": user["cf"].strip().upper()
            }
        ).scalar()

        if is_bannato:

            return templates.TemplateResponse(
                request=request,
                name="prenota.html",
                context={
                    "user": user,
                    "ha_usato_prova": ha_usato_prova,
                    "error":
                        "Il tuo account risulta bannato. "
                        "Impossibile effettuare prenotazioni."
                }
            )

    if not trattamento or not data or not ora:

        return templates.TemplateResponse(
            request=request,
            name="prenota.html",
            context={
                "user": user,
                "ha_usato_prova": ha_usato_prova,
                "error":
                    "Seleziona un trattamento, una data "
                    "e un orario validi prima di procedere."
            }
        )

    try:

        dt_app = datetime.strptime(
            data,
            "%Y-%m-%d"
        )

        giorno_settimana = dt_app.weekday()
        ora_num = int(
            ora.split(":")[0]
        )

        if giorno_settimana == 6:

            return templates.TemplateResponse(
                request=request,
                name="prenota.html",
                context={
                    "user": user,
                    "ha_usato_prova": ha_usato_prova,
                    "error":
                        "La domenica lo studio è chiuso."
                }
            )

        elif giorno_settimana == 5:

            if not (8 <= ora_num <= 13):

                return templates.TemplateResponse(
                    request=request,
                    name="prenota.html",
                    context={
                        "user": user,
                        "ha_usato_prova": ha_usato_prova,
                        "error":
                            "Il sabato è possibile prenotare "
                            "solo dalle 08:00 alle 13:00."
                    }
                )

        else:

            if not (8 <= ora_num <= 19):

                return templates.TemplateResponse(
                    request=request,
                    name="prenota.html",
                    context={
                        "user": user,
                        "ha_usato_prova": ha_usato_prova,
                        "error":
                            "Gli orari consentiti vanno "
                            "dalle 08:00 alle 19:00."
                    }
                )

    except Exception:
        pass

    if (
        "prova" in trattamento.lower()
        and ha_usato_prova
    ):

        return templates.TemplateResponse(
            request=request,
            name="prenota.html",
            context={
                "user": user,
                "ha_usato_prova": True,
                "error":
                    "Hai già usufruito della Seduta di Prova "
                    "(limite massimo: 1 a persona)."
            }
        )

    nome_completo = (
        f"{user['nome']} {user['cognome']}"
    )

    data_creazione = (
        logic.get_current_time_local()
        .strftime("%Y-%m-%d %H:%M:%S")
    )

    nome_completo_2 = None
    cf_2_clean = None

    is_coppia = (
        "coppia" in trattamento.lower()
    )

    if is_coppia:

        if not nome_2 or not cognome_2 or not cf_2:

            return templates.TemplateResponse(
                request=request,
                name="prenota.html",
                context={
                    "user": user,
                    "ha_usato_prova": ha_usato_prova,
                    "error":
                        "Per il Pilates di Coppia è necessario "
                        "inserire tutti i dati della seconda persona."
                }
            )

        valido, msg = logic.valida_codice_fiscale(
            nome_2.strip(),
            cognome_2.strip(),
            cf_2.strip()
        )

        if not valido:

            return templates.TemplateResponse(
                request=request,
                name="prenota.html",
                context={
                    "user": user,
                    "ha_usato_prova": ha_usato_prova,
                    "error":
                        f"Dati 2° partecipante errati: {msg}"
                }
            )

        nome_completo_2 = (
            f"{nome_2.strip().title()} "
            f"{cognome_2.strip().title()}"
        )

        cf_2_clean = cf_2.strip().upper()

    with engine.begin() as conn:

        user_cf = (
            user["cf"].strip().upper()
        )

        gia_prenotato = conn.execute(
            text("""
                SELECT COUNT(*)
                FROM prenotazioni
                WHERE
                    data = :d
                    AND ora = :o
                    AND
                    (
                        UPPER(codice_fiscale) = :cf

                        OR UPPER(codice_fiscale_2) = :cf

                        OR (
                            :cf_2 IS NOT NULL
                            AND
                            (
                                UPPER(codice_fiscale) = :cf_2
                                OR
                                UPPER(codice_fiscale_2) = :cf_2
                            )
                        )
                    )

                    AND NOT (
                        UPPER(codice_fiscale) = :cf
                        AND LOWER(
                            COALESCE(stato, 'confermata')
                        ) = 'cancellata'
                    )

                    AND NOT (
                        UPPER(codice_fiscale_2) = :cf
                        AND LOWER(
                            COALESCE(stato_2, 'confermata')
                        ) = 'cancellata'
                    )
            """),
            {
                "d": data,
                "o": ora,
                "cf": user_cf,
                "cf_2":
                    cf_2_clean
                    if is_coppia
                    else None
            }
        ).scalar()

        if gia_prenotato > 0:

            return templates.TemplateResponse(
                request=request,
                name="prenota.html",
                context={
                    "user": user,
                    "ha_usato_prova": ha_usato_prova,
                    "error":
                        "Risulti già prenotato "
                        "(o inserito come secondo partecipante) "
                        "in questo giorno e orario!"
                }
            )

        prenotazioni_esistenti = conn.execute(
            text("""
                SELECT
                    trattamento,
                    COALESCE(stato, 'confermata')
                FROM prenotazioni
                WHERE
                    data = :d
                    AND ora = :o
            """),
            {
                "d": data,
                "o": ora
            }
        ).fetchall()

        posti_occupati = 0

        for (
            p_trattamento,
            p_stato
        ) in prenotazioni_esistenti:

            if str(p_stato).lower() == "cancellata":
                continue

            peso = (
                2
                if "coppia"
                in str(p_trattamento).lower()
                else 1
            )

            posti_occupati += peso

        posti_richiesti = (
            2
            if is_coppia
            else 1
        )

        if (
            posti_occupati + posti_richiesti
        ) > 2:

            return templates.TemplateResponse(
                request=request,
                name="prenota.html",
                context={
                    "user": user,
                    "ha_usato_prova": ha_usato_prova,
                    "error":
                        "Spiacenti, i lettini per questo orario "
                        "sono esauriti o non sufficienti "
                        "per questa prenotazione!"
                }
            )

        conn.execute(
            text("""
                INSERT INTO prenotazioni
                (
                    nome,
                    data,
                    ora,
                    trattamento,
                    data_creazione,
                    codice_fiscale,
                    nome_2,
                    codice_fiscale_2,
                    stato,
                    stato_2,
                    seduta_scalata,
                    seduta_scalata_2
                )
                VALUES
                (
                    :n,
                    :d,
                    :o,
                    :t,
                    :dc,
                    :cf,
                    :n2,
                    :cf2,
                    'confermata',
                    'confermata',
                    false,
                    false
                )
            """),
            {
                "n": nome_completo,
                "d": data,
                "o": ora,
                "t": trattamento,
                "dc": data_creazione,
                "cf": user["cf"],
                "n2": nome_completo_2,
                "cf2": cf_2_clean
            }
        )

    return templates.TemplateResponse(
        request=request,
        name="prenota.html",
        context={
            "user": user,
            "ha_usato_prova": ha_usato_prova,
            "success":
                f"Prenotazione confermata per il "
                f"{data} alle ore {ora}!",
            "ultimo_trattamento": trattamento,
            "ultima_data": data,
            "ultima_ora": ora
        }
    )


# ============================================================
# API ORARI DISPONIBILI
# ============================================================

@app.get("/api/orari")
def get_orari_disponibili(
    request: Request,
    data: str,
    trattamento: str = ""
):

    try:

        dt = datetime.strptime(
            data,
            "%Y-%m-%d"
        )

    except ValueError:

        return JSONResponse(
            {"orari": []}
        )

    giorno_settimana = dt.weekday()

    if giorno_settimana == 6:

        return JSONResponse(
            {"orari": []}
        )

    elif giorno_settimana == 5:

        orari_teorici = [
            f"{h:02d}:00"
            for h in range(8, 14)
        ]

    else:

        orari_teorici = [
            f"{h:02d}:00"
            for h in range(8, 20)
        ]

    user = request.session.get("user")

    user_cf = (
        user["cf"].strip().upper()
        if user and "cf" in user
        else None
    )

    with engine.begin() as conn:

        giorno_bloccato = conn.execute(
            text("""
                SELECT id
                FROM blocchi
                WHERE
                    data = :d
                    AND ora IS NULL
            """),
            {"d": data}
        ).fetchone()

        if giorno_bloccato:

            return JSONResponse(
                {"orari": []}
            )

        orari_bloccati = [
            r[0]
            for r in conn.execute(
                text("""
                    SELECT ora
                    FROM blocchi
                    WHERE
                        data = :d
                        AND ora IS NOT NULL
                """),
                {"d": data}
            ).fetchall()
        ]

        prenotazioni_giorno = conn.execute(
            text("""
                SELECT
                    ora,
                    trattamento,
                    COALESCE(stato, 'confermata'),
                    codice_fiscale,
                    codice_fiscale_2,
                    COALESCE(stato_2, 'confermata')
                FROM prenotazioni
                WHERE data = :d
            """),
            {"d": data}
        ).fetchall()

    posti_occupati_per_ora = {}
    orari_utente_prenotato = set()

    for (
        ora,
        t_esistente,
        stato,
        cf1,
        cf2,
        stato_2
    ) in prenotazioni_giorno:

        if user_cf:

            is_cf1_match = (
                cf1
                and cf1.strip().upper() == user_cf
                and str(stato).lower()
                != "cancellata"
            )

            is_cf2_match = (
                cf2
                and cf2.strip().upper() == user_cf
                and str(stato_2).lower()
                != "cancellata"
            )

            if (
                is_cf1_match
                or is_cf2_match
            ):
                orari_utente_prenotato.add(
                    ora
                )

        if str(stato).lower() == "cancellata":
            continue

        peso = (
            2
            if "coppia"
            in str(t_esistente).lower()
            else 1
        )

        posti_occupati_per_ora[ora] = (
            posti_occupati_per_ora.get(
                ora,
                0
            )
            + peso
        )

    richiede_due_posti = (
        "coppia"
        in trattamento.lower()
    )

    orari_liberi = []

    for o in orari_teorici:

        if o in orari_bloccati:
            continue

        if (
            user_cf
            and o in orari_utente_prenotato
        ):
            continue

        posti_occupati = (
            posti_occupati_per_ora.get(
                o,
                0
            )
        )

        if richiede_due_posti:

            if posti_occupati == 0:
                orari_liberi.append(o)

        else:

            if posti_occupati < 2:
                orari_liberi.append(o)

    return JSONResponse(
        {"orari": orari_liberi}
    )


# ============================================================
# MIE PRENOTAZIONI
# ============================================================

@app.get("/api/mie-prenotazioni")
def get_mie_prenotazioni(request: Request):

    user = request.session.get("user")

    if not user:

        return JSONResponse(
            {"error": "Non autenticato"},
            status_code=401
        )

    user_cf = (
        user["cf"].strip().upper()
    )

    with engine.begin() as conn:

        prenotazioni = conn.execute(
            text("""
                SELECT
                    id,
                    nome,
                    data,
                    ora,
                    trattamento,
                    codice_fiscale,
                    nome_2,
                    codice_fiscale_2,
                    COALESCE(
                        stato,
                        'confermata'
                    ) AS stato,
                    COALESCE(
                        stato_2,
                        'confermata'
                    ) AS stato_2
                FROM prenotazioni
                WHERE
                    (
                        UPPER(codice_fiscale) = :cf
                        OR
                        UPPER(codice_fiscale_2) = :cf
                    )

                    AND NOT (
                        UPPER(codice_fiscale) = :cf
                        AND LOWER(
                            COALESCE(
                                stato,
                                'confermata'
                            )
                        ) = 'cancellata'
                    )

                    AND NOT (
                        UPPER(codice_fiscale_2) = :cf
                        AND LOWER(
                            COALESCE(
                                stato_2,
                                'confermata'
                            )
                        ) = 'cancellata'
                    )

                ORDER BY
                    data ASC,
                    ora ASC
            """),
            {
                "cf": user_cf
            }
        ).fetchall()

    risultati = []

    for p in prenotazioni:

        (
            id_prenotazione,
            nome,
            data,
            ora,
            trattamento,
            cf1,
            nome_2,
            cf2,
            stato1,
            stato2
        ) = p

        if (
            cf1
            and cf1.strip().upper()
            == user_cf
        ):
            stato_personale = stato1

        else:
            stato_personale = stato2

        risultati.append({
            "id": id_prenotazione,
            "nome": nome,
            "data": data,
            "ora": str(ora)[:5],
            "trattamento": trattamento,
            "stato": stato_personale,
            "is_coppia": bool(nome_2)
        })

    return JSONResponse(
        {
            "prenotazioni": risultati
        }
    )


# ============================================================
# VERIFICA ADMIN
# ============================================================

def verifica_admin(request: Request) -> bool:

    user = request.session.get("user")

    return bool(
        user
        and user.get("cf") == ADMIN_CF
    )


# ============================================================
# API SCHEDA CLIENTE
# ============================================================

@app.get("/api/utente/{utente_id}")
def get_utente_gestionale(
    request: Request,
    utente_id: int
):

    if not verifica_admin(request):

        return JSONResponse(
            {"error": "Non autorizzato"},
            status_code=403
        )

    with engine.connect() as conn:

        utente = conn.execute(
            text("""
                SELECT
                    id,
                    nome,
                    cognome,
                    codice_fiscale,
                    email,
                    data_registrazione,

                    COALESCE(
                        bannato,
                        false
                    ) AS bannato,

                    data_nascita,
                    luogo_nascita,
                    luogo_residenza,
                    telefono,
                    note,

                    tipo_abbonamento,
                    data_inizio_abbonamento,
                    data_fine_abbonamento,

                    COALESCE(
                        sedute_totali,
                        0
                    ) AS sedute_totali,

                    COALESCE(
                        sedute_residue,
                        0
                    ) AS sedute_residue,

                    COALESCE(
                        pagamento_effettuato,
                        false
                    ) AS pagamento_effettuato,

                    metodo_pagamento

                FROM utenti

                WHERE id = :id
            """),
            {
                "id": utente_id
            }
        ).mappings().first()

        if not utente:

            return JSONResponse(
                {"error": "Utente non trovato"},
                status_code=404
            )

        cf = (
            utente["codice_fiscale"]
            or ""
        ).strip().upper()

        prenotazioni_db = conn.execute(
            text("""
                SELECT
                    id,
                    data,
                    ora,
                    trattamento,

                    nome,
                    nome_2,

                    codice_fiscale,
                    codice_fiscale_2,

                    COALESCE(
                        stato,
                        'confermata'
                    ) AS stato_1,

                    COALESCE(
                        stato_2,
                        'confermata'
                    ) AS stato_2,

                    COALESCE(
                        seduta_scalata,
                        false
                    ) AS seduta_scalata_1,

                    COALESCE(
                        seduta_scalata_2,
                        false
                    ) AS seduta_scalata_2

                FROM prenotazioni

                WHERE
                    UPPER(codice_fiscale) = :cf
                    OR
                    UPPER(codice_fiscale_2) = :cf

                ORDER BY
                    data DESC,
                    ora DESC
            """),
            {
                "cf": cf
            }
        ).mappings().all()

    prenotazioni = []

    for p in prenotazioni_db:

        if (
            p["codice_fiscale"]
            and
            p["codice_fiscale"]
            .strip()
            .upper()
            == cf
        ):

            partecipante = 1

            stato = p["stato_1"]

            scalata = bool(
                p["seduta_scalata_1"]
            )

            nome_partecipante = p["nome"]

        elif (
            p["codice_fiscale_2"]
            and
            p["codice_fiscale_2"]
            .strip()
            .upper()
            == cf
        ):

            partecipante = 2

            stato = p["stato_2"]

            scalata = bool(
                p["seduta_scalata_2"]
            )

            nome_partecipante = p["nome_2"]

        else:
            continue

        trattamento = str(
            p["trattamento"] or ""
        )

        is_prova = (
            "prova"
            in trattamento.lower()
        )

        puo_scalare = (
            str(stato).lower()
            == "presente"

            and not is_prova

            and not scalata

            and int(
                utente["sedute_residue"]
                or 0
            ) > 0
        )

        prenotazioni.append({
            "id": p["id"],

            "data": p["data"],

            "ora": str(
                p["ora"]
            )[:5],

            "trattamento":
                trattamento,

            "partecipante":
                partecipante,

            "nome_partecipante":
                nome_partecipante,

            "stato":
                stato,

            "seduta_scalata":
                scalata,

            "is_prova":
                is_prova,

            "puo_scalare":
                puo_scalare
        })

    sedute_totali = int(
        utente["sedute_totali"]
        or 0
    )

    sedute_residue = int(
        utente["sedute_residue"]
        or 0
    )

    return {
        "utente": dict(utente),

        "riepilogo": {
            "sedute_totali":
                sedute_totali,

            "sedute_residue":
                sedute_residue,

            "sedute_utilizzate":
                max(
                    0,
                    sedute_totali
                    - sedute_residue
                )
        },

        "prenotazioni":
            prenotazioni
    }


# ============================================================
# AGGIORNAMENTO DATI CLIENTE
# ============================================================

@app.put("/api/utente/{utente_id}")
def aggiorna_utente_gestionale(
    request: Request,
    utente_id: int,
    dati: UtenteGestionaleUpdate
):

    if not verifica_admin(request):

        return JSONResponse(
            {"error": "Non autorizzato"},
            status_code=403
        )

    if (
        dati.sedute_totali is not None
        and dati.sedute_totali < 0
    ):

        return JSONResponse(
            {
                "error":
                    "Il numero di sedute totali "
                    "non può essere negativo."
            },
            status_code=400
        )

    if (
        dati.sedute_residue is not None
        and dati.sedute_residue < 0
    ):

        return JSONResponse(
            {
                "error":
                    "Il numero di sedute residue "
                    "non può essere negativo."
            },
            status_code=400
        )

    if (
        dati.sedute_totali is not None
        and dati.sedute_residue is not None
        and dati.sedute_residue
        > dati.sedute_totali
    ):

        return JSONResponse(
            {
                "error":
                    "Le sedute residue non possono "
                    "superare quelle totali."
            },
            status_code=400
        )

    with engine.begin() as conn:

        esiste = conn.execute(
            text("""
                SELECT
                    id,

                    COALESCE(
                        sedute_totali,
                        0
                    ) AS sedute_totali,

                    COALESCE(
                        sedute_residue,
                        0
                    ) AS sedute_residue,

                    COALESCE(
                        pagamento_effettuato,
                        false
                    ) AS pagamento_effettuato,

                    metodo_pagamento

                FROM utenti

                WHERE id = :id
            """),
            {
                "id": utente_id
            }
        ).mappings().first()

        if not esiste:

            return JSONResponse(
                {"error": "Utente non trovato"},
                status_code=404
            )

        sedute_totali = (
            dati.sedute_totali
            if dati.sedute_totali is not None
            else esiste["sedute_totali"]
        )

        sedute_residue = (
            dati.sedute_residue
            if dati.sedute_residue is not None
            else esiste["sedute_residue"]
        )

        pagamento = (
            dati.pagamento_effettuato
            if dati.pagamento_effettuato
            is not None
            else esiste[
                "pagamento_effettuato"
            ]
        )

        metodo_pagamento = (
            dati.metodo_pagamento
            if dati.metodo_pagamento is not None
            else esiste[
                "metodo_pagamento"
            ]
        )

        if (
            sedute_residue
            > sedute_totali
        ):

            return JSONResponse(
                {
                    "error":
                        "Le sedute residue non possono "
                        "superare quelle totali."
                },
                status_code=400
            )

        conn.execute(
            text("""
                UPDATE utenti
                SET

                    data_nascita =
                        :data_nascita,

                    luogo_nascita =
                        :luogo_nascita,

                    luogo_residenza =
                        :luogo_residenza,

                    telefono =
                        :telefono,

                    email =
                        :email,

                    note =
                        :note,

                    tipo_abbonamento =
                        :tipo_abbonamento,

                    data_inizio_abbonamento =
                        :data_inizio_abbonamento,

                    data_fine_abbonamento =
                        :data_fine_abbonamento,

                    sedute_totali =
                        :sedute_totali,

                    sedute_residue =
                        :sedute_residue,

                    pagamento_effettuato =
                        :pagamento_effettuato,

                    metodo_pagamento =
                        :metodo_pagamento

                WHERE id = :id
            """),
            {
                "id": utente_id,

                "data_nascita":
                    dati.data_nascita,

                "luogo_nascita":
                    dati.luogo_nascita,

                "luogo_residenza":
                    dati.luogo_residenza,

                "telefono":
                    dati.telefono,

                "email":
                    dati.email,

                "note":
                    dati.note,

                "tipo_abbonamento":
                    dati.tipo_abbonamento,

                "data_inizio_abbonamento":
                    dati.data_inizio_abbonamento,

                "data_fine_abbonamento":
                    dati.data_fine_abbonamento,

                "sedute_totali":
                    sedute_totali,

                "sedute_residue":
                    sedute_residue,

                "pagamento_effettuato":
                    pagamento,

                "metodo_pagamento":
                    metodo_pagamento
            }
        )

    return {
        "success": True,
        "message":
            "Dati utente aggiornati con successo."
    }


# ============================================================
# CAMBIO STATO PRENOTAZIONE
# ============================================================

@app.post(
    "/api/prenotazione/{prenotazione_id}/stato"
)
def aggiorna_stato_prenotazione(
    request: Request,
    prenotazione_id: int,
    dati: StatoPrenotazioneUpdate
):

    if not verifica_admin(request):

        return JSONResponse(
            {"error": "Non autorizzato"},
            status_code=403
        )

    if dati.partecipante not in (1, 2):

        return JSONResponse(
            {
                "error":
                    "Partecipante non valido."
            },
            status_code=400
        )

    stato = dati.stato.strip().lower()

    stati_validi = {
        "confermata",
        "presente",
        "assente",
        "cancellata"
    }

    if stato not in stati_validi:

        return JSONResponse(
            {
                "error":
                    "Stato non valido."
            },
            status_code=400
        )

    colonna = (
        "stato"
        if dati.partecipante == 1
        else "stato_2"
    )

    with engine.begin() as conn:

        esiste = conn.execute(
            text("""
                SELECT id
                FROM prenotazioni
                WHERE id = :id
            """),
            {
                "id":
                    prenotazione_id
            }
        ).fetchone()

        if not esiste:

            return JSONResponse(
                {
                    "error":
                        "Prenotazione non trovata."
                },
                status_code=404
            )

        conn.execute(
            text(
                f"""
                UPDATE prenotazioni

                SET {colonna} = :stato

                WHERE id = :id
                """
            ),
            {
                "stato": stato,
                "id":
                    prenotazione_id
            }
        )

    return {
        "success": True,
        "stato": stato
    }


# ============================================================
# SCALA SEDUTA
# ============================================================

@app.post(
    "/api/utente/{utente_id}/prenotazione/"
    "{prenotazione_id}/scala/{partecipante}"
)
def scala_seduta_utente(
    request: Request,
    utente_id: int,
    prenotazione_id: int,
    partecipante: int
):

    if not verifica_admin(request):

        return JSONResponse(
            {"error": "Non autorizzato"},
            status_code=403
        )

    if partecipante not in (1, 2):

        return JSONResponse(
            {
                "error":
                    "Partecipante non valido."
            },
            status_code=400
        )

    with engine.begin() as conn:

        # ----------------------------------------
        # BLOCCO CLIENTE
        # ----------------------------------------

        utente = conn.execute(
            text("""
                SELECT
                    codice_fiscale,

                    COALESCE(
                        sedute_residue,
                        0
                    ) AS sedute_residue

                FROM utenti

                WHERE id = :id

                FOR UPDATE
            """),
            {
                "id":
                    utente_id
            }
        ).mappings().first()

        if not utente:

            return JSONResponse(
                {
                    "error":
                        "Utente non trovato."
                },
                status_code=404
            )

        # ----------------------------------------
        # BLOCCO PRENOTAZIONE
        # ----------------------------------------

        prenotazione = conn.execute(
            text("""
                SELECT

                    trattamento,

                    codice_fiscale,
                    codice_fiscale_2,

                    COALESCE(
                        stato,
                        'confermata'
                    ) AS stato_1,

                    COALESCE(
                        stato_2,
                        'confermata'
                    ) AS stato_2,

                    COALESCE(
                        seduta_scalata,
                        false
                    ) AS scalata_1,

                    COALESCE(
                        seduta_scalata_2,
                        false
                    ) AS scalata_2

                FROM prenotazioni

                WHERE id = :id

                FOR UPDATE
            """),
            {
                "id":
                    prenotazione_id
            }
        ).mappings().first()

        if not prenotazione:

            return JSONResponse(
                {
                    "error":
                        "Prenotazione non trovata."
                },
                status_code=404
            )

        cf_utente = (
            utente["codice_fiscale"]
            or ""
        ).strip().upper()

        if partecipante == 1:

            cf_prenotazione = (
                prenotazione[
                    "codice_fiscale"
                ]
                or ""
            ).strip().upper()

            stato = str(
                prenotazione[
                    "stato_1"
                ]
            ).lower()

            scalata = bool(
                prenotazione[
                    "scalata_1"
                ]
            )

            colonna = (
                "seduta_scalata"
            )

        else:

            cf_prenotazione = (
                prenotazione[
                    "codice_fiscale_2"
                ]
                or ""
            ).strip().upper()

            stato = str(
                prenotazione[
                    "stato_2"
                ]
            ).lower()

            scalata = bool(
                prenotazione[
                    "scalata_2"
                ]
            )

            colonna = (
                "seduta_scalata_2"
            )

        # ----------------------------------------
        # CONTROLLO APPARTENENZA
        # ----------------------------------------

        if (
            cf_prenotazione
            != cf_utente
        ):

            return JSONResponse(
                {
                    "error":
                        "La prenotazione non appartiene "
                        "a questo cliente."
                },
                status_code=400
            )

        # ----------------------------------------
        # DEVE ESSERE PRESENTE
        # ----------------------------------------

        if stato != "presente":

            return JSONResponse(
                {
                    "error":
                        "Puoi scalare la seduta solo "
                        "dopo aver segnato il cliente "
                        "come presente."
                },
                status_code=400
            )

        # ----------------------------------------
        # SEDUTA DI PROVA
        # ----------------------------------------

        trattamento = str(
            prenotazione[
                "trattamento"
            ]
            or ""
        )

        if "prova" in trattamento.lower():

            return JSONResponse(
                {
                    "error":
                        "La Seduta di Prova non viene "
                        "scalata dall'abbonamento."
                },
                status_code=400
            )

        # ----------------------------------------
        # GIÀ SCALATA
        # ----------------------------------------

        if scalata:

            return JSONResponse(
                {
                    "error":
                        "Questa seduta è già stata scalata."
                },
                status_code=400
            )

        residue = int(
            utente[
                "sedute_residue"
            ]
            or 0
        )

        if residue <= 0:

            return JSONResponse(
                {
                    "error":
                        "Il cliente non ha più sedute residue."
                },
                status_code=400
            )

        # ----------------------------------------
        # SCALATURA
        # ----------------------------------------

        conn.execute(
            text(
                f"""
                UPDATE prenotazioni

                SET {colonna} = true

                WHERE id = :id
                """
            ),
            {
                "id":
                    prenotazione_id
            }
        )

        nuove_residue = (
            residue - 1
        )

        conn.execute(
            text("""
                UPDATE utenti

                SET sedute_residue = :residue

                WHERE id = :id
            """),
            {
                "residue":
                    nuove_residue,
                "id":
                    utente_id
            }
        )

    return {
        "success": True,
        "sedute_residue":
            nuove_residue,
        "message":
            "Seduta scalata con successo."
    }


# ============================================================
# ANNULLA SCALATURA
# ============================================================

@app.post(
    "/api/utente/{utente_id}/prenotazione/"
    "{prenotazione_id}/scala/{partecipante}/annulla"
)
def annulla_scala_seduta(
    request: Request,
    utente_id: int,
    prenotazione_id: int,
    partecipante: int
):

    if not verifica_admin(request):

        return JSONResponse(
            {"error": "Non autorizzato"},
            status_code=403
        )

    if partecipante not in (1, 2):

        return JSONResponse(
            {
                "error":
                    "Partecipante non valido."
            },
            status_code=400
        )

    with engine.begin() as conn:

        # ----------------------------------------
        # CLIENTE
        # ----------------------------------------

        utente = conn.execute(
            text("""
                SELECT
                    codice_fiscale,

                    COALESCE(
                        sedute_totali,
                        0
                    ) AS sedute_totali,

                    COALESCE(
                        sedute_residue,
                        0
                    ) AS sedute_residue

                FROM utenti

                WHERE id = :id

                FOR UPDATE
            """),
            {
                "id":
                    utente_id
            }
        ).mappings().first()

        if not utente:

            return JSONResponse(
                {
                    "error":
                        "Utente non trovato."
                },
                status_code=404
            )

        # ----------------------------------------
        # PRENOTAZIONE
        # ----------------------------------------

        prenotazione = conn.execute(
            text("""
                SELECT

                    codice_fiscale,
                    codice_fiscale_2,

                    COALESCE(
                        seduta_scalata,
                        false
                    ) AS scalata_1,

                    COALESCE(
                        seduta_scalata_2,
                        false
                    ) AS scalata_2

                FROM prenotazioni

                WHERE id = :id

                FOR UPDATE
            """),
            {
                "id":
                    prenotazione_id
            }
        ).mappings().first()

        if not prenotazione:

            return JSONResponse(
                {
                    "error":
                        "Prenotazione non trovata."
                },
                status_code=404
            )

        cf_utente = (
            utente["codice_fiscale"]
            or ""
        ).strip().upper()

        if partecipante == 1:

            cf_prenotazione = (
                prenotazione[
                    "codice_fiscale"
                ]
                or ""
            ).strip().upper()

            scalata = bool(
                prenotazione[
                    "scalata_1"
                ]
            )

            colonna = (
                "seduta_scalata"
            )

        else:

            cf_prenotazione = (
                prenotazione[
                    "codice_fiscale_2"
                ]
                or ""
            ).strip().upper()

            scalata = bool(
                prenotazione[
                    "scalata_2"
                ]
            )

            colonna = (
                "seduta_scalata_2"
            )

        # ----------------------------------------
        # CONTROLLO APPARTENENZA
        # ----------------------------------------

        if (
            cf_prenotazione
            != cf_utente
        ):

            return JSONResponse(
                {
                    "error":
                        "La prenotazione non appartiene "
                        "a questo cliente."
                },
                status_code=400
            )

        # ----------------------------------------
        # CONTROLLO SCALATURA
        # ----------------------------------------

        if not scalata:

            return JSONResponse(
                {
                    "error":
                        "Questa seduta non risulta scalata."
                },
                status_code=400
            )

        residue = int(
            utente[
                "sedute_residue"
            ]
            or 0
        )

        totale = int(
            utente[
                "sedute_totali"
            ]
            or 0
        )

        nuove_residue = min(
            residue + 1,
            totale
        )

        # ----------------------------------------
        # ANNULLAMENTO
        # ----------------------------------------

        conn.execute(
            text(
                f"""
                UPDATE prenotazioni

                SET {colonna} = false

                WHERE id = :id
                """
            ),
            {
                "id":
                    prenotazione_id
            }
        )

        conn.execute(
            text("""
                UPDATE utenti

                SET sedute_residue = :residue

                WHERE id = :id
            """),
            {
                "residue":
                    nuove_residue,
                "id":
                    utente_id
            }
        )

    return {
        "success": True,
        "sedute_residue":
            nuove_residue,
        "message":
            "Scalatura annullata."
    }


# ============================================================
# API REST GESTIONALE CLIENTI
# ============================================================

@app.get("/api/clienti-gestionale")
def get_clienti_gestionale():

    with engine.connect() as conn:

        result = conn.execute(
            text("""
                SELECT *
                FROM clienti_gestionale
                ORDER BY id DESC
            """)
        )

        clienti = [
            dict(row._mapping)
            for row in result
        ]

        return clienti


@app.post("/api/clienti-gestionale")
def create_cliente_gestionale(
    cliente: ClienteCreate
):

    with engine.connect() as conn:

        query = text("""
            INSERT INTO clienti_gestionale
            (
                nome,
                email,
                data_nascita,
                tipo_abbonamento,
                sedute_totali,
                sedute_residue,
                note
            )
            VALUES
            (
                :nome,
                :email,
                :data_nascita,
                :tipo_abbonamento,
                :sedute_totali,
                :sedute_residue,
                :note
            )
            RETURNING id
        """)

        result = conn.execute(
            query,
            cliente.dict()
        )

        conn.commit()

        new_id = result.fetchone()[0]

        return {
            "success": True,
            "id": new_id,
            "message":
                "Cliente aggiunto con successo"
        }


@app.put(
    "/api/clienti-gestionale/{cliente_id}"
)
def update_cliente_gestionale(
    cliente_id: int,
    cliente: ClienteUpdate
):

    with engine.connect() as conn:

        update_data = {
            k: v
            for k, v in cliente.dict().items()
            if v is not None
        }

        if not update_data:

            return {
                "success": False,
                "message":
                    "Nessun dato da aggiornare"
            }

        set_clauses = ", ".join(
            [
                f"{k} = :{k}"
                for k in update_data.keys()
            ]
        )

        update_data[
            "cliente_id"
        ] = cliente_id

        query = text(
            f"""
            UPDATE clienti_gestionale

            SET {set_clauses}

            WHERE id = :cliente_id
            """
        )

        conn.execute(
            query,
            update_data
        )

        conn.commit()

        return {
            "success": True,
            "message":
                "Cliente aggiornato con successo"
        }


@app.post(
    "/api/clienti-gestionale/{cliente_id}/scala"
)
def scala_seduta(cliente_id: int):

    with engine.connect() as conn:

        res = conn.execute(
            text("""
                SELECT sedute_residue
                FROM clienti_gestionale
                WHERE id = :id
            """),
            {
                "id":
                    cliente_id
            }
        ).fetchone()

        if not res:

            return {
                "success": False,
                "message":
                    "Cliente non trovato"
            }

        nuove_sedute = max(
            0,
            (res[0] or 0) - 1
        )

        conn.execute(
            text("""
                UPDATE clienti_gestionale

                SET sedute_residue = :s

                WHERE id = :id
            """),
            {
                "s": nuove_sedute,
                "id":
                    cliente_id
            }
        )

        conn.commit()

        return {
            "success": True,
            "sedute_residue":
                nuove_sedute,
            "message":
                "Seduta scalata con successo"
        }


@app.delete(
    "/api/clienti-gestionale/{cliente_id}"
)
def delete_cliente_gestionale(
    cliente_id: int
):

    with engine.connect() as conn:

        conn.execute(
            text("""
                DELETE FROM clienti_gestionale
                WHERE id = :id
            """),
            {
                "id":
                    cliente_id
            }
        )

        conn.commit()

        return {
            "success": True,
            "message":
                "Cliente eliminato con successo"
        }


# ============================================================
# PANNELLO ADMIN
# ============================================================

@app.get(
    "/admin",
    response_class=HTMLResponse
)
def admin_panel(
    request: Request,
    data: str = None
):

    user = request.session.get("user")

    if (
        not user
        or user.get("cf") != ADMIN_CF
    ):

        return RedirectResponse(
            url="/admin/login",
            status_code=303
        )

    if not data:

        data = (
            logic.get_current_time_local()
            .strftime("%Y-%m-%d")
        )

    with engine.begin() as conn:

        prenotazioni = conn.execute(
            text("""
                SELECT
                    p.id,
                    p.nome,
                    p.data,
                    p.ora,
                    p.trattamento,
                    p.codice_fiscale,
                    p.stato,

                    p.nome_2,
                    p.codice_fiscale_2,
                    p.stato_2,

                    u.email

                FROM prenotazioni p

                LEFT JOIN utenti u
                    ON UPPER(
                        p.codice_fiscale
                    )
                    =
                    UPPER(
                        u.codice_fiscale
                    )

                WHERE p.data = :d

                ORDER BY p.ora ASC
            """),
            {
                "d": data
            }
        ).fetchall()

        blocchi = conn.execute(
            text("""
                SELECT
                    id,
                    data,
                    ora
                FROM blocchi
                ORDER BY data ASC
            """)
        ).fetchall()

        utenti = conn.execute(
            text("""
                SELECT
                    id,
                    nome,
                    cognome,
                    codice_fiscale,
                    data_registrazione,

                    COALESCE(
                        bannato,
                        false
                    ),

                    email

                FROM utenti
            """)
        ).fetchall()

    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "prenotazioni":
                prenotazioni,

            "blocchi":
                blocchi,

            "utenti":
                utenti,

            "data_selezionata":
                data
        }
    )


# ============================================================
# ADMIN - ELIMINA PRENOTAZIONE
# ============================================================

@app.post(
    "/admin/prenotazione/elimina"
)
def elimina_prenotazione(
    request: Request,
    id_prenotazione: int = Form(...)
):

    user = request.session.get("user")

    if (
        user
        and user.get("cf") == ADMIN_CF
    ):

        with engine.begin() as conn:

            conn.execute(
                text("""
                    DELETE FROM prenotazioni
                    WHERE id = :id
                """),
                {
                    "id":
                        id_prenotazione
                }
            )

    return RedirectResponse(
        url="/admin",
        status_code=303
    )


# ============================================================
# ADMIN - VECCHIO CAMBIO STATO
# ============================================================
# Mantenuto per compatibilità con eventuali vecchie parti
# dell'interfaccia. Il nuovo admin.html userà invece
# /api/prenotazione/{id}/stato per gestire separatamente
# i due partecipanti.

@app.post(
    "/admin/prenotazione/stato"
)
def cambia_stato_prenotazione(
    request: Request,
    id_prenotazione: int = Form(...),
    nuovo_stato: str = Form(...)
):

    user = request.session.get("user")

    if (
        user
        and user.get("cf") == ADMIN_CF
    ):

        stato = nuovo_stato.strip().lower()

        stati_validi = {
            "confermata",
            "presente",
            "assente",
            "cancellata"
        }

        if stato in stati_validi:

            with engine.begin() as conn:

                conn.execute(
                    text("""
                        UPDATE prenotazioni

                        SET
                            stato = :s,
                            stato_2 = :s

                        WHERE id = :id
                    """),
                    {
                        "s": stato,
                        "id":
                            id_prenotazione
                    }
                )

    return RedirectResponse(
        url="/admin",
        status_code=303
    )


# ============================================================
# ADMIN - BLOCCA ORARIO
# ============================================================

@app.post("/admin/blocca")
def blocca_orario(
    request: Request,
    data: str = Form(...),
    ora: str = Form(None)
):

    user = request.session.get("user")

    if (
        user
        and user.get("cf") == ADMIN_CF
    ):

        ora_val = (
            ora.strip()
            if ora
            and ora.strip() != ""
            else None
        )

        with engine.begin() as conn:

            conn.execute(
                text("""
                    INSERT INTO blocchi
                    (
                        data,
                        ora
                    )
                    VALUES
                    (
                        :d,
                        :o
                    )
                """),
                {
                    "d": data,
                    "o": ora_val
                }
            )

    return RedirectResponse(
        url="/admin",
        status_code=303
    )


# ============================================================
# ADMIN - SBLOCCA ORARIO
# ============================================================

@app.post("/admin/sblocca")
def sblocca_orario(
    request: Request,
    id_blocco: int = Form(...)
):

    user = request.session.get("user")

    if (
        user
        and user.get("cf") == ADMIN_CF
    ):

        with engine.begin() as conn:

            conn.execute(
                text("""
                    DELETE FROM blocchi
                    WHERE id = :id
                """),
                {
                    "id":
                        id_blocco
                }
            )

    return RedirectResponse(
        url="/admin",
        status_code=303
    )


# ============================================================
# ADMIN - BAN / UNBAN
# ============================================================

@app.post("/admin/utente/banna")
def toggle_ban_utente(
    request: Request,
    id_utente: int = Form(...),
    stato_ban: bool = Form(...)
):

    user = request.session.get("user")

    if (
        user
        and user.get("cf") == ADMIN_CF
    ):

        with engine.begin() as conn:

            conn.execute(
                text("""
                    UPDATE utenti

                    SET bannato = :b

                    WHERE id = :id
                """),
                {
                    "b":
                        not stato_ban,
                    "id":
                        id_utente
                }
            )

    return RedirectResponse(
        url="/admin",
        status_code=303
    )


# ============================================================
# ADMIN - ELIMINA UTENTE
# ============================================================

@app.post("/admin/utente/elimina")
def elimina_utente(
    request: Request,
    id_utente: int = Form(...)
):

    user = request.session.get("user")

    if (
        user
        and user.get("cf") == ADMIN_CF
    ):

        with engine.begin() as conn:

            conn.execute(
                text("""
                    DELETE FROM utenti
                    WHERE id = :id
                """),
                {
                    "id":
                        id_utente
                }
            )

    return RedirectResponse(
        url="/admin",
        status_code=303
    )


# ============================================================
# CHECK-IN
# ============================================================

def esegui_checkin_utente(
    cf: str
):

    now = logic.get_current_time_local()

    now_naive = now.replace(
        tzinfo=None
    )

    data_oggi = now_naive.strftime(
        "%Y-%m-%d"
    )

    cf_upper = (
        cf.strip().upper()
    )

    with engine.begin() as conn:

        prenotazioni = conn.execute(
            text("""
                SELECT
                    id,
                    ora,

                    COALESCE(
                        stato,
                        'confermata'
                    ),

                    COALESCE(
                        stato_2,
                        'confermata'
                    ),

                    codice_fiscale,
                    codice_fiscale_2

                FROM prenotazioni

                WHERE
                    (
                        UPPER(codice_fiscale) = :cf
                        OR
                        UPPER(codice_fiscale_2) = :cf
                    )

                    AND data = :d
            """),
            {
                "cf":
                    cf_upper,
                "d":
                    data_oggi
            }
        ).fetchall()

        for (
            p_id,
            p_ora,
            p_stato,
            p_stato_2,
            cf1,
            cf2
        ) in prenotazioni:

            try:

                ora_pulita = (
                    str(p_ora)
                    .strip()[:5]
                )

                dt_appuntamento = (
                    datetime.strptime(
                        f"{data_oggi} "
                        f"{ora_pulita}",
                        "%Y-%m-%d %H:%M"
                    )
                )

                diff_minuti = (
                    now_naive
                    - dt_appuntamento
                ).total_seconds() / 60

                # Finestra reale: ±35 minuti
                if (
                    -35
                    <= diff_minuti
                    <= 35
                ):

                    # PARTECIPANTE 1
                    if (
                        cf1
                        and cf_upper
                        == cf1.strip().upper()
                    ):

                        if (
                            p_stato
                            == "presente"
                        ):

                            return (
                                True,
                                "Presenza già "
                                "confermata per "
                                "la prima persona!"
                            )

                        conn.execute(
                            text("""
                                UPDATE prenotazioni

                                SET stato = 'presente'

                                WHERE id = :id
                            """),
                            {
                                "id":
                                    p_id
                            }
                        )

                        return (
                            True,
                            "Presenza confermata "
                            "con successo! "
                            "Buon allenamento!"
                        )

                    # PARTECIPANTE 2
                    elif (
                        cf2
                        and cf_upper
                        == cf2.strip().upper()
                    ):

                        if (
                            p_stato_2
                            == "presente"
                        ):

                            return (
                                True,
                                "Presenza già "
                                "confermata per "
                                "la seconda persona!"
                            )

                        conn.execute(
                            text("""
                                UPDATE prenotazioni

                                SET stato_2 = 'presente'

                                WHERE id = :id
                            """),
                            {
                                "id":
                                    p_id
                            }
                        )

                        return (
                            True,
                            "Presenza confermata "
                            "con successo! "
                            "Buon allenamento!"
                        )

            except Exception:
                continue

    return (
        False,
        "Nessuna prenotazione a tuo nome "
        "trovata per l'orario attuale "
        "(finestra consentita: ±35 min)."
    )


@app.get(
    "/checkin",
    response_class=HTMLResponse
)
def checkin_qr_get(
    request: Request
):

    user = request.session.get("user")

    if not user:

        return templates.TemplateResponse(
            request=request,
            name="checkin_login.html",
            context={
                "error": None
            }
        )

    successo, messaggio = (
        esegui_checkin_utente(
            user["cf"]
        )
    )

    context = (
        {"success": messaggio}
        if successo
        else
        {"error": messaggio}
    )

    return templates.TemplateResponse(
        request=request,
        name="checkin_result.html",
        context=context
    )


@app.post(
    "/checkin",
    response_class=HTMLResponse
)
def checkin_qr_post(
    request: Request,
    nome: str = Form(...),
    cognome: str = Form(...),
    password: str = Form(...)
):

    with engine.begin() as conn:

        res = conn.execute(
            text("""
                SELECT
                    id,
                    nome,
                    cognome,
                    codice_fiscale,
                    password_salt,
                    password_hash,
                    COALESCE(
                        bannato,
                        false
                    )

                FROM utenti

                WHERE
                    UPPER(nome) = :n
                    AND
                    UPPER(cognome) = :c
            """),
            {
                "n":
                    nome.strip().upper(),
                "c":
                    cognome.strip().upper()
            }
        ).fetchone()

        if (
            not res
            or not logic.verifica_password(
                password,
                res[4],
                res[5]
            )
        ):

            return templates.TemplateResponse(
                request=request,
                name="login.html",
                context={
                    "error":
                        "Credenziali non valide "
                        "o utente non trovato.",
                    "admin_error": None
                }
            )

        if res[6]:

            return templates.TemplateResponse(
                request=request,
                name="checkin_result.html",
                context={
                    "error":
                        "Account disabilitato. "
                        "Contatta l'amministrazione."
                }
            )

        user = {
            "id": str(res[0]),
            "nome": str(res[1]),
            "cognome": str(res[2]),
            "cf": str(res[3])
        }

        request.session["user"] = user

    successo, messaggio = (
        esegui_checkin_utente(
            user["cf"]
        )
    )

    context = (
        {"success": messaggio}
        if successo
        else
        {"error": messaggio}
    )

    return templates.TemplateResponse(
        request=request,
        name="checkin_result.html",
        context=context
    )


# ============================================================
# DOWNLOAD CALENDARIO ICS
# ============================================================

@app.get("/download-ics")
def download_ics(
    trattamento: str,
    data: str,
    ora: str
):

    ics_content = logic.genera_file_ics(
        trattamento,
        data,
        ora
    )

    return Response(
        content=ics_content,
        media_type="text/calendar",
        headers={
            "Content-Disposition":
                "attachment; "
                "filename="
                "appuntamento_pilates.ics"
        }
    )
