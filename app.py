import hashlib
import math
import random
import streamlit as st
import streamlit.components.v1 as components
import requests
import json
import urllib.parse
import asyncio
import concurrent.futures
import pandas as pd
import pydeck as pdk
import time
from openai import OpenAI
from datetime import datetime, timedelta
from dateutil import parser as dateutil_parser
from streamlit_geolocation import streamlit_geolocation
from supabase import create_client, Client
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_not_exception_type

# ==========================================
# 1. CONFIGURATION & SECRETS
# ==========================================
TIER_PERSONALITIES = [
    {"tier_name": "The Crowd-Pleaser",  "description": "A highly rated safe bet everyone will enjoy"},
    {"tier_name": "The Hidden Gem",     "description": "Quirky, unique, or off the beaten path"},
    {"tier_name": "The Fresh Take",     "description": "New, trending, or a live event happening now"},
    {"tier_name": "The Local Favorite", "description": "Where locals actually go, not tourists"},
    {"tier_name": "The Wild Card",      "description": "Unexpected and spontaneous — trust the process"},
    {"tier_name": "The Date Night Pick","description": "Intimate, romantic, and impressive"},
    {"tier_name": "The Comeback Kid",   "description": "An old classic that's been reinvented or is having a moment"},
    {"tier_name": "The Underdog",       "description": "Lesser known but punches above its weight"},
    {"tier_name": "The Vibe Match",     "description": "Perfectly matches the specific mood requested"},
    {"tier_name": "The Adventure",      "description": "Gets you out of your comfort zone"},
]

CACHE_VERSION = "v2"

GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
TAVILY_API_KEY = st.secrets["TAVILY_API_KEY"]
OPENWEATHER_API_KEY = st.secrets["OPENWEATHER_API_KEY"] 
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

@st.cache_resource
def init_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase: Client = init_supabase()

# ==========================================
# 2. CUSTOM CSS & STYLING
# ==========================================
st.set_page_config(page_title="Get Wild", page_icon="🌿", layout="centered")

