import hashlib
import hmac
import os
from datetime import datetime, timezone
import zoneinfo
import re
import random

# --- GESTIONE PASSWORD (HASHING SICURO) ---
def hash_password(password: str) -> tuple[str, str]:
    salt = os.urandom(16).hex()
    pwd_hash = hashlib.pbkdf2_hmac(
        'sha256', 
        password.encode('utf-8'), 
        bytes.fromhex(salt), 
        100000
    ).hex()
    return salt, pwd_hash

def verifica_password(password: str, salt: str, pwd_hash: str) -> bool:
    new_hash = hashlib.pbkdf2_hmac(
        'sha256', 
        password.encode('utf-8'), 
        bytes.fromhex(salt), 
        100000
    ).hex()
    return hmac.compare_digest(new_hash, pwd_hash)

# --- VALIDAZIONE CODICE FISCALE ---
def valida_codice_fiscale(nome: str, cognome: str, cf: str) -> tuple[bool, str]:
    cf_clean = cf.strip().upper()
    pattern = r"^[A-Z]{6}[0-9LMNP-V]{2}[A-EHLMPR-T]{1}[0-9LMNP-V]{2}[A-Z]{1}[0-9LMNP-V]{3}[A-Z]{1}$"
    
    if not re.match(pattern, cf_clean):
        return False, "Il formato del Codice Fiscale non è valido."
    
    return True, ""

# --- GESTIONE ORARI E ORARIO LOCALE ---
def get_current_time_local() -> datetime:
    try:
        tz = zoneinfo.ZoneInfo("Europe/Rome")
    except Exception:
        tz = timezone(timedelta(hours=1))
    return datetime.now(tz)

def get_orari_per_data(dt: datetime) -> list[str]:
    giorno = dt.weekday()
    
    if giorno in [0, 2, 4]:  # Lunedì, Mercoledì, Venerdì
        return ["09:00", "10:00", "11:00", "16:00", "17:00", "18:00", "19:00"]
    elif giorno in [1, 3]:   # Martedì, Giovedì
        return ["10:00", "11:00", "17:00", "18:00", "19:00"]
    elif giorno == 5:        # Sabato (dalle 08:00 alle 13:00)
        return ["08:00", "09:00", "10:00", "11:00", "12:00", "13:00"]
    else:                    # Domenica (chiuso)
        return []

def get_orari_disponibili_filtrati(data_str: str, orari_teorici: list[str]) -> list[str]:
    try:
        data_appuntamento = datetime.strptime(data_str, "%Y-%m-%d").date()
    except ValueError:
        return orari_teorici

    oggi = get_current_time_local().date()
    
    if data_appuntamento > oggi:
        return orari_teorici
    
    if data_appuntamento == oggi:
        ora_attuale = get_current_time_local().strftime("%H:%M")
        return [o for o in orari_teorici if o > ora_attuale]
    
    return []

# --- GENERAZIONE FILE ICS (CALENDARIO) ---
def genera_file_ics(trattamento: str, data: str, ora: str) -> str:
    try:
        dt_inizio = datetime.strptime(f"{data} {ora}", "%Y-%m-%d %H:%M")
        dt_fine = dt_inizio.replace(hour=dt_inizio.hour + 1)
        
        fmt = "%Y%m%dT%H%M00"
        str_inizio = dt_inizio.strftime(fmt)
        str_fine = dt_fine.strftime(fmt)
        str_stamp = datetime.now(timezone.utc).strftime(fmt)
        
        ics = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Studio Pilates//Prenotazioni//IT
BEGIN:VEVENT
UID:pilates-{str_inizio}-{random.randint(1000,9999)}@studio.local
DTSTAMP:{str_stamp}
DTSTART:{str_inizio}
DTEND:{str_fine}
SUMMARY:Appuntamento {trattamento}
DESCRIPTION:Prenotazione confermata presso lo Studio di Pilates.
LOCATION:Studio Pilates
END:VEVENT
END:VCALENDAR"""
        return ics
    except Exception:
        return ""