custom_css = """
<style>
    /* HERO */
    .hero-header { text-align: center; padding: 2rem 0 1rem 0; }
    .hero-title { color: #2e7d32; font-family: 'Helvetica Neue', sans-serif; font-size: 3.5rem; font-weight: 800; letter-spacing: -1px; text-transform: uppercase; margin-bottom: 0; line-height: 1.1; }
    .hero-subtitle { color: #558b2f; font-size: 1.2rem; font-weight: 400; letter-spacing: 1px; margin-top: 10px; }

    /* CARD */
    .wc-shell { overflow: hidden; animation: fadeSlideUp 0.5s ease-out forwards; }

    /* Card inner content */
    .wc-img-wrap { position: relative; width: 100%; height: 200px; overflow: hidden; }
    .wc-img { width: 100%; height: 100%; object-fit: cover; display: block; }
    .wc-tier { position: absolute; bottom: 10px; left: 12px; background: rgba(0,0,0,0.62); color: #fff; font-size: 0.68rem; font-weight: 600; letter-spacing: 0.5px; padding: 4px 10px; border-radius: 20px; text-transform: uppercase; }

    .wc-body { padding: 16px; }
    .wc-name { font-size: 20px; font-weight: 700; color: #1a1a1a; margin: 0 0 5px 0; line-height: 1.3; }
    .wc-meta { font-size: 0.78rem; color: #888; margin-bottom: 3px; font-weight: 500; }
    .wc-address { font-size: 12px; color: #aaa; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 12px; }
    .wc-hr { border: none; border-top: 1px solid #f0f0f0; margin: 12px 0; }
    .wc-pitch { font-size: 14px; line-height: 1.6; color: #444; margin: 0 0 8px 0; }
    .wc-tags { margin: 0 0 2px 0; }
    .wc-tag { display: inline-block; background: #e8f5e9; color: #2e7d32; padding: 3px 10px; border-radius: 12px; font-size: 0.73rem; font-weight: 600; margin: 2px 4px 2px 0; border: 1px solid #c8e6c9; }

    .wc-utility { display: flex; align-items: center; flex-wrap: wrap; gap: 2px; margin-bottom: 12px; }
    .wc-util-link { color: #aaa; font-size: 0.78rem; text-decoration: none; font-weight: 500; transition: color 0.15s; }
    .wc-util-link:hover { color: #555; text-decoration: underline; }
    .wc-util-sep { color: #ddd; padding: 0 4px; font-size: 0.78rem; }

    /* Dark mode */
    @media (prefers-color-scheme: dark) {
        .stTextInput > label, .stSelectbox > label, .stRadio > label,
        .stCheckbox > label, .stTextArea > label, .stMultiSelect > label,
        .stSlider > label, .stNumberInput > label { color: #f0f0f0 !important; }
        .wc-name { color: #f0f0f0 !important; }
        .wc-meta, .wc-address { color: #999 !important; }
        .wc-pitch { color: #ccc !important; }
        .wc-hr { border-color: #333 !important; }
        .wc-util-link { color: #666 !important; }
        .wc-util-link:hover { color: #999 !important; }
        .wc-tag { background: #1a3320 !important; border-color: #2a5230 !important; }
    }

    @keyframes fadeSlideUp { from {opacity: 0; transform: translateY(20px);} to { opacity: 1; transform: translateY(0); } }
    @keyframes wildGlow {
        0%, 100% { box-shadow: 0 0 20px rgba(45,106,79,0.4), 0 0 40px rgba(45,106,79,0.2); }
        50%       { box-shadow: 0 0 30px rgba(45,106,79,0.6), 0 0 60px rgba(45,106,79,0.3); }
    }
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

def scroll_to_top():
    components.html(
        """
        <script>
            var body = window.parent.document.querySelector(".main");
            if (body) { body.scrollTop = 0; }
        </script>
        """,
        height=0
    )

# ==========================================
# 3. SESSION STATE & DATABASE HELPERS
# ==========================================
if 'user' not in st.session_state: st.session_state.user = None
if 'current_results' not in st.session_state: st.session_state.current_results = None 
if 'current_mode' not in st.session_state: st.session_state.current_mode = None
if 'session_seen_spots' not in st.session_state: st.session_state.session_seen_spots = []
if 'search_active' not in st.session_state: st.session_state.search_active = False
if 'trigger_fetch' not in st.session_state: st.session_state.trigger_fetch = False
if 'saved_spots_dirty' not in st.session_state: st.session_state.saved_spots_dirty = False
if 'fetch_timed_out' not in st.session_state: st.session_state.fetch_timed_out = False
if 'skip_cache' not in st.session_state: st.session_state.skip_cache = False

# Persistent memory state variables
if 'mem_loc' not in st.session_state: st.session_state.mem_loc = ""
if 'mem_day' not in st.session_state: st.session_state.mem_day = "☀️ Today"
if 'mem_time' not in st.session_state: st.session_state.mem_time = "🌙 Night"
if 'mem_group' not in st.session_state: st.session_state.mem_group = "Date"
if 'mem_vibe' not in st.session_state: st.session_state.mem_vibe = "Doesn't Matter"
if 'mem_food' not in st.session_state: st.session_state.mem_food = "Full Meal"
if 'mem_dist' not in st.session_state: st.session_state.mem_dist = 5
if 'mem_spec' not in st.session_state: st.session_state.mem_spec = ""
if 'mem_gps_active' not in st.session_state: st.session_state.mem_gps_active = False
if 'mem_geo_data' not in st.session_state: st.session_state.mem_geo_data = None

def get_profile(user_id):
    try:
        res = supabase.table('user_profiles').select('*').eq('id', user_id).execute()
        return res.data[0] if res.data else None
    except: return None

def get_excluded_spots(user_id):
    try:
        res = supabase.table('saved_spots').select('spot_name').eq('user_id', user_id).execute()
        return [spot['spot_name'] for spot in res.data] if res.data else []
    except: return []

def get_favorite_spots(user_id):
    try:
        # Pull spots rated 4 or 5 stars to train the AI
        res = supabase.table('saved_spots').select('spot_name, category').eq('user_id', user_id).gte('rating', 4).execute()
        return [f"{spot['spot_name']} ({spot['category']})" for spot in res.data] if res.data else []
    except: return []

def save_spot_to_db(user_id, name, address, category, rating=None, notes=""):
    try:
        current_time = datetime.utcnow().isoformat()
        supabase.table('saved_spots').insert({
            'user_id': user_id, 
            'spot_name': name, 
            'address': address, 
            'category': category, 
            'rating': rating, 
            'user_notes': notes,
            'saved_at': current_time
        }).execute()
        
        if rating != 1:
            prof = get_profile(user_id)
            new_tally = (prof.get('wild_tally') or 0) + 1
            supabase.table('user_profiles').update({'wild_tally': new_tally}).eq('id', user_id).execute()
            st.toast(f"✅ Saved! Your Get Wild Tally is now {new_tally} 🏆")
        else:
            st.toast("🚫 Blacklisted. We won't recommend this again.")
    except Exception as e: st.error("Database error.")

def generate_cache_key(filters_dict, location_name, target_date_str, mode):
    raw = json.dumps(filters_dict, sort_keys=True) + location_name + target_date_str + mode + CACHE_VERSION
    return hashlib.md5(raw.encode()).hexdigest()

def delete_spot_from_db(spot_id):
    try:
        supabase.table('saved_spots').delete().eq('id', spot_id).execute()
        st.toast("🗑️ Spot permanently deleted.")
        return True
    except Exception as e:
        st.error(f"Database error while deleting: {e}")
        return False

def increment_wild_counter(city):
    try:
        today = datetime.utcnow().date().isoformat()
        supabase.rpc('increment_wild_counter', {'p_date': today, 'p_city': city}).execute()
    except:
        pass

def get_wild_count_today():
    try:
        today = datetime.utcnow().date().isoformat()
        res = supabase.table('wild_counter').select('count').eq('search_date', today).execute()
        if res.data:
            return sum(row['count'] for row in res.data)
        return 0
    except:
        return None

# ==========================================
# 4. HELPER FUNCTIONS (The Engine)
# ==========================================
def get_coordinates(location_query):
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={location_query}&key={GOOGLE_API_KEY}"
    try:
        response = requests.get(url, timeout=10).json()
        if response['status'] == 'OK':
            loc = response['results'][0]['geometry']['location']
            return loc['lat'], loc['lng']
    except: pass
    return None, None

@st.cache_data(ttl=86400)
def get_local_target_date(lat, lng, day_choice):
    timestamp = int(time.time())
    url = f"https://maps.googleapis.com/maps/api/timezone/json?location={lat},{lng}&timestamp={timestamp}&key={GOOGLE_API_KEY}"
    try:
        res = requests.get(url, timeout=10).json()
        if res['status'] == 'OK':
            local_timestamp = timestamp + res['dstOffset'] + res['rawOffset']
            local_time = datetime.utcfromtimestamp(local_timestamp)
        else:
            local_time = datetime.utcnow()
    except:
        local_time = datetime.utcnow()
        
    if "Tomorrow" in day_choice:
        target_date = local_time + timedelta(days=1)
        return target_date.strftime("%A, %B %d, %Y"), "TOMORROW"
    else:
        return local_time.strftime("%A, %B %d, %Y"), "TODAY"

def get_state_from_coords(lat, lng):
    url = f"https://maps.googleapis.com/maps/api/geocode/json?latlng={lat},{lng}&key={GOOGLE_API_KEY}"
    try:
        res = requests.get(url, timeout=10).json()
        if res['status'] == 'OK':
            for component in res['results'][0]['address_components']:
                if 'administrative_area_level_1' in component['types']:
                    return component['short_name'], component['long_name']
    except:
        pass
    return None, None

def get_live_weather(lat, lng):
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lng}&units=imperial&appid={OPENWEATHER_API_KEY}"
        res = requests.get(url, timeout=10).json()
        if res.get("cod") == 200:
            return f"{res['main']['temp']}°F and {res['weather'][0]['description']}"
    except: pass
    return "Weather data unavailable."

def build_semantic_query(filters_dict, profile):
    modifiers = []
    
    # Highest priority: The Specific Keyword
    if filters_dict.get('specific'):
        modifiers.append(filters_dict['specific'])

    if profile:
        if profile.get('needs_dog_friendly') and filters_dict['vibe'] == "Outside": modifiers.append("dog-friendly")
        if profile.get('vibe_preference'): modifiers.append(profile.get('vibe_preference'))

    if filters_dict['group'] == "Date": modifiers.append("intimate")
    elif filters_dict['group'] == "Family Outing": modifiers.append("kid-friendly")
    elif filters_dict['group'] == "Friends": modifiers.append("lively")

    modifier_str = " ".join(modifiers)
    
    # Always keep a strong base category so Google doesn't return random offices/services
    no_food = filters_dict['food'] == "No Food Needed"
    if filters_dict['vibe'] == "Outside":
        if filters_dict['food'] == "Full Meal": base = "restaurants with nice patios"
        elif filters_dict['food'] == "Just Drinks/Coffee": base = "wineries, cocktail bars with patios, or upscale breweries"
        else: base = "parks, botanical gardens, hiking trails, scenic outdoor activities, nature reserves"
    elif filters_dict['vibe'] == "Inside":
        if filters_dict['food'] == "Full Meal": base = "highly rated restaurants"
        elif filters_dict['food'] == "Just Drinks/Coffee": base = "wine bars, speakeasies, or lounges"
        else: base = "museums, art galleries, science centers, escape rooms, bowling alleys, entertainment venues, unique attractions"
    else:
        if filters_dict['food'] == "Full Meal": base = "highly rated restaurants"
        elif filters_dict['food'] == "Just Drinks/Coffee": base = "wine bars, speakeasies, or lounges"
        else: base = "museums, parks, entertainment venues, unique attractions, or outdoor experiences"

    exclusion = " NOT bar NOT brewery NOT restaurant NOT cafe" if no_food else ""
    return f"{modifier_str} {base}{exclusion}".strip()

def haversine_miles(lat1, lon1, lat2, lon2):
    R = 3958.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def fetch_places_semantic(semantic_query, lat, lng, radius_miles):
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_API_KEY,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.rating,places.websiteUri,places.photos,places.editorialSummary,places.location"
    }
    radius_meters = int(radius_miles * 1609.34)
    data = {
        "textQuery": semantic_query,
        "pageSize": 8,
        "locationBias": {"circle": {"center": {"latitude": lat, "longitude": lng}, "radius": radius_meters}}
    }
    try:
        response = requests.post(url, headers=headers, json=data, timeout=15)
        if response.status_code == 200:
            places = response.json().get('places', [])
            for place in places:
                photos = place.get('photos', [])
                if photos:
                    photo_name = photos[0].get('name', '')
                    place['photo_ref'] = photo_name
                    place['photo_url'] = f"https://places.googleapis.com/v1/{photo_name}/media?key={GOOGLE_API_KEY}&maxHeightPx=400&maxWidthPx=800"
                else:
                    place['photo_ref'] = None
                    place['photo_url'] = None
            # Python-side distance filter (Google Places API ignores radius for text search)
            threshold = radius_miles * 1.5
            filtered = []
            for place in places:
                loc = place.get('location', {})
                plat, plng = loc.get('latitude'), loc.get('longitude')
                if plat and plng:
                    dist = haversine_miles(lat, lng, plat, plng)
                    place['distance_miles'] = round(dist, 1)
                    if dist <= threshold:
                        filtered.append(place)
                else:
                    filtered.append(place)
            return filtered
    except: pass
    return []

def fetch_live_events(location_name, intended_time, group_type, target_date_str, relative_day, lat, lng):
    import re

    US_STATES = {
        "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
        "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
        "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana",
        "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
        "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
        "New Hampshire", "New Jersey", "New Mexico", "New York",
        "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon",
        "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
        "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
        "West Virginia", "Wisconsin", "Wyoming"
    }

    try:
        state_abbr, state_name = get_state_from_coords(lat, lng)
        search_location = state_name if state_name else location_name

        try:
            target_date = dateutil_parser.parse(target_date_str).date()
        except:
            target_date = None

        url = "https://api.tavily.com/search"
        queries = [
            f"live music concerts events {target_date_str} {search_location}",
            f"festivals theater shows activities {target_date_str} {search_location}"
        ]

        validated_results = []

        def _tavily_search(query):
            payload = {
                "api_key": TAVILY_API_KEY,
                "query": query,
                "search_depth": "advanced",
                "include_answer": False,
                "max_results": 5
            }
            response = requests.post(url, json=payload, timeout=2.5)
            return response.json().get('results', [])

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            futures = {ex.submit(_tavily_search, q): q for q in queries}
            for future in concurrent.futures.as_completed(futures):
                try:
                    results = future.result()
                except:
                    continue

                for r in results:
                    snippet = r.get('content', '') or ''
                    title = r.get('title', '')
                    result_url = r.get('url', '')

                    # Reject results that mention another US state without mentioning our target state
                    if state_name:
                        foreign_state_only = False
                        for state in US_STATES:
                            if state != state_name and state.lower() in snippet.lower():
                                if (state_name.lower() not in snippet.lower() and
                                        (not state_abbr or state_abbr not in snippet)):
                                    foreign_state_only = True
                                    break
                        if foreign_state_only:
                            continue

                    # Validate date against target
                    date_verified = False
                    if target_date:
                        date_patterns = re.findall(
                            r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|'
                            r'Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
                            r'\s+\d{1,2}(?:,?\s*\d{4})?\b',
                            snippet, re.IGNORECASE
                        )
                        for dp in date_patterns:
                            try:
                                parsed = dateutil_parser.parse(
                                    dp, default=datetime(target_date.year, 1, 1)
                                ).date()
                                if parsed == target_date:
                                    date_verified = True
                                    break
                            except:
                                pass

                    validated_results.append({
                        "title": title,
                        "venue_name": "",
                        "venue_address": "",
                        "date_str": target_date_str,
                        "start_time": "",
                        "date_verified": date_verified,
                        "url": result_url,
                        "snippet": snippet[:500]
                    })

        return validated_results
    except:
        return []

@retry(wait=wait_exponential(min=1, max=10), stop=stop_after_attempt(3), retry=retry_if_not_exception_type(TimeoutError))
def get_ai_recommendations(raw_places, live_events_data, weather_report, filters_dict, location_name, target_date_str, relative_day, profile, excluded_spots, favorite_spots, mode="top_3", tier_personalities=None, lat=None, lng=None, radius_miles=20):
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    trimmed_places = raw_places[:8] if isinstance(raw_places, list) and len(raw_places) > 8 else raw_places
    if isinstance(live_events_data, list):
        safe_events_data = live_events_data[:6]
    elif isinstance(live_events_data, str):
        safe_events_data = live_events_data[:4000]
    else:
        safe_events_data = live_events_data

    profile_context = ""
    if profile:
        stroller = "MUST be stroller accessible." if profile.get('needs_stroller_access') else ""
        dog = "MUST be dog-friendly." if profile.get('needs_dog_friendly') and filters_dict['vibe'] == "Outside" else ""
        vibe_pref = f"Prioritize locations matching this vibe: {profile.get('vibe_preference')}." if profile.get('vibe_preference') else ""
        nonalc = "NEVER recommend bars, breweries, cocktail bars, or any alcohol-focused venue." if profile.get('needs_nonalcoholic') else ""
        restrictions = profile.get('dietary_restrictions', '')
        dietary = f"User dietary restrictions: {restrictions}. Only recommend venues that can accommodate these." if restrictions and restrictions.strip() else ""
        history_context = f"\nUSER'S HISTORICAL FAVORITES (Learn from their taste!): {', '.join(favorite_spots)}" if favorite_spots else ""
        profile_context = f"\nUSER BASELINE PROFILE:\n{stroller}\n{dog}\n{vibe_pref}\n{nonalc}\n{dietary}{history_context}"

    blacklist_context = f"CRITICAL: DO NOT RECOMMEND ANY OF THESE PLACES: {', '.join(excluded_spots)}" if excluded_spots else ""

    if mode == "get_wild":
        instruction = """Select EXACTLY ONE option from the data. Assign it the category: 'Spontaneous Adventure'."""
    else:
        tiers = tier_personalities or TIER_PERSONALITIES[:3]
        tier_lines = "\n".join(f"        {i+1}. '{t['tier_name']}': {t['description']}." for i, t in enumerate(tiers))
        instruction = f"""
        Return EXACTLY 3 options from the data, providing STRICT VARIETY (do not return 3 of the exact same type of venue).
        Assign each to one of these directional 'tier_name' categories:
{tier_lines}
        """

    if filters_dict.get('vibe') == "Outside":
        weather_rule = "4. WEATHER: If RAIN, SNOW, or under 45°F → prefer indoor or heated-patio venues."
    else:
        weather_rule = "4. WEATHER: No weather restrictions (user wants indoor or is flexible)."

    specific_rule = ""
    if filters_dict.get('specific'):
        specific_rule = f"""7. SPECIFIC REQUEST — HARD FILTER ON ALL RESULTS: '{filters_dict['specific']}'
    Applies to every recommendation, not just one. Honor literal and conceptual meaning:
    - "happy hour" → bars/restaurants with happy hour specials; mention deals/times in why_its_perfect
    - "live music" → confirmed live music venues only
    - "romantic" → intimate, quiet, date-appropriate only
    matched_tags MUST be populated with 1-3 keywords from this request (never leave empty).
    If no data genuinely matches, say so honestly — don't force irrelevant results."""

    # Geography rule
    geo_center = f"{location_name}{f' (lat={lat:.4f}, lng={lng:.4f})' if lat and lng else ''}"
    geo_rule = (
        f"1. STRICT GEOGRAPHY: Search center is {geo_center}. "
        f"Every result MUST be within {radius_miles} miles. "
        "For events specifically: the venue must be in the search city or its immediate suburbs — NOT a distant city. "
        "OUT-OF-RANGE examples for a Northern VA/DC search: Virginia Beach, Richmond, Ocean City, Baltimore. "
        "If an event venue city does not match the search location or its suburbs, discard it and use a Google Places result."
    )

    # Events rule — hierarchy depends on food filter
    food_filter = filters_dict.get('food', '')
    if food_filter == "Full Meal":
        events_rule = (
            "2. DATA SOURCE — FULL MEAL MODE: Google Places is your ONLY source. "
            "The user wants restaurants and dining. DO NOT use any live events regardless of verification. "
            "Ignore the events section entirely. All 3 results must be restaurants/dining from Google Places."
        )
    elif food_filter == "Just Drinks/Coffee":
        events_rule = (
            "2. DATA SOURCE PRIORITY: Google Places is PRIMARY (use for at least 2 of 3 results). "
            "One event slot is acceptable ONLY if ALL of these are true: "
            "(a) date_verified=True on today's date, "
            "(b) the event venue is within the search radius in the correct city/suburbs, "
            "(c) the event is drinks or nightlife related. "
            "If no event meets all three criteria, use Google Places for all results."
        )
    else:  # No Food Needed
        events_rule = (
            "2. DATA SOURCE PRIORITY: Google Places is PRIMARY — default to it for all results. "
            "Events may fill ONE slot only if ALL of these are true: "
            "(a) date_verified=True on today's date, "
            "(b) venue is physically inside the search city or immediate suburbs within the radius. "
            "If any doubt about an event's location or date, skip it and use a Google Places result."
        )

    system_prompt = f"""You are a local concierge for 'Get Wild'.

CONTEXT: {location_name} | {weather_report} | {target_date_str} ({relative_day}) | {filters_dict['time']} | {filters_dict['group']}, {filters_dict['food']}, {filters_dict['vibe']}
{profile_context}{blacklist_context}
RULES:
{geo_rule}
{events_rule}
3. EVENTS DATE CHECK: Only events with date_verified=True on {relative_day} ({target_date_str}) are eligible. why_its_perfect must include venue name and address. Never fabricate event details.
{weather_rule}
5. NO HALLUCINATION: Use exact addresses and URLs from input data. Never invent.
6. VARIETY: Do not return 3 events, 3 of the same venue type, or 3 of the same category. Google Places results must provide the backbone of variety.
{specific_rule}

{instruction}

Return JSON with a 'recommendations' array. Each item: name, tier_name, category, address (exact), why_its_perfect (2-3 sentences), vibe_check (3 words), matched_tags (2-3 strings; mandatory if specific given), website, lat, lng."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={ "type": "json_object" },
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"GOOGLE PLACES DATA: {json.dumps(trimmed_places)}\n\nLIVE WEB SEARCH EVENTS:\n{json.dumps(safe_events_data) if isinstance(safe_events_data, list) else safe_events_data}"}
            ],
            max_tokens=2500,
            timeout=30
        )
    except Exception as e:
        if "timeout" in type(e).__name__.lower() or "timeout" in str(e).lower():
            raise TimeoutError("Taking longer than usual, please try again")
        raise
    
    raw_content = response.choices[0].message.content.strip()
    if raw_content.startswith("```json"):
        raw_content = raw_content[7:-3].strip()
    elif raw_content.startswith("```"):
        raw_content = raw_content[3:-3].strip()
        
    return json.loads(raw_content)

def match_photos_to_results(recommendations, raw_places):
    place_photos = {}
    for place in (raw_places or []):
        name = place.get('displayName', {}).get('text', '').lower().replace(' ', '')
        if name and place.get('photo_url'):
            url = place['photo_url']
            try:
                r = requests.head(url, timeout=3)
                if r.status_code == 200:
                    place_photos[name] = url
            except:
                pass
    for rec in recommendations:
        rec_name = rec.get('name', '').lower().replace(' ', '')
        if rec_name in place_photos:
            rec['photo_url'] = place_photos[rec_name]
            continue
        matched = False
        for place_name, url in place_photos.items():
            if place_name in rec_name or rec_name in place_name:
                rec['photo_url'] = url
                matched = True
                break
        if not matched:
            rec['photo_url'] = None
    return recommendations

def render_spot_card(spot, location_input, user_id, index, mode):
    title_prefix = f"{index}." if mode == "top_3" else "🎲"

    search_term = spot['name'].replace(' ', '+') + f"+{location_input.replace(' ', '+')}"
    map_url = f"https://www.google.com/maps/search/?api=1&query={search_term}"
    encoded_address = urllib.parse.quote(spot['address'])
    uber_url = f"https://m.uber.com/ul/?action=setPickup&pickup=my_location&dropoff[formatted_address]={encoded_address}"

    # Fallback image (priority: category → tier_name → why_its_perfect → name)
    text_to_check = " ".join([
        (spot.get('name', '') or ''),
        (spot.get('category', '') or ''),
        (spot.get('tier_name', '') or ''),
        (spot.get('why_its_perfect', '') or ''),
    ]).lower()
    if any(k in text_to_check for k in ["wine", "winery", "vineyard", "sommelier"]):
        fallback_url = "https://images.unsplash.com/photo-1510812431401-41d2bd2722f3?w=800&q=80"
    elif any(k in text_to_check for k in ["brewery", "brewing", "brewpub", "craft beer", "taproom"]):
        fallback_url = "https://images.unsplash.com/photo-1575367439058-6096bb9cf5e2?w=800&q=80"
    elif any(k in text_to_check for k in ["cocktail", "speakeasy", "lounge", " bar", " pub"]):
        fallback_url = "https://images.unsplash.com/photo-1575367439058-6096bb9cf5e2?w=800&q=80"
    elif any(k in text_to_check for k in ["coffee", "cafe", "espresso", "tea"]):
        fallback_url = "https://images.unsplash.com/photo-1501339847302-ac426a4a7cbb?w=800&q=80"
    elif any(k in text_to_check for k in ["concert", "live music", "jazz", "band", "music venue", "performance"]):
        fallback_url = "https://images.unsplash.com/photo-1540039155732-d68a96670afb?w=800&q=80"
    elif any(k in text_to_check for k in ["theater", "comedy", "cinema", "show"]):
        fallback_url = "https://images.unsplash.com/photo-1507676184212-d03ab07a01bf?w=800&q=80"
    elif any(k in text_to_check for k in ["museum", "gallery", "art", "exhibit", "culture"]):
        fallback_url = "https://images.unsplash.com/photo-1554907984-15263bfd63bd?w=800&q=80"
    elif any(k in text_to_check for k in ["park", "garden", "outdoor", "nature", "trail", "hiking"]):
        fallback_url = "https://images.unsplash.com/photo-1459749411175-04bf5292ceea?w=800&q=80"
    elif any(k in text_to_check for k in ["restaurant", "dining", "food", "bistro", "kitchen", "eatery"]):
        fallback_url = "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?w=800&q=80"
    elif any(k in text_to_check for k in ["bowling", "escape room", "arcade", "entertainment", "activity"]):
        fallback_url = "https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?w=800&q=80"
    else:
        fallback_url = "https://images.unsplash.com/photo-1492684223066-81342ee5ff30?w=800&q=80"

    img_url = spot.get('photo_url') or fallback_url

    # Tag pills
    tags_html = ""
    matched_tags = spot.get('matched_tags')
    if matched_tags:
        if isinstance(matched_tags, str):
            matched_tags = [t.strip() for t in matched_tags.split(',') if t.strip()]
        for tag in matched_tags:
            tags_html += f'<span class="wc-tag">✓ {tag}</span>'

    tier_name = spot.get('tier_name', 'Top Pick')
    category  = spot.get('category', '')
    vibe      = spot.get('vibe_check', '')
    address   = spot.get('address', '')
    pitch     = spot.get('why_its_perfect', '')

    # Utility row links
    share_text     = f"Let's go to {spot['name']}! {address}\n{map_url}"
    share_encoded  = urllib.parse.quote(share_text)
    share_subj_enc = urllib.parse.quote(f"Wild Plan: {spot['name']}")
    share_body_enc = urllib.parse.quote(share_text)
    sep = '<span class="wc-util-sep">|</span>'
    website_part = f'<a href="{spot["website"]}" target="_blank" class="wc-util-link">🌐 Website</a>{sep}' if spot.get('website') else ''
    utility_html = (
        f'<div class="wc-utility">'
        f'{website_part}'
        f'<a href="{map_url}" target="_blank" class="wc-util-link">🗺️ Directions</a>{sep}'
        f'<a href="{uber_url}" target="_blank" class="wc-util-link">🚗 Uber</a>{sep}'
        f'<a href="sms:?body={share_encoded}" class="wc-util-link">📱 Text</a>{sep}'
        f'<a href="mailto:?subject={share_subj_enc}&body={share_body_enc}" class="wc-util-link">📧 Email</a>'
        f'</div>'
    )

    # GET WILD: inject anchor + green glow CSS targeting the native border wrapper
    if mode == "get_wild":
        st.markdown(
            '<style>'
            'div:has(#wca-wild)+[data-testid="stVerticalBlockBorderWrapper"]{'
            'border-color:#2d6a4f!important;'
            'box-shadow:0 0 20px rgba(45,106,79,0.4),0 0 40px rgba(45,106,79,0.2)!important;'
            'animation:wildGlow 3s ease-in-out infinite!important;'
            '}'
            '</style>'
            '<p style="color:#2d6a4f;font-weight:700;font-size:1.05rem;margin:8px 0 4px 0;">🎲 Your Wild Adventure Awaits</p>'
            '<div id="wca-wild"></div>',
            unsafe_allow_html=True
        )

    html_card = f"""<div class="wc-shell">
  <div class="wc-img-wrap">
    <img src="{img_url}" class="wc-img" alt="">
    <div class="wc-tier">✦ {tier_name}</div>
  </div>
  <div class="wc-body">
    <div class="wc-name">{title_prefix} {spot['name']}</div>
    <div class="wc-meta">{category} • ✨ {vibe}</div>
    <div class="wc-address">📍 {address}</div>
    {utility_html}
    <hr class="wc-hr">
    <p class="wc-pitch">{pitch}</p>
    <div class="wc-tags">{tags_html}</div>
  </div>
</div>
"""
    with st.container(border=True):
        st.markdown(html_card, unsafe_allow_html=True)
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("⭐ Save", key=f"save_{index}_{spot['name']}", use_container_width=True, help="Save for later"):
                save_spot_to_db(user_id, spot['name'], spot['address'], spot.get('category', 'Top Pick'))
        with col2:
            if st.button("✅ I'm Going", key=f"going_{index}_{spot['name']}", use_container_width=True, type="primary", help="Mark as chosen"):
                save_spot_to_db(user_id, spot['name'], spot['address'], spot.get('category', 'Top Pick'), notes="chosen")
        with col3:
            if st.button("👎 Not for me", key=f"nope_{index}_{spot['name']}", use_container_width=True, help="Never suggest this again"):
                save_spot_to_db(user_id, spot['name'], spot['address'], spot.get('category', 'Top Pick'), rating=1, notes="Blacklisted via quick-button.")

# ==========================================
# 5. ASYNC DATA GATHERER
# ==========================================
async def gather_all_data(lat, lng, semantic_query, distance, location_input, intended_time, group_type, target_date_str, relative_day, user_id):
    async def _events_with_timeout():
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(fetch_live_events, location_input or "nearby", intended_time, group_type, target_date_str, relative_day, lat, lng),
                timeout=3.0
            )
        except (asyncio.TimeoutError, Exception):
            return []

    weather_task   = asyncio.to_thread(get_live_weather, lat, lng)
    places_task    = asyncio.to_thread(fetch_places_semantic, semantic_query, lat, lng, distance)
    excluded_task  = asyncio.to_thread(get_excluded_spots, user_id)
    favorites_task = asyncio.to_thread(get_favorite_spots, user_id)
    return await asyncio.gather(weather_task, places_task, _events_with_timeout(), excluded_task, favorites_task)

# ==========================================
# 6. UI ROUTING
# ==========================================
st.markdown("""
<div class="hero-header">
    <h1 class="hero-title">Get Wild</h1>
    <p class="hero-subtitle">Disconnect. Explore. Connect.</p>
</div>
""", unsafe_allow_html=True)

if st.session_state.user is None:
    st.write("---")
    st.subheader("Welcome to the Wild.")
    
    tab_login, tab_signup = st.tabs(["Log In", "Sign Up"])
    with tab_login:
        with st.form("login_form"):
            email_login = st.text_input("Email")
            password_login = st.text_input("Password", type="password")
            if st.form_submit_button("Log In", type="primary", use_container_width=True):
                try:
                    res = supabase.auth.sign_in_with_password({"email": email_login, "password": password_login})
                    st.session_state.user = res.user
                    st.rerun()
                except Exception as e: st.error("Login failed. Check your credentials.")

    with tab_signup:
        with st.form("signup_form"):
            email_signup = st.text_input("Email (New Account)")
            password_signup = st.text_input("Password (New Account)", type="password")
            if st.form_submit_button("Sign Up", type="primary", use_container_width=True):
                try:
                    res = supabase.auth.sign_up({"email": email_signup, "password": password_signup})
                    st.session_state.user = res.user
                    st.rerun()
                except Exception as e: st.error(f"Signup failed: {e}")

else:
    tab_explore, tab_profile, tab_saved = st.tabs(["🌍 Explore", "👤 My Profile", "⭐ Saved Spots"])

    with tab_explore:
        user_profile = get_profile(st.session_state.user.id)
        
        # --- SCREEN 1: THE INPUT FORM ---
        if not st.session_state.search_active:
            st.subheader("Where are we going?")
            loc_col1, loc_col2 = st.columns([5, 1])
            
            with loc_col1: 
                ui_loc = st.text_input("Location", value=st.session_state.mem_loc, placeholder="Enter City or ZIP Code", label_visibility="collapsed")
            with loc_col2: 
                geo_data = streamlit_geolocation()

            if geo_data and geo_data.get('latitude') is not None:
                st.session_state.mem_gps_active = True
                st.session_state.mem_geo_data = geo_data
                st.session_state.mem_loc = "" 

            if st.session_state.mem_gps_active:
                st.success("🌿 GPS Locked!")

            st.write("---")
            st.subheader("What's the plan?")

            col_day, col_time = st.columns(2)
            day_index = 0 if st.session_state.mem_day == "☀️ Today" else 1
            time_index = 0 if st.session_state.mem_time == "☀️ Daytime" else 1
            
            with col_day: 
                ui_day = st.radio("Day", ["☀️ Today", "📅 Tomorrow"], index=day_index, horizontal=True, label_visibility="collapsed")
            with col_time: 
                ui_time = st.radio("Time", ["☀️ Daytime", "🌙 Night"], index=time_index, horizontal=True, label_visibility="collapsed")
            
            intended_time = f"{ui_day} ({ui_time})"

            st.write("") 
            col_group, col_vibe = st.columns(2)
            
            group_options = ["Date", "Family Outing", "Friends", "Solo"]
            with col_group: 
                ui_group = st.selectbox("Who is going?", group_options, index=group_options.index(st.session_state.mem_group))
            
            vibe_options = ["Doesn't Matter", "Outside", "Inside"]
            with col_vibe: 
                ui_vibe = st.radio("Setting?", vibe_options, index=vibe_options.index(st.session_state.mem_vibe), horizontal=True)
            
            st.write("") 
            col_food, col_dist = st.columns(2)
            
            food_options = ["Full Meal", "Just Drinks/Coffee", "No Food Needed"]
            with col_food: 
                ui_food = st.selectbox("Sustenance?", food_options, index=food_options.index(st.session_state.mem_food))
            with col_dist: 
                ui_dist = st.slider("Max Distance (Miles)", 1, 20, st.session_state.mem_dist)

            with st.expander("Need something specific? (Optional)", expanded=False):
                ui_spec = st.text_input("Keyword", value=st.session_state.mem_spec, placeholder="e.g., 'romantic', 'live jazz', 'large group'", label_visibility="collapsed")

            st.write("---")
            
            btn_col1, btn_col2 = st.columns(2)
            with btn_col1: top_3_clicked = st.button("🌟 Top 3 Recommendations", use_container_width=True)
            with btn_col2: get_wild_clicked = st.button("🎲 GET WILD", type="primary", use_container_width=True)

            wild_count = get_wild_count_today()
            if wild_count is not None and wild_count > 0:
                st.markdown(f"<div style='text-align:center;color:#e65100;font-weight:600;font-size:0.9rem;margin-top:4px;'>🔥 {wild_count} {'person' if wild_count == 1 else 'people'} got wild today — join them</div>", unsafe_allow_html=True)

            if top_3_clicked or get_wild_clicked:
                if not ui_loc and not st.session_state.mem_gps_active:
                    st.warning("Please enter a location or click the GPS icon first!")
                else:
                    st.session_state.mem_loc = ui_loc
                    st.session_state.mem_day = ui_day
                    st.session_state.mem_time = ui_time
                    st.session_state.mem_group = ui_group
                    st.session_state.mem_vibe = ui_vibe
                    st.session_state.mem_food = ui_food
                    st.session_state.mem_dist = ui_dist
                    st.session_state.mem_spec = ui_spec
                    
                    st.session_state.current_mode = "get_wild" if get_wild_clicked else "top_3"
                    st.session_state.filters_dict = {
                        "group": ui_group, "time": intended_time, 
                        "vibe": ui_vibe, "food": ui_food, 
                        "specific": ui_spec
                    }
                    st.session_state.search_active = True
                    st.session_state.trigger_fetch = True
                    st.session_state.session_seen_spots = []
                    city = "Nearby" if st.session_state.mem_gps_active else (ui_loc.split()[0].rstrip(',') if ui_loc else "Unknown")
                    if get_wild_clicked:
                        increment_wild_counter(city)
                    st.rerun()

        # --- SCREEN 2: THE RESULTS & LOADER ---
        else:
            scroll_to_top()
            
            if st.button("← Start a Fresh Search"):
                st.session_state.search_active = False
                st.session_state.current_results = None
                st.session_state.session_seen_spots = []
                st.rerun()
                
            if st.session_state.trigger_fetch:
                st.session_state.trigger_fetch = False
                st.session_state.fetch_timed_out = False

                status_loader = st.empty()
                status_loader.info("📍 Locking in coordinates...")
                
                try:
                    location_context = st.session_state.mem_loc

                    if st.session_state.mem_gps_active and st.session_state.mem_geo_data:
                        lat, lng = st.session_state.mem_geo_data['latitude'], st.session_state.mem_geo_data['longitude']
                        location_context = "exact GPS coordinates"
                    else:
                        lat, lng = get_coordinates(st.session_state.mem_loc)

                    if lat is None:
                        status_loader.error("Couldn't find that location.")
                    else:
                        target_date_str, relative_day = get_local_target_date(lat, lng, st.session_state.mem_day)
                        semantic_query = build_semantic_query(st.session_state.filters_dict, user_profile)

                        status_loader.info("☁️ Curating local weather, places, and events...")
                        def _run_gather():
                            return gather_all_data(
                                lat, lng, semantic_query, st.session_state.mem_dist, location_context,
                                st.session_state.filters_dict['time'], st.session_state.filters_dict['group'],
                                target_date_str, relative_day, st.session_state.user.id
                            )
                        try:
                            weather_report, raw_places, live_events_data, db_excluded, user_favorites = asyncio.run(_run_gather())
                        except RuntimeError:
                            import nest_asyncio
                            nest_asyncio.apply()
                            weather_report, raw_places, live_events_data, db_excluded, user_favorites = asyncio.run(_run_gather())

                        if st.session_state.current_mode == "get_wild":
                            status_loader.info("🎲 Loading up your adventure and revealing the spontaneity...")
                        else:
                            status_loader.info("🗺️ Assembling your perfect itinerary...")

                        all_excluded = list(set((db_excluded or []) + st.session_state.session_seen_spots))
                        user_favorites = user_favorites or []

                        cache_key = generate_cache_key(
                            st.session_state.filters_dict, location_context,
                            target_date_str, st.session_state.current_mode
                        )
                        cached_result = None
                        try:
                            cutoff = (datetime.utcnow() - timedelta(hours=2)).isoformat()
                            rows = supabase.table('recommendation_cache').select('result_json').eq('cache_key', cache_key).gte('created_at', cutoff).limit(1).execute()
                            if rows.data:
                                cached_result = json.loads(rows.data[0]['result_json'])
                        except:
                            pass

                        if cached_result and not st.session_state.get('skip_cache', False):
                            st.session_state.current_results = cached_result
                        else:
                            st.session_state.skip_cache = False
                            selected_tiers = random.sample(TIER_PERSONALITIES, 3) if st.session_state.current_mode != "get_wild" else None
                            ai_results = get_ai_recommendations(
                                raw_places, live_events_data, weather_report,
                                st.session_state.filters_dict, location_context,
                                target_date_str, relative_day, user_profile, all_excluded,
                                user_favorites, mode=st.session_state.current_mode,
                                tier_personalities=selected_tiers,
                                lat=lat, lng=lng, radius_miles=st.session_state.mem_dist
                            )
                            match_photos_to_results(ai_results.get('recommendations', []), raw_places)
                            st.session_state.current_results = ai_results
                            try:
                                supabase.table('recommendation_cache').insert({
                                    'cache_key': cache_key,
                                    'result_json': json.dumps(st.session_state.current_results),
                                    'created_at': datetime.utcnow().isoformat()
                                }).execute()
                            except:
                                pass

                        for rec in st.session_state.current_results.get("recommendations", []):
                            st.session_state.session_seen_spots.append(rec['name'])

                        if st.session_state.current_mode == "get_wild":
                            status_loader.success("✅ Adventure Ready!")
                        else:
                            status_loader.success("✅ Itinerary Ready!")
                except Exception as e:
                    if isinstance(e, TimeoutError):
                        status_loader.error("Taking longer than usual, please try again.")
                        st.session_state.fetch_timed_out = True
                    else:
                        status_loader.error(f"Error connecting to the wild. Try again! ({type(e).__name__})")

            if st.session_state.fetch_timed_out:
                def _retry():
                    st.session_state.fetch_timed_out = False
                    st.session_state.trigger_fetch = True
                st.button("🔄 Try Again", on_click=_retry, type="primary", key="retry_timeout_btn")

            if st.session_state.current_results:
                st.write("---")
                results = st.session_state.current_results
                mode = st.session_state.current_mode
                
                # --- PYDECK INTERACTIVE MAP WITH HOVER TOOLTIPS ---
                map_data = []
                for i, spot in enumerate(results.get("recommendations", [])):
                    if spot.get('lat') and spot.get('lng'):
                        display_name = f"{i+1}. {spot['name']}" if mode == "top_3" else f"🎲 {spot['name']}"
                        spot_search = urllib.parse.quote(f"{spot['name']} {st.session_state.mem_loc}")
                        spot_map_url = f"https://www.google.com/maps/search/?api=1&query={spot_search}"
                        map_data.append({"lat": spot['lat'], "lon": spot['lng'], "name": display_name, "map_url": spot_map_url})
                
                if map_data:
                    with st.expander("🗺️ View on Map"):
                        layer = pdk.Layer(
                            'ScatterplotLayer',
                            data=map_data,
                            get_position='[lon, lat]',
                            get_color='[255, 75, 75, 200]',
                            get_radius=250,
                            pickable=True,
                        )
                        view_state = pdk.ViewState(latitude=map_data[0]['lat'], longitude=map_data[0]['lon'], zoom=12)
                        st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip={"html": "<b>{name}</b>"}))
                        num_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
                        map_btn_cols = st.columns(len(map_data))
                        for i, (col, item) in enumerate(zip(map_btn_cols, map_data)):
                            with col:
                                emoji = num_emojis[i] if i < len(num_emojis) else f"{i+1}."
                                st.link_button(f"{emoji} Open in Maps", item['map_url'], use_container_width=True)
                
                # --- RENDER CARDS ---
                for index, spot in enumerate(results.get("recommendations", [])):
                    render_spot_card(spot, st.session_state.mem_loc, st.session_state.user.id, index + 1, mode)
                    
                # --- SHUFFLE BUTTON (ONLY IN TOP 3 MODE) ---
                if mode == "top_3":
                    st.write("---")
                    if st.button("🔀 Shuffle", use_container_width=True):
                        st.session_state.trigger_fetch = True
                        st.session_state.skip_cache = True
                        st.rerun()

    # ----------------------------------------
    # TAB 2 & 3: PROFILE & SAVED SPOTS 
    # ----------------------------------------
    with tab_profile:
        current_prof = get_profile(st.session_state.user.id) or {}
        st.markdown(f"### 🏆 Get Wild Tally: **{current_prof.get('wild_tally', 0)}**")
        st.write("Save spots to increase your tally and build your exploration streak!")
        st.write("---")
        st.subheader("Personalize Your Profile")
        st.write("Set your baseline preferences so the app learns how you like to explore.")
        
        with st.form("profile_form"):
            fname = st.text_input("First Name", value=current_prof.get('first_name', ''))
            pname = st.text_input("Partner/Spouse Name (Optional)", value=current_prof.get('partner_name', ''))
            stroller = st.checkbox("Require Stroller Accessibility", value=current_prof.get('needs_stroller_access', False))
            dog = st.checkbox("Require Dog-Friendly Patios", value=current_prof.get('needs_dog_friendly', False))
            vibe_pref = st.text_area("What is your ideal aesthetic? (e.g., 'Warm, modern, naturalistic')", value=current_prof.get('vibe_preference', ''))
            alcohol_choice = st.radio("Alcohol Preference", ["Drinks Alcohol", "Non-Alcoholic Only"],
                index=1 if current_prof.get('needs_nonalcoholic', False) else 0)
            dietary_options = ["Vegan", "Vegetarian", "Gluten-Free", "Nut Allergy", "Halal", "Kosher"]
            current_dietary = [r.strip() for r in current_prof.get('dietary_restrictions', '').split(',') if r.strip()]
            dietary = st.multiselect("Dietary Restrictions", dietary_options, default=[d for d in current_dietary if d in dietary_options])

            if st.form_submit_button("Save Profile", type="primary"):
                supabase.table('user_profiles').upsert({
                    'id': st.session_state.user.id, 'first_name': fname, 'partner_name': pname,
                    'needs_stroller_access': stroller, 'needs_dog_friendly': dog, 'vibe_preference': vibe_pref,
                    'needs_nonalcoholic': alcohol_choice == "Non-Alcoholic Only",
                    'dietary_restrictions': ', '.join(dietary)
                }).execute()
                st.success("Your preferences have been locked in.")
                
        st.write("---")
        if st.button("🚪 Log Out", type="secondary"):
            supabase.auth.sign_out()
            st.session_state.user = None
            st.session_state.current_results = None
            st.session_state.session_seen_spots = []
            st.session_state.search_active = False
            st.session_state.trigger_fetch = False
            st.rerun()

    with tab_saved:
        st.subheader("Your Adventure Ledger")
        st.write("Rate your past spots. Spots rated 1-star will NEVER be recommended again.")
        # Always re-fetch fresh from Supabase — no caching
        st.session_state.saved_spots_dirty = False
        res = supabase.table('saved_spots').select('*').eq('user_id', st.session_state.user.id).order('saved_at', desc=True).execute()
        saved_spots = res.data if res.data else []

        if not saved_spots:
            st.info("You haven't saved any spots yet. Go explore!")
        else:
            # Rating nudge for spots marked "I'm Going" but not yet rated
            try:
                cutoff = (datetime.utcnow() - timedelta(hours=12)).isoformat()
                nudge_res = supabase.table('saved_spots').select('*')\
                    .eq('user_id', st.session_state.user.id)\
                    .eq('user_notes', 'chosen')\
                    .is_('rating', 'null')\
                    .lt('saved_at', cutoff)\
                    .execute()
                nudge_spots = nudge_res.data if nudge_res.data else []
            except:
                nudge_spots = []
            nudge_ids = {n['id'] for n in nudge_spots}

            for saved in saved_spots:
                if saved['id'] in nudge_ids:
                    st.markdown(
                        '<div style="border-left:4px solid #f4a261;border-radius:6px;padding:8px 12px;background:#fff8f0;margin-bottom:4px;">'
                        f'⭐ <b>How was your visit to {saved["spot_name"]}?</b> Tap to rate</div>',
                        unsafe_allow_html=True
                    )
                icon = "🚫" if saved['rating'] == 1 else "📍"
                with st.expander(f"{icon} {saved['spot_name']}"):
                    st.caption(saved['address'])

                    with st.form(f"rate_form_{saved['id']}"):
                        _star_opts = ["★", "★★", "★★★", "★★★★", "★★★★★"]
                        current_rating = saved['rating'] if saved['rating'] else 3
                        new_rating_stars = st.select_slider("Rate this spot (★ = Blacklist)", options=_star_opts, value=_star_opts[current_rating - 1])
                        new_rating = _star_opts.index(new_rating_stars) + 1
                        notes = st.text_input("Private Notes", value=saved.get('user_notes', ''))

                        if st.form_submit_button("Update Feedback", type="primary"):
                            supabase.table('saved_spots').update({'rating': new_rating, 'user_notes': notes}).eq('id', saved['id']).execute()
                            st.success("Feedback saved!")
                            st.session_state.saved_spots_dirty = True
                            st.rerun()

                    if st.button("🗑️ Delete Spot", key=f"del_{saved['id']}"):
                        if delete_spot_from_db(saved['id']):
                            st.session_state.saved_spots_dirty = True
                            st.rerun()